"""[Wave G] 기준선·시뮬레이션·의사결정 API. prefix `/api/v1/baseline`.

## 경계표 (`data_preparation_control` 과 같은 규칙)

· 타 조직·tenant·entity mode → **404**(은폐). 403 은 「그것이 존재한다」를 알려 준다.
· 문맥을 확정하지 못함 → **503**.
· 지금 상태에서 할 수 없는 일 → **409**.

⚠️ 계산은 여기서 하지 않는다 — `core/calc_graph` 가 한다. 라우트가 산식을 들고 있으면
  두 곳이 갈라지고, 갈린 날 어느 쪽이 맞는지 아무도 모른다.
"""
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import Principal, current_principal, require_caps, viewing_context
from core import base_values as bv
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


class BaseValueRequest(BaseModel):
    """기준값을 «고른 판에서» 뽑아 달라는 요청. 기준선 요청과 같은 모양이다."""
    instance_id: str
    snapshot_ids: List[str]


def _rows_of(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    """인증된 판의 원본을 **그때 그 파일인지 확인하고** 읽는다.

    ★★★ checksum 대조 없이 읽으면 「인증한 판에서 뽑았다」는 말이 거짓이 될 수 있다.
    ⚠️ 못 읽으면 «되는 만큼» 읽지 않고 던진다 — 잘린 합계는 그럴듯하다."""
    from core.data_preparation import snapshot_service as ss

    path = str(snapshot.get("raw_path") or "")
    if not path or not os.path.exists(path):
        raise bv.BaseValueError(
            f"인증된 판의 원본 파일을 찾을 수 없습니다({os.path.basename(path) or '(경로 없음)'}).")
    if not ss.verify_raw(path, str(snapshot.get("checksum") or "")):
        raise bv.BaseValueError(
            "보관된 원본이 인증 당시와 다릅니다 — 이 판에서 값을 뽑지 않습니다.")
    with open(path, "rb") as f:
        payload = f.read()
    try:
        parsed = ss.parse_csv(payload, file_name=os.path.basename(path))
    except Exception as e:
        raise bv.BaseValueError(f"원본을 읽을 수 없습니다: {str(e)[:120]}")
    if len(parsed.rows) > bv.MAX_ROWS:
        raise bv.BaseValueError(
            f"행이 너무 많습니다({len(parsed.rows)}) — 일부만 더한 합계를 «전체» 라고 "
            f"적지 않습니다.")
    return parsed.rows


@router.post("/base-values")
async def base_values(req: BaseValueRequest, p: Principal = Depends(current_principal)):
    """고른 인증판에서 기준값을 뽑는다. **뽑을 수 없는 것은 뽑을 수 없다고 답한다.**

    ★★★ 화면이 7칸을 전부 사람에게 받고 있었다. 그중 셋은 이미 올려서 인증까지 마친
      판 안에 있다 — 있는 것을 다시 묻는 화면은 「데이터를 올리면 숫자가 나온다」는
      약속을 지키지 않는다.

    ⚠️ 유도한 값과 사람이 넣을 값을 **구분해서** 돌려준다. 섞으면 「이 숫자는 어디서
      왔나」에 답할 수 없다.
    ⚠️ 여기서 기본값을 지어내지 않는다 — 채울 수 없으면 사유를 돌려준다."""
    require_caps(p, PROJECT_RUN, resource="baseline", action="base-values")
    #: ★ 기준선과 **같은 문**을 지난다 — 범위·인증·성격 검사를 여기서 다시 쓰지
    #:   않는다. 두 벌이 되면 갈라지고, 갈린 쪽이 느슨한 쪽이 된다.
    baseline = _baseline(p, req.instance_id, req.snapshot_ids)

    by_id = {str(s.get("snapshot_id")): s for s in store.list_snapshots(req.instance_id)}
    rows_by_dataset: Dict[str, List[Dict[str, str]]] = {}
    snapshot_by_dataset: Dict[str, str] = {}
    try:
        for sid in baseline.snapshot_ids:
            snap = by_id.get(str(sid)) or {}
            key = str(snap.get("dataset_contract_key") or "")
            if not key:
                continue
            rows_by_dataset[key] = _rows_of(snap)
            snapshot_by_dataset[key] = str(sid)
    except bv.BaseValueError as e:
        #: 「지금 상태에서 할 수 없는 일」 — 요청을 고쳐서 되는 것이 아니다.
        raise HTTPException(status_code=409, detail=str(e))

    #: ★ 사유 문장이 사용자 화면에 그대로 나간다 — 계약키가 아니라 계약이 선언한
    #:   이름으로 말하게 한다(설계 §12).
    from core.data_preparation import kit_registry

    inst = _instance_or_404(p, req.instance_id)
    kit = kit_registry.resolve(store, inst["kit_id"], inst["version"])
    labels = {k: (v.get("label") or k)
              for k, v in kit_registry.dataset_labels((kit or {}).get("profile")).items()}
    fields = bv.derive(rows_by_dataset=rows_by_dataset,
                       snapshot_by_dataset=snapshot_by_dataset, labels=labels)
    return {"status": "success",
            "data": {**bv.summary(fields),
                     "baseline_fingerprint": baseline.fingerprint,
                     "data_kind": baseline.data_kind}}


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
                      instance_id: str = "",
                      snapshot_ids: List[str] = Query(default=[]),
                      p: Principal = Depends(current_principal)):
    """온톨로지 경로 하나. **수치는 없다** — 그것은 시뮬레이션이 답한다.

    ★★★ 기준선을 함께 주면 **그 기준선으로** 근거를 잇는다. 주지 않으면 근거를
      «확인하지 않은» 것이지 «없는» 것이 아니다 — 응답의 `evidence_checked` 가
      그 둘을 가른다. 이것을 섞으면 한 화면에서 위쪽은 「근거 없음」, 아래쪽 안건은
      그 판을 근거로 쓰는 상태가 된다(2026-08-19 화면에서 실제로 그랬다)."""
    require_caps(p, PROJECT_RUN, resource="baseline", action="impact-path")
    index = None
    if instance_id:
        #: ⚠️ 범위 밖 인스턴스로 경로를 채워 주지 않는다 — 여기서도 같은 404 다.
        _instance_or_404(p, instance_id)
        index = _snapshot_index(instance_id, [str(x) for x in (snapshot_ids or [])])
    try:
        return {"status": "success", "data": op.trace(start, end, snapshot_index=index)}
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
