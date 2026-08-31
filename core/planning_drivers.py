"""[M4] 계획 동인(Driver)과 영향 매핑 (§11.2 계획 동인 · §11.4 가치사슬 · §17.2 기능 5).

## 왜 계정에 직접 가정을 넣는 것으로는 부족한가

실제 경영계획은 "매출 계정을 10% 올린다"로 세우지 않는다. **"판매량이 10% 늘면"** 으로 세우고,
그것이 매출·원가·물류비에 각각 다른 비율로 파급된다. 계정에 직접 넣으면 그 파급 관계가
사람 머릿속에만 남고, 다음 사람은 왜 그 숫자인지 알 수 없다.

동인을 1급으로 두면 가정이 **업무 언어**가 된다 — "판매량 +10%, 환율 1,300→1,400" 은
경영진이 읽을 수 있지만 "4000 계정 pct +10" 은 읽을 수 없다.

## 파급 계수는 **사람이 등록하고 승인한다**

> `판매량 +10% → 매출 +10%` 는 자명해 보이지만 `환율 +10% → 원가 +6%` 는 자명하지 않다.

이 계수를 LLM 이나 자동 회귀로 만들면 **그럴듯한 가짜 인과**가 생긴다. 그리고 그것은 경영
보고서에 "환율 때문에 원가가 이만큼 오릅니다"라고 인쇄된다. 그래서:

- 영향 매핑은 **명시적 등록만** 허용한다(추론 금지).
- `rationale`(근거)과 `source`(출처)가 **필수**다. 근거 없는 계수는 창작이다.
- 매핑이 없는 동인은 **조용히 무시되지 않고** 미적용으로 보고된다.

## 외부 지표와의 연결

환율·금리·원자재 지수 같은 동인은 §12 외부 인텔리전스의 지표와 연결될 수 있다(`external_code`).
다만 **연결은 표시일 뿐 자동 주입이 아니다** — Gold 등급 관측값만 기준계획에 쓸 수 있다는
§12.2 정책은 그쪽에서 강제되고, 여기서는 "어느 지표를 보는 동인인가"만 기록한다.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.planning_model import PlanningError, planning_store

_DDL = """
-- 계획 동인 (§11.2). 업무 언어로 된 가정의 단위.
CREATE TABLE IF NOT EXISTS plan_drivers (
    driver_code   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    unit          TEXT DEFAULT '',
    category      TEXT DEFAULT '',      -- volume | price | cost | fx | labor | energy
    -- §12 외부 지표 연결(표시용). 연결이 곧 자동 주입은 아니다.
    external_code TEXT DEFAULT '',
    note          TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);

-- 동인 → 계정 파급 계수. **사람이 등록하고 근거를 남긴다.**
CREATE TABLE IF NOT EXISTS driver_impacts (
    impact_id    TEXT PRIMARY KEY,
    driver_code  TEXT NOT NULL,
    account_code TEXT NOT NULL,
    -- 동인이 1% 변할 때 계정이 몇 % 변하는가(탄력도).
    elasticity   REAL NOT NULL,
    rationale    TEXT NOT NULL,          -- ★ 필수 — 근거 없는 계수는 창작이다
    source       TEXT NOT NULL,          -- ★ 필수 — 어디서 온 숫자인가(실적회귀·업계자료·전문가판단)
    approved_by  TEXT DEFAULT '',
    approved_at  TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_impact_driver ON driver_impacts(driver_code);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_schema():
    conn = planning_store._connect()
    try:
        conn.executescript(_DDL)
        conn.commit()
    finally:
        conn.close()


def register_driver(driver_code: str, name: str, unit: str = "", category: str = "",
                    external_code: str = "", note: str = "") -> Dict[str, Any]:
    _ensure_schema()
    if not (driver_code or "").strip() or not (name or "").strip():
        raise PlanningError("driver_code 와 name 은 필수입니다.")
    conn = planning_store._connect()
    try:
        conn.execute(
            "INSERT INTO plan_drivers(driver_code,name,unit,category,external_code,note,created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(driver_code) DO UPDATE SET "
            "name=excluded.name, unit=excluded.unit, category=excluded.category, "
            "external_code=excluded.external_code, note=excluded.note",
            (driver_code, name, unit or "", category or "", external_code or "", note or "", _now()))
        conn.commit()
        return dict(conn.execute("SELECT * FROM plan_drivers WHERE driver_code=?",
                                 (driver_code,)).fetchone())
    finally:
        conn.close()


def add_impact(driver_code: str, account_code: str, elasticity: float,
               rationale: str, source: str, approved_by: str = "") -> Dict[str, Any]:
    """동인 → 계정 파급 계수를 등록한다.

    ⚠️ `rationale`·`source` 가 필수인 이유: 이 계수는 경영 보고서에 "환율 때문에 원가가
      이만큼 오릅니다"로 인쇄된다. 근거를 못 대는 숫자를 그렇게 쓰면 안 된다."""
    _ensure_schema()
    if not (rationale or "").strip():
        raise PlanningError("rationale(근거)은 필수입니다 — 근거 없는 파급 계수는 창작입니다.")
    if not (source or "").strip():
        raise PlanningError("source(출처)는 필수입니다 — 실적회귀·업계자료·전문가판단 중 "
                            "무엇에서 나온 숫자인지 밝히십시오.")
    conn = planning_store._connect()
    try:
        if not conn.execute("SELECT 1 FROM plan_drivers WHERE driver_code=?",
                            (driver_code,)).fetchone():
            raise PlanningError(f"등록되지 않은 동인입니다: {driver_code}")
        iid = uuid.uuid4().hex[:16]
        conn.execute(
            "INSERT INTO driver_impacts(impact_id,driver_code,account_code,elasticity,"
            "rationale,source,approved_by,approved_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (iid, driver_code, account_code, float(elasticity), rationale, source,
             approved_by or "", _now() if approved_by else "", _now()))
        conn.commit()
        return dict(conn.execute("SELECT * FROM driver_impacts WHERE impact_id=?",
                                 (iid,)).fetchone())
    finally:
        conn.close()


