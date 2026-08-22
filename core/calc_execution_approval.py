"""★★★ [M0-0] 계산 능력 **실행 승인** — 사람이 누르는 자리, 그리고 그 승인이 죽는 조건.

## 이 파일이 하는 일과 **하지 않는 일**

    하는 일    승인 제안서를 산출하고, 사람이 누르면 원장에 남기고, 매 실행마다 다시 본다
    안 하는 일 **스스로 승인하지 않는다.** `approve()` 는 사람의 요청으로만 불린다.

⚠️⚠️ 이 모듈을 import 하는 것만으로는 아무것도 승인되지 않는다. 등록부(`calc_capability`)
  는 계속 `IMPLEMENTED_UNAPPROVED` 이고, 승인 기록이 **살아 있을 때만** 실행 가능으로
  덮인다. 기록이 죽으면 등록부의 원래 상태로 돌아간다 — 되돌리기가 기본값이다.

## ⚠️⚠️ 승인은 「이 산식」이 아니라 **「이 산식을 이 조건에서」**를 승인한다

승인 대상(`subject_id`)은 아래 전부를 묶은 **하나의 지문**이다. 하나라도 바뀌면 지문이
바뀌고, 그 순간 승인은 **자동으로 죽는다.**

| 묶는 것 | 왜 |
|---|---|
| 산식 정체성·판 | 산식이 바뀌면 다른 계산이다 |
| 단위·부호 방향 | 「재고 +230」이 좋은 소식인지 나쁜 소식인지가 뒤집힌다 |
| 필수 계약키 | 입력이 달라지면 다른 계산이다 |
| **인증판 집합** | 승인 이후 올라온 판으로 계산하면서 옛 승인을 근거로 삼을 수 없다 |
| 코드 지문 | 계약이 같아도 구현이 바뀌면 다른 답이 나온다 |
| 정본 규칙(BOM·날짜) | 규칙이 바뀌면 같은 입력이 다른 답을 낸다 |
| 실행 범위 | `DEMO/SYNTHETIC` 승인으로 운영 자료를 계산하지 않는다 |

★ 그리고 **유효기간**이 있다. 시연 한정 승인은 영구 승인이 아니다.

⚠️ `subject_id` 에 `Capability.fingerprint()` 를 쓰지 않는다 — 그 값은 `state` 와
  `ledger_event_id` 를 포함하므로, 승인하고 상태를 올리는 순간 지문이 바뀌어 **방금 한
  승인이 죽는다**(M0-3.2 에서 실측했다).

LLM 호출: 0건.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core import calc_capability as cc
from core.data_preparation import store as dp

#: 원장 사건. ⚠️ 대상은 **결속 지문**이다 — 참조 이름이 아니다.
APPROVED_EVENT = "CALC_CAPABILITY_APPROVED"
REVOKED_EVENT = "CALC_CAPABILITY_REVOKED"
SUBJECT_TYPE = "calc_capability"

ACTIVE = "active"
REVOKED = "revoked"

#: 시연 한정 승인의 기본값 — 사용자가 화면에서 바꿀 수 있다.
DEFAULT_DATA_KIND = "DEMO/SYNTHETIC"
DEFAULT_ENTITY_MODE = "VIRTUAL"
DEFAULT_VALID_DAYS = 30
MAX_VALID_DAYS = 90

#: 승인이 매달리는 **정본 규칙**. ⚠️ 이 값이 바뀌면 같은 입력이 다른 답을 낸다.
_CANON_RULES = ("bom_recompute_must_match", "date_only_is_midnight_utc",
                "available_excludes_safety_and_reserved")

#: 코드 지문을 뜨는 파일. ⚠️ 계약이 같아도 **구현이 바뀌면 다른 답**이 나온다.
_CODE_FILES = ("core/calc_models.py", "core/calc_projection.py")


class ExecutionApprovalError(Exception):
    """실행 승인을 만들거나 읽을 수 없다. ⚠️ 「일단 통과」로 접지 않는다."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def code_fingerprint() -> str:
    """산식 구현의 지문.

    ⚠️ 파일을 못 읽으면 **던진다.** 빈 문자열로 접으면 「코드가 없는 승인」이 서고,
      그 승인은 어떤 구현으로 바뀌어도 살아남는다."""
    parts: List[str] = []
    for rel in _CODE_FILES:
        path = os.path.join(_repo_root(), rel.replace("/", os.sep))
        try:
            with io.open(path, "rb") as fh:
                parts.append(f"{rel}:{hashlib.sha256(fh.read()).hexdigest()}")
        except OSError as exc:
            raise ExecutionApprovalError(
                f"산식 구현 파일을 읽지 못했습니다({rel}): {exc} — 코드 지문 없이 "
                f"승인하지 않습니다.")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def binding(cap: cc.Capability, *, data_kind: str, entity_mode: str, tenant_id: str,
            scope_node_id: str, snapshots: Mapping[str, str],
            contract_fingerprint: str) -> Dict[str, Any]:
    """승인이 매달리는 **조건 전부.** 화면이 이것을 그대로 보여 준다."""
    return {
        "ref": cap.ref,
        "model_version": cap.model_version,
        "relation": f"{cap.subject_type} -{cap.relation}-> {cap.object_type}",
        #: 단위·부호는 계약의 코드 그대로 — 표시명으로 굳히지 않는다.
        "outputs": [list(o) for o in cap.outputs],
        "required_datasets": list(cap.required_datasets),
        #: ★★★ **어느 판으로 승인했는가.** 판이 바뀌면 승인이 죽는다.
        "snapshots": {str(k): str(v) for k, v in sorted(dict(snapshots).items())},
        "code_fingerprint": code_fingerprint(),
        "contract_fingerprint": str(contract_fingerprint or ""),
        "canonical_rules": list(_CANON_RULES),
        "scope": {"data_kind": data_kind, "entity_mode": entity_mode,
                  "tenant_id": tenant_id, "scope_node_id": scope_node_id},
    }


