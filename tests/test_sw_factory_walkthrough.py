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
    #: ⚠️ `current_sprint_task_id` 를 빼면 제품과 다른 것을 시험한다 — 스프린트는 언제나
    #:   **어떤 태스크를 돌고 있다.** 이 값이 없으면 「지금 도는 태스크」가 없어서
    #:   초안 요구 자체가 성립하지 않는다(2026-08-26 범위 정리 이후).
    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "T-1",
         "runtime_contract_profile": PROFILE}))
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


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 아직 시작 안 한 태스크가 **앞 태스크를 막지 않는다** (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

def _wbs_status(ws: str, tasks):
    with open(os.path.join(ws, "00_wbs_master_plan.json"), "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False)


def test_앞_태스크가_뒤_APP_태스크를_기다리지_않는다(tmp_path):
    """★★★ **실제 가동에서 완주가 여기서 죽었다.**

    WBS 4개 중 TASK-03 만 APP(계약 대상)이었다. TASK-01(LIBRARY)을 돌렸더니

        「계약 대상 태스크인데 계약 초안이 없습니다: TASK-03」 → CONTRACT_BLOCKED

    TASK-03 은 **아직 시작도 안 했다.** 초안은 그 태스크의 Tech Lead 가 만드는데 그
    Tech Lead 는 컴파일러를 지나야 도니까, 앞 태스크가 뒤 태스크의 미래를 기다리는
    교착이다. 순서대로 돌리면 프로젝트는 **영원히 계약을 만들지 못한다.**"""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [
        {"task_id": "TASK-01", "goal": "골격", "artifact_kind": "LIBRARY", "status": "IN_PROGRESS"},
        {"task_id": "TASK-03", "goal": "화면", "artifact_kind": "APP", "status": "TODO"},
    ])
    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "TASK-01",
         "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") != "CONTRACT_BLOCKED", (
        "아직 시작 안 한 태스크 때문에 막혔다: " + str(out.get("terminal_reason", "")))


def test_실패한_APP_태스크가_다른_태스크를_영영_막지_않는다(tmp_path):
    """★★★ **[2026-08-26 실측] 처음 고칠 때 내가 틀린 자리.**

    나는 「이미 손댄(IN_PROGRESS·DONE) 태스크가 초안을 안 남긴 것은 오류」로 두었다.
    그런데 **종결 롤백이 `contracts/drafts/*.json` 을 지운다**(커밋 전이므로). 그래서
    APP 태스크가 한 번 실패하면 「손댔는데 초안이 없는」 상태로 굳고, 그때부터 **다른
    모든 태스크가 영영 막힌다** — 실측에서 TASK-02 가 정확히 그렇게 죽었다.

    ★ 그래서 판단 기준은 상태가 아니라 **초안의 존재**다. 통제는 아래 시험이
      지키는 자리 — 「지금 도는 태스크」 — 에서 지켜진다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [
        {"task_id": "TASK-02", "goal": "라이브러리", "artifact_kind": "LIBRARY",
         "status": "IN_PROGRESS"},
        #: 한 번 돌았다가 실패해 초안이 롤백으로 사라진 APP 태스크
        {"task_id": "TASK-03", "goal": "화면", "artifact_kind": "APP", "status": "FAILED"},
    ])
    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "TASK-02",
         "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") != "CONTRACT_BLOCKED", (
        "실패한 APP 태스크가 다른 태스크를 막았다: " + str(out.get("terminal_reason", "")))


def test_지금_도는_태스크는_상태와_무관하게_계약에_들어간다(tmp_path):
    """⚠️ 자기 계약을 스스로 빠뜨리면 **검토 없이** 지나간다. 상태가 TODO 여도 남긴다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [
        {"task_id": "TASK-03", "goal": "화면", "artifact_kind": "APP", "status": "TODO"},
    ])
    out = asyncio.run(cn.run_host_contract_compiler(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "TASK-03",
         "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") == "CONTRACT_BLOCKED", \
        "지금 도는 태스크의 초안을 요구하지 않았다 — 검토 없이 지나간다"


def test_게이트가_컴파일러와_같은_범위를_본다(tmp_path):
    """★★★ **두 계층의 답이 갈리면 통제가 아니라 교착이다.**

    컴파일러는 「아직 시작 안 한 태스크」를 빼는데 게이트가 WBS 전체로 판정하면,
    컴파일러가 통과시킨 태스크를 게이트가 막는다. 실제 가동에서 그렇게 막혔다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [
        {"task_id": "TASK-01", "goal": "골격", "artifact_kind": "LIBRARY", "status": "IN_PROGRESS"},
        {"task_id": "TASK-03", "goal": "화면", "artifact_kind": "APP", "status": "TODO"},
    ])
    out = asyncio.run(cn.run_contract_review_gate(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "TASK-01",
         "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") != "CONTRACT_BLOCKED", (
        "게이트가 아직 시작 안 한 태스크로 막았다: " + str(out.get("terminal_reason", "")))


def test_게이트가_막을_때_사유를_함께_남긴다(tmp_path):
    """⚠️ 상태만 찍고 사유를 안 세우면 **직전 실패의 사유가 그대로 남는다.**
    실제로 그것 때문에 컴파일러를 한참 잘못 짚었다 — 원인은 게이트였다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [
        {"task_id": "TASK-03", "goal": "화면", "artifact_kind": "APP", "status": "IN_PROGRESS"},
    ])
    out = asyncio.run(cn.run_contract_review_gate(
        {"workspace_root": ws, "project_name": "p", "current_sprint_task_id": "TASK-03",
         "runtime_contract_profile": PROFILE}))
    assert out.get("terminal_status") == "CONTRACT_BLOCKED"
    assert (out.get("terminal_reason") or "").strip(), "막았는데 사유가 비어 있다"


