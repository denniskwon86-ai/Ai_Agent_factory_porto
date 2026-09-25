# -*- coding: utf-8 -*-
"""★★★ 키트 앱 런타임 계약의 **초안·승인·조회.** (2026-08-23)

## 왜 이 모듈이 생겼나

`kit_app_builder` 는 **승인된 계약만** 물질화한다. 그런데 그 계약을 승인할 곳이
제품 어디에도 없었다 — 승인 관문은 서 있는데 **누를 것이 없었다.**

    「통제는 있는데 부르는 경로가 없다」

소유권 승인(4.1c-D)에서 이미 같은 지적을 받았다. 그때와 같은 모양으로 짓는다.

## 두 사람이 필요하다

    ① `draft()`   만드는 사람 — 계약 초안을 저장한다
    ② `approve()` **다른 사람** — 원장에 사건을 남기고 상태를 올린다

⚠️⚠️ 요청자가 승인자 자리에 앉으면 승인은 절차의 이름만 남는다. 응용에서 막고
  **DB 트리거로도** 막는다(`trg_kac_no_self_approval_*`) — 층마다 다른 가정에 선다.

## 원장 없는 승인은 만들지 않는다

승인 사건 기록이 실패하면 상태를 올리지 않는다. 「승인 이력 없는 승인」이 남으면
나중에 누가 왜 열었는지 답할 수 없다.

LLM 0콜.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from core import app_runtime_contract as arc
from core import kit_app_builder as kb

#: 원장에 남기는 사건·주체 이름.
#:
#: ★★★ **이미 있는 어휘를 쓴다.** 처음에 `KIT_APP_CONTRACT_APPROVED` /
#:   `kit_app_contract` 를 새로 만들려다 원장의 닫힌 목록에 막혔고, 확인해 보니
#:   `APP_CONTRACT_APPROVED` / `app_contract` 가 **같은 질문으로 이미 있었다**
#:   (I-4 4단계 — 「이 계약이 언제 어떤 지문으로 승인됐나」).
#: ⚠️ 같은 질문에 두 번째 이름을 만들면 승인 건수를 세는 순간 둘로 조각난다.
#: ★ 닫힌 목록이 그 실수를 잡아 줬다 — 목록이 열려 있었으면 조용히 갈렸을 것이다.
EVENT_APPROVED = "APP_CONTRACT_APPROVED"
EVENT_REJECTED = "APP_CONTRACT_REJECTED"
SUBJECT_TYPE = "app_contract"
STATUS_REJECTED = "REJECTED"  # 검토 행만 변경하며 runtime 문서 상태·원문은 보존한다.

STATUS_DRAFT, STATUS_APPROVED, STATUS_SUPERSEDED = (
    arc.STATUS_DRAFT, arc.STATUS_APPROVED, arc.STATUS_SUPERSEDED)


class ContractFlowError(Exception):
    """계약 흐름 위반 — 4xx 로 전달한다."""


class LedgerUnavailable(Exception):
    """원장에 남기지 못했다 — 503 이다. ⚠️ 「입력을 고쳐 다시 하라」가 아니다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_id(instance_id: str, app_id: str, revision: int) -> str:
    """결정론적 행 id. ★ 같은 개정을 두 번 저장해도 같은 자리다."""
    return f"kac_{instance_id}_{app_id}_r{int(revision)}"


def _to_dict(row: Any) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["contract"] = json.loads(d.pop("contract_json", "") or "{}")
    except Exception:
        #: ⚠️ 판독 실패를 빈 계약으로 바꾸지 않는다 — 빈 계약은 「데이터셋 0개 앱」으로
        #:   읽히고, 그것은 정상 상태다. 못 읽었다는 사실을 남긴다.
        d["contract"] = None
        d["unreadable"] = True
    return d


# ── 조회 ────────────────────────────────────────────────────────────────
def list_for_instance(store: Any, instance_id: str) -> List[Dict[str, Any]]:
    with store.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM kit_app_contracts WHERE instance_id=? "
            "ORDER BY app_id, revision DESC", (str(instance_id),)).fetchall()
    return [_to_dict(r) for r in rows]


def latest(store: Any, instance_id: str, app_id: str) -> Optional[Dict[str, Any]]:
    """이 앱의 **가장 최근 개정**. 승인 여부와 무관하다."""
    with store.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? "
            "ORDER BY revision DESC LIMIT 1", (str(instance_id), str(app_id))).fetchone()
    return _to_dict(row) if row else None


def approved(store: Any, instance_id: str, app_id: str) -> Optional[Dict[str, Any]]:
    """승인된 계약. 없으면 `None` — **없는 것을 «괜찮음» 으로 읽지 않는다.**"""
    with store.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? "
            "AND status=?", (str(instance_id), str(app_id), STATUS_APPROVED)).fetchone()
    return _to_dict(row) if row else None


