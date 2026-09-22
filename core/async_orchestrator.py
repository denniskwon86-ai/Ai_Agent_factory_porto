import asyncio
import os
import shutil
import json
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from typing import Optional, Dict, Any

from core import atomic_write
from core.agent_graph import get_runtime_app
from core.broadcaster import factory_broadcaster
from core.studio_execution_guard import execution_command, finish_before_cancel

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
        #: ★ [W03.2] 마지막 상태 저장 실패. `_save_latest_state` 는 실패를 **삼키고 실행을
        #:   계속한다**(저장 실패로 스프린트 전체를 잃는 것이 더 나쁘다). 그러나 조용히
        #:   삼키면 아무도 모르므로 **여기에 남겨 사후에 물어볼 수 있게** 한다.
        #:   성공하면 지운다 — 남아 있다는 것은 「마지막 저장이 실패한 상태」라는 뜻이다.
        self.last_state_save_error: Optional[Dict[str, Any]] = None
        #: ★★ [2026-09-22] **프로젝트마다** 따로 남긴다. 위 단일 필드만 두면 A 가 실패한
        #:   뒤 B 가 성공하는 순간 A 의 실패가 지워진다 — 물어보면 「없다」고 답하게 된다.
        #:   단일 필드는 화면 호환을 위해 남기되, 판정은 이 표로 한다.
        self.state_save_failures: Dict[str, Dict[str, Any]] = {}
        #: 조건부 저장의 기준 판본(프로젝트별). **이 writer 가 마지막으로 본 값**이다.
        #: ⚠️ 충돌로 거절되면 지운다 — 다음 저장이 현재 판본을 다시 읽어 이어받는다.
        #:   낡은 기준을 그대로 들고 재시도하면 영원히 거절된다.
        self._state_baselines: Dict[str, str] = {}

    def _forget_task(self, key, task):
        """이전 실행의 완료 콜백이 같은 ID의 새 실행을 지우지 않는다."""
        if self.active_tasks.get(key) is task:
            self.active_tasks.pop(key, None)
            self.task_projects.pop(key, None)

    def _register_task(self, project_id, task_id, task):
        key = _skey(project_id, task_id)
        self.active_tasks[key] = task
        self.task_projects[key] = project_id
        task.add_done_callback(lambda done: self._forget_task(key, done))

    def _project_running(self, project_id):
        return any(not task.done() and (self.task_projects.get(key) == project_id
                   or key.startswith(project_id + "__")) for key, task in self.active_tasks.items())

    async def _save_latest_state(self, state_data: Any, workspace_root: str):
        # 전체 상태(생성 코드 포함 - 수 MB 가능)의 json 직렬화+쓰기는 동기 작업이라
        # 매 노드마다 이벤트 루프(SSE/전체 API)를 멈추게 하므로 스레드로 내린다
        def _write():
            #: ★★ [2026-09-22] `makedirs` 도 **링크 경계 안**에서 한다. 검사 밖에 있으면
            #:   그 자체가 우회로다 — 연결된 상위 아래에 디렉터리를 만들어 놓고 나서
            #:   「대상은 링크가 아니다」로 통과한다.
            from core.paths import PROJECTS_DIR
            atomic_write.ensure_directory(workspace_root, root=PROJECTS_DIR)
            state_path = os.path.join(workspace_root, "latest_state.json")
            data_to_save = jsonable_encoder(state_data)
            #: ★★★ **조건부 저장.** 기준은 「이 writer 가 마지막으로 본 판본」이다 —
            #:   쓰기 직전에 읽어 기준으로 삼으면 그건 조건이 아니라 형식이고, 늦게 온
            #:   쓰기가 여전히 이긴다. 다른 노드가 그 사이에 올렸으면 여기서 거절된다.
            #:
            #: ⚠️ 기준을 모를 때(프로세스 재시작 뒤 이어받기)는 **현재 판본을 한 번
            #:   받아들인다.** 그 한 번은 경쟁을 못 잡는다 — 재시작 직후 동시 쓰기는
            #:   여전히 뒤엣것이 이긴다. 그 한계를 숨기지 않고 적어 둔다.
            baseline = self._state_baselines.get(project_id)
            if baseline is None:
                baseline = atomic_write.digest_of(state_path)
            self._state_baselines[project_id] = atomic_write.replace_json_if_unchanged(
                state_path, data_to_save, expected_digest=baseline,
                root=PROJECTS_DIR, indent=2)
        project_id = _pid(workspace_root)
        try:
            await finish_before_cancel(asyncio.to_thread(_write))
            #: ★★ [2026-09-22 보완] **이 프로젝트 것만** 지운다.
            #:   ⚠️ 예전에는 `last_state_save_error = None` 이라 **A 가 실패한 뒤 B 가
            #:     성공하면 A 의 실패가 지워졌다.** 실패 하나를 남의 성공이 덮는 구조는
            #:     「관측을 붙였다」고 말할 수 없다 — 물어보면 없다고 답한다.
            self.state_save_failures.pop(project_id, None)
            self.last_state_save_error = None       # 성공했으니 지난 실패 표시를 지운다
            return {"saved": True, "project_id": project_id, "error": ""}
        except Exception as e:
            # ⚠️ **삼키는 것은 그대로 둔다.** 여기서 예외를 올리면 상태 저장 하나 때문에
            #   스프린트 실행 전체를 잃는다 — 그쪽이 더 나쁘다. 대신 «조용히» 삼키지 않는다:
            #   사후에 물어볼 수 있게 남기고(`last_state_save_error`), 화면에도 알린다.
            #   ★ 원자 쓰기를 붙여도 이 경로는 여전히 소실이 가능하다. Windows 가 교체를
            #     거절하면(probe 실측 41/180) 예외가 오고, 그것이 여기서 멈춘다.
            record = {
                "project_id": project_id,
                "at": datetime.now().isoformat(timespec="seconds"),
                "error": f"{type(e).__name__}: {e}",
                #: ★ 「낡은 판본으로 덮으려다 거절」과 「교체 자체가 실패」는 다르다.
                #:   앞쪽은 **다시 읽고 다시 만들어야** 하고, 뒤쪽은 재시도로 풀린다.
                "stale": type(e).__name__ == "StaleWriteError",
            }
            #: ⚠️ 충돌이면 기준을 버린다. 안 버리면 같은 낡은 기준으로 계속 거절된다.
            if record["stale"]:
                self._state_baselines.pop(project_id, None)
            self.state_save_failures[project_id] = record
            self.last_state_save_error = record
            print(f" 상태 백업 실패: {e}")
            try:
                await factory_broadcaster.broadcast(
                    "STATE_SAVE_FAILED", {"project_id": project_id,
                                          "error": type(e).__name__})
            except Exception:
                pass    # 알림이 실패해도 실행을 멈추지 않는다. 기록은 위에 이미 남았다.
            #: ★★ 실행은 계속하되 **결과를 돌려준다.** 호출자가 「계산은 됐지만 정본
            #:   저장은 안 됐다」를 구분해 소비할 수 있어야 한다 — 관측만 남기고 정상
            #:   반환하면 호출자는 저장이 된 줄 알고 다음으로 간다.
            return {"saved": False, "project_id": project_id,
                    "error": f"{type(e).__name__}: {e}", "stale": record["stale"]}

    @execution_command("workspace_root")
    async def start_sprint(self, task_id: str, project_state_payload: dict, workspace_root: str) -> bool:
        # 중복 확인은 요청 본문 변경·아카이브·WBS 쓰기보다 먼저 한다.
        pid = _pid(workspace_root)
        if self._project_running(pid):
            return False
        if task_id.startswith("PLANNING") and len(task_id.split("_")) == 2 and os.path.isdir(workspace_root):
            from core import studio_pause_state as pauses
            from core.enterprise_context.process_schema import ProcessError
            if await asyncio.to_thread(pauses.read, workspace_root, task_id):
                return False
            try:
                engine = await self._bound_engine(pid)
                prior = await engine.aget_state({"configurable": {"thread_id": _thread(pid, task_id)}})
            except Exception as exc:
                raise ProcessError("STUDIO_CHECKPOINT_UNAVAILABLE", "기존 기획 체크포인트를 확인하지 못했습니다.", 503) from exc
            if getattr(prior, "values", None):
                return False  # 기존 기획은 완료/실패 여부와 무관하게 새 기획으로 덮지 않는다.
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
                                    "config_snapshot.json", ".studio_setup.json",
                                    ".studio_pause_state.json", ".studio_pause_state.json.lock"]:
                            continue
                        src_path = os.path.join(workspace_root, item)
                        dst_path = os.path.join(archive_dir, item)
                        try:
                            shutil.move(src_path, dst_path)
                        except Exception as e:
                            print(f"⚠️ [Orchestrator] 아카이브 이동 실패 ({item}): {e}")
                # 디스크 이동은 동기 작업 - 이벤트 루프 동결 방지 위해 스레드로
                await finish_before_cancel(asyncio.to_thread(_archive))

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
        self._register_task(pid, task_id, task)
        return True

    async def cancel_project(self, project_id: str) -> int:
        """해당 프로젝트의 실행 중 스프린트를 모두 취소 (삭제/이탈 시 좀비 스프린트 방지)."""
        cancelled = 0
        pending = []
        for tid, t in list(self.active_tasks.items()):
            if self.task_projects.get(tid) == project_id:
                if t and not t.done():
                    t.cancel()
                    cancelled += 1
                    pending.append((tid, t))
                # 취소 전달만으로 실행을 등록부에서 지우지 않는다.
                if t.done():
                    self._forget_task(tid, t)
        if pending:
            try:
                await finish_before_cancel(asyncio.gather(*(t for _, t in pending), return_exceptions=True))
            finally:
                for tid, t in pending:
                    if t.done():
                        self._forget_task(tid, t)
        if cancelled:
            print(f" [Orchestrator] 프로젝트 '{project_id}'의 실행 중 스프린트 {cancelled}건을 취소했습니다.")
        return cancelled

    @execution_command("project_id")
    async def pause_sprint(self, task_id: str, project_id: str, reason: str = "") -> bool:
        """취소를 전달한 실행의 실제 종료와 정지 증거 저장까지 확인한다."""
        skey = _skey(project_id, task_id)
        task = self.active_tasks.get(skey)
        if not task or task.done():
            return False
        task.cancel()

        async def settle():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass  # 종료된 오류를 취소 성공 증거로 바꾸지 않는다.
            if (getattr(task, "_studio_stream_completed", False) or getattr(task, "_studio_at_hotl", False)
                    or not (task.cancelled() or getattr(task, "_studio_cancelled", False))):
                return False
            from core import studio_pause_state as pauses
            from core.enterprise_context.process_schema import ProcessError
            engine = await self._bound_engine(project_id)
            config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
            snapshot = await engine.aget_state(config)
            if reason:
                values = jsonable_encoder(snapshot.values)
                queue = list(values.get("human_feedback_queue", []))
                queue.append({"task_id": task_id, "feedback": f"[SUPERVISOR] {reason}", "status": "pending", "priority": 5})
                await engine.aupdate_state(config, {"human_feedback_queue": queue,
                    "needs_revision": True, "supervisor_feedback": reason})
                snapshot = await engine.aget_state(config)
            # 종료 확인과 재개 가능성은 다르다. 게이트/종결 상태에는 재개 증거를 만들지 않는다.
            try:
                root, evidence = self._pause_evidence(snapshot, engine, task_id, project_id)
            except ProcessError as exc:
                if exc.status_code != 409:
                    raise
            else:
                await asyncio.to_thread(pauses.record, root, evidence)
            await factory_broadcaster.broadcast("SPRINT_PAUSED", {"task_id": task_id, "project_id": project_id, "reason": reason})
            return True
        try:
            return await finish_before_cancel(settle())
        finally:
            if task.done():
                self._forget_task(skey, task)

    def _pause_evidence(self, snapshot, engine, task_id, project_id):
        """현재 서버 체크포인트의 동일성 및 전용 승인 경계를 검증한다."""
        from pathlib import Path
        from core.paths import workspace_path
        from core import studio_pause_state as pauses
        values = jsonable_encoder(getattr(snapshot, "values", None))
        config = getattr(snapshot, "config", None)
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        checkpoint_id = configurable.get("checkpoint_id")
        if not isinstance(values, dict) or not values:
            pauses.fail("CHECKPOINT_REQUIRED", "재개할 기존 체크포인트가 없습니다.")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            pauses.fail("UNAVAILABLE", "체크포인트 판본을 확인하지 못했습니다.", 503)
        root = values.get("workspace_root")
        if (not isinstance(root, str) or Path(root).resolve() != Path(workspace_path(project_id)).resolve()
                or values.get("current_sprint_task_id") != task_id
                or configurable.get("thread_id") != _thread(project_id, task_id)):
            pauses.fail("CONTEXT_CONFLICT", "체크포인트의 프로젝트 또는 작업 결속이 다릅니다.")
        try:
            meta_path = Path(root, "project_meta.json")
            if meta_path.is_symlink() or getattr(meta_path, "is_junction", lambda: False)():
                raise ValueError("연결된 프로젝트 메타")
            with meta_path.open("r", encoding="utf-8-sig") as stream:
                meta = json.load(stream, object_pairs_hook=pauses._pairs)
            if not isinstance(meta, dict):
                raise ValueError("프로젝트 메타 형식")
        except (OSError, ValueError, TypeError) as exc:
            from core.enterprise_context.process_schema import ProcessError
            raise ProcessError("STUDIO_PAUSE_UNAVAILABLE", "프로젝트의 실행 결속을 확인하지 못했습니다.", 503) from exc
        if values.get("template_id", "default") != (meta.get("template_id") or "default"):
            pauses.fail("CONTEXT_CONFLICT", "체크포인트와 프로젝트의 워크플로우가 다릅니다.")
        next_nodes = getattr(snapshot, "next", None)
        if not isinstance(next_nodes, (tuple, list)) or not next_nodes:
            pauses.fail("FINISHED", "다음 실행 노드가 없는 작업은 일반 재개할 수 없습니다.")
        if not all(isinstance(n, str) and n for n in next_nodes):
            pauses.fail("UNAVAILABLE", "체크포인트의 다음 노드가 손상되었습니다.", 503)
        if values.get("factory_mode") == "SUSPENDED_QUOTA":
            pauses.fail("QUOTA_REQUIRED", "쿼터 회복 전용 경로가 필요합니다.")
        if (values.get("current_stage") in {"CONTRACT_REVIEW", "CLARIFICATION"}
                or values.get("contract_review_request_event_id")
                or values.get("app_runtime_contract_status") in {"APPROVAL_PENDING", "REJECTED"}):
            pauses.fail("REVIEW_REQUIRED", "현재 사람 검토의 전용 결정 경로가 필요합니다.")
        if values.get("terminal_status") or values.get("current_stage") == "COMPLETED":
            pauses.fail("TERMINAL", "종결 판정을 지우는 일반 재개는 허용하지 않습니다.")
        tasks = getattr(snapshot, "tasks", ())
        if any(getattr(t, "interrupts", ()) for t in tasks):
            pauses.fail("HOTL_REQUIRED", "HOTL 응답 전용 경로가 필요합니다.")
        before = getattr(engine, "interrupt_before_nodes", None)
        after = getattr(engine, "interrupt_after_nodes", None)
        metadata = getattr(snapshot, "metadata", None)
        if before is None or after is None or not isinstance(metadata, dict):
            pauses.fail("UNAVAILABLE", "그래프의 사람 검토 경계를 확인하지 못했습니다.", 503)
        writes = metadata.get("writes") or {}
        if not isinstance(writes, dict):
            pauses.fail("UNAVAILABLE", "체크포인트 쓰기 근거를 확인하지 못했습니다.", 503)
        if (before == "*" or after == "*" or set(next_nodes).intersection(before)
                or set(writes).intersection(after)):
            pauses.fail("HOTL_REQUIRED", "HOTL 중단점은 일반 재개할 수 없습니다.")
        try:
            state_digest = pauses.digest(values)
        except (ValueError, TypeError) as exc:
            from core.enterprise_context.process_schema import ProcessError
            raise ProcessError("STUDIO_PAUSE_UNAVAILABLE", "체크포인트 상태 지문을 확인하지 못했습니다.", 503) from exc
        return root, {"project_id": project_id, "task_id": task_id,
            "thread_id": _thread(project_id, task_id), "checkpoint_id": checkpoint_id,
            "state_digest": state_digest, "next_nodes": list(next_nodes),
            "factory_mode": values.get("factory_mode"), "template_id": values.get("template_id", "default"),
            "config_fingerprint": values.get("config_fingerprint", "")}

    async def read_pause_state(self, task_id: str, project_id: str) -> dict:
        """명시적 정지의 조회 투영. 현재 권한과 재개 구성 검사는 API 책임이다."""
        from core import studio_pause_state as pauses
        from core.paths import workspace_path
        from core.enterprise_context.process_schema import ProcessError
        result = {"status": "NOT_PAUSED", "resumable": False, "reason_code": "STUDIO_PAUSE_EVIDENCE_REQUIRED"}
        row = await asyncio.to_thread(pauses.read, workspace_path(project_id), task_id)
        if not row or row["status"] != "PAUSED":
            return result
        result["status"] = "PAUSED"
        if self._project_running(project_id):
            return {**result, "reason_code": "STUDIO_COMMAND_BUSY"}
        engine = await self._bound_engine(project_id)
        snapshot = await engine.aget_state({"configurable": {"thread_id": _thread(project_id, task_id)}})
        try:
            _, evidence = self._pause_evidence(snapshot, engine, task_id, project_id)
        except ProcessError as exc:
            if exc.status_code != 409:
                raise
            return {**result, "reason_code": exc.reason_code}
        return {**result, "resumable": evidence == row["evidence"],
            "reason_code": "" if evidence == row["evidence"] else "STUDIO_PAUSE_CONFLICT"}

    async def _manual_stop_snapshot(self, snapshot, task_id, project_id):
        """정지·재개 접수된 판본을 HOTL 승인 대상으로 오인하지 않는다."""
        from pathlib import Path
        from core.paths import workspace_path
        from core import studio_pause_state as pauses
        root = workspace_path(project_id)
        values = jsonable_encoder(getattr(snapshot, "values", None))
        if (not isinstance(values, dict) or not isinstance(values.get("workspace_root"), str)
                or Path(values["workspace_root"]).resolve() != Path(root).resolve()):
            return False
        if not Path(root, pauses.FILENAME).exists():
            return False
        row = await asyncio.to_thread(pauses.read, root, task_id)
        if not row:
            return False
        config = getattr(snapshot, "config", None) or {}
        return (row["evidence"]["checkpoint_id"] == config.get("configurable", {}).get("checkpoint_id")
            and row["evidence"]["state_digest"] == pauses.digest(values))

    @staticmethod
    def _failed_retry(snapshot):
        """현재 다음 노드의 실제 오류만 실패 재시도의 근거로 삼는다."""
        return any(getattr(t, "name", None) in snapshot.next
            and isinstance(getattr(t, "error", None), str) and bool(t.error)
            and not getattr(t, "interrupts", ()) for t in getattr(snapshot, "tasks", ()))

    @execution_command("project_id")
    async def resume_existing(self, task_id: str, project_id: str) -> bool:
        """같은 체크포인트를 그대로 재개한다. 새 기획·WBS·판정 초기화는 없다."""
        from core import studio_pause_state as pauses
        from core.paths import workspace_path
        from core.enterprise_context.process_schema import ProcessError
        if self._project_running(project_id):
            return False
        row = await asyncio.to_thread(pauses.read, workspace_path(project_id), task_id)
        config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
        try:
            engine = await self._bound_engine(project_id)
            snapshot = await engine.aget_state(config)
            root, evidence = self._pause_evidence(snapshot, engine, task_id, project_id)
            # 오류 재시도는 현재 판본의 실제 노드 오류가 있을 때만 인정한다.
            failed = self._failed_retry(snapshot)
            paused = bool(row and row["status"] == "PAUSED" and row["evidence"] == evidence)
            if row and row["status"] == "PAUSED" and not paused:
                pauses.fail("CONFLICT", "정지한 체크포인트가 변경되었습니다.")
            if not paused and not failed:
                return False
            tid, expected_fp = evidence["template_id"], evidence["config_fingerprint"]
            engine = await get_runtime_app(tid, expected_fp)
            latest = await engine.aget_state(config)
            _, current = self._pause_evidence(latest, engine, task_id, project_id)
            if current != evidence:
                pauses.fail("CONFLICT", "실행 직전 체크포인트가 변경되었습니다.")
            if not paused and not self._failed_retry(latest):
                pauses.fail("CONFLICT", "현재 판본의 실패 재시도 근거가 바뀌었습니다.")
            if paused:
                await finish_before_cancel(asyncio.to_thread(pauses.consume, root, row))
                # 파일 잠금 대기 후에도 같은 판본이어야 한다. 소비 뒤 실패는 결과 불명으로 남긴다.
                try:
                    final = await engine.aget_state(config)
                    _, final_evidence = self._pause_evidence(final, engine, task_id, project_id)
                    if final_evidence != evidence:
                        raise ValueError("재개 접수 후 체크포인트 변경")
                except Exception as exc:
                    raise ProcessError("STUDIO_PAUSE_OUTCOME_UNKNOWN", "재개 접수 후 판본을 확인하지 못했습니다. 상태를 다시 조회하십시오.", 503) from exc
            task = asyncio.create_task(self._resume_stream(config, task_id, root, tid, expected_fp))
            self._register_task(project_id, task_id, task)
            return True
        except ProcessError:
            raise
        except Exception as exc:
            raise ProcessError("STUDIO_PAUSE_UNAVAILABLE", "기존 작업 재개 상태를 확인하지 못했습니다.", 503) from exc

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


    async def _bound_engine(self, project_id: str):
        """이 프로젝트의 **결속된 그래프**를 준다. 템플릿은 파일에서 읽는다.

        ## ⚠️⚠️ [2026-09-03 실가동] 「대기 중인데 대기 없음」의 원인

        조회·사전점검 경로가 `get_runtime_app()` 을 인자 없이 불러 **기본(SW) 그래프**를
        세우고 그 위에서 체크포인트를 읽었다. 그런데 상태 스키마(`ProjectState`)만
        공유될 뿐 **토폴로지는 다르다**:

            기본 그래프 노드(NODE_IMPL)              15개
            mfg_sim 에이전트 16개 중 거기 있는 것    0개  ← 교집합 0

        `snapshot.values` 는 채널에서 복원되므로 토폴로지와 무관하지만, **`snapshot.next`
        와 `aupdate_state` 는 노드를 안다는 전제 위에 선다.** 그래서 실제로는 `Sim_Designer`
        직전 인터럽트에 멈춰 있는데 `is_hotl_pending` 이 «다음 노드 없음» 으로 읽어
        화면·API 가 「대기 없음」이라고 답했다(2026-09-03 실가동 실측).

        ★ **닭이 먼저냐를 파일로 끊는다.** 종전에는 «템플릿을 알려면 상태를 읽어야 하고,
          상태를 읽으려면 그래프가 필요하다» 는 순환 때문에 기본 그래프를 먼저 세웠다.
          템플릿은 `project_meta.json` 이 권위 있는 출처이고 스프린트 시작이 이미 거기서
          읽어 주입한다(`_read_project_template`). 그래프 없이 읽으면 순환이 없다.

        ⚠️ **구성 지문은 넘기지 않는다.** 지문이 어긋나면 `get_runtime_app` 이 예외를 낸다 —
          실행을 막는 것은 옳지만, **조회까지 막으면 워크플로우가 개정된 순간 대기 중인
          스프린트가 화면에서 사라진다.** 지금 고치는 결함과 같은 증상이 된다.
        ⚠️ 읽기 실패는 기본 그래프로 떨어진다 — 조회가 죽는 것보다 낫고, 종전 동작이다.
        """
        tid = "default"
        try:
            import json

            from core.project_visibility import project_meta_path
            from core.paths import workspace_path
            with open(project_meta_path(workspace_path(project_id)), "r",
                      encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta, dict):
                tid = str(meta.get("template_id") or "default")
        except Exception as e:
            print(f"⚠️ [Orchestrator] 템플릿 결속 정보를 읽지 못해 기본 그래프로 조회합니다"
                  f"({project_id}): {e}")
        return await get_runtime_app(tid)

    async def is_hotl_pending(self, task_id: str, project_id: str) -> bool:
        """해당 태스크 스레드가 HOTL 중단점에서 '대기 중'인지 확인 (SSE 유실 복구용).
        ⚠️ snapshot.next 는 실행 중에도(다음 노드 예정) 차 있어 그것만으로는 오탐이 난다.
        → 스프린트 asyncio 태스크가 '아직 실행 중'이면 HOTL 대기가 아니다(오탐 방지).
        태스크가 끝났는데(또는 재시작으로 없는데) next 가 남아 있으면 = interrupt 에서 멈춘 진짜 HOTL."""
        try:
            #: ★ `next` 를 보므로 **반드시** 이 프로젝트의 그래프여야 한다.
            langgraph_engine = await self._bound_engine(project_id)
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
            if await self._manual_stop_snapshot(snapshot, task_id, project_id):
                return False
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
                "runtime_document_version": get("runtime_document_version", "1.0"),
                "process_context": get("process_context", {}),
                "approved_blueprint_revision_id": get("approved_blueprint_revision_id", ""),
                "approved_blueprint_digest": get("approved_blueprint_digest", ""),
                "bootstrap_operation_id": get("bootstrap_operation_id", ""),
            }
        except Exception as e:
            print(f"⚠️ [Orchestrator] 계약 상태 조회 실패({project_id}/{task_id}): {e}")
            return {}

    async def _reconcile_snapshot(self, task_id: str, project_id: str):
        """복구는 프로젝트에 결속된 그래프의 현재 task만 읽는다."""
        from core.enterprise_context.process_schema import ProcessError
        try:
            engine = await self._bound_engine(project_id)
            config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
            snapshot = await engine.aget_state(config)
            values = getattr(snapshot, "values", None)
            if not values:
                raise ProcessError("CONTRACT_CHECKPOINT_NOT_FOUND", "복구할 작업 상태가 없습니다.", 404)
            state = jsonable_encoder(values)
            if not isinstance(state, dict):
                raise ValueError("checkpoint shape")
            return engine, config, state
        except ProcessError:
            raise
        except Exception as exc:
            raise ProcessError("CONTRACT_CHECKPOINT_UNAVAILABLE", "복구할 작업 상태를 확인하지 못했습니다.", 503) from exc

    async def read_reconcile_state(self, task_id: str, project_id: str):
        return (await self._reconcile_snapshot(task_id, project_id))[2]

    async def apply_reconciled_contract_decision(self, task_id: str, project_id: str, *,
                                                fingerprint: str, request_event_id: str,
                                                expected_state: Dict[str, Any]) -> bool:
        """이미 승인된 사건의 투영만 고정 task에 재적용한다. 실행을 시작하지 않는다."""
        from core.enterprise_context.process_schema import ProcessError
        from core.studio_execution_guard import is_reconciling
        if not is_reconciling(self, project_id):
            raise ProcessError("CONTRACT_RECONCILE_REQUIRED", "복구 예약 없이 계약 상태를 반영할 수 없습니다.", 409)
        engine, config, state = await self._reconcile_snapshot(task_id, project_id)
        keys = ("app_runtime_contract_fingerprint", "contract_review_request_event_id",
                "runtime_document_version", "process_context", "approved_blueprint_revision_id",
                "approved_blueprint_digest", "bootstrap_operation_id")
        if (not fingerprint or state.get("app_runtime_contract_fingerprint") != fingerprint
                or state.get("contract_review_request_event_id", "") not in ("", request_event_id)
                or any(state.get(k) != expected_state.get(k) for k in keys)):
            raise ProcessError("CONTRACT_RECONCILE_CONFLICT", "검토한 계약 또는 작업 문맥이 바뀌었습니다.", 409)
        updates = {"approved_contract_fingerprint": fingerprint,
                   "app_runtime_contract_status": "APPROVED", "contract_review_request_event_id": ""}
        if all(state.get(k) == value for k, value in updates.items()):
            return True
        try:
            await engine.aupdate_state(config, updates)
            _, _, after = await self._reconcile_snapshot(task_id, project_id)
        except ProcessError:
            raise
        except Exception as exc:
            raise ProcessError("CONTRACT_CHECKPOINT_UNAVAILABLE", "승인 투영을 반영하지 못했습니다. 같은 사건으로 다시 확인하십시오.", 503) from exc
        return (after.get("app_runtime_contract_fingerprint") == fingerprint
                and all(after.get(k) == value for k, value in updates.items())
                and all(after.get(k) == state.get(k) for k in keys if k != "contract_review_request_event_id"))

    async def apply_contract_decision(self, task_id: str, project_id: str,
                                      updates: Dict[str, Any]) -> bool:
        """원장에 남은 결정을 **체크포인트 상태에 반영**한다.

        ⚠️ 이 반영이 실패해도 **결정 자체는 사라지지 않는다** — 원장이 SSOT 이고
          여기는 투영이다. 그래서 실패를 삼키지 않고 돌려주되, 호출부는 이미 기록된
          승인을 되돌리지 않는다(되돌릴 수도 없다. 원장은 추가만 된다)."""
        try:
            #: ★ 여기도 **쓴다** — 위 `_bound_engine` 의 이유가 그대로 적용된다.
            engine = await self._bound_engine(project_id)
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
                    asyncio.current_task()._studio_at_hotl = (node_name == "__interrupt__"
                        or node_name in getattr(langgraph_engine, "interrupt_after_nodes", ()))
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    saved = await self._save_latest_state(full_state, workspace_root)

                    #: ★★ [2026-09-22] **계산 성공과 정본 저장 성공을 구분해 보낸다.**
                    #:   예전에는 저장이 실패해도 `NODE_COMPLETED` 가 그대로 나갔다 —
                    #:   화면은 「이 노드 끝남」으로 읽고 새로고침하면 옛 상태가 온다.
                    #:   실행을 멈추지는 않되(저장 하나로 스프린트를 잃지 않는다)
                    #:   **완료 통지가 저장 성공을 뜻하지 않게** 한다.
                    payload = _node_completed_payload(pid, task_id, node_name,
                                                      state_data, full_state)
                    payload["state_saved"] = bool(saved.get("saved"))
                    if not saved.get("saved"):
                        payload["state_save_error"] = saved.get("error", "")
                        payload["state_save_stale"] = bool(saved.get("stale"))
                    await factory_broadcaster.broadcast("NODE_COMPLETED", payload)

            asyncio.current_task()._studio_stream_completed = True
            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            asyncio.current_task()._studio_cancelled = True
            print(f"⏸️ [Orchestrator] Sprint Loop Cancelled (Paused): {task_id}")
        except QuotaExhaustedException as e:
            await self._suspend_for_quota(langgraph_engine, config, task_id, workspace_root)
        except Exception as e:
            # 침묵 금지: 실패 이벤트를 브로드캐스트해야 UI 가 '영원히 가동 중' 상태에 갇히지 않는다
            print(f" [Orchestrator] Sprint Loop Error: {e}")
            await factory_broadcaster.broadcast("SPRINT_FAILED", {"task_id": task_id, "project_id": pid, "error": str(e)})

    async def read_hotl_context(self, task_id: str, project_id: str) -> dict:
        from core.studio_hotl_context import hotl_context
        active = self.active_tasks.get(_skey(project_id, task_id))
        running = bool(active and not active.done())
        try:
            engine = await self._bound_engine(project_id)
            snapshot = await engine.aget_state({"configurable": {"thread_id": _thread(project_id, task_id)}})
            if await self._manual_stop_snapshot(snapshot, task_id, project_id):
                return {"status": "NOT_PENDING", "pending": False, "available": False,
                    "reason_code": "STUDIO_EXPLICIT_PAUSE", "request_id": "",
                    "questions_digest": "", "decision_kind": ""}
        except Exception:
            snapshot = None
        return hotl_context(snapshot, project_id=project_id, task_id=task_id, running=running)

    @execution_command("project_id")
    async def resume_hotl(self, task_id: str, feedback: Optional[str], project_id: str, *,
                          expected_request_id: str = "", expected_questions_digest: str = "",
                          expected_studio_context: Optional[dict] = None) -> bool:
        # 이중 재개 차단: 실행 중인 스트림 위에 aupdate_state/astream 을 겹치면 체크포인트가 오염된다
        _existing = self.active_tasks.get(_skey(project_id, task_id))
        if _existing and not _existing.done():
            print(f"⚠️ [Orchestrator] Task {task_id} (project={project_id}) 는 이미 실행 중 - 중복 재개 요청 무시.")
            return False
        strict_round = bool(expected_studio_context or expected_request_id or expected_questions_digest)
        from core.enterprise_context.process_schema import ProcessError
        config = {"configurable": {"thread_id": _thread(project_id, task_id)}}
        try:
            langgraph_engine = await self._bound_engine(project_id) if strict_round else await get_runtime_app()
            snapshot = await langgraph_engine.aget_state(config)
        except Exception as exc:
            if strict_round:
                raise ProcessError("HOTL_CHECKPOINT_UNAVAILABLE", "대기 상태를 확인하지 못했습니다. 입력을 보존하고 다시 조회하십시오.", 503) from exc
            raise
        if not snapshot.values:
            return False
        if await self._manual_stop_snapshot(snapshot, task_id, project_id):
            return False
            
        current_state = snapshot.values
        workspace_root = current_state.get("workspace_root", "./workspace") if isinstance(current_state, dict) else current_state.workspace_root
        # T2-b: 재개도 이 프로젝트의 템플릿 그래프로(초기 스프린트와 동일 토폴로지여야 체크포인트 정합)
        tid = (current_state.get("template_id", "default") if isinstance(current_state, dict)
               else getattr(current_state, "template_id", "default"))
        expected_fp = (current_state.get("config_fingerprint", "") if isinstance(current_state, dict)
                       else getattr(current_state, "config_fingerprint", ""))
        version = current_state.get("runtime_document_version", "1.0") if isinstance(current_state, dict) else getattr(current_state, "runtime_document_version", "1.0")
        strict_round = strict_round or version == "2.0"
        try:
            langgraph_engine = await get_runtime_app(tid, expected_fp)
        except Exception as exc:
            if strict_round:
                raise ProcessError("HOTL_CHECKPOINT_UNAVAILABLE", "결속된 실행 구성을 확인하지 못했습니다. 입력을 보존하십시오.", 503) from exc
            raise

        # 쓰기 직전 영속 차수를 재조회한다. 같은 질문 내용이어도 새 체크포인트는 새 요청이다.
        from core.studio_hotl_context import hotl_context
        if strict_round:
            try:
                snapshot = await langgraph_engine.aget_state(config)
            except Exception as exc:
                raise ProcessError("HOTL_CHECKPOINT_UNAVAILABLE", "현재 질문 차수를 확인하지 못했습니다. 입력을 보존하고 다시 조회하십시오.", 503) from exc
            context = hotl_context(snapshot, project_id=project_id, task_id=task_id)
            if (not context["available"] or not expected_request_id or not expected_questions_digest
                    or context["request_id"] != expected_request_id
                    or context["questions_digest"] != expected_questions_digest):
                raise ProcessError("HOTL_ROUND_CONFLICT", "질문 또는 대기 차수가 바뀌었습니다. 입력을 보존하고 현재 요청을 다시 확인하십시오.", 409)
            current_state = snapshot.values
            from pathlib import Path
            from core.paths import workspace_path
            latest = jsonable_encoder(current_state)
            if (not isinstance(latest, dict)
                    or latest.get("workspace_root") != workspace_root
                    or latest.get("template_id", "default") != tid
                    or latest.get("config_fingerprint", "") != expected_fp
                    or not isinstance(workspace_root, str)
                    or Path(workspace_root).resolve() != Path(workspace_path(project_id)).resolve()):
                raise ProcessError("HOTL_CONTEXT_CONFLICT", "재개할 프로젝트 경로 또는 실행 구성이 바뀌었습니다.", 409)
            if expected_studio_context:
                fixed = ("runtime_document_version", "process_context", "approved_blueprint_revision_id",
                         "approved_blueprint_digest", "bootstrap_operation_id")
                if not isinstance(current_state, dict) or any(current_state.get(k) != expected_studio_context[k] for k in fixed):
                    raise ProcessError("HOTL_CONTEXT_CONFLICT", "질문의 승인 업무 문맥이 바뀌었습니다.", 409)

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
        except Exception as exc:
            if strict_round:
                raise ProcessError("HOTL_RESUME_OUTCOME_UNKNOWN", "답변 반영 결과를 확인하지 못했습니다. 입력을 보존하고 현재 상태를 조회하십시오. 자동으로 다시 제출하지 마십시오.", 503) from exc
            return False

        skey = _skey(_pid(workspace_root), task_id)
        task = asyncio.create_task(self._resume_stream(
            config, task_id, workspace_root, tid, expected_fp))
        self._register_task(_pid(workspace_root), task_id, task)
        return True

    async def _resume_stream(self, config: dict, task_id: str, workspace_root: str,
                             template_id: str = "default", expected_fingerprint: str = ""):
        pid = _pid(workspace_root)
        langgraph_engine = await get_runtime_app(template_id, expected_fingerprint)
        try:
            async for event in langgraph_engine.astream(None, config=config):
                for node_name, state_data in event.items():
                    asyncio.current_task()._studio_at_hotl = (node_name == "__interrupt__"
                        or node_name in getattr(langgraph_engine, "interrupt_after_nodes", ()))
                    snapshot = await langgraph_engine.aget_state(config)
                    full_state = snapshot.values
                    saved = await self._save_latest_state(full_state, workspace_root)

                    #: ★★ [2026-09-22] **계산 성공과 정본 저장 성공을 구분해 보낸다.**
                    #:   예전에는 저장이 실패해도 `NODE_COMPLETED` 가 그대로 나갔다 —
                    #:   화면은 「이 노드 끝남」으로 읽고 새로고침하면 옛 상태가 온다.
                    #:   실행을 멈추지는 않되(저장 하나로 스프린트를 잃지 않는다)
                    #:   **완료 통지가 저장 성공을 뜻하지 않게** 한다.
                    payload = _node_completed_payload(pid, task_id, node_name,
                                                      state_data, full_state)
                    payload["state_saved"] = bool(saved.get("saved"))
                    if not saved.get("saved"):
                        payload["state_save_error"] = saved.get("error", "")
                        payload["state_save_stale"] = bool(saved.get("stale"))
                    await factory_broadcaster.broadcast("NODE_COMPLETED", payload)

            asyncio.current_task()._studio_stream_completed = True
            await self._broadcast_stream_end(langgraph_engine, config, task_id, workspace_root)
        except asyncio.CancelledError:
            asyncio.current_task()._studio_cancelled = True
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

    @execution_command("project_id")
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
            from core.enterprise_context.process_schema import ProcessError
            raise ProcessError("STUDIO_QUOTA_RESUME_UNKNOWN",
                "쿼터 재개 상태 변경을 시도한 뒤 결과를 확인하지 못했습니다. 원요청을 조회하십시오.", 503) from e

        pid = _pid(workspace_root)
        skey = _skey(pid, task_id)
        task = asyncio.create_task(self._resume_stream(
            config, task_id, workspace_root, tid, expected_fp))
        self._register_task(pid, task_id, task)
        print(f"▶️ [Orchestrator] 쿼터 회복 재개: {task_id} (project={pid}, mode={restored_mode})")
        return True

orchestrator = AsyncFactoryOrchestrator()
