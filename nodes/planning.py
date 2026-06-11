import os
import re
import asyncio
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway

def _load_skill(role_name: str) -> str:
    """마크다운 프롬프트를 동적으로 로드 (하드코딩 배제)"""
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

async def run_master_pm(state: ProjectState) -> Dict[str, Any]:
    """
    [Track 0] 전체 시스템 Master PRD 작성
    무거운 도메인 지식이 필요하므로 Pro 모델(is_heavy=True)에 라우팅합니다.
    """
    print("🧭 [Agent] Master PM 비동기 기획 진행 중...")
    prompt = _load_skill("pm_skill")
    
    # 1. PRD 본문 생성 (Pro 모델)
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    
    # 2. 토큰 과금 방어용 고속 요약 (Flash 모델)
    summary_prompt = "다음 기획서를 핵심 기능과 Out-of-Scope 위주로 짧게 요약하십시오:\n\n" + output[:8000]
    summary = await gateway.aexecute(state, summary_prompt, is_heavy=False)
    
    return {
        "prd_summary": summary
    }

async def run_master_pmo(state: ProjectState) -> Dict[str, Any]:
    """
    [Track 0] WBS 마스터플랜 JSON 분할
    JSON 스키마를 엄격히 준수해야 하므로 Pro 모델을 사용합니다.
    """
    print("🧭 [Agent] Master PMO 비동기 WBS 분할 진행 중...")
    prompt = _load_skill("pmo_skill")
    
    output = await gateway.aexecute(state, prompt, is_heavy=True)
    
    # JSON 텍스트 블록만 안전하게 추출 (Zero-Chatter 보장)
    json_str = output
    try:
        match = re.search(r'\{.*\}', output, re.DOTALL)
        if match:
            json_str = match.group()
    except Exception:
        pass
    
    # 🚨 [패치] Pydantic vs Dict 타입 충돌 방어
    workspace_root = state.get("workspace_root") if isinstance(state, dict) else state.workspace_root
        
    def _save_wbs_to_disk():
        """디스크 I/O 블로킹 방지를 위한 내부 헬퍼 함수 (Lock 적용 완료)"""
        if not workspace_root:
            print("🚨 [에러] workspace_root가 설정되지 않아 WBS 저장을 건너뜁니다.")
            return
            
        from nodes.utils.wbs_manager import WBSManager
        wbs_mgr = WBSManager(workspace_root=workspace_root)
        wbs_mgr.save_raw_wbs(json_str)
            
    # 비동기 이벤트 루프가 멈추지 않도록 별도 워커 스레드로 파일 저장 오프로딩
    await asyncio.to_thread(_save_wbs_to_disk)
    
    return {
        "factory_mode": "EXECUTION"
    }