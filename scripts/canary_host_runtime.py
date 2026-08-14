"""★★★ [G1-B 4] **격리 카나리 — 실행.** 살아 있는 서버를 실제로 눌러 본다.

교차검토 `[G1-B-I3-REVIEW-82]` 의 카나리 판정:

> 전용 임시 AppData DB·테스트 Release/Ownership/Manifest·`AFS_TEST_SANDBOX`·별도 포트·
> `AFS_SHADOW_RUN` 으로 **6개 작업의 허용/거부와 6개 부정 시나리오**를 실제 Preview 에서
> 수행한다. 운영 DB 쓰기 금지. 카나리 결과는 HTTP 결과와 `policy_shadow.switch_gate(run_id)`
> 를 **함께 대조**하고, **표본 없음은 통과로 세지 않는다.**

## 왜 스크립트인가 — 그리고 무엇을 증명하지 못하는가

이것은 **서버 쪽 종단**을 증명한다: 증명 발급 → 여섯 작업 → 여섯 부정 시나리오 → 게이트 표본.
**증명하지 못하는 것**: iframe 안에서 `window.afs` 가 실제로 도는가. 그것은 브라우저가
필요하고 별도로 확인한다(`docs/handoff` 참조). 여기서 그 둘을 섞어 «전부 검증했다» 고
적지 않는다.

⚠️ 실행 전제: `scripts/canary_host_runtime_seed.py` 를 **격리 워크트리**에서 돌려 두었고,
  그 워크트리에서 백엔드가 떠 있어야 한다. 운영 저장소에는 아무것도 쓰지 않는다.

LLM 0콜.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

R = "/api/v1/appdata/runtime"

#: 게이트가 요구하는 여섯 부정 시나리오 → **그것을 만들 방법**.
#: ★ 라벨은 우리가 붙이지 않는다 — PDP 가 낸 거부 사유에서 읽힌다. 여기서는 «그 판정이
#:   실제로 일어나게 만드는 것» 까지만 한다.
NEGATIVE = (
    "만료된 증명", "다른 세션에서 재사용", "다른 사용자의 증명",
    "다른 앱의 데이터", "다른 조직 범위", "문맥 불일치",
)


class Http:
    def __init__(self, base: str, session: str, scope: str, mode: str):
        self.base, self.session, self.scope, self.mode = base, session, scope, mode

    def __call__(self, method, path, body=None, proof="", scope=None, mode=None, session=None):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Session-Token", session if session is not None else self.session)
        req.add_header("X-Enterprise-Scope", scope if scope is not None else self.scope)
        req.add_header("X-Entity-Mode", mode if mode is not None else self.mode)
        if proof:
            req.add_header("X-App-Proof", proof)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return e.code, {"raw": raw[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8083")
    ap.add_argument("--seed", default="", help="씨앗 스크립트가 출력한 JSON")
    #: ⚠️ 셸 변수로 넘기면 따옴표·인코딩에서 조용히 빈 문자열이 된다(실제로 그렇게 두 번
    #:   헛돌았다). 파일 경로가 안전하다.
    ap.add_argument("--seed-file", default="", help="씨앗 JSON 파일 경로")
    ap.add_argument("--run", default="canary_4", help="AFS_SHADOW_RUN 과 같은 값이어야 한다")
    ap.add_argument("--wait-expiry", action="store_true",
                    help="만료 시나리오를 위해 실제로 기다린다")
    #: ★★★ 기본값이 **실제 만료(15분)+여유** 인 이유: 워크트리의 TTL 상수를 낮추면 구조
    #:   지문이 운영 코드와 달라져 **그 증거가 운영에서 무효**가 된다(그것이 지문의 목적이다).
    #:   빠르게 돌리려면 낮출 수 있지만, 그때 나온 증거는 그 코드에만 유효하다.
    ap.add_argument("--expiry-wait", type=int, default=16 * 60,
                    help="만료 대기 초. 기본은 실제 TTL(15분)+여유")
    args = ap.parse_args()
    if args.seed_file:
        with open(args.seed_file, "r", encoding="utf-8") as f:
            seed = json.load(f)
    elif args.seed.strip():
        seed = json.loads(args.seed)
    else:
        raise SystemExit("--seed 또는 --seed-file 이 필요합니다(빈 값으로 돌면 헛돕니다).")
    wait_expiry = args.wait_expiry

    http = Http(args.base, seed["session_me"], seed["scope"], seed["mode"])
    results = []
    #: 구조 불변식 — 판정으로 관측되지 않는 통제. 결과를 게이트에 **코드 지문과 함께** 남긴다.
    structure = {}

    def step(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": detail})
        print(("  OK  " if ok else "  실패 ") + name + (f"  — {detail}" if detail else ""))

    print("── 준비 ─────────────────────────────────────────────")
    #: 데이터셋은 **관리 API** 로 만든다. 런타임 API 는 데이터셋을 만들지 않는다(사람의 일).
    for rel in ("rel_canary", "rel_canary_ro", "rel_canary_other"):
        st, _ = http("POST", "/api/v1/appdata/datasets", {
            "release_id": rel, "name": "orders",
            "schema": {"fields": [{"name": "qty", "type": "number"}]}})
        #: ⚠️ 다시 돌려도 되게 둔다 — 이미 있으면 400 이고 그것은 실패가 아니다.
        step(f"데이터셋 준비 {rel}", st in (200, 400), f"HTTP {st}")

    print("── 증명 발급 ────────────────────────────────────────")
    st, body = http("POST", f"{R}/proof", {"release_id": "rel_canary"})
    step("증명 발급", st == 200, f"HTTP {st}")
    if st != 200:
        print(json.dumps(body, ensure_ascii=False))
        return 2
    proof = body["data"]["token"]
    step("capability = 선언 ∩ 권한",
         set(body["data"]["capabilities"]) == {"read", "write", "delete"},
         str(body["data"]["capabilities"]))

    st, ro = http("POST", f"{R}/proof", {"release_id": "rel_canary_ro"})
    proof_ro = ro["data"]["token"] if st == 200 else ""
    step("읽기전용 앱은 read 만", st == 200 and ro["data"]["capabilities"] == ["read"],
         str(ro.get("data", {}).get("capabilities")))

    st, other = http("POST", f"{R}/proof", {"release_id": "rel_canary_other"})
    proof_other = other["data"]["token"] if st == 200 else ""
    step("다른 앱 증명 발급", st == 200, f"HTTP {st}")
    #: ★ 대조군 — 공격자 앱이 **자기 데이터셋에는** 쓸 수 있어야 한다. 그렇지 않으면
    #:   아래 주입 시험이 「권한이 없어서 막혔다」와 구분되지 않는다.
    st_w, _own = http("POST", f"{R}/datasets/orders/records", {"payload": {"qty": 7}},
                      proof=proof_other)
    step("공격자 앱은 자기 데이터에는 쓸 수 있다(대조군)", st_w == 200, f"HTTP {st_w}")

    print("── 여섯 작업 · 허용 ─────────────────────────────────")
    st, _ = http("GET", f"{R}/datasets/orders/schema", proof=proof)
    step("data.schema 허용", st == 200, f"HTTP {st}")
    st, made = http("POST", f"{R}/datasets/orders/records", {"payload": {"qty": 1}}, proof=proof)
    step("data.create 허용", st == 200, f"HTTP {st}")
    rid = made.get("data", {}).get("record_id", "")
    st, _ = http("GET", f"{R}/datasets/orders/records", proof=proof)
    step("data.list 허용", st == 200, f"HTTP {st}")
    st, _ = http("GET", f"{R}/datasets/orders/records/{rid}", proof=proof)
    step("data.get 허용", st == 200, f"HTTP {st}")
    st, _ = http("PUT", f"{R}/datasets/orders/records/{rid}", {"payload": {"qty": 2}}, proof=proof)
    step("data.update 허용", st == 200, f"HTTP {st}")
    st, _ = http("DELETE", f"{R}/datasets/orders/records/{rid}", proof=proof)
    step("data.remove 허용", st == 200, f"HTTP {st}")

    print("── 여섯 작업 · 거부 ─────────────────────────────────")
    #: ★ 읽기전용 앱으로 쓰기 계열을 눌러 «거부» 표본을 만든다. 읽기 계열은 아래 부정
    #:   시나리오(다른 사용자·다른 세션 등)에서 거부가 나온다.
    st, made2 = http("POST", f"{R}/datasets/orders/records", {"payload": {"qty": 1}},
                     proof=proof_ro)
    step("data.create 거부(선언 밖)", st == 403, f"HTTP {st}")
    st, _ = http("PUT", f"{R}/datasets/orders/records/none", {"payload": {"qty": 1}},
                 proof=proof_ro)
    step("data.update 거부(선언 밖)", st == 403, f"HTTP {st}")
    st, _ = http("DELETE", f"{R}/datasets/orders/records/none", proof=proof_ro)
    step("data.remove 거부(선언 밖)", st == 403, f"HTTP {st}")

    lib_path = os.path.join(seed["root"], "library", "rel_canary", "release.json")

    print("── 부정 시나리오 여섯 ───────────────────────────────")
    #: ① 다른 사용자의 증명 — **`data.get` 으로** 눌러 그 작업의 거부 표본도 함께 만든다.
    #:   ⚠️ 게이트는 여섯 작업 각각에 허용·거부 **양쪽**을 요구한다. 한 작업만 허용 쪽이
    #:     비면 그 칸은 「안전」이 아니라 「모름」이다(첫 회차에서 `data.get` 이 그랬다).
    st, _ = http("GET", f"{R}/datasets/orders/schema", proof=proof,
                 session=seed["session_other"])
    step("다른 사용자의 증명 → 차단", st == 404, f"HTTP {st}")
    st, _ = http("GET", f"{R}/datasets/orders/records/none", proof=proof,
                 session=seed["session_other"])
    step("다른 사용자의 증명 → data.get 차단", st == 404, f"HTTP {st}")

    #: ② 다른 세션에서 재사용 — 같은 사람, 새 세션
    st, _ = http("GET", f"{R}/datasets/orders/records", proof=proof,
                 session=seed["session_me_2"])
    step("다른 세션에서 재사용 → 차단", st == 404, f"HTTP {st}")

    #: ③ 교차 앱 격리 — **살아 있는 sentinel 로** 본다(구조 불변식 증거)
    #:
    #: ⚠️⚠️ [교차검토 86 ②] 종전에는 A 에서 만든 레코드를 **지운 뒤** B 에서 0건인지 봤다.
    #:   비교 대상이 이미 없으므로 그 0 은 **격리를 증명하지 못한다** — 무엇을 해도 0 이다.
    #:   이제 A 에 sentinel 을 **남겨 두고**, 같은 순간 A 는 보이고 B 는 안 보이는지 본다.
    st, sentinel = http("POST", f"{R}/datasets/orders/records",
                        {"payload": {"qty": 4242}}, proof=proof)
    ok_made = st == 200
    st_a, list_a = http("GET", f"{R}/datasets/orders/records", proof=proof)
    st_b, list_b = http("GET", f"{R}/datasets/orders/records", proof=proof_other)
    rows_a = (list_a.get("data") or {}).get("records") or []
    rows_b = (list_b.get("data") or {}).get("records") or []
    mine = [r for r in rows_a if (r.get("payload") or {}).get("qty") == 4242]
    theirs = [r for r in rows_b if (r.get("payload") or {}).get("qty") == 4242]
    #: ⚠️ 「정확히 1건」이 아니라 「A 에 살아 있고 B 에는 없다」가 성질이다 — 여러 번 돌리면
    #:   sentinel 이 쌓이는데, 그것 때문에 격리 시험이 빨개지면 사람이 시험을 지운다.
    isolated = ok_made and st_a == 200 and st_b == 200 and len(mine) >= 1 and not theirs
    step("교차 앱 격리(살아 있는 sentinel)", isolated,
         f"A={len(rows_a)}건(sentinel {len(mine)}) · B={len(rows_b)}건(sentinel {len(theirs)})")
    structure["교차 앱 블랙박스 시험 통과"] = isolated

    #: ③-b 식별자 주입 — **B 는 쓰기·삭제를 가진 채로** 남의 앱을 말해 본다.
    #: ⚠️ [교차검토 87] B 가 읽기 전용이면 주입이 403 인 것은 «귀속 격리» 가 아니라 단순
    #:   권한 거부다. 「할 수 있는데도 남의 것에는 못 닿는다」여야 격리다.
    sid_rec = (sentinel.get("data") or {}).get("record_id", "")
    injections = [
        ("본문에 릴리스", lambda: http("POST", f"{R}/datasets/orders/records",
                                   {"payload": {"qty": 1}, "release_id": "rel_canary",
                                    "app_id": "proj_canary"}, proof=proof_other)),
        ("payload 안 릴리스", lambda: http("POST", f"{R}/datasets/orders/records",
                                       {"payload": {"qty": 1, "release_id": "rel_canary"}},
                                       proof=proof_other)),
        ("질의 문자열", lambda: http("GET", f"{R}/datasets/orders/records?release_id=rel_canary",
                                proof=proof_other)),
        ("남의 레코드 읽기", lambda: http("GET", f"{R}/datasets/orders/records/{sid_rec}",
                                   proof=proof_other)),
        ("남의 레코드 수정", lambda: http("PUT", f"{R}/datasets/orders/records/{sid_rec}",
                                   {"payload": {"qty": 1}}, proof=proof_other)),
        ("남의 레코드 삭제", lambda: http("DELETE", f"{R}/datasets/orders/records/{sid_rec}",
                                   proof=proof_other)),
    ]
    #: ⚠️ sentinel 이 그대로인 것만으로는 부족하다 — 주입된 **생성**이 A 에 성공하면
    #:   sentinel 은 멀쩡한 채 **새 행이 하나 늘어난다.** 총량도 함께 본다.
    before_n = len(rows_a)
    injected = []
    for label, call in injections:
        st_i, body_i = call()
        leaked = st_i == 200 and "4242" in json.dumps(body_i, ensure_ascii=False)
        injected.append((label, st_i, leaked))

    #: ★★★ 상태코드만 보지 않는다. **A 의 sentinel 이 그대로인지** 본다 —
    #:   「404 를 주고 지우기는 했다」를 놓치지 않기 위해서다.
    st_after, after = http("GET", f"{R}/datasets/orders/records", proof=proof)
    rows_after = (after.get("data") or {}).get("records") or []
    still = [r for r in rows_after
             if (r.get("payload") or {}).get("qty") == 4242 and not r.get("deleted")]
    intact = (st_after == 200 and len(still) == len(mine)
              and len([r for r in rows_after if not r.get("deleted")]) == before_n)
    no_leak = not any(l for _n, _s, l in injected)
    step("공격자(쓰기 가능)가 식별자 주입으로 남의 앱에 닿지 못한다", no_leak and intact,
         " · ".join(f"{n}:{s}{'(누설)' if l else ''}" for n, s, l in injected)
         + f" · A sentinel {len(still)}/{len(mine)}"
         + f" · A 총 {len([r for r in rows_after if not r.get('deleted')])}/{before_n}건"
         + ("" if intact else " ← 변조됨"))
    structure["요청에 app_id·release_id 입력이 없다"] = no_leak
    structure["데이터셋은 증명의 릴리스에 귀속된다"] = no_leak and intact
    structure["레코드는 해결된 데이터셋에 귀속된다"] = no_leak and intact

    #: ④ 다른 조직 범위
    #: ⚠️ 화면이 고른 범위를 바꾸는 것만으로는 **문맥 축**에서 먼저 걸린다(문맥을 확정하지
    #:   못하면 그것이 먼저다). 조직 축 자체를 태우려면 «자원이 다른 범위로 옮겨진» 상태를
    #:   만들어야 한다 — 실제 운영에서 조직 개편이 그것이다.
    with open(lib_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    keep = doc["enterprise_scope_id"]
    doc["enterprise_scope_id"] = "node_elsewhere"
    with open(lib_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    try:
        st, _ = http("GET", f"{R}/datasets/orders/records", proof=proof)
        step("다른 조직 범위 → 차단", st in (403, 404), f"HTTP {st}")
    finally:
        doc["enterprise_scope_id"] = keep
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

    #: ⑤ 문맥 불일치
    #: ⚠️ **헤더를 바꾸는 것으로는 만들 수 없다.** 서버는 실행 모드를 헤더에서 받지 않고
    #:   문맥을 스스로 해석한다 — 그것이 옳다(클라이언트가 자기 문맥을 정하면 그 축은 없다).
    #:   그래서 «자원 쪽» 을 바꾼다: 증명을 받은 뒤 릴리스의 실행 모드를 SIM 으로 돌린다.
    #:   실제 운영에서 이것은 「자료가 다른 문맥으로 옮겨졌다」에 해당한다.
    with open(lib_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    original_mode = doc["entity_mode"]
    doc["entity_mode"] = "SIM"
    with open(lib_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    try:
        st, _ = http("GET", f"{R}/datasets/orders/records", proof=proof)
        step("문맥 불일치 → 차단", st in (403, 404), f"HTTP {st}")
    finally:
        doc["entity_mode"] = original_mode
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

    #: ⑥ 만료된 증명
    #: ⚠️⚠️ 증명 저장소는 **서버 프로세스 메모리**다. 밖에서 만료시킬 방법이 없고, 기본
    #:   만료는 15분이다. 그래서 카나리 워크트리에서만 `DEFAULT_TTL_MINUTES=1` 로 낮추고
    #:   실제로 **기다린다** — 시계를 속이지 않고 만료 판정 그대로를 태운다.
    if wait_expiry:
        st, fresh = http("POST", f"{R}/proof", {"release_id": "rel_canary"})
        if st == 200:
            print(f"  … 만료를 기다린다({args.expiry_wait}초)")
            time.sleep(args.expiry_wait)
            st, _ = http("GET", f"{R}/datasets/orders/records", proof=fresh["data"]["token"])
            step("만료된 증명 → 차단", st == 401, f"HTTP {st}")
        else:
            step("만료 시나리오 준비", False, f"증명 재발급 실패 HTTP {st}")

    #: ⑦ 증명 없음 — 세션으로 내려가지 않는다
    st, _ = http("GET", f"{R}/datasets/orders/records")
    step("증명 없음 → 세션 폴백 없음", st == 403, f"HTTP {st}")

    #: ★ 「릴리스는 증명에서만 유도된다」 — 요청 어디에도 릴리스를 싣지 않았는데 이 앱의
    #:   데이터가 정상으로 오갔다는 사실 자체가 그 증거다.
    structure["릴리스는 증명에서만 유도된다"] = all(
        r["ok"] for r in results if r["name"].startswith("data.") and "허용" in r["name"])

    print("-- 구조 불변식 -----------------------------------")
    for _name, _ok in structure.items():
        print(("  OK  " if _ok else "  실패 ") + _name)
    print("STRUCTURE " + json.dumps(structure, ensure_ascii=False))

    print("\n" + json.dumps({"steps": results}, ensure_ascii=False))
    bad = [r["name"] for r in results if not r["ok"]]
    print(f"\n결과: {len(results) - len(bad)}/{len(results)} 통과")
    if bad:
        print("실패: " + ", ".join(bad))

    # ── 구조 증거 기록 + 최종 판정 ────────────────────────────────────────
    #
    # ★★★ [교차검토 87] 이 둘을 **드라이버 안에서** 한다. 밖에서 손으로 기록하면
    #   「게이트가 열렸다」가 **사람의 절차**에 달리게 되고, 그 절차는 언젠가 빠진다.
    # ⚠️ 그래서 이 스크립트는 **워크트리 안에서** 돌아야 한다 — `core.policy_shadow` 가
    #   그 사본의 DB 를 가리켜야 기록과 판정이 같은 곳을 본다.
    from core.paths import PROJECT_ROOT
    from core.policy_shadow import policy_shadow
    if os.path.basename(PROJECT_ROOT) != "canary_wt":
        print(f"\n⚠️ 격리 워크트리가 아닙니다({PROJECT_ROOT}) — 기록·판정을 생략합니다.")
        return 1 if bad else 0

    for name, ok in structure.items():
        policy_shadow.record_structure(args.run, name, bool(ok))
    g = policy_shadow.switch_gate(args.run)

    print("\n── 전환 게이트 ──────────────────────────────────────")
    print("safe_to_switch:", g["safe_to_switch"])
    print("counts:", json.dumps(g["counts"], ensure_ascii=False))
    print("scenarios:", json.dumps(g["scenario_coverage"], ensure_ascii=False))
    print("structure:", json.dumps(g["structure"], ensure_ascii=False))
    print("code_hash:", g["structure_hash"])
    for b in g["blockers"]:
        print("BLOCK:", b)
    print("\nGATE " + json.dumps(
        {"safe_to_switch": g["safe_to_switch"], "run": args.run,
         "counts": g["counts"], "structure": g["structure"],
         "code_hash": g["structure_hash"]}, ensure_ascii=False))

    #: 하나라도 어긋나면 **실패로 끝낸다** — 초록이 아닌 것을 초록으로 읽지 않게.
    return 0 if (not bad and g["safe_to_switch"]) else 1


if __name__ == "__main__":
    sys.exit(main())
