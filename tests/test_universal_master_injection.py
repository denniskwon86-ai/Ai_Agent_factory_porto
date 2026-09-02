# -*- coding: utf-8 -*-
"""★★★ 범용 노드의 기준정보 주입 — 무엇을 주고 무엇을 안 주는가. (2026-08-29)

## ⚠️⚠️ 무엇이 있었나

범용 노드(시뮬레이터·보고서 계열 7개 템플릿이 쓴다)는 `state.master_data` 라는 **원시
문자열 칸**만 읽었다. 그 칸을 채우는 곳은 `/projects/{id}/mega/plan` 하나뿐인데(LLM 이
«추천 지표» 를 지어내 저장한다) **프로젝트 63개 전부 비어 있었다.**

한편 SW 파이프라인은 같은 자리에서 `get_master_context()` 를 부른다 — 조직 범위로 거르는
확정 조회다. `mfg_sim` 으로 부르면 8,947자가 나온다(LME 니켈가·환율·TC/RC·CBAM…).

★★★ 그래서 시뮬레이터 스킬이 「**상상 금지 — 주입된 데이터로 예측하라**」고 명령하는데
  아무 데이터도 도착하지 않았다. 수행 불가능한 지시였고 결과는 지어낸 숫자였다.

## ⚠️⚠️ 그리고 고치면서 **새 오염**을 만들 뻔했다

배선한 뒤 `mfg_sim` 만 확인하고 넘어갔더니, 도메인을 유추할 수 없는 템플릿
(`content-marketing`·`data-analytics`)에 **비철금속 제련 기준정보 10,141자**가 통째로
들어갔다 — 마케팅 콘텐츠 쓰는 에이전트에게 자용로·BOM·CBAM 을 주는 꼴이다.
`get_master_context` 는 도메인이 비면 «도메인 무관» 으로 전수를 주기 때문이다.

★ **관련 없는 기준정보는 «없는 것» 보다 나쁘다** — 산출물이 그쪽으로 끌려간다.
  같은 형태의 사고가 이미 있었다(`context_engine.py:66` — 전수가 곧 DB 전체가 되어
  블록 하나가 예산을 삼켰다). 이 시험이 그 가드를 고정한다.
"""
import io
from contextlib import redirect_stdout

import pytest

from nodes.universal import _master_block_text
from state_models import ProjectState

#: ⚠️⚠️ **DB 내용에 기대지 않는다.** `tests/conftest.py` 의 autouse fixture 가 master.db 를
#:   `tmp_path` 사본으로 돌린다(올바른 격리다 — 시험이 운영 기준정보를 읽으면 안 된다).
#:   그래서 이 파일이 고정하는 것은 «무엇이 담겼는가» 가 아니라 **내가 쓴 가드·폴백 논리**다:
#:   어떤 템플릿에 확정 조회를 «부르는가/안 부르는가», 실패하면 어디로 떨어지는가, 예산은
#:   누구 것을 쓰는가. 조회기 자체는 `core/master_data` 의 시험이 본다.
_SENTINEL = "[[MASTER_CONTEXT_SENTINEL]]"

#: 템플릿 id 는 `templates/*.json` 에 실재하는 것만 쓴다(내 말로 짓지 않는다).
_MFG = ("mfg_sim", "manufacturing-cost-analysis", "manufacturing-qc",
        "manufacturing-production", "manufacturing-market-forecast")
_NO_DOMAIN = ("data-analytics", "content-marketing")


@pytest.fixture()
def calls(monkeypatch):
    """확정 조회를 센티널로 바꾸고 **호출 인자를 받아 적는다.**"""
    seen = []

    def _fake(state, max_chars=-1):
        seen.append({"max_chars": max_chars,
                     "template_id": getattr(state, "template_id", "")})
        return _SENTINEL

    from core.master_data import master_data as md
    monkeypatch.setattr(md, "get_master_context", _fake)
    return seen


def _block(**kw) -> str:
    base = dict(project_name="t", initial_idea="원료 조달 원가와 환율 변동의 영업이익 영향",
                workspace_root="projects/CRM003")
    base.update(kw)
    with redirect_stdout(io.StringIO()):          # 노드의 print 억제
        return _master_block_text(ProjectState(**base))


