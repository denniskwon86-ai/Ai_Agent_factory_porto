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

## ⚠️⚠️ 이 모듈이 실제로 거짓말한 두 가지 (2026-08-07 조사로 확인, 아래가 그 수정)

초판은 관측률은 훌륭하게 방어했지만 **시간 축**과 **레코드≠콜** 을 방어하지 못했다.
`Master_PMO 성공률 6.7%` 라는 숫자가 화면에 떴고, 그 숫자는 다음 두 겹으로 틀렸다.

**(1) 시간 축이 없었다 — 죽은 과거가 현재로 보고된다.**
  전체 로그 생애를 한 덩어리로 집계했다. 실패 40건은 **전부 2026-07-29 11:43~12:03 의 단일
  실행**(`test_a1_unitconv_canary2`)이었고, 그 원인(계측 콜백이 `AttributeError` 로 파이프라인을
  죽인 결함)은 **같은 날 12:18 에 이미 고쳐졌다**(커밋 `2334d1572`). 직후 실행은 48/48 성공이다.
  그런데 9일 뒤 대시보드는 그 20분을 «현재 상태» 로 보여주고 있었다.
  → `since` 로 창을 자르고, **창을 응답에 반드시 실어** 「이 숫자가 언제의 것인지」를 남긴다.
  → 그리고 창 밖 건수를 함께 낸다 — 잘라낸 것을 없는 것처럼 만들지 않기 위해서다.

**(2) 레코드를 콜로 셌다 — 분모가 실패 쪽으로만 부푼다.**
  게이트웨이는 실패하면 `pro(retry0)` + `flash(retry1)` 로 **2줄**을 남기고, 성공하면 **1줄**만
  남긴다. 줄 수로 나누면 실패한 호출만 분모를 두 배로 키운다(12.5% → 6.7%).
  `retry_count==0` 만 세는 우회도 틀린다 — 재시도로 **살아난** 호출(전체 로그 5건)이 머리
  기록만 보면 실패로 남는다. 순서로 묶는 것도 틀린다 — 동시 실행이라 로그가 교차한다(실측 11건).
  → 그래서 게이트웨이가 `call_id` 를 심고(`llm_gateway._log_llm_call`), 여기서는 **그 id 로
    묶어** 체인의 최종 결과를 콜 1건의 결과로 센다. 추론하지 않는다.
  → `call_id` 가 없는 **과거 기록은 묶지 않는다.** 대신 몇 건이 그런지를 `coverage` 에 낸다 —
    그 구간의 성공률은 **하한** 이라는 사실이 숫자 옆에 붙어 있어야 한다.

★ 두 수정의 공통 원칙: **잘라낸 것·모르는 것을 응답에 남긴다.** 조용히 좋아 보이게 만드는 것은
  조용히 나빠 보이게 만드는 것과 같은 종류의 거짓말이다.
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


def _in_window(r: Dict[str, Any], since: str = "", until: str = "") -> bool:
    """`ts` 는 `datetime.isoformat(timespec="seconds")` 라 **문자열 비교가 곧 시간 비교**다.

    ⚠️ ts 가 없거나 형식이 깨진 기록은 **버리지 않고 통과시킨다.** 창을 못 재는 기록을 조용히
      떨어뜨리면 「창 밖 N건」에도 안 잡혀 영영 사라진다 — 그것이 이 모듈이 막으려는 실패다."""
    ts = str(r.get("ts") or "")
    if not ts:
        return True
    if since and ts < since:
        return False
    if until and ts > until:
        return False
    return True


