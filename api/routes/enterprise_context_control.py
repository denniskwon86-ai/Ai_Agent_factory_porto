"""Enterprise Context API — `docs/design_enterprise_context_master.md` §9 / E1.

E1 범위: 조직 트리 조회, 엔터티/노드/엣지 등록·승인, 문맥 선택 검증, 프로필 저장·조회, 시드.

현재 구현 범위(2026-08-03 기준 — 로드맵 E1~E4):
  · **E2** `GET /contexts/{scope_id}/resolved-profile` — 프로필 상속 해석 **구현됨**
    (`profile_resolver`). 응답의 `sources`(적용 순서)·`skipped`(미승인 제외)를 함께 봐야
    "이 값이 어디서 왔나"에 답할 수 있다.
    ⚠️ 이 줄은 오래 "미구현(E2)"으로 남아 있었다 — 이미 있는 기능을 없다고 적은 주석은 다음
      사람이 같은 것을 다시 만들게 한다. 범위 주석은 코드가 바뀔 때 함께 고친다.
  · **E2** 에이전트팩 바인딩 — `/agent-packs*` · `/nodes/{id}/agents`(상속 해석·provenance)
  · **E3** 가상 Sandbox — `/entities/{id}/clone` · `/scenarios*` · `/copy-policy`.
    가상 엔터티는 **직접 생성할 수 없고 복제로만** 만들어진다: `POST /entities` 는 여전히 REAL
    만 받고, 목적·유효기간·복사 정책이 함께 없으면 가상 조직이 생기지 않는다.
  · **E3** 가정 세트·기준선 스냅샷·계산 결과·비교 — `/assumption-sets*` · `/snapshots*` ·
    `/results*` · `/comparisons`
  · **E3 §7.3** 경쟁사 참조 — `/competitors*`. 경쟁사 엔터티도 전용 문으로만 만들어진다.
  · **E3↔M4** `/run-calculation` — ECM 가정 세트로 결정론적 엔진 실행 후 결과 등록
  · **E4** `/rollup` · `/executive-board` — 조직 트리 집계와 상태 분리 비교 보드

미구현(범위 밖):
  · 외부환경 인텔리전스를 보드의 `FORECAST` 계열로 연결 — E4 의 남은 조각.
    지금 보드에는 계열 자리만 있고, `core/external_intelligence.py` 가 아직 이어져 있지 않다.

권한: 조직 트리는 부서 권한으로 필터한다(§10.1 이행 — ECM 전용 권한 테이블은 E2).
  등록·승인은 조직 편집 권한(`assert_can_edit_org`)을 요구한다 — 조직은 기준정보다.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import (
    Principal,
    assert_can_edit_org,
    assert_identified,
    current_principal,
    enterprise_context,
    viewer_visible_scopes,
)
from core.route_authority import guard as _route_authority_guard
from core.enterprise_context import (ENTITY_MODES, NODE_TYPES, PROFILE_KINDS, RELATION_TYPES,
                                     STATUS_ACTIVE, EcmError, EnterpriseContext,
                                     EnterpriseEntity, EnterpriseProfile, OrganizationEdge,
                                     OrganizationNode, ecm_repository, ecm_resolver)

# ★★ [2026-08-07] 권한 배정표를 **라우터에 붙인다.** 라우트마다 `require_caps` 를 적지
#   않는 이유: 37개에 적으면 37번 빠뜨릴 기회가 생기고, 새 라우트가 생겨도 아무도
#   알려 주지 않는다. 표는 `core/route_authority.ROUTE_CAPS` 하나뿐이며,
#   `tests/test_route_authority_table.py` 가 표와 라우터를 **양방향으로** 대조한다.
router = APIRouter(prefix="/api/v1/enterprise-context", tags=["EnterpriseContext"], dependencies=[Depends(_route_authority_guard)])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "전사 컨텍스트"



def _sandbox_err(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


def _assert_node_visible(p: Principal, node_id: str) -> None:
    """[D-017 §9 P0-4] 이 조직 노드를 볼 수 있는가.

    ★ 판정을 여기서 새로 만들지 않는다 — `viewer_visible_scopes()` 가 이미 «상향 상속은 주고
      하향 열람은 경영진에게만» 을 한 곳에서 정한다(그 함수 주석 참조). 라우트마다 판정을
      두면 한 라우트만 조용히 넓어진다.
    ⚠️ 권한 밖은 **404** 다. 403 은 «그 조직이 존재한다» 를 알리고, 조직도는 그 자체가 정보다.
    ⚠️ 빈 집합은 «전부 허용» 이 아니라 **«아무것도 허용하지 않음»** 이다(fail-closed)."""
    allowed = viewer_visible_scopes(p)
    if allowed is None:          # 강제 OFF · unrestricted · 표준 관리 권한 → 필터하지 않는다
        return
    if node_id not in allowed:
        try:
            from core.enterprise_context import audit
            audit.record(audit.ACCESS_DENIED_SCOPE_MISMATCH, resource_type="scope_node",
                         resource_id=node_id, actor=p.user_id or "", outcome="denied",
                         reason="가시 범위 밖 조직 노드의 에이전트 구성 조회",
                         detail=f"allowed={len(allowed)}개")
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="조직 노드를 찾을 수 없습니다.")


def _tree_dict(sn) -> Dict[str, Any]:
    """`ScopeNode` → dict. `readable` 은 resolver 가 동적으로 붙인 표시용 플래그다
    (권한 없이 경로만 보여주는 노드를 화면이 흐리게 그릴 수 있어야 한다)."""
    return {
        "node_id": sn.node_id, "node_type": sn.node_type, "name_ko": sn.name_ko,
        "code": sn.code, "dept_id": sn.dept_id, "entity_id": sn.entity_id,
        "entity_mode": sn.entity_mode, "depth": sn.depth,
        "readable": bool(sn.__dict__.get("readable", True)),
        "children": [_tree_dict(c) for c in sn.children],
    }


# ── 조회 ─────────────────────────────────────────────────────────────────
@router.get("/meta")
async def get_meta(
        p: Principal = Depends(current_principal)):
    """등록 가능한 유형 목록. 미등록 값은 거부되므로 클라이언트가 알아야 한다."""
    assert_identified(p, WHAT)
    return {"status": "success", "data": {
        "node_types": list(NODE_TYPES), "relation_types": list(RELATION_TYPES),
        "entity_modes": list(ENTITY_MODES), "profile_kinds": list(PROFILE_KINDS),
        "inheritable_relations": ["OPERATING_PARENT"],
        "note": "권한 상속은 OPERATING_PARENT 만 따릅니다. 공유서비스·연결집계는 "
                "자동 열람 권한을 만들지 않습니다(§6.1).",
    }}


@router.get("/tree")
async def get_tree(p: Principal = Depends(current_principal),
                   ctx: EnterpriseContext = Depends(enterprise_context)):
    """권한 범위 내 조직 트리(§9 `GET /tree`).

    문맥의 `entity_mode` 로 걸러 **실제·가상·경쟁사가 한 트리에 섞이지 않게** 한다(비협상 3)."""
    roots = await asyncio.to_thread(ecm_resolver.visible_tree, p, ctx.tenant_id, ctx.entity_mode)
    return {"status": "success", "data": [_tree_dict(r) for r in roots],
            "permission": {"tenant_id": ctx.tenant_id, "entity_mode": ctx.entity_mode}}


@router.get("/entities")
async def list_entities(p: Principal = Depends(current_principal),
                        ctx: EnterpriseContext = Depends(enterprise_context)):
    rows = await asyncio.to_thread(ecm_repository.list_entities, ctx.tenant_id, ctx.entity_mode)
    return {"status": "success", "data": [e.model_dump() for e in rows]}


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str, p: Principal = Depends(current_principal),
                     ctx: EnterpriseContext = Depends(enterprise_context)):
    e = await asyncio.to_thread(ecm_repository.get_entity, entity_id)
    if not e:
        raise HTTPException(status_code=404, detail="엔터티를 찾을 수 없습니다.")
    if e.tenant_id != ctx.tenant_id or e.entity_mode != ctx.entity_mode:
        # 다른 문맥의 자료는 이 문맥에서 존재하지 않는 것이다(advisor 와 같은 규약).
        raise HTTPException(status_code=404, detail="현재 문맥에 없는 엔터티입니다.")
    nodes = [n.model_dump() for n in await asyncio.to_thread(ecm_repository.list_nodes,
                                                            ctx.tenant_id)
             if n.entity_id == entity_id]
    return {"status": "success", "data": {"entity": e.model_dump(), "nodes": nodes}}


@router.get("/nodes/{node_id}/scope")
async def get_node_scope(node_id: str, p: Principal = Depends(current_principal)):
    """이 노드를 선택하면 어디까지 포함되는가 — 운영 범위와 집계 범위를 **분리해서** 준다.

    ⚠️ `consolidation`·`shared_service_consumers` 는 **권한이 아니다**(§6.1). 집계·서비스 대상
      목록일 뿐이며, 이것을 열람 권한으로 오해하면 전사 조직이 모든 상세 데이터를 보게 된다."""
    node = await asyncio.to_thread(ecm_repository.get_node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다.")
    if not await asyncio.to_thread(ecm_resolver.can_read_node, p, node_id):
        raise HTTPException(status_code=403, detail="이 조직 범위를 볼 권한이 없습니다.")
    operating = await asyncio.to_thread(ecm_resolver.descendants, node_id)
    consolidation = await asyncio.to_thread(ecm_resolver.consolidation_scope, node_id)
    shared = await asyncio.to_thread(ecm_resolver.shared_service_consumers, node_id)
    ancestors = await asyncio.to_thread(ecm_resolver.ancestors, node_id)
    return {"status": "success", "data": {
        "node": node.model_dump(),
        "operating_scope": operating,        # 권한 상속이 따르는 범위
        "ancestors": ancestors,
        "consolidation_scope": consolidation,          # 권한 아님
        "shared_service_consumers": shared,            # 권한 아님
        "note": "consolidation_scope·shared_service_consumers 는 집계/서비스 대상이며 "
                "열람 권한을 부여하지 않습니다.",
    }}


class ContextSelect(BaseModel):
    enterprise_scope_id: str
    entity_mode: str = "REAL"


@router.post("/contexts/select")
async def select_context(req: ContextSelect, p: Principal = Depends(current_principal),
                         ctx: EnterpriseContext = Depends(enterprise_context)):
    """세션의 EnterpriseContext 선택을 **검증**한다(§9 `POST /contexts/select`).

    서버가 상태를 저장하지 않는다 — 클라이언트가 헤더로 문맥을 보내는 구조이므로(ECM-lite),
    여기서는 "그 범위를 고를 수 있는가"만 판정해 준다. 부서 id 와 ECM node_id 를 모두 받는다."""
    resolved = await asyncio.to_thread(ecm_resolver.resolve_scope_ref, req.enterprise_scope_id)
    if req.entity_mode not in ENTITY_MODES:
        raise HTTPException(status_code=400, detail=f"entity_mode 는 {ENTITY_MODES} 중 하나여야 합니다.")
    if resolved["node_id"]:
        if not await asyncio.to_thread(ecm_resolver.can_read_node, p, resolved["node_id"]):
            raise HTTPException(status_code=403, detail="이 조직 범위를 볼 권한이 없습니다.")
    elif resolved["dept_id"]:
        # ECM 에 아직 없는 부서 — 기존 부서 권한으로 판정한다(하위호환)
        if not p.scope.can_read(resolved["dept_id"]):
            raise HTTPException(status_code=403, detail="이 부서 자료를 볼 권한이 없습니다.")
    return {"status": "success", "data": {
        "scope": resolved, "entity_mode": req.entity_mode, "tenant_id": ctx.tenant_id,
        "headers": {"X-Enterprise-Scope": req.enterprise_scope_id,
                    "X-Entity-Mode": req.entity_mode},
        "note": "이 값을 이후 요청 헤더에 실어 보내십시오(전역 선택기).",
    }}


# ── 등록·승인 (조직은 기준정보 — 편집 권한 필요) ────────────────────────────
class EntityIn(BaseModel):
    entity_type: str = "legal_entity"
    entity_mode: str = "REAL"
    name_ko: str
    legal_name: str = ""
    industry_code: str = ""
    base_entity_id: str = ""
    source_ref: str = ""
    evidence_ref: str = ""


@router.post("/entities")
async def create_entity(req: EntityIn, p: Principal = Depends(current_principal),
                        ctx: EnterpriseContext = Depends(enterprise_context)):
    assert_can_edit_org(p)
    try:
        e = await asyncio.to_thread(ecm_repository.upsert_entity, EnterpriseEntity(
            tenant_id=ctx.tenant_id, **req.model_dump()))
    except EcmError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"status": "success", "data": e.model_dump()}


@router.post("/entities/{entity_id}/approve")
async def approve_entity(entity_id: str, p: Principal = Depends(current_principal)):
    """§4.1 — 조직/프로필은 승인 가능한 버전을 갖는다. 승인 전에는 DRAFT 다."""
    assert_can_edit_org(p)
    e = await asyncio.to_thread(ecm_repository.approve_entity, entity_id, p.user_id)
    if not e:
        raise HTTPException(status_code=404, detail="엔터티를 찾을 수 없습니다.")
    return {"status": "success", "data": e.model_dump()}


class NodeIn(BaseModel):
    entity_id: str
    node_type: str = "business_division"
    name_ko: str
    code: str = ""
    default_parent_id: str = ""
    dept_id: str = ""
    status: str = "ACTIVE"


@router.post("/nodes")
async def create_node(req: NodeIn, p: Principal = Depends(current_principal),
                      ctx: EnterpriseContext = Depends(enterprise_context)):
    assert_can_edit_org(p)
    try:
        n = await asyncio.to_thread(ecm_repository.upsert_node, OrganizationNode(
            tenant_id=ctx.tenant_id, **req.model_dump()))
    except EcmError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"status": "success", "data": n.model_dump()}


class EdgeIn(BaseModel):
    from_node_id: str
    to_node_id: str
    relation_type: str = "OPERATING_PARENT"
    weight: float = 1.0


@router.post("/edges")
async def create_edge(req: EdgeIn, p: Principal = Depends(current_principal),
                      ctx: EnterpriseContext = Depends(enterprise_context)):
    """관계 추가. 순환은 거부한다 — 사이클이 생기면 범위 전개가 무한 재귀에 빠진다."""
    assert_can_edit_org(p)
    try:
        e = await asyncio.to_thread(ecm_repository.add_edge, OrganizationEdge(
            tenant_id=ctx.tenant_id, **req.model_dump()))
    except EcmError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"status": "success", "data": e.model_dump()}


# ── 프로필 (E1: 저장·조회만) ────────────────────────────────────────────────
class ProfileIn(BaseModel):
    profile_kind: str = "business_profile"
    scope_node_id: str = ""
    industry_code: str = ""
    payload: Dict[str, Any] = {}
    inheritance_mode: str = "merge"
    status: str = "DRAFT"


@router.post("/profiles")
async def create_profile(req: ProfileIn, p: Principal = Depends(current_principal),
                         ctx: EnterpriseContext = Depends(enterprise_context)):
    assert_can_edit_org(p)
    try:
        pr = await asyncio.to_thread(ecm_repository.upsert_profile, EnterpriseProfile(
            tenant_id=ctx.tenant_id, **req.model_dump()))
    except EcmError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"status": "success", "data": pr.model_dump()}


@router.get("/profiles")
async def list_profiles(scope_node_id: str = "", industry_code: str = "", profile_kind: str = "",
                        p: Principal = Depends(current_principal)):
    """프로필 조회. ⚠️ **상속 병합은 하지 않는다(E2)** — 저장된 것을 그대로 준다.
    `is_effective=False` 는 승인되지 않아 상속에 참여할 수 없는 프로필이다(§4.4)."""
    rows = await asyncio.to_thread(ecm_repository.list_profiles, scope_node_id, industry_code,
                                   profile_kind)
    out = []
    for pr in rows:
        d = pr.model_dump()
        d["is_effective"] = pr.is_effective
        out.append(d)
    return {"status": "success", "data": out,
            "note": "프로필 상속 병합은 ECM 로드맵 E2 에서 제공됩니다. 여기는 저장된 원본입니다."}


# ── E2: 프로필 상속 해석 · 템플릿 바인딩 ────────────────────────────────────
@router.get("/contexts/{scope_id}/resolved-profile")
async def get_resolved_profile(scope_id: str, profile_kind: str = "data_profile",
                               playbook_id: str = "",
                               p: Principal = Depends(current_principal)):
    """상속이 해석된 실행 프로필(§9). **E2**.

    `playbook_id` 를 주면 그 플레이북이 **산업 공통 층**으로 들어간다(`DECISIONS.md` D-002).
    응답의 `sources`(적용 순서)와 `skipped`(미승인으로 제외)를 함께 봐야 "이 값이 어디서
    왔나"에 답할 수 있다 — 근거 없는 추천은 신뢰할 수 없다(§5.2)."""
    from core.enterprise_context.profile_resolver import (playbook_industry_base,
                                                          profile_resolver)
    resolved_ref = await asyncio.to_thread(ecm_resolver.resolve_scope_ref, scope_id)
    node_id = resolved_ref["node_id"]
    if node_id and not await asyncio.to_thread(ecm_resolver.can_read_node, p, node_id):
        raise HTTPException(status_code=403, detail="이 조직 범위를 볼 권한이 없습니다.")
    if not node_id and resolved_ref["dept_id"] and not p.scope.can_read(resolved_ref["dept_id"]):
        raise HTTPException(status_code=403, detail="이 부서 자료를 볼 권한이 없습니다.")

    base = None
    industry = None
    if playbook_id:
        from core.advisor_playbook import load_playbook
        from core.enterprise_context.profile_resolver import check_industry_compatibility
        try:
            pb = load_playbook(playbook_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not pb:
            raise HTTPException(status_code=404, detail=f"플레이북을 찾을 수 없습니다: {playbook_id}")
        # D-002 보완 ① — 업종 호환성을 **검증하되 막지 않는다**(§2.1-6: 사용자가 선택·수정할 수
        #   있어야 한다). 신사업 진출·업종 코드 미정비 같은 정당한 예외를 차단하면 안 된다.
        #   ⚠️ 저장소를 **명시적으로 넘긴다.** 전역을 쓰게 두면 라우트가 다른 저장소를 쓰는
        #     구성(테스트·다중 테넌트 분리)에서 업종이 빈 값으로 나와 검증이 조용히 무력화된다.
        industry = await asyncio.to_thread(check_industry_compatibility, pb, node_id,
                                           ecm_repository)
        if profile_kind == "data_profile":
            base = playbook_industry_base(pb)
    try:
        out = await asyncio.to_thread(profile_resolver.resolve, node_id, profile_kind, base)
    except EcmError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["scope_ref"] = resolved_ref
    if industry is not None:
        out["industry_compatibility"] = industry
    return {"status": "success", "data": out}


@router.get("/templates/{template_id}/binding")
async def get_template_binding(template_id: str, p: Principal = Depends(current_principal)):
    """템플릿별 필수 기준정보 바인딩(감사 ENTERPRISE-01 Action 3 / `DECISIONS.md` R-002).

    ⚠️ 마스터 **본문은 주지 않는다** — 그건 MDM(`master_data.get_master_context`)이 결정론적으로
      주입한다(R-001). 여기는 "어느 섹션을 반드시 근거로 써야 하고, 그 수치를 지어내면 안 되는가"
      라는 규칙만 준다. `prompt_block` 이 실제로 프롬프트에 들어가는 문구다."""
    from core.enterprise_context.profile_resolver import (TEMPLATE_MASTER_BINDINGS,
                                                          binding_for_template,
                                                          render_binding_block)
    b = binding_for_template(template_id)
    if not b:
        return {"status": "success", "data": {
            "template_id": template_id, "bound": False,
            "known_templates": sorted(TEMPLATE_MASTER_BINDINGS),
            "note": "이 템플릿에는 필수 기준정보 바인딩이 등록되지 않았습니다(제약 없음)."}}
    b.update({"template_id": template_id, "bound": True,
              "prompt_block": render_binding_block(template_id)})
    return {"status": "success", "data": b}


# ── 시드 ─────────────────────────────────────────────────────────────────
@router.post("/seed-example")
async def seed_example(force: bool = False, p: Principal = Depends(current_principal)):
    """설계서 §3.3 예시 조직을 넣는다(멱등). **실제 조직이 아니라 예시**임을 응답에 명시한다.

    E0(파일럿 조직 확정)은 사용자 결정 사항이므로, 그전에 범위 전개·권한·트리를 실측할 수 있게
    하기 위한 것이다. 이미 노드가 있으면 건너뛴다 — 실제 조직을 시드가 지우면 안 된다."""
    assert_can_edit_org(p)
    from core.enterprise_context.seed import seed_example_organization
    return {"status": "success", "data": await asyncio.to_thread(seed_example_organization,
                                                                 None, force)}


# ── [E3] 가상 기업 Sandbox ────────────────────────────────────────────────
# ★ 가상 조직을 만드는 문은 **여기 하나뿐이다.** `POST /entities` 는 REAL 만 받는다 —
#   흐름(원본·목적·유효기간·복사 정책)을 안내 문구가 아니라 구조로 강제한다(§7.1).
class CloneIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name_ko: str
    purpose: str                              # 목적 없는 가상 조직은 아무도 정리하지 못한다
    valid_until: str                          # YYYY-MM-DD — 만료 없는 가상 조직은 영구 조직이 된다
    # ⚠️ 필드명을 `copy` 로 두면 `BaseModel.copy()` 를 가려 경고가 나고, 언젠가 그 메서드를
    #   쓰는 코드가 조용히 깨진다. API 계약은 `copy` 로 유지하고(alias) 파이썬 쪽 이름만 바꾼다.
    copy_options: Dict[str, bool] = Field(default_factory=dict, alias="copy")
    assumption_set_id: str = ""
    snapshot_id: str = ""


class PromoteIn(BaseModel):
    rationale: str


class CloseIn(BaseModel):
    reason: str = ""


@router.get("/copy-policy")
async def copy_policy(
        p: Principal = Depends(current_principal)):
    """복제 시 무엇을 가져오고 무엇을 **절대 가져오지 않는지**(§7.1).

    ★ 화면이 이 표를 그대로 보여주게 하려고 API 로 낸다 — 정책을 화면에 다시 적으면 두 곳이
      갈라지고, 사용자는 실제로 무엇이 복사됐는지 알 수 없게 된다."""
    assert_identified(p, WHAT)
    from core.enterprise_context.clone_service import COPY_POLICY, NEVER_COPIED
    return {"status": "success",
            "data": {"selectable": COPY_POLICY, "never_copied": NEVER_COPIED}}


@router.post("/entities/{entity_id}/clone")
async def clone_entity(entity_id: str, req: CloneIn,
                       p: Principal = Depends(current_principal),
                       ctx: EnterpriseContext = Depends(enterprise_context)):
    """실제 엔터티를 격리된 가상 시나리오로 복제한다(§9 `CLONE_TO_VIRTUAL`)."""
    assert_can_edit_org(p)
    from core.enterprise_context.clone_service import SandboxError, clone_service
    try:
        data = await asyncio.to_thread(
            clone_service.clone_to_virtual, entity_id, req.name_ko, req.purpose,
            req.valid_until, (p.user_id or ""), req.copy_options, ctx.tenant_id,
            req.assumption_set_id, req.snapshot_id)
    except (SandboxError, EcmError) as e:
        _sandbox_err(e)
    return {"status": "success", "data": data}


@router.get("/scenarios")
async def list_scenarios(status: str = "", entity_id: str = "",
                         p: Principal = Depends(current_principal)):
    """가상 시나리오 목록. **만료 여부를 함께 준다** — 만료된 가정으로 판단하면 안 된다."""
    from core.enterprise_context.clone_service import clone_service
    data = await asyncio.to_thread(clone_service.list_scenarios, status, entity_id)
    return {"status": "success", "data": data}


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, p: Principal = Depends(current_principal)):
    from core.enterprise_context.clone_service import clone_service
    data = await asyncio.to_thread(clone_service.get_scenario, scenario_id)
    if not data:
        raise HTTPException(status_code=404, detail="시나리오를 찾을 수 없습니다.")
    return {"status": "success", "data": data}


