"""core/async_orchestrator.py — 프로젝트 격리(thread_id 네임스페이스) 검증.
동일 task_id(E2E-01)가 서로 다른 프로젝트에서 같은 체크포인트를 공유하면 안 된다(상태 누수)."""
from core.async_orchestrator import _skey, _thread


def test_skey_namespaced_by_project():
    assert _skey("AAAA", "E2E-01") == "AAAA__E2E-01"
    # 동일 task_id 라도 프로젝트가 다르면 키가 달라야 함
    assert _skey("AAAA", "E2E-01") != _skey("TTT01", "E2E-01")


def test_thread_id_namespaced_by_project():
    assert _thread("AAAA", "E2E-01") == "sprint_AAAA__E2E-01"
    assert _thread("AAAA", "E2E-01") != _thread("TTT01", "E2E-01")


def test_same_project_same_task_is_stable():
    # 같은 프로젝트·태스크는 안정적으로 동일 키(재개·HOTL 조회가 일관되게 동작)
    assert _thread("AAAA", "E2E-01") == _thread("AAAA", "E2E-01")