# ── ① 초안 ──────────────────────────────────────────────────────────────
def draft(store: Any, *, blueprint: Mapping[str, Any], instance_id: str,
          actor_id: str, tenant_id: str, scope_node_id: str, entity_mode: str,
          app_class: str, labels: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """계약 초안을 만들어 저장한다. **승인하지 않는다.**

    ★ 필드는 인증판에서 읽는다(`kb.fields_from_certified`) — 여기서 지어내면 계약과
      실제 자료가 갈라진다.
    ★ 같은 내용을 다시 부르면 **같은 개정을 덮는다**(멱등). 내용이 달라지면 개정을
      올린다 — 그래야 「무엇이 바뀌었나」가 이력에 남는다.
    ⚠️ **이미 승인된 계약은 덮지 않는다.** 덮으면 승인이 조용히 다른 내용을 가리킨다."""
    app_id = str(blueprint.get("app_id") or "").strip()
    if not str(actor_id or "").strip():
        raise ContractFlowError("만든 사람이 필요합니다.")

    kb.reject_process_legacy(store, instance_id)

    prev = latest(store, instance_id, app_id)
    revision = int(prev["revision"]) if prev else 1
    contract = kb.contract_from_blueprint(
        blueprint, project_id=str(instance_id), app_class=app_class,
        revision=revision, labels=labels,
        schema_for=lambda k: kb.fields_from_certified(store, instance_id, k))
    fp = str(contract.get("semantic_fingerprint") or "")

    if prev:
        if prev.get("status") == STATUS_REJECTED:
            _proof_rejection(prev)
        if str(prev.get("semantic_fingerprint") or "") == fp and prev.get("status") != STATUS_REJECTED:
            #: ★ 같은 내용이다 — 개정을 올리지 않는다. 재시도만으로 이력이 부풀지 않는다.
            if str(prev.get("status")) == STATUS_APPROVED:
                return prev
        else:
            #: ⚠️ 내용이 달라졌다. 승인된 것을 덮지 않고 **다음 개정**을 만든다.
            revision = int(prev["revision"]) + 1
            contract["revision"] = revision
            contract["semantic_fingerprint"] = arc.semantic_fingerprint(contract)
            fp = contract["semantic_fingerprint"]

    now = _now()
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? ORDER BY revision DESC LIMIT 1",
                               (str(instance_id), app_id)).fetchone()
        if (_to_dict(current) if current else None) != prev:
            from core.enterprise_context.process_schema import ProcessError
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "초안 작성 중 다른 검토가 반영되었습니다.", 409)
        conn.execute(
            "INSERT INTO kit_app_contracts "
            "(contract_row_id, instance_id, app_id, revision, status, "
            " semantic_fingerprint, contract_json, drafted_by, drafted_at, "
            " tenant_id, scope_node_id, entity_mode, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            #: ★ 같은 개정을 다시 저장하면 내용을 갱신한다. ⚠️ 단 **승인된 행은 건드리지
            #:   않는다** — WHERE 가 그것을 지킨다(응용 검사에 기대지 않는다).
            "ON CONFLICT(instance_id, app_id, revision) DO UPDATE SET "
            "  semantic_fingerprint=excluded.semantic_fingerprint, "
            "  contract_json=excluded.contract_json, "
            "  drafted_by=excluded.drafted_by, drafted_at=excluded.drafted_at, "
            "  updated_at=excluded.updated_at "
            "WHERE kit_app_contracts.status NOT IN ('APPROVED','REJECTED')",
            (_row_id(instance_id, app_id, revision), str(instance_id), app_id,
             revision, STATUS_DRAFT, fp,
             json.dumps(contract, ensure_ascii=False, sort_keys=True),
             str(actor_id), now, str(tenant_id), str(scope_node_id), str(entity_mode),
             now))
    out = latest(store, instance_id, app_id)
    if not out:                                            # pragma: no cover - 방어
        raise ContractFlowError(f"{app_id}: 계약 초안을 저장하지 못했습니다.")
    return out


# ── ② 승인 ──────────────────────────────────────────────────────────────
def approve(store: Any, *, instance_id: str, app_id: str, revision: int,
            actor_id: str, rationale: str) -> Dict[str, Any]:
    """**다른 사람이** 초안을 승인한다.

    ⚠️⚠️ 만든 사람은 승인할 수 없다. 응용에서 막고 트리거로도 막는다.
    ⚠️ 근거가 필요하다 — 「왜 이 앱을 열었나」에 답할 수 없는 승인은 나중에 아무도
      뒤집지 못한다(소유권 승인의 `evidence_ref` 와 같은 규칙).
    ★ 원장 기록이 실패하면 **상태를 올리지 않는다.**"""
    if not str(actor_id or "").strip():
        raise ContractFlowError("승인 행위자가 필요합니다.")
    if not str(rationale or "").strip():
        raise ContractFlowError(
            "승인 근거가 필요합니다 — 「왜 이 앱을 열었나」에 답할 수 없는 승인은 "
            "나중에 아무도 뒤집을 수 없습니다.")

    #: ★★★ 승인 권한은 **소유권 승인과 같은 질문**이다("데이터 표준을 승인할 수 있는가").
    #:   규칙을 복제하지 않는다 — 복제하면 두 판정이 반드시 갈라지고, 갈린 날 어느 쪽이
    #:   옳은지 아무도 모른다.
    from core.data_preparation import ownership_binding as _ob
    _ob.require_approval_authority(str(actor_id))

    with store.transaction() as conn:
        r = conn.execute(
            "SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? "
            "AND revision=?", (str(instance_id), str(app_id), int(revision))).fetchone()
    row = _to_dict(r) if r else None
    if not row:
        raise ContractFlowError(
            f"{app_id}: 개정 {revision} 의 계약 초안이 없습니다 — 먼저 만들어야 합니다.")
    if isinstance(row.get("contract"), dict) and row["contract"].get("schema_version") == "2.0":
        from core.enterprise_context.process_schema import ProcessError
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "2.0 계약은 현재 문맥과 고정 지문을 명시해 승인하십시오.", 409)
    if str(row.get("status")) == STATUS_APPROVED:
        #: ★ 멱등 — 이미 승인돼 있으면 원장에 아무것도 더 쓰지 않는다.
        return row
    if row.get("status") == STATUS_REJECTED:
        _proof_rejection(row)
        from core.enterprise_context.process_schema import ProcessError
        raise ProcessError("PROCESS_CONTRACT_REJECTED", "반려된 계약은 새 개정으로 다시 제안하십시오.", 409)
    if row.get("unreadable") or not isinstance(row.get("contract"), dict):
        raise ContractFlowError(
            f"{app_id}: 계약을 읽을 수 없어 승인하지 않습니다 — 못 읽은 것을 "
            f"«괜찮음» 으로 승인하면 무엇을 열었는지 아무도 모릅니다.")
    if str(row.get("drafted_by") or "").strip().lower() == str(actor_id).strip().lower():
        raise ContractFlowError(
            f"{app_id}: 계약을 만든 사람은 승인할 수 없습니다 — 요청자가 승인자 자리에 "
            f"앉으면 승인은 절차의 이름만 남습니다.")

    try:
        from core.decision_ledger import decision_ledger
        ev = decision_ledger.append(
            event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE,
            #: ★ 대상은 **의미 지문**이다 — 사건 자체에 «무엇을 승인했는가» 가 박힌다.
            subject_id=str(row["semantic_fingerprint"]),
            actor_type="user", actor_id=str(actor_id), decision="APPROVED",
            rationale=rationale,
            evidence_refs=[f"kit_instance:{instance_id}", f"app:{app_id}",
                           f"revision:{revision}"],
            tenant_id=str(row.get("tenant_id") or ""),
            enterprise_scope_id=str(row.get("scope_node_id") or ""),
            entity_mode=str(row.get("entity_mode") or ""))
    except Exception as e:
        #: ⚠️ 삼키지 않는다 — 「승인 이력 없는 승인」이 생긴다.
        raise LedgerUnavailable(f"승인 사건을 원장에 남기지 못했습니다: {e}")

    event_id = str(ev.get("event_id", ""))
    now = _now()
    contract = dict(row["contract"])
    contract["status"] = STATUS_APPROVED
    contract["approval"] = {"status": "APPROVED", "approved_by": str(actor_id),
                            "approved_at": now, "decision_ledger_id": event_id}
    #: ★★★ 승인 봉투가 바뀌면 지문도 다시 센다. ⚠️ 지문이 내용을 따라가지 않으면
    #:   재승인 판정이 거짓이 된다(`arc.validate` 규칙 7).
    contract["semantic_fingerprint"] = arc.semantic_fingerprint(contract)
    errs = arc.validate(contract)
    if errs:
        raise ContractFlowError(
            f"{app_id}: 승인한 계약이 정본 스키마를 통과하지 못합니다 — "
            + " / ".join(errs[:3]))

    with store.transaction() as conn:
        #: ★ 앞선 승인이 있으면 **밀어낸다.** 한 앱에 승인은 하나뿐이다(유일 색인).
        conn.execute("BEGIN IMMEDIATE")
        current = _v2_row(conn, str(instance_id), str(app_id), int(revision))
        if current != row:
            from core.enterprise_context.process_schema import ProcessError
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "승인 검토 중 초안·반려 상태가 변경되었습니다.", 409)
        conn.execute(
            "UPDATE kit_app_contracts SET status=?, updated_at=? "
            "WHERE instance_id=? AND app_id=? AND status=?",
            (STATUS_SUPERSEDED, now, str(instance_id), str(app_id), STATUS_APPROVED))
        conn.execute(
            "UPDATE kit_app_contracts SET status=?, approved_by=?, approved_at=?, "
            "  ledger_event_id=?, contract_json=?, semantic_fingerprint=?, updated_at=? "
            "WHERE contract_row_id=?",
            (STATUS_APPROVED, str(actor_id), now, event_id,
             json.dumps(contract, ensure_ascii=False, sort_keys=True),
             contract["semantic_fingerprint"], now,
             str(row["contract_row_id"])))
    out = approved(store, instance_id, app_id)
    if not out:                                            # pragma: no cover - 방어
        raise ContractFlowError(f"{app_id}: 승인을 저장하지 못했습니다.")
    return out



