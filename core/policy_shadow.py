"""★★★ [G1-B P0] **이중 판정 관측** — 기존 판정을 강제하면서 신규 PDP 를 나란히 돌린다.

교차검토 `[G1-B-P0-REVIEW-75]` 의 지시:

> 기존 `assert_release_*` 를 곧바로 제거하지 않는다. 신규 PDP 가 기존보다 동등하거나 더
> 엄격하다는 것이 **종단 부정 테스트로 입증된 뒤** 원자적으로 전환한다.

`tests/test_app_policy_equivalence.py` 는 **판정기 단위**로 그것을 증명했다. 그러나 단위
동등성은 «실제 요청에서도 같은 사실이 먹인다» 를 증명하지 못한다 — 이 저장소는 그 차이로
여러 번 다쳤다(「테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다」).

그래서 **살아 있는 라우트에서** 두 판정을 함께 돌리고 어긋남을 센다.

## 세 가지 결과

| 결과 | 뜻 | 취급 |
|---|---|---|
| `match` | 두 판정이 같다 | 정상 |
| `stricter` | 기존 허용 · PDP 거부 | **예상된 강화**(미바인딩·문맥·계정 상태). 세되 막지 않는다 |
| `looser` | 기존 거부 · PDP 허용 | ★★★ **절대 있어서는 안 된다.** 전환하면 권한이 넓어지는 칸이다 |

## ⚠️ 관측이 동작을 바꾸지 않는다

- 강제하는 것은 **기존 판정**이다. PDP 결과는 기록만 한다.
- PDP 판정 중 예외가 나도 **요청을 죽이지 않는다** — 관측 장애가 기능 장애가 되면 안 된다.
  다만 그 실패를 **센다**(조용한 유실 금지, `audit` 모듈과 같은 규약).

## ⚠️ 프로세스 메모리에 센다

재시작하면 사라진다. 그것이 의도다 — 이 계수는 «전환해도 되는가» 를 판단하는 **작업 중 관측**
이지 영구 지표가 아니다. 영구 기록이 필요한 어긋남(`looser`)은 감사 로그에도 남긴다.

LLM 0콜.
"""
from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MATCH = "match"
STRICTER = "stricter"
LOOSER = "looser"
ERROR = "error"

#: 최근 어긋남 보관 개수. 전부 들고 있으면 장시간 운영에서 메모리를 먹는다.
_KEEP = 50


class _ShadowObserver:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counts: Counter = Counter()
        self._recent: List[Dict[str, Any]] = []

    def observe(self, *, path: str, action: str, old_allowed: bool,
                new_allowed: bool, new_reason: str = "",
                actor: str = "", resource_id: str = "") -> str:
        """한 요청의 두 판정을 기록하고 결과 종류를 돌려준다."""
        if old_allowed and new_allowed:
            kind = MATCH
        elif not old_allowed and not new_allowed:
            kind = MATCH
        elif old_allowed and not new_allowed:
            kind = STRICTER
        else:
            kind = LOOSER

        with self._lock:
            self._counts[kind] += 1
            if kind != MATCH:
                self._recent.append({
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "kind": kind, "path": path, "action": action,
                    "old": "allow" if old_allowed else "deny",
                    "new": "allow" if new_allowed else f"deny({new_reason})",
                    "actor": actor, "resource_id": resource_id,
                })
                del self._recent[:-_KEEP]

        if kind == LOOSER:
            # ★★★ 이것만은 영구 기록으로도 남긴다. 「전환하면 권한이 넓어진다」는 사실이
            #   프로세스 재시작으로 사라지면 안 된다.
            try:
                from core.enterprise_context import audit
                audit.record(event=audit.ACCESS_DENIED_SCOPE_MISMATCH,
                             resource_type="policy_shadow", resource_id=resource_id or path,
                             actor=actor, outcome="denied",
                             reason="PDP 가 기존 판정보다 느슨하다 — 전환 금지",
                             detail=f"{path} {action} old=deny new=allow")
            except Exception:
                pass
        return kind

    def error(self, detail: str = "") -> None:
        """PDP 판정 자체가 실패했다. **요청은 죽이지 않되 세어서 드러낸다.**"""
        with self._lock:
            self._counts[ERROR] += 1
            self._recent.append({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": ERROR, "detail": detail[:300],
            })
            del self._recent[:-_KEEP]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            c = dict(self._counts)
            total = sum(c.values())
            return {
                "total": total,
                "match": c.get(MATCH, 0),
                "stricter": c.get(STRICTER, 0),
                "looser": c.get(LOOSER, 0),
                "error": c.get(ERROR, 0),
                #: ★ 전환 가능 판정은 **여기 하나**로 읽는다 — 여러 숫자를 사람이 보고
                #:   해석하게 두면 판단이 갈린다.
                "safe_to_switch": c.get(LOOSER, 0) == 0 and c.get(ERROR, 0) == 0 and total > 0,
                "recent": list(self._recent[-10:]),
            }

    def reset(self) -> None:
        """시험 전용. 운영에서 부르면 관측 이력이 사라진다."""
        with self._lock:
            self._counts.clear()
            self._recent.clear()


policy_shadow = _ShadowObserver()
