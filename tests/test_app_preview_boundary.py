"""★★★ [I-4 6 / Wave F-1] Preview 경계 — **미리보기가 운영 데이터에 닿을 수 없다.**

## 이 파일이 막으려는 네 가지

★★★ ① **논리적 분리에 기대는 것.** 「플래그를 보고 걸러라」로 두면 그 플래그를 안
  보는 경로 하나가 곧 운영 데이터 오염이다. 그리고 그 경로는 대개 나중에 추가된다.
★★★ ② **한 방향만 막는 것.** 반대쪽이 곧 우회로다 — 운영 증명으로 Preview 를 보게
  두면 운영 권한을 가진 사람이 **검토되지 않은 코드에 자기 권한을 빌려 준다.**
★★★ ③ **승격 뒤에도 옛 증명이 도는 것.** 후보였던 판이 운영이 되면 그때 발급된
  Preview 증명이 운영 데이터를 가리키게 된다 — 그것이 교차 사용의 실제 경로다.
★★★ ④ **실제 조직 문맥으로 미리보기를 도는 것.** 승인 전 판이 만든 숫자가 실적으로
  읽히고, 그 화면은 오류를 내지 않는다.
"""
import pytest

from core import app_preview as ap


# ── 어휘 ─────────────────────────────────────────────────────────────────
def test_the_audience_list_is_closed():
    assert ap.AUDIENCES == ("operational", "preview")


@pytest.mark.parametrize("bad", ["", "   ", None, "PREVIEW_MODE", "prod", "test", 0])
def test_an_unknown_audience_gets_no_default(bad):
    """★★★ 「모르면 운영」이면 오타 하나가 운영 데이터를 열고, 「모르면 Preview」면
    운영 요청이 조용히 빈 DB 를 읽는다. **둘 다 조용하다.**"""
    assert ap.normalize_audience(bad) == ""
    with pytest.raises(ap.PreviewBoundaryError):
        ap.assert_audience(bad)
    with pytest.raises(ap.PreviewBoundaryError):
        ap.db_path(bad)
    with pytest.raises(ap.PreviewBoundaryError):
        ap.app_data_for(bad)


@pytest.mark.parametrize("value", ["Preview", "PREVIEW", " preview "])
def test_the_audience_name_is_normalized_not_guessed(value):
    """⚠️ 대소문자·공백은 받아 준다 — 그것은 오타가 아니라 표기다. 다만 **뜻이 다른
    값**은 위 시험처럼 거부한다."""
    assert ap.normalize_audience(value) == ap.AUDIENCE_PREVIEW


# ── ① 물리 분리 ──────────────────────────────────────────────────────────
def test_the_two_audiences_use_different_files():
    """★★★ 여기가 분리의 실체다. 플래그가 아니라 **경로**가 보증한다."""
    assert ap.db_path(ap.AUDIENCE_PREVIEW) != ap.db_path(ap.AUDIENCE_OPERATIONAL)
    assert ap.db_path(ap.AUDIENCE_PREVIEW).endswith("app_data_preview.db")
    assert ap.db_path(ap.AUDIENCE_OPERATIONAL).endswith("app_data.db")


def test_the_preview_plane_is_not_the_operational_singleton():
    """⚠️ 같은 객체를 경로만 바꿔 쓰면 한쪽에서 되돌릴 때 다른 쪽이 조용히 따라간다."""
    from core.app_data import app_data_service

    preview = ap.app_data_for(ap.AUDIENCE_PREVIEW)
    assert preview is not app_data_service
    assert ap.app_data_for(ap.AUDIENCE_OPERATIONAL) is app_data_service


def test_the_preview_plane_is_the_same_object_every_time():
    """⚠️ 매번 새로 만들면 요청마다 다른 연결이 생기고, 그 사이의 쓰기가 서로 안 보인다."""
    assert ap.app_data_for(ap.AUDIENCE_PREVIEW) is ap.app_data_for(ap.AUDIENCE_PREVIEW)


# ── ② 양방향 차단 ────────────────────────────────────────────────────────
def test_a_preview_proof_cannot_be_used_operationally():
    with pytest.raises(ap.PreviewBoundaryError) as e:
        ap.assert_audience_match(sealed=ap.AUDIENCE_PREVIEW,
                                 requested=ap.AUDIENCE_OPERATIONAL)
    assert "청중이 다릅니다" in str(e.value)


