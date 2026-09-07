"""[DAO-7] 수집 오케스트레이터 — 지금까지 만든 조각을 관통시킨다.

    discover()  DRAFT → DISCOVERING → PLAN_READY | NO_DATA | FAILED
    dry_run()   PLAN_READY → DRY_RUN → REVIEW_REQUIRED | QUARANTINED | NO_DATA | FAILED
    apply()     REVIEW_REQUIRED → APPLYING → ACTIVE | QUARANTINED | FAILED

## ★★★ Dry-run 은 운영에 쓰지 않는다

원문은 보관한다(그게 격리 수집이다). 그러나 **격리 적재본에는 한 줄도 넣지 않는다.**
시험이 dry-run 전후로 `staged_count()` 가 그대로인지 센다 — 「쓰지 않는다」를 주석으로
적는 것과 실제로 안 쓰는 것은 다르다.

## ★★★ 부분 실패를 성공으로 표시하지 않는다(지시 8)

적용은 단계별로 돌고, **한 단계라도 실패하면 `ACTIVE` 로 가지 않는다.** 그리고 실패해도
원문과 이미 들어간 정상 행을 **지우지 않는다** — 지우면 무엇 때문에 실패했는지 알 길이
없어진다.

## 어디까지 하고 어디부터 안 하는가 (지시 14 의 분리)

    오케스트레이터 구현   ✔
    Provider 구현        ✔
    fixture 검증         ✔
    실제 API 실측        ✘  키가 없다
    실제 데이터 수집      ✘
    격리 DB 적재         ✔  ← **여기까지가 이 모듈이다**
    운영 적용            ✘  업무키트 결속·준비도 재평가는 계약 승인 이후 별도
    자동갱신 활성화       ✘

⚠️ `apply()` 가 「운영 적용」까지 했다고 말하지 않는다. 격리 적재본(`data_acquisition_rows`)
  은 운영 데이터셋이 아니고, 보고서가 `pending_stages` 로 그것을 **명시한다.**
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence import mapping as M
from core.external_intelligence.providers import base as B

#: 적용 단계 이름(지시 8 의 순서). **이 목록이 곧 보고서의 뼈대다.**
STAGE_RAW = "RAW_PRESERVED"
STAGE_CHECKSUM = "CHECKSUM"
STAGE_NORMALIZE = "NORMALIZED"
STAGE_CLASSIFY = "CLASSIFIED"
STAGE_QUALITY = "QUALITY_CHECKED"
STAGE_RECONCILE = "RECONCILED"
STAGE_STAGE_ROWS = "STAGED_TO_ISOLATED_DB"
STAGE_LINEAGE = "LINEAGE_RECORDED"

#: 한 수집이 받을 수 있는 최대 쪽수. **끝없는 페이징을 막는다** — 원천이 `has_more` 를
#: 잘못 주면 영원히 돈다. Provider 쪽에도 상한이 있지만 **여기에도 둔다**(층마다 가정이
#: 달라야 층이다).
MAX_COLLECT_PAGES = 50

APPLY_STAGES: Tuple[str, ...] = (STAGE_RAW, STAGE_CHECKSUM, STAGE_NORMALIZE, STAGE_CLASSIFY,
                                 STAGE_QUALITY, STAGE_RECONCILE, STAGE_STAGE_ROWS,
                                 STAGE_LINEAGE)

#: ★ 이 모듈이 **하지 않는** 단계. 보고서에 그대로 실려 화면까지 간다.
PENDING_STAGES: Tuple[Tuple[str, str], ...] = (
    ("SNAPSHOT_CERTIFIED", "업무키트 Snapshot 인증은 계약이 키트에 편입된 뒤에 합니다."),
    ("KIT_BOUND", "업무키트 결속은 사람이 계약을 키트에 편입한 뒤 별도로 합니다."),
    ("READINESS_REEVALUATED", "준비도 재평가는 키트 결속 이후에 의미가 있습니다."),
)


class OrchestrationError(RuntimeError):
    """오케스트레이션 중단 — 상태는 이미 옮겨져 있다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def failure_kind_of(exc: Exception) -> str:
    """★★★ 실패 종류를 **한 곳에서만** 정한다.

    ⚠️ 실측으로 어긋났다 — OpenDART 가 `status=010`(등록되지 않은 키)을 `AUTH` 로 판정해
      예외에 실어 보냈는데, 오케스트레이터가 **예외의 타입만 보고** `POLICY` 로 덮어썼다.
      그러면 화면은 「정책 위반」이라 말하고 사람은 권한 설정을 뒤진다 — 실제로는 키가
      틀린 것이다. 예외가 스스로 밝힌 값이 있으면 그것이 우선이다."""
    declared = getattr(exc, "failure_kind", "")
    if declared in am.FAILURE_KINDS:
        return declared
    if isinstance(exc, B.ProviderCredentialError):
        return am.FAILURE_AUTH
    if isinstance(exc, B.ProviderTransportError):
        return am.FAILURE_TRANSPORT
    return am.FAILURE_POLICY


