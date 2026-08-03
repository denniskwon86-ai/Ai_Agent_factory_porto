"""★★★ [E3] 가정 세트 · 기준선 스냅샷 · 결과 비교 — **숫자가 어디서 왔는지 답할 수 있게 한다.**

## 왜 이 파일이 생겼나

E3 를 구현했을 때 `assumption_set_id` 와 `baseline_snapshot_id` 는 **문자열로만 통과**하고
있었다. §8.1 이 실행 문맥 키로 못 박은 두 값인데 키만 있고 대상이 없었다 — 시나리오를 만들고
계산까지 할 수 있지만, "이 숫자는 무슨 가정으로 어떤 기준선과 비교해 나왔나"에 답할 수 없었다.

⚠️ 답할 수 없는 숫자는 근거가 아니라 주장이다. 그런데 경영 판단에 쓰이면 그때부터 사실처럼
  취급된다(비협상 3: 모든 값은 상태와 근거를 갖는다).

이 파일이 지키는 계약:
1. 근거 없는 가정은 저장되지 않는다.
2. 계산에 쓰인 입력은 동결된다(수정은 새 버전으로만).
3. 승인된 가정·기준선만 계산에 쓰인다.
4. 가상에서 나온 값이 실제 기준선으로 스며들지 않는다.
5. 비교표에서 **실제와 가정이 같은 값처럼 보이지 않는다.**
"""
import pytest

from core.enterprise_context.clone_service import CloneService
from core.enterprise_context.comparison import (MODE_ACTUAL, MODE_SCENARIO, ComparisonError,
                                                compare_result, compare_results)
from core.enterprise_context.models import EnterpriseEntity, OrganizationNode
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.scenario_inputs import ScenarioInputError, ScenarioInputStore

TOMORROW = "2099-12-31"
TODAY = "2026-08-03"
V = {"연산능력_톤": 12000, "단위원가_원": 3200}
EV = {"연산능력_톤": "설비사양서 2026-05 rev.3", "단위원가_원": "구매 계약단가 2026 상반기"}


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def clone(repo):
    return CloneService(repository=repo)


@pytest.fixture
def store(repo, clone):
    return ScenarioInputStore(repository=repo, clone=clone)


@pytest.fixture
def scenario(repo, clone):
    ent = repo.upsert_entity(EnterpriseEntity(
        entity_type="business_division", entity_mode="REAL", name_ko="배터리소재 사업부"))
    repo.upsert_node(OrganizationNode(entity_id=ent.entity_id, code="MNM_BATTERY",
                                      name_ko="배터리소재 사업부", status="ACTIVE"))
    return clone.clone_to_virtual(ent.entity_id, "가상 증설", purpose="증설 타당성",
                                  valid_until=TOMORROW, actor="hikwon", today=TODAY)


def _approved_inputs(store, actor="hikwon"):
    a = store.create_assumption_set("에너지가 +12%", "증설 타당성 가정", V, EV, actor=actor)
    store.approve_assumption_set(a["assumption_set_id"], actor)
    s = store.create_snapshot("2026 상반기 확정", "2026-06-30",
                              {"연산능력_톤": 10000, "단위원가_원": 3000},
                              source="ERP 집계 2026-07-05 승인본", actor=actor)
    store.approve_snapshot(s["snapshot_id"], actor)
    return a, s


# ── 가정 세트: 근거 없는 가정은 저장되지 않는다 ────────────────────────────
def test_assumption_requires_evidence_for_every_value(store):
    """★★★ **이 파일의 첫 계약.** 가정값마다 근거가 있어야 한다.

    ⚠️ 근거를 선택 항목으로 두면 아무도 채우지 않는다. 그리고 근거 없는 가정은 계산을 통과한 뒤
      결과 숫자로만 남아, 나중에는 그 숫자가 어디서 왔는지 아무도 모른다."""
    with pytest.raises(ScenarioInputError, match="근거"):
        store.create_assumption_set("가정", "목적", V, {"연산능력_톤": "설비사양서"})


def test_assumption_requires_name_and_purpose(store):
    """★ 목적 없는 가정 세트는 재사용도 폐기도 판단할 수 없다."""
    with pytest.raises(ScenarioInputError):
        store.create_assumption_set("", "목적", V, EV)
    with pytest.raises(ScenarioInputError, match="목적"):
        store.create_assumption_set("이름", "", V, EV)


