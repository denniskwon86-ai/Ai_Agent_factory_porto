import asyncio
import os
import shutil
import json
from fastapi.encoders import jsonable_encoder
from typing import Optional, Dict, Any

from core.agent_graph import app as langgraph_engine
from core.broadcaster import factory_broadcaster
from nodes.utils.wbs_manager import WBSManager

class AsyncFactoryOrchestrator:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}

    def _save_latest_state(self, state_data: Any, workspace_root: str):
        try:
            os.makedirs(workspace_root, exist_ok=True)
            state_path = os.path.join(workspace_root, "latest_state.json")
            data_to_save = jsonable_encoder(state_data)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"🚨 상태 백업 실패: {e}")

    async def start_sprint(self, task_id: str, project_state_payload: dict, workspace_root: str) -> bool:
        
        if task_id.startswith("PLANNING"):
            if os.path.exists(workspace_root):
                shutil.rmtree(workspace_root, ignore_errors=True)
            os.makedirs(workspace_root, exist_ok=True)
            print(f"🧹 [Orchestrator] 신규 기획을 위해 {workspace_root} 폴더를 초기화했습니다.")

        if not task_id.startswith("PLANNING"):
            wbs_mgr = WBSManager(workspace_root=workspace_root)
            wbs_mgr.checkout_task(task_id)
            await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "status": "IN_PROGRESS"})

        config = {"configurable": {"thread_id": f"sprint_{task_id}"}}
        task = asyncio.create_task(self._run_sprint_loop(config, project_state_payload, task_id, workspace_root))
        self.active_tasks[task_id] = task
        return True

    async def _run_sprint_loop(self, config: dict, state_dict: dict, task_id: str, workspace_root: str):
        try:
            async for event in langgraph_engine.astream(state_dict, config=config):
                for node_name, state_data in event.items():
                    # 🚨 [핵심 패치 1] Delta(state_data)가 아닌 Full State를 퍼올려 물리적 파일에 저장 (Docs 증발 방지)
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    self._save_latest_state(full_state, workspace_root) 
                    
                    # 브로드캐스터에는 Delta만 보내어 프론트엔드의 Zustand 상태망과 효율적으로 병합되게 함
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except Exception as e:
            print(f"🚨 [Orchestrator] Sprint Loop Error: {e}")

    async def resume_hotl(self, task_id: str, feedback: Optional[str]) -> bool:
        config = {"configurable": {"thread_id": f"sprint_{task_id}"}}
        snapshot = await langgraph_engine.aget_state(config)
        if not snapshot.values:
            return False
            
        current_state = snapshot.values
        workspace_root = current_state.get("workspace_root", "./workspace") if isinstance(current_state, dict) else current_state.workspace_root
        
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
        except Exception:
            return False
            
        task = asyncio.create_task(self._resume_stream(config, task_id, workspace_root))
        self.active_tasks[task_id] = task
        return True

    async def _resume_stream(self, config: dict, task_id: str, workspace_root: str):
        try:
            async for event in langgraph_engine.astream(None, config=config):
                for node_name, state_data in event.items():
                    # 🚨 [핵심 패치 2] Resume 루프에서도 Full State 백업 로직 동일 적용
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    self._save_latest_state(full_state, workspace_root) 
                    
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except Exception as e:
            print(f"🚨 [Orchestrator] Resume Stream Error: {e}")

orchestrator = AsyncFactoryOrchestrator()