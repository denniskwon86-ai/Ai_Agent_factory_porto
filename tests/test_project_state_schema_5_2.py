"""[I-4 1단계] `ProjectState.schema_version` 5.1.0 → 5.2.0 지연 마이그레이션 회귀.

## 왜 버전을 올렸나

⚠️ 필드 추가는 기존 상태를 깨지 않으니 major 는 아니다. 그러나 버전을 그대로 두면
**「구버전이라 계약 필드가 없는 상태」와 「신버전인데 데이터셋 0개인 정상 계약 상태」를
구분할 수 없다.** 그 둘은 전혀 다른 사실이고, I-4 는 후자를 정상 계약으로 다룬다.

## 실측 분포 (2026-08-15)

`projects/**/latest_state.json` 58개 — **버전 없음 42 · `5.1.0` 16**.
두 경우를 **모두** 잠근다(하나만 잠그면 나머지 42개가 조용히 실패한다).
"""
import json

import pytest
from pydantic import ValidationError

from state_models import PROJECT_STATE_SCHEMA_VERSION, ProjectState

CONTRACT_FIELDS = ("capability_intents", "app_runtime_contract_status",
                   "app_runtime_contract_fingerprint", "app_runtime_contract_summary",
                   "unsupported_requirements", "approved_contract_fingerprint")


# ── 1. 버전 없는 기존 상태 (실측 42개) ──────────────────────────────────────
def test_state_without_version_is_promoted():
    s = ProjectState(**{"project_name": "구버전", "rfp_summary": "지난 스프린트"})
    assert s.schema_version == PROJECT_STATE_SCHEMA_VERSION == "5.2.0"
    assert s.rfp_summary == "지난 스프린트"  # 승격이 기존 값을 건드리지 않는다


def test_state_with_null_version_is_promoted():
    # 부분 저장/직렬화 사고로 null 이 들어온 경우까지 승격 대상이다.
    assert ProjectState(**{"schema_version": None}).schema_version == "5.2.0"
    assert ProjectState(**{"schema_version": "  "}).schema_version == "5.2.0"


# ── 2. 5.1.0 상태 (실측 16개) ───────────────────────────────────────────────
def test_state_510_promoted_with_default_contract_fields():
    s = ProjectState(**{"schema_version": "5.1.0", "project_name": "구계약"})
    assert s.schema_version == "5.2.0"
    assert s.capability_intents == []
    assert s.unsupported_requirements == []
    for f in CONTRACT_FIELDS:
        assert hasattr(s, f), f"{f} 가 선언되지 않았다 — extra='forbid' 라 조용히 버려진다"
    assert s.app_runtime_contract_status == ""  # ⚠️ 안전한 기본값(승인 아님)
    assert s.approved_contract_fingerprint == ""


def test_older_than_510_also_promoted():
    # 명시 목록이 아니라 「현재보다 낮으면 승격」이므로 더 오래된 상태도 열린다.
    assert ProjectState(**{"schema_version": "5.0.0"}).schema_version == "5.2.0"
    assert ProjectState(**{"schema_version": "4.9.9"}).schema_version == "5.2.0"


# ── 3. 신규 계약 필드의 JSON 저장·재로드 ────────────────────────────────────
def test_contract_fields_survive_json_roundtrip(tmp_path):
    s = ProjectState(
        project_name="계약 있는 프로젝트",
        capability_intents=[{"intent_id": "intent_1", "capability": "app_data.read",
                             "status": "SUPPORTED"}],
        app_runtime_contract_status="COMPILED",
        app_runtime_contract_fingerprint="0123456789abcdef",
        app_runtime_contract_summary="데이터셋 1개: arrivals",
        unsupported_requirements=[{"requirement_ref": "R-9", "status": "PROHIBITED",
                                   "user_decision": "REDUCE"}],
        approved_contract_fingerprint="",
    )
    p = tmp_path / "latest_state.json"
    p.write_text(json.dumps(s.model_dump(), ensure_ascii=False), encoding="utf-8")

    back = ProjectState(**json.loads(p.read_text(encoding="utf-8")))
    assert back.schema_version == "5.2.0"
    assert back.capability_intents[0]["capability"] == "app_data.read"
    assert back.app_runtime_contract_fingerprint == "0123456789abcdef"
    assert back.unsupported_requirements[0]["user_decision"] == "REDUCE"


def test_saved_state_records_the_new_version():
    # ★ 저장이 일어날 때 5.2.0 이 기록돼야 한다 — 기록되지 않으면 다음 로드가 다시
    #   「버전 없음」으로 보이고, 두 사실을 구분하려던 목적이 사라진다.
    dumped = ProjectState(**{"schema_version": "5.1.0"}).model_dump()
    assert dumped["schema_version"] == "5.2.0"
    for f in CONTRACT_FIELDS:
        assert f in dumped


# ── 4. 체크포인트 직렬화·역직렬화 ───────────────────────────────────────────
def test_checkpoint_roundtrip_preserves_contract_fields():
    from fastapi.encoders import jsonable_encoder  # 실제 저장 경로가 쓰는 인코더
    s = ProjectState(app_runtime_contract_status="APPROVED",
                     approved_contract_fingerprint="abcdef0123456789",
                     capability_intents=[{"capability": "app_data.create"}])
    encoded = jsonable_encoder(s)
    back = ProjectState(**json.loads(json.dumps(encoded, ensure_ascii=False)))
    assert back.app_runtime_contract_status == "APPROVED"
    assert back.approved_contract_fingerprint == "abcdef0123456789"
    assert back.capability_intents == [{"capability": "app_data.create"}]


