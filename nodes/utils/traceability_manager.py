import os
import json
from typing import Dict, Any, List
from filelock import FileLock

class TraceabilityManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.map_file_path = os.path.join(self.workspace_root, "traceability_map.json")
        self._lock = FileLock(self.map_file_path + ".lock")
        os.makedirs(self.workspace_root, exist_ok=True)
        self._init_if_not_exists()

    def _init_if_not_exists(self) -> None:
        if not os.path.exists(self.map_file_path):
            with self._lock:
                if not os.path.exists(self.map_file_path): # Double-check after acquiring lock
                    with open(self.map_file_path, "w", encoding="utf-8") as f:
                        json.dump({"mappings": []}, f, indent=4, ensure_ascii=False)

    def _read_unlocked(self) -> Dict[str, Any]:
        try:
            with open(self.map_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"mappings": []}

    def update_mapping(self, task_id: str, fr_ids: List[str], files: List[str]) -> None:
        """새로 생성/수정된 파일들을 해당 태스크의 요구사항(FR-ID)과 맵핑하여 저장합니다."""
        if not fr_ids and not files:
            return
            
        with self._lock:
            data = self._read_unlocked()
            mappings = data.get("mappings", [])
            
            # Remove existing mapping for this task if it exists (for rework/retries)
            mappings = [m for m in mappings if m.get("task_id") != task_id]
            
            mappings.append({
                "task_id": task_id,
                "fr_ids": list(set(fr_ids)),
                "files": list(set(files))
            })
            
            data["mappings"] = mappings
            
            with open(self.map_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    def get_mappings(self) -> List[Dict[str, Any]]:
        """저장된 모든 추적성 맵핑 데이터를 반환합니다."""
        with self._lock:
            data = self._read_unlocked()
            return data.get("mappings", [])
