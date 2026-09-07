"""[DAO-11] 정기 갱신 실행기 — 운영 스케줄러가 부르는 한 바퀴.

## ⚠️ 프로세스 안에 타이머를 두지 않는다(지시 9)

이 모듈에는 `sleep` 도 `Timer` 도 없다. 운영 스케줄러(cron · Windows 작업 스케줄러)가
`scripts/run_acquisition_refresh.py` 를 부르고, 그것이 여기 `run_once()` 를 한 번 돈다.

★ 왜: 프로세스 안에 타이머를 두면 **다중 워커에서 같은 수집이 N배로 돈다.** 웹 서버가
  4개 뜨면 환율을 하루 4번 받고, 그 사실을 아무도 모른다.

## ★★★ 자동 적용은 «처음 승인한 것과 같은 모양일 때만»

정기 갱신이 매번 사람 승인을 요구하면 일별 환율은 실무에서 못 쓴다. 그렇다고 무조건
적용하면 사람 관문이 무의미해진다. 그래서 **모양이 같을 때만** 적용한다.

    ① 자동 적용이 켜져 있는가          기본 꺼짐 · 켜는 것 자체가 원장에 남는 결정
    ② 원천·계약이 처음 그대로인가       바뀌었으면 그건 다른 수집이다
    ③ 계약이 여전히 승인 상태인가       사람이 되돌렸을 수 있다
    ④ 계약의 성격과 원천의 성격이 맞는가  `assert_origin_fits` 와 같은 판정
    ⑤ 품질 검사를 통과했는가           격리 사유가 있으면 사람이 봐야 한다
    ⑥ **원천의 필드 구성이 그대로인가**  스키마가 바뀌면 사람이 봐야 한다

⑥ 이 이 관문의 핵심이고, **처음에 잘못 만들었다.** 정규화된 행을 계약과 대조했는데,
명시적 변환기가 새 열을 애초에 버리므로 **원천이 바뀌어도 아무 차이가 없었다** — 관문이
장식이었고 시험이 그것을 잡았다.

고친 뒤: 마지막 적용 때 **원천이 실제로 준 필드 이름들**을 체크포인트에 적어 두고, 다음
갱신에서 그것과 비교한다. 스스로 기준을 만들므로 Provider 마다 목록을 선언하지 않아도 된다.

⚠️ 새 열이 생겼다고 값이 틀린 것은 아니다. 그러나 **원천이 무언가를 바꿨다는 사실은 사람이
  알아야 한다** — 우리가 안 쓰는 열이 늘었을 수도, 우리가 쓰던 열의 뜻이 바뀌었을 수도 있다.

**하나라도 어긋나면 `REVIEW_REQUIRED` 에 두고 사람에게 넘긴다.** 실패가 아니다.

## 한 바퀴의 결과

`run_once()` 는 **던지지 않는다.** 한 작업이 실패해도 나머지를 계속 돈다 — 환율이 안
받아졌다고 물가까지 멈추면 안 된다. 모든 결과가 보고서에 담긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.orchestrator import (OrchestrationError, assert_origin_fits)

#: 한 바퀴에 도는 최대 작업 수. 스케줄러가 다시 부르면 이어서 돈다 —
#: 한 번에 전부 돌면 첫 실행이 끝나기 전에 다음 실행이 겹친다.
DEFAULT_BATCH = 25

#: 자동 적용을 막은 이유. **닫힌 목록**이다 — 화면이 문구를 지어내지 않게.
BLOCK_AUTO_APPLY_OFF = "AUTO_APPLY_OFF"
BLOCK_SHAPE_CHANGED = "SHAPE_CHANGED"
BLOCK_CONTRACT_NOT_APPROVED = "CONTRACT_NOT_APPROVED"
BLOCK_ORIGIN_MISMATCH = "ORIGIN_MISMATCH"
BLOCK_QUALITY = "QUALITY_CHECK_FAILED"
BLOCK_NEW_FIELDS = "NEW_FIELDS_IN_SOURCE"

BLOCK_REASONS: Dict[str, str] = {
    BLOCK_AUTO_APPLY_OFF: "자동 적용이 켜져 있지 않습니다 — 사람이 검토해 적용합니다.",
    BLOCK_SHAPE_CHANGED: "원천 또는 대상 계약이 처음 승인한 것과 다릅니다.",
    BLOCK_CONTRACT_NOT_APPROVED: "대상 계약의 승인이 더 이상 유효하지 않습니다.",
    BLOCK_ORIGIN_MISMATCH: "계약이 담는다고 선언한 성격과 원천이 내는 성격이 다릅니다.",
    BLOCK_QUALITY: "품질·대사 검사가 걸렸습니다 — 사람이 봐야 합니다.",
    BLOCK_NEW_FIELDS: ("원천의 필드 구성이 마지막 적용 때와 다릅니다 — 스키마가 바뀌었습니다."),
}


class RefreshError(RuntimeError):
    """실행기 자체의 오류. 개별 작업 실패는 여기 오지 않고 보고서에 담긴다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobOutcome:
    """작업 하나의 결과. **무엇을 했고 무엇을 안 했는지**가 둘 다 있다."""
    job_id: str
    provider_id: str = ""
    contract_key: str = ""
    #: 최종 상태
    status: str = ""
    #: 적용까지 갔나
    applied: bool = False
    inserted: int = 0
    duplicate: int = 0
    rejected: int = 0
    #: 자동 적용을 막았다면 그 이유(닫힌 목록)
    blocked: str = ""
    blocked_detail: str = ""
    #: 실패했다면
    failure_kind: str = ""
    error: str = ""
    #: 다음 실행 예정
    next_run_at: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id, "provider_id": self.provider_id,
            "contract_key": self.contract_key, "status": self.status,
            "applied": self.applied, "inserted": self.inserted,
            "duplicate": self.duplicate, "rejected": self.rejected,
            "blocked": self.blocked,
            "blocked_reason": BLOCK_REASONS.get(self.blocked, "") if self.blocked else "",
            "blocked_detail": self.blocked_detail,
            "failure_kind": self.failure_kind, "error": self.error,
            "next_run_at": self.next_run_at,
        }


