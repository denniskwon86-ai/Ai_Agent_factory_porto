"""[D-017 §9 P3-4] **멈춰 있는 동안 세상이 바뀌었을 때** 재개 규칙.

## 무엇이 문제인가

스프린트는 멈춰 있을 수 있다 — HOTL 이 사람의 답을 기다리거나, 쿼터가 소진돼 동결되거나.
그 사이에 세 가지가 바뀔 수 있고, 셋 다 조용히 지나가면 안 된다.

| 바뀐 것 | 그대로 재개하면 |
|---|---|
| **권한 회수** | 이제 자격이 없는 사람이 실행을 이어간다 |
| **템플릿 폐기** | 폐기된 워크플로우가 계속 돈다 — 「승인된 것만 실행」이 무너진다 |
| **버전 변경** | **체크포인트와 다른 그래프로 이어붙는다** |

★★ 세 번째가 가장 위험하고 가장 안 보인다. LangGraph 체크포인트는 노드 이름으로 상태를
  들고 있다. 재개 시점의 그래프에서 그 노드가 사라졌거나 순서가 바뀌었으면, 실행은
  **오류 없이** 엉뚱한 지점으로 이어지거나 단계를 건너뛴다. 산출물은 나오고, 아무도
  「무엇이 빠졌는지」 묻지 않는다.

## 규칙 — 다르면 이어가지 않는다

P3-2 가 만든 **구성 지문**이 여기서 쓰인다. 시작 시점의 지문과 지금의 지문이 다르면 재개를
막고 **무엇이 달라졌는지** 말한다. 사용자는 두 가지 중 하나를 고를 수 있다 —
새 구성으로 «처음부터» 돌리거나, 구성을 되돌리거나.

⚠️ 자동으로 «새 구성으로 이어서» 를 고르지 않는다. 그것이 바로 위 표의 세 번째 줄이다.

## ⚠️ 모르면 막지 않는다 — 여기만은 fail-open 이다

시작 시점 스냅샷이 **없으면**(P3-2 이전에 시작된 프로젝트) 비교할 대상이 없다. 그때 막으면
진행 중이던 모든 프로젝트가 재개 불가가 된다. 유출 경로가 아니라 **가용성 경로**이므로
열어 두되, 그 사실을 이유에 적는다(`compared=False`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ResumeVerdict:
    """재개해도 되는가. **불변**이며 `check()` 만이 만든다."""
    ok: bool
    #: 사용자에게 보일 이유. 허용이면 빈 문자열
    reason: str = ""
    #: 지문을 실제로 비교했는가. `False` = 비교할 대상이 없었다(막지는 않는다)
    compared: bool = False
    started_fingerprint: str = ""
    current_fingerprint: str = ""
    #: 무엇이 달라졌는지 — 사람이 읽는 목록
    changes: List[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "compared": self.compared,
                "started_fingerprint": self.started_fingerprint,
                "current_fingerprint": self.current_fingerprint,
                "changes": list(self.changes or [])}


def _diff(started: Dict[str, Any], now) -> List[str]:
    """무엇이 달라졌는지 **사람이 읽을 수 있게** 적는다.

    ⚠️ 「구성이 바뀌었습니다」만 말하면 사용자는 무엇을 되돌려야 할지 모른다. 그러면 결국
      «그냥 새로 시작» 을 고르고, 그때까지 쓴 LLM 비용이 버려진다."""
    out: List[str] = []
    a_ag = list(started.get("agents") or [])
    b_ag = list(now.agents or [])
    if a_ag != b_ag:
        gone = [x for x in a_ag if x not in b_ag]
        added = [x for x in b_ag if x not in a_ag]
        if gone:
            out.append(f"빠진 에이전트: {', '.join(gone)}")
        if added:
            out.append(f"추가된 에이전트: {', '.join(added)}")
        if not gone and not added:
            out.append("에이전트 실행 순서가 바뀌었습니다")
    a_hl = list(started.get("interrupt_after") or [])
    b_hl = list(now.interrupt_after or [])
    if a_hl != b_hl:
        out.append(f"사용자 확인 지점(HOTL)이 달라졌습니다: {a_hl or '없음'} → {b_hl or '없음'}")
    a_v, b_v = started.get("asset_version") or "", now.asset_version or ""
    if a_v != b_v:
        out.append(f"워크플로우 버전: {a_v or '(없음)'} → {b_v or '(없음)'}")
    if not out:
        # 지문은 달라졌는데 위 항목이 같다면 스킬·모델 티어 등 세부가 바뀐 것이다.
        out.append("에이전트 목록은 같지만 스킬·모델 등 실행 설정이 달라졌습니다")
    return out


def check(workspace_root: str, template_id: str) -> ResumeVerdict:
    """★ 재개 판정의 **유일한 지점.** 아무것도 바꾸지 않는다."""
    from core import config_snapshot as cs

    now = cs.capture(template_id)

    # ── ① 템플릿 폐기·미승인 ────────────────────────────────────────────────
    # `capture` 는 실제 실행과 같은 판정(`require_runnable=True`)을 지난다. 못 읽었다면
    # 지금 실행해도 못 읽는다 — 그러니 재개도 막는다.
    if not now.resolved:
        return ResumeVerdict(
            ok=False, compared=False,
            reason=("지금은 이 워크플로우를 실행할 수 없습니다 — 폐기됐거나 승인 상태가 "
                    f"바뀌었을 수 있습니다. ({now.error})"))

    data = cs.read(workspace_root) or {}
    started = data.get("current") or {}
    started_fp = str(started.get("fingerprint") or "")

    # ── ② 비교할 대상이 없다 ────────────────────────────────────────────────
    if not started_fp:
        # ⚠️ 여기만 fail-open 이다. 막으면 진행 중이던 모든 프로젝트가 재개 불가가 된다.
        return ResumeVerdict(
            ok=True, compared=False, current_fingerprint=now.fingerprint,
            reason=("시작 시점의 구성 기록이 없어 비교하지 못했습니다 — 재개는 허용하되, "
                    "산출물이 이상하면 구성이 바뀌었을 가능성을 먼저 보십시오."))

    # ── ③ 구성이 달라졌다 ───────────────────────────────────────────────────
    if started_fp != now.fingerprint:
        changes = _diff(started, now)
        return ResumeVerdict(
            ok=False, compared=True, started_fingerprint=started_fp,
            current_fingerprint=now.fingerprint, changes=changes,
            reason=("멈춰 있는 동안 워크플로우 구성이 바뀌어 그대로 이어갈 수 없습니다. "
                    "저장된 진행 상태는 옛 구성의 단계 이름을 담고 있어, 새 구성으로 이어붙이면 "
                    "오류 없이 단계를 건너뛰거나 엉뚱한 지점으로 갑니다.\n"
                    "· " + "\n· ".join(changes)
                    + "\n\n구성을 되돌린 뒤 재개하거나, 새 구성으로 처음부터 가동하십시오."))

    return ResumeVerdict(ok=True, compared=True, started_fingerprint=started_fp,
                         current_fingerprint=now.fingerprint)