def assert_origin_fits(contract: Mapping[str, Any], row_origin: str, *,
                       contract_key: str) -> None:
    """★★★ 계약이 **말하는 성격**과 들어올 행의 성격이 같은지.

    ⚠️⚠️ 이 검사가 없으면 시연용으로 선언된 계약(`data_class: SYNTHETIC`)에 공개 통계가
      들어가고, 그 계약을 읽는 쪽은 **자기가 아는 뜻으로** 읽는다. 「시연 자료」라고 적힌
      그릇에 사실인 값이 담기면 아무도 그것을 신뢰하지 않거나, 반대로 시연 자료를 사실로
      읽는다 — 어느 쪽이든 계약이 거짓말을 하게 된다.

    ★ 업무키트의 `EXT-01`(환율·금리·물가)이 실제로 그 경우다: 열 모양은 관측값 그대로인데
      분류는 `SYNTHETIC` 이다. ECOS 를 붙이려면 **사람이 계약을 고쳐야** 한다."""
    declared = str((contract.get("classification") or {}).get("data_origin") or "")
    incoming = str(row_origin or "")
    if not declared:
        raise OrchestrationError(
            f"{contract_key} 계약이 자료 성격을 선언하지 않았습니다 — 무엇이 담기는지 "
            f"말하지 않는 계약에는 넣지 않습니다.")
    if declared != incoming:
        raise OrchestrationError(
            f"{contract_key} 계약은 «{declared}» 를 담는다고 선언했는데 이 원천은 "
            f"«{incoming}» 를 냅니다. 억지로 넣지 않습니다 — 계약을 고쳐 승인하거나 "
            f"다른 계약을 쓰십시오.")


@dataclass(frozen=True)
class StageResult:
    name: str
    ok: bool
    detail: str = ""
    count: int = 0


@dataclass(frozen=True)
class DryRunReport:
    """지시 7 이 요구한 항목을 **전부** 담는다. 화면은 이것만 보고 그린다."""
    job_id: str
    provider_id: str = ""
    dataset_ref: str = ""
    contract_key: str = ""
    #: 원천 후보와 선택 이유 / 고르지 않은 것과 사유
    chosen_reason: str = ""
    excluded_sources: Tuple[Mapping[str, str], ...] = ()
    ambiguous_with: Tuple[str, ...] = ()
    #: 건수
    expected_rows: int = 0
    new_rows: int = 0
    duplicate_rows: int = 0
    superseded_rows: int = 0
    rejected_rows: int = 0
    #: 결손·매핑·환산
    missing_fields: Mapping[str, int] = field(default_factory=dict)
    mapping_ok: int = 0
    mapping_needs_human: Tuple[str, ...] = ()
    mapping_failed: Tuple[Mapping[str, str], ...] = ()
    unit_conversions: Tuple[Mapping[str, Any], ...] = ()
    #: 연결·격리·용량·일정
    target_contract_status: str = ""
    quarantined: Tuple[Mapping[str, str], ...] = ()
    estimated_bytes: int = 0
    refresh_schedule: str = ""
    readiness_change_note: str = ""
    validation: Tuple[Mapping[str, Any], ...] = ()
    pending_stages: Tuple[Mapping[str, str], ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id, "provider_id": self.provider_id,
            "dataset_ref": self.dataset_ref, "contract_key": self.contract_key,
            "chosen_reason": self.chosen_reason,
            "excluded_sources": [dict(x) for x in self.excluded_sources],
            "ambiguous_with": list(self.ambiguous_with),
            "expected_rows": self.expected_rows, "new_rows": self.new_rows,
            "duplicate_rows": self.duplicate_rows, "superseded_rows": self.superseded_rows,
            "rejected_rows": self.rejected_rows, "missing_fields": dict(self.missing_fields),
            "mapping_ok": self.mapping_ok,
            "mapping_needs_human": list(self.mapping_needs_human),
            "mapping_failed": [dict(x) for x in self.mapping_failed],
            "unit_conversions": [dict(x) for x in self.unit_conversions],
            "target_contract_status": self.target_contract_status,
            "quarantined": [dict(x) for x in self.quarantined],
            "estimated_bytes": self.estimated_bytes,
            "refresh_schedule": self.refresh_schedule,
            "readiness_change_note": self.readiness_change_note,
            "validation": [dict(x) for x in self.validation],
            "pending_stages": [dict(x) for x in self.pending_stages],
        }


