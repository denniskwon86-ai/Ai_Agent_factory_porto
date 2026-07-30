"""[M2 §2.1/§2.2] 범위 계약 쓰기 경로 — 조직 간 명시적 공유.

이 파일이 잠그는 것:
  · 자기 승인은 승인이 아니다(신청자 = 승인자면 거부)
  · 책임 조직 없이 공유하지 않는다
  · 공유 대상 없는 `ORG_SHARED` 는 만들 수 없다
  · `LEGACY_UNSCOPED` 는 신규 생성에 쓸 수 없다(§2.3-4)
  · 한시 예외는 만료되면 **비노출**이다(§2.3-2) — 관측만으로는 '한시'가 영구가 된다
  · 모든 변경은 감사에 남는다
  · 되돌릴 수 있다(공유 회수)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.business_glossary import BusinessGlossary
from core.enterprise_context.scoping import (ENTERPRISE_SHARED, LEGACY_UNSCOPED, ORG_PRIVATE,
                                             ORG_SHARED, SANDBOX, is_visible)
from core.master_data import MasterData
from core.scope_contract import (ScopeContract, ScopeContractError,
                                 validate_new_scope_type)

OWNER = "MNM_BATTERY"
OTHER = "LS_CABLE"


@pytest.fixture()
def sc(tmp_path, monkeypatch):
    md = MasterData(db_path=str(tmp_path / "m.db"))
    g = BusinessGlossary(md=md)
    t = g.create_term("전극 두께", definition="양극 코팅 두께")
    inst = ScopeContract(md=md)
    return inst, g, t["term_id"], md


def _row(md, term_id):
    with md._connect() as conn:
        r = conn.execute("SELECT * FROM business_terms WHERE term_id=?", (term_id,)).fetchone()
        return dict(r)


# ── 기본값은 비노출이다 ─────────────────────────────────────────────────────
def test_new_row_is_invisible_until_owner_is_set(sc):
    """★★ 관문 A 의 기본 상태 — 소유 조직이 없으면 아무에게도 보이지 않는다.

    빈 값은 **설정 누락**이지 공유 의사가 아니다."""
    inst, _, tid, md = sc
    c = inst.contract("business_term", tid)
    assert c["owner"] == "" and c["scope_type_effective"] == ORG_PRIVATE
    assert "아무에게도 보이지 않습니다" in c["visibility"]
    assert is_visible(_row(md, tid), OWNER) is False

    inst.set_owner("business_term", tid, OWNER, actor="admin@ls")
    assert is_visible(_row(md, tid), OWNER) is True
    assert is_visible(_row(md, tid), OTHER) is False, "소유 조직 밖에서는 여전히 안 보인다"


def test_owner_cannot_be_blanked(sc):
    """빈 소유는 '전사 공용'이 아니라 '비노출'이다 — 지우기를 우회 경로로 쓰지 못하게 막는다."""
    inst, _, tid, _ = sc
    with pytest.raises(ScopeContractError, match="빈 값으로 둘 수 없습니다"):
        inst.set_owner("business_term", tid, "", actor="admin@ls")


def test_change_without_actor_is_refused(sc):
    """누가 바꿨는지 없는 권한 변경은 감사 대상이 될 수 없다."""
    inst, _, tid, _ = sc
    with pytest.raises(ScopeContractError, match="actor"):
        inst.set_owner("business_term", tid, OWNER, actor="")


# ── 조직 간 공유 (ORG_SHARED) ───────────────────────────────────────────────
def test_share_with_named_orgs_opens_exactly_those(sc):
    """★★ 공유는 **명시된 목록**으로만 성립한다."""
    inst, _, tid, md = sc
    inst.set_owner("business_term", tid, OWNER, actor="admin@ls")
    inst.share_with("business_term", tid, [OTHER], actor="admin@ls")

    row = _row(md, tid)
    assert is_visible(row, OTHER) is True, "공유 대상 조직에서 보여야 한다"
    assert is_visible(row, OWNER) is True, "소유 조직은 계속 본다"
    assert is_visible(row, "SMELTING") is False, "목록에 없는 조직에는 열리지 않는다"


def test_share_without_targets_is_refused(sc):
    """★★ 대상 없는 공유는 공유가 아니다 — 화면에만 '공유됨'으로 남아 실제와 갈린다."""
    inst, _, tid, _ = sc
    inst.set_owner("business_term", tid, OWNER, actor="admin@ls")
    with pytest.raises(ScopeContractError, match="공유 대상 조직을 지정"):
        inst.share_with("business_term", tid, [], actor="admin@ls")


def test_share_requires_owner_first(sc):
    """★ 책임 조직 없는 데이터를 공유하면 문제가 생겼을 때 물어볼 곳이 없다."""
    inst, _, tid, _ = sc
    with pytest.raises(ScopeContractError, match="소유 조직을 먼저 지정"):
        inst.share_with("business_term", tid, [OTHER], actor="admin@ls")


def test_sharing_can_be_revoked(sc):
    """★ 되돌릴 수 있어야 사람들이 공유를 겁내지 않는다. 승인 이력도 함께 비운다."""
    inst, _, tid, md = sc
    inst.set_owner("business_term", tid, OWNER, actor="admin@ls")
    inst.share_with("business_term", tid, [OTHER], actor="admin@ls")
    out = inst.revoke_sharing("business_term", tid, actor="admin@ls")

    assert out["scope_type"] == ORG_PRIVATE and out["assignments"] == []
    assert out["approval_status"] == "" and out["approved_by"] == ""
    assert is_visible(_row(md, tid), OTHER) is False


# ── 전사 공용 (ENTERPRISE_SHARED) ───────────────────────────────────────────
def test_request_alone_does_not_make_it_visible(sc):
    """★★ 신청만으로 보이면 승인 절차가 장식이 된다."""
    inst, _, tid, md = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    c = inst.request_enterprise_shared("business_term", tid, actor="owner@ls")

    assert c["scope_type"] == ENTERPRISE_SHARED and c["approval_status"] == "PENDING"
    assert "승인 이력이 없어" in c["visibility"]
    assert is_visible(_row(md, tid), OTHER) is False, "미승인 전사 공용이 보인다"


def test_self_approval_is_refused(sc):
    """★★ 신청자와 승인자가 같으면 승인이 아니다 — 한 사람이 자기 데이터를 전사에 열 수 없다.

    신청자는 감사로그(진실원본)에서 찾는다. 별도 컬럼에 두면 두 곳이 어긋난다."""
    inst, _, tid, _ = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    inst.request_enterprise_shared("business_term", tid, actor="owner@ls")

    with pytest.raises(ScopeContractError, match="자기 승인은 승인이 아닙니다"):
        inst.approve_enterprise_shared("business_term", tid, approver="owner@ls")


def test_self_approval_is_refused_even_when_a_custom_reason_is_given(sc):
    """★★ [2026-07-30 브라우저 실측으로 잡은 결함] 신청자 판정을 **자유 텍스트**에 걸면,
    호출자가 사유를 주는 순간 그 판정이 사라진다.

    처음 구현은 사유 문구("전사 공용 신청")로 신청자를 찾았다. API 로 실제 호출해 보니
    `reason` 을 주면 문구가 밀려나 신청자를 못 찾고 **자기 승인이 200 으로 통과**했다.
    단위 테스트는 사유 없이 호출해서 통과했다 — 그래서 이 테스트는 **사유를 준다.**"""
    inst, _, tid, _ = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    inst.request_enterprise_shared("business_term", tid, actor="owner@ls",
                                   reason="전사 표준 용어로 승격 요청")

    with pytest.raises(ScopeContractError, match="자기 승인은 승인이 아닙니다"):
        inst.approve_enterprise_shared("business_term", tid, approver="owner@ls")


def test_approval_by_another_person_opens_enterprise_wide(sc):
    """★★ 승인된 전사 공용은 전 조직에서 보인다 — 그리고 승인자가 기록된다."""
    inst, _, tid, md = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    inst.request_enterprise_shared("business_term", tid, actor="owner@ls")
    c = inst.approve_enterprise_shared("business_term", tid, approver="cdo@ls")

    assert c["approval_status"] == "APPROVED" and c["approved_by"] == "cdo@ls"
    assert is_visible(_row(md, tid), OTHER) is True
    assert is_visible(_row(md, tid), "ANY_OTHER_ORG") is True


def test_approval_without_request_is_refused(sc):
    """★ 신청 없는 승인은 무엇을 승인했는지 알 수 없다."""
    inst, _, tid, _ = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    with pytest.raises(ScopeContractError, match="신청 상태가 아닙니다"):
        inst.approve_enterprise_shared("business_term", tid, approver="cdo@ls")


def test_rejection_returns_to_private_and_requires_reason(sc):
    """★ 반려는 `ORG_PRIVATE` 로 되돌린다 — 미승인 전사 공용으로 남기면 화면에 '전사 공용'으로
    보인다. 사유 없는 반려는 같은 신청을 반복시킨다."""
    inst, _, tid, md = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    inst.request_enterprise_shared("business_term", tid, actor="owner@ls")

    with pytest.raises(ScopeContractError, match="반려 사유는 필수"):
        inst.reject_enterprise_shared("business_term", tid, approver="cdo@ls", reason="")

    c = inst.reject_enterprise_shared("business_term", tid, approver="cdo@ls",
                                      reason="개인정보 포함 여부 확인 필요")
    assert c["scope_type"] == ORG_PRIVATE and c["approval_status"] == "REJECTED"
    assert is_visible(_row(md, tid), OTHER) is False


# ── 한시 예외 이행 (§2.3) ───────────────────────────────────────────────────
def test_legacy_is_not_allowed_for_new_rows(sc):
    """★★ [§2.3-4] 이행용 표시를 신규에 허용하면 이행이 끝나지 않는다."""
    with pytest.raises(ScopeContractError, match="한시 이행 표시"):
        validate_new_scope_type(LEGACY_UNSCOPED)
    assert validate_new_scope_type("") == ORG_PRIVATE          # 기본값은 소유 조직 전용
    assert validate_new_scope_type("org_shared") == ORG_SHARED  # 대소문자는 받아준다


def test_expired_legacy_row_is_invisible(sc):
    """★★ [§2.3-2] 한시 예외는 만료되면 **보이지 않는다.**

    만료를 관측만 하고 통과시키면 '한시'가 영구가 된다 — 폐기한 규칙("빈 값 = 전사 공용")도
    처음엔 한시 조치였고, 만료를 강제하지 않은 것이 그것을 영구화했다."""
    live = {"scope_type": LEGACY_UNSCOPED, "effective_to": "2099-12-31"}
    dead = {"scope_type": LEGACY_UNSCOPED, "effective_to": "2020-01-01"}
    assert is_visible(live, OTHER) is True
    assert is_visible(dead, OTHER) is False, "만료된 한시 예외가 그대로 보인다"


def test_legacy_pending_lists_what_must_be_cleaned_up(sc):
    """★★ 만료일을 아는 것과 **무엇을 정리해야 하는지** 아는 것은 다르다. 사람은 후자로 움직인다."""
    inst, _, tid, md = sc
    with md._connect() as conn:
        conn.execute("UPDATE business_terms SET scope_type=?, effective_to=? WHERE term_id=?",
                     (LEGACY_UNSCOPED, "2020-01-01", tid))
    out = inst.legacy_pending("business_term")
    assert out["total"] == 1 and out["expired"] == 1
    assert out["items"][0]["resource_id"] == tid
    assert "이미 만료되어 보이지 않습니다" in out["note"]


def test_adopt_legacy_narrows_visibility_and_says_so(sc):
    """★ 한시 예외 이행은 가시성을 **좁힌다**(전 조직 → 소유 조직). 그 사실을 응답에 적어
    "정리했더니 안 보인다"는 놀람을 없앤다."""
    inst, _, tid, md = sc
    with md._connect() as conn:
        conn.execute("UPDATE business_terms SET scope_type=? WHERE term_id=?",
                     (LEGACY_UNSCOPED, tid))
    assert is_visible(_row(md, tid), OTHER) is True, "이행 전에는 한시 예외로 보인다"

    out = inst.adopt_legacy("business_term", tid, OWNER, actor="admin@ls")
    assert out["scope_type"] == ORG_PRIVATE and out["owner"] == OWNER
    assert "소유 조직과 그 하위에서만" in out["note"]
    assert is_visible(_row(md, tid), OTHER) is False
    assert is_visible(_row(md, tid), OWNER) is True


# ── Sandbox 는 토큰 없이 열리지 않는다 ──────────────────────────────────────
def test_sandbox_is_fail_closed_until_token_path_exists(sc):
    """★ 아직 만들지 않은 통제(capability token §4.3)를 통과로 두면 그게 곧 구멍이다."""
    assert is_visible({"scope_type": SANDBOX, "owner_organization_id": OWNER}, OWNER) is False


# ── 감사 ────────────────────────────────────────────────────────────────────
def test_every_change_is_audited_with_the_diff(sc):
    """★★ 기록 없는 권한 변경은 되돌릴 근거가 없다. **무엇이 어떻게 바뀌었는지**까지 남는다."""
    from core.enterprise_context import audit
    inst, _, tid, _ = sc
    before = len(audit.recent(limit=200))
    inst.set_owner("business_term", tid, OWNER, actor="admin@ls")
    inst.share_with("business_term", tid, [OTHER], actor="admin@ls")

    events = audit.recent(limit=10)
    assert len(events) > before
    e = events[0]
    assert e["event"] == audit.SCOPE_BINDING_CHANGED
    assert e["resource_id"] == tid and e["actor"] == "admin@ls"
    assert "scope_type" in (e.get("detail") or ""), "무엇이 바뀌었는지가 남지 않았다"


def test_approval_is_audited_as_approval(sc):
    """승인은 범위 변경과 다른 이벤트다 — 같은 이름으로 남기면 "누가 열었나"를 셀 수 없다."""
    from core.enterprise_context import audit
    inst, _, tid, _ = sc
    inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
    inst.request_enterprise_shared("business_term", tid, actor="owner@ls")
    inst.approve_enterprise_shared("business_term", tid, approver="cdo@ls")

    assert audit.recent(limit=1)[0]["event"] == audit.APPROVAL_GRANTED


# ── 자원 종류는 열거값이다 ──────────────────────────────────────────────────
def test_unknown_resource_type_is_refused(sc):
    """★ 테이블명을 자유 문자열로 받으면 이 모듈이 임의 테이블 UPDATE 도구가 된다."""
    inst, _, tid, _ = sc
    with pytest.raises(ScopeContractError, match="지원하지 않는 자원 종류"):
        inst.set_owner("users; DROP TABLE business_terms", tid, OWNER, actor="a")


# ══════════════════════════════════════════════════════════════════════════
# API 계층 — 식별·권한 경계는 라우트에서만 검증된다
# ══════════════════════════════════════════════════════════════════════════
def test_scope_routes_are_reachable():
    """★ 라우터를 등록하지 않으면 모듈 전체가 장식이다(404 로 확인된다)."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    r = c.get("/api/v1/scope/legacy/pending")
    assert r.status_code != 404, "범위 계약 라우터가 등록되지 않았다"
    r2 = c.get("/api/v1/scope/contract/business_term/nope")
    assert r2.status_code != 404 or "자원" in r2.text