def _rejection_refs(row):
    from core.enterprise_context.process_schema import fingerprint
    return [f"kit_instance:{row['instance_id']}", f"app:{row['app_id']}",
            f"revision:{row['revision']}", f"contract_row:{row['contract_row_id']}",
            f"runtime_document_version:{row['contract']['schema_version']}",
            f"contract_digest:{fingerprint(row['contract'])}"]


def _rejection_event_matches(event, row):
    return (isinstance(event, dict) and event.get("event_type") == EVENT_REJECTED
            and event.get("subject_type") == SUBJECT_TYPE
            and event.get("subject_id") == row["semantic_fingerprint"]
            and event.get("actor_type") == "user" and bool(event.get("actor_id"))
            and event["actor_id"].strip().lower() != row["drafted_by"].strip().lower()
            and event.get("decision") == STATUS_REJECTED
            and isinstance(event.get("rationale"), str) and bool(event["rationale"].strip())
            and event.get("tenant_id") == row["tenant_id"]
            and event.get("entity_mode") == row["entity_mode"]
            and event.get("enterprise_scope_id") == row["scope_node_id"]
            and event.get("evidence_refs") == _rejection_refs(row))


def _proof_rejection(row, *, event_reader=None):
    """반려 상태는 원장에 결속된 검토 행이다. 원래 DRAFT 문서·지문은 불변이다."""
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_schema import ProcessError
    try:
        contract = row["contract"]
        if (row["status"] != STATUS_REJECTED or not isinstance(contract, dict)
                or contract.get("status") != STATUS_DRAFT or arc.validate(contract)
                or contract["semantic_fingerprint"] != row["semantic_fingerprint"]
                or contract["revision"] != row["revision"]
                or contract["project_id"] != row["instance_id"] or contract["task_id"] != row["app_id"]
                or contract["approval"]["status"] != "PENDING"
                or row["approved_by"] or row["approved_at"] or not row["ledger_event_id"]):
            raise ValueError("rejection row mismatch")
        event = (event_reader or decision_ledger.get_event_strict)(row["ledger_event_id"])
        if not _rejection_event_matches(event, row):
            raise ValueError("rejection evidence mismatch")
        return event
    except Exception as exc:
        raise ProcessError("PROCESS_CONTRACT_REJECTION_UNAVAILABLE", "반려 원장과 고정 계약의 일치를 확인하지 못했습니다.", 503) from exc


def _legacy_rejection_read(store, instance, actor_id, context, repo):
    """새 legacy 반려에도 현재 ECM READ를 요구한다. 표시 트리로 root를 추정하지 않는다."""
    from core.enterprise_context.process_configuration import ProcessConfigurationService, missing
    from core.enterprise_context.process_schema import ProcessBoundary
    if (not isinstance(context, Mapping) or not context.get("scope_node_id")
            or any(context.get(k) != instance[k] for k in ("tenant_id", "entity_mode"))):
        raise missing()
    service = ProcessConfigurationService(repo=repo, store=store)
    provisional = ProcessBoundary(tenant_id=instance["tenant_id"], entity_mode=instance["entity_mode"],
        context_root_id=instance["scope_node_id"], scope_node_id=instance["scope_node_id"])
    with service.transaction() as conn:
        chain = service._chain(conn, instance["scope_node_id"], provisional)
        root = chain[-1]
        if context.get("context_root_id", root) != root:
            raise missing()
        boundary = provisional.model_copy(update={"context_root_id": root})
        service._authorize(conn, boundary, actor_id, context, "read")


def _rejection_reviewer(actor_id, row):
    from core.data_preparation import ownership_binding as ob
    from core.enterprise_context.process_schema import ProcessError
    try:
        ob.require_approval_authority(actor_id)
    except ob.OwnershipError as exc:
        raise ProcessError("PROCESS_ACTION_FORBIDDEN", "앱 계약 반려 권한이 없습니다.", 403) from exc
    if row["drafted_by"].strip().lower() == actor_id.strip().lower():
        raise ProcessError("PROCESS_DISTINCT_REVIEWER_REQUIRED", "작성자와 다른 적격 검토자가 필요합니다.", 403)


def _rejection_result(row, event):
    return {**row, "rejection": {"rejected_by": event["actor_id"], "rejected_at": event["created_at"],
            "rationale": event["rationale"], "decision_ledger_id": event["event_id"]}}


def _replay_rejection(row, actor_id, rationale):
    from core.enterprise_context.process_schema import ProcessError
    event = _proof_rejection(row)
    if event["actor_id"] != actor_id or event["rationale"] != rationale:
        raise ProcessError("PROCESS_CONTRACT_CONFLICT", "완료한 반려 요청과 다른 본문입니다.", 409)
    return _rejection_result(row, event)


