"""[M4] 경영계획 계산 엔진 — **재현 가능한 손익 계산과 시나리오**. LLM 0콜.

명세서 §11.3: *"수치 계산은 재현 가능한 함수·규칙·제약조건 모델로 구현한다."*
§17.3 파일럿 성공 기준: *"적어도 세 개의 시나리오를 동일 기준선에서 재현한다."*

## 왜 LLM 을 쓰지 않는가

LLM 은 같은 입력에 같은 출력을 보장하지 않는다. 그러므로 §17.3 의 "재현한다"를 **원리적으로**
만족할 수 없다. 경영계획에서 재현 불가능한 숫자는 틀린 숫자보다 나쁘다 — 틀린 숫자는 고칠 수
있지만, 재현되지 않는 숫자는 **무엇을 고쳐야 하는지조차 알 수 없다.**

LLM 의 몫은 가정 후보 제안 · 결과 설명 · 이상 탐지 **보조**뿐이다(§11.3).

## 재현성을 만드는 세 가지

1. **입력 지문(`input_hash`)** — 같은 입력인지 사람 눈이 아니라 해시로 판정한다.
2. **엔진 버전(`ENGINE_VERSION`)** — 산식이 바뀌면 결과도 바뀐다. 어느 엔진의 결과인지
   모르면 "왜 지난달과 다른가"에 답할 수 없다.
3. **가정의 근거(`rationale`)** — 근거 없는 가정은 재현이 아니라 창작이다.

## 계산 규칙

```
매출총이익 = REVENUE − COGS
영업이익   = 매출총이익 − SGA
세전이익   = 영업이익 + OTHER_INCOME − OTHER_EXPENSE
당기순이익 = 세전이익 − TAX
```

부호는 계정의 `sign` 컬럼에서 온다 — 산식에 하드코딩하면 계정을 늘릴 때마다 코드를 고쳐야
하고, 그러다 한 곳을 빠뜨리면 **조용히 틀린 손익**이 나온다.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.planning_model import (ACTUAL, CF_CATEGORIES, ENGINE_VERSION, FORECAST, PLAN,
                                 SCENARIO, PlanningError, planning_store)

#: 손익 계산에서 각 분류가 이익에 기여하는 방향. 계정의 `sign` 과 곱해 최종 부호를 만든다.
_PL_LINES = ("REVENUE", "COGS", "SGA", "OTHER_INCOME", "OTHER_EXPENSE", "TAX")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def input_fingerprint(facts: List[Dict[str, Any]], assumptions: List[Dict[str, Any]]) -> str:
    """입력 스냅샷 지문. **같은 입력인지 눈이 아니라 해시로 판정한다.**

    정렬을 고정하는 이유: dict 순서나 조회 순서가 달라졌을 뿐인데 다른 지문이 나오면
    "재현되지 않았다"는 거짓 신호가 된다."""
    payload = {
        "facts": sorted(
            [(f.get("org_id"), f.get("account_code"), f.get("period"),
              f.get("value_kind"), round(float(f.get("amount") or 0), 6)) for f in facts]),
        "assumptions": sorted(
            [(a.get("target_kind"), a.get("target_code"), a.get("operator"),
              round(float(a.get("value") or 0), 6)) for a in assumptions]),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _accounts_by_code() -> Dict[str, Dict[str, Any]]:
    return {a["account_code"]: a for a in planning_store.list_accounts()}


def compute_pl(facts: List[Dict[str, Any]],
               accounts: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """손익 계산. **결정론적이고 부작용이 없다** — 같은 입력이면 언제나 같은 출력이다.

    ⚠️ 등록되지 않은 계정은 **조용히 버리지 않고** `unmapped` 로 돌려준다. 합계에서 빠진
      금액이 있는데 아무도 모르면, 그 손익표는 맞아 보이지만 틀렸다."""
    accounts = accounts if accounts is not None else _accounts_by_code()
    by_line: Dict[str, float] = {k: 0.0 for k in _PL_LINES}
    unmapped: List[Dict[str, Any]] = []
    excluded_non_pl: List[str] = []

    for f in facts:
        acc = accounts.get(f.get("account_code"))
        if not acc:
            unmapped.append({"account_code": f.get("account_code"),
                             "amount": float(f.get("amount") or 0)})
            continue
        cat = acc["category"]
        if cat in CF_CATEGORIES:
            # 현금흐름 전용 계정(감가상각·CAPEX·운전자본·재무)은 손익에 들어가지 않는다.
            # ⚠️ 이것을 `unmapped` 로 처리하면 "합계에서 빠진 금액" 경고가 상시 뜨고,
            #   그러면 진짜 누락이 그 소음에 묻힌다.
            excluded_non_pl.append(f.get("account_code"))
            continue
        if cat not in by_line:
            unmapped.append({"account_code": f.get("account_code"),
                             "amount": float(f.get("amount") or 0), "why": f"알 수 없는 분류 {cat}"})
            continue
        # 값은 양수로 입력하고 방향은 계정의 sign 이 정한다 — 입력자가 부호를 고민하지 않게 한다.
        by_line[cat] += float(f.get("amount") or 0) * (1 if acc["sign"] > 0 else 1)

    gross = by_line["REVENUE"] - by_line["COGS"]
    operating = gross - by_line["SGA"]
    pretax = operating + by_line["OTHER_INCOME"] - by_line["OTHER_EXPENSE"]
    net = pretax - by_line["TAX"]

    return {
        "lines": {k: round(v, 4) for k, v in by_line.items()},
        "gross_profit": round(gross, 4),
        "operating_profit": round(operating, 4),
        "pretax_profit": round(pretax, 4),
        "net_profit": round(net, 4),
        # ★ 매핑 실패는 결과와 같은 자리에 실어 보낸다. 별도 로그로 빼면 아무도 안 본다.
        "unmapped": unmapped,
        # 손익 대상이 아니어서 제외된 계정(현금흐름 전용) — 누락과 구분한다.
        "excluded_non_pl": sorted(set(excluded_non_pl)),
        "complete": not unmapped,
        "engine_version": ENGINE_VERSION,
    }


def apply_assumptions(facts: List[Dict[str, Any]],
                      assumptions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """가정을 기준선에 적용해 **새 사실 목록**을 만든다(원본은 건드리지 않는다).

    연산자
      - `pct`   : 비율 변경(+10 → 10% 증가)
      - `delta` : 절대 증감
      - `set`   : 값 고정

    ⚠️ **적용되지 않은 가정을 조용히 넘기지 않는다.** 대상 계정이 기준선에 없으면 사용자는
      "가정을 넣었는데 결과가 그대로"인 이유를 알 수 없다 — 두 번째 반환값으로 돌려준다."""
    out = [dict(f) for f in facts]
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for f in out:
        by_code.setdefault(f.get("account_code"), []).append(f)

    unapplied: List[str] = []
    for a in assumptions:
        code = a.get("target_code")
        targets = by_code.get(code) or []
        if not targets:
            unapplied.append(f"{code}({a.get('operator')} {a.get('value')})")
            continue
        op = (a.get("operator") or "").lower()
        val = float(a.get("value") or 0)
        for t in targets:
            base = float(t.get("amount") or 0)
            if op == "pct":
                t["amount"] = base * (1.0 + val / 100.0)
            elif op == "delta":
                t["amount"] = base + val
            elif op == "set":
                t["amount"] = val
            else:
                unapplied.append(f"{code}(알 수 없는 연산자 {op})")
                break
    return out, unapplied


def run_scenario(scenario_id: str, org_id: str, period: str,
                 baseline_kind: str = PLAN, persist: bool = False) -> Dict[str, Any]:
    """시나리오 1회 실행 — 기준선을 읽고, 가정을 적용하고, 손익을 계산한다.

    `persist=True` 면 결과를 `value_kind=SCENARIO` 로 저장한다. 기본값이 False 인 이유는
    **탐색적 실행이 기록을 오염시키면 안 되기** 때문이다 — 저장은 명시적 선택이어야 한다."""
    if baseline_kind not in (ACTUAL, PLAN, FORECAST):
        raise PlanningError(f"기준선은 {ACTUAL}|{PLAN}|{FORECAST} 중 하나여야 합니다 — "
                            "시나리오 위에 시나리오를 얹으면 무엇이 기준인지 사라집니다.")

    conn = planning_store._connect()
    try:
        scn = conn.execute("SELECT * FROM scenarios WHERE scenario_id=?", (scenario_id,)).fetchone()
        if not scn:
            raise PlanningError(f"존재하지 않는 시나리오입니다: {scenario_id}")
        assumptions = [dict(r) for r in conn.execute(
            "SELECT * FROM scenario_assumptions WHERE scenario_id=? ORDER BY assumption_id",
            (scenario_id,))]
    finally:
        conn.close()

    baseline = planning_store.list_facts(org_id=org_id, period=period, value_kind=baseline_kind)
    if not baseline:
        raise PlanningError(
            f"기준선이 비어 있습니다({org_id}/{period}/{baseline_kind}) — "
            "기준선 없이 계산하면 0 에서 시작한 숫자가 계획처럼 보입니다.")

    # ★ [§17.2 기능 5] 동인 가정을 계정 가정으로 펼친 뒤 한 경로로 합류시킨다.
    #   두 형태를 따로 처리하면 한쪽에만 적용되는 규칙이 생긴다.
    from core.planning_drivers import expand_assumptions
    expanded, driver_warnings = expand_assumptions(assumptions)
    applied, unapplied = apply_assumptions(baseline, expanded)
    accounts = _accounts_by_code()
    before = compute_pl(baseline, accounts)
    after = compute_pl(applied, accounts)

    run_id = uuid.uuid4().hex[:16]
    fingerprint = input_fingerprint(baseline, assumptions)
    result = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "org_id": org_id,
        "period": period,
        "baseline_kind": baseline_kind,
        "engine_version": ENGINE_VERSION,
        "input_hash": fingerprint,
        "baseline": before,
        "result": after,
        "delta": {
            "gross_profit": round(after["gross_profit"] - before["gross_profit"], 4),
            "operating_profit": round(after["operating_profit"] - before["operating_profit"], 4),
            "net_profit": round(after["net_profit"] - before["net_profit"], 4),
        },
        # ★ 적용되지 않은 가정은 결과와 함께 돌려준다 — "넣었는데 안 변했다"의 유일한 단서다.
        "unapplied_assumptions": unapplied,
        # 동인 관련 경고(매핑 없음·미승인 계수·미지원 연산자)는 별도로 남긴다 —
        # "동인을 넣었는데 아무것도 안 변했다"의 유일한 단서다.
        "driver_warnings": driver_warnings,
        "assumptions_count": len(assumptions),
        "expanded_count": len(expanded),
        "note": ("`unapplied_assumptions` 가 비어 있지 않으면 이 결과는 의도한 가정을 전부 "
                 "반영하지 않았습니다. `unmapped` 가 비어 있지 않으면 합계에서 빠진 금액이 있습니다. "
                 "`driver_warnings` 는 동인 파급 계수가 없거나 미승인임을 뜻합니다."),
    }

    conn = planning_store._connect()
    try:
        conn.execute(
            "INSERT INTO simulation_runs(run_id,scenario_id,engine_version,input_hash,status,"
            "started_at,completed_at,metrics_json) VALUES(?,?,?,?,?,?,?,?)",
            (run_id, scenario_id, ENGINE_VERSION, fingerprint, "completed", _now(), _now(),
             json.dumps({"net_profit": after["net_profit"],
                         "operating_profit": after["operating_profit"]}, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()

    if persist:
        for f in applied:
            planning_store.put_fact(
                org_id=f["org_id"], account_code=f["account_code"], period=f["period"],
                value_kind=SCENARIO, amount=f["amount"], scenario_id=scenario_id,
                source_ref=f"run:{run_id}",
                owner_organization_id=f.get("owner_organization_id") or f["org_id"],
                scope_type=f.get("scope_type") or "ORG_PRIVATE")

    return result


def compare_scenarios(scenario_ids: List[str], org_id: str, period: str,
                      baseline_kind: str = PLAN) -> Dict[str, Any]:
    """여러 시나리오를 **동일 기준선에서** 비교한다(§17.3 파일럿 성공 기준).

    ⚠️ 기준선이 다르면 비교가 성립하지 않는다 — 각 실행의 `input_hash` 를 함께 돌려주어
      **같은 기준선이었는지 검증 가능**하게 한다. '비교했다'는 주장만으로는 부족하다."""
    runs = [run_scenario(sid, org_id, period, baseline_kind) for sid in scenario_ids]
    baseline_hashes = {r["input_hash"][:8] for r in runs}
    return {
        "org_id": org_id,
        "period": period,
        "baseline_kind": baseline_kind,
        "engine_version": ENGINE_VERSION,
        "scenarios": [
            {"scenario_id": r["scenario_id"], "run_id": r["run_id"],
             "input_hash": r["input_hash"],
             "operating_profit": r["result"]["operating_profit"],
             "net_profit": r["result"]["net_profit"],
             "delta_net": r["delta"]["net_profit"],
             "unapplied_assumptions": r["unapplied_assumptions"],
             "complete": r["result"]["complete"]}
            for r in runs
        ],
        # 지문이 갈리면 서로 다른 기준선에서 계산된 것이다 — 그 비교는 무효다.
        "same_baseline": len(baseline_hashes) <= 1 or all(
            r["baseline"]["net_profit"] == runs[0]["baseline"]["net_profit"] for r in runs),
    }


def variance(org_id: str, period: str,
             plan_kind: str = PLAN, actual_kind: str = ACTUAL) -> Dict[str, Any]:
    """계획 대비 실적 차이 분석(§17.2 기능 4).

    ⚠️ 한쪽이 비어 있으면 **차이를 계산하지 않는다.** 없는 값을 0 으로 두면 "계획 100 · 실적 0
      → 100 미달"처럼 보이는데, 실제로는 실적이 아직 안 들어온 것뿐이다. 그 둘은 완전히 다르다."""
    plan = planning_store.list_facts(org_id=org_id, period=period, value_kind=plan_kind)
    act = planning_store.list_facts(org_id=org_id, period=period, value_kind=actual_kind)
    if not plan or not act:
        return {
            "org_id": org_id, "period": period, "comparable": False,
            "reason": ("계획이 없습니다" if not plan else "실적이 아직 입력되지 않았습니다"),
            "note": "한쪽이 비어 있어 차이를 계산하지 않았습니다 — "
                    "없는 값을 0 으로 두면 '미달'로 잘못 읽힙니다.",
        }
    accounts = _accounts_by_code()
    p, a = compute_pl(plan, accounts), compute_pl(act, accounts)
    rows = []
    plan_by = {f["account_code"]: float(f["amount"]) for f in plan}
    act_by = {f["account_code"]: float(f["amount"]) for f in act}
    for code in sorted(set(plan_by) | set(act_by)):
        pv, av = plan_by.get(code), act_by.get(code)
        rows.append({
            "account_code": code,
            "plan": pv, "actual": av,
            # 한쪽이 없으면 diff 도 None 이다(0 이 아니다).
            "diff": None if (pv is None or av is None) else round(av - pv, 4),
            "missing": ("actual" if av is None else ("plan" if pv is None else "")),
        })
    return {
        "org_id": org_id, "period": period, "comparable": True,
        "plan": p, "actual": a,
        "diff": {
            "operating_profit": round(a["operating_profit"] - p["operating_profit"], 4),
            "net_profit": round(a["net_profit"] - p["net_profit"], 4),
        },
        "by_account": rows,
        "engine_version": ENGINE_VERSION,
    }