@dataclass(frozen=True)
class RefreshReport:
    """한 바퀴의 결과. 운영 스케줄러의 로그가 이것이다."""
    started_at: str
    finished_at: str
    considered: int = 0
    outcomes: Tuple[JobOutcome, ...] = ()

    @property
    def applied(self) -> int:
        return sum(1 for o in self.outcomes if o.applied)

    @property
    def awaiting_review(self) -> int:
        return sum(1 for o in self.outcomes if o.status == am.REVIEW_REQUIRED)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status in (am.FAILED, am.QUARANTINED))

    @property
    def no_data(self) -> int:
        return sum(1 for o in self.outcomes if o.status == am.NO_DATA)

    @property
    def inserted(self) -> int:
        return sum(o.inserted for o in self.outcomes)

    def as_dict(self) -> Dict[str, Any]:
        return {"started_at": self.started_at, "finished_at": self.finished_at,
                "considered": self.considered, "applied": self.applied,
                "awaiting_review": self.awaiting_review, "failed": self.failed,
                "no_data": self.no_data, "inserted": self.inserted,
                "outcomes": [o.as_dict() for o in self.outcomes]}

    def summary_line(self) -> str:
        return (f"수집 갱신 {self.considered}건 검토 · 적용 {self.applied} · "
                f"검토대기 {self.awaiting_review} · 자료없음 {self.no_data} · "
                f"실패 {self.failed} · 신규 {self.inserted}행")


def auto_apply_gate(job: Mapping[str, Any], *, store, provider, report,
                    batch) -> Tuple[bool, str, str]:
    """★★★ 「처음 승인한 것과 같은 모양인가」. `(허용, 막은코드, 상세)`.

    ⚠️ **던지지 않는다** — 막힌 이유가 보고서에 실려야 사람이 무엇을 볼지 안다."""
    if not job.get("auto_apply"):
        return False, BLOCK_AUTO_APPLY_OFF, ""

    #: ② 원천·계약이 처음 그대로인가
    if str(batch.provider_id) != str(job.get("provider_id") or ""):
        return False, BLOCK_SHAPE_CHANGED, (
            f"원천이 {job.get('provider_id')} → {batch.provider_id} 로 바뀌었습니다.")
    contract_key = str(job.get("target_contract_key") or "")
    if str(batch.contract_key) != contract_key:
        return False, BLOCK_SHAPE_CHANGED, (
            f"대상 계약이 {contract_key} → {batch.contract_key} 로 바뀌었습니다.")

    #: ③ 계약이 여전히 승인 상태인가
    approved = store.approved_contract(contract_key)
    if not approved:
        return False, BLOCK_CONTRACT_NOT_APPROVED, contract_key

    #: ④ 성격이 맞는가 — 적용 직전 검사와 **같은 판정자**를 쓴다
    try:
        assert_origin_fits(approved.get("document") or {},
                           provider.describe().data_origin, contract_key=contract_key)
    except OrchestrationError as exc:
        return False, BLOCK_ORIGIN_MISMATCH, str(exc)

    #: ⑤ 품질 검사
    if not report.ok:
        return False, BLOCK_QUALITY, "; ".join(
            f"{c.name}: {c.detail}" for c in report.failures)[:300]

    #: ⑥ ★★★ 원천의 필드 구성이 마지막 적용 때와 같은가.
    #:   ⚠️ **정규화된 행이 아니라 원문의 필드**를 본다. 정규화 결과를 보면 명시적
    #:     변환기가 새 열을 버리므로 원천이 바뀌어도 아무 차이가 없다(실측으로 뚫렸다).
    baseline = tuple(str(x) for x in (job.get("checkpoint") or {}).get("source_fields") or ())
    current = tuple(batch.source_fields)
    if baseline and set(current) != set(baseline):
        added = sorted(set(current) - set(baseline))
        removed = sorted(set(baseline) - set(current))
        parts = []
        if added:
            parts.append(f"새로 생김 {len(added)}개: {', '.join(added[:6])}")
        if removed:
            parts.append(f"사라짐 {len(removed)}개: {', '.join(removed[:6])}")
        return False, BLOCK_NEW_FIELDS, " · ".join(parts)
    if not baseline and current:
        #: 비교 기준이 없다 — 이 작업은 이 관문이 생기기 전에 적용됐다.
        #: **한 번은 사람이 봐야** 기준이 생긴다. 통과시키면 기준 없이 계속 돈다.
        return False, BLOCK_NEW_FIELDS, (
            "이 작업에는 비교할 원천 필드 기준이 없습니다 — 한 번 사람이 적용하면 "
            "그때의 구성이 기준이 됩니다.")

    return True, "", ""