def _reject_contract(store, *, instance_id, app_id, revision, expected_fingerprint,
                     actor_id, context, rationale, repo, version):
    from core import project_data_context as pdc
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_configuration import missing
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if (type(revision) is not int or revision < 1 or not isinstance(expected_fingerprint, str)
            or len(expected_fingerprint) != 64 or any(c not in "0123456789abcdef" for c in expected_fingerprint)
            or not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000):
        raise ProcessError("PROCESS_CONTRACT_INVALID", "현재 개정·정확한 지문·반려 사유가 필요합니다.", 422)
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ProcessError("PROCESS_AUTHENTICATION_REQUIRED", "로그인이 필요합니다.", 401)
    with ProcessContextService._errors():
        if version == "2.0":
            instance = _visible_v2_instance(store, instance_id, actor_id, context, repo)
        else:
            instance = store.get_instance(instance_id)
            if not instance:
                raise missing()
            _legacy_rejection_read(store, instance, actor_id, context, repo)
            kb.reject_process_legacy(store, instance_id)
        if instance["status"] != "active":
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "활성 적용본의 계약만 검토할 수 있습니다.", 409)
        with store.transaction() as conn:
            row = _v2_row(conn, instance_id, app_id, revision)
        if not row:
            raise ProcessError("PROCESS_CONTRACT_NOT_FOUND", "검토할 앱 계약을 찾을 수 없습니다.", 404)
        if row["status"] not in (STATUS_DRAFT, STATUS_REJECTED):
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "현재 초안만 반려할 수 있습니다. 승인판은 보존됩니다.", 409)
        contract = row["contract"]
        if (not isinstance(contract, dict) or contract.get("schema_version") != version or arc.validate(contract)
                or contract["status"] != STATUS_DRAFT or contract["approval"]["status"] != "PENDING"
                or contract["revision"] != revision or contract["project_id"] != instance_id
                or contract["task_id"] != app_id or contract["semantic_fingerprint"] != row["semantic_fingerprint"]
                or any(row[k] != instance[k] for k in ("tenant_id", "scope_node_id", "entity_mode"))
                or row["approved_by"] or row["approved_at"]
                or (row["status"] == STATUS_DRAFT and row["ledger_event_id"])):
            raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "검토할 고정 계약의 원문·문맥이 일치하지 않습니다.", 503)
        if row["semantic_fingerprint"] != expected_fingerprint:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "검토한 계약 지문이 다릅니다.", 409)
        if version == "2.0":
            # 반려는 데이터 소비가 아니다. READ 가능한 보류 이력을 검토할 수 있지만
            # 현재 권한·업무 의미·정확한 고정 원본은 그대로 재검증한다.
            pdc.process_instance(store, instance_id, actor_id=actor_id, context=context,
                process_context=contract["process_context"], for_action="READ", repo=repo)
        _rejection_reviewer(actor_id, row)
        if row["status"] == STATUS_REJECTED:
            return _replay_rejection(row, actor_id, rationale)
        with store.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = _v2_row(conn, instance_id, app_id, revision)
            newest = conn.execute("SELECT MAX(revision) FROM kit_app_contracts WHERE instance_id=? AND app_id=?",
                                  (instance_id, app_id)).fetchone()[0]
            concurrent_replay = (current and current["status"] == STATUS_REJECTED
                                 and current["semantic_fingerprint"] == expected_fingerprint
                                 and current["contract"] == contract)
            if not concurrent_replay and (current != row or newest != revision):
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "다른 개정·검토가 먼저 반영되었습니다.", 409)
            current_instance = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (instance_id,)).fetchone()
            if not current_instance or dict(current_instance) != instance or instance["status"] != "active":
                raise ProcessError("PROCESS_INSTANCE_CONFLICT", "검토 중 적용본이 변경되었습니다.", 409)
            if version == "2.0":
                _write_authority_v2(store, contract["process_context"], actor_id, context, "READ", repo)
            else:
                _legacy_rejection_read(store, instance, actor_id, context, repo)
            _rejection_reviewer(actor_id, row)
            if concurrent_replay:
                return _replay_rejection(current, actor_id, rationale)
            # 원장은 별도 DB다. DP rollback 뒤에는 같은 근거 사건을 재사용하며,
            # 미결속 원장 사건을 앱 계약 반려 상태로 해석하지 않는다.
            try:
                with decision_ledger.transaction() as ledger:
                    found = ledger.find_events(event_type=EVENT_REJECTED, subject_type=SUBJECT_TYPE,
                                               subject_id=expected_fingerprint, limit=1001)
                    if len(found) >= 1001:
                        raise ValueError("rejection history incomplete")
                    own = [e for e in found if f"contract_row:{row['contract_row_id']}" in e.get("evidence_refs", [])]
                    if len(own) > 1 or any(not _rejection_event_matches(e, row) for e in own):
                        raise ValueError("rejection history mismatch")
                    if own:
                        event = own[0]
                        if event["actor_id"] != actor_id or event["rationale"] != rationale:
                            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "기록된 반려 요청과 다른 본문입니다.", 409)
                    else:
                        event = ledger.append(event_type=EVENT_REJECTED, subject_type=SUBJECT_TYPE,
                            subject_id=expected_fingerprint, actor_type="user", actor_id=actor_id,
                            decision=STATUS_REJECTED, rationale=rationale, evidence_refs=_rejection_refs(row),
                            tenant_id=row["tenant_id"], enterprise_scope_id=row["scope_node_id"],
                            entity_mode=row["entity_mode"])
                if not _rejection_event_matches(event, row):
                    raise ValueError("rejection write mismatch")
            except ProcessError:
                raise
            except Exception as exc:
                raise ProcessError("PROCESS_CONTRACT_REJECTION_UNAVAILABLE", "반려 원장을 기록·확인하지 못했습니다.", 503) from exc
            changed = conn.execute("UPDATE kit_app_contracts SET status=?,ledger_event_id=?,updated_at=? "
                "WHERE contract_row_id=? AND status=? AND semantic_fingerprint=?",
                (STATUS_REJECTED, event["event_id"], _now(), row["contract_row_id"], STATUS_DRAFT, expected_fingerprint))
            if changed.rowcount != 1:
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "다른 검토가 먼저 반영되었습니다.", 409)
            return _rejection_result(_v2_row(conn, instance_id, app_id, revision), event)


def reject(store, *, instance_id, app_id, revision, expected_fingerprint,
           actor_id, context, rationale, repo=None):
    """legacy 1.0 현재 초안의 명시 반려. runtime 원문·승인판을 바꾸지 않는다."""
    return _reject_contract(store, instance_id=instance_id, app_id=app_id, revision=revision,
        expected_fingerprint=expected_fingerprint, actor_id=actor_id, context=context,
        rationale=rationale, repo=repo, version="1.0")


