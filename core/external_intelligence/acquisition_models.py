"""[DAO-0] 데이터 수집·정비 오케스트레이터의 **닫힌 어휘**.

이 파일은 코드를 거의 담지 않는다. 담는 것은 «이 시스템에 어떤 상태가 존재하는가» 이고,
그것을 한 곳에 두는 이유는 이 저장소가 같은 실패를 반복했기 때문이다 — 어떤 값을 두 곳에서
각자 정의하면 **두 정의는 반드시 갈린다.** 갈린 뒤에도 오류는 나지 않는다. 한쪽이 모르는
값을 다른 쪽이 쓸 뿐이고, 그 순간 화면과 원장이 다른 이야기를 한다.

## 왜 기존 상태 어휘를 재사용하지 않는가

이 저장소에는 이미 네 벌의 상태 목록이 있고, 착수 전에 전부 읽었다.

    결속(BINDING)   DRAFT VALIDATED APPROVED ACTIVE RETIRED BLOCKED
    스냅샷(SNAPSHOT) RAW PROFILED STANDARDIZED RECONCILED DEMO_CERTIFIED QUARANTINED REVOKED
    조사작업(JOB)    SCHEDULED RUNNING CANDIDATE_READY ACCEPTED REJECTED FAILED CANCELLED
    프로파일(PROFILE) DRAFT REVIEW_REQUIRED APPROVED PAUSED RETIRED

★ 셋은 **재사용한다.** 수집이 실제로 값을 넣는 단계(원본보존→정규화→품질검사→대사→인증)는
  `SNAPSHOT_STATES` 가 이미 정확히 그 순서다. 여기서 평행 파이프라인을 만들면 「인증된 판」이
  두 곳에서 각자 정의된다.

★★★ 그런데 **수집 작업 자체**는 넷 중 어느 것도 아니다. 조사작업(JOB)은 «문서를 찾는» 일이고
  결과물이 후보 링크다. 수집작업은 «값을 들여오는» 일이고 결과물이 인증판과 키트 결속이다.
  둘을 한 목록으로 뭉개면 `CANDIDATE_READY` 인 수집작업이 생기고, 그것이 무슨 뜻인지 아무도
  답할 수 없다. 그래서 **이 하나만 새로 만든다.**

## ⚠️ `NO_DATA` 는 지시에 없던 상태다 — 왜 더했나

지시는 「장애와 『자료 없음』을 같은 상태로 처리하지 않는다」를 요구하면서 예외 상태로
`FAILED / QUARANTINED / DISABLED` 셋만 줬다. 셋으로는 그 요구를 표현할 수 없다.

    FAILED    원천이 응답하지 않았다 · 인증이 거부됐다 · 스키마가 깨졌다  → **다시 시도한다**
    NO_DATA   원천이 정상 응답했고 그 기간에 해당 자료가 **없다**        → **다시 시도해도 같다**

둘을 `FAILED` 하나로 접으면 스케줄러가 없는 자료를 영원히 재시도하고, 사람은 「연동이 고장났다」
고 읽는다. 반대로 `NO_DATA` 를 성공으로 접으면 **0건이 적재 완료로 보인다** — 이 저장소가
`readiness.py` 에서 「부족한 값을 0으로 채우지 않는다」로 막아 온 바로 그 상태다.

## 원장 기록

전환마다 `decision_ledger.append()` 를 부른다. 주체 이름은 새로 만들지 않고 **이미 예약돼
있던 `external_connection`** 을 쓴다(`decision_ledger.SUBJECT_TYPES` 에 선언만 되고 쓰는
곳이 0곳이었다).
"""
from __future__ import annotations

from typing import Dict, Tuple

