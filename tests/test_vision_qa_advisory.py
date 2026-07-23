"""nodes/vision_qa.py — VisionQA '자문 강등' 검증.

VisionQA 는 UI 를 자동 반려(REWORK_DEV → UIDesigner 왕복)하지 않는다. 텍스트 추정 판정의
부정확성 + 무료 티어 콜(RPD) 폭발의 주범이던 왕복을 제거하고, 소견(ui_review_advisory)만
남겨 사람 HOTL 미리보기에서 참고하도록 한다. pytest-asyncio 없이 asyncio.run 으로 구동.
"""
import asyncio
import tempfile
import nodes.vision_qa as vq

_HTML = "<!DOCTYPE html><html><body><main><h1>단위 변환기</h1></main></body></html>"


def _state():
    return {"project_name": "T", "workspace_root": "", "ui_mockup_summary": f"```html\n{_HTML}\n```"}


def _patch(monkeypatch, decision, feedback):
    from core.llm_gateway import gateway
    import json

    async def fake_aexecute(state, prompt, **kw):
        return json.dumps({"decision": decision, "feedback": feedback}, ensure_ascii=False)
    monkeypatch.setattr(gateway, "aexecute", fake_aexecute)
    from core.broadcaster import factory_broadcaster

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(factory_broadcaster, "broadcast", noop)


def test_rework_becomes_advisory_not_blocking(monkeypatch):
    _patch(monkeypatch, "REWORK_DEV", "여백이 부족하고 시맨틱 태그가 없음")
    out = asyncio.run(vq.run_vision_qa(_state()))
    # 자동 반려 금지: reviewer_decision 은 절대 REWORK_DEV 가 아니어야 함(라우터가 되돌리지 않도록)
    assert out["reviewer_decision"] == "NONE"
    # 소견은 자문 필드에 보존
    assert "자문" in out["ui_review_advisory"]
    assert "여백이 부족" in out["ui_review_advisory"]


def test_pass_has_empty_advisory(monkeypatch):
    _patch(monkeypatch, "PASS", "")
    out = asyncio.run(vq.run_vision_qa(_state()))
    assert out["reviewer_decision"] == "NONE"
    assert out["ui_review_advisory"] == ""
    assert out["stage_scores"]["VISION_QA"] == 1.0


def test_no_html_skips(monkeypatch):
    _patch(monkeypatch, "REWORK_DEV", "무시됨")
    # UI 산출물이 전혀 없는 빈 워크스페이스(리포 루트의 frontend/ 를 잘못 읽지 않도록 격리)
    empty_ws = tempfile.mkdtemp()
    out = asyncio.run(vq.run_vision_qa({"project_name": "T", "workspace_root": empty_ws}))
    assert out["reviewer_decision"] == "NONE"
    assert out["ui_review_advisory"] == ""
