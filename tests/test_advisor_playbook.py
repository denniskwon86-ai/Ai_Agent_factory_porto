# ==========================================
# 업무·데이터 설계 상담 플레이북 (마스터 명세서 §4 / M0 백로그 1)
#
# 검증하는 계약 넷:
#  ① **준비도는 결정론이다** — LLM 판단이 아니라 규칙. 같은 입력이면 같은 점수가 나와야 한다.
#     이 숫자가 "프로젝트를 시작할 준비가 됐나"를 결정하므로 재현 불가능하면 쓸 수 없다.
#  ② **모르는 것을 보유로 치지 않는다** — 상태가 없는 요구사항은 `missing`. 낙관 편향이
#     착수 판단을 망친다.
#  ③ **미측정 차원을 만점으로 주지 않는다** — 플레이북이 그 차원을 정의하지 않은 것이
#     "준비됐다"는 뜻이 아니다.
#  ④ **조건부 요구사항은 required 일 수 없다**(저작 불변식) — required 인데 특정 선택지에서만
#     켜지면, 추천안만 고른 사용자에게 필수 데이터가 활성화되지 않아 준비도가 부풀려진다.
#     실제로 이 플레이북 초안이 21건 중 7건만 활성화되는 상태였다.
# ==========================================
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.advisor_playbook import (BUSINESS_TYPES, READINESS_DIMENSIONS, DataRequirement,
                                   ExternalSpec, Playbook, PlaybookQuestion, QuestionOption,
                                   active_requirement_keys, list_playbooks, load_playbook,
                                   score_readiness, validate_playbook)


def _req(key, **kw):
    base = dict(key=key, canonical_term=key, necessity="required",
                readiness_dimension="master_completeness",
                gap_impact="영향", next_action="조치")
    base.update(kw)
    return DataRequirement(**base)


def _q(qid, *opts, **kw):
    return PlaybookQuestion(id=qid, question="?", options=list(opts), **kw)


def _opt(label, recommended=False, unlocks=None, value=""):
    return QuestionOption(label=label, recommended=recommended, value=value,
                          unlocks_requirements=list(unlocks or []))


def _pb(**kw):
    base = dict(playbook_id="t", name_ko="테스트", recommended_sequence=["1) 무언가"])
    base.update(kw)
    return Playbook(**base)


# ── 로더 ─────────────────────────────────────────────────────────────────
def test_business_planning_playbook_loads():
    pb = load_playbook("business_planning")
    assert pb is not None, "경영계획 플레이북이 로드되지 않으면 M0 전체가 성립하지 않는다"
    assert pb.business_type == "planning_budget"
    assert pb.business_type in BUSINESS_TYPES


def test_shipped_playbook_has_no_authoring_warnings():
    """★ 저작 회귀 방지 — 배포되는 플레이북은 경고 0 이어야 한다."""
    pb = load_playbook("business_planning")
    assert validate_playbook(pb) == []


def test_shipped_playbook_weights_sum_to_100():
    assert sum(load_playbook("business_planning").weights().values()) == 100


def test_unknown_playbook_returns_none():
    assert load_playbook("nope_xyz") is None


def test_invalid_id_rejected():
    with pytest.raises(ValueError):
        load_playbook("../etc/passwd")


def test_corrupt_file_returns_none_not_raises(tmp_path, monkeypatch):
    """플레이북 하나가 깨져도 상담 기능 전체가 500 이 되면 안 된다."""
    import core.advisor_playbook as ap
    monkeypatch.setattr(ap, "PLAYBOOKS_DIR", str(tmp_path))
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
    assert ap.load_playbook("broken") is None
    assert ap.list_playbooks() == [], "손상 파일은 목록에서 건너뛴다"


def test_list_playbooks_includes_shipped():
    ids = [p["playbook_id"] for p in list_playbooks()]
    assert "business_planning" in ids


# ── §12 외부환경 인텔리전스 정렬 ──────────────────────────────────────────
def test_external_indicators_cover_spec_six():
    """§12.10 이 확정한 첫 외부지표 6종이 플레이북에 반영돼야 한다.
    M1 에서 원천 등록부를 만들 때 이 목록이 입력이 된다."""
    pb = load_playbook("business_planning")
    ext = {r.key for r in pb.data_requirements if r.requirement_type == "external"}
    assert ext == {"ext_fx", "ext_material", "ext_energy", "ext_rate",
                   "ext_demand_index", "ext_wage"}


def test_external_requirements_carry_grade_and_latency():
    """§12.2 등급과 §12.4 허용 지연이 없으면 M1 수집기가 판단할 근거가 없다."""
    pb = load_playbook("business_planning")
    for r in pb.data_requirements:
        if r.requirement_type == "external":
            assert r.external is not None, r.key
            assert r.external.grade in ("gold", "silver", "bronze"), r.key
            assert r.external.acceptable_latency, r.key
            assert r.external.vintage_required is True, f"{r.key}: 당시 발표값 재현이 필수(§12.5)"