def list_drivers() -> List[Dict[str, Any]]:
    _ensure_schema()
    conn = planning_store._connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM plan_drivers ORDER BY driver_code")]
    finally:
        conn.close()


def impacts_of(driver_code: str) -> List[Dict[str, Any]]:
    _ensure_schema()
    conn = planning_store._connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM driver_impacts WHERE driver_code=? ORDER BY account_code",
            (driver_code,))]
    finally:
        conn.close()


def expand_driver_assumption(driver_code: str, pct_change: float) -> Tuple[List[Dict[str, Any]], List[str]]:
    """동인 가정을 **계정 단위 가정으로 펼친다**.

    반환: (계정 가정 목록, 경고 목록)

    ⚠️ 매핑이 없으면 **조용히 무시하지 않는다.** "판매량 10% 올렸는데 아무것도 안 변했다"는
      상황에서 사용자가 알 수 있는 것은 이 경고뿐이다."""
    _ensure_schema()
    impacts = impacts_of(driver_code)
    if not impacts:
        return [], [f"동인 '{driver_code}' 에 등록된 파급 계수가 없습니다 — "
                    f"이 가정은 어떤 계정에도 적용되지 않습니다."]

    out, warns = [], []
    for im in impacts:
        if not im.get("approved_by"):
            # 미승인 계수를 막지는 않는다(초기 도입이 멈춘다). 대신 결과에 표시한다.
            warns.append(f"{driver_code}→{im['account_code']} 계수가 미승인 상태입니다"
                         f"(탄력도 {im['elasticity']}, 출처 {im['source']}).")
        out.append({
            "target_kind": "account",
            "target_code": im["account_code"],
            "operator": "pct",
            "value": pct_change * float(im["elasticity"]),
            "rationale": f"[{driver_code} {pct_change:+g}% × 탄력도 {im['elasticity']}] "
                         f"{im['rationale']}",
            "derived_from_driver": driver_code,
            "elasticity_source": im["source"],
            "approved": bool(im.get("approved_by")),
        })
    return out, warns


def expand_assumptions(assumptions: List[Dict[str, Any]], *, tenant_id: str = "",
                       scope_node_id: str = "", entity_mode: str = "REAL",
                       as_of: str = "") -> Tuple[List[Dict[str, Any]], List[str]]:
    """실행용 확장. 동인 가정은 유효한 승인 판본의 파급계수만 사용한다.

    초안 미리보기는 ``expand_driver_assumption`` 이 담당한다. 두 함수를 섞으면 미승인
    초안이 실제 숫자로 흘러가므로, 실행 경로는 조직 범위까지 봉인된 판본을 요구한다."""
    expanded: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for a in assumptions:
        if (a.get("target_kind") or "account") != "driver":
            expanded.append(a)
            continue
        if (a.get("operator") or "").lower() != "pct":
            warnings.append(f"동인 가정은 pct 만 지원합니다(받은 값: {a.get('operator')}) — "
                            f"'{a.get('target_code')}' 는 적용되지 않았습니다.")
            continue
        if not all(str(value or "").strip() for value in
                   (tenant_id, scope_node_id, entity_mode)):
            raise PlanningError("동인 계산에는 tenant·조직 범위·실행 문맥이 필요합니다.")
        from core import planning_driver_release
        code = str(a.get("target_code") or "")
        approved = planning_driver_release.effective_release(code, as_of=as_of)
        if not approved:
            raise PlanningError(f"승인된 동인 판본이 없습니다: {code}")
        binding = (str(approved.get("tenant_id") or ""),
                   str(approved.get("scope_node_id") or ""),
                   str(approved.get("entity_mode") or ""))
        if binding != (str(tenant_id), str(scope_node_id), str(entity_mode)):
            raise PlanningError(f"동인 승인 판본의 조직 범위가 시나리오와 다릅니다: {code}")
        try:
            impacts = __import__("json").loads(str(approved.get("impacts_json") or "[]"))
        except (TypeError, ValueError) as exc:
            raise PlanningError(f"승인 동인 판본의 파급계수를 읽지 못했습니다: {code}") from exc
        for impact in impacts:
            elasticity = float(impact["elasticity"])
            expanded.append({
                "target_kind": "account", "target_code": impact["account_code"],
                "operator": "pct", "value": float(a.get("value") or 0) * elasticity,
                "rationale": (f"[{code} {float(a.get('value') or 0):+g}% × 탄력도 {elasticity}] "
                              f"{impact['rationale']}"),
                "derived_from_driver": code, "elasticity_source": impact["source"],
                "approved": True, "driver_release_fingerprint": approved["fingerprint"],
            })
    return expanded, warnings