def test_api_refuses_anonymous_scope_change():
    """★★ 식별 없는 권한 변경은 **401** 이다 — 404 로 은폐하지 않는다(§3.3).

    행위자를 모르면 "누가 열었나"에 답할 수 없고, 그러면 되돌릴 근거도 없다."""
    from fastapi.testclient import TestClient
    import config
    import main

    saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = ""
    try:
        c = TestClient(main.app)
        r = c.post("/api/v1/scope/owner/business_term/whatever",
                   json={"owner_organization_id": OWNER})
        assert r.status_code == 401, f"식별 없는 변경이 401 이 아니다: {r.status_code}"
        assert "행위자 없는 권한 변경" in r.text
    finally:
        config.ORG_DEFAULT_USER_ID = saved


def test_api_self_approval_is_400_not_500(sc, monkeypatch):
    """★ 정책 위반은 4xx 로 전달된다 — 500 이면 클라이언트가 "서버 오류"로 오독하고 재시도한다."""
    from fastapi.testclient import TestClient
    import config
    import main
    import api.routes.scope_control as route

    inst, _, tid, _ = sc
    # ⚠️ `core.scope_contract.scope_contract` 를 바꿔도 소용없다 — 라우트는 import 시점에
    #   그 객체를 **자기 모듈 전역으로 바인딩**했다. 바꿔야 할 이름은 라우트 쪽이다.
    #   (오늘 라이브러리 경로에서 고친 것과 같은 유형: 값 import 는 테스트가 못 갈아탄다.)
    monkeypatch.setattr(route, "scope_contract", inst)
    saved = getattr(config, "ORG_DEFAULT_USER_ID", "")
    config.ORG_DEFAULT_USER_ID = "owner@ls"
    try:
        inst.set_owner("business_term", tid, OWNER, actor="owner@ls")
        inst.request_enterprise_shared("business_term", tid, actor="owner@ls")
        c = TestClient(main.app)
        r = c.post(f"/api/v1/scope/enterprise/approve/business_term/{tid}", json={})
        assert r.status_code == 400, f"자기 승인이 400 이 아니다: {r.status_code} {r.text[:200]}"
        assert "자기 승인은 승인이 아닙니다" in r.text
    finally:
        config.ORG_DEFAULT_USER_ID = saved
