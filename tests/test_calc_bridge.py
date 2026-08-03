"""★★★ [E3 ↔ M4] 계산 엔진 연결 — **ECM 가정 세트가 엔진 가정의 원본이다.**

## 왜 필요했나

두 세계가 나란히 있었다: ECM 가정 세트(근거·승인·동결이 붙는다)와 엔진의 자체 가정 표
(결정론적 계산을 한다). 연결이 없으면 결과를 **사람이 손으로 옮겨** 등록해야 하고, 그러면 두 곳의
가정이 조용히 달라진다 — 엔진에서는 +12%로 계산하고 ECM 기록에는 +10%로 남는 상황이 생긴다.
그때 비교표의 "근거"는 거짓이 된다.

⚠️ 같은 사실이 두 곳에 선언되면 반드시 갈라진다 — 이 저장소가 라이브러리 경로,
  `owner_org_id`/`scope_code`, 부서/코드/노드에서 반복해 겪은 실패다. 그래서 원본을 하나로 둔다.

## 이 파일이 지키는 계약

1. 규약에 맞지 않는 가정 키는 **거부한다**(조용히 무시하면 그 가정만 빠지고 결과는 정상처럼 보인다).
2. 번역이 **전부 성공한 뒤에야** 엔진에 쓴다(반쯤 만들어진 시나리오를 남기지 않는다).
3. 승인되지 않은 가정 세트로는 계산하지 않는다.
4. 계산 모델 버전이 결과에 남는다(§8.1 — 재현 가능성).
5. 반영되지 않은 가정·동인 경고를 **소리 내어** 알린다.
"""
import pytest

from core.enterprise_context.calc_bridge import (CalcBridge, CalcBridgeError,
                                                 parse_assumption_key, translate_assumptions)
from core.enterprise_context.clone_service import CloneService
from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.scenario_inputs import ScenarioInputStore

TOMORROW = "2099-12-31"
TODAY = "2026-08-03"


# ── 키 규약 ───────────────────────────────────────────────────────────────
def test_key_convention_is_parsed():
    """★ 규약: `account|driver : 코드 : pct|delta|set`."""
    assert parse_assumption_key("account:4000:pct") == ("account", "4000", "pct")
    assert parse_assumption_key("driver:ENERGY_PRICE:delta") == ("driver", "ENERGY_PRICE", "delta")


@pytest.mark.parametrize("bad", [
    "4000", "account:4000", "account:4000:multiply", "sales:4000:pct", "", "account::pct",
])
def test_bad_keys_are_refused_not_ignored(bad):
    """★★★ **이 파일의 핵심.** 규약 밖의 키를 조용히 무시하면 그 가정만 계산에서 빠지고 결과는
    정상처럼 보인다 — 사람은 12개 가정을 넣었다고 믿는데 실제로는 9개만 반영된 상태다.

    (이 저장소가 "필터를 부르지 않으면 통제가 없다"에서 배운 것과 같은 교훈이다.)"""
    with pytest.raises(CalcBridgeError, match="규약"):
        parse_assumption_key(bad)


def test_non_numeric_assumption_is_refused():
    """★★ 문자열을 숫자로 해석하면 근사값이 확정 계산의 입력이 된다."""
    with pytest.raises(CalcBridgeError, match="숫자여야"):
        translate_assumptions({"account:4000:pct": "약 12%"},
                              {"account:4000:pct": "근거"})


def test_translation_carries_the_evidence(store_free=None):
    """★★★ 근거를 함께 옮긴다 — 엔진도 `rationale` 을 필수로 요구하므로, 여기서 옮기지 않으면
    두 곳의 근거가 갈라진다."""
    rows = translate_assumptions({"account:4000:pct": 12.0},
                                 {"account:4000:pct": "에너지 계약단가 2026 상반기"})
    assert rows[0]["rationale"].startswith("에너지 계약단가")
    assert rows[0]["target_kind"] == "account" and rows[0]["operator"] == "pct"


def test_missing_evidence_is_refused_at_the_bridge_too():
    """★★ ECM 쪽에서 이미 막지만 다리에서도 확인한다 — 다리를 직접 부르는 경로가 생길 수 있다."""
    with pytest.raises(CalcBridgeError, match="근거"):
        translate_assumptions({"account:4000:pct": 12.0}, {})


