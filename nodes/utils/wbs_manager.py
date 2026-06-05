import json
import os

class WBSManager:
    """WBS 마스터 플랜 JSON 파일의 상태를 원자적으로 읽고 쓰는 유틸리티"""
    
    def __init__(self, json_path="workspace/00_wbs_master_plan.json"):
        self.json_path = json_path

    def _read_wbs(self):
        if not os.path.exists(self.json_path):
            return None
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _write_wbs(self, data):
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def checkout_task(self, task_id: str):
        """스프린트 시작 시 태스크를 진행 중(IN_PROGRESS) 상태로 마킹합니다."""
        data = self._read_wbs()
        if not data:
            return
        for task in data.get('tasks', []):
            if task.get('task_id') == task_id:
                task['status'] = 'IN_PROGRESS'
        self._write_wbs(data)

    def complete_task(self, task_id: str):
        """스프린트 종료 시 태스크를 완료(DONE) 상태로 마킹합니다."""
        data = self._read_wbs()
        if not data:
            return
        for task in data.get('tasks', []):
            if task.get('task_id') == task_id:
                task['status'] = 'DONE'
        self._write_wbs(data)