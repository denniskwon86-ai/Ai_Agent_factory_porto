import os
import json
from typing import Dict, Any, List
from filelock import FileLock

from core import wbs_artifact_kind as artifact_kind

class WBSManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.wbs_file_path = os.path.join(self.workspace_root, "00_wbs_master_plan.json")
        self._lock = FileLock(self.wbs_file_path + ".lock")
        os.makedirs(self.workspace_root, exist_ok=True)

    def initialize_wbs(self, project_name: str, tasks: list,
                       runtime_contract_profile: str = "") -> List[Dict[str, Any]]:
        """WBS 를 기록하고 **실제로 기록된 태스크 목록을 돌려준다.**

        ★ 여기가 LLM 이 만든 태스크가 처음 파일이 되는 자리다. 그래서 `artifact_kind`
          정규화와 `Tech_Lead` 강제를 여기서 한다 — [I-4 §15]. 뒤쪽 노드에서 하면 그
          노드를 타지 않는 경로가 곧 우회로가 된다.

        ⚠️⚠️ **반환값을 쓰지 않으면 정규화가 파일에만 남는다.** 호출부가 넘긴 원본
          리스트를 그대로 다시 읽으면 `Tech_Lead` 가 없는 명단이 실행 상태로 들어가고,
          최초 실행이 계약 없이 지나간다 — 저장본과 실행본이 갈리는 전형적인 자리다.
          그래서 `None` 이 아니라 **기록된 목록**을 돌려준다.

        ⚠️ `runtime_contract_profile` 이 `v1` 이 아니면 **아무것도 바꾸지 않는다.**
          기존 프로젝트에 소급 적용하지 않기 위해서다([I-4 §3])."""
        enforced = artifact_kind.profile_enforces_contract(runtime_contract_profile)
        tasks = artifact_kind.normalize_tasks(tasks) if enforced else list(tasks or [])
        for i, t in enumerate(tasks):
            if isinstance(t, dict) and not t.get("task_id"):
                t["task_id"] = f"WBS-{i+1:03d}"
        wbs_data = {
            "project_name": project_name,
            "version": "1.0",
            "status": "PLANNING",
            #: ★ 프로필을 **파일에 남긴다.** append 경로(`add_revision_task` 등)는
            #:   상태를 들고 있지 않으므로, 여기 없으면 그 경로가 프로필을 모른 채
            #:   제 판단으로 정규화하거나 건너뛰게 된다.
            artifact_kind.PROFILE_KEY: (artifact_kind.PROFILE_V1 if enforced
                                        else artifact_kind.PROFILE_NONE),
            "total_tasks": len(tasks),
            "tasks": tasks
        }
        with self._lock:
            with open(self.wbs_file_path, "w", encoding="utf-8") as f:
                json.dump(wbs_data, f, indent=4, ensure_ascii=False)
        return tasks

    def get_wbs(self) -> Dict[str, Any]:
        if not os.path.exists(self.wbs_file_path):
            return {"tasks": []}
        try:
            with self._lock:
                with open(self.wbs_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ WBS 파일 읽기 오류: {e}")
            return {"tasks": []}

    def checkout_task(self, task_id: str) -> None:
        self.update_task_status(task_id, "IN_PROGRESS")

    def complete_task(self, task_id: str) -> None:
        self.update_task_status(task_id, "DONE")

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._lock:
            wbs_data = self._read_unlocked()
            for task in wbs_data.get("tasks", []):
                if task.get("task_id") == task_id:
                    task["status"] = status
                    break
            self._write_unlocked(wbs_data)

    def add_revision_task(self, feedback: str, required_agents: List[str] = None) -> str:
        """사용자 피드백을 받아 WBS에 새로운 수정(Revision) 태스크를 추가합니다."""
        if required_agents is None:
            required_agents = ["Tech_Lead", "Backend", "Frontend"]

        with self._lock:
            wbs_data = self._read_unlocked()
            tasks = wbs_data.get("tasks", [])

            rev_count = sum(1 for t in tasks if t.get("task_id", "").startswith("TASK_REV_"))
            new_task_id = f"TASK_REV_{rev_count + 1:02d}"

            #: ★ 종류를 **명시**한다. 비워 두면 fail-closed 로 `APP` 에 떨어져 결과는
            #:   같지만, 감사 기록에는 「읽을 수 없었다」로 남는다 — 그러면 판독 실패
            #:   건수가 기획 프롬프트의 결함을 가리키는 신호로 못 쓰인다.
            #: 수정 태스크는 앱을 고친다 → 계약 대상이다. 데이터셋이 그대로라면
            #:   게이트가 지문 불변으로 자동 통과시킨다.
            new_task = self._apply_profile(wbs_data, {
                "task_id": new_task_id,
                "title": f"사용자 피드백 반영 (Revision #{rev_count + 1})",
                "goal": feedback,
                "status": "TODO",
                "required_agents": required_agents,
                artifact_kind.KIND_KEY: artifact_kind.APP,
            })
            tasks.append(new_task)
            wbs_data["tasks"] = tasks
            wbs_data["total_tasks"] = len(tasks)

            self._write_unlocked(wbs_data)

        return new_task_id

    def add_data_task(self, title: str, goal: str,
                      required_agents: List[str] = None) -> str:
        """데이터 준비·연계·검증 태스크를 WBS에 추가합니다 (명세서 §4.7 / M0 백로그 4).

        ⚠️ **기획(initialize_wbs) 이후에만 호출해야 합니다.** `initialize_wbs` 는 파일을 통째로
          다시 쓰므로, 기획 전에 넣은 태스크는 PMO 가 WBS 를 만드는 순간 사라집니다. 호출부가
          WBS 존재를 먼저 확인하도록 여기서는 파일이 없으면 예외를 올립니다 —
          조용히 만들어 두면 지워진 줄도 모릅니다.
        `add_revision_task` 와 같은 append 패턴을 씁니다(TASK_DATA_* 접두어로 구분)."""
        if not os.path.exists(self.wbs_file_path):
            raise FileNotFoundError("WBS가 아직 없습니다(기획 완료 후 추가하십시오).")
        if required_agents is None:
            # 데이터 준비는 코드 생성이 아니라 조사·정의·연계 작업이다.
            required_agents = ["Master_PM"]
        with self._lock:
            wbs_data = self._read_unlocked()
            tasks = wbs_data.get("tasks", [])
            n = sum(1 for t in tasks if str(t.get("task_id", "")).startswith("TASK_DATA_"))
            new_task_id = f"TASK_DATA_{n + 1:02d}"
            #: ★ 데이터 준비는 **실행 가능한 SW 릴리스를 만들지 않는다** — 조사·정의·
            #:   연계다. 그래서 `DOCUMENT`(계약 불필요)로 **명시**한다.
            #: ⚠️ 이 태스크가 만든 데이터를 쓰는 것은 앱이고, 그 앱 태스크가 계약을
            #:   진다. 여기에 계약을 또 걸면 같은 데이터셋을 두 번 승인하게 되고,
            #:   사람은 두 번째 게이트를 습관으로 통과시킨다.
            tasks.append(self._apply_profile(wbs_data, {
                "task_id": new_task_id,
                "title": title,
                "goal": goal,
                "status": "TODO",
                "required_agents": required_agents,
                artifact_kind.KIND_KEY: artifact_kind.DOCUMENT,
            }))
            wbs_data["tasks"] = tasks
            wbs_data["total_tasks"] = len(tasks)
            self._write_unlocked(wbs_data)
        return new_task_id

    @staticmethod
    def _apply_profile(wbs_data: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """append 경로의 태스크에 **WBS 파일이 기록해 둔 프로필**을 적용한다.

        ⚠️ 이 경로는 상태(`ProjectState`)를 들고 있지 않다. 그래서 프로필을 파일에서
          읽는다 — 여기서 제 판단으로 정규화하면, 프로필이 꺼진 기존 프로젝트에
          피드백 한 번 준 것만으로 새 절차가 소급 적용된다."""
        if artifact_kind.profile_enforces_contract(wbs_data.get(artifact_kind.PROFILE_KEY)):
            return artifact_kind.normalize_task(task)
        #: 프로필이 꺼져 있으면 계약 관련 키를 **남기지 않는다** — 남기면 나중에
        #: 「이 프로젝트는 계약을 선언했다」로 오독된다.
        return {k: v for k, v in task.items() if k != artifact_kind.KIND_KEY}

    def _read_unlocked(self) -> Dict[str, Any]:
        """FileLock을 이미 획득한 상태에서 호출. 내부 전용."""
        if not os.path.exists(self.wbs_file_path):
            return {"tasks": []}
        try:
            with open(self.wbs_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ WBS 내부 읽기 오류: {e}")
            return {"tasks": []}

    def _write_unlocked(self, wbs_data: Dict[str, Any]) -> None:
        """FileLock을 이미 획득한 상태에서 호출. 내부 전용."""
        with open(self.wbs_file_path, "w", encoding="utf-8") as f:
            json.dump(wbs_data, f, indent=4, ensure_ascii=False)