# ── 저작 검증 규칙 ───────────────────────────────────────────────────────
def test_conditional_required_is_flagged():
    """★ 불변식 — required 를 조건부로 걸면 경고."""
    pb = _pb(data_requirements=[_req("a", necessity="required")],
             questions=[_q("Q1", _opt("예", True, ["a"]), _opt("아니오"))])
    assert any("조건부" in w for w in validate_playbook(pb))


def test_conditional_recommended_is_fine():
    pb = _pb(data_requirements=[_req("a", necessity="recommended")],
             questions=[_q("Q1", _opt("예", True, ["a"]), _opt("아니오"))])
    assert validate_playbook(pb) == []


def test_single_option_question_is_flagged():
    pb = _pb(questions=[_q("Q1", _opt("유일", True))])
    assert any("선택지가 2개 미만" in w for w in validate_playbook(pb))


def test_recommended_option_must_be_exactly_one():
    pb = _pb(questions=[_q("Q1", _opt("a"), _opt("b"))])
    assert any("추천 선택지" in w for w in validate_playbook(pb))
    pb2 = _pb(questions=[_q("Q1", _opt("a", True), _opt("b", True))])
    assert any("추천 선택지" in w for w in validate_playbook(pb2))


def test_dangling_requirement_reference_is_flagged():
    pb = _pb(questions=[_q("Q1", _opt("a", True, ["ghost"]), _opt("b"))])
    assert any("존재하지 않는 요구사항 키" in w for w in validate_playbook(pb))


def test_missing_gap_guidance_is_flagged():
    """점수만 주고 무엇을 하라고 못 알려주면 준비도가 쓸모없다(§4.3 F-DA-05)."""
    pb = _pb(data_requirements=[DataRequirement(key="a", canonical_term="A")])
    assert any("gap_impact/next_action" in w for w in validate_playbook(pb))


def test_external_without_spec_is_flagged():
    pb = _pb(data_requirements=[_req("a", requirement_type="external")])
    assert any("external 규격이 없습니다" in w for w in validate_playbook(pb))


def test_duplicate_keys_flagged():
    pb = _pb(data_requirements=[_req("a"), _req("a")])
    assert any("key 중복" in w for w in validate_playbook(pb))


# ── 조건부 활성화 ────────────────────────────────────────────────────────
def test_unconditional_requirements_always_active():
    pb = _pb(data_requirements=[_req("always"), _req("cond", necessity="recommended")],
             questions=[_q("Q1", _opt("예", True, ["cond"]), _opt("아니오"))])
    assert active_requirement_keys(pb, {}) == ["always"]


def test_picking_option_unlocks_its_requirements():
    pb = _pb(data_requirements=[_req("always"), _req("cond", necessity="recommended")],
             questions=[_q("Q1", _opt("예", True, ["cond"], value="yes"), _opt("아니오", value="no"))])
    assert active_requirement_keys(pb, {"Q1": ["yes"]}) == ["always", "cond"]
    assert active_requirement_keys(pb, {"Q1": ["no"]}) == ["always"], "안 고른 것은 켜지지 않는다"


def test_option_identity_falls_back_to_label():
    pb = _pb(data_requirements=[_req("cond", necessity="recommended")],
             questions=[_q("Q1", _opt("라벨로", True, ["cond"]), _opt("다른것"))])
    assert active_requirement_keys(pb, {"Q1": ["라벨로"]}) == ["cond"]


def test_shipped_playbook_defaults_activate_all_required():
    """★ 추천안만 눌러도 플레이북이 '필수'라 한 것은 전부 활성화되어야 한다."""
    pb = load_playbook("business_planning")
    answers = {q.id: [o.key() for o in q.options if o.recommended] for q in pb.questions}
    active = set(active_requirement_keys(pb, answers))
    required = {r.key for r in pb.data_requirements if r.necessity == "required"}
    assert required <= active, f"필수인데 비활성: {sorted(required - active)}"


# ── 준비도 산정 ──────────────────────────────────────────────────────────
def _five_dim_pb():
    """5축을 모두 정의한 플레이북 — 100점 만점이 측정 가능해진다."""
    return _pb(data_requirements=[
        _req("m", readiness_dimension="master_completeness"),
        _req("h", readiness_dimension="history_linkage"),
        _req("d", readiness_dimension="driver_coverage"),
        _req("q", readiness_dimension="quality_freshness"),
        _req("o", readiness_dimension="ownership"),
    ])


def test_all_held_is_100():
    pb = _five_dim_pb()
    r = score_readiness(pb, {k: "held" for k in ("m", "h", "d", "q", "o")})
    assert r["score"] == 100.0
    assert r["gaps"] == [] and r["blocking_gaps"] == []


def test_nothing_provided_is_zero_and_all_blocking():
    pb = _five_dim_pb()
    r = score_readiness(pb, {})
    assert r["score"] == 0.0
    assert len(r["blocking_gaps"]) == 5, "상태를 모르면 missing — 보유로 치지 않는다"


