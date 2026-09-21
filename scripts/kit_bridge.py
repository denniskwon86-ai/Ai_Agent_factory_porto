#!/usr/bin/env python3
"""키트 → 플랫폼 이음매 — **키트가 아는 것을 플랫폼 언어로 옮긴다.**

명세: `docs/data-kits/KIT_PLATFORM_BRIDGE_SPEC_2026-09-16.md`
설계(왜 이렇게 하는가): `docs/data-kits/KIT_PLATFORM_BRIDGE_DESIGN_2026-09-16.md`

## 이 모듈이 하지 않는 것

| | 왜 |
|---|---|
| **파급 계수(`driver_impacts`)를 만들지 않는다** | 계수는 **현업이 근거·출처와 함께** 등록한다. 키트가 만들면 창작이 된다 |
| 시나리오를 옮기지 않는다 | 계수가 쌓인 뒤에만 뜻이 있다 (명세 3.3) |
| `seed_starter_data.py` 에 연결하지 않는다 | 「누가 구현하나」가 아직 정해지지 않았고(명세 6 장), 빈 설치본 결함 확인이 선행이다 |

★ 그래서 이 모듈은 **순수하게 옮기기만 한다.** 쓰는 쪽은 나중에 붙인다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


class BridgeError(Exception):
    """이음매가 옮길 수 없을 때. **조용히 버리지 않는다.**"""


class UnsupportedScenarioUnit(BridgeError):
    """비율이 아닌 시나리오 — 동인 경로가 받지 못한다."""


class NeedsBaseline(BridgeError):
    """`%p` 를 비율로 바꾸려면 **현재 값**이 있어야 한다. 그것은 회사 데이터다."""


# ── 1. 동인 대응표 ────────────────────────────────────────────────────────
#
# ★ **이것이 「산업 최대한 반영」의 실체다.** `input_metric` 을 그대로 넣으면
#   `AR_AP_TIMING` 같은 기계 이름이 화면에 뜨고, 플랫폼이 동인을 1 급으로 둔 이유
#   (**가정이 업무 언어가 된다**)가 깨진다. 그래서 사람이 한 번 적는다.
#
# `unit` 과 `external_code` 는 키트의 `EXT-01~03` 에서 **실측한 값**이다.
#
# ⚠️ `category` 의 `schedule` 은 **플랫폼 범주 밖이다**(`volume|price|cost|fx|
#   labor|energy`). 「일수」가 어디에도 없어 새로 썼다 — 컬럼이 자유 텍스트라 들어는
#   가지만, **범주를 우리가 늘리는 것이 맞는지는 플랫폼 쪽과 맞춰야 한다**(명세 6 장).

_DRIVER_MAP: Dict[str, Dict[str, str]] = {
    "DRV-FX":        {"name": "환율 (USD/KRW)",      "unit": "KRW/USD",  "category": "fx",       "external_code": "USD_KRW"},
    "DRV-COMMODITY": {"name": "원자재 기준가격",       "unit": "USD/TON",  "category": "price",    "external_code": "COPPER"},
    "DRV-FREIGHT":   {"name": "해상 운임",            "unit": "USD/TON",  "category": "cost",     "external_code": "SEA_FREIGHT"},
    "DRV-POWER":     {"name": "산업용 전력 단가",      "unit": "KRW/KWH",  "category": "energy",   "external_code": "INDUSTRIAL_POWER"},
    #: ⚠️ 외부 지표는 `INDEX` 인데 동인은 `%` 다. 「지수가 변하는 비율」이라 연결은
    #:   맞지만 **단위가 같지 않다** — 자동 주입을 붙일 때 다시 봐야 한다
    "DRV-DEMAND":    {"name": "수요 변화율",          "unit": "%",        "category": "volume",   "external_code": "MFG_DEMAND_INDEX"},
    "DRV-SUPPLY":    {"name": "공급 감소율",          "unit": "%",        "category": "volume",   "external_code": ""},
    "DRV-YIELD":     {"name": "생산 수율",            "unit": "%",        "category": "volume",   "external_code": ""},
    "DRV-DOWNTIME":  {"name": "설비 정지 시간",        "unit": "HOUR",     "category": "volume",   "external_code": ""},
    "DRV-DELAY":     {"name": "도착 지연 일수",        "unit": "DAY",      "category": "schedule", "external_code": ""},
    "DRV-CASH":      {"name": "대금 회수·지급 시점",   "unit": "DAY",      "category": "schedule", "external_code": ""},
    "DRV-CAPEX":     {"name": "설비투자액",           "unit": "KRW",      "category": "cost",     "external_code": ""},
}

#: ★ `DRV-GM` 은 **동인이 아니라 계산식이다.**
#:
#:   `input=REVENUE_AND_COST · output=GROSS_MARGIN · formula=REVENUE-COGS`
#:
#:   「매출과 원가가 1% 변하면 매출총이익이 몇 % 변하는가」는 물음이 성립하지 않는다 —
#:   매출이 오르면 오르고 원가가 오르면 내린다. **하나의 탄력도로 답할 수 없다.**
#:   게다가 플랫폼은 이미 이것을 계산한다(`plan_accounts.category`·`sign`). 동인으로
#:   넣으면 **같은 것을 두 번 세고**, 현업은 의미 없는 계수를 등록하라는 요구를 받는다.
EXCLUDED_DRIVERS = {"DRV-GM": "동인이 아니라 계산식이다 — 플랫폼이 계정 부호로 이미 계산한다"}


def driver_map() -> Dict[str, Dict[str, str]]:
    """대응표 사본. **시험이 이것과 등록 결과를 대조한다** — 새 동인을 넣으면
    시험이 먼저 깨지고, 그것이 의도다(명세 4.1)."""
    return {k: dict(v) for k, v in _DRIVER_MAP.items()}


# ── 2. 단위 환산 ──────────────────────────────────────────────────────────

def to_pct_change(change_value: Any, change_unit: str) -> float:
    """키트 시나리오의 변화량을 플랫폼의 `pct_change` 로 옮긴다.

    ⚠️ 키트는 **비율**로 적고(`0.1` = 10%), 플랫폼은 **퍼센트 수**를 받는다(`10`).
      그대로 넘기면 오류 없이 **100 배 작게** 계산되고, 「환율이 10% 올랐는데 원가가
      0.06%」를 이상하다고 느끼지 못하면 그대로 경영 보고서로 간다.
    """
    v = float(change_value)
    u = (change_unit or "").strip().upper()
    if u in ("%", "PCT", "PERCENT"):
        return v * 100.0
    if u == "PERCENT_POINT":
        #: %p 는 % 가 아니다 — 수율 92%→90% 는 −2%p 이고 **−2.17%** 다.
        #: 기준값은 **회사 데이터**라 여기서 만들 수 없다.
        raise NeedsBaseline(
            f"%p 시나리오는 기준값이 있어야 옮길 수 있습니다: {change_value}{change_unit}. "
            f"현업이 현재 값을 넣은 뒤 to_pct_change_from_baseline() 을 쓰십시오.")
    raise UnsupportedScenarioUnit(
        f"퍼센트가 아닌 시나리오는 옮길 수 없습니다: {change_value} {change_unit}. "
        f"동인 경로(expand_driver_assumption)는 비율 변화만 받습니다 — "
        f"절대량은 플랫폼 검토 건입니다.")


def to_pct_change_from_baseline(change_value: Any, change_unit: str,
                                baseline: float) -> float:
    """`%p` 를 기준값으로 비율 변화로 바꾼다. **기준값은 현업이 준다.**"""
    if (change_unit or "").strip().upper() != "PERCENT_POINT":
        return to_pct_change(change_value, change_unit)
    if not baseline:
        raise NeedsBaseline("기준값이 0 이거나 없습니다 — %p 를 비율로 바꿀 수 없습니다.")
    return float(change_value) / float(baseline) * 100.0


# ── 3. 동인 심기 ──────────────────────────────────────────────────────────

def _note_for(row: Mapping[str, Any]) -> str:
    """키트가 아는 것을 담는다 — **계수는 담지 않는다.**"""
    out = str(row.get("output_metric") or "").strip()
    formula = str(row.get("formula_definition") or "").strip()
    lag = str(row.get("lag_period_months") or "").strip()
    note = f"{out} 에 파급된다."
    if formula:
        note += f" 계산식 {formula}"
    if lag and lag not in ("0", "0.0", ""):
        note += f" (지연 {lag}개월)"
    return note


def seed_plan_drivers(rows: Sequence[Mapping[str, Any]],
                      drivers: Any = None) -> Dict[str, List[Any]]:
    """`SIM-01` → `plan_drivers`. **파급 계수는 만들지 않는다.**

    | 반환 | 무엇 |
    |---|---|
    | `loaded` | 새로 심은 `driver_code` |
    | `skipped_existing` | 이미 있어 **건드리지 않은** 것 |
    | `excluded` | 대응표에 없어 **일부러 뺀** `(code, 이유)` |

    ⚠️ 셋을 갈라 돌려준다. 하나로 뭉치면 「없다」와 「뺐다」와 「이미 있다」가 같은
      모양이 되고, 부른 쪽은 무엇을 확인해야 할지 모른다.
    """
    if drivers is None:
        from core import planning_drivers as drivers  # noqa: N813

    existing = {str(d.get("driver_code")) for d in drivers.list_drivers()}
    out: Dict[str, List[Any]] = {"loaded": [], "skipped_existing": [], "excluded": []}
    seen = set()
    for row in rows:
        code = str(row.get("driver_id") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        if code in EXCLUDED_DRIVERS:
            out["excluded"].append((code, EXCLUDED_DRIVERS[code]))
            continue
        spec = _DRIVER_MAP.get(code)
        if spec is None:
            #: 대응표에 없다 = **업무 이름을 아직 사람이 안 적었다.** 기계 이름으로
            #: 채우지 않는다 — 그러면 화면에 `AR_AP_TIMING` 이 뜬다
            out["excluded"].append((code, "대응표에 업무 이름이 없다 — 사람이 적어야 한다"))
            continue
        if code in existing:
            #: ⚠️ 덮지 않는다. 현업이 고쳐 놓았을 수 있고, 승인된 판본이 딸려 있을 수 있다
            out["skipped_existing"].append(code)
            continue
        drivers.register_driver(driver_code=code, name=spec["name"], unit=spec["unit"],
                                category=spec["category"],
                                external_code=spec["external_code"],
                                note=_note_for(row))
        out["loaded"].append(code)
    return out


# ── 4. 계정 심기 ──────────────────────────────────────────────────────────

#: 키트의 `pnl_line` → 플랫폼의 `plan_accounts.category`
_PNL_TO_CATEGORY = {"REVENUE": "REVENUE", "COGS": "COGS", "OPEX": "SGA"}


def seed_plan_accounts(rows: Sequence[Mapping[str, Any]],
                       store: Any = None) -> Dict[str, List[Any]]:
    """`MDM-07` → `plan_accounts`. **손익 계정만 옮긴다.**

    ⚠️ `BALANCE_SHEET`(현금·매출채권·재고자산·매입채무)는 **건너뛰고 반환값에 담는다.**
      버릴지 `WORKING_CAPITAL` 로 보낼지는 아직 정해지지 않았다(명세 6 장) — 그때까지
      **조용히 사라지게 두지 않는다.**
    """
    if store is None:
        from core.planning_model import planning_store as store

    out: Dict[str, List[Any]] = {"loaded": [], "skipped": [], "failed": []}
    seen = set()
    for row in rows:
        code = str(row.get("account_id") or "").strip()
        name = str(row.get("account_name") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        pnl = str(row.get("pnl_line") or "").strip().upper()
        category = _PNL_TO_CATEGORY.get(pnl)
        if category is None:
            out["skipped"].append((code, name, pnl))
            continue
        #: 부호는 계정 성격에서 — 수익은 +1, 그 외는 −1
        sign = 1 if str(row.get("account_type") or "").strip().upper() == "REVENUE" else -1
        try:
            store.upsert_account(account_code=code, name=name, category=category, sign=sign)
            out["loaded"].append(code)
        except Exception as e:                       # noqa: BLE001 — 무엇이 실패했는지 남긴다
            out["failed"].append((code, str(e)[:120]))
    return out


# ── 보고 ──────────────────────────────────────────────────────────────────

def summarize(drivers_result: Mapping[str, Any], accounts_result: Mapping[str, Any]) -> str:
    """사람이 읽는 한 줄들. **건너뛴 것이 보여야 한다**(명세 시험 8)."""
    lines = [
        f"동인  심음 {len(drivers_result.get('loaded') or [])} · "
        f"이미 있음 {len(drivers_result.get('skipped_existing') or [])} · "
        f"뺌 {len(drivers_result.get('excluded') or [])}",
        f"계정  심음 {len(accounts_result.get('loaded') or [])} · "
        f"건너뜀 {len(accounts_result.get('skipped') or [])} · "
        f"실패 {len(accounts_result.get('failed') or [])}",
    ]
    for code, why in (drivers_result.get("excluded") or []):
        lines.append(f"   뺌: {code} — {why}")
    for item in (accounts_result.get("skipped") or [])[:6]:
        lines.append(f"   건너뜀: {item[0]} {item[1]} ({item[2]})")
    for item in (accounts_result.get("failed") or []):
        lines.append(f"   ! 실패: {item[0]} — {item[1]}")
    return "\n".join(lines)
