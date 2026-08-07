"""[D-017 §9 P3-2] 실행 구성의 신원 — **무엇이 실제로 돌았는가.**

## 이 파일이 고정하는 두 가지

`agent_graph.get_runtime_app()` 은 컴파일된 그래프를 `template_id` 로만 캐시했고, 그 주석이
스스로 한계를 적어 두었다: 「조직 자산을 개정하면 이 캐시가 낡는다」. 거기서 두 결함이 함께
나온다 — ① **개정이 먹지 않는다**(서버 재시작 전까지 옛 그래프가 돈다) ② **무엇이 돌았는지
알 수 없다**(산출물만 보고 되짚을 수 없다).

둘 다 «구성의 신원» 이 없어서 생긴다. 지문을 만들어 캐시 키로 쓰면 ①이, 기록하면 ②가 사라진다.

★ 지문에는 **실행 결과를 바꾸는 것만** 넣는다. 표시용 이름을 넣으면 오탈자 수정에도 재컴파일이
  일어나고, 「무엇이 달라졌나」를 물어도 답이 소음이 된다.
"""
import json

import pytest

from core import config_snapshot as cs


def _reg(agents):
    return {"agents": agents}


# ── ① 지문은 실행에 영향을 주는 것만 센다 ───────────────────────────────────
def test_display_only_change_keeps_fingerprint(monkeypatch):
    """★★ 이름만 바꾸면 지문이 **그대로**여야 한다 — 아니면 오탈자 수정이 재컴파일을 부른다."""
    a1 = [{"id": "A", "enabled": True, "skill": "s.md", "name_ko": "가", "role": "설명"}]
    a2 = [{"id": "A", "enabled": True, "skill": "s.md", "name_ko": "나", "role": "다른 설명"}]
    import core.agent_asset_adapter as ad
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg(a1))
    f1 = cs.capture("t").fingerprint
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg(a2))
    f2 = cs.capture("t").fingerprint
    assert f1 and f1 == f2, "표시용 필드가 지문을 흔든다"


@pytest.mark.parametrize("field,value", [
    ("enabled", False),
    ("hotl_after", True),
    ("skill", "other.md"),
    ("model_tier", "flash"),
    ("llm", False),
])
def test_execution_affecting_change_moves_fingerprint(monkeypatch, field, value):
    """★★ 실행이 달라지는 변경은 지문을 **반드시** 바꾼다 — 아니면 옛 그래프가 계속 돈다."""
    base = {"id": "A", "enabled": True, "hotl_after": False, "skill": "s.md",
            "model_tier": "pro", "llm": True}
    import core.agent_asset_adapter as ad
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg([dict(base)]))
    f1 = cs.capture("t").fingerprint
    changed = dict(base)
    changed[field] = value
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg([changed]))
    f2 = cs.capture("t").fingerprint
    assert f1 != f2, f"{field} 를 바꿨는데 지문이 그대로다 — 개정이 먹지 않는다"


def test_agent_order_matters(monkeypatch):
    """순서가 곧 실행 순서다(범용 선형 파이프라인) — 순서가 바뀌면 다른 구성이다."""
    import core.agent_asset_adapter as ad
    x = {"id": "A", "enabled": True}
    y = {"id": "B", "enabled": True}
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg([x, y]))
    f1 = cs.capture("t").fingerprint
    monkeypatch.setattr(ad, "resolve_workflow", lambda tid, **kw: _reg([y, x]))
    assert f1 != cs.capture("t").fingerprint


# ── ② 모르면 «없음» 이라고 쓰지 않는다 ──────────────────────────────────────
def test_unresolved_config_is_not_an_empty_snapshot(monkeypatch):
    """★★★ 구성을 읽지 못하면 지문이 비고 **이유가 붙는다.**

    ⚠️ 빈 지문을 «구성이 비었다» 로 읽으면 안 된다. 그래서 `resolved` 와 `error` 를 함께 본다 —
      이 저장소의 «조회 실패 ≠ 0건» 이 실행 구성에도 그대로 적용된다."""
    import core.agent_asset_adapter as ad

    def _boom(tid, **kw):
        raise RuntimeError("승인된 워크플로우가 아닙니다")

    monkeypatch.setattr(ad, "resolve_workflow", _boom)
    s = cs.capture("t")
    assert not s.resolved
    assert s.fingerprint == ""
    assert "승인된 워크플로우가 아닙니다" in s.error, "왜 못 읽었는지가 사라졌다"


def test_capture_uses_the_runnable_gate(monkeypatch):
    """★ 스냅샷은 **실제 실행과 같은 판정**을 지나야 한다.

    ⚠️ 조회용 완화(`require_runnable=False`)로 찍으면, 승인되지 않은 구성을 스냅샷이
      정당화한다 — 「기록에는 이것이 돌았다고 되어 있다」가 되고 그것은 거짓이다."""
    import inspect
    src = inspect.getsource(cs.capture)
    assert "require_runnable=False" not in src


