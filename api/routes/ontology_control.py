"""G2 manufacturing-management ontology REST contract.

The router is a factory so tests and the future product integration can inject an
``OntologyRuntime`` with the correct namespace-specific object-scope resolver.
The global runtime deliberately has no resolver yet; mounting it before ECM/MDM/
Snapshot resolution is available would turn missing scope data into a public graph.

LLM calls: zero.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import (Principal, assert_can_manage_standard, assert_identified,
                      current_principal, viewing_context, visibility_block_reason)
from core import app_policy
from core.ontology_runtime import (ObjectRef, OntologyAccessError, OntologyError,
                                   OntologyIntegrityError, OntologyRuntime, RelationProposal,
                                   ontology_runtime)


class ObjectRefInput(BaseModel):
    namespace: str
    object_type: str
    object_id: str

    def runtime(self) -> ObjectRef:
        return ObjectRef(self.namespace, self.object_type, self.object_id)


class ModelContractInput(BaseModel):
    contract: Dict[str, Any]


class RelationProposalInput(BaseModel):
    subject: ObjectRefInput
    relation_type_id: str
    object: ObjectRefInput
    tenant_id: str
    enterprise_scope_id: str
    entity_mode: str
    owner_organization_id: str
    effective_from: str
    effective_to: str = ""
    origin: str = "user"
    evidence_refs: List[str] = Field(default_factory=list)
    source_lineage: List[str] = Field(default_factory=list)
    calculation_ref: str = ""
    classification: str = "INTERNAL"
    scope_type: str = "ORG_PRIVATE"
    scope_assignments: List[str] = Field(default_factory=list)
    supersedes_relation_id: str = ""

    def runtime(self) -> RelationProposal:
        return RelationProposal(
            subject=self.subject.runtime(), relation_type_id=self.relation_type_id,
            object=self.object.runtime(), tenant_id=self.tenant_id,
            enterprise_scope_id=self.enterprise_scope_id, entity_mode=self.entity_mode,
            owner_organization_id=self.owner_organization_id,
            effective_from=self.effective_from, effective_to=self.effective_to,
            origin=self.origin, evidence_refs=tuple(self.evidence_refs),
            source_lineage=tuple(self.source_lineage), calculation_ref=self.calculation_ref,
            classification=self.classification, scope_type=self.scope_type,
            scope_assignments=tuple(self.scope_assignments),
            supersedes_relation_id=self.supersedes_relation_id)


class ApprovalInput(BaseModel):
    decision_ledger_id: str


class ReasonInput(BaseModel):
    reason: str
    decision_ledger_id: str = ""


class RelationDecisionInput(BaseModel):
    rationale: str


class ImpactQueryInput(BaseModel):
    roots: List[ObjectRefInput]
    target_types: List[str] = Field(default_factory=list)
    relation_types: List[str] = Field(default_factory=list)
    as_of: str
    max_depth: int = 6
    max_paths: int = 20


def _subject(p: Principal) -> app_policy.Subject:
    return app_policy.Subject(
        user_id=p.user_id or "", scope=p.scope, ctx=viewing_context(p),
        session_id=p.session_id or "", blocked_reason=visibility_block_reason(p))


def _raise(exc: Exception) -> None:
    if isinstance(exc, OntologyAccessError):
        raise HTTPException(status_code=404, detail="요청한 온톨로지 자원을 찾을 수 없습니다.")
    if isinstance(exc, OntologyIntegrityError):
        raise HTTPException(status_code=503, detail=f"온톨로지 상태를 확인할 수 없습니다: {exc}")
    if isinstance(exc, OntologyError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _apply_relation_decision(service: OntologyRuntime, relation_id: str, action: str,
                             rationale: str, actor: str,
                             subject: app_policy.Subject) -> Dict[str, Any]:
    """Record the actual domain decision, then bind it to the relation.

    The generic Decision Ledger API is deliberately read-only.  A browser must not manufacture
    arbitrary ledger events and paste their ids into an approval form.  This domain path records
    only the event that is being applied, and compensates it when the ontology write fails.
    """
    from core.decision_ledger import DecisionLedgerError, decision_ledger

    why = (rationale or "").strip()
    who = (actor or "").strip()
    if not why:
        raise OntologyError("the decision rationale is required.")
    if action not in ("approve", "retire"):
        raise OntologyError("unsupported relation decision action.")

    row = service.relation_for_management(subject, relation_id)
    event_type = ("ONTOLOGY_RELATION_APPROVED" if action == "approve"
                  else "ONTOLOGY_RELATION_RETIRED")
    expected, finished = (("IN_REVIEW", "APPROVED") if action == "approve"
                          else ("APPROVED", "RETIRED"))

    # Network retries do not create unattached duplicate approvals.
    if row.get("approval_status") == finished and row.get("ledger_correlation_id"):
        event_id = str(row["ledger_correlation_id"])
        try:
            existing = decision_ledger.get_event_strict(event_id)
            invalidated = decision_ledger.has_invalidating_child(
                event_id, ("ONTOLOGY_APPROVAL_REVOKED",))
        except DecisionLedgerError as exc:
            raise OntologyIntegrityError("decision ledger could not be verified.") from exc
        if (existing and not invalidated
                and existing.get("event_type") == event_type
                and existing.get("subject_type") == "ontology_relation"
                and existing.get("subject_id") == relation_id
                and existing.get("actor_id") == who):
            return {"relation": row, "decision_event": existing, "idempotent": True}

    if row.get("approval_status") != expected:
        raise OntologyError(f"only {expected} relations can be {action}d.")
    if action == "approve" and str(row.get("submitted_by") or "") == who:
        raise OntologyError("self approval is forbidden.")
    if action == "approve" and not list(row.get("evidence_refs") or []):
        raise OntologyError("a relation without evidence cannot be approved.")

    try:
        event = decision_ledger.append(
            event_type=event_type, subject_type="ontology_relation", subject_id=relation_id,
            actor_type="user", actor_id=who,
            decision="APPROVE" if action == "approve" else "RETIRE",
            rationale=why, evidence_refs=list(row.get("evidence_refs") or []),
            input_version_refs=[{
                "relation_id": relation_id, "version": row.get("version"),
                "approval_status": row.get("approval_status"),
                "effective_from": row.get("effective_from"),
                "effective_to": row.get("effective_to"),
                "calculation_ref": row.get("calculation_ref"),
                "scope_node_id": row.get("enterprise_scope_id"),
            }],
            output_version_refs=[{"relation_id": relation_id, "approval_status": finished}],
            tenant_id=str(row.get("tenant_id") or "tenant_default"),
            # Decision Ledger currently stores department ids in this field (ECM-lite).
            enterprise_scope_id=str(row.get("owner_organization_id") or ""),
            entity_mode=str(row.get("entity_mode") or "REAL"))
    except DecisionLedgerError as exc:
        raise OntologyIntegrityError("decision ledger could not record the relation decision.") from exc

    try:
        if action == "approve":
            updated = service.approve(relation_id, who, event["event_id"], subject)
        else:
            updated = service.retire(relation_id, who, why, event["event_id"], subject)
    except Exception as original:
        try:
            decision_ledger.append(
                event_type="ONTOLOGY_APPROVAL_REVOKED", subject_type="ontology_relation",
                subject_id=relation_id, actor_type="system", actor_id=who,
                decision="COMPENSATE", rationale=(
                    f"관계 {action} 반영 실패로 승인 사건 취소: {type(original).__name__}"),
                parent_event_id=event["event_id"],
                tenant_id=str(row.get("tenant_id") or "tenant_default"),
                enterprise_scope_id=str(row.get("owner_organization_id") or ""),
                entity_mode=str(row.get("entity_mode") or "REAL"))
        except Exception as compensation:
            raise OntologyIntegrityError(
                f"relation decision failed and ledger compensation also failed; repair required "
                f"for {event['event_id']}.") from compensation
        raise original

    return {"relation": updated, "decision_event": event, "idempotent": False}


def create_router(service: OntologyRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ontology", tags=["Manufacturing Ontology"])

    @router.get("/model/status")
    async def model_status(contract_id: str = "",
                           p: Principal = Depends(current_principal)):
        assert_identified(p, "기업 경영 의미지도")
        return {"status": "success", "data": await asyncio.to_thread(
            service.model_status, contract_id)}

    @router.get("/runtime/status")
    async def runtime_status(p: Principal = Depends(current_principal)):
        """Resolver/display readiness, distinct from model installation status.

        Counts describe implemented object types only.  They never count hidden
        business rows, so an unready namespace cannot leak another scope's data.
        """
        assert_identified(p, "기업 경영 의미지도")
        from core.ontology_namespace_capabilities import runtime_status as _status
        from core.ontology_resolvers import (current_decision_object_types,
                                             current_g4_object_types,
                                             current_knowledge_object_types,
                                             current_scenario_object_types)
        from core.data_preparation import scope_index
        from core.data_preparation.store import data_preparation_store
        try:
            materialized = await asyncio.to_thread(
                scope_index.materialized_object_types, data_preparation_store)
        except Exception as exc:
            _raise(OntologyIntegrityError(
                "업무 객체 색인 준비 상태를 읽지 못했습니다."))
            raise AssertionError("unreachable") from exc
        materialized = dict(materialized)
        # ECM is resolved from its own authoritative directory, not the snapshot index.
        materialized["ecm"] = ("organization-node",)
        try:
            decision_types = await asyncio.to_thread(current_decision_object_types)
            scenario_types = await asyncio.to_thread(current_scenario_object_types)
            materialized["decision"] = tuple(sorted(set(decision_types + scenario_types)))
            materialized["g4"] = await asyncio.to_thread(current_g4_object_types)
            materialized["knowledge"] = await asyncio.to_thread(
                current_knowledge_object_types)
        except Exception as exc:
            _raise(OntologyIntegrityError(
                "의사결정 객체 결속 준비 상태를 읽지 못했습니다."))
            raise AssertionError("unreachable") from exc
        return {"status": "success", "data": _status(materialized)}

    @router.get("/model/{contract_id}")
    async def model_contract(contract_id: str, contract_version: str = "",
                             p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.model_contract, contract_id,
                                           contract_version)
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/model/validate")
    async def validate_model(req: ModelContractInput,
                             p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.validate_model_contract, req.contract)
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/model/install")
    async def install_model(req: ModelContractInput,
                            p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.install_model_contract, req.contract,
                                           p.user_id or "")
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.get("/proposal/context")
    async def proposal_context(p: Principal = Depends(current_principal)):
        """Verified defaults for a relation proposal; the browser never invents scope ids."""
        assert_can_manage_standard(p)
        ctx = viewing_context(p)
        owner = str(getattr(p.scope, "primary_dept_id", "") or "").strip()
        if not owner:
            owner = next(iter(sorted(getattr(p.scope, "writable_dept_ids", ()) or ())), "")
        scope_node = str(ctx.get("scope_node_id", "") or "").strip()
        return {"status": "success", "data": {
            "tenant_id": str(ctx.get("tenant_id", "") or ""),
            "enterprise_scope_id": scope_node,
            "entity_mode": str(ctx.get("entity_mode", "") or ""),
            "owner_organization_id": owner,
            "ready": bool(ctx.get("tenant_id") and scope_node and ctx.get("entity_mode") and owner),
            "reason": ("" if scope_node else
                       "현재 ‘권한 범위 전체’는 조회 문맥입니다. 관계를 저장하려면 화면 상단 "
                       "OPERATING CONTEXT에서 귀속할 회사·조직 범위를 하나 선택하십시오."),
        }}

    @router.get("/relations")
    async def relations(approval_status: str = "", limit: int = 200,
                        p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.list_relations, _subject(p),
                                           approval_status, limit)
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/propose")
    async def propose(req: RelationProposalInput,
                      p: Principal = Depends(current_principal)):
        assert_identified(p, "기업 경영 의미지도")
        try:
            data = await asyncio.to_thread(service.propose_relation, req.runtime(),
                                           p.user_id or "", _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/submit")
    async def submit(relation_id: str, p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.submit, relation_id, p.user_id or "",
                                           _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/approve")
    async def approve(relation_id: str, req: ApprovalInput,
                      p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.approve, relation_id, p.user_id or "",
                                           req.decision_ledger_id, _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/decisions/approve")
    async def decide_approve(relation_id: str, req: RelationDecisionInput,
                             p: Principal = Depends(current_principal)):
        """Approve as one product action: ledger event first, relation binding second."""
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(
                _apply_relation_decision, service, relation_id, "approve", req.rationale,
                p.user_id or "", _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/reject")
    async def reject(relation_id: str, req: ReasonInput,
                     p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.reject, relation_id, p.user_id or "",
                                           req.reason, _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/retire")
    async def retire(relation_id: str, req: ReasonInput,
                     p: Principal = Depends(current_principal)):
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(service.retire, relation_id, p.user_id or "",
                                           req.reason, req.decision_ledger_id, _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/relations/{relation_id}/decisions/retire")
    async def decide_retire(relation_id: str, req: RelationDecisionInput,
                            p: Principal = Depends(current_principal)):
        """Retire as one product action and compensate the ledger if state binding fails."""
        assert_can_manage_standard(p)
        try:
            data = await asyncio.to_thread(
                _apply_relation_decision, service, relation_id, "retire", req.rationale,
                p.user_id or "", _subject(p))
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.post("/query/impact")
    async def impact(req: ImpactQueryInput, p: Principal = Depends(current_principal)):
        assert_identified(p, "기업 경영 의미지도")
        try:
            data = await asyncio.to_thread(
                service.find_paths, _subject(p), [v.runtime() for v in req.roots],
                req.target_types, req.relation_types, req.as_of, req.max_depth, req.max_paths)
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.get("/objects")
    async def objects(as_of: str, namespace: str = "", object_type: str = "",
                      relation_types: str = "", limit: int = 200,
                      p: Principal = Depends(current_principal)):
        """[M0-4] 시작점으로 고를 수 있는 객체들 — **화면이 손으로 치지 않게 한다.**

        ⚠️ 가시성은 영향 질의와 **같은 판정**이다. 목록에는 뜨는데 질의하면 빈 결과가
          나오면 사용자는 그것을 고장으로 읽는다."""
        assert_identified(p, "기업 경영 의미지도")
        rels = [v for v in (relation_types or "").split(",") if v.strip()]
        try:
            data = await asyncio.to_thread(service.list_objects, _subject(p), as_of,
                                           namespace, object_type, rels, limit)
        except Exception as exc:
            _raise(exc)
        return {"status": "success", "data": data}

    @router.get("/relations/{relation_id}/evidence")
    async def evidence(relation_id: str, as_of: str,
                       p: Principal = Depends(current_principal)):
        assert_identified(p, "기업 경영 의미지도")
        try:
            data = await asyncio.to_thread(service.relation_evidence, _subject(p), relation_id,
                                           as_of)
        except Exception as exc:
            _raise(exc)
        if data is None:
            raise HTTPException(status_code=404, detail="요청한 온톨로지 자원을 찾을 수 없습니다.")
        return {"status": "success", "data": data}

    return router


#: ★ [2026-08-20] 제품 Resolver(ECM 범위 + Decision Ledger 승인)가 배선돼 `main.py` 에 등록됐다.
#: ⚠️ 등록 조건은 `tests/test_ontology_wiring_contract.py` 가 **양방향으로** 감시한다 —
#:   Resolver 없이 붙여도, 붙이고 등록을 잊어도 실패한다.
#: ⚠️ 다만 `dataset`·`mdm`·`external`·`g4`·`decision`·`knowledge` 는 **아직 막혀 있다**(503).
router = create_router(ontology_runtime)
