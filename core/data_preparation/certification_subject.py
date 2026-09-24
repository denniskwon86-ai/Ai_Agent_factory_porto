"""불변 인증 대상과 서명 사건. DP 안의 원자성만 보장한다."""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from core.data_preparation import certification_authority as auth
from core.data_preparation import models as m, ownership_binding as ob, usage_policy

DDL = """
CREATE TABLE IF NOT EXISTS certification_subjects (
 subject_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, revision INTEGER NOT NULL,
 digest TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 created_by TEXT NOT NULL, previous_subject_id TEXT NOT NULL DEFAULT '',
 UNIQUE(snapshot_id, revision)
);
CREATE TABLE IF NOT EXISTS certification_subject_heads (
 snapshot_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS certification_signatures (
 event_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
 review_kind TEXT NOT NULL, reviewer_id TEXT NOT NULL, owner_dept_id TEXT NOT NULL,
 reconciliation_evidence TEXT NOT NULL, signed_at TEXT NOT NULL, eligibility_json TEXT NOT NULL,
 UNIQUE(subject_id, review_kind)
);
CREATE TABLE IF NOT EXISTS certification_requests (
 subject_id TEXT NOT NULL, review_kind TEXT NOT NULL, actor TEXT NOT NULL,
 client_request_id TEXT NOT NULL, request_digest TEXT NOT NULL, response_json TEXT NOT NULL,
 PRIMARY KEY(subject_id, review_kind, actor, client_request_id)
);
CREATE TRIGGER IF NOT EXISTS certification_subject_no_update BEFORE UPDATE ON certification_subjects
BEGIN SELECT RAISE(ABORT, 'immutable certification subject'); END;
CREATE TRIGGER IF NOT EXISTS certification_subject_no_delete BEFORE DELETE ON certification_subjects
BEGIN SELECT RAISE(ABORT, 'immutable certification subject'); END;
CREATE TRIGGER IF NOT EXISTS certification_signature_no_update BEFORE UPDATE ON certification_signatures
BEGIN SELECT RAISE(ABORT, 'immutable certification signature'); END;
CREATE TRIGGER IF NOT EXISTS certification_signature_no_delete BEFORE DELETE ON certification_signatures
BEGIN SELECT RAISE(ABORT, 'immutable certification signature'); END;
CREATE TRIGGER IF NOT EXISTS certification_request_no_update BEFORE UPDATE ON certification_requests
BEGIN SELECT RAISE(ABORT, 'immutable certification request'); END;
CREATE TRIGGER IF NOT EXISTS certification_request_no_delete BEFORE DELETE ON certification_requests
BEGIN SELECT RAISE(ABORT, 'immutable certification request'); END;
"""


def visible_snapshot(conn: Any, snapshot_id: str, actor: str, context: dict) -> dict:
    row = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
    if row is None:
        raise auth.CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    row = dict(row)
    instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (row["instance_id"],)).fetchone()
    # 사본 문맥이 현재 인스턴스와 다르면 옛 서명/타 회사 데이터를 보여주지 않는다.
    if not instance or any(row[k] != instance[k] for k in ("tenant_id", "entity_mode", "scope_node_id")):
        raise auth.CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    auth.require_context(row, context)
    owner = ob.resolve(conn, tenant_id=row["tenant_id"], entity_mode=row["entity_mode"],
                       dataset_contract_key=row["dataset_contract_key"], scope_node_id=row["scope_node_id"])
    if not owner:
        raise auth.CertificationError("OWNERSHIP_REQUIRED", "현재 승인된 데이터 소유권이 필요합니다.")
    auth.require_read({**row, "owner_dept_id": owner["owner_dept_id"]}, actor, context)
    head = _head(conn, snapshot_id)
    if head:
        auth.require_context(head["payload"], context)
    return row


def _state(row: dict) -> None:
    if row["state"] != m.RECONCILED:
        raise m.StateConflict("RECONCILED 를 마친 판에만 서명합니다. 서명이 대사를 대신하지 않습니다. 인증 완료 후 변경은 새 Snapshot이 필요합니다.")
    if row["data_kind"] != m.DATA_KIND_REAL:
        raise m.StateConflict("이 종점은 «REAL» 전용입니다.")


