"""api/routes/factory_control.py — stale 페이로드 누적 필드 복원 검증.
새로고침/재연결로 클라이언트 state가 비어도 디스크 진실원본에서 '빈 필드만' 복원하고,
클라이언트가 채운 값(이번 태스크 의도)은 절대 덮어쓰지 않아야 한다."""
import json
from api.routes.factory_control import _restore_accumulated_from_disk


def _write_disk(tmp_path, data):
    (tmp_path / "latest_state.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_empty_field_restored_from_disk(tmp_path):
    _write_disk(tmp_path, {"rfp_summary": "디스크 RFP", "file_index": {"a.tsx": {"path": "a.tsx"}}})
    payload = {"rfp_summary": "", "file_index": {}}
    out = _restore_accumulated_from_disk(payload, str(tmp_path))
    assert out["rfp_summary"] == "디스크 RFP"
    assert out["file_index"] == {"a.tsx": {"path": "a.tsx"}}


def test_nonempty_payload_not_overridden(tmp_path):
    _write_disk(tmp_path, {"rfp_summary": "디스크 RFP(구버전)"})
    payload = {"rfp_summary": "클라이언트 최신 RFP"}
    out = _restore_accumulated_from_disk(payload, str(tmp_path))
    assert out["rfp_summary"] == "클라이언트 최신 RFP"  # 클라이언트 값 보존


def test_no_disk_state_keeps_payload(tmp_path):
    payload = {"rfp_summary": ""}
    out = _restore_accumulated_from_disk(payload, str(tmp_path))
    assert out == {"rfp_summary": ""}


def test_task_intent_fields_untouched(tmp_path):
    # factory_mode/current_required_agents 등 누적 목록 밖 필드는 디스크가 있어도 건드리지 않음
    _write_disk(tmp_path, {"factory_mode": "PLANNING", "current_required_agents": ["Old"]})
    payload = {"factory_mode": "EXECUTION", "current_required_agents": []}
    out = _restore_accumulated_from_disk(payload, str(tmp_path))
    assert out["factory_mode"] == "EXECUTION"
    assert out["current_required_agents"] == []  # 누적 필드 아님 → 복원 대상 아님
