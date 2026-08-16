"""품질 결과 텔레메트리(§10.3 `quality_outcomes` / §8.3 실패 원인 분류) 검증.

이 테스트가 잠그는 것은 **숫자가 아니라 구분**이다.
  ① '사람이 승인함' ≠ '사람에게 묻지 않음'
  ② '원인 미분류' ≠ '원인 없음(정상)'
  ③ 공급자 장애 ≠ 산출물 결함
셋 중 하나라도 무너지면 이 지표는 있는 것보다 나쁘다 — 틀린 방향의 개선을 유도하기 때문이다.
"""
import json

import pytest

from core import quality_telemetry as qt


class _S:
    """ProjectState 대역(계측은 getattr 만 쓴다)."""
    def __init__(self, name="P1", ws="./projects/p1", dept="D-BAT", task="WBS-001",
                 hops=0, dev_retry=0, stage="QA"):
        self.project_name = name
        self.workspace_root = ws
        self.owner_dept_id = dept
        self.current_sprint_task_id = task
        self.supervisor_hops = hops
        self.developer_retry_count = dev_retry
        self.current_stage = stage


@pytest.fixture()
def log(tmp_path, monkeypatch):
    """로그 경로를 tmp 로 돌린다 — 개발 DB/실로그 상태에 의존하면 회귀를 놓친다."""
    p = tmp_path / "quality_outcomes.jsonl"
    monkeypatch.setattr(qt, "_LOG_PATH", str(p))
    return p


# ── 기록 ─────────────────────────────────────────────────────────────────────
def test_gate_record_keeps_verdict_and_returns_outcome_id(log):
    oid = qt.record_gate(_S(hops=2, dev_retry=1), gate_name="QA", artifact_type="QA",
                         verdict="ROLLBACK", score=0.4, threshold=0.7,
                         blocking_fails=["fr_coverage"], failed_checks=["fr_coverage", "api_spec"])
    assert oid
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["verdict"] == "ROLLBACK"      # 원문 보존
    assert rec["pass_fail"] == "FAIL"        # 파생값
    assert rec["gate_loops"] == 2 and rec["dev_retry_count"] == 1   # 두 재시도 축 분리
    assert rec["project_id"] == "p1" and rec["owner_dept_id"] == "D-BAT"
    assert rec["root_cause"] == qt.CAUSE_UNCLASSIFIED   # 점수 미달의 원인은 지어내지 않는다


def test_score_failure_is_not_auto_blamed_on_the_model(log):
    """★ 점수 미달을 `model_quality` 로 자동 분류하지 않는다.

    자동 귀속은 통계를 그럴싸하게 만들지만, '요구사항이 모호해서 미달'인 건까지 모델 탓으로
    돌려 **모델 교체/프롬프트 수정이라는 틀린 처방**을 유도한다."""
    qt.record_gate(_S(), gate_name="SUPERVISOR", artifact_type="SUPERVISOR",
                   verdict="REWORK", score=0.55, threshold=0.7, failed_checks=["biz_fit"])
    out = qt.resolve_outcomes(qt.read_events())
    assert out[0]["root_cause"] == qt.CAUSE_UNCLASSIFIED
    assert "biz_fit" not in (out[0]["root_cause"] or "")
    assert out[0]["failed_checks"] == ["biz_fit"]      # 사실(어느 기준이 미달)은 남는다


# ── §8.3 분류 규칙 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind,expected", [
    ("PROVIDER_TIMEOUT", qt.CAUSE_EXTERNAL_ENV),
    ("NETWORK", qt.CAUSE_EXTERNAL_ENV),
    ("QUOTA", qt.CAUSE_EXTERNAL_ENV),
    ("STRUCTURED_PARSE", qt.CAUSE_OUTPUT_CONTRACT),
    ("CAPACITY", qt.CAUSE_OUTPUT_CONTRACT),
    ("UNKNOWN", qt.CAUSE_UNCLASSIFIED),
])
def test_generation_kind_is_mapped_not_reinvented(kind, expected):
    cause, rule = qt.classify_generation_kind(kind)
    assert cause == expected
    assert (rule != "") == (expected != qt.CAUSE_UNCLASSIFIED)   # 분류엔 항상 근거가 붙는다


def test_provider_failure_is_not_counted_as_code_defect(log):
    """★★ 공급자 타임아웃이 '모델 품질'로 집계되면 안 된다.

    실측 사고 이력이 있다(228.6s·420.0s·77.0s 타임아웃 3건이 개발자 재작업 예산을 태웠다).
    계측에서 같은 오귀속이 반복되면 사고가 데이터로 굳는다."""
    qt.record_failure(_S(), gate_name="Frontend", artifact_type="CODE", kind="PROVIDER_TIMEOUT")
    agg = qt.aggregate(qt.resolve_outcomes(qt.read_events()))
    assert agg["by_root_cause"] == {qt.CAUSE_EXTERNAL_ENV: 1}
    assert qt.CAUSE_MODEL_QUALITY not in agg["by_root_cause"]


