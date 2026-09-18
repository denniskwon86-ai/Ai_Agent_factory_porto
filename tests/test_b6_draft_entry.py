"""[DRAFT-ENTRY-01] 초안 진입 확인 — **경계를 받지 않고 «찾는다».** 2026-09-15.

이 파일이 지키는 것 여섯.

  ① ★★★ **요청이 경계를 싣지 않는다** — 서버가 초안의 소유 문맥을 «찾고» 선택 문맥과
     대조한다. 기존 `GET /drafts/{id}` 는 `context_root_id` 를 «인자로 받는다» — 그러면
     프런트가 경계를 지어내야 하고, 지어낸 값이 현재 선택과 다르면 다른 문맥이 열린다
  ② **종류를 검증한다** — 지원하지 않는 종류를 «조용히 열지» 않는다
  ③ **판본을 검증한다** — 없는 판본은 열리지 않는다
  ④ **소유를 검증한다** — 다른 회사·모드·조직의 초안은 같은 문구로 404
  ⑤ **초안 원문·승인 상태를 주지 않는다** — 「볼 수 있는가」만 답한다
  ⑥ **조회가 자원을 만들지 않는다**

⚠️ 권한 판정은 기존 `_authorize` 가 한다. 여기서 그것을 다시 시험하지 «않되»,
  「부르는가」와 「그 판정이 실제로 막는가」는 HTTP 로 확인한다.
"""
from __future__ import annotations

import json

import pytest

from tests.test_b3_studio_api import (  # noqa: F401
    PREFIX, _boundary, _headers, _ok, _save, studio_api,
)
from tests.test_b3_studio_drafts import (  # noqa: F401
    PATCH, _count, _db, enforced_org, isolated_stores, real_studio,
)
from tests.test_b3_studio_bootstrap import _events, _files, _make_bootstrap  # noqa: F401

#: ★ 권한 층의 `missing()` 과 «같은 문구» 여야 한다. 여기에 손으로 적어 두면 제품이
#:   바뀔 때 시험만 옛말을 하므로, 제품에서 가져온다.
from core.enterprise_context.process_configuration import missing as _missing

HIDDEN = str(_missing())


def entry(env, draft_id, *, kind="blueprint", revision=1, headers=None, **params):
    query = {"kind": kind, "revision": revision, **params}
    return env.client.get(PREFIX + f"/drafts/{draft_id}/entry-metadata", params=query,
                          headers=headers if headers is not None else _headers(env))


def reason(response):
    detail = response.json().get("detail")
    return detail.get("reason_code") if isinstance(detail, dict) else detail


# ── ① ★★★ 요청이 경계를 싣지 않는다 ──────────────────────────────────────
def test_entry_confirms_without_the_caller_supplying_any_boundary(studio_api):
    """★★★ 이 파일의 이유다. 질의에 `context_root_id` 가 **없다.**

    서버가 초안이 들고 있는 경계를 «찾아» 선택 문맥(헤더)과 대조한다."""
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=draft["revision"])
    assert response.status_code == 200, response.text
    data = _ok(response)
    assert data["draft_id"] == draft["draft_id"] and data["draft_kind"] == "blueprint"
    assert data["revision"] == draft["revision"]
    assert data["ownership"] == {
        "tenant_id": env.boundary.tenant_id, "context_root_id": env.boundary.context_root_id,
        "entity_mode": env.boundary.entity_mode, "scope_node_id": env.boundary.scope_node_id}
    assert data["viewing_context"] == {
        "tenant_id": "tenant_default", "scope_node_id": env.boundary.scope_node_id,
        "entity_mode": "REAL"}


def test_a_supplied_boundary_is_not_what_decides(studio_api):
    """⚠️ 질의에 남의 경계를 적어 보내도 **판정이 바뀌지 않는다.**

    이 경로는 경계를 인자로 «받지 않으므로» 그런 값은 아무 뜻이 없다."""
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=draft["revision"],
                     context_root_id="somebody-elses-root", scope_node_id="somebody-elses-scope")
    assert response.status_code == 200, response.text


def test_the_exact_key_set_is_fixed(studio_api):
    """⚠️ 정확히 이 집합이다. 느슨하게 풀지 않는다 — 이 단언이 「응답에 뭐가 더 따라
    나오지 않는가」를 지키는 유일한 통제다."""
    env = studio_api
    draft = _save(env)
    data = _ok(entry(env, draft["draft_id"], revision=draft["revision"]))
    assert set(data) == {"draft_id", "draft_kind", "revision", "ownership", "viewing_context"}
    assert set(data["ownership"]) == {"tenant_id", "context_root_id", "entity_mode", "scope_node_id"}
    assert set(data["viewing_context"]) == {"tenant_id", "scope_node_id", "entity_mode"}


