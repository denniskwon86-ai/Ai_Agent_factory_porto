"""품질 결과 텔레메트리 — 명세서 §10.3 `quality_outcomes` + §8.3 실패 원인 분류. **LLM 0콜.**

`llm_calls`(`core/llm_gateway.py::_log_llm_call`)는 "무엇을 얼마에 불렀는가"만 남긴다.
그것으로는 **"그래서 통과했는가, 왜 실패했는가, 사람이 받아들였는가"** 를 알 수 없다.
§10.4 의 비용 절감 규칙도, §8.3 의 "재시도 횟수만 늘리지 않는다"도 이 데이터가 없으면
근거 없이 추측하는 조정이 된다.

## 이 모듈이 지키는 세 가지 규칙

1. **원인을 지어내지 않는다.** 결정론적 신호(생성 실패 kind, 빌드 로그 패턴, 심판 인프라 오류)로
   판정되는 것만 분류하고, 나머지는 `unclassified` 로 남긴다. 점수 미달을 보고 "모델 품질이
   나빴다"고 적는 순간 그 통계는 근거가 아니라 창작이 된다. 대신 **어떤 기준이 미달이었는지는
   사실 그대로**(`rework_reason`) 남기고, 사람이 나중에 분류할 수 있게 `outcome_id` 를 준다.
2. **모든 분류에 근거(rule id)를 함께 적는다**(`root_cause_rule`). 나중에 분류 규칙이 틀렸다는
   것이 드러나도 어느 규칙이 만든 값인지 알면 되돌릴 수 있다.
3. **"사람이 승인함"과 "사람에게 묻지 않음"을 절대 같은 칸에 두지 않는다.** 거버넌스 콘솔에서
   `unverifiable`/`kept` 를 분리한 것과 같은 이유다 — 안 물어본 것이 승인으로 읽히면 이 지표는
   위험한 거짓이 된다.

## 저장

`data/quality_outcomes.jsonl` **append-only**. `llm_call_log.jsonl` 과 같은 규약이다.
사람의 수용 판정과 사후 분류는 **원본 줄을 고치지 않고 별도 이벤트로 덧붙인다**(감사 추적 보존).
읽을 때 `outcome_id` 로 접합한다.

기록 실패가 파이프라인을 멈추면 안 된다 — 모든 예외를 삼킨다(부가 계측).
"""
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from core.paths import data_path

_LOG_PATH = data_path("quality_outcomes.jsonl")

# ── §8.3 실패 원인 분류 (이 6개가 명세가 정한 전부) ──────────────────────────
CAUSE_MODEL_QUALITY = "model_quality"              # 모델 품질
CAUSE_INSUFFICIENT_CONTEXT = "insufficient_context"  # 문맥 부족
CAUSE_OUTPUT_CONTRACT = "output_contract"          # 출력 계약
CAUSE_EXTERNAL_ENV = "external_environment"        # 외부 환경
CAUSE_TEST_HARNESS = "test_harness"                # 테스트 하네스
CAUSE_REQUIREMENT_AMBIGUITY = "requirement_ambiguity"  # 요구사항 모호성

#: 아직 모른다. **분류 실패가 아니라 정직한 상태값이다.**
CAUSE_UNCLASSIFIED = "unclassified"

CAUSES: Tuple[str, ...] = (
    CAUSE_MODEL_QUALITY, CAUSE_INSUFFICIENT_CONTEXT, CAUSE_OUTPUT_CONTRACT,
    CAUSE_EXTERNAL_ENV, CAUSE_TEST_HARNESS, CAUSE_REQUIREMENT_AMBIGUITY,
)

# 사람이 사후 분류할 때 허용되는 값 = 6개 원인만(unclassified 로 되돌리는 것은 허용).
ASSIGNABLE_CAUSES: Tuple[str, ...] = CAUSES + (CAUSE_UNCLASSIFIED,)

# 사람의 수용 판정 (§10.3 `human_acceptance`)
HUMAN_ACCEPTED = "accepted"
HUMAN_REVISION_REQUESTED = "revision_requested"


# ── 분류 규칙 ────────────────────────────────────────────────────────────────
# ⚠️ `GenerationFailure.kind` 는 이미 게이트웨이가 결정론적으로 판정해 둔 값이다
#   (429/타임아웃/파싱실패…). 그것을 §8.3 어휘로 옮기기만 한다 — 새로 추측하지 않는다.
_KIND_TO_CAUSE: Dict[str, str] = {
    "PROVIDER_TIMEOUT": CAUSE_EXTERNAL_ENV,
    "NETWORK": CAUSE_EXTERNAL_ENV,
    "QUOTA": CAUSE_EXTERNAL_ENV,
    "STRUCTURED_PARSE": CAUSE_OUTPUT_CONTRACT,
    "CAPACITY": CAUSE_OUTPUT_CONTRACT,
}


