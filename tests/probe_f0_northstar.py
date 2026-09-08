"""[F-0] 북극성 «양 끝 잇기» 탐침 — 끊긴 곳의 목록을 만든다.

    실행   venv/Scripts/python.exe -m pytest tests/probe_f0_northstar.py -q
    산출   docs/test_plan/F0_BREAKS.md   ← ★ 이것이 F-0 의 결과물이다

파일 이름이 `test_` 로 시작하지 않는다. 일부러다 — **T3 에 섞이면 안 된다.** 여기서의
실패는 「회귀」가 아니라 **「아직 안 이어진 곳」**이고, 그것이 이 파일의 산출물이다.

★★★ **F-0 의 통과 조건은 「완주」가 아니라 「끊긴 곳의 목록이 확정됨」이다.**

## ⚠️⚠️⚠️ 첫 판은 «거짓 목록»을 만들었다 — 이 파일의 가장 중요한 교훈

첫 판은 `TestClient` 로 HTTP 를 쳐서 8개 이음매 중 6개가 «비었다»고 적었다. 전부 거짓이었다.
**conftest 는 `enterprise_context.db` 하나만 복사하고 나머지는 빈 DB 를 준다.** 그래서 내가
본 것은 «제품이 못 한다»가 아니라 «격리 환경에 데이터가 없다»였다.

    격리 환경에서 본 것          운영 데이터의 실제
    ─────────────────────       ─────────────────────
    안건 0건 → 「출구가 비었다」   decision_cases  **256건** — 출구는 실제로 돌았다
    원장 0건 → 「축적 안 됨」      decision_ledger **148건**
    인스턴스 0건 → 「대상 없음」   kit_instances 1 · source_bindings 35 · snapshots 36

★ 그래서 이 탐침은 두 도구를 **용도에 따라 갈라** 쓴다:

    구조(라우트가 있는가)   `main.app` 의 라우트 — 데이터와 무관하다
    실제(무엇이 흘렀는가)   **운영 DB 읽기 전용** — 격리된 빈 DB 로는 답할 수 없다

⚠️ 운영 DB 는 **읽기만** 한다(`mode=ro`). 그리고 경로를 `PROJECT_ROOT` 로 고정한다 —
  conftest 가 `DATA_DIR` 을 tmp 로 돌려놓기 때문에 그것을 읽으면 감시자가 뒤집힌다.

## ⚠️ 이 탐침을 만들며 «내가» 틀린 것 넷

    ① /decisions/* 가 401 → 식별 헤더를 안 붙였을 뿐이다
    ② /lineage/edges 가 422 → 전역 목록이 아니라 «노드별» 조회였다
    ③ /app-deliveries/preflight 가 422 → release_id 필수. «선행 조건»이지 끊김이 아니다
    ④ ★★★ 격리 DB 를 운영 데이터로 착각해 «끊김» 6건을 지어냈다

넷 다 제품이 아니라 «재는 도구»가 틀린 것이었다.
"""
from __future__ import annotations

import datetime
import io
import os
import sqlite3

import pytest

import main
from core.paths import PROJECT_ROOT

#: ★ 격리가 아니라 **운영** 데이터를 본다. conftest 가 `DATA_DIR` 을 tmp 로 돌려놓으므로
#:   그것을 쓰면 안 된다 — 기준을 `PROJECT_ROOT` 로 고정한다.
LIVE = os.path.join(PROJECT_ROOT, "data")

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "F0_BREAKS.md")

MISSING = "MISSING"    # 이음매 자체가 없다 — 만들어야 한다
EMPTY = "EMPTY"        # 이음매는 있는데 «한 번도 흐른 적이 없다»
THIN = "THIN"          # 흐르긴 했는데 «거의 안 쓰인다»
OK = "OK"


def _count(db, table):
    """운영 DB 를 **읽기 전용**으로 센다. 표가 없으면 -1(= 그런 개념이 없다)."""
    path = os.path.join(LIVE, db)
    if not os.path.exists(path):
        return -1
    con = sqlite3.connect("file:" + path.replace(os.sep, "/") + "?mode=ro", uri=True)
    try:
        return int(con.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0])
    except sqlite3.Error:
        return -1
    finally:
        con.close()