# ══════════════════════════════════════════════════════════════════════════
# ⑥ 한 번 실패한 태스크를 **다시 돌릴 수 있는가** (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

def test_새_가동은_직전_종결_판정을_물려받지_않는다():
    """★★★ **「생성 실패」가 영영 안 풀리던 이유.**

    `terminal_status` 는 체크포인트에 남는다. 다시 가동하면 라우터가 첫 갈림길에서
    `_terminated(state)` 를 보고 곧바로 종결 노드로 보낸다 — **노드가 하나도 돌지 않고**
    직전과 똑같은 사유로 다시 실패한다. 결함을 고쳐도 그 태스크는 살아나지 않는다.

    ⚠️ 화면의 「재시도」도 같은 구멍이라(`...state` 를 그대로 실어 보낸다) 클라이언트가
      아니라 **서버에서** 지워야 한다."""
    import inspect

    from core import async_orchestrator as ao

    src = inspect.getsource(ao.AsyncFactoryOrchestrator.start_sprint)
    assert 'terminal_status' in src, "새 가동이 직전 판정을 지우지 않는다"
    i_clear = src.index('terminal_status')
    i_task = src.index('create_task')
    assert i_clear < i_task, "판정을 지우기 전에 스트림이 시작된다"


def test_근거는_지우지_않는다():
    """⚠️ 판정만 지운다. `build_error_log` 는 **근거**이고, 자가복구가 직전 실패
    원인을 프롬프트에 실어야 한다([자가복구 P1]). 근거까지 지우면 재시도가 원인을
    모른 채 같은 프롬프트를 다시 돌린다."""
    import inspect

    from core import async_orchestrator as ao

    src = inspect.getsource(ao.AsyncFactoryOrchestrator.start_sprint)
    head = src[:src.index('create_task')]
    assert 'build_error_log' not in head.replace('build_error_log` 같은', ''), \
        "근거(build_error_log)까지 지우고 있다"


# ══════════════════════════════════════════════════════════════════════════
# ⑦ 승인 기억은 **프로젝트 단위**다 (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

#: ⚠️ 지문은 **64자 hex** 다(`arc.FINGERPRINT_PATTERN`). 내 말로 «fp_same» 이라고 쓰면
#:   `ProjectState` 검증에서 조용히 떨어져 「컴파일된 계약이 없다」로 엉뚱하게 실패한다 —
#:   실제로 그렇게 한 번 틀렸다. 형식은 **정본을 보고** 정한다.
FP_SAME = "a" * 64
FP_OLD = "b" * 64
FP_NEW = "c" * 64
FP_STATE = "d" * 64


def _approved_contract(ws, fingerprint=FP_SAME, status="APPROVED",
                       approval_status="APPROVED"):
    import os as _o
    d = _o.path.join(ws, "contracts")
    _o.makedirs(d, exist_ok=True)
    with open(_o.path.join(d, "app_runtime_contract.json"), "w", encoding="utf-8") as f:
        json.dump({"semantic_fingerprint": fingerprint, "status": status,
                   "approval": {"status": approval_status},
                   "datasets": [{"name": "x"}]}, f, ensure_ascii=False)


