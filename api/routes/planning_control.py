"""[M4] 경영계획 REST API. prefix `/api/v1/planning`. **LLM 0콜.**

명세서 §17 첫 파일럿(경영계획–실적–시나리오)의 백엔드 계약이다.

## 권한은 M2 자산을 그대로 쓴다

조직 범위 판정은 `core/scope_guard.resolve_effective_scope` 하나를 탄다 —
**클라이언트가 보낸 범위는 요청이지 권한이 아니다.** 거부는 감사로그에 남고 응답은 404 로
은폐한다(§3.3 경계표). 같은 판정을 여기서 다시 구현하면 반드시 어긋난다.

⚠️ 조직별 손익은 새어 나가면 되돌릴 수 없다. 그래서 이 라우터는 M1~M2 에서 만든 격리를
  **처음부터** 타고, 나중에 붙이는 것이 아니다.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_identified, current_principal
from core import planning_engine as engine
from core.planning_model import PLAN, VALUE_KINDS, PlanningError, planning_store
from core.scope_guard import resolve_effective_scope

router = APIRouter(prefix="/api/v1/planning", tags=["Planning"])


def _err(e: PlanningError):
    raise HTTPException(status_code=400, detail=str(e))


async def _scope(p: Principal, requested: str, resource_id: str = "",
                 tenant_id: str = "", entity_mode: str = "") -> str:
    """요청 범위를 인증 주체 안에서 교차 검증한다. 거부는 감사 + 404 은폐.

    ★ [D-018 ③④] 판정·정규화는 `api.deps.assert_scope_allowed` **한 곳**에 있다. 이 함수는
      그 결과에서 정본 `node_id` 만 꺼내는 얇은 래퍼다 — 종전에는 같은 코드가 이 파일과
      `briefing_control`·`connector_control` 에 **세 벌** 복제돼 있었고, 그러면 문맥 인자를
      하나에만 붙이거나 감사 이름을 한 곳만 고치는 일이 생긴다.
    ⚠️ 표시용 코드·이름이 필요하면 `_scope_eff()` 를 써서 `EffectiveScope` 를 그대로 받는다."""
    return (await _scope_eff(p, requested, resource_id, tenant_id, entity_mode)).scope_node_id


async def _scope_eff(p: Principal, requested: str, resource_id: str = "",
                     tenant_id: str = "", entity_mode: str = ""):
    from api.deps import assert_scope_allowed
    return await assert_scope_allowed(p, requested, resource_type="plan_fact",
                                     resource_id=resource_id, tenant_id=tenant_id,
                                     entity_mode=entity_mode)


# ── [2026-08-05] 무방비 라우트 봉합 ────────────────────────────────────
# 실측: 익명이 `GET /accounts`(계정과목 10건) · `GET /scenarios`(시나리오 4건) ·
#   `GET /submissions`(**경영계획 제출물**)을 그대로 읽고, `POST /accounts` · `POST /drivers`
#   로 기준정보를 **실제로 등록**할 수 있었다. 라우트에 `Principal` 의존성이 없었기 때문이다.
# ⚠️ 인수인계 기록은 «지금은 0건이라 실제 유출이 없다» 고 적었지만 **그 사이 데이터가 들어왔다.**
#   «비어 있으니 나중에» 로 미룬 통제는 데이터가 들어오는 순간 유출이 된다.

# ★ 판정은 `api/deps.py` 하나에 있다. 여기 있던 `_assert_identified`·`_eul` 을 2026-08-07 에
#   그리로 올렸다 — 트랙 G 가 같은 봉합을 16개 파일에 더 해야 하는데, 파일마다 복사하면 판정이
#   열일곱 벌이 되고 그중 하나만 고쳐지는 날이 온다(인계서가 여덟 번 기록한 결함 유형).
#   이름을 남겨 두는 이유는 이 파일의 호출부 20여 곳을 건드리지 않기 위해서다.
_assert_identified = assert_identified


def _only_visible_orgs(p: Principal, rows: list, key: str = "org_id") -> tuple:
    """조직 범위 밖 행을 걷어낸다. **판정은 `viewer_visible_scopes` 하나를 탄다.**

    ⚠️ 저장소 시그니처에 범위 인자가 없는 목록(`list_submissions`·`scenarios`)을 위한 후처리다.
      판정 자체를 여기서 다시 쓰지 않는 것이 중요하다 — 이 파일 머리말이 경고한 그대로,
      같은 판정을 두 번 구현하면 반드시 어긋난다.
    ⚠️ 소유 조직이 **비어 있는 행은 보이지 않는다**(`scope_allows_owner` 의 계약). 미기재를
      «공개» 로 읽으면 이행 기간에 전 조직 자료가 새어 나간다."""
    from api.deps import scope_allows_owner, viewer_visible_scopes
    scopes = viewer_visible_scopes(p)
    if scopes is None:                       # 강제 OFF · unrestricted · DA — 의도된 전면 통과
        return rows, 0
    kept = [r for r in rows if scope_allows_owner(scopes, str((r or {}).get(key) or ""))]
    return kept, len(rows) - len(kept)


async def _assert_rows_in_scope(p: Principal, rows: list) -> None:
    """등록 행의 **모든 조직**이 요청자 범위 안인가.

    ⚠️ [2026-08-05] `planning_import.import_rows` 는 행의 `org_id` 를 **검증 없이 그대로
      저장한다.** 즉 식별된 사용자면 누구나 **남의 조직 실적·계획을 등록**할 수 있었다 —
      읽기를 막아도 이 경로로 들어온 값이 그 조직의 실적이 되므로 통제가 성립하지 않는다.
    ★ 하나라도 범위 밖이면 **전부 거부**한다. importer 의 «한 행이라도 문제가 있으면 아무것도
      저장하지 않는다» 와 같은 규칙이다 — 부분 저장은 무엇이 들어갔는지 아무도 모르게 만든다.
    ★ `commit` 여부와 무관하게 검증한다. 검증 전용 호출도 «그 조직에 무엇이 들어갈 수 있는가»
      를 알려 주고, 무엇보다 두 경로의 판정이 다르면 반드시 어긋난다."""
    orgs = sorted({str((r or {}).get("org_id") or "").strip() for r in (rows or [])})
    for org in orgs:
        if not org:
            # 조직 없는 행은 여기서 막지 않는다 — importer 의 필수 열 검증이 사유를 말한다.
            continue
        await _scope(p, org, org)


def _hidden(p: Principal, total: int, shown: int) -> dict:
    """숨긴 건수의 노출 정책. **사실은 모두에게, 정확한 수는 자격자에게만.**

    경영계획은 재무 정보다 — «전사에 계획이 몇 건 있는가» 자체가 정보이므로 정확한 수는
    경영진·데이터 관리자에게만 준다(Data Stealth, 사용자 결정 2026-08-04)."""
    from api.deps import hidden_envelope
    return hidden_envelope(p, total, shown, exact_for="plan")


# ── 계정 ──────────────────────────────────────────────────────────────
class AccountRequest(BaseModel):
    account_code: str
    name: str
    category: str
    sign: int = 1
    parent_code: Optional[str] = ""


@router.get("/accounts")
async def list_accounts(p: Principal = Depends(current_principal)):
    """계정과목 체계. 조직 범위가 없는 **전사 기준정보**이므로 행 필터는 없고 식별만 요구한다.

    ⚠️ 익명에게 줄 이유가 없다 — 계정 체계는 그 회사가 무엇을 어떻게 관리하는지 드러낸다."""
    _assert_identified(p, "계정과목")
    return {"status": "success", "data": await asyncio.to_thread(planning_store.list_accounts)}


@router.post("/accounts")
async def upsert_account(req: AccountRequest, p: Principal = Depends(current_principal)):
    """★★★ [2026-08-05 실측 결함] 익명이 계정과목을 **실제로 등록할 수 있었다.**

    계정과목은 전사 기준정보다 — 한 사람이 추가하면 전 조직의 계획·실적 집계가 바뀐다.
    그리고 `upsert` 이므로 **기존 계정을 덮어쓸 수도** 있었다(같은 코드로 이름·부호를 바꾸면
    과거 집계의 의미가 달라진다). 그래서 기준정보 관리 권한을 요구한다."""
    _assert_identified(p, "계정과목")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(planning_store.upsert_account, req.account_code,
                                       req.name, req.category, req.sign, req.parent_code or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 사실(계획·실적·예측) ──────────────────────────────────────────────
class FactRequest(BaseModel):
    org_id: str
    account_code: str
    period: str
    #: ★ 기본값을 두지 않는다 — 두면 호출자가 생각 없이 넣고 '실적처럼 보이는 계획'이 생긴다.
    value_kind: str
    amount: float
    currency: Optional[str] = "KRW"
    scenario_id: Optional[str] = ""
    source_ref: Optional[str] = ""
    owner_organization_id: Optional[str] = ""
    scope_type: Optional[str] = "ORG_PRIVATE"
    classification: Optional[str] = "INTERNAL"
    #: 분석 차원. 빈 값 = 그 차원으로 나누지 않은 **합계** 행이다(상세 행과 섞이면 이중 계상).
    product_code: Optional[str] = ""
    cost_center: Optional[str] = ""


@router.get("/facts")
async def list_facts(org_id: str = "", period: str = "", value_kind: str = "",
                     scenario_id: str = "", scope_node_id: str = "",
                     tenant_id: str = "", entity_mode: str = "REAL",
                     product_code: str = "", cost_center: str = "",
                     p: Principal = Depends(current_principal)):
    # [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 값은 가려진다.
    #   ⚠️ 경영계획 값은 특히 민감하다(사업부 손익) — 등급을 안 넘기면 전 조직이 전량을 본다.
    _assert_identified(p, "경영계획")
    from core.enterprise_context.classification import clearance_of_scope
    # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체인가 — 이것도 권한에서 파생한다.
    from core.enterprise_context.scoping import may_drill_down
    # ★ [D-018 ③④] `tenant_id`·`entity_mode` 를 **범위 해석에도** 넘긴다. 종전에는 저장소
    #   조회에만 넘기고 해석에는 넣지 않아, 코드로 들어온 범위가 문맥과 무관하게 해석됐다.
    _eff = await _scope_eff(p, scope_node_id, org_id, tenant_id, entity_mode)
    eff = _eff.scope_node_id
    data = await asyncio.to_thread(planning_store.list_facts, org_id, period, value_kind,
                                   scenario_id, eff, tenant_id, entity_mode,
                                   product_code, cost_center,
                                   clearance_of_scope(p.scope),
                                   may_drill_down(p.scope))
    from api.deps import scope_meta
    return {"status": "success", "data": data,
            "permission": {"scope": eff or "(범위 필터 없음)", **scope_meta(_eff)}}


@router.post("/facts")
async def put_fact(req: FactRequest, p: Principal = Depends(current_principal)):
    """[D-018 ⑥] **소유 조직은 정본 `node_id` 로 저장한다.**

    ★ `_scope()` 는 이미 요청 값을 정본으로 해석해 돌려준다 — 종전에는 그 결과를 판정에만 쓰고
      **저장은 원본(코드)으로** 했다. 그래서 백필로 정리한 컬럼에 코드가 다시 들어왔다.
    ⚠️ `planning_store.put_fact` 는 `owner_organization_id` 가 비면 `org_id` 로 채운다 —
      즉 빈 값을 넘기면 **코드가 소유로 저장된다.** 그래서 항상 정규화된 값을 채워 넘긴다.
    ⚠️ `org_id` 는 정규화하지 **않는다.** 그것은 `fact_id` 의 구성 요소이고(`org_id|account|…`)
      인덱스 3개·화면 조회 파라미터가 그 값을 쓴다 — 바꾸면 기본키가 달라져 기존 행과 이어지지
      않는다. 권한 판정은 `owner_organization_id`(정본)로 하므로 통제는 정본을 탄다."""
    _assert_identified(p, "경영계획")
    eff = await _scope_eff(p, req.owner_organization_id or req.org_id, req.account_code)
    owner = eff.scope_node_id or (req.owner_organization_id or req.org_id)
    try:
        data = await asyncio.to_thread(
            planning_store.put_fact, req.org_id, req.account_code, req.period,
            req.value_kind, req.amount, req.currency or "KRW", req.scenario_id or "",
            req.source_ref or "", owner,
            req.scope_type or "ORG_PRIVATE", req.classification or "INTERNAL",
            "tenant_default", "REAL", req.product_code or "", req.cost_center or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 시나리오 ──────────────────────────────────────────────────────────
class ScenarioRequest(BaseModel):
    scenario_id: str
    name: str
    org_id: str = ""
    baseline_kind: str = PLAN
    owner: Optional[str] = ""


class AssumptionRequest(BaseModel):
    target_code: str
    operator: str            # pct | delta | set
    value: float
    target_kind: str = "account"
    unit: Optional[str] = ""
    #: 근거 없는 가정은 재현이 아니라 창작이다(§11.3).
    rationale: str = ""


class ScenarioDecisionRequest(BaseModel):
    rationale: str


async def _scenario_owner(p: Principal, scenario_id: str) -> dict:
    """Read the canonical scenario scope; callers never submit scope or tenant IDs."""
    def _read():
        conn = planning_store._connect()
        try:
            row = conn.execute(
                "SELECT org_id,tenant_id,owner_organization_id,entity_mode "
                "FROM scenarios WHERE scenario_id=?", (scenario_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    row = await asyncio.to_thread(_read)
    if not row:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    await _scope(
        p, str(row.get("org_id") or ""), scenario_id,
        str(row.get("tenant_id") or ""), str(row.get("entity_mode") or ""))
    return row


@router.post("/scenarios/{scenario_id}/approve")
async def approve_scenario(scenario_id: str, req: ScenarioDecisionRequest,
                           p: Principal = Depends(current_principal)):
    """Freeze the editable scenario into an immutable, ledger-backed release."""
    _assert_identified(p, "시나리오 승인")
    from api.deps import assert_can_manage_standard
    from core import planning_scenario_release
    assert_can_manage_standard(p)
    await _scenario_owner(p, scenario_id)
    try:
        data = await asyncio.to_thread(
            planning_scenario_release.approve, scenario_id, p.user_id,
            req.rationale, store=planning_store)
        return {"status": "success", "data": data}
    except PlanningError as exc:
        _err(exc)


@router.post("/scenarios/{scenario_id}/revoke")
async def revoke_scenario(scenario_id: str, req: ScenarioDecisionRequest,
                          p: Principal = Depends(current_principal)):
    """Revoke an approved release; the approval and revocation remain in the ledger."""
    _assert_identified(p, "시나리오 승인 철회")
    from api.deps import assert_can_manage_standard
    from core import planning_scenario_release
    assert_can_manage_standard(p)
    await _scenario_owner(p, scenario_id)
    try:
        data = await asyncio.to_thread(
            planning_scenario_release.revoke, scenario_id, p.user_id,
            req.rationale, store=planning_store)
        return {"status": "success", "data": data}
    except PlanningError as exc:
        _err(exc)


@router.get("/scenarios")
async def list_scenarios(org_id: str = "", p: Principal = Depends(current_principal)):
    """★★★ [2026-08-05 실측 결함] 익명이 시나리오 4건을 그대로 읽었다.

    ⚠️ 시나리오 이름과 기준(`baseline_kind`)만으로도 그 조직이 무엇을 걱정하는지 드러난다
      («원가 급등 시나리오» 가 있다는 사실 자체가 정보다). `org_id` 필터가 **호출자 선택**
      이었던 것이 원인이다 — 통제를 호출자에게 맡기면 그 파라미터를 빼면 전량이 나온다."""
    _assert_identified(p, "시나리오")
    await _scope(p, org_id, org_id)          # 요청 범위 교차 검증(거부는 404 은폐)

    def _q():
        conn = planning_store._connect()
        try:
            sql = "SELECT * FROM scenarios" + (" WHERE org_id=?" if org_id else "")
            return [dict(r) for r in conn.execute(sql, (org_id,) if org_id else ())]
        finally:
            conn.close()
    rows = await asyncio.to_thread(_q)
    shown, _ = _only_visible_orgs(p, rows)
    return {"status": "success", "data": shown, **_hidden(p, len(rows), len(shown))}


@router.post("/scenarios")
async def create_scenario(req: ScenarioRequest, p: Principal = Depends(current_principal)):
    """[D-018 ⑥] 소유 조직은 **정본**으로 저장한다(`org_id` 는 조회 키이므로 그대로 둔다)."""
    _assert_identified(p, "시나리오")
    eff = await _scope_eff(p, req.org_id, req.scenario_id)
    owner = eff.scope_node_id or req.org_id

    def _ins():
        from datetime import datetime, timezone
        conn = planning_store._connect()
        try:
            if conn.execute("SELECT 1 FROM scenarios WHERE scenario_id=?",
                            (req.scenario_id,)).fetchone():
                raise PlanningError(f"이미 존재하는 시나리오입니다: {req.scenario_id}")
            conn.execute(
                "INSERT INTO scenarios(scenario_id,name,org_id,baseline_kind,owner,created_at,"
                "owner_organization_id) VALUES(?,?,?,?,?,?,?)",
                (req.scenario_id, req.name, req.org_id, req.baseline_kind, req.owner or "",
                 datetime.now(timezone.utc).isoformat(timespec="seconds"), owner))
            conn.commit()
            return dict(conn.execute("SELECT * FROM scenarios WHERE scenario_id=?",
                                     (req.scenario_id,)).fetchone())
        finally:
            conn.close()
    try:
        return {"status": "success", "data": await asyncio.to_thread(_ins)}
    except PlanningError as e:
        _err(e)


@router.post("/scenarios/{scenario_id}/assumptions")
async def add_assumption(scenario_id: str, req: AssumptionRequest,
                         p: Principal = Depends(current_principal)):
    """★★★ [2026-08-05 실측 결함] 익명이 **계획 가정을 바꿀 수 있었다.**

    가정은 시나리오 결과를 직접 움직인다 — «환율 10% 상승» 을 누가 넣었는지 모르면 그 결과로
    쓰인 경영 보고를 되짚을 수 없다. 자격은 `POST /scenarios`(시나리오 생성)와 **같게** 둔다:
    시나리오를 만들 수 있는 사람이 가정도 넣는다. 별도 «계획 수립 권한» 을 새로 만들지 않은
    이유는 그것이 제품 정책이고 사용자 결정 사항이기 때문이다(인수인계 §7-2).
    ⚠️ 대상 시나리오의 **소유 조직**으로 범위를 검증한다 — 요청자가 보낸 값이 아니다."""
    _assert_identified(p, "계획 가정")

    def _owner():
        conn = planning_store._connect()
        try:
            r = conn.execute("SELECT org_id FROM scenarios WHERE scenario_id=?",
                             (scenario_id,)).fetchone()
            return (dict(r).get("org_id") if r else None)
        finally:
            conn.close()
    owner = await asyncio.to_thread(_owner)
    if owner is None:
        # 없는 시나리오는 404 — 존재 여부를 알려 주지 않는다(그러면 id 를 훑어볼 수 있다).
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    await _scope(p, owner, scenario_id)

    if (req.operator or "").lower() not in ("pct", "delta", "set"):
        raise HTTPException(status_code=400, detail="operator 는 pct | delta | set 이어야 합니다.")
    if not (req.rationale or "").strip():
        # 근거를 강제하는 이유: 나중에 "왜 10% 로 뒀는가"에 답할 수 없으면 그 시나리오는
        # 재현은 되지만 **설명되지 않는다**. 경영 보고에서는 둘 다 필요하다.
        raise HTTPException(status_code=400,
                            detail="rationale(가정의 근거)은 필수입니다 — 근거 없는 가정은 재현이 아니라 창작입니다.")

    def _ins():
        import uuid
        from datetime import datetime, timezone
        conn = planning_store._connect()
        try:
            if not conn.execute("SELECT 1 FROM scenarios WHERE scenario_id=?",
                                (scenario_id,)).fetchone():
                raise PlanningError(f"존재하지 않는 시나리오입니다: {scenario_id}")
            aid = uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                "target_code,operator,value,unit,rationale,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (aid, scenario_id, req.target_kind, req.target_code, req.operator.lower(),
                 req.value, req.unit or "", req.rationale,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
            return {"assumption_id": aid, "scenario_id": scenario_id}
        finally:
            conn.close()
    try:
        return {"status": "success", "data": await asyncio.to_thread(_ins)}
    except PlanningError as e:
        _err(e)


class RunRequest(BaseModel):
    org_id: str
    period: str
    baseline_kind: str = PLAN
    #: 기본 False — 탐색적 실행이 기록을 오염시키면 안 된다.
    persist: bool = False


@router.post("/scenarios/{scenario_id}/run")
async def run_scenario(scenario_id: str, req: RunRequest,
                       p: Principal = Depends(current_principal)):
    _assert_identified(p, "시나리오 실행")
    await _scope(p, req.org_id, scenario_id)
    try:
        data = await asyncio.to_thread(engine.run_scenario, scenario_id, req.org_id,
                                       req.period, req.baseline_kind, req.persist)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


class CompareRequest(BaseModel):
    scenario_ids: List[str]
    org_id: str
    period: str
    baseline_kind: str = PLAN


@router.post("/scenarios/compare")
async def compare(req: CompareRequest, p: Principal = Depends(current_principal)):
    """여러 시나리오를 **동일 기준선에서** 비교(§17.3 파일럿 성공 기준).

    응답의 `same_baseline` 이 false 면 그 비교는 무효다 — 화면은 그것을 숨기지 말 것."""
    _assert_identified(p, "시나리오 비교")
    await _scope(p, req.org_id, ",".join(req.scenario_ids))
    if not req.scenario_ids:
        raise HTTPException(status_code=400, detail="비교할 시나리오가 없습니다.")
    try:
        data = await asyncio.to_thread(engine.compare_scenarios, req.scenario_ids,
                                       req.org_id, req.period, req.baseline_kind)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


# ── 차이 분석 ─────────────────────────────────────────────────────────
@router.get("/variance")
async def variance(org_id: str, period: str, p: Principal = Depends(current_principal)):
    """계획 대비 실적 차이(§17.2 기능 4).

    ⚠️ 한쪽이 비어 있으면 `comparable=false` 로 돌려주고 **차이를 계산하지 않는다.**
      없는 값을 0 으로 두면 '미달'로 잘못 읽힌다."""
    _assert_identified(p, "계획 대비 실적")
    await _scope(p, org_id, org_id)
    data = await asyncio.to_thread(engine.variance, org_id, period)
    return {"status": "success", "data": data}


# ── 제출·승인 흐름 (§17.2 기능 3) ─────────────────────────────────────
# ⚠️ 승인은 상태 플래그가 아니다 — 승인 시점의 값 지문을 함께 박고, 조회 때 무결성을
#   다시 확인한다. "승인됐다"와 "승인받은 그 값 그대로다"는 다른 질문이다.
from core import planning_approval as approval


class SubmitRequest(BaseModel):
    org_id: str
    period: str
    value_kind: str = PLAN
    note: Optional[str] = ""


class ApproveRequest(BaseModel):
    #: 자기 승인은 통제가 아니라 형식이라 기본 차단. 1인 부서면 명시적으로 연다(감사에 남는다).
    allow_self_approval: bool = False


class RejectRequest(BaseModel):
    #: 사유 없는 반려는 제출자가 무엇을 고쳐야 할지 모른다.
    reason: str


@router.get("/submissions")
async def list_submissions(org_id: str = "", period: str = "", status: str = "",
                           p: Principal = Depends(current_principal)):
    """★★★ [2026-08-05 실측 결함] **경영계획 제출물이 익명에게 노출되고 있었다.**

    인수인계 기록은 «지금은 0건이라 실제 유출이 없다» 고 적었는데 그 사이 제출물이 들어왔다.
    ⚠️ 제출 이력은 «어느 조직이 언제 무엇을 올렸고 승인됐는가» 다 — 본문 금액이 없어도 조직의
      계획 수립 상태가 드러난다. «비어 있으니 나중에» 로 미룬 통제는 데이터가 들어오는 순간
      유출이 된다. 그것이 이 라우트에서 실제로 일어났다."""
    _assert_identified(p, "경영계획 제출 이력")
    await _scope(p, org_id, org_id)
    rows = await asyncio.to_thread(approval.list_submissions, org_id, period, status)
    shown, _ = _only_visible_orgs(p, rows)
    return {"status": "success", "data": shown, **_hidden(p, len(rows), len(shown))}


@router.get("/submissions/current")
async def current_approved(org_id: str, period: str, value_kind: str = PLAN,
                           p: Principal = Depends(current_principal)):
    """현재 유효한 승인본 + **무결성 판정**. 없으면 data=null(빈 객체로 위장하지 않는다).

    ⚠️ 이것은 **계획 본문**이다(금액 포함). 범위 밖 요청은 `_scope` 가 404 로 은폐한다 —
      «그 조직에 승인된 계획이 있다» 는 사실조차 알려 주지 않는다."""
    _assert_identified(p, "승인된 경영계획")
    await _scope(p, org_id, org_id)
    data = await asyncio.to_thread(approval.current_approved, org_id, period, value_kind)
    return {"status": "success", "data": data}


@router.post("/submissions")
async def submit_plan(req: SubmitRequest, p: Principal = Depends(current_principal)):
    _assert_identified(p, "계획 제출본")
    await _scope(p, req.org_id, req.org_id)
    if not p.user_id:
        raise HTTPException(status_code=401, detail="제출자 식별 정보가 없습니다.")
    try:
        data = await asyncio.to_thread(approval.submit, req.org_id, req.period,
                                       p.user_id, req.value_kind, req.note or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/submissions/{submission_id}/approve")
async def approve_plan(submission_id: str, req: ApproveRequest = None,
                       p: Principal = Depends(current_principal)):
    _assert_identified(p, "계획 제출본 승인")
    if not p.user_id:
        raise HTTPException(status_code=401, detail="승인자 식별 정보가 없습니다 — "
                                                   "익명 승인은 받지 않습니다.")
    try:
        data = await asyncio.to_thread(approval.approve, submission_id, p.user_id,
                                       bool(req.allow_self_approval) if req else False)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/submissions/{submission_id}/reject")
async def reject_plan(submission_id: str, req: RejectRequest,
                      p: Principal = Depends(current_principal)):
    _assert_identified(p, "계획 제출본 반려")
    if not p.user_id:
        raise HTTPException(status_code=401, detail="반려자 식별 정보가 없습니다.")
    try:
        data = await asyncio.to_thread(approval.reject, submission_id, p.user_id, req.reason)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/submissions/{submission_id}/integrity")
async def check_integrity(submission_id: str, p: Principal = Depends(current_principal)):
    """★ 승인 후 값이 바뀌었는지 — 상태만 보면 알 수 없다.

    ⚠️ 무결성 판정은 «그 조직의 승인본이 사후 변경됐다» 는 사실을 알려 준다. 남의 조직 것을
      들여다볼 수 있으면 그 조직의 통제 실패를 외부에서 관찰하게 된다. 대상 제출물의 **소유
      조직**으로 범위를 검증한다."""
    _assert_identified(p, "제출물 무결성")
    rows = await asyncio.to_thread(approval.list_submissions, "", "", "")
    row = next((r for r in rows if str(r.get("submission_id")) == submission_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 제출입니다: {submission_id}")
    await _scope(p, str(row.get("org_id") or ""), submission_id)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(approval.verify_integrity, submission_id)}
    except PlanningError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 계획 동인 (§17.2 기능 5) ──────────────────────────────────────────
# ⚠️ 파급 계수는 **사람이 등록하고 근거를 남긴다.** LLM·자동 회귀로 만들면 그럴듯한 가짜
#   인과가 생기고, 그것이 경영 보고서에 "환율 때문에 원가가 이만큼 오릅니다"로 인쇄된다.
from core import planning_drivers as drivers


class DriverRequest(BaseModel):
    driver_code: str
    name: str
    unit: Optional[str] = ""
    category: Optional[str] = ""
    #: §12 외부 지표 연결. **표시일 뿐 자동 주입이 아니다**(등급 정책은 외부 인텔리전스가 강제).
    external_code: Optional[str] = ""
    note: Optional[str] = ""


class ImpactRequest(BaseModel):
    account_code: str
    #: 동인이 1% 변할 때 계정이 몇 % 변하는가.
    elasticity: float
    rationale: str        # 필수 — 근거 없는 계수는 창작이다
    source: str           # 필수 — 실적회귀·업계자료·전문가판단 중 무엇인가


@router.get("/drivers")
async def list_drivers(p: Principal = Depends(current_principal)):
    """계획 동인 목록. 전사 기준정보이므로 행 필터는 없고 식별만 요구한다."""
    _assert_identified(p, "계획 동인")
    return {"status": "success", "data": await asyncio.to_thread(drivers.list_drivers)}


@router.post("/drivers")
async def register_driver(req: DriverRequest, p: Principal = Depends(current_principal)):
    """★★★ [2026-08-05 실측 결함] 익명이 동인을 **실제로 등록할 수 있었다.**

    동인은 «무엇이 계획을 움직이는가» 의 목록이고 파급 계수의 뿌리다 — 여기 등록된 동인이
    시나리오 가정으로 쓰인다. 계정과목과 같은 전사 기준정보이므로 같은 자격을 요구한다."""
    _assert_identified(p, "계획 동인")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(drivers.register_driver, req.driver_code, req.name,
                                       req.unit or "", req.category or "",
                                       req.external_code or "", req.note or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/drivers/{driver_code}/impacts")
async def list_impacts(driver_code: str, p: Principal = Depends(current_principal)):
    _assert_identified(p, "파급 계수")
    return {"status": "success",
            "data": await asyncio.to_thread(drivers.impacts_of, driver_code)}


@router.post("/drivers/{driver_code}/impacts")
async def add_impact(driver_code: str, req: ImpactRequest,
                     p: Principal = Depends(current_principal)):
    """파급 계수 등록. 승인자는 인증 주체로 기록된다.

    ⚠️ [2026-08-05] `Principal` 은 있었지만 **권한 검사가 없었다** — 익명이면 «미승인» 으로
      기록될 뿐 행은 만들어졌다. 미승인 계수도 `preview` 의 경고에 섞여 나오고, 무엇보다
      전사 기준정보에 아무나 행을 추가할 수 있다는 사실은 그대로다."""
    _assert_identified(p, "동인 영향")
    from api.deps import assert_can_manage_standard
    assert_can_manage_standard(p)
    try:
        data = await asyncio.to_thread(drivers.add_impact, driver_code, req.account_code,
                                       req.elasticity, req.rationale, req.source, p.user_id)
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/drivers/{driver_code}/approve")
async def approve_driver(driver_code: str, req: ScenarioDecisionRequest,
                         p: Principal = Depends(current_principal)):
    """Freeze the selected draft driver and impacts in the verified viewing context."""
    _assert_identified(p, "경영 동인 승인")
    from api.deps import assert_can_manage_standard, viewing_context
    from core import planning_driver_release
    assert_can_manage_standard(p)
    ctx = viewing_context(p)
    scope_node_id = str(ctx.get("scope_node_id") or "").strip()
    tenant_id = str(ctx.get("tenant_id") or "").strip()
    entity_mode = str(ctx.get("entity_mode") or "").strip()
    if not all((scope_node_id, tenant_id, entity_mode)):
        raise HTTPException(status_code=409, detail="승인할 회사·조직 문맥을 먼저 선택하십시오.")
    try:
        data = await asyncio.to_thread(
            planning_driver_release.approve, driver_code, p.user_id, req.rationale,
            tenant_id=tenant_id, scope_node_id=scope_node_id, entity_mode=entity_mode,
            store=planning_store)
        return {"status": "success", "data": data}
    except PlanningError as exc:
        _err(exc)


@router.post("/drivers/{driver_code}/revoke")
async def revoke_driver(driver_code: str, req: ScenarioDecisionRequest,
                        p: Principal = Depends(current_principal)):
    _assert_identified(p, "경영 동인 승인 철회")
    from api.deps import assert_can_manage_standard
    from core import planning_driver_release
    assert_can_manage_standard(p)
    try:
        current = await asyncio.to_thread(
            planning_driver_release.effective_release, driver_code, store=planning_store)
        if not current:
            raise PlanningError("철회할 승인 동인 판본이 없습니다.")
        await _scope(
            p, str(current.get("scope_node_id") or ""), driver_code,
            str(current.get("tenant_id") or ""), str(current.get("entity_mode") or ""))
        data = await asyncio.to_thread(
            planning_driver_release.revoke, driver_code, p.user_id, req.rationale,
            store=planning_store)
        return {"status": "success", "data": data}
    except PlanningError as exc:
        _err(exc)


@router.get("/drivers/{driver_code}/preview")
async def preview_driver(driver_code: str, pct_change: float,
                         p: Principal = Depends(current_principal)):
    """동인 가정을 계정 단위로 **펼쳐서 미리 본다** — 시나리오에 넣기 전에 파급을 확인한다.

    `warnings` 가 비어 있지 않으면 매핑이 없거나 미승인 계수가 섞여 있다는 뜻이다.
    ⚠️ 계정별 파급을 펼쳐 보여주므로 계정 체계와 탄성치가 함께 드러난다 — 식별을 요구한다."""
    _assert_identified(p, "동인 파급 미리보기")
    rows, warns = await asyncio.to_thread(drivers.expand_driver_assumption,
                                          driver_code, pct_change)
    return {"status": "success", "data": {"expanded": rows, "warnings": warns}}


@router.get("/cash-flow")
async def cash_flow(org_id: str, period: str, value_kind: str = PLAN,
                    p: Principal = Depends(current_principal)):
    """현금흐름(간접법, §17.2 기능 6).

    ⚠️ `computable=false` 면 **계산하지 않은 것**이다(0 이 아니다). `missing` 에 무엇이
      없는지 이름이 있다. 감가상각·운전자본·CAPEX 를 0 으로 채우면 '영업현금흐름 = 순이익'이
      되어 현금이 충분한 것처럼 보인다 — 화면은 이 구분을 반드시 표시할 것."""
    _assert_identified(p, "현금흐름")
    await _scope(p, org_id, org_id)
    data = await asyncio.to_thread(engine.cash_flow_for, org_id, period, value_kind)
    return {"status": "success", "data": data}


# ── 실적·계획 파일 등록 (§17.2 기능 2) ────────────────────────────────
# ⚠️ 파일 등록은 **조용히 틀리기 가장 쉬운 경로**다. 엑셀 오타 하나가 그대로 경영 보고서에
#   들어가고 아무 오류도 나지 않는다. 그래서 먼저 검증하고 나중에 저장하며,
#   한 행이라도 문제가 있으면 **전부 거부**한다(부분 저장 금지).
from fastapi import File, UploadFile

from core import planning_import as importer


class ImportRowsRequest(BaseModel):
    rows: List[dict]
    #: 기본 False — 무엇이 들어갈지 먼저 보여준다.
    commit: bool = False
    source_ref: Optional[str] = ""


@router.post("/import/rows")
async def import_rows(req: ImportRowsRequest, p: Principal = Depends(current_principal)):
    """행 목록 등록. `commit=false`(기본)면 **검증만** 하고 저장하지 않는다."""
    _assert_identified(p, "실적·계획 등록")
    await _assert_rows_in_scope(p, req.rows)
    try:
        data = await asyncio.to_thread(importer.import_rows, req.rows, req.commit,
                                       req.source_ref or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...), commit: bool = False,
                     p: Principal = Depends(current_principal)):
    """CSV 등록. 인코딩은 UTF-8(BOM 허용) → CP949 순으로 시도한다(국내 엑셀 관례)."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    _assert_identified(p, "실적·계획 등록")
    try:
        rows = await asyncio.to_thread(importer.parse_csv, text)
    except PlanningError as e:
        _err(e)
    # ⚠️ 파싱 **후** 범위를 검증한다 — 파일 안의 조직을 알아야 판정할 수 있다. 검증을 저장
    #   뒤로 미루면 그 사이에 남의 조직 실적이 들어간다.
    await _assert_rows_in_scope(p, rows)
    try:
        data = await asyncio.to_thread(importer.import_rows, rows, commit, file.filename or "")
        return {"status": "success", "data": data}
    except PlanningError as e:
        _err(e)