def reject_v2(store, *, instance_id, app_id, revision, expected_fingerprint,
              actor_id, context, rationale, repo=None):
    """2.0 현재 초안의 명시 반려. 현재 READ·타인 적격성·원장·CAS를 강제한다."""
    return _reject_contract(store, instance_id=instance_id, app_id=app_id, revision=revision,
        expected_fingerprint=expected_fingerprint, actor_id=actor_id, context=context,
        rationale=rationale, repo=repo, version="2.0")


def _visible_v2_instance(store, instance_id, actor_id, context, repo=None):
    from core.data_preparation.process_kit_instances import binding_for_instance
    from core.enterprise_context.process_configuration import ProcessConfigurationService, missing
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessBoundary
    with ProcessContextService._errors():
        instance = store.get_instance(instance_id)
        if (not instance or not isinstance(context, Mapping) or not context.get("scope_node_id")
                or context.get("tenant_id") != instance["tenant_id"] or context.get("entity_mode") != instance["entity_mode"]):
            raise missing()
        link = binding_for_instance(store, instance)
        if not link or context.get("context_root_id", link["context_root_id"]) != link["context_root_id"]:
            raise missing()
        boundary = ProcessBoundary(tenant_id=instance["tenant_id"], entity_mode=instance["entity_mode"],
                                   context_root_id=link["context_root_id"], scope_node_id=instance["scope_node_id"])
        svc = ProcessConfigurationService(repo=repo, store=store)
        with svc.transaction() as conn:
            svc._authorize(conn, boundary, actor_id, context)
        return instance


def _v2_row(conn, instance_id, app_id, revision):
    row = conn.execute("SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? AND revision=?",
                       (instance_id, app_id, revision)).fetchone()
    return _to_dict(row) if row else None


def _proof_v2(row, *, event_reader=None):
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_schema import ProcessError
    try:
        event = (event_reader or decision_ledger.get_event_strict)(row["ledger_event_id"])
        contract = row["contract"]
        approval = contract["approval"]
        if (not event or event["event_type"] != EVENT_APPROVED or event["subject_type"] != SUBJECT_TYPE
                or event["subject_id"] != row["semantic_fingerprint"] or event["actor_id"] != row["approved_by"]
                or event["tenant_id"] != row["tenant_id"] or event["entity_mode"] != row["entity_mode"]
                or event["enterprise_scope_id"] != row["scope_node_id"] or event["actor_type"] != "user"
                or event["decision"] != STATUS_APPROVED or approval["decision_ledger_id"] != row["ledger_event_id"]
                or approval["approved_by"] != row["approved_by"] or approval["approved_at"] != row["approved_at"]
                or row["drafted_by"].strip().lower() == row["approved_by"].strip().lower()):
            raise ValueError("approval mismatch")
        return event
    except Exception as exc:
        raise ProcessError("PROCESS_CONTRACT_APPROVAL_UNAVAILABLE", "고정 계약의 승인 증명을 확인하지 못했습니다.", 503) from exc


def _review_event_v2(event_id):
    """검토 GET은 원장 파일·테이블을 만들거나 복구하지 않는다. 해당 사건 지문도 검사한다."""
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    from core.decision_ledger import decision_ledger, _compute_hash
    from core.enterprise_context.process_schema import ProcessError
    try:
        uri = Path(decision_ledger.db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            stored = conn.execute("SELECT * FROM decision_ledger_events WHERE event_id=?", (event_id,)).fetchone()
            if not stored:
                raise ValueError("검토 사건 없음")
            row = dict(stored)
            previous = conn.execute("SELECT event_hash FROM decision_ledger_events WHERE seq=?", (row["seq"] - 1,)).fetchone()
            if (row["seq"] < 1 or (row["seq"] > 1 and previous is None)
                    or row["prev_hash"] != (previous[0] if previous else "")
                    or row["event_hash"] != _compute_hash(row, row["prev_hash"])):
                raise ValueError("검토 사건 지문 불일치")
            for key in ("evidence_refs_json", "input_version_refs_json", "output_version_refs_json"):
                if not isinstance(json.loads(row[key]), list):
                    raise ValueError("원장 근거 목록 손상")
            return decision_ledger._to_public(row)
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as exc:
        raise ProcessError("PROCESS_CONTRACT_DECISION_UNAVAILABLE", "고정 계약의 검토 사건을 읽기 전용으로 검증하지 못했습니다.", 503) from exc


def _review_document_v2(store, row, instance, actor_id, context, repo):
    """저장 원문과 과거 승인 업무판을 검증한다. 현재 데이터 사용 허가와는 별개다."""
    from core.data_preparation.process_kit_instances import binding_for_instance, pin_for_store
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, fingerprint
    contract = row["contract"]
    expected_status = {STATUS_DRAFT: STATUS_DRAFT, STATUS_REJECTED: STATUS_DRAFT,
                       STATUS_APPROVED: STATUS_APPROVED, STATUS_SUPERSEDED: STATUS_APPROVED}
    if (not isinstance(contract, dict) or contract.get("schema_version") != "2.0" or arc.validate(contract)
            or row["status"] not in expected_status or contract["status"] != expected_status[row["status"]]
            or type(row["revision"]) is not int or row["revision"] < 1
            or row["contract_row_id"] != _row_id(instance["instance_id"], row["app_id"], row["revision"])
            or contract["project_id"] != instance["instance_id"] or contract["task_id"] != row["app_id"]
            or contract["contract_id"] != arc.contract_id_for(instance["instance_id"], row["app_id"])
            or contract["revision"] != row["revision"] or contract["semantic_fingerprint"] != row["semantic_fingerprint"]
            or any(row[k] != instance[k] for k in ("instance_id", "tenant_id", "scope_node_id", "entity_mode"))
            or not isinstance(row["drafted_by"], str) or not row["drafted_by"].strip() or not row["drafted_at"]):
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "저장 계약의 원문·행·지문이 일치하지 않습니다.", 503)
    if row["status"] == STATUS_DRAFT and (row["approved_by"] or row["approved_at"] or row["ledger_event_id"]
            or contract["approval"]["status"] != "PENDING"
            or any(contract["approval"].get(k) for k in ("approved_by", "approved_at", "decision_ledger_id"))):
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "초안에 미결속 승인 증명이 있습니다.", 503)
    fixed = contract["process_context"]
    boundary = ProcessBoundary.model_validate(fixed["context_key"])
    link = binding_for_instance(store, instance)
    if (not link or boundary.tenant_id != instance["tenant_id"] or boundary.entity_mode != instance["entity_mode"]
            or (boundary.scope_node_id or boundary.context_root_id) != instance["scope_node_id"]
            or boundary.context_root_id != link["context_root_id"]):
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "저장 계약과 적용본의 고정 문맥이 다릅니다.", 503)
    service = ProcessContextService(repo=repo, store=store)
    historical, _, head = service._profiles(boundary, actor_id, context, fixed["profile_id"])
    try:
        description = service._describe(historical, fixed["process_ids"], boundary)
    except ProcessError as exc:
        if exc.status_code != 409:
            raise
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "저장된 계약의 과거 승인 업무 선택이 일치하지 않습니다.", 503) from exc
    digest = fingerprint(historical)
    sources = [dict(kind="PROCESS_PROFILE", configuration_id=head["configuration_id"],
                    profile_id=fixed["profile_id"], fingerprint=digest), *description["sources"]]
    own = [s for s in sources if s["kind"] == "PROCESS_PACK" and s["instance_id"] == instance["instance_id"]]
    if (fixed["configuration_id"] != head["configuration_id"] or fixed["configuration_fingerprint"] != digest
            or fixed["process_semantic_fingerprint"] != description["semantic"]
            or fixed["data_requirements"] != description["requirements"] or fixed["sources"] != sources
            or len(own) != 1
            #: ★ [2026-09-25] 업그레이드한 적용본은 고정 이력을 갖는다 — 계약이 가리키는 원본이 그 이력
            #:   안에 있어야 한다(인스턴스 행·원 링크의 원 정체성 검증은 `pin_for_store` 안에서 한다).
            or not pin_for_store(store, instance, own[0]["artifact_digest"])):
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "고정 업무판·원본과 저장 계약의 참조가 다릅니다.", 503)
    event = None
    if row["status"] == STATUS_REJECTED:
        event = _proof_rejection(row, event_reader=_review_event_v2)
    elif row["status"] in (STATUS_APPROVED, STATUS_SUPERSEDED):
        event = _proof_v2(row, event_reader=_review_event_v2)
        if (event.get("evidence_refs") != [f"kit_instance:{row['instance_id']}", f"app:{row['app_id']}",
                                           f"revision:{row['revision']}"]
                or not isinstance(event.get("rationale"), str) or not event["rationale"].strip()):
            raise ProcessError("PROCESS_CONTRACT_APPROVAL_UNAVAILABLE", "승인 사건의 고정 대상·사유가 다릅니다.", 503)
    if event and event.get("event_id") != row["ledger_event_id"]:
        raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "검토 사건 식별자가 일치하지 않습니다.", 503)
    return event


