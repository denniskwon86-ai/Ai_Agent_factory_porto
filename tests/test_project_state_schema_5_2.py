"""[I-4 1단계·4c-2] `ProjectState.schema_version` 지연 마이그레이션 회귀.

⚠️ 현재 정본은 **5.3.0** 이다(4c-2 에서 `contract_review_request_event_id` 를 더하며
  올렸다). 아래 리터럴은 «지금 이 빌드가 무엇을 정본으로 삼는가» 를 손으로 못 박는
  것이므로 상수로 바꾸지 않는다 — 상수를 읽으면 버전이 바뀌어도 늘 통과한다.

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
    assert s.schema_version == PROJECT_STATE_SCHEMA_VERSION == "5.3.0"
    assert s.rfp_summary == "지난 스프린트"  # 승격이 기존 값을 건드리지 않는다


def test_state_with_null_version_is_promoted():
    # 부분 저장/직렬화 사고로 null 이 들어온 경우까지 승격 대상이다.
    assert ProjectState(**{"schema_version": None}).schema_version == "5.3.0"
    assert ProjectState(**{"schema_version": "  "}).schema_version == "5.3.0"


# ── 2. 5.1.0 상태 (실측 16개) ───────────────────────────────────────────────
def test_state_510_promoted_with_default_contract_fields():
    s = ProjectState(**{"schema_version": "5.1.0", "project_name": "구계약"})
    assert s.schema_version == "5.3.0"
    assert s.capability_intents == []
    assert s.unsupported_requirements == []
    for f in CONTRACT_FIELDS:
        assert hasattr(s, f), f"{f} 가 선언되지 않았다 — extra='forbid' 라 조용히 버려진다"
    assert s.app_runtime_contract_status == ""  # ⚠️ 안전한 기본값(승인 아님)
    assert s.approved_contract_fingerprint == ""


def test_older_than_510_also_promoted():
    # 명시 목록이 아니라 「현재보다 낮으면 승격」이므로 더 오래된 상태도 열린다.
    assert ProjectState(**{"schema_version": "5.0.0"}).schema_version == "5.3.0"
    assert ProjectState(**{"schema_version": "4.9.9"}).schema_version == "5.3.0"


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
    assert back.schema_version == "5.3.0"
    assert back.capability_intents[0]["capability"] == "app_data.read"
    assert back.app_runtime_contract_fingerprint == "0123456789abcdef"
    assert back.unsupported_requirements[0]["user_decision"] == "REDUCE"


def test_saved_state_records_the_new_version():
    # ★ 저장이 일어날 때 5.3.0 이 기록돼야 한다 — 기록되지 않으면 다음 로드가 다시
    #   「버전 없음」으로 보이고, 두 사실을 구분하려던 목적이 사라진다.
    dumped = ProjectState(**{"schema_version": "5.1.0"}).model_dump()
    assert dumped["schema_version"] == "5.3.0"
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
    assert merged.schema_version == "5.3.0"
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
@pytest.mark.parametrize("future", ["5.3.1", "5.4.0", "6.0.0", "10.0.0"])
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


def test_i4_nodes_are_wired_only_behind_the_profile():
    """★ 1단계에서는 「아직 붙지 않았음」을 못 박던 자리다 — **그 순서가 도착했다**
    (4c-6). 지우지 않고 **반대 방향으로 뒤집는다.**

    ⚠️ 감시를 그냥 지우면 「순서를 지켰다」는 기록도 함께 사라지고, 다음에 누가
      순서를 어겨도 아무것도 말해 주지 않는다. 이제 지켜야 할 것은 「붙지 않았다」가
      아니라 **「프로필 뒤에만 붙었다」**다.
    ★ 배선 자체의 회귀는 `tests/test_contract_graph_wiring.py` 가 본다. 여기서는
      **소급 적용이 없다는 것**만 확인한다."""
    import inspect

    from core import agent_graph

    src = inspect.getsource(agent_graph)
    for node in ("HostContractCompiler", "ContractReviewGate"):
        assert node in src, f"{node} 가 4단계에서도 붙지 않았다."
    assert "_contract_profile_on" in src, "계약 노드가 프로필 없이 무조건 붙었다"

    #: 프로필이 꺼진 상태(= 기존 모든 프로젝트)는 계약 노드에 닿지 않는다
    st = ProjectState(project_name="구", current_required_agents=["Tech_Lead", "Backend"])
    assert st.runtime_contract_profile == ""
    assert agent_graph.route_from_tech_lead(st) == "Backend"


# ── 5.2.0 → 5.3.0 (I-4 4c-2) ───────────────────────────────────────────────
def test_52_state_is_promoted_with_a_safe_default_request_id():
    """★ 5.2 로 저장된 체크포인트는 **열린 검토 요청이 없는 상태**로 승격된다.

    ⚠️ 여기서 아무 값이나 채워 넣으면 그 프로젝트는 «존재하지 않는 요청을 가진»
      상태가 되고, 원장 조회가 빈손으로 돌아온다."""
    s = ProjectState(**{"schema_version": "5.2.0", "project_name": "구계약"})
    assert s.schema_version == "5.3.0"
    assert s.contract_review_request_event_id == ""
    assert s.runtime_contract_profile == "", "소급 적용도 없어야 한다"


def test_client_cannot_pin_the_request_event_id_through_a_stale_payload():
    """⚠️ 이 값은 **캐시**다. 정본은 원장이므로, 클라이언트가 실어 보낸 값이 그대로
    상태가 되더라도 판정은 원장에서 다시 한다 — 그래서 이 시험은 「막힌다」가 아니라
    「믿지 않는다」를 고정한다. 서버 주입 경로는 `sprint/start` 회귀가 지킨다."""
    s = ProjectState(**{"schema_version": "5.2.0",
                        "contract_review_request_event_id": "dle_남의것"})
    assert s.contract_review_request_event_id == "dle_남의것"   # 상태에는 들어간다
    # 그러나 게이트는 이 값을 근거로 쓰지 않는다(원장 조회가 정본) —
    # `test_contract_review_gate.py::test_open_request_is_found_from_the_ledger_not_the_state`
