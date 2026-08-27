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
        if name.startswith("_"):
            #: ⚠️ `_resolutions.json` 은 초안이 아니다. 태스크로 읽히면 합산기가
            #:   「_resolutions 라는 태스크의 초안」을 보게 되고, 계약 범위가 틀어진다.
            continue
        task_id = name[: -len(".json")]
        raw = _read_json(os.path.join(d, name))
        out[task_id] = raw if isinstance(raw, dict) else {"__unreadable__": name}
    #: ★★★ [2026-08-27 실측] **사람이 정한 것을 다시 덮어씌운다.**
    #:
    #: ⚠️⚠️ 결정은 초안 파일에 착지하는데, 그 파일은 Tech Lead 가 다시 돌 때 **통째로
    #:   덮인다.** 실측: `customers` 를 E2E-01·E2E-02 가 다르게 선언 → 사람이 E2E-01 로
    #:   정함 → 태스크 재개 → Tech Lead 가 초안을 새로 씀 → **같은 충돌이 다시** →
    #:   45초마다 도는 무한 루프가 됐다(LLM 비용도 그만큼).
    #:   승인된 계약 원문을 4,289자 그대로 프롬프트에 줘도 모델은 다르게 썼다 —
    #:   설득으로는 안 되는 자리다.
    #: ★ 그래서 결정을 **초안 밖에** 적어 두고, 초안을 읽을 때마다 그 위에 다시 얹는다.
    #:   읽는 곳이 하나이므로(컴파일러·pending·합산기 전부 이 함수를 지난다) 여기서
    #:   얹으면 모두가 같은 것을 본다.
    #: ⚠️ 지우는 것이 아니라 **정해진 쪽으로 맞추는 것**이다 — 원본 초안은 그대로 두고
    #:   메모리에서만 얹는다. 다음에 사람이 다시 정하면 그 값이 이긴다.
    return _with_resolutions(workspace_root, out)


def resolutions_path(workspace_root: str) -> str:
    """사람이 내린 결정의 **지속 기록**. 초안과 나란히 둔다."""
    return os.path.join(draft_dir(workspace_root), "_resolutions.json")