def test_assumption_starts_as_draft(store):
    """★ 만들면 DRAFT 다 — 승인 전 가정으로 계산하면 기준이 흔들린다."""
    a = store.create_assumption_set("가정", "목적", V, EV)
    assert a["status"] == "DRAFT" and a["frozen"] is False


def test_revision_creates_new_version_and_keeps_original(store):
    """★★★ 개정은 **새 버전**이다. 원본을 제자리에서 고치지 않는다.

    ⚠️ 동결된(계산에 쓰인) 가정을 제자리에서 고치면 과거 결과의 근거가 사라진다."""
    a = store.create_assumption_set("가정", "목적", V, EV, actor="kim")
    b = store.revise_assumption_set(a["assumption_set_id"],
                                    {"연산능력_톤": 15000}, {"연산능력_톤": "증설 설계안 v2"},
                                    actor="kim")
    old = store.get_assumption_set(a["assumption_set_id"])
    assert b["version"] == 2 and b["supersedes"] == a["assumption_set_id"]
    assert old["status"] == "SUPERSEDED", "구판이 살아 있으면 어느 것이 유효한지 알 수 없다"
    assert old["values"] == V, "원본 값이 바뀌었다 — 과거 결과의 근거가 사라진다"


# ── 스냅샷: 언제 기준인지·어디서 왔는지 없으면 기준선이 아니다 ──────────────
@pytest.mark.parametrize("kw,why", [
    ({"as_of": ""}, "기준 시점"),
    ({"source": ""}, "출처"),
])
def test_snapshot_requires_as_of_and_source(store, kw, why):
    """★★ "작년 실적"과 "이번 달 추정"을 같은 칼럼에서 비교하는 순간 결과는 의미를 잃는다."""
    args = {"name": "기준선", "as_of": "2026-06-30", "values": {"a": 1},
            "source": "ERP 집계"}
    args.update(kw)
    with pytest.raises(ScenarioInputError):
        store.create_snapshot(**args)


def test_scenario_values_cannot_become_a_real_baseline(store):
    """★★★ **가상에서 나온 값이 실제 기준선으로 스며들 수 없다.**

    §8.3 "가상 결과를 실제 시스템에 자동 반영하지 않는다"의 저장소 쪽 방어선이다. 실제로 이
    경로가 열려 있으면, 한 번 승격 절차를 우회한 값이 이후 모든 비교의 기준이 된다."""
    with pytest.raises(ScenarioInputError, match="실제\\(REAL\\) 기준선으로 등록할 수 없"):
        store.create_snapshot("가상 결과", "2026-06-30", {"a": 1},
                              source="scenario:scn_abc123", entity_mode="REAL")
    # 가상 기준선으로는 등록된다 — 가상끼리 비교하는 것은 정당하다
    ok = store.create_snapshot("가상 기준선", "2026-06-30", {"a": 1},
                               source="scenario:scn_abc123", entity_mode="VIRTUAL")
    assert ok["entity_mode"] == "VIRTUAL"


def test_snapshot_checksum_detects_tampering(store):
    """★★★ 같은 id 로 내용이 바뀌면 **다른 스냅샷**이다 — 재현 불가를 조용히 넘기지 않는다."""
    s = store.create_snapshot("기준선", "2026-06-30", {"a": 1}, source="ERP")
    assert s["checksum_ok"] is True
    # 저장소를 직접 건드려 내용만 바꾼다(실제 사고 형태: 스크립트로 값 수정)
    import sqlite3
    conn = sqlite3.connect(store._repo.db_path)
    conn.execute("UPDATE baseline_snapshots SET values_json=? WHERE snapshot_id=?",
                 ('{"a": 999}', s["snapshot_id"]))
    conn.commit(); conn.close()

    bad = store.get_snapshot(s["snapshot_id"])
    assert bad["checksum_ok"] is False and "재현할 수 없" in bad["warning"]
    with pytest.raises(ScenarioInputError, match="체크섬"):
        store.approve_snapshot(s["snapshot_id"])


