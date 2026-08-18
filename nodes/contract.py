"""[I-4 4c-6] 계약 컴파일·검토 노드 — **둘 다 비-LLM 시스템 노드**다.

설계서 §3 의 파이프라인:

```text
Tech_Lead
→ HostContractCompiler   [비-LLM] WBS 의 계약 대상 태스크 초안을 프로젝트 계약 하나로
→ ContractReviewGate     [비-LLM] 최초·지문 변경이면 사람, 지문 불변이면 자동 통과
   ├ AUTO_PASS / NOT_APPLICABLE → 기존 경로(Backend·Frontend·CodeBuilder)
   ├ REVIEW_REQUIRED           → ContractReviewPending → END (전용 API 로 결정)
   └ BLOCKED                   → TerminalHandler (계약 오류)
```

⚠️⚠️ **판정은 LLM 이 할 일이 아니다.** 두 노드는 `CodeBuilder` 와 같은 부류다 —
  같은 입력에 같은 출력을 준다. 여기에 모델을 넣으면 「어제는 통과했는데 오늘은
  막힌다」가 생기고, 그 순간 게이트는 통제가 아니라 운이 된다.

⚠️ **진행 중 프로젝트에 소급되지 않는다.** 라우팅이 `runtime_contract_profile` 을
  보고 갈리며, 기존 프로젝트는 전부 `""`(LEGACY_OFF)이라 이 두 노드에 **닿지
  않는다.** 닿지 않으므로 `completed_agents` 도 체크포인트 스키마도 그대로다.
"""
import json
import os
from typing import Any, Dict, List

from core import contract_review_gate as gate
from core import project_contract_aggregator as aggregator
from core import wbs_artifact_kind as artifact_kind
from state_models import ProjectState

#: 계약 **설계 정본**의 자리(설계 §4). 상태에는 요약·상태·지문만 둔다.
CONTRACT_DIR = "contracts"
CONTRACT_FILE = "app_runtime_contract.json"
#: 태스크별 초안. Tech Lead 가 여기에 쓴다.
DRAFT_DIR = os.path.join(CONTRACT_DIR, "drafts")


def contract_path(workspace_root: str) -> str:
    return os.path.join(workspace_root or ".", CONTRACT_DIR, CONTRACT_FILE)


def draft_dir(workspace_root: str) -> str:
    return os.path.join(workspace_root or ".", DRAFT_DIR)


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_drafts(workspace_root: str) -> Dict[str, Dict[str, Any]]:
    """`<workspace>/contracts/drafts/<task_id>.json` 을 모은다.

    ⚠️ 읽지 못한 초안을 **건너뛰지 않는다.** 건너뛰면 「초안이 없다」와 「초안이
      깨졌다」가 같아지고, 합산기는 전자로 읽어 그 태스크를 빠뜨린 채 막는다 —
      사람은 초안을 안 썼다고 생각하고 다시 쓴다. 깨진 것은 깨진 채로 넘긴다."""
    out: Dict[str, Dict[str, Any]] = {}
    d = draft_dir(workspace_root)
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        task_id = name[: -len(".json")]
        raw = _read_json(os.path.join(d, name))
        out[task_id] = raw if isinstance(raw, dict) else {"__unreadable__": name}
    return out


def _wbs_tasks(workspace_root: str) -> List[Any]:
    from nodes.utils.wbs_manager import WBSManager

    if not workspace_root:
        return []
    return (WBSManager(workspace_root).get_wbs() or {}).get("tasks") or []


def _summary(contract: Dict[str, Any], required: List[str]) -> str:
    """사람이 읽는 한 줄. **상태에 원문을 싣지 않는 대신** 이것을 싣는다."""
    datasets = contract.get("datasets") or []
    names = ", ".join(str(d.get("name", "")) for d in datasets[:6])
    more = "" if len(datasets) <= 6 else f" 외 {len(datasets) - 6}개"
    return (f"계약 대상 태스크 {len(required)}개 · 데이터셋 {len(datasets)}개"
            + (f"({names}{more})" if datasets else "(데이터셋 0개 — 그 선언 자체가 통제다)"))