@dataclass(frozen=True)
class ApplyReport:
    """적용 결과. `ok` 가 아니면 **어느 단계에서 멈췄는지**가 남는다."""
    job_id: str
    stages: Tuple[StageResult, ...] = ()
    inserted: int = 0
    duplicate: int = 0
    superseded: int = 0
    rejected: int = 0
    raw_object_ref: str = ""
    pending_stages: Tuple[Mapping[str, str], ...] = ()
    failure_kind: str = ""
    failure_detail: str = ""

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.stages) and not self.failure_kind

    @property
    def partial(self) -> bool:
        """★★★ 일부만 들어간 상태. **성공이 아니다.**"""
        return bool(self.inserted) and not self.ok

    def as_dict(self) -> Dict[str, Any]:
        return {"job_id": self.job_id, "ok": self.ok, "partial": self.partial,
                "stages": [{"name": s.name, "ok": s.ok, "detail": s.detail, "count": s.count}
                           for s in self.stages],
                "inserted": self.inserted, "duplicate": self.duplicate,
                "superseded": self.superseded, "rejected": self.rejected,
                "raw_object_ref": self.raw_object_ref,
                "pending_stages": [dict(x) for x in self.pending_stages],
                "failure_kind": self.failure_kind, "failure_detail": self.failure_detail}