def _routes():
    from fastapi.routing import APIRoute
    return {r.path for r in main.app.routes if isinstance(r, APIRoute)}


def _write(kind, seam, fact):
    with io.open(REPORT, "a", encoding="utf-8", newline="\n") as f:
        f.write("| `" + kind + "` | " + seam + " | " + fact + " |\n")


def _verdict(kind, seam, fact):
    _write(kind, seam, fact)
    if kind != OK:
        pytest.fail("[" + kind + "] " + seam + " — " + fact, pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def _report():
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("# F-0 — 끊긴 곳 목록\n\n")
        f.write("> 자동 생성: `tests/probe_f0_northstar.py` · "
                + str(datetime.date.today()) + "\n")
        f.write("> 구조는 라우트로, 실제 흐름은 **운영 DB 읽기 전용**으로 봤다.\n")
        f.write("> ⚠️ **손으로 고치지 말 것.** 고칠 것은 탐침이거나 제품이다.\n\n")
        f.write("| 종류 | 이음매 | 사실 |\n|---|---|---|\n")
    yield


# ── F-1  01 의도 → 02 데이터·기준 정의 ───────────────────────────────────────
def test_seam_f1():
    seam = "F-1 의도 → 데이터 정의"
    if "/api/v1/advisor/blueprints/{blueprint_id}/create-data-tasks" not in _routes():
        _verdict(MISSING, seam, "청사진을 데이터 과업으로 바꾸는 라우트가 없다.")
    reqs = _count("advisor.db", "blueprint_data_requirements")
    bps = _count("advisor.db", "solution_blueprints")
    if reqs <= 0:
        _verdict(EMPTY, seam, "청사진 데이터 요구가 0건 — 의도가 데이터 목록이 된 적이 없다.")
    _verdict(OK, seam, "청사진 " + str(bps) + "건에서 데이터 요구 " + str(reqs)
             + "건이 나왔다. 의도 → 데이터 정의가 실제로 흘렀다.")


# ── F-2  02 데이터 정의 → 03 안전한 연계 ─────────────────────────────────────
def test_seam_f2():
    seam = "F-2 데이터 정의 → 연계"
    binds = _count("data_preparation.db", "source_bindings")
    jobs = _count("external_intelligence.db", "data_acquisition_jobs")
    if binds <= 0:
        _verdict(EMPTY, seam, "원천 결속이 0건 — 「어디서 가져올지」가 정해진 적이 없다.")
    if jobs <= 0:
        _verdict(EMPTY, seam, "수집 작업이 0건 — 결속은 있으나 수집으로 이어진 적이 없다.")
    _verdict(OK, seam, "원천 결속 " + str(binds) + "건 · 수집 작업 " + str(jobs) + "건.")


# ── F-3  03 연계 → 04 생성  ★ 구조적 결함 ────────────────────────────────────
def test_seam_f3():
    seam = "F-3 연계 → 생성"
    cand = [x for x in _routes()
            if ("acquisition" in x and ("appdata" in x or "factory" in x))
            or ("appdata" in x and ("contract" in x or "acquisition" in x))]
    rows = _count("external_intelligence.db", "data_acquisition_rows")
    raws = _count("external_intelligence.db", "data_acquisition_raw_objects")
    if not cand:
        _verdict(MISSING, seam,
                 "수집 적재본을 생성 입력으로 넘기는 라우트가 **한 개도 없다**. "
                 "수집은 `data_acquisition_rows` 에, 생성은 `app_datasets` 에 산다 — "
                 "두 데이터 평면이 만나는 지점이 제품에 없다. "
                 "(참고: 수집 작업 " + str(_count("external_intelligence.db", "data_acquisition_jobs"))
                 + "건인데 적재 행 " + str(rows) + "건 · 원문 " + str(raws) + "건 — "
                 "수집이 «한 번도 완주하지 않았다»는 뜻이기도 하다.)")
    _verdict(OK, seam, "후보 라우트 " + str(len(cand)) + "개.")


# ── F-4  04 생성 → 05 부서 운영·승인·공유 ────────────────────────────────────
def test_seam_f4():
    seam = "F-4 생성 → 운영·승인"
    deliv = _count("collaboration.db", "app_deliveries")
    promo = _count("workspace.db", "release_promotions")
    if deliv <= 0:
        _verdict(EMPTY, seam,
                 "개인 앱 전달이 0건이다. 승격(`release_promotions`)은 " + str(promo)
                 + "건 있으나 «사람에게 전달된» 적은 없다 — 생성물이 부서 손에 닿지 않았다.")
    _verdict(OK, seam, "전달 " + str(deliv) + "건.")


# ── F-5  05 운영 → 06 전사 지식 축적 ─────────────────────────────────────────
def test_seam_f5():
    seam = "F-5 운영 → 축적"
    ledger = _count("decision_ledger.db", "decision_ledger_events")
    pubs = _count("collaboration.db", "publications")
    if ledger <= 0:
        _verdict(EMPTY, seam, "원장 사건이 0건 — 무엇도 축적되지 않았다.")
    _verdict(OK, seam, "원장 사건 " + str(ledger) + "건 · 발간물 " + str(pubs) + "건.")


# ── F-6  06 축적 → 07 비교  ★★★ 여기가 진짜 끊긴 곳 ─────────────────────────
def test_seam_f6():
    seam = "F-6 축적 → 비교"
    drivers = _count("planning.db", "plan_drivers")
    impacts = _count("planning.db", "driver_impacts")
    indic = _count("external_intelligence.db", "external_indicators")
    obs = _count("external_intelligence.db", "external_observations")
    if drivers <= 0:
        _verdict(MISSING, seam,
                 "**계획 동인(`plan_drivers`)이 0건이다.** 외부 지표는 " + str(indic)
                 + "건 정의돼 있으나 «붙을 자리»가 없고, 관측값도 " + str(obs) + "건이다. "
                 "→ 환율·원자재가 계획에 영향을 주는 경로가 **한 번도 연결된 적이 없다**. "
                 "경영자의 Q2(「무엇이 바뀌면 어디에 영향?」)가 여기서 막힌다.")
    _verdict(OK, seam, "동인 " + str(drivers) + "건 · 영향 " + str(impacts) + "건.")


# ── F-7  07 비교 → 08 경영 의사결정 ──────────────────────────────────────────
def test_seam_f7():
    seam = "F-7 비교 → 경영 의사결정"
    cases = _count("collaboration.db", "decision_cases")
    runs = _count("planning.db", "simulation_runs")
    actions = _count("collaboration.db", "decision_actions")
    if cases <= 0:
        _verdict(EMPTY, seam, "안건이 0건 — 비교가 결정으로 이어진 적이 없다.")
    if actions <= 0 or (cases and actions * 20 < cases):
        _verdict(THIN, seam,
                 "안건은 " + str(cases) + "건인데 **실행 지시(`decision_actions`)는 "
                 + str(actions) + "건**이다(시뮬레이션 실행 " + str(runs) + "건). "
                 "결정은 쌓이는데 «누가 언제 실행하는가»로 거의 이어지지 않는다 — "
                 "경영자의 Q3 가 사실상 비어 있다.")
    _verdict(OK, seam, "안건 " + str(cases) + "건 · 실행 지시 " + str(actions) + "건.")


# ── F-0  01 → 08  양 끝 잇기 ─────────────────────────────────────────────────
def test_seam_f0():
    seam = "F-0 양 끝 잇기 (01 → 08)"
    cons = _count("advisor.db", "consultations")
    cases = _count("collaboration.db", "decision_cases")
    if cons <= 0 or cases <= 0:
        _verdict(EMPTY, seam,
                 "상담 " + str(cons) + "건 · 안건 " + str(cases) + "건 — 한쪽이 비어 있다.")
    _verdict(OK, seam,
             "입구(상담) " + str(cons) + "건 · 출구(안건) " + str(cases) + "건. "
             "**양 끝에 «둘 다 실물이 있다»** — 다만 이 숫자만으로 «같은 흐름으로 이어졌는지»는 "
             "증명되지 않는다. 그것은 계보로 확인해야 한다(별도 과제).")
