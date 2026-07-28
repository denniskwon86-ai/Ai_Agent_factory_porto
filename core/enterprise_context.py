"""Enterprise Context (ECM-lite) — `docs/design_enterprise_context_master.md` 의 최소 선점 구현.

## 이 파일이 지금 존재하는 이유

ECM 설계서 최상단 선행 규칙이 **"이후 구현되는 MDM·카탈로그·MCP·권한·상담사·SW 생성기·
시뮬레이션은 `tenant → 기업집단 → 법인 → 사업부 → 사업장/공장` 문맥과 실제/가상/경쟁사 상태를
명시적으로 가져야 한다"** 고 못 박았다. 상담사(M0)는 그 적용 대상이다.

전체 ECM(E1: `enterprise_entities`/`organization_nodes`/`organization_edges`/`enterprise_profiles`
+ 프로필 상속 리솔버 + 전역 스위처)은 아직 없다. 그런데 상담·Blueprint 는 **사용자 데이터**라,
문맥 키 없이 데이터가 쌓이기 시작하면 나중에 저장분 마이그레이션 + 화면 + API 를 한꺼번에
고쳐야 한다. 그래서 **문맥 키와 격리 규칙만 먼저 선점**한다(데이터 0행인 지금이 가장 싸다).

## 지금 하는 것 / 안 하는 것

| | 상태 |
|---|---|
| 문맥 키(`tenant_id`·`enterprise_scope_id`·`entity_mode`) 표준화와 전달 | ✅ 여기 |
| `entity_mode` 기반 조회 격리(문맥이 다른 자료가 섞이지 않게) | ✅ 여기 |
| 조직 노드·관계 그래프, 프로필 상속 해석 | ❌ E1 |
| 프로필 기반 템플릿·질문·에이전트 추천 차별화(수용 기준 3) | ❌ E2 |
| 가상 조직 복제·스냅샷·가정, 경쟁사 근거 관리 | ❌ E3 |

⚠️ **`REAL` 외의 문맥 생성은 지금 막는다.** 설계서 §2.1-4 는 "가상 조직은 실제 조직의 안전한
  복제본이지 운영계의 우회 통로가 아니다"라고 하고, 그 안전장치(격리 스냅샷·가정 세트·외부 연계
  차단·복사 정책)는 E3 의 내용이다. 안전장치 없이 `VIRTUAL` 자료를 만들 수 있게 열어두면
  가정값이 실제와 섞인 채 쌓인다 — 그게 이 설계서가 가장 경계하는 일이다(§13 위험표).
  `entity_mode` 컬럼은 **기록·격리의 기반으로만** 먼저 깔아둔다.

## E1 이 오면 바뀌는 것

`enterprise_scope_id` 는 지금 부서 id(`org_directory`)를 담지만, E1 에서 ECM `node_id` 로
승격된다. 설계서 §10.1 이 "기존 모듈을 한 번에 교체하지 않고 ECM 을 공통 범위·프로필 해석
계층으로 먼저 도입한 뒤 점진 이행"하라고 한 그 경로다. 그래서 이 모듈은 값의 **출처를 함께
기록**한다(`scope_kind`) — 나중에 무엇을 승격해야 하는지 알 수 있어야 한다.
"""
from dataclasses import dataclass
from typing import Optional

import config

# ── §4.3 entity_mode ──────────────────────────────────────────────────────
ENTITY_MODE_REAL = "REAL"
ENTITY_MODE_VIRTUAL = "VIRTUAL"
ENTITY_MODE_COMPETITOR = "COMPETITOR_REFERENCE"
ENTITY_MODES = (ENTITY_MODE_REAL, ENTITY_MODE_VIRTUAL, ENTITY_MODE_COMPETITOR)

# 지금 생성이 허용되는 모드. 위 docstring 의 이유로 REAL 만 열려 있다.
CREATABLE_ENTITY_MODES = (ENTITY_MODE_REAL,)

ENTITY_MODE_KO = {
    ENTITY_MODE_REAL: "실제 운영 문맥",
    ENTITY_MODE_VIRTUAL: "가상 시나리오",
    ENTITY_MODE_COMPETITOR: "경쟁사 참조",
}

# `enterprise_scope_id` 가 무엇을 담고 있는가. E1 승격 대상을 식별하기 위한 표시다.
SCOPE_KIND_DEPARTMENT = "department"    # 현재 — org_directory 부서 id
SCOPE_KIND_ECM_NODE = "ecm_node"        # E1 이후 — ECM organization_nodes.node_id


class EnterpriseContextError(ValueError):
    """문맥 검증 실패 — 라우트가 400 으로 바꾼다."""


