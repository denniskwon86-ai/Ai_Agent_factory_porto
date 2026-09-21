"""[2026-09-20] 「사용 재개」는 **중단 직전 상태로** 되돌린다 — 무조건 활성이 아니다.

⚠️⚠️ 종전에는 `reactivate` 가 `set_status(ACTIVE)` 하나였다. 그래서 `candidate`(아직 승인되지
  않은 Preview 후보)를 **껐다 켜는 것만으로 운영 청중**이 됐다 —
  `core/app_preview.audience_for_state` 가 candidate→Preview, active→운영으로 갈라 놓은
  의미가 그 문으로 사라진다. 승격 절차를 지나치는 길이었다.
⚠️ 「모르면 활성」은 그 사고를 다시 만든다 — 이력이 없으면 **거절**해야 한다.
"""
from __future__ import annotations

import json

import pytest


def _lifecycle(tmp_path, monkeypatch):
    """격리 뿌리에 라이브러리와 DB 를 세운 lifecycle 한 개."""
    from core import library_paths, program_lifecycle as pl

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(library_paths, "library_dir", lambda: str(library))
    return pl, pl.ProgramLifecycle(str(tmp_path / "lifecycle.db")), library


def _publish(library, release_id: str):
    folder = library / release_id
    folder.mkdir()
    (folder / "release.json").write_text(
        json.dumps({"release_id": release_id, "project_id": "p1"}), encoding="utf-8")


def test_candidate_comes_back_as_candidate_not_active(tmp_path, monkeypatch):
    """★ 핵심: 후보 판은 껐다 켜도 **후보**다. 운영 청중으로 승격되지 않는다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_candidate")

    life.set_status("rel_candidate", pl.CANDIDATE, "admin", "게시된 새 판")
    life.disable("rel_candidate", "admin", "검증 중 중단")
    assert life.get_status("rel_candidate")["status"] == pl.DISABLED

    out = life.reactivate("rel_candidate", "admin")
    assert out["status"] == pl.CANDIDATE, "후보가 운영 청중(active)으로 열렸다"

    #: 그 의미가 실제로 갈리는지 정본 판정으로 확인한다 — 상태값만 보고 끝내지 않는다.
    from core.app_preview import audience_for_state
    assert audience_for_state(pl.CANDIDATE) != audience_for_state(pl.ACTIVE)
    assert audience_for_state(out["status"]) == audience_for_state(pl.CANDIDATE)


def test_active_comes_back_as_active(tmp_path, monkeypatch):
    """★ 양성 대조 — 운영이던 판은 그대로 운영으로 돌아온다(과잉 차단이 아니다)."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_active")

    life.set_status("rel_active", pl.ACTIVE, "admin", "")
    life.disable("rel_active", "admin", "오류로 중단")
    out = life.reactivate("rel_active", "admin")
    assert out["status"] == pl.ACTIVE


def test_deprecated_keeps_its_warning(tmp_path, monkeypatch):
    """폐기 예고였던 판은 **경고를 유지한 채** 돌아온다 — 조용히 승격되지 않는다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_dep")

    life.set_status("rel_dep", pl.DEPRECATED, "admin", "다음 판으로 교체 예정")
    life.disable("rel_dep", "admin", "사고로 즉시 중단")
    out = life.reactivate("rel_dep", "admin")
    assert out["status"] == pl.DEPRECATED


def test_unknown_history_is_refused_not_guessed(tmp_path, monkeypatch):
    """⚠️ 직전 상태를 모르면 **거절한다.** 「모르면 활성」이 바로 그 사고다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_ghost")

    #: 이력 없이 상태만 disabled 로 심는다(구 자료·손상 이력을 흉내).
    conn = life._connect()
    try:
        conn.execute(
            "INSERT INTO program_status(release_id,status,reason,changed_by,changed_at) "
            "VALUES(?,?,?,?,?)", ("rel_ghost", pl.DISABLED, "옛 중단", "admin", "2026-01-01"))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(pl.ProgramLifecycleError) as caught:
        life.reactivate("rel_ghost", "admin")
    assert "확인할 수 없어" in str(caught.value)
    #: 거절했으면 **상태를 바꾸지 않았어야** 한다.
    assert life.get_status("rel_ghost")["status"] == pl.DISABLED