def record_dataset_resolution(workspace_root: str, dataset_key: str,
                              winner_task_id: str) -> None:
    """데이터셋 충돌 결정을 남긴다 — 초안이 다시 써져도 살아남게."""
    path = resolutions_path(workspace_root)
    doc = _read_json(path)
    doc = doc if isinstance(doc, dict) else {}
    doc.setdefault("datasets", {})[str(dataset_key)] = str(winner_task_id)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def _with_resolutions(workspace_root: str,
                      drafts: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """기록된 결정을 초안 위에 얹는다. **기록이 없으면 그대로 돌려준다.**"""
    doc = _read_json(resolutions_path(workspace_root))
    picks = (doc or {}).get("datasets") if isinstance(doc, dict) else None
    if not isinstance(picks, dict) or not picks:
        return drafts
    for key, winner in picks.items():
        win = drafts.get(str(winner))
        if not isinstance(win, dict):
            continue                       # 이긴 초안이 사라졌으면 얹을 것이 없다
        src = next((d for d in (win.get("datasets") or [])
                    if str((d or {}).get("name", "")) == str(key)), None)
        if src is None:
            continue
        for tid, draft in drafts.items():
            if tid == winner or not isinstance(draft, dict):
                continue
            dss = draft.get("datasets")
            if not isinstance(dss, list):
                continue
            for i, d in enumerate(dss):
                if str((d or {}).get("name", "")) == str(key):
                    dss[i] = json.loads(json.dumps(src))     # 깊은 복사
    return drafts


def save_draft(workspace_root: str, task_id: str, draft: Dict[str, Any]) -> str:
    """태스크 하나의 **계약 초안**을 저장한다. 돌려주는 것은 저장 경로.

    ## ⚠️⚠️ [2026-08-25 실측] 이 함수가 **없었다**

    `load_drafts()` 는 처음부터 있었는데 **쓰는 곳이 저장소 어디에도 없었다**(전수 확인:
    `contracts/drafts` 를 언급하는 코드는 이 파일의 읽기 쪽뿐이었다). 그래서 SW 생성기가
    Tech Lead 를 지나 계약 컴파일러에 오면 언제나:

        「계약 대상 태스크인데 계약 초안이 없습니다: … Tech Lead 가 초안을 만들어야 합니다.」

    가 나오고, 지문이 비어 `TerminalHandler` 로 빠졌다 — 사용자가 본 「계약이 생성되지
    않아 전달이 실패」가 이것이다. **읽는 곳은 있는데 쓰는 곳이 없었다.**

    ★ 초안의 모양은 합산기(`core/project_contract_aggregator.aggregate`)가 정한다:

        {"app_class": "...", "datasets": [...], "capability_intents": [...]}

    ⚠️ 여기서 **검증하지 않는다.** 초안은 «아직 다듬는 중» 인 것이고, 판정은 합산기와
      컴파일러가 한다. 여기서 한 번 더 막으면 같은 규칙이 두 곳에 생긴다.
    ⚠️ 다만 **모양이 아닌 것은 저장하지 않는다** — 깨진 것을 저장하면 `load_drafts` 가
      「초안이 있다」고 읽고, 합산기는 그것을 데이터셋 0개로 본다."""
    if not isinstance(draft, dict):
        raise TypeError("계약 초안은 객체여야 합니다.")
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("어느 태스크의 초안인지 없습니다.")
    d = draft_dir(workspace_root)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{tid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    return path


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


def stamp_approval(workspace_root: str, *, fingerprint: str, actor_id: str = "",
                   ledger_event_id: str = "") -> str:
    """승인을 **계약 정본에** 남긴다. 성공하면 `""`, 실패하면 사람이 읽을 사유.

    ## ⚠️⚠️ [2026-08-26 실측] 왜 이 함수가 생겼는가 — 승인해도 완주가 안 됐다

    승인은 원장에 남고 **체크포인트 상태**(`approved_contract_fingerprint`)에 반영됐다.
    그런데 컴파일러의 승인 이월은 **디스크의 계약 파일**을 본다:

        if previous and not changed:                     # host_contract_compiler.py
            if previous["approval"]["status"] == "APPROVED": ...

    그 파일에 승인을 쓰는 곳이 **어디에도 없었다.** 그래서 재가동할 때마다

        Tech_Lead → 컴파일 → 게이트 「지문은 같지만 상태가 COMPILED」 → 승인 대기

    가 **끝없이 반복**됐다. 사용자는 승인을 눌러도 코드가 나오지 않는다.
    ★ 쓰는 곳과 찾는 곳의 출처가 갈리면, 양쪽 다 200 을 돌려주면서 아무 일도 안 한다.

    ## 무엇을 지키는가

    ⚠️⚠️ **파일의 지문이 승인된 지문과 같을 때만 찍는다.** 다르면 「사람이 A 를 보고
      B 를 승인한」 것이 되고, 그 승인은 승인이 아니다. 그 자리는 재승인이 맞다.
    ⚠️ 던지지 않는다 — 결정은 **이미 원장에 있다.** 파일 기록 실패가 승인을 되돌리면
      안 되므로, 사유를 돌려주어 호출부가 사람에게 그대로 전하게 한다.
    """
    from core import app_runtime_contract as arc

    fp = (fingerprint or "").strip()
    if not fp:
        return "승인할 계약 지문이 없습니다."
    path = contract_path(workspace_root)
    contract = _read_json(path)
    if not isinstance(contract, dict) or not contract:
        return f"계약 정본을 읽지 못했습니다({path}) — 승인은 기록됐지만 계약에 반영하지 못했습니다."

    on_disk = str(contract.get("semantic_fingerprint", ""))
    if on_disk != fp:
        return (f"계약 정본의 지문({on_disk[:12] or '없음'}…)이 승인한 지문({fp[:12]}…)과 "
                f"다릅니다 — 그 사이에 계약이 바뀌었습니다. 다시 검토하십시오.")

    from datetime import datetime, timezone
    contract["status"] = arc.STATUS_APPROVED
    #: ★ 모양은 `core/kit_app_contract.py` 의 승인 도장과 같다 — 두 곳이 다른 봉투를
    #:   쓰면 읽는 쪽이 한쪽만 알아본다.
    contract["approval"] = {"status": "APPROVED", "approved_by": str(actor_id or ""),
                            "approved_at": datetime.now(timezone.utc).isoformat(),
                            "decision_ledger_id": str(ledger_event_id or "")}
    #: ⚠️ 봉투를 바꿨으면 정본 검증기를 **다시** 지난다 — 내가 만든 흠을 내가 봐주지 않는다.
    errs = arc.validate(contract)
    if errs:
        return "승인 도장을 찍은 계약이 검증을 통과하지 못했습니다: " + " / ".join(errs[:3])

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(contract, f, ensure_ascii=False, indent=2)
    except Exception as e:                                # pragma: no cover - 방어
        return f"계약 정본에 승인을 기록하지 못했습니다({e})."
    return ""


def adapter_path(workspace_root: str) -> str:
    from core.typed_sdk_adapter import ADAPTER_PATH
    return os.path.join(workspace_root or ".", *ADAPTER_PATH.split("/"))


def _write_adapter(workspace_root: str, contract: Dict[str, Any]) -> str:
    """어댑터를 쓰고 **사람이 읽을 한 줄**을 돌려준다. 던지지 않는다.

    ⚠️ 승인되지 않은 계약이면 만들지 않는다 — 그리고 그 사실을 말한다. 아무 말 없이
      건너뛰면 「생성이 실패했다」와 「아직 승인 전이다」가 같은 모양이 된다."""
    from core import typed_sdk_adapter

    result = typed_sdk_adapter.generate(contract)
    if not result.ok:
        return f"어댑터 미생성({result.reason})"
    path = adapter_path(workspace_root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(result.source)
    except Exception as e:                                # pragma: no cover - 방어
        return f"어댑터 기록 실패({e})"
    return f"어댑터 {len(result.dataset_names)}개 데이터셋"


def _tasks_in_contract_scope(tasks: List[Dict[str, Any]], drafts: Dict[str, Any],
                             current_task_id: str) -> List[Dict[str, Any]]:
    """지금 계약에 합산할 태스크만 남긴다.

    ## ⚠️⚠️ [2026-08-26 실측] 왜 걸러야 하는가 — 교착이었다

    합산기는 **계약 대상 태스크 전부**의 초안을 요구한다. 그런데 초안은 그 태스크의
    Tech Lead 가 만들고, 그 Tech Lead 는 **컴파일러를 지나야** 돈다. 그래서 WBS 에
    APP 태스크가 뒤에 하나라도 있으면:

        TASK-01(LIBRARY) 가동 → Tech Lead → 컴파일러
          → 「계약 대상 태스크인데 계약 초안이 없습니다: TASK-03」 → CONTRACT_BLOCKED

    TASK-03 은 아직 **시작도 안 했는데** 그 초안을 요구한다. 실제 가동에서 그대로
    재현됐다(live-walk-02). 앞 태스크가 뒤 태스크의 미래를 기다리는 교착이다.

    ## 규칙 — 초안을 **요구하는 것은 지금 도는 태스크 하나뿐**이다

        남긴다:  ① 지금 도는 태스크         (상태와 무관하게 **언제나**)
                 ② 초안이 이미 있는 태스크   (합산해야 데이터가 안 사라진다)
        뺀다:    그 밖의 계약 대상 태스크    (아직 초안이 없다 = 아직 만들 것이 없다)

    ★ 통제는 **쓰이는 자리에서** 지켜진다. 어떤 태스크가 계약 없이 코드를 만들 수 있는
      순간은 **그 태스크가 도는 때뿐**이고, 그때 이 함수는 ①로 그것을 반드시 요구한다.
      TASK-03 이 초안을 안 남겼다고 **TASK-02 를** 막는 것은 아무것도 지키지 못한다 —
      TASK-03 은 지금 아무것도 만들고 있지 않다.

    ⚠️⚠️ 처음에는 「이미 손댄(IN_PROGRESS·DONE) 태스크가 초안을 안 남긴 것은 오류」로
      두었다. 그런데 **종결 롤백이 `contracts/drafts/*.json` 을 지운다**(커밋 전이므로).
      그래서 APP 태스크가 한 번 실패하면 「손댔는데 초안이 없는」 상태로 굳고, 그때부터
      **다른 모든 태스크가 영영 막혔다** — 실측에서 TASK-02 가 그렇게 죽었다.
      상태(status)로 판단하지 않는 이유가 이것이다. 초안의 존재만 본다.

    ⚠️ 나중에 빠진 태스크가 돌면 데이터셋이 붙고 **지문이 바뀌어 재승인을 지난다** —
      이 저장소가 원래 설계해 둔 그 경로다([4c-1] 의 데이터 소실도 생기지 않는다.
      초안이 없는 태스크에는 합산할 데이터셋이 애초에 없다).
    """
    keep, dropped = [], []
    for t in (tasks or []):
        tid = str(t.get("task_id", ""))
        if tid == current_task_id or tid in (drafts or {}):
            keep.append(t)
        else:
            dropped.append(tid)
    if dropped:
        #: ★ 조용히 빼지 않는다 — 「계약에 무엇이 들어갔나」는 승인의 근거다.
        print(f"ℹ️ [HostContractCompiler] 아직 시작하지 않은 태스크는 이번 계약에서 "
              f"제외합니다({', '.join(dropped)}) — 그 태스크가 돌면 지문이 바뀌어 "
              f"다시 검토를 지납니다.")
    return keep


async def run_host_contract_compiler(state: Any) -> Dict[str, Any]:
    """WBS 의 계약 대상 태스크 초안을 **프로젝트 계약 하나**로 컴파일한다.

    ⚠️ 태스크 하나씩 컴파일하면 뒤 태스크의 계약이 앞 태스크를 덮어 데이터셋이
      소실된다([4c-1]). 그래서 언제나 WBS 전체를 다시 합산한다 — 그 덕에 태스크가
      삭제되면 자연히 계약에서도 빠지고, 지문이 바뀌어 재승인을 지난다."""
    st = ProjectState.model_validate(state)
    ws = st.workspace_root or ""
    tasks = _wbs_tasks(ws)
    previous = _read_json(contract_path(ws))

    #: ★★★ [2026-08-25 실측] **WBS 를 못 읽은 것을 «계약이 잘못됐다» 로 말하지 않는다.**
    #:
    #: ⚠️⚠️ WBS 가 없거나 비면 계약 대상이 0건이 되고, 합산기는 막지 않는다(막을 것이
    #:   없으므로). 그러면 **빈 초안**이 컴파일러로 가서 「app_class 가 …중 하나여야
    #:   합니다(현재 (없음))」로 죽는다. 사용자는 「분류를 안 골랐나?」를 찾아 헤매지만
    #:   진짜 원인은 **WBS 를 못 읽은 것**이다 — 사유가 원인을 가리키지 않으면 사람은
    #:   영영 엉뚱한 곳을 고친다.
    #: ★ 여기서 먼저 말한다. `normalize_tasks` 머리말이 「WBS 전체를 못 읽는 것이 태스크
    #:   하나를 못 읽는 것보다 나쁘다」고 적어 둔 것과 같은 방향이다.
    if not tasks:
        reason = ("WBS 를 읽지 못했습니다(태스크 0건) — 계약을 만들 대상이 없습니다. "
                  "기획이 WBS 를 남겼는지 먼저 확인하십시오.")
        print(f"⛔ [HostContractCompiler] {reason}")
        return {
            "app_runtime_contract_status": "DRAFT",
            "app_runtime_contract_fingerprint": "",
            "app_runtime_contract_summary": reason,
            "terminal_status": "CONTRACT_BLOCKED",
            "terminal_reason": reason,
            "supervisor_feedback": reason,
        }

    drafts = load_drafts(ws)
    tasks = _tasks_in_contract_scope(tasks, drafts, st.current_sprint_task_id or "")

    #: ★★★ 이번 범위에 **계약 대상이 하나도 없으면** 만들 계약이 없다.
    #:
    #: ⚠️⚠️ 그냥 컴파일하면 빈 초안이 들어가 「app_class 가 … 중 하나여야 합니다(현재
    #:   (없음))」로 죽는다 — WBS 를 못 읽었을 때와 **똑같은 거짓 사유**다(바로 위 갈래가
    #:   그 사고를 기록해 두었다). 사용자는 분류를 고르러 헤매지만 진짜 사실은
    #:   「이 태스크는 계약이 필요 없다」이다.
    #: ★ 종결 상태를 세우지 않는다. 판정은 검토 게이트가 `NOT_APPLICABLE` 로 내린다 —
    #:   판정하는 곳은 하나여야 한다.
    if not artifact_kind.contract_required_task_ids(tasks):
        note = ("이번 범위에 계약이 필요한 산출물이 없습니다 — 계약을 만들지 않고 "
                "다음 단계로 넘어갑니다.")
        print(f"ℹ️ [HostContractCompiler] {note}")
        return {"app_runtime_contract_status": "",
                "app_runtime_contract_fingerprint": "",
                "app_runtime_contract_summary": note}

    result, agg = aggregator.compile_project_contract(
        tasks, drafts, project_id=os.path.basename(ws.rstrip("/\\")) or st.project_name,
        previous=previous if isinstance(previous, dict) else None)
    contract = result.contract
    required = artifact_kind.contract_required_task_ids(tasks)

    if result.errors:
        #: ⚠️ 실패해도 **정본 파일을 덮지 않는다.** 덮으면 「무엇이 승인돼 있었는가」를
        #:   잃고, 고칠 근거까지 사라진다.
        print("⛔ [HostContractCompiler] 계약을 만들지 못했습니다:")
        for e in result.errors[:8]:
            print(f"   · {e}")
        #: ★★★ [2026-08-25 사용자 실측] **종결 상태를 여기서 확정한다.**
        #:
        #: ⚠️⚠️ 종전에는 지문만 비워 돌려줬다. 그러면 `route_from_contract_compiler` 가
        #:   `TerminalHandler` 로 보내고, 그 노드는 `terminal_status` 가 비어 있으니
        #:   **「FAILED_BUILD — 빌드 자가복구 N회 소진」** 으로 확정했다.
        #:   사용자가 본 「자가복구 실패했다고 하고 생성 실패」가 이것이다.
        #:
        #:   계약을 못 만든 것은 **코드가 빌드되지 않은 것이 아니다.** 뭉개면
        #:   「모델이 형식을 못 맞췄다」와 「사람이 계약을 정해야 한다」가 같은 화면이 되고,
        #:   사용자는 **재시도만 반복한다** — `state_models` 의 `CONTRACT_BLOCKED` 주석이
        #:   정확히 그 위험을 경고해 두었는데, 세우는 곳이 검토 게이트뿐이었다.
        #: ★ 사유는 **합산기가 준 말 그대로** 싣는다. 여기서 새 문구를 지으면 같은 사실이
        #:   두 가지로 설명된다.
        reason = ("계약을 만들지 못해 다음 단계로 넘어갈 수 없습니다: "
                  + " / ".join(result.errors[:4]))
        return {
            "app_runtime_contract_status": "DRAFT",
            "app_runtime_contract_fingerprint": "",
            "app_runtime_contract_summary": "; ".join(result.errors[:4]),
            "terminal_status": "CONTRACT_BLOCKED",
            "terminal_reason": reason,
            "supervisor_feedback": reason,
            "unsupported_requirements": contract.get("unsupported_requirements") or [],
            "capability_intents": contract.get("capability_intents") or [],
        }

    os.makedirs(os.path.join(ws, CONTRACT_DIR), exist_ok=True)
    with open(contract_path(ws), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    fp = str(contract.get("semantic_fingerprint", ""))

    #: ── [I-4 5a] Typed SDK Adapter ─────────────────────────────────────
    #:
    #: ⚠️ **승인 전에는 만들지 않는다.** 만들면 앱 코드가 승인 전 계약에 맞춰
    #:   작성되고, 계약이 바뀌면 코드가 통째로 어긋난다. 승인 직후 재컴파일에서
    #:   나온다(지문이 같으면 컴파일러가 승인을 이어 준다).
    #: ⚠️ 어댑터 생성 실패가 계약 컴파일을 되돌리지 않는다 — 계약은 이미 정본이고,
    #:   어댑터는 그 투영이다. 다만 **조용히 넘기지 않는다.**
    adapter_note = _write_adapter(ws, contract)

    print(f"[OK] [HostContractCompiler] 계약 컴파일 — 지문 {fp[:12]}… · "
          f"대상 태스크 {len(agg.included_task_ids)}개" + (f" · {adapter_note}" if adapter_note else ""))
    return {
        "app_runtime_contract_status": str(contract.get("status", "COMPILED")),
        "app_runtime_contract_fingerprint": fp,
        "app_runtime_contract_summary": _summary(contract, required),
        "unsupported_requirements": contract.get("unsupported_requirements") or [],
        "capability_intents": contract.get("capability_intents") or [],
    }


def _with_project_approval(st: Any, workspace_root: str) -> Dict[str, Any]:
    """게이트가 볼 상태에 **프로젝트 단위 승인 기억**을 이어 붙인다.

    ## ⚠️⚠️ [2026-08-26 실측] 승인 기억의 범위가 계약의 범위와 달랐다

    계약은 **프로젝트 하나**인데(`compile_project_contract` 가 WBS 전체를 합산한다),
    `approved_contract_fingerprint` 는 **체크포인트**에 산다. 체크포인트의 단위는
    `project__task` 이므로 태스크가 바뀌면 그 기억이 비어 있다. 그래서 실측에서:

        · 태스크마다 **같은 계약을 다시 승인**받았다(5개 태스크 = 5번).
        · 문구가 「이 프로젝트의 **최초 계약**입니다」였다 — 이미 승인된 계약이 있는데도.
          사실이 아닌 말을 화면이 하면, 사람은 다음번에 그 화면을 믿지 않는다.

    ★ 계약 정본(`contracts/app_runtime_contract.json`)에는 승인이 남아 있다
      (`approval.status` · `semantic_fingerprint`) — `stamp_approval` 이 찍는다.
      **계약과 같은 범위에 있는 그 기록**을 승인 기억으로 쓴다.

    ⚠️ 상태에 값이 있으면 그것이 이긴다. 반려는 상태를 비우는데(`""`), 그때는 정본의
      옛 승인(다른 지문)으로 떨어지므로 판정이 `REVIEW_REQUIRED` 로 남는다 — 반려의
      뜻이 유지되고, 사유도 「최초 계약」이 아니라 「지문이 바뀌었다」로 정확해진다.
    ⚠️ `approval.status` 가 `APPROVED` 일 때만 읽는다. 「승인 봉투가 있다」와
      「승인됐다」는 다르다 — `PENDING`·`REJECTED` 를 승인으로 읽으면 게이트가 사라진다.
    """
    #: ⚠️ 상태는 **객체로도 dict 로도** 온다 — 그래프 노드는 `ProjectState`, API 는
    #:   체크포인트에서 읽은 dict 다. 한쪽만 받으면 그쪽만 이 기억을 쓰고, 그러면
    #:   「화면은 승인을 요구하는데 파이프라인은 자동 통과」가 된다(2026-08-26 실측).
    def _read(name: str) -> str:
        if isinstance(st, dict):
            return str(st.get(name, "") or "")
        return str(getattr(st, name, "") or "")

    view = {
        "app_runtime_contract_fingerprint": _read("app_runtime_contract_fingerprint"),
        "approved_contract_fingerprint": _read("approved_contract_fingerprint"),
        "app_runtime_contract_status": _read("app_runtime_contract_status"),
    }
    if view["approved_contract_fingerprint"]:
        return view

    contract = _read_json(contract_path(workspace_root))
    if not isinstance(contract, dict):
        return view
    if str((contract.get("approval") or {}).get("status", "")) != "APPROVED":
        return view
    fp = str(contract.get("semantic_fingerprint", "") or "")
    if not fp:
        return view

    view["approved_contract_fingerprint"] = fp
    #: ★ 상태 필드도 함께 이어 준다. 지문만 이어 주면 「지문은 같은데 상태가 COMPILED」로
    #:   또 막힌다 — 그것이 정확히 무한 재승인의 모양이었다(같은 파일 `stamp_approval` 참조).
    if not view["app_runtime_contract_status"]:
        view["app_runtime_contract_status"] = str(contract.get("status", "") or "")
    return view


async def run_contract_review_gate(state: Any) -> Dict[str, Any]:
    """최초 계약 또는 지문 변경이면 **검토 요청을 원장에 열고** 멈춘다.

    ⚠️ 요청 기록에 실패하면 **진행하지 않는다.** 요청 없이 지나가면 승인 이력이
      없는 승인이 생기고, 그것은 승인이 아니다."""
    st = ProjectState.model_validate(state)
    ws = st.workspace_root or ""
    project_id = os.path.basename(ws.rstrip("/\\")) or st.project_name
    #: ★★★ 컴파일러와 **같은 범위**를 본다.
    #:
    #: ⚠️⚠️ [2026-08-26 실측] 컴파일러는 「아직 시작 안 한 태스크」를 빼는데 게이트는
    #:   WBS 전체로 판정했다. 그래서 컴파일러가 「이번엔 계약 대상이 없다」고 통과시킨
    #:   태스크를 게이트가 「계약 대상인데 컴파일된 계약이 없다」로 막았다 —
    #:   **두 계층의 답이 갈리면 통제가 아니라 교착이 된다**([I-4 2.2a] 와 같은 종류).
    tasks = _tasks_in_contract_scope(_wbs_tasks(ws), load_drafts(ws),
                                     st.current_sprint_task_id or "")
    decision, required = gate.evaluate_project(tasks, _with_project_approval(st, ws))

    if decision.verdict == gate.AUTO_PASS:
        print("[OK] [ContractReviewGate] 승인된 계약과 지문이 같습니다 — 자동 통과.")
        return {"contract_review_request_event_id": ""}

    if decision.verdict == gate.NOT_APPLICABLE:
        print("[OK] [ContractReviewGate] 계약이 필요 없는 산출물입니다.")
        return {"contract_review_request_event_id": ""}

    if decision.verdict == gate.BLOCKED:
        print(f"⛔ [ContractReviewGate] {decision.reason}")
        #: ⚠️⚠️ [2026-08-26 실측] `terminal_reason` 을 함께 세운다. 종전에는 상태만
        #:   찍고 사유를 안 세워서, 화면과 로그에 **직전 실패의 사유가 그대로 남았다.**
        #:   실제로 그것 때문에 「컴파일러가 못 만들었다」고 한참을 잘못 짚었다 —
        #:   진짜 원인은 게이트였다. 사유가 원인을 가리키지 않으면 사람은 영영
        #:   엉뚱한 곳을 고친다(같은 파일 위쪽이 경고해 둔 그 결함이다).
        return {"terminal_status": "CONTRACT_BLOCKED",
                "terminal_reason": decision.reason,
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
