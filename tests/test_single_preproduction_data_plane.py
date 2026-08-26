"""현장 적용 전 제품 확인과 시연이 서로 다른 DB로 갈라지지 않게 한다."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_server_uses_the_canonical_data_root():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert '"data", "instance.json"' in run
    assert "demo_data" not in run


def test_legacy_demo_entrypoint_refuses_a_separate_product_state():
    src = (ROOT / "scripts" / "run_local_demo.py").read_text(encoding="utf-8")
    assert "CANONICAL_PREPROD_ROOT = OPERATIONAL" in src
    assert "별도 demo_data 서버는 폐지됐습니다" in src
    assert "TARGET_ROOT) != os.path.abspath(CANONICAL_PREPROD_ROOT" in src


def test_legacy_demo_main_actually_stops_before_parsing_or_starting(monkeypatch):
    from scripts import run_local_demo as demo

    monkeypatch.setattr(demo, "TARGET_ROOT", demo.DEMO_ROOT)
    assert demo.main() == 2


def test_manual_audit_contract_names_one_data_plane_and_keeps_regressions_temporary():
    src = (ROOT / "scripts" / "audit_local_ui.py").read_text(encoding="utf-8")
    assert "단일 사전검증 정본 `data/`" in src
    assert "자동 회귀만 실행별 임시 사본" in src
