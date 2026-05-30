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
        """내부 메서드: JSON 데이터를 Pandas로 읽어 Excel로 변환 및 백분율 서식 적용"""
        tasks = wbs_data.get("tasks", [])
        if not tasks:
            return

        # 진척률 파이썬 내부 계산 (Lazy Evaluation 방어)
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.get("status") == "DONE")
        progress_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0

        # DataFrame 변환
        df = pd.DataFrame(tasks)
        
        # 1차 쓰기 (Pandas Engine)
        df.to_excel(self.excel_path, index=False, sheet_name="WBS_Master")

        # 2차 쓰기 (Openpyxl을 이용한 메타데이터 및 서식 주입)
        wb = load_workbook(self.excel_path)
        ws = wb["WBS_Master"]

        # 상단에 3행을 삽입하여 요약 정보 배치
        ws.insert_rows(1, 3)
        ws["A1"] = f"프로젝트명: {wbs_data.get('project_name', 'Unknown')}"
        ws["A2"] = "전체 진척률:"
        
        # 엑셀 수식이 아닌 계산된 실수(Float)를 직접 주입
        progress_cell = ws["B2"]
        progress_cell.value = progress_rate
        # 엑셀 열기 전에도 완벽하게 %로 보이도록 서식만 적용
        progress_cell.number_format = '0.00%' 

        wb.save(self.excel_path)