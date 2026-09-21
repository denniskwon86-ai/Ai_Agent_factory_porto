# -*- coding: utf-8 -*-
"""[P2] **배포 상태 원장** — 어느 환경에 무엇이 서 있고, 누가 무엇을 근거로 넘겼는가.

## 왜 원장인가

배포 자동화의 사고는 대부분 **「지금 무엇이 돌고 있는지 모르는 상태에서 또 한 번
누르는 것」**에서 난다. 응답이 유실되면 사람도 스크립트도 다시 누른다. 그래서 여기서는
**계획에 이름(`plan_id`)을 붙이고**, 같은 이름으로 다시 오면 **다시 실행하지 않고 현재
상태를 돌려준다.**

## 상태

    PLANNED ──readiness READY──▶ READY_CHECKED ──승인──▶ APPROVED ──▶ PROMOTED
        │              │                                     │
        └──────────────┴──────────── 실패 ───────────────────┴──▶ HELD
                                                        PROMOTED ──▶ SUPERSEDED / ROLLED_BACK

`PLANNED · READY_CHECKED · APPROVED` 는 **진행 중**이고 **환경 잠금을 잡는다** —
한 환경에 진행 중인 계획은 **하나뿐**이다.

## 이 원장이 지키는 것

1. ★★ **[Z05] Green 이 준비되지 않으면 승격하지 않고, Blue 를 건드리지도 않는다.**
   실패는 `HELD` 로 «이유와 함께» 남는다. 지금 서비스 중인 계획의 상태는 **바뀌지 않는다.**
2. ★★ **승인은 «무엇에 대한» 승인인지 결속된다.** 환경·artifact digest·설정 지문·
   마이그레이션 계획을 묶어 지문을 만든다. **승인 뒤 하나라도 바뀌면 그 승인은 죽는다.**
3. ★★ **`ROLLED_BACK` 을 명령 성공만으로 적지 않는다.** 되돌아간 노드가 실제로 그
   digest 를 서빙하고 있다는 «관측값» 을 받아 대조한 뒤에만 적는다.
4. 읽기·판정·쓰기를 **한 트랜잭션**으로 묶는다(`BEGIN IMMEDIATE` + 기대 상태 CAS).
   프로세스가 둘이면 응용 lock 은 소용이 없다.

⚠️⚠️ **미연결 프로토타입이다 — 제품에 배선하지 않는다.**
  독립 검토가 이 상태 기계를 정본과 다르다고 판정했고(과거 계획 되살리기는 수용 불가),
  「폐기 예정 상태 기계를 먼저 완성하는 이중 작업」을 하지 않기로 했다. 살아 있는 것은
  **정책 시나리오와 그 시험 의도**이며, 실제 domain/persistence 는 보완된 정본 위에서
  다시 구현한다. 알려진 미해결 반례는 `ops_control/counterexamples_deploy_ledger.py`.

⚠️ 이 모듈은 **아무것도 배포하지 않는다.** 트래픽을 옮기지도, LB 를 건드리지도 않는다.
  NCP LB 의 가중치·연결 드레인 지원 여부는 **미확인**이므로 그것이 있다고 가정한 코드를
  쓰지 않는다. 여기 있는 것은 **상태 기계와 그 기록**뿐이다.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

#: 닫힌 목록이다. 오타로 «새 환경» 이 생기면 **환경 잠금이 통째로 우회된다.**
STAGING, TRIAL, PRODUCTION = "staging", "trial", "production"
ENVIRONMENTS = (STAGING, TRIAL, PRODUCTION)

PLANNED = "PLANNED"
READY_CHECKED = "READY_CHECKED"
APPROVED = "APPROVED"
PROMOTED = "PROMOTED"
HELD = "HELD"
SUPERSEDED = "SUPERSEDED"
ROLLED_BACK = "ROLLED_BACK"
STATES = (PLANNED, READY_CHECKED, APPROVED, PROMOTED, HELD, SUPERSEDED, ROLLED_BACK)

#: 환경 잠금을 «잡는» 상태. 끝난 계획은 잠그지 않는다.
IN_FLIGHT = (PLANNED, READY_CHECKED, APPROVED)

_DDL = """
CREATE TABLE IF NOT EXISTS deploy_plan(
    plan_id              TEXT PRIMARY KEY,
    environment          TEXT NOT NULL,
    artifact_digest      TEXT NOT NULL,
    config_fingerprint   TEXT NOT NULL,
    migration_plan       TEXT NOT NULL DEFAULT '',
    state                TEXT NOT NULL,
    reason               TEXT NOT NULL DEFAULT '',
    readiness_verdict    TEXT NOT NULL DEFAULT '',
    approval_fingerprint TEXT NOT NULL DEFAULT '',
    approved_by          TEXT NOT NULL DEFAULT '',
    actor                TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deploy_plan_env ON deploy_plan(environment, state);
CREATE TABLE IF NOT EXISTS deploy_plan_history(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id    TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state   TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    actor      TEXT NOT NULL,
    at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deploy_hist_plan ON deploy_plan_history(plan_id, id);
"""


class DeployLedgerError(RuntimeError):
    """배포 원장의 계약 위반. 호출자는 **다시 누르기 전에** 이유를 읽어야 한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def approval_fingerprint(environment: str, artifact_digest: str,
                         config_fingerprint: str, migration_plan: str) -> str:
    """승인이 «무엇에 대한» 승인이었는지. 하나라도 바뀌면 값이 달라진다.

    ⚠️ 구분자를 넣는 이유: 붙여 쓰면 `("ab","c")` 와 `("a","bc")` 가 같은 지문이 된다."""
    raw = "␟".join((environment, artifact_digest, config_fingerprint, migration_plan))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DeployLedger:
    def __init__(self, db_path: Optional[str] = None, connect=None,
                 begin_immediate: str = ""):
        #: ⚠️⚠️ [DEP-R4] **업무 `data/` 로 떨어지지 않는다.**
        #:   폴더를 `ops_control/` 로 옮겨 놓고도 기본 경로가 `data_path(...)` 여서,
        #:   인자를 빠뜨리면 관리 원장이 **업무 저장소 안에** 만들어지고 생성자가 거기서
        #:   DDL 까지 돌았다. 폴더 이동은 분리가 아니다 — 의존과 기본값까지 끊어야 한다.
        #:   관리 DB 설정은 정식 OPS 구현의 몫이므로, 여기서는 **경로 없이 만들 수 없다.**
        if not (db_path or "").strip() and connect is None:
            raise DeployLedgerError(
                "관리 원장의 저장 경로를 명시해야 합니다 — 업무 data/ 로 "
                "돌아가지 않습니다.")
        self._db_path = db_path or ""
        self._connect_factory = connect
        #: `BEGIN IMMEDIATE` 는 **SQLite 전용 문장**이다 — 부르는 쪽이 방언을 준다.
        self._begin_immediate = begin_immediate or "BEGIN IMMEDIATE"
        self._init_db()

    # ── 연결 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        if self._connect_factory is not None:
            #: ⚠️ 주입은 「연결을 어디서 얻는가」만 바꾼다 — 준비 절차를 건너뛰는 문이 아니다.
            conn = self._connect_factory()
        else:
            if not self._db_path:
                raise DeployLedgerError("관리 원장의 저장 경로가 없습니다.")
            folder = os.path.dirname(self._db_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    # ── 읽기 ────────────────────────────────────────────────────────────
    @staticmethod
    def _row(conn: sqlite3.Connection, plan_id: str) -> Optional[sqlite3.Row]:
        return conn.execute("SELECT * FROM deploy_plan WHERE plan_id=?",
                            (plan_id,)).fetchone()

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = self._row(conn, plan_id)
            return dict(row) if row else None
        finally:
            conn.close()

    def current_serving(self, environment: str) -> Optional[Dict[str, Any]]:
        """지금 **실제로 서비스 중**이라고 원장이 아는 계획."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM deploy_plan WHERE environment=? AND state=? "
                "ORDER BY updated_at DESC LIMIT 1", (environment, PROMOTED)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def history(self, plan_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM deploy_plan_history WHERE plan_id=? ORDER BY id",
                (plan_id,)).fetchall()]
        finally:
            conn.close()

    # ── 쓰기 공통 ───────────────────────────────────────────────────────
    def _begin(self, conn: sqlite3.Connection) -> None:
        conn.isolation_level = None
        conn.execute(self._begin_immediate)

    @staticmethod
    def _record(conn: sqlite3.Connection, plan_id: str, from_state: str,
                to_state: str, reason: str, actor: str) -> None:
        conn.execute(
            "INSERT INTO deploy_plan_history(plan_id, from_state, to_state, reason, "
            "actor, at) VALUES (?,?,?,?,?,?)",
            (plan_id, from_state, to_state, reason, actor, _now()))

    def _transition(self, plan_id: str, to_state: str, *, expected: tuple,
                    actor: str, reason: str = "",
                    extra: Optional[Mapping[str, Any]] = None,
                    guard=None, guard_fail_state: str = HELD) -> Dict[str, Any]:
        """읽기·판정·쓰기를 **한 트랜잭션**으로. 사이에 남이 바꾸면 여기서 걸린다.

        ⚠️ `guard` 는 **트랜잭션 «안»** 에서 현재 행을 보고 막을 사유를 돌려준다.
          바깥에서 미리 읽어 판단하면, 읽은 뒤 쓰기 전에 값이 바뀌어도 그대로 통과한다 —
          그 창이 바로 승격 사고가 지나가는 자리다."""
        if not (actor or "").strip():
            raise DeployLedgerError("행위자 없이 배포 상태를 바꿀 수 없습니다.")
        conn = self._connect()
        try:
            self._begin(conn)
            row = self._row(conn, plan_id)
            if row is None:
                conn.execute("ROLLBACK")
                raise DeployLedgerError(f"없는 계획입니다: {plan_id}")
            if row["state"] not in expected:
                conn.execute("ROLLBACK")
                raise DeployLedgerError(
                    f"'{row['state']}' 상태에서는 '{to_state}' 로 갈 수 없습니다 "
                    f"(가능한 이전 상태: {', '.join(expected)}).")
            blocked = guard(row) if guard is not None else None
            if blocked:
                #: 막혔다 — 목적 상태로 가지 않고 **이유와 함께** 보류로 떨어진다.
                to_state, reason, extra = guard_fail_state, blocked, None
            fields = dict(extra or {})
            fields.update({"state": to_state, "reason": reason, "updated_at": _now()})
            assignments = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE deploy_plan SET {assignments} WHERE plan_id=?",
                         (*fields.values(), plan_id))
            self._record(conn, plan_id, row["state"], to_state, reason, actor)
            updated = dict(self._row(conn, plan_id))
            conn.execute("COMMIT")
            return updated
        finally:
            conn.close()

    # ── ① 계획 열기 — **같은 이름으로 다시 오면 다시 하지 않는다** ──────
    def open_plan(self, plan_id: str, environment: str, artifact_digest: str,
                  config_fingerprint: str, actor: str,
                  migration_plan: str = "") -> Dict[str, Any]:
        """반환에 `created` 가 들어 있다 — **새로 만들었는지 이미 있던 것인지.**

        ⚠️ 응답이 유실되면 사람도 스크립트도 다시 누른다. 그때 두 번째 계획을 만들면
          환경에 두 개가 떠 있게 된다. 같은 이름·같은 결속이면 **현재 상태를 돌려준다.**"""
        if environment not in ENVIRONMENTS:
            raise DeployLedgerError(
                f"모르는 환경입니다: {environment} (허용: {', '.join(ENVIRONMENTS)})")
        for label, value in (("계획 ID", plan_id), ("artifact digest", artifact_digest),
                             ("설정 지문", config_fingerprint), ("행위자", actor)):
            if not (str(value or "").strip()):
                raise DeployLedgerError(f"{label} 가 필요합니다.")

        conn = self._connect()
        try:
            self._begin(conn)
            existing = self._row(conn, plan_id)
            if existing is not None:
                same = (existing["environment"] == environment
                        and existing["artifact_digest"] == artifact_digest
                        and existing["config_fingerprint"] == config_fingerprint
                        and existing["migration_plan"] == migration_plan)
                conn.execute("ROLLBACK")
                if not same:
                    #: ⚠️ 같은 이름에 «다른 내용» 을 붙이면 원장이 거짓말을 시작한다.
                    raise DeployLedgerError(
                        f"계획 ID {plan_id} 는 이미 다른 내용으로 열려 있습니다.")
                return {"created": False, "plan": dict(existing)}

            locked = conn.execute(
                "SELECT plan_id FROM deploy_plan WHERE environment=? AND state IN "
                f"({','.join('?' * len(IN_FLIGHT))}) LIMIT 1",
                (environment, *IN_FLIGHT)).fetchone()
            if locked is not None:
                conn.execute("ROLLBACK")
                raise DeployLedgerError(
                    f"{environment} 에 진행 중인 계획이 있습니다: {locked['plan_id']} — "
                    f"그것을 끝내거나 보류한 뒤에 여십시오.")

            now = _now()
            conn.execute(
                "INSERT INTO deploy_plan(plan_id, environment, artifact_digest, "
                "config_fingerprint, migration_plan, state, actor, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (plan_id, environment, artifact_digest, config_fingerprint,
                 migration_plan, PLANNED, actor, now, now))
            self._record(conn, plan_id, "", PLANNED, "", actor)
            created = dict(self._row(conn, plan_id))
            conn.execute("COMMIT")
            return {"created": True, "plan": created}
        finally:
            conn.close()

    # ── ② 준비도 기록 — 실패도 «이유와 함께» 남는다 ─────────────────────
    def record_readiness(self, plan_id: str, verdict: str, actor: str,
                         reason: str = "") -> Dict[str, Any]:
        """★ [Z05] `READY` 가 아니면 `HELD` 다. **Blue 는 건드리지 않는다** —

        이 호출은 지금 서비스 중인 계획의 상태를 **한 글자도 바꾸지 않는다**."""
        if verdict == "READY":
            return self._transition(plan_id, READY_CHECKED,
                                    expected=(PLANNED, READY_CHECKED), actor=actor,
                                    extra={"readiness_verdict": verdict})
        #: ⚠️ `UNKNOWN` 도 승격 사유가 아니다 — 「모른다」를 통과로 두지 않는다.
        return self._transition(plan_id, HELD, expected=(PLANNED, READY_CHECKED),
                                actor=actor, reason=reason or f"readiness={verdict}",
                                extra={"readiness_verdict": verdict})

    # ── ③ 승인 — 「무엇에 대한」 승인인지 묶는다 ─────────────────────────
    def approve(self, plan_id: str, approver: str) -> Dict[str, Any]:
        plan = self.get_plan(plan_id)
        if plan is None:
            raise DeployLedgerError(f"없는 계획입니다: {plan_id}")
        fingerprint = approval_fingerprint(
            plan["environment"], plan["artifact_digest"],
            plan["config_fingerprint"], plan["migration_plan"])
        return self._transition(plan_id, APPROVED, expected=(READY_CHECKED,),
                                actor=approver,
                                extra={"approval_fingerprint": fingerprint,
                                       "approved_by": approver})

    # ── ④ 승격 — 게이트가 여기 있다 ─────────────────────────────────────
    def promote(self, plan_id: str, actor: str) -> Dict[str, Any]:
        """★★ 준비도 `READY` + 살아 있는 승인이 **둘 다** 있어야 넘어간다.

        ⚠️ 막히면 `HELD` 로 떨어지고 **지금 서비스 중인 계획은 그대로다**(Z05)."""
        def gate(row) -> str:
            if row["readiness_verdict"] != "READY":
                return "readiness_not_ready"
            live = approval_fingerprint(row["environment"], row["artifact_digest"],
                                        row["config_fingerprint"], row["migration_plan"])
            if not row["approval_fingerprint"] or row["approval_fingerprint"] != live:
                #: 승인 뒤 digest·설정·마이그레이션 계획이 바뀌었다 — **그 승인은 죽었다.**
                return "approval_not_bound"
            return ""

        previous = self.current_serving(self._environment_of(plan_id))
        result = self._transition(plan_id, PROMOTED,
                                  expected=(PLANNED, READY_CHECKED, APPROVED),
                                  actor=actor, guard=gate)
        if result["state"] != PROMOTED:
            #: ★ [Z05] 막혔다. **지금 서비스 중인 계획은 한 글자도 바뀌지 않았다.**
            return result
        if previous and previous["plan_id"] != plan_id:
            self._transition(previous["plan_id"], SUPERSEDED, expected=(PROMOTED,),
                             actor=actor, reason=f"superseded_by:{plan_id}")
        return result

    def _environment_of(self, plan_id: str) -> str:
        plan = self.get_plan(plan_id)
        if plan is None:
            raise DeployLedgerError(f"없는 계획입니다: {plan_id}")
        return plan["environment"]

    def hold(self, plan_id: str, reason: str, actor: str) -> Dict[str, Any]:
        if not (reason or "").strip():
            raise DeployLedgerError("사유 없는 보류는 나중에 되돌릴 근거가 없습니다.")
        return self._transition(plan_id, HELD,
                                expected=(PLANNED, READY_CHECKED, APPROVED),
                                actor=actor, reason=reason)

    # ── ⑤ 복귀 — **관측값 없이는 적지 않는다** ──────────────────────────
    def rollback(self, plan_id: str, actor: str, reason: str,
                 observed_serving_digest: str,
                 restored_plan_id: str = "") -> Dict[str, Any]:
        """⚠️⚠️ 명령이 0 으로 끝났다고 `ROLLED_BACK` 을 적지 않는다(§6-4).

        **되돌아간 노드가 실제로 무엇을 서빙하고 있는지** 관측값을 받아 대조한다.

        ★ 대조 방향을 틀리기 쉽다 — 복귀가 끝나면 노드는 이 계획이 «아닌» 것을 서빙한다.
          그래서 관측값이 이 계획의 digest 와 **같으면** 아직 안 끝난 것이다.
          되돌아간 대상(`restored_plan_id`)을 주면 그쪽 digest 와 **같아야** 한다."""
        plan = self.get_plan(plan_id)
        if plan is None:
            raise DeployLedgerError(f"없는 계획입니다: {plan_id}")
        observed = (observed_serving_digest or "").strip()
        if not observed:
            raise DeployLedgerError(
                "서빙 중인 digest 관측값이 없으면 복귀를 기록하지 않습니다.")
        if observed == plan["artifact_digest"]:
            raise DeployLedgerError(
                "이 계획의 artifact 가 아직 서빙 중입니다 — 복귀가 끝나지 않았습니다.")

        restored = None
        if restored_plan_id:
            restored = self.get_plan(restored_plan_id)
            if restored is None:
                raise DeployLedgerError(f"없는 계획입니다: {restored_plan_id}")
            if restored["environment"] != plan["environment"]:
                raise DeployLedgerError("복귀 대상이 다른 환경의 계획입니다.")
            if restored["artifact_digest"] != observed:
                raise DeployLedgerError(
                    "관측된 서빙 digest 가 복귀 대상의 것과 다릅니다 — 원장이 "
                    "«복귀했다» 고 말할 근거가 없습니다.")

        rolled = self._transition(plan_id, ROLLED_BACK, expected=(PROMOTED,),
                                  actor=actor, reason=reason)
        if restored is not None:
            self._transition(restored_plan_id, PROMOTED, expected=(SUPERSEDED,),
                             actor=actor, reason=f"restored_from:{plan_id}")
        return rolled