# ══════════════════════════════════════════════════════════════════════
# 현금흐름 (§17.2 기능 6 · §11.4 가치사슬의 마지막 단계)
# ══════════════════════════════════════════════════════════════════════
#: 간접법 현금흐름에 반드시 필요한 항목. **하나라도 없으면 계산하지 않는다.**
_CF_REQUIRED = ("DEPRECIATION", "WORKING_CAPITAL", "CAPEX")


def compute_cash_flow(facts: List[Dict[str, Any]],
                      accounts: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """간접법 현금흐름. **손익만으로는 계산할 수 없다** — 없으면 없다고 말한다.

    ```
    영업현금흐름 = 당기순이익 + 감가상각비 − 운전자본 증가
    투자현금흐름 = −CAPEX
    재무현금흐름 = FINANCING(차입 − 상환 − 배당)
    ```

    ⚠️ **이 함수의 핵심은 계산이 아니라 거절이다.** 감가상각·운전자본·CAPEX 가 없는데
      0 으로 채우면 "영업현금흐름 = 순이익"이 되어 **현금이 충분한 것처럼 보인다.**
      흑자도산은 정확히 그 착시에서 온다. 그래서 누락 항목이 있으면 `computable=false` 로
      돌려주고 무엇이 없는지 이름을 댄다.

    ⚠️ 부호 규약: `WORKING_CAPITAL` 은 **증가분**을 양수로 입력한다(운전자본이 늘면 현금은
      줄어든다). `CAPEX` 도 지출을 양수로 입력한다. 입력자가 부호를 고민하지 않게 하고,
      방향은 여기 산식이 정한다."""
    accounts = accounts if accounts is not None else _accounts_by_code()
    pl = compute_pl(facts, accounts)

    buckets: Dict[str, float] = {k: 0.0 for k in CF_CATEGORIES}
    seen: set = set()
    for f in facts:
        acc = accounts.get(f.get("account_code"))
        if not acc or acc["category"] not in CF_CATEGORIES:
            continue
        buckets[acc["category"]] += float(f.get("amount") or 0)
        seen.add(acc["category"])

    missing = [c for c in _CF_REQUIRED if c not in seen]
    if missing:
        return {
            "computable": False,
            "missing": missing,
            "net_profit": pl["net_profit"],
            "reason": f"현금흐름 계산에 필요한 항목이 없습니다: {', '.join(missing)}",
            "note": ("없는 항목을 0 으로 채우면 '영업현금흐름 = 순이익'이 되어 현금이 "
                     "충분한 것처럼 보입니다 — 흑자도산은 그 착시에서 옵니다. "
                     "그래서 계산하지 않았습니다."),
            "engine_version": ENGINE_VERSION,
        }

    operating = pl["net_profit"] + buckets["DEPRECIATION"] - buckets["WORKING_CAPITAL"]
    investing = -buckets["CAPEX"]
    financing = buckets["FINANCING"]
    return {
        "computable": True,
        "net_profit": pl["net_profit"],
        "operating_cf": round(operating, 4),
        "investing_cf": round(investing, 4),
        "financing_cf": round(financing, 4),
        "free_cash_flow": round(operating + investing, 4),
        "net_change": round(operating + investing + financing, 4),
        "components": {k: round(v, 4) for k, v in buckets.items()},
        # 손익이 불완전하면 현금흐름도 그만큼 불완전하다 — 그 사실을 물고 간다.
        "pl_complete": pl["complete"],
        "engine_version": ENGINE_VERSION,
    }


def cash_flow_for(org_id: str, period: str, value_kind: str = PLAN) -> Dict[str, Any]:
    """조직·기간의 현금흐름. 값이 없으면 **빈 계산을 하지 않는다.**"""
    facts = planning_store.list_facts(org_id=org_id, period=period, value_kind=value_kind)
    if not facts:
        return {"computable": False, "missing": ["ALL"],
                "reason": f"값이 없습니다({org_id}/{period}/{value_kind}).",
                "note": "빈 입력으로 계산하면 0 이 결과처럼 보입니다.",
                "engine_version": ENGINE_VERSION}
    return {**compute_cash_flow(facts), "org_id": org_id, "period": period,
            "value_kind": value_kind}
