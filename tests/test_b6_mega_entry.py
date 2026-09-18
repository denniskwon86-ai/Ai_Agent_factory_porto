"""[MEGA-ENTRY-01] 메가 진입 확인 — **관계는 서버가 판정한다.** 2026-09-15.

이 파일이 지키는 것 다섯.

  ① **하나의 확인 응답**이다 — 프런트가 두 번 물어 관계를 «추론» 하지 않는다
  ② ★★★ **양쪽이 다 가리켜야 관계다** — 소속의 출처가 둘(부모 `sub_projects_map`,
     자식 `parent_project_id`)이고 서로 다른 파일에 있다. 한쪽만 보면 조용히 뚫린다
  ③ **어디서 막혔는지 말하지 않는다** — 부모·자식·관계 실패가 전부 같은 404 다
  ④ **조회가 자원을 만들지 않는다** — 작업공간·상태 파일이 생기지 않는다
  ⑤ **소속을 못 읽으면** 부모 단독은 `is_mega_project=False`(기존 진입 보존),
     관계 주장(`?child=`)은 **404**(주장은 증명돼야 한다)

⚠️ 기존 `project` 진입 계약은 `tests/test_b6_project_entry.py` 가 지킨다. 여기서
  그것을 다시 시험하지 않되, **소속 두 칸이 늘어난 것**은 그 파일이 정확히 고정한다.
"""
import json

import pytest

from tests import org_seed as org
from tests.test_b5_input_drafts import PROJECT, api, enforced_org, headers, isolated_stores  # noqa: F401

MEGA = PROJECT                      # 부모로 쓰는 기존 합성 프로젝트
CHILD = "B6_MEGA_CHILD"
OUTSIDER = "B6_MEGA_OUTSIDER"


def url(project_id=MEGA, child=None):
    base = f"/api/v1/factory/{project_id}/entry-metadata"
    return base if child is None else f"{base}?child={child}"


def get(api, project_id=MEGA, child=None, actor=org.MEMBER_A, scope=None):
    return api.client.get(url(project_id, child), headers=headers(actor, scope))


def state_of(api, changes, root=None):
    """소속 정본(`latest_state.json`)을 고친다. 실행 상태 칸은 보존한다."""
    path = (root or api.root) / "latest_state.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    value.update(changes)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def make_project(api, project_id, *, dept=org.DEPT_A, state=None):
    """같은 문맥에 합성 프로젝트를 하나 더 만든다. 소유 부서만 바꿔 «다른 조직»을 만든다."""
    root = api.root.parent / project_id
    root.mkdir(parents=True)
    meta = {"tenant_id": "tenant_default", "enterprise_scope_id": org.NODES[dept],
            "entity_mode": "REAL", "runtime_document_version": "1.0",
            "owner_dept_id": dept, "owner_user_id": "", "visibility": "dept",
            "project_name": f"[합성] {project_id}"}
    (root / "project_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (root / "latest_state.json").write_text(
        json.dumps(state if state is not None else {}, ensure_ascii=False), encoding="utf-8")
    return root


def mega(api, *, children=(CHILD,), child_dept=org.DEPT_A, child_parent=MEGA, make_child=True):
    """부모를 메가로 세우고 자식을 만든다. 각 칸을 따로 비틀 수 있게 열어 둔다."""
    state_of(api, {"is_mega_project": True, "parent_project_id": "",
                   "sub_projects_map": {f"d{index}": value
                                        for index, value in enumerate(children)}})
    if make_child:
        make_project(api, CHILD, dept=child_dept,
                     state={"is_mega_project": False, "parent_project_id": child_parent})
    return api.root.parent / CHILD


# ── ① 정상 · 하나의 확인 응답 ──────────────────────────────────────────────
def test_parent_alone_reports_that_it_is_a_mega(api):
    """부모 단독 조회는 «메가인가»에만 답한다. 자식은 주지 않는다."""
    mega(api)
    value = get(api).json()["data"]
    assert value["is_mega_project"] is True and value["child"] is None


def test_a_plain_project_is_not_a_mega(api):
    """소속을 세우지 않은 기존 프로젝트는 그대로 False 다 — 기존 진입을 안 깬다."""
    assert get(api).json()["data"]["is_mega_project"] is False


def test_parent_and_child_are_confirmed_in_one_response(api):
    """★ 두 번 묻지 않는다. 한 응답에 부모·자식·관계가 전부 들어 있다."""
    mega(api)
    response = get(api, child=CHILD)
    assert response.status_code == 200, response.text
    value = response.json()["data"]
    assert value["is_mega_project"] is True
    child = value["child"]
    assert set(child) == {"project_id", "project_name", "runtime_document_version",
                          "ownership", "viewing_context"}
    assert child["project_id"] == CHILD and child["project_name"] == f"[합성] {CHILD}"
    assert set(child["ownership"]) == {"tenant_id", "enterprise_scope_id", "entity_mode"}
    assert set(child["viewing_context"]) == {"tenant_id", "scope_node_id", "entity_mode"}


