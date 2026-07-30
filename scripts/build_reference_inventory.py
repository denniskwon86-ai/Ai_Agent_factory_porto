"""docs/reference 원본 자산 등록부를 생성한다. LLM 호출·RAG 색인은 수행하지 않는다.

실행: python scripts/build_reference_inventory.py
"""
import sys
from pathlib import Path

# `python scripts/...py` 직접 실행 시에도 저장소 루트를 import 경로에 둔다.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.reference_registry import build_registry


if __name__ == "__main__":
    registry = build_registry()
    summary = registry["summary"]
    print(
        "[ReferenceRegistry] "
        f"총 {summary['total']}건 / 추출 가능 {summary['supported']}건 / "
        f"변환 필요 {summary['conversion_required']}건 / 검토 대기 {summary['pending_review']}건"
    )
