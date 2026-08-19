"""[BDR-201] 값 목록과 상태 전이 — **판정이 아니라 어휘**를 두는 곳.

⚠️⚠️ 이 모듈은 아무것도 import 하지 않는다. 상태 전이 규칙이 저장 계층과 API 계층에
  각각 구현되면 두 곳이 반드시 갈라진다([I-4 2.2a] 에서 실제로 겪었다). 전이를 묻는
  질문은 전부 여기로 온다.
"""
from typing import Any, Dict, Tuple

# ── Source Binding 상태 ──────────────────────────────────────────────────
#
# ```text
# DRAFT → VALIDATED → APPROVED → ACTIVE → RETIRED
#                   ↘ BLOCKED
# ```
DRAFT = "DRAFT"
VALIDATED = "VALIDATED"
APPROVED = "APPROVED"
ACTIVE = "ACTIVE"
RETIRED = "RETIRED"
BLOCKED = "BLOCKED"

BINDING_STATES: Tuple[str, ...] = (DRAFT, VALIDATED, APPROVED, ACTIVE, RETIRED, BLOCKED)

#: 어느 상태에서 어디로 갈 수 있는가. **여기 없는 전이는 없는 전이다.**
#:
#: ★ `BLOCKED` 에서 `DRAFT` 로 돌아갈 수 있다 — 막힌 후보를 고쳐 다시 낼 수 있어야
#:   한다. 돌아갈 길이 없으면 사람들은 새 후보를 만들고, 그러면 「무엇이 왜 막혔는가」의
#:   이력이 끊긴다.
#: ⚠️ `RETIRED` 에서는 어디로도 가지 않는다. 되살리려면 새 후보를 만든다 — 되살린
#:   결속은 「언제부터 다시 쓰였나」가 흐려진다.
BINDING_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    DRAFT: (VALIDATED, BLOCKED),
    VALIDATED: (APPROVED, BLOCKED, DRAFT),
    APPROVED: (ACTIVE, BLOCKED, DRAFT),
    ACTIVE: (RETIRED,),
    BLOCKED: (DRAFT,),
    RETIRED: (),
}

#: 지원 Provider. `CONNECTOR_QUERY` 는 **계약과 화면 자리만** 두고 아직 안 만든다.
PROVIDER_FILE_SNAPSHOT = "FILE_SNAPSHOT"
PROVIDER_AFS_NATIVE = "AFS_NATIVE"
PROVIDER_CONNECTOR_QUERY = "CONNECTOR_QUERY"

PROVIDERS: Tuple[str, ...] = (PROVIDER_FILE_SNAPSHOT, PROVIDER_AFS_NATIVE,
                              PROVIDER_CONNECTOR_QUERY)
#: MVP 에서 **실제로 물질화되는** Provider.
#: ⚠️ 「목록에 있으니 된다」가 아니다 — 있는 것과 되는 것을 구분하지 않으면 시연에서
#:   「선택은 되는데 아무 일도 안 일어나는」 화면이 나온다.
MATERIALIZABLE_PROVIDERS: Tuple[str, ...] = (PROVIDER_FILE_SNAPSHOT, PROVIDER_AFS_NATIVE)

#: 실행 문맥. 운영 자원은 셋 다 **명시**해야 만들어진다(공용 기본값 금지).
#: ★★★ [I-4 8 / Wave F-3] `SYNTHETIC_TEST` 를 **의도적으로** 연다.
#:
#: ⚠️⚠️ 종단 카나리가 이 자리에서 멈춰 드러났다 — Preview 는 `SYNTHETIC_TEST` 문맥에서만
#:   돌고(F-1), Dispatch 는 매 요청 범위를 대조한다(BDR-6). 그런데 업무 데이터에 그
#:   문맥이 없어서 **Preview 는 어떤 파일 Snapshot 도 읽을 수 없었다.** 설계서가
#:   「파일 Snapshot 은 시연용 복제/참조 정책을 명시한다」고 한 자리가 바로 여기다.
#:
#: ★ 열어도 안전한 이유: 이것은 **별도의 범위**다. `REAL` 인증판과 섞이지 않고,
#:   범위 대조가 둘을 갈라 놓는다. 즉 Preview 에서 본 것은 운영 기준선이 되지 않는다 —
#:   애초에 다른 문맥의 판이기 때문이다.
#: ⚠️ 조직 문맥(`enterprise_context.ENTITY_MODES`)에는 **넣지 않는다.** 넣으면 사람이
#:   그 문맥으로 실제 조직 자료를 만들 수 있게 되고, 「미리보기 전용」이 사라진다.
ENTITY_MODE_SYNTHETIC = "SYNTHETIC_TEST"
ENTITY_MODES: Tuple[str, ...] = ("REAL", "VIRTUAL", "COMPETITOR_REFERENCE",
                                 ENTITY_MODE_SYNTHETIC)