@router.post("/scenarios/{scenario_id}/promote-request")
async def promote_request(scenario_id: str, req: PromoteIn,
                          p: Principal = Depends(current_principal)):
    """가상 설계를 실제 조직 초안으로 **승격 요청**한다.

    ⚠️ 요청까지만이다 — 실제 조직은 바뀌지 않는다(§8.3: 가상 결과를 실제 시스템에 자동 반영하지
      않는다). 응답의 `note` 가 그것을 말한다."""
    assert_can_edit_org(p)
    from core.enterprise_context.clone_service import SandboxError, clone_service
    try:
        data = await asyncio.to_thread(clone_service.request_promotion, scenario_id,
                                       (p.user_id or ""), req.rationale)
    except SandboxError as e:
        _sandbox_err(e)
    return {"status": "success", "data": data}


@router.post("/scenarios/{scenario_id}/close")
async def close_scenario(scenario_id: str, req: CloseIn,
                         p: Principal = Depends(current_principal)):
    """시나리오를 닫는다(삭제하지 않는다 — 어떤 가정으로 판단했는지가 감사 대상이다)."""
    assert_can_edit_org(p)
    from core.enterprise_context.clone_service import SandboxError, clone_service
    try:
        data = await asyncio.to_thread(clone_service.close_scenario, scenario_id,
                                       (p.user_id or ""), req.reason)
    except SandboxError as e:
        _sandbox_err(e)
    return {"status": "success", "data": data}