def _review_actions_v2(store, row, newest, instance, actor_id, context, repo):
    """POST의 현재 타인 검토 조건을 읽기 전용으로 투영한다. 장애는 빈 권한이 아니다."""
    from core import project_data_context as pdc
    from core.enterprise_context.process_schema import ProcessError
    blockers = []

    def block(code, message):
        item = dict(reason_code=code, message=message)
        if item not in blockers:
            blockers.append(item)

    if row["status"] != STATUS_DRAFT:
        block("PROCESS_CONTRACT_" + row["status"], "완료된 검토판입니다. 새 검토는 현재 초안에서 진행하십시오.")
    if newest != row["revision"]:
        block("PROCESS_CONTRACT_CONFLICT", "최신 개정이 아닙니다. 검토하려면 최신 계약을 조회하십시오.")
    if instance["status"] != "active":
        block("PROCESS_INSTANCE_INACTIVE", "현재 적용본이 비활성 상태입니다.")
    # 표시 시점에도 적격성·작성자 분리를 확인한다. 저장 시 POST가 다시 판정한다.
    reviewer = True
    try:
        _rejection_reviewer(actor_id, row)
    except ProcessError as exc:
        if exc.status_code != 403:
            raise
        reviewer = False
        block(exc.reason_code, str(exc))
    if instance["status"] != "active":
        return [], blockers
    try:
        pdc.process_instance(store, instance["instance_id"], actor_id=actor_id, context=context,
            process_context=row["contract"]["process_context"], for_action="READ", repo=repo)
    except ProcessError as exc:
        if exc.status_code not in (403, 409):
            raise
        block(exc.reason_code, str(exc))
        return [], blockers
    eligible = reviewer and row["status"] == STATUS_DRAFT and newest == row["revision"]
    # 반려는 데이터 소비가 아니다. 보류 이력은 읽되 새 계약 승인은 계속 차단한다.
    actions = ["reject"] if eligible else []
    try:
        rebuilt = kb._contract_from_process_context(store, instance_id=instance["instance_id"], app_id=row["app_id"],
            actor_id=actor_id, context=context, process_context=row["contract"]["process_context"],
            app_class=row["contract"]["app_class"], revision=row["revision"], repo=repo, for_action="READ")
        if rebuilt["semantic_fingerprint"] != row["semantic_fingerprint"]:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "현재 고정 앱 후보·데이터 의미와 검토 계약이 다릅니다.", 409)
    except ProcessError as exc:
        if exc.status_code not in (403, 409):
            raise
        block(exc.reason_code, str(exc))
    else:
        if eligible:
            actions.insert(0, "approve")
    return actions, blockers