def classify_generation_kind(kind: str) -> Tuple[str, str]:
    """생성 실패 kind → (원인, 규칙 id). 매핑에 없으면 미분류."""
    cause = _KIND_TO_CAUSE.get((kind or "").upper())
    if cause:
        return cause, f"gen_kind:{(kind or '').upper()}"
    return CAUSE_UNCLASSIFIED, ""


# 빌드/검사 로그 패턴 → 원인. **순서가 의미를 가진다.**
#   ① 우리가 직접 만든 무결성 가드 메시지(가장 확실) → 출력 계약
#   ② 외부 환경(네트워크·레지스트리·인증서) — 코드 결함으로 오인되면 개발자 재작업 예산을 태운다
#   ③ 테스트 하네스 자체의 오류 — 산출물 결함이 아니다
#   ④ 생성된 코드의 구문 결함 → 모델 품질
# 어디에도 걸리지 않으면 **분류하지 않는다.**
_BUILD_RULES: List[Tuple[str, str, Tuple[str, ...]]] = [
    (CAUSE_OUTPUT_CONTRACT, "build:empty_or_truncated",
     ("산출물이 비어 있습니다", "출력 절단", "파싱 실패", "json 파싱", "length limit")),
    (CAUSE_EXTERNAL_ENV, "build:network_or_registry",
     ("enotfound", "econnrefused", "etimedout", "getaddrinfo", "registry.npmjs.org",
      "network error", "proxy", "ssl:", "certificate verify failed", "429", "rate limit")),
    (CAUSE_TEST_HARNESS, "build:harness",
     ("pytest: error", "internalerror", "collection error", "errors during collection",
      "no tests ran", "unrecognized arguments", "conftest.py")),
    (CAUSE_MODEL_QUALITY, "build:syntax_or_missing_symbol",
     ("syntaxerror", "indentationerror", "unexpected token", "unterminated",
      "is not defined", "cannot find module", "modulenotfounderror", "importerror",
      "nameerror", "attributeerror", "type error", "ts(")),
]


def classify_build_error(error_log: str) -> Tuple[str, str]:
    """빌드/실행 오류 로그 → (원인, 규칙 id). 판정 근거가 없으면 `unclassified`.

    ⚠️ 여기서 억지로 하나를 고르면 통계가 그럴듯해지지만 **틀린 방향의 개선**을 유도한다.
      실측 사례가 있다: 공급자 타임아웃이 '빌드 실패'로 취급돼 개발자 재작업 예산 3회를
      대기로 날렸다(`core/llm_gateway.py` 상단 주석). 오분류의 비용은 미분류보다 크다."""
    low = (error_log or "").lower()
    if not low.strip():
        return CAUSE_UNCLASSIFIED, ""
    for cause, rule, needles in _BUILD_RULES:
        for n in needles:
            if n in low:
                return cause, rule
    return CAUSE_UNCLASSIFIED, ""


# ── 기록 ─────────────────────────────────────────────────────────────────────
def _identity(state_obj: Any) -> Dict[str, str]:
    """프로젝트·부서 식별. `llm_call_log` 와 **같은 규약**(basename)을 써야 두 로그를 붙일 수 있다."""
    ws = str(getattr(state_obj, "workspace_root", "") or "")
    pid = os.path.basename(ws.rstrip("/\\")) if ws else ""
    return {
        "project": str(getattr(state_obj, "project_name", "") or ""),
        "project_id": pid,
        "owner_dept_id": str(getattr(state_obj, "owner_dept_id", "") or ""),
        # [D-019] 조직 노드 병기 — `llm_call_log` 와 **같은 필드명**이어야 두 로그가 같은 축으로 붙는다.
        "owner_scope_node_id": str(getattr(state_obj, "owner_scope_node_id", "") or ""),
        "task_id": str(getattr(state_obj, "current_sprint_task_id", "") or ""),
    }


