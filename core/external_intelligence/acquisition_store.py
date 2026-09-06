"""[DAO-4] 수집 작업 저장소 — 상태를 옮기고, 옮긴 사실을 원장에 남긴다.

## 두 층으로 막는다

    응용층  `acquisition_models.assert_transition()` — **왜 안 되는지 사람에게 말해 준다**
    DB층    `CHECK` 제약 + 조건부 UPDATE(`WHERE status=?`) — **경쟁 상태에서도 하나만 이긴다**

★★★ 한 층만 두면 각각 다른 방식으로 뚫린다. 응용층만 있으면 두 요청이 동시에 읽고 둘 다
  통과한다(둘 다 `REVIEW_REQUIRED` 를 보고 둘 다 `APPLYING` 으로 간다). DB층만 있으면
  사용자는 「제약 위반」만 보고 무엇을 해야 하는지 모른다.
  ⚠️ 그리고 DB층은 **응용층의 판정에 기대면 안 된다** — 층마다 가정이 달라야 층이다.

## 이력을 두 곳에 두지 않는다

전이 이력 표를 따로 만들지 않는다. 원장(`decision_ledger`)이 해시 사슬로 append-only 이고,
`list_events("external_connection", job_id)` 가 그 작업의 전 이력을 준다. 로컬 표를 하나 더
두면 두 이력은 반드시 갈리고, 갈린 뒤에는 어느 쪽이 사실인지 아무도 모른다.

작업 행에는 **마지막 전이의 원장 사건 id** 만 들고 있는다 — 조회 편의이지 정본이 아니다.

## ⚠️ 기록 실패를 삼키지 않는다

원장 기록이 실패하면 상태도 옮기지 않는다. 한 트랜잭션 안에서 «상태는 바뀌었는데 기록은
없는» 순간을 만들지 않기 위해, **원장에 먼저 쓰고 그 다음 상태를 옮긴다.** 반대로 하면
기록이 실패했을 때 이미 옮겨진 상태를 되돌려야 하는데, 그 되돌리기가 또 실패할 수 있다.
기록만 남고 상태가 안 바뀌는 쪽이 **덜 나쁘다** — 남은 기록은 보이지만, 없는 기록은 안 보인다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.paths import data_path

#: 설계서 §5.1 — 「외부 원천·지표·관측·**수집 이력**」은 이 DB 다. 새 파일을 만들지 않는다.
_DB_PATH = data_path("external_intelligence.db")

#: ★★★ 상태 → 원장 사건 이름. **이 표 하나만 있다.**
#:   호출부가 사건 이름을 직접 적으면 어떤 전이는 기록되고 어떤 전이는 안 되며,
#:   그 차이는 감사 때까지 드러나지 않는다.
LEDGER_EVENT_BY_STATE: Dict[str, str] = {
    am.DRAFT: "DATA_ACQUISITION_REQUESTED",
    am.DISCOVERING: "DATA_ACQUISITION_STATE_CHANGED",
    am.PLAN_READY: "DATA_ACQUISITION_STATE_CHANGED",
    am.DRY_RUN: "DATA_ACQUISITION_STATE_CHANGED",
    am.REVIEW_REQUIRED: "DATA_ACQUISITION_REVIEW_REQUESTED",
    #: ★ 사람이 승인해야만 여기로 온다 — 그래서 별도 사건이다.
    am.APPLYING: "DATA_ACQUISITION_APPROVED",
    am.ACTIVE: "DATA_ACQUISITION_ACTIVATED",
    am.FAILED: "DATA_ACQUISITION_FAILED",
    am.NO_DATA: "DATA_ACQUISITION_NO_DATA",
    am.QUARANTINED: "DATA_ACQUISITION_QUARANTINED",
    am.DISABLED: "DATA_ACQUISITION_DISABLED",
}

LEDGER_SUBJECT_TYPE = "external_connection"

#: 사유 없이 갈 수 없는 상태. 사유가 없으면 나중에 「왜 이렇게 됐지?」에 답할 수 없고,
#: 그러면 아무도 되돌리지 못한다(`source_binding` 의 BLOCKED 와 같은 규칙).
_REASON_REQUIRED = (am.FAILED, am.NO_DATA, am.QUARANTINED, am.DISABLED)

_STATES_SQL = ", ".join(f"'{s}'" for s in am.ACQUISITION_STATES)

_DDL = f"""
CREATE TABLE IF NOT EXISTS data_acquisition_jobs (
    job_id           TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    scope_node_id    TEXT NOT NULL DEFAULT '',
    requested_by     TEXT NOT NULL,
    subject_name     TEXT NOT NULL DEFAULT '',
    purpose          TEXT NOT NULL DEFAULT '',
    request_json     TEXT NOT NULL DEFAULT '{{}}',
    -- ★★★ DB 층의 첫 통제. 응용층이 실수해도 목록 밖 상태는 저장되지 않는다.
    status           TEXT NOT NULL CHECK (status IN ({_STATES_SQL})),
    provider_id      TEXT NOT NULL DEFAULT '',
    dataset_ref      TEXT NOT NULL DEFAULT '',
    target_contract_key TEXT NOT NULL DEFAULT '',
    plan_json        TEXT NOT NULL DEFAULT '{{}}',
    dry_run_json     TEXT NOT NULL DEFAULT '{{}}',
    checkpoint_json  TEXT NOT NULL DEFAULT '{{}}',
    -- 「왜 이 상태인가」. 장애·자료없음·격리·중지는 사유 없이 될 수 없다.
    status_reason    TEXT NOT NULL DEFAULT '',
    failure_kind     TEXT NOT NULL DEFAULT '',
    schedule_rule    TEXT NOT NULL DEFAULT '',
    next_run_at      TEXT NOT NULL DEFAULT '',
    last_success_at  TEXT NOT NULL DEFAULT '',
    last_event_id    TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daq_status ON data_acquisition_jobs(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_daq_tenant ON data_acquisition_jobs(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_daq_schedule ON data_acquisition_jobs(status, next_run_at);

-- 작업 ↔ 원문. 계보의 고리이고, **적용 실패 때도 지우지 않는다**(지시 8).
CREATE TABLE IF NOT EXISTS data_acquisition_raw_objects (
    job_id           TEXT NOT NULL,
    raw_object_ref   TEXT NOT NULL,
    checksum         TEXT NOT NULL,
    source_id        TEXT NOT NULL DEFAULT '',
    dataset_ref      TEXT NOT NULL DEFAULT '',
    byte_size        INTEGER NOT NULL DEFAULT 0,
    fetched_at       TEXT NOT NULL DEFAULT '',
    recorded_at      TEXT NOT NULL,
    PRIMARY KEY (job_id, raw_object_ref)
);
CREATE INDEX IF NOT EXISTS idx_daq_raw_checksum
    ON data_acquisition_raw_objects(source_id, checksum);
"""


class AcquisitionStoreError(ValueError):
    """저장소 사용 오류 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


class AcquisitionStore:
    """수집 작업의 저장소. 상태 전이는 **여기를 통해서만** 일어난다."""

    def __init__(self, db_path: Optional[str] = None, ledger: Any = None):
        self.db_path = str(db_path or _DB_PATH)
        self._lock = threading.RLock()
        self._ready_done = False
        #: ⚠️ 원장을 주입 가능하게 둔다 — 시험이 운영 원장에 쓰지 않아야 한다.
        #:   그러나 **기본값은 진짜 원장**이다. 기본이 가짜면 배선을 잊어도 아무도 모른다.
        self._ledger = ledger

    # ── 연결 ─────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ready(self) -> None:
        if self._ready_done:
            return
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_DDL)
            self._ready_done = True

    def ledger(self):
        if self._ledger is None:
            from core.decision_ledger import decision_ledger
            self._ledger = decision_ledger
        return self._ledger

    # ── 만들기 ───────────────────────────────────────────────────────────
    def create(self, *, tenant_id: str, requested_by: str, request: Mapping[str, Any],
               scope_node_id: str = "", subject_name: str = "", purpose: str = "",
               actor_type: str = "user") -> Dict[str, Any]:
        """새 수집 작업. **언제나 `DRAFT` 로 시작한다.**

        ⚠️ 호출부가 시작 상태를 정하게 두면 「탐색도 안 했는데 계획 완료」가 만들어진다
          (`create_snapshot` 이 언제나 `RAW` 로 시작하는 것과 같은 이유)."""
        self._ready()
        if not str(tenant_id or "").strip():
            raise AcquisitionStoreError("tenant_id 가 필요합니다.")
        if not str(requested_by or "").strip():
            raise AcquisitionStoreError("요청자가 필요합니다 — 누가 요청했는지 없는 수집은 없습니다.")

        job_id = f"daq_{uuid.uuid4().hex[:20]}"
        now = _now()
        row = {
            "job_id": job_id, "tenant_id": str(tenant_id), "scope_node_id": str(scope_node_id or ""),
            "requested_by": str(requested_by), "subject_name": str(subject_name or ""),
            "purpose": str(purpose or ""), "request_json": _dumps(dict(request or {})),
            "status": am.DRAFT, "provider_id": "", "dataset_ref": "",
            "target_contract_key": "", "plan_json": "{}", "dry_run_json": "{}",
            "checkpoint_json": "{}", "status_reason": "", "failure_kind": "",
            "schedule_rule": "", "next_run_at": "", "last_success_at": "",
            "last_event_id": "", "created_at": now, "updated_at": now,
        }
        #: ★ 원장에 먼저 쓴다 — 기록이 실패하면 작업도 만들지 않는다.
        event = self._append_event(am.DRAFT, job_id=job_id, tenant_id=str(tenant_id),
                                   scope_node_id=str(scope_node_id or ""),
                                   actor_id=str(requested_by), actor_type=actor_type,
                                   from_status="", reason=str(purpose or ""),
                                   evidence_refs=[{"kind": "request", "value": dict(request or {})}])
        row["last_event_id"] = str(event.get("event_id", ""))
        with self._lock, self._connect() as conn:
            cols = ", ".join(row)
            conn.execute(f"INSERT INTO data_acquisition_jobs ({cols}) "
                         f"VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
        return self._public(row)

    # ── 상태 전이 ────────────────────────────────────────────────────────
    def transition(self, job_id: str, target: str, *, actor_id: str,
                   actor_type: str = "user", reason: str = "", failure_kind: str = "",
                   patch: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """상태를 옮기고 원장에 남긴다.

        ★★★ 순서가 중요하다: **읽기 → 응용층 판정 → 원장 기록 → 조건부 UPDATE.**
          마지막 UPDATE 는 `WHERE status=<읽은 값>` 이라, 그 사이에 남이 먼저 옮겼으면
          0행이 바뀌고 우리는 진다. 두 요청이 같은 관문을 동시에 통과할 수 없다."""
        self._ready()
        job = self.get(job_id)
        if job is None:
            raise AcquisitionStoreError(f"존재하지 않는 수집 작업입니다: {job_id}")
        current = str(job["status"])
        target = str(target or "")

        #: ① 응용층 — 사람이 읽을 이유를 준다.
        am.assert_transition(current, target)

        if target in _REASON_REQUIRED and not str(reason or "").strip():
            raise AcquisitionStoreError(
                f"{target} 로 옮기려면 사유가 필요합니다 — 사유가 없으면 되돌릴 근거도 없습니다.")
        if failure_kind:
            am.assert_failure_kind(failure_kind)
            expected = am.state_for_failure(failure_kind)
            if target in (am.FAILED, am.QUARANTINED) and target != expected:
                #: ⚠️ 실패 종류와 도착 상태가 어긋나면 「품질 문제인데 재시도 대상」이 된다.
                raise AcquisitionStoreError(
                    f"{failure_kind} 는 {expected} 로 가야 합니다 — {target} 가 아닙니다.")

        #: ② 원장 — 기록이 실패하면 상태를 옮기지 않는다.
        event = self._append_event(target, job_id=job_id, tenant_id=str(job["tenant_id"]),
                                   scope_node_id=str(job.get("scope_node_id") or ""),
                                   actor_id=str(actor_id or ""), actor_type=actor_type,
                                   from_status=current, reason=str(reason or ""),
                                   failure_kind=failure_kind)

        #: ③ 조건부 UPDATE — DB 층의 두 번째 통제.
        fields: Dict[str, Any] = {
            "status": target, "status_reason": str(reason or ""),
            "failure_kind": str(failure_kind or ""),
            "last_event_id": str(event.get("event_id", "")), "updated_at": _now(),
        }
        for key in ("provider_id", "dataset_ref", "target_contract_key", "schedule_rule",
                    "next_run_at", "last_success_at"):
            if patch and key in patch:
                fields[key] = str(patch[key] or "")
        for key in ("plan_json", "dry_run_json", "checkpoint_json"):
            plain = key[:-5]
            if patch and plain in patch:
                fields[key] = _dumps(patch[plain])

        assignments = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE data_acquisition_jobs SET {assignments} "
                f"WHERE job_id=? AND status=?",
                tuple(fields.values()) + (job_id, current))
            if cur.rowcount != 1:
                #: 우리가 읽은 뒤 남이 먼저 옮겼다. 여기서 이기려 하지 않는다 —
                #: 이기면 남의 전이를 덮어쓴다.
                raise AcquisitionStoreError(
                    f"수집 작업의 상태가 그 사이 바뀌었습니다({current} 를 기대했습니다). "
                    f"다시 읽고 판단하십시오.")
        out = self.get(job_id)
        assert out is not None
        return out

    def _append_event(self, target: str, *, job_id: str, tenant_id: str, scope_node_id: str,
                      actor_id: str, actor_type: str, from_status: str, reason: str,
                      failure_kind: str = "",
                      evidence_refs: Optional[List[Any]] = None) -> Dict[str, Any]:
        event_type = LEDGER_EVENT_BY_STATE.get(target)
        if not event_type:
            raise AcquisitionStoreError(f"상태 {target!r} 에 대응하는 원장 사건이 없습니다.")
        decision = f"{from_status or '(신규)'} → {target}"
        rationale = reason or ""
        if failure_kind:
            rationale = f"[{failure_kind}] {rationale}".strip()
        return self.ledger().append(
            event_type=event_type, subject_type=LEDGER_SUBJECT_TYPE, subject_id=job_id,
            actor_type=actor_type, actor_id=actor_id, decision=decision,
            rationale=rationale, evidence_refs=evidence_refs or [],
            tenant_id=tenant_id, enterprise_scope_id=scope_node_id)

    # ── 원문 결속 ────────────────────────────────────────────────────────
    def record_raw_object(self, job_id: str, meta: Mapping[str, Any]) -> Dict[str, Any]:
        """받아 둔 원문을 작업에 잇는다. **적용이 실패해도 이 줄은 지우지 않는다**(지시 8).

        ⚠️ 실패했다고 원천 응답까지 지우면 무엇 때문에 실패했는지 알 길이 없어진다."""
        self._ready()
        ref = str(meta.get("raw_object_ref") or "").strip()
        checksum = str(meta.get("checksum") or "").strip()
        if not ref or not checksum:
            raise AcquisitionStoreError("원문 참조와 체크섬이 모두 필요합니다.")
        row = {"job_id": str(job_id), "raw_object_ref": ref, "checksum": checksum,
               "source_id": str(meta.get("source_id") or ""),
               "dataset_ref": str(meta.get("dataset_ref") or ""),
               "byte_size": int(meta.get("byte_size") or 0),
               "fetched_at": str(meta.get("fetched_at") or ""), "recorded_at": _now()}
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO data_acquisition_raw_objects "
                "(job_id, raw_object_ref, checksum, source_id, dataset_ref, byte_size, "
                " fetched_at, recorded_at) VALUES (?,?,?,?,?,?,?,?)",
                tuple(row.values()))
        return row

    def raw_objects(self, job_id: str) -> List[Dict[str, Any]]:
        self._ready()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_acquisition_raw_objects WHERE job_id=? "
                "ORDER BY recorded_at", (str(job_id),)).fetchall()
        return [dict(r) for r in rows]

    def already_collected(self, source_id: str, checksum: str) -> Optional[Dict[str, Any]]:
        """이 응답을 이미 받은 적이 있나. **중복 적재 방지**의 DB 쪽 판정자다."""
        self._ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM data_acquisition_raw_objects WHERE source_id=? AND checksum=? "
                "ORDER BY recorded_at LIMIT 1",
                (str(source_id or ""), str(checksum or ""))).fetchone()
        return dict(row) if row else None

    # ── 조회 ─────────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._ready()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM data_acquisition_jobs WHERE job_id=?",
                               (str(job_id),)).fetchone()
        return self._public(dict(row)) if row else None

    def list_jobs(self, *, tenant_id: str = "", status: str = "",
                  limit: int = 100) -> List[Dict[str, Any]]:
        self._ready()
        where, params = [], []
        if tenant_id:
            where.append("tenant_id=?")
            params.append(str(tenant_id))
        if status:
            if status not in am.ACQUISITION_STATES:
                raise AcquisitionStoreError(f"모르는 상태입니다: {status!r}")
            where.append("status=?")
            params.append(status)
        sql = "SELECT * FROM data_acquisition_jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 1000)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._public(dict(r)) for r in rows]

    def due_for_refresh(self, *, now: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """스케줄러가 부를 목록. **`ACTIVE` 만** 돌려준다(지시 9).

        ⚠️ 프로세스 안에 타이머를 두지 않는다 — 다중 워커에서 같은 수집이 N배로 돈다.
          운영 스케줄러가 이 목록을 받아 하나씩 부른다."""
        self._ready()
        cutoff = str(now or _now())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_acquisition_jobs "
                "WHERE status=? AND next_run_at<>'' AND next_run_at<=? "
                "ORDER BY next_run_at LIMIT ?",
                (am.ACTIVE, cutoff, max(1, min(int(limit or 50), 500)))).fetchall()
        return [self._public(dict(r)) for r in rows]

    def history(self, job_id: str) -> List[Dict[str, Any]]:
        """이 작업의 전 이력. **원장에서 읽는다** — 로컬 사본을 두지 않는다."""
        return list(self.ledger().list_events(LEDGER_SUBJECT_TYPE, str(job_id)))

    @staticmethod
    def _public(row: Mapping[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        for key in ("request_json", "plan_json", "dry_run_json", "checkpoint_json"):
            out[key[:-5]] = _loads(out.pop(key, "{}"))
        out["is_schedulable"] = out.get("status") in am.SCHEDULABLE_STATES
        out["awaits_human"] = out.get("status") in am.HUMAN_GATE_STATES
        return out


acquisition_store = AcquisitionStore()