@router.get("/import/template")
async def import_template(p: Principal = Depends(current_principal)):
    """등록 양식 안내 — 열 이름을 추측하게 두면 조용히 틀린 열을 읽는다.

    ⚠️ 예시에 실제 조직 코드(`MNM_BATTERY`)가 들어 있다. 양식 자체는 비밀이 아니지만 조직
      코드를 익명에게 알려 줄 이유가 없다 — 다른 라우트의 404 은폐를 우회하는 단서가 된다."""
    _assert_identified(p, "등록 양식")
    return {"status": "success", "data": {
        "required_columns": list(importer.REQUIRED_COLUMNS),
        "optional_columns": list(importer.OPTIONAL_COLUMNS),
        "value_kinds": list(VALUE_KINDS),
        "example_csv": ("org_id,account_code,period,value_kind,amount,source_ref\n"
                        "MNM_BATTERY,4000,2026,ACTUAL,\"1,100\",2026결산.xlsx\n"),
        "notes": [
            "한 행이라도 문제가 있으면 아무것도 저장하지 않습니다(부분 저장 없음).",
            "계정은 먼저 등록해야 합니다 — 자동 생성하면 오타가 새 계정이 됩니다.",
            "value_kind 는 비울 수 없습니다(실제·계획·예측·시나리오를 섞지 않습니다).",
            "천단위 구분(1,000)과 회계 음수 표기((600))를 지원합니다.",
        ],
    }}