def read_v2(store, *, instance_id, app_id, actor_id, context, revision=None, repo=None):
    """현재 READ로 고정 계약을 열람한다. 과거 결정 확인은 실행·재승인이 아니다."""
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if (revision is not None and (type(revision) is not int or revision < 1)) or any(
            not isinstance(value, str) or not value.strip() for value in (instance_id, app_id)):
        raise ProcessError("PROCESS_CONTRACT_INVALID", "적용본·앱과 양의 정수 개정을 지정하십시오.", 422)
    with ProcessContextService._errors():
        instance = _visible_v2_instance(store, instance_id, actor_id, context, repo)
        with store.transaction() as conn:
            newest = conn.execute("SELECT MAX(revision) FROM kit_app_contracts WHERE instance_id=? AND app_id=?",
                                  (instance_id, app_id)).fetchone()[0]
            row = _v2_row(conn, instance_id, app_id, revision if revision is not None else newest)
        if not row:
            raise ProcessError("PROCESS_CONTRACT_NOT_FOUND", "조회할 고정 앱 계약을 찾을 수 없습니다.", 404)
        event = _review_document_v2(store, row, instance, actor_id, context, repo)
        actions, blockers = _review_actions_v2(store, row, newest, instance, actor_id, context, repo)
        # 데이터·원장 조회 도중 변경된 행을 과거 조회 결과와 혼합하지 않는다.
        with store.transaction() as conn:
            current = _v2_row(conn, instance_id, app_id, row["revision"])
            latest_revision = conn.execute("SELECT MAX(revision) FROM kit_app_contracts WHERE instance_id=? AND app_id=?",
                                           (instance_id, app_id)).fetchone()[0]
        if current != row or latest_revision != newest:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "조회 중 계약 검토판이 변경되었습니다. 다시 조회하십시오.", 409)
        if actions:
            try:
                _rejection_reviewer(actor_id, row)
            except ProcessError as exc:
                if exc.status_code != 403:
                    raise
                actions = []
                blockers.append(dict(reason_code=exc.reason_code, message=str(exc)))
        if _visible_v2_instance(store, instance_id, actor_id, context, repo) != instance:
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "조회 중 적용본 상태가 변경되었습니다.", 409)
        return dict(instance_id=instance_id, app_id=app_id, revision=row["revision"], latest_revision=newest,
            status=row["status"], semantic_fingerprint=row["semantic_fingerprint"], contract=row["contract"],
            drafted_by=row["drafted_by"], approved_by=row["approved_by"], principal_user_id=actor_id,
            review_blockers=blockers, permitted_actions=actions,
            decision_event=({"event_id": event["event_id"], "decision": event["decision"],
                             "actor_id": event["actor_id"], "rationale": event["rationale"]} if event else None))


def validated_v2(store, *, instance_id, app_id, revision, expected_fingerprint, actor_id, context,
                 for_action="GENERATE", require_approved=False, repo=None):
    from core import project_data_context as pdc
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if type(revision) is not int or revision < 1 or not isinstance(expected_fingerprint, str) or not expected_fingerprint:
        raise ProcessError("PROCESS_CONTRACT_INVALID", "고정 개정과 검토 지문이 필요합니다.", 422)
    instance = _visible_v2_instance(store, instance_id, actor_id, context, repo)
    with ProcessContextService._errors():
        with store.transaction() as conn:
            row = _v2_row(conn, instance_id, app_id, revision)
        if not row:
            raise ProcessError("PROCESS_CONTRACT_NOT_FOUND", "고정 앱 계약을 찾을 수 없습니다.", 404)
        if row["status"] == STATUS_REJECTED:
            _proof_rejection(row)
            raise ProcessError("PROCESS_CONTRACT_REJECTED", "반려된 계약은 새 개정으로 다시 제안하십시오.", 409)
        if row["status"] == STATUS_SUPERSEDED:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "다른 승인 개정으로 대체된 앱 계약입니다.", 409)
        contract = row["contract"]
        if (not isinstance(contract, dict) or contract.get("schema_version") != "2.0" or arc.validate(contract)
                or contract["project_id"] != instance_id or contract["task_id"] != app_id
                or contract["revision"] != revision or contract["semantic_fingerprint"] != row["semantic_fingerprint"]
                or contract["status"] != row["status"]
                or any(row[k] != instance[k] for k in ("tenant_id", "scope_node_id", "entity_mode"))):
            raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "고정 앱 계약의 형식·정체성을 확인하지 못했습니다.", 503)
        if row["semantic_fingerprint"] != expected_fingerprint:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "검토한 앱 계약의 지문이 다릅니다.", 409)
        if require_approved and row["status"] != STATUS_APPROVED:
            raise ProcessError("PROCESS_CONTRACT_APPROVAL_REQUIRED", "앱 계약을 먼저 독립 승인하십시오.", 409)
        pdc.process_instance(store, instance_id, actor_id=actor_id, context=context,
            process_context=contract["process_context"], for_action=for_action, repo=repo)
        rebuilt = kb._contract_from_process_context(store, instance_id=instance_id, app_id=app_id,
            actor_id=actor_id, context=context, process_context=contract["process_context"],
            app_class=contract["app_class"], revision=revision, repo=repo, for_action=for_action)
        if rebuilt["semantic_fingerprint"] != row["semantic_fingerprint"]:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "원본 앱 후보·고정 schema와 계약 의미가 다릅니다.", 409)
        if row["status"] == STATUS_APPROVED:
            _proof_v2(row)
        return row


def draft_v2(store, *, instance_id, app_id, actor_id, context, process_context,
             app_class, expected_revision, repo=None):
    from core import project_data_context as pdc
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if type(expected_revision) is not int or expected_revision < 0:
        raise ProcessError("PROCESS_CONTRACT_INVALID", "현재 개정을 정수로 명시하십시오.", 422)
    contract = kb.contract_from_process_context(store, instance_id=instance_id, app_id=app_id,
        actor_id=actor_id, context=context, process_context=process_context, app_class=app_class,
        revision=expected_revision + 1, repo=repo)
    instance, bundle, verified = pdc.process_instance(store, instance_id, actor_id=actor_id,
        context=context, process_context=contract["process_context"], repo=repo)
    with ProcessContextService._errors():
        with store.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            pdc.check_process_refs_conn(conn, store=store, instance=instance, bundle=bundle,
                process_context=verified, actor_id=actor_id, context=context, repo=repo)
            _write_authority_v2(store, verified, actor_id, context, "GENERATE", repo)
            previous = conn.execute("SELECT * FROM kit_app_contracts WHERE instance_id=? AND app_id=? ORDER BY revision DESC LIMIT 1",
                                    (instance_id, app_id)).fetchone()
            previous = _to_dict(previous) if previous else None
            if previous and (not isinstance(previous["contract"], dict) or previous["contract"].get("schema_version") != "2.0"):
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "레거시 계약을 새 업무 문맥으로 덮을 수 없습니다.", 409)
            if previous and previous["status"] == STATUS_REJECTED:
                _proof_rejection(previous)
            if previous and (arc.validate(previous["contract"])
                    or previous["contract"]["semantic_fingerprint"] != previous["semantic_fingerprint"]
                    or previous["contract"]["revision"] != previous["revision"]
                    or previous["contract"]["project_id"] != instance_id or previous["contract"]["task_id"] != app_id
                    or previous["contract"]["status"] != (STATUS_DRAFT if previous["status"] == STATUS_REJECTED else previous["status"])):
                raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "이전 앱 계약의 원문·지문을 확인하지 못했습니다.", 503)
            current_revision = previous["revision"] if previous else 0
            fp = contract["semantic_fingerprint"]
            if (previous and previous["status"] != STATUS_REJECTED
                    and previous["semantic_fingerprint"] == fp and previous["drafted_by"] == actor_id
                    and current_revision in (expected_revision, expected_revision + 1)):
                if previous["status"] == STATUS_APPROVED:
                    _proof_v2(previous)
                return previous
            if current_revision != expected_revision:
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "다른 앱 계약 개정이 먼저 저장되었습니다.", 409)
            now, revision = _now(), expected_revision + 1
            conn.execute("INSERT INTO kit_app_contracts (contract_row_id,instance_id,app_id,revision,status,semantic_fingerprint,"
                         "contract_json,drafted_by,drafted_at,tenant_id,scope_node_id,entity_mode,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_row_id(instance_id, app_id, revision), instance_id, app_id, revision, STATUS_DRAFT, fp,
                 json.dumps(contract, ensure_ascii=False, sort_keys=True), actor_id, now, instance["tenant_id"],
                 instance["scope_node_id"], instance["entity_mode"], now))
            return _v2_row(conn, instance_id, app_id, revision)


