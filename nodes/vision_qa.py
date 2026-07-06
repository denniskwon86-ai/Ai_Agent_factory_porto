import os
import json
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway
from langchain_core.messages import SystemMessage, HumanMessage
import config

async def run_vision_qa(state: Any) -> Dict[str, Any]:
    """
    (Phase 3) Vision LLM을 활용한 UI/UX 시각적 품질 검증 노드.
    Playwright 등을 통해 프론트엔드 결과물을 렌더링하고 스크린샷을 찍어
    디자인 토큰, 여백, 정렬 상태를 평가합니다.
    """
    state_obj = ProjectState.model_validate(state)
    print("👁️ [Agent] Vision QA (UI/UX 시각 품질 검증) 진행 중...")
    
    # 실제 환경에서는 Playwright로 dev server를 띄우고 스크린샷을 캡처해야 함
    # 본 구현은 아키텍처 데모를 위해 Vision LLM 연동 뼈대만 제공합니다.
    screenshot_path = os.path.join(state_obj.workspace_root, "screenshot.png")
    
    # 스크린샷 캡처 시뮬레이션 (Playwright 로직이 들어갈 자리)
    has_screenshot = False
    # if os.path.exists(screenshot_path): ...
    
    if not has_screenshot:
        print("⏩ [Vision QA] UI 스크린샷이 확보되지 않아 평가를 생략합니다.")
        return {}

    # Vision 모델 연동 프롬프트
    prompt = (
        "첨부된 UI 스크린샷을 보고 다음 항목을 평가하세요.\n"
        "1. 여백(Padding/Margin)의 일관성\n"
        "2. 색상 대비(Contrast) 및 시인성\n"
        "3. 컴포넌트 정렬 상태\n\n"
        "개선이 필요한 경우 REWORK_DEV를 판정하고 구체적 피드백을 제공하세요.\n"
        "응답은 반드시 JSON 포맷이어야 합니다: {\"decision\": \"PASS\" | \"REWORK_DEV\", \"feedback\": \"...\"}"
    )
    
    # 현재 Gateway는 텍스트만 받으므로 향후 Multimodal 연동 시 base64 인코딩 추가 필요
    # output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")
    
    # 임시 목업 결과
    output_str = '{"decision": "PASS", "feedback": "UI/UX 시각 품질이 디자인 시스템과 일치합니다."}'
    
    data = json.loads(output_str)
    decision = data.get("decision", "PASS")
    feedback = data.get("feedback", "")
    
    if decision == "REWORK_DEV":
        print(f"❌ [Vision QA] 시각적 결함 감지: {feedback}")
        return {
            "reviewer_decision": "REWORK_DEV",
            "reviewer_feedback": f"👁️ [Vision QA 반려]\n{feedback}"
        }
        
    print("✅ [Vision QA] UI/UX 시각적 품질 검증 통과.")
    return {}
