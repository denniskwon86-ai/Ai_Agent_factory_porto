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
#
#   ★★ [2026-07-30] **부서 매핑은 1:N 이 되면 권한을 결정할 수 없다.**
#     종전에는 `production` 하나를 네 노드(사업부 2 + 공장 2)에 달아 뒀다. 그러면
#     `find_node_by_dept` 의 `ORDER BY updated_at DESC LIMIT 1` 승자가 조직 권한을 결정하고,
#     시드는 네 노드를 같은 시각에 만들므로 그 승자가 **비결정적**이었다 — 배터리 사용자가 동제련
#     문맥으로 해석되거나 그 반대가 되며 오류는 나지 않았다(실측으로 확인).
#
#     [사용자 결정] **생산부서는 사업부마다 각각 존재한다.** 그래서 부서 체계에
#     `production_copper`·`production_battery` 를 두고(`core/org_seed.py`) 각 사업부에 **1:1** 로
#     매핑한다. 모호함을 코드에서 우회하는 것과 **데이터에서 없애는 것**은 다르다 — 우회만 하면
#     그 부서 사용자는 영원히 조직 상속을 못 받는다.
#
#     · 공장 2개는 매핑하지 않는다. 부서 체계에 공장 단위 부서가 없고, 공장은 상위 사업부의
#       범위를 상속한다.
#     · 상위 `production`(생산 총괄)도 매핑하지 않는다 — 매핑하면 1:N 모호함이 되살아난다.
_NODES = [
    ("LS",            "LS",             "enterprise_group",      "",        "",          ""),
    ("LS_CABLE",      "LS전선",          "legal_entity",          "LS",      "C2830",     ""),
    ("LS_ELECTRIC",   "LS일렉트릭",       "legal_entity",          "LS",      "C2812",     ""),
    ("LS_MNM",        "LS MnM",         "legal_entity",          "LS",      "C2412",     ""),
    ("MNM_SHARED",    "전사공통",         "shared_service",        "LS_MNM",  "",          "hq"),
    ("MNM_COPPER",    "동제련 사업부",     "business_division",     "LS_MNM",  "C2412",
     "production_copper"),
    ("MNM_BATTERY",   "배터리소재 사업부",  "business_division",     "LS_MNM",  "C2013",
     "production_battery"),
    ("BATT_PLANT_1",  "제1공장",          "site_plant",            "MNM_BATTERY", "C2013", ""),
    ("BATT_PLANT_2",  "제2공장",          "site_plant",            "MNM_BATTERY", "C2013", ""),
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
    안 된다. 반환은 `{status, nodes, edges, node_ids}`.

    ★★★ [D-018 ⑩] **기존 `node_id`·`entity_id` 를 보존한다. 재생성하지 않는다.**

    `node_id` 는 조직 범위의 **정본**이고(D-018) 다른 저장소가 그 값으로 소유·권한을 기록한다
    (`departments.scope_node_id` · `plan_facts.owner_organization_id` · 자산 `owner_scope_id` …).
    시드가 «덮어쓰기» 를 «새로 만들기» 로 구현하면 그 참조가 **전부 끊긴다** — 조회는 «없음» 을
    돌려주고 그것은 «권한이 없다» 와 구분되지 않는다.

    ⚠️ 이 결함은 실제로 있었고 D-018 ⑦(코드 유일성)이 그것을 드러냈다: `force=True` 가 같은
      코드로 새 노드를 만들려 해 `EcmError` 로 막혔다. **막힌 것이 다행**이다 — 종전에는 같은
      코드의 노드가 하나 더 생기고, 그 뒤로 코드 해석이 «모호» 로 거부됐을 것이다.
    ⚠️ 엔티티도 재사용한다. 새로 만들면 노드가 새 엔티티를 가리키고 **옛 엔티티는 고아**가 된다
      (`entity_mode` 로 문맥을 판정하므로 고아 엔티티는 조용한 오염이다).
    """
    repo = repo or ecm_repository
    existing = repo.list_nodes(tenant_id=_TENANT)
    if existing and not force:
        return {"status": "skipped", "reason": f"이미 노드 {len(existing)}건이 있습니다.",
                "nodes": 0, "edges": 0,
                "node_ids": {n.code: n.node_id for n in existing if n.code}}

    #: 코드 → 기존 노드. `force` 로 다시 심을 때 **그 노드를 갱신**하기 위한 것이다.
    prior = {n.code: n for n in existing if n.code}

    code_to_node: Dict[str, str] = {}
    n_nodes = 0
    for code, name, node_type, parent_code, industry, dept_id in _NODES:
        was = prior.get(code)
        ent = repo.upsert_entity(EnterpriseEntity(
            entity_id=(was.entity_id if was else ""),      # ★ 엔티티도 보존
            tenant_id=_TENANT, entity_type=node_type, entity_mode="REAL",
            legal_name=name, name_ko=name, industry_code=industry,
            status=STATUS_ACTIVE, source_ref=SEED_SOURCE_REF,
            approved_by="system", approved_at=repo._now()))
        node = repo.upsert_node(OrganizationNode(
            node_id=(was.node_id if was else ""),           # ★★★ 정본 보존 — 재생성 금지
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
