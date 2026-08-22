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


def create_router(service: OntologyRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ontology", tags=["Manufacturing Ontology"])

    @router.get("/model/status")
    async def model_status(contract_id: str = "",
                           p: Principal = Depends(current_principal)):
        assert_identified(p, "기업 경영 의미지도")
        return {"status": "success", "data": await asyncio.to_thread(
            service.model_status, contract_id)}

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
