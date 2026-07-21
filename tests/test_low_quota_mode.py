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
    assert config.LOW_QUOTA_MODE is True
    assert "ARCHITECTURE" in config.PRO_DRAFT_STAGES and "TECH_SPEC" in config.PRO_DRAFT_STAGES