def test_다음_태스크가_같은_계약을_다시_승인받지_않는다(tmp_path):
    """★★★ **실측: 5개 태스크에 승인을 5번 받았다.**

    계약은 프로젝트 하나인데 `approved_contract_fingerprint` 는 체크포인트(`project__task`)
    에 산다. 태스크가 바뀌면 그 기억이 비어 「이 프로젝트의 **최초 계약**입니다」가 뜬다 —
    이미 승인된 계약이 있는데도. 사실이 아닌 말을 화면이 하면 사람은 그 화면을 안 믿는다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [{"task_id": "T-2", "goal": "화면", "artifact_kind": "APP",
                      "status": "IN_PROGRESS"}])
    _approved_contract(ws, FP_SAME)

    out = asyncio.run(cn.run_contract_review_gate({
        "workspace_root": ws, "project_name": "p", "current_sprint_task_id": "T-2",
        "runtime_contract_profile": PROFILE,
        #: 새 태스크의 체크포인트 — 승인 기억이 비어 있다(이것이 실측 상황이다).
        "app_runtime_contract_fingerprint": FP_SAME,
        "approved_contract_fingerprint": "",
        "app_runtime_contract_status": "APPROVED",
    }))
    assert not (out.get("contract_review_request_event_id") or ""), \
        "이미 승인된 계약인데 또 승인을 요구했다"
    assert not out.get("terminal_status")


def test_계약이_바뀌었으면_여전히_재승인을_요구한다(tmp_path):
    """★★★ **대조군.** 위 완화가 게이트를 없애면 안 된다 — 계약이 실제로 달라졌으면
    태스크가 무엇이든 사람이 다시 봐야 한다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [{"task_id": "T-2", "goal": "화면", "artifact_kind": "APP",
                      "status": "IN_PROGRESS"}])
    _approved_contract(ws, FP_OLD)

    out = asyncio.run(cn.run_contract_review_gate({
        "workspace_root": ws, "project_name": "p", "current_sprint_task_id": "T-2",
        "runtime_contract_profile": PROFILE,
        "app_runtime_contract_fingerprint": FP_NEW,     # ← 달라졌다
        "approved_contract_fingerprint": "",
        "app_runtime_contract_status": "COMPILED",
    }))
    assert out.get("contract_review_request_event_id"), "바뀐 계약을 그냥 통과시켰다"


@pytest.mark.parametrize("approval_status", ["PENDING", "REJECTED", ""])
def test_승인되지_않은_봉투를_승인으로_읽지_않는다(tmp_path, approval_status):
    """⚠️⚠️ 「승인 봉투가 있다」와 「승인됐다」는 다르다. `PENDING`·`REJECTED` 를 승인으로
    읽으면 **게이트가 사라진다** — 반려된 계약이 반려된 채로 빌드된다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [{"task_id": "T-2", "goal": "화면", "artifact_kind": "APP",
                      "status": "IN_PROGRESS"}])
    _approved_contract(ws, FP_SAME, status="COMPILED", approval_status=approval_status)

    out = asyncio.run(cn.run_contract_review_gate({
        "workspace_root": ws, "project_name": "p", "current_sprint_task_id": "T-2",
        "runtime_contract_profile": PROFILE,
        "app_runtime_contract_fingerprint": FP_SAME,
        "approved_contract_fingerprint": "",
        "app_runtime_contract_status": "COMPILED",
    }))
    assert out.get("contract_review_request_event_id"), \
        f"«{approval_status}» 봉투를 승인으로 읽었다 — 게이트가 열렸다"


def test_상태에_있는_승인_기억이_정본보다_우선한다(tmp_path):
    """⚠️ 정본은 **보조 기억**이다. 체크포인트에 값이 있으면 그것이 이긴다 — 두 곳이
    다를 때 어느 쪽을 믿는지가 정해져 있지 않으면 판정이 실행마다 달라진다."""
    from nodes import contract as cn

    ws = str(tmp_path)
    _wbs_status(ws, [{"task_id": "T-2", "goal": "화면", "artifact_kind": "APP",
                      "status": "IN_PROGRESS"}])
    _approved_contract(ws, "fp_file")

    out = asyncio.run(cn.run_contract_review_gate({
        "workspace_root": ws, "project_name": "p", "current_sprint_task_id": "T-2",
        "runtime_contract_profile": PROFILE,
        "app_runtime_contract_fingerprint": FP_STATE,
        "approved_contract_fingerprint": FP_STATE,      # ← 상태가 이겨야 한다
        "app_runtime_contract_status": "APPROVED",
    }))
    assert not (out.get("contract_review_request_event_id") or ""), \
        "상태의 승인 기억을 무시하고 정본으로 판정했다"