# ── 계측기부터 ──────────────────────────────────────────────────────────
def test_센티널_배선이_실제로_작동한다(calls):
    """⚠️ 이것이 깨지면 아래가 전부 «주입 안 됨» 으로 공회전하며 초록이 된다."""
    assert _SENTINEL in _block(template_id="mfg_sim")
    assert len(calls) == 1


# ── ① 도메인이 있으면 부른다 ────────────────────────────────────────────
@pytest.mark.parametrize("tid", _MFG)
def test_제조_계열_템플릿은_확정조회를_부른다(tid, calls):
    assert _SENTINEL in _block(template_id=tid), f"{tid} 가 확정 조회를 안 부른다"
    assert calls and calls[0]["template_id"] == tid


# ── ② 도메인이 없으면 부르지 않는다 (내가 만들 뻔한 오염) ───────────────
@pytest.mark.parametrize("tid", _NO_DOMAIN)
def test_도메인을_모르는_템플릿에는_주입하지_않는다(tid, calls):
    """★★★ **이 파일의 요지.** 마케팅 콘텐츠에 구리 제련 파라미터를 주면 안 된다.

    `get_master_context` 는 도메인이 비면 «도메인 무관» 으로 **전수**를 준다. 가드를 빼고
    실측했더니 `content-marketing` 에 비철금속 제련 기준정보 **10,141자**가 들어갔다.
    ★ 관련 없는 기준정보는 «없는 것» 보다 나쁘다 — 산출물이 그쪽으로 끌려간다."""
    assert _block(template_id=tid) == "", f"{tid} 에 무관한 기준정보가 주입된다"
    assert not calls, "도메인을 모르는데 확정 조회를 불렀다"


# ── ③ 사람이 도메인을 명시하면 통과한다 ─────────────────────────────────
def test_도메인을_명시하면_템플릿과_무관하게_받는다(calls):
    """★ 가드가 «금지» 가 아니라 «유추 실패 시 보류» 임을 고정한다.

    ⚠️ 이 시험이 없으면 다음 사람이 가드를 «이 템플릿은 영원히 못 받는다» 로 읽는다."""
    assert _SENTINEL in _block(template_id="content-marketing",
                               master_domains=["manufacturing"])


# ── ④ 종전 경로를 끊지 않는다 (MEGA 흐름) ───────────────────────────────
def test_도메인이_없으면_상태의_값으로_떨어진다(calls):
    """⚠️ `/mega/plan` 이 채우는 `state.master_data` 를 끊으면 그쪽 흐름이 죽는다."""
    assert _block(template_id="data-analytics",
                  master_data="[추천 지표] 목표 리드타임 30일") == "[추천 지표] 목표 리드타임 30일"


def test_확정조회가_터져도_막지_않는다(monkeypatch):
    """★ 조회 실패는 «판정» 이 아니다 — 종전 값으로 진행한다."""
    def _boom(state, max_chars=-1):
        raise RuntimeError("조회 불가")

    from core.master_data import master_data as md
    monkeypatch.setattr(md, "get_master_context", _boom)
    assert _block(template_id="mfg_sim", master_data="[추천 지표] X") == "[추천 지표] X"


def test_둘_다_있으면_확정조회가_앞에_온다(calls):
    """★ 사내 확정 기준이 LLM 추천값보다 세다 — 순서가 곧 우선순위다."""
    got = _block(template_id="mfg_sim", master_data="[추천 지표] X")
    assert got.index(_SENTINEL) < got.index("[추천 지표]")


# ── ⑤ 예산을 여기서 다시 정의하지 않았는가 ──────────────────────────────
def test_예산이_SW_파이프라인과_같은_식이다(calls):
    """★★★ 두 경로가 각자 예산을 정하면 갈리고, 갈린 쪽이 굶는다.

    ⚠️ 기준정보 하나가 예산을 삼켜 기술명세가 통째로 잘린 사고가 이미 있었다
      (실측 21,877자 > 20,000자 — `context_engine.py:66`)."""
    import config

    _block(template_id="mfg_sim")
    expected = max(8000, int(getattr(config, "CONTEXT_MAX_LENGTH", 20000) * 0.5))
    assert calls[0]["max_chars"] == expected, (
        f"예산 {calls[0]['max_chars']} 이 SW 파이프라인의 {expected} 와 다르다")