# ── [E3] 가정 세트 · 기준선 스냅샷 · 계산 결과 · 비교 ──────────────────────
# ★ §8.1 이 실행 문맥 키로 못 박은 `assumption_set_id`·`baseline_snapshot_id` 의 **대상**이다.
#   이것이 없던 동안은 키만 있고 대상이 없어서, "이 숫자가 무슨 가정으로 어떤 기준선과 비교해
#   나왔나"에 답할 수 없었다 — 답할 수 없는 숫자는 근거가 아니라 주장이다.
class AssumptionIn(BaseModel):
    name: str
    purpose: str
    values: Dict[str, Any]
    evidence: Dict[str, str]         # 값마다 근거 — 없으면 400(추측이 계산에 들어가면 안 된다)
    scope_node_id: str = ""


class AssumptionRevise(BaseModel):
    values: Dict[str, Any]
    evidence: Dict[str, str]
    purpose: str = ""


class SnapshotIn(BaseModel):
    name: str
    as_of: str                       # 언제 기준인가 — 없으면 비교 기준이 못 된다
    source: str                      # 어디서 온 집계인가 — 없으면 근거가 못 된다
    values: Dict[str, Any]
    scope_node_id: str = ""
    entity_mode: str = "REAL"


class ResultIn(BaseModel):
    scenario_id: str
    snapshot_id: str
    assumption_set_id: str
    calculation_model_version: str   # 어떤 모델이 낸 숫자인가(§8.1) — 없으면 재현 불가
    values: Dict[str, Any]


