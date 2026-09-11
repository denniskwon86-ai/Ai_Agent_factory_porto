"""[F-8] 전 구간 관통 — **실물 데이터로 어디까지 가는가.**

## ★★★ 이 탐침의 판정 규칙은 다른 것과 «반대» 다

계획 §4 F-8: 「**PASS 조건은 완주가 아니라 「막히는 지점과 이유가 명확히 드러남」이다.**
지금 제품이 실물로 어디까지 가는지 **정직하게 기록**하는 것이 목적이다」.

그래서 어휘를 이렇게 둔다:

    흐름        실물이 이 이음매를 지나갔다
    막힘·설명   막혔고 **제품이 이유와 다음 행동을 말해 준다**       ← 이것도 PASS 다
    막힘·침묵   막혔는데 **왜인지 말해 주지 않는다**                ← ⚠️ 이것이 FAIL 이다
    미확인      이 탐침으로는 알 수 없다

⚠️ 「막혔으니 실패」로 세면 안 된다. 인증 종점이 하나뿐인 것은 **의도된 설계**이고,
  그 의도를 결함으로 보고하면 다음 사람이 그것을 «고쳐» 버린다.

## F-1·F-2·F-5 도 여기서 함께 걷는다

F-8 은 나머지 F 이음매의 **상위 집합**이다. 따로 걸으면 같은 것을 두 번 세게 된다.

## ⚠️ 운영 DB 는 읽기만 한다
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "F8_REAL_WALK.md")
LIVE_DATA = os.path.join(PROJECT_ROOT, "data")

FLOWS = "흐름"
BLOCKED_EXPLAINED = "막힘·설명"
BLOCKED_SILENT = "막힘·침묵"
UNKNOWN = "미확인"
ERROR = "탐침 오류"
PASSING = (FLOWS, BLOCKED_EXPLAINED)

#: 자동 실행기. **도메인으로 거르지 않는다** — `.invalid` 에는 의도된 합성 행위자도 있다.
AUTOMATION_ACTORS = ("owner@afs.invalid", "runner@afs.invalid")

KIT_INSTANCE = "ki_6b06ffb50a994a"


def ro(name: str) -> sqlite3.Connection:
    path = os.path.join(LIVE_DATA, name).replace("\\", "/")
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def count(db: str, table: str, where: str = "") -> int:
    try:
        conn = ro(db)
    except sqlite3.Error:
        return -1
    try:
        sql = 'SELECT COUNT(*) FROM "%s"' % table + (" WHERE " + where if where else "")
        return int(conn.execute(sql).fetchone()[0])
    except sqlite3.Error:
        return -1
    finally:
        conn.close()


class Seam:
    def __init__(self, seam: str, verdict: str, fact: str):
        self.seam, self.verdict, self.fact = seam, verdict, fact

    def line(self) -> str:
        mark = {FLOWS: "→  ", BLOCKED_EXPLAINED: "✋ ", BLOCKED_SILENT: "⚠️ ",
                UNKNOWN: "?  "}.get(self.verdict, "?? ")
        return "| %s | %s%s | %s |" % (self.seam, mark, self.verdict,
                                       self.fact.replace("|", "/")[:230])


def walk(seam: str, fn: Callable[[], Tuple[str, str]]) -> Seam:
    try:
        verdict, fact = fn()
    except Exception:                       # noqa: BLE001
        return Seam(seam, ERROR, traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Seam(seam, verdict, fact)


# ── F-1 의도 → 데이터 정의 ──────────────────────────────────────────────────
def f1_intent_to_data() -> Tuple[str, str]:
    """수용 기준: 산출물이 「무엇이 필요한지」의 **구체적 목록**이다."""
    reqs = count("advisor.db", "blueprint_data_requirements")
    bps = count("advisor.db", "solution_blueprints")
    cons = count("advisor.db", "consultations")
    if reqs <= 0:
        return BLOCKED_SILENT, "데이터 요구 0건 — 의도가 «데이터 목록» 이 된 적이 없다"
    conn = ro("advisor.db")
    try:
        sample = conn.execute(
            "SELECT * FROM blueprint_data_requirements LIMIT 1").fetchone()
    finally:
        conn.close()
    #: ⚠️ [2026-09-11] 처음에 `name`·`title` 같은 «있을 법한» 열 이름을 추측해 표본이
    #:   「이름 열 없음」으로 나왔다. 실제 열은 `canonical_term`·`req_key` 다 —
    #:   **먼저 물어보고 쓴다**(계측기를 추측으로 만들지 않는다).
    row = dict(sample) if sample else {}
    detail = "%s(%s) · 필요도 %s · 담당 %s" % (
        row.get("canonical_term") or "?", row.get("req_key") or "?",
        row.get("necessity") or "?", row.get("owner_department") or "미지정")
    return FLOWS, ("상담 %d · 청사진 %d → 데이터 요구 **%d건**. 표본: «%s» — "
                   "일반론이 아니라 «이름·필요도·담당» 이 붙은 목록이다"
                   % (cons, bps, reqs, detail))


# ── F-2 데이터 정의 → 연계 ──────────────────────────────────────────────────
def f2_data_to_connection() -> Tuple[str, str]:
    """수용 기준: 부족한 계약마다 **다음 행동과 담당자**가 붙는다."""
    from core.data_preparation import readiness as R
    from core.data_preparation.store import data_preparation_store as DP

    binds = count("data_preparation.db", "source_bindings")
    jobs = count("external_intelligence.db", "data_acquisition_jobs")
    if binds <= 0:
        return BLOCKED_SILENT, "원천 결속 0건 — 「어디서 가져올지」가 정해진 적이 없다"

    #: ★ 「준비되지 않음에서 끝나지 않는가」를 **실제로 눌러 본다.**
    snaps = [s for s in DP.list_snapshots(KIT_INSTANCE)
             if s["dataset_contract_key"] == "EXT-02"]
    binding = [b for b in DP.list_bindings(KIT_INSTANCE)
               if b["dataset_contract_key"] == "EXT-02"][0]
    real_only = [s for s in snaps if s.get("data_kind") == "REAL"]
    verdict = R.evaluate_dataset("EXT-02", binding=binding, snapshots=real_only,
                                 now="2026-09-11T00:00:00Z")
    #: ⚠️ [2026-09-11 정정] 「다음 행동이 비었다 = 침묵」으로 뒀다가 틀렸다(계측기 10번째).
    #:   `READY` 는 «막혔는데 말을 안 하는» 상태가 아니라 **안 막힌** 상태다 — 다음 행동이
    #:   없는 게 정상이다. 실물이 인증 종점에 닿을 일이 없다고 가정한 논리였다.
    state = str(verdict.get("state") or "")
    action = str(verdict.get("next_action") or "")
    if state == "READY":
        return FLOWS, ("결속 %d · 수집 작업 %d. EXT-02 실물이 `READY` 다 — "
                       "막히지 않았으므로 다음 행동이 없는 것이 정상이다" % (binds, jobs))
    if not action:
        return BLOCKED_SILENT, "준비 안 된 계약에 «다음 행동» 이 비어 있다: %s" % state
    return FLOWS, ("결속 %d · 수집 작업 %d. 부족한 계약(EXT-02 실물)에 실제로 "
                   "다음 행동이 붙는다 — 상태 `%s` → 「%s」" % (binds, jobs, state, action))


# ── F-3 연계 → 생성  ★ 오늘 이은 곳 ────────────────────────────────────────
def f3_connection_to_generation() -> Tuple[str, str]:
    """★★★ 2026-09-11 에 선택지 B 로 이었다. **실물이 어디서 멈추는가.**"""
    from core.data_preparation import readiness as R
    from core.data_preparation.store import data_preparation_store as DP

    snaps = [s for s in DP.list_snapshots(KIT_INSTANCE)
             if s["dataset_contract_key"] == "EXT-02"]
    real = [s for s in snaps if s.get("data_kind") == "REAL"]
    demo = [s for s in snaps if s.get("data_kind") != "REAL"]
    if not real:
        return BLOCKED_SILENT, "EXT-02 에 실물 판이 없다 — F-3(B) 가 적재되지 않았다"

    binding = [b for b in DP.list_bindings(KIT_INSTANCE)
               if b["dataset_contract_key"] == "EXT-02"][0]
    only_real = R.evaluate_dataset("EXT-02", binding=binding, snapshots=real,
                                   now="2026-09-11T00:00:00Z")
    both = R.evaluate_dataset("EXT-02", binding=binding, snapshots=snaps,
                              now="2026-09-11T00:00:00Z")
    state = str(only_real.get("state") or "")
    action = str(only_real.get("next_action") or "")
    if state == "READY":
        #: ★★★ [2026-09-11] 여기가 F-8 이 「막힌다」고 기록했던 바로 그 지점이다.
        #:   `SOURCE_CERTIFIED`(승인된 공개 원천 전용 종점)를 열어 «흐르게» 됐다.
        return FLOWS, ("실물 %d행이 `%s` 로 인증되어 준비도 `READY` 다 — "
                       "인증판만 읽는 기준선·계산·색인이 이제 이 자료를 «본다». "
                       "시연 판 %d개와 섞이지 않고 나란히 있다"
                       % (real[0].get("row_count", 0), real[0].get("state"), len(demo)))
    if not action:
        return BLOCKED_SILENT, "실물 판이 «%s» 인데 다음 행동이 없다" % state

    #: ⚠️⚠️ 더 날카로운 사실 — 실물을 올려도 준비도는 **시연 판을 가리킨다.**
    mixed_note = ""
    if str(both.get("state")) == "READY" and str(both.get("data_kind")) != "REAL":
        mixed_note = (" ⚠️ 다만 둘을 함께 주면 준비도는 `READY` 이고 그때 가리키는 판은 "
                      "**시연 판**(`%s`·%s)이다 — 응답이 `data_kind` 를 함께 주므로 "
                      "화면이 그것을 «반드시» 표시해야 한다"
                      % (both.get("snapshot_id"), both.get("data_kind")))
    return BLOCKED_EXPLAINED, ("실물 %d행이 `%s` 까지 갔고 거기서 멈춘다 — 「%s」. "
                               "시연 판 %d개와 **섞이지 않고 나란히** 있다.%s"
                               % (real[0].get("row_count", 0), only_real.get("state"),
                                  action, len(demo), mixed_note))


# ── F-4 생성 → 운영·승인·공유 ──────────────────────────────────────────────
def f4_generation_to_operation() -> Tuple[str, str]:
    releases = count("app_data.db", "app_release_dataset_bindings")
    deliveries = count("collaboration.db", "app_deliveries")
    if releases <= 0:
        return BLOCKED_SILENT, "앱 릴리스 데이터 결속이 0건"
    if deliveries == 0:
        return BLOCKED_EXPLAINED, ("릴리스 데이터 결속 %d건은 있으나 **전달 0건** — "
                                   "경로는 검증됐고(§9-E) 아직 «안 썼을» 뿐이다" % releases)
    return FLOWS, "릴리스 결속 %d · 전달 %d건" % (releases, deliveries)


# ── F-5 운영 → 전사 축적 ───────────────────────────────────────────────────
def f5_operation_to_accumulation() -> Tuple[str, str]:
    """수용 기준: **다음 프로젝트가 그것을 찾아 쓸 수 있다.**"""
    pubs = count("collaboration.db", "publications")
    approved = count("collaboration.db", "publications", "status='APPROVED'")
    ledger = count("decision_ledger.db", "decision_ledger_events")
    if pubs <= 0:
        return BLOCKED_SILENT, "발간물 0건 — 부서 산출물이 전사 자산이 된 적이 없다"
    if approved <= 0:
        return BLOCKED_EXPLAINED, ("발간물 %d건 중 **승인 0건** — 렌더까지만 갔다. "
                                   "찾아 쓸 수 있으려면 승인이 필요하다" % pubs)
    return FLOWS, ("발간물 %d건(승인 **%d건**) · 원장 %d건. 다음 프로젝트가 찾을 수 있는 "
                   "형태로 남아 있다" % (pubs, approved, ledger))


# ── F-6 축적 → 비교  ★ 실물이 흐른다 ──────────────────────────────────────
def f6_accumulation_to_comparison() -> Tuple[str, str]:
    from core.external_intelligence import external_intelligence as ei

    obs = count("external_intelligence.db", "external_observations")
    drivers = count("planning.db", "plan_drivers")
    if obs <= 0:
        return BLOCKED_SILENT, "관측값 0건"
    if drivers <= 0:
        return BLOCKED_SILENT, "계획 동인 0건 — 관측값이 계획에 닿지 않는다"
    scen = ei.resolve_value("WB_COPPER", purpose="scenario")
    base = ei.resolve_value("WB_COPPER", purpose="baseline_plan")
    if not scen.get("allowed"):
        return BLOCKED_SILENT, "시나리오 용도조차 막힌다: %s" % scen.get("reason")
    return FLOWS, ("관측값 **%d건**(실물) · 동인 %d건. 시나리오 용도는 열린다"
                   "(구리 %s). ✋ 기준계획은 등급으로 막히고 이유를 말한다 — 「%s」"
                   % (obs, drivers, scen.get("value"),
                      str(base.get("reason") or "")[:60]))


# ── F-7 비교 → 경영 의사결정 ───────────────────────────────────────────────
def f7_comparison_to_decision() -> Tuple[str, str]:
    conn = ro("collaboration.db")
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM decision_cases")]
        actions = int(conn.execute("SELECT COUNT(*) FROM decision_actions").fetchone()[0])
    finally:
        conn.close()
    real = [r for r in rows if r.get("created_by") not in AUTOMATION_ACTORS]
    decided = [r for r in real if (r.get("decided_by") or "").strip()]
    measured = [r for r in real if str(r.get("status")) == "EFFECT_MEASURED"]
    if not real:
        return BLOCKED_SILENT, "실제 계정 안건 0건"
    return FLOWS, ("실제 계정 안건 **%d건** → 결정 %d → 효과측정 %d · 실행과제 %d건. "
                   "(전체 %d건 중 %d건은 자동 실행기 소유라 제외했다)"
                   % (len(real), len(decided), len(measured), actions,
                      len(rows), len(rows) - len(real)))


# ── F-8 종합 ───────────────────────────────────────────────────────────────
def f8_summary() -> Tuple[str, str]:
    """★ 실물이 «어디까지» 갔는가 — 한 문장."""
    from core.data_preparation.store import data_preparation_store as DP

    real_snaps = [s for s in DP.list_snapshots(KIT_INSTANCE)
                  if s.get("data_kind") == "REAL"]
    obs = count("external_intelligence.db", "external_observations")
    #: ★ 실물 판이 «인증 종점» 에 닿았는지로 갈린다.
    from core.data_preparation import models as dpm
    certified = [s for s in real_snaps if dpm.is_certified(s.get("state"))]
    if certified:
        return FLOWS, (
            "실물이 **① 수집 → ② 승격(관측값 %d건) → ③ 계획 동인 → ④ 시나리오 계산 → "
            "⑤ 업무키트 스냅샷 `%s`(%d판)** 까지 **끝까지 흐른다.** "
            "⚠️ 다만 이 인증은 «발행 기관이 따로 있는 공표 자료» 전용이다 — "
            "**회사 실적(자사 매출·원가·생산)에는 여전히 인증 종점이 없고**, 그것은 "
            "실제 Data Owner 가 서명하는 일이라 코드가 열 수 있는 것이 아니다"
            % (obs, certified[0].get("state"), len(certified)))
    return BLOCKED_EXPLAINED, (
        "실물은 **① 수집 → ② 승격(관측값 %d건) → ③ 계획 동인 → ④ 시나리오 계산**까지 "
        "돌고, **⑤ 업무키트 스냅샷(%d판)** 에서 멈춘다. 제품이 그 이유를 문장으로 말한다 — "
        "**이것이 F-8 의 PASS 조건이다**" % (obs, len(real_snaps)))


SEAMS: List[Tuple[str, Callable[[], Tuple[str, str]]]] = [
    ("F-1 의도 → 데이터 정의", f1_intent_to_data),
    ("F-2 데이터 정의 → 연계", f2_data_to_connection),
    ("F-3 연계 → 생성", f3_connection_to_generation),
    ("F-4 생성 → 운영·승인", f4_generation_to_operation),
    ("F-5 운영 → 전사 축적", f5_operation_to_accumulation),
    ("F-6 축적 → 비교", f6_accumulation_to_comparison),
    ("F-7 비교 → 의사결정", f7_comparison_to_decision),
    ("**F-8 실물 종합**", f8_summary),
]


def main() -> int:
    found = [walk(s, f) for s, f in SEAMS]
    silent = [x for x in found if x.verdict == BLOCKED_SILENT]
    errors = [x for x in found if x.verdict == ERROR]
    flowing = [x for x in found if x.verdict == FLOWS]
    stopped = [x for x in found if x.verdict == BLOCKED_EXPLAINED]

    b = io.StringIO()
    b.write("# F-8 — 실물 데이터로 전 구간을 걸었다\n\n")
    b.write("> 자동 생성: `tests/probe_f8_real_walk.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    b.write("> ★★★ **PASS 조건이 다른 트랙과 반대다**(계획 §4 F-8): "
            "「완주」가 아니라 **「막히는 지점과 이유가 명확히 드러남」**이다.\n")
    b.write("> 그래서 `막힘·설명` 은 **통과**이고, `막힘·침묵` 만 실패다.\n\n")
    b.write("    이음매 %d개 · 흐름 %d · 막힘·설명 %d · **막힘·침묵 %d** · 탐침 오류 %d\n\n"
            % (len(found), len(flowing), len(stopped), len(silent), len(errors)))
    b.write("| 이음매 | 판정 | 사실 |\n|---|---|---|\n")
    for x in found:
        b.write(x.line() + "\n")

    b.write("\n---\n\n## 판정\n\n")
    if errors:
        b.write("⚠️ **탐침 자신이 %d건 실패했다** — 「모른다」이지 「통과」가 아니다.\n\n" % len(errors))
    if silent:
        b.write("### ⚠️⚠️ F-8 **실패** — 막혔는데 «왜인지 말해 주지 않는» 곳\n\n")
        for x in silent:
            b.write("- **%s** → %s\n" % (x.seam, x.fact))
    else:
        b.write("### F-8 **통과** — 막히는 곳마다 제품이 이유를 말한다\n\n")
        b.write("★ 이것이 계획이 요구한 것이다. 「실물이 끝까지 간다」가 아니라 "
                "**「어디서 왜 멈추는지 사람이 알 수 있다」**.\n")
    b.write("\n## ⚠️ 이 걸음이 «주장하지 않는» 것\n\n")
    b.write("- **화면이 이 사실들을 보여 주는지는 모른다.** 특히 F-3 의 "
            "「준비도는 `READY` 인데 가리키는 판은 시연」 — 응답이 `data_kind` 를 함께 주지만 "
            "화면이 그것을 안 그리면 사용자는 실물이 올라간 줄 안다(Codex 레인).\n")
    b.write("- F-1·F-5 의 자료 중 일부는 **시연 계보**다. 실물로 표시된 것은 "
            "관측값 240건과 EXT-02 스냅샷뿐이다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(b.getvalue())
    print(b.getvalue())
    print("기록:", REPORT)
    return 1 if silent or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