@pytest.mark.parametrize("log_text,expected", [
    ("[src/App.tsx] SyntaxError: Unexpected token '}'", qt.CAUSE_MODEL_QUALITY),
    ("npm ERR! code ENOTFOUND registry.npmjs.org", qt.CAUSE_EXTERNAL_ENV),
    ("프론트엔드 산출물이 비어 있습니다(출력 절단/파싱 실패 의심).", qt.CAUSE_OUTPUT_CONTRACT),
    ("ERROR: usage: pytest: error: unrecognized arguments", qt.CAUSE_TEST_HARNESS),
    ("", qt.CAUSE_UNCLASSIFIED),
    ("알 수 없는 실패", qt.CAUSE_UNCLASSIFIED),
])
def test_build_error_classification(log_text, expected):
    cause, rule = qt.classify_build_error(log_text)
    assert cause == expected


# ── 사람 판정 ────────────────────────────────────────────────────────────────
def test_no_human_decision_is_not_acceptance(log):
    """★★ 이 파일에서 가장 중요한 테스트.

    사람에게 묻지 않은 게이트가 `accepted` 로 집계되면, 이 지표는 "사람이 승인한 산출물 비율"을
    부풀려 보고하는 거짓말이 된다."""
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="PASS", score=0.9)
    agg = qt.aggregate(qt.resolve_outcomes(qt.read_events()))
    assert agg["human_acceptance"]["accepted"] == 0
    assert agg["human_acceptance"]["no_human_decision"] == 1


def test_human_decision_joins_to_gate_record(log):
    oid = qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="PASS", score=0.9)
    qt.record_human_decision(_S(), gate_name="QA", accepted=False,
                             actor="u1", feedback="단가 근거가 없습니다", outcome_id=oid)
    out = qt.resolve_outcomes(qt.read_events())
    assert len(out) == 1                                   # 접합됐다(줄이 늘지 않는다)
    assert out[0]["human_acceptance"] == qt.HUMAN_REVISION_REQUESTED
    assert out[0]["rework_reason"] == "단가 근거가 없습니다"   # 사람이 쓴 사유가 최선의 rework_reason


def test_orphan_human_decision_is_kept_not_dropped(log):
    """HOTL 재개처럼 게이트 기록과 짝이 없는 사람 판정도 사실이므로 버리지 않는다."""
    qt.record_human_decision(_S(stage="PLANNING"), gate_name="HOTL", accepted=True, actor="u1")
    agg = qt.aggregate(qt.resolve_outcomes(qt.read_events()))
    assert agg["human_acceptance"]["accepted"] == 1
    assert agg["totals"]["evaluations"] == 0        # 게이트 평가 건수는 늘지 않는다


# ── 사후 분류 ────────────────────────────────────────────────────────────────
def test_human_classification_overrides_and_records_actor(log):
    oid = qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="REWORK",
                         score=0.5, threshold=0.7, failed_checks=["req_clarity"])
    assert qt.record_classification(oid, qt.CAUSE_REQUIREMENT_AMBIGUITY, actor="u1", note="RFP 모호")
    out = qt.resolve_outcomes(qt.read_events())
    assert out[0]["root_cause"] == qt.CAUSE_REQUIREMENT_AMBIGUITY
    assert out[0]["root_cause_rule"] == "human"      # 규칙이 아니라 사람이 정한 값임을 남긴다
    assert out[0]["classified_by"] == "u1"


def test_classification_requires_identity_and_existing_target(log):
    oid = qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="FAIL")
    assert qt.record_classification(oid, qt.CAUSE_MODEL_QUALITY, actor="") is False   # 익명 금지
    assert qt.record_classification("nope", qt.CAUSE_MODEL_QUALITY, actor="u1") is False  # 없는 대상
    assert qt.record_classification(oid, "made_up_cause", actor="u1") is False        # 임의 어휘 금지


def test_classification_inherits_scope_identity(log):
    """★ 분류 이벤트가 부서 식별을 상속하지 않으면 부서 스코프 조회에서 조용히 사라진다."""
    oid = qt.record_gate(_S(dept="D-BAT"), gate_name="QA", artifact_type="QA", verdict="FAIL")
    qt.record_classification(oid, qt.CAUSE_TEST_HARNESS, actor="u1")
    ev = [e for e in qt.read_events() if e["event"] == "classification"][0]
    assert ev["owner_dept_id"] == "D-BAT" and ev["project_id"] == "p1"


