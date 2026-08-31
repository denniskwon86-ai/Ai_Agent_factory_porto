import asyncio
import os
import shutil
import json
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from typing import Optional, Dict, Any

from core.agent_graph import get_runtime_app
from core.broadcaster import factory_broadcaster

def _node_completed_payload(project_id: str, task_id: str, node_name: str,
                            state_data, full_state) -> dict:
    """★★★ [G1-C1.1] `NODE_COMPLETED` 에서 **상태 전체를 빼낸다.**

    종전에는 `{"node": ..., "state": state_data, "project_id": ...}` 로 **노드 산출 상태를
    통째로** 실어 보냈다. 조직 격리가 걸린 뒤에도 문제가 남는다 —

      · 그 프로젝트를 볼 수 있는 **부서 안의 모든 열람자**에게 코드·산출물·피드백 원문이
        실시간으로 밀린다. 「목록을 볼 수 있다」와 「모든 중간 산출물을 실시간으로 받는다」는
        같은 권한이 아니다.
      · SSE 큐는 클라이언트당 500개다. 큰 상태를 매 노드마다 밀면 느린 클라이언트의 큐가
        금세 차서 **오래된 이벤트부터 버려진다** — 정작 필요한 완료 신호가 사라진다.

    그래서 «무엇이 바뀌었는가» 만 보내고, 상세는 화면이 `/state/latest` 로 가져간다.
    그 경로에는 **권한 검사가 붙어 있다** — 이벤트에 실어 보내면 그 검사를 건너뛴다.

    ⚠️ `state_version` 은 화면이 **중복 조회를 걸러내는** 데 쓴다. 없으면 노드가 끝날 때마다
      전체 상태를 다시 받아 오히려 느려진다."""
    changed = []
    try:
        if isinstance(state_data, dict):
            changed = sorted(str(k) for k in state_data.keys())
    except Exception:
        changed = []
    version = ""
    try:
        import hashlib
        import json as _json
        blob = _json.dumps(full_state, ensure_ascii=False, sort_keys=True, default=str)
        version = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    except Exception:
        pass                     # 판본을 못 만들어도 완료 신호 자체는 보내야 한다
    return {
        "project_id": project_id,
        "task_id": task_id,
        "node": node_name,
        "status": "completed",
        "changed_fields": changed,
        "state_version": version,
    }

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
        # ── ★★★ 새 가동은 **직전 판정을 물려받지 않는다** ────────────────────
        #
        # ⚠️⚠️ [2026-08-26 실측] 이것이 「생성 실패」가 영영 안 풀리던 이유다.
        #
        #   `terminal_status` 는 체크포인트(thread_id = project__task)에 남는다. 그래서
        #   한 번 종결로 끝난 태스크를 **다시 가동하면**, 라우터가 첫 갈림길에서
        #   `_terminated(state)` 를 보고 곧바로 `TerminalHandler` 로 보낸다 —
        #   노드는 하나도 돌지 않고 **직전과 똑같은 사유로** 다시 실패한다.
        #   실측: 계약 결함을 고친 뒤에도 TASK-01 이 옛 사유 그대로 3회 연속 실패했고,
        #   나는 그것을 「아직 안 고쳐졌다」로 두 번 잘못 짚었다.
        #
        #   화면의 「재시도」도 같은 구멍이다(`ControlPanel.handleRetryFailedTask` 가
        #   `...state` 를 그대로 실어 보낸다). 그래서 **클라이언트가 아니라 여기서** 지운다 —
        #   재시도 경로가 몇 개든 서버를 지나므로 한 곳에서 막힌다.
        #
        # ★ 지우는 것은 **판정**뿐이다. `build_error_log` 같은 **근거는 남긴다** —
        #   자가복구가 직전 실패 원인을 프롬프트에 실어야 하기 때문이다([자가복구 P1]).
        #   판정은 매번 새로 내려야 하고, 근거는 물려받아야 한다.
        if isinstance(project_state_payload, dict):
            project_state_payload["terminal_status"] = ""
            project_state_payload["terminal_reason"] = ""

        if task_id.startswith("PLANNING") and len(task_id.split("_")) == 2:
            if os.path.exists(workspace_root):
                #  [Phase 3] 파괴적 삭제(rmtree) 제거 및 스마트 아카이빙 적용
                def _archive():
                    archive_dir = os.path.join(workspace_root, ".archive", datetime.now().strftime("%Y%m%d_%H%M%S"))
                    os.makedirs(archive_dir, exist_ok=True)
                    for item in os.listdir(workspace_root):
                        # .git/.archive 와 project_meta.json(템플릿 바인딩의 권위 원본, 생성 시 1회 기록)은
                        # 절대 이동 금지 - 아카이브되면 이후 모든 태스크가 'default' 템플릿으로 강등된다
                        #
                        # ★★ [2026-08-07 · P3-2 실측] `config_snapshot.json` 도 여기 들어간다.
                        #   그것은 «무엇이 실제로 돌았는가» 의 기록이고 **산출물이 아니다.**
                        #   빼 두지 않으면 기록이 그것을 만든 실행에 의해 아카이브로 쓸려 가고,
                        #   그 순간 프로젝트에는 기록이 없는 것으로 보인다 — 살아 있는 서버에서
                        #   실제로 그렇게 됐다(`.archive/<시각>/config_snapshot.json`).
                        #   ⚠️ 이력이 목적이므로 **누적돼야** 한다. 기획을 다시 돌릴 때마다
                        #     비워지면 「3주 전 산출물은 무엇으로 만들었나」에 답할 수 없다.
                        if item in [".git", ".archive", "project_meta.json",
                                    "config_snapshot.json"]:
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
        _is_planning = task_id.startswith("PLANNING") and len(task_id.split("_")) == 2

        # ══════════════════════════════════════════════════════════════════════
        # ★ [2026-07-27] END 는 성공이 아니다 — 업무 종료 상태로 판정한다
        # ══════════════════════════════════════════════════════════════════════
        # ⚠️ 기존 결함: 빌드 3회 실패만 걸러내고 **그 외 모든 END 를 DONE** 으로 마킹했다.
        #   그래서 리뷰 왕복 상한 END, QA 반려 상한, 공급자 장애 종결이 전부 '완료'로 보였다.
        #   실측: E2E-01 이 `재작업 상한(8) 도달 - best-effort 수용` 뒤 DONE 이 됐다.
        #   `END` 는 "그래프가 더 진행할 노드가 없다"는 기술적 사실일 뿐이다.
        terminal = (vals.get("terminal_status") or "").strip()

        # 종료 상태가 비어 있는데 빌드가 실패로 끝났다면 = 자가복구 소진 (하위호환 경로)
        if not terminal and vals.get("build_status") == "failed" and (vals.get("developer_retry_count") or 0) >= 3:
            terminal = "FAILED_BUILD"

        if terminal and terminal != "COMPLETED":
            reason = (vals.get("terminal_reason") or "").strip()
            detail = reason or (vals.get("build_error_log") or "").strip()
            _suspended = terminal.startswith("SUSPENDED_")
            # 보류(SUSPENDED)는 '실패'가 아니라 '회복 후 재개 가능' — WBS 를 FAILED 로 태우지 않는다.
            wbs_status = "BLOCKED" if _suspended else "FAILED"
            print(f"❌ [Orchestrator] Task {task_id}: 종결 상태 {terminal} → WBS {wbs_status}. 사유: {detail[:200]}")
            try:
                if not _is_planning:
                    WBSManager(workspace_root=workspace_root).update_task_status(task_id, wbs_status)
            except Exception as e:
                print(f"⚠️ [Orchestrator] WBS {wbs_status} 마킹 실패: {e}")
            # UI 의 WBS 가 갱신되도록 WBS_UPDATED 도 함께 발행한다(기존엔 누락되어 화면이 안 바뀌었다).
            await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "project_id": pid, "status": wbs_status})
            await factory_broadcaster.broadcast("SPRINT_FAILED", {
                "task_id": task_id, "project_id": pid,
                "terminal_status": terminal,
                "error": detail[:300] or terminal,
                "detail": detail[:2000],
                "failure_bundle": (vals.get("failure_bundle_path") or ""),
                "resumable": _suspended,
            })
            return

        # ══════════════════════════════════════════════════════════════════
        # ★★★ [2026-08-25 실측] **계약 승인 대기를 «완료» 로 보고하지 않는다**
        # ══════════════════════════════════════════════════════════════════
        # `ContractReviewPending` 은 `END` 로 끝난다(승인은 전용 API 가 원장에 남긴다).
        # 그래서 `snapshot.next` 가 비고, `terminal_status` 도 비어 있다 —
        # 그 결과 **아래 DONE 경로로 떨어져 WBS 가 DONE, SPRINT_COMPLETED** 가 나갔다.
        #
        # ⚠️⚠️ 즉 사람이 계약을 승인해야 하는데 화면은 「완료」라고 말했다. 이 필드
        #   (`terminal_status`)를 만든 이유가 정확히 「END 는 성공이 아니다」인데,
        #   그 규칙이 이 갈래에서만 새고 있었다.
        # ★ 대기는 **실패가 아니다.** WBS 를 FAILED 로 태우지 않고 `BLOCKED` 로 두고,
        #   화면이 승인 자리로 갈 수 있게 별도 신호를 보낸다.
        if (vals.get("current_stage") or "") == "CONTRACT_REVIEW":
            req_id = (vals.get("contract_review_request_event_id") or "").strip()
            print(f"⏸️ [Orchestrator] Task {task_id}: 계약 승인 대기 — 완료로 보고하지 않습니다.")
            try:
                if not _is_planning:
                    WBSManager(workspace_root=workspace_root).update_task_status(task_id, "BLOCKED")
            except Exception as e:
                print(f"⚠️ [Orchestrator] WBS BLOCKED 마킹 실패: {e}")
            await factory_broadcaster.broadcast("WBS_UPDATED", {
                "task_id": task_id, "project_id": pid, "status": "BLOCKED"})
            await factory_broadcaster.broadcast("CONTRACT_REVIEW_PENDING", {
                "task_id": task_id, "project_id": pid,
                "request_event_id": req_id,
                "contract_fingerprint": (vals.get("app_runtime_contract_fingerprint") or ""),
                "summary": (vals.get("app_runtime_contract_summary") or ""),
            })
            return

        try:
            if not _is_planning:
                WBSManager(workspace_root=workspace_root).update_task_status(task_id, "DONE")
        except Exception as e:
            print(f"⚠️ [Orchestrator] WBS DONE 마킹 실패: {e}")

        await factory_broadcaster.broadcast("WBS_UPDATED", {"task_id": task_id, "project_id": pid, "status": "DONE"})
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
            
            # 쿼터 고갈로 인한 SUSPENDED_QUOTA 상태라면 HOTL 이 아님
            factory_mode = snapshot.values.get("factory_mode") if isinstance(snapshot.values, dict) else getattr(snapshot.values, "factory_mode", None)
            if factory_mode == "SUSPENDED_QUOTA":
                return False
            running = self.active_tasks.get(skey)
            if running is not None and not running.done():
                return False  # 아직 스트리밍 중 = 가동 중이지 HOTL 대기 아님(오탐 차단)
            return True
        except Exception:
            return False

    async def read_contract_state(self, task_id: str, project_id: str) -> Dict[str, Any]:
        """[I-4 4c-3] **서버가** 체크포인트에서 계약 상태를 파생한다.

        ★★★ 클라이언트가 보낸 지문·승인 상태를 믿지 않는다. 승인 요청 본문에는
          `request_event_id`·`decision`·`rationale` 만 담기고, 「지금 계약이 무엇인가」
          는 오직 여기서 나온다 — 그래야 「사람이 A 를 보고 B 를 승인하는」 경로가
          만들어지지 않는다.

        ⚠️ 없는 스레드·읽기 실패는 **빈 dict** 로 돌려준다. 여기서 추측한 기본값을
          채우면 그 추측이 곧 승인 근거가 된다."""
        try:
            engine = await get_runtime_app()
            snapshot = await engine.aget_state(
                {"configurable": {"thread_id": _thread(project_id, task_id)}})
            values = getattr(snapshot, "values", None)
            if not values:
                return {}
            get = (values.get if isinstance(values, dict)
                   else lambda k, d="": getattr(values, k, d))
            return {
                "app_runtime_contract_fingerprint": get("app_runtime_contract_fingerprint", ""),
                "approved_contract_fingerprint": get("approved_contract_fingerprint", ""),
                "app_runtime_contract_status": get("app_runtime_contract_status", ""),
                "contract_review_request_event_id": get("contract_review_request_event_id", ""),
                "runtime_contract_profile": get("runtime_contract_profile", ""),
            }
        except Exception as e:
            print(f"⚠️ [Orchestrator] 계약 상태 조회 실패({project_id}/{task_id}): {e}")
            return {}

    async def apply_contract_decision(self, task_id: str, project_id: str,
                                      updates: Dict[str, Any]) -> bool:
        """원장에 남은 결정을 **체크포인트 상태에 반영**한다.

        ⚠️ 이 반영이 실패해도 **결정 자체는 사라지지 않는다** — 원장이 SSOT 이고
          여기는 투영이다. 그래서 실패를 삼키지 않고 돌려주되, 호출부는 이미 기록된
          승인을 되돌리지 않는다(되돌릴 수도 없다. 원장은 추가만 된다)."""
        try:
            engine = await get_runtime_app()
            await engine.aupdate_state(
                {"configurable": {"thread_id": _thread(project_id, task_id)}}, updates)
            return True
        except Exception as e:
            print(f"⚠️ [Orchestrator] 계약 결정 상태 반영 실패({project_id}/{task_id}): {e}")
            return False

    async def _run_sprint_loop(self, config: dict, state_dict: dict, task_id: str, workspace_root: str):
        pid = _pid(workspace_root)
        # T2-b: 이 프로젝트의 워크플로우 템플릿 그래프로 실행(스킬/토폴로지/HOTL 게이트가 템플릿별)
        tid = (state_dict or {}).get("template_id", "default")
        expected_fp = (state_dict or {}).get("config_fingerprint", "")
        langgraph_engine = await get_runtime_app(tid, expected_fp)
        try:
            async for event in langgraph_engine.astream(state_dict, config=config):
                for node_name, state_data in event.items():
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    await self._save_latest_state(full_state, workspace_root)

                    await factory_broadcaster.broadcast(
                        "NODE_COMPLETED", _node_completed_payload(pid, task_id, node_name,
                                                                 state_data, full_state))

            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Sprint Loop Cancelled (Paused): {task_id}")
        except QuotaExhaustedException as e:
            await self._suspend_for_quota(langgraph_engine, config, task_id, workspace_root)
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
        expected_fp = (current_state.get("config_fingerprint", "") if isinstance(current_state, dict)
                       else getattr(current_state, "config_fingerprint", ""))
        langgraph_engine = await get_runtime_app(tid, expected_fp)

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

            # ★ [2026-07-29 / §10.3 `human_acceptance`] 사람의 수용 판정을 계측한다.
            #   HOTL 재개는 이 시스템에서 **사람이 산출물에 대해 내리는 유일한 명시적 판정**이다
            #   (피드백 있음 = 반려·수정요구 / 없음 = 그대로 승인). 이것을 남기지 않으면
            #   "게이트는 통과했는데 사람은 매번 고쳐 보냈다" 같은 실제 품질 신호가 사라진다.
            #   ⚠️ 판정이 **없는** 게이트를 승인으로 적지 않기 위해, 기록은 오직 여기서만 만든다.
            try:
                from core import quality_telemetry as _qt
                _qt.record_human_decision(
                    _qt.StateRef(current_state, workspace_root=workspace_root, task_id=task_id),
                    gate_name="HOTL", accepted=not bool(feedback), feedback=feedback or "")
            except Exception:
                pass
        except Exception:
            return False

        skey = _skey(_pid(workspace_root), task_id)
        task = asyncio.create_task(self._resume_stream(
            config, task_id, workspace_root, tid, expected_fp))
        self.active_tasks[skey] = task
        self.task_projects[skey] = _pid(workspace_root)
        task.add_done_callback(lambda t, k=skey: (self.active_tasks.pop(k, None), self.task_projects.pop(k, None)))
        return True

    async def _resume_stream(self, config: dict, task_id: str, workspace_root: str,
                             template_id: str = "default", expected_fingerprint: str = ""):
        pid = _pid(workspace_root)
        langgraph_engine = await get_runtime_app(template_id, expected_fingerprint)
        try:
            async for event in langgraph_engine.astream(None, config=config):
                for node_name, state_data in event.items():
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    await self._save_latest_state(full_state, workspace_root)

                    await factory_broadcaster.broadcast(
                        "NODE_COMPLETED", _node_completed_payload(pid, task_id, node_name,
                                                                 state_data, full_state))

            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            print(f"⏸️ [Orchestrator] Resume Stream Cancelled (Paused): {task_id}")
        except QuotaExhaustedException as e:
            await self._suspend_for_quota(langgraph_engine, config, task_id, workspace_root)
        except Exception as e:
            print(f" [Orchestrator] Resume Stream Error: {e}")
            await factory_broadcaster.broadcast("SPRINT_FAILED", {"task_id": task_id, "project_id": pid, "error": str(e)})

    async def _suspend_for_quota(self, langgraph_engine, config: dict, task_id: str, workspace_root: str):
        """쿼터 완전 고갈 시 스프린트를 SUSPENDED_QUOTA 로 동결한다.
        재개(resume_from_suspend) 시 정확 복구를 위해 SUSPEND '직전의 정상 모드'를 pre_suspend_mode 에
        보존한다. 이미 SUSPENDED_QUOTA 인 상태(재개 직후 재소진)에서는 원래 보존값을 덮지 않는다."""
        pid = _pid(workspace_root)
        print(f"⏸️ [Orchestrator] 쿼터 소진으로 인해 태스크 보류됨: {task_id}")
        try:
            snap = await langgraph_engine.aget_state(config)
            cur_vals = snap.values if isinstance(snap.values, dict) else {}
            prev_mode = cur_vals.get("factory_mode") or "EXECUTION"
            updates = {"factory_mode": "SUSPENDED_QUOTA"}
            if prev_mode != "SUSPENDED_QUOTA":
                updates["pre_suspend_mode"] = prev_mode  # 직전 정상 모드 보존
            await langgraph_engine.aupdate_state(config, updates)
            snapshot = await langgraph_engine.aget_state(config)
            await self._save_latest_state(snapshot.values, workspace_root)
        except Exception as e:
            print(f"⚠️ [Orchestrator] SUSPENDED_QUOTA 상태 기록 실패: {e}")
        await factory_broadcaster.broadcast("QUOTA_EXHAUSTED", {"task_id": task_id, "project_id": pid})

    async def resume_from_suspend(self, task_id: str, project_id: str) -> bool:
        """[R2] 쿼터 회복 후 SUSPENDED_QUOTA 로 동결된 스프린트를 마지막 체크포인트에서 재개한다.
        factory_mode 를 SUSPEND 직전 모드(pre_suspend_mode)로 복구한 뒤 astream(None) 으로 이어서
        실행하므로 '처음부터 재실행'이 아니라 중단 지점부터 이어진다. 쿼터가 아직 회복되지 않았다면
        재개 스트림이 다시 QuotaExhaustedException 을 만나 자연히 재동결된다(무한루프/오탐 없음)."""
        skey = _skey(project_id, task_id)
        existing = self.active_tasks.get(skey)
        if existing and not existing.done():
            print(f"⚠️ [Orchestrator] Task {task_id} (project={project_id}) 는 이미 실행 중 - 중복 재개 요청 무시.")
            return False
        langgraph_engine = await get_runtime_app()
        config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
        snapshot = await langgraph_engine.aget_state(config)
        if not snapshot.values:
            return False
        vals = snapshot.values if isinstance(snapshot.values, dict) else {}
        # SUSPENDED_QUOTA 상태가 아니면 쿼터 재개 대상이 아니다(오작동/중복 트리거 방지)
        if vals.get("factory_mode") != "SUSPENDED_QUOTA":
            print(f"⚠️ [Orchestrator] Task {task_id} 는 SUSPENDED_QUOTA 상태가 아님 - 쿼터 재개 무시.")
            return False
        workspace_root = vals.get("workspace_root", "./workspace")
        tid = vals.get("template_id", "default")
        expected_fp = vals.get("config_fingerprint", "")
        restored_mode = vals.get("pre_suspend_mode") or "EXECUTION"
        # T2-b: 재개도 이 프로젝트의 템플릿 그래프로(초기 스프린트와 동일 토폴로지여야 체크포인트 정합)
        langgraph_engine = await get_runtime_app(tid, expected_fp)
        try:
            # factory_mode 복구 + 보존값 초기화. 이 복구가 있어야 재개 후 HOTL 게이트 감지가 정상화된다.
            await langgraph_engine.aupdate_state(config, {"factory_mode": restored_mode, "pre_suspend_mode": ""})
            snapshot = await langgraph_engine.aget_state(config)
            await self._save_latest_state(snapshot.values, workspace_root)
        except Exception as e:
            print(f"⚠️ [Orchestrator] 쿼터 재개 모드 복구 실패: {e}")
            return False

        pid = _pid(workspace_root)
        skey = _skey(pid, task_id)
        task = asyncio.create_task(self._resume_stream(
            config, task_id, workspace_root, tid, expected_fp))
        self.active_tasks[skey] = task
        self.task_projects[skey] = pid
        task.add_done_callback(lambda t, k=skey: (self.active_tasks.pop(k, None), self.task_projects.pop(k, None)))
        print(f"▶️ [Orchestrator] 쿼터 회복 재개: {task_id} (project={pid}, mode={restored_mode})")
        return True

orchestrator = AsyncFactoryOrchestrator()
