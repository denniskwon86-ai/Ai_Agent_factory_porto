import asyncio
import os
import shutil
import json
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from typing import Optional, Dict, Any

from core.agent_graph import get_runtime_app
from core.broadcaster import factory_broadcaster
from nodes.utils.wbs_manager import WBSManager
from core.persona_learner import persona_learner
from core.llm_gateway import QuotaExhaustedException

def _pid(workspace_root: str) -> str:
    """workspace_root(./projects/<id>)에서 project_id 추출 - SSE 프로젝트 격리용."""
    return os.path.basename(str(workspace_root or "").rstrip("/\\"))


def _skey(project_id: str, task_id: str) -> str:
    """프로젝트 격리 복합 키 - langgraph thread_id 및 active_tasks 키 공용.
    동일 task_id(예: 'E2E-01' - WBS 가 프로젝트마다 동일하게 생성)가 서로 다른 프로젝트에서
    같은 체크포인트(pipeline_state.db)를 공유해 이전 프로젝트의 산출물/진행상태가 새 프로젝트로
    새는 것을 차단한다. thread_id 와 in-memory active_tasks 키 모두 이 복합키로 통일."""
    return f"{project_id}__{task_id}"


def _thread(project_id: str, task_id: str) -> str:
    return f"sprint_{_skey(project_id, task_id)}"


