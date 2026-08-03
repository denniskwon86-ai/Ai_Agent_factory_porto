"""★★★ [ECM E4] 조직 트리 집계 · 경영진 비교 보드 — **합치는 순간 거짓말이 되기 쉬운 계산.**

## 이 파일이 지키는 것

집계는 이 저장소에서 가장 조용하게 틀리는 자리다. 오류가 나지 않고, 손익표는 그럴듯해 보이며,
잘못된 합계는 **의사결정이 끝난 뒤에야** 드러난다.

1. **이중 계상**: 부모가 자기 값을 갖고 자식도 값을 가지면 더하지 않는다 — 그대로 더하면 실제의
   두 배가 된다. 자동으로 한쪽을 고르지 않는다(어느 쪽이 정본인지는 넣은 사람만 안다).
2. **법인 경계**: 운영 집계는 넘지 않고, 연결 집계는 **지분율**로 넘는다. 지분율을 빼먹으면
   100% 자회사가 아닌 곳의 매출이 전액 우리 것이 된다.
3. **결손을 0 으로 채우지 않는다**: 값이 없는 자식을 0 으로 보면 부분 합계가 전체처럼 보인다.
4. **상태 혼합 금지**: 확정 실적 + 가상 계산값의 합계는 존재하지 않는 숫자다(§8.1).
5. **판단하지 않는다**: 우열·증감 해석은 지표의 방향을 알아야 하고, 그건 도메인 지식이다.
"""
import pytest

from core.enterprise_context.executive_board import SERIES_ORDER, BoardError, build_board
from core.enterprise_context.models import EnterpriseEntity, OrganizationEdge, OrganizationNode
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.rollup import COVERAGE_WARN_BELOW, Rollup, RollupError


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def svc(repo):
    return Rollup(repository=repo)


def _node(repo, name, code, ntype="business_division", mode="REAL"):
    e = repo.upsert_entity(EnterpriseEntity(entity_type=ntype, entity_mode=mode, name_ko=name))
    return repo.upsert_node(OrganizationNode(entity_id=e.entity_id, node_type=ntype, code=code,
                                             name_ko=name, status="ACTIVE"))


@pytest.fixture
def tree(repo):
    """LS MnM → (동제련, 배터리소재) → 배터리 제1·제2공장."""
    mnm = _node(repo, "LS MnM", "LS_MNM", "legal_entity")
    cu = _node(repo, "동제련", "MNM_COPPER")
    bat = _node(repo, "배터리소재", "MNM_BATTERY")
    p1 = _node(repo, "제1공장", "BATT_P1", "site_plant")
    p2 = _node(repo, "제2공장", "BATT_P2", "site_plant")
    for a, b in ((mnm, cu), (mnm, bat), (bat, p1), (bat, p2)):
        repo.add_edge(OrganizationEdge(from_node_id=a.node_id, to_node_id=b.node_id,
                                       relation_type="OPERATING_PARENT"))
    return {"mnm": mnm, "cu": cu, "bat": bat, "p1": p1, "p2": p2}


# ── 기본 집계 ─────────────────────────────────────────────────────────────
def test_operating_rollup_sums_descendants(svc, tree):
    """★★ 하위 조직 값을 합친다. 기여 내역도 함께 준다 — 합계만 주면 검산할 수 없다."""
    vals = {tree["p1"].node_id: {"매출": 600}, tree["p2"].node_id: {"매출": 400}}
    r = svc.rollup(tree["bat"].node_id, vals)
    assert r["totals"]["매출"] == 1000
    assert {c["node_id"] for c in r["contributions"]["매출"]} == {tree["p1"].node_id,
                                                                 tree["p2"].node_id}


def test_own_value_is_used_when_no_children_have_values(svc, tree):
    """★ 자식 값이 없으면 자기 입력값을 쓴다(그 자체가 정본이다)."""
    r = svc.rollup(tree["bat"].node_id, {tree["bat"].node_id: {"매출": 900}})
    assert r["totals"]["매출"] == 900
    assert r["contributions"]["매출"][0]["how"] == "직접 입력"


def test_double_counting_is_excluded_not_resolved(svc, tree):
    """★★★ **이 파일의 핵심.** 부모 값과 자식 값이 함께 있으면 합계에서 **제외**하고 알린다.

    ⚠️ 그대로 더하면 2배가 되고 아무 오류도 나지 않는다. 자동으로 한쪽을 고르면 그 선택이
      조용히 굳는다 — 합계가 최신일 수도, 상세가 정본일 수도 있고 그건 넣은 사람만 안다."""
    vals = {tree["bat"].node_id: {"매출": 1000},
            tree["p1"].node_id: {"매출": 600}, tree["p2"].node_id: {"매출": 400}}
    r = svc.rollup(tree["bat"].node_id, vals)
    assert "매출" not in r["totals"], "이중 계상 값이 합계에 들어갔다"
    c = r["conflicts"][0]
    assert c["own_value"] == 1000 and c["child_sum"] == 1000
    assert any("이중 계상" in n for n in r["notes"])