def test_an_operational_proof_cannot_be_used_in_preview():
    """★★★ **반대 방향도 막는다.** 「Preview 는 약한 권한이니 운영 증명으로 봐도
    되겠지」가 정확히 그 실수다 — 그러면 운영 권한을 가진 사람이 검토되지 않은 코드에
    자기 권한을 빌려 준다."""
    with pytest.raises(ap.PreviewBoundaryError):
        ap.assert_audience_match(sealed=ap.AUDIENCE_OPERATIONAL,
                                 requested=ap.AUDIENCE_PREVIEW)


@pytest.mark.parametrize("audience", [ap.AUDIENCE_PREVIEW, ap.AUDIENCE_OPERATIONAL])
def test_a_matching_audience_passes(audience):
    """⚠️ 대조군 — 위 둘이 「전부 막힘」으로도 통과하지 않게 한다."""
    ap.assert_audience_match(sealed=audience, requested=audience)


@pytest.mark.parametrize("sealed", ["", None, "   "])
def test_a_proof_without_a_sealed_audience_is_refused(sealed):
    """★★★ 청중 이전에 발급된 증명은 **어느 쪽인지 알 수 없다.**

    ⚠️ 「모르니까 통과」가 곧 경계 없음이다.

    ⚠️⚠️ [변이 검사 실측] 이 시험은 처음에 `"봉인" in str(e)` 만 봤고, **그것으로는
      부족했다.** 봉인 검사(`if not got`)를 지워도 다음 줄(`got != want`)이 잡는데,
      그 오류 문구에도 「봉인」이라는 **단어가 들어 있어서** 초록이었다.
      §4.1b 에 적은 「문구가 게이트를 대신한다」를 시험이 그대로 반복한 것이다.
    ★ 그래서 **그 분기에만 있는 문장**을 본다."""
    with pytest.raises(ap.PreviewBoundaryError) as e:
        ap.assert_audience_match(sealed=sealed, requested=ap.AUDIENCE_OPERATIONAL)
    assert "봉인돼 있지 않습니다" in str(e.value), str(e.value)
    #: 「청중이 다릅니다」로 떨어지면 안 된다 — 그것은 **다른 사실**이다
    assert "다릅니다" not in str(e.value), "봉인 없음이 «불일치» 로 답해졌다"


# ── ③ 상태 → 청중 ───────────────────────────────────────────────────────
def test_a_candidate_can_only_issue_preview():
    assert ap.audience_for_state(ap.STATE_CANDIDATE) == ap.AUDIENCE_PREVIEW
    ap.assert_issuable(state=ap.STATE_CANDIDATE, audience=ap.AUDIENCE_PREVIEW)
    with pytest.raises(ap.PreviewBoundaryError):
        ap.assert_issuable(state=ap.STATE_CANDIDATE,
                           audience=ap.AUDIENCE_OPERATIONAL)


@pytest.mark.parametrize("state", ["active", "deprecated"])
def test_a_live_release_can_only_issue_operational(state):
    """⚠️ 폐기 예정도 **이미 도는 앱**이다 — 열되 운영 청중이다."""
    assert ap.audience_for_state(state) == ap.AUDIENCE_OPERATIONAL
    with pytest.raises(ap.PreviewBoundaryError):
        ap.assert_issuable(state=state, audience=ap.AUDIENCE_PREVIEW)


@pytest.mark.parametrize("state", ["", None, "disabled", "아무거나", "CANDIDATE_2"])
def test_an_unknown_state_issues_nothing(state):
    """★★★ 「모르면 운영」이면 아직 승인되지 않은 판이 운영 데이터를 만진다."""
    assert ap.audience_for_state(state) == ""
    for audience in ap.AUDIENCES:
        with pytest.raises(ap.PreviewBoundaryError):
            ap.assert_issuable(state=state, audience=audience)


def test_disabled_is_not_usable_at_all():
    """⚠️ 관리자가 「쓰지 마라」고 적은 판은 어느 청중으로도 열리지 않는다."""
    from core.program_lifecycle import DISABLED

    assert ap.audience_for_state(DISABLED) == ""


# ── ④ SYNTHETIC_TEST ─────────────────────────────────────────────────────
def test_preview_only_runs_in_synthetic_context():
    ap.assert_preview_context(ap.ENTITY_MODE_SYNTHETIC)


