"""B3 서버 승인 업무 문맥. 요구 초안은 가능하지만 데이터 사용권을 발급하지 않는다.

ECM 승인판/현재 head, DP 고정 원문/인스턴스/인증판, 현재 조직·원장 정책을 읽는다.
DB 사이의 분산 원자성을 주장하지 않는다. 소비자는 서버에 보존한 DTO로 매 행위
직전에 revalidate를 호출하고, 실제 RAW 및 행위별 권한/용도는 실행 경계에서 검사한다.
이 모듈은 RAW를 읽거나 인증·정책·업무판·인스턴스를 생성/변경하지 않는다.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from typing import Annotated, Literal

from pydantic import Field, model_validator

from core.enterprise_context.process_configuration import ProcessConfigurationService, missing
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, StrictModel, fingerprint

Action = Literal["READ", "DRAFT", "BOOTSTRAP", "GENERATE", "RUN", "RELEASE"]
ACTIONS = ("READ", "DRAFT", "BOOTSTRAP", "GENERATE", "RUN", "RELEASE")
DATA_ACTIONS = ("GENERATE", "RUN", "RELEASE")
CONTEXT_KEYS = ("tenant_id", "context_root_id", "entity_mode", "scope_node_id")
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class ContextKey(StrictModel):
    tenant_id: Identifier
    context_root_id: Identifier
    entity_mode: Literal["REAL", "VIRTUAL", "COMPETITOR_REFERENCE"]
    scope_node_id: str


class DataRequirement(StrictModel):
    process_id: Identifier
    requirement_key: Identifier
    logical_requirement: str
    mandatory: bool
    candidate_contract_keys: list[Identifier]
    unresolved_requirement: bool


class VerifiedBindingRef(StrictModel):
    process_id: Identifier
    requirement_key: Identifier
    instance_id: Identifier
    contract_key: Identifier
    artifact_digest: Sha256
    binding_id: Identifier
    binding_fingerprint: Sha256
    snapshot_id: Identifier
    snapshot_fingerprint: Sha256
    checksum: Sha256
    ownership_binding_id: Identifier
    ownership_fingerprint: Sha256
    certification_state: Literal["OWNER_CERTIFIED", "SOURCE_CERTIFIED", "DEMO_CERTIFIED"]
    certification_subject_id: Identifier | None
    certification_subject_digest: Sha256 | None
    signing_policy_id: Identifier | None
    signing_policy_digest: Sha256 | None
    certified_use_kind: Literal["OPERATIONAL", "MANAGEMENT"] | None
    usage_policy_fingerprint: Sha256

    @model_validator(mode="after")
    def certification_kind(self):
        values = (self.certification_subject_id, self.certification_subject_digest,
                  self.signing_policy_id, self.signing_policy_digest, self.certified_use_kind)
        if self.certification_state == "OWNER_CERTIFIED":
            if any(value is None for value in values):
                raise ValueError("owner certification proof required")
        elif any(value is not None for value in values):
            raise ValueError("non-owner certification must not impersonate owner signatures")
        return self


class Blocker(StrictModel):
    reason_code: Identifier
    process_id: Identifier | None
    requirement_key: Identifier | None
    blocking_actions: list[Action]
    next_action: str


class ProfileSource(StrictModel):
    kind: Literal["PROCESS_PROFILE"]
    configuration_id: Identifier
    profile_id: Identifier
    fingerprint: Sha256


class PackSource(StrictModel):
    kind: Literal["PROCESS_PACK"]
    artifact_digest: Sha256
    pack_id: Identifier
    pack_version: Identifier
    pack_digest: Sha256
    instance_id: Identifier
    template_keys: list[Identifier]


class ProcessContextDTO(StrictModel):
    schema_version: Literal[1]
    configuration_id: Identifier
    profile_id: Identifier
    process_ids: list[Identifier] = Field(min_length=1, max_length=200)
    process_semantic_fingerprint: Sha256
    configuration_fingerprint: Sha256
    context_key: ContextKey
    data_requirements: list[DataRequirement]
    verified_binding_refs: list[VerifiedBindingRef]
    blockers: list[Blocker]
    permitted_actions: list[Action]
    sources: list[Annotated[ProfileSource | PackSource, Field(discriminator="kind")]]

    @model_validator(mode="after")
    def unique_references(self):
        ids = self.process_ids
        requirements = [(r.process_id, r.requirement_key) for r in self.data_requirements]
        refs = [(r.process_id, r.requirement_key, r.instance_id, r.contract_key)
                for r in self.verified_binding_refs]
        if (ids != sorted(set(ids)) or len(set(requirements)) != len(requirements)
                or refs != sorted(set(refs)) or len(set(self.permitted_actions)) != len(self.permitted_actions)):
            raise ValueError("duplicate or noncanonical context references")
        if any(pid not in ids for pid, _ in requirements):
            raise ValueError("requirement outside selected processes")
        if any((r.process_id, r.requirement_key) not in requirements for r in self.verified_binding_refs):
            raise ValueError("binding without logical requirement")
        return self

    @model_validator(mode="before")
    @classmethod
    def exact_version(cls, value):
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("integer schema version required")
        return value


# 외부 소비자는 형식 검증만 재사용할 수 있다. 이 모델 검증은 서버 권한 검증이 아니다.
ProcessContext = ProcessContextDTO


def _invalid():
    return ProcessError("PROCESS_CONTEXT_INVALID", "업무 문맥의 필수 필드·판본·참조 형식을 확인하십시오.", 422)


def _unavailable(code="PROCESS_CONTEXT_UNAVAILABLE"):
    return ProcessError(code, "업무 문맥 또는 데이터 근거의 무결성을 확인하지 못했습니다.", 503)


def _conflict(code="PROCESS_SEMANTIC_CONFLICT"):
    return ProcessError(code, "고정 업무·데이터 근거가 변경되었습니다. 초안을 보존하고 다시 검토하십시오.", 409)


def _block(code, process_id=None, requirement_key=None):
    return dict(reason_code=code, process_id=process_id, requirement_key=requirement_key,
                blocking_actions=list(DATA_ACTIONS),
                next_action="요구사항 초안을 보존하고 데이터 담당자와 원천·인증·사용 보류 근거를 확인하십시오.")


def _ref_key(ref):
    return tuple(ref[k] for k in ("process_id", "requirement_key", "instance_id", "contract_key"))


class _HeldReference(ProcessError):
    """권한·고정 판/증거는 검증했지만 현재 원천 보류 때문에 소비 불가인 과거 참조."""
    def __init__(self, ref):
        super().__init__("DATA_USAGE_HOLD", "고정 참조의 현재 데이터 사용이 보류되었습니다.", 409)
        self.ref = ref


def snapshot_fingerprint(snapshot):
    """RAW 경로/조회시각 제외. 인증판의 정체성·내용·대사·용도·인증 증거 지문 v1."""
    keys = ("snapshot_id", "binding_id", "instance_id", "dataset_contract_key", "tenant_id",
            "scope_node_id", "entity_mode", "state", "data_kind", "checksum", "content_fingerprint",
            "byte_size", "row_count", "schema_json", "profile_json", "control_total_json",
            "quarantine_json", "period_from", "period_to", "certified_use_kind", "certified_by", "certified_at")
    return fingerprint({"schema_version": 1, "snapshot": {k: snapshot[k] for k in keys}})


class ProcessContextService:
    def __init__(self, repo=None, store=None):
        self.configuration = ProcessConfigurationService(repo=repo, store=store)
        self.repo = self.configuration.repo
        self.store = store

    def _store(self):
        if self.store is None:
            from core.data_preparation.store import data_preparation_store
            return data_preparation_store
        return self.store

    @staticmethod
    @contextmanager
    def _errors():
        from core.data_preparation import certification_authority as ca, ownership_binding as ob
        try:
            yield
        except ProcessError:
            raise
        except ca.CertificationError as exc:
            if exc.status_code == 404:
                raise missing() from exc
            raise ProcessError(exc.reason_code, "현재 데이터 권한·인증 근거를 확인하십시오.", exc.status_code) from exc
        except (sqlite3.Error, ob.OwnershipUnavailable, ob.OwnershipIntegrityError, OSError) as exc:
            raise _unavailable() from exc
        except (KeyError, TypeError, ValueError) as exc:
            # 저장된 형식 손상을 빈 데이터/초안 허용으로 숨기지 않는다.
            raise _unavailable() from exc

    @staticmethod
    def _input(boundary, context, profile_id, process_ids):
        try:
            boundary = ProcessBoundary.model_validate(boundary)
            if (not isinstance(context, dict) or not isinstance(profile_id, str) or not profile_id.strip()
                    or not isinstance(process_ids, list) or not 1 <= len(process_ids) <= 200
                    or any(not isinstance(pid, str) or not pid.strip() or len(pid) > 160 for pid in process_ids)
                    or len(set(process_ids)) != len(process_ids)):
                raise ValueError("explicit approved selection required")
        except (TypeError, ValueError) as exc:
            raise _invalid() from exc
        if context.get("context_root_id", boundary.context_root_id) != boundary.context_root_id:
            raise missing()
        return boundary, sorted(process_ids)

    def _profiles(self, boundary, actor, context, profile_id):
        """B1 검증을 같은 ECM 읽기 snapshot에서 재사용한다. 다른 회사 ID는 항상404."""
        svc = self.configuration
        with svc.transaction() as conn:
            svc._authorize(conn, boundary, actor, context)
            head = svc._head(conn, boundary)
            if not head or not conn.execute(
                    "SELECT 1 FROM enterprise_profiles WHERE profile_id=? AND configuration_id=? AND approved_at<>''",
                    (profile_id, head["configuration_id"])).fetchone():
                raise missing()
            _, historical = svc._profile(conn, profile_id, head)
            _, current = svc._profile(conn, head["active_profile_id"], head)
            return historical, current, head

    def _permissions(self, boundary, actor, context):
        """기능 capability와 해당 업무 범위의 변경권을 동시에 검사한다."""
        from core import admin_capability as caps
        specs = {"READ": ("read", None), "DRAFT": ("propose", None),
                 "BOOTSTRAP": ("propose", caps.PROJECT_CREATE),
                 "GENERATE": ("propose", caps.PROJECT_RUN),
                 "RUN": ("read", caps.AGENT_EXECUTE),
                 "RELEASE": ("read", caps.PROJECT_RELEASE)}
        allowed = []
        with self.configuration.transaction() as conn:
            # 읽기 자체가 철회됐다면 목록으로 숨기지 않고 요청을 실패시킨다.
            self.configuration._authorize(conn, boundary, actor, context)
            for action, (mode, capability) in specs.items():
                try:
                    rights = self.configuration._authorize(conn, boundary, actor, context, mode)
                except ProcessError as exc:
                    if exc.status_code == 403 and exc.reason_code == "PROCESS_ACTION_FORBIDDEN":
                        continue
                    raise
                if capability is None or rights.has(capability):
                    allowed.append(action)
        return allowed

    def _describe(self, payload, process_ids, boundary):
        from core.data_preparation.process_pack_artifacts import get_bundle
        nodes = {n["process_id"]: n for n in payload["nodes"]}
        if any(pid not in nodes for pid in process_ids):
            raise _conflict("PROCESS_SELECTION_CONFLICT")
        selected = set(process_ids)
        relevant = set(selected)
        for pid in process_ids:
            parent = nodes[pid]["parent_process_id"]
            if parent:
                relevant.add(parent)
        if any(not nodes[pid]["enabled"] for pid in relevant):
            raise _conflict("PROCESS_DISABLED")
        sources, bundles, by_node = [], {}, {}
        for source in payload["template_sources"]:
            mapping = {key: pid for key, pid in source["template_process_ids"].items() if pid in relevant}
            if not mapping:
                continue
            bundle = get_bundle(self._store(), source["artifact_digest"])
            if (source["kit_id"] != bundle["kit_id"] or source["kit_version"] != bundle["version"]
                    or source["pack_id"] != bundle["pack"]["pack_id"]
                    or source["pack_version"] != bundle["pack"]["version"]
                    or source["accepted_standard_digest"] != bundle["pack_digest"]
                    or bundle["profile"]["mode"] != boundary.entity_mode):
                raise _unavailable("PROCESS_ARTIFACT_UNAVAILABLE")
            templates = {t["template_key"]: t for t in bundle["pack"]["templates"]}
            for key, pid in mapping.items():
                if key not in templates or templates[key]["level"] != nodes[pid]["level"]:
                    raise _unavailable("PROCESS_ARTIFACT_UNAVAILABLE")
                by_node[pid] = (source, bundle, templates[key])
            bundles[source["artifact_digest"]] = (source, bundle)
            sources.append(dict(kind="PROCESS_PACK", artifact_digest=source["artifact_digest"],
                                pack_id=source["pack_id"], pack_version=source["pack_version"],
                                pack_digest=bundle["pack_digest"], instance_id=source["kit_instance_ref"],
                                template_keys=sorted(mapping)))
        meanings, requirements, blockers = [], [], []
        for pid in sorted(relevant):
            node = nodes[pid]
            meaning = {k: node[k] for k in ("process_id", "level", "parent_process_id", "enabled", "origin")}
            meaning["selected"] = pid in selected
            if pid not in by_node:
                # 이름/note를 목적·입출력·실행 정책으로 추측하지 않는다.
                meaning.update(purpose=None, input_roles=None, output_roles=None, policy=None, requirements=[])
                if pid in selected:
                    blockers.append(_block("PROCESS_REQUIREMENTS_UNRESOLVED", pid))
            else:
                source, bundle, template = by_node[pid]
                required = []
                bindings = {b["requirement_key"]: b for b in payload["bindings"]
                            if b["kind"] == "DATA_REQUIREMENT" and b["process_id"] == pid}
                specs = {r["logical_requirement_key"]: r for r in template["data_requirements"]}
                if set(bindings) != set(specs):
                    raise _unavailable("PROCESS_REQUIREMENT_UNAVAILABLE")
                for key, spec in sorted(specs.items()):
                    binding = bindings[key]
                    row = dict(process_id=pid, requirement_key=key, logical_requirement=spec["logical_requirement"],
                               mandatory=binding["mandatory"], candidate_contract_keys=sorted(binding["candidate_dataset_keys"]),
                               unresolved_requirement=spec["unresolved_requirement"])
                    required.append(row)
                    if pid in selected:
                        requirements.append(row)
                # 원문 SHA·판번·표시명·배치는 무결성 출처일 뿐 의미 재료가 아니다.
                meaning.update(template_key=node["template_key"], instance_id=source["kit_instance_ref"],
                               purpose=template["purpose"], trigger=template["trigger"],
                               input_roles=sorted(template["input_roles"]), output_roles=sorted(template["output_roles"]),
                               policy={k: bundle["profile"][k] for k in ("mode", "data_class", "setup_only", "status")},
                               requirements=required)
            meanings.append(meaning)
        return dict(semantic=fingerprint({"schema_version": 1, "selected_process_ids": process_ids, "nodes": meanings}),
                    requirements=requirements, blockers=blockers,
                    sources=sorted(sources, key=lambda s: (s["instance_id"], s["artifact_digest"])),
                    bundles=bundles, by_node=by_node)

    @staticmethod
    def _instance(conn, boundary, source, bundle):
        instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (source["kit_instance_ref"],)).fetchone()
        expected = dict(kit_id=bundle["kit_id"], version=bundle["version"], kit_fingerprint=bundle["artifact_digest"],
                        tenant_id=boundary.tenant_id, entity_mode=boundary.entity_mode,
                        scope_node_id=boundary.scope_node_id or boundary.context_root_id)
        if instance is None or any(instance[k] != expected[k] for k in ("tenant_id", "entity_mode", "scope_node_id")):
            raise missing()
        if instance["status"] != "active":
            raise _conflict("PROCESS_INSTANCE_INACTIVE")
        #: ★ [2026-09-25] 업그레이드한 적용본은 같은 인스턴스 ID 로 여러 판본에 고정된 이력을 갖는다.
        #:   인스턴스 행·원 링크는 원 정체성으로 검증하고(`pins` 안의 `_link`), 이 업무판이 가리키는
        #:   번들은 **그 이력 안에** 있어야 한다. 과거 승인판(옛 판본)도 이력에 있으므로 그대로 읽힌다.
        #: ★ [2026-09-25 Codex §19.1] 새 판본은 업무판 승인 **뒤에** 활성화된다. 승인판이 이력에 없는
        #:   더 높은 판본을 가리키면 손상이 아니라 «활성화 대기» 다 — 어느 쪽이든 소비는 막는다.
        from core.data_preparation.process_kit_instances import activation_pending, pin_for
        try:
            pin = pin_for(conn, dict(instance), bundle["artifact_digest"])
            pending = not pin and activation_pending(conn, dict(instance), bundle)
        except ProcessError as exc:
            raise _unavailable("PROCESS_INSTANCE_UNAVAILABLE") from exc
        if pending:
            raise _conflict("PROCESS_UPGRADE_ACTIVATION_PENDING")
        if not pin or pin["context_root_id"] != boundary.context_root_id or pin["identity"] != expected:
            raise _unavailable("PROCESS_INSTANCE_UNAVAILABLE")
        return dict(instance)

    @staticmethod
    def _signed_against_current_contract(conn, row, payload):
        """★★ [2026-09-25 Codex 검토] **운영 사용은 현재 고정 계약으로 검증된 서명만.**

        계약 관문 이전의 서명(계약 지문 없음)이나 업그레이드 전 계약의 서명은 서명·이력을 그대로
        두되 운영에는 쓰지 않는다 — 재인증(새 판)으로만 다시 쓸 수 있다.
        ⚠️ 새 문맥을 만들 때 이 충돌은 차단 항목으로 접혀 초안·열람은 되고 운영 행동만 빠진다.
          이미 고정된 문맥을 다시 검증할 때는 그대로 막힌다(`_data` 의 409 처리)."""
        from core.data_preparation import certification_authority as ca
        from core.data_preparation.process_kit_instances import pinned_dataset_contract
        instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (row["instance_id"],)).fetchone()
        try:
            contract = pinned_dataset_contract(conn, dict(instance), row["dataset_contract_key"]) if instance else None
        except ProcessError as exc:
            raise _unavailable("PROCESS_CERTIFICATION_UNAVAILABLE") from exc
        if contract is None:
            raise _conflict("CONTRACT_NOT_PINNED")
        if payload.get("dataset_contract_digest") != ca.digest(contract):
            raise _conflict("CERTIFICATION_RECERTIFICATION_REQUIRED")

    @staticmethod
    def _owner_proof(conn, row, binding, owner, actor, context, *, held_history=False):
        """완료판을 RECONCILED로 가장하지 않고 불변 subject를 현재 B0 정책으로 검증한다."""
        from core.data_preparation import certification_authority as ca, certification_subject as cs
        head = cs._head(conn, row["snapshot_id"])
        if not head:
            raise _conflict("CERTIFICATION_SIGNATURES_REQUIRED")
        payload = head["payload"]
        ca.require_context(payload, context)
        policy = ca.resolve_policy(conn, tenant_id=row["tenant_id"], entity_mode=row["entity_mode"],
                                   context_root_id=payload["context_root_id"])
        use = row["certified_use_kind"]
        if use not in ca.USES:
            raise _unavailable("PROCESS_CERTIFICATION_UNAVAILABLE")
        expected = {k: row[k] for k in ("snapshot_id", "checksum", "binding_id", "instance_id", "dataset_contract_key",
                                         "tenant_id", "entity_mode", "scope_node_id", "data_kind", "period_from", "period_to")}
        expected.update(use_kind=use, owner_dept_id=owner["owner_dept_id"], ownership_binding_id=owner["binding_id"],
                        ownership_digest=owner["fingerprint"], signing_policy_id=policy["policy_id"],
                        signing_policy_revision=policy["revision"], signing_policy_digest=policy["digest"],
                        required=policy["document"]["required_reviews"][use], source_digest=ca.digest(binding),
                        reconciliation_digest=ca.digest({k: row[k] for k in ("profile_json", "control_total_json", "quarantine_json")}))
        if held_history:
            # 보류가 추가된 현재 config는 과거 source_digest와 달라질 수 있다.
            # 고정 이력 조회에만 사용하며 호출자는 반드시 _HeldReference로 반환해
            # 모든 데이터 소비를 막는다. 신규 인증/사용 검증에는 이 예외가 없다.
            expected.pop("source_digest")
        if any(payload.get(k) != value for k, value in expected.items()):
            raise _conflict("REVIEW_STALE")
        if not held_history:
            #: ⚠️ 이력 조회(`held_history`)는 이 검사를 건너뛴다 — 역사 조회와 운영 사용을 가른다.
            ProcessContextService._signed_against_current_contract(conn, row, payload)
        signatures = [dict(s) for s in conn.execute(
            "SELECT * FROM certification_signatures WHERE subject_id=? ORDER BY review_kind", (head["subject_id"],))]
        document = policy["document"]
        if (len(signatures) != len(payload["required"])
                or {s["review_kind"] for s in signatures} != set(payload["required"])
                or (not document["allow_same_actor"] and len({s["reviewer_id"] for s in signatures}) != len(signatures))):
            raise _conflict("CERTIFICATION_SIGNATURES_REQUIRED")
        for signature in signatures:
            if (signature["snapshot_id"] != row["snapshot_id"] or signature["owner_dept_id"] != owner["owner_dept_id"]
                    or len(signature["reconciliation_evidence"].strip()) < document["min_evidence_length"]):
                raise _unavailable("PROCESS_CERTIFICATION_UNAVAILABLE")
            try:
                ca.can_sign(payload, signature["reviewer_id"], signature["review_kind"], policy=policy, context=context)
            except ca.CertificationError as exc:
                if exc.status_code in (403, 404):
                    raise _conflict("SIGNER_INELIGIBLE") from exc
                raise
        return dict(certification_subject_id=head["subject_id"], certification_subject_digest=head["digest"],
                    signing_policy_id=policy["policy_id"], signing_policy_digest=policy["digest"], certified_use_kind=use)

    def _reference(self, conn, *, instance, bundle, requirement, contract_key, actor, context, fixed=None):
        from core.data_preparation import models as m, ownership_binding as ob, usage_policy as holds
        from core.data_preparation import certification_authority as ca
        from core.data_preparation.readiness import latest_certified
        expected = {k: instance[k] for k in ("instance_id", "tenant_id", "scope_node_id", "entity_mode")}
        expected["dataset_contract_key"] = contract_key
        rows = conn.execute("SELECT * FROM source_bindings WHERE instance_id=? AND dataset_contract_key=? AND state=?",
                            (instance["instance_id"], contract_key, m.ACTIVE)).fetchall()
        if not rows:
            raise _conflict("SOURCE_BINDING_REQUIRED")
        if len(rows) != 1:
            raise _unavailable("PROCESS_BINDING_UNAVAILABLE")
        binding = dict(rows[0])
        if any(binding[k] != value for k, value in expected.items()):
            raise missing()
        # 상세/인증 상태를 반환하기 전에 현재 승인 소유권과 호출자 PDP를 검사한다.
        ca.require_context(expected, context)
        owner = ob.resolve(conn, tenant_id=instance["tenant_id"], entity_mode=instance["entity_mode"],
                           scope_node_id=instance["scope_node_id"], dataset_contract_key=contract_key)
        if not owner:
            raise _conflict("OWNERSHIP_REQUIRED")
        ca.require_read({**expected, "owner_dept_id": owner["owner_dept_id"]}, actor, context)
        # 알 수 없는 코드까지 보류다. 손상은503이며 DRAFT 허용 결과로 접지 않는다.
        codes = holds.binding_holds(binding)
        if holds.INVALID in codes:
            raise _unavailable(holds.INVALID)
        if codes and fixed is None:
            raise _conflict("DATA_USAGE_HOLD")
        config = json.loads(binding["config_json"])
        if not codes and fingerprint({"provider": binding["provider"], "config": config}) != binding["fingerprint"]:
            raise _unavailable("PROCESS_BINDING_UNAVAILABLE")
        if fixed:
            if binding["binding_id"] != fixed["binding_id"]:
                raise _conflict("PROCESS_BINDING_CONFLICT")
            snapshot = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (fixed["snapshot_id"],)).fetchone()
            snapshot = dict(snapshot) if snapshot else None
        else:
            snapshots = [dict(s) for s in conn.execute(
                "SELECT * FROM dataset_snapshots WHERE instance_id=? AND dataset_contract_key=? AND binding_id=?",
                (instance["instance_id"], contract_key, binding["binding_id"]))]
            snapshot = latest_certified(snapshots)
        if snapshot is None or snapshot["state"] not in m.CERTIFIED_STATES or snapshot["status"] != "active":
            raise _conflict("CERTIFIED_SNAPSHOT_REQUIRED")
        if any(snapshot[k] != value for k, value in expected.items()) or snapshot["binding_id"] != binding["binding_id"]:
            raise missing()
        snapshot_codes = holds.snapshot_holds(conn, snapshot)
        if holds.INVALID in snapshot_codes:
            raise _unavailable(holds.INVALID)
        if tuple(snapshot_codes) != tuple(codes):
            raise _unavailable("PROCESS_BINDING_UNAVAILABLE")
        if not codes:
            holds.require_usable_conn(conn, snapshot)
        if (snapshot["data_kind"] != m.CERTIFICATION_DATA_KIND[snapshot["state"]]
                or not snapshot["certified_by"] or not snapshot["certified_at"]):
            raise _unavailable("PROCESS_CERTIFICATION_UNAVAILABLE")
        proof = dict(certification_subject_id=None, certification_subject_digest=None, signing_policy_id=None,
                     signing_policy_digest=None, certified_use_kind=None)
        if snapshot["state"] == m.OWNER_CERTIFIED:
            proof = self._owner_proof(conn, snapshot, binding, owner, actor, context, held_history=bool(codes))
        elif snapshot["state"] == m.SOURCE_CERTIFIED:
            # 기존 certify_source는 source_id/원천 승인 증거를 Snapshot에 고정하지
            # 않는다. 상태 이름만으로 현재 원천 승인을 검증했다고 발급하지 않는다.
            # 원천 고정 증거·현재 승인 어댑터가 연결될 때까지 명시적 미해결이다.
            raise _conflict("PROCESS_SOURCE_REVALIDATION_REQUIRED")
        elif snapshot["state"] == m.DEMO_CERTIFIED and instance["entity_mode"] != "VIRTUAL":
            # 시연 인증을 REAL 업무의 실적 인증으로 자동 승격하지 않는다.
            raise _conflict("PROCESS_DATA_KIND_CONFLICT")
        result = dict(process_id=requirement["process_id"], requirement_key=requirement["requirement_key"],
                      instance_id=instance["instance_id"], contract_key=contract_key, artifact_digest=bundle["artifact_digest"],
                      binding_id=binding["binding_id"], binding_fingerprint=binding["fingerprint"],
                      snapshot_id=snapshot["snapshot_id"], snapshot_fingerprint=snapshot_fingerprint(snapshot),
                      checksum=snapshot["checksum"], ownership_binding_id=owner["binding_id"], ownership_fingerprint=owner["fingerprint"],
                      certification_state=snapshot["state"], **proof,
                      usage_policy_fingerprint=fingerprint({"schema_version": 1, "binding_id": binding["binding_id"],
                                                           "binding_fingerprint": binding["fingerprint"], "holds": list(codes)}))
        result = VerifiedBindingRef.model_validate(result).model_dump()
        if fixed is not None:
            if any(result[k] != fixed[k] for k in result if k != "usage_policy_fingerprint"):
                raise _conflict("PROCESS_BINDING_CONFLICT")
            historical_usage = fingerprint({"schema_version": 1, "binding_id": binding["binding_id"],
                                            "binding_fingerprint": binding["fingerprint"], "holds": []})
            if fixed["usage_policy_fingerprint"] != historical_usage:
                raise _conflict("PROCESS_BINDING_CONFLICT")
            if codes:
                # DATA_USAGE_HOLD 예외만 보고 검증하지 않은 참조를 반환하지 않는다.
                raise _HeldReference(copy.deepcopy(fixed))
        return result

    def _data(self, description, boundary, actor, context, fixed_refs=None):
        from core.data_preparation import certification_authority as ca
        refs, blockers = [], copy.deepcopy(description["blockers"])
        fixed = {_ref_key(ref): ref for ref in fixed_refs} if fixed_refs is not None else None
        seen = set()
        if description["bundles"]:
            with self._store().transaction() as conn:
                if not conn.in_transaction:
                    conn.execute("BEGIN")
                instances = {digest: self._instance(conn, boundary, source, bundle)
                             for digest, (source, bundle) in description["bundles"].items()}
                for requirement in description["requirements"]:
                    pid, key = requirement["process_id"], requirement["requirement_key"]
                    source, bundle, _ = description["by_node"][pid]
                    instance = instances[source["artifact_digest"]]
                    candidates = requirement["candidate_contract_keys"]
                    if requirement["unresolved_requirement"] or not candidates:
                        blockers.append(_block("PROCESS_REQUIREMENTS_UNRESOLVED", pid, key))
                    known = {d["dataset_contract_key"] for d in bundle["profile"]["datasets"]}
                    for contract in candidates:
                        if contract not in known:
                            raise _unavailable("PROCESS_REQUIREMENT_UNAVAILABLE")
                        ref_key = (pid, key, instance["instance_id"], contract)
                        seen.add(ref_key)
                        if fixed is not None and ref_key not in fixed:
                            # 보존된 초안 재개가 새 결속/최신 인증판을 묵시적으로 선택하지 않는다.
                            blockers.append(_block("PROCESS_BINDING_REFRESH_REQUIRED", pid, key))
                            continue
                        try:
                            refs.append(self._reference(conn, instance=instance, bundle=bundle, requirement=requirement,
                                                        contract_key=contract, actor=actor, context=context,
                                                        fixed=fixed.get(ref_key) if fixed is not None else None))
                        except _HeldReference as exc:
                            refs.append(exc.ref)
                            blockers.append(_block("DATA_USAGE_HOLD", pid, key))
                        except (ProcessError, ca.CertificationError) as exc:
                            if exc.status_code != 409:
                                raise
                            # 과거 검증 참조가 실제로 달라진 경우에는 초안에서도 조용히 버리지 않는다.
                            if fixed is not None and ref_key in fixed:
                                raise _conflict(exc.reason_code) from exc
                            blockers.append(_block(exc.reason_code, pid, key))
        if fixed is not None and set(fixed) - seen:
            raise _conflict("PROCESS_BINDING_CONFLICT")
        if not refs:
            blockers.append(_block("CERTIFIED_BINDINGS_REQUIRED"))
        unique = {fingerprint(blocker): blocker for blocker in blockers}
        return sorted(refs, key=_ref_key), sorted(unique.values(), key=lambda b: (
            b["process_id"] or "", b["requirement_key"] or "", b["reason_code"]))

    def _build(self, boundary, actor, context, profile_id, process_ids, fixed_refs=None):
        historical, current, head = self._profiles(boundary, actor, context, profile_id)
        fixed = self._describe(historical, process_ids, boundary)
        latest = self._describe(current, process_ids, boundary)
        if fixed["semantic"] != latest["semantic"]:
            raise _conflict()
        refs, blockers = self._data(fixed, boundary, actor, context, fixed_refs)
        # DP/조직 조회 사이 ECM 변경이 있었으면 마지막 권한·head를 다시 확인한다.
        _, rechecked, _ = self._profiles(boundary, actor, context, profile_id)
        if fingerprint(rechecked) != fingerprint(current):
            if self._describe(rechecked, process_ids, boundary)["semantic"] != fixed["semantic"]:
                raise _conflict()
        digest = fingerprint(historical)
        authority = self._permissions(boundary, actor, context)
        denied_authority = [a for a in ACTIONS if a not in authority]
        if denied_authority:
            blockers.append(dict(reason_code="PROCESS_ACTION_FORBIDDEN", process_id=None, requirement_key=None,
                                 blocking_actions=denied_authority,
                                 next_action="현재 업무 범위의 제안·앱 사용·프로젝트 작업 권한을 확인하십시오."))
        denied = {action for blocker in blockers for action in blocker["blocking_actions"]}
        result = dict(schema_version=1, configuration_id=head["configuration_id"], profile_id=profile_id,
                      process_ids=process_ids, process_semantic_fingerprint=fixed["semantic"], configuration_fingerprint=digest,
                      context_key={k: getattr(boundary, k) for k in CONTEXT_KEYS}, data_requirements=fixed["requirements"],
                      verified_binding_refs=refs, blockers=blockers, permitted_actions=[a for a in ACTIONS if a not in denied],
                      sources=[dict(kind="PROCESS_PROFILE", configuration_id=head["configuration_id"],
                                    profile_id=profile_id, fingerprint=digest), *fixed["sources"]])
        return ProcessContextDTO.model_validate(result).model_dump()

    def build(self, *, boundary, actor, context, profile_id, process_ids):
        boundary, ids = self._input(boundary, context, profile_id, process_ids)
        with self._errors():
            return self._build(boundary, actor, context, profile_id, ids)

    def revalidate(self, *, fixed_context, actor, current_context, for_action):
        """서버 저장 DTO만 받는다. DTO digest/권한 문자열은 bearer 권한이 아니다."""
        try:
            if for_action not in ACTIONS or not isinstance(for_action, str):
                raise ValueError("unsupported action")
            fixed = ProcessContextDTO.model_validate(fixed_context).model_dump()
        except (ValueError, TypeError) as exc:
            raise _invalid() from exc
        boundary, ids = self._input(fixed["context_key"], current_context, fixed["profile_id"], fixed["process_ids"])
        with self._errors():
            current = self._build(boundary, actor, current_context, fixed["profile_id"], ids, fixed["verified_binding_refs"])
            # 표시 변경은 과거 승인판을 보존한다. 요청이 준 현재 권한/차단 목록은 재사용하지 않는다.
            immutable = ("schema_version", "configuration_id", "profile_id", "process_ids", "process_semantic_fingerprint",
                         "configuration_fingerprint", "context_key", "data_requirements", "verified_binding_refs", "sources")
            if any(current[k] != fixed[k] for k in immutable):
                raise _conflict("PROCESS_CONTEXT_CONFLICT")
            if for_action not in current["permitted_actions"]:
                if any(b["reason_code"] == "PROCESS_ACTION_FORBIDDEN" and for_action in b["blocking_actions"]
                       for b in current["blockers"]):
                    raise ProcessError("PROCESS_ACTION_FORBIDDEN", "현재 업무 범위에서 이 작업을 수행할 권한이 없습니다.", 403)
                first = next(b for b in current["blockers"] if for_action in b["blocking_actions"])
                raise _conflict(first["reason_code"])
            return current