def test_data_fingerprint_is_not_wiped_by_reactivate(tmp_path, monkeypatch):
    """⚠️ `set_status` 는 준 값으로 **덮어쓴다** — 빈 값으로 재개하면 「어느 업무 데이터

    위에서 내린 결정인가」가 지워진다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_mark")

    life.set_status("rel_mark", pl.ACTIVE, "admin", "", data_fingerprint="FP-2026-09")
    life.disable("rel_mark", "admin", "중단")
    out = life.reactivate("rel_mark", "admin")
    assert out["status"] == pl.ACTIVE
    assert life.get_status("rel_mark").get("data_fingerprint") == "FP-2026-09"


# ── R1 [P1] 반복 재개가 청중을 올리면 안 된다 ────────────────────────────
def _snapshot(life, release_id):
    st = life.get_status(release_id)
    return (st["status"], st.get("data_fingerprint", ""),
            st.get("replacement_release_id", ""), len(life.history(release_id)))


def test_reactivate_is_a_noop_when_not_disabled(tmp_path, monkeypatch):
    """⚠️⚠️ **중단이 아니면 아무것도 바꾸지 않는다.** reactivate 는 중단 해제이지

    승격 명령이 아니다. 앞선 판은 「중단이 아니면 ACTIVE」였고, 그 때문에
    `candidate → 복원 → 다시 호출` 로 운영 청중이 됐다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)

    for release_id, seed in (("rel_cand", pl.CANDIDATE), ("rel_act", pl.ACTIVE),
                             ("rel_dep", pl.DEPRECATED)):
        _publish(library, release_id)
        life.set_status(release_id, seed, "admin", "게시" if seed != pl.ACTIVE else "")
        before = _snapshot(life, release_id)
        out = life.reactivate(release_id, "admin")
        assert out["status"] == seed, f"{seed} 인데 {out['status']} 로 바뀌었다"
        assert out.get("restored") is False, "바꾸지 않았는데 복원했다고 말한다"
        assert _snapshot(life, release_id) == before, f"{seed}: 상태·지문·대체·이력이 바뀌었다"


def test_repeated_reactivate_does_not_climb_to_active(tmp_path, monkeypatch):
    """★ 이번 결함의 핵심 — **복원한 뒤 한 번 더 눌러도** 후보는 후보다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_twice")

    life.set_status("rel_twice", pl.CANDIDATE, "admin", "게시")
    life.disable("rel_twice", "admin", "중단")
    assert life.reactivate("rel_twice", "admin")["status"] == pl.CANDIDATE

    before = _snapshot(life, "rel_twice")
    assert life.reactivate("rel_twice", "admin")["status"] == pl.CANDIDATE, "두 번째 호출이 올렸다"
    assert _snapshot(life, "rel_twice") == before, "두 번째 호출이 기록을 남겼다"


def test_reactivate_still_checks_actor_and_existence(tmp_path, monkeypatch):
    """조기 반환이 **검증을 건너뛰지 않는다.**"""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_guard")

    with pytest.raises(pl.ProgramLifecycleError):
        life.reactivate("rel_guard", "   ")
    with pytest.raises(pl.ProgramLifecycleError):
        life.reactivate("rel_absent", "admin")


# ── R2 [P1] 지문·대체 대상은 «중단 직전 그 한 행» 에서 온다 ────────────────
def test_empty_fingerprint_is_not_backfilled_from_the_past(tmp_path, monkeypatch):
    """⚠️ F1 → **빈 지문 상태** → 중단 → 복원. 빈 값도 값이다 — F1 을 되살리면

    **다른 시점의 데이터가 현재 상태에 결속된다.**"""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_fp")

    life.set_status("rel_fp", pl.ACTIVE, "admin", "", data_fingerprint="F1")
    life.set_status("rel_fp", pl.CANDIDATE, "admin", "새 판", data_fingerprint="")
    life.disable("rel_fp", "admin", "중단")

    out = life.reactivate("rel_fp", "admin")
    assert out["status"] == pl.CANDIDATE
    assert life.get_status("rel_fp").get("data_fingerprint") == "", "과거 F1 을 끌어다 붙였다"


def test_fingerprint_comes_from_the_snapshot_just_before_disable(tmp_path, monkeypatch):
    """★ 양성 대조 — F1 → F2 → 중단 → 복원이면 **F2** 다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_fp2")

    life.set_status("rel_fp2", pl.ACTIVE, "admin", "", data_fingerprint="F1")
    life.set_status("rel_fp2", pl.ACTIVE, "admin", "", data_fingerprint="F2")
    life.disable("rel_fp2", "admin", "중단")

    life.reactivate("rel_fp2", "admin")
    assert life.get_status("rel_fp2").get("data_fingerprint") == "F2"


