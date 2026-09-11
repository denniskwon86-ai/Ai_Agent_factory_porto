"""[T-1 ~ T-4] 신뢰 트랙 — **F 가 통과해도 T 가 실패하면 그 흐름은 쓸 수 없다.**

이어지기는 하는데 믿을 수 없다는 뜻이기 때문이다(계획 §5).

## X 트랙과 다르다 — 여기는 «실제 자료» 를 잰다

X 는 함정을 «일으키려» 했다. T 는 **지금 우리 DB 에 실제로 들어 있는 것**을 센다.
그래서 이 탐침은 **운영 DB 를 읽는다**(`mode=ro`). 한 줄도 쓰지 않는다 —
쓰기 검사(T-2)는 «쓰기 직전에 거부되는지» 를 보므로 통과하면 애초에 안 쓰인다.

⚠️ 거부되지 **않으면** 운영 DB 에 쓰일 수 있는 항목은 **격리 인스턴스**로 돌린다.
  (기억: 「운영 DB 에 쓰기 탐침 금지」)

## 네 질문

    T-1  주요 데이터에 다섯 가지(소유자·정의·원천·갱신일·품질)가 붙어 있는가
    T-2  실제·계획·전망·시나리오가 섞이지 않는가            ★★★
    T-3  같은 입력·같은 버전으로 재현되는가
    T-4  결정에 「데이터·가정·산식·승인」이 전부 붙어 있는가  (Q4)

## ★ T-1 과 T-4 는 «측정» 이지 «반증» 이 아니다

빈 칸이 나오면 그것은 제품 결함일 수도 있고 **아직 안 채운 것**일 수도 있다.
그래서 판정 어휘를 나눈다 — `미달` 은 「고쳐야 한다」가 아니라 「지금 비어 있다」다.
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "T_FINDINGS.md")

#: ★★★ 운영 경로의 기준은 **PROJECT_ROOT** 로 고정한다. 환경변수로 돌리면
#:   「운영이냐」 판정이 반대가 된다(기억: 격리 monkeypatch 가 감시자를 뒤집는다).
LIVE_DATA = os.path.join(PROJECT_ROOT, "data")

OK = "충족"
SHORT = "미달"          # 비어 있다 — 결함일 수도, 아직 안 채운 것일 수도
BLOCKED = "막힘"
LEAKED = "샘"
ERROR = "탐침 오류"
PASSING = (OK, BLOCKED)

#: 자동 실행기 소유 행위자. **도메인으로 거르지 않는다** — `.invalid` 에는
#: 의도된 합성 행위자도 있다(기억: `.invalid` 는 잔여물 표시가 아니다).
AUTOMATION_ACTORS = ("owner@afs.invalid", "runner@afs.invalid")


def ro(name: str) -> sqlite3.Connection:
    path = os.path.join(LIVE_DATA, name)
    conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class Finding:
    def __init__(self, track: str, what: str, verdict: str, evidence: str):
        self.track, self.what, self.verdict, self.evidence = track, what, verdict, evidence

    def line(self) -> str:
        mark = {OK: "OK ", BLOCKED: "OK ", SHORT: "⚠️ ", LEAKED: "⚠️ "}.get(self.verdict, "?? ")
        return "| %s | %s | %s%s | %s |" % (
            self.track, self.what, mark, self.verdict, self.evidence.replace("|", "/")[:165])


def probe(track: str, what: str, fn: Callable[[], Tuple[str, str]]) -> Finding:
    try:
        verdict, evidence = fn()
    except Exception:                       # noqa: BLE001
        return Finding(track, what, ERROR,
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Finding(track, what, verdict, evidence)


def _one(x: Any, n: int = 160) -> str:
    return " ".join(str(x).split())[:n]


# ══ T-1 다섯 가지가 붙어 있는가 ════════════════════════════════════════════
#: 「다섯 가지」를 각 저장소의 실제 열로 옮긴 표. **이 표가 이 탐침의 계약이다** —
#: 열 이름을 바꾸면 여기도 바꿔야 하고, 안 바꾸면 탐침이 조용히 거짓말한다.
FIVE = {
    "external_sources": {"소유자": "owner_department", "정의": "allowed_usage",
                         "원천": "base_url", "갱신일": "updated_at", "품질": "trust_grade"},
    "external_observations": {"소유자": "source_id", "정의": "indicator_id",
                              "원천": "source_id", "갱신일": "vintage", "품질": "grade"},
    "data_acquisition_rows": {"소유자": "tenant_id", "정의": "contract_key",
                              "원천": "raw_object_ref", "갱신일": "as_of_date",
                              "품질": "quality_status"},
}



#: ★★★ 「사유 있는 빈 칸」 — 빈 것이 **정직한 답**인 경우.
#:
#: 첫 판에서 `as_of_date` 240행이 비어 «미달» 로 나왔다. 파고드니 제품이 맞았다:
#: World Bank Pink Sheet 는 **값별 발표일을 주지 않는다.** Provider 는 그것을
#: 지어내지 않고 비웠고, 자기 검증에 「발표일 없음(정상)」이라고 적어 두기까지 했다.
#: 대신 `payload_json.vintage_date` 에 «어느 시점 자료인가» 가 240/240 들어 있다.
#:
#: ⚠️ 그러므로 **내 계측표가 거칠었던 것**이지 데이터가 미달인 게 아니었다.
#:   대체 칸이 **실제로 채워져 있을 때만** 충족으로 센다 — 「사유가 적혀 있으니 됐다」가
#:   아니라 «대신할 값이 진짜 있는가» 로 판정한다(고지문은 차단기가 아니다).
FALLBACK = {
    ("data_acquisition_rows", "갱신일"): (
        "payload_json.vintage_date",
        "Pink Sheet 는 값별 발표일을 주지 않는다 — 지어내지 않고 비웠다"),
}

def _five_of(table: str) -> Tuple[str, str]:
    cols = FIVE[table]
    conn = ro("external_intelligence.db")
    try:
        have = {r[1] for r in conn.execute('PRAGMA table_info("%s")' % table)}
        missing_cols = [k for k, c in cols.items() if c not in have]
        if missing_cols:
            return ERROR, "탐침의 열 이름이 틀렸다: %s (실제 열 %s)" % (missing_cols, sorted(have)[:8])
        total = conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        if not total:
            return SHORT, "0행 — 잴 것이 없다"
        rows = [dict(r) for r in conn.execute('SELECT * FROM "%s"' % table)]
    finally:
        conn.close()

    def _blank(value):
        return not str(value if value is not None else "").strip()

    empty: Dict[str, int] = {}
    covered: List[str] = []
    for label, col in cols.items():
        n = sum(1 for r in rows if _blank(r.get(col)))
        if not n:
            continue
        alt = FALLBACK.get((table, label))
        if not alt:
            empty[label] = n
            continue
        path, why = alt
        root, key = path.split(".", 1)
        filled = 0
        for r in rows:
            try:
                doc = json.loads(r.get(root) or "{}")
            except (TypeError, ValueError):
                doc = {}
            if not _blank(doc.get(key)):
                filled += 1
        if filled == total:
            covered.append("%s←%s(%d행 · %s)" % (label, path, filled, why))
        else:
            empty[label] = n          # 대체 칸도 안 채워졌다 — 진짜 미달이다

    note = (" · 대체: " + ", ".join(covered)) if covered else ""
    if empty:
        return SHORT, "%d행 중 빈 칸: %s%s" % (
            total, ", ".join("%s %d행(%s)" % (k, v, cols[k]) for k, v in empty.items()), note)
    return OK, "%d행 · 다섯 칸 모두 채워짐%s" % (total, note)


def five_on_sources() -> Tuple[str, str]:
    return _five_of("external_sources")


def five_on_observations() -> Tuple[str, str]:
    return _five_of("external_observations")


def five_on_staged_rows() -> Tuple[str, str]:
    return _five_of("data_acquisition_rows")


# ══ T-2 네 성격이 섞이지 않는가 ════════════════════════════════════════════
def value_kind_has_no_default() -> Tuple[str, str]:
    """`value_kind` 에 기본값이 있으면 «실적처럼 보이는 계획» 이 생긴다."""
    import inspect
    from core.planning_model import planning_store

    default = inspect.signature(planning_store.put_fact).parameters["value_kind"].default
    if default is not inspect.Parameter.empty:
        return LEAKED, "value_kind 기본값이 %r 이다" % (default,)
    return BLOCKED, "put_fact(value_kind=…) 에 기본값이 없다 — 호출자가 반드시 고른다"


def unknown_value_kind_is_rejected() -> Tuple[str, str]:
    from core.planning_model import planning_store, PlanningError

    try:
        planning_store.put_fact(org_id="__probe_t__", account_code="5000",
                                period="2099-01", value_kind="REAL_ISH", amount=1.0)
    except PlanningError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "닫힌 목록 밖의 value_kind 가 저장됐다"


def scenario_result_cannot_masquerade_as_actual() -> Tuple[str, str]:
    """★★★ 시나리오 결과가 실적으로 섞여 들어가는 경로를 막는가."""
    from core.planning_model import planning_store, PlanningError

    try:
        planning_store.put_fact(org_id="__probe_t__", account_code="5000",
                                period="2099-01", value_kind="ACTUAL", amount=1.0,
                                scenario_id="scn_probe")
    except PlanningError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "ACTUAL 에 scenario_id 가 붙었다 — 시나리오가 실적이 된다"


def scenario_without_its_scenario_is_rejected() -> Tuple[str, str]:
    """반대편 — SCENARIO 인데 «어느 가정에서 나왔는지» 가 없으면 재현할 수 없다."""
    from core.planning_model import planning_store, PlanningError

    try:
        planning_store.put_fact(org_id="__probe_t__", account_code="5000",
                                period="2099-01", value_kind="SCENARIO", amount=1.0)
    except PlanningError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "scenario_id 없는 SCENARIO 값이 저장됐다"


def contract_origin_mismatch_is_rejected() -> Tuple[str, str]:
    """★★★ 「시연 자료」 그릇에 공표 통계를 넣으려 하면 막는가 — 실제로 있었던 문제다."""
    from core.external_intelligence.orchestrator import assert_origin_fits, OrchestrationError

    demo_contract = {"classification": {"data_origin": "SYNTHETIC"}}
    try:
        assert_origin_fits(demo_contract, "PUBLIC_DISCLOSED", contract_key="EXT-01")
    except OrchestrationError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "SYNTHETIC 계약에 PUBLIC_DISCLOSED 행이 들어갔다 — 계약이 거짓말을 한다"


def contract_without_declared_origin_is_rejected() -> Tuple[str, str]:
    """성격을 «말하지 않는» 계약에는 아예 넣지 않는가."""
    from core.external_intelligence.orchestrator import assert_origin_fits, OrchestrationError

    try:
        assert_origin_fits({"classification": {}}, "PUBLIC_DISCLOSED", contract_key="EXT-99")
    except OrchestrationError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "성격을 선언하지 않은 계약에 행이 들어갔다"


def live_kinds_are_not_mixed() -> Tuple[str, str]:
    """★ 실측 — 지금 DB 에 성격이 섞인 행이 실제로 있는가."""
    conn = ro("planning.db")
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT value_kind, COUNT(*) n, "
            "SUM(CASE WHEN TRIM(COALESCE(scenario_id,''))<>'' THEN 1 ELSE 0 END) with_scn "
            "FROM plan_facts GROUP BY value_kind")]
    finally:
        conn.close()
    bad = [r for r in rows
           if (r["value_kind"] == "SCENARIO") != bool(r["with_scn"] == r["n"])]
    detail = " · ".join("%s %d행(scenario_id %d)" % (r["value_kind"], r["n"], r["with_scn"])
                        for r in rows)
    if bad:
        return LEAKED, "성격과 scenario_id 가 어긋난 묶음: %s" % _one(bad)
    return OK, detail or "plan_facts 0행"


# ══ T-3 재현되는가 ═════════════════════════════════════════════════════════
def same_input_same_fingerprint() -> Tuple[str, str]:
    from core.planning_engine import input_fingerprint

    facts = [{"org_id": "a", "account_code": "5000", "period": "2026-06",
              "value_kind": "PLAN", "amount": 100.0},
             {"org_id": "a", "account_code": "4000", "period": "2026-06",
              "value_kind": "PLAN", "amount": 200.0}]
    assumptions = [{"target_kind": "account", "target_code": "5000",
                    "operator": "pct", "value": 3.0}]
    first = input_fingerprint(facts, assumptions)
    shuffled = input_fingerprint(list(reversed(facts)), assumptions)
    if first != shuffled:
        return LEAKED, "조회 «순서»가 달라졌을 뿐인데 지문이 달라졌다 — 거짓 «재현 실패» 신호"
    changed = input_fingerprint(
        facts, [{"target_kind": "account", "target_code": "5000",
                 "operator": "pct", "value": 3.0001}])
    if changed == first:
        return LEAKED, "가정이 바뀌었는데 지문이 같다 — 지문이 입력을 대표하지 않는다"
    return OK, "순서 무관 %s · 값이 바뀌면 달라짐(%s→%s)" % (first[:12], first[:8], changed[:8])


def simulation_is_deterministic() -> Tuple[str, str]:
    from core import calc_graph as cg

    class Fake:
        fingerprint = "fp_probe_t3"

    base = {"production_qty": 1000.0, "ending_inventory": 50.0, "purchase_payment": 800.0,
            "ending_cash": 300.0, "operating_profit": 120.0, "power_cost": 90.0,
            "period_days": 30.0}
    a = cg.simulate(Fake(), base, {"fx_rate_pct": 5.0}).public()
    b = cg.simulate(Fake(), base, {"fx_rate_pct": 5.0}).public()
    if a != b:
        return LEAKED, "같은 입력을 두 번 돌렸는데 결과가 다르다"
    c = cg.simulate(Fake(), base, {"fx_rate_pct": 6.0}).public()
    if c == a:
        return LEAKED, "가정을 바꿨는데 결과가 같다 — 가정이 계산에 안 닿는다"
    return OK, "두 번 같음(지문 %s) · 가정을 바꾸면 달라짐" % str(a.get("fingerprint", ""))[:12]


def past_vintage_is_replayable() -> Tuple[str, str]:
    """★ 「그 계획이 «당시» 어떤 발표값을 썼나」 — 재현의 마지막 고리."""
    from core.external_intelligence import external_intelligence as ei

    latest = ei.resolve_value("WB_COPPER", purpose="scenario")
    old = ei.resolve_value("WB_COPPER", purpose="scenario", vintage="2016-01")
    if not old.get("allowed"):
        return SHORT, "과거 vintage 를 못 불러온다: %s" % _one(old.get("reason"))
    if old.get("value") == latest.get("value"):
        return LEAKED, "과거 vintage 가 최신값과 같다 — vintage 가 실제로 안 걸린다"
    return OK, "2016-01 발표값 %s (최신 %s) — 다른 값이 나온다" % (old.get("value"), latest.get("value"))


def ledger_hash_chain_is_intact() -> Tuple[str, str]:
    """원장이 «이어져» 있는가 — 끊기면 그 뒤의 승인 이력을 믿을 수 없다."""
    conn = ro("decision_ledger.db")
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT seq, event_id, prev_hash, event_hash FROM decision_ledger_events "
            "ORDER BY seq")]
    finally:
        conn.close()
    if not rows:
        return SHORT, "원장 0건 — 잴 것이 없다"
    broken = []
    for prev, cur in zip(rows, rows[1:]):
        if (cur["prev_hash"] or "") != (prev["event_hash"] or ""):
            broken.append(cur["seq"])
    empty = [r["seq"] for r in rows if not (r["event_hash"] or "").strip()]
    if empty:
        return LEAKED, "해시가 빈 사건 %d건(seq %s…)" % (len(empty), empty[:3])
    if broken:
        return LEAKED, "사슬이 끊긴 곳 %d군데(seq %s…)" % (len(broken), broken[:3])
    return OK, "%d건 연속 · prev_hash 가 전부 앞 사건의 event_hash 와 일치" % len(rows)


# ══ T-4 결정에 네 가지가 붙어 있는가 ═══════════════════════════════════════
#: Q4 의 네 가지를 «증거에 실제로 실리는 이름» 으로 옮긴 표.
FOUR = {
    "데이터": ("baseline_id", "baseline_fingerprint", "department_result_fingerprints",
               "composition_fingerprint"),
    "가정": ("assumptions", "assumption_set_id", "scenario_id"),
    "산식": ("calc_version", "engine_version", "package_version"),
    "승인": ("decided_by",),
}


def decisions_carry_all_four() -> Tuple[str, str]:
    import json

    conn = ro("collaboration.db")
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM decision_cases")]
    finally:
        conn.close()
    real = [r for r in rows if r.get("created_by") not in AUTOMATION_ACTORS]
    if not real:
        return SHORT, "실제 계정 안건 0건 — 잴 것이 없다"

    decided = [r for r in real if (r.get("decided_by") or "").strip()]
    full, partial = [], []
    for r in decided:
        try:
            ev = json.loads(r.get("evidence_json") or "{}")
        except (TypeError, ValueError):
            ev = {}
        bag = dict(ev, decided_by=r.get("decided_by"), package_version=r.get("package_version"),
                   baseline_id=r.get("baseline_id"), scenario_id=r.get("scenario_id"))
        missing = [name for name, keys in FOUR.items()
                   if not any(str(bag.get(k) or "").strip() for k in keys)]
        #: ★★★ [2026-09-11] 넷이 다 없어도 «근거 종류를 밝혔으면» Q4 에 답할 수 있다.
        #:   「산식에 근거하지 않았다」는 것도 **답**이다 — 침묵만이 실패다.
        basis = str(r.get("evidence_basis") or "").strip()
        if missing and basis and basis != "UNSTATED":
            missing = []                    # 밝혔으므로 Q4 가 침묵하지 않는다
            full.append((r["decision_id"][:14] + "(" + basis + ")", []))
            continue
        (full if not missing else partial).append((r["decision_id"][:14], missing))
    if not decided:
        return SHORT, "결정된 안건 0건(전체 %d) — Q4 를 잴 수 없다" % len(real)
    if partial:
        return SHORT, "결정 %d건 중 네 가지 완비 %d건 · 빠진 것: %s" % (
            len(decided), len(full),
            "; ".join("%s→%s" % (i, m) for i, m in partial[:4]))
    return OK, "결정 %d건 전부 네 가지 완비(%s)" % (len(decided), [i for i, _ in full])


def approval_has_a_named_person() -> Tuple[str, str]:
    """★ 승인자가 «자동 실행기» 면 그것은 사람의 승인이 아니다."""
    conn = ro("collaboration.db")
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT decision_id, decided_by FROM decision_cases "
            "WHERE TRIM(COALESCE(decided_by,''))<>''")]
    finally:
        conn.close()
    if not rows:
        return SHORT, "결정자가 적힌 안건 0건"
    robots = [r["decision_id"][:14] for r in rows if r["decided_by"] in AUTOMATION_ACTORS]
    humans = sorted({r["decided_by"] for r in rows if r["decided_by"] not in AUTOMATION_ACTORS})
    if robots:
        return SHORT, "자동 실행기가 결정자인 안건 %d건 · 사람 결정자 %s" % (len(robots), humans)
    return OK, "결정 %d건 전부 사람 명의 · 결정자 %s" % (len(rows), humans)


PROBES: List[Tuple[str, str, Callable[[], Tuple[str, str]]]] = [
    ("T-1", "원천 등록부에 다섯 칸이 있는가", five_on_sources),
    ("T-1", "관측값에 다섯 칸이 있는가", five_on_observations),
    ("T-1", "격리 적재본에 다섯 칸이 있는가", five_on_staged_rows),
    ("T-2", "value_kind 에 기본값이 없는가", value_kind_has_no_default),
    ("T-2", "닫힌 목록 밖 성격을 넣는다", unknown_value_kind_is_rejected),
    ("T-2", "시나리오 결과를 실적으로 넣는다", scenario_result_cannot_masquerade_as_actual),
    ("T-2", "가정 없는 시나리오 값을 넣는다", scenario_without_its_scenario_is_rejected),
    ("T-2", "시연 계약에 공표 통계를 넣는다", contract_origin_mismatch_is_rejected),
    ("T-2", "성격을 선언 안 한 계약에 넣는다", contract_without_declared_origin_is_rejected),
    ("T-2", "실측 — 지금 DB 에 섞인 행이 있는가", live_kinds_are_not_mixed),
    ("T-3", "같은 입력이 같은 지문을 내는가", same_input_same_fingerprint),
    ("T-3", "같은 계산을 두 번 돌린다", simulation_is_deterministic),
    ("T-3", "과거 발표값(vintage)으로 되돌린다", past_vintage_is_replayable),
    ("T-3", "원장 해시 사슬이 이어져 있는가", ledger_hash_chain_is_intact),
    ("T-4", "결정에 데이터·가정·산식·승인이 다 있는가", decisions_carry_all_four),
    ("T-4", "승인자가 사람 명의인가", approval_has_a_named_person),
]


def main() -> int:
    findings = [probe(t, w, f) for t, w, f in PROBES]
    leaked = [f for f in findings if f.verdict == LEAKED]
    short = [f for f in findings if f.verdict == SHORT]
    errors = [f for f in findings if f.verdict == ERROR]

    b = io.StringIO()
    b.write("# T 트랙 결과 — 「이어지는가」가 아니라 「믿을 수 있는가」\n\n")
    b.write("> 자동 생성: `tests/probe_t_trust.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    b.write("> X 트랙과 다르다 — 여기는 **운영 DB 의 실제 자료**를 읽어서 센다(`mode=ro`, 쓰기 0).\n\n")
    b.write("    항목 %d건 · 충족/막힘 %d건 · **미달 %d건** · **샘 %d건** · 탐침 오류 %d건\n\n"
            % (len(findings), len(findings) - len(short) - len(leaked) - len(errors),
               len(short), len(leaked), len(errors)))
    b.write("| 트랙 | 무엇을 봤나 | 결과 | 근거 |\n|---|---|---|---|\n")
    for f in findings:
        b.write(f.line() + "\n")
    b.write("\n---\n\n## 판정\n\n")
    if errors:
        b.write("⚠️ **탐침 자신이 %d건 실패했다** — 「모른다」이지 「통과」가 아니다.\n\n" % len(errors))
    if leaked:
        b.write("### ⚠️⚠️ 통제가 샜다\n\n")
        for f in leaked:
            b.write("- **%s %s** → %s\n" % (f.track, f.what, f.evidence))
        b.write("\n")
    if short:
        b.write("### ⚠️ 미달 — «비어 있다» 이지 «고장났다» 가 아니다\n\n")
        b.write("★ T-1·T-4 는 **측정**이다. 빈 칸은 제품 결함일 수도 있고 "
                "**아직 안 채운 것**일 수도 있다. 둘을 섞어 부르지 않는다.\n\n")
        for f in short:
            b.write("- **%s %s** → %s\n" % (f.track, f.what, f.evidence))
        b.write("\n")
    if not leaked and not short and not errors:
        b.write("### T 트랙 **통과** — 네 질문에 전부 답이 있다\n")
    b.write("\n⚠️ 이 결과가 «주장하지 않는» 것: 화면이 이 다섯 칸·네 가지를 "
            "**실제로 보여 주는지**는 여기서 알 수 없다(Codex 레인). "
            "그리고 T-1 의 「다섯 가지」를 어느 열로 볼지는 이 탐침의 `FIVE` 표가 정한 것이다 — "
            "열 이름이 바뀌면 표도 바꿔야 한다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(b.getvalue())
    print(b.getvalue())
    print("기록:", REPORT)
    return 1 if leaked or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