# ── 수집 작업 상태 ────────────────────────────────────────────────────────────
DRAFT = "DRAFT"                      # 요청이 구조화됐다. 아직 아무것도 찾지 않았다.
DISCOVERING = "DISCOVERING"          # 원천 후보를 탐색 중이다. 네트워크는 읽기만 한다.
PLAN_READY = "PLAN_READY"            # 수집 계획과 매핑 제안이 나왔다. 아직 받아오지 않았다.
DRY_RUN = "DRY_RUN"                  # 격리 환경에서 실제로 받아 봤다. **운영에 쓰지 않는다.**
REVIEW_REQUIRED = "REVIEW_REQUIRED"  # 사람이 볼 차례다. 여기서 저절로 넘어가지 않는다.
APPLYING = "APPLYING"                # 적용 중. 중간에 죽으면 이 상태로 남아 다음 판단을 받는다.
ACTIVE = "ACTIVE"                    # 적용됐고 정기 갱신 대상이다.

FAILED = "FAILED"                    # 장애 — 다시 시도할 값이 있다.
NO_DATA = "NO_DATA"                  # 정상 응답 · 해당 자료 없음 — 다시 시도해도 같다.
QUARANTINED = "QUARANTINED"          # 받아왔으나 품질·대사에서 걸렸다. 원문은 지우지 않는다.
DISABLED = "DISABLED"                # 사람이 껐다. 스케줄러가 건드리지 않는다.

ACQUISITION_STATES: Tuple[str, ...] = (
    DRAFT, DISCOVERING, PLAN_READY, DRY_RUN, REVIEW_REQUIRED, APPLYING, ACTIVE,
    FAILED, NO_DATA, QUARANTINED, DISABLED,
)

#: ★★★ 전이표. 여기 없는 전이는 **일어나지 않는다** — 저장소가 거부한다.
#:   ⚠️ `DRY_RUN → ACTIVE` 가 없는 것이 이 표의 핵심이다. 사람 검토를 건너뛰는 경로를
#:     한 줄이라도 남기면 언젠가 그 줄로 간다.
ACQUISITION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    DRAFT:           (DISCOVERING, DISABLED, FAILED),
    DISCOVERING:     (PLAN_READY, NO_DATA, FAILED, DISABLED),
    PLAN_READY:      (DRY_RUN, DISABLED, FAILED),
    DRY_RUN:         (REVIEW_REQUIRED, QUARANTINED, NO_DATA, FAILED, DISABLED),
    REVIEW_REQUIRED: (APPLYING, PLAN_READY, DISABLED),
    APPLYING:        (ACTIVE, QUARANTINED, FAILED),
    ACTIVE:          (DRY_RUN, QUARANTINED, DISABLED, FAILED),
    FAILED:          (DRAFT, DISCOVERING, DISABLED),
    NO_DATA:         (DRAFT, DISCOVERING, DISABLED),
    QUARANTINED:     (REVIEW_REQUIRED, DISABLED),
    DISABLED:        (DRAFT,),
}

#: 스케줄러가 건드려도 되는 유일한 상태(지시 9). 다른 상태의 작업은 사람이 움직인다.
SCHEDULABLE_STATES: Tuple[str, ...] = (ACTIVE,)

#: 사람 결정 없이는 넘어갈 수 없는 관문.
HUMAN_GATE_STATES: Tuple[str, ...] = (REVIEW_REQUIRED, QUARANTINED)


# ── 자료의 성격 ──────────────────────────────────────────────────────────────
#: ⚠️ 계약 JSON(`classification.data_class`)은 지금까지 **코드가 검사하지 않는 자유 문자열**
#:   이었고 35개 전부 `SYNTHETIC` 이었다. 여기서 닫는다 — 닫지 않으면 공개 재무자료가
#:   `REAL` 로 적히는 날이 온다.
ORIGIN_REAL = "REAL"                          # 회사 내부 실적. 이 시스템은 아직 넣지 않는다.
ORIGIN_PUBLIC_DISCLOSED = "PUBLIC_DISCLOSED"  # 공시·공식통계. 사실이지만 **내부 실적이 아니다.**
ORIGIN_SYNTHETIC = "SYNTHETIC"                # 시연용 합성. 기존 35개 계약이 쓰는 값.
ORIGIN_SYNTHETIC_DERIVED = "SYNTHETIC_DERIVED"  # 공개 총계에 맞춰 만든 합성 상세.

