"""★★★ SW 생성기 **완주** — Tech Lead 부터 코드까지 끊긴 칸이 없는가. (2026-08-25)

## ⚠️⚠️ 사용자 실측 — 두 번 막혔다

> tech리드한테 지시 내리는 부분에서 계약이 생성되지 않아서 전달이 실패
> tech리드한테 전달하는 과정에서 자가복구 실패 했다고 하고 생성 실패

원인은 **네 자리**였고, 전부 같은 모양이었다 — 「읽는 곳·통제는 있는데 부르는 곳이 없다」.

    ① contracts/drafts 를 읽는 코드만 있고 **쓰는 코드가 없었다**
    ② 계약 실패가 종결 상태를 안 세워 **「빌드 자가복구 소진」으로 위장**됐다
    ③ WBS 를 못 읽으면 **「app_class 가 없음」** 이라는 엉뚱한 사유가 나왔다
    ④ 계약 승인 대기가 **「완료」로 보고**됐고, 승인할 화면이 없었다

이 파일은 그 네 자리를 **경로로** 확인한다. LLM 을 부르지 않는다 — 부르면 이 시험이
비용과 날씨에 따라 답이 달라지고, 그러면 회귀가 아니다.
"""
import asyncio
import json
import os

import pytest


PROFILE = "v1"


def _wbs(ws: str, tasks):
    with open(os.path.join(ws, "00_wbs_master_plan.json"), "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False)


def _draft(name: str = "material_arrivals") -> dict:
    """정본 스키마를 통과하는 최소 초안. ⚠️ 내 말로 쓰지 않는다 — 아래 시험이 실제
    컴파일러로 검증하므로, 틀리면 그 자리에서 빨개진다."""
    return {
        "app_class": "departmental",
        "datasets": [{
            "name": name, "label": "원료 도입", "purpose": "도입 추적",
            "allowed_actions": ["read"],
            "fields": [{"name": "po_id", "type": "string", "required": False,
                        "classification": "INTERNAL"}],
            "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
            "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
            "enterprise_contract_key": "PRC-02",
        }],
        "capability_intents": [],
    }


# ══════════════════════════════════════════════════════════════════════════
# ① Tech Lead → 초안 → 계약 컴파일 → 게이트 → 코드로 넘어간다
# ══════════════════════════════════════════════════════════════════════════

def test_초안이_있으면_계약이_나오고_게이트로_간다(tmp_path):
    """★★★ **완주의 첫 관문.** 지문이 나와야 게이트로 간다."""
    from core import agent_graph as ag
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "goal": "원료 도입 화면", "artifact_kind": "app"}])
    cn.save_draft(ws, "T-1", _draft())

    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "runtime_contract_profile": PROFILE}))
    assert out.get("app_runtime_contract_fingerprint"), out.get("app_runtime_contract_summary")
    assert not out.get("terminal_status"), out.get("terminal_reason")

    #: ★ 라우터가 실제로 게이트로 보내는가 — 노드만 통과하고 라우팅이 다르면 소용없다.
    st = {"workspace_root": ws, "runtime_contract_profile": PROFILE,
          "app_runtime_contract_fingerprint": out["app_runtime_contract_fingerprint"]}
    assert ag.route_from_contract_compiler(_S(st)) == "ContractReviewGate"


class _S:
    """`route_*` 는 속성으로 읽는다 — dict 를 그대로 넘기면 전부 기본값이 된다."""

    def __init__(self, d):
        self.__dict__.update(d)

    def __getattr__(self, k):
        return ""


def test_승인_전에는_코드로_넘어가지_않는다(tmp_path):
    """★★★ **검토를 지나지 않은 계약으로 코드를 만들지 않는다.**

    ⚠️ 여기가 뚫리면 승인 절차는 이름만 남는다."""
    from core import agent_graph as ag

    #: 게이트가 검토 요청을 연 상태 — 대기로 가야 한다.
    st = _S({"contract_review_request_event_id": "ev_1"})
    assert ag.route_from_contract_gate(st) == "ContractReviewPending"


