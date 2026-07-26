"""저쿼터 모드(LOW_QUOTA_MODE) 티어 배정 검증 — 실제 run_debate/run_single_revision 이
단계별로 Pro/Flash 를 올바르게 고르는지 gateway.aexecute 를 모킹해 확인(LLM 0콜)."""
import asyncio
from unittest.mock import AsyncMock, patch

import config
import nodes.utils.debate as debate
from state_models import ProjectState


def _run_draft_tier(stage_key, low_quota):
    """해당 단계 드래프트 1콜의 is_heavy 를 포착한다(비평은 blocking=False 로 조기 종료)."""
    captured = []

    async def fake_aexecute(state, prompt, is_heavy=True, output_mode="code", light=False, **kw):
        captured.append(is_heavy)
        if output_mode == "json":   # 비평 호출 → 합의(무결함)로 조기 종료
            return '{"checks": [], "verdict_blocking": false}'
        return "dra프트 본문"

    with patch.object(config, "LOW_QUOTA_MODE", low_quota), \
         patch("core.llm_gateway.gateway.aexecute", new=AsyncMock(side_effect=fake_aexecute)):
        asyncio.run(debate.run_debate(ProjectState(), "rfp_skill", stage_key))
    return captured[0]  # 첫 호출 = 드래프트


def test_low_quota_document_stages_use_flash():
    # RFP/PRD/UI 드래프트 → Flash
    assert _run_draft_tier("RFP", True) is False
    assert _run_draft_tier("PLANNING", True) is False
    assert _run_draft_tier("UI_DESIGN", True) is False


def test_low_quota_structural_stages_stay_pro():
    # 아키텍처/기술명세 드래프트 → Pro 유지
    assert _run_draft_tier("ARCHITECTURE", True) is True
    assert _run_draft_tier("TECH_SPEC", True) is True


def test_normal_mode_all_drafts_pro():
    # 저쿼터 모드 꺼지면 모든 드래프트 Pro(기존 동작)
    assert _run_draft_tier("RFP", False) is True
    assert _run_draft_tier("ARCHITECTURE", False) is True


def test_single_revision_flash_in_low_quota():
    captured = []

    async def fake(state, prompt, is_heavy=True, output_mode="code", **kw):
        captured.append(is_heavy)
        return "개정본"

    with patch.object(config, "LOW_QUOTA_MODE", True), \
         patch("core.llm_gateway.gateway.aexecute", new=AsyncMock(side_effect=fake)):
        asyncio.run(debate.run_single_revision(ProjectState(), "rfp_skill", "이전", "피드백"))
    assert captured[0] is False  # 재작업 → Flash


def test_config_defaults():
    """설정 '배선'을 검증한다 — 운영 토글의 특정 값은 단정하지 않는다.

    ⚠️ 과거 이 테스트는 `LOW_QUOTA_MODE is True` 를 단정했다. 그러나 이 값은 쿼터 전략에 따라
    운영자가 바꾸는 토글이다(무료 티어=True / 유료 전환=False). 2026-07-24 유료 모델 전환으로
    False 가 되자 이 테스트가 깨졌다 — 코드 결함이 아니라 '스테일 어서션'이었다.
    → 값이 아니라 (1) 토글이 bool 로 존재하는지 (2) 구조 설계 단계가 Pro 로 유지되는 설계
      불변식이 지켜지는지를 검증한다. 티어 배정 동작 자체는 위 4개 테스트가 patch 로 양쪽 다 덮는다."""
    assert isinstance(config.LOW_QUOTA_MODE, bool)
    # 설계 불변식: 저쿼터 모드에서도 구조 설계(아키텍처/기술명세) 드래프트는 Pro 를 유지한다
    assert "ARCHITECTURE" in config.PRO_DRAFT_STAGES and "TECH_SPEC" in config.PRO_DRAFT_STAGES