def _head(conn: Any, snapshot_id: str) -> dict | None:
    row = conn.execute("SELECT s.* FROM certification_subject_heads h JOIN certification_subjects s ON s.subject_id=h.subject_id WHERE h.snapshot_id=?",
                       (snapshot_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        payload = json.loads(result["payload_json"])
        if auth.digest(payload) != result["digest"] or payload["snapshot_id"] != snapshot_id or payload["revision"] != result["revision"]:
            raise ValueError("subject mismatch")
    except (ValueError, KeyError, TypeError) as exc:
        raise auth.CertificationError("SUBJECT_UNAVAILABLE", "인증 대상 무결성을 확인하지 못했습니다.", 503) from exc
    return {**result, "payload": payload}


_ISSUE_LABELS = {"MISSING_FIELD": "필수 필드 누락", "EMPTY_BUSINESS_KEY": "빈 업무키",
                 "DUPLICATE_BUSINESS_KEY": "업무키 중복"}


def _conforming_contract(conn: Any, row: dict) -> str:
    """★★ [2026-09-25] **설치가 고정한 데이터셋 계약**과 판의 봉인 원문을 대조한다. 계약 지문을 돌려준다.

    종전에는 인증이 판의 열을 어떤 계약과도 대조하지 않아, 정본 INV-01 에 없는 `amount` 한
    칸짜리 판이 인증·게시·운영 조회까지 통과했다. 이제 서명 대상을 만들기 전에 막는다.

    ⚠️ 고정 계약이 없으면 **막는다**(`CONTRACT_NOT_PINNED`). 계약을 싣지 않은 팩(1.1.0)의
      설치본과 등록부 키트가 여기에 해당한다 — 못 본 것을 통과로 세지 않는다(2026-09-25 결정).
    ⚠️ 대조는 호출자가 준 행이 아니라 **지문을 검증한 원문**으로 한다(`sealed_table`).
    ⚠️ 오류 문장에 자료 값을 싣지 않는다 — 필드 이름과 줄 번호만."""
    from core.data_preparation import contract_conformance as cc
    from core.data_preparation.process_kit_instances import pinned_dataset_contract
    from core.enterprise_context.process_schema import ProcessError
    instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (row["instance_id"],)).fetchone()
    try:
        contract = pinned_dataset_contract(conn, dict(instance), row["dataset_contract_key"]) if instance else None
        if contract is None:
            raise auth.CertificationError(
                "CONTRACT_NOT_PINNED",
                "설치가 고정한 데이터셋 계약이 없습니다 — 계약을 싣는 업무 팩으로 설치한 데이터만 실적 인증을 할 수 있습니다.")
        issues = cc.inspect(contract, *cc.sealed_table(row))
    except (ProcessError, cc.ContractShapeError) as exc:
        raise auth.CertificationError("CONTRACT_UNAVAILABLE", "고정된 데이터셋 계약을 확인하지 못했습니다.", 503) from exc
    if issues:
        parts = []
        for code, label in _ISSUE_LABELS.items():
            found = [i for i in issues if i["code"] == code]
            if not found:
                continue
            if code == "MISSING_FIELD":
                names = found[0]["fields"]
                parts.append(f"{label} {len(names)}개({', '.join(names[:10])}{' …' if len(names) > 10 else ''})")
            else:
                lines = [str(i["line"]) for i in found]
                parts.append(f"{label} {len(found)}행(줄 {', '.join(lines[:10])}{' …' if len(lines) > 10 else ''})")
        error = auth.CertificationError(
            "CONTRACT_CONFORMANCE_FAILED",
            f"판이 데이터셋 계약과 맞지 않습니다 — {'; '.join(parts)}. 원천을 고쳐 새 Snapshot 으로 다시 올리십시오.", 422)
        error.issues = issues
        raise error
    return auth.digest(contract)


def _candidate(conn: Any, row: dict, *, use_kind: str, period_from: str, period_to: str,
               new_revision: bool = False) -> tuple[dict, dict, dict | None]:
    from core import actual_certification_policy as acp
    _state(row)
    use = str(use_kind).strip().upper()
    if use not in auth.USES:
        raise acp.ActualCertificationPolicyError("실적 용도는 OPERATIONAL 또는 MANAGEMENT여야 합니다.")
    try:
        start, end = date.fromisoformat(period_from.strip()).isoformat(), date.fromisoformat(period_to.strip()).isoformat()
    except (ValueError, AttributeError) as exc:
        raise m.DataPreparationError("귀속 기간의 시작일·종료일을 명시한 유효한 날짜가 필요합니다.") from exc
    if start > end:
        raise m.DataPreparationError("귀속 기간의 종료일이 시작일보다 앞섭니다.")
    usage_policy.require_usable_conn(conn, row)
    owner = ob.resolve(conn, tenant_id=row["tenant_id"], entity_mode=row["entity_mode"],
                       dataset_contract_key=row["dataset_contract_key"], scope_node_id=row["scope_node_id"])
    if not owner:
        raise m.DataPreparationError("이 판의 소유 부서가 결속돼 있지 않습니다 — 먼저 데이터셋 소유권을 승인하십시오.")
    root = auth.context_root(row["tenant_id"], row["entity_mode"], row["scope_node_id"])
    policy = auth.resolve_policy(conn, tenant_id=row["tenant_id"], entity_mode=row["entity_mode"], context_root_id=root)
    head = _head(conn, row["snapshot_id"])
    if head and head["payload"]["context_root_id"] != root:
        raise auth.CertificationError("SNAPSHOT_NOT_FOUND", "데이터 Snapshot 을 찾을 수 없습니다.", 404)
    contract_digest = _conforming_contract(conn, row)
    revision = (head["revision"] + int(new_revision)) if head else 1
    payload = {k: row[k] for k in ("snapshot_id", "checksum", "binding_id", "instance_id", "dataset_contract_key",
                                   "tenant_id", "entity_mode", "scope_node_id", "data_kind")}
    payload.update(context_root_id=root, use_kind=use, period_from=start, period_to=end,
                   owner_dept_id=owner["owner_dept_id"], ownership_binding_id=owner["binding_id"],
                   ownership_digest=owner["fingerprint"], signing_policy_id=policy["policy_id"],
                   signing_policy_revision=policy["revision"], signing_policy_digest=policy["digest"],
                   required=policy["document"]["required_reviews"][use], revision=revision,
                   dataset_contract_digest=contract_digest)
    # checksum뿐 아니라 대사/프로파일과 원천 결속 변경도 서명 대상 변경이다.
    binding = conn.execute("SELECT * FROM source_bindings WHERE binding_id=?", (row["binding_id"],)).fetchone()
    payload["source_digest"] = auth.digest(dict(binding))
    payload["reconciliation_digest"] = auth.digest({k: row[k] for k in ("profile_json", "control_total_json", "quarantine_json")})
    fp = auth.digest(payload)
    if head and not new_revision and head["digest"] != fp:
        previous = head["payload"]
        if previous["use_kind"] != use:
            raise m.StateConflict("용도가 섞이면 인증 대상을 알 수 없습니다 — 명시적으로 새 검토 판을 만드십시오.")
        if previous["period_from"] != start or previous["period_to"] != end:
            raise m.StateConflict("이미 서명한 귀속 기간과 다릅니다 — 새 검토 판이 필요합니다.")
        raise auth.CertificationError("REVIEW_STALE", "소유권·정책·원천이 변경되었습니다. 기존 서명을 보존하고 새 검토 판을 시작하십시오.")
    return {"subject_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "certification:" + fp)), "digest": fp,
            "payload": payload}, policy, head


def _insert_subject(conn: Any, subject: dict, actor: str, previous: str = "") -> None:
    payload = subject["payload"]
    conn.execute("INSERT INTO certification_subjects VALUES(?,?,?,?,?,?,?,?)",
                 (subject["subject_id"], payload["snapshot_id"], payload["revision"], subject["digest"],
                  auth.canonical(payload), auth.now(), actor, previous))
    conn.execute("INSERT INTO certification_subject_heads VALUES(?,?) ON CONFLICT(snapshot_id) DO UPDATE SET subject_id=excluded.subject_id",
                 (payload["snapshot_id"], subject["subject_id"]))


def preview(store: Any, snapshot_id: str, *, actor: str, context: dict, use_kind: str,
            period_from: str, period_to: str, new_revision: bool = False) -> dict:
    with store.transaction() as conn:
        conn.execute("BEGIN")
        row = visible_snapshot(conn, snapshot_id, actor, context)
        subject, policy, head = _candidate(conn, row, use_kind=use_kind, period_from=period_from, period_to=period_to, new_revision=new_revision)
        return {**subject, "previous_subject_id": head["subject_id"] if head else "",
                "allow_same_actor": policy["document"]["allow_same_actor"]}


def restart(store: Any, snapshot_id: str, *, actor: str, context: dict, use_kind: str,
            period_from: str, period_to: str, expected_subject_digest: str, previous_subject_id: str) -> dict:
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = visible_snapshot(conn, snapshot_id, actor, context)
        subject, policy, head = _candidate(conn, row, use_kind=use_kind, period_from=period_from, period_to=period_to, new_revision=True)
        if not head or head["subject_id"] != previous_subject_id or subject["digest"] != expected_subject_digest:
            raise auth.CertificationError("SUBJECT_CONFLICT", "검토 대상이 바뀌었습니다. 다시 확인하십시오.")
        auth.can_sign(subject["payload"], actor, "DATA_OWNER", policy=policy, context=context)
        _insert_subject(conn, subject, actor, previous_subject_id)
        conn.execute("UPDATE dataset_snapshots SET certified_use_kind=?, period_from=?, period_to=?, updated_at=? WHERE snapshot_id=?",
                     (subject["payload"]["use_kind"], subject["payload"]["period_from"], subject["payload"]["period_to"], auth.now(), snapshot_id))
        return subject


def sign(store: Any, snapshot_id: str, *, review_kind: str, actor: str, context: dict,
         reconciliation_evidence: str, use_kind: str, period_from: str, period_to: str,
         subject_id: str, expected_subject_digest: str, client_request_id: str) -> dict:
    from core import actual_certification_policy as acp
    kind = review_kind.strip().upper()
    if kind not in auth.KINDS:
        raise m.DataPreparationError("지원하지 않는 서명 종류입니다.")
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = visible_snapshot(conn, snapshot_id, actor, context)
        if not client_request_id.strip() or len(client_request_id) > 128 or not subject_id or not expected_subject_digest:
            raise auth.CertificationError("SUBJECT_REQUIRED", "미리 확인한 서명 대상과 요청 식별자가 필요합니다.", 422)
        request = {"snapshot_id": snapshot_id, "subject_id": subject_id, "expected_subject_digest": expected_subject_digest,
                   "review_kind": kind, "actor": actor, "reconciliation_evidence": reconciliation_evidence,
                   "use_kind": use_kind, "period_from": period_from, "period_to": period_to}
        request_fp = auth.digest(request)
        previous = conn.execute("SELECT * FROM certification_requests WHERE subject_id=? AND review_kind=? AND actor=? AND client_request_id=?",
                                (subject_id, kind, actor, client_request_id)).fetchone()
        if previous:
            stored = conn.execute("SELECT payload_json,digest FROM certification_subjects WHERE subject_id=? AND snapshot_id=?", (subject_id, snapshot_id)).fetchone()
            if not stored:
                raise auth.CertificationError("SUBJECT_UNAVAILABLE", "원 요청의 인증 대상을 확인하지 못했습니다.", 503)
            saved_payload = json.loads(stored["payload_json"])
            if auth.digest(saved_payload) != stored["digest"]:
                raise auth.CertificationError("SUBJECT_UNAVAILABLE", "원 요청의 인증 대상 무결성이 다릅니다.", 503)
            auth.require_context(saved_payload, context)
            if previous["request_digest"] != request_fp:
                raise auth.CertificationError("IDEMPOTENCY_CONFLICT", "같은 요청 식별자로 다른 서명을 보낼 수 없습니다.")
            # 완료/새 revision 이후에도 원 결과를 반환한다. 현재 읽기 권한은 위에서 재검사했다.
            return json.loads(previous["response_json"])
        subject, policy, head = _candidate(conn, row, use_kind=use_kind, period_from=period_from, period_to=period_to)
        if subject["digest"] != expected_subject_digest or subject["subject_id"] != subject_id:
            raise auth.CertificationError("SUBJECT_CONFLICT", "미리 확인한 서명 대상과 현재 대상이 다릅니다.")
        payload, document = subject["payload"], policy["document"]
        if kind not in payload["required"]:
            raise m.DataPreparationError(f"이 용도에는 {kind} 서명이 필요하지 않습니다.")
        eligibility = auth.can_sign(payload, actor, kind, policy=policy, context=context)
        evidence = reconciliation_evidence.strip()
        if len(evidence) < document["min_evidence_length"]:
            raise acp.ActualCertificationPolicyError("대사 증거가 없거나 너무 짧습니다.")
        signatures = [dict(r) for r in conn.execute("SELECT * FROM certification_signatures WHERE subject_id=? ORDER BY review_kind", (subject_id,))]
        if any(r["review_kind"] == kind for r in signatures):
            raise m.StateConflict("이미 기록된 서명과 다릅니다 — 기존 서명을 덮어쓸 수 없습니다. 원 요청 식별자로 재시도하십시오.")
        if not document["allow_same_actor"] and any(r["reviewer_id"] == actor for r in signatures):
            raise auth.CertificationError("DISTINCT_SIGNER_REQUIRED", "다른 종류의 서명은 다른 적격자가 수행해야 합니다.", 403)
        # 과거 적격성이 현재 적격성을 대신하지 않는다. 위임자 회수도 여기서 다시 검사한다.
        rechecks = []
        for signature in signatures:
            rechecks.append(auth.can_sign(payload, signature["reviewer_id"], signature["review_kind"], policy=policy, context=context))
        if not head:
            # 구버전 서명은 감사 자료로만 남긴다. v2 서명 집합에 자동 합산하지 않는다.
            _insert_subject(conn, subject, actor)
        event_id = str(uuid.uuid4())
        conn.execute("INSERT INTO certification_signatures VALUES(?,?,?,?,?,?,?,?,?)",
                     (event_id, subject_id, snapshot_id, kind, actor, payload["owner_dept_id"], evidence, auth.now(),
                      auth.canonical({"current": eligibility, "previous_rechecks": rechecks})))
        conn.execute("UPDATE dataset_snapshots SET certified_use_kind=?, period_from=?, period_to=?, updated_at=? WHERE snapshot_id=?",
                     (payload["use_kind"], payload["period_from"], payload["period_to"], auth.now(), snapshot_id))
        signed = sorted([r["review_kind"] for r in signatures] + [kind])
        missing = [k for k in payload["required"] if k not in signed]
        certified = None
        if not missing:
            certified = store._advance_snapshot_conn(conn, snapshot_id, m.OWNER_CERTIFIED, certified_by=actor)
        out = {"snapshot_id": snapshot_id, "subject_id": subject_id, "subject_digest": subject["digest"], "event_id": event_id,
               "review_kind": kind, "reviewer_id": actor, "owner_dept_id": payload["owner_dept_id"],
               "use_kind": payload["use_kind"], "required": payload["required"], "signed": signed, "missing": missing,
               "certified": certified is not None}
        if missing:
            out["next_action"] = "남은 서명: " + ", ".join(f"{k}({acp.reviewer_title(k)})" for k in missing)
        else:
            out.update(state=certified["state"], certified_at=certified["certified_at"],
                       note="용도 선언이 사용을 제약합니다. OPERATIONAL 로 인증한 실적은 경영 보고에 쓸 수 없습니다.")
        conn.execute("INSERT INTO certification_requests VALUES(?,?,?,?,?,?)",
                     (subject_id, kind, actor, client_request_id, request_fp, auth.canonical(out)))
        return out


def assert_complete(conn: Any, row: dict) -> None:
    """일반 상태 전환 API로 OWNER_CERTIFIED를 우회할 수 없도록 저장소도 검사한다."""
    head = _head(conn, row["snapshot_id"])
    if not head:
        raise auth.CertificationError("CERTIFICATION_SIGNATURES_REQUIRED", "확인한 불변 대상과 종류별 서명이 필요합니다.")
    payload = head["payload"]
    current, _policy, _ = _candidate(conn, row, use_kind=payload["use_kind"], period_from=payload["period_from"], period_to=payload["period_to"])
    if current["digest"] != head["digest"]:
        raise auth.CertificationError("REVIEW_STALE", "인증 대상이 변경되었습니다.")
    signatures = conn.execute("SELECT review_kind FROM certification_signatures WHERE subject_id=?", (head["subject_id"],)).fetchall()
    if set(r[0] for r in signatures) != set(payload["required"]):
        raise auth.CertificationError("CERTIFICATION_SIGNATURES_REQUIRED", "필요한 종류의 서명이 모두 모이지 않았습니다.")


def read(store: Any, snapshot_id: str, *, actor: str, context: dict) -> dict:
    with store.transaction() as conn:
        conn.execute("BEGIN")
        row = visible_snapshot(conn, snapshot_id, actor, context)
        head = _head(conn, snapshot_id)
        if head:
            auth.require_context(head["payload"], context)
        signatures = [dict(r) for r in conn.execute("SELECT * FROM certification_signatures WHERE subject_id=? ORDER BY review_kind", (head["subject_id"] if head else "",))]
        required = head["payload"]["required"] if head else []
        review_status = "CERTIFIED" if row["state"] == m.OWNER_CERTIFIED else ("PENDING" if head else "NOT_STARTED")
        review_issue = None
        if head and row["state"] == m.RECONCILED:
            try:
                payload = head["payload"]
                _candidate(conn, row, use_kind=payload["use_kind"], period_from=payload["period_from"], period_to=payload["period_to"])
            except usage_policy.UsageHoldError as exc:
                # 사용 보류는 신규 서명을 막지만, 권한 있는 과거 이력 조회까지 막지 않는다.
                review_status = "ON_HOLD"
                review_issue = {"reason_code": exc.reason_code, "message": str(exc)}
            except auth.CertificationError as exc:
                if exc.reason_code == "REVIEW_STALE":
                    review_status = "REVIEW_STALE"
                    review_issue = {"reason_code": exc.reason_code, "message": str(exc)}
                else:
                    raise
        return {"snapshot_id": snapshot_id, "state": row["state"], "data_kind": row["data_kind"],
                "use_kind": row["certified_use_kind"], "period_from": row["period_from"], "period_to": row["period_to"],
                "subject": head, "required": required, "signatures": signatures,
                "review_status": review_status, "review_issue": review_issue,
                "requires_new_revision": review_status == "REVIEW_STALE",
                "missing": [] if review_status == "REVIEW_STALE" else [k for k in required if k not in {s["review_kind"] for s in signatures}],
                "signatures_count_toward_completion": review_status not in ("REVIEW_STALE", "ON_HOLD"),
                "usage_holds": list(usage_policy.snapshot_holds(conn, row)),
                "legacy_signatures": [dict(r) for r in conn.execute("SELECT * FROM snapshot_certifications WHERE snapshot_id=?", (snapshot_id,))],
                "previous_subjects": [dict(r) for r in conn.execute("SELECT subject_id,revision,digest,created_at FROM certification_subjects WHERE snapshot_id=? AND subject_id<>? ORDER BY revision", (snapshot_id, head["subject_id"] if head else ""))]}
