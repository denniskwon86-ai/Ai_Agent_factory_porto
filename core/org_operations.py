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
    """부서별 호출·실패·비용. 부서가 비면 «(미상)» 으로 세운다 — **버리지 않는다.**

    [D-019] 세는 축은 `owner_dept_id` 하나이고, `owner_scope_node_id` 는 **롤업용으로 병기**만
    한다. node 로 세지 않는 이유는 실측이다 — 활성 부서 12개 중 9개가 `node_41402723bc90`
    하나에 매핑돼 있어, node 로 세면 「(미상) 한 줄」이 「LS MnM 한 줄」로 바뀔 뿐 부서별 비용은
    여전히 없다.

    ⚠️ 한 부서에서 노드가 **여러 개** 나올 수 있다(조직개편 뒤 기록 시점이 갈린 경우). 그때
      하나로 고르지 않고 본 것을 전부 남긴다 — 임의로 하나를 고르면 나머지 기간의 비용이
      말없이 다른 조직으로 옮겨간다."""
    rows: Dict[str, Dict[str, Any]] = {}
    unattributed = 0          # 부서가 비어 있는 레코드(=«(미상)» 으로 묶인 것)
    pre_field = 0             # ↳ 그중 **필드 자체가 없던** 레코드(계측 도입 전)
    for r in records or ():
        dept = str(r.get("owner_dept_id") or "").strip()
        if not dept:
            dept = "(미상)"
            unattributed += 1
            # ⚠️ 「필드가 없다」와 「필드는 있는데 비었다」는 **다른 결함**이다. 앞은 계측 도입
            #   전이라 소급이 원천적으로 불가능하고, 뒤는 기록해야 할 때 못 기록한 것이라
            #   고칠 대상이다. 한 숫자로 합치면 고칠 수 있는 쪽이 안 보인다.
            if "owner_dept_id" not in (r or {}):
                pre_field += 1
        b = rows.setdefault(dept, {"org": dept, "calls": 0, "failed": 0,
                                   "cost_usd": 0.0, "unpriced_calls": 0,
                                   "scope_node_ids": set()})
        _node = str(r.get("owner_scope_node_id") or "").strip()
        if _node:
            b["scope_node_ids"].add(_node)
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
        b["scope_node_ids"] = sorted(b["scope_node_ids"])      # JSON 직렬화 가능한 형태로
        out.append(b)
    out.sort(key=lambda x: -x["calls"])
    total = len(records or ())
    missing = unattributed - pre_field
    return {
        "orgs": out,
        "coverage": {
            "records": total,
            "without_org": unattributed,
            # [D-019] 소급 가능성이 갈리는 지점이라 나눠서 준다.
            "without_org_pre_field": pre_field,     # 소급 불가 — 필드가 없던 시기
            "without_org_missing": missing,         # 고칠 대상 — 필드는 있는데 안 실렸다
            "attribution_rate": round((total - unattributed) / total, 4) if total else None,
            "note": _coverage_note(total, unattributed, pre_field, missing),
        },
    }


def _coverage_note(total: int, unattributed: int, pre_field: int, missing: int) -> str:
    """«왜 0인가» 에 답하는 문장. **비어 있으면 화면이 아무 말도 하지 않는다.**

    ⚠️ 두 종류를 한 문장으로 뭉치면 「기록을 고치면 되는 문제」로 읽힌다. 실제로는 계측 도입
      전 레코드가 다수이고 그쪽은 **어떤 배선을 고쳐도 되살아나지 않는다** — 그 사실이
      화면에 남아야 나중에 「왜 아직도 미상이 있나」를 다시 조사하지 않는다."""
    if not unattributed:
        return ""
    head = (f"전체 {total}건 중 {unattributed}건은 소속 부서가 기록되지 않아 «(미상)» 으로 "
            f"묶였습니다 — 부서별 숫자는 **전체가 아닙니다.**")
    if pre_field and missing:
        return (f"{head} 이 중 {pre_field}건은 부서 계측 도입 **이전** 기록이라 소급 귀속이 "
                f"불가능하고, {missing}건은 계측 이후인데 값이 실리지 않은 건입니다.")
    if pre_field:
        return f"{head} 전부 부서 계측 도입 **이전** 기록이라 소급 귀속이 불가능합니다."
    return f"{head} 전부 계측 이후 기록인데 값이 실리지 않았습니다 — 기록 경로 점검이 필요합니다."


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