# ── 결과 기록: 승인된 입력만, 그리고 동결 ──────────────────────────────────
def test_result_requires_approved_inputs(store, scenario):
    """★★★ 승인되지 않은 가정·기준선으로는 결과를 기록할 수 없다.

    승인 전 가정으로 낸 숫자가 기준이 되면, 같은 계산이 어제와 오늘 다른 답을 낸다."""
    a = store.create_assumption_set("가정", "목적", V, EV)          # DRAFT
    s = store.create_snapshot("기준선", "2026-06-30", {"a": 1}, source="ERP")  # DRAFT
    with pytest.raises(ScenarioInputError, match="승인되지 않은 가정"):
        store.record_result(scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"],
                            "capacity_cost_v1.4", {"a": 2})
    store.approve_assumption_set(a["assumption_set_id"])
    with pytest.raises(ScenarioInputError, match="승인되지 않은 기준선"):
        store.record_result(scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"],
                            "capacity_cost_v1.4", {"a": 2})


def test_result_requires_model_version(store, scenario):
    """★★ 어떤 모델이 낸 숫자인지 없으면 재현할 수 없다(§8.1)."""
    a, s = _approved_inputs(store)
    with pytest.raises(ScenarioInputError, match="계산 모델 버전"):
        store.record_result(scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"],
                            "", {"a": 1})


def test_recording_a_result_freezes_its_inputs(store, scenario):
    """★★★ **결과를 기록하는 순간 입력이 잠긴다.** 이후 그 가정을 고치려면 새 버전을 만들어야 하고,
    원본은 그대로 남아 과거 결과를 설명한다."""
    a, s = _approved_inputs(store)
    store.record_result(scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"],
                        "capacity_cost_v1.4", {"연산능력_톤": 12500, "단위원가_원": 3350},
                        actor="hikwon")
    assert store.get_assumption_set(a["assumption_set_id"])["frozen"] is True
    assert store.get_snapshot(s["snapshot_id"])["frozen"] is True
    # 동결본을 개정하면 새 버전이 생기고 **원본 값은 보존된다**
    b = store.revise_assumption_set(a["assumption_set_id"], {"연산능력_톤": 1},
                                    {"연산능력_톤": "재검토"})
    assert store.get_assumption_set(a["assumption_set_id"])["values"] == V
    assert b["version"] == 2