def test_missing_children_are_not_treated_as_zero(svc, tree):
    """★★★ 값이 없는 자식을 0 으로 보면 **부분 합계가 전체처럼** 보인다."""
    r = svc.rollup(tree["bat"].node_id, {tree["p1"].node_id: {"매출": 600}})
    assert r["totals"]["매출"] == 600
    assert r["coverage"]["with_values"] == 1 and r["coverage"]["descendants"] == 2
    assert r["coverage"]["missing"] == [tree["p2"].node_id]
    assert any("부분 합계" in n for n in r["notes"])


def test_coverage_threshold_is_one_place(svc, tree):
    """★ 임계값이 코드 한 곳에 있다 — 화면마다 다른 기준을 쓰면 같은 합계가 어디선 정상,
    어디선 경고로 보인다."""
    assert 0 < COVERAGE_WARN_BELOW <= 1


def test_non_numeric_values_are_skipped(svc, tree):
    """★★ 문자열을 억지로 숫자로 만들지 않는다 — 합계에 들어가면 근사값이 확정값이 된다."""
    r = svc.rollup(tree["bat"].node_id, {tree["p1"].node_id: {"등급": "A", "매출": 100}})
    assert r["totals"] == {"매출": 100.0}


def test_unknown_relation_is_refused(svc, tree):
    """★★ 아무 관계로나 합치면 그 합계가 무엇인지 설명할 수 없다."""
    with pytest.raises(RollupError, match="집계 관계"):
        svc.rollup(tree["bat"].node_id, {}, relation="SHARED_SERVICE")


# ── 법인 경계 · 지분율 ────────────────────────────────────────────────────
def test_same_legal_entity_rollup_does_not_warn(svc, tree):
    """★★★ [2026-08-03 실측 결함] **오탐이 없어야 한다.** 사업부→공장은 같은 법인 안이다.

    처음 구현은 노드 자신의 `entity_id` 를 법인으로 봤다. 이 저장소는 노드마다 엔터티가 1:1
    이므로 부모와 자식이 항상 달라서 **모든 운영 집계에 경고가 붙었다**(실서버에서
    `MNM_BATTERY → BATT_PLANT_1/2` 에 경고가 떠 발견).

    ⚠️ 오탐 경고는 진짜 경고를 묻는다 — 항상 뜨는 경고는 아무도 읽지 않게 되고, 그러면 실제로
      법인을 넘은 집계도 지나간다. 이 테스트가 없었기 때문에 아래 양성 테스트가 **틀린 이유로
      통과**하고 있었다."""
    r = svc.rollup(tree["bat"].node_id,
                   {tree["p1"].node_id: {"매출": 600}, tree["p2"].node_id: {"매출": 400}})
    assert not any("법인 경계" in n for n in r["notes"]), f"오탐: {r['notes']}"


def test_operating_rollup_warns_when_crossing_legal_entities(svc, repo, tree):
    """★★★ 운영 합계에 다른 법인이 섞이면 **그건 우리 실적이 아니다.**"""
    other = _node(repo, "LS전선", "LS_CABLE", "legal_entity")
    repo.add_edge(OrganizationEdge(from_node_id=tree["mnm"].node_id,
                                   to_node_id=other.node_id,
                                   relation_type="OPERATING_PARENT"))
    r = svc.rollup(tree["mnm"].node_id, {other.node_id: {"매출": 500}})
    assert any("법인 경계를 넘었습니다" in n for n in r["notes"])


def test_consolidation_applies_ownership_weight(svc, repo):
    """★★★ 연결 집계는 지분율을 적용한다 — 빼먹으면 100% 자회사가 아닌 곳의 매출이 전액
    우리 것이 된다."""
    a = _node(repo, "지주", "HOLD", "legal_entity")
    b = _node(repo, "자회사", "SUB", "legal_entity")
    repo.add_edge(OrganizationEdge(from_node_id=a.node_id, to_node_id=b.node_id,
                                   relation_type="CONSOLIDATION_SCOPE", weight=0.6))
    r = svc.rollup(a.node_id, {b.node_id: {"매출": 1000}},
                   relation="CONSOLIDATION_SCOPE")
    assert r["totals"]["매출"] == 600.0
    assert r["contributions"]["매출"][0]["weight"] == 0.6


def test_multi_level_ownership_is_multiplied(svc, repo):
    """★★★ 다단 자회사에서 지분이 **희석**된다. 한 단계만 보면 손자회사를 100% 로 계산한다
    (A→B 60%, B→C 50% 인데 A→C 를 100% 로 보는 것)."""
    a = _node(repo, "A", "A", "legal_entity")
    b = _node(repo, "B", "B", "legal_entity")
    c = _node(repo, "C", "C", "legal_entity")
    repo.add_edge(OrganizationEdge(from_node_id=a.node_id, to_node_id=b.node_id,
                                   relation_type="CONSOLIDATION_SCOPE", weight=0.6))
    repo.add_edge(OrganizationEdge(from_node_id=b.node_id, to_node_id=c.node_id,
                                   relation_type="CONSOLIDATION_SCOPE", weight=0.5))
    r = svc.rollup(a.node_id, {c.node_id: {"매출": 1000}}, relation="CONSOLIDATION_SCOPE")
    assert r["totals"]["매출"] == 300.0, "지분 희석이 반영되지 않았다"


