"""사용 보류 집중 API 시험의 조직/정책 격리. 운영 읽기 없음."""
import json
import pytest


def pytest_configure(config):
    #: ⚠️ 격리 러너는 `--noconftest` 로 돌고 `tests/plugin_test_auth.py` 도 안 읽는다.
    #:   그 파일이 등록하는 표식을 여기서도 «같은 뜻으로» 등록해 둔다 — 안 하면
    #:   「Unknown mark」 경고가 남고, 경고가 쌓이면 진짜 경고를 못 본다.
    #: ★ 표식의 «동작» 은 저쪽 플러그인에 있다. 여기서는 이름만 안다 — 격리 러너에는
    #:   주입 자체가 없으므로 이 파일의 시험은 언제나 실제 인증 경로를 쓴다.
    config.addinivalue_line(
        "markers",
        "real_auth: principal 주입 없이 **실제 세션**으로 인증한다(인증·권한 경로 검증).")


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
