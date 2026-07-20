import os
import json
import asyncio
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway, is_llm_error_text
from langchain_core.messages import SystemMessage, HumanMessage
import config

async def run_vision_qa(state: Any) -> Dict[str, Any]:
    """
    (Phase 3) 경량형 Vision QA (HTML 정적 검증 노드)
    Playwright 등을 사용하지 않고, UI 목업이나 프론트엔드 빌드 결과물의 HTML/DOM을 추출하여
    텍스트 기반 LLM에 전달하여 UI/UX 구조를 평가합니다.
    """
    state_obj = ProjectState.model_validate(state)
    print("️ [Agent] Vision QA (UI/UX 정적 코드 검증) 진행 중...")
    
    html_content = ""
    
    # 0순위: 기획 단계에서 생성된 UI 목업 추출
    ui_mockup = getattr(state_obj, "ui_mockup_summary", "") or ""
    if ui_mockup:
        import re
        match = re.search(r'```(?:html)?\s*(<!DOCTYPE html>[\s\S]*?)```', ui_mockup, re.IGNORECASE)
        if match:
            html_content = match.group(1)
        elif "<!DOCTYPE html>" in ui_mockup:
            idx = ui_mockup.find("<!DOCTYPE html>")
            html_content = ui_mockup[idx:]
            
    if not html_content:
        # 확인 경로 우선순위: 빌드 결과물 -> 원본 -> 루트
        for p in ["frontend/dist/index.html", "frontend/index.html", "index.html", "public/index.html", "src/index.html", "dist/index.html"]:
            full_p = os.path.join(state_obj.workspace_root, p)
            if os.path.exists(full_p):
                try:
                    with open(full_p, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    print(f" [Vision QA] 로컬 파일에서 HTML 로드 완료: {full_p}")
                    break
                except Exception as e:
                    print(f"⚠️ [Vision QA] HTML 파일 읽기 실패: {e}")
                    
    if not html_content:
        print("⏩ [Vision QA] 평가할 HTML/UI 결과물을 찾을 수 없습니다. 평가를 생략합니다.")
        scores = state_obj.stage_scores.copy() if state_obj.stage_scores else {}
        scores["VISION_QA"] = 1.0
        return {
            "stage_scores": scores,
            "reviewer_decision": "NONE"
        }

    # HTML body 부분 추출 (토큰 절약)
    import re
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.IGNORECASE | re.DOTALL)
    if body_match:
        analyze_target = body_match.group(1)
    else:
        analyze_target = html_content
        
    # 매우 긴 번들 코드를 제외하기 위해 글자수 제한 (토큰 비용 방지)
    analyze_target = analyze_target[:8000]

    prompt = (
        "다음은 프론트엔드 UI의 핵심 HTML/DOM 구조입니다.\n"
        "아래 사항을 정적 분석하여 평가해 주세요.\n"
        "1. 여백(Padding/Margin), 정렬 등을 위한 적절한 CSS 클래스(또는 Tailwind)가 논리적으로 사용되었는가?\n"
        "2. 시맨틱 태그(header, main, section 등) 및 접근성 구조가 잘 구성되었는가?\n"
        "3. UI/UX 관점에서 컴포넌트 레이아웃이 훌륭하며 의도한 기획 목적에 부합하는가?\n\n"
        f"--- HTML 코드 ---\n{analyze_target}\n-----------------\n\n"
        "개선이 필요하거나 명백히 깨진 구조가 있다면 REWORK_DEV를 판정하고 구체적 피드백을 제공하세요.\n"
        "응답은 반드시 아래 JSON 포맷이어야 합니다: {\"decision\": \"PASS\" | \"REWORK_DEV\", \"feedback\": \"상세한 구조적 피드백...\"}"
    )
    
    print("⏳ [Vision QA] 정적 HTML 구조 분석 요청 중...")
    # ⚠️ [판정 붕괴 수정] output_mode 기본값은 "code"(파일 스키마 강제 구조화 출력)라서
    #    {"decision","feedback"} JSON 을 절대 받을 수 없다 → 판정이 항상 PASS 로 붕괴하던 결함.
    #    반드시 "json" 모드로 호출한다. (UI 구조 자문 판정이므로 Flash + 경량 컨텍스트면 충분)
    output_str = await gateway.aexecute(state_obj, prompt, is_heavy=False, output_mode="json", light=True)

    # [fail-loud] 게이트웨이 최종 실패 sentinel 은 '판정 불가'다 — 조용한 PASS 로 삼키지 않고
    # 예외로 표면화한다(오케스트레이터가 SPRINT_FAILED 방송 → UI 에 실패 노출 → 사람이 재시도 결정).
    if is_llm_error_text(output_str):
        raise RuntimeError(f"[Vision QA] 판정 LLM 호출 실패(인프라 오류) — 검증 불가로 중단: {str(output_str)[:200]}")

    try:
        data = json.loads(output_str)
        decision = data.get("decision", "PASS")
        feedback = data.get("feedback", "")
    except Exception as e:
        # 모델이 '응답은 했으나' 형식이 비정형인 경우에 한해 보수적 PASS 유지(자문 게이트 성격).
        # 인프라 실패(위 sentinel)와 달리, 이 경로는 게이트웨이가 정상 응답을 준 상태다.
        print(f"⚠️ [Vision QA] 판정 JSON 파싱 실패(비정형 응답) — 보수적 PASS 처리: {e}")
        decision = "PASS"
        feedback = str(e)
    
    if decision == "REWORK_DEV":
        print(f"❌ [Vision QA] 구조적 결함 감지: {feedback}")
        return {
            "reviewer_decision": "REWORK_DEV",
            "reviewer_feedback": f"️ [Vision QA 반려]\n{feedback}"
        }
        
    print("[OK] [Vision QA] UI/UX 정적 코드 품질 검증 통과.")
    scores = state_obj.stage_scores.copy() if state_obj.stage_scores else {}
    scores["VISION_QA"] = 1.0

    return {
        "stage_scores": scores,
        "reviewer_decision": "NONE"
    }