class AsyncFactoryOrchestrator:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_projects: Dict[str, str] = {}  # task_id -> project_id (삭제 시 취소·격리용)

    async def _save_latest_state(self, state_data: Any, workspace_root: str):
        # 전체 상태(생성 코드 포함 - 수 MB 가능)의 json 직렬화+쓰기는 동기 작업이라
        # 매 노드마다 이벤트 루프(SSE/전체 API)를 멈추게 하므로 스레드로 내린다
        def _write():
            os.makedirs(workspace_root, exist_ok=True)
            state_path = os.path.join(workspace_root, "latest_state.json")
            data_to_save = jsonable_encoder(state_data)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        try:
            await asyncio.to_thread(_write)
        except Exception as e:
            print(f" 상태 백업 실패: {e}")

    async def start_sprint(self, task_id: str, project_state_payload: dict, workspace_root: str) -> bool:
        if task_id.startswith("PLANNING") and len(task_id.split("_")) == 2:
            if os.path.exists(workspace_root):
                #  [Phase 3] 파괴적 삭제(rmtree) 제거 및 스마트 아카이빙 적용
                def _archive():
                    archive_dir = os.path.join(workspace_root, ".archive", datetime.now().strftime("%Y%m%d_%H%M%S"))
                    os.makedirs(archive_dir, exist_ok=True)
                    for item in os.listdir(workspace_root):
                        # .git/.archive 와 project_meta.json(템플릿 바인딩의 권위 원본, 생성 시 1회 기록)은
                        # 절대 이동 금지 - 아카이브되면 이후 모든 태스크가 'default' 템플릿으로 강등된다
                        if item in [".git", ".archive", "project_meta.json"]:
                            continue
                        src_path = os.path.join(workspace_root, item)
                        dst_path = os.path.join(archive_dir, item)
                        try:
                            shutil.move(src_path, dst_path)
                        except Exception as e:
                            print(f"⚠️ [Orchestrator] 아카이브 이동 실패 ({item}): {e}")
                # 디스크 이동은 동기 작업 - 이벤트 루프 동결 방지 위해 스레드로
                await asyncio.to_thread(_archive)

            os.makedirs(workspace_root, exist_ok=True)
            print(f" [Orchestrator] 신규 기획을 위해 기존 산출물을 .archive/ 폴더로 안전하게 백업했습니다.")

        pid = _pid(workspace_root)
        if not (task_id.startswith("PLANNING") and len(task_id.split("_")) == 2):
            wbs_mgr = WBSManager(workspace_root=workspace_root)
            wbs_mgr.checkout_task(task_id)
            await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "status": "IN_PROGRESS", "project_id": pid})

        skey = _skey(pid, task_id)
        # 이중 가동 차단: 같은 thread_id 로 두 astream 이 동시에 돌면 체크포인트 오염 + LLM 중복 호출 +
        # 먼저 돌던 태스크 핸들이 덮여 취소 불가(좀비)가 된다
        existing = self.active_tasks.get(skey)
        if existing and not existing.done():
            print(f"⚠️ [Orchestrator] Task {task_id} (project={pid}) 는 이미 실행 중 - 중복 가동 요청 무시.")
            return False
        config = {"configurable": {"thread_id": _thread(pid, task_id)}}
        task = asyncio.create_task(self._run_sprint_loop(config, project_state_payload, task_id, workspace_root))
        self.active_tasks[skey] = task
        self.task_projects[skey] = pid
        # 완료 시 레지스트리에서 제거(무한 누적 방지). pause 가 먼저 지웠어도 pop(None) 이라 무해.
        task.add_done_callback(lambda t, k=skey: (self.active_tasks.pop(k, None), self.task_projects.pop(k, None)))
        return True

    async def cancel_project(self, project_id: str) -> int:
        """해당 프로젝트의 실행 중 스프린트를 모두 취소 (삭제/이탈 시 좀비 스프린트 방지)."""
        cancelled = 0
        for tid, t in list(self.active_tasks.items()):
            if self.task_projects.get(tid) == project_id:
                if t and not t.done():
                    t.cancel()
                    cancelled += 1
                self.active_tasks.pop(tid, None)
                self.task_projects.pop(tid, None)
        if cancelled:
            print(f" [Orchestrator] 프로젝트 '{project_id}'의 실행 중 스프린트 {cancelled}건을 취소했습니다.")
        return cancelled

    #  [Phase 3] 세션 인지형 프로세스 강제 일시정지 (Pause) 메서드 추가
    async def pause_sprint(self, task_id: str, project_id: str, reason: str = "") -> bool:
        skey = _skey(project_id, task_id)
        task = self.active_tasks.get(skey)
        if task and not task.done():
            task.cancel()  # 비동기 태스크 강제 종료
            pid = self.task_projects.get(skey, project_id)
            del self.active_tasks[skey]
            self.task_projects.pop(skey, None)
            print(f" [Orchestrator] Task {task_id} (project={project_id}) 프로세스가 강제 일시정지 되었습니다. 사유: {reason}")
            
            # 슈퍼바이저 인터럽트 발생 시 LangGraph State에 기록하여 UI가 인지하도록 함
            if reason:
                try:
                    langgraph_engine = await get_runtime_app()
                    config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
                    snapshot = await langgraph_engine.aget_state(config)
                    if snapshot.values:
                        current_state = snapshot.values
                        queue = current_state.get("human_feedback_queue", []) if isinstance(current_state, dict) else getattr(current_state, "human_feedback_queue", [])
                        queue.append({"task_id": task_id, "feedback": f"[SUPERVISOR] {reason}", "status": "pending", "priority": 5})
                        await langgraph_engine.aupdate_state(config, {"human_feedback_queue": queue, "needs_revision": True, "supervisor_feedback": reason})
                        
                        new_snapshot = await langgraph_engine.aget_state(config)
                        ws_root = current_state.get("workspace_root", f"./projects/{project_id}") if isinstance(current_state, dict) else getattr(current_state, "workspace_root", f"./projects/{project_id}")
                        await self._save_latest_state(new_snapshot.values, ws_root)
                except Exception as e:
                    print(f"⚠️ [Orchestrator] 슈퍼바이저 인터럽트 상태 기록 실패: {e}")

            await factory_broadcaster.broadcast("SPRINT_PAUSED", {"task_id": task_id, "project_id": pid, "reason": reason})
            return True
        return False

    async def _broadcast_stream_end(self, langgraph_engine, config: dict, task_id: str, workspace_root: str):
        """스트림 종료 시 결과 브로드캐스트. 빌드 재시도(3회) 소진 실패를 '완료'로 위장하지 않고
        SPRINT_FAILED 로 보고하고 WBS 태스크를 FAILED 로 마킹한다(자가복구 P3)."""
        pid = _pid(workspace_root)
        snapshot = await langgraph_engine.aget_state(config)
        if snapshot.next:
            await factory_broadcaster.broadcast("HOTL_PAUSED", {"task_id": task_id, "project_id": pid})
            return
        vals = snapshot.values if isinstance(snapshot.values, dict) else {}
        if vals.get("build_status") == "failed" and (vals.get("developer_retry_count") or 0) >= 3:
            detail = (vals.get("build_error_log") or "").strip()
            print(f"❌ [Orchestrator] Task {task_id}: 빌드 자가복구 3회 소진 - 실패로 종결(FAILED).")
            try:
                if not (task_id.startswith("PLANNING") and len(task_id.split("_")) == 2):
                    WBSManager(workspace_root=workspace_root).update_task_status(task_id, "FAILED")
            except Exception as e:
                print(f"⚠️ [Orchestrator] WBS FAILED 마킹 실패: {e}")
            await factory_broadcaster.broadcast("SPRINT_FAILED", {
                "task_id": task_id, "project_id": pid,
                "error": "빌드 3회 연속 실패(자가복구 소진)", "detail": detail[:2000],
            })
            return
            
        try:
            if not (task_id.startswith("PLANNING") and len(task_id.split("_")) == 2):
                WBSManager(workspace_root=workspace_root).update_task_status(task_id, "DONE")
        except Exception as e:
            print(f"⚠️ [Orchestrator] WBS DONE 마킹 실패: {e}")
            
        await factory_broadcaster.broadcast("SPRINT_COMPLETED", {"task_id": task_id, "project_id": pid})

    async def is_hotl_pending(self, task_id: str, project_id: str) -> bool:
        """해당 태스크 스레드가 HOTL 중단점에서 '대기 중'인지 확인 (SSE 유실 복구용).
        ⚠️ snapshot.next 는 실행 중에도(다음 노드 예정) 차 있어 그것만으로는 오탐이 난다.
        → 스프린트 asyncio 태스크가 '아직 실행 중'이면 HOTL 대기가 아니다(오탐 방지).
        태스크가 끝났는데(또는 재시작으로 없는데) next 가 남아 있으면 = interrupt 에서 멈춘 진짜 HOTL."""
        try:
            langgraph_engine = await get_runtime_app()
            skey = _skey(project_id, task_id)
            config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
            snapshot = await langgraph_engine.aget_state(config)
            if not (getattr(snapshot, "values", None) and getattr(snapshot, "next", None)):
                return False  # 다음 노드가 없으면 완료(END) - HOTL 아님
            running = self.active_tasks.get(skey)
            if running is not None and not running.done():
                return False  # 아직 스트리밍 중 = 가동 중이지 HOTL 대기 아님(오탐 차단)
            return True
        except Exception:
            return False

    async def _run_sprint_loop(self, config: dict, state_dict: dict, task_id: str, workspace_root: str):
        pid = _pid(workspace_root)
        # T2-b: 이 프로젝트의 워크플로우 템플릿 그래프로 실행(스킬/토폴로지/HOTL 게이트가 템플릿별)
        tid = (state_dict or {}).get("template_id", "default")
        langgraph_engine = await get_runtime_app(tid)
        try:
            async for event in langgraph_engine.astream(state_dict, config=config):
                for node_name, state_data in event.items():
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    await self._save_latest_state(full_state, workspace_root)

                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data, "project_id": pid})

            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Sprint Loop Cancelled (Paused): {task_id}")
        except QuotaExhaustedException as e:
            print(f"⏸️ [Orchestrator] 쿼터 소진으로 인해 태스크 보류됨: {task_id}")
            await langgraph_engine.aupdate_state(config, {"factory_mode": "SUSPENDED_QUOTA"})
            snapshot = await langgraph_engine.aget_state(config)
            await self._save_latest_state(snapshot.values, workspace_root)
            await factory_broadcaster.broadcast("QUOTA_EXHAUSTED", {"task_id": task_id, "project_id": pid})
        except Exception as e:
            # 침묵 금지: 실패 이벤트를 브로드캐스트해야 UI 가 '영원히 가동 중' 상태에 갇히지 않는다
            print(f" [Orchestrator] Sprint Loop Error: {e}")
            await factory_broadcaster.broadcast("SPRINT_FAILED", {"task_id": task_id, "project_id": pid, "error": str(e)})

    async def resume_hotl(self, task_id: str, feedback: Optional[str], project_id: str) -> bool:
        # 이중 재개 차단: 실행 중인 스트림 위에 aupdate_state/astream 을 겹치면 체크포인트가 오염된다
        _existing = self.active_tasks.get(_skey(project_id, task_id))
        if _existing and not _existing.done():
            print(f"⚠️ [Orchestrator] Task {task_id} (project={project_id}) 는 이미 실행 중 - 중복 재개 요청 무시.")
            return False
        langgraph_engine = await get_runtime_app()
        config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
        snapshot = await langgraph_engine.aget_state(config)
        if not snapshot.values:
            return False
            
        current_state = snapshot.values
        workspace_root = current_state.get("workspace_root", "./workspace") if isinstance(current_state, dict) else current_state.workspace_root
        # T2-b: 재개도 이 프로젝트의 템플릿 그래프로(초기 스프린트와 동일 토폴로지여야 체크포인트 정합)
        tid = (current_state.get("template_id", "default") if isinstance(current_state, dict)
               else getattr(current_state, "template_id", "default"))
        langgraph_engine = await get_runtime_app(tid)

        try:
            if feedback:
                if isinstance(current_state, dict):
                    queue = current_state.get("human_feedback_queue", [])
                else:
                    queue = getattr(current_state, "human_feedback_queue", [])

                queue.append({"task_id": task_id, "feedback": feedback, "status": "pending", "priority": 1})
                await langgraph_engine.aupdate_state(config, {"human_feedback_queue": queue, "needs_revision": True})
                
                # 피드백 내용 학습 기록
                persona_learner.record_interaction("hotl_feedback", feedback, project_id)
            else:
                await langgraph_engine.aupdate_state(config, {"needs_revision": False})
        except Exception:
            return False

        skey = _skey(_pid(workspace_root), task_id)
        task = asyncio.create_task(self._resume_stream(config, task_id, workspace_root, tid))
        self.active_tasks[skey] = task
        self.task_projects[skey] = _pid(workspace_root)
        task.add_done_callback(lambda t, k=skey: (self.active_tasks.pop(k, None), self.task_projects.pop(k, None)))
        return True

    async def _resume_stream(self, config: dict, task_id: str, workspace_root: str, template_id: str = "default"):
        pid = _pid(workspace_root)
        langgraph_engine = await get_runtime_app(template_id)
        try:
            async for event in langgraph_engine.astream(None, config=config):
                for node_name, state_data in event.items():
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    await self._save_latest_state(full_state, workspace_root)

                    await factory_broadcaster.broadcast("NODE_COMPLETED", {"node": node_name, "state": state_data, "project_id": pid})

            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Resume Stream Cancelled (Paused): {task_id}")
        except QuotaExhaustedException as e:
            print(f"⏸️ [Orchestrator] 쿼터 소진으로 인해 태스크 보류됨: {task_id}")
            await langgraph_engine.aupdate_state(config, {"factory_mode": "SUSPENDED_QUOTA"})
            snapshot = await langgraph_engine.aget_state(config)
            await self._save_latest_state(snapshot.values, workspace_root)
            await factory_broadcaster.broadcast("QUOTA_EXHAUSTED", {"task_id": task_id, "project_id": pid})
        except Exception as e:
            print(f" [Orchestrator] Resume Stream Error: {e}")
            await factory_broadcaster.broadcast("SPRINT_FAILED", {"task_id": task_id, "project_id": pid, "error": str(e)})

orchestrator = AsyncFactoryOrchestrator()