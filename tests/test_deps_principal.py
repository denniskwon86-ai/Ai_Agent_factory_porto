# ==========================================
# 요청자 식별·권한 단일 지점 (설계서 Phase 2)
#
# 라우트마다 헤더를 직접 받으면 SSO 이행 시 전부 고쳐야 하고, 하나만 빠뜨려도
# 그 경로는 조용히 익명으로 통과한다. 추출을 api/deps.py 한 곳으로 모은다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from api.deps import Principal, _extract_user_id, assert_can_edit_org, assert_enterprise
from core.org_directory import AccessScope
from fastapi import HTTPException


class _Req:
    """FastAPI Request 의 최소 대역 — 식별에 쓰는 세 경로만 흉내낸다."""
    def __init__(self, header=None, query=None, state_uid=None, legacy=None):
        h = {}
        if header: h[getattr(config, "ORG_USER_HEADER", "X-Factory-User")] = header
        if legacy: h["X-User-Id"] = legacy
        self.headers = h
        self.query_params = query or {}
        self.state = type("S", (), {"principal_user_id": state_uid or ""})()


def test_sso_slot_wins_over_header(monkeypatch):
    """미래 SSO 미들웨어가 채우는 슬롯이 최우선이어야 한다 — 헤더 위조로 덮을 수 없어야 함."""
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    assert _extract_user_id(_Req(header="attacker", state_uid="real_user")) == "real_user"


def test_header_then_query_fallback(monkeypatch):
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    assert _extract_user_id(_Req(header="bob")) == "bob"
    # SSE/iframe/다운로드 링크는 헤더를 붙일 수 없어 쿼리 폴백이 필요하다
    assert _extract_user_id(_Req(query={"as_user": "kim"})) == "kim"


def test_legacy_header_still_accepted(monkeypatch):
    """Phase 1 이 쓰던 X-User-Id 도 계속 받아준다 — 전환 중 깨지면 안 된다."""
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    assert _extract_user_id(_Req(legacy="old")) == "old"


def test_trust_header_off_ignores_client_supplied_id(monkeypatch):
    """★ 헤더 신뢰를 끄면 클라이언트가 보낸 식별은 전부 무시돼야 한다(SSO 최종 형태)."""
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", False, raising=False)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "", raising=False)
    assert _extract_user_id(_Req(header="bob", query={"as_user": "kim"})) == ""
    assert _extract_user_id(_Req(header="bob", state_uid="real")) == "real"


def test_default_user_when_nothing_supplied(monkeypatch):
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(config, "ORG_DEFAULT_USER_ID", "svc", raising=False)
    assert _extract_user_id(_Req()) == "svc"


# ── 권한 단언 ────────────────────────────────────────────────────────────
def _p(**kw) -> Principal:
    return Principal(user_id=kw.pop("user_id", "u"), scope=AccessScope(**kw))


def test_unrestricted_passes_every_assertion():
    p = _p(unrestricted=True)
    assert_can_edit_org(p)
    assert_enterprise(p)


def test_plain_user_denied_org_edit_and_enterprise():
    p = _p(unrestricted=False)
    with pytest.raises(HTTPException) as e1:
        assert_can_edit_org(p)
    assert e1.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        assert_enterprise(p)
    assert e2.value.status_code == 403


def test_executive_can_run_enterprise_but_not_edit_org():
    """경영진은 전사 실행은 되고 조직 편집은 안 된다 — 두 권한이 분리돼 있어야 한다."""
    p = _p(unrestricted=False, is_executive=True, can_run_enterprise=True, can_edit_org=False)
    assert_enterprise(p)
    with pytest.raises(HTTPException):
        assert_can_edit_org(p)