# ── ⑤ 초안 원문·상태를 주지 않는다 ────────────────────────────────────────
def test_the_answer_carries_no_draft_content_or_decision_state(studio_api):
    """★ 진입 확인은 「볼 수 있는가」만 답한다. 요구사항 원문·지문·승인 상태를 주지 않는다."""
    env = studio_api
    draft = _save(env)
    body = entry(env, draft["draft_id"], revision=draft["revision"]).text
    #: ⚠️ `blueprint` 는 **종류 이름으로** 정당하게 실린다 — 딱 한 번, 그 자리에만.
    assert body.count("blueprint") == 1
    assert json.loads(body)["data"]["draft_kind"] == "blueprint"
    for leaked in ("digest", "process_ref", "owner_actor", "head_revision",
                   "content", "DRAFT", "APPROVED", "patch"):
        assert leaked not in body, f"진입 확인이 «{leaked}» 를 흘렸다: {body[:200]}"


# ── ② 종류 검증 — 조용히 열지 않는다 ──────────────────────────────────────
def test_consultation_is_refused_as_unsupported_not_silently_opened(studio_api):
    """⚠️⚠️ 상담에는 **판본 개념이 없는데** URL 문법은 판본을 필수로 받는다.

    확인할 대상이 없는 값을 그냥 버리면 kit_app `releaseId` 와 **같은 결함**이 된다.
    「지원 전」임을 서버가 **말한다** — 그리고 그 말은 「없다」와 구분된다."""
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], kind="consultation", revision=draft["revision"])
    assert response.status_code == 422, response.text
    assert reason(response) == "STUDIO_DRAFT_KIND_UNSUPPORTED"


@pytest.mark.parametrize("kind", ["", "  ", "BLUEPRINT", "project", "blueprint2", "../blueprint"])
def test_an_unknown_kind_is_refused(studio_api, kind):
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], kind=kind, revision=draft["revision"])
    assert response.status_code == 422, response.text
    assert reason(response) == "STUDIO_DRAFT_KIND_INVALID"


def test_the_kind_is_echoed_only_after_it_is_accepted(studio_api):
    """확인된 종류만 응답에 실린다 — 요청 문자열을 그대로 메아리치지 않는다."""
    env = studio_api
    draft = _save(env)
    assert _ok(entry(env, draft["draft_id"], revision=draft["revision"]))["draft_kind"] == "blueprint"


# ── ③ 판본 검증 ───────────────────────────────────────────────────────────
def test_a_revision_that_does_not_exist_is_hidden(studio_api):
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=draft["revision"] + 7)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("bad", [0, -1])
def test_a_non_positive_revision_is_refused(studio_api, bad):
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=bad)
    assert response.status_code == 422, response.text
    assert reason(response) == "STUDIO_DRAFT_REVISION_INVALID"


@pytest.mark.parametrize("bad", ["", "one", "1.5", "1e3"])
def test_a_malformed_revision_is_refused_before_anything_is_read(studio_api, bad):
    env = studio_api
    draft = _save(env)
    assert entry(env, draft["draft_id"], revision=bad).status_code == 422


def test_an_older_revision_is_confirmable(studio_api):
    """★ 판본은 «지금 최신» 이 아니라 **요청한 그 판본**을 확인한다."""
    env = studio_api
    first = _save(env)
    second = _save(env, first)
    assert second["revision"] > first["revision"]
    assert _ok(entry(env, first["draft_id"], revision=first["revision"]))["revision"] == first["revision"]
    assert _ok(entry(env, first["draft_id"], revision=second["revision"]))["revision"] == second["revision"]


# ── ④ 소유 검증 — 전부 같은 문구 ──────────────────────────────────────────
def test_a_draft_that_does_not_exist_is_hidden(studio_api):
    env = studio_api
    response = entry(env, "no-such-draft-id", revision=1)
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["message"] == HIDDEN