class StateRef:
    """식별 필드만 가진 경량 상태 대역.

    오케스트레이터의 체크포인트 상태는 **dict 일 수도, ProjectState 일 수도** 있다(langgraph
    버전·경로에 따라 다르다). 호출부에서 그때그때 분기하면 한쪽 형태에서만 조용히 기록이
    빠진다 — 그 분기를 여기 한 곳에 가둔다."""

    def __init__(self, state: Any, workspace_root: str = "", task_id: str = ""):
        def _g(key: str) -> str:
            if isinstance(state, dict):
                return str(state.get(key, "") or "")
            return str(getattr(state, key, "") or "")
        self.project_name = _g("project_name")
        self.workspace_root = workspace_root or _g("workspace_root")
        self.owner_dept_id = _g("owner_dept_id")
        # [D-019] 여기에 안 실으면 체크포인트 경로의 품질 로그만 조직 노드가 조용히 빈다 —
        #   이 클래스가 존재하는 이유(한쪽 형태에서만 기록이 빠지는 것)를 그대로 되풀이하게 된다.
        self.owner_scope_node_id = _g("owner_scope_node_id")
        self.current_sprint_task_id = task_id or _g("current_sprint_task_id")
        self.current_stage = _g("current_stage")
        self.supervisor_hops = 0
        self.developer_retry_count = 0


def _append(rec: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 계측이 파이프라인을 막지 않는다


def record_gate(state_obj: Any, gate_name: str, artifact_type: str, verdict: str,
                score: Optional[float] = None, threshold: Optional[float] = None,
                blocking_fails: Optional[List[str]] = None,
                failed_checks: Optional[List[str]] = None,
                root_cause: str = CAUSE_UNCLASSIFIED, root_cause_rule: str = "",
                rework_reason: str = "") -> str:
    """게이트 판정 1건을 기록하고 `outcome_id` 를 돌려준다(사후 분류·수용 판정의 접합 키).

    `verdict` 는 원문 그대로 남긴다(PASS/REWORK/ROLLBACK/FAIL) — PASS 여부로 압축해 버리면
    "반려"와 "치명 미달 롤백"의 차이가 사라진다. `pass_fail` 은 그 위의 파생값이다."""
    oid = uuid.uuid4().hex[:16]
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "gate",
        "outcome_id": oid,
        **_identity(state_obj),
        "artifact_type": artifact_type or "",
        "gate_name": gate_name or "",
        "verdict": verdict or "",
        "pass_fail": "PASS" if (verdict or "").upper() == "PASS" else "FAIL",
        "score": score,
        "threshold": threshold,
        # ★ 재시도 축이 둘이다. 하나로 합치면 "코드가 3번 깨졌다"와 "검수를 3번 반려당했다"가
        #   구분되지 않는다 — 처방이 완전히 다른 두 상황이다.
        "gate_loops": int(getattr(state_obj, "supervisor_hops", 0) or 0),
        "dev_retry_count": int(getattr(state_obj, "developer_retry_count", 0) or 0),
        "blocking_fails": list(blocking_fails or []),
        "failed_checks": list(failed_checks or []),
        "root_cause": root_cause or CAUSE_UNCLASSIFIED,
        "root_cause_rule": root_cause_rule or "",
        "rework_reason": rework_reason or "",
        "stage": str(getattr(state_obj, "current_stage", "") or ""),
    }
    _append(rec)
    return oid


def record_failure(state_obj: Any, gate_name: str, artifact_type: str,
                   kind: str = "", error_log: str = "", detail: str = "") -> str:
    """실패(생성 실패·빌드 실패·심판 인프라 오류)를 원인 분류와 함께 기록한다.

    `kind` 가 있으면 게이트웨이 분류를 그대로 옮기고, 없으면 로그 패턴으로 판정한다.
    둘 다 근거가 없으면 `unclassified` — 그것이 사실이다."""
    if kind:
        cause, rule = classify_generation_kind(kind)
    else:
        cause, rule = classify_build_error(error_log)
    return record_gate(
        state_obj, gate_name=gate_name, artifact_type=artifact_type, verdict="FAIL",
        root_cause=cause, root_cause_rule=rule,
        rework_reason=(detail or error_log or "")[:600],
    )


def record_human_decision(state_obj: Any, gate_name: str, accepted: bool,
                          actor: str = "", feedback: str = "",
                          outcome_id: str = "") -> None:
    """사람의 수용/반려 판정 (§10.3 `human_acceptance`).

    ⚠️ **판정이 없는 것을 승인으로 적지 않는다.** 이 함수가 호출되지 않은 게이트는 집계에서
      `no_human_decision` 으로 남는다 — "안 물어봤다"와 "승인받았다"는 다른 사실이다."""
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "human",
        "outcome_id": outcome_id or "",
        **_identity(state_obj),
        "gate_name": gate_name or "",
        "human_acceptance": HUMAN_ACCEPTED if accepted else HUMAN_REVISION_REQUESTED,
        "actor": actor or "",
        # 반려 사유는 사람이 쓴 문장 그대로가 가장 정확한 `rework_reason` 이다.
        "rework_reason": (feedback or "")[:600],
        "stage": str(getattr(state_obj, "current_stage", "") or ""),
    }
    _append(rec)


