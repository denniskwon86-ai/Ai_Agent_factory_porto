"""Enterprise Context Master 데이터 모델 — `docs/design_enterprise_context_master.md` §4 / E1.

## 왜 트리가 아니라 그래프인가 (§2.1-2, §3.1)

한 노드에 부모 하나만 강제하면 **전사 공통 재무조직·매트릭스 조직·공동 물류센터·연결회계
범위를 표현할 수 없다.** 그래서 노드(`organization_nodes`)와 다중 관계(`organization_edges`)를
분리한다. 화면에서 보여줄 이해하기 쉬운 기본 트리는 `default_parent_id` 로 따로 두고,
의미 관계는 엣지가 보존한다.

법적 소유 / 운영 보고 / 공유 서비스 / 연결 집계는 **서로 다른 관계**다. 하나로 뭉개면
"전사공통 재무조직이 여러 사업부를 집계할 수 있지만 운영 원천 데이터 열람 권한은 별개"라는
규칙(§3.3)을 표현할 수 없다.

## 이 파일의 경계

Pydantic 모델과 열거 값만 둔다. 저장은 `repository.py`, 범위 해석은 `resolver.py`.
프로필 **상속 해석은 E2** 다 — E1 은 프로필을 저장·조회만 하고 병합하지 않는다(설계서 §11).
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ── §3.2 표준 조직 노드 유형 ──────────────────────────────────────────────
NODE_TYPES = (
    "tenant",                  # 보안·계약·데이터 격리 최상위 경계
    "enterprise_group",        # 지주/기업집단
    "legal_entity",            # 법인
    "shared_service",          # 전사공통(경영관리·재무회계·IT 등)
    "business_division",       # 사업부 / Business Unit
    "site_plant",              # 사업장·공장
    "facility",                # 설비·라인·창고
    "functional_department",   # 구매·생산·품질·물류·판매 등 기능 부서
)

# ⚠️ `business_division`/`functional_department`/`site_plant` 는 **하나의 법인 아래에만 있어야
#   한다는 제약을 두지 않는다**(§3.2). 법인 간 공유 시설은 관계와 유효기간으로 모델링한다.

# ── §3.1 관계 유형 ────────────────────────────────────────────────────────
REL_TENANT_BOUNDARY = "TENANT_BOUNDARY"        # 누구의 독립 환경인가
REL_LEGAL_OWNERSHIP = "LEGAL_OWNERSHIP"        # 어느 법인·지주 관계인가
REL_OPERATING_PARENT = "OPERATING_PARENT"      # 실제 누가 업무·공정을 수행하는가
REL_SHARED_SERVICE = "SHARED_SERVICE"          # 공유 서비스 제공 관계
REL_CONSOLIDATION_SCOPE = "CONSOLIDATION_SCOPE"  # 연결 집계 범위
RELATION_TYPES = (REL_TENANT_BOUNDARY, REL_LEGAL_OWNERSHIP, REL_OPERATING_PARENT,
                  REL_SHARED_SERVICE, REL_CONSOLIDATION_SCOPE)

# ⚠️ **권한 상속은 `OPERATING_PARENT` 만 따른다**(§6.1). 공유서비스·연결집계 관계는 자동
#   전체열람 권한을 만들지 않는다 — 전사 재무조직이 집계 권한을 갖는 것과 각 사업부의 운영
#   원천 데이터를 볼 수 있는 것은 다른 문제다. 여기서 뭉개면 "전사 권한이 모든 상세 데이터
#   권한으로 비화"하는 위험(§13 위험표)이 실현된다.
INHERITABLE_RELATIONS = (REL_OPERATING_PARENT,)

# ── §4.1 공통 상태 ────────────────────────────────────────────────────────
STATUS_DRAFT = "DRAFT"
STATUS_ACTIVE = "ACTIVE"
STATUS_SUSPENDED = "SUSPENDED"
STATUS_ARCHIVED = "ARCHIVED"
STATUSES = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_SUSPENDED, STATUS_ARCHIVED)

# ── §4.4 프로필 묶음 ──────────────────────────────────────────────────────
PROFILE_KINDS = ("business_profile", "process_profile", "data_profile",
                 "solution_profile", "agent_profile", "simulation_profile")
# 하위 프로필이 상위를 어떻게 다루는가. `merge`=키 단위 병합(기본), `replace`=상위를 버림.
INHERITANCE_MODES = ("merge", "replace")


class EcmError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


class EnterpriseEntity(BaseModel):
    """실제/가상/경쟁사 기업 또는 조직 실체 (§4.2 `enterprise_entities`).

    `entity_mode` 는 `context.py` 의 것과 **같은 값**을 쓴다(REAL/VIRTUAL/COMPETITOR_REFERENCE).
    `base_entity_id` 는 복제 원본 — 가상 조직이 어느 실제 조직에서 나왔는지의 계보(§7.1)."""
    entity_id: str = ""
    tenant_id: str = "tenant_default"
    entity_type: str = "legal_entity"        # NODE_TYPES 중 하나(실체의 성격)
    entity_mode: str = "REAL"
    legal_name: str = ""
    name_ko: str = ""
    industry_code: str = ""                  # 업종 — E2 프로필 매칭의 키
    base_entity_id: str = ""                 # 복제 원본(가상/경쟁사)
    status: str = STATUS_DRAFT
    effective_from: str = ""
    effective_to: str = ""
    version: int = 1
    approved_by: str = ""
    approved_at: str = ""
    source_ref: str = ""                     # 원본 시스템(§2.2 — ECM 은 원본이 아니다)
    evidence_ref: str = ""                   # 증빙(경쟁사 모델에 필수 — §7.3)


class OrganizationNode(BaseModel):
    """화면 기본 트리와 운영 단위 (§4.2 `organization_nodes`).

    `default_parent_id` 는 **보기용 기본 트리**일 뿐이다. 진짜 관계는 엣지에 있다(§3.1)."""
    node_id: str = ""
    entity_id: str = ""
    tenant_id: str = "tenant_default"
    node_type: str = "business_division"
    code: str = ""
    name_ko: str = ""
    default_parent_id: str = ""
    path_hint: str = ""                      # 화면 표시용 경로 문자열(권한 판정에 쓰지 않는다)
    # 기존 `org_directory.departments` 와의 연결. ECM 은 부서 체계를 **교체하지 않고 매핑**한다
    #   (§10.1 "한 번에 교체하지 않는다"). 이 값이 있으면 그 부서 권한이 이 노드에 적용된다.
    dept_id: str = ""
    status: str = STATUS_DRAFT
    effective_from: str = ""
    effective_to: str = ""


class OrganizationEdge(BaseModel):
    """소유·운영·공유서비스·집계 관계 (§4.2 `organization_edges`)."""
    edge_id: str = ""
    tenant_id: str = "tenant_default"
    from_node_id: str = ""                   # 상위(부모/제공자)
    to_node_id: str = ""                     # 하위(자식/수혜자)
    relation_type: str = REL_OPERATING_PARENT
    weight: float = 1.0                      # 연결 집계 지분율 등
    effective_from: str = ""
    effective_to: str = ""
    status: str = STATUS_ACTIVE


class EnterpriseProfile(BaseModel):
    """업종·공정·제품·회계·용어 특성 (§4.2 `enterprise_profiles`).

    `scope_node_id` 가 비고 `industry_code` 가 있으면 **산업 공통 프로필**(§4.4 체인 최상위)이며,
    그 자리는 `playbooks/*.json` 의 저작 기본값이 담당한다(M0-a 결정 — `advisor_playbook.py` 주석).

    ⚠️ **상속 병합은 E2** 다. E1 은 저장·조회만 한다. 다만 §4.4 가 "충돌 시 가장 하위의
      **승인된** 프로필이 이긴다"고 못 박았으므로 `approved_at` 을 지금부터 받아 둔다 —
      나중에 추가하면 이미 쌓인 프로필의 승인 여부를 알 수 없다."""
    profile_id: str = ""
    tenant_id: str = "tenant_default"
    scope_node_id: str = ""                  # 비면 산업 공통
    industry_code: str = ""
    profile_kind: str = "business_profile"
    payload: Dict[str, Any] = Field(default_factory=dict)
    inheritance_mode: str = "merge"
    status: str = STATUS_DRAFT
    version: int = 1
    approved_by: str = ""
    approved_at: str = ""

    @property
    def is_effective(self) -> bool:
        """상속에 참여할 수 있는가. **승인되지 않은 프로필은 참여하지 않는다**(§4.4)."""
        return self.status == STATUS_ACTIVE and bool(self.approved_at)


class ScopeNode(BaseModel):
    """범위 해석 결과 1건 — 트리 표시와 권한 판정에 함께 쓴다."""
    node_id: str
    node_type: str
    name_ko: str
    code: str = ""
    dept_id: str = ""
    entity_id: str = ""
    entity_mode: str = "REAL"
    default_parent_id: str = ""
    depth: int = 0
    children: List["ScopeNode"] = Field(default_factory=list)


ScopeNode.model_rebuild()
