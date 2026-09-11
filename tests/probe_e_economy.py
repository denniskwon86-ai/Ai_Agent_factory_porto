"""[X-6 · E-1 · E-2 · E-3] 계획 6단계 — 비용은 «측정되는가».

    X-6 (§9.6)  비용보다 모델 이름   고성능 모델이 «불필요한 작업에도» 쓰이는가
    E-1         승인 결과물 1건당 비용  **측정된다.** 측정 못 하면 통제 못 한다
    E-2         모델 배분 근거         고성능 모델이 «필요한 곳에만»
    E-3         축적 효과              2회차가 1회차보다 적게 드는가

## ★ 이 트랙의 수용 기준은 「싸다」가 아니라 「**잴 수 있다**」이다

E-1 이 그렇게 적혀 있다 — 「측정된다. 측정 못 하면 통제 못 한다」. 그래서 이 탐침은
비용의 **크기**를 판정하지 않는다. 얼마가 적정한지는 사람이 정한다.
여기서 보는 것은 **숫자가 실제로 나오는가**, 그리고 **안 나오는 부분이 명시되는가** 다.

## 자료 — 실제 호출 로그

`data/llm_call_log.jsonl` 을 **제품이 읽는 함수로** 읽는다
(`api.routes.telemetry_control._read_records` · `aggregate`). 파일을 직접 파싱하면
제품이 보는 것과 내가 보는 것이 갈린다(이 저장소에서 여러 번 그랬다).

⚠️ 운영 DB·로그에 **한 줄도 쓰지 않는다.** 전부 읽기다.
"""
from __future__ import annotations

import io
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "E_FINDINGS.md")

OK = "측정됨"
SHORT = "미측정"        # 잴 수 없다 — 그것이 E 트랙의 실패 조건이다
LEAKED = "샘"
ERROR = "탐침 오류"
PASSING = (OK,)

#: ★ 한 번만 읽어 모든 항목이 **같은 자료**를 본다. 항목마다 다시 읽으면
#:   그 사이 로그가 늘어 「합이 안 맞는다」가 생긴다(공유 트리 정산에서 이미 겪었다).
_CACHE: Dict[str, Any] = {}


def _records() -> List[dict]:
    if "recs" not in _CACHE:
        import api.routes.telemetry_control as T
        _CACHE["recs"] = T._read_records()
        _CACHE["agg"] = T.aggregate(_CACHE["recs"])
    return _CACHE["recs"]


def _agg() -> Dict[str, Any]:
    _records()
    return _CACHE["agg"]


class Finding:
    def __init__(self, track: str, what: str, verdict: str, evidence: str):
        self.track, self.what, self.verdict, self.evidence = track, what, verdict, evidence

    def line(self) -> str:
        mark = {OK: "OK ", SHORT: "⚠️ ", LEAKED: "⚠️ "}.get(self.verdict, "?? ")
        return "| %s | %s | %s%s | %s |" % (
            self.track, self.what, mark, self.verdict, self.evidence.replace("|", "/")[:170])