#: 키트 모드 — 시연용 합성 데이터와 실제 업무 데이터를 **섞지 않는다.**
KIT_MODE_DEMO = "DEMO/SYNTHETIC"
KIT_MODE_REAL = "REAL"
KIT_MODES: Tuple[str, ...] = (KIT_MODE_DEMO, KIT_MODE_REAL)


class DataPreparationError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


class StateConflict(DataPreparationError):
    """지금 상태에서 할 수 없는 일 — 라우트가 **409** 로 바꾼다."""


def can_transition(current: Any, target: Any) -> bool:
    """이 전이가 허용되는가. **모르는 상태는 허용하지 않는다.**"""
    return str(target or "") in BINDING_TRANSITIONS.get(str(current or ""), ())


def assert_transition(current: Any, target: Any) -> None:
    """허용되지 않으면 `StateConflict`. 사유에 **가능한 다음 상태**를 담는다 —
    막기만 하고 갈 곳을 안 알려 주면 사용자는 아무 버튼이나 누른다."""
    cur, tgt = str(current or ""), str(target or "")
    if cur not in BINDING_TRANSITIONS:
        raise StateConflict(f"알 수 없는 현재 상태입니다: {cur or '(없음)'}")
    if tgt not in BINDING_STATES:
        raise StateConflict(f"알 수 없는 목표 상태입니다: {tgt or '(없음)'}")
    if not can_transition(cur, tgt):
        allowed = BINDING_TRANSITIONS[cur]
        raise StateConflict(
            f"«{cur}» 에서 «{tgt}» 로 갈 수 없습니다 — 가능한 다음 상태: "
            f"{', '.join(allowed) if allowed else '(없음. 종료 상태입니다)'}")


def assert_context(tenant_id: Any, scope_node_id: Any, entity_mode: Any) -> None:
    """운영 자원의 **실행 문맥 세 값**을 강제한다.

    ★★★ 미지정 공용 기본값을 두지 않는다. 「비어 있으면 전사」 같은 기본값은 한 번
      새면 되돌릴 수 없다 — 그 자원이 어느 조직 것이었는지 아무도 모르게 되기 때문이다.
    ⚠️ `tenant_id` 는 서버가 문맥에서 파생한다(요청 본문에서 받지 않는다). 여기서는
      «파생에 실패한 채로 저장되지 않는가» 만 본다."""
    if not str(tenant_id or "").strip():
        raise DataPreparationError("tenant 를 확정하지 못했습니다 — 문맥 없이 만들지 않습니다.")
    if not str(scope_node_id or "").strip():
        raise DataPreparationError(
            "scope_node_id 가 필요합니다 — 조직 범위 없는 자원은 권한 필터에서 «미기록» 이 "
            "되어 통제 밖에 놓입니다.")
    mode = str(entity_mode or "").strip()
    if mode not in ENTITY_MODES:
        raise DataPreparationError(
            f"entity_mode 는 {list(ENTITY_MODES)} 중 하나여야 합니다(현재 {mode or '(없음)'}) — "
            f"실제 데이터와 가상 시나리오를 섞으면 둘 다 못 쓴다.")


def provider_supported(provider: Any) -> bool:
    return str(provider or "") in PROVIDERS


def provider_materializable(provider: Any) -> bool:
    """지금 **실제로 데이터가 흐르는가.** 목록에 있는 것과 되는 것은 다르다."""
    return str(provider or "") in MATERIALIZABLE_PROVIDERS


