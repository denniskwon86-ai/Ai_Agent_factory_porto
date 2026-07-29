"""[M4] 계획 제출·승인 흐름 (§11.2 업무 흐름 · §17.2 기능 3). **LLM 0콜.**

## 이 모듈이 푸는 문제

계획 데이터가 있어도 승인이 없으면 **"누구의 계획인지"가 확정되지 않는다.** 그런데 승인을
상태 플래그 하나로 두면 더 나쁜 일이 생긴다 —

> **승인된 계획의 값이 조용히 바뀌면 그 승인은 무의미하다.**

경영 보고에서 이것은 흔한 사고다. 3월에 승인받은 계획의 숫자가 5월에 바뀌어 있는데
상태는 여전히 `APPROVED` 다. 아무도 거짓말하지 않았고 아무 오류도 나지 않았지만,
그 계획서는 이미 **승인받지 않은 문서**다.

## 그래서 승인 시점의 지문을 저장한다

승인할 때 그 시점 값들의 해시(`approved_fingerprint`)를 함께 박는다. 이후 언제든
`verify_integrity()` 로 현재 값의 지문과 대조하면 **"승인 후 변경됨"을 즉시 안다.**
상태만 보는 것과 달리 이 방식은 **속일 수 없다** — 값을 바꾸면 지문이 바뀌기 때문이다.

## 상태 전이

```
DRAFT ──제출──> SUBMITTED ──승인──> APPROVED
                    │                  │
                    └──반려──> REJECTED └──값 변경 감지──> APPROVED(무결성 깨짐)
```

- **익명 승인 금지.** 승인자 식별이 없으면 아무도 승인하지 않은 것이 승인된 것으로 남는다
  (외부 인텔리전스 원천 승인·용어사전 승인과 같은 원칙).
- **자기 제출 자기 승인 금지**(기본값). 제출자와 승인자가 같으면 통제가 아니라 형식이다.
  단 1인 부서·시범 운영을 위해 `allow_self_approval` 로 열 수 있고, 그 사실은 감사에 남는다.
- **반려에는 사유가 필수다.** 사유 없는 반려는 제출자가 무엇을 고쳐야 할지 모른다.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.planning_model import PLAN, PlanningError, planning_store

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
STATUSES = (DRAFT, SUBMITTED, APPROVED, REJECTED)

_DDL = """
CREATE TABLE IF NOT EXISTS plan_submissions (
    submission_id   TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    period          TEXT NOT NULL,
    value_kind      TEXT NOT NULL DEFAULT 'PLAN',
    status          TEXT NOT NULL DEFAULT 'SUBMITTED',
    submitted_by    TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    -- 제출 시점 값의 지문. 승인 시점 지문과 함께 두어 "언제부터 달라졌나"를 좁힌다.
    submitted_fingerprint TEXT NOT NULL DEFAULT '',
    approved_by     TEXT DEFAULT '',
    approved_at     TEXT DEFAULT '',
    -- ★ 승인 시점 값의 지문. 이것이 이 모듈의 핵심이다 — 상태는 속일 수 있어도 지문은 못 속인다.
    approved_fingerprint TEXT DEFAULT '',
    rejected_by     TEXT DEFAULT '',
    rejected_at     TEXT DEFAULT '',
    reject_reason   TEXT DEFAULT '',
    note            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_submission_lookup
    ON plan_submissions(org_id, period, value_kind, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_schema():
    conn = planning_store._connect()
    try:
        conn.executescript(_DDL)
        conn.commit()
    finally:
        conn.close()


def fingerprint(org_id: str, period: str, value_kind: str = PLAN) -> str:
    """현재 값들의 지문. **정렬을 고정**해 조회 순서 차이가 거짓 불일치를 만들지 않게 한다."""
    facts = planning_store.list_facts(org_id=org_id, period=period, value_kind=value_kind)
    payload = sorted([(f["account_code"], round(float(f["amount"]), 6)) for f in facts])
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def submit(org_id: str, period: str, submitted_by: str, value_kind: str = PLAN,
           note: str = "") -> Dict[str, Any]:
    """계획을 제출한다. 값이 하나도 없으면 거부 — 빈 계획의 승인은 승인이 아니다."""
    _ensure_schema()
    if not (submitted_by or "").strip():
        raise PlanningError("제출자 식별이 필요합니다 — 익명 제출은 받지 않습니다.")
    facts = planning_store.list_facts(org_id=org_id, period=period, value_kind=value_kind)
    if not facts:
        raise PlanningError(
            f"제출할 값이 없습니다({org_id}/{period}/{value_kind}) — "
            "빈 계획을 승인하면 '승인된 계획이 있다'는 사실만 남고 내용은 없습니다.")

    sid = uuid.uuid4().hex[:16]
    fp = fingerprint(org_id, period, value_kind)
    conn = planning_store._connect()
    try:
        # 같은 (조직·기간·종류)의 이전 제출은 대체된다 — 제출이 여러 건 살아 있으면
        # "무엇이 현재 계획인지" 알 수 없다.
        conn.execute("UPDATE plan_submissions SET status=?, note=? "
                     "WHERE org_id=? AND period=? AND value_kind=? AND status IN (?,?)",
                     (DRAFT, "새 제출로 대체됨", org_id, period, value_kind, SUBMITTED, REJECTED))
        conn.execute(
            "INSERT INTO plan_submissions(submission_id,org_id,period,value_kind,status,"
            "submitted_by,submitted_at,submitted_fingerprint,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, org_id, period, value_kind, SUBMITTED, submitted_by, _now(), fp, note or ""))
        conn.commit()
        return dict(conn.execute("SELECT * FROM plan_submissions WHERE submission_id=?",
                                 (sid,)).fetchone())
    finally:
        conn.close()


def approve(submission_id: str, approved_by: str,
            allow_self_approval: bool = False) -> Dict[str, Any]:
    """승인 — **승인 시점의 값 지문을 함께 박는다.**

    ⚠️ 지문을 안 박으면 승인은 상태 플래그에 불과하다. 값이 나중에 바뀌어도 `APPROVED` 가
      그대로 남고, 그 계획서는 아무도 거짓말하지 않은 채 **승인받지 않은 문서**가 된다."""
    _ensure_schema()
    if not (approved_by or "").strip():
        raise PlanningError("승인자 식별이 필요합니다 — 익명 승인은 "
                            "아무도 승인하지 않은 것을 승인된 것으로 만듭니다.")
    conn = planning_store._connect()
    try:
        row = conn.execute("SELECT * FROM plan_submissions WHERE submission_id=?",
                           (submission_id,)).fetchone()
        if not row:
            raise PlanningError(f"존재하지 않는 제출입니다: {submission_id}")
        if row["status"] != SUBMITTED:
            raise PlanningError(f"제출 상태가 아닙니다(status={row['status']}) — "
                                "이미 처리됐거나 새 제출로 대체됐습니다.")
        if not allow_self_approval and row["submitted_by"] == approved_by:
            raise PlanningError(
                "제출자와 승인자가 같습니다 — 자기 승인은 통제가 아니라 형식입니다. "
                "1인 부서·시범 운영이면 allow_self_approval 로 명시하십시오(감사에 남습니다).")

        fp = fingerprint(row["org_id"], row["period"], row["value_kind"])
        conn.execute("UPDATE plan_submissions SET status=?, approved_by=?, approved_at=?, "
                     "approved_fingerprint=? WHERE submission_id=?",
                     (APPROVED, approved_by, _now(), fp, submission_id))
        conn.commit()
        out = dict(conn.execute("SELECT * FROM plan_submissions WHERE submission_id=?",
                                (submission_id,)).fetchone())
    finally:
        conn.close()

    try:
        from core.enterprise_context import audit
        audit.record(audit.APPROVAL_GRANTED, "plan_submission", submission_id,
                     actor=approved_by, requested_scope=out["org_id"], outcome="granted",
                     reason="self_approval" if allow_self_approval and
                     out["submitted_by"] == approved_by else "approved",
                     detail=f"period={out['period']} fingerprint={out['approved_fingerprint']}")
    except Exception:
        pass
    return out


def reject(submission_id: str, rejected_by: str, reason: str) -> Dict[str, Any]:
    """반려 — **사유가 필수다.** 사유 없는 반려는 제출자가 무엇을 고쳐야 할지 모른다."""
    _ensure_schema()
    if not (rejected_by or "").strip():
        raise PlanningError("반려자 식별이 필요합니다.")
    if not (reason or "").strip():
        raise PlanningError("반려 사유는 필수입니다 — 사유가 없으면 제출자가 "
                            "무엇을 고쳐야 하는지 알 수 없습니다.")
    conn = planning_store._connect()
    try:
        row = conn.execute("SELECT status FROM plan_submissions WHERE submission_id=?",
                           (submission_id,)).fetchone()
        if not row:
            raise PlanningError(f"존재하지 않는 제출입니다: {submission_id}")
        if row["status"] != SUBMITTED:
            raise PlanningError(f"제출 상태가 아닙니다(status={row['status']}).")
        conn.execute("UPDATE plan_submissions SET status=?, rejected_by=?, rejected_at=?, "
                     "reject_reason=? WHERE submission_id=?",
                     (REJECTED, rejected_by, _now(), reason, submission_id))
        conn.commit()
        return dict(conn.execute("SELECT * FROM plan_submissions WHERE submission_id=?",
                                 (submission_id,)).fetchone())
    finally:
        conn.close()


def verify_integrity(submission_id: str) -> Dict[str, Any]:
    """★★ **승인 후 값이 바뀌었는가.** 이 모듈의 존재 이유다.

    상태(`APPROVED`)만 보면 알 수 없다 — 값을 고쳐도 상태는 그대로이기 때문이다.
    승인 시점 지문과 현재 지문을 대조하면 **속일 수 없는 판정**이 나온다."""
    _ensure_schema()
    conn = planning_store._connect()
    try:
        row = conn.execute("SELECT * FROM plan_submissions WHERE submission_id=?",
                           (submission_id,)).fetchone()
        if not row:
            raise PlanningError(f"존재하지 않는 제출입니다: {submission_id}")
        r = dict(row)
    finally:
        conn.close()

    if r["status"] != APPROVED:
        return {"submission_id": submission_id, "status": r["status"], "verifiable": False,
                "reason": "승인된 제출이 아니라 무결성을 판정할 수 없습니다.",
                "note": "'확인 불가'는 '이상 없음'이 아닙니다."}

    current = fingerprint(r["org_id"], r["period"], r["value_kind"])
    intact = current == r["approved_fingerprint"]
    return {
        "submission_id": submission_id,
        "status": r["status"],
        "verifiable": True,
        "intact": intact,
        "approved_fingerprint": r["approved_fingerprint"],
        "current_fingerprint": current,
        "approved_by": r["approved_by"],
        "approved_at": r["approved_at"],
        "message": ("승인 시점과 값이 동일합니다." if intact else
                    "⚠️ **승인 후 값이 변경되었습니다.** 이 계획은 상태상 APPROVED 이지만 "
                    "승인받은 내용과 다릅니다 — 재승인이 필요합니다."),
    }


def list_submissions(org_id: str = "", period: str = "", status: str = "") -> List[Dict[str, Any]]:
    _ensure_schema()
    sql = "SELECT * FROM plan_submissions WHERE 1=1"
    args: List[Any] = []
    for col, val in (("org_id", org_id), ("period", period), ("status", status)):
        if val:
            sql += f" AND {col}=?"
            args.append(val)
    conn = planning_store._connect()
    try:
        return [dict(r) for r in conn.execute(sql + " ORDER BY submitted_at DESC", args)]
    finally:
        conn.close()


def current_approved(org_id: str, period: str, value_kind: str = PLAN) -> Optional[Dict[str, Any]]:
    """현재 유효한 승인본. **무결성까지 확인해서** 돌려준다 —
    "승인됐다"만으로는 부족하고 "승인받은 그 값 그대로인가"가 실제 질문이다."""
    rows = [s for s in list_submissions(org_id, period, APPROVED)
            if s["value_kind"] == value_kind]
    if not rows:
        return None
    latest = rows[0]
    v = verify_integrity(latest["submission_id"])
    return {**latest, "integrity": v}