def _si():
    from core.enterprise_context.scenario_inputs import ScenarioInputError, scenario_inputs
    return scenario_inputs, ScenarioInputError


@router.post("/assumption-sets")
async def create_assumption_set(req: AssumptionIn, p: Principal = Depends(current_principal),
                                ctx: EnterpriseContext = Depends(enterprise_context)):
    """가정값 묶음을 만든다(DRAFT). **가정값마다 근거가 필요하다.**"""
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.create_assumption_set, req.name, req.purpose, req.values,
                                    req.evidence, req.scope_node_id, ctx.tenant_id,
                                    (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/assumption-sets")
async def list_assumption_sets(status: str = "", scope_node_id: str = "",
                               p: Principal = Depends(current_principal)):
    si, _ = _si()
    return {"status": "success",
            "data": await asyncio.to_thread(si.list_assumption_sets, status, scope_node_id)}


@router.post("/assumption-sets/{assumption_set_id}/approve")
async def approve_assumption_set(assumption_set_id: str,
                                 p: Principal = Depends(current_principal)):
    """승인 — **승인된 가정만 계산에 쓸 수 있다.**"""
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.approve_assumption_set, assumption_set_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/assumption-sets/{assumption_set_id}/revise")
async def revise_assumption_set(assumption_set_id: str, req: AssumptionRevise,
                                p: Principal = Depends(current_principal)):
    """개정 — **새 버전을 만든다.** 계산에 쓰인 가정을 제자리에서 고치면 과거 결과의 근거가 사라진다."""
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.revise_assumption_set, assumption_set_id, req.values,
                                    req.evidence, (p.user_id or ""), req.purpose)
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/snapshots")
async def create_snapshot(req: SnapshotIn, p: Principal = Depends(current_principal),
                          ctx: EnterpriseContext = Depends(enterprise_context)):
    """기준선 집계를 스냅샷으로 고정한다(DRAFT)."""
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.create_snapshot, req.name, req.as_of, req.values,
                                    req.source, req.scope_node_id, req.entity_mode,
                                    ctx.tenant_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/snapshots")
