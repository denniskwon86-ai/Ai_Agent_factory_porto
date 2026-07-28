# ==========================================
# 프로젝트 소유권 1급 속성화 (설계서 Phase 3)
#
# 핵심 계약 둘:
#  ① `_write_project_meta` 는 소유권을 **None 이면 보존**한다. 템플릿만 바꾸려는 호출부가
#     많은데 거기서 소유권이 초기화되면 프로젝트가 조용히 무소속이 되어 권한 필터에서 사라진다.
#  ② 소유권 **미기록** 자원은 목록에서 막지 않는다. 마이그레이션 전 기존 프로젝트가 전부
#     안 보이면 기능이 통째로 멈춘다 — 하위호환이 우선이다.
# ==========================================
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.deps import Principal
from api.routes.factory_control import (_ownership_visible, _read_project_meta,
                                        _read_project_ownership, _write_project_meta)
from core.org_directory import AccessScope


def _p(**kw):
    return Principal(user_id=kw.pop("user_id", "u"), scope=AccessScope(**kw))


def test_ownership_roundtrip(tmp_path):
    ws = str(tmp_path)
    _write_project_meta(ws, "default", owner_dept_id="sales", owner_user_id="bob",
                        visibility="company", nature="enterprise")
    own = _read_project_ownership(ws)
    assert own["owner_dept_id"] == "sales"
    assert own["owner_user_id"] == "bob"
    assert own["visibility"] == "company"
    assert own["nature"] == "enterprise"


def test_ownership_preserved_when_writing_other_fields(tmp_path):
    """★ 템플릿만 바꾸는 호출이 소유권을 날리면 안 된다."""
    ws = str(tmp_path)
    _write_project_meta(ws, "default", owner_dept_id="sales", visibility="company")
    _write_project_meta(ws, "manufacturing-qc")           # 소유권 인자 없이 호출
    own = _read_project_ownership(ws)
    assert own["owner_dept_id"] == "sales", "소유권이 초기화되면 프로젝트가 무소속이 된다"
    assert own["visibility"] == "company"
    assert _read_project_meta(ws)[0] == "manufacturing-qc", "템플릿은 정상 갱신되어야 한다"


def test_knowledge_packs_still_preserved(tmp_path):
    """P0-1 회귀 방지 — 소유권 추가로 기존 보존 로직이 깨지지 않았는지."""
    ws = str(tmp_path)
    _write_project_meta(ws, "default", knowledge_pack_ids=["pack_a"])
    _write_project_meta(ws, "default", owner_dept_id="rnd")
    with open(os.path.join(ws, "project_meta.json"), encoding="utf-8") as f:
        d = json.load(f)
    assert d["knowledge_pack_ids"] == ["pack_a"]
    assert d["owner_dept_id"] == "rnd"


def test_read_ownership_of_missing_file_is_safe(tmp_path):
    own = _read_project_ownership(str(tmp_path / "nope"))
    assert own["owner_dept_id"] == "" and own["visibility"] == "dept"


# ── 목록 가시성 ──────────────────────────────────────────────────────────
def test_unrecorded_ownership_is_visible(tmp_path):
    """마이그레이션 전 기존 프로젝트가 사라지면 안 된다."""
    p = _p(unrestricted=False, readable_dept_ids=frozenset({"sales"}))
    assert _ownership_visible(p, {"owner_dept_id": "", "owner_user_id": "", "visibility": "dept"})


def test_unrestricted_sees_everything(tmp_path):
    p = _p(unrestricted=True)
    assert _ownership_visible(p, {"owner_dept_id": "secret", "visibility": "dept"})


def test_dept_scope_filters(tmp_path):
    p = _p(unrestricted=False, readable_dept_ids=frozenset({"sales"}))
    assert _ownership_visible(p, {"owner_dept_id": "sales", "visibility": "dept"})
    assert not _ownership_visible(p, {"owner_dept_id": "rnd", "visibility": "dept"})


def test_company_visibility_crosses_dept(tmp_path):
    p = _p(unrestricted=False, readable_dept_ids=frozenset({"sales"}))
    assert _ownership_visible(p, {"owner_dept_id": "rnd", "visibility": "company"})


def test_personal_owner_sees_own(tmp_path):
    p = _p(user_id="bob", unrestricted=False, readable_dept_ids=frozenset())
    assert _ownership_visible(p, {"owner_dept_id": "rnd", "owner_user_id": "bob",
                                  "visibility": "personal"})
    assert not _ownership_visible(p, {"owner_dept_id": "rnd", "owner_user_id": "eve",
                                      "visibility": "personal"})


def test_state_model_accepts_ownership_fields():
    """ProjectState 는 extra='forbid' 라 선언이 없으면 ValidationError 로 즉사한다."""
    from state_models import ProjectState
    s = ProjectState.model_validate({"project_name": "p", "owner_dept_id": "sales",
                                     "owner_user_id": "bob", "visibility": "company"})
    assert s.owner_dept_id == "sales" and s.visibility == "company"