# ── [BDR-3] Dataset Snapshot 파이프라인 ──────────────────────────────────
#
# ```text
# RAW → PROFILED → STANDARDIZED → RECONCILED → CERTIFIED | QUARANTINED | REVOKED
# ```
RAW = "RAW"
PROFILED = "PROFILED"
STANDARDIZED = "STANDARDIZED"
RECONCILED = "RECONCILED"
DEMO_CERTIFIED = "DEMO_CERTIFIED"
QUARANTINED = "QUARANTINED"
REVOKED = "REVOKED"

SNAPSHOT_STATES: Tuple[str, ...] = (RAW, PROFILED, STANDARDIZED, RECONCILED,
                                    DEMO_CERTIFIED, QUARANTINED, REVOKED)

#: ★★★ **인증 뒤에는 앞으로 못 간다.** 정정은 새 Snapshot 을 만든다.
#:
#: ⚠️ 인증된 것을 고칠 수 있게 두면 「우리가 인증한 그 숫자」가 무엇이었는지 아무도
#:   답할 수 없다 — 보고서에 실린 값과 지금 표의 값이 달라도 알아챌 방법이 없다.
#: ⚠️ 격리(`QUARANTINED`)에서는 되돌아가지 않는다. 고친 파일은 **새 Snapshot** 이다 —
#:   같은 Snapshot 을 고쳐 통과시키면 「무엇이 왜 격리됐는가」의 이력이 지워진다.
SNAPSHOT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    RAW: (PROFILED, QUARANTINED),
    PROFILED: (STANDARDIZED, QUARANTINED),
    STANDARDIZED: (RECONCILED, QUARANTINED),
    RECONCILED: (DEMO_CERTIFIED, QUARANTINED),
    DEMO_CERTIFIED: (REVOKED,),
    QUARANTINED: (),
    REVOKED: (),
}

#: 데이터의 성격. **시연용 합성 데이터와 실제 업무 데이터를 절대 섞지 않는다.**
#:
#: ⚠️⚠️ 실제 Data Owner 가 없는 상태에서 `CERTIFIED ACTUAL` 을 주장하면, 그 숫자를
#:   본 사람은 그것이 검증된 실적이라고 믿는다. 시연 자료로 경영 판단을 하게 되는
#:   경로가 바로 거기서 열린다.
#: ★★★ 격리 «사유» 는 사람이 읽는 문장이고, 격리 «종류» 는 **기계가 읽는 코드**다.
#: ⚠️ 문장으로 분기하면 문구를 다듬는 순간 판정이 조용히 바뀐다 — 시험은 그대로 통과한다.
QUARANTINE_QUALITY = "QUALITY"                  # 미매핑 코드·단위 불일치
QUARANTINE_RECONCILIATION = "RECONCILIATION"    # 원천 합계·행 수 대사 실패
QUARANTINE_KINDS: Tuple[str, ...] = (QUARANTINE_QUALITY, QUARANTINE_RECONCILIATION)

DATA_KIND_DEMO = "DEMO/SYNTHETIC"
DATA_KIND_REAL = "REAL"
DATA_KINDS: Tuple[str, ...] = (DATA_KIND_DEMO, DATA_KIND_REAL)


def can_snapshot_transition(current: Any, target: Any) -> bool:
    return str(target or "") in SNAPSHOT_TRANSITIONS.get(str(current or ""), ())


def assert_snapshot_transition(current: Any, target: Any) -> None:
    """허용되지 않으면 `StateConflict`. **인증 뒤 수정은 여기서 막힌다.**"""
    cur, tgt = str(current or ""), str(target or "")
    if cur not in SNAPSHOT_TRANSITIONS:
        raise StateConflict(f"알 수 없는 현재 상태입니다: {cur or '(없음)'}")
    if tgt not in SNAPSHOT_STATES:
        raise StateConflict(f"알 수 없는 목표 상태입니다: {tgt or '(없음)'}")
    if not can_snapshot_transition(cur, tgt):
        allowed = SNAPSHOT_TRANSITIONS[cur]
        raise StateConflict(
            f"«{cur}» 에서 «{tgt}» 로 갈 수 없습니다 — 가능한 다음 상태: "
            f"{', '.join(allowed) if allowed else '(없음. 정정은 새 Snapshot 을 만듭니다)'}")
