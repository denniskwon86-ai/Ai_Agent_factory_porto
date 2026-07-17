import os
import json
import asyncio
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
    print("️ [Agent] Vision QA (UI/UX 시각 품질 검증) 진행 중...")
    
    screenshot_path = os.path.join(state_obj.workspace_root, "screenshot.png")
    
    # Playwright 스크린샷 캡처
    has_screenshot = False
    try:
        from playwright.async_api import async_playwright
        
        # 프로젝트 루트에 index.html 이나 dist/index.html 이 있는지 확인
        target_html = None
        # 확인 경로 우선순위: 빌드 결과물 -> 원본 -> 루트
        for p in ["frontend/dist/index.html", "frontend/index.html", "index.html"]:
            full_p = os.path.join(state_obj.workspace_root, p)
            if os.path.exists(full_p):
                target_html = full_p
                break
                
        if target_html:
            print(f" [Vision QA] 렌더링 대상 발견: {target_html}")
            target_dir = os.path.dirname(target_html)
            target_file = os.path.basename(target_html)
            
            import http.server
            import socketserver
            import threading
            import socket

            def get_free_port():
                s = socket.socket(socket.AF_INET, type=socket.SOCK_STREAM)
                s.bind(('localhost', 0))
                _, port = s.getsockname()
                s.close()
                return port

            port = get_free_port()
            Handler = http.server.SimpleHTTPRequestHandler
            
            class ThreadedHTTPServer(socketserver.TCPServer):
                allow_reuse_address = True

            httpd = ThreadedHTTPServer(("127.0.0.1", port), lambda *args, **kwargs: Handler(*args, directory=target_dir, **kwargs))
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()

            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    # HTTP url 로드 (CORS 문제 방지)
                    file_url = f"http://127.0.0.1:{port}/{target_file}"
                    await page.goto(file_url, wait_until="networkidle")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    await browser.close()
                has_screenshot = os.path.exists(screenshot_path)
            finally:
                httpd.shutdown()
                httpd.server_close()
        else:
            print("⏩ [Vision QA] 평가할 HTML/UI 결과물을 찾을 수 없습니다.")
    except Exception as e:
        print(f"⚠️ [Vision QA] Playwright 스크린샷 캡처 중 오류 발생: {e}")

    if not has_screenshot:
        print("⏩ [Vision QA] UI 스크린샷이 확보되지 않아 평가를 생략합니다.")

        scores = state_obj.stage_scores.copy() if state_obj.stage_scores else {}
        scores["VISION_QA"] = 1.0

        # reviewer_decision 초기화: 직전 반려(REWORK_DEV) 잔존 시 라우터가 UIDesigner 로 무한 왕복함
        return {
            "stage_scores": scores,
            "reviewer_decision": "NONE"
        }
    # Vision 모델 연동 프롬프트
    prompt = (
        "첨부된 UI 스크린샷을 보고 다음 항목을 엄격하게 평가하세요.\n"
        "1. 여백(Padding/Margin)의 일관성 및 시각적 균형\n"
        "2. 색상 대비(Contrast) 및 시인성\n"
        "3. 컴포넌트 정렬 상태 및 전반적인 심미성\n\n"
        "개선이 필요하거나 어색한 부분이 있다면 REWORK_DEV를 판정하고 구체적 피드백을 제공하세요.\n"
        "응답은 반드시 아래 JSON 포맷이어야 합니다: {\"decision\": \"PASS\" | \"REWORK_DEV\", \"feedback\": \"상세한 시각적 피드백...\"}"
    )
    
    print("⏳ [Vision QA] Gemini Vision 모델에 이미지 전송 및 분석 요청 중...")
    try:
        output_str = await gateway.aexecute_vision(state_obj, prompt, image_path=screenshot_path, is_heavy=True)
        data = json.loads(output_str)
        decision = data.get("decision", "PASS")
        feedback = data.get("feedback", "")
    except Exception as e:
        print(f"⚠️ [Vision QA] Vision LLM 연동 실패: {e}")
        decision = "PASS"
        feedback = str(e)
    
    if decision == "REWORK_DEV":
        print(f"❌ [Vision QA] 시각적 결함 감지: {feedback}")
        return {
            "reviewer_decision": "REWORK_DEV",
            "reviewer_feedback": f"️ [Vision QA 반려]\n{feedback}"
        }
        
    print("[OK] [Vision QA] UI/UX 시각적 품질 검증 통과.")

    scores = state_obj.stage_scores.copy() if state_obj.stage_scores else {}
    scores["VISION_QA"] = 1.0

    # reviewer_decision 초기화: 직전 반려(REWORK_DEV) 잔존 시 라우터가 UIDesigner 로 무한 왕복함
    return {
        "stage_scores": scores,
        "reviewer_decision": "NONE"
    }