@pytest.mark.parametrize("mode", ["REAL", "VIRTUAL", "COMPETITOR_REFERENCE", "", None,
                                  "synthetic_test"])
def test_preview_refuses_any_other_context(mode):
    """★★★ 실제 조직 문맥으로 미리보기를 돌리면 **승인 전 판이 만든 숫자가 실적으로
    읽힌다.** 그리고 그 화면은 오류를 내지 않는다.

    ⚠️ 소문자도 거부한다 — 문맥 이름은 표기가 아니라 값이다."""
    with pytest.raises(ap.PreviewBoundaryError) as e:
        ap.assert_preview_context(mode)
    assert ap.ENTITY_MODE_SYNTHETIC in str(e.value)


def test_the_synthetic_mode_is_not_a_real_entity_mode():
    """★★★ `SYNTHETIC_TEST` 는 **실제 조직 문맥 목록에 없다.**

    ⚠️ 목록에 넣으면 사람이 그 문맥으로 실제 데이터를 만들 수 있게 되고, 그 순간
      「미리보기 전용」이라는 성질이 사라진다."""
    from core.enterprise_context.context import ENTITY_MODES

    assert ap.ENTITY_MODE_SYNTHETIC not in ENTITY_MODES


def test_is_preview_never_answers_true_for_unknown_values():
    """⚠️ `not is_preview(x)` 를 운영으로 읽으면 오타가 운영이 된다 — 그래서 이 함수는
    운영 판단에 쓰지 않는다. 여기서는 그 성질만 못 박는다."""
    for bad in ("", None, "아무거나", "operational"):
        assert ap.is_preview(bad) is False


# ── Preview 경로를 **실제 라우터로** 태운다 ─────────────────────────────
#
# ★★★ 여기가 없으면 Preview 분기는 죽은 코드다. 단위 시험이 전부 초록이어도
#   「운영 요청만 도는」 상태가 유지되고, 변이 검사가 그것을 잡아낸다(실측 7건).
import json                                                          # noqa: E402

import pytest                                                        # noqa: E402

H_USER = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
          "X-Enterprise-Scope": "node_hq"}
R = "/api/v1/appdata/runtime"