def test_none_collections_do_not_crash():
    # 부분 저장에서 컬렉션이 null 로 오면 검증이 죽는다 — 기존 보정 대상에 편입돼 있어야 한다.
    s = ProjectState(**{"capability_intents": None, "unsupported_requirements": None})
    assert s.capability_intents == [] and s.unsupported_requirements == []


# ── 5. 오래된 프런트가 옛 버전을 보내도 다운그레이드되지 않는다 ─────────────
def test_stale_client_payload_cannot_downgrade():
    """★★★ 오래 열어 둔 브라우저가 `5.1.0` 을 되돌려 보내는 경로.

    ⚠️ 서버가 그 값을 그대로 받으면 상태가 **조용히 다운그레이드**되고, 그때 화면은
      아무 오류도 내지 않는다."""
    disk = ProjectState(app_runtime_contract_status="APPROVED",
                        approved_contract_fingerprint="feedfacefeedface").model_dump()
    stale_payload = dict(disk, schema_version="5.1.0")   # 옛 화면이 보낸 것
    merged = ProjectState(**stale_payload)
    assert merged.schema_version == "5.2.0"
    # 승격이 계약 상태를 지우지도 않는다 — 지우면 승인이 사라진 것처럼 보인다.
    assert merged.approved_contract_fingerprint == "feedfacefeedface"


def test_frontend_does_not_send_a_schema_version_literal():
    """제품 코드가 스키마 버전을 **적어 보내지 않는지** 소스로 확인한다.

    ⚠️ 주석은 빼고 본다 — 「보내지 않는다」는 **주석**이 검사를 통과시킨 적이 있다."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = [
        ("frontend/src/components/ControlPanel.tsx", "//"),
        ("frontend/src/factory/sprintActions.ts", "//"),
        ("run_e2e_scenario.py", "#"),
    ]
    for rel, comment in targets:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            body = "\n".join(l.split(comment)[0] for l in f)
        hits = re.findall(r"schema_version\s*:\s*['\"][\d.]+['\"]", body)
        assert not hits, f"{rel} 가 스키마 버전을 직접 싣는다: {hits}"


def test_api_version_is_not_coupled_to_state_schema():
    """⚠️ `main.py` 의 FastAPI `version=` 은 **다른 계약**이다(API 버전).

    같은 문자열이라 함께 고치고 싶어지는데, 묶으면 이후 한쪽만 올릴 수 없게 된다."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "main.py"), encoding="utf-8") as f:
        body = f.read()
    assert "PROJECT_STATE_SCHEMA_VERSION" not in body, (
        "main.py 가 상태 스키마 상수를 API 버전으로 쓰고 있다 — 두 계약이 한 숫자에 묶인다.")


# ── 6. 미래 버전은 명확하게 거부한다 ────────────────────────────────────────
@pytest.mark.parametrize("future", ["5.2.1", "5.3.0", "6.0.0", "10.0.0"])
def test_future_version_is_rejected(future):
    """⚠️⚠️ 모르는 계약을 추측해 읽으면 그 추측이 곧 데이터 손상이다 —
    필드 하나를 잘못 해석한 상태가 저장되면 원본은 사라진다."""
    with pytest.raises(ValidationError) as e:
        ProjectState(**{"schema_version": future})
    assert "새 계약" in str(e.value)   # 사용자가 무엇을 해야 하는지 읽히는 문구


def test_malformed_version_is_rejected_clearly():
    for bad in ("abc", "5.2", "5.2.0.1", "v5.2.0"):
        with pytest.raises(ValidationError):
            ProjectState(**{"schema_version": bad})


# ── 7. 기존 진행 프로젝트를 신규 노드로 끌고 가지 않는다 ────────────────────
def test_contract_fields_do_not_change_routing():
    """★ 1단계는 **파이프라인을 건드리지 않는다.**

    ⚠️ 진행 중 프로젝트에 노드를 삽입하면 `completed_agents` 순서 전제와 체크포인터 상태가
      어긋난다 — 그 결함은 재개할 때에야 드러나고, 그때는 원인을 찾기 어렵다."""
    from core import agent_graph
    agents = ["Backend", "Frontend"]
    plain = ProjectState(current_required_agents=agents)
    with_contract = ProjectState(
        current_required_agents=agents,
        app_runtime_contract_status="COMPILED",
        app_runtime_contract_fingerprint="0123456789abcdef",
        capability_intents=[{"capability": "app_data.read", "status": "SUPPORTED"}])

    assert (agent_graph._route_to_first_assigned(agents)
            == agent_graph._route_to_first_assigned(agents))
    for st in (plain, with_contract):
        assert agent_graph.route_from_tech_lead(st) == "Backend"
    # 계약 필드가 채워졌다고 다른 노드로 새지 않는다.
    assert agent_graph.route_from_tech_lead(with_contract) == agent_graph.route_from_tech_lead(plain)


def test_no_i4_node_is_wired_yet():
    """1단계에서 그래프에 신규 노드가 붙지 않았음을 못박는다(순서를 지킨다)."""
    import inspect
    from core import agent_graph
    src = inspect.getsource(agent_graph)
    for node in ("HostContractCompiler", "ContractReviewGate"):
        assert node not in src, f"{node} 가 1단계에서 그래프에 붙었다 — 순서는 4단계다."