# ── Backtest (§17.3 파일럿 성공 기준 "과거 기간 재현") ────────────────
# ⚠️ Backtest 의 고전적 실패는 **결과를 알고 나서 만든 가정으로 과거를 맞히는 것**이다.
#   오차가 0 에 가깝게 나오고 사람들은 모델을 신뢰하게 된다 — 실제 미래엔 빗나간다.
#   그래서 응답의 `lookahead_risk` 와 `warnings` 를 화면이 반드시 함께 보여줘야 한다.
from core import planning_backtest as backtest


class BacktestSeriesRequest(BaseModel):
    org_id: str
    periods: List[str]


@router.get("/backtest/plan")
async def backtest_plan(org_id: str, period: str, p: Principal = Depends(current_principal)):
    """계획 vs 실적 오차. `measurable=false` 면 **재지 않은 것**이다(오차 0 이 아니다)."""
    _assert_identified(p, "계획 백테스트")
    await _scope(p, org_id, org_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_plan, org_id, period)}


@router.get("/backtest/scenario")
async def backtest_scenario(scenario_id: str, org_id: str, period: str,
                            baseline_kind: str = PLAN,
                            p: Principal = Depends(current_principal)):
    """시나리오를 과거 기간에 돌려 실적과 비교한다.

    `lookahead_risk=true` 면 가정이 대상 기간 이후에 작성된 것이다 —
    그 오차는 **실제 예측력이 아니다.**"""
    _assert_identified(p, "시나리오 백테스트")
    await _scope(p, org_id, scenario_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_scenario, scenario_id,
                                            org_id, period, baseline_kind)}