def _collapse_to_calls(records: Iterable[Dict[str, Any]]) -> tuple:
    """레코드 → **논리적 호출**. 반환 `(calls, legacy_records)`.

    한 번의 호출이 재시도·티어우회로 여러 줄을 남긴다. `call_id` 가 같은 줄들을 하나로 접는다.

    접는 규칙(전부 «관측» 이고 추론이 아니다):
      - `ok` — 체인 안에 성공이 하나라도 있으면 성공. 게이트웨이는 성공 즉시 반환하므로
        「retry1 에서 살아난 호출」은 **성공한 호출 1건**이지 「1실패+1성공」이 아니다.
      - 토큰·비용 — 체인 전체를 **합산한다.** 재시도는 실제로 돈을 썼다. 콜 수만 1로 접고
        비용도 1회분으로 접으면 이번엔 비용이 거짓이 된다.
      - 그 외 축(stage/used/tier) — 결과를 만든 기록(성공 기록, 없으면 마지막)을 대표로 쓴다.

    ⚠️ `call_id` 가 없는 과거 기록은 **묶지 않는다.** 순서로 추측하면 동시 실행 교차에서 깨지고
      (실측 11건), `retry_count==0` 만 세면 재시도로 살아난 호출을 실패로 만든다(실측 5건).
      묶지 못한 건수는 호출자가 `coverage` 로 드러낸다."""
    chains: Dict[str, List[Dict[str, Any]]] = {}
    legacy: List[Dict[str, Any]] = []
    for r in records or ():
        cid = str(r.get("call_id") or "").strip()
        if cid:
            chains.setdefault(cid, []).append(r)
        else:
            legacy.append(r)

    calls: List[Dict[str, Any]] = []
    for cid, chain in chains.items():
        chain = sorted(chain, key=lambda x: (str(x.get("ts") or ""), _num(x.get("retry_count"))))
        winner = next((c for c in chain if c.get("ok")), chain[-1])
        merged = dict(winner)
        merged["ok"] = any(c.get("ok") for c in chain)
        merged["_records"] = len(chain)
        merged["_call_id"] = cid
        # 합산 축 — 재시도가 쓴 토큰·비용은 사라지면 안 된다.
        merged["input_tokens"] = sum(int(_num(c.get("input_tokens"))) for c in chain)
        merged["output_tokens"] = sum(int(_num(c.get("output_tokens"))) for c in chain)
        _costs = [c.get("cost_estimate_usd") for c in chain]
        merged["cost_estimate_usd"] = (None if all(x is None for x in _costs)
                                       else sum(_num(x) for x in _costs if x is not None))
        # 하나라도 미산정이면 그 콜의 비용은 «부분» 이다 — 호출자가 unpriced 로 세도록 남긴다.
        merged["_has_unpriced_leg"] = any(x is None for x in _costs)
        merged["downgraded"] = any(c.get("downgraded") for c in chain)
        merged["_fellback"] = any(len(c.get("attempts") or []) > 1 for c in chain)
        merged["agent"] = next((c.get("agent") for c in chain if str(c.get("agent") or "").strip()),
                               winner.get("agent"))
        calls.append(merged)

    for r in legacy:
        m = dict(r)
        m["_records"] = 1
        m["_call_id"] = ""
        m["_has_unpriced_leg"] = r.get("cost_estimate_usd") is None
        m["_fellback"] = len(r.get("attempts") or []) > 1
        calls.append(m)

    calls.sort(key=lambda x: str(x.get("ts") or ""))
    return calls, legacy


