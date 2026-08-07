"""[D-017 §9 P4-3] 전사 승격 추천.

## 무엇을 추천하는가 — 그 이상은 말하지 않는다

**「지금 승격 신청하면 게이트를 통과할 릴리스」** 만 추천한다.

★ 「좋은 자산」이나 「가치 있는 자산」을 추천하지 않는다. 그것은 사람의 판단이고 우리가 가진
  데이터로는 근사조차 할 수 없다. 답할 수 있는 질문은 **「형식 요건이 갖춰졌는가」** 뿐이다.

## ★★ 판정을 여기서 다시 하지 않는다

`workspace.evaluate_gate()` 가 이미 `promotable` 을 준다. 여기서 `checks` 를 다시 세어
「아마 될 것 같다」를 만들면 **화면과 실제 게이트가 다른 말을 하게 된다** — 화면은 「승격
준비됨」이라 하는데 신청하면 막히고, 그때 사용자는 추천을 신뢰하지 않게 된다.
그러면 이 기능은 있으나 마나다.

⚠️⚠️ 특히 **`unverifiable` 을 완화하지 않는다.** 게이트에서 가장 흔한 상태가 그것이고
  (「사용 자산을 모르므로 검사할 수 없다」), 통과로 세면 거의 전부가 추천된다.
  게이트의 note 가 이미 못박았다 — 「확인하지 못한 것이며 승격을 막습니다」.

## 추천하지 않는 것도 말한다

추천 목록만 주면 「내 릴리스는 왜 없나」에 답할 수 없다. 그래서 막고 있는 항목과
**그 해소 방법**을 함께 준다. ★ 해소 방법(`suggested_action`)은 게이트가 이미 만들어 준다 —
여기서 새로 짓지 않는다.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

#: 한 번에 훑을 릴리스 수 상한. 라이브러리가 커져도 이 API 가 응답을 못 하는 일이 없게 한다.
MAX_RELEASES = 200


def _releases() -> Optional[List[str]]:
    """라이브러리의 릴리스 id 목록. `None` = **읽지 못했다**(빈 목록과 다르다)."""
    import os

    from core import library_paths
    try:
        root = library_paths.library_dir()
    except Exception:
        return None
    try:
        names = sorted(os.listdir(root))
    except FileNotFoundError:
        return []                      # 라이브러리가 아직 없다 — 확인된 0건
    except OSError:
        return None                    # 권한·잠금 — 모른다
    return [n for n in names if os.path.isdir(os.path.join(root, n))][:MAX_RELEASES]


def _project_of(release_id: str) -> str:
    """릴리스가 속한 프로젝트. **`release.json` 에서 읽는다.**

    ⚠️ id 에서 잘라내지 않는다 — 게이트 자신이 「릴리스 id 에서 이름을 추론하면 명명 규칙이
      바뀔 때 조용히 틀린다」고 적어 두었다. 읽지 못하면 빈 문자열이고, 그러면 게이트가
      품질 검사를 `unverifiable` 로 두어 추천에서 빠진다 — 그것이 옳은 결과다."""
    import json

    from core import library_paths
    try:
        with open(library_paths.release_json(release_id), "r", encoding="utf-8") as f:
            return str((json.load(f) or {}).get("project_id") or "").strip()
    except Exception:
        return ""


def recommend(target_scope: str = "enterprise", evaluate: Optional[Callable] = None,
              releases: Optional[List[str]] = None) -> Dict[str, Any]:
    """승격 추천. **아무것도 바꾸지 않는다.**

    :param evaluate: 게이트 평가 함수(주입 가능 — 테스트용). 기본은 `workspace.evaluate_gate`.
    """
    if evaluate is None:
        from core.workspace_promotion import workspace
        evaluate = workspace.evaluate_gate

    ids = releases if releases is not None else _releases()
    if ids is None:
        # ★ 빈 추천이 아니라 «읽지 못함» 이다. 「추천할 것이 없다」와 구분한다.
        return {"recommended": [], "almost": [],
                "coverage": {"evaluated": 0, "unreadable": None,
                             "note": ("릴리스 보관소를 읽지 못해 추천을 만들지 못했습니다 — "
                                      "«추천할 것이 없다» 가 아닙니다.")}}

    recommended: List[Dict[str, Any]] = []
    almost: List[Dict[str, Any]] = []
    unreadable: List[str] = []

    for rid in ids:
        try:
            g = evaluate(rid, target_scope, project_id=_project_of(rid)) or {}
        except Exception as e:
            # ⚠️ 조용히 빼지 않는다. 빼면 「검사했는데 없음」과 「검사를 못 함」이 뭉개진다.
            unreadable.append(f"{rid}: {type(e).__name__}: {e}")
            continue

        row = {"release_id": rid, "target_scope": target_scope,
               "linked_assets": g.get("linked_assets") or []}

        # ★★ `promotable` 을 **그대로** 쓴다. 여기서 checks 를 다시 세지 않는다.
        if g.get("promotable"):
            recommended.append(row)
            continue

        blocking = [c for c in (g.get("checks") or [])
                    if c.get("state") in ("fail", "unverifiable")]
        almost.append({
            **row,
            "blocking": blocking,
            # 확인 못 한 것이 몇 개인지 따로 센다 — 「고치면 되는 것」과 「알 수 없는 것」은
            # 사용자가 할 일이 다르다.
            "fail_count": sum(1 for c in blocking if c.get("state") == "fail"),
            "unverifiable_count": sum(1 for c in blocking if c.get("state") == "unverifiable"),
        })

    # 가까운 것부터 — 막힌 항목이 적을수록 위로.
    almost.sort(key=lambda x: (len(x["blocking"]), x["release_id"]))

    return {
        "recommended": recommended,
        "almost": almost,
        "coverage": {
            "evaluated": len(ids) - len(unreadable),
            "unreadable": len(unreadable),
            "unreadable_detail": unreadable[:10],
            "note": _note(len(ids), len(unreadable), len(recommended)),
        },
        "rule": ("네 검사가 **전부 pass** 인 것만 추천합니다. `unverifiable` 은 통과가 아니라 "
                 "**확인하지 못한 것**이며 승격을 막습니다 — 게이트와 같은 규칙입니다."),
    }


def _note(total: int, unreadable: int, recommended: int) -> str:
    """사람이 읽는 요약. **비어 있으면 특이사항이 없다는 뜻이다.**"""
    parts: List[str] = []
    if unreadable:
        parts.append(f"{total}건 중 {unreadable}건은 게이트를 읽지 못해 판정에서 빠졌습니다 "
                     f"— «추천 대상 아님» 이 아닙니다.")
    if total and not recommended:
        parts.append("지금 승격 가능한 릴리스가 없습니다. 아래 «가까운 것» 의 막힌 항목을 "
                     "먼저 해소하십시오.")
    if not total:
        parts.append("보관된 릴리스가 없습니다 — 확인했고 0건입니다.")
    return " ".join(parts)