# ── 집계 ─────────────────────────────────────────────────────────────────────
def test_unclassified_ratio_is_none_when_no_failures(log):
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="PASS", score=1.0)
    agg = qt.aggregate(qt.resolve_outcomes(qt.read_events()))
    # 실패가 0건인데 비율 0.0 을 주면 "미분류가 없다(=건강하다)"로 읽힌다. 없는 값은 None 이다.
    assert agg["unclassified_ratio"] is None


def test_aggregate_axes(log):
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="PASS", score=0.9)
    qt.record_gate(_S(hops=3), gate_name="QA", artifact_type="QA", verdict="ROLLBACK",
                   blocking_fails=["fr_coverage"])
    qt.record_failure(_S(), gate_name="BUILD", artifact_type="CODE",
                      error_log="SyntaxError: invalid syntax")
    agg = qt.aggregate(qt.resolve_outcomes(qt.read_events()))
    assert agg["totals"] == {"evaluations": 3, "passed": 1, "failed": 2}
    assert agg["by_gate"]["QA"]["rollback"] == 1
    assert agg["by_gate"]["QA"]["max_gate_loops"] == 3
    assert agg["by_root_cause"][qt.CAUSE_MODEL_QUALITY] == 1
    assert agg["unclassified_failures"] == 1
    assert agg["unclassified_ratio"] == 0.5
    assert len(qt.unclassified_failures(qt.resolve_outcomes(qt.read_events()))) == 1


def test_reused_gate_names_do_not_collide_across_projects(log):
    qt.record_gate(_S(name="A", ws="./projects/a", dept="D1"), gate_name="QA",
                   artifact_type="QA", verdict="PASS")
    qt.record_gate(_S(name="B", ws="./projects/b", dept="D2"), gate_name="QA",
                   artifact_type="QA", verdict="FAIL")
    assert len(qt.read_events(project="A")) == 1
    assert qt.read_events(project="A")[0]["owner_dept_id"] == "D1"


def test_broken_line_is_skipped_not_fatal(log, tmp_path):
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="PASS")
    with open(log, "a", encoding="utf-8") as f:
        f.write('{"event": "gate", "outcome_i\n')   # 실행 중 append 로 잘린 줄
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="FAIL")
    assert len(qt.read_events()) == 2


# ── API 계약 ─────────────────────────────────────────────────────────────────
# 함수 단위로는 통과하는데 HTTP 로는 404 인 계열(경로 변수에 잡아먹힘)을 따로 잠근다.
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


@pytest.fixture()
def client(log, seeded_org):
    """품질 API를 조직이 구성된 정상 운영 문맥에서 검증한다.

    이 라우트가 현재 조직 범위를 판정하지 않는다는 이유로 조직 0건 부트스트랩에 기대면,
    향후 범위 통제를 추가했을 때 인증·권한 회귀가 거짓 초록이 된다.
    """
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


@pytest.mark.parametrize("path", [
    "/api/v1/telemetry/quality/summary",
    "/api/v1/telemetry/quality/raw",
    "/api/v1/telemetry/quality/unclassified",
])
def test_quality_routes_are_reachable(client, path):
    r = client.get(path)
    assert r.status_code != 404, f"{path} 미도달: {r.text[:200]}"


def test_summary_reports_gaps_not_silence(client, log):
    qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="FAIL", score=0.3)
    d = client.get("/api/v1/telemetry/quality/summary").json()["data"]
    assert d["unclassified_failures"] == 1
    assert d["human_acceptance"]["no_human_decision"] == 1
    assert "no_human_decision" in d["note"]      # 화면이 오독하지 않게 응답 자체가 설명한다


def test_classify_requires_identity_and_scope(client, log):
    oid = qt.record_gate(_S(), gate_name="QA", artifact_type="QA", verdict="FAIL")
    body = {"outcome_id": oid, "root_cause": "requirement_ambiguity"}
    # 식별 없이(기본 사용자 없음) 분류 시도 → 401. 가짜 분류자를 만들어 넣지 않는다.
    import config
    _saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = ""
    try:
        assert client.post("/api/v1/telemetry/quality/classify", json=body).status_code == 401
    finally:
        config.ORG_DEFAULT_USER_ID = _saved

    from tests import org_seed
    actor = org_seed.MEMBER_A
    r = client.post("/api/v1/telemetry/quality/classify", json=body,
                    headers={"X-Factory-User": actor})
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/telemetry/quality/classify",
                       json={"outcome_id": "nope", "root_cause": "model_quality"},
                       headers={"X-Factory-User": actor}).status_code == 404
    assert client.post("/api/v1/telemetry/quality/classify",
                       json={"outcome_id": oid, "root_cause": "made_up"},
                       headers={"X-Factory-User": actor}).status_code == 400
