"""Enterprise Context API — `docs/design_enterprise_context_master.md` §9 / E1.

E1 범위: 조직 트리 조회, 엔터티/노드/엣지 등록·승인, 문맥 선택 검증, 프로필 저장·조회, 시드.

미구현(범위 밖, 설계서 로드맵 그대로):
  · `GET /contexts/{scope_id}/resolved-profile` — **프로필 상속 해석은 E2**. E1 은 프로필을
    저장·조회만 하고 병합하지 않는다. 지금 반쪽 병합을 넣으면 "상속이 되는 것처럼 보이는데
    실제로는 아닌" 상태가 되어 더 위험하다.
  (E3 는 2026-07-31 에 구현했다 — 아래 `/entities/{id}/clone` · `/scenarios` 참조.
   가상 엔터티는 **직접 생성할 수 없고 복제로만** 만들어진다: `POST /entities` 는 여전히 REAL
   만 받고, 목적·유효기간·복사 정책이 함께 없으면 가상 조직이 생기지 않는다.)

권한: 조직 트리는 부서 권한으로 필터한다(§10.1 이행 — ECM 전용 권한 테이블은 E2).
  등록·승인은 조직 편집 권한(`assert_can_edit_org`)을 요구한다 — 조직은 기준정보다.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_can_edit_org, current_principal, enterprise_context)
from core.enterprise_context import (ENTITY_MODES, NODE_TYPES, PROFILE_KINDS, RELATION_TYPES,
                                     STATUS_ACTIVE, EcmError, EnterpriseContext,
                                     EnterpriseEntity, EnterpriseProfile, OrganizationEdge,
                                     OrganizationNode, ecm_repository, ecm_resolver)

router = APIRouter(prefix="/api/v1/enterprise-context", tags=["EnterpriseContext"])


def _sandbox_err(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


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
async def get_meta():
    """등록 가능한 유형 목록. 미등록 값은 거부되므로 클라이언트가 알아야 한다."""
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
    name_ko: str
    purpose: str                              # 목적 없는 가상 조직은 아무도 정리하지 못한다
    valid_until: str                          # YYYY-MM-DD — 만료 없는 가상 조직은 영구 조직이 된다
    copy: Dict[str, bool] = {}                # 선택 복사 항목만(금지 항목은 요청해도 거부)
    assumption_set_id: str = ""
    snapshot_id: str = ""


class PromoteIn(BaseModel):
    rationale: str


class CloseIn(BaseModel):
    reason: str = ""


@router.get("/copy-policy")
async def copy_policy():
    """복제 시 무엇을 가져오고 무엇을 **절대 가져오지 않는지**(§7.1).

    ★ 화면이 이 표를 그대로 보여주게 하려고 API 로 낸다 — 정책을 화면에 다시 적으면 두 곳이
      갈라지고, 사용자는 실제로 무엇이 복사됐는지 알 수 없게 된다."""
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
            req.valid_until, (p.user_id or ""), req.copy, ctx.tenant_id,
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