def aggregate_by_agent(records: Iterable[Dict[str, Any]],
                       since: str = "", until: str = "") -> Dict[str, Any]:
    """에이전트별 집계 + **관측률** + **시간 창**.

    `since`/`until` 은 ISO 문자열(예: `"2026-08-01"`). 비우면 전 기간이다. 정책(기본 며칠인가)은
    호출자가 정한다 — 이 함수는 순수하게 유지해 테스트가 «오늘» 에 의존하지 않게 한다.

    반환의 `coverage` 를 무시하지 말 것 — 그것 없이는 아래 숫자가 전체인지 일부인지 알 수 없다.
    ★ `window` 도 함께 볼 것 — 그것 없이는 이 숫자가 **언제의 것인지** 알 수 없다.
    """
    _all = list(records or ())
    _kept = [r for r in _all if _in_window(r, since, until)]
    _outside = len(_all) - len(_kept)

    calls, _legacy = _collapse_to_calls(_kept)
    #: 재시도로 갈라졌던 줄 수 - 콜 수. 「몇 줄이 접혔는지」를 사람이 볼 수 있게 남긴다.
    collapsed_records = sum(int(c.get("_records") or 1) for c in calls) - len(calls)
    legacy_records = len(_legacy)
    # ★ 경고는 **실제로 왜곡이 있을 때만** 낸다.
    #   `call_id` 가 없다는 사실 자체는 문제가 아니다 — 왜곡은 «재시도로 갈라진 여분의 줄» 이
    #   접히지 않을 때만 생기고, 그 줄은 `retry_count > 0` 으로 스스로를 드러낸다.
    #   ⚠️ 이 조건 없이 「call_id 없음」만으로 경고하면 **모든 응답에 경고가 붙는다.** 늘 켜져
    #     있는 경고는 꺼져 있는 것과 같다(같은 파일 `test_full_coverage_says_nothing_alarming`).
    legacy_retry_records = sum(1 for r in _legacy if _num(r.get("retry_count")) > 0)

    rows: Dict[str, Dict[str, Any]] = {}
    total = 0
    attributed = 0
    #: 비용 근거를 모르는 호출 수. **0원이 아니라 «모른다» 다**(`llm_cost` 주석).
    unpriced = 0
    priced_cost = 0.0

    for r in calls:
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
            #: 접힌 줄 수 — 「30콜」이 사실은 몇 줄이었는지를 남긴다.
            "log_records": 0, "legacy_records": 0,
            #: ★ 실패가 «언제·어디에» 몰렸는가. 이것이 없어서 고쳐진 결함을 9일 동안 못 봤다.
            "_fail_days": {}, "_fail_projects": {},
        })
        b["calls"] += 1
        b["log_records"] += int(r.get("_records") or 1)
        if not str(r.get("_call_id") or ""):
            b["legacy_records"] += 1
        if r.get("ok"):
            b["ok"] += 1
        else:
            b["failed"] += 1
            _day = str(r.get("ts") or "")[:10] or "(미상)"
            b["_fail_days"][_day] = b["_fail_days"].get(_day, 0) + 1
            _proj = str(r.get("project_id") or "").strip() or "(미상)"
            b["_fail_projects"][_proj] = b["_fail_projects"].get(_proj, 0) + 1
        b["input_tokens"] += int(_num(r.get("input_tokens")))
        b["output_tokens"] += int(_num(r.get("output_tokens")))

        cost = r.get("cost_estimate_usd")
        if cost is None or r.get("_has_unpriced_leg"):
            # ⚠️ 0 으로 더하지 않는다 — 「공짜였다」는 거짓이 된다.
            #   재시도 중 한 다리라도 단가를 모르면 그 콜의 비용은 «부분» 이므로 여기로 센다.
            b["unpriced_calls"] += 1
            unpriced += 1
        if cost is not None:
            b["cost_usd"] += _num(cost)
            priced_cost += _num(cost)

        if r.get("downgraded"):
            b["downgraded"] += 1
        if r.get("_fellback"):
            b["fallback_calls"] += 1

        used = str(r.get("used") or "").strip() or "(미상)"
        b["models"][used] = b["models"].get(used, 0) + 1
        stage = str(r.get("stage") or "").strip() or "(미상)"
        b["stages"][stage] = b["stages"].get(stage, 0) + 1

    out: List[Dict[str, Any]] = []
    for b in rows.values():
        _n = b["calls"] or 1
        b["success_rate"] = round(b["ok"] / _n, 4)
        b["fallback_rate"] = round(b["fallback_calls"] / _n, 4)
        b["cost_usd"] = round(b["cost_usd"], 6)
        # ★ 비용을 «평균» 으로만 보여 주면 가격을 모르는 호출이 평균을 낮춘다.
        #   가격을 아는 호출로만 나눈다는 사실을 이름에 담는다.
        priced = b["calls"] - b["unpriced_calls"]
        b["avg_cost_usd_of_priced"] = round(b["cost_usd"] / priced, 6) if priced else None
        b["failure_concentration"] = _concentration(b.pop("_fail_days"), b.pop("_fail_projects"),
                                                    b["failed"])
        out.append(b)
    out.sort(key=lambda x: (-x["calls"], x["agent"]))

    return {
        "agents": out,
        # ── ★★ 관측률 — 이것 없이 위 숫자를 읽으면 안 된다 ─────────────────
        "coverage": {
            # ⚠️ 이름은 유지하되 의미는 «논리적 호출 수» 다(과거엔 로그 줄 수였고, 그래서 틀렸다).
            "records": total,
            "with_agent": attributed,
            "without_agent": total - attributed,
            "attribution_rate": round(attributed / total, 4) if total else None,
            "unpriced_calls": unpriced,
            "priced_cost_usd": round(priced_cost, 6),
            # ── 콜 단위 집계의 근거를 드러낸다 ──────────────────────────
            #: 재시도·티어우회로 갈라졌다가 `call_id` 로 접힌 여분의 줄 수.
            "collapsed_retry_records": collapsed_records,
            #: `call_id` 가 없어 **접지 못한** 과거 기록 수.
            "records_without_call_id": legacy_records,
            #: 그중 실제로 왜곡을 만드는 것 — 접히지 못한 재시도 줄. 이만큼 성공률이 낮게 보인다.
            "uncollapsed_retry_records": legacy_retry_records,
            "note": _coverage_note(total, attributed, unpriced, legacy_retry_records),
        },
        # ── ★★ 시간 창 — 이것 없이 위 숫자가 «언제» 의 것인지 알 수 없다 ────
        "window": {
            "since": since or None,
            "until": until or None,
            "records_outside_window": _outside,
            "note": _window_note(since, until, _outside, total),
        },
    }


