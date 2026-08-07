"""[M2] 커넥터 등록부 + Query Contract REST API. prefix `/api/v1/connectors`. **LLM 0콜.**

§7.1 커넥터 계층 · §7.2 MCP 원칙(최소 권한·읽기 전용·명시적 등록·감사).

권한은 M2 자산(`core/scope_guard.py`)을 그대로 쓴다 — 커넥터도 조직 자산이고,
남의 사업부 연결은 **존재 자체가 보이면 안 된다**(404 은폐 + 감사).
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_identified, current_principal, require_caps
from core.route_authority import guard as _route_authority_guard
from core.admin_capability import ADMIN_DATA_ACCESS
from core.connector_registry import ConnectorError, connector_registry
from core.scope_guard import resolve_effective_scope

# ★★ [2026-08-07] 권한 배정표를 **라우터에 붙인다.** 라우트마다 `require_caps` 를 적지
#   않는 이유: 37개에 적으면 37번 빠뜨릴 기회가 생기고, 새 라우트가 생겨도 아무도
#   알려 주지 않는다. 표는 `core/route_authority.ROUTE_CAPS` 하나뿐이며,
#   `tests/test_route_authority_table.py` 가 표와 라우터를 **양방향으로** 대조한다.
router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"], dependencies=[Depends(_route_authority_guard)])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "커넥터"

# ── [2026-08-07 · 트랙 G] 무방비 라우트 봉합 ─────────────────────────────────
#
# 무방비 3개: `GET /adapters` · `GET /{id}/contracts` · `POST /{id}/validate`.
#
# ★★ `validate` 가 특히 그렇다. 그 docstring 이 **스스로 이유를 적어 두었다** —
#   「하나씩 튕기면 사용자가 여러 번 시도하며 무엇이 되는지 탐색하게 되고, **그 탐색 자체가
#   스키마 정보 유출**이다」. 거부 사유를 한 번에 다 주도록 만들어 놓고, 정작 그 응답을
#   익명에게 열어 두었다. 즉 익명이 한 번의 호출로 계약의 전모를 받을 수 있었다.
#   ⚠️ 위험을 알고 쓴 주석 옆에서 통제가 빠지는 것이 이 저장소가 반복한 모양이다.


def _assert_may_write(p: Principal, action: str) -> None:
    """★★ [2026-08-07 · 트랙 G] 커넥터를 **바꿔도 되는 주체인가.**

    ## 이것은 «무방비 라우트» 목록에 없던 결함이다

    이 세 라우트는 `Principal` 을 받고 있었다. 그래서 라우트 점검에서는 «통제됨» 으로 세어졌다.
    그런데 받기만 하고 **권한을 확인하지 않았다** — viewer 계정으로 커넥터를 등록하고 활성화하고
    Query Contract 를 추가할 수 있었다(트랙 G 게이트의 2차 검사가 잡았다: 400 = 인가를 지나
    업무 검증까지 도달했다는 뜻이다).

    ⚠️⚠️ **«주체를 받는가» 와 «권한을 보는가» 는 다른 질문이다.** 전자만 세면 절반이 초록으로
      보이고, 그 절반은 익명 검사만으로는 영원히 드러나지 않는다.

    ★ `_scope()` 도 통제가 아니다 — `owner_organization_id` 를 비우면 요청 범위가 빈 값이라
      정규화할 대상이 없어 통과한다. 파라미터를 주지 않는 것이 가장 넓은 호출이다
      (`/planning/facts` 유출의 두 번째 겹과 같은 구조)."""
    assert_identified(p, WHAT)
    require_caps(p, ADMIN_DATA_ACCESS, resource="connector", action=action)


def _err(e: ConnectorError):
    raise HTTPException(status_code=400, detail=str(e))


async def _scope(p: Principal, requested: str, resource_id: str = "",
                 tenant_id: str = "", entity_mode: str = "") -> str:
    """★ [D-018 ③④] 판정·정규화는 `api.deps.assert_scope_allowed` **한 곳**에 있다 —
    종전에는 이 코드가 `planning_control`·`briefing_control` 에도 복제돼 있었다."""
    from api.deps import assert_scope_allowed
    eff = await assert_scope_allowed(p, requested, resource_type="connector",
                                    resource_id=resource_id, tenant_id=tenant_id,
                                    entity_mode=entity_mode)
    return eff.scope_node_id


class ConnectorRequest(BaseModel):
    connector_id: str
    name: str
    kind: str                       # mcp | api | db | file
    endpoint: Optional[str] = ""
    #: ★ 자격증명이 아니라 **참조**(환경변수명·비밀관리자 키). 실제 비밀은 거부된다.
    auth_ref: Optional[str] = ""
    access_mode: str = "read"       # 기본 읽기 전용(§7.2)
    owner_organization_id: Optional[str] = ""
    scope_type: Optional[str] = "ORG_PRIVATE"
    note: Optional[str] = ""


class ContractRequest(BaseModel):
    query_name: str
    #: 비울 수 없다 — 빈 화이트리스트는 "아무거나 다 준다"가 된다.
    allowed_fields: List[str]
    required_params: Optional[List[str]] = None
    max_rows: int = 1000
    #: 허용 목록에 있어도 **프롬프트로는 나가지 않는다**(§7.2).
    sensitive_fields: Optional[List[str]] = None
    description: Optional[str] = ""


class ValidateRequest(BaseModel):
    query_name: str
    fields: List[str]
    params: Optional[Dict[str, Any]] = None
    limit: int = 0
    #: True 면 민감 필드를 제거한다(오류가 아니라 제거이며, 무엇이 빠졌는지 알려준다).
    for_prompt: bool = False


class ExecuteRequest(BaseModel):
    query_name: str
    fields: List[str]
    #: ★ §7.2 는 목적을 감사 항목으로 규정한다. 옵션으로 두면 아무도 적지 않고,
    #:   감사로그에서 "왜"가 영구히 빠져 사후에 정당성을 판단할 수 없다.
    purpose: str
    params: Optional[Dict[str, Any]] = None
    limit: int = 0
    for_prompt: bool = False


@router.get("/adapters")
async def list_adapters(p: Principal = Depends(current_principal)):
    """등록된 실행 어댑터. 비어 있으면 **어떤 조회도 실행되지 않는다**(빈 결과가 아니라 실패)."""
    assert_identified(p, WHAT)
    from core.connector_execution import registered_adapters
    ids = registered_adapters()
    return {"status": "success", "data": {"adapters": ids},
            "note": ("어댑터가 없는 커넥터는 계약을 통과해도 조회가 실패합니다. "
                     "빈 결과로 돌려주면 '데이터가 없다'로 오독되기 때문입니다."
                     if not ids else "")}


@router.get("")
async def list_connectors(scope_node_id: str = "", tenant_id: str = "",
                          entity_mode: str = "REAL",
                          p: Principal = Depends(current_principal)):
    # [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 내용은 가려진다.
    from core.enterprise_context.classification import clearance_of_scope
    # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체인가 — 이것도 권한에서 파생한다.
    from core.enterprise_context.scoping import may_drill_down
    eff = await _scope(p, scope_node_id)
    data = await asyncio.to_thread(connector_registry.list_connectors, eff,
                                   tenant_id, entity_mode,
                                   clearance_of_scope(p.scope),
                                   may_drill_down(p.scope))
    return {"status": "success", "data": data,
            "permission": {"scope": eff or "(범위 필터 없음)"}}


@router.post("")
async def register_connector(req: ConnectorRequest,
                             p: Principal = Depends(current_principal)):
    _assert_may_write(p, "register")
    await _scope(p, req.owner_organization_id or "", req.connector_id)
    try:
        data = await asyncio.to_thread(
            connector_registry.register, req.connector_id, req.name, req.kind,
            req.endpoint or "", req.auth_ref or "", req.access_mode,
            req.owner_organization_id or "", req.scope_type or "ORG_PRIVATE")
        return {"status": "success", "data": data}
    except ConnectorError as e:
        _err(e)


@router.post("/{connector_id}/activate")
async def activate(connector_id: str, p: Principal = Depends(current_principal)):
    """활성화 — 승인된 Query Contract 가 1건 이상 있어야 하고, 승인자가 식별돼야 한다."""
    # ⚠️ 종전에는 «식별됐는가» 만 봤다. 식별은 신원이지 권한이 아니다 — viewer 도 식별된다.
    _assert_may_write(p, "activate")
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(connector_registry.activate,
                                                connector_id, p.user_id)}
    except ConnectorError as e:
        _err(e)


@router.get("/{connector_id}/contracts")
async def list_contracts(connector_id: str, p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(connector_registry.list_contracts, connector_id)}


@router.post("/{connector_id}/contracts")
async def add_contract(connector_id: str, req: ContractRequest,
                       p: Principal = Depends(current_principal)):
    """Query Contract 등록. 승인자는 인증 주체로 기록된다(익명이면 미승인 상태)."""
    # ⚠️ 「익명이면 미승인 상태」는 **기록 방식**이지 접근 통제가 아니었다. 미승인이어도
    #   계약 자체는 등록되고 목록에 남는다 — 등록할 수 있는 사람을 먼저 정한다.
    _assert_may_write(p, "add_contract")
    try:
        data = await asyncio.to_thread(
            connector_registry.add_contract, connector_id, req.query_name,
            req.allowed_fields, req.required_params, req.max_rows,
            req.sensitive_fields, req.description or "", p.user_id)
        return {"status": "success", "data": data}
    except ConnectorError as e:
        _err(e)


@router.post("/{connector_id}/validate")
async def validate_request(connector_id: str, req: ValidateRequest,
                           p: Principal = Depends(current_principal)):
    """조회 요청이 계약을 지키는지 검증한다.

    ⚠️ 거부 사유를 **한 번에 전부** 돌려준다. 하나씩 튕기면 사용자가 여러 번 시도하며
      무엇이 되는지 탐색하게 되고, 그 탐색 자체가 스키마 정보 유출이다."""
    assert_identified(p, WHAT)
    data = await asyncio.to_thread(connector_registry.validate_request, connector_id,
                                   req.query_name, req.fields, req.params or {},
                                   req.limit, req.for_prompt)
    return {"status": "success", "data": data}


@router.post("/{connector_id}/execute")
async def execute_query(connector_id: str, req: ExecuteRequest,
                        p: Principal = Depends(current_principal)):
    """계약을 지켜 실제 조회한다 — **응답에도 계약을 적용한다**(§7.1/§7.2).

    `validate` 는 요청만 본다. 원천이 요청보다 더 준 것을 그대로 흘리면 계약서는 종이 조각이므로,
    계약에 없는 컬럼은 버리고 상한 초과 행은 자른다. 무엇을 버렸는지는 `enforcement` 에 담긴다 —
    ⚠️ `enforcement.contract_violations_by_source` 가 비어 있지 않으면 **원천 쪽 결함**이며,
    조용히 넘기면 그 결함은 영원히 고쳐지지 않는다."""
    if not p.user_id:
        raise HTTPException(
            status_code=401,
            detail="요청자 식별 정보가 없습니다 — X-User-Id 를 보내십시오. "
                   "§7.2 는 모든 조회에 요청자·목적을 감사로 남기도록 요구합니다.")
    from core.connector_execution import ConnectorExecutionError, execute, fetch_for_prompt
    fn = fetch_for_prompt if req.for_prompt else execute
    try:
        if req.for_prompt:
            data = await asyncio.to_thread(fn, connector_id, req.query_name, req.fields,
                                           p.user_id, req.purpose, req.params or {},
                                           req.limit)
        else:
            data = await asyncio.to_thread(fn, connector_id, req.query_name, req.fields,
                                           p.user_id, req.purpose, req.params or {},
                                           req.limit, False)
    except ConnectorExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not data.get("executed"):
        # 계약 위반은 거부지만 200 으로 감춘 채 빈 배열을 주면 "데이터 없음"으로 오독된다.
        raise HTTPException(status_code=403, detail={"errors": data.get("errors", []),
                                                    "note": data.get("note", "")})
    return {"status": "success", "data": data}
