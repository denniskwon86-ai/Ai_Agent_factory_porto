"""Enterprise Context Master — `docs/design_enterprise_context_master.md`.

⚠️ **기존 import 경로를 그대로 유지한다.** ECM-lite 단계에서 `core/enterprise_context.py`
  단일 모듈로 시작했고 `api/deps.py`·`advisor_store.py`·`advisor_control.py`·`factory_control.py`
  가 `from core.enterprise_context import EnterpriseContext, build_context, ...` 로 가져다 쓴다.
  설계서 §10.1 이 예고한 패키지 구조로 바꾸면서 그 심볼을 여기서 re-export 해 **호출부 수정 0**
  으로 이행한다.

구성:
  · `context.py`    — 실행 문맥 토큰(tenant/scope/entity_mode). ECM-lite 부터 있던 것.
  · `models.py`     — 조직 엔터티·노드·엣지·프로필 (E1)
  · `repository.py` — 저장소 (E1)
  · `resolver.py`   — 범위 전개·권한 가시성·문맥 해석 (E1). **프로필 상속 병합은 E2**.
  · (예정) `clone_service.py`(E3) · `profile_recommender.py`(E2) · `audit.py`
"""
from core.enterprise_context.context import (  # noqa: F401  (호환 re-export)
    CREATABLE_ENTITY_MODES, ENTITY_MODE_COMPETITOR, ENTITY_MODE_KO, ENTITY_MODE_REAL,
    ENTITY_MODE_VIRTUAL, ENTITY_MODES, SCOPE_KIND_DEPARTMENT, SCOPE_KIND_ECM_NODE,
    EnterpriseContext, EnterpriseContextError, build_context, default_tenant_id,
    isolation_filter,
)
from core.enterprise_context.models import (  # noqa: F401
    INHERITABLE_RELATIONS, INHERITANCE_MODES, NODE_TYPES, PROFILE_KINDS, REL_CONSOLIDATION_SCOPE,
    REL_LEGAL_OWNERSHIP, REL_OPERATING_PARENT, REL_SHARED_SERVICE, REL_TENANT_BOUNDARY,
    RELATION_TYPES, STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_DRAFT, STATUS_SUSPENDED, STATUSES,
    EcmError, EnterpriseEntity, EnterpriseProfile, OrganizationEdge, OrganizationNode, ScopeNode,
)
from core.enterprise_context.repository import EcmRepository, ecm_repository  # noqa: F401
from core.enterprise_context.resolver import EcmResolver, ecm_resolver  # noqa: F401
