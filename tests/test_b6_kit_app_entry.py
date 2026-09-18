"""B6 업무 앱 진입 확인 HTTP. 실제 격리 설치·PDP·SQLite 를 쓴다.

★★★ **목록 수준 판정**이다(사용자 결정 2026-09-15, `docs/design_l2_studio_entry_readers_2026-09-15.md`
  §6-6·§6-7). 화면 목록이 보여 주는 것과 같은 조건으로 답한다 — 목록에 보이는 앱을
  링크로는 못 여는 상태를 만들지 않는다.

⚠️ 실제 실행·브라우저·앱 승인 증거가 아니다. main strict-writes 런너 전용.
"""
from types import SimpleNamespace

import pytest

from tests import org_seed as org
from tests.test_b1_process_configuration import headers
from tests.test_b2_installation import (  # noqa: F401
    _apply, _prepared, _read, _state, _tables, enforced_org, installation, workspace,
)


@pytest.fixture
def kitapi(installation, monkeypatch):
    """실제 B2 설치로 인스턴스를 만들고 data-preparation 라우터만 mount 한다."""
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import data_preparation_control as dp

    w = installation
    operation = _prepared(w)
    _apply(w, operation)
    # 인스턴스 참조는 승인 뒤 해석된 업무판의 template_sources 에 있다.
    instance_id = str(_read(w)["payload"]["template_sources"][0]["kit_instance_ref"])
    assert instance_id, "설치가 인스턴스를 만들지 않았다"
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "")
    app = FastAPI()
    app.include_router(dp.router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, instance_id=instance_id, env=w, operation=operation)


def url(instance_id, app_id):
    return f"/api/v1/data-preparation/instances/{instance_id}/apps/{app_id}/entry-metadata"


def get(api, app_id, instance_id=None, actor=org.MANAGER_ROOT, scope=None):
    return api.client.get(url(instance_id or api.instance_id, app_id), headers=headers(actor, scope))


def apps_of(api, actor=org.MANAGER_ROOT):
    """화면 목록이 보여 주는 앱. 진입 확인은 **이것과 같은 답**을 해야 한다."""
    response = api.client.get(
        f"/api/v1/data-preparation/instances/{api.instance_id}/apps", headers=headers(actor))
    assert response.status_code == 200, response.text
    return [str(row["app_id"]) for row in response.json()["data"]["apps"]]


HIDDEN = "현재 문맥에서 업무 앱을 찾을 수 없습니다."


def test_entry_answers_the_same_set_as_the_visible_list(kitapi):
    """★ 목록에 보이는 앱은 **전부** 진입 확인을 통과한다 — 두 답이 갈리지 않는다."""
    listed = apps_of(kitapi)
    assert listed, "설치 직후 목록이 비어 이 회귀가 공허해진다"
    for app_id in listed:
        response = get(kitapi, app_id)
        assert response.status_code == 200, f"{app_id}: {response.text}"
        assert response.json()["data"]["app_id"] == app_id


def test_exact_response_shape_and_no_readiness_or_contract_leak(kitapi):
    """진입 확인은 「볼 수 있는가」만 답한다. 준비도·계약·릴리스는 주지 않는다."""
    app_id = apps_of(kitapi)[0]
    body = get(kitapi, app_id).json()
    assert set(body) == {"status", "data"} and body["status"] == "success"
    value = body["data"]
    assert set(value) == {"instance_id", "app_id", "app_label", "ownership", "viewing_context"}
    assert set(value["ownership"]) == {"tenant_id", "enterprise_scope_id", "entity_mode"}
    assert set(value["viewing_context"]) == {"tenant_id", "scope_node_id", "entity_mode"}
    assert value["app_label"] and isinstance(value["app_label"], str)
    # 확장 필드가 조용히 섞여 나가지 않는다.
    text = get(kitapi, app_id).text
    for leaked in ("readiness_state", "contract_status", "contract_revision",
                   "release_id", "lifecycle_state", "built_datasets", "user_message"):
        assert leaked not in text, f"{leaked} 가 진입 확인 응답에 새어 나갔다"


