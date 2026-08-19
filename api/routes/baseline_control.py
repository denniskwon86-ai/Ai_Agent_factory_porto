"""[Wave G] 기준선·시뮬레이션·의사결정 API. prefix `/api/v1/baseline`.

## 경계표 (`data_preparation_control` 과 같은 규칙)

· 타 조직·tenant·entity mode → **404**(은폐). 403 은 「그것이 존재한다」를 알려 준다.
· 문맥을 확정하지 못함 → **503**.
· 지금 상태에서 할 수 없는 일 → **409**.

⚠️ 계산은 여기서 하지 않는다 — `core/calc_graph` 가 한다. 라우트가 산식을 들고 있으면
  두 곳이 갈라지고, 갈린 날 어느 쪽이 맞는지 아무도 모른다.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal, require_caps, viewing_context
from core import baseline_build as bb
from core import calc_graph as cg
from core import decision_package as dpkg
from core import ontology_path as op
from core.admin_capability import PROJECT_RUN
from core.data_preparation.store import data_preparation_store as store
from core.route_authority import guard as _route_authority_guard

router = APIRouter(prefix="/api/v1/baseline", tags=["baseline"],
                   dependencies=[Depends(_route_authority_guard)])


class BuildRequest(BaseModel):
    """★ `snapshot_ids` 를 **명시**한다 — 「최신으로 알아서」를 받지 않는다.

    ⚠️ 그것을 받는 순간 재현할 수 없는 기준선이 생기고, 그 위의 보고서는 한 달 뒤
      다른 답을 낸다."""
    instance_id: str
    snapshot_ids: List[str]
    label: str = ""


class SimulateRequest(BaseModel):
    instance_id: str
    snapshot_ids: List[str]
    base_values: Dict[str, float]
    assumptions: Dict[str, float] = {}


class DecisionRequest(SimulateRequest):
    title: str
    owner: str
    due: str
    path_from: str = "purchase_order"
    path_to: str = "cash_pl"


def _visible_scopes(p: Principal) -> List[str]:
    return [str(x) for x in (getattr(p.scope, "readable_scope_nodes", ()) or ()) if str(x)]


def _instance_or_404(p: Principal, instance_id: str) -> Dict[str, Any]:
    """인스턴스를 **보이는 범위 안에서만** 찾는다.

    ★★★ 없는 것과 못 보는 것을 같은 404 로 돌려준다."""
    row = store.get_instance(instance_id)
    ctx = viewing_context(p)
    ok = bool(row) and (
        p.scope.unrestricted or (
            str(row["tenant_id"]) == str(ctx.get("tenant_id", "")) and
            str(row["entity_mode"]) == str(ctx.get("entity_mode", "")) and
            str(row["scope_node_id"]) in _visible_scopes(p)))
    if not ok:
        raise HTTPException(status_code=404, detail="키트 인스턴스를 찾을 수 없습니다.")
    return row


def _baseline(p: Principal, instance_id: str, snapshot_ids: List[str],
              label: str = "") -> bb.Baseline:
    """요청한 판들로 기준선을 만든다. **그 인스턴스의 판만** 쓴다.

    ⚠️ 남의 인스턴스 판 id 를 섞어 보내는 경로를 막는다 — 섞이면 그 합계는
      아무 회사의 숫자도 아니다."""
    inst = _instance_or_404(p, instance_id)
    want = {str(x).strip() for x in (snapshot_ids or []) if str(x).strip()}
    if not want:
        raise HTTPException(status_code=422,
                            detail="snapshot_ids 가 비었습니다 — 「최신으로 알아서」는 "
                                   "재현할 수 없는 기준선을 만듭니다.")
    rows = [s for s in store.list_snapshots(instance_id)
            if str(s.get("snapshot_id")) in want]
    found = {str(s.get("snapshot_id")) for s in rows}
    missing = sorted(want - found)
    if missing:
        #: ⚠️ 못 찾은 것을 조용히 빼지 않는다 — 빼면 «요청한 것보다 작은 기준선» 이
        #:   만들어지고, 사용자는 자기가 고른 대로 됐다고 믿는다.
        raise HTTPException(
            status_code=404,
            detail=f"이 인스턴스에 없는 판이 있습니다: {missing}")
    try:
        return bb.build(rows, label=label,
                        scope={"tenant_id": inst["tenant_id"],
                               "scope_node_id": inst["scope_node_id"],
                               "entity_mode": inst["entity_mode"]})
    except bb.BaselineError as e:
        #: 「지금 상태에서 할 수 없는 일」 — 요청을 고쳐서 되는 것이 아니다.
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/builds")
async def create_build(req: BuildRequest, p: Principal = Depends(current_principal)):
    """Snapshot 집합을 **고정**한다 — 「최신 포인터」가 아니다."""
    require_caps(p, PROJECT_RUN, resource="baseline", action="builds:create")
    return {"status": "success",
            "data": _baseline(p, req.instance_id, req.snapshot_ids, req.label).public()}


@router.post("/simulate")
async def simulate(req: SimulateRequest, p: Principal = Depends(current_principal)):
    """기준선 + 가정 → 다섯 결과. **같은 입력이면 같은 답이다.**"""
    require_caps(p, PROJECT_RUN, resource="baseline", action="simulate")
    baseline = _baseline(p, req.instance_id, req.snapshot_ids)
    try:
        base = cg.simulate(baseline, req.base_values, {})
        scen = cg.simulate(baseline, req.base_values, req.assumptions)
    except cg.CalcError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "success",
            "data": {"baseline": baseline.public(), "base": base.public(),
                     "scenario": scen.public(), "compare": cg.compare(base, scen)}}


@router.post("/decisions")
async def create_decision(req: DecisionRequest,
                          p: Principal = Depends(current_principal)):
    """시뮬레이션 → **회의 안건 하나**(3관점 검토서 + 책임자 + 기한 + 계보)."""
    require_caps(p, PROJECT_RUN, resource="baseline", action="decisions:create")
    baseline = _baseline(p, req.instance_id, req.snapshot_ids)
    try:
        base = cg.simulate(baseline, req.base_values, {})
        scen = cg.simulate(baseline, req.base_values, req.assumptions)
        path = op.trace(req.path_from, req.path_to, baseline=baseline,
                        snapshot_index=_snapshot_index(req.instance_id,
                                                       baseline.snapshot_ids))
        pkg = dpkg.build(title=req.title, owner=req.owner, due=req.due,
                         base=base, scenario=scen, baseline=baseline, path=path)
    except (cg.CalcError, op.OntologyError, dpkg.DecisionError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "success",
            "data": {**pkg.public(), "briefing": dpkg.briefing_lines(pkg)}}


@router.get("/impact-path")
async def impact_path(start: str = "purchase_order", end: str = "cash_pl",
                      p: Principal = Depends(current_principal)):
    """온톨로지 경로 하나. **수치는 없다** — 그것은 시뮬레이션이 답한다."""
    require_caps(p, PROJECT_RUN, resource="baseline", action="impact-path")
    try:
        return {"status": "success", "data": op.trace(start, end)}
    except op.OntologyError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _snapshot_index(instance_id: str, snapshot_ids: List[str]) -> Dict[str, str]:
    """계약키 → Snapshot id. **경로의 각 칸이 어느 판을 근거로 하는지** 잇는다.

    ⚠️ 본문을 싣지 않는다 — 식별자만이다(G2 §12.1)."""
    want = set(snapshot_ids or [])
    out: Dict[str, str] = {}
    for row in store.list_snapshots(instance_id):
        sid = str(row.get("snapshot_id") or "")
        if sid in want:
            key = str(row.get("dataset_contract_key") or "")
            if key:
                out[key] = sid
    return out