def _concentration(fail_days: Dict[str, int], fail_projects: Dict[str, int],
                   failed: int) -> Optional[Dict[str, Any]]:
    """실패가 **한 날·한 실행에 몰렸는가.**

    ★ 이 필드가 없어서 2026-07-29 에 이미 고쳐진 결함이 08-07 까지 «현재의 낮은 성공률» 로
      읽혔다. 실패 28건은 전부 하루·한 프로젝트였고, 그 사실만 보였어도 5분이면 끝났다.
      성공률은 «얼마나» 를 말하지만 «언제 한 번» 인지는 말하지 않는다 — 그 둘은 다른 질문이다."""
    if not failed:
        return None
    top_day, top_day_n = max(fail_days.items(), key=lambda kv: kv[1])
    top_proj, top_proj_n = max(fail_projects.items(), key=lambda kv: kv[1])
    single_run = len(fail_projects) == 1 and len(fail_days) == 1
    return {
        "failed": failed,
        "distinct_days": len(fail_days),
        "distinct_projects": len(fail_projects),
        "top_day": top_day, "top_day_share": round(top_day_n / failed, 4),
        "top_project": top_proj, "top_project_share": round(top_proj_n / failed, 4),
        "single_run": single_run,
        "note": (f"실패 {failed}건이 **전부 {top_day} 의 단일 실행({top_proj})** 에서 나왔습니다. "
                 f"지속적인 낮은 성공률이 아니라 **한 번의 사고**일 수 있습니다 — "
                 f"그 실행 이후의 기록으로 창을 좁혀 확인하십시오."
                 if single_run else
                 f"실패 {failed}건이 {len(fail_days)}일 · {len(fail_projects)}개 실행에 걸쳐 있습니다"
                 f"(최다: {top_day} {top_day_n}건).")
    }


