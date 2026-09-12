"""사용 보류 집중 API 시험의 조직/정책 격리. 운영 읽기 없음."""
import json
import pytest


@pytest.fixture
def enforced_org(tmp_path, monkeypatch):
    from core import scope_policy
    from core.data_preparation.store import data_preparation_store
    from core.enterprise_context.repository import ecm_repository
    from core.org_directory import org_directory
    from tests import org_seed
    for obj, name in ((data_preparation_store, "preparation"), (ecm_repository, "ecm"),
                      (org_directory, "org")):
        monkeypatch.setattr(obj, "db_path", str(tmp_path / f"{name}.db"))
    monkeypatch.setattr(data_preparation_store, "_prepared_for", None)
    ecm_repository._init_db()
    org_directory._init_db()
    org_seed.seed(org_directory)
    org_seed.seed_ecm(ecm_repository, org_directory)
    org_directory._invalidate()
    path = tmp_path / "scope_policy.json"
    path.write_text(json.dumps({"org_enforce": True}), encoding="utf-8")
    monkeypatch.setattr(scope_policy, "_POLICY_PATH", str(path))
    assert scope_policy.org_enforce() is True
    yield org_seed
    org_directory._invalidate()
