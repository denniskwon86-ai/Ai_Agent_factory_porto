import asyncio
import os
import shutil
import json
from datetime import datetime
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
                # 🚨 [Phase 3] 파괴적 삭제(rmtree) 제거 및 스마트 아카이빙 적용
                archive_dir = os.path.join(workspace_root, ".archive", datetime.now().strftime("%Y%m%d_%H%M%S"))
                os.makedirs(archive_dir, exist_ok=True)
                
                for item in os.listdir(workspace_root):
                    # .git 저장소와 기존 아카이브 폴더는 절대 건드리지 않음
                    if item in [".git", ".archive"]:
                        continue
                        
                    src_path = os.path.join(workspace_root, item)
                    dst_path = os.path.join(archive_dir, item)
                    try:
                        shutil.move(src_path, dst_path)
                    except Exception as e:
                        print(f"⚠️ [Orchestrator] 아카이브 이동 실패 ({item}): {e}")
                        
            os.makedirs(workspace_root, exist_ok=True)
            print(f"🧹 [Orchestrator] 신규 기획을 위해 기존 산출물을 .archive/ 폴더로 안전하게 백업했습니다.")

        if not task_id.startswith("PLANNING"):
            wbs_mgr = WBSManager(workspace_root=workspace_root)
            wbs_mgr.checkout_task(task_id)
            await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "status": "IN_PROGRESS"})

        config = {"configurable": {"thread_id": f"sprint_{task_id}"}}
        task = asyncio.create_task(self._run_sprint_loop(config, project_state_payload, task_id, workspace_root))
        self.active_tasks[task_id] = task
        return True

    # 🚨 [Phase 3] 세션 인지형 프로세스 강제 일시정지 (Pause) 메서드 추가
    async def pause_sprint(self, task_id: str) -> bool:
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()  # 비동기 태스크 강제 종료
            del self.active_tasks[task_id]
            print(f"🛑 [Orchestrator] Task {task_id} 프로세스가 사용자에 의해 일시정지 되었습니다.")
            await factory_broadcaster.broadcast("SPRINT_PAUSED", {"task_id": task_id})
            return True
        return False

    async def _run_sprint_loop(self, config: dict, state_dict: dict, task_id: str, workspace_root: str):
        try:
            async for event in langgraph_engine.astream(state_dict, config=config):
                for node_name, state_data in event.items():
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    self._save_latest_state(full_state, workspace_root) 
                    
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Sprint Loop Cancelled (Paused): {task_id}")
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
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    self._save_latest_state(full_state, workspace_root) 
                    
                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data})
                    
            snapshot = await langgraph_engine.aget_state(config)
            if snapshot.next:
                await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id})
            else:
                await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id})
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Resume Stream Cancelled (Paused): {task_id}")
        except Exception as e:
            print(f"🚨 [Orchestrator] Resume Stream Error: {e}")

orchestrator = AsyncFactoryOrchestrator()