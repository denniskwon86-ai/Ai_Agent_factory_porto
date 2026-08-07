"""[D-017 §9 P4-2] 조직별 운영 현황 — 사용량·실패·승인 대기·정책 위반.

## ⚠️⚠️ 거버넌스 콘솔에서 **0은 「문제 없음」으로 읽힌다**

이 화면은 정의상 «무엇이 안 되어 있는가» 를 모아 보여 준다. 그래서 원천 하나를 못 읽었을 때
0 을 찍으면 **가장 나쁜 방식으로 틀린다** — 사람은 그것을 「승인 대기 없음」·「위반 없음」으로
읽고 안심한다. 아무도 「왜 0인가」를 묻지 않는다.

`governance_block_reason` 주석이 같은 이유로 이 화면을 아무에게나 열지 않는다:
「어디가 비어 있는지는 그 자체로 보호해야 하는 정보」. 그 화면이 **틀린 0** 을 보여 주면
보호할 가치조차 없어진다.

★ 그래서 모든 지표는 `Metric` 이다 — 값과 «읽었는가» 를 함께 들고 다닌다.
  읽지 못하면 `value=None` 이고 `error` 가 붙는다. 화면은 그때 숫자 대신 «확인 못 함» 을 쓴다.

## 무엇을 세는가

| 구획 | 원천 | 비고 |
|---|---|---|
| 사용량·실패 | `llm_call_log.jsonl` | 부서는 `owner_dept_id` 로 실린다 |
| 승인 대기 | `agent_assets`(DRAFT·REVIEW) · `workspace_promotions` | 조직 자산 승인 흐름 |
| 정책 위반 | `access_audit.jsonl` 의 `ACCESS_DENIED_*` | **거부 기록이 침해 시도의 신호다** |

⚠️ 「정책 위반 0」이 좋은 소식이 아닐 수 있다 — 통제가 없어서 아무것도 거부되지 않았을 수도
  있다. 그래서 위반 수와 함께 **어떤 종류인지**를 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Metric:
    """값 하나. **`value=None` 은 0 이 아니라 «읽지 못했다» 다.**"""
    value: Optional[float] = None
    error: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "known": self.known,
                "error": self.error, "detail": self.detail}


def _metric(fn, *a, **kw) -> Metric:
    """실패를 **`None`(모름)** 으로 감싼다. 0 으로 바꾸지 않는다.

    ⚠️ 이름·속성 오류는 프로그래밍 결함이므로 소리를 낸다 — `agent_design_context._safe` 가
      같은 함정에 빠졌던 것(모듈 이름 오타를 «읽지 못함» 으로 위장)을 되풀이하지 않는다."""
    try:
        return Metric(value=float(fn(*a, **kw)))
    except (ImportError, AttributeError, NameError, TypeError) as e:
        print(f"🐞 [org_operations] 수집기 버그({getattr(fn, '__name__', fn)}): "
              f"{type(e).__name__}: {e}")
        return Metric(error=f"수집기 오류: {type(e).__name__}: {e}")
    except Exception as e:
        return Metric(error=f"{type(e).__name__}: {e}")


# ── 사용량·실패 ─────────────────────────────────────────────────────────────
def usage_by_org(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """부서별 호출·실패·비용. 부서가 비면 «(미상)» 으로 세운다 — **버리지 않는다.**"""
    rows: Dict[str, Dict[str, Any]] = {}
    unattributed = 0
    for r in records or ():
        dept = str(r.get("owner_dept_id") or "").strip()
        if not dept:
            dept = "(미상)"
            unattributed += 1
        b = rows.setdefault(dept, {"org": dept, "calls": 0, "failed": 0,
                                   "cost_usd": 0.0, "unpriced_calls": 0})
        b["calls"] += 1
        if not r.get("ok"):
            b["failed"] += 1
        c = r.get("cost_estimate_usd")
        if c is None:
            b["unpriced_calls"] += 1        # 0 으로 더하지 않는다
        else:
            try:
                b["cost_usd"] += float(c)
            except (TypeError, ValueError):
                b["unpriced_calls"] += 1
    out = []
    for b in rows.values():
        b["cost_usd"] = round(b["cost_usd"], 6)
        b["failure_rate"] = round(b["failed"] / b["calls"], 4) if b["calls"] else None
        out.append(b)
    out.sort(key=lambda x: -x["calls"])
    total = len(records or ())
    return {
        "orgs": out,
        "coverage": {
            "records": total,
            "without_org": unattributed,
            "attribution_rate": round((total - unattributed) / total, 4) if total else None,
            "note": ("" if not unattributed else
                     f"전체 {total}건 중 {unattributed}건은 소속 부서가 기록되지 않아 «(미상)» "
                     f"으로 묶였습니다 — 부서별 숫자는 **전체가 아닙니다.**"),
        },
    }


# ── 승인 대기 ───────────────────────────────────────────────────────────────
def _pending_assets(viewer_scopes) -> int:
    from core.agent_assets import ST_DRAFT, ST_REVIEW, agent_assets
    n = 0
    for kind in ("agent", "skill", "workflow"):
        for st in (ST_DRAFT, ST_REVIEW):
            n += len(agent_assets.list_assets(kind, viewer_scopes, "", status=st) or [])
    return n


def _pending_promotions() -> int:
    from core.workspace_promotion import workspace
    # ⚠️ 상태 문자열을 여기서 지어내지 않는다 — 전체를 읽고 «끝나지 않은 것» 을 센다.
    rows = workspace.list_promotions() or []
    done = {"promoted", "rejected", "withdrawn"}
    return sum(1 for r in rows if str(r.get("status") or "").lower() not in done)


# ── 정책 위반 ───────────────────────────────────────────────────────────────
#: 거부 이벤트 종류. ⚠️ 문자열을 여기서 새로 적지 않는다 — `audit` 의 상수를 그대로 쓴다.
def _denied_events() -> Dict[str, Any]:
    from core.enterprise_context import audit
    kinds = {audit.ACCESS_DENIED_SCOPE_MISMATCH: "조직 범위 불일치",
             audit.ACCESS_DENIED_UNAUTHENTICATED: "식별 없음",
             audit.ACCESS_DENIED_CLASSIFICATION: "등급 부족"}
    by_kind: Dict[str, int] = {}
    by_actor: Dict[str, int] = {}
    for e in (audit.read_events() or []):
        ev = str(e.get("event") or e.get("event_type") or "")
        if ev not in kinds:
            continue
        by_kind[kinds[ev]] = by_kind.get(kinds[ev], 0) + 1
        actor = str(e.get("actor") or "").strip() or "(익명)"
        by_actor[actor] = by_actor.get(actor, 0) + 1
    return {"total": sum(by_kind.values()), "by_kind": by_kind,
            "top_actors": sorted(by_actor.items(), key=lambda kv: -kv[1])[:5]}


def collect(records: List[Dict[str, Any]], viewer_scopes) -> Dict[str, Any]:
    """조직 대시보드 한 판. **각 칸이 «읽었는가» 를 들고 온다.**"""
    denied = _metric(lambda: _denied_events()["total"])
    detail: Dict[str, Any] = {}
    if denied.known:
        try:
            detail = _denied_events()
        except Exception:
            detail = {}

    return {
        "usage": usage_by_org(records),
        "pending_approvals": {
            "assets": _metric(_pending_assets, viewer_scopes).to_dict(),
            "promotions": _metric(_pending_promotions).to_dict(),
        },
        "policy_denials": {
            **denied.to_dict(),
            "detail": detail,
            # ★ 0 을 «좋은 소식» 으로 읽지 않게 한다.
            "note": ("거부 기록이 0 입니다 — 통제가 잘 지켜졌다는 뜻일 수도, **통제가 걸려 "
                     "있지 않다는 뜻일 수도** 있습니다. 최근 봉합한 라우트가 있으면 그쪽부터 "
                     "확인하십시오."
                     if denied.known and denied.value == 0 else ""),
        },
    }