def test_the_child_carries_no_state_or_plan(api):
    """⚠️ 진입 확인은 「볼 수 있는가」만 답한다. 계획·상태·형제 목록을 주지 않는다."""
    mega(api, children=(CHILD, "SIBLING_NOT_ASKED"))
    body = get(api, child=CHILD).text
    assert "SIBLING_NOT_ASKED" not in body and "sub_projects_map" not in body
    assert "clarification_questions" not in body and "artifacts" not in body


# ── ② ★★★ 양쪽이 다 가리켜야 관계다 ──────────────────────────────────────
def test_child_pointing_at_the_parent_is_not_enough(api):
    """자식만 부모를 가리키고 **부모가 열거하지 않으면** 관계가 아니다.

    ⚠️ 이쪽만 보면 아무 프로젝트나 남의 메가에 자기를 끼워 넣을 수 있다."""
    mega(api, children=("SOMEONE_ELSE",))          # 부모의 목록에 CHILD 가 없다
    assert get(api, child=CHILD).status_code == 404


def test_parent_listing_the_child_is_not_enough(api):
    """부모만 열거하고 **자식이 가리키지 않으면** 관계가 아니다.

    ⚠️ 이쪽만 보면 남의 프로젝트를 자기 메가 목록에 적어 끌어올 수 있다."""
    mega(api, child_parent="ANOTHER_MEGA")         # 자식이 다른 부모를 가리킨다
    assert get(api, child=CHILD).status_code == 404


def test_a_child_that_claims_nothing_is_refused(api):
    mega(api, child_parent="")
    assert get(api, child=CHILD).status_code == 404


# ── ③ 어디서 막혔는지 말하지 않는다 ───────────────────────────────────────
@pytest.mark.parametrize("case", ["missing_parent", "missing_child", "not_a_mega",
                                  "self_as_child", "unlisted", "wrong_parent"])
def test_every_failure_answers_with_the_same_words(api, case):
    """★ 여섯 가지가 **전부 같은 404 문구**다. 나누면 존재 여부가 응답으로 샌다."""
    if case == "missing_parent":
        response = get(api, project_id="B6_NO_SUCH_MEGA", child=CHILD)
    elif case == "missing_child":
        mega(api, make_child=False)
        response = get(api, child=CHILD)
    elif case == "not_a_mega":
        make_project(api, CHILD, state={"parent_project_id": MEGA})
        response = get(api, child=CHILD)          # 부모 소속을 세우지 않았다
    elif case == "self_as_child":
        mega(api)
        response = get(api, child=MEGA)
    elif case == "unlisted":
        mega(api, children=("SOMEONE_ELSE",))
        response = get(api, child=CHILD)
    else:
        mega(api, child_parent="ANOTHER_MEGA")
        response = get(api, child=CHILD)
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "현재 문맥에서 프로젝트를 찾을 수 없습니다."
    assert "data" not in response.json()


# ── 다른 조직 · 권한 부족 ─────────────────────────────────────────────────
def test_a_child_owned_by_another_department_is_hidden(api):
    """부모는 보이는데 자식이 다른 조직이면 열리지 않는다."""
    mega(api, child_dept=org.DEPT_B)
    assert get(api, child=CHILD).status_code == 404


def test_a_user_outside_the_department_sees_neither(api):
    mega(api)
    assert get(api, child=CHILD, actor=org.MEMBER_B).status_code == 404


def test_selecting_another_scope_hides_the_mega(api):
    mega(api)
    assert get(api, child=CHILD, actor=org.ADMIN, scope=org.NODES[org.DEPT_B]).status_code == 404


def test_a_viewer_may_confirm_entry(api):
    """열람자는 **볼 수 있다.** 조회 가능은 실행·승인이 아니므로 쓰기 권한을 요구하지 않는다."""
    mega(api)
    assert get(api, child=CHILD, actor=org.VIEWER_A).status_code == 200


# ── ④ 조회가 자원을 만들지 않는다 ─────────────────────────────────────────
def test_confirming_creates_nothing(api):
    """없는 자식을 물어도 작업공간이 생기지 않고, 부모의 상태 파일도 그대로다."""
    mega(api, make_child=False)
    missing = api.root.parent / CHILD
    before = (api.root / "latest_state.json").read_bytes()
    assert not missing.exists()
    assert get(api, child=CHILD).status_code == 404
    assert not missing.exists()
    assert (api.root / "latest_state.json").read_bytes() == before