def binding_fingerprint(bound: Mapping[str, Any]) -> str:
    """결속의 지문 — 원장 사건의 **대상**이 된다.

    ⚠️ 유효기간은 넣지 않는다. 기간은 «언제까지» 이지 «무엇을» 이 아니고, 넣으면 같은
      조건의 재승인이 다른 대상이 되어 멱등을 잃는다."""
    return hashlib.sha256(json.dumps(
        bound, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


# ── 제안서: 화면이 보여 주는 것 ───────────────────────────────────────────

def proposal(store: Any, *, instance_id: str, tenant_id: str, entity_mode: str = "",
             scope_node_id: str, data_kind: str = DEFAULT_DATA_KIND,
             valid_days: int = DEFAULT_VALID_DAYS, contract_fingerprint: str = "",
             refs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """승인 화면이 보여 줄 **제안서.** 서버가 지문을 직접 산출한다.

    ★★★ 호출자가 지문을 적어 보낼 수 없다 — 적어 보내게 두면 「무엇을 승인했는가」가
      주장이 된다. 화면은 서버가 낸 값을 **보여 주기만** 한다.

    ⚠️ 이 함수는 **아무것도 승인하지 않는다.** 부작용이 없다."""
    from core import calc_dataset_loader as loader
    from core import path_calculation as pc

    mode = str(entity_mode or DEFAULT_ENTITY_MODE)
    days = int(valid_days or DEFAULT_VALID_DAYS)
    if not 1 <= days <= MAX_VALID_DAYS:
        raise ExecutionApprovalError(
            f"유효기간은 1~{MAX_VALID_DAYS}일이어야 합니다({days}) — 무기한 승인은 "
            f"승인이 아니라 기본값입니다.")
    seals = loader.active_seals(store, instance_id=instance_id,
                                contract_keys=pc.REQUIRED_DATASETS)
    now = _now()
    valid_until = _iso(now + timedelta(days=days))

    wanted = [str(r).strip() for r in (refs or pc.SEGMENTS) if str(r).strip()]
    items: List[Dict[str, Any]] = []
    for ref in wanted:
        cap = cc.get(ref)
        missing = sorted(set(cap.required_datasets) - set(seals))
        bound = binding(cap, data_kind=data_kind, entity_mode=mode, tenant_id=tenant_id,
                        scope_node_id=scope_node_id,
                        #: ★ 이 산식이 **쓰는 계약키의 판만** 묶는다 — 안 쓰는 판이 바뀐다고
                        #:   승인이 죽으면 재승인이 잦아 사람이 내용을 안 읽게 된다.
                        snapshots={k: v for k, v in seals.items()
                                   if k in cap.required_datasets},
                        contract_fingerprint=contract_fingerprint)
        items.append({
            "ref": ref,
            "state": cap.state,
            "blocked_reason": cap.blocked_reason,
            #: 화면이 보여 줄 것 — 정의·단위·부호·범위·유효기간.
            "definition": {
                "relation": bound["relation"],
                "model_version": cap.model_version,
                "outputs": [{"metric": m, "unit": u,
                             "unit_display": cc.UNIT_DISPLAY.get(u, u), "direction": d}
                            for m, u, d in cap.outputs],
                "required_datasets": list(cap.required_datasets),
                "canonical_rules": list(_CANON_RULES),
            },
            "binding": bound,
            "binding_fingerprint": binding_fingerprint(bound),
            #: ⚠️ 인증판이 없는 계약키가 있으면 **승인할 수 없다** — 무엇으로 계산할지
            #:   모르는 채 승인하는 것이고, 그 승인은 아무 판에나 붙는다.
            "approvable": not missing,
            "missing_contract_keys": missing,
        })
    return {
        "scope": {"data_kind": data_kind, "entity_mode": mode, "tenant_id": tenant_id,
                  "scope_node_id": scope_node_id, "instance_id": instance_id},
        "valid_days": days,
        "valid_until": valid_until,
        "generated_at": _iso(now),
        "items": items,
        #: ★★★ **아직 아무것도 승인되지 않았다.** 화면이 이 문장을 그대로 보여 준다.
        "notice": ("이 화면은 제안서입니다 — 누르기 전까지 계산은 계속 BLOCKED 로 "
                   "답합니다. 승인은 능력마다 별도 원장 사건으로 남습니다."),
    }


# ── 승인·철회: 사람이 누를 때만 불린다 ────────────────────────────────────

def approve(store: Any, *, ref: str, bound: Mapping[str, Any], actor: str,
            rationale: str, valid_days: int = DEFAULT_VALID_DAYS) -> Dict[str, Any]:
    """실행 승인을 **원장에 남기고 저장소에 기록한다.**

    ⚠️⚠️ **이 함수는 사람의 요청으로만 불린다.** 시드·마이그레이션·기동 코드에서 부르지
      않는다 — 그러면 「누가 승인했는지 없는 승인」이 선다.

    ★ 멱등: 같은 결속에 살아 있는 승인이 있으면 **새 사건을 만들지 않고** 그것을
      돌려준다. 재시도가 승인 사건을 쌓으면 원장이 「몇 번 승인했나」로 오염된다.

    ★ 원장 먼저, 저장소 나중. 반대로 하면 원장 실패 시 «승인됐다고 적힌 행» 이 남는다."""
    who = str(actor or "").strip()
    why = str(rationale or "").strip()
    if not who:
        raise ExecutionApprovalError("승인 행위자가 없습니다 — 「누가 승인했나」에 답할 수 "
                                     "없는 승인은 승인이 아닙니다.")
    if not why:
        raise ExecutionApprovalError("승인 사유가 필요합니다 — 사유 없는 승인은 나중에 "
                                     "「왜 켰나」에 답할 수 없습니다.")
    cap = cc.get(str(ref or "").strip())
    if cap.state == cc.OUT_OF_SCOPE:
        #: ⚠️ 범위 밖을 승인으로 열지 않는다. 범위를 넓히는 것은 계약 변경이다.
        raise ExecutionApprovalError(
            f"{cap.ref}: 범위 밖 계산은 승인으로 열 수 없습니다 — 계약을 먼저 바꾸십시오.")
    if cap.state == cc.NOT_IMPLEMENTED:
        raise ExecutionApprovalError(f"{cap.ref}: 구현되지 않은 계산은 승인할 수 없습니다.")
    if str(bound.get("ref", "")) != cap.ref:
        raise ExecutionApprovalError(
            f"결속이 이 계산의 것이 아닙니다({bound.get('ref')} ≠ {cap.ref}).")

    days = int(valid_days or DEFAULT_VALID_DAYS)
    if not 1 <= days <= MAX_VALID_DAYS:
        raise ExecutionApprovalError(f"유효기간은 1~{MAX_VALID_DAYS}일이어야 합니다({days}).")

    fp = binding_fingerprint(bound)
    scope = dict(bound.get("scope") or {})
    tenant = str(scope.get("tenant_id", "") or "")
    mode = str(scope.get("entity_mode", "") or "")

    existing = _row(store, fp)
    if existing and existing["status"] == ACTIVE:
        #: ★ 멱등 — 같은 결속의 살아 있는 승인이 이미 있다.
        return {**existing, "idempotent": True}

    from core.decision_ledger import DecisionLedgerError, decision_ledger

    try:
        event = decision_ledger.append(
            event_type=APPROVED_EVENT, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="user", actor_id=who, decision="APPROVED", rationale=why,
            tenant_id=tenant or "tenant_default", entity_mode=mode or DEFAULT_ENTITY_MODE)
    except DecisionLedgerError as exc:
        raise ExecutionApprovalError(f"승인을 원장에 남기지 못했습니다: {exc}")

    now = _now()
    row = {
        "approval_id": "cea_" + uuid.uuid4().hex[:20],
        "ref": cap.ref, "binding_fingerprint": fp, "status": ACTIVE,
        "ledger_event_id": str(event["event_id"]),
        "binding_json": json.dumps(bound, ensure_ascii=False, sort_keys=True),
        "tenant_id": tenant, "entity_mode": mode,
        "scope_node_id": str(scope.get("scope_node_id", "") or ""),
        "data_kind": str(scope.get("data_kind", "") or ""),
        "valid_until": _iso(now + timedelta(days=days)),
        "approved_by": who, "rationale": why,
        "created_at": _iso(now), "updated_at": _iso(now),
    }
    try:
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO calc_execution_approvals (approval_id, ref, "
                "binding_fingerprint, status, ledger_event_id, binding_json, tenant_id, "
                "entity_mode, scope_node_id, data_kind, valid_until, approved_by, "
                "rationale, created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[k] for k in (
                    "approval_id", "ref", "binding_fingerprint", "status",
                    "ledger_event_id", "binding_json", "tenant_id", "entity_mode",
                    "scope_node_id", "data_kind", "valid_until", "approved_by",
                    "rationale", "created_at", "updated_at")))
    except Exception as exc:  # noqa: BLE001
        #: ⚠️⚠️ 원장에는 승인이 남았는데 저장소가 실패했다. **보상 철회**를 남긴다 —
        #:   안 남기면 원장만 보고 「승인됐다」고 읽게 된다.
        try:
            decision_ledger.append(
                event_type=REVOKED_EVENT, subject_type=SUBJECT_TYPE, subject_id=fp,
                actor_type="system", actor_id="system@afs.invalid", decision="REVOKED",
                rationale=f"승인 기록 실패로 자동 취소: {exc}",
                parent_event_id=str(event["event_id"]),
                tenant_id=tenant or "tenant_default",
                entity_mode=mode or DEFAULT_ENTITY_MODE)
        except Exception as undo:  # noqa: BLE001
            raise ExecutionApprovalError(
                f"승인을 기록하지 못했고 취소도 남기지 못했습니다 — 원장에 승인만 "
                f"남아 있습니다(사건 {event['event_id']}). 기록 실패: {exc} / "
                f"취소 실패: {undo}")
        raise ExecutionApprovalError(f"승인을 기록하지 못해 취소했습니다: {exc}")
    return {**row, "idempotent": False}


def revoke(store: Any, *, approval_id: str, actor: str, reason: str) -> Dict[str, Any]:
    """실행 승인을 철회한다. **원장에 자식 사건을 남기고** 저장소 행을 내린다.

    ⚠️ 행만 내리면 원장에는 승인만 남아 여전히 유효해 보인다."""
    who = str(actor or "").strip()
    why = str(reason or "").strip()
    if not who or not why:
        raise ExecutionApprovalError("철회에는 행위자와 사유가 모두 필요합니다.")
    with store.transaction() as conn:
        row = conn.execute("SELECT * FROM calc_execution_approvals WHERE approval_id=?",
                           (str(approval_id or "").strip(),)).fetchone()
    if not row:
        raise ExecutionApprovalError(f"실행 승인을 찾을 수 없습니다: {approval_id}")
    item = dict(row)
    if item["status"] != ACTIVE:
        return {**item, "already": True}

    from core.decision_ledger import DecisionLedgerError, decision_ledger

    try:
        decision_ledger.append(
            event_type=REVOKED_EVENT, subject_type=SUBJECT_TYPE,
            subject_id=item["binding_fingerprint"], actor_type="user", actor_id=who,
            decision="REVOKED", rationale=why,
            parent_event_id=item["ledger_event_id"],
            tenant_id=item["tenant_id"] or "tenant_default",
            entity_mode=item["entity_mode"] or DEFAULT_ENTITY_MODE)
    except DecisionLedgerError as exc:
        raise ExecutionApprovalError(f"철회를 원장에 남기지 못했습니다: {exc}")
    with store.transaction() as conn:
        conn.execute("UPDATE calc_execution_approvals SET status=?, updated_at=? "
                     "WHERE approval_id=?", (REVOKED, _iso(_now()), item["approval_id"]))
    return {**item, "status": REVOKED, "already": False}


# ── 확인: 매 실행마다 다시 본다 ───────────────────────────────────────────

def _row(store: Any, fingerprint: str) -> Optional[Dict[str, Any]]:
    with store.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM calc_execution_approvals WHERE binding_fingerprint=? "
            "AND status=? ORDER BY created_at DESC LIMIT 1",
            (fingerprint, ACTIVE)).fetchone()
    return dict(row) if row else None


