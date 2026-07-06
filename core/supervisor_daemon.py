import asyncio
import json
from core.broadcaster import factory_broadcaster
from core.async_orchestrator import orchestrator
from core.llm_gateway import gateway

class SupervisorDaemon:
    """
    백그라운드에서 모든 노드 완료 이벤트를 모니터링하며,
    비용 효율적인 모델(예: Flash/GPT-4o-mini)을 이용해 프로젝트 진행 방향의 결함을 실시간으로 감지하고 개입합니다.
    """
    def __init__(self):
        # 브로드캐스터 내부 리스너에 등록
        factory_broadcaster.add_internal_listener(self.handle_event)
        
    async def handle_event(self, event_type: str, payload: dict):
        if event_type == "NODE_COMPLETED":
            await self._evaluate_state(payload)
            
    async def _evaluate_state(self, payload: dict):
        project_id = payload.get("project_id")
        state_data = payload.get("state")
        node_name = payload.get("node")
        
        if not project_id or not state_data or not node_name:
            return
            
        task_id = state_data.get("current_sprint_task_id", "UNKNOWN")
        
        prompt = f"""
당신은 백그라운드에서 프로젝트의 진행 상황을 모니터링하는 비즈니스 관점의 슈퍼바이저(AGI)입니다.
현재 '{node_name}' 노드의 작업이 방금 완료되었습니다.

[🚨 절대 주의사항]
하위 에이전트들(Micro-Swarm)이 단순 문법이나 컴파일(빌드) 에러는 자체적인 샌드박스를 통해 100% 필터링하고 해결합니다.
따라서 당신은 "문법 에러", "오타", "import 누락" 같은 사소한 개발 결함을 지적할 필요가 없습니다.

당신은 오직 다음 사항만 감시하십시오:
1. 사용자의 기획 의도(RFP/PRD)에 맞지 않는 엉뚱한 비즈니스 로직이 짜여졌는가?
2. 이미 사용자가 승인했거나 지시한 사항(human_feedback_queue 내역 참고)을 무시하고 무한루프(핑퐁)를 돌고 있는가?
3. 전체 아키텍처 관점에서 치명적인 논리적 결함이 있는가?

위 관점에서 개입하여 파이프라인을 당장 중단시켜야 한다면 'intervene': true 로 설정하고, 'reason'에 그 이유와 수정 지시사항을 상세히 적어주세요.
개입할 필요 없이 기획 의도대로 잘 진행되고 있다면 'intervene': false 로 설정하세요.

반드시 다음 JSON 형식으로만 응답하세요:
{{
  "intervene": true 또는 false,
  "reason": "개입 시 상세 이유 (intervene이 false면 빈 문자열)"
}}
"""
        try:
            # 실시간 백그라운드 모니터링이므로 비용 최적화를 위해 is_heavy=False (Flash/mini 모델) 사용
            # 컨텍스트 절감을 위해 light=True 속성 사용
            response = await gateway.aexecute(
                state=state_data, 
                skill_prompt=prompt, 
                is_heavy=False, 
                output_mode="json", 
                light=True
            )
            
            result = json.loads(response)
            if result.get("intervene") and result.get("reason"):
                reason = result.get("reason")
                print(f"👁️‍🗨️ [Supervisor Daemon] 치명적 결함 감지! 파이프라인 개입(Pause)을 시도합니다. 사유: {reason}")
                await orchestrator.pause_sprint(task_id, project_id, reason=reason)
                
        except Exception as e:
            print(f"⚠️ [Supervisor Daemon] 상태 모니터링 중 오류 발생: {e}")

    async def handle_user_chat(self, project_id: str, task_id: str, message: str, state_data: dict) -> dict:
        prompt = f"""
당신은 현재 가동 중인 프로젝트의 비즈니스 관점 슈퍼바이저(AGI)입니다.
사용자(인간)가 파이프라인 가동 중에 당신에게 다음과 같은 메시지(질문/지시)를 보냈습니다:
"{message}"

현재 프로젝트 상태와 산출물을 분석하여 사용자의 질문에 답변하거나, 지시에 대해 어떻게 처리할지 안내하세요.
만약 사용자의 지시가 매우 중요하여 현재 진행 중인 파이프라인을 당장 일시정지(Pause)하고 에이전트들의 작업 방향을 수정해야 한다면 'intervene': true 로 설정하세요.
그렇지 않고 단순한 답변이나, 다음 작업에 반영해도 충분하다면 'intervene': false 로 설정하세요.

반드시 다음 JSON 형식으로만 응답하세요:
{{
  "reply": "사용자에게 보여줄 당신의 친절한 답변 (Markdown 형식 지원)",
  "intervene": true 또는 false,
  "reason": "개입(일시정지) 시 에이전트들에게 전달할 수정 지시사항 (intervene이 false면 빈 문자열)"
}}
"""
        try:
            response = await gateway.aexecute(
                state=state_data, 
                skill_prompt=prompt, 
                is_heavy=False, 
                output_mode="json", 
                light=True
            )
            
            result = json.loads(response)
            if result.get("intervene") and result.get("reason"):
                reason = result.get("reason")
                print(f"👁️‍🗨️ [Supervisor Daemon] 사용자의 지시로 파이프라인 개입(Pause)을 시도합니다. 사유: {reason}")
                await orchestrator.pause_sprint(task_id, project_id, reason=reason)
            
            return {"status": "success", "reply": result.get("reply", "답변을 생성하지 못했습니다.")}
                
        except Exception as e:
            print(f"⚠️ [Supervisor Daemon] 사용자 채팅 처리 중 오류 발생: {e}")
            return {"status": "error", "reply": "슈퍼바이저와 통신하는 중 오류가 발생했습니다."}

# 싱글톤 인스턴스 생성 (모듈 import 시 자동 등록)
supervisor_daemon = SupervisorDaemon()