def test_confirming_does_not_start_or_approve_anything(api):
    """조회만으로 실행 엔진이 불리지 않는다 — fixture 가 쓰기·실행을 실패로 만든다."""
    mega(api)
    assert get(api, child=CHILD).status_code == 200
    assert api.calls == []


# ── ⑤ 소속을 못 읽을 때 — 방향이 갈린다 ──────────────────────────────────
@pytest.mark.parametrize("raw", ["{broken", "[]", '"text"'])
def test_a_corrupt_state_file_is_unavailable_not_a_silent_mega(api, raw):
    """★ **실측으로 계약을 고쳤다.** 나는 「손상이면 `is_mega_project=False` 로 200」을
    예상했는데, 실제로는 **기존 인증 경로가 먼저 503** 을 낸다
    (`studio_project_context` 가 같은 파일을 읽는다 — 내 변경 이전부터 그렇다).

    더 닫힌 쪽이고 메가로도 열리지 않으므로 그대로 둔다. ⚠️ 다만 **그 503 은 내
      코드가 내는 게 아니다** — 소속 판독기는 손상에 `None` 을 돌려줄 뿐이다."""
    (api.root / "latest_state.json").write_text(raw, encoding="utf-8")
    response = get(api)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "PROJECT_ENTRY_UNAVAILABLE"


def test_a_project_without_any_state_file_still_enters(api):
    """★★★ **이 시험이 §10.5 의 핵심이다.** 레거시 프로젝트엔 상태 파일이 아예 없다 —
    소속을 못 읽는다고 진입을 막으면 지금 되던 것이 죽는다. 없으면 «메가가 아니다»."""
    (api.root / "latest_state.json").unlink()
    response = get(api)
    assert response.status_code == 200 and response.json()["data"]["is_mega_project"] is False


def test_a_relationship_claim_against_a_stateless_parent_is_refused(api):
    """소속이 아예 없는 부모에게 관계를 주장하면 **404** 다. 주장은 증명돼야 한다."""
    make_project(api, CHILD, state={"parent_project_id": MEGA})
    (api.root / "latest_state.json").unlink()
    assert get(api, child=CHILD).status_code == 404


def test_a_relationship_claim_against_a_stateless_child_is_refused(api):
    mega(api, make_child=False)
    child_root = make_project(api, CHILD, state={})
    (child_root / "latest_state.json").unlink()
    assert get(api, child=CHILD).status_code == 404


@pytest.mark.parametrize("listed", [[], "not-a-map", 42, None])
def test_a_malformed_child_list_is_not_a_relationship(api, listed):
    mega(api)
    state_of(api, {"sub_projects_map": listed})
    assert get(api, child=CHILD).status_code == 404


@pytest.mark.parametrize("flag", ["true", 1, "yes", None])
def test_only_a_real_boolean_counts_as_a_mega(api, flag):
    """⚠️ 참처럼 «보이는» 값을 메가로 받지 않는다. 손상된 파일이 메가를 만들면 안 된다."""
    mega(api)
    state_of(api, {"is_mega_project": flag})
    assert get(api).json()["data"]["is_mega_project"] is False
    assert get(api, child=CHILD).status_code == 404


# ── 문맥·소속이 확인 «중에» 바뀌면 ────────────────────────────────────────
@pytest.mark.parametrize("mutate", ["unlist_child", "repoint_child", "demote_parent"])
def test_membership_changed_during_the_read_is_not_confirmed(api, monkeypatch, mutate):
    """★ 반환 «직전» 재확인이 소속도 본다 — 판정 근거가 된 파일이 하나 늘었기 때문이다."""
    from api.routes import studio_revision_control

    child_root = mega(api)
    original = studio_revision_control._same_context

    def shift(pid, p, boundary, studio, *, write):
        if mutate == "unlist_child":
            state_of(api, {"sub_projects_map": {"d0": "SOMEONE_ELSE"}})
        elif mutate == "repoint_child":
            state_of(api, {"parent_project_id": "ANOTHER_MEGA"}, root=child_root)
        else:
            state_of(api, {"is_mega_project": False})
        return original(pid, p, boundary, studio, write=write)

    monkeypatch.setattr(studio_revision_control, "_same_context", shift)
    response = get(api, child=CHILD)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "PROJECT_ENTRY_UNAVAILABLE"


# ── 형식 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["../escape", "a b", "child/../..", "%2e%2e", "."])
def test_a_malformed_child_id_is_rejected_before_anything_is_read(api, bad):
    """자식 id 도 부모와 **같은 형식 규칙**(`_safe_id`)을 지난다 — 경로 탈출 금지."""
    mega(api)
    assert get(api, child=bad).status_code == 400