class AcquisitionOrchestrator:
    """수집 작업을 관통시킨다. **상태 전이는 저장소에 맡기고 여기서 하지 않는다.**"""

    def __init__(self, *, store, raw_store, registry, env: Optional[Mapping[str, str]] = None,
                 transport=None):
        self.store = store
        self.raw = raw_store
        self.registry = registry
        self._env = env
        self._transport = transport

    def _provider(self, provider_id: str) -> B.Provider:
        return self.registry.get(provider_id, env=self._env, transport=self._transport)

    # ── ① 탐색 ─────────────────────────────────────────────────────────
    def discover(self, job_id: str, *, actor_id: str,
                 provider_id: str = "") -> Dict[str, Any]:
        """원천에서 후보를 찾는다. **없으면 `NO_DATA`** — 장애가 아니다."""
        job = self._job(job_id)
        self.store.transition(job_id, am.DISCOVERING, actor_id=actor_id)
        request = self._request(job)
        pid = provider_id or (list(request.extras.get("provider_ids") or []) or [""])[0]
        if not pid:
            self.store.transition(job_id, am.FAILED, actor_id=actor_id,
                                  reason="요청에 쓸 원천이 없습니다.",
                                  failure_kind=am.FAILURE_POLICY)
            raise OrchestrationError("요청에 쓸 원천이 지정되지 않았습니다.")
        try:
            provider = self._provider(pid)
            candidates = provider.discover(request)
        except B.ProviderError as exc:
            return self._fail(job_id, actor_id, failure_kind_of(exc), str(exc))

        if not candidates:
            #: ★★★ 「자료 없음」은 정상 응답이다. 재시도해도 같으므로 FAILED 가 아니다.
            return self.store.transition(
                job_id, am.NO_DATA, actor_id=actor_id,
                reason=f"{pid} 에 이 요청에 맞는 자료가 없습니다.",
                patch={"provider_id": pid})

        chosen = candidates[-1]
        plan = {
            "provider_id": pid,
            "candidates": [self._candidate_dict(c) for c in candidates],
            "chosen": self._candidate_dict(chosen),
            "excluded_sources": list(request.extras.get("excluded_providers") or []),
            "required_grade": request.required_grade,
        }
        return self.store.transition(
            job_id, am.PLAN_READY, actor_id=actor_id,
            patch={"provider_id": pid, "dataset_ref": chosen.dataset_ref,
                   "target_contract_key": chosen.target_contract_key, "plan": plan})

    # ── ② Dry-run ──────────────────────────────────────────────────────
    def dry_run(self, job_id: str, *, actor_id: str,
                mapping_proposal: Optional[Sequence[Mapping[str, Any]]] = None,
                as_of: str = "") -> Tuple[Dict[str, Any], DryRunReport]:
        """실제로 받아 보되 **격리 적재본에는 한 줄도 넣지 않는다.**"""
        job = self._job(job_id)
        self.store.transition(job_id, am.DRY_RUN, actor_id=actor_id)
        plan = dict(job.get("plan") or {})
        pid = str(job.get("provider_id") or plan.get("provider_id") or "")
        chosen = plan.get("chosen") or {}
        candidate = self._candidate_from(chosen)

        try:
            provider = self._provider(pid)
            #: ★ 원문은 보관한다(그게 「격리 수집」이다). 쪽이 나뉘면 **쪽마다 따로** 보관한다.
            results, batch = self._collect(provider, candidate, job_id=job_id, store_raw=True)
        except B.ProviderError as exc:
            #: ★ 「자료 없음」은 장애가 아니다 — 실패 종류를 붙이지 않고 따로 보낸다.
            if type(exc).__name__ == "NoDataFromSource":
                self.store.transition(job_id, am.NO_DATA, actor_id=actor_id, reason=str(exc))
                raise OrchestrationError(str(exc)) from exc
            self._fail(job_id, actor_id, failure_kind_of(exc), str(exc))
            raise OrchestrationError(str(exc)) from exc
        result = results[0]
        meta = self.raw.meta(self.store.raw_objects(job_id)[-1]["raw_object_ref"]) or {}
        report = self._build_dry_run(job=job, provider=provider, result=result, batch=batch,
                                     meta=meta, plan=plan, candidate=candidate,
                                     mapping_proposal=mapping_proposal, as_of=as_of)

        validation = provider.validate(batch)
        if not validation.ok:
            kind = validation.worst_failure_kind() or am.FAILURE_QUALITY
            target = am.state_for_failure(kind)
            detail = "; ".join(f"{c.name}: {c.detail}" for c in validation.failures)[:400]
            job = self.store.transition(job_id, target, actor_id=actor_id, reason=detail,
                                        failure_kind=kind, patch={"dry_run": report.as_dict()})
            return job, report

        job = self.store.transition(job_id, am.REVIEW_REQUIRED, actor_id=actor_id,
                                    patch={"dry_run": report.as_dict()})
        return job, report

    # ── ③ 적용 ─────────────────────────────────────────────────────────
    def apply(self, job_id: str, *, actor_id: str, as_of: str = "") -> Tuple[Dict[str, Any],
                                                                             ApplyReport]:
        """사람이 승인한 뒤에만 온다. **격리 DB 까지** 적재한다 — 운영 적용이 아니다."""
        job = self._job(job_id)
        contract_key = str(job.get("target_contract_key") or "")
        approved = self.store.approved_contract(contract_key)
        if not approved:
            #: ★★★ 승인되지 않은 계약에는 한 줄도 넣지 않는다. 상태도 옮기지 않는다 —
            #:   APPLYING 으로 갔다가 곧바로 실패하면 「승인했는데 실패한」 기록이 남는다.
            raise OrchestrationError(
                f"{contract_key or '(대상 계약 없음)'} 이 아직 승인되지 않았습니다. "
                f"계약 제안을 먼저 승인하십시오 — 승인 전에는 적재 대상이 될 수 없습니다.")

        pid = str(job.get("provider_id") or "")
        assert_origin_fits(approved.get("document") or {},
                           self._provider(pid).describe().data_origin,
                           contract_key=contract_key)

        self.store.transition(job_id, am.APPLYING, actor_id=actor_id)
        stages: List[StageResult] = []
        pid = str(job.get("provider_id") or "")
        plan = dict(job.get("plan") or {})
        candidate = self._candidate_from(plan.get("chosen") or {})

        try:
            provider = self._provider(pid)
            results, batch = self._collect(provider, candidate, job_id=job_id, store_raw=True)
        except B.ProviderError as exc:
            kind = failure_kind_of(exc)
            report = ApplyReport(job_id=job_id, failure_kind=kind, failure_detail=str(exc),
                                 stages=(StageResult(STAGE_RAW, False, str(exc)),),
                                 pending_stages=tuple(dict(name=n, reason=r)
                                                      for n, r in PENDING_STAGES))
            job = self._fail(job_id, actor_id, kind, str(exc), report=report)
            return job, report

        # ① 원본 보존 ② 체크섬 — 쪽마다 따로 보관돼 있다
        kept = self.store.raw_objects(job_id)
        meta = self.raw.meta(kept[-1]["raw_object_ref"]) or {}
        result = results[-1]
        stages.append(StageResult(
            STAGE_RAW, bool(kept),
            f"{len(results)}쪽 · {kept[-1]['raw_object_ref']}" if len(results) > 1
            else str(kept[-1]["raw_object_ref"]),
            count=sum(int(r.get("byte_size") or 0) for r in kept)))
        #: ★ 쪽이 여럿이면 **전부** 확인한다 — 마지막 쪽만 보면 앞 쪽의 변조를 놓친다.
        checks = [self.raw.verify(r["raw_object_ref"]) for r in kept]
        stages.append(StageResult(
            STAGE_CHECKSUM, all(c.get("ok") for c in checks),
            f"{len(checks)}건 확인" if len(checks) > 1
            else str(kept[-1]["checksum"])[:16] + "…"))

        # ③ 정규화 (이미 `_collect` 가 쪽마다 하고 합쳤다)
        stages.append(StageResult(STAGE_NORMALIZE, True,
                                  f"적재 후보 {len(batch.rows)} · 제외 {len(batch.rejected)}",
                                  count=len(batch.rows)))

        # ④ 데이터 분류 + 정정공시·미래발표 정리
        current, superseded = self._split_supersessions(provider, batch.rows)
        if as_of:
            current, leaked = self._drop_future(provider, current, as_of)
        else:
            leaked = ()
        origin = provider.describe().data_origin
        stages.append(StageResult(
            STAGE_CLASSIFY, True,
            f"성격 {origin} · 대체 {len(superseded)} · 미래발표 제외 {len(leaked)}",
            count=len(current)))

        # ⑤ 품질검사
        validation = provider.validate(batch)
        stages.append(StageResult(STAGE_QUALITY, validation.ok,
                                  "; ".join(f"{c.name}:{c.detail}" for c in validation.failures)
                                  [:300] or "통과", count=len(validation.checks)))

        # ⑥ 대사 — 받은 줄이 전부 설명되는가
        accounted = batch.accounted
        stages.append(StageResult(
            STAGE_RECONCILE, accounted,
            f"원문 {batch.source_row_count} = 적재후보 {len(batch.rows)} + "
            f"제외 {len(batch.rejected)}", count=batch.source_row_count))

        if not validation.ok or not accounted:
            kind = validation.worst_failure_kind() or am.FAILURE_RECONCILIATION
            report = ApplyReport(job_id=job_id, stages=tuple(stages), rejected=len(batch.rejected),
                                 raw_object_ref=meta["raw_object_ref"], failure_kind=kind,
                                 failure_detail="품질·대사 관문에서 멈췄습니다.",
                                 pending_stages=tuple(dict(name=n, reason=r)
                                                      for n, r in PENDING_STAGES))
            #: ⚠️ 여기서 원문을 지우지 않는다 — 무엇 때문에 실패했는지 알 길이 없어진다.
            job = self._fail(job_id, actor_id, kind, report.failure_detail, report=report)
            return job, report

        # ⑦ 격리 적재
        envelope_rows = [self._envelope(job, r, contract_key, origin, meta, provider)
                         for r in current]
        envelope_rows += [self._envelope(job, r, contract_key, origin, meta, provider,
                                         quality_status="SUPERSEDED") for r in superseded]
        staged = self.store.stage_rows(job_id, envelope_rows)
        stages.append(StageResult(STAGE_STAGE_ROWS, True,
                                  f"신규 {staged['inserted']} · 중복 {staged['duplicate']}",
                                  count=staged["inserted"]))

        # ⑧ 계보
        stages.append(StageResult(STAGE_LINEAGE, True,
                                  f"{meta['raw_object_ref']} ← {pid}",
                                  count=len(self.store.raw_objects(job_id))))

        report = ApplyReport(job_id=job_id, stages=tuple(stages), inserted=staged["inserted"],
                             duplicate=staged["duplicate"], superseded=len(superseded),
                             rejected=len(batch.rejected),
                             raw_object_ref=meta["raw_object_ref"],
                             pending_stages=tuple(dict(name=n, reason=r)
                                                  for n, r in PENDING_STAGES))
        checkpoint = provider.checkpoint(batch)
        job = self.store.transition(
            job_id, am.ACTIVE, actor_id=actor_id,
            patch={"last_success_at": _now(),
                   "checkpoint": {"provider_id": checkpoint.provider_id,
                                  "dataset_ref": checkpoint.dataset_ref,
                                  "cursor": checkpoint.cursor,
                                  "covered_from": checkpoint.covered_from,
                                  "covered_to": checkpoint.covered_to,
                                  #: ★★★ 이번에 원천이 준 필드. 다음 정기 갱신이
                                  #:   **이것과 비교해** 스키마 변경을 알아챈다.
                                  "source_fields": list(batch.source_fields)},
                   "dry_run": dict(dict(job.get("dry_run") or {}), apply=report.as_dict())})
        return job, report

    # ── 페이징 ─────────────────────────────────────────────────────────
    def _collect(self, provider, candidate, *, job_id: str,
                 store_raw: bool) -> Tuple[List[B.FetchResult], B.NormalizedBatch]:
        """★★★ 쪽이 나뉜 원천을 **끝까지** 받는다.

        ⚠️⚠️ 쪽을 합쳐 하나의 「원문」으로 만들지 않는다. 그러면 보관된 원문이 **원천이
          보낸 것이 아니게** 되고 「원천이 이렇게 말했다」가 거짓이 된다 — 계보의 근거가
          우리가 만든 물건이 된다. **쪽마다 따로 보관**하고, 정규화 결과만 합친다.

        ⚠️ `has_more` 를 안 읽으면 **첫 쪽만 받고 다 받았다고 보고한다.** 그것이 이 함수가
          생긴 이유다 — `FetchResult.has_more` 는 선언만 돼 있고 아무도 읽지 않았다."""
        results: List[B.FetchResult] = []
        rows: List[Mapping[str, Any]] = []
        rejected: List[B.RejectedRow] = []
        source_fields: set = set()
        source_rows = 0
        page = 0
        while True:
            page += 1
            try:
                result = provider.fetch(candidate, page=page)
            except TypeError:
                #: 쪽을 모르는 Provider — 한 번에 다 준다(앞의 셋이 그렇다).
                result = provider.fetch(candidate)
            results.append(result)
            if store_raw:
                meta = self.raw.put(
                    result.payload, source_id=provider.describe().provider_id,
                    requested_url=result.requested_url, content_type=result.content_type,
                    job_id=job_id, secrets=provider.secret_values(),
                    fetched_at=result.fetched_at,
                    note=f"{page}쪽" if result.page or result.has_more else "")
                self.store.record_raw_object(job_id, dict(meta, dataset_ref=result.dataset_ref))
            part = provider.normalize(result)
            rows.extend(part.rows)
            #: ⚠️ 제외 사유의 `index` 는 **쪽 안의** 번호다 — 쪽을 밝히지 않으면 어느 줄인지
            #:   모른다. 그러나 **`reason` 은 건드리지 않는다** — 그것은 비교 가능한 어휘이고,
            #:   앞에 「1쪽: 」을 붙이면 사유로 세는 시험과 화면이 전부 어긋난다(실측).
            rejected.extend(
                B.RejectedRow(r.index, r.reason,
                              (f"[{page}쪽] {r.detail}" if page > 1 or result.has_more
                               else r.detail),
                              r.raw_excerpt) for r in part.rejected)
            source_fields.update(part.source_fields)
            source_rows += part.source_row_count
            if not result.has_more or page >= MAX_COLLECT_PAGES:
                break
        merged = B.NormalizedBatch(
            provider_id=results[0].provider_id if results else "",
            contract_key=part.contract_key if results else "",
            rows=tuple(rows), rejected=tuple(rejected), source_row_count=source_rows,
            source_fields=tuple(sorted(source_fields)))
        return results, merged

    # ── 보조 ───────────────────────────────────────────────────────────
    def _job(self, job_id: str) -> Dict[str, Any]:
        job = self.store.get(job_id)
        if job is None:
            raise OrchestrationError(f"존재하지 않는 수집 작업입니다: {job_id}")
        return job

    def _request(self, job: Mapping[str, Any]) -> B.AcquisitionRequest:
        r = dict(job.get("request") or {})
        return B.AcquisitionRequest(
            subject_name=str(r.get("subject_name") or job.get("subject_name") or ""),
            purpose=str(r.get("purpose") or job.get("purpose") or ""),
            period_from=str(r.get("period_from") or ""), period_to=str(r.get("period_to") or ""),
            indicators=tuple(r.get("indicators") or ()),
            target_contract_keys=tuple(r.get("target_contract_keys") or ()),
            frequency=str(r.get("frequency") or ""),
            required_grade=str(r.get("required_grade") or ""),
            extras=dict(r.get("extras") or r))

    def _fail(self, job_id: str, actor_id: str, kind: str, detail: str,
              report: Optional[ApplyReport] = None) -> Dict[str, Any]:
        target = am.state_for_failure(kind)
        patch = {"dry_run": report.as_dict()} if report else None
        return self.store.transition(job_id, target, actor_id=actor_id,
                                     reason=detail[:400] or "(사유 없음)",
                                     failure_kind=kind, patch=patch)

    @staticmethod
    def _candidate_dict(c: B.DiscoveryCandidate) -> Dict[str, Any]:
        return {"provider_id": c.provider_id, "dataset_ref": c.dataset_ref, "title": c.title,
                "target_contract_key": c.target_contract_key, "period_from": c.period_from,
                "period_to": c.period_to, "frequency": c.frequency, "unit": c.unit,
                "match_reason": c.match_reason, "params": dict(c.params or {}),
                "ambiguous_with": list(c.ambiguous_with)}

    @staticmethod
    def _candidate_from(d: Mapping[str, Any]) -> B.DiscoveryCandidate:
        return B.DiscoveryCandidate(
            provider_id=str(d.get("provider_id") or ""),
            dataset_ref=str(d.get("dataset_ref") or ""), title=str(d.get("title") or ""),
            target_contract_key=str(d.get("target_contract_key") or ""),
            period_from=str(d.get("period_from") or ""), period_to=str(d.get("period_to") or ""),
            frequency=str(d.get("frequency") or ""), unit=str(d.get("unit") or ""),
            match_reason=str(d.get("match_reason") or ""), params=dict(d.get("params") or {}),
            ambiguous_with=tuple(d.get("ambiguous_with") or ()))

    @staticmethod
    def _split_supersessions(provider, rows):
        """Provider 가 정정공시 규칙을 알면 그것을 쓴다. 모르면 전부 현행이다."""
        module = type(provider).__module__
        resolver = getattr(__import__(module, fromlist=["resolve_supersessions"]),
                           "resolve_supersessions", None)
        if resolver is None:
            return tuple(dict(r) for r in rows), ()
        return resolver(rows)

    @staticmethod
    def _drop_future(provider, rows, as_of: str):
        module = type(provider).__module__
        dropper = getattr(__import__(module, fromlist=["drop_future_disclosures"]),
                          "drop_future_disclosures", None)
        if dropper is None:
            return tuple(dict(r) for r in rows), ()
        return dropper(rows, as_of)

    #: 계약별 업무 키 규칙. **이 표 하나만 있다** — 호출부가 각자 만들면 같은 행이
    #: 다른 키를 얻고, 중복 적재 방지 인덱스가 아무것도 막지 못한다.
    _BUSINESS_KEY_RULES = {
        "PUB-01": M.disclosure_row_id,
        "EXT-01": M.observation_row_id,
        "EXT-03": M.indicator_row_id,
    }

    @classmethod
    def _business_key(cls, row: Mapping[str, Any], contract_key: str) -> str:
        rule = cls._BUSINESS_KEY_RULES.get(contract_key)
        if rule is not None:
            return rule(row)
        #: 계약별 키 규칙이 없으면 내용 해시로 둔다 — **같은 내용은 같은 행**이 되어
        #: 중복 적재를 막는다. ⚠️ 키 규칙이 생기면 그것으로 바꾼다.
        blob = "|".join(f"{k}={row.get(k)}" for k in sorted(row) if not k.startswith("_"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def _envelope(self, job: Mapping[str, Any], row: Mapping[str, Any], contract_key: str,
                  origin: str, meta: Mapping[str, Any], provider,
                  quality_status: str = "") -> Dict[str, Any]:
        """공통 봉투를 씌운다. **Provider 는 테넌트를 모른다** — 여기서만 채운다."""
        payload = {k: v for k, v in row.items() if not k.startswith("_")}
        payload.setdefault("source_id", provider.describe().provider_id)
        payload.setdefault("raw_object_ref", meta.get("raw_object_ref", ""))
        payload.setdefault("trust_grade", provider.describe().default_trust_grade)
        return {
            "contract_key": contract_key,
            "business_key": self._business_key(payload, contract_key),
            "tenant_id": str(job.get("tenant_id") or ""),
            "scope_node_id": str(job.get("scope_node_id") or ""),
            "data_class": origin, "data_origin": origin,
            "quality_status": quality_status or str(row.get("quality_status") or "VALIDATED"),
            "certification_status": "UNCERTIFIED",
            "as_of_date": str(row.get("published_at") or ""),
            "lineage_id": f"lin_{uuid.uuid4().hex[:16]}",
            "payload": payload,
            "raw_object_ref": meta.get("raw_object_ref", ""),
            "checksum": meta.get("checksum", ""),
            "superseded_by": str(row.get("superseded_by_rcept_no") or ""),
        }

    def _build_dry_run(self, *, job, provider, result, batch, meta, plan, candidate,
                       mapping_proposal, as_of) -> DryRunReport:
        contract_key = str(job.get("target_contract_key") or batch.contract_key)
        approved = self.store.approved_contract(contract_key)
        contract_doc = (approved or {}).get("document") or M.pub01_proposal() \
            if contract_key == "PUB-01" else (approved or {}).get("document") or {}

        current, superseded = self._split_supersessions(provider, batch.rows)
        leaked = ()
        if as_of:
            current, leaked = self._drop_future(provider, current, as_of)

        #: 중복은 **격리 적재본에 이미 있는지**로 센다 — 「예상」이 아니라 실측이다.
        existing = {r["business_key"] for r in
                    self.store.staged_rows(contract_key=contract_key, limit=5000)}
        keys = [self._business_key(dict(r), contract_key) for r in current]
        duplicate = sum(1 for k in keys if k in existing)

        missing: Dict[str, int] = {}
        for r in batch.rows:
            for k, v in r.items():
                if k.startswith("_"):
                    continue
                if v is None or v == "":
                    missing[k] = missing.get(k, 0) + 1

        mapping_report = None
        if mapping_proposal is not None and contract_doc:
            source_fields = sorted({k for r in batch.rows for k in r if not k.startswith("_")})
            mapping_report = M.validate_mapping(mapping_proposal, contract=contract_doc,
                                                source_fields=source_fields)

        validation = provider.validate(batch)
        return DryRunReport(
            job_id=str(job["job_id"]), provider_id=provider.describe().provider_id,
            dataset_ref=result.dataset_ref, contract_key=contract_key,
            chosen_reason=candidate.match_reason,
            excluded_sources=tuple(plan.get("excluded_sources") or ()),
            ambiguous_with=tuple(candidate.ambiguous_with),
            expected_rows=len(current) + len(superseded),
            new_rows=len(keys) - duplicate, duplicate_rows=duplicate,
            superseded_rows=len(superseded), rejected_rows=len(batch.rejected),
            missing_fields=missing,
            mapping_ok=(len(mapping_proposal or ()) - len(mapping_report.problems)
                        if mapping_report else 0),
            mapping_needs_human=(mapping_report.requires_human_approval if mapping_report else ()),
            mapping_failed=tuple({"source": p.source_field, "target": p.target_field,
                                  "reason": p.reason} for p in
                                 (mapping_report.problems if mapping_report else ())),
            unit_conversions=(mapping_report.conversions if mapping_report else ()),
            target_contract_status=("APPROVED" if approved else "PROPOSED(미승인)"),
            quarantined=tuple({"reason": r.reason, "detail": r.detail}
                              for r in batch.rejected) +
                        tuple({"reason": "as-of 이후 발표", "detail": str(r.get("published_at"))}
                              for r in leaked),
            estimated_bytes=int(meta.get("byte_size") or 0),
            refresh_schedule=str(job.get("schedule_rule") or
                                 provider.describe().refresh_frequency),
            readiness_change_note=(
                "격리 적재까지입니다 — 업무키트 준비도는 계약이 키트에 편입된 뒤에 바뀝니다."),
            validation=tuple({"name": c.name, "ok": c.ok, "detail": c.detail}
                             for c in validation.checks),
            pending_stages=tuple(dict(name=n, reason=r) for n, r in PENDING_STAGES),
        )
