# ==========================================
# 부서 시드 · 하드코딩 제거 검증 (설계서 Phase 1)
#
# 부서 정보가 factory_control.py 안에 하드코딩 딕셔너리 3개로 흩어져 있었다.
# 부서 하나를 추가·개명·이동·폐지하려면 코드를 고치고 배포해야 했고, 세 맵이 서로 어긋나도
# 아무도 알아채지 못했다(한 곳에만 추가하면 조용히 누락).
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.org_seed as org_seed
from core.org_directory import OrgDirectory


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    od = OrgDirectory(db_path=str(tmp_path / "seed.db"))
    monkeypatch.setattr(org_seed, "org_directory", od, raising=True)
    return od


def test_legacy_maps_removed_from_factory_control():
    """하드코딩 맵 3개가 코드에서 실제로 사라졌는지 — 이관의 핵심이다."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "api", "routes", "factory_control.py"), encoding="utf-8").read()
    for name in ("domain_agents_map", "domain_templates_map", "domain_ko_map"):
        assert f"{name} = {{" not in src, f"{name} 하드코딩이 아직 남아 있습니다"


def test_seed_creates_root_and_departments(seeded):
    res = org_seed.seed_departments()
    assert "hq" in res["created"]
    depts = {d["dept_id"]: d for d in seeded.list_departments()}
    assert "sales" in depts and depts["sales"]["parent_id"] == "hq"
    assert depts["sales"]["default_template_id"] == "manufacturing-market-forecast"
    assert depts["procurement"]["domain_agents"] == ["Purchase_Agent"]
    assert depts["quality"]["path"] == "/hq/quality/"


def test_seed_is_idempotent_and_does_not_overwrite(seeded):
    org_seed.seed_departments()
    seeded.update_department("sales", name_ko="영업본부")     # 운영 중 개편
    res = org_seed.seed_departments()
    assert res["created"] == [], "재시드가 기존 부서를 다시 만들면 안 됩니다"
    assert seeded.get_department("sales")["name_ko"] == "영업본부", "시드가 개편본을 덮어쓰면 안 됩니다"


def test_resolve_config_reflects_revision(seeded):
    """부서를 개명·재설정하면 코드 수정 없이 조회 결과가 따라와야 한다 — 이관의 목적."""
    org_seed.seed_departments()
    before = org_seed.resolve_department_config("marketing")
    assert before["template_id"] == "content-marketing"
    seeded.update_department("marketing", name_ko="브랜드마케팅",
                             default_template_id="manufacturing-qc",
                             domain_agents=["Marketing_Agent", "Quality_Agent"])
    after = org_seed.resolve_department_config("marketing")
    assert after["name_ko"] == "브랜드마케팅"
    assert after["template_id"] == "manufacturing-qc"
    assert after["agents"] == ["Marketing_Agent", "Quality_Agent"]


def test_resolve_config_unknown_is_safe(seeded):
    """미등록 부서는 빈 설정 — 호출부가 기본값으로 동작해야 하고 예외로 막으면 안 된다."""
    cfg = org_seed.resolve_department_config("nope")
    assert cfg["template_id"] == "" and cfg["agents"] == []


def test_retired_department_not_returned_as_active(seeded):
    org_seed.seed_departments()
    seeded.retire_department("accounting")
    assert org_seed.resolve_department_config("accounting")["template_id"] == ""


def test_reconcile_builds_ownership_mirror(seeded, tmp_path):
    import json
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "project_meta.json").write_text(
        json.dumps({"dept_id": "sales", "owner_user_id": "u1", "visibility": "dept"}),
        encoding="utf-8")
    lib = tmp_path / "library" / "r1"
    lib.mkdir(parents=True)
    (lib / "release.json").write_text(
        json.dumps({"dept_id": "rnd", "visibility": "company"}), encoding="utf-8")

    res = org_seed.reconcile_ownership(str(tmp_path / "projects"), str(tmp_path / "library"))
    assert res == {"projects": 1, "releases": 1}
    own = seeded.get_ownership("project", "p1")
    assert own["dept_id"] == "sales" and own["owner_user_id"] == "u1"
    assert seeded.get_ownership("release", "r1")["visibility"] == "company"


def test_reconcile_tolerates_missing_dirs(seeded):
    assert org_seed.reconcile_ownership("no_such_dir", "also_none") == {"projects": 0, "releases": 0}