@pytest.mark.parametrize("axis", ["tenant", "mode", "scope"])
def test_another_context_cannot_confirm_the_draft(studio_api, axis):
    """다른 회사·모드·조직에서 고른 문맥으로는 열리지 않는다."""
    env = studio_api
    draft = _save(env)
    headers = _headers(env)
    if axis == "tenant":
        headers["X-Enterprise-Tenant"] = "foreign-tenant.test.invalid"
    elif axis == "mode":
        headers["X-Entity-Mode"] = "VIRTUAL"
    else:
        headers["X-Enterprise-Scope"] = env.boundary.context_root_id + "-not-mine"
    response = entry(env, draft["draft_id"], revision=draft["revision"], headers=headers)
    assert response.status_code in (404, 422), response.text
    assert "blueprint" not in response.text


def test_a_valid_but_unrelated_scope_selection_cannot_confirm(studio_api):
    """★★★ 조직에 **실재하는** 다른 부서를 골라도 열리지 않는다.

    ⚠️⚠️ 이 시험이 왜 따로 필요한가 — 앞선 관문(`explicit_context`)은 「그 노드가 조직에
      있는가」만 본다. 없는 노드를 적은 시험은 **거기서** 막히므로, 권한 층을 통째로
      지워도 초록이었다(실측: `authorize` 호출을 제거해도 28건 전부 통과).
      실재하는 남의 부서를 골라야 **권한 층만이** 막는 자리가 된다."""
    env = studio_api
    draft = _save(env)
    headers = _headers(env, scope=env.org.NODES[env.org.DEPT_B])
    response = entry(env, draft["draft_id"], revision=draft["revision"], headers=headers)
    assert response.status_code == 404, response.text
    assert "blueprint" not in response.text


def test_a_user_without_read_rights_cannot_confirm(studio_api):
    """다른 부서 구성원은 **같은 문맥을 골라도** 이 초안을 볼 수 없다.

    ★ 문맥이 아니라 «사람» 이 막히는 자리다 — 이것도 권한 층만이 판정한다."""
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=draft["revision"],
                     headers=_headers(env, env.other))
    assert response.status_code == 404, response.text
    assert "blueprint" not in response.text


def test_a_missing_selection_is_refused_and_no_department_fallback(studio_api):
    """★ 선택 문맥을 **명시**해야 한다 — 주체의 소속 부서로 슬쩍 채우지 않는다."""
    env = studio_api
    draft = _save(env)
    response = entry(env, draft["draft_id"], revision=draft["revision"],
                     headers=_headers(env, scope=False))
    assert response.status_code == 422, response.text
    assert reason(response) == "PROCESS_CONTEXT_REQUIRED"


def test_the_hidden_answer_is_the_same_for_missing_and_for_out_of_context(studio_api):
    """★ 「없는 초안」과 「있지만 내 문맥이 아닌 초안」이 **같은 문구**여야 한다."""
    env = studio_api
    draft = _save(env)
    headers = _headers(env)
    headers["X-Enterprise-Scope"] = env.boundary.context_root_id + "-not-mine"
    missing = entry(env, "no-such-draft-id", revision=1)
    foreign = entry(env, draft["draft_id"], revision=draft["revision"], headers=headers)
    assert missing.status_code == 404
    assert foreign.status_code == 404, foreign.text
    #: ★★★ 두 답이 «글자까지» 같아야 한다. 다르면 그 차이가 존재를 알려 준다.
    assert foreign.json()["detail"]["message"] == missing.json()["detail"]["message"]
    assert foreign.json()["detail"]["reason_code"] == missing.json()["detail"]["reason_code"]


# ── ⑥ 조회가 자원을 만들지 않는다 ─────────────────────────────────────────
def test_confirming_creates_nothing(studio_api):
    env = studio_api
    draft = _save(env)
    before = (_count(env, "advisor_v2_revisions"), _count(env, "advisor_v2_requests"),
              _count(env, "advisor_v2_bootstraps"))
    for _ in range(3):
        entry(env, draft["draft_id"], revision=draft["revision"])
    entry(env, "no-such-draft-id", revision=1)
    after = (_count(env, "advisor_v2_revisions"), _count(env, "advisor_v2_requests"),
             _count(env, "advisor_v2_bootstraps"))
    assert before == after, "진입 확인이 자원을 만들었다"


def test_confirming_does_not_approve_or_promote(studio_api):
    """조회 가능 ≠ 승인·승격. 확인만으로 결정 원장이 늘지 않는다."""
    env = studio_api
    draft = _save(env)
    before = _count(env, "decision_ledger_events")
    entry(env, draft["draft_id"], revision=draft["revision"])
    assert _count(env, "decision_ledger_events") == before
