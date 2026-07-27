# ==========================================
# 파일 삭제 계약 테스트 (2026-07-27)
#
# 고치는 결함: 파이프라인에 파일을 지울 수단이 없었다.
#   실측(test_a1_v9 E2E-04): Tech Lead 가 React→바닐라 JS 전환을 결정하고
#   `src/App.tsx` 등을 "삭제"하라고 명시했으나, 개발자는 생성/덮어쓰기만 가능했다.
#   두 아키텍처가 공존 → 렌더 검증이 App 루트를 확정 못 함 → 리뷰어 지적 →
#   Tech Lead 재지시 → 개발자 삭제 불가 → 8회 반복 → FAILED_REVIEW.
#   Tech Lead 의 THINKING 에 "삭제 지시가 있었음에도 여전히 존재합니다" 라고 적혀 있었다.
# ==========================================
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from nodes.code_builder import CodeBuilder
from nodes.execution import _extract_deleted_from_json


def test_extract_deleted_files():
    payload = json.dumps({"files": [], "deleted_files": ["src/App.tsx", "src/types.ts"]})
    assert _extract_deleted_from_json(payload) == ["src/App.tsx", "src/types.ts"]


def test_extract_returns_empty_when_absent():
    assert _extract_deleted_from_json(json.dumps({"files": []})) == []
    assert _extract_deleted_from_json("") == []
    assert _extract_deleted_from_json("not json at all") == []


def _seed(tmp_path):
    b = CodeBuilder(workspace_root=str(tmp_path))
    b.run({}, [
        {"file_path": "src/App.tsx", "code": "export default () => null;"},
        {"file_path": "keep.ts", "code": "export const k = 1;"},
    ])
    return b


def test_delete_removes_only_targets(tmp_path):
    b = _seed(tmp_path)
    removed = b.delete_files(["src/App.tsx"])
    assert removed == ["src/App.tsx"]
    assert not (tmp_path / "src" / "App.tsx").exists()
    assert (tmp_path / "keep.ts").exists(), "지정하지 않은 파일은 남아야 합니다"


def test_delete_blocks_path_escape(tmp_path):
    """`../` 로 워크스페이스 밖을 지우려는 시도는 거부되어야 한다."""
    b = _seed(tmp_path)
    outside = tmp_path.parent / "outside_should_survive.txt"
    outside.write_text("x", encoding="utf-8")
    removed = b.delete_files(["../outside_should_survive.txt", "../../etc/passwd"])
    assert removed == [], f"워크스페이스 밖 삭제가 허용되면 안 됩니다: {removed}"
    assert outside.exists()
    outside.unlink()


def test_delete_ignores_internal_dirs(tmp_path):
    """`.git` 등 내부 디렉터리는 건드리지 않는다."""
    b = _seed(tmp_path)
    gitdir = tmp_path / ".git"
    gitdir.mkdir(exist_ok=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    removed = b.delete_files([".git/HEAD"])
    assert removed == []
    assert (gitdir / "HEAD").exists()


def test_delete_missing_path_is_harmless(tmp_path):
    b = _seed(tmp_path)
    assert b.delete_files(["does/not/exist.ts"]) == []