def active(store: Any, *, ref: str, bound: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """이 결속의 **살아 있는 승인.** 없으면 `None`.

    ★★★ 확인하는 것 — 하나라도 어긋나면 승인이 아니다:
      ① 저장소에 `active` 행이 있는가(대상은 **결속 지문**이다)
      ② 참조가 같은가
      ③ **유효기간이 남았는가** — 시연 한정 승인은 영구 승인이 아니다
      ④ 원장 사건이 실재하고 목적 전용 유형인가
      ⑤ 철회 자식 사건이 없는가

    ⚠️ 원장을 못 읽으면 **던진다.** 「모르니까 승인 없음」으로 접으면 장애 중에 모든
      계산이 「승인 대기」로 보이고, 아무도 원장을 보러 가지 않는다."""
    fp = binding_fingerprint(bound)
    row = _row(store, fp)
    if not row or str(row["ref"]) != str(ref):
        return None
    try:
        until = datetime.fromisoformat(str(row["valid_until"]))
    except ValueError:
        #: ⚠️ 기간을 읽지 못한 승인은 **무기한이 아니다.** 무효로 본다.
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if until <= _now():
        return None

    from core.decision_ledger import decision_ledger

    #: ⚠️ `get_event_strict`·`has_invalidating_child` 는 판독 실패를 **던진다** —
    #:   그 예외를 여기서 잡지 않는다(호출부가 503 으로 바꾼다).
    event = decision_ledger.get_event_strict(str(row["ledger_event_id"]))
    if not event:
        return None
    if str(event.get("event_type", "")) != APPROVED_EVENT:
        return None
    if str(event.get("subject_type", "")) != SUBJECT_TYPE:
        return None
    if str(event.get("subject_id", "")).strip() != fp:
        return None
    if decision_ledger.has_invalidating_child(str(row["ledger_event_id"]),
                                              (REVOKED_EVENT,)):
        return None
    return row


def effective(store: Any, ref: str, *, bound: Mapping[str, Any]) -> cc.Capability:
    """지금 이 조건에서의 **실효 능력.**

    ★★★ 살아 있는 승인이 있으면 `APPROVED` 로 덮고, 없으면 **등록부 그대로** 돌려준다.
      되돌리기가 기본값이다 — 승인 기록이 사라지면 자동으로 막힌다.

    ⚠️ 등록부 상수를 고치지 않는다. 고치면 프로세스 전체·모든 테넌트에 걸리고, 그때는
      「이 조직에서 승인됐다」와 「어디서나 승인됐다」가 같은 말이 된다."""
    cap = cc.get(ref)
    got = active(store, ref=ref, bound=bound)
    if not got:
        return cap
    return cc.Capability(**{**cap.__dict__, "state": cc.APPROVED, "blocked_reason": "",
                            "ledger_event_id": str(got["ledger_event_id"])})


def list_approvals(store: Any, *, tenant_id: str = "", scope_node_id: str = ""
                   ) -> List[Dict[str, Any]]:
    """승인 목록. ⚠️ 문맥으로 좁힌다 — 남의 조직 승인의 존재를 알려 주지 않는다."""
    sql = "SELECT * FROM calc_execution_approvals WHERE 1=1"
    args: List[Any] = []
    if tenant_id:
        sql += " AND tenant_id=?"
        args.append(tenant_id)
    if scope_node_id:
        sql += " AND scope_node_id=?"
        args.append(scope_node_id)
    sql += " ORDER BY created_at DESC LIMIT 200"
    with store.transaction() as conn:
        rows = conn.execute(sql, tuple(args)).fetchall()
    return [dict(r) for r in rows]