async def list_snapshots(status: str = "", entity_mode: str = "",
                         p: Principal = Depends(current_principal)):
    si, _ = _si()
    return {"status": "success",
            "data": await asyncio.to_thread(si.list_snapshots, status, entity_mode)}


@router.post("/snapshots/{snapshot_id}/approve")
async def approve_snapshot(snapshot_id: str, p: Principal = Depends(current_principal)):
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.approve_snapshot, snapshot_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/results")
async def record_result(req: ResultIn, p: Principal = Depends(current_principal),
                        ctx: EnterpriseContext = Depends(enterprise_context)):
    """결정론적 계산 결과를 등록한다. **등록하는 순간 입력(가정·기준선)이 동결된다.**

    ⚠️ 이 API 는 계산하지 않는다 — 엔진이 계산하고 결과를 여기에 남긴다(§8.2: LLM 은 계산값을
      만들지 않는다)."""
    assert_can_edit_org(p)
    si, Err = _si()
    try:
        d = await asyncio.to_thread(si.record_result, req.scenario_id, req.snapshot_id,
                                    req.assumption_set_id, req.calculation_model_version,
                                    req.values, (p.user_id or ""), ctx.tenant_id)
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/results")
async def list_results(scenario_id: str = "", p: Principal = Depends(current_principal)):
    si, _ = _si()
    return {"status": "success", "data": await asyncio.to_thread(si.list_results, scenario_id)}


