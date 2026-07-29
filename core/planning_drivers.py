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


def expand_assumptions(assumptions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """시나리오 가정 목록에서 **동인 가정을 계정 가정으로 펼친다**(계정 가정은 그대로 통과).

    이 함수 하나를 엔진이 호출하면 동인·계정 두 형태가 한 경로로 합류한다 —
    두 경로를 따로 두면 한쪽에만 적용되는 규칙이 생긴다."""
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
        rows, warns = expand_driver_assumption(a.get("target_code"), float(a.get("value") or 0))
        expanded.extend(rows)
        warnings.extend(warns)
    return expanded, warnings
