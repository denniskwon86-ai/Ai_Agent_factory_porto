# -*- coding: utf-8 -*-
"""★★★ 조회·쓰기 경로가 **이 프로젝트의 그래프**를 써야 한다. (2026-09-03 실가동)

## ⚠️⚠️ 무엇이 있었나

`mfg_sim` 실가동에서 `Sim_PM` 이 끝나고 `Sim_Designer` 직전 인터럽트에 **실제로 멈춰
있는데** 화면·API 가 「대기 없음」이라고 답했다.

조회 경로가 `get_runtime_app()` 을 **인자 없이** 불러 기본(SW) 그래프를 세우고 그 위에서
체크포인트를 읽었기 때문이다. 상태 스키마(`ProjectState`)는 두 그래프가 공유하지만
토폴로지는 다르다:

    기본 그래프 노드(NODE_IMPL)              15개
    mfg_sim 에이전트 16개 중 거기 있는 것    0개   ← 교집합 0

`snapshot.values` 는 채널에서 복원되므로 무관하지만 **`snapshot.next` 와 `aupdate_state`
는 노드를 안다는 전제 위에 선다.** 그래서 `next` 가 비어 「완료」로 읽혔다.

## 왜 여섯 곳 중 셋만 고쳤나

    197 pause_sprint            aupdate_state 로 **쓴다**        → 결속 필요
    309 is_hotl_pending         snapshot.next 로 **판정한다**    → 결속 필요
    365 apply_contract_decision aupdate_state 로 **쓴다**        → 결속 필요
    338 read_contract_state     values 만 읽는다                 → 불필요
    406 resume_hotl(선행)       values 만 (템플릿을 알아내려고)   → 불필요
    513 resume_from_suspend(선행) values 만                      → 불필요

★ 이 시험은 그 경계까지 함께 고정한다 — 다음 사람이 «전부 바꿔야 하나» 를 다시 묻지
  않도록, 그리고 셋 중 하나가 조용히 되돌아가지 않도록.
"""
import asyncio
import inspect
import io
import json
from contextlib import redirect_stdout

import pytest

import core.async_orchestrator as ao


class _FakeEngine:
    def __init__(self, nxt=("Sim_Designer",), values=None):
        self._n, self._v = nxt, (values or {"factory_mode": "PLANNING"})

    async def aget_state(self, config):
        class _S:
            next = self._n
            values = self._v
        return _S()

    async def aupdate_state(self, config, updates):
        return None


@pytest.fixture()
def spy(monkeypatch, tmp_path):
    """`get_runtime_app` 이 **무슨 인자로** 불렸는지 받아 적는다."""
    seen = []

    async def _fake(template_id="default", expected_fingerprint=""):
        seen.append({"template_id": template_id,
                     "expected_fingerprint": expected_fingerprint})
        return _FakeEngine()

    monkeypatch.setattr(ao, "get_runtime_app", _fake)

    #: ⚠️ 실제 `projects/` 를 건드리지 않는다 — 메타 경로를 tmp 로 돌린다.
    meta = tmp_path / "project_meta.json"

    def _meta_path(workspace_root):
        return str(meta)

    monkeypatch.setattr("core.project_visibility.project_meta_path", _meta_path)
    return seen, meta


def _write_meta(meta, **kw):
    meta.write_text(json.dumps(kw, ensure_ascii=False), encoding="utf-8")


# ── 계측기부터 ──────────────────────────────────────────────────────────
def test_스파이가_실제로_인자를_받아적는다(spy):
    seen, meta = spy
    _write_meta(meta, template_id="mfg_sim")
    with redirect_stdout(io.StringIO()):
        asyncio.run(ao.orchestrator._bound_engine("prj_x"))
    assert seen and seen[0]["template_id"] == "mfg_sim"


# ── ① 결속이 필요한 세 곳 ───────────────────────────────────────────────
def test_HOTL_조회가_프로젝트_그래프를_쓴다(spy):
    """★★★ **이 파일의 요지.** 기본 그래프로 읽으면 `next` 를 못 세고 «대기 없음» 이 된다."""
    seen, meta = spy
    _write_meta(meta, template_id="mfg_sim")
    with redirect_stdout(io.StringIO()):
        got = asyncio.run(ao.orchestrator.is_hotl_pending("PLANNING_1", "prj_x"))
    assert seen[0]["template_id"] == "mfg_sim", "기본 그래프로 HOTL 을 조회한다"
    assert got is True, "next 가 있는데 대기로 보지 않는다"


def test_계약결정_반영이_프로젝트_그래프를_쓴다(spy):
    """★ `aupdate_state` 는 노드를 안다는 전제 위에 선다."""
    seen, meta = spy
    _write_meta(meta, template_id="mfg_sim")
    with redirect_stdout(io.StringIO()):
        asyncio.run(ao.orchestrator.apply_contract_decision("PLANNING_1", "prj_x", {"a": 1}))
    assert seen[0]["template_id"] == "mfg_sim"


# ── ② 조회는 구성 지문으로 막지 않는다 ──────────────────────────────────
def test_조회에는_구성지문을_넘기지_않는다(spy):
    """⚠️⚠️ 지문이 어긋나면 `get_runtime_app` 이 예외를 낸다. 실행을 막는 것은 옳지만
    **조회까지 막으면 워크플로우가 개정된 순간 대기 중인 스프린트가 화면에서 사라진다** —
    지금 고치는 결함과 같은 증상이 된다."""
    seen, meta = spy
    _write_meta(meta, template_id="mfg_sim", template_fingerprint="26d1ec252041ca21")
    with redirect_stdout(io.StringIO()):
        asyncio.run(ao.orchestrator.is_hotl_pending("PLANNING_1", "prj_x"))
    assert seen[0]["expected_fingerprint"] == "", "조회가 지문에 막힐 수 있다"


# ── ③ 읽기 실패는 조회를 죽이지 않는다 ──────────────────────────────────
def test_메타를_못_읽으면_기본_그래프로_떨어진다(spy):
    """⚠️ 조회가 죽는 것보다 기본 그래프로라도 답하는 편이 낫다(종전 동작)."""
    seen, meta = spy                      # meta 파일을 만들지 않는다
    with redirect_stdout(io.StringIO()):
        asyncio.run(ao.orchestrator._bound_engine("prj_없음"))
    assert seen[0]["template_id"] == "default"


# ── ④ 경계 고정: values 만 읽는 곳은 결속하지 않는다 ────────────────────
def test_결속이_필요한_곳과_아닌_곳의_경계():
    """★ 「전부 바꿔야 하나」를 다시 묻지 않도록 판정 근거를 코드로 남긴다.

    ⚠️ 이 시험이 없으면 다음 사람이 나머지 셋도 바꾸거나, 셋 중 하나를 되돌린다."""
    src = inspect.getsource(ao)
    for fn in ("is_hotl_pending", "apply_contract_decision"):
        body = src[src.index(f"async def {fn}("):]
        body = body[:body.index("\n    async def ", 10)]
        assert "_bound_engine(" in body, f"{fn} 이 프로젝트 그래프를 안 쓴다"
    #: `values` 만 읽는 곳은 그대로 둔다 — 채널은 두 그래프가 공유한다.
    body = src[src.index("async def read_contract_state("):]
    body = body[:body.index("\n    async def ", 10)]
    assert "get_runtime_app()" in body, (
        "read_contract_state 는 values 만 읽으므로 결속이 필요 없다 — "
        "바꿨다면 그 이유를 여기 적을 것")
