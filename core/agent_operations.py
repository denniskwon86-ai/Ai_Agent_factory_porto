"""[D-017 §9 P4-1] 에이전트별 운영 지표 — 호출·성공률·비용·폴백.

## ⚠️⚠️ 이 파일이 가장 조심하는 것 — 대시보드는 조용히 거짓말한다

실측(2026-08-07): `llm_call_log.jsonl` 1,133건 중 **`agent` 필드가 있는 것은 113건(10%)** 이다.
계측 축이 나중에 추가됐기 때문이고, 그 자체는 정상이다.

그런데 이 상태에서 「에이전트별 비용」을 순진하게 집계하면 **총비용의 10%만 보인다.**
화면에는 그럴듯한 막대가 서고, 아무도 「나머지 90%는 어디 갔나」를 묻지 않는다.
숫자가 있으면 사람은 그것을 전부라고 읽는다 — 이것이 대시보드가 거짓말하는 방식이다.

★ 그래서 이 모듈은 **집계와 함께 관측률을 낸다.** 그리고 귀속되지 않은 호출을 버리지 않고
  «(미상)» 이라는 이름의 한 줄로 **같은 표에** 세운다. 없는 것처럼 만들지 않는다.

## 다른 축이 비어도 살아남는다

`stage` 축은 2026-07-29 카나리에서 **36콜 중 13콜이 단계 미상**이었다(`_with_agent_identity`
주석). 그래서 `agent` 축이 추가됐다. 두 축 중 하나가 비어도 계측이 남게 하려는 설계이므로,
이 모듈도 같은 태도를 취한다 — **비어 있음을 지우지 않고 드러낸다.**
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

#: 귀속되지 않은 호출을 세울 이름. **버리지 않는다.**
UNATTRIBUTED = "(미상)"


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def aggregate_by_agent(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """에이전트별 집계 + **관측률**.

    반환의 `coverage` 를 무시하지 말 것 — 그것 없이는 아래 숫자가 전체인지 일부인지 알 수 없다.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    total = 0
    attributed = 0
    #: 비용 근거를 모르는 호출 수. **0원이 아니라 «모른다» 다**(`llm_cost` 주석).
    unpriced = 0
    priced_cost = 0.0

    for r in records or ():
        total += 1
        name = str(r.get("agent") or "").strip()
        if name:
            attributed += 1
        else:
            name = UNATTRIBUTED

        b = rows.setdefault(name, {
            "agent": name, "calls": 0, "ok": 0, "failed": 0,
            "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "unpriced_calls": 0,
            "downgraded": 0, "fallback_calls": 0,
            "models": {}, "stages": {},
        })
        b["calls"] += 1
        if r.get("ok"):
            b["ok"] += 1
        else:
            b["failed"] += 1
        b["input_tokens"] += int(_num(r.get("input_tokens")))
        b["output_tokens"] += int(_num(r.get("output_tokens")))

        cost = r.get("cost_estimate_usd")
        if cost is None:
            # ⚠️ 0 으로 더하지 않는다 — 「공짜였다」는 거짓이 된다.
            b["unpriced_calls"] += 1
            unpriced += 1
        else:
            b["cost_usd"] += _num(cost)
            priced_cost += _num(cost)

        if r.get("downgraded"):
            b["downgraded"] += 1
        if len(r.get("attempts") or []) > 1:
            b["fallback_calls"] += 1

        used = str(r.get("used") or "").strip() or "(미상)"
        b["models"][used] = b["models"].get(used, 0) + 1
        stage = str(r.get("stage") or "").strip() or "(미상)"
        b["stages"][stage] = b["stages"].get(stage, 0) + 1

    out: List[Dict[str, Any]] = []
    for b in rows.values():
        calls = b["calls"] or 1
        b["success_rate"] = round(b["ok"] / calls, 4)
        b["fallback_rate"] = round(b["fallback_calls"] / calls, 4)
        b["cost_usd"] = round(b["cost_usd"], 6)
        # ★ 비용을 «평균» 으로만 보여 주면 가격을 모르는 호출이 평균을 낮춘다.
        #   가격을 아는 호출로만 나눈다는 사실을 이름에 담는다.
        priced = b["calls"] - b["unpriced_calls"]
        b["avg_cost_usd_of_priced"] = round(b["cost_usd"] / priced, 6) if priced else None
        out.append(b)
    out.sort(key=lambda x: (-x["calls"], x["agent"]))

    return {
        "agents": out,
        # ── ★★ 관측률 — 이것 없이 위 숫자를 읽으면 안 된다 ─────────────────
        "coverage": {
            "records": total,
            "with_agent": attributed,
            "without_agent": total - attributed,
            "attribution_rate": round(attributed / total, 4) if total else None,
            "unpriced_calls": unpriced,
            "priced_cost_usd": round(priced_cost, 6),
            "note": _coverage_note(total, attributed, unpriced),
        },
    }


def _coverage_note(total: int, attributed: int, unpriced: int) -> str:
    """사람이 읽는 경고문. **비어 있으면 문제가 없다는 뜻이다.**

    ⚠️ 「관측률 10%」를 숫자로만 두면 아무도 안 본다. 그것이 무엇을 뜻하는지 문장으로 쓴다."""
    if not total:
        return ("집계할 호출 기록이 없습니다 — 이것은 «비용이 0» 이 아니라 «기록이 없다» 입니다.")
    parts: List[str] = []
    rate = attributed / total
    if rate < 1.0:
        parts.append(
            f"전체 {total}건 중 {total - attributed}건은 실행 주체가 기록되지 않아 «{UNATTRIBUTED}» "
            f"로 묶였습니다(관측률 {rate:.0%}). 에이전트별 숫자는 **전체가 아닙니다** — "
            f"계측 축이 추가되기 전의 호출이 여기 들어갑니다.")
    if unpriced:
        parts.append(
            f"{unpriced}건은 단가를 몰라 비용에 더하지 않았습니다 — 0원이 아니라 «모름» 입니다.")
    return " ".join(parts)


def top_cost_agents(agg: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """비용 상위. ⚠️ «(미상)» 은 제외하지 않는다 — 대개 그것이 1위이고, 그 사실이 중요하다."""
    rows = sorted(agg.get("agents") or [], key=lambda x: -(x.get("cost_usd") or 0))
    return rows[:max(1, limit)]


def failing_agents(agg: Dict[str, Any], threshold: float = 0.9,
                   min_calls: int = 5) -> List[Dict[str, Any]]:
    """성공률이 낮은 에이전트.

    ⚠️ `min_calls` 를 두는 이유: 1콜 실패한 에이전트를 «성공률 0%» 로 올리면 목록이 소음이 되고,
      소음이 되면 사람이 목록 자체를 보지 않는다. 표본이 적다는 사실도 함께 돌려준다."""
    out = []
    for a in (agg.get("agents") or []):
        if a["agent"] == UNATTRIBUTED or a["calls"] < min_calls:
            continue
        if a["success_rate"] < threshold:
            out.append({**a, "sample_size": a["calls"]})
    out.sort(key=lambda x: x["success_rate"])
    return out