@dataclass(frozen=True)
class EnterpriseContext:
    """한 요청이 "어느 회사·조직·상태를 위해" 실행되는지.

    설계서 §5.1 은 이것을 "모든 API·SSE·LLM 호출에 전달되는 토큰"으로 정의한다. 지금은 그
    토큰의 **최소 골격**이다 — 기업집단·법인·사업부 단계는 E1 에서 `enterprise_scope_id` 가
    ECM 노드를 가리키게 되면 노드 조회로 해석된다(여기서 계층을 흉내내지 않는다.
    가짜 계층을 만들면 E1 에서 두 번 고쳐야 한다)."""
    tenant_id: str
    enterprise_scope_id: str = ""
    entity_mode: str = ENTITY_MODE_REAL
    scope_kind: str = SCOPE_KIND_DEPARTMENT
    scenario_id: str = ""          # E3 — 가상 시나리오 실행 단위

    def validate(self, creating: bool = False) -> "EnterpriseContext":
        if not self.tenant_id:
            raise EnterpriseContextError("tenant_id 가 필요합니다.")
        if self.entity_mode not in ENTITY_MODES:
            raise EnterpriseContextError(
                f"entity_mode 는 {ENTITY_MODES} 중 하나여야 합니다.")
        if creating and self.entity_mode not in CREATABLE_ENTITY_MODES:
            # 안전장치(격리 스냅샷·가정·외부 연계 차단)가 없는 상태로 가상/경쟁사 자료를
            # 만들게 하면 실제와 섞인 채 쌓인다. 설계서 §7·§13 참조.
            raise EnterpriseContextError(
                f"{ENTITY_MODE_KO.get(self.entity_mode, self.entity_mode)} 는 아직 생성할 수 "
                f"없습니다(ECM 로드맵 E3 — 격리 스냅샷·가정 세트·외부 연계 차단이 선행). "
                f"현재는 {ENTITY_MODE_KO[ENTITY_MODE_REAL]}만 생성할 수 있습니다.")
        if self.scenario_id and self.entity_mode == ENTITY_MODE_REAL:
            # 실제 문맥에 시나리오 id 가 붙으면 실제값과 가정값의 구분이 무너진다(비협상 3).
            raise EnterpriseContextError("실제 운영 문맥에는 scenario_id 를 붙일 수 없습니다.")
        return self

    def to_dict(self) -> dict:
        return {"tenant_id": self.tenant_id,
                "enterprise_scope_id": self.enterprise_scope_id,
                "entity_mode": self.entity_mode,
                "scope_kind": self.scope_kind,
                "scenario_id": self.scenario_id}


def default_tenant_id() -> str:
    return str(getattr(config, "ECM_DEFAULT_TENANT_ID", "tenant_default") or "tenant_default")


def build_context(tenant_id: str = "", enterprise_scope_id: str = "",
                  entity_mode: str = "", scenario_id: str = "",
                  fallback_scope_id: str = "") -> EnterpriseContext:
    """느슨한 입력(헤더·요청 바디)에서 문맥을 조립한다.

    `fallback_scope_id`: 문맥이 명시되지 않았을 때 쓸 범위(보통 요청자의 소속 부서). 전역
      스위처(§5.1)가 없는 동안 사용자가 매번 범위를 지정하게 강제하면 기존 흐름이 전부 막힌다 —
      Phase 2 가 사용자 식별에 기본값을 둔 것과 같은 단계적 도입 판단이다."""
    return EnterpriseContext(
        tenant_id=(tenant_id or "").strip() or default_tenant_id(),
        enterprise_scope_id=(enterprise_scope_id or "").strip() or (fallback_scope_id or ""),
        entity_mode=((entity_mode or "").strip().upper() or ENTITY_MODE_REAL),
        scope_kind=SCOPE_KIND_DEPARTMENT,
        scenario_id=(scenario_id or "").strip(),
    )


def isolation_filter(ctx: Optional[EnterpriseContext]) -> dict:
    """조회 격리 조건. 문맥이 다른 자료가 목록·집계에 섞이지 않게 한다.

    ⚠️ 설계서 수용 기준 5 — "가상 시나리오의 가정과 결과가 실제/계획/예측 데이터와 조회·저장·
      차트에서 명확히 분리된다." 저장만 분리하고 조회를 안 나누면 목록에서 섞여 보인다.
      문맥이 없으면(`None`) 격리하지 않는다 — 하위호환(문맥 도입 전 흐름)."""
    if ctx is None:
        return {}
    return {"tenant_id": ctx.tenant_id, "entity_mode": ctx.entity_mode}