def test_replacement_release_survives_the_restore(tmp_path, monkeypatch):
    """폐기 예고의 **대체 대상**도 복원 때 사라지지 않는다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_old")
    _publish(library, "rel_new")

    life.set_status("rel_old", pl.DEPRECATED, "admin", "교체 예정",
                    replacement_release_id="rel_new")
    life.disable("rel_old", "admin", "중단")

    out = life.reactivate("rel_old", "admin")
    assert out["status"] == pl.DEPRECATED
    assert life.get_status("rel_old").get("replacement_release_id") == "rel_new"


# ── R3 [P2] 낡은 복원 판단이 남의 변경을 덮지 않는다 ──────────────────────
def test_stale_restore_does_not_overwrite_a_concurrent_change(tmp_path, monkeypatch):
    """★ 결정적 재현 — 복원점을 읽은 «뒤» 다른 요청이 상태를 바꾼다.

    ⚠️ append-only 이력은 「과거 행이 안 바뀐다」는 뜻이지 「현재 상태가 그대로다」가 아니다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_race")

    life.set_status("rel_race", pl.CANDIDATE, "admin", "게시")
    life.disable("rel_race", "admin", "중단")

    original = life._restore_point

    def racing(release_id, conn=None):
        point = original(release_id, conn)
        #: 판정과 쓰기 사이에 «남» 이 상태를 바꾼다.
        life.set_status(release_id, pl.DEPRECATED, "other", "경쟁 요청")
        return point

    monkeypatch.setattr(life, "_restore_point", racing)

    with pytest.raises(pl.ProgramLifecycleError) as caught:
        life.reactivate("rel_race", "admin")
    assert "바뀌었습니다" in str(caught.value)
    #: 남의 변경이 살아 있어야 한다 — 낡은 복원이 덮지 않았다.
    assert life.get_status("rel_race")["status"] == pl.DEPRECATED


def test_history_records_the_restore(tmp_path, monkeypatch):
    """감사 이력은 지우지 않고 **한 줄 더** 쌓는다. 무엇으로 되돌렸는지도 남는다."""
    pl, life, library = _lifecycle(tmp_path, monkeypatch)
    _publish(library, "rel_hist")

    life.set_status("rel_hist", pl.CANDIDATE, "admin", "게시")
    life.disable("rel_hist", "admin", "중단")
    life.reactivate("rel_hist", "admin")

    rows = life.history("rel_hist")
    assert [r["to_status"] for r in rows] == [pl.CANDIDATE, pl.DISABLED, pl.CANDIDATE]
    assert "중단 직전 상태로 되돌림" in rows[-1]["reason"]
    assert rows[-1]["from_status"] == pl.DISABLED