def _release_json(lib, rid, *, scope="node_hq", mode="REAL"):
    (lib / rid).mkdir(parents=True, exist_ok=True)
    (lib / rid / "release.json").write_text(json.dumps({
        "release_id": rid, "project_id": "proj_a", "tenant_id": "tenant_default",
        "entity_mode": mode, "enterprise_scope_id": scope,
        "owner_user_id": "", "owner_dept_id": "hq", "visibility": "dept",
        "manifest": {"fingerprint": "fp_" + rid, "valid": True, "manifest": {
            "version": "1.0", "app_class": "departmental",
            "capabilities": ["memo.read", "memo.create"],
            "required_capabilities": []}},
    }, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def rt(monkeypatch, tmp_path):
    """실제 앱 + 후보 릴리스 하나 + 운영 릴리스 하나."""
    import config
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow
    from core.program_lifecycle import CANDIDATE, program_lifecycle

    lib = tmp_path / "library"
    lib.mkdir()
    _release_json(lib, "rel_live")
    #: ⚠️ 후보 판은 **SYNTHETIC_TEST 문맥**에서만 열린다
    _release_json(lib, "rel_cand", mode=ap.ENTITY_MODE_SYNTHETIC)
    #: ⚠️ **문맥까지 REAL 인 후보 판.** 기존 문맥 대조는 이것을 통과시키므로, 여기서
    #:   막는 것은 오직 `assert_preview_context` 하나다 — 그러지 않으면 이 시험은
    #:   「다른 검사가 막아서」 통과하고, 내 검사를 지워도 초록이 된다.
    _release_json(lib, "rel_cand_real", mode="REAL")

    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(program_lifecycle, "db_path",
                        str(tmp_path / "lifecycle.db"), raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})

    #: ★ 후보 상태를 **실제 API 로** 만든다 — 시험이 표를 직접 쓰지 않는다.
    monkeypatch.setattr(program_lifecycle, "_release_exists", lambda rid: True,
                        raising=False)
    for rid in ("rel_cand", "rel_cand_real"):
        program_lifecycle.set_status(rid, CANDIDATE, actor="u@x",
                                     reason="Preview 검토용 후보 판")

    app_capability_tokens._tokens.clear()
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _ctx(monkeypatch, mode):
    """이 요청의 조직 문맥을 정한다."""
    import api.routes.app_data_runtime as ard

    monkeypatch.setattr(ard, "viewing_context",
                        lambda p: {"tenant_id": "tenant_default", "entity_mode": mode,
                                   "scope_node_id": "node_hq"}, raising=False)


def _proof(c, rid):
    return c.post(R + "/proof", json={"release_id": rid}, headers=H_USER)


def test_a_candidate_release_issues_a_preview_proof(rt, monkeypatch):
    """★★★ 청중은 **릴리스 상태가 정한다** — 요청이 고르지 않는다."""
    _ctx(monkeypatch, ap.ENTITY_MODE_SYNTHETIC)
    r = _proof(rt, "rel_cand")
    assert r.status_code == 200, r.text
    from core.app_capability_token import app_capability_tokens

    rec = app_capability_tokens.resolve(r.json()["data"]["token"], quiet=True)
    assert rec["audience"] == ap.AUDIENCE_PREVIEW


def test_a_live_release_issues_an_operational_proof(rt, monkeypatch):
    """⚠️ 대조군 — 위 시험이 「전부 preview」로도 통과하지 않게 한다."""
    _ctx(monkeypatch, "REAL")
    r = _proof(rt, "rel_live")
    assert r.status_code == 200, r.text
    from core.app_capability_token import app_capability_tokens

    rec = app_capability_tokens.resolve(r.json()["data"]["token"], quiet=True)
    assert rec["audience"] == ap.AUDIENCE_OPERATIONAL


def test_a_candidate_release_refuses_a_real_context(rt, monkeypatch):
    """★★★ 실제 조직 문맥으로 미리보기를 돌리면 **승인 전 판이 만든 숫자가 실적으로
    읽힌다.** 그리고 그 화면은 오류를 내지 않는다."""
    _ctx(monkeypatch, "REAL")
    #: 문맥이 릴리스와 **맞는** 후보 판을 쓴다 — 그래야 다른 검사가 먼저 막지 않고
    #: `assert_preview_context` 가 실제로 실행된다.
    r = _proof(rt, "rel_cand_real")
    assert r.status_code == 403, r.text


def test_preview_writes_land_in_the_preview_file_not_the_operational_one(rt, monkeypatch):
    """★★★ **물리 분리가 실제로 도는가.** 여기가 F-1 의 핵심 주장이다.

    ⚠️ 논리 분리였다면 이 시험은 통과하면서도 운영 파일에 썼을 것이다."""
    from core import app_preview
    from core.app_data import app_data_service

    _ctx(monkeypatch, ap.ENTITY_MODE_SYNTHETIC)

    #: **운영 평면에** 데이터셋을 하나 만든다. 관리 API 대신 서비스를 직접 쓴다 —
    #: 이 시험의 주제는 «관리 라우트» 가 아니라 **평면 분리**다.
    #: ⚠️ 증명을 **먼저 받지 않는다.** 발급은 물질화 지문을 봉인하는데, 그 뒤에 운영
    #:   평면을 바꾸면 「이 판은 사라졌다」(410)가 되어 이 시험이 엉뚱한 이유로 빨개진다.
    #: ★ [F-1 관찰] 그때 봉인되는 지문은 **운영 평면의 것**이다 — Preview 증명인데도.
    #:   Preview 가 자기 평면을 읽는다는 점과 어긋나며, F-2 에서 정리해야 한다.
    made = app_data_service.create_dataset(
        "rel_cand", "memo", {"fields": [{"name": "note", "type": "string"}]},
        actor_id="u@x", tenant_id="tenant_default", scope_node_id="node_hq")
    assert made["dataset_id"]
    assert app_data_service.find_dataset("rel_cand", "memo"), "운영 평면 준비 실패"

    tok = _proof(rt, "rel_cand").json()["data"]["token"]

    #: ★★★ Preview 증명으로는 **그것이 보이지 않아야** 한다.
    r = rt.get(R + "/datasets/memo/records", headers={**H_USER, "X-App-Proof": tok})
    assert r.status_code == 404, "Preview 가 운영 데이터셋을 봤다: " + r.text[:160]

    preview = app_preview.app_data_for(ap.AUDIENCE_PREVIEW)
    assert preview is not app_data_service
    assert preview.find_dataset("rel_cand", "memo") is None,         "Preview 평면이 운영 파일을 읽고 있다"


def test_a_preview_proof_stops_working_once_the_release_goes_live(rt, monkeypatch):
    """★★★ **승격 뒤에도 옛 증명이 도는 것** — 교차 사용의 실제 경로다.

    ⚠️ 발급 시점에 맞았다는 것으로는 부족하다. 요청마다 지금 상태에서 다시 유도해
      봉인 값과 대조해야 한다."""
    from core.program_lifecycle import ACTIVE, program_lifecycle

    _ctx(monkeypatch, ap.ENTITY_MODE_SYNTHETIC)
    tok = _proof(rt, "rel_cand").json()["data"]["token"]

    #: 그 사이 후보가 운영으로 승격됐다
    program_lifecycle.set_status("rel_cand", ACTIVE, actor="u@x", reason="승격")

    r = rt.get(R + "/datasets/memo/records", headers={**H_USER, "X-App-Proof": tok})
    assert r.status_code == 401, \
        "승격 뒤에도 Preview 증명이 통했다: " + str(r.status_code)


def test_an_unreadable_release_state_stops_requests_too(rt, monkeypatch):
    """★★★ **발급만 막아서는 부족하다.** 이미 발급된 증명으로 오는 요청도 막아야 한다.

    ⚠️ 요청 경로가 「모르면 운영」이면, 상태를 못 읽는 순간 **후보 판이 운영 데이터를
      만진다.** 발급 경로와 요청 경로는 다른 코드이고, 변이 검사가 그 틈을 뚫었다."""
    import api.routes.app_data_runtime as ard

    _ctx(monkeypatch, ap.ENTITY_MODE_SYNTHETIC)
    tok = _proof(rt, "rel_cand").json()["data"]["token"]

    #: 증명을 받은 뒤 상태를 못 읽게 된다
    monkeypatch.setattr(ard, "_release_state", lambda rid: "", raising=False)
    r = rt.get(R + "/datasets/memo/records", headers={**H_USER, "X-App-Proof": tok})
    #: ⚠️ **404 다(은폐).** 「쓸 수 없는 상태」를 503 으로 답하면 「그것이 존재하는데
    #:   서버가 아프다」를 알려 주는 셈이다 — 끈 프로그램·격리된 판과 같은 규칙으로
    #:   「없거나 못 보거나」를 한 답으로 돌려준다.
    assert r.status_code == 404,         "상태를 못 읽는데 요청이 통과했다: " + str(r.status_code)


def test_an_unreadable_release_state_issues_nothing(rt, monkeypatch):
    """★★★ 「모르면 운영」이면 상태를 못 읽는 순간 후보 판이 운영 데이터를 만진다."""
    import api.routes.app_data_runtime as ard

    _ctx(monkeypatch, "REAL")
    monkeypatch.setattr(ard, "_release_state", lambda rid: "", raising=False)
    assert _proof(rt, "rel_live").status_code == 404


def test_a_token_cannot_be_issued_without_an_audience():
    """★★★ **기본값이 없다.** 「안 적었으면 운영」이면 Preview 경로가 하나만 빠뜨려도
    운영 데이터가 열린다."""
    from core.app_capability_token import AppCapabilityTokenStore, AppTokenError

    store = AppCapabilityTokenStore()
    base = dict(actor="u@x", session_id="s", app_id="a", release_id="r",
                tenant_id="tenant_default", entity_mode="REAL", scope_node_id="n",
                #: 이 시험의 주제는 «청중» 이다 — 다른 필수값이 먼저 막으면 주제가
                #: 가려진다(문구가 게이트를 대신하던 사고와 같은 종류).
                manifest_fingerprint="fp", manifest_version="1.0",
                contract_fingerprint="cfp", materialization_fingerprint="mfp",
                #: ★ [§4.2] 읽는 판 지문도 필수다 — 여기서 채워야 이 시험이 «청중»
                #:   때문에 막히는 것을 본다. 안 채우면 다른 이유로 막히고 초록이 된다.
                data_fingerprint="dfp")
    with pytest.raises(AppTokenError) as e:
        store.issue(**base)
    assert "청중" in str(e.value)

    #: 대조군 — 명시하면 나간다
    assert store.issue(**base, audience=ap.AUDIENCE_OPERATIONAL)["token"]