def test_mode_is_carried_through(svc, tree):
    """★★ 어떤 상태의 값을 합쳤는지가 결과에 붙어 나간다 — 없으면 합계가 실적인지 가정인지
    알 수 없다."""
    r = svc.rollup(tree["bat"].node_id, {tree["p1"].node_id: {"매출": 1}}, mode="SCENARIO")
    assert r["mode"] == "SCENARIO"


# ── 경영진 보드 ───────────────────────────────────────────────────────────
def test_board_lines_up_states_without_mixing(tree):
    """★★★ 상태별 계열을 나란히 세우되 **가로 합계를 만들지 않는다.**

    확정 실적 + 가상 계산값의 합계는 존재하지 않는 숫자다(§8.1)."""
    b = build_board(tree["bat"].node_id,
                    series={"ACTUAL": {"매출": 1000}, "PLAN": {"매출": 1200},
                            "SCENARIO": {"매출": 1350}},
                    meta={"ACTUAL": {"as_of": "2026-06-30", "source": "ERP"},
                          "SCENARIO": {"as_of": "", "source": "scn_x", "official": False}})
    row = b["rows"][0]
    assert row["cells"]["ACTUAL"]["official"] is True
    assert row["cells"]["SCENARIO"]["official"] is False
    assert row["cross_mode_total"] is None and "합치지 않습니다" in row["cross_mode_note"]
    assert any("색·범례로 구분" in n for n in b["notes"])


def test_board_refuses_unknown_state(tree):
    """★★★ 상태 없는 값을 보드에 세우면 그 숫자가 실제인지 가정인지 구분할 수 없다."""
    with pytest.raises(BoardError, match="알 수 없는 값 상태"):
        build_board(tree["bat"].node_id, series={"GUESS": {"매출": 1}})


def test_board_series_order_is_fixed(tree):
    """★ 화면 순서가 코드에 한 번만 선언돼 있다(확정 → 계획 → 예측 → 가상 → 경쟁사)."""
    b = build_board(tree["bat"].node_id,
                    series={"SCENARIO": {"a": 1}, "ACTUAL": {"a": 2}, "PLAN": {"a": 3}})
    assert [s["mode"] for s in b["series"]] == ["ACTUAL", "PLAN", "SCENARIO"]
    assert SERIES_ORDER[0] == "ACTUAL" and SERIES_ORDER[-1] == "COMPETITOR"


def test_board_hides_contributions_without_drill_down(svc, tree):
    """★★★ 하위 조직별 기여는 **경영진만** 본다(사용자 결정 ③).

    ⚠️ 그래도 합계와 **커버리지는 남긴다** — 커버리지를 빼면 부분 합계를 전체로 오해한다."""
    r = svc.rollup(tree["bat"].node_id, {tree["p1"].node_id: {"매출": 600}})
    staff = build_board(tree["bat"].node_id, series={"ACTUAL": {"매출": 600}},
                        rollups={"ACTUAL": r}, drill_down=False)
    assert "contributions" not in staff["rollups"]["ACTUAL"]
    assert staff["rollups"]["ACTUAL"]["contributions_hidden"] is True
    assert staff["rollups"]["ACTUAL"]["coverage"]["missing"]
    assert any("기여 내역은 표시하지 않았습니다" in n for n in staff["notes"])

    exec_ = build_board(tree["bat"].node_id, series={"ACTUAL": {"매출": 600}},
                        rollups={"ACTUAL": r}, drill_down=True)
    assert exec_["rollups"]["ACTUAL"]["contributions"]


def test_board_carries_rollup_warnings(svc, tree):
    """★★ 집계 경고(이중 계상·부분 합계)가 보드까지 올라온다 — 집계 단계에서만 알리면
    경영진 화면에는 깨끗한 숫자만 남는다."""
    vals = {tree["bat"].node_id: {"매출": 1000}, tree["p1"].node_id: {"매출": 600}}
    r = svc.rollup(tree["bat"].node_id, vals)
    b = build_board(tree["bat"].node_id, series={"ACTUAL": {}}, rollups={"ACTUAL": r},
                    drill_down=True)
    assert any("이중 계상" in n for n in b["notes"])


def test_board_marks_competitor_rows_as_reference(tree):
    """★★ 경쟁사 행이 있으면 **참조이며 공식 수치가 아니라는 사실**을 보드가 말한다(§7.3-5)."""
    b = build_board(tree["bat"].node_id, series={"ACTUAL": {"매출": 1}},
                    competitor_rows=[{"key": "매출", "competitor": {"value": 900}}])
    assert any("공식 수치가 아닙니다" in n for n in b["notes"])


def test_board_is_quiet_when_only_one_state(tree):
    """★ 계열이 하나면 혼합 경고를 띄우지 않는다 — 항상 뜨는 경고는 아무도 읽지 않는다."""
    b = build_board(tree["bat"].node_id, series={"ACTUAL": {"매출": 1}})
    assert b["notes"] == []
