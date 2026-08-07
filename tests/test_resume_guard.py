"""[D-017 §9 P3-4] 멈춰 있는 동안 세상이 바뀌었을 때의 재개 규칙.

스프린트는 멈춰 있을 수 있다 — HOTL 이 사람의 답을 기다리거나 쿼터가 소진돼 동결되거나.
그 사이에 셋이 바뀔 수 있고 셋 다 조용히 지나가면 안 된다.

| 바뀐 것 | 그대로 재개하면 |
|---|---|
| 권한 회수 | 자격 없는 사람이 실행을 이어간다 |
| 템플릿 폐기 | 폐기된 워크플로우가 계속 돈다 — 「승인된 것만 실행」이 무너진다 |
| **버전 변경** | **체크포인트와 다른 그래프로 이어붙는다** |

★★ 세 번째가 가장 위험하고 가장 안 보인다. LangGraph 체크포인트는 노드 이름으로 상태를
  들고 있어서, 그 노드가 사라졌거나 순서가 바뀌면 실행은 **오류 없이** 단계를 건너뛰거나
  엉뚱한 지점으로 간다. 산출물은 나오고 아무도 「무엇이 빠졌는지」 묻지 않는다.
"""
import pytest

from core import config_snapshot as cs
from core import resume_guard as rg


def _patch(monkeypatch, agents):
    import core.agent_asset_adapter as ad
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: {"agents": agents})


A1 = [{"id": "A", "enabled": True, "skill": "s.md"},
      {"id": "B", "enabled": True, "hotl_after": True}]


# ── ① 구성이 같으면 재개한다 ────────────────────────────────────────────────
def test_same_config_resumes(tmp_path, monkeypatch):
    ws = str(tmp_path / "p")
    _patch(monkeypatch, A1)
    cs.write(ws, cs.capture("t"))
    v = rg.check(ws, "t")
    assert v.ok and v.compared
    assert v.started_fingerprint == v.current_fingerprint


# ── ② 구성이 달라지면 막고, 무엇이 달라졌는지 말한다 ────────────────────────
def test_changed_config_blocks_and_names_the_change(tmp_path, monkeypatch):
    """★★★ 「구성이 바뀌었습니다」만 말하면 사용자는 무엇을 되돌려야 할지 모른다.

    그러면 결국 «그냥 새로 시작» 을 고르고, 그때까지 쓴 LLM 비용이 버려진다."""
    ws = str(tmp_path / "p")
    _patch(monkeypatch, A1)
    cs.write(ws, cs.capture("t"))

    _patch(monkeypatch, [A1[0]])            # B 가 사라졌다
    v = rg.check(ws, "t")
    assert not v.ok and v.compared
    assert any("빠진 에이전트" in c and "B" in c for c in v.changes), v.changes
    # ⚠️ 왜 위험한지가 문구에 있어야 한다 — 없으면 사용자는 「그냥 무시하고 돌려」를 요구한다.
    assert "건너뛰" in v.reason


def test_hotl_point_change_is_named(tmp_path, monkeypatch):
    """사용자 확인 지점이 사라지면 **사람이 봐야 할 곳을 안 보고 지나간다.**"""
    ws = str(tmp_path / "p")
    _patch(monkeypatch, A1)
    cs.write(ws, cs.capture("t"))
    _patch(monkeypatch, [A1[0], {"id": "B", "enabled": True, "hotl_after": False}])
    v = rg.check(ws, "t")
    assert not v.ok
    assert any("HOTL" in c for c in v.changes), v.changes


def test_subtle_change_still_named(tmp_path, monkeypatch):
    """에이전트 목록은 같은데 스킬만 바뀐 경우에도 **말은 해야 한다.**

    ⚠️ 「달라졌는데 무엇이 달라졌는지 못 말하는」 상태를 만들지 않는다 — 그런 메시지는
      사용자를 «무시하고 진행» 으로 몬다."""
    ws = str(tmp_path / "p")
    _patch(monkeypatch, A1)
    cs.write(ws, cs.capture("t"))
    _patch(monkeypatch, [{"id": "A", "enabled": True, "skill": "other.md"}, A1[1]])
    v = rg.check(ws, "t")
    assert not v.ok
    assert v.changes and all(c.strip() for c in v.changes)


# ── ③ 템플릿 폐기 ───────────────────────────────────────────────────────────
def test_retired_workflow_blocks_resume(tmp_path, monkeypatch):
    """★ 폐기된 워크플로우로는 재개하지 않는다 — 「승인된 것만 실행」이 재개에도 적용된다."""
    ws = str(tmp_path / "p")
    _patch(monkeypatch, A1)
    cs.write(ws, cs.capture("t"))

    import core.agent_asset_adapter as ad

    def _retired(tid, **kw):
        raise RuntimeError("RETIRED 상태입니다 — 승인된 워크플로우만 실행할 수 있습니다.")

    monkeypatch.setattr(ad, "resolve_workflow", _retired)
    v = rg.check(ws, "t")
    assert not v.ok
    assert "폐기됐거나" in v.reason and "RETIRED" in v.reason


# ── ④ 모르면 막지 않는다 (여기만 fail-open) ─────────────────────────────────
def test_missing_baseline_is_fail_open_but_says_so(tmp_path, monkeypatch):
    """★★ 시작 시점 기록이 없으면(P3-2 이전 프로젝트) **막지 않는다.**

    ⚠️ 막으면 진행 중이던 모든 프로젝트가 재개 불가가 된다. 유출 경로가 아니라 **가용성
      경로**이므로 열되, 비교하지 못했다는 사실을 남긴다(`compared=False`).
      이 저장소의 규칙 — 유출은 fail-closed, 가용성은 fail-open."""
    ws = str(tmp_path / "empty")
    _patch(monkeypatch, A1)
    v = rg.check(ws, "t")
    assert v.ok
    assert not v.compared
    assert "비교하지 못했" in v.reason


# ── ⑤ 라우트가 실제로 쓰는가 ────────────────────────────────────────────────
def test_both_resume_paths_are_guarded():
    """★★★ **한쪽만 걸면 사용자는 막힌 쪽을 피해 열린 쪽으로 간다.**

    이 저장소가 반복해서 확인한 형태다 — 그래서 두 경로가 같은 한 줄을 쓴다."""
    import inspect

    import api.routes.factory_control as fc
    for fn, label in ((fc.resume_from_hotl, "HOTL 재개"),
                      (fc.resume_from_quota, "쿼터 재개")):
        assert "_assert_resumable" in inspect.getsource(fn), f"{label} 경로가 무방비다"
    # 판정은 한 곳에만 있어야 한다.
    assert "resume_guard" in inspect.getsource(fc._assert_resumable)


def test_route_returns_409_not_403():
    """★ 409 다 — 요청은 정당하지만 **지금 상태와 맞지 않는다.**

    ⚠️ 403 으로 답하면 사용자는 권한을 요청하러 가고, 400 으로 답하면 요청을 고치려 한다.
      실제로 할 일은 「구성을 되돌리거나 새로 가동」이다."""
    import inspect

    import api.routes.factory_control as fc
    assert "status_code=409" in inspect.getsource(fc._assert_resumable)
