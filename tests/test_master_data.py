"""core/master_data.py — M1 경량 기준정보 저장소 검증 (LLM 0콜).

핵심 불변식:
  - 개정 = 새 버전 삽입(version+1) + 구판 retire → 리니지 보존(복합 PK).
  - 별칭 텍스트 감지는 단어경계 매칭으로 오탐(부분문자열)을 막는다.
  - 결정론적 주입: 별칭 히트 1순위 + 도메인 핵심(is_core) 2순위, 상한 적용.
  - attr_schema 위반은 저장 거부.
"""
import os
import tempfile
import pytest
from core.master_data import MasterData, MasterDataError


@pytest.fixture
def md():
    path = os.path.join(tempfile.mkdtemp(), "master.db")
    m = MasterData(db_path=path)
    m.create_type("process", "공정", attr_schema={"표준리드타임_h": {"type": "number", "required": False}})
    m.create_type("kpi", "KPI")
    return m


class _State:
    """ProjectState 대역(get_master_context 는 getattr 로만 접근)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_type_crud_and_duplicate(md):
    types = {t["type_id"] for t in md.list_types()}
    assert {"process", "kpi"} <= types
    with pytest.raises(MasterDataError):
        md.create_type("process", "중복")  # 중복 거부


def test_delete_type_blocked_when_records_exist(md):
    md.create_or_revise_record("PROC-A", "process", "공정A")
    with pytest.raises(MasterDataError):
        md.delete_type("process")  # 레코드 존재 → 거부
    # 사용 안 하는 타입은 삭제 가능
    md.delete_type("kpi")
    assert "kpi" not in {t["type_id"] for t in md.list_types()}


def test_master_code_validation(md):
    with pytest.raises(MasterDataError):
        md.create_or_revise_record("bad code!", "process", "x")  # 형식 위반


def test_attr_schema_validation(md):
    with pytest.raises(MasterDataError):
        md.create_or_revise_record("PROC-A", "process", "공정A",
                                   attributes={"표준리드타임_h": "문자열아님"})  # number 여야 함


def test_revision_preserves_lineage(md):
    md.create_or_revise_record("PROC-A", "process", "공정A", attributes={"표준리드타임_h": 72})
    rec2 = md.create_or_revise_record("PROC-A", "process", "공정A개정", attributes={"표준리드타임_h": 60})
    assert rec2["version"] == 2
    assert rec2["name"] == "공정A개정"
    assert rec2["attributes"]["표준리드타임_h"] == 60
    # 개정 계보(이력 2건, supersedes 링크)
    assert len(rec2["history"]) == 2
    assert rec2["supersedes"] == "PROC-A@1"
    # 현행은 1건만(구판 retire)
    current = md.list_records(type_id="process")
    assert len([r for r in current if r["master_code"] == "PROC-A"]) == 1


def test_retire_is_soft(md):
    md.create_or_revise_record("PROC-A", "process", "공정A")
    assert md.retire_record("PROC-A") is True
    assert md.get_record("PROC-A") is None                     # 현행 조회에서 사라짐
    assert md.retire_record("PROC-A") is False                 # 이미 폐기
    # 이력은 include_retired 로 조회 가능(물리 삭제 아님)
    assert any(r["master_code"] == "PROC-A" for r in md.list_records(include_retired=True))


def test_alias_detection_word_boundary(md):
    md.create_or_revise_record("PROC-ASSY", "process", "조립 공정",
                               aliases=["ASSY", "조립"], domains=[], is_core=False)
    assert md.select_for_injection("조립 라인을 검토", [])          # 히트
    assert not md.select_for_injection("조립식 가구", [])            # '조립식' 오탐 없음
    assert md.select_for_injection("the ASSY step", [])             # 대문자
    assert md.select_for_injection("the assy step", [])             # 소문자(IGNORECASE)
    assert not md.select_for_injection("passembly test", [])        # 부분문자열 오탐 없음


def test_injection_priority_alias_then_core(md):
    # 별칭 히트(비-core) + 도메인 핵심(core) 공존 시 별칭 히트가 앞선다
    md.create_or_revise_record("PROC-ASSY", "process", "조립 공정",
                               aliases=["조립"], domains=["mfg"], is_core=False)
    md.create_or_revise_record("KPI-CORE", "kpi", "핵심 KPI",
                               domains=["mfg"], is_core=True)
    sel = md.select_for_injection("조립 공정을 다룬다", ["mfg"])
    codes = [r["master_code"] for r in sel]
    assert "PROC-ASSY" in codes and "KPI-CORE" in codes
    assert codes.index("PROC-ASSY") < codes.index("KPI-CORE")     # 별칭 히트 우선


def test_core_requires_domain_match(md):
    md.create_or_revise_record("KPI-CORE", "kpi", "핵심 KPI", domains=["mfg"], is_core=True)
    assert md.select_for_injection("무관 텍스트", ["mfg"])           # 도메인 일치 → 주입
    assert not md.select_for_injection("무관 텍스트", ["finance"])    # 도메인 불일치 → 미주입


def test_get_master_context_from_state(md):
    md.create_or_revise_record("PROC-ASSY", "process", "조립 공정",
                               attributes={"표준리드타임_h": 72}, aliases=["조립"], domains=["mfg"])
    state = _State(master_domains=["mfg"], initial_idea="조립 공정 자동화",
                   rfp_summary="", prd_summary="", template_id="default")
    ctx = md.get_master_context(state)
    assert "기준정보 (Master Data)" in ctx
    assert "PROC-ASSY" in ctx and "표준리드타임_h=72" in ctx
    # 미매칭 도메인/텍스트면 빈 문자열
    empty = md.get_master_context(_State(master_domains=["x"], initial_idea="관계없음",
                                         rfp_summary="", prd_summary="", template_id="default"))
    assert empty == ""


def test_csv_import_partial_success(md):
    rows = [
        {"master_code": "PROC-1", "name": "공정1", "domains": "mfg", "aliases": "P1;공정하나",
         "attr:표준리드타임_h": "24"},
        {"master_code": "bad!", "name": "잘못", "domains": "", "aliases": ""},  # 형식 위반 → 실패
    ]
    report = md.import_csv_rows(rows, "process")
    assert report["imported"] == 1
    assert report["total"] == 2
    assert len(report["failed"]) == 1
    rec = md.get_record("PROC-1")
    assert rec["attributes"]["표준리드타임_h"] == 24  # 숫자 변환
    assert "P1" in rec["aliases"]
