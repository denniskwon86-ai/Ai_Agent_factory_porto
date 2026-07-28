import os
import json
from typing import Dict, Any, List
from filelock import FileLock

class WBSManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.wbs_file_path = os.path.join(self.workspace_root, "00_wbs_master_plan.json")
        self._lock = FileLock(self.wbs_file_path + ".lock")
        os.makedirs(self.workspace_root, exist_ok=True)

    def initialize_wbs(self, project_name: str, tasks: list) -> None:
        for i, t in enumerate(tasks):
            if not t.get("task_id"):
                t["task_id"] = f"WBS-{i+1:03d}"
        wbs_data = {
            "project_name": project_name,
            "version": "1.0",
            "status": "PLANNING",
            "total_tasks": len(tasks),
            "tasks": tasks
        }
        with self._lock:
            with open(self.wbs_file_path, "w", encoding="utf-8") as f:
                json.dump(wbs_data, f, indent=4, ensure_ascii=False)

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

            new_task = {
                "task_id": new_task_id,
                "title": f"사용자 피드백 반영 (Revision #{rev_count + 1})",
                "goal": feedback,
                "status": "TODO",
                "required_agents": required_agents
            }
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
            tasks.append({
                "task_id": new_task_id,
                "title": title,
                "goal": goal,
                "status": "TODO",
                "required_agents": required_agents,
            })
            wbs_data["tasks"] = tasks
            wbs_data["total_tasks"] = len(tasks)
            self._write_unlocked(wbs_data)
        return new_task_id

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