def record_classification(outcome_id: str, root_cause: str, actor: str, note: str = "") -> bool:
    """사람이 미분류 실패에 원인을 지정한다(사후 분류).

    원본 줄을 고치지 않고 이벤트를 덧붙인다 — **누가 언제 무엇으로 분류했는지**가 남아야
    분류가 바뀔 때 근거를 되짚을 수 있다. 식별(`actor`) 없는 분류는 받지 않는다.

    ⚠️ 대상 게이트 기록의 **식별(project/부서)을 복사해 넣는다.** 그러지 않으면 부서 스코프
      조회에서 이 줄이 '귀속 불가'로 걸러져, 분류가 기록은 됐는데 **화면에는 영원히 반영되지
      않는** 조용한 유실이 생긴다(생산자→소비자 배선 누락의 전형). 동시에 존재하지 않는
      `outcome_id` 에 대한 분류를 거부하는 검증도 겸한다."""
    if root_cause not in ASSIGNABLE_CAUSES or not outcome_id or not actor:
        return False
    target = next((e for e in read_events()
                   if e.get("event") == "gate" and e.get("outcome_id") == outcome_id), None)
    if target is None:
        return False
    _append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "classification",
        "outcome_id": outcome_id,
        "project": target.get("project", ""),
        "project_id": target.get("project_id", ""),
        "owner_dept_id": target.get("owner_dept_id", ""),
        # [D-019] 원 gate 이벤트가 들고 있던 스냅샷을 **그대로 복사**한다. 여기서 다시 풀면
        #   분류 시점의 조직으로 바뀌어, 같은 사건이 두 노드에 걸쳐 집계된다.
        "owner_scope_node_id": target.get("owner_scope_node_id", ""),
        "root_cause": root_cause,
        "root_cause_rule": "human",
        "actor": actor,
        "note": (note or "")[:600],
    })
    return True


# ── 읽기 ─────────────────────────────────────────────────────────────────────
def read_events(project: str = "", path: str = "") -> List[Dict[str, Any]]:
    """JSONL 전 이벤트를 읽는다. 실행 중 append 되므로 **깨진 줄은 건너뛴다**(전체 폐기 금지)."""
    out: List[Dict[str, Any]] = []
    p = path or _LOG_PATH
    if not os.path.exists(p):
        return out
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if project and (r.get("project") or "") != project:
                    continue
                out.append(r)
    except Exception:
        pass
    return out