def _coverage_note(total: int, attributed: int, unpriced: int, uncollapsed_retries: int = 0) -> str:
    """사람이 읽는 경고문. **비어 있으면 문제가 없다는 뜻이다.**

    ⚠️ 「관측률 10%」를 숫자로만 두면 아무도 안 본다. 그것이 무엇을 뜻하는지 문장으로 쓴다."""
    if not total:
        return ("집계할 호출 기록이 없습니다 — 이것은 «비용이 0» 이 아니라 «기록이 없다» 입니다.")
    parts: List[str] = []
    rate = attributed / total
    if rate < 1.0:
        parts.append(
            f"전체 {total}콜 중 {total - attributed}콜은 실행 주체가 기록되지 않아 «{UNATTRIBUTED}» "
            f"로 묶였습니다(관측률 {rate:.0%}). 에이전트별 숫자는 **전체가 아닙니다** — "
            f"계측 축이 추가되기 전의 호출이 여기 들어갑니다.")
    if unpriced:
        parts.append(
            f"{unpriced}콜은 단가를 몰라 비용에 더하지 않았습니다 — 0원이 아니라 «모름» 입니다.")
    if uncollapsed_retries:
        parts.append(
            f"{uncollapsed_retries}건은 `call_id` 가 없던 시절의 **재시도 기록**이라 하나의 호출로 "
            f"접지 못했습니다 — 실패한 호출만 여러 줄을 남기므로 그 구간의 성공률은 실제보다 "
            f"**낮게** 보입니다. 여기 표시된 성공률은 하한입니다.")
    return " ".join(parts)


def _window_note(since: str, until: str, outside: int, total: int) -> str:
    """★ 창을 좁혔다는 사실 자체를 문장으로 남긴다.

    ⚠️ 창을 조용히 적용하면 「최근 7일」이 「전 기간」으로 읽힌다. 좋아 보이게 만드는 침묵도
      나빠 보이게 만드는 침묵과 같은 거짓말이다(이 모듈의 첫 줄 참조)."""
    if not since and not until:
        return "전 기간입니다(시간 창 없음) — 오래전에 고쳐진 사고도 이 숫자에 남아 있습니다."
    rng = f"{since or '처음'} ~ {until or '지금'}"
    if not total:
        return (f"{rng} 구간에 호출 기록이 **없습니다** — 이것은 «전부 실패» 가 아니라 "
                f"«호출이 없었다» 입니다. 창 밖에 {outside}건이 있습니다.")
    base = f"{rng} 구간만 집계했습니다."
    if outside:
        base += f" 창 밖 {outside}건은 제외했습니다 — 사라진 것이 아니라 **이 창에 없을 뿐**입니다."
    return base


def top_cost_agents(agg: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    """비용 상위. ⚠️ «(미상)» 은 제외하지 않는다 — 대개 그것이 1위이고, 그 사실이 중요하다."""
    rows = sorted(agg.get("agents") or [], key=lambda x: -(x.get("cost_usd") or 0))
    return rows[:max(1, limit)]


def failing_agents(agg: Dict[str, Any], threshold: float = 0.9,
                   min_calls: int = 5) -> List[Dict[str, Any]]:
    """성공률이 낮은 에이전트.

    ⚠️ `min_calls` 를 두는 이유: 1콜 실패한 에이전트를 «성공률 0%» 로 올리면 목록이 소음이 되고,
      소음이 되면 사람이 목록 자체를 보지 않는다. 표본이 적다는 사실도 함께 돌려준다.

    ★★ [2026-08-07] 그런데 «표본이 충분하다» 가 «지속적인 문제다» 를 뜻하지는 않는다.
      실측: Master_PMO 30줄(=16콜) 중 실패가 **전부 한 날 한 실행**이었다. 표본은 충분했고
      우연도 아니었지만, 원인은 그날 안에 이미 고쳐진 결함 하나였다. 「표본이 크니 진짜다」는
      추론이 조사를 9일 늦췄다.
      → **목록에서 빼지는 않는다**(빼면 진짜 문제까지 사라진다). 대신 `single_run` 을 달아
        읽는 사람이 「지속」과 「사고 1회」를 구분할 수 있게 하고, 지속되는 것을 위로 올린다."""
    out = []
    for a in (agg.get("agents") or []):
        if a["agent"] == UNATTRIBUTED or a["calls"] < min_calls:
            continue
        if a["success_rate"] < threshold:
            conc = a.get("failure_concentration") or {}
            out.append({**a, "sample_size": a["calls"],
                        "single_run": bool(conc.get("single_run")),
                        "why": conc.get("note", "")})
    # 단일 사고(single_run)는 아래로 — 여러 날에 걸친 «지속되는» 실패가 먼저 보여야 한다.
    out.sort(key=lambda x: (x["single_run"], x["success_rate"]))
    return out