# ══════════════════════════════════════════════════════════════════════
# 외부 지표 → 동인 실연결 (§12.7 내부 KPI 영향 매핑 · §12.8 시나리오 연결)
# ══════════════════════════════════════════════════════════════════════
def resolve_external_change(driver_code: str, purpose: str = "scenario",
                            baseline_value: Optional[float] = None,
                            as_of: str = "", vintage: str = "") -> Dict[str, Any]:
    """연결된 외부 지표의 **실제 관측값**으로 동인의 변화율을 산출한다.

    ## 왜 "연결"만으로는 부족했나

    지금까지 `external_code` 는 **표시**일 뿐이었다. "이 동인은 환율을 본다"고 적혀 있어도
    실제 환율 값은 흐르지 않아, 사용자가 손으로 "+7.7%"를 계산해 넣어야 했다.
    그러면 그 7.7% 가 **어느 시점 어느 등급의 값에서 나왔는지** 아무도 모른다.

    ## 등급 정책은 여기서 다시 판정하지 않는다

    §12.2 의 등급 게이트(`baseline_plan` 은 Gold 필수 등)는 `external_intelligence.
    resolve_value()` 가 강제한다. 여기서 다시 구현하면 두 곳이 어긋나고, 한쪽만 고쳐졌을 때
    **정책이 조용히 뚫린다.** 이 함수는 그 판정을 **그대로 물고 온다**.

    ⚠️ 값을 못 쓰는 경우 `usable=False` 와 사유·다음 조치를 돌려준다. 0% 로 대체하지 않는다 —
      0% 는 "변화 없음"이라는 **적극적 주장**이고, "모른다"와 완전히 다르다.
    """
    _ensure_schema()
    conn = planning_store._connect()
    try:
        row = conn.execute("SELECT * FROM plan_drivers WHERE driver_code=?",
                           (driver_code,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"usable": False, "driver_code": driver_code,
                "reason": f"등록되지 않은 동인입니다: {driver_code}"}
    d = dict(row)
    code = (d.get("external_code") or "").strip()
    if not code:
        return {"usable": False, "driver_code": driver_code, "external_code": "",
                "reason": "이 동인에는 외부 지표가 연결돼 있지 않습니다.",
                "next_action": "`external_code` 를 지정하거나 변화율을 직접 입력하십시오."}

    try:
        from core.external_intelligence import external_intelligence as ext
        res = ext.resolve_value(code, purpose=purpose, as_of=as_of, vintage=vintage)
    except Exception as e:
        return {"usable": False, "driver_code": driver_code, "external_code": code,
                "reason": f"외부 지표 조회에 실패했습니다: {e}"}

    if not res.get("allowed"):
        # ★ 등급 미달·관측값 없음 — **0% 로 대체하지 않는다.**
        return {"usable": False, "driver_code": driver_code, "external_code": code,
                "purpose": purpose, "reason": res.get("reason", "값을 사용할 수 없습니다."),
                "required_grade": res.get("required_grade"),
                "available_grade": res.get("available_grade"),
                "next_action": res.get("next_action", ""),
                "note": ("0% 로 대체하지 않았습니다 — 0% 는 '변화 없음'이라는 주장이고 "
                         "'모른다'와 다릅니다.")}

    observed = float(res["value"])
    out = {
        "usable": True, "driver_code": driver_code, "external_code": code,
        "purpose": purpose,
        "observed_value": observed, "unit": res.get("unit") or d.get("unit") or "",
        "grade": res.get("grade"), "observed_at": res.get("observed_at"),
        "vintage": res.get("vintage"), "source_id": res.get("source_id"),
        # 재현성: 어느 시점 발표값(vintage)으로 계산했는지가 결과에 남아야 한다.
        "note": res.get("note", ""),
    }
    if baseline_value is None:
        out["pct_change"] = None
        out["reason"] = ("기준값(baseline_value)이 없어 변화율을 계산하지 않았습니다 — "
                         "관측값만으로는 '무엇 대비 몇 %'인지 알 수 없습니다.")
        return out
    if baseline_value == 0:
        out["pct_change"] = None
        out["reason"] = "기준값이 0 이라 변화율을 계산할 수 없습니다."
        return out
    out["baseline_value"] = float(baseline_value)
    out["pct_change"] = round((observed - baseline_value) / abs(baseline_value) * 100.0, 4)
    return out