@pytest.mark.parametrize("app_id", ["APP-99", "NOT-A-REAL-APP", "APP-01x"])
def test_unknown_app_is_404_without_data(kitapi, app_id):
    response = get(kitapi, app_id)
    assert response.status_code == 404 and response.json()["detail"] == HIDDEN
    assert "data" not in response.json()


def test_missing_instance_uses_the_same_wording_as_missing_app(kitapi):
    """★★★ 없는 인스턴스와 없는 앱이 **다른 문구**면 인스턴스 존재 여부가 샌다.

    ⚠️ 이 회귀는 실제로 그랬던 구현을 고치고 넣은 것이다 — `_instance_or_404` 의 기존
      문구를 그대로 통과시키면 「키트 인스턴스를 찾을 수 없습니다」가 나온다."""
    listed = apps_of(kitapi)
    absent = get(kitapi, listed[0], instance_id="ki_nosuchinstance")
    unknown = get(kitapi, "APP-99")
    assert absent.status_code == unknown.status_code == 404
    assert absent.json()["detail"] == unknown.json()["detail"] == HIDDEN


@pytest.mark.parametrize("app_id", ["has space", "앱", "x" * 161, "APP@01", "APP.01"])
def test_malformed_app_id_is_rejected_with_400(kitapi, app_id):
    """★ 라우팅을 통과하는 형식 위반은 **400 으로 끊는다.**

    ⚠️ 처음에는 `in (400, 404, 405)` 로 느슨하게 썼다. 그러면 **형식 검사를 통째로 지워도
      404 로 통과**한다 — 가짜 통과다. 조사하면서 직접 확인하고 조였다."""
    response = get(kitapi, app_id)
    assert response.status_code == 400, response.text
    assert "data" not in response.text


@pytest.mark.parametrize("app_id", ["../etc", "a/b", ""])
def test_path_shaped_app_id_never_reaches_the_handler(kitapi, app_id):
    """슬래시·빈 값은 라우팅에서 갈린다. 다른 자원으로 새지 않는 것만 확인한다."""
    response = get(kitapi, app_id)
    assert response.status_code in (404, 405), response.text
    assert "data" not in response.text


def test_lookup_creates_nothing(kitapi):
    """조회가 자원을 만들지 않는다 — 없는 대상을 물어도 DB 가 그대로다."""
    before = _state(kitapi.env)
    for app_id in ("APP-99", "NOT-A-REAL-APP"):
        assert get(kitapi, app_id).status_code == 404
    assert get(kitapi, "APP-01", instance_id="ki_nosuchinstance").status_code == 404
    assert _state(kitapi.env) == before


def test_ownership_reports_the_instance_not_the_caller_context(kitapi):
    """소유는 인스턴스의 것이다. 호출자 문맥을 소유로 되돌려 주지 않는다."""
    app_id = apps_of(kitapi)[0]
    value = get(kitapi, app_id).json()["data"]
    row = next(r for r in _tables(kitapi.env, "dp")["kit_instances"]
               if str(r["instance_id"]) == kitapi.instance_id)
    assert value["ownership"]["tenant_id"] == str(row["tenant_id"])
    assert value["ownership"]["enterprise_scope_id"] == str(row["scope_node_id"])
    assert value["ownership"]["entity_mode"] == str(row["entity_mode"])


def test_unauthenticated_caller_is_rejected(kitapi):
    app_id = apps_of(kitapi)[0]
    response = kitapi.client.get(url(kitapi.instance_id, app_id))
    assert response.status_code in (401, 403), response.text
    assert "data" not in response.text