def test_승인_뒤에는_코드로_넘어간다(tmp_path):
    """★ 대조군 — 늘 멈추기만 하면 그것은 완주가 아니다."""
    from core import agent_graph as ag

    st = _S({"contract_review_request_event_id": "",
             "required_agents": [{"role": "Backend"}]})
    assert ag.route_from_contract_gate(st) in ("Backend", "Frontend", "CodeBuilder")


# ══════════════════════════════════════════════════════════════════════════
# ② 막힌 자리마다 **사유가 원인을 가리키는가**
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("setup,expect_in,forbid", [
    #: 초안 없음 — 사용자가 처음 본 메시지
    (lambda ws: _wbs(ws, [{"task_id": "T-1", "goal": "x", "artifact_kind": "app"}]),
     "계약 초안이 없습니다", "자가복구"),
    #: WBS 없음 — 「app_class 가 없음」으로 새던 자리
    (lambda ws: None, "WBS", "app_class"),
])
def test_막힌_사유가_원인을_가리킨다(tmp_path, setup, expect_in, forbid):
    from nodes import contract as cn

    ws = str(tmp_path)
    setup(ws)
    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") == "CONTRACT_BLOCKED"
    reason = out.get("terminal_reason") or ""
    assert expect_in in reason, reason
    assert forbid not in reason, f"엉뚱한 사유가 붙었다: {reason}"


# ══════════════════════════════════════════════════════════════════════════
# ③ 승인 대기를 **「완료」로 보고하지 않는가**
# ══════════════════════════════════════════════════════════════════════════

def test_승인_대기는_완료가_아니다():
    """★★★ **사용자에게 가장 위험한 거짓말.**

    `ContractReviewPending` 은 `END` 로 끝나므로 `snapshot.next` 도 `terminal_status` 도
    비어 있다. 그래서 오케스트레이터가 **WBS DONE · SPRINT_COMPLETED** 를 쐈다 —
    사람이 승인해야 하는데 화면은 「완료」라고 말했다.

    ⚠️ `terminal_status` 필드를 만든 이유가 정확히 「END 는 성공이 아니다」인데,
      그 규칙이 이 갈래에서만 새고 있었다."""
    import inspect

    from core import async_orchestrator as ao

    src = inspect.getsource(ao.AsyncFactoryOrchestrator._broadcast_stream_end)
    #: ★ 산문이 아니라 **코드**를 본다 — 주석만 고치고 코드를 안 고치는 결함이
    #:   이 저장소에서 반복됐다.
    assert 'CONTRACT_REVIEW' in src, "승인 대기 갈래가 없다"
    i_pending = src.index('CONTRACT_REVIEW')
    i_done = src.index('"DONE"')
    assert i_pending < i_done, "승인 대기 판정이 DONE 마킹보다 뒤에 있다 — 먼저 걸러야 한다"
    assert 'CONTRACT_REVIEW_PENDING' in src, "화면이 승인 자리를 열 신호가 없다"


# ══════════════════════════════════════════════════════════════════════════
# ④ 승인 화면이 **실제로 있는가** — 「부르는 곳이 없다」를 다시 만들지 않는다
# ══════════════════════════════════════════════════════════════════════════

def _fe(*parts) -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "frontend", "src", *parts)


def test_승인_경로를_부르는_화면이_있다():
    """⚠️⚠️ 서버에 경로가 있어도 **부르는 곳이 없으면** 사용자는 승인할 수 없다.
    이 저장소에서 네 번째 반복이라 시험으로 못박는다."""
    api = _fe("lib", "contractReviewApi.ts")
    assert os.path.isfile(api), "계약 검토 클라이언트가 없다"
    text = open(api, encoding="utf-8").read()
    assert "contract-review/pending" in text
    assert "contract-review/decision" in text

    gate = _fe("components", "ContractReviewGate.tsx")
    assert os.path.isfile(gate), "승인 화면이 없다"
    used = open(_fe("components", "TimelinePanel.tsx"), encoding="utf-8").read()
    assert "ContractReviewGate" in used, "승인 화면을 어디서도 그리지 않는다"


def test_스토어가_승인_대기_신호를_받는다():
    """⚠️ 신호를 안 받으면 사용자가 **새로고침해야** 승인 자리가 나타난다."""
    store = open(_fe("store", "useFactoryStore.ts"), encoding="utf-8").read()
    assert "CONTRACT_REVIEW_PENDING" in store
