import json
import os
import pandas as pd
from openpyxl import load_workbook
from filelock import FileLock, Timeout

class WBSManager:
    """
    투 트랙 PMO 아키텍처의 물리적 산출물을 전담하는 통합 유틸리티.
    JSON 읽기/쓰기, 동시성 제어(FileLock), Excel 내보내기를 단일 책임으로 관리합니다.
    """
    
    def __init__(self, json_path: str = "00_wbs_master_plan.json"):
        self.json_path = json_path
        self.excel_path = self.json_path.replace(".json", ".xlsx")
        self.lock_path = f"{self.json_path}.lock"
        # 대시보드(Streamlit)가 읽고 있을 때 팩토리가 덮어쓰지 않도록 5초간 대기
        self.lock = FileLock(self.lock_path, timeout=5)

    def checkout_task(self, task_id: str) -> bool:
        """QA 통과 시 호출되어 해당 태스크를 DONE으로 처리하고 엑셀을 갱신합니다."""
        if not os.path.exists(self.json_path):
            print(f"⚠️ [WBSManager] WBS 파일을 찾을 수 없습니다: {self.json_path}")
            return False

        try:
            with self.lock:
                # 1. JSON 로드
                with open(self.json_path, "r", encoding="utf-8") as f:
                    wbs_data = json.load(f)

                # 2. 상태 업데이트
                task_found = False
                for task in wbs_data.get("tasks", []):
                    if task["task_id"] == task_id:
                        task["status"] = "DONE"
                        task["completed_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                        task_found = True
                        break

                if not task_found:
                    return False

                # 3. JSON 덮어쓰기
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(wbs_data, f, indent=2, ensure_ascii=False)

                # 4. 엑셀 동기화 (원자적 처리)
                self._export_to_excel(wbs_data)
                
            return True

        except Timeout:
            print("⏳ [WBSManager] 파일 잠금 획득 실패 (대시보드가 사용 중일 수 있습니다).")
            return False
        except Exception as e:
            print(f"❌ [WBSManager] 체크아웃 중 치명적 오류 발생: {e}")
            return False

    def _export_to_excel(self, wbs_data: dict):
        """내부 메서드: JSON 데이터를 Pandas로 읽어 Excel로 단일 패스(Atomic) 변환"""
        tasks = wbs_data.get("tasks", [])
        if not tasks:
            return

        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.get("status") == "DONE")
        progress_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0

        df = pd.DataFrame(tasks)
        
        # [수정] ExcelWriter를 사용하여 단일 패스로 메모리 상에서 작업 후 한 번에 저장
        with pd.ExcelWriter(self.excel_path, engine='openpyxl') as writer:
            # 1. 먼저 빈 데이터프레임으로 시트를 생성하고 (1행부터 시작)
            df.to_excel(writer, index=False, sheet_name="WBS_Master", startrow=3)
            
            # 2. 생성된 워크북과 워크시트 객체에 접근
            wb = writer.book
            ws = writer.sheets["WBS_Master"]

            # 3. 상단 메타데이터 주입
            ws["A1"] = f"프로젝트명: {wbs_data.get('project_name', 'Unknown')}"
            ws["A2"] = "전체 진척률:"
            
            progress_cell = ws["B2"]
            progress_cell.value = progress_rate
            progress_cell.number_format = '0.00%' 
        # with 블록을 빠져나갈 때 자동으로 단 한 번의 원자적 save()가 호출됨.