@pytest.mark.parametrize("actor", [org.MANAGER_ROOT, org.ADMIN])
def test_sibling_selection_is_hidden_like_v2_list(kitapi, actor):
    """두 조직을 읽더라도 B 선택으로 A의 v2 인스턴스를 열 수 없다."""
    app_id = apps_of(kitapi)[0]
    selected = org.NODES[org.DEPT_B]
    listed = kitapi.client.get(
        f"/api/v1/data-preparation/instances/{kitapi.instance_id}/apps",
        headers=headers(actor, selected))
    assert listed.status_code == 404, listed.text
    entry = get(kitapi, app_id, actor=actor, scope=selected)
    assert entry.status_code == 404, entry.text
    assert entry.json()["detail"] == HIDDEN


def test_v2_missing_explicit_context_matches_list(kitapi):
    auth = {"X-Factory-User": org.MANAGER_ROOT}
    listed = kitapi.client.get(
        f"/api/v1/data-preparation/instances/{kitapi.instance_id}/apps", headers=auth)
    assert listed.status_code == 422, listed.text
    entry = kitapi.client.get(url(kitapi.instance_id, "APP-01"), headers=auth)
    assert entry.status_code == 422, entry.text


def test_v2_read_only_viewer_can_enter_without_run_permission(kitapi):
    listed = apps_of(kitapi, org.VIEWER_A)
    assert listed
    assert get(kitapi, listed[0], actor=org.VIEWER_A).status_code == 200


@pytest.fixture
def legacy_id(kitapi):
    from core import demo_vertical_slice as dv
    store = kitapi.env["store"]
    dv.register_kit(store)
    row = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION, kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=kitapi.env["boundary"].tenant_id, scope_node_id=org.NODES[org.DEPT_A],
        entity_mode="REAL", label="격리 legacy 진입 시험", created_by=org.MEMBER_A)
    return row["instance_id"]


@pytest.mark.parametrize("actor", [org.VIEWER_A, org.EXEC])
def test_legacy_without_run_permission_hides_existence(kitapi, legacy_id, actor):
    present = get(kitapi, "APP-01", instance_id=legacy_id, actor=actor)
    absent = get(kitapi, "APP-01", instance_id="ki_missing", actor=actor)
    assert present.status_code == absent.status_code == 404, present.text
    assert present.json()["detail"] == absent.json()["detail"] == HIDDEN


def test_legacy_allowed_entry_still_matches_list(kitapi, legacy_id):
    listed = kitapi.client.get(
        f"/api/v1/data-preparation/instances/{legacy_id}/apps",
        headers=headers(org.MEMBER_A))
    assert listed.status_code == 200, listed.text
    assert any(row["app_id"] == "APP-01" for row in listed.json()["data"]["apps"])
    entry = get(kitapi, "APP-01", instance_id=legacy_id, actor=org.MEMBER_A)
    assert entry.status_code == 200, entry.text


def test_legacy_unrestricted_list_policy_is_not_narrowed(kitapi, legacy_id):
    selected = org.NODES[org.DEPT_B]
    listed = kitapi.client.get(
        f"/api/v1/data-preparation/instances/{legacy_id}/apps", headers=headers(org.ADMIN, selected))
    assert listed.status_code == 200, listed.text
    entry = get(kitapi, "APP-01", instance_id=legacy_id, actor=org.ADMIN, scope=selected)
    assert entry.status_code == 200, entry.text


@pytest.mark.parametrize("legacy", [False, True])
def test_revocation_during_lookup_is_hidden_before_response(kitapi, legacy_id, monkeypatch, legacy):
    """프로필을 읽는 동안 다른 연결에서 회수해도 캐시된 Principal로 응답하지 않는다."""
    from api.routes import data_preparation_control as dp
    from core.org_directory import OrgDirectory
    instance_id = legacy_id if legacy else kitapi.instance_id
    assert get(kitapi, "APP-01", instance_id=instance_id, actor=org.MEMBER_A).status_code == 200
    original = dp._kit_profile_or_503

    def revoke(inst):
        profile = original(inst)
        other = OrgDirectory(str(kitapi.env["paths"]["org"]))
        assert other.delete_user(org.MEMBER_A, actor=org.ADMIN)
        return profile

    monkeypatch.setattr(dp, "_kit_profile_or_503", revoke)
    entry = get(kitapi, "APP-01", instance_id=instance_id, actor=org.MEMBER_A)
    assert entry.status_code == 404, entry.text
    assert entry.json()["detail"] == HIDDEN