@router.get("/results/{result_id}/comparison")
async def result_comparison(result_id: str, p: Principal = Depends(current_principal)):
    """결과를 기준선과 비교한다. **각 값의 상태(실제/가상)와 근거를 함께 준다.**

    ★ 두 숫자를 나란히 놓는 순간 한쪽이 확정 실적이고 다른 쪽이 가정이라는 사실이 표에서
      사라지기 쉽다(§8.1 은 그 분리를 요구한다). 응답의 `notes` 가 그것을 말한다."""
    from core.enterprise_context.comparison import ComparisonError, compare_result
    try:
        d = await asyncio.to_thread(compare_result, result_id)
    except ComparisonError as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/comparisons")
async def multi_comparison(result_ids: str, p: Principal = Depends(current_principal)):
    """여러 결과를 나란히 본다(콤마 구분). **기준선이 다르면 거부한다** — 그 차이가 시나리오
    차이인지 기준선 차이인지 구분할 수 없기 때문이다."""
    from core.enterprise_context.comparison import ComparisonError, compare_results
    ids = [x.strip() for x in (result_ids or "").split(",") if x.strip()]
    try:
        d = await asyncio.to_thread(compare_results, ids)
    except ComparisonError as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


# ── [E2 잔여] 에이전트팩 바인딩 ────────────────────────────────────────────
# ★ 부서별 평면 목록(`domain_agents`)은 전사 표준 하나를 추가할 때 모든 부서를 각각 고쳐야 하고,
#   한 곳을 빠뜨리면 그 부서만 조용히 다른 구성으로 돈다. 바인딩 + 상속으로 바꾼다.
class PackIn(BaseModel):
    name: str
    purpose: str
    agents: List[str]


class PackBindIn(BaseModel):
    scope_node_id: str
    entity_mode: str = "REAL"
    inherit_descendants: bool = True
    effective_from: str = ""
    effective_to: str = ""


def _ap():
    from core.enterprise_context.agent_pack_binding import AgentPackError, agent_packs
    return agent_packs, AgentPackError