@router.post("/backtest/series")
async def backtest_series(req: BacktestSeriesRequest,
                          p: Principal = Depends(current_principal)):
    """여러 기간 연속 검증 — **한 해만 맞힌 것은 우연일 수 있다.**

    `systematic_bias=true` 면 편향이 여러 기간에 걸쳐 같은 방향이라는 뜻이고,
    그것은 우연이 아니라 모델의 습관이다(MAPE 가 작아도 그대로 쓰면 안 된다)."""
    _assert_identified(p, "백테스트 시계열")
    await _scope(p, req.org_id, req.org_id)
    return {"status": "success",
            "data": await asyncio.to_thread(backtest.backtest_series, req.org_id, req.periods)}


@router.get("/rollup-check")
async def rollup_check(org_id: str, period: str, value_kind: str = PLAN,
                       p: Principal = Depends(current_principal)):
    """★ 합계 행과 상세 행이 섞였는지 점검한다(제품·원가센터 차원의 필연적 함정).

    둘이 함께 있으면 단순 합산 시 **이중 계상**이다. 어느 쪽이 정본인지는 데이터를 넣은
    사람만 알기 때문에 자동으로 고르지 않고 **표시만** 한다."""
    _assert_identified(p, "합산 검증")
    await _scope(p, org_id, org_id)
    facts = await asyncio.to_thread(planning_store.list_facts, org_id, period, value_kind)
    return {"status": "success", "data": await asyncio.to_thread(engine.rollup_conflicts, facts)}