# ── 실행 ──────────────────────────────────────────────────────────────────
@pytest.fixture
def wired(tmp_path):
    """ECM 저장소 + 시나리오 + 승인된 가정·기준선. 엔진은 대역으로 둔다."""
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    clone = CloneService(repository=repo)
    store = ScenarioInputStore(repository=repo, clone=clone)

    ent = repo.upsert_entity(EnterpriseEntity(entity_mode="REAL", name_ko="배터리소재 사업부"))
    repo.upsert_node(OrganizationNode(entity_id=ent.entity_id, code="MNM_BATTERY",
                                      name_ko="배터리소재", status="ACTIVE"))
    scn = clone.clone_to_virtual(ent.entity_id, "가상 증설", purpose="증설 검토",
                                 valid_until=TOMORROW, today=TODAY)

    a = store.create_assumption_set(
        "에너지가 +12%", "증설 타당성",
        {"account:4000:pct": 12.0, "driver:ENERGY_PRICE:delta": 50.0},
        {"account:4000:pct": "계약단가 2026H1", "driver:ENERGY_PRICE:delta": "전력 고시"},
        actor="hikwon")
    store.approve_assumption_set(a["assumption_set_id"], "hikwon")
    s = store.create_snapshot("2026H1 확정", "2026-06-30",
                              {"gross_profit": 1000, "operating_profit": 500},
                              source="ERP 집계 승인본", actor="hikwon")
    store.approve_snapshot(s["snapshot_id"], "hikwon")
    return {"repo": repo, "clone": clone, "store": store, "scn": scn, "asm": a, "snap": s}


class _FakeEngine:
    """엔진 대역 — 실물과 **같은 반환 모양**을 준다(`result`·`unapplied_assumptions`·`input_hash`).

    ⚠️ 대역이 실물과 다르면 그 테스트는 실물이 아니라 대역을 검증한다 — 이 저장소가 이미 겪은
      실패이므로 키 이름을 실물에서 그대로 가져왔다."""
    def __init__(self, unapplied=None, warnings=None, result=None):
        self.calls = []
        self._unapplied = unapplied or []
        self._warnings = warnings or []
        self._result = result if result is not None else {
            "gross_profit": 1120.0, "operating_profit": 560.0, "net_profit": 400.0}

    def run_scenario(self, scenario_id, org_id, period, baseline_kind="PLAN", persist=False):
        self.calls.append({"scenario_id": scenario_id, "org_id": org_id, "period": period,
                           "baseline_kind": baseline_kind, "persist": persist})
        return {"run_id": "run_abc", "engine_version": "1.0.0", "input_hash": "hash_xyz",
                "baseline": {"gross_profit": 1000.0}, "result": dict(self._result),
                "unapplied_assumptions": list(self._unapplied),
                "driver_warnings": list(self._warnings)}


