import json
from types import SimpleNamespace

import pytest

from core.enterprise_context.models import EnterpriseEntity
from core.enterprise_context.repository import EcmRepository
from core.installation_context import InstallationContextError, apply_file, apply_settings


def _settings():
    return {
        "tenant_id": "tenant-install",
        "company_name": "LS MnM",
        "company_legal_name": "LS MnM 주식회사",
        "organization": {
            "entity_id": "ent-install",
            "legal_node_id": "org-install",
            "legal_node_code": "LS_MNM",
            "legal_dept_id": "hq",
            "scope_nodes": [
                {"node_id": "plant-a", "code": "PLANT_A",
                 "name_ko": "제련공장", "dept_id": "demo_smelting"},
                {"node_id": "plant-b", "code": "PLANT_B",
                 "name_ko": "배터리소재 공장"},
            ],
        },
    }


def test_설치본_회사_법인_업무범위를_같은_tenant에_결속한다(tmp_path):
    repo = EcmRepository(str(tmp_path / "ecm.db"))
    cfg = SimpleNamespace(ECM_DEFAULT_TENANT_ID="old")

    out = apply_settings(_settings(), repo=repo, config_module=cfg)

    assert out["tenant_id"] == cfg.ECM_DEFAULT_TENANT_ID == "tenant-install"
    assert repo.get_tenant("tenant-install")["name_ko"] == "LS MnM"
    assert repo.get_entity("ent-install").tenant_id == "tenant-install"
    assert repo.get_node("org-install").tenant_id == "tenant-install"
    assert repo.get_node("plant-a").tenant_id == "tenant-install"
    assert repo.get_node("plant-a").dept_id == "demo_smelting"
    assert repo.parents("plant-a", "OPERATING_PARENT") == ["org-install"]


def test_같은_설정을_두번_적용해도_조직이_늘지_않는다(tmp_path):
    repo = EcmRepository(str(tmp_path / "ecm.db"))
    cfg = SimpleNamespace(ECM_DEFAULT_TENANT_ID="old")

    first = apply_settings(_settings(), repo=repo, config_module=cfg)
    second = apply_settings(_settings(), repo=repo, config_module=cfg)

    assert first == second
    assert len(repo.list_entities("tenant-install", "REAL")) == 1
    assert len(repo.list_nodes("tenant-install", status="ACTIVE")) == 3
    assert len(repo.list_edges("tenant-install", "OPERATING_PARENT")) == 2


def test_다른_tenant의_기존_id를_덮지_않고_아무것도_쓰기전에_막는다(tmp_path):
    repo = EcmRepository(str(tmp_path / "ecm.db"))
    repo.upsert_entity(EnterpriseEntity(
        entity_id="ent-install", tenant_id="tenant-other", name_ko="다른 회사",
        entity_mode="REAL", status="ACTIVE"))
    cfg = SimpleNamespace(ECM_DEFAULT_TENANT_ID="old")

    with pytest.raises(InstallationContextError, match="다른 tenant"):
        apply_settings(_settings(), repo=repo, config_module=cfg)

    assert cfg.ECM_DEFAULT_TENANT_ID == "old"
    assert repo.get_tenant("tenant-install") is None


def test_중복_범위_id는_반쪽_결속을_만들기전에_거부한다(tmp_path):
    repo = EcmRepository(str(tmp_path / "ecm.db"))
    cfg = SimpleNamespace(ECM_DEFAULT_TENANT_ID="old")
    settings = _settings()
    settings["organization"]["scope_nodes"][1]["node_id"] = "plant-a"

    with pytest.raises(InstallationContextError, match="중복"):
        apply_settings(settings, repo=repo, config_module=cfg)

    assert repo.get_tenant("tenant-install") is None
    assert repo.get_entity("ent-install") is None


def test_설정파일_판독과_적용은_같은_계약을_쓴다(tmp_path):
    path = tmp_path / "instance.json"
    path.write_text(json.dumps(_settings(), ensure_ascii=False), encoding="utf-8")
    repo = EcmRepository(str(tmp_path / "ecm.db"))
    cfg = SimpleNamespace(ECM_DEFAULT_TENANT_ID="old")

    out = apply_file(str(path), repo=repo, config_module=cfg)
    assert out["applied"] is True
    assert repo.get_node("plant-b").default_parent_id == "org-install"


def test_손상된_설정은_기본값으로_접지_않는다(tmp_path):
    path = tmp_path / "instance.json"
    path.write_text("[", encoding="utf-8")

    with pytest.raises(InstallationContextError, match="읽지 못했습니다"):
        apply_file(str(path), repo=EcmRepository(str(tmp_path / "ecm.db")),
                   config_module=SimpleNamespace(ECM_DEFAULT_TENANT_ID="old"))