async def run_host_contract_compiler(state: Any) -> Dict[str, Any]:
    """WBS 의 계약 대상 태스크 초안을 **프로젝트 계약 하나**로 컴파일한다.

    ⚠️ 태스크 하나씩 컴파일하면 뒤 태스크의 계약이 앞 태스크를 덮어 데이터셋이
      소실된다([4c-1]). 그래서 언제나 WBS 전체를 다시 합산한다 — 그 덕에 태스크가
      삭제되면 자연히 계약에서도 빠지고, 지문이 바뀌어 재승인을 지난다."""
    st = ProjectState.model_validate(state)
    ws = st.workspace_root or ""
    tasks = _wbs_tasks(ws)
    previous = _read_json(contract_path(ws))

    result, agg = aggregator.compile_project_contract(
        tasks, load_drafts(ws), project_id=os.path.basename(ws.rstrip("/\\")) or st.project_name,
        previous=previous if isinstance(previous, dict) else None)
    contract = result.contract
    required = artifact_kind.contract_required_task_ids(tasks)

    if result.errors:
        #: ⚠️ 실패해도 **정본 파일을 덮지 않는다.** 덮으면 「무엇이 승인돼 있었는가」를
        #:   잃고, 고칠 근거까지 사라진다.
        print("⛔ [HostContractCompiler] 계약을 만들지 못했습니다:")
        for e in result.errors[:8]:
            print(f"   · {e}")
        return {
            "app_runtime_contract_status": "DRAFT",
            "app_runtime_contract_fingerprint": "",
            "app_runtime_contract_summary": "; ".join(result.errors[:4]),
            "unsupported_requirements": contract.get("unsupported_requirements") or [],
            "capability_intents": contract.get("capability_intents") or [],
        }

    os.makedirs(os.path.join(ws, CONTRACT_DIR), exist_ok=True)
    with open(contract_path(ws), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    fp = str(contract.get("semantic_fingerprint", ""))
    print(f"[OK] [HostContractCompiler] 계약 컴파일 — 지문 {fp[:12]}… · "
          f"대상 태스크 {len(agg.included_task_ids)}개")
    return {
        "app_runtime_contract_status": str(contract.get("status", "COMPILED")),
        "app_runtime_contract_fingerprint": fp,
        "app_runtime_contract_summary": _summary(contract, required),
        "unsupported_requirements": contract.get("unsupported_requirements") or [],
        "capability_intents": contract.get("capability_intents") or [],
    }


async def run_contract_review_gate(state: Any) -> Dict[str, Any]:
    """최초 계약 또는 지문 변경이면 **검토 요청을 원장에 열고** 멈춘다.

    ⚠️ 요청 기록에 실패하면 **진행하지 않는다.** 요청 없이 지나가면 승인 이력이
      없는 승인이 생기고, 그것은 승인이 아니다."""
    st = ProjectState.model_validate(state)
    ws = st.workspace_root or ""
    project_id = os.path.basename(ws.rstrip("/\\")) or st.project_name
    decision, required = gate.evaluate_project(_wbs_tasks(ws), st)

    if decision.verdict == gate.AUTO_PASS:
        print("[OK] [ContractReviewGate] 승인된 계약과 지문이 같습니다 — 자동 통과.")
        return {"contract_review_request_event_id": ""}

    if decision.verdict == gate.NOT_APPLICABLE:
        print("[OK] [ContractReviewGate] 계약이 필요 없는 산출물입니다.")
        return {"contract_review_request_event_id": ""}

    if decision.verdict == gate.BLOCKED:
        print(f"⛔ [ContractReviewGate] {decision.reason}")
        return {"terminal_status": "CONTRACT_BLOCKED",
                "supervisor_feedback": decision.reason,
                "contract_review_request_event_id": ""}

    from core.decision_ledger import decision_ledger

    ev, created = gate.ensure_review_request(
        decision_ledger, decision, project_id=project_id, task_ids=required,
        tenant_id=st.tenant_id or "tenant_default",
        enterprise_scope_id=st.enterprise_scope_id or "",
        entity_mode=st.entity_mode or "REAL")
    print(f"⏸️ [ContractReviewGate] 사용자 검토가 필요합니다"
          f"({'요청 생성' if created else '기존 요청 재사용'} {ev.get('event_id','')}). "
          f"{decision.reason}")
    return {"contract_review_request_event_id": str(ev.get("event_id", "")),
            "supervisor_feedback": decision.reason}


async def run_contract_review_pending(state: Any) -> Dict[str, Any]:
    """검토 대기 표시 노드. **여기서 멈춘다.**

    ★ `WBS_Approved` 와 같은 형태다 — 「멈췄다」를 상태로 남기려면 실제 노드가
      하나 있어야 한다. 결정은 전용 API 로 하고(`/contract-review/decision`),
      그 뒤에 다시 가동한다.
    ⚠️ 일반 `/hotl/resume` 으로는 지날 수 없다([4c-4]) — 빈 피드백을 승인으로
      해석하지 않는다."""
    print("⏸️ [ContractReviewPending] 계약 승인 대기 — 전용 결정 API 로 승인 또는 반려하십시오.")
    return {"current_stage": "CONTRACT_REVIEW"}