def test_same_inputs_cannot_produce_two_results(store, scenario):
    """★★ 결정론적 계산은 같은 입력에 같은 답을 낸다 — 같은 조합의 결과가 둘이면 하나는 거짓이다."""
    a, s = _approved_inputs(store)
    kw = (scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"], "v1.4")
    store.record_result(*kw, {"a": 1})
    with pytest.raises(ScenarioInputError, match="이미 있습니다"):
        store.record_result(*kw, {"a": 2})


def test_closed_or_expired_scenario_rejects_results(store, repo, clone, scenario):
    """★★ 종료·만료된 시나리오에는 결과를 붙일 수 없다."""
    a, s = _approved_inputs(store)
    clone.close_scenario(scenario["scenario_id"])
    with pytest.raises(ScenarioInputError, match="종료된 시나리오"):
        store.record_result(scenario["scenario_id"], s["snapshot_id"],
                            a["assumption_set_id"], "v1.4", {"a": 1})


# ── 비교: 실제와 가정을 같은 값처럼 보이지 않게 한다 ───────────────────────
def _recorded(store, scenario, actor="hikwon"):
    a, s = _approved_inputs(store, actor)
    r = store.record_result(scenario["scenario_id"], s["snapshot_id"], a["assumption_set_id"],
                            "capacity_cost_v1.4",
                            {"연산능력_톤": 12500, "단위원가_원": 3000, "신규지표": 7},
                            actor=actor)
    return a, s, r


def test_comparison_keeps_the_state_of_each_value(store, scenario):
    """★★★ **이 모듈의 핵심.** 기준선은 확정 실적, 결과는 가상 계산값 — 표에서 그 구분이
    사라지면 안 된다(§8.1: 실제·계획·예측·시나리오는 분리한다)."""
    a, s, r = _recorded(store, scenario)
    c = compare_result(r["result_id"], store=store)
    row = next(x for x in c["rows"] if x["key"] == "연산능력_톤")
    assert row["baseline"]["mode"] == MODE_ACTUAL and row["result"]["mode"] == MODE_SCENARIO
    assert row["baseline"]["as_of"] == "2026-06-30" and row["baseline"]["source"]
    assert row["delta"] == 2500 and round(row["delta_pct"], 1) == 25.0
    assert any("같은 종류의 값이 아닙니다" in n for n in c["notes"])


def test_comparison_carries_the_execution_context(store, scenario):
    """★★ §8.1 — 산출 결과는 입력과 같은 키를 갖는다. 비교 결과도 그 키를 그대로 들고 있어야
    "무엇으로 계산했나"에 답할 수 있다."""
    a, s, r = _recorded(store, scenario)
    ctx = compare_result(r["result_id"], store=store)["context"]
    assert ctx["scenario_id"] == scenario["scenario_id"]
    assert ctx["baseline_snapshot_id"] == s["snapshot_id"]
    assert ctx["assumption_set_id"] == a["assumption_set_id"]
    assert ctx["calculation_model_version"] == "capacity_cost_v1.4"


def test_comparison_exposes_the_assumptions_and_evidence(store, scenario):
    """★★★ 가정과 **근거**를 함께 낸다 — 가정만 보여주면 "왜 그 값인가"가 화면에서 사라진다."""
    a, s, r = _recorded(store, scenario)
    c = compare_result(r["result_id"], store=store)
    assert c["assumptions"]["values"] == V
    assert c["assumptions"]["evidence"]["단위원가_원"].startswith("구매 계약단가")


def test_comparison_does_not_hide_missing_items(store, scenario):
    """★★★ 교집합만 비교하고 넘어가면 "빠진 항목 없이 다 비교됐다"고 오해한다."""
    a, s, r = _recorded(store, scenario)
    c = compare_result(r["result_id"], store=store)
    assert c["result_only"] == ["신규지표"]
    assert c["summary"]["result_only"] == 1
    assert any("기준선에 없습니다" in n for n in c["notes"])


def test_zero_baseline_gives_no_percentage(store, scenario):
    """★★ 기준선이 0 이면 증감률은 의미가 없다 — 0 으로 나누는 대신 주지 않는다."""
    a = store.create_assumption_set("가정", "목적", {"x": 1}, {"x": "근거"})
    store.approve_assumption_set(a["assumption_set_id"])
    s = store.create_snapshot("영기준", "2026-06-30", {"x": 0}, source="ERP")
    store.approve_snapshot(s["snapshot_id"])
    r = store.record_result(scenario["scenario_id"], s["snapshot_id"],
                            a["assumption_set_id"], "v1", {"x": 5})
    row = compare_result(r["result_id"], store=store)["rows"][0]
    assert row["delta"] == 5 and row["delta_pct"] is None


def test_non_numeric_values_are_not_subtracted(store, scenario):
    """★★★ "약 12%" 같은 문자열을 억지로 숫자로 만들면 근사값이 확정값으로 계산에 들어간다."""
    a = store.create_assumption_set("가정", "목적", {"x": 1}, {"x": "근거"})
    store.approve_assumption_set(a["assumption_set_id"])
    s = store.create_snapshot("기준선", "2026-06-30", {"등급": "B"}, source="ERP")
    store.approve_snapshot(s["snapshot_id"])
    r = store.record_result(scenario["scenario_id"], s["snapshot_id"],
                            a["assumption_set_id"], "v1", {"등급": "A"})
    row = compare_result(r["result_id"], store=store)["rows"][0]
    assert row["comparable"] is False and "delta" not in row
    assert "사람이 봐야" in row["note"]


def test_unapproved_baseline_is_flagged_in_notes(store, scenario, repo):
    """★★ 승인되지 않은 기준선으로 만든 비교는 **경고를 달고 나온다**(기록은 막았지만, 나중에
    승인이 취소되는 경우가 있다)."""
    a, s, r = _recorded(store, scenario)
    import sqlite3
    conn = sqlite3.connect(store._repo.db_path)
    conn.execute("UPDATE baseline_snapshots SET status='DRAFT' WHERE snapshot_id=?",
                 (s["snapshot_id"],))
    conn.commit(); conn.close()
    c = compare_result(r["result_id"], store=store)
    assert any("기준선이 승인되지 않았습니다" in n for n in c["notes"])


def test_notes_are_quiet_when_everything_matches(store, scenario):
    """★ 가상 기준선 vs 가상 결과이고 결손이 없으면 경고가 없다 — 항상 뜨는 경고는 안 읽힌다."""
    a = store.create_assumption_set("가정", "목적", {"x": 1}, {"x": "근거"})
    store.approve_assumption_set(a["assumption_set_id"])
    s = store.create_snapshot("가상 기준선", "2026-06-30", {"x": 1},
                              source="scenario:prev", entity_mode="VIRTUAL")
    store.approve_snapshot(s["snapshot_id"])
    r = store.record_result(scenario["scenario_id"], s["snapshot_id"],
                            a["assumption_set_id"], "v1", {"x": 2})
    assert compare_result(r["result_id"], store=store)["notes"] == []


# ── 다중 비교: 기준선이 다르면 한 표에 넣지 않는다 ─────────────────────────
def test_multi_compare_lines_up_scenarios(store, scenario):
    """★★ 가정별 결과를 나란히 본다(§7.2) — 같은 기준선을 공유할 때만."""
    a1, s = _approved_inputs(store)
    a2 = store.create_assumption_set("에너지가 +20%", "민감도", V, EV)
    store.approve_assumption_set(a2["assumption_set_id"])
    r1 = store.record_result(scenario["scenario_id"], s["snapshot_id"],
                             a1["assumption_set_id"], "v1.4", {"연산능력_톤": 12500})
    r2 = store.record_result(scenario["scenario_id"], s["snapshot_id"],
                             a2["assumption_set_id"], "v1.4", {"연산능력_톤": 11800})
    out = compare_results([r1["result_id"], r2["result_id"]], store=store)
    row = next(t for t in out["table"] if t["key"] == "연산능력_톤")
    assert [c["value"] for c in row["cells"]] == [12500, 11800]
    assert [c["delta"] for c in row["cells"]] == [2500, 1800]


def test_multi_compare_refuses_different_baselines(store, scenario):
    """★★★ 기준선이 다른 결과를 나란히 놓으면 그 차이가 **시나리오 차이인지 기준선 차이인지**
    구분할 수 없다. 표는 그것을 말해주지 않으므로 여기서 거부한다."""
    a1, s1 = _approved_inputs(store)
    s2 = store.create_snapshot("다른 기준선", "2025-12-31", {"연산능력_톤": 9000},
                               source="ERP 2025")
    store.approve_snapshot(s2["snapshot_id"])
    r1 = store.record_result(scenario["scenario_id"], s1["snapshot_id"],
                             a1["assumption_set_id"], "v1.4", {"연산능력_톤": 12500})
    r2 = store.record_result(scenario["scenario_id"], s2["snapshot_id"],
                             a1["assumption_set_id"], "v1.4", {"연산능력_톤": 12500})
    with pytest.raises(ComparisonError, match="기준선이 서로 다른"):
        compare_results([r1["result_id"], r2["result_id"]], store=store)


def test_comparison_needs_a_baseline(store, scenario):
    """★ 기준선이 사라진 결과는 비교할 수 없다 — 조용히 빈 표를 주지 않는다."""
    a, s, r = _recorded(store, scenario)
    import sqlite3
    conn = sqlite3.connect(store._repo.db_path)
    conn.execute("DELETE FROM baseline_snapshots WHERE snapshot_id=?", (s["snapshot_id"],))
    conn.commit(); conn.close()
    with pytest.raises(ComparisonError, match="기준선"):
        compare_result(r["result_id"], store=store)


# ── 감사 ──────────────────────────────────────────────────────────────────
def test_inputs_and_results_are_audited(store, scenario, tmp_path, monkeypatch):
    """★★★ 입력과 결과의 변경이 남는다 — 남지 않으면 "이 숫자가 무슨 가정에서 나왔나"를
    나중에 재구성할 수 없다."""
    import json

    from core.enterprise_context import audit
    log = tmp_path / "a.jsonl"
    monkeypatch.setattr(audit, "_LOG_PATH", str(log), raising=False)
    _recorded(store, scenario)
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    ev = [r for r in rows if r["event"] == "SCENARIO_INPUT_CHANGED"]
    reasons = [r["reason"] for r in ev]
    assert "가정 세트 생성" in reasons and "기준선 스냅샷 승인" in reasons
    assert any("입력 동결" in r for r in reasons)