def test_a_very_long_child_id_is_not_a_format_error(api):
    """⚠️ **관찰 기록** — `_ID_RE` 에 길이 상한이 없다. 200자도 형식상 «정상» 이고
    없는 프로젝트로 404 가 된다. 부모 `project_id` 도 처음부터 같은 성질이라
    이번 범위에서 바꾸지 않는다. 상한을 둘지는 지시 대상이다(프런트는 160자로 막는다)."""
    mega(api)
    assert get(api, child="x" * 200).status_code == 404


def test_an_empty_child_parameter_means_parent_alone(api):
    """빈 값은 «관계 주장이 없는» 것이다 — 400 이 아니라 부모 단독으로 읽는다."""
    mega(api)
    response = api.client.get(url() + "?child=", headers=headers())
    assert response.status_code == 200 and response.json()["data"]["child"] is None


# ── [FIX1 · 결정 B] 판정 «순서» — 숨겨야 할 대상은 읽기 전에 닫는다 ──────────
#
# ⚠️⚠️ 503 을 404 로 «접지» 않는다. 볼 수 있는 자원의 판독 장애는 503 이 맞다.
#   대신 **순서**를 고친다 — 부모 사실만으로 끝나는 거절은 자식을 읽기 «전에» 한다.
#   읽고 나서 거절하면 그 읽기가 실패할 때 503 이 나가 **존재가 응답으로 샌다.**

def test_a_child_outside_the_parent_list_is_refused_before_it_is_read(api):
    """★★★ 부모 목록 밖 자식은 **상태가 손상돼 있어도 404** 다.

    이것이 순서의 증거다 — 손상된 파일을 읽었다면 503 이 나왔을 것이고, 그러면
    「없는 자식」과 「관계 밖이지만 존재하는 자식」이 구분된다."""
    mega(api, children=("SOMEONE_ELSE",))
    child_root = api.root.parent / CHILD
    (child_root / "latest_state.json").write_text("{broken", encoding="utf-8")
    (child_root / "project_meta.json").write_text("{broken", encoding="utf-8")
    assert get(api, child=CHILD).status_code == 404


def test_a_child_of_a_non_mega_parent_is_refused_before_it_is_read(api):
    """부모가 메가가 아니면 자식을 읽지 않는다 — 자식이 손상돼 있어도 404 다."""
    make_project(api, CHILD, state={"parent_project_id": MEGA})
    (api.root.parent / CHILD / "project_meta.json").write_text("{broken", encoding="utf-8")
    assert get(api, child=CHILD).status_code == 404


def test_a_readable_related_child_with_a_broken_state_read_stays_unavailable(api):
    """반대 방향 — **볼 수 있고 관계도 맞는** 자식의 판독 장애는 503 을 유지한다.

    ⚠️ 이것을 404 로 접으면 실제 장애가 「없는 자원」으로 위장되고, 고칠 사람이
      「원래 없는 것」으로 읽는다."""
    child_root = mega(api)
    (child_root / "latest_state.json").write_text("{broken", encoding="utf-8")
    response = get(api, child=CHILD)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["reason_code"] == "PROJECT_ENTRY_UNAVAILABLE"


def test_a_corrupt_child_meta_is_hidden_by_the_existing_pdp_layer(api):
    """★ **실측 기록** — 손상된 `project_meta.json` 은 503 이 아니라 **404** 다.

    소속(ownership)을 못 읽으면 기존 PDP 계층이 «없는 것»으로 은폐한다. 부모 단독
    경로도 처음부터 그렇고(`test_corrupt_metadata_never_returns_legacy_success` 가
    404·503 둘 다 허용한다), 내가 만든 동작이 **아니다**.

    ⚠️ 즉 판독 장애가 항상 503 인 것은 아니다 — «소속» 판독 장애는 404 로 접히고,
      «상태» 판독 장애는 503 으로 남는다. 보장 범위를 이 시험이 고정한다."""
    child_root = mega(api)
    (child_root / "project_meta.json").write_text("{broken", encoding="utf-8")
    assert get(api, child=CHILD).status_code == 404


def test_an_invisible_child_is_hidden_even_when_its_state_is_corrupt(api):
    """⚠️ **관찰점** — 부모 목록에는 있지만 «다른 조직» 인 자식 + 손상 상태.

    관계 검사로는 걸러지지 않으므로 여기서는 **기존 권한 헬퍼의 순서**가 결과를
    정한다. 비가시 판정이 상태 판독보다 앞서면 404, 뒤면 503 이 샌다."""
    child_root = mega(api, child_dept=org.DEPT_B)
    (child_root / "latest_state.json").write_text("{broken", encoding="utf-8")
    response = get(api, child=CHILD)
    assert response.status_code == 404, (
        "비가시 자식의 판독 장애가 503 으로 샌다 — 존재가 응답으로 드러난다: "
        + response.text)