@router.post("/agent-packs")
async def create_agent_pack(req: PackIn, p: Principal = Depends(current_principal),
                            ctx: EnterpriseContext = Depends(enterprise_context)):
    assert_can_edit_org(p)
    ap, Err = _ap()
    try:
        d = await asyncio.to_thread(ap.create_pack, req.name, req.purpose, req.agents,
                                    ctx.tenant_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/agent-packs")
async def list_agent_packs(status: str = "", p: Principal = Depends(current_principal),
                           ctx: EnterpriseContext = Depends(enterprise_context)):
    """팩 목록.

    ⚠️ [D-017 §2.4] 예전에는 요청자 가시 범위·테넌트로 **전혀 필터하지 않았다.** 다른 회사의
      팩 이름·목적·에이전트 구성이 그대로 보였다 — 팩 이름만으로도 «저쪽이 무엇을 자동화하고
      있는가» 가 드러난다."""
    ap, _ = _ap()
    rows = await asyncio.to_thread(ap.list_packs, status, ctx.tenant_id or "")
    return {"status": "success", "data": rows,
            "tenant_id": ctx.tenant_id or "",
            # 화면이 «전부 본다» 고 오해하지 않게 필터가 걸렸다는 사실을 함께 낸다.
            "scoped": bool(ctx.tenant_id)}


@router.post("/agent-packs/{pack_id}/approve")
async def approve_agent_pack(pack_id: str, p: Principal = Depends(current_principal)):
    """승인 — **승인된 팩만 조직에 바인딩할 수 있다.**"""
    assert_can_edit_org(p)
    ap, Err = _ap()
    try:
        d = await asyncio.to_thread(ap.approve_pack, pack_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/agent-packs/{pack_id}/bind")
async def bind_agent_pack(pack_id: str, req: PackBindIn,
                          p: Principal = Depends(current_principal),
                          ctx: EnterpriseContext = Depends(enterprise_context)):
    """팩을 조직 노드에 적용한다(상속 기본 켬).

    ⚠️ `master_scope_bindings` 와 같은 UNIQUE 키다 — **기간이 같으면 덮어쓴다**(추가가 아니라 수정)."""
    assert_can_edit_org(p)
    ap, Err = _ap()
    try:
        d = await asyncio.to_thread(ap.bind, pack_id, req.scope_node_id, ctx.tenant_id,
                                    req.entity_mode, req.inherit_descendants,
                                    req.effective_from, req.effective_to, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.delete("/agent-pack-bindings/{binding_id}")
async def unbind_agent_pack(binding_id: str, p: Principal = Depends(current_principal)):
    """해제(소프트) — 물리 삭제하지 않는다. 과거 산출물이 어떤 구성으로 만들어졌는지의 근거다."""
    assert_can_edit_org(p)
    ap, _ = _ap()
    ok = await asyncio.to_thread(ap.unbind, binding_id, (p.user_id or ""))
    if not ok:
        raise HTTPException(status_code=404, detail="바인딩을 찾을 수 없습니다.")
    return {"status": "success", "data": {"binding_id": binding_id, "status": "revoked"}}


@router.get("/nodes/{node_id}/agents")
async def resolve_node_agents(node_id: str, entity_mode: str = "REAL",
                              p: Principal = Depends(current_principal)):
    """★★ [D-017 §2.4] **이 노드를 볼 권한부터 확인한다.** 예전에는 확인이 없어서, 노드 ID 만
      알면 다른 사업부에서 어떤 에이전트가 도는지 그대로 읽을 수 있었다.
    ⚠️ 권한 밖 노드는 **404** 다 — 403 은 «그 조직이 존재한다» 를 알린다."""
    """이 조직에서 실제로 도는 에이전트와 **그 근거**(어느 팩·어느 조직에서 상속됐는가).

    ★ `skipped` 도 함께 본다 — 만료·비상속·미승인으로 빠진 것을 알아야 "왜 안 도는지"에
      답할 수 있다. 비어 있으면 `bound=false` 와 안내 문구가 나온다(에이전트가 없는 것과
      바인딩이 없는 것은 다르다)."""
    _assert_node_visible(p, node_id)
    ap, Err = _ap()
    try:
        d = await asyncio.to_thread(ap.resolve_agents, node_id, "", entity_mode)
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


# ── [E3 §7.3] 경쟁사 참조 ──────────────────────────────────────────────────
class CompetitorIn(BaseModel):
    name_ko: str
    evidence_ref: str                # 공개·승인된 근거 — 없으면 400
    industry_code: str = ""
    legal_name: str = ""


class MetricIn(BaseModel):
    metric_key: str
    value: Any
    source: str
    published_at: str
    as_of_date: str
    confidence: str                  # HIGH | MEDIUM | LOW (숫자를 받지 않는다)
    evidence_level: str              # 허용 4종만
    unit: str = ""
    note: str = ""


class UnverifiableIn(BaseModel):
    metric_key: str
    as_of_date: str
    note: str                        # 무엇을 찾아봤고 왜 없었는지


def _cr():
    from core.enterprise_context.competitor_reference import (CompetitorError,
                                                              competitor_reference)
    return competitor_reference, CompetitorError


@router.get("/competitors/evidence-kinds")
async def competitor_evidence_kinds(
        p: Principal = Depends(current_principal)):
    """허용된 근거 종류와 신뢰도 단계(§7.3-1,2). 화면이 이 목록을 그대로 쓰게 낸다."""
    assert_identified(p, WHAT)
    from core.enterprise_context.competitor_reference import (CONFIDENCE, CONFIDENCE_KO,
                                                              EVIDENCE_LEVELS,
                                                              STALE_AFTER_DAYS)
    return {"status": "success",
            "data": {"evidence_levels": EVIDENCE_LEVELS,
                     "confidence": {c: CONFIDENCE_KO[c] for c in CONFIDENCE},
                     "stale_after_days": STALE_AFTER_DAYS}}


@router.post("/competitors")
async def create_competitor(req: CompetitorIn, p: Principal = Depends(current_principal),
                            ctx: EnterpriseContext = Depends(enterprise_context)):
    """경쟁사 참조 엔터티 생성. **이 경로가 유일한 문이다**(`POST /entities` 는 REAL 만 받는다)."""
    assert_can_edit_org(p)
    cr, Err = _cr()
    try:
        d = await asyncio.to_thread(cr.create_competitor, req.name_ko, req.evidence_ref,
                                    req.industry_code, req.legal_name, ctx.tenant_id,
                                    (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/competitors/{entity_id}/metrics")
async def record_competitor_metric(entity_id: str, req: MetricIn,
                                   p: Principal = Depends(current_principal),
                                   ctx: EnterpriseContext = Depends(enterprise_context)):
    """경쟁사 지표 1건. **근거 5종이 모두 있어야 저장된다**(§7.3-2)."""
    assert_can_edit_org(p)
    cr, Err = _cr()
    try:
        d = await asyncio.to_thread(cr.record_metric, entity_id, req.metric_key, req.value,
                                    req.source, req.published_at, req.as_of_date,
                                    req.confidence, req.evidence_level, req.unit, req.note,
                                    ctx.tenant_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/competitors/{entity_id}/unverifiable")
async def mark_competitor_unverifiable(entity_id: str, req: UnverifiableIn,
                                       p: Principal = Depends(current_principal),
                                       ctx: EnterpriseContext = Depends(enterprise_context)):
    """**확인 불가**를 명시적으로 기록한다(§7.3-3).

    ★ 모른다고 말할 자리가 있어야 지어내지 않는다. 값을 넣을 칸이 하나뿐이면 결국 그럴듯한
      숫자가 들어간다."""
    assert_can_edit_org(p)
    cr, Err = _cr()
    try:
        d = await asyncio.to_thread(cr.mark_unverifiable, entity_id, req.metric_key,
                                    req.as_of_date, req.note, ctx.tenant_id, (p.user_id or ""))
    except Err as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.get("/competitors/{entity_id}/metrics")
async def list_competitor_metrics(entity_id: str, metric_key: str = "",
                                  p: Principal = Depends(current_principal)):
    cr, _ = _cr()
    return {"status": "success",
            "data": await asyncio.to_thread(cr.list_metrics, entity_id, metric_key)}


@router.get("/competitors/{entity_id}/coverage")
async def competitor_coverage(entity_id: str, expected_keys: str = "",
                              p: Principal = Depends(current_principal)):
    """무엇이 채워졌고 무엇이 비었는지. **확인 불가와 미조사를 구분해 센다** —
    앞은 찾아봤고 없는 것, 뒤는 아직 안 본 것이다."""
    cr, _ = _cr()
    keys = [k.strip() for k in (expected_keys or "").split(",") if k.strip()]
    return {"status": "success",
            "data": await asyncio.to_thread(cr.coverage, entity_id, keys)}


# ── [E3 ↔ M4] 계산 엔진 연결 ───────────────────────────────────────────────
class RunIn(BaseModel):
    scenario_id: str                 # ECM 가상 시나리오
    assumption_set_id: str
    snapshot_id: str
    org_id: str                      # 엔진 쪽 조직 키
    period: str
    baseline_kind: str = "PLAN"      # ACTUAL | PLAN | FORECAST


@router.post("/run-calculation")
async def run_calculation(req: RunIn, p: Principal = Depends(current_principal),
                          ctx: EnterpriseContext = Depends(enterprise_context)):
    """ECM 가정 세트로 결정론적 엔진을 돌리고 결과를 등록한다.

    ★ **ECM 가정 세트가 원본이다** — 엔진 가정은 여기서 파생된다. 손으로 옮기면 두 곳의 가정이
      조용히 달라지고, 그때 비교표의 근거는 거짓이 된다.
    ⚠️ 응답의 `warning`(반영되지 않은 가정·동인 경고)을 반드시 확인할 것 — 가정 12개를 넣고
      9개만 반영된 결과도 정상처럼 보인다."""
    assert_can_edit_org(p)
    from core.enterprise_context.calc_bridge import CalcBridgeError, calc_bridge
    from core.enterprise_context.scenario_inputs import ScenarioInputError
    try:
        d = await asyncio.to_thread(calc_bridge.run_and_record, req.scenario_id,
                                    req.assumption_set_id, req.snapshot_id, req.org_id,
                                    req.period, req.baseline_kind, (p.user_id or ""),
                                    ctx.tenant_id)
    except (CalcBridgeError, ScenarioInputError) as e:
        _sandbox_err(e)
    except Exception as e:            # 엔진 오류(기준선 없음 등)는 그대로 전달한다
        raise HTTPException(status_code=400, detail=f"계산 실패: {e}")
    return {"status": "success", "data": d}


# ── [E4] 조직 트리 집계 · 경영진 보드 ──────────────────────────────────────
class RollupIn(BaseModel):
    node_id: str
    values_by_node: Dict[str, Dict[str, Any]]
    mode: str = "ACTUAL"
    relation: str = "OPERATING_PARENT"


class BoardIn(BaseModel):
    node_id: str
    series: Dict[str, Dict[str, Any]]
    meta: Dict[str, Dict[str, Any]] = {}
    rollups: Dict[str, Dict[str, Any]] = {}
    competitor_entity_id: str = ""
    internal_values: Dict[str, Any] = {}
    #: [E4] 외부환경 지표를 `FORECAST` 계열로 얹는다. 등급 미달·관측 없음은 값이 아니라
    #: `outlook.blocked` 로 올라간다(0 으로 채우지 않는다 — §12.1/§12.2).
    outlook_indicators: List[str] = []
    outlook_purpose: str = "scenario"      # 경영 보고용이면 official_report(gold)
    outlook_as_of: str = ""
    outlook_vintage: str = ""


@router.post("/rollup")
async def compute_rollup(req: RollupIn, p: Principal = Depends(current_principal)):
    """조직 트리 집계. **무엇을 더했고 무엇이 빠졌는지 함께 준다.**

    ⚠️ 이중 계상(부모 값 + 자식 값)은 합계에서 **제외**하고 `conflicts` 로 알린다 — 자동으로
      한쪽을 고르지 않는다. 어느 쪽이 정본인지는 값을 넣은 사람만 안다."""
    from core.enterprise_context.rollup import RollupError, rollup_service
    try:
        d = await asyncio.to_thread(rollup_service.rollup, req.node_id, req.values_by_node,
                                    req.mode, req.relation)
    except RollupError as e:
        _sandbox_err(e)
    return {"status": "success", "data": d}


@router.post("/executive-board")
async def executive_board(req: BoardIn, p: Principal = Depends(current_principal)):
    """경영진 비교 보드 — 실제·계획·예측·가상·경쟁사를 한 화면에, **섞지 않고.**

    ★ 하위 조직별 기여 내역은 경영진만 본다(사용자 결정 2026-07-30 ③). 판정은
      `api/deps.viewer_may_drill_down()` 한 곳에서 온다 — 여기서 다시 판단하지 않는다."""
    from api.deps import viewer_may_drill_down
    from core.enterprise_context.executive_board import BoardError, build_board
    comp_rows = []
    if req.competitor_entity_id:
        from core.enterprise_context.competitor_reference import competitor_reference
        comp_rows = (await asyncio.to_thread(competitor_reference.compare_with_internal,
                                             req.competitor_entity_id,
                                             req.internal_values))["rows"]

    series, meta, outlook = req.series, req.meta, None
    if req.outlook_indicators:
        # ★ 등급 미달·관측 없음은 계열에서 빠지고 `outlook.blocked` 로 올라온다 —
        #   0 으로 채우면 §12.1 이 금지한 "검증 없이 전망값으로 기준을 바꾸는" 상황이 된다.
        from core.enterprise_context.outlook_series import OutlookError, outlook_series
        try:
            merged = await asyncio.to_thread(
                outlook_series.attach_to_board,
                {"series": req.series, "meta": req.meta}, req.outlook_indicators,
                req.outlook_purpose, req.outlook_as_of, req.outlook_vintage)
        except OutlookError as e:
            _sandbox_err(e)
        series, meta, outlook = merged["series"], merged["meta"], merged["outlook"]

    try:
        d = await asyncio.to_thread(build_board, req.node_id, series, meta,
                                    req.rollups, viewer_may_drill_down(p), comp_rows)
    except BoardError as e:
        _sandbox_err(e)
    if outlook is not None:
        d["outlook"] = outlook
        # 제외된 지표 안내를 보드 경고에 합류시킨다 — 별도 필드에만 두면 화면이 안 읽는다.
        d["notes"] = list(d.get("notes") or []) + list(outlook.get("notes") or [])
    return {"status": "success", "data": d}
