"""키트 명시 반려의 실제 임시 HTTP/PDP/원장 시험. 격리 runner 전용."""
import pytest

from tests import org_seed as org
from tests.test_b3_kit_api import (api_client, workspace, enforced_org, installation, kit,
                                 create, url, headers, revision_body, success)


def rejection_body(row):
    return dict(revision=row["revision"], expected_digest=row["semantic_fingerprint"],
                rationale="명시 반려 API 합성 시험")


def test_actual_rejection_retry_and_new_draft_revision(api_client, kit):
    first = create(api_client, kit)
    body = rejection_body(first)
    rejected = success(api_client.post(url(kit, "contract/reject"), json=body, headers=headers(org.DATA_ADMIN)))
    assert rejected["status"] == "REJECTED"
    assert success(api_client.post(url(kit, "contract/reject"), json=body, headers=headers(org.DATA_ADMIN))) == rejected
    assert api_client.post(url(kit, "contract/v2/approve"), json=revision_body(first, approve=True),
                           headers=headers(org.DATA_ADMIN)).status_code == 409
    assert create(api_client, kit, expected_revision=1)["revision"] == 2


@pytest.mark.parametrize("actor", [None, org.VIEWER_A, org.MEMBER_A])
def test_rejection_route_guard_before_unknown_instance(api_client, actor):
    response = api_client.post(url(suffix="contract/reject"),
        json=dict(revision=1, expected_digest="a" * 64, rationale="합성 시험"),
        headers=headers(actor) if actor else {})
    assert response.status_code == (401 if actor is None else 403)


def test_rejection_requires_reviewed_digest_and_no_caller_authority(api_client):
    response = api_client.post(url(suffix="contract/reject"),
        json=dict(revision=1, expected_digest="a" * 64, rationale="합성 시험", actor_id=org.ADMIN),
        headers=headers(org.DATA_ADMIN))
    assert response.status_code == 422