@router.get("/drivers/{driver_code}/external")
async def driver_external_value(driver_code: str, purpose: str = "scenario",
                                baseline_value: Optional[float] = None,
                                as_of: str = "", vintage: str = "",
                                p: Principal = Depends(current_principal)):
    """연결된 외부 지표의 **실제 관측값**으로 동인 변화율을 산출한다(§12.7·§12.8).

    ⚠️ 등급 정책(§12.2)은 외부 인텔리전스가 강제한다 — 여기서 다시 판정하지 않고 **물고 온다.**
      `usable=false` 면 값을 쓸 수 없다는 뜻이고, **0% 로 대체하지 않는다**
      (0% 는 '변화 없음'이라는 주장이고 '모른다'와 다르다).
    `vintage` 를 주면 그 시점 발표값으로 계산한다 — 과거 계획의 재현 경로다.
    ⚠️ 등급 판정은 외부 인텔리전스가 하지만 **식별은 여기서 요구한다** — 익명에게는 등급을
      매길 주체가 없어 «누구 자격으로 물고 왔는가» 에 답할 수 없다."""
    _assert_identified(p, "외부 지표 값")
    data = await asyncio.to_thread(drivers.resolve_external_change, driver_code,
                                   purpose, baseline_value, as_of, vintage)
    return {"status": "success", "data": data}