# ── ③ 이력으로 쌓인다 ───────────────────────────────────────────────────────
def test_history_accumulates_and_dedupes(tmp_path, monkeypatch):
    """마지막 것만 남기면 「3주 전 산출물은 무엇으로 만들었나」에 답할 수 없다.

    ⚠️ 다만 같은 지문이 연달아 오면 쌓지 않는다 — 재개할 때마다 같은 줄이 늘어난다."""
    ws = str(tmp_path / "p")
    import core.agent_asset_adapter as ad
    monkeypatch.setattr(ad, "resolve_workflow",
                        lambda tid, **kw: _reg([{"id": "A", "enabled": True}]))
    s1 = cs.capture("t")
    cs.write(ws, s1)
    cs.write(ws, s1)                                     # 같은 지문 — 쌓이지 않아야
    monkeypatch.setattr(ad, "resolve_workflow",
                        lambda tid, **kw: _reg([{"id": "A", "enabled": False}]))
    cs.write(ws, cs.capture("t"))

    data = cs.read(ws)
    assert data is not None
    assert len(data["history"]) == 2, f"이력이 {len(data['history'])}건 — 중복 억제/누적이 어긋난다"
    assert data["current"]["fingerprint"] == data["history"][-1]["fingerprint"]


def test_read_returns_none_when_absent(tmp_path):
    """없는 것과 빈 것을 구분한다."""
    assert cs.read(str(tmp_path / "nope")) is None


def test_write_is_atomic(tmp_path, monkeypatch):
    """중간에 죽어도 반쪽 파일이 남지 않아야 한다 — `os.replace` 를 쓴다."""
    import inspect
    assert "os.replace" in inspect.getsource(cs.write)


# ── ④ 캐시 키가 지문을 쓴다 ─────────────────────────────────────────────────
def test_runtime_cache_key_includes_fingerprint():
    """★★★ [이 변경의 본체] 개정이 먹지 않던 원인은 캐시 키가 `tid` 하나였던 것이다.

    ⚠️ 실제로 컴파일하면 SQLite 체크포인터가 붙어 무겁다 — 여기서는 **키가 지문을 포함하도록
      배선됐는지**만 본다. 동작 확인은 위 지문 테스트가 담당한다."""
    import inspect

    from core import agent_graph
    src = inspect.getsource(agent_graph.get_runtime_app)
    assert "config_snapshot" in src, "지문을 계산하지 않는다"
    assert 'f"{tid}@{snap.fingerprint}"' in src, "캐시 키에 지문이 들어가지 않는다"
    assert "except Exception" in src, "지문 실패가 실행을 막으면 안 된다(fail-open)"


# ── ⑤ 릴리스에 봉인된다 ─────────────────────────────────────────────────────
def test_release_seals_the_snapshot():
    """프로젝트 기록은 계속 덮이지만 릴리스는 그 시점에 고정돼야 한다."""
    import inspect

    import api.routes.factory_control as fc
    src = inspect.getsource(fc.create_release)
    assert 'release["config_snapshot"]' in src, "릴리스에 구성이 봉인되지 않는다"
    assert "resolved\": False" in src or "'resolved': False" in src, (
        "읽지 못했을 때 키를 비우고 있다 — 「옛 릴리스라 기록이 없다」와 구분되지 않는다")


def test_sprint_start_records_snapshot():
    import inspect

    import api.routes.factory_control as fc
    src = inspect.getsource(fc.start_sprint)
    assert "config_snapshot" in src and "_snap.write" in src, "가동 시점에 남기지 않는다"
    assert "가동은 계속" in src, "스냅샷 실패가 가동을 막으면 안 된다"


def test_snapshot_json_is_serializable(tmp_path, monkeypatch):
    """dataclass 가 그대로 JSON 이 돼야 한다 — 직렬화가 깨지면 기록 자체가 사라진다."""
    import core.agent_asset_adapter as ad
    monkeypatch.setattr(ad, "resolve_workflow",
                        lambda tid, **kw: _reg([{"id": "A", "enabled": True, "hotl_after": True}]))
    s = cs.capture("t", policy_decision_id="dec_1")
    raw = json.dumps(s.to_dict(), ensure_ascii=False)
    back = json.loads(raw)
    assert back["policy_decision_id"] == "dec_1"
    assert back["interrupt_after"] == ["A"]
    assert back["resolved"] is True


def test_planning_archive_keeps_the_snapshot():
    """★★★ [2026-08-07 살아 있는 서버 실측 결함] **기록이 그것을 만든 실행에 의해 지워졌다.**

    신규 기획(`PLANNING_*`)은 기존 산출물을 `.archive/<시각>/` 으로 옮긴다. 그런데
    `config_snapshot.json` 까지 함께 옮겨져, 방금 「무엇으로 도는지」를 찍어 두고도 프로젝트
    폴더에는 기록이 없는 상태가 됐다(`.archive/20260807_104923/config_snapshot.json`).

    ⚠️ 단위 테스트로는 잡히지 않았다 — 스냅샷 모듈도, 라우트 배선도 각각 초록이었다.
      **두 기능이 만나는 지점**은 실제로 돌려 봐야 보였다.

    ⚠️ 이력이 목적이므로 누적돼야 한다. 기획을 다시 돌릴 때마다 비워지면 「3주 전 산출물은
      무엇으로 만들었나」에 답할 수 없다."""
    import inspect

    from core import async_orchestrator
    src = inspect.getsource(async_orchestrator)
    assert '"config_snapshot.json"' in src, (
        "기획 재가동 아카이브가 구성 스냅샷을 쓸어 간다 — 제외 목록에 넣을 것")
    assert cs.SNAPSHOT_FILE == "config_snapshot.json", (
        "파일 이름이 바뀌었는데 아카이브 제외 목록은 그대로다 — 두 곳이 갈라졌다")