@pytest.mark.parametrize("during_read", [False, True])
def test_selected_scope_revoked_with_target_rights_preserved(kitapi, legacy_id, monkeypatch, during_read):
    """대상 A 권한은 남아도 선택 B 권한이 회수되면 캐시 문맥으로 응답하지 않는다."""
    from api.routes import data_preparation_control as dp
    from core.org_directory import OrgDirectory
    directory = kitapi.env["directory"]
    directory.set_user_roles(org.MEMBER_A, {org.DEPT_A: "member", org.DEPT_B: "member"}, actor=org.ADMIN)
    cached = directory.resolve_scope(org.MEMBER_A)
    selected = org.NODES[org.DEPT_B]
    assert selected in cached.readable_scope_nodes
    assert get(kitapi, "APP-01", instance_id=legacy_id, actor=org.MEMBER_A, scope=selected).status_code == 200

    def revoke():
        other = OrgDirectory(str(kitapi.env["paths"]["org"]))
        other.set_user_roles(org.MEMBER_A, {org.DEPT_A: "member"}, actor=org.ADMIN)
        assert directory.resolve_scope(org.MEMBER_A) is cached
        fresh = directory.resolve_scope(org.MEMBER_A, fresh=True)
        assert org.NODES[org.DEPT_A] in fresh.readable_scope_nodes
        assert selected not in fresh.readable_scope_nodes

    if during_read:
        original = dp._kit_profile_or_503
        def read_and_revoke(inst):
            profile = original(inst)
            revoke()
            return profile
        monkeypatch.setattr(dp, "_kit_profile_or_503", read_and_revoke)
    else:
        revoke()
    entry = get(kitapi, "APP-01", instance_id=legacy_id, actor=org.MEMBER_A, scope=selected)
    assert entry.status_code == 404, entry.text
    assert entry.json()["detail"] == HIDDEN


def test_authority_failure_at_recheck_is_503_without_metadata(kitapi, monkeypatch):
    from api.routes import data_preparation_control as dp
    from core.org_directory import OrgDirectory
    directory = kitapi.env["directory"]
    original = dp._kit_profile_or_503
    resolve = OrgDirectory.resolve_scope
    profile_read = False

    def observe(inst):
        nonlocal profile_read
        profile = original(inst)
        profile_read = True
        return profile

    def unavailable(self, *args, **kwargs):
        if profile_read and kwargs.get("fresh"):
            raise OSError("SYNTHETIC_PRIVATE_FAILURE")
        return resolve(self, *args, **kwargs)

    monkeypatch.setattr(dp, "_kit_profile_or_503", observe)
    # singleton 메서드를 바꾸면 복구된 bound method가 copy.copy의 fresh를 오염시킨다.
    assert "resolve_scope" not in directory.__dict__
    with monkeypatch.context() as patch:
        patch.setattr(OrgDirectory, "resolve_scope", unavailable)
        entry = get(kitapi, "APP-01")
    assert OrgDirectory.resolve_scope is resolve
    assert "resolve_scope" not in directory.__dict__
    assert entry.status_code == 503, entry.text
    assert "data" not in entry.json()
    assert "SYNTHETIC_PRIVATE_FAILURE" not in entry.text


def test_entry_does_not_compute_readiness_or_contract_and_preserves_data(kitapi, monkeypatch):
    from api.routes import data_preparation_control as dp
    from core import kit_app_contract as kac
    before = _state(kitapi.env)

    def forbidden(*args, **kwargs):
        raise AssertionError("진입 확인은 준비도/계약을 평가하지 않는다")

    monkeypatch.setattr(dp, "_app_readiness", forbidden)
    monkeypatch.setattr(kac, "read_v2", forbidden)
    entry = get(kitapi, "APP-01", actor=org.VIEWER_A)
    assert entry.status_code == 200, entry.text
    assert _state(kitapi.env) == before
