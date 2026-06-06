import asyncio
import os
import shutil
from typing import Optional, Dict, Any
from core.agent_graph import app as langgraph_engine
from core.broadcaster import factory_broadcaster
from nodes.utils.wbs_manager import WBSManager

class AsyncFactoryOrchestrator:
    """AI 팩토리의 비동기 실행 및 HOTL(인간 개입) 중재를 담당하는 중앙 오케스트레이터"""
    
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def start_sprint(self, task_id: str, project_state_payload: dict) -> bool:
        """새로운 스프린트(또는 신규 기획)를 가동합니다."""
        
        # 🚨 [원인 해결 1] 신규 기획(PLANNING) 시작 시 '과거의 유령'을 없애기 위해 workspace 폴더를 완전히 폭파 후 재생성
        if task_id.startswith("PLANNING"):
            workspace_path = project_state_payload.get("workspace_root", "./workspace")
            if os.path.exists(workspace_path):
                # 권한 오류 방지를 위해 ignore_errors=True 옵션 적용
                shutil.rmtree(workspace_path, ignore_errors=True)
            os.makedirs(workspace_path, exist_ok=True)
            print(f"🧹 [Orchestrator] 신규 기획을 위해 {workspace_path} 폴더를 초기화했습니다.")

        # 신규 기획이 아닐 때만 WBS 상태를 업데이트 (PLANNING 트랙은 WBS가 아직 없으므로 패스)
        if not task_id.startswith("PLANNING"):
            wbs_mgr = WBSManager()
            wbs_mgr.checkout_task(task_id)
            await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "status": "IN_PROGRESS"})

        config = {"configurable": {"thread_id": f"sprint_{task_id}"}}
        task = asyncio.create_task(self._run_sprint_loop(config, project_state_payload, task_id))
        self.active_tasks[task_id] = task
        return True

    async def _run_sprint_loop(self, config: dict, state_dict: dict, task_id: str):
        """스프린트 초기 가동 루프"""
        try:
            async for event in langgraph_engine.astream(state_dict, config=config):
                for node_name, state_data in event.items():
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except Exception as e:
            print(f"🚨 [Orchestrator] Sprint Loop Error: {e}")

    async def resume_hotl(self, task_id: str, feedback: Optional[str]) -> bool:
        """인간의 피드백을 상태에 주입하고 멈춰있던 파이프라인을 재가동합니다."""
        config = {"configurable": {"thread_id": f"sprint_{task_id}"}}
        snapshot = await langgraph_engine.aget_state(config)
        
        if not snapshot.values:
            print(f"🚨 [Orchestrator] {task_id}의 체크포인트를 찾을 수 없습니다.")
            return False
            
        current_state = snapshot.values
        
        try:
            if feedback:
                if isinstance(current_state, dict):
                    queue = current_state.get("human_feedback_queue", [])
                else:
                    queue = getattr(current_state, "human_feedback_queue", [])
                
                queue.append({"task_id": task_id, "feedback": feedback, "status": "pending", "priority": 1})
                await langgraph_engine.aupdate_state(config, {"human_feedback_queue": queue, "needs_revision": True})
            else:
                await langgraph_engine.aupdate_state(config, {"needs_revision": False})
                
        except Exception as e:
            print(f"🚨 [Orchestrator] HOTL 피드백 주입 중 치명적 오류 발생: {e}")
            return False
            
        task = asyncio.create_task(self._resume_stream(config, task_id))
        self.active_tasks[task_id] = task
        return True

    async def _resume_stream(self, config: dict, task_id: str):
        """HOTL 이후 중단된 파이프라인을 이어서 실행하는 루프"""
        try:
            async for event in langgraph_engine.astream(None, config=config):
                for node_name, state_data in event.items():
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except Exception as e:
            print(f"🚨 [Orchestrator] Resume Stream Error: {e}")

orchestrator = AsyncFactoryOrchestrator()