def approve_v2(store, *, instance_id, app_id, revision, expected_fingerprint,
               actor_id, context, rationale, repo=None):
    from core import project_data_context as pdc
    from core.data_preparation import ownership_binding as ob
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if not isinstance(rationale, str) or not rationale.strip():
        raise ProcessError("PROCESS_CONTRACT_INVALID", "앱 계약 승인 이유가 필요합니다.", 422)
    row = validated_v2(store, instance_id=instance_id, app_id=app_id, revision=revision,
        expected_fingerprint=expected_fingerprint, actor_id=actor_id, context=context, for_action="READ", repo=repo)
    with ProcessContextService._errors():
        try:
            ob.require_approval_authority(actor_id)
        except ob.OwnershipError as exc:
            # OwnershipError는 ValueError 하위다. 공통 손상 처리기보다 먼저
            # 권한 거부를 변환해야 정상적인 403을 저장소 장애 503으로 오인하지 않는다.
            raise ProcessError("PROCESS_ACTION_FORBIDDEN", "앱 계약 승인 권한이 없습니다.", 403) from exc
    if row["drafted_by"].strip().lower() == actor_id.strip().lower():
        raise ProcessError("PROCESS_DISTINCT_REVIEWER_REQUIRED", "작성자와 다른 적격 앱 계약 승인자가 필요합니다.", 403)
    if row["status"] == STATUS_APPROVED:
        event = _proof_v2(row)
        if row["approved_by"] != actor_id or event.get("rationale") != rationale:
            raise ProcessError("PROCESS_CONTRACT_CONFLICT", "완료한 승인 요청과 다른 본문입니다.", 409)
        return row
    if row["status"] != STATUS_DRAFT:
        raise ProcessError("PROCESS_CONTRACT_CONFLICT", "승인 가능한 계약 초안이 아닙니다.", 409)
    instance, bundle, verified = pdc.process_instance(store, instance_id, actor_id=actor_id,
        context=context, process_context=row["contract"]["process_context"], for_action="READ", repo=repo)
    with ProcessContextService._errors():
        with store.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = _v2_row(conn, instance_id, app_id, revision)
            latest_revision = conn.execute("SELECT MAX(revision) FROM kit_app_contracts WHERE instance_id=? AND app_id=?",
                                           (instance_id, app_id)).fetchone()[0]
            if current != row or latest_revision != revision:
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "앱 계약 초안이 검토 중 변경되었습니다.", 409)
            pdc.check_process_refs_conn(conn, store=store, instance=instance, bundle=bundle,
                process_context=verified, actor_id=actor_id, context=context, repo=repo)
            _write_authority_v2(store, verified, actor_id, context, "READ", repo)
            try:
                ob.require_approval_authority(actor_id)
            except ob.OwnershipError as exc:
                raise ProcessError("PROCESS_ACTION_FORBIDDEN", "현재 앱 계약 승인 권한이 없습니다.", 403) from exc
            # 원장은 별도 DB다. DP 실패 시 미결속 원장 사건은 승인 상태가 아니다.
            try:
                event = decision_ledger.append(event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE,
                    subject_id=expected_fingerprint, actor_type="user", actor_id=actor_id, decision="APPROVED",
                    rationale=rationale, evidence_refs=[f"kit_instance:{instance_id}", f"app:{app_id}", f"revision:{revision}"],
                    tenant_id=instance["tenant_id"], enterprise_scope_id=instance["scope_node_id"], entity_mode=instance["entity_mode"])
            except Exception as exc:
                raise ProcessError("PROCESS_CONTRACT_APPROVAL_UNAVAILABLE", "앱 계약 승인 원장 기록에 실패했습니다.", 503) from exc
            now = _now()
            contract = dict(row["contract"])
            contract["status"] = STATUS_APPROVED
            contract["approval"] = dict(status="APPROVED", approved_by=actor_id, approved_at=now, decision_ledger_id=event["event_id"])
            contract["semantic_fingerprint"] = arc.semantic_fingerprint(contract)
            if arc.validate(contract) or contract["semantic_fingerprint"] != expected_fingerprint:
                raise ProcessError("PROCESS_CONTRACT_UNAVAILABLE", "승인 봉투와 고정 계약 지문이 다릅니다.", 503)
            conn.execute("UPDATE kit_app_contracts SET status=?,updated_at=? WHERE instance_id=? AND app_id=? AND status=?",
                         (STATUS_SUPERSEDED, now, instance_id, app_id, STATUS_APPROVED))
            updated = conn.execute("UPDATE kit_app_contracts SET status=?,approved_by=?,approved_at=?,ledger_event_id=?,contract_json=?,updated_at=? "
                                   "WHERE contract_row_id=? AND status=? AND semantic_fingerprint=?",
                (STATUS_APPROVED, actor_id, now, event["event_id"], json.dumps(contract, ensure_ascii=False, sort_keys=True), now,
                 row["contract_row_id"], STATUS_DRAFT, expected_fingerprint))
            if updated.rowcount != 1:
                raise ProcessError("PROCESS_CONTRACT_CONFLICT", "다른 앱 계약 검토가 먼저 반영되었습니다.", 409)
            return _v2_row(conn, instance_id, app_id, revision)


def _write_authority_v2(store, process_context, actor_id, context, action, repo):
    """데이터 조회 중 역할 회수가 일어났다면 저장 직전 현재 권한으로 거부한다."""
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessBoundary, ProcessError
    service = ProcessContextService(repo=repo, store=store)
    allowed = service._permissions(ProcessBoundary.model_validate(process_context["context_key"]), actor_id, context)
    if action not in allowed:
        raise ProcessError("PROCESS_ACTION_FORBIDDEN", "현재 업무 범위의 계약 저장 권한이 없습니다.", 403)
