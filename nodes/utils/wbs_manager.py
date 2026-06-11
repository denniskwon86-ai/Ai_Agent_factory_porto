# nodes/utils/wbs_manager.py
import json
import os
from filelock import FileLock, Timeout

class WBSManager:
    """WBS 마스터 플랜 JSON 파일의 상태를 원자적으로 읽고 쓰는 유틸리티"""
    
    def __init__(self, workspace_root: str):
        if not workspace_root:
            raise ValueError("workspace_root가 반드시 전달되어야 합니다.")
        self.workspace_root = workspace_root
        self.json_path = os.path.join(self.workspace_root, "00_wbs_master_plan.json")
        self.lock_path = os.path.join(self.workspace_root, ".wbs.lock")

    def _read_wbs(self):
        if not os.path.exists(self.json_path):
            return None
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"🚨 WBS 읽기 에러: {e}")
            return None

    def _write_wbs(self, data):
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_raw_wbs(self, raw_json_str: str):
        """Master PMO가 최초 생성한 JSON 문자열을 락 기반으로 안전하게 저장합니다."""
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        try:
            with FileLock(self.lock_path, timeout=10.0):
                with open(self.json_path, "w", encoding="utf-8") as f:
                    f.write(raw_json_str)
        except Timeout:
            print("🚨 WBS 파일 락 획득 타임아웃 (save_raw_wbs)")

    def checkout_task(self, task_id: str):
        """스프린트 시작 시 태스크를 진행 중(IN_PROGRESS) 상태로 마킹합니다."""
        try:
            with FileLock(self.lock_path, timeout=10.0):
                data = self._read_wbs()
                if not data:
                    return
                for task in data.get('tasks', []):
                    if task.get('task_id') == task_id:
                        task['status'] = 'IN_PROGRESS'
                self._write_wbs(data)
        except Timeout:
            print(f"🚨 WBS 파일 락 획득 타임아웃 (checkout_task: {task_id})")

    def complete_task(self, task_id: str):
        """스프린트 종료 시 태스크를 완료(DONE) 상태로 마킹합니다."""
        try:
            with FileLock(self.lock_path, timeout=10.0):
                data = self._read_wbs()
                if not data:
                    return
                for task in data.get('tasks', []):
                    if task.get('task_id') == task_id:
                        task['status'] = 'DONE'
                self._write_wbs(data)
        except Timeout:
            print(f"🚨 WBS 파일 락 획득 타임아웃 (complete_task: {task_id})")

    def add_revision_task(self, feedback: str) -> str:
        """PM의 피드백을 애자일 백로그(새로운 태스크)로 WBS 최하단에 주입합니다."""
        try:
            with FileLock(self.lock_path, timeout=10.0):
                data = self._read_wbs()
                if not data:
                    return ""
                
                tasks = data.get('tasks', [])
                rev_count = sum(1 for t in tasks if str(t.get('task_id', '')).startswith('REV-'))
                new_task_id = f"REV-{(rev_count + 1):03d}"
                
                new_task = {
                    "task_id": new_task_id,
                    "title": f"UI/UX 및 기능 피드백 반영 (Revision {rev_count + 1})",
                    "goal": feedback,
                    "status": "TODO"
                }
                
                tasks.append(new_task)
                self._write_wbs(data)
                return new_task_id
        except Timeout:
            print("🚨 WBS 파일 락 획득 타임아웃 (add_revision_task)")
            return ""