DATA_ORIGINS: Tuple[str, ...] = (ORIGIN_REAL, ORIGIN_PUBLIC_DISCLOSED,
                                 ORIGIN_SYNTHETIC, ORIGIN_SYNTHETIC_DERIVED)

#: ★★★ 경영 판단에 쓸 수 있는 성격. `PUBLIC_DISCLOSED` 가 여기 **없는** 이유는
#:   공개 재무제표가 틀려서가 아니라, 내부 매입·고객·BOM 실적을 **대체하지 않기** 때문이다.
#:   총계 대사에는 쓰고 상세 계산의 근거로는 쓰지 않는다.
ORIGINS_FOR_INTERNAL_ACTUAL: Tuple[str, ...] = (ORIGIN_REAL,)


# ── 실패의 종류 ──────────────────────────────────────────────────────────────
FAILURE_TRANSPORT = "TRANSPORT"      # 응답 없음·타임아웃·5xx
FAILURE_AUTH = "AUTH"                # 인증키 없음·만료·거부
FAILURE_SCHEMA_DRIFT = "SCHEMA_DRIFT"  # 원천이 모양을 바꿨다
FAILURE_POLICY = "POLICY"            # 라이선스 미확인·미승인 원천·범위 밖
FAILURE_QUALITY = "QUALITY"          # 단위 불일치·미매핑 코드
FAILURE_RECONCILIATION = "RECONCILIATION"  # 합계·행 수 대사 실패

FAILURE_KINDS: Tuple[str, ...] = (FAILURE_TRANSPORT, FAILURE_AUTH, FAILURE_SCHEMA_DRIFT,
                                  FAILURE_POLICY, FAILURE_QUALITY, FAILURE_RECONCILIATION)

#: 격리(QUARANTINED)로 가는 실패. 나머지는 FAILED 다.
#: ⚠️ `core.data_preparation.models.QUARANTINE_KINDS` 와 **같은 둘**이다 — 이름을 맞춰 둔다.
QUARANTINE_FAILURES: Tuple[str, ...] = (FAILURE_QUALITY, FAILURE_RECONCILIATION)


class AcquisitionStateError(ValueError):
    """허용되지 않은 전이 — 4xx 로 전달한다."""


def assert_transition(current: str, target: str) -> None:
    """전이 가능성만 판정한다. **저장하지 않는다** — 저장소가 부른다.

    ⚠️ 검사를 저장소 안에만 두면 「왜 안 되는지」를 사람에게 말해 줄 층이 없어진다.
      반대로 여기에만 두면 경쟁 상태에서 뚫린다. `source_binding.py` 와 같은 이유로 **둘 다** 둔다."""
    cur = str(current or "")
    tgt = str(target or "")
    if cur not in ACQUISITION_STATES:
        raise AcquisitionStateError(f"모르는 현재 상태입니다: {cur!r}")
    if tgt not in ACQUISITION_STATES:
        raise AcquisitionStateError(f"모르는 목표 상태입니다: {tgt!r}")
    allowed = ACQUISITION_TRANSITIONS.get(cur, ())
    if tgt not in allowed:
        raise AcquisitionStateError(
            f"{cur} 에서 {tgt} 로는 갈 수 없습니다. 갈 수 있는 곳: {', '.join(allowed) or '없음'}")


def assert_origin(value: str) -> str:
    """자료 성격을 닫힌 목록으로 강제한다."""
    v = str(value or "").strip()
    if v not in DATA_ORIGINS:
        raise AcquisitionStateError(
            f"자료 성격은 {DATA_ORIGINS} 중 하나여야 합니다: {v!r}")
    return v


def assert_failure_kind(value: str) -> str:
    v = str(value or "").strip()
    if v not in FAILURE_KINDS:
        raise AcquisitionStateError(f"실패 종류는 {FAILURE_KINDS} 중 하나여야 합니다: {v!r}")
    return v


def state_for_failure(kind: str) -> str:
    """실패 종류가 어느 상태로 가는지. **호출부가 각자 판단하지 않게** 여기서 정한다."""
    return QUARANTINED if assert_failure_kind(kind) in QUARANTINE_FAILURES else FAILED
