"""ECM 파일럿 조직 시드 — `docs/design_enterprise_context_master.md` §3.3.

## 왜 시드를 두는가

설계서 로드맵 E0 은 "첫 파일럿 조직을 정하고 실제 원본 시스템과 책임자를 지정한다"인데 그건
**사용자 결정 사항**이다. 그런데 조직 그래프가 하나도 없으면 범위 전개·권한 가시성·트리를
실측할 수 없다. 그래서 설계서가 예시로 제시한 구조(§3.3)를 **시드**로 넣는다.

⚠️ **이것은 예시다. 실제 조직이 아니다.** 그래서:
  · `source_ref='design_doc_example'` 로 출처를 남긴다 — 나중에 실제 조직과 구분해야 한다.
  · 멱등이다. 이미 있으면 덮어쓰지 않는다(운영 중 실제 조직을 지우면 안 된다).
  · `force=False` 기본. 노드가 하나라도 있으면 건너뛴다.

## 시드가 표현하는 것 (§3.3)

```
LS (기업집단)
├─ LS전선 (법인·제조업)
├─ LS일렉트릭 (법인·제조업)
└─ LS MnM (법인·제련/소재)
   ├─ 전사공통 (공유서비스: 경영관리·재무회계)
   ├─ 동제련 사업부
   └─ 배터리소재 사업부
      ├─ 제1공장
      └─ 제2공장
```

관계를 **세 종류로 나눠** 넣는다 — 단일 트리로는 표현할 수 없는 것을 시드가 실제로 보여줘야
설계 의도가 검증된다:
  · `OPERATING_PARENT` — 운영 보고선(권한 상속이 여기만 따른다)
  · `LEGAL_OWNERSHIP`  — 지주 → 법인 소유 관계
  · `SHARED_SERVICE`   — 전사공통이 두 사업부에 서비스(권한을 만들지 않음)
  · `CONSOLIDATION_SCOPE` — 전사공통이 두 사업부를 연결 집계(권한을 만들지 않음)
"""
from typing import Any, Dict

from core.enterprise_context.models import (REL_CONSOLIDATION_SCOPE, REL_LEGAL_OWNERSHIP,
                                            REL_OPERATING_PARENT, REL_SHARED_SERVICE,
                                            STATUS_ACTIVE, EnterpriseEntity, OrganizationEdge,
                                            OrganizationNode)
from core.enterprise_context.repository import EcmRepository, ecm_repository

SEED_SOURCE_REF = "design_doc_example"       # 실제 조직과 구분하는 표지
_TENANT = "tenant_default"

# (코드, 이름, 노드유형, 부모코드, 업종, 매핑 부서id)
#   ⚠️ `dept_id` 는 기존 `org_directory.departments` 와의 매핑이다. 부서 체계를 교체하지 않고
#     연결한다(§10.1). 매핑이 없는 노드는 권한 판정에서 자체 열람 권한을 갖지 않는다.
_NODES = [
    ("LS",            "LS",             "enterprise_group",      "",        "",          ""),
    ("LS_CABLE",      "LS전선",          "legal_entity",          "LS",      "C2830",     ""),
    ("LS_ELECTRIC",   "LS일렉트릭",       "legal_entity",          "LS",      "C2812",     ""),
    ("LS_MNM",        "LS MnM",         "legal_entity",          "LS",      "C2412",     ""),
    ("MNM_SHARED",    "전사공통",         "shared_service",        "LS_MNM",  "",          "hq"),
    ("MNM_COPPER",    "동제련 사업부",     "business_division",     "LS_MNM",  "C2412",     "production"),
    ("MNM_BATTERY",   "배터리소재 사업부",  "business_division",     "LS_MNM",  "C2013",     "production"),
    ("BATT_PLANT_1",  "제1공장",          "site_plant",            "MNM_BATTERY", "C2013", "production"),
    ("BATT_PLANT_2",  "제2공장",          "site_plant",            "MNM_BATTERY", "C2013", "production"),
]

# (관계, 상위코드, 하위코드)
_EDGES = [
    # 지주 → 법인 소유
    (REL_LEGAL_OWNERSHIP, "LS", "LS_CABLE"),
    (REL_LEGAL_OWNERSHIP, "LS", "LS_ELECTRIC"),
    (REL_LEGAL_OWNERSHIP, "LS", "LS_MNM"),
    # 운영 보고선 — 권한 상속은 이것만 따른다
    (REL_OPERATING_PARENT, "LS_MNM", "MNM_SHARED"),
    (REL_OPERATING_PARENT, "LS_MNM", "MNM_COPPER"),
    (REL_OPERATING_PARENT, "LS_MNM", "MNM_BATTERY"),
    (REL_OPERATING_PARENT, "MNM_BATTERY", "BATT_PLANT_1"),
    (REL_OPERATING_PARENT, "MNM_BATTERY", "BATT_PLANT_2"),
    # 전사공통이 사업부에 서비스 — **권한을 만들지 않는다**
    (REL_SHARED_SERVICE, "MNM_SHARED", "MNM_COPPER"),
    (REL_SHARED_SERVICE, "MNM_SHARED", "MNM_BATTERY"),
    # 전사공통이 사업부를 연결 집계 — **권한을 만들지 않는다**
    (REL_CONSOLIDATION_SCOPE, "MNM_SHARED", "MNM_COPPER"),
    (REL_CONSOLIDATION_SCOPE, "MNM_SHARED", "MNM_BATTERY"),
]


def seed_example_organization(repo: EcmRepository = None, force: bool = False) -> Dict[str, Any]:
    """설계서 §3.3 예시 조직을 멱등하게 넣는다.

    이미 노드가 있으면 건너뛴다(`force=True` 로만 덮어씀) — 운영 중 실제 조직을 시드가 지우면
    안 된다. 반환은 `{status, nodes, edges, node_ids}`."""
    repo = repo or ecm_repository
    existing = repo.list_nodes(tenant_id=_TENANT)
    if existing and not force:
        return {"status": "skipped", "reason": f"이미 노드 {len(existing)}건이 있습니다.",
                "nodes": 0, "edges": 0,
                "node_ids": {n.code: n.node_id for n in existing if n.code}}

    code_to_node: Dict[str, str] = {}
    n_nodes = 0
    for code, name, node_type, parent_code, industry, dept_id in _NODES:
        ent = repo.upsert_entity(EnterpriseEntity(
            tenant_id=_TENANT, entity_type=node_type, entity_mode="REAL",
            legal_name=name, name_ko=name, industry_code=industry,
            status=STATUS_ACTIVE, source_ref=SEED_SOURCE_REF,
            approved_by="system", approved_at=repo._now()))
        node = repo.upsert_node(OrganizationNode(
            entity_id=ent.entity_id, tenant_id=_TENANT, node_type=node_type,
            code=code, name_ko=name, dept_id=dept_id,
            default_parent_id=code_to_node.get(parent_code, ""),
            path_hint="", status=STATUS_ACTIVE))
        code_to_node[code] = node.node_id
        n_nodes += 1

    n_edges = 0
    for relation, up, down in _EDGES:
        repo.add_edge(OrganizationEdge(
            tenant_id=_TENANT, from_node_id=code_to_node[up], to_node_id=code_to_node[down],
            relation_type=relation, status=STATUS_ACTIVE))
        n_edges += 1

    return {"status": "seeded", "nodes": n_nodes, "edges": n_edges, "node_ids": code_to_node,
            "note": "설계서 §3.3 예시 조직입니다. 실제 조직은 API 로 등록·교체하십시오."}