def resolve_outcomes(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """게이트 기록에 사후 이벤트(사람 수용·사후 분류)를 접합해 §10.3 한 줄 형태로 만든다.

    사후 분류가 있으면 규칙 분류를 **덮어쓰되**, 규칙이 무엇이었는지(`root_cause_rule`)도
    함께 남긴다(`human`). 사람이 규칙보다 늦게 판단하므로 나중 것이 이긴다."""
    gates = [dict(e) for e in events if e.get("event") == "gate"]
    by_id = {g.get("outcome_id"): g for g in gates if g.get("outcome_id")}
    for g in gates:
        g["human_acceptance"] = None       # ★ None = 판정 없음. False/PASS 로 대체 금지.
        g["human_actor"] = ""
    for e in events:
        ev = e.get("event")
        oid = e.get("outcome_id") or ""
        if ev == "human":
            tgt = by_id.get(oid)
            if tgt is None:
                # 게이트 기록과 짝지어지지 않은 사람 판정(HOTL 재개처럼 게이트 밖에서 온 것).
                # 버리지 않는다 — 마지막에 독립 레코드로 합류시킨다.
                continue
            tgt["human_acceptance"] = e.get("human_acceptance")
            tgt["human_actor"] = e.get("actor") or ""
            if e.get("rework_reason") and not tgt.get("rework_reason"):
                tgt["rework_reason"] = e.get("rework_reason")
        elif ev == "classification":
            tgt = by_id.get(oid)
            if tgt is not None:
                tgt["root_cause"] = e.get("root_cause") or CAUSE_UNCLASSIFIED
                tgt["root_cause_rule"] = "human"
                tgt["classified_by"] = e.get("actor") or ""
    # 짝 없는 사람 판정도 사실이므로 별도 레코드로 보존한다(집계에서 human 축에만 반영).
    orphans = [
        {**e, "artifact_type": e.get("artifact_type", ""), "verdict": "", "pass_fail": "",
         "root_cause": CAUSE_UNCLASSIFIED, "root_cause_rule": "", "orphan_human": True}
        for e in events
        if e.get("event") == "human" and (e.get("outcome_id") or "") not in by_id
    ]
    return gates + orphans


def aggregate(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """§10.3 축(게이트·산출물·원인·사람 수용)으로 집계."""
    gates = [o for o in outcomes if not o.get("orphan_human")]
    totals = {"evaluations": len(gates),
              "passed": sum(1 for g in gates if g.get("pass_fail") == "PASS"),
              "failed": sum(1 for g in gates if g.get("pass_fail") == "FAIL")}

    by_gate: Dict[str, Dict[str, Any]] = {}
    for g in gates:
        k = g.get("gate_name") or "-"
        b = by_gate.setdefault(k, {"evaluations": 0, "passed": 0, "failed": 0,
                                   "rollback": 0, "max_gate_loops": 0, "max_dev_retries": 0})
        b["evaluations"] += 1
        b["passed" if g.get("pass_fail") == "PASS" else "failed"] += 1
        if (g.get("verdict") or "").upper() == "ROLLBACK":
            b["rollback"] += 1
        b["max_gate_loops"] = max(b["max_gate_loops"], int(g.get("gate_loops") or 0))
        b["max_dev_retries"] = max(b["max_dev_retries"], int(g.get("dev_retry_count") or 0))

    by_artifact: Dict[str, Dict[str, int]] = {}
    for g in gates:
        k = g.get("artifact_type") or "-"
        b = by_artifact.setdefault(k, {"evaluations": 0, "passed": 0, "failed": 0})
        b["evaluations"] += 1
        b["passed" if g.get("pass_fail") == "PASS" else "failed"] += 1

    # 원인 분포는 **실패 건에 대해서만** 집계한다(통과 건의 원인은 존재하지 않는다).
    fails = [g for g in gates if g.get("pass_fail") == "FAIL"]
    by_cause: Dict[str, int] = {}
    for g in fails:
        by_cause[g.get("root_cause") or CAUSE_UNCLASSIFIED] = \
            by_cause.get(g.get("root_cause") or CAUSE_UNCLASSIFIED, 0) + 1
    unclassified = by_cause.get(CAUSE_UNCLASSIFIED, 0)

    # ★ 사람 축: 3칸이다. `no_human_decision` 을 승인 쪽에 합치지 않는다.
    human = {"accepted": 0, "revision_requested": 0, "no_human_decision": 0}
    for g in gates:
        ha = g.get("human_acceptance")
        if ha == HUMAN_ACCEPTED:
            human["accepted"] += 1
        elif ha == HUMAN_REVISION_REQUESTED:
            human["revision_requested"] += 1
        else:
            human["no_human_decision"] += 1
    for o in outcomes:
        if o.get("orphan_human"):
            key = "accepted" if o.get("human_acceptance") == HUMAN_ACCEPTED else "revision_requested"
            human[key] += 1

    return {
        "totals": totals,
        "by_gate": by_gate,
        "by_artifact_type": by_artifact,
        "by_root_cause": by_cause,
        "unclassified_failures": unclassified,
        # 실패 중 원인을 아직 모르는 비율. 이 값이 높다는 것은 **지표의 결손**이지
        # 시스템이 건강하다는 뜻이 아니다 — 화면에서 그렇게 읽히게 두면 안 된다.
        "unclassified_ratio": round(unclassified / len(fails), 3) if fails else None,
        "human_acceptance": human,
        "note": ("`no_human_decision` 은 '사람이 승인함'이 아니라 '사람 판정이 없음'이다"
                 "(묻지 않은 게이트 포함). `unclassified` 는 분류 실패가 아니라 "
                 "'결정론적 근거가 없어 분류하지 않음'이다."),
    }


def unclassified_failures(outcomes: List[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    """사람이 분류해야 할 실패 목록(사후 분류 화면의 작업 큐)."""
    out = [o for o in outcomes
           if not o.get("orphan_human")
           and o.get("pass_fail") == "FAIL"
           and (o.get("root_cause") or CAUSE_UNCLASSIFIED) == CAUSE_UNCLASSIFIED]
    out.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return out[:limit]
