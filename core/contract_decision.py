"""★★★ 컴파일러가 **사람에게 넘긴 결정**을 사람이 실제로 내릴 수 있게 한다. (2026-08-26)

## ⚠️⚠️ 무엇이 있었나 — 「사람이 정해야 합니다」인데 정할 방법이 없었다

계약 컴파일러는 스스로 못 정하는 두 가지를 **사람에게 넘긴다.** 실측에서 둘 다 나왔고,
둘 다 **막다른 길**이었다.

    ① 지원되지 않는 능력의 처리
       「사용자 결정이 필요한 요구가 …(지원 대기) 있습니다」
       → `pending_decisions` 를 **만드는 곳만 있고 읽는 곳이 0곳**이었다(전수 확인).

    ② 같은 데이터셋을 두 태스크가 다르게 선언
       「데이터셋 «x» 를 «A» 와 «B» 가 다르게 선언했습니다 — … 사람이 정해야 합니다
        (자동 병합하지 않습니다)」
       → 고를 화면도 API 도 없었다.

★ 합산기의 거절은 **옳다.** 자동 병합은 조용한 권한 확대다. 잘못된 것은 「정해야 한다」고
  말해 놓고 정할 자리를 안 준 것이다. 통제가 아니라 교착이다.

## 결정은 **초안**에 착지한다

컴파일러의 입력은 `contracts/drafts/<task_id>.json` 이다. 그러므로 결정도 거기에 남아야
다음 컴파일이 그것을 본다. 별도 «결정 표» 를 만들어 컴파일러가 안 보면, 그것이 바로
「만들어 두고 부르는 곳이 없다」의 아홉 번째 반복이다.

⚠️ 결정 자체는 **원장에도** 남는다. 초안 파일은 롤백·재생성으로 바뀔 수 있고, 「누가 언제
  무슨 근거로 이 능력을 줄이기로 했나」는 덮어쓸 수 없는 곳에 있어야 한다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from core import app_runtime_contract as arc
from core import project_contract_aggregator as aggregator

#: 원장 주체 유형. ★ 「무엇을 결정했는가」를 여기서 못박는다 — 행위자 하나의 아무 결정으로
#:   다른 대상이 통과되지 않게 하는 것이 이 저장소의 규칙이다(`decision_ledger` 머리말).
SUBJECT_CAPABILITY = "app_contract_capability"
SUBJECT_DATASET = "app_contract_dataset"


class DecisionError(ValueError):
    """결정을 적용할 수 없다. **사유가 사람이 읽을 말이어야 한다** — 이 예외는 그대로
    화면에 나간다."""


# ══════════════════════════════════════════════════════════════════════════
# 무엇이 사람을 기다리는가
# ══════════════════════════════════════════════════════════════════════════

def pending_items(tasks: Any, drafts: Dict[str, Any]) -> Dict[str, Any]:
    """지금 사람이 정해야 하는 것들. **컴파일러와 같은 판정기를 쓴다.**

    ⚠️ 여기서 판정을 다시 계산하면 화면이 보여 주는 것과 컴파일러가 막는 것이 갈린다 —
      이 저장소가 이미 두 번 겪은 결함이다(게이트↔컴파일러 범위 불일치).
    """
    agg = aggregator.aggregate(tasks, drafts)

    caps: List[Dict[str, Any]] = []
    seen: set = set()
    for tid, raw in sorted((drafts or {}).items()):
        if tid not in agg.included_task_ids or not isinstance(raw, dict):
            continue
        for it in (raw.get("capability_intents") or []):
            if not isinstance(it, dict):
                continue
            cap = str(it.get("capability", "")).strip()
            status, reason = arc.decide(cap)
            if arc.is_buildable(status) or str(it.get("user_decision", "")).strip():
                continue
            key = (tid, cap)
            if key in seen:
                continue
            seen.add(key)
            caps.append({
                "task_id": tid,
                "intent_id": str(it.get("intent_id", "")),
                "capability": cap,
                "requirement_ref": str(it.get("requirement_ref", "")),
                "status": status,
                "status_label": arc.STATUS_LABEL.get(status, status),
                "reason": reason,
                #: ★ 고를 수 있는 것을 **함께** 준다. 목록 없이 「정하라」고 하면 사람은
                #:   무엇을 적어야 하는지 모르고, 그 화면은 다시 막다른 길이 된다.
                "choices": list(arc.allowed_decisions(status)),
            })

    conflicts = [c for c in agg.conflicts
                 if c.get("kind") == aggregator.CONFLICT_DATASET]
    for c in conflicts:
        #: ⚠️ 「무엇이 다른가」를 반드시 함께 준다. 이름만 주면 사람은 두 초안을 손으로
        #:   열어 비교해야 하고, 그러면 아무도 안 고른다.
        c.setdefault("differences", [])
        c["choices"] = list(c.get("tasks") or [])

    return {
        "capability_decisions": caps,
        "dataset_conflicts": conflicts,
        #: 나머지 오류는 사람이 «고르는» 것이 아니라 에이전트가 고쳐야 하는 것이다.
        #: 섞어 보여 주면 사람이 못 고치는 것을 붙들고 있게 된다.
        "other_errors": list(agg.errors),
        "pending": bool(caps or conflicts),
    }


# ══════════════════════════════════════════════════════════════════════════
# 결정을 초안에 남긴다
# ══════════════════════════════════════════════════════════════════════════

def apply_capability_decision(draft: Dict[str, Any], *, capability: str,
                              decision: str) -> Tuple[Dict[str, Any], str]:
    """능력 하나의 `user_decision` 을 정한다. `(바뀐 초안, 사람이 읽을 요약)`.

    ⚠️⚠️ **상태가 허용하는 결정만 받는다.** `arc.allowed_decisions` 밖의 값을 넣으면
      컴파일러가 그 자리에서 버리고(`user_decision = ""`), 결정은 원장에만 남아
      「분명히 정했는데 또 물어본다」가 된다 — 사람은 시스템을 믿지 않게 된다.
    ★ 금지(`PROHIBITED`) 능력에 `REQUEST_HOST_FEATURE` 를 넣는 경로가 여기서 막힌다.
    """
    cap = (capability or "").strip()
    dec = (decision or "").strip().upper()
    if not cap:
        raise DecisionError("어떤 능력에 대한 결정인지 지정해야 합니다.")

    status, _reason = arc.decide(cap)
    if arc.is_buildable(status):
        raise DecisionError(
            f"«{cap}» 은 이미 지원되는 능력입니다 — 고를 것이 없습니다.")
    allowed = arc.allowed_decisions(status)
    if dec not in allowed:
        raise DecisionError(
            f"«{cap}»({arc.STATUS_LABEL.get(status, status)}) 에서 고를 수 있는 것은 "
            f"{list(allowed)} 입니다 — «{dec}» 는 받을 수 없습니다.")

    intents = list(draft.get("capability_intents") or [])
    hit = False
    for it in intents:
        if isinstance(it, dict) and str(it.get("capability", "")).strip() == cap:
            it["user_decision"] = dec
            hit = True
    if not hit:
        raise DecisionError(f"이 초안에 «{cap}» 요구가 없습니다 — 대상을 다시 확인하십시오.")

    out = dict(draft)
    out["capability_intents"] = intents
    return out, f"«{cap}» → {dec}"


def apply_dataset_resolution(drafts: Dict[str, Any], *, dataset_key: str,
                             winner_task_id: str) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """충돌한 데이터셋 선언을 **한쪽으로 통일**한다. `(바뀐 초안들, 요약)`.

    ★ 이긴 태스크의 선언을 **통째로 복사**한다. 칸을 골라 합치지 않는다 — 그것이 곧
      「자동 병합」이고, 합산기가 거절한 바로 그 행위다. 사람이 고른 것은 「어느 선언이
      맞는가」이지 「어떻게 섞을까」가 아니다.
    ⚠️ 진 쪽 초안의 **다른 데이터셋은 건드리지 않는다.** 충돌한 것 하나만 맞춘다.
    """
    key = (dataset_key or "").strip()
    win = (winner_task_id or "").strip()
    if not key or not win:
        raise DecisionError("어느 데이터셋을 어느 태스크 기준으로 맞출지 지정해야 합니다.")

    src = (drafts or {}).get(win)
    if not isinstance(src, dict):
        raise DecisionError(f"«{win}» 의 계약 초안을 찾지 못했습니다.")

    winning = None
    for ds in (src.get("datasets") or []):
        if isinstance(ds, dict) and aggregator._dataset_identity(ds) == key:
            winning = ds
            break
    if winning is None:
        raise DecisionError(f"«{win}» 초안에 데이터셋 «{key}» 가 없습니다.")

    changed: Dict[str, Dict[str, Any]] = {}
    for tid, raw in (drafts or {}).items():
        if tid == win or not isinstance(raw, dict):
            continue
        datasets = list(raw.get("datasets") or [])
        touched = False
        for i, ds in enumerate(datasets):
            if isinstance(ds, dict) and aggregator._dataset_identity(ds) == key:
                if ds != winning:
                    datasets[i] = json.loads(json.dumps(winning, ensure_ascii=False))
                    touched = True
        if touched:
            out = dict(raw)
            out["datasets"] = datasets
            changed[tid] = out

    if not changed:
        raise DecisionError(
            f"데이터셋 «{key}» 에서 «{win}» 과 다르게 선언한 태스크가 없습니다 — "
            f"이미 정리되었거나 대상을 잘못 지정했습니다.")
    return changed, f"데이터셋 «{key}» 를 «{win}» 기준으로 통일({', '.join(sorted(changed))})"
