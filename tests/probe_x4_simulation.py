"""[X-4] §9.4 「데이터 없이 시뮬레이션을 약속하기」를 **일으키려는** 탐침.

## 왜 시험(`test_*`)이 아니라 탐침인가

F-0 탐침과 같은 이유다 — 이것은 회귀 시험이 아니라 **조사**다. `test_` 로 시작하지
않으므로 T3(시간 예산 전체 스위트)에 들어가지 않는다. 손으로 돌리고 결과를 문서에 남긴다.

## 판정 규칙 (계획 §6)

    통과 = 함정이 «재현되지 않음»
    증거 = **실행 결과**여야 한다 — 고지문은 차단기가 아니다

그래서 각 항목은 「막는 코드가 있다」가 아니라 **「실제로 불렀더니 막혔다」**를 기록한다.
막힌 경우 그 사유 문장을 그대로 옮긴다 — 사용자가 보게 될 것이 그 문장이기 때문이다.

## ⚠️ 이 탐침이 «쓰지» 않는 것

운영 DB 에 한 줄도 쓰지 않는다. `planning_store`·`calc_graph` 는 읽기만 하고,
쓰기가 필요한 항목은 **격리 인스턴스**를 따로 만든다.
(기억: 「운영 DB 에 쓰기 탐침 금지」 — 세 번 어긋났다.)

## X-4 가 묻는 것을 항목으로 옮기면

    ① 기준선 없이 계산이 되는가              되면 FAIL
    ② 입력값이 빠졌는데 기본값으로 채우는가    채우면 FAIL
    ③ 파급계수가 없는데 «변화 없음» 으로 답하는가   답하면 FAIL (0% 는 적극적 주장이다)
    ④ 등급이 모자란데 값을 주는가             주면 FAIL
    ⑤ 한쪽 자료만 있는데 오차를 재는가         재면 FAIL
    ⑥ 계산 구성요소가 없는데 0 으로 채우는가    채우면 FAIL
    ⑦ 안 붙은 계정·가정을 조용히 버리는가      버리면 FAIL
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

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "X4_FINDINGS.md")

#: 판정 어휘 — 닫아 둔다. 「대체로 괜찮음」 같은 말이 끼면 집계가 무의미해진다.
BLOCKED = "막힘"        # 함정을 일으키려 했으나 거부됐다 = X-4 통과
REFUSED = "거부 응답"    # 예외는 아니지만 «못 한다»고 답했다 = X-4 통과
LEAKED = "샘"          # 그럴듯한 결과가 나왔다 = X-4 실패
ERROR = "탐침 오류"      # 탐침 자신이 틀렸다 — 판정에 쓰지 않는다

PASSING = (BLOCKED, REFUSED)


class Finding:
    def __init__(self, item: str, what: str, verdict: str, evidence: str):
        self.item, self.what, self.verdict, self.evidence = item, what, verdict, evidence

    def line(self) -> str:
        mark = "OK " if self.verdict in PASSING else ("⚠️ " if self.verdict == LEAKED else "?? ")
        return "| %s | %s | %s%s | %s |" % (
            self.item, self.what, mark, self.verdict, self.evidence.replace("|", "/")[:170])


def probe(item: str, what: str, fn: Callable[[], Tuple[str, str]]) -> Finding:
    """탐침 하나를 돌린다. **탐침 자신의 오류와 «함정이 열렸다»를 구분한다.**"""
    try:
        verdict, evidence = fn()
    except Exception:                      # noqa: BLE001 — 탐침 오류를 삼키지 않는다
        return Finding(item, what, ERROR, traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Finding(item, what, verdict, evidence)


def _one_line(text: Any, limit: int = 165) -> str:
    s = " ".join(str(text).split())
    return s[:limit]


# ── ① 기준선 없이 계산 ───────────────────────────────────────────────────────
def no_baseline_no_math() -> Tuple[str, str]:
    from core import calc_graph as cg

    class Naked:                            # fingerprint 가 없는 가짜 기준선
        fingerprint = ""

    full = {"production_qty": 100.0, "ending_inventory": 10.0, "purchase_payment": 50.0,
            "ending_cash": 30.0, "operating_profit": 5.0, "power_cost": 7.0,
            "period_days": 30.0}
    try:
        out = cg.simulate(Naked(), full, {})
    except cg.CalcError as exc:
        return BLOCKED, _one_line(exc)
    return LEAKED, "기준선 없이 결과가 나왔다: %s" % _one_line(getattr(out, "public", lambda: out)())


# ── ② 입력값이 빠졌을 때 기본값으로 채우는가 ────────────────────────────────
def missing_base_values_are_not_defaulted() -> Tuple[str, str]:
    from core import calc_graph as cg

    class Fake:
        fingerprint = "fp_probe_x4"

    partial = {"production_qty": 100.0, "period_days": 30.0}   # 다섯 개가 없다
    try:
        out = cg.simulate(Fake(), partial, {})
    except cg.CalcError as exc:
        return BLOCKED, _one_line(exc)
    return LEAKED, "빠진 입력을 채워 계산했다: %s" % _one_line(getattr(out, "public", lambda: out)())


# ── ③ 파급계수 없는 동인 ─────────────────────────────────────────────────────
def driver_without_impacts_is_not_silence() -> Tuple[str, str]:
    """미리보기 경로. 계수가 없으면 «빈 결과 + 경고» 여야 한다 — 조용한 빈 값이면 FAIL."""
    from core import planning_drivers as PD

    rows, warns = PD.expand_driver_assumption("COPPER_PRICE", 10.0)
    if rows:
        return LEAKED, "계수가 없는데 계정 가정 %d건이 나왔다" % len(rows)
    if not warns:
        return LEAKED, "계수도 경고도 없이 «조용한 빈 값»이다 — 사용자는 이유를 알 수 없다"
    return REFUSED, _one_line(warns[0])


def driver_without_approved_release_cannot_execute() -> Tuple[str, str]:
    """실행 경로. 미리보기와 달리 **승인 판본**을 요구해야 한다."""
    from core import planning_drivers as PD

    assumption = [{"target_kind": "driver", "target_code": "COPPER_PRICE",
                   "operator": "pct", "value": 10.0}]
    try:
        expanded, _ = PD.expand_assumptions(
            assumption, tenant_id="tenant_default", scope_node_id="hq", entity_mode="REAL")
    except PD.PlanningError as exc:
        return BLOCKED, _one_line(exc)
    if expanded:
        return LEAKED, "승인 판본 없이 계정 가정 %d건이 실행 경로로 흘렀다" % len(expanded)
    return LEAKED, "승인 판본이 없는데 예외도 경고도 없이 «조용히» 빈 결과가 됐다"


# ── ④ 등급 미달 ─────────────────────────────────────────────────────────────
def grade_shortfall_gives_no_value() -> Tuple[str, str]:
    from core import planning_drivers as PD

    r = PD.resolve_external_change("COPPER_PRICE", purpose="baseline_plan",
                                   baseline_value=4471.79)
    if r.get("usable"):
        return LEAKED, "silver 원천이 baseline_plan 에 값을 줬다: %s" % r.get("observed_value")
    if r.get("pct_change") == 0:
        return LEAKED, "0% 로 대체했다 — 0% 는 «변화 없음»이라는 주장이다"
    return REFUSED, _one_line("%s / %s" % (r.get("reason"), r.get("note")))


def grade_sufficient_still_needs_a_baseline() -> Tuple[str, str]:
    """★ 반대편 — 등급이 되더라도 «무엇 대비» 없이 변화율을 만들면 안 된다."""
    from core import planning_drivers as PD

    r = PD.resolve_external_change("COPPER_PRICE", purpose="scenario", baseline_value=None)
    if r.get("pct_change") is not None:
        return LEAKED, "기준값 없이 변화율 %s 를 만들어 냈다" % r.get("pct_change")
    return REFUSED, _one_line(r.get("reason"))


# ── ⑤ 한쪽 자료만 있을 때 오차를 재는가 ─────────────────────────────────────
def one_sided_data_is_not_measured() -> Tuple[str, str]:
    from core import planning_backtest as BT

    out = BT.backtest_plan("__probe_x4_no_such_org__", "2099-01")
    if out.get("measurable"):
        return LEAKED, "자료가 없는데 측정했다: %s" % _one_line(out)
    if out.get("mape") is not None:
        return LEAKED, "측정 불가인데 MAPE 가 %s 로 나왔다" % out.get("mape")
    return REFUSED, _one_line("%s / %s" % (out.get("reason"), out.get("note")))


# ── ⑥ 구성요소가 없을 때 0 으로 채우는가 ────────────────────────────────────
def missing_components_are_not_zero() -> Tuple[str, str]:
    from core import planning_engine as PE

    out = PE.cash_flow_for("__probe_x4_no_such_org__", "2099-01")
    if out.get("computable"):
        return LEAKED, "값이 없는데 계산했다: %s" % _one_line(out)
    if not out.get("missing"):
        return LEAKED, "계산 불가인데 «무엇이 없는지»를 말하지 않는다"
    return REFUSED, _one_line("missing=%s / %s" % (out.get("missing"), out.get("note")))


# ── ⑦ 안 붙은 것을 조용히 버리는가 ──────────────────────────────────────────
def unapplied_assumptions_are_reported() -> Tuple[str, str]:
    from core.planning_engine import apply_assumptions

    facts = [{"account_code": "5000", "amount": 100.0}]
    ghost = [{"target_kind": "account", "target_code": "NO_SUCH_ACCOUNT",
              "operator": "pct", "value": 10.0}]
    applied, unapplied = apply_assumptions(facts, ghost)
    if not unapplied:
        return LEAKED, "없는 계정에 건 가정이 «조용히» 사라졌다 — 사용자는 적용된 줄 안다"
    if applied[0]["amount"] != 100.0:
        return LEAKED, "적용되지 않았다면서 값이 바뀌었다: %s" % applied[0]["amount"]
    return REFUSED, "unapplied=%s (기준선은 그대로 %s)" % (unapplied, applied[0]["amount"])


def unmapped_accounts_are_reported() -> Tuple[str, str]:
    from core.planning_engine import compute_pl

    facts = [{"account_code": "__probe_x4_unknown__", "amount": 999.0}]
    out = compute_pl(facts, accounts={})
    if not out.get("unmapped"):
        return LEAKED, "등록되지 않은 계정의 금액이 «조용히» 빠졌다: %s" % _one_line(out)
    return REFUSED, "unmapped=%s" % _one_line(out.get("unmapped"))


PROBES: List[Tuple[str, str, Callable[[], Tuple[str, str]]]] = [
    ("①", "기준선 없이 계산을 시킨다", no_baseline_no_math),
    ("②", "입력값 5개를 빼고 계산을 시킨다", missing_base_values_are_not_defaulted),
    ("③-a", "파급계수 0건인 동인을 «미리보기» 한다", driver_without_impacts_is_not_silence),
    ("③-b", "승인 판본 없는 동인을 «실행» 시킨다", driver_without_approved_release_cannot_execute),
    ("④-a", "silver 원천을 기준계획 용도로 부른다", grade_shortfall_gives_no_value),
    ("④-b", "기준값 없이 변화율을 요구한다", grade_sufficient_still_needs_a_baseline),
    ("⑤", "계획·실적이 없는 조직의 오차를 잰다", one_sided_data_is_not_measured),
    ("⑥", "값이 없는 조직의 현금흐름을 부른다", missing_components_are_not_zero),
    ("⑦-a", "없는 계정에 가정을 건다", unapplied_assumptions_are_reported),
    ("⑦-b", "등록되지 않은 계정의 금액을 합산시킨다", unmapped_accounts_are_reported),
]


def main() -> int:
    findings = [probe(item, what, fn) for item, what, fn in PROBES]
    leaked = [f for f in findings if f.verdict == LEAKED]
    errors = [f for f in findings if f.verdict == ERROR]

    body = io.StringIO()
    body.write("# X-4 결과 — 「데이터 없이 시뮬레이션을 약속하기」를 일으키려 했다\n\n")
    body.write("> 자동 생성: `tests/probe_x4_simulation.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    body.write("> 판정 규칙(계획 §6): 통과 = 함정이 «재현되지 않음». 증거는 실행 결과여야 한다.\n\n")
    body.write("    시도 %d건 · 막힘/거부 %d건 · **샘 %d건** · 탐침 오류 %d건\n\n"
               % (len(findings), len(findings) - len(leaked) - len(errors), len(leaked), len(errors)))
    body.write("| | 무엇을 시켰나 | 결과 | 사용자가 보게 될 문장 |\n|---|---|---|---|\n")
    for f in findings:
        body.write(f.line() + "\n")
    body.write("\n---\n\n## 판정\n\n")
    if errors:
        body.write("⚠️ **탐침 자신이 %d건 실패했다.** 그 항목은 판정에 쓰지 않는다 — "
                   "「모른다」이지 「통과」가 아니다.\n\n" % len(errors))
    if leaked:
        body.write("### ⚠️⚠️ X-4 **실패** — 함정이 재현됐다\n\n")
        for f in leaked:
            body.write("- **%s %s** → %s\n" % (f.item, f.what, f.evidence))
    else:
        body.write("### X-4 **통과** — 열 가지 시도가 전부 막혔다\n\n")
        body.write("★ 중요한 것은 «막혔다» 가 아니라 **막을 때 뭐라고 말하는가** 다. "
                   "위 표의 마지막 칸이 사용자가 실제로 보게 될 문장이다. "
                   "전부 「왜 못 하는지」와 「무엇이 없는지」를 말하고 있고, "
                   "**어느 것도 0 으로 대체하지 않았다.**\n")
    body.write("\n⚠️ 이 결과가 «주장하지 않는» 것: 화면이 이 문장들을 실제로 그리는지는 "
               "여기서 알 수 없다. 서버가 거부해도 화면이 «값 없음»으로만 그리면 "
               "사용자에게는 같은 함정이다 — 그 확인은 Codex 레인이다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(body.getvalue())

    print(body.getvalue())
    print("기록:", REPORT)
    return 1 if leaked or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