class _FakePlanningStore:
    """엔진 시나리오·가정 표 대역. 실제 sqlite 를 쓰되 최소 스키마만 만든다."""
    def __init__(self, path):
        self.path = str(path)
        import sqlite3
        conn = sqlite3.connect(self.path)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS scenarios (scenario_id TEXT PRIMARY KEY, name TEXT,
            org_id TEXT, baseline_kind TEXT, baseline_period TEXT, status TEXT, owner TEXT,
            created_at TEXT, tenant_id TEXT, entity_mode TEXT);
        CREATE TABLE IF NOT EXISTS scenario_assumptions (assumption_id TEXT PRIMARY KEY,
            scenario_id TEXT, target_kind TEXT, target_code TEXT, operator TEXT, value REAL,
            unit TEXT, rationale TEXT, created_at TEXT);
        """)
        conn.commit(); conn.close()

    def _connect(self):
        import sqlite3
        return sqlite3.connect(self.path)

    def rows(self, table):
        conn = self._connect()
        try:
            return conn.execute(f"SELECT * FROM {table}").fetchall()
        finally:
            conn.close()


def _bridge(wired, tmp_path, engine=None):
    ps = _FakePlanningStore(tmp_path / "planning.db")
    return CalcBridge(store=wired["store"], engine=engine or _FakeEngine(),
                      planning_store=ps), ps


def test_run_and_record_writes_engine_inputs_and_ecm_result(wired, tmp_path):
    """★★★ 다리가 하는 일 전체: 번역 → 엔진 시나리오·가정 생성 → 실행 → ECM 결과 등록."""
    br, ps = _bridge(wired, tmp_path)
    out = br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                            wired["snap"]["snapshot_id"], org_id="MNM_BATTERY",
                            period="2026H2", actor="hikwon")
    assert out["result_id"].startswith("res_")
    assert out["calculation_model_version"] == "planning_engine_v1.0.0"
    assert out["values"]["gross_profit"] == 1120.0
    # 엔진 쪽에 가정 2건이 실제로 들어갔다
    assert len(ps.rows("scenario_assumptions")) == 2
    assert len(ps.rows("scenarios")) == 1
    # 추적 정보가 함께 남는다
    assert out["engine"]["input_hash"] == "hash_xyz"
    assert out["engine"]["translated_assumptions"] == 2


def test_inputs_are_frozen_after_the_run(wired, tmp_path):
    """★★ 결과가 등록되면 그 가정·기준선은 동결된다 — 다리를 통해도 같은 규율이 적용된다."""
    br, _ = _bridge(wired, tmp_path)
    br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                      wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    assert wired["store"].get_assumption_set(
        wired["asm"]["assumption_set_id"])["frozen"] is True
    assert wired["store"].get_snapshot(wired["snap"]["snapshot_id"])["frozen"] is True


def test_unapproved_assumption_set_is_refused(wired, tmp_path):
    """★★ 승인 전 가정으로 계산하면 같은 계산이 어제와 오늘 다른 답을 낸다."""
    br, _ = _bridge(wired, tmp_path)
    draft = wired["store"].create_assumption_set(
        "초안", "목적", {"account:4000:pct": 1.0}, {"account:4000:pct": "근거"})
    with pytest.raises(CalcBridgeError, match="승인되지 않은"):
        br.run_and_record(wired["scn"]["scenario_id"], draft["assumption_set_id"],
                          wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")


def test_bad_key_stops_before_touching_the_engine(wired, tmp_path):
    """★★★ **번역이 전부 성공한 뒤에야 엔진에 쓴다.**

    ⚠️ 순서가 반대면 엔진 시나리오가 반쯤 만들어진 채로 남는다 — 다음 사람이 그 껍데기를 보고
      "왜 가정이 일부만 있나"를 조사하게 된다."""
    br, ps = _bridge(wired, tmp_path)
    bad = wired["store"].create_assumption_set(
        "혼합", "목적", {"account:4000:pct": 1.0, "총원가": 2.0},
        {"account:4000:pct": "근거", "총원가": "근거"})
    wired["store"].approve_assumption_set(bad["assumption_set_id"])
    with pytest.raises(CalcBridgeError, match="규약"):
        br.run_and_record(wired["scn"]["scenario_id"], bad["assumption_set_id"],
                          wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    assert ps.rows("scenarios") == [], "엔진 시나리오가 남았다"
    assert ps.rows("scenario_assumptions") == []


def test_unapplied_assumptions_are_surfaced_loudly(wired, tmp_path):
    """★★★ 반영되지 않은 가정을 조용히 넘기면 "가정 2개를 넣었고 결과가 나왔다"로 읽힌다 —
    실제로는 1개만 반영된 결과일 수 있고, 그 숫자가 경영 판단에 쓰인다."""
    eng = _FakeEngine(unapplied=[{"target_code": "9999", "why": "기준선에 없음"}],
                      warnings=["ENERGY_PRICE 파급 계수 미승인"])
    br, _ = _bridge(wired, tmp_path, engine=eng)
    out = br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                            wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    assert "반영되지 않은 가정 1건" in out["warning"]
    assert "동인 경고 1건" in out["warning"]
    assert out["engine"]["unapplied_assumptions"] and out["engine"]["driver_warnings"]


def test_empty_engine_result_is_refused(wired, tmp_path):
    """★★ 빈 결과를 기록하면 "계산했다"는 기록만 남고 근거가 없다."""
    br, _ = _bridge(wired, tmp_path, engine=_FakeEngine(result={}))
    with pytest.raises(CalcBridgeError, match="비교 가능한 결과"):
        br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                          wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")


def test_only_numeric_metrics_become_result_values(wired, tmp_path):
    """★★ 엔진 결과의 실행 메타(문자열·플래그)까지 결과 값으로 넣으면 비교표에 의미 없는 차이
    행이 생긴다 — 숫자만 가져온다."""
    eng = _FakeEngine(result={"gross_profit": 10.0, "note": "설명", "ok": True})
    br, _ = _bridge(wired, tmp_path, engine=eng)
    out = br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                            wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    assert out["values"] == {"gross_profit": 10.0}


def test_engine_facts_are_not_persisted_by_default(wired, tmp_path):
    """★★ 탐색적 실행이 실적 표를 오염시키면 안 된다 — 엔진의 `persist` 기본값(False)을 그대로 쓴다."""
    eng = _FakeEngine()
    br, _ = _bridge(wired, tmp_path, engine=eng)
    br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                      wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    assert eng.calls[0]["persist"] is False


def test_result_is_comparable_right_away(wired, tmp_path):
    """★★★ 다리를 통과한 결과는 곧바로 비교된다 — 이것이 연결의 목적이다.

    기준선(확정 실적)과 결과(가상 계산값)의 상태가 표에서 구분돼 나온다."""
    from core.enterprise_context.comparison import compare_result
    br, _ = _bridge(wired, tmp_path)
    out = br.run_and_record(wired["scn"]["scenario_id"], wired["asm"]["assumption_set_id"],
                            wired["snap"]["snapshot_id"], "MNM_BATTERY", "2026H2")
    c = compare_result(out["result_id"], store=wired["store"])
    row = next(r for r in c["rows"] if r["key"] == "gross_profit")
    assert row["baseline"]["mode_ko"] == "확정 실적" and row["result"]["mode_ko"] == "가상 시나리오"
    assert row["delta"] == 120.0
    assert c["context"]["calculation_model_version"] == "planning_engine_v1.0.0"