def test_needs_verification_counts_half():
    pb = _five_dim_pb()
    r = score_readiness(pb, {"m": "needs_verification", "h": "held", "d": "held",
                             "q": "held", "o": "held"})
    assert r["score"] == pytest.approx(87.5), "25점 축의 절반만 인정 → 100 - 12.5"
    assert [g["key"] for g in r["gaps"]] == ["m"], "검증 필요도 결손 목록에 올린다"
    assert r["blocking_gaps"] == [], "검증 필요는 '차단'이 아니다"


def test_unmeasured_dimension_is_not_free_marks():
    """★ 플레이북이 그 축을 정의하지 않은 것이 '준비됐다'는 뜻은 아니다."""
    pb = _pb(data_requirements=[_req("m", readiness_dimension="master_completeness")])
    r = score_readiness(pb, {"m": "held"})
    assert r["score"] == 25.0, "정의되지 않은 4축을 만점 처리하면 100 이 나와 거짓이 된다"
    assert r["measurable_max"] == 25
    assert r["unmeasured_weight"] == 75
    assert [d["measured"] for d in r["dimensions"]].count(True) == 1


def test_required_weighs_double_recommended():
    pb = _pb(data_requirements=[
        _req("req", necessity="required", readiness_dimension="master_completeness"),
        _req("rec", necessity="recommended", readiness_dimension="master_completeness"),
    ])
    # required(2) 보유 + recommended(1) 부족 → 2/3 × 25 = 16.67 (총점은 소수 1자리)
    r = score_readiness(pb, {"req": "held"})
    assert r["score"] == pytest.approx(16.7, abs=0.05)
    assert r["dimensions"][0]["score"] == pytest.approx(16.67, abs=0.01)


def test_optional_does_not_affect_score_but_is_reported():
    """있으면 좋은 것이 없는 것은 '준비되지 않음'의 근거가 될 수 없다."""
    pb = _pb(data_requirements=[
        _req("req", necessity="required", readiness_dimension="master_completeness"),
        _req("opt", necessity="optional", readiness_dimension="master_completeness"),
    ])
    r = score_readiness(pb, {"req": "held"})
    assert r["score"] == 25.0, "optional 부족이 감점하면 안 된다"
    opt_gap = next(g for g in r["gaps"] if g["key"] == "opt")
    assert opt_gap["counts_toward_score"] is False, "점수엔 안 넣되 숨기지도 않는다"


def test_gaps_carry_impact_and_next_action():
    """§4.3 F-DA-05 — 점수와 함께 결손 항목·영향·다음 조치를 반드시 표시한다."""
    pb = load_playbook("business_planning")
    r = score_readiness(pb, {})
    assert r["gaps"], "데이터가 없으면 결손이 나와야 한다"
    for g in r["gaps"]:
        if g["necessity"] != "optional":
            assert g["impact"] and g["next_action"], g["key"]


def test_gaps_sorted_required_missing_first():
    pb = _pb(data_requirements=[
        _req("z_opt", necessity="optional"),
        _req("y_rec", necessity="recommended"),
        _req("x_req_verify", necessity="required"),
        _req("a_req_missing", necessity="required"),
    ])
    r = score_readiness(pb, {"x_req_verify": "needs_verification"})
    assert [g["key"] for g in r["gaps"]][:2] == ["a_req_missing", "x_req_verify"]


def test_active_filter_shrinks_evaluation():
    pb = _five_dim_pb()
    r = score_readiness(pb, {"m": "held"}, active_requirements=["m"])
    assert r["evaluated_requirements"] == 1
    assert r["score"] == 25.0 and r["measurable_max"] == 25


def test_scoring_is_deterministic():
    """같은 입력 → 같은 점수. 준비도가 착수 판단 근거이므로 재현 가능해야 한다."""
    pb = load_playbook("business_planning")
    st = {"master_org": "held", "master_account": "needs_verification"}
    assert score_readiness(pb, st) == score_readiness(pb, st)


def test_unknown_status_treated_as_missing():
    pb = _pb(data_requirements=[_req("m")])
    assert score_readiness(pb, {"m": "존재하지않는상태"})["score"] == 0.0


# ── 선택형 질문이 기존 HOTL 형태와 호환되는가 ────────────────────────────
def test_question_shape_matches_clarification_contract():
    """`nodes/clarification.py` 가 만드는 형태와 같아야 `HOTLInput.tsx` 를 재사용할 수 있다:
    {id, question, why, multi, options:[{label, description, recommended}]}"""
    pb = load_playbook("business_planning")
    for q in pb.questions:
        d = q.model_dump()
        assert {"id", "question", "why", "multi", "options"} <= set(d)
        assert 2 <= len(q.options) <= 4, f"{q.id}: 선택지는 2~4개(§4.3 F-DA-02)"
        for o in q.options:
            assert {"label", "description", "recommended"} <= set(o.model_dump())


def test_questions_cover_required_stages():
    """§4.3 F-DA-02 — 목적·범위·시간·사용자·데이터·결정 단계를 우선 묻는다."""
    stages = {q.stage for q in load_playbook("business_planning").questions}
    assert {"purpose", "scope", "time", "users", "data", "decision"} <= stages
