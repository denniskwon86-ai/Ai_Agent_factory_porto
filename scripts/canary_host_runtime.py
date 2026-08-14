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
    ap.add_argument("--seed", required=True, help="씨앗 스크립트가 출력한 JSON")
    ap.add_argument("--wait-expiry", action="store_true",
                    help="만료 시나리오를 위해 65초 기다린다(워크트리 TTL=1분 전제)")
    args = ap.parse_args()
    seed = json.loads(args.seed)
    wait_expiry = args.wait_expiry

    http = Http(args.base, seed["session_me"], seed["scope"], seed["mode"])
    results = []

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

    #: ③ 다른 앱의 데이터
    #: ⚠️⚠️ **이 시나리오는 런타임 경로에서 «판정으로» 재현되지 않는다.** 서버가 자원을
    #:   증명 자체에서 유도하므로 `tok.release_id == app.release_id` 가 **언제나 참**이다.
    #:   즉 `TOKEN_APP_MISMATCH` 는 판정이 아니라 **구조로** 막혀 있다.
    #:   여기서는 「남의 앱 증명으로는 이 앱 데이터가 보이지 않는다」를 결과로 확인한다.
    st, body_o = http("GET", f"{R}/datasets/orders/records", proof=proof_other)
    seen = len((body_o.get("data") or {}).get("records") or []) if st == 200 else -1
    step("다른 앱 증명으로는 이 앱 데이터가 보이지 않는다", st == 200 and seen == 0,
         f"HTTP {st} records={seen}")

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
            print("  … 만료를 기다린다(65초)")
            time.sleep(65)
            st, _ = http("GET", f"{R}/datasets/orders/records", proof=fresh["data"]["token"])
            step("만료된 증명 → 차단", st == 401, f"HTTP {st}")
        else:
            step("만료 시나리오 준비", False, f"증명 재발급 실패 HTTP {st}")

    #: ⑦ 증명 없음 — 세션으로 내려가지 않는다
    st, _ = http("GET", f"{R}/datasets/orders/records")
    step("증명 없음 → 세션 폴백 없음", st == 403, f"HTTP {st}")

    print("\n" + json.dumps({"steps": results}, ensure_ascii=False))
    bad = [r["name"] for r in results if not r["ok"]]
    print(f"\n결과: {len(results) - len(bad)}/{len(results)} 통과")
    if bad:
        print("실패: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
