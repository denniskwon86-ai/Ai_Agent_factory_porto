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
SUBJECT_TYPE = "app_contract"

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

    prev = latest(store, instance_id, app_id)
    revision = int(prev["revision"]) if prev else 1
    contract = kb.contract_from_blueprint(
        blueprint, project_id=str(instance_id), app_class=app_class,
        revision=revision, labels=labels,
        schema_for=lambda k: kb.fields_from_certified(store, instance_id, k))
    fp = str(contract.get("semantic_fingerprint") or "")

    if prev:
        if str(prev.get("semantic_fingerprint") or "") == fp:
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
            "WHERE kit_app_contracts.status <> 'APPROVED'",
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
    if str(row.get("status")) == STATUS_APPROVED:
        #: ★ 멱등 — 이미 승인돼 있으면 원장에 아무것도 더 쓰지 않는다.
        return row
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