def probe(track: str, what: str, fn: Callable[[], Tuple[str, str]]) -> Finding:
    try:
        verdict, evidence = fn()
    except Exception:                       # noqa: BLE001
        return Finding(track, what, ERROR,
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Finding(track, what, verdict, evidence)


# ══ E-1 비용이 실제로 나오는가 ═════════════════════════════════════════════
def cost_is_actually_measured() -> Tuple[str, str]:
    t = _agg()["totals"]
    if not t.get("calls"):
        return SHORT, "호출 기록이 0건 — 잴 것이 없다"
    priced, unpriced = t.get("priced_calls", 0), t.get("unpriced_calls", 0)
    if t.get("cost_usd") is None:
        return SHORT, "합계 비용이 없다"
    return OK, ("호출 {:,}건 · 비용 ${:,.2f} · 산정됨 {:,}건 / 미산정 {}건({:.1f}%) · "
                "토큰 입력 {:,} / 출력 {:,}").format(
        t["calls"], t["cost_usd"], priced, unpriced,
        100.0 * unpriced / max(t["calls"], 1),
        t.get("total_input_tokens", 0), t.get("total_output_tokens", 0))


def unpriced_calls_are_not_counted_as_free() -> Tuple[str, str]:
    """★★★ 가장 중요한 것 — **미산정을 0 으로 접으면 「공짜였다」는 거짓**이 된다."""
    agg = _agg()
    basis = agg.get("by_cost_basis") or {}
    if "unpriced" not in basis and "free_tier" not in basis:
        return SHORT, "cost_basis 구분이 없다 — 무료와 «모름» 이 섞인다"
    free = basis.get("free_tier", {}).get("calls", 0)
    unp = basis.get("unpriced", {}).get("calls", 0)
    cache = basis.get("cache_hit", {}).get("calls", 0)
    paid = basis.get("paid", {}).get("calls", 0)
    if unp and basis["unpriced"].get("cost_usd", 0) != 0:
        return LEAKED, "미산정 호출에 비용이 붙었다 — 모르는 값을 지어냈다"
    return OK, ("무료 %d · 캐시 %d · 유료 %d · **모름 %d** 로 갈라 센다 — "
                "「모름」을 0 으로 접지 않는다" % (free, cache, paid, unp))


def cost_can_be_split_by_project() -> Tuple[str, str]:
    """비용을 «일 단위» 로 나눌 수 있는가 — 통제하려면 나눌 수 있어야 한다."""
    import collections
    recs = _records()
    per = collections.Counter()
    for r in recs:
        key = str(r.get("project_id") or r.get("project") or "")
        if key and r.get("cost_estimate_usd") is not None:
            per[key] += float(r["cost_estimate_usd"])
    if not per:
        return SHORT, "프로젝트별로 나눌 수 없다 — 호출에 프로젝트 표시가 없다"
    top = per.most_common(4)
    return OK, "프로젝트 %d개로 나뉜다 · 상위: %s" % (
        len(per), ", ".join("%s $%.2f" % (k, v) for k, v in top))


def cost_per_approved_deliverable() -> Tuple[str, str]:
    """★★★ E-1 이 «문자 그대로» 요구하는 것 — 「**승인된 결과물** 1건당 비용」."""
    import sqlite3
    path = os.path.join(PROJECT_ROOT, "data", "collaboration.db")
    conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    try:
        approved = conn.execute(
            "SELECT COUNT(*) FROM publications WHERE status='APPROVED'").fetchone()[0]
        cols = {r[1] for r in conn.execute("PRAGMA table_info(publications)")}
    finally:
        conn.close()
    recs = _records()
    has_link = any(str(r.get("publication_id") or r.get("decision_id") or "") for r in recs)
    if not approved:
        return SHORT, "승인된 발간물 0건 — 분모가 없다"
    if not has_link and not ({"project_id", "project"} & cols):
        return SHORT, ("승인 발간물 %d건이지만 **호출과 잇는 키가 없다** — 호출 로그는 "
                       "`project_id` 로, 발간물은 `source_id`(결정 안건)로 묶인다. "
                       "둘을 잇는 열이 어느 쪽에도 없어 «1건당 비용» 을 못 낸다" % approved)
    return OK, "승인 발간물 %d건 · 호출과 연결 가능" % approved


# ══ X-6 · E-2 모델 배분에 근거가 있는가 ════════════════════════════════════
def model_choice_has_a_declared_policy() -> Tuple[str, str]:
    """★ 「근거가 있다」의 최소 조건 — 작업 등급별 모델 사슬이 **선언돼 있다**."""
    from core import model_routing_policy as MR

    chains = MR.chains()
    if not chains:
        return SHORT, "작업 등급별 모델 사슬이 선언돼 있지 않다"
    eff = MR.effective()
    return OK, "등급 %s · 우선순위 판정(%s)이 «누가 이겼는지» 를 함께 돌려준다: %s" % (
        list(chains), eff.get("source"), chains)


def the_pro_tier_is_not_an_expensive_name() -> Tuple[str, str]:
    """★★★ §9.6 의 함정 그 자체 — 「pro」 라는 «이름» 이 비싼 모델을 뜻하는가."""
    from core import model_routing_policy as MR
    from core.llm_cost import is_paid_model

    chains = MR.chains()
    pro = list(chains.get("pro") or ())
    if not pro:
        return SHORT, "pro 사슬이 비어 있다"
    first = pro[0]
    flash = list(chains.get("flash") or ())
    if flash and first == flash[0]:
        return LEAKED, "pro 와 flash 의 첫 모델이 같다 — 등급이 이름뿐이다"
    return OK, ("pro 의 첫 모델은 `%s` 다 — 「pro」가 «비싼 이름» 을 뜻하지 않는다"
                "(유료 판정 %s). flash 첫 모델 `%s`" % (first, is_paid_model(first),
                                                      flash[0] if flash else "-"))


def high_tier_is_not_used_everywhere() -> Tuple[str, str]:
    """§9.6 계측 — 고성능 등급이 «불필요한 작업에도» 쓰이는가."""
    agg = _agg()
    tiers = agg.get("by_requested_tier") or {}
    if not tiers:
        return SHORT, "요청 등급이 기록되지 않는다 — 배분을 잴 수 없다"
    total = sum(v.get("calls", 0) for v in tiers.values())
    pro = sum(v.get("calls", 0) for k, v in tiers.items() if "pro" in k)
    share = 100.0 * pro / max(total, 1)
    down = sum(v.get("downgraded", 0) for v in tiers.values())
    if share >= 100.0:
        return LEAKED, "모든 호출이 고성능 등급이다 — 등급을 나눈 의미가 없다"
    return OK, ("고성능 등급 %d/%d (%.0f%%) · 저성능 %d · 강등된 호출 %d건 — "
                "등급이 실제로 갈리고 강등도 일어난다"
                % (pro, total, share, total - pro, down))


def stages_have_different_model_mixes() -> Tuple[str, str]:
    """★ 「작업별 배분에 근거가 있다」 — 단계마다 «다른» 모델을 쓰는가.
    전 단계가 같은 모델이면 그것은 배분이 아니라 기본값이다."""
    agg = _agg()
    stages = agg.get("by_stage") or {}
    named = {k: v for k, v in stages.items() if k not in ("(none)", "")}
    if len(named) < 2:
        return SHORT, "단계 표시가 있는 호출이 %d종뿐 — 배분을 비교할 수 없다" % len(named)
    mixes = {k: tuple(sorted((v.get("models") or {}))) for k, v in named.items()}
    distinct = len(set(mixes.values()))
    top = sorted(named.items(), key=lambda kv: -kv[1].get("calls", 0))[:3]
    return OK, ("단계 %d종 · 서로 다른 모델 조합 %d가지 · 상위: %s"
                % (len(named), distinct,
                   ", ".join("%s %d회" % (k, v.get("calls", 0)) for k, v in top)))


# ══ E-3 축적 효과 ══════════════════════════════════════════════════════════
def repeat_runs_are_comparable() -> Tuple[str, str]:
    """2회차가 1회차보다 싼가.

    ⚠️⚠️ **이 탐침은 «답» 을 주지 않는다.** 로그에 `live-walk-02`·`live-walk-03` 처럼
      회차로 보이는 이름이 있지만, 그것이 «같은 일을 두 번» 한 것인지 «다른 일» 인지
      이름만으로는 알 수 없다. 다른 일이면 싸진 것이 축적 효과가 아니다 —
      그 구분은 사람이 한다(기억: 대조군이 진짜 대조군인지 먼저 증명한다).

    그래서 여기서는 **비교할 짝이 있는지와 그 수치까지만** 낸다."""
    import collections
    import re

    recs = _records()
    per = collections.Counter()
    calls = collections.Counter()
    for r in recs:
        key = str(r.get("project_id") or r.get("project") or "")
        if not key:
            continue
        calls[key] += 1
        if r.get("cost_estimate_usd") is not None:
            per[key] += float(r["cost_estimate_usd"])

    #: 접미 숫자가 다른 «같은 뿌리» 이름을 짝으로 본다.
    fam: Dict[str, List[Tuple[str, int]]] = {}
    for key in calls:
        m = re.match(r"^(.*?)[-_]?(\d{1,3})$", key)
        if m and m.group(1):
            fam.setdefault(m.group(1), []).append((key, int(m.group(2))))
    pairs = {k: sorted(v, key=lambda x: x[1]) for k, v in fam.items() if len(v) >= 2}
    if not pairs:
        return SHORT, "회차로 볼 수 있는 짝이 없다 — 축적 효과를 잴 대상이 없다"

    lines = []
    cheaper = 0
    for root, seq in sorted(pairs.items())[:4]:
        firsts, lasts = seq[0], seq[-1]
        c1, c2 = per.get(firsts[0], 0.0), per.get(lasts[0], 0.0)
        n1, n2 = calls[firsts[0]], calls[lasts[0]]
        if c2 < c1:
            cheaper += 1
        lines.append("%s: %s $%.2f(%d회) → %s $%.2f(%d회)"
                     % (root, firsts[0], c1, n1, lasts[0], c2, n2))
    return OK, ("회차 짝 %d묶음 · 나중 회차가 더 싼 경우 %d — %s ⚠️ 같은 일인지는 "
                "이름만으로 모른다(사람이 판정)" % (len(pairs), cheaper, " / ".join(lines)))


PROBES: List[Tuple[str, str, Callable[[], Tuple[str, str]]]] = [
    ("E-1", "비용이 실제로 숫자로 나오는가", cost_is_actually_measured),
    ("E-1", "«모름» 을 0(공짜)으로 접지 않는가", unpriced_calls_are_not_counted_as_free),
    ("E-1", "비용을 일 단위로 나눌 수 있는가", cost_can_be_split_by_project),
    ("E-1", "«승인된 결과물 1건당» 을 낼 수 있는가", cost_per_approved_deliverable),
    ("X-6", "작업 등급별 모델 정책이 선언돼 있는가", model_choice_has_a_declared_policy),
    ("X-6", "「pro」가 «비싼 이름» 을 뜻하는가", the_pro_tier_is_not_an_expensive_name),
    ("E-2", "고성능 등급이 모든 곳에 쓰이는가", high_tier_is_not_used_everywhere),
    ("E-2", "단계마다 모델 조합이 다른가", stages_have_different_model_mixes),
    ("E-3", "회차 비교가 가능한가", repeat_runs_are_comparable),
]


def main() -> int:
    findings = [probe(t, w, f) for t, w, f in PROBES]
    short = [f for f in findings if f.verdict == SHORT]
    leaked = [f for f in findings if f.verdict == LEAKED]
    errors = [f for f in findings if f.verdict == ERROR]

    b = io.StringIO()
    b.write("# X-6 · E 트랙 결과 — 비용은 «측정되는가»\n\n")
    b.write("> 자동 생성: `tests/probe_e_economy.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    b.write("> ★ 이 트랙의 수용 기준은 「싸다」가 아니라 **「잴 수 있다」** 다 — "
            "얼마가 적정한지는 사람이 정한다.\n")
    b.write("> 자료: `data/llm_call_log.jsonl` 을 **제품이 읽는 함수로** 읽었다"
            "(`telemetry_control._read_records`·`aggregate`).\n\n")
    b.write("    항목 %d건 · 측정됨 %d건 · **미측정 %d건** · **샘 %d건** · 탐침 오류 %d건\n\n"
            % (len(findings), len(findings) - len(short) - len(leaked) - len(errors),
               len(short), len(leaked), len(errors)))
    b.write("| 트랙 | 무엇을 봤나 | 결과 | 근거 |\n|---|---|---|---|\n")
    for f in findings:
        b.write(f.line() + "\n")

    b.write("\n---\n\n## 판정\n\n")
    if errors:
        b.write("⚠️ **탐침 자신이 %d건 실패했다** — 「모른다」이지 「통과」가 아니다.\n\n" % len(errors))
    if leaked:
        b.write("### ⚠️⚠️ 샜다\n\n")
        for f in leaked:
            b.write("- **%s %s** → %s\n" % (f.track, f.what, f.evidence))
        b.write("\n")
    if short:
        b.write("### ⚠️ 미측정 — 「잴 수 없다」는 E 트랙의 실패 조건이다\n\n")
        for f in short:
            b.write("- **%s %s** → %s\n" % (f.track, f.what, f.evidence))
        b.write("\n")
    if not short and not leaked and not errors:
        b.write("### X-6 · E 트랙 **통과** — 전부 숫자가 나온다\n")

    b.write("\n⚠️ 이 결과가 «주장하지 않는» 것\n\n")
    b.write("- **비용이 적정한지 판정하지 않았다.** 「$19.83 이 싼가」는 사람이 정한다.\n")
    b.write("- E-3 은 «짝이 있다» 까지만이다. 회차 이름이 «같은 일을 두 번» 이라는 보장이 "
            "없으므로, 싸진 것을 축적 효과라고 부르지 않았다.\n")
    b.write("- 이 로그는 **개발 중 호출**이 섞여 있다. 운영 단가로 읽으면 안 된다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(b.getvalue())
    print(b.getvalue())
    print("기록:", REPORT)
    return 1 if leaked or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
