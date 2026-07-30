"""[§5.5 / §14 M5] 전사 자비스의 **기반** — 권한 범위 안의 전사 상태를 결정론적으로 모은다.

## 왜 챗봇부터 만들지 않는가

제품 성경 §5.5: *"슈퍼바이저는 단순 Task ID 기반 챗봇이 아니다. 권한 범위 내에서 제품 전체의
프로젝트, 데이터 결손, 비용, 위험, 시나리오, 승인 상태를 **이해**하고 사용자를 안내해야 한다."*

"이해"의 재료가 없는 대화창은 정확히 성경이 거부한 그 챗봇이다. 그리고 그 재료는 이미 다
만들어져 있다 — 승격 게이트·릴리스 체크리스트·Shadow run·데이터 계약·거버넌스 결손·비용
텔레메트리·프로그램 사용여부. 없는 것은 **하나의 권한 필터를 통과한 집계**다. 그것이 이 모듈이다.

LLM 0콜. 서술(narration)은 이 결과 위에 얹는 별개의 층이며, 판정은 여기서 끝난다 —
판정을 LLM 에 맡기면 같은 상태에서 매번 다른 답이 나오고, 그건 보좌가 아니라 소음이다.

## 세 가지 불변식

1. **권한 범위를 못 정하면 아무것도 보여주지 않는다(fail-closed).** 전사 보좌 에이전트에서
   범위 오류의 기본값이 "전체 노출"이면 그 한 번으로 제품이 끝난다.
2. **읽지 못한 소스를 "이상 없음"으로 두지 않는다.** 모든 섹션은 실패를 `unavailable` 에
   적고, 최상위 `complete=False` 로 올린다 — 조용히 빠진 위험이 가장 위험하다.
3. **항목마다 "그래서 무엇을 하면 풀리는가"를 함께 준다.** 상태만 나열하는 화면은
   대시보드지 보좌가 아니다.
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: 심각도 정렬 순서. 자유 문자열을 쓰면 정렬이 무의미해진다.
SEVERITY_ORDER = ("high", "medium", "low", "info")

#: 섹션 식별자 — 선언만 하고 안 쓰는 상수를 만들지 않는다(이 저장소의 지배적 결함).
#: `briefing()` 이 이 순서대로 채우고, 응답의 `sections` 키와 1:1 로 대응한다.
SECTIONS = ("my_decisions", "blocked", "data_health", "programs", "cost")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rank(sev: str) -> int:
    return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else len(SEVERITY_ORDER)


def _item(kind: str, severity: str, title: str, why: str, action: str = "",
          ref: str = "", ref_type: str = "") -> Dict[str, Any]:
    """브리핑 항목 1건. `action` 이 없으면 사용자는 무엇을 해야 할지 모른다."""
    return {"kind": kind, "severity": severity, "title": title, "why": why,
            "suggested_action": action, "ref": ref, "ref_type": ref_type}


class _Collector:
    """섹션 수집기. 실패를 삼키지 않고 `unavailable` 로 승격시킨다."""

    def __init__(self):
        self.items: List[Dict[str, Any]] = []
        self.unavailable: List[Dict[str, str]] = []

    def run(self, source: str, fn) -> None:
        try:
            fn()
        except Exception as e:
            # ★ "영향 없음"과 "확인 못 함"은 다르다. 후자를 전자로 표시하면 브리핑이 거짓이 된다.
            self.unavailable.append({"source": source, "error": str(e)[:300]})

    def sorted_items(self) -> List[Dict[str, Any]]:
        return sorted(self.items, key=lambda i: (_rank(i["severity"]), i["kind"], i["title"]))


class EnterpriseBriefing:
    """권한 범위 안의 전사 상태 집계. 상태를 저장하지 않는다(읽기 전용)."""

    # ── 권한 범위 ─────────────────────────────────────────────────────
    def _visible(self, rows: List[dict], scope_node_id: str, tenant_id: str,
                 entity_mode: str, scope_field: str) -> List[dict]:
        """범위 필터. 범위 지정이 없으면 필터하지 않는다(조직 미도입 하위호환).

        ⚠️ 예외는 삼키지 않고 위로 던진다 — 필터가 깨진 채 전체를 돌려주면 유출이다."""
        if not (scope_node_id or tenant_id):
            return rows
        from core.enterprise_context.scoping import filter_visible
        prepared = []
        for r in rows:
            d = dict(r)
            d["enterprise_scope_id"] = d.get(scope_field) or ""
            prepared.append(d)
        return filter_visible(prepared, scope_node_id, tenant_id, entity_mode)

    # ── ① 내가 결정해야 하는 것 ───────────────────────────────────────
    def my_decisions(self, actor: str = "", scope_node_id: str = "", tenant_id: str = "",
                     entity_mode: str = "REAL") -> _Collector:
        c = _Collector()

        def _promotions():
            from core.workspace_promotion import workspace
            for status, sev, title, why, act in (
                ("requested", "high", "전사 승격 승인 대기",
                 "데이터 오너의 명시적 승인이 없으면 승격되지 않습니다.",
                 "데이터 오너가 승격 신청을 승인하거나 반려해야 합니다."),
                ("approved", "medium", "승인됐지만 아직 승격되지 않음",
                 "승인만으로는 전사 앱이 되지 않습니다 — 승격 실행이 남았습니다.",
                 "게이트를 다시 확인한 뒤 승격을 실행하십시오."),
            ):
                rows = [r for r in (workspace.list_promotions(status) or []) if r]
                for r in self._visible(rows, scope_node_id, tenant_id, entity_mode,
                                       "from_scope"):
                    c.items.append(_item(
                        f"promotion_{status}", sev, f"{title}: {r['release_id']}",
                        why + f" 신청자: {r.get('requested_by') or '(미기록)'}",
                        act, r["release_id"], "release"))
        c.run("workspace_promotion.list_promotions", _promotions)

        def _shadow():
            from core.shadow_mode import shadow_mode
            s = shadow_mode.summary(scope_node_id, tenant_id, entity_mode)
            pending = int((s.get("by_review_status") or {}).get("pending", 0))
            if pending:
                c.items.append(_item(
                    "shadow_review_pending", "medium",
                    f"Shadow Mode 검토 대기 {pending}건",
                    "검토되지 않은 비교 결과는 운영 판단의 근거가 되지 못합니다.",
                    "각 run 의 비교 결과를 검토하고 승인 또는 반려하십시오."))
            for inc in (s.get("incomparable") or []):
                c.items.append(_item(
                    "shadow_incomparable", "medium",
                    f"비교 불가 run: {inc.get('name') or inc.get('run_id')}",
                    ("같은 입력이 아니어서 비교 자체가 성립하지 않았습니다 — 실패가 아니라 "
                     f"**판정 불가**입니다. {inc.get('reason', '')}"),
                    "입력 스냅샷을 맞춰 다시 실행하십시오.",
                    inc.get("run_id", ""), "shadow_run"))
        c.run("shadow_mode.summary", _shadow)

        def _unapproved_contracts():
            from core.connector_registry import connector_registry
            for conn in connector_registry.list_connectors(scope_node_id, tenant_id,
                                                           entity_mode):
                for ct in connector_registry.list_contracts(conn["connector_id"]):
                    if not ct.get("approved_by"):
                        c.items.append(_item(
                            "query_contract_unapproved", "high",
                            f"미승인 조회 계약: {conn['connector_id']}/{ct['query_name']}",
                            ("승인되지 않은 Query Contract 로는 조회가 거부됩니다. "
                             "연계가 되는데 안 되는 것처럼 보이는 전형적인 원인입니다."),
                            "계약 내용을 검토하고 승인하십시오.",
                            conn["connector_id"], "connector"))
        c.run("connector_registry.list_contracts", _unapproved_contracts)

        def _skills():
            from core.skill_evolution import skill_evolution
            n = len(skill_evolution.list_pending_proposals() or [])
            if n:
                c.items.append(_item(
                    "skill_proposal_pending", "low", f"스킬 제안 검토 대기 {n}건",
                    "검토되지 않은 제안은 에이전트에 반영되지 않습니다.",
                    "AI 스킬 진화 화면에서 제안을 승인 또는 반려하십시오."))
        c.run("skill_evolution.list_pending_proposals", _skills)
        return c

    # ── ② 막혀 있는 것과 그 이유 ─────────────────────────────────────
    def blocked(self, scope_node_id: str = "", tenant_id: str = "",
                entity_mode: str = "REAL", max_gates: int = 30) -> _Collector:
        """승격이 **왜** 막혔는지. 게이트 판정을 다시 계산하지 않고 소유 모듈에 묻는다.

        ⚠️ 게이트 평가는 건당 비용이 있어 상한을 둔다. 자른 사실은 반드시 보고한다 —
          조용히 자르면 "막힌 게 이것뿐"으로 읽힌다."""
        c = _Collector()

        def _gates():
            from core.workspace_promotion import workspace
            rows = []
            for st in ("requested", "approved"):
                rows += [r for r in (workspace.list_promotions(st) or []) if r]
            rows = self._visible(rows, scope_node_id, tenant_id, entity_mode, "from_scope")
            truncated = max(0, len(rows) - max_gates)
            for r in rows[:max_gates]:
                g = workspace.evaluate_gate(r["release_id"],
                                            r.get("target_scope") or "enterprise")
                if g.get("promotable"):
                    continue
                for chk in g.get("checks", []):
                    if chk["state"] == "pass":
                        continue
                    c.items.append(_item(
                        f"gate_{chk['state']}",
                        "high" if chk["state"] == "fail" else "medium",
                        f"승격 차단({chk['check']}): {r['release_id']}",
                        # `unverifiable` 이 통과가 아니라는 사실을 문구로 못 박는다.
                        chk["why"] + ("" if chk["state"] == "fail" else
                                      " — `unverifiable` 은 통과가 아니라 확인하지 못한 것입니다."),
                        chk.get("suggested_action", ""), r["release_id"], "release"))
            if truncated:
                c.items.append(_item(
                    "gate_truncated", "info", f"게이트 평가 {truncated}건을 생략했습니다",
                    f"평가 비용 때문에 {max_gates}건까지만 계산했습니다 — 막힌 것이 이것뿐이라는 "
                    f"뜻이 아닙니다.",
                    "워크스페이스 화면에서 나머지 릴리스를 개별 확인하십시오."))
        c.run("workspace_promotion.evaluate_gate", _gates)
        return c

    # ── ③ 데이터 건강 ────────────────────────────────────────────────
    def data_health(self, scope_node_id: str = "", tenant_id: str = "",
                    entity_mode: str = "REAL", max_gaps: int = 20) -> _Collector:
        c = _Collector()

        def _gaps():
            from core.data_catalog import data_catalog
            gaps = data_catalog.governance_gaps(scope_node_id, tenant_id, entity_mode) or []
            for g in gaps[:max_gaps]:
                c.items.append(_item(
                    f"governance_{g['kind']}", g.get("severity", "medium"),
                    f"{g.get('asset') or g.get('asset_id')}: {g['kind']}",
                    g.get("why", ""), g.get("suggested_action", ""),
                    g.get("asset_id", ""), "data_asset"))
            if len(gaps) > max_gaps:
                c.items.append(_item(
                    "governance_truncated", "info",
                    f"거버넌스 결손 {len(gaps) - max_gaps}건을 더 표시하지 않았습니다",
                    "화면 상한 때문이며 해결된 것이 아닙니다.",
                    "거버넌스 콘솔에서 전체 목록을 확인하십시오."))
        c.run("data_catalog.governance_gaps", _gaps)

        def _contracts():
            from core.data_contract import data_contracts
            res = data_contracts.evaluate_all()
            for r in res.get("results", []):
                if r["state"] == "kept":
                    continue
                sev = {"breached": "high", "at_risk": "medium"}.get(r["state"], "medium")
                why = "; ".join(f["why"] for f in (r.get("findings") or [])[:3])
                if r["state"] == "unverifiable":
                    # ⚠️ `unverifiable` 은 문자열이 아니라 {"kind","why"} dict 목록이다
                    #   (`data_contract.evaluate` 실측). 문자열로 가정하면 조용히 깨진다.
                    uv = [(u.get("why") or u.get("kind") or "") if isinstance(u, dict) else str(u)
                          for u in (r.get("unverifiable") or [])]
                    why = ("확인하지 못한 항목이 있습니다: " + "; ".join([u for u in uv if u][:3])
                           + " — '계약 준수 중'이라는 거짓 안심은 계약이 없는 것보다 위험합니다.")
                c.items.append(_item(
                    f"contract_{r['state']}", sev,
                    f"데이터 계약 {r['state']}: {r['contract_key']} v{r['version']}",
                    why or "(사유 미기록)",
                    ("계약을 위반한 자산을 고치거나 계약을 갱신하십시오."
                     if r["state"] != "unverifiable" else
                     "확인 불가 항목의 근거(품질 측정·자산 등록)를 채우십시오."),
                    r["contract_id"], "data_contract"))
        c.run("data_contract.evaluate_all", _contracts)
        return c

    # ── ④ 프로그램 사용여부 ──────────────────────────────────────────
    def programs(self) -> _Collector:
        """사용 중단·예고된 프로그램. 삭제되지 않았으므로 목록에서 사라지지 않는다."""
        c = _Collector()

        def _life():
            from core.program_lifecycle import DEPRECATED, DISABLED, program_lifecycle
            for r in program_lifecycle.list_statuses():
                if r["status"] == DISABLED:
                    rep = r.get("replacement_release_id") or ""
                    c.items.append(_item(
                        "program_disabled", "medium" if rep else "high",
                        f"사용 중단: {r['release_id']}",
                        (r.get("reason") or "(사유 미기록)")
                        + (f" 대체: {rep}" if rep else
                           " ⚠️ 대체 프로그램이 지정되지 않았습니다 — 사용자가 막다른 길에서 "
                           "같은 프로그램을 다시 만들게 됩니다."),
                        "" if rep else "대체 프로그램을 지정하십시오.",
                        r["release_id"], "release"))
                elif r["status"] == DEPRECATED:
                    c.items.append(_item(
                        "program_deprecated", "low", f"사용 중단 예고: {r['release_id']}",
                        r.get("reason") or "(사유 미기록)",
                        "종료 전에 사용 부서를 이전시키십시오.", r["release_id"], "release"))
        c.run("program_lifecycle.list_statuses", _life)
        return c

    # ── ⑤ 비용 ───────────────────────────────────────────────────────
    def cost(self, principal=None) -> Dict[str, Any]:
        """비용 집계. **여기서 다시 계산하지 않고** 소유 모듈의 집계를 재사용한다.

        ⚠️ 두 곳에서 계산하면 반드시 어긋나고, 그때 어느 쪽이 맞는지 아무도 모른다.
          (layering 부채: core 가 api 를 import 한다 — 집계를 core 로 옮기는 것이 정리 방향이다.)"""
        out: Dict[str, Any] = {"available": False, "reason": ""}
        try:
            from api.routes.telemetry_control import _read_records, aggregate, apply_scope
            recs = _read_records()
            if principal is not None:
                scoped = apply_scope(recs, principal)
                recs = scoped.get("records", recs) if isinstance(scoped, dict) else recs
            agg = aggregate(recs)
            t = agg.get("totals", agg)
            out.update({
                "available": True, "calls": t.get("calls", 0),
                "cost_usd": t.get("cost_usd", 0.0),
                "priced_calls": t.get("priced_calls", 0),
                "unpriced_calls": t.get("unpriced_calls", 0),
                # ★ 단가를 모르는 호출이 있으면 총액은 **하한**이다. 완전한 총액으로 읽히면
                #   예산 판단이 틀린다.
                "cost_complete": bool(t.get("cost_complete", False)),
                "note": ("" if t.get("cost_complete") else
                         f"단가가 등록되지 않은 호출 {t.get('unpriced_calls', 0)}건이 있어 "
                         f"총액은 **하한**입니다 — 실제 비용은 이보다 큽니다."),
            })
        except Exception as e:
            out["reason"] = f"비용 집계를 읽을 수 없습니다: {e}"
        return out

    # ── 브리핑 ───────────────────────────────────────────────────────
    def briefing(self, actor: str = "", scope_node_id: str = "", tenant_id: str = "",
                 entity_mode: str = "REAL", principal=None) -> Dict[str, Any]:
        """권한 범위 안의 전사 상태 1장. 섹션 순서는 `SECTIONS` 를 따른다."""
        collectors = {
            "my_decisions": self.my_decisions(actor, scope_node_id, tenant_id, entity_mode),
            "blocked": self.blocked(scope_node_id, tenant_id, entity_mode),
            "data_health": self.data_health(scope_node_id, tenant_id, entity_mode),
            "programs": self.programs(),
        }
        sections: Dict[str, Any] = {}
        unavailable: List[Dict[str, str]] = []
        for name in SECTIONS:
            if name == "cost":
                continue
            col = collectors[name]
            sections[name] = {"items": col.sorted_items(), "count": len(col.items)}
            unavailable += [dict(u, section=name) for u in col.unavailable]

        cost = self.cost(principal)
        sections["cost"] = cost
        if not cost["available"]:
            unavailable.append({"section": "cost", "source": "telemetry aggregate",
                                "error": cost["reason"]})

        all_items = [i for name in SECTIONS if name != "cost"
                     for i in sections[name]["items"]]
        by_sev: Dict[str, int] = {}
        for i in all_items:
            by_sev[i["severity"]] = by_sev.get(i["severity"], 0) + 1

        # ★ 비용이 불완전한 것도 "완전한 브리핑"이 아니다.
        complete = not unavailable and cost.get("cost_complete", False)
        return {
            "generated_at": _now(), "actor": actor,
            "scope": {"scope_node_id": scope_node_id, "tenant_id": tenant_id,
                      "entity_mode": entity_mode,
                      "filtered": bool(scope_node_id or tenant_id)},
            "sections": sections,
            "attention_count": sum(1 for i in all_items if i["severity"] in ("high", "medium")),
            "by_severity": by_sev,
            "top": sorted(all_items, key=lambda i: _rank(i["severity"]))[:5],
            # ⚠️ 읽지 못한 소스. 비어 있지 않으면 이 브리핑은 **전부가 아니다.**
            "unavailable": unavailable,
            "complete": complete,
            "note": ("" if complete else
                     "⚠️ 이 브리핑은 완전하지 않습니다 — "
                     + (f"읽지 못한 소스 {len(unavailable)}건이 있습니다. " if unavailable else "")
                     + ("비용 총액이 하한입니다. " if not cost.get("cost_complete") else "")
                     + "빠진 항목이 '문제 없음'을 의미하지 않습니다."),
        }


enterprise_briefing = EnterpriseBriefing()
