# -*- coding: utf-8 -*-
"""[DEP-R1] 배포 원장의 **미해결 반례** — 고치지 않고 «다시 돌릴 수 있게» 남긴다.

## 왜 고치지 않았나

독립 검토가 이 상태 기계를 정본과 다르다고 판정했다(과거 계획 되살리기는 수용 불가).
「폐기 예정 상태 기계를 먼저 완성한 뒤 다시 버리는 이중 작업은 하지 않는다」가 지시다.
그래서 **반례를 재현 가능한 형태로 보존**하고, 정본에 맞춘 구현이 나올 때 이것들을
필수 수용 사례로 쓴다.

## 왜 시험(pytest)이 아닌가

- 「지금 동작이 이렇다」를 초록으로 단언하면 **시험이 결함을 지켜 준다.** 고친 날 그
  시험이 빨강이 되고, 누군가 시험을 고칠 것이다.
- 「올바른 동작」을 단언하면 지금은 빨강이다. 고치지 않기로 한 코드를 빨강으로 두면
  묶음 전체가 못 쓰게 된다.
- 그래서 **집계되지 않는 실행 가능한 재현기**로 둔다. 판정은 사람이 읽는다.

## 무엇이 잘못됐나 — 한 줄로

`_transition()` **하나**는 트랜잭션이지만, `promote()`·`rollback()` 은 그것을 **두 번**
부르고 각각 커밋한다. 앞이 성공하고 뒤가 실패하면 «전체 실패» 를 돌려줘도 원장은
이미 바뀌어 있다.

## 정본 구현이 충족해야 할 것

    ① 환경 단위 동시성 통제 아래에서 «현재 포인터 · 새 계획 결과 · 감사 기록» 을
      **한 번에** 갱신한다.
    ② 한 환경에 `PROMOTED` 가 둘일 수 없다.
    ③ 복귀 대상이 부적격이면 **아무것도 기록하지 않는다** — 특히 현재 계획을
      «복귀 완료» 로 적지 않는다.
    ④ DB 트랜잭션이 «외부 트래픽 전환» 까지 원자적으로 만들지는 못한다. 외부 전환과
      DB 기록 사이의 장애는 관측·재대조 경로로 처리한다.

⚠️ 이 재현기는 **named in-memory SQLite** 만 쓴다. 파일도 운영 DB 도 건드리지 않는다.

실행:
    venv/Scripts/python.exe ops_control/counterexamples_deploy_ledger.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple

#: 이 파일을 «직접» 실행할 수 있어야 한다 — 재현기는 부르기 쉬워야 쓰인다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops_control import deploy_ledger as dl  # noqa: E402

ACTOR = "ops@example.invalid"
APPROVER = "approver@example.invalid"


class _Memory:
    """named in-memory DB 하나. 연결이 하나라도 살아 있어야 내용이 유지된다."""

    def __init__(self, name: str):
        self._uri = f"file:{name}?mode=memory&cache=shared"
        self._keepalive = sqlite3.connect(self._uri, uri=True)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._uri, uri=True, timeout=5)

    def rows(self) -> List[Tuple[str, str]]:
        cur = self._keepalive.execute(
            "SELECT plan_id, state FROM deploy_plan ORDER BY plan_id")
        return [(r[0], r[1]) for r in cur.fetchall()]

    def close(self) -> None:
        self._keepalive.close()


def _promote_through(ledger: "dl.DeployLedger", plan_id: str, digest: str,
                     env: str = dl.STAGING) -> None:
    ledger.open_plan(plan_id, env, digest, "cfg-1", ACTOR)
    ledger.record_readiness(plan_id, "READY", ACTOR)
    ledger.approve(plan_id, APPROVER)
    ledger.promote(plan_id, ACTOR)


# ── 반례 ① 한 환경에 PROMOTED 가 둘 ─────────────────────────────────────
def reproduce_double_promoted() -> Dict[str, Any]:
    """BLUE 를 승격한 뒤 GREEN 을 승격한다. **두 번째 전이(BLUE→SUPERSEDED)만** 실패시킨다.

    기대: 아무것도 바뀌지 않거나, BLUE 는 물러나고 GREEN 만 서비스 중.
    실제: **둘 다 `PROMOTED`.** `current_serving()` 은 한 행만 보므로 이 모순을 가린다."""
    mem = _Memory("cex_double_promote")
    try:
        ledger = dl.DeployLedger(connect=mem.connect)
        _promote_through(ledger, "BLUE", "sha-blue")

        ledger.open_plan("GREEN", dl.STAGING, "sha-green", "cfg-1", ACTOR)
        ledger.record_readiness("GREEN", "READY", ACTOR)
        ledger.approve("GREEN", APPROVER)

        original = ledger._transition

        def flaky(plan_id, to_state, **kwargs):
            #: 실행 중 인스턴스에만 주입한다 — 소스 파일을 변이하지 않는다.
            if to_state == dl.SUPERSEDED:
                raise RuntimeError("주입: 두 번째 전이가 실패했다")
            return original(plan_id, to_state, **kwargs)

        ledger._transition = flaky  # type: ignore[assignment]
        error = ""
        try:
            ledger.promote("GREEN", ACTOR)
        except RuntimeError as exc:
            error = str(exc)

        promoted = [p for p, st in mem.rows() if st == dl.PROMOTED]
        return {"case": "promotion_second_transition_failure",
                "raised": error,
                "rows": mem.rows(),
                "promoted_count": len(promoted),
                "defect": len(promoted) > 1}
    finally:
        mem.close()


# ── 반례 ② 복귀 실패인데 «복귀 완료» 로 기록 ────────────────────────────
def reproduce_rollback_recorded_without_restore() -> Dict[str, Any]:
    """복귀 대상이 부적격(`PLANNED`)인데 현재 계획을 먼저 `ROLLED_BACK` 으로 적는다.

    기대: 대상이 부적격이면 **아무것도 기록하지 않는다.**
    실제: GREEN 은 `ROLLED_BACK`, 서비스 중인 것은 **하나도 없다.**
    ★ 실패 주입이 필요 없다 — 두 번째 전이의 상태 조건에서 그냥 터진다."""
    mem = _Memory("cex_rollback_target")
    try:
        ledger = dl.DeployLedger(connect=mem.connect)
        _promote_through(ledger, "BLUE", "sha-blue")
        _promote_through(ledger, "GREEN", "sha-green")
        #: 같은 환경에 아직 한 번도 승격된 적 없는 계획을 둔다.
        ledger.open_plan("UNDEPLOYED", dl.STAGING, "sha-undeployed", "cfg-1", ACTOR)

        error = ""
        try:
            ledger.rollback("GREEN", ACTOR, "오류율 증가",
                            observed_serving_digest="sha-undeployed",
                            restored_plan_id="UNDEPLOYED")
        except dl.DeployLedgerError as exc:
            error = type(exc).__name__

        rows = mem.rows()
        serving = [p for p, st in rows if st == dl.PROMOTED]
        return {"case": "rollback_invalid_target_state",
                "raised": error,
                "rows": rows,
                "serving_after_failed_rollback": serving,
                "defect": error != "" and ("GREEN", dl.ROLLED_BACK) in rows}
    finally:
        mem.close()


def main() -> int:
    result = {"counterexamples": [reproduce_double_promoted(),
                                  reproduce_rollback_recorded_without_restore()],
              "database_mode": "named in-memory only",
              "file_writes": 0}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    #: ⚠️ 반례가 «재현되면» 0 이다. 이건 「통과」가 아니라 **「아직 그대로다」** 는 뜻이다.
    #:   고쳐지면 여기가 1 이 되고, 그때 이 파일을 정식 시험으로 옮긴다.
    return 0 if all(c["defect"] for c in result["counterexamples"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
