"""[사용자 결정 2026-07-30] 프로그램 사용여부 — **삭제하지 않고 비활성화한다.**

> "이미 생성되어 다른 사용자가 기록을 남긴 코드(프로그램)을 삭제하면 꼬일 수 있으니
>  그냥 사용여부만 제어해서 더이상 사용하지 않는 프로그램이라고 비활성화 조치만 하는 것이
>  좋을 것 같습니다."

이 파일이 잠그는 것:
  · 비활성화해도 **기록과 이력이 남는다**(삭제와 다르다)
  · 사유 없는 비활성화는 거부된다 — 사유가 없으면 아무도 다시 켜지 못한다
  · 의존 대상이 있으면 확인 없이 끄지 못한다
  · 대체 프로그램이 또 비활성이면 거부된다 — 막다른 길에서 막다른 길로 보내지 않는다
  · 미기록은 사용 가능이지만 `recorded=False` — 추정을 관리자 결정으로 표시하지 않는다
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import program_lifecycle as plmod
from core.program_lifecycle import (ACTIVE, DEPRECATED, DISABLED,
                                    ProgramLifecycleError, ProgramLifecycle)


def _publish(lib, release_id):
    d = lib / release_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "release.json").write_text(
        json.dumps({"release_id": release_id, "project_name": release_id}),
        encoding="utf-8")
    return release_id


@pytest.fixture()
def pl(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    monkeypatch.setattr(plmod, "_LIBRARY_DIR", str(lib), raising=False)
    _publish(lib, "app-a")
    _publish(lib, "app-b")
    inst = ProgramLifecycle(db_path=str(tmp_path / "pl.db"))
    inst._lib = lib
    return inst


class _NoDeps:
    def list_forks(self, rid=""): return []
    def list_shares(self, release_id="", **kw): return []
    def get_promotion(self, rid, target_scope="enterprise"): return None


@pytest.fixture(autouse=True)
def _no_deps(monkeypatch):
    """의존 조회는 별도 저장소를 본다 — 기본은 의존 없음으로 고정해 테스트를 결정론적으로 만든다."""
    import core.workspace_promotion as wp
    monkeypatch.setattr(wp, "workspace", _NoDeps(), raising=False)


# ── 미기록과 관리자 결정을 구분한다 ─────────────────────────────────────────
def test_unrecorded_is_usable_but_not_claimed_as_approved(pl):
    """★★ 기본을 disabled 로 두면 기존 프로그램이 전부 죽는다.

    그래서 사용 가능으로 보되, `recorded=False` 로 **추정임을 밝힌다** —
    추정을 관리자의 결정처럼 표시하면 감사에서 거짓이 된다."""
    st = pl.get_status("app-a")
    assert st["status"] == ACTIVE and st["recorded"] is False
    assert "승인한 상태는 아닙니다" in st["note"]
    assert pl.assert_usable("app-a")["usable"] is True


def test_recorded_active_says_recorded_true(pl):
    pl.set_status("app-a", ACTIVE, actor="it-admin", reason="검토 완료")
    assert pl.get_status("app-a")["recorded"] is True


# ── 비활성화는 삭제가 아니다 ────────────────────────────────────────────────
def test_disable_blocks_use_but_keeps_record(pl):
    """★★ 사용을 막는 것과 존재를 지우는 것은 다른 조치이며, 필요한 것은 전자다."""
    out = pl.disable("app-a", actor="it-admin", reason="후속 버전으로 대체")
    assert out["status"] == DISABLED
    assert "삭제되지 않았습니다" in out["note"]
    # 기록은 조회된다.
    assert pl.get_status("app-a")["reason"] == "후속 버전으로 대체"
    assert pl.history("app-a"), "변경 이력이 남아야 한다"
    # 그러나 사용은 막힌다.
    with pytest.raises(ProgramLifecycleError, match="사용을 중단"):
        pl.assert_usable("app-a")


def test_history_is_append_only_across_changes(pl):
    pl.disable("app-a", actor="admin1", reason="결함")
    pl.reactivate("app-a", actor="admin2", reason="수정 완료")
    pl.disable("app-a", actor="admin3", reason="재발")
    h = pl.history("app-a")
    assert [e["to_status"] for e in h] == [DISABLED, ACTIVE, DISABLED]
    assert [e["actor"] for e in h] == ["admin1", "admin2", "admin3"]
    assert h[1]["from_status"] == DISABLED, "직전 상태가 남아야 언제부터 못 썼는지 안다"


def test_reactivate_restores_use(pl):
    pl.disable("app-a", actor="it-admin", reason="결함")
    pl.reactivate("app-a", actor="it-admin")
    assert pl.assert_usable("app-a")["usable"] is True


# ── 사유는 필수다 ───────────────────────────────────────────────────────────
def test_disable_without_reason_is_refused(pl):
    """★ 사유가 없으면 나중에 "왜 껐지?"에 답할 수 없고, 그러면 아무도 다시 켜지 못한다."""
    with pytest.raises(ProgramLifecycleError, match="사유"):
        pl.disable("app-a", actor="it-admin", reason="")


def test_actor_is_required(pl):
    with pytest.raises(ProgramLifecycleError, match="변경자"):
        pl.disable("app-a", actor="", reason="결함")


def test_unknown_status_is_refused(pl):
    with pytest.raises(ProgramLifecycleError, match="허용되지 않은 상태"):
        pl.set_status("app-a", "archived", actor="it-admin", reason="x")


def test_nonexistent_program_is_refused(pl):
    with pytest.raises(ProgramLifecycleError, match="존재하지 않는"):
        pl.disable("no-such-app", actor="it-admin", reason="결함")


def test_path_traversal_release_id_is_refused(pl):
    with pytest.raises(ProgramLifecycleError, match="존재하지 않는"):
        pl.disable("../../etc", actor="it-admin", reason="결함")


# ── 예고는 사용을 막지 않지만 경고를 남긴다 ─────────────────────────────────
def test_deprecated_still_usable_with_warning(pl):
    """★ 예고 없이 죽이면 의존하던 부서가 원인 모를 고장을 겪는다.

    다만 경고를 반환하지 않으면 `deprecated` 는 장식이 된다."""
    pl.set_status("app-a", DEPRECATED, actor="it-admin", reason="2026-09 종료 예정",
                  replacement_release_id="app-b")
    u = pl.assert_usable("app-a")
    assert u["usable"] is True
    assert "자제" in u["warning"] and "app-b" in u["warning"]


# ── 대체 프로그램 ───────────────────────────────────────────────────────────
def test_replacement_must_exist(pl):
    with pytest.raises(ProgramLifecycleError, match="대체 프로그램이 존재하지"):
        pl.disable("app-a", actor="it-admin", reason="대체",
                   replacement_release_id="ghost")


def test_replacement_cannot_be_itself(pl):
    with pytest.raises(ProgramLifecycleError, match="자기 자신"):
        pl.disable("app-a", actor="it-admin", reason="대체",
                   replacement_release_id="app-a")


def test_replacement_cannot_be_disabled(pl):
    """★★ 막다른 길에서 또 막다른 길로 보내면 사용자는 같은 프로그램을 새로 만든다."""
    pl.disable("app-b", actor="it-admin", reason="폐기")
    with pytest.raises(ProgramLifecycleError, match="또 다른 막다른 길"):
        pl.disable("app-a", actor="it-admin", reason="대체",
                   replacement_release_id="app-b")


def test_disabled_message_points_to_replacement(pl):
    pl.disable("app-a", actor="it-admin", reason="v2 로 이전",
               replacement_release_id="app-b")
    with pytest.raises(ProgramLifecycleError, match="app-b"):
        pl.assert_usable("app-a")


def test_disabled_without_replacement_says_so(pl):
    pl.disable("app-a", actor="it-admin", reason="폐기")
    with pytest.raises(ProgramLifecycleError, match="대체 프로그램이 지정되지 않았"):
        pl.assert_usable("app-a")


# ── 의존 대상 ───────────────────────────────────────────────────────────────
class _WithDeps(_NoDeps):
    def list_forks(self, rid=""):
        return [{"new_project_id": "child-1"}, {"new_project_id": "child-2"}]

    def get_promotion(self, rid, target_scope="enterprise"):
        return {"status": "promoted"}


def test_disable_with_dependents_requires_acknowledgement(pl, monkeypatch):
    """★★ 의존이 있는 프로그램을 조용히 끄면, 끊긴 쪽은 원인을 모른 채 고장난다."""
    import core.workspace_promotion as wp
    monkeypatch.setattr(wp, "workspace", _WithDeps(), raising=False)
    with pytest.raises(ProgramLifecycleError) as ei:
        pl.disable("app-a", actor="it-admin", reason="폐기")
    msg = str(ei.value)
    assert "전사 승격" in msg and "child-1" in msg
    assert "acknowledge_dependents" in msg

    out = pl.disable("app-a", actor="it-admin", reason="폐기",
                     acknowledge_dependents=True)
    assert out["status"] == DISABLED
    assert out["dependents"]["blast_radius"] == "enterprise"


def test_dependents_lookup_failure_is_not_reported_as_zero(pl, monkeypatch):
    """★★ "영향 없음"과 "영향을 못 셌음"은 다르다. 실패를 0 으로 두면 위험을 과소평가한다."""
    class _Broken:
        def list_forks(self, rid=""): raise RuntimeError("db down")
        def list_shares(self, **kw): raise RuntimeError("db down")
        def get_promotion(self, rid, target_scope="enterprise"): raise RuntimeError("db down")
    import core.workspace_promotion as wp
    monkeypatch.setattr(wp, "workspace", _Broken(), raising=False)
    dep = pl.dependents("app-a")
    assert dep["count"] == 0
    assert len(dep["unmeasured"]) == 3, "세지 못한 항목이 드러나야 한다"


def test_reactivate_does_not_require_dependent_acknowledgement(pl, monkeypatch):
    """켜는 것은 아무것도 끊지 않는다 — 여기서 확인을 요구하면 복구가 늦어진다."""
    import core.workspace_promotion as wp
    monkeypatch.setattr(wp, "workspace", _WithDeps(), raising=False)
    pl.disable("app-a", actor="it-admin", reason="폐기", acknowledge_dependents=True)
    assert pl.reactivate("app-a", actor="it-admin")["status"] == ACTIVE


# ── 목록 ────────────────────────────────────────────────────────────────────
def test_list_statuses_only_shows_recorded(pl):
    pl.disable("app-a", actor="it-admin", reason="폐기")
    rows = pl.list_statuses()
    assert [r["release_id"] for r in rows] == ["app-a"], "미기록은 목록에 없다"
    assert pl.list_statuses(DISABLED)[0]["release_id"] == "app-a"
    assert pl.list_statuses(ACTIVE) == []


def test_audit_event_types_are_registered(pl):
    from core.enterprise_context import audit
    assert audit.PROGRAM_STATUS_CHANGED in audit.EVENTS
    assert audit.PROGRAM_USE_BLOCKED in audit.EVENTS


def test_status_change_is_audited(pl):
    from core.enterprise_context import audit
    pl.disable("app-a", actor="it-admin", reason="폐기")
    lines = []
    if os.path.exists(audit._LOG_PATH):
        with open(audit._LOG_PATH, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
    hits = [l for l in lines if l.get("event") == "PROGRAM_STATUS_CHANGED"]
    assert hits and hits[-1]["actor"] == "it-admin"
    assert "active->disabled" in hits[-1].get("detail", "")