def refresh_job(orchestrator, job: Mapping[str, Any], *, actor_id: str,
                as_of: str = "") -> JobOutcome:
    """한 작업을 한 바퀴 돌린다. **던지지 않는다** — 결과를 돌려준다.

    `ACTIVE → DRY_RUN → REVIEW_REQUIRED` 까지는 언제나 가고, 관문을 통과하면 `APPLYING →
    ACTIVE` 까지 간다."""
    store = orchestrator.store
    job_id = str(job["job_id"])
    provider_id = str(job.get("provider_id") or "")
    contract_key = str(job.get("target_contract_key") or "")
    base = dict(job_id=job_id, provider_id=provider_id, contract_key=contract_key)

    try:
        moved, report = orchestrator.dry_run(job_id, actor_id=actor_id, as_of=as_of)
    except OrchestrationError as exc:
        current = store.get(job_id) or {}
        return JobOutcome(**base, status=str(current.get("status") or ""),
                          failure_kind=str(current.get("failure_kind") or ""),
                          error=str(exc)[:400],
                          next_run_at=str(current.get("next_run_at") or ""))
    except Exception as exc:                  # noqa: BLE001 — 한 작업이 바퀴를 멈추지 않는다
        return JobOutcome(**base, status=str((store.get(job_id) or {}).get("status") or ""),
                          error=f"{type(exc).__name__}: {exc}"[:400])

    status = str(moved.get("status") or "")
    if status != am.REVIEW_REQUIRED:
        #: 품질에서 걸려 격리로 갔거나 자료가 없다 — 사람이 볼 자리다.
        return JobOutcome(**base, status=status,
                          failure_kind=str(moved.get("failure_kind") or ""),
                          rejected=int((moved.get("dry_run") or {}).get("rejected_rows") or 0),
                          next_run_at=str(moved.get("next_run_at") or ""))

    #: 관문 — 자동 적용해도 되는가
    try:
        provider = orchestrator._provider(provider_id)
        candidate = orchestrator._candidate_from((moved.get("plan") or {}).get("chosen") or {})
        result = provider.fetch(candidate)
        batch = provider.normalize(result)
        validation = provider.validate(batch)
    except Exception as exc:                  # noqa: BLE001
        return JobOutcome(**base, status=status, blocked=BLOCK_QUALITY,
                          blocked_detail=f"관문 확인 중 오류: {exc}"[:300],
                          next_run_at=str(moved.get("next_run_at") or ""))

    allowed, blocked, detail = auto_apply_gate(
        moved, store=store, provider=provider, report=validation, batch=batch)
    if not allowed:
        return JobOutcome(**base, status=am.REVIEW_REQUIRED, blocked=blocked,
                          blocked_detail=detail,
                          rejected=len(batch.rejected),
                          next_run_at=str(moved.get("next_run_at") or ""))

    try:
        applied_job, apply_report = orchestrator.apply(job_id, actor_id=actor_id, as_of=as_of)
    except OrchestrationError as exc:
        current = store.get(job_id) or {}
        return JobOutcome(**base, status=str(current.get("status") or ""),
                          failure_kind=str(current.get("failure_kind") or ""),
                          error=str(exc)[:400])
    return JobOutcome(**base, status=str(applied_job.get("status") or ""),
                      applied=apply_report.ok, inserted=apply_report.inserted,
                      duplicate=apply_report.duplicate, rejected=apply_report.rejected,
                      next_run_at=str(applied_job.get("next_run_at") or ""))


def run_once(orchestrator, *, actor_id: str = "system:acquisition-scheduler",
             now: str = "", limit: int = DEFAULT_BATCH, as_of: str = "") -> RefreshReport:
    """운영 스케줄러가 부르는 한 바퀴. **`ACTIVE` 이고 시각이 된 것만** 돈다.

    ⚠️ 한 작업이 실패해도 나머지를 계속 돈다 — 환율이 안 받아졌다고 물가까지 멈추면 안 된다."""
    started = _now()
    due = orchestrator.store.due_for_refresh(now=now or started, limit=limit)
    outcomes = [refresh_job(orchestrator, job, actor_id=actor_id, as_of=as_of) for job in due]
    return RefreshReport(started_at=started, finished_at=_now(),
                         considered=len(due), outcomes=tuple(outcomes))
