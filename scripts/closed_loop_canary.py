"""[CL-5] 폐루프 카나리 — **동작하는 서버에 대고 한 바퀴 돌린다.**

작업서 §11-6: "기존 기능 회귀 + 실제 회사 문맥 과업 1회".

## 왜 pytest 로 충분하지 않은가

pytest 는 모듈을 직접 부른다. 그래서 **라우터·의존성·직렬화·원장 허용목록·SSE 배선**을 지나가지
않는다. 2026-08-04 에 실제로 그 틈에서 사고가 났다 — 발간 단위 테스트 33건이 전부 통과했는데
화면에서 첫 요청이 500 으로 죽었다(`PUBLICATION_CREATED` 가 원장에 등록돼 있지 않았다).
가짜 원장이 진짜보다 관대했기 때문이다.

★ 그래서 이 스크립트는 **HTTP 로만** 말한다. import 하지 않는다.

## 판정 규칙

- `PASS` 는 확인한 것에만 쓴다.
- `SKIP` 은 **이유와 함께** 남긴다. 확인하지 못한 것을 통과로 세면 카나리는 거짓말이 된다.
- 하나라도 `FAIL` 이면 종료 코드가 1 이다.

## 예시 계정

★★ 실측 계정은 `hikwon@lsmnm.com` **하나만** 쓴다. 임의 계정을 만들지 않는다(실제 인원과 충돌).
  그래서 두 사람이 필요한 CL-1 수락 경로는 여기서 `SKIP` 이고, 대신 **격리 검사**(자기 전달
  거절 · 남의 요청 404 · 내 수신함만)를 확인한다.

사용법:
    venv\\Scripts\\python.exe scripts/closed_loop_canary.py --base-url http://127.0.0.1:8080
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Canary:
    def __init__(self, base_url: str, user: str, other_user: str):
        self.base = base_url.rstrip("/")
        self.user = user
        # ⚠️ 이 값으로 **아무것도 만들지 않는다.** 격리 검사(남의 것은 404)에만 쓰는 주소다.
        self.other = other_user
        self.results: List[Tuple[str, str, str]] = []
        self.created: Dict[str, str] = {}

    # ── HTTP ─────────────────────────────────────────────────────────────
    def call(self, method: str, path: str, body: Optional[dict] = None,
             as_user: Optional[str] = None) -> Tuple[int, Any]:
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Factory-User", self.user if as_user is None else as_user)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return e.code, {"detail": raw[:300]}
        except Exception as e:
            return 0, {"detail": f"{type(e).__name__}: {e}"}

    # ── 판정 ─────────────────────────────────────────────────────────────
    def check(self, name: str, ok: bool, note: str = "") -> bool:
        self.results.append((PASS if ok else FAIL, name, note))
        print(f"  {'✓' if ok else '✗'} {name}" + (f" — {note}" if note else ""))
        return ok

    def skip(self, name: str, why: str) -> None:
        """★ 건너뛴 것을 통과로 세지 않는다. 이유 없이 건너뛰지도 않는다."""
        self.results.append((SKIP, name, why))
        print(f"  – {name} — 건너뜀: {why}")

    # ── 단계 ─────────────────────────────────────────────────────────────
    def stage_identity(self) -> bool:
        print("\n[0] 식별과 권한")
        s, j = self.call("GET", "/api/v1/org/me")
        ok = self.check("사용자 식별", s == 200, f"HTTP {s}")
        if ok:
            me = (j or {}).get("data") or {}
            self.check("실측 계정이 하나로 고정됨", str(me.get("user_id", "")) == self.user,
                       f"user_id={me.get('user_id')}")
        # ★ 식별하지 않으면 협업 API 는 401 이어야 한다 — 익명으로 남의 결정을 볼 수 없다.
        s2, _ = self.call("GET", "/api/v1/decisions/queue", as_user="")
        self.check("익명 요청은 401", s2 == 401, f"HTTP {s2}")
        return ok

    def stage_cl1_isolation(self) -> None:
        print("\n[1] CL-1 앱 전달 — 격리")
        # 두 사람이 필요한 수락 경로는 계정을 지어내야 하므로 하지 않는다.
        self.skip("전달→수락→내 앱 전체 경로",
                  f"두 번째 실제 사용자가 필요합니다. 실측 계정은 {self.user} 하나뿐이며 "
                  f"임의 계정을 만들지 않습니다(팀 규약).")
        s, j = self.call("POST", "/api/v1/app-deliveries",
                         {"release_id": "canary", "recipient_user_id": self.user,
                          "purpose": "카나리 자기 전달 거절 확인"})
        self.check("자기 자신에게 전달은 거절", s == 400,
                   f"HTTP {s} · {(j or {}).get('detail', '')[:60]}")
        s, j = self.call("GET", "/api/v1/app-deliveries/dlv_does_not_exist")
        self.check("없는 전달은 404(403 이 아니다)", s == 404, f"HTTP {s}")
        s, j = self.call("GET", "/api/v1/app-deliveries/inbox")
        if s == 200:
            rows = (j or {}).get("data") or []
            mine = all(r.get("recipient_user_id") == self.user for r in rows)
            self.check("수신함에 내 것만 있다", mine, f"{len(rows)}건")
        else:
            self.check("수신함 조회", False, f"HTTP {s}")

    def stage_cl2(self) -> None:
        print("\n[2] CL-2 Decision Package — 한 문서 · 세 관점 · 결정 차단")
        s, j = self.call("POST", "/api/v1/simulations/canary_run/decision-cases", {
            "question": "[카나리] 정련 가동률 상향안을 승인할 것인가",
            "record_purpose": "VALIDATION",
            "baseline_id": "BL-CANARY",
            "package": {"baseline": "무행동 시 변화 없음",
                        "options": ["A안 상향", "B안 단계 상향", "C안 유지"]},
            "evidence": {"가동률 실적": {"value": "78.3%", "verified": True}},
        })
        if not self.check("안건 생성", s == 200, f"HTTP {s} · {(j or {}).get('detail','')[:80]}"):
            return
        did = j["data"]["decision_id"]
        self.created["decision_id"] = did

        s, j = self.call("POST", f"/api/v1/decisions/{did}/generate-views")
        if self.check("세 관점 렌더링", s == 200, f"HTTP {s}"):
            d = j["data"]
            # ★ 세 관점이 같은 문서라는 **증거**. 이것이 깨지면 참석자들이 서로 다른 숫자를 본다.
            self.check("세 관점이 같은 package_version·evidence_hash",
                       d.get("same_package") is True,
                       f"v{d.get('package_version')} · {str(d.get('evidence_hash'))[:12]}")
            reqs = d["views"]["requester"]["sections"]
            self.check("미작성 항목이 숨겨지지 않고 표시된다",
                       any(x.get("missing") for x in reqs),
                       f"미작성 {sum(1 for x in reqs if x.get('missing'))}개")

        s, j = self.call("POST", f"/api/v1/decisions/{did}/request-review",
                         {"participants": [{"user_id": self.user, "role": "DECIDER"}]})
        self.check("검토 요청", s == 200, f"HTTP {s}")

        # ★ '정보 부족'은 결정을 **막아야** 한다. 막지 않으면 모르는 채로 승인된다.
        self.call("POST", f"/api/v1/decisions/{did}/participant-response",
                  {"response_status": "NEED_INFO", "response": "정비 인력 소요 미확인"})
        s, j = self.call("POST", f"/api/v1/decisions/{did}/decide",
                         {"outcome": "APPROVED", "rationale": "카나리"})
        self.check("정보 부족이 있으면 결정이 막힌다", s == 400,
                   f"HTTP {s} · {(j or {}).get('detail','')[:70]}")

        self.call("POST", f"/api/v1/decisions/{did}/participant-response",
                  {"response_status": "AGREE", "response": "확인"})
        s, j = self.call("POST", f"/api/v1/decisions/{did}/decide",
                         {"outcome": "CONDITIONAL", "rationale": "카나리 조건부 승인"})
        self.check("조건 없는 조건부 승인은 거절", s == 400,
                   f"HTTP {s} · {(j or {}).get('detail','')[:70]}")

        s, j = self.call("POST", f"/api/v1/decisions/{did}/decide",
                         {"outcome": "CONDITIONAL", "rationale": "카나리 조건부 승인",
                          "conditions": "정비 인력 확인 후 착수"})
        self.check("조건을 채우면 결정된다", s == 200 and j["data"]["status"] == "DECIDED",
                   f"HTTP {s}")

        s, j = self.call("POST", f"/api/v1/decisions/{did}/create-actions",
                         {"actions": [{"action": "정비 인력 산정", "owner_user_id": self.user,
                                       "due_at": ""}]})
        self.check("기한 없는 실행과제는 거절", s == 400, f"HTTP {s}")

        s, j = self.call("POST", f"/api/v1/decisions/{did}/create-actions",
                         {"actions": [{"action": "정비 인력 산정", "owner_user_id": self.user,
                                       "due_at": "2026-09-30"}]})
        if self.check("실행과제 생성", s == 200, f"HTTP {s}"):
            aid = j["data"]["actions"][0]["action_id"]
            before = j["data"]["actions"][0]
            self.check("측정 전에는 «미측정»이며 0 이 아니다",
                       before["status"] == "OPEN" and before["measured_effect"] == "",
                       f"status={before['status']} effect={before['measured_effect']!r}")
            s, j = self.call("POST", f"/api/v1/decisions/{did}/measure-effect",
                             {"action_id": aid, "measured_effect": ""})
            self.check("빈 측정값은 0 으로 저장되지 않고 거절", s == 400, f"HTTP {s}")
            s, j = self.call("POST", f"/api/v1/decisions/{did}/measure-effect",
                             {"action_id": aid, "measured_effect": "인력 2명 추가 소요 확인"})
            self.check("효과 측정 기록", s == 200 and j["data"]["status"] == "EFFECT_MEASURED",
                       f"HTTP {s}")

    def stage_cl3(self) -> None:
        print("\n[3] CL-3 대내외 발간 — 이중 승인·게시 실패")
        did = self.created.get("decision_id")
        if not did:
            self.skip("발간 전체 경로", "CL-2 안건이 만들어지지 않아 원천이 없습니다.")
            return
        s, j = self.call("POST", "/api/v1/publications", {
            "title": "[카나리] 정련 가동률 상향 결정 요약", "source_type": "DECISION_CASE",
            "source_id": did, "audience": "EXTERNAL",
            "publication_type": "EXTERNAL_LIMITED", "security_class": "CONFIDENTIAL"})
        if not self.check("대외 발간 초안 생성", s == 200,
                          f"HTTP {s} · {(j or {}).get('detail','')[:80]}"):
            return
        pid = j["data"]["publication_id"]
        self.created["publication_id"] = pid
        self.check("렌더 전에는 발간할 수 없다", j["data"]["can_publish"] is False)

        s, j = self.call("POST", f"/api/v1/publications/{pid}/render")
        if self.check("문서 렌더링", s == 200, f"HTTP {s} · {(j or {}).get('detail','')[:80]}"):
            v = j["data"]["current_version"]
            self.check("발간본에 원천 근거 지문이 실린다",
                       bool(v and v.get("evidence_hash")), str(v and v.get("evidence_hash"))[:16])

        s, j = self.call("POST", f"/api/v1/publications/{pid}/request-approval",
                         {"review_types": []})
        if self.check("검토 요청", s == 200, f"HTTP {s}"):
            types = {r["review_type"] for r in j["data"]["reviews"]}
            # ★ 요청자가 법무 검토를 빼는 것을 허용하지 않는다.
            self.check("대외는 임원·법무 검토가 자동 포함",
                       {"EXECUTIVE", "LEGAL_DISCLOSURE"} <= types, str(sorted(types)))

        self.call("POST", f"/api/v1/publications/{pid}/approve",
                  {"review_type": "EXECUTIVE", "status": "APPROVED"})
        # ★★★ 작업서 §10-8. 화면 버튼이 아니라 **API 가** 막아야 한다.
        s, j = self.call("POST", f"/api/v1/publications/{pid}/publish",
                         {"targets": [{"target": "canary", "channel": "TEST"}]})
        self.check("단일 승인으로는 대외 발간이 API 에서 막힌다", s == 400,
                   f"HTTP {s} · {(j or {}).get('detail','')[:70]}")

        self.call("POST", f"/api/v1/publications/{pid}/approve",
                  {"review_type": "LEGAL_DISCLOSURE", "status": "APPROVED"})
        s, j = self.call("POST", f"/api/v1/publications/{pid}/publish",
                         {"targets": [{"target": "canary", "channel": "TEST"}]})
        if self.check("이중 승인 후 발간 요청은 통과", s == 200, f"HTTP {s}"):
            d = j["data"]
            # ★★★ 작업서 §10-9. 어댑터가 없으므로 게시는 실패해야 하고, 실패는 성공으로
            #   저장되면 안 된다 — 아무 데도 안 나간 문서를 «발간됨»으로 믿는 것이 사고다.
            dist = d.get("distributions") or []
            self.check("게시 어댑터가 없으면 배포는 «실패»로 기록",
                       any(x["status"] == "FAILED" for x in dist), f"{len(dist)}건")
            self.check("게시 실패 시 PUBLISHED 로 올리지 않는다", d["status"] == "APPROVED",
                       f"status={d['status']}")
            self.check("실패 사실을 사용자에게 말한다", bool(d.get("note")),
                       str(d.get("note", ""))[:60])

    def stage_cl4(self) -> None:
        print("\n[4] CL-4 알림 격리 — 내 것만 온다")
        seen: "queue.Queue[Tuple[str, str]]" = queue.Queue()

        def listen(as_user: str, tag: str):
            url = f"{self.base}/ws/timeline"
            if as_user:
                url += f"?as_user={urllib.parse.quote(as_user)}"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=12) as r:
                    deadline = time.time() + 8
                    for raw in r:
                        if time.time() > deadline:
                            break
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            d = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if str(d.get("type", "")).startswith(("DECISION_", "PUBLICATION_",
                                                              "APP_")):
                            seen.put((tag, json.dumps(d, ensure_ascii=False)))
            except Exception:
                pass

        threads = [threading.Thread(target=listen, args=(self.user, "mine"), daemon=True),
                   threading.Thread(target=listen, args=(self.other, "other"), daemon=True),
                   threading.Thread(target=listen, args=("", "anon"), daemon=True)]
        for t in threads:
            t.start()
        time.sleep(1.5)   # 구독이 붙을 시간

        s, j = self.call("POST", "/api/v1/simulations/canary_run/decision-cases", {
            "question": "[카나리] 알림 격리 확인용 안건", "baseline_id": "BL-CANARY",
            "record_purpose": "VALIDATION",
            "package": {"baseline": "무행동", "options": ["A", "B"]}, "evidence": {}})
        if s != 200:
            self.check("알림 트리거용 안건 생성", False, f"HTTP {s}")
            return
        did2 = j["data"]["decision_id"]
        s, _ = self.call("POST", f"/api/v1/decisions/{did2}/request-review",
                         {"participants": [{"user_id": self.user, "role": "DECIDER"}]})
        self.check("알림 트리거(검토 요청)", s == 200, f"HTTP {s}")

        for t in threads:
            t.join(timeout=12)
        got: Dict[str, List[str]] = {"mine": [], "other": [], "anon": []}
        while not seen.empty():
            tag, payload = seen.get()
            got[tag].append(payload)

        self.check("참여자 본인은 알림을 받는다", len(got["mine"]) >= 1,
                   f"{len(got['mine'])}건")
        # ★★★ 작업서 §10-11. 이것이 실패하면 CL-4 는 완료가 아니다.
        self.check("다른 사용자에게는 가지 않는다", len(got["other"]) == 0,
                   f"{len(got['other'])}건")
        self.check("익명 구독자에게는 가지 않는다", len(got["anon"]) == 0,
                   f"{len(got['anon'])}건")
        if got["mine"]:
            body = got["mine"][0]
            # ★ 알림이 조회 API 를 대신하면 권한 검사를 우회하는 두 번째 경로가 된다.
            self.check("알림에 문서 본문·참여자 명단이 실리지 않는다",
                       "package" not in body and "participants" not in body,
                       body[:90])

    # ── 보고 ─────────────────────────────────────────────────────────────
    def report(self) -> int:
        p = sum(1 for r in self.results if r[0] == PASS)
        f = sum(1 for r in self.results if r[0] == FAIL)
        k = sum(1 for r in self.results if r[0] == SKIP)
        print("\n" + "=" * 72)
        print(f"카나리 결과 — 통과 {p} · 실패 {f} · 건너뜀 {k}")
        if f:
            print("\n실패 항목:")
            for st, name, note in self.results:
                if st == FAIL:
                    print(f"  ✗ {name} — {note}")
        if k:
            # ★ 건너뛴 것을 조용히 두지 않는다. 확인하지 못한 것은 확인하지 못한 것이다.
            print("\n확인하지 못한 항목(통과가 아니다):")
            for st, name, note in self.results:
                if st == SKIP:
                    print(f"  – {name} — {note}")
        if self.created:
            print(f"\n생성된 실측 데이터: {self.created}")
        print("=" * 72)
        return 1 if f else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="[CL-5] 폐루프 카나리")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--user", default="hikwon@lsmnm.com",
                    help="실측 계정. 팀 규약상 이 하나만 쓴다.")
    ap.add_argument("--other-user", default="canary.not.a.real.account@invalid",
                    help="격리 검사 전용 주소. 이 값으로는 아무것도 만들지 않는다.")
    a = ap.parse_args()

    print(f"[CL-5] 폐루프 카나리 — {a.base_url} · 사용자 {a.user}")
    c = Canary(a.base_url, a.user, a.other_user)
    if not c.stage_identity():
        print("\n서버에 연결하거나 사용자를 식별하지 못했습니다. 서버가 떠 있는지 확인하십시오.")
        return c.report()
    c.stage_cl1_isolation()
    c.stage_cl2()
    c.stage_cl3()
    c.stage_cl4()
    return c.report()


if __name__ == "__main__":
    sys.exit(main())
