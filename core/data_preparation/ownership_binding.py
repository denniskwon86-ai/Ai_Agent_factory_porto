"""★★★ [G2 · Dataset Ownership Binding] 「이 데이터셋은 어느 부서가 소유하는가」의 **정본.**

## 왜 별도 정본인가 — 업무 행이 자기 권한을 정하면 안 된다

종전 색인은 업무 데이터 행의 `owner_dept_id` 열을 그대로 읽었다. 그러면 **자기 데이터의
권한 범위를 데이터가 스스로 정한다** — 직전에 지운 `calc_binding` 과 **같은 유형의
자기진술 통제**다. 고객사 파일 한 칸을 고치면 그 데이터의 소유 부서가 바뀐다.

그래서 소유권은 **승인된 결속**에만 있다.

    (tenant_id, entity_mode, dataset_contract_key, scope_node_id, 유효기간)
        → owner_dept_id     + 승인자 · 승인시각 · 근거 · 지문

## `object_scope_index.owner_dept_id` 는 정본이 아니다

그것은 **물질화된 결과**다. 그래서 `owner_binding_id` · `owner_binding_fingerprint` 를 함께
봉인한다 — 나중에 「이 색인 값은 어느 결속에서 나왔나」를 물을 수 있어야 하고, 결속이
바뀌었는지도 알 수 있어야 한다.

⚠️⚠️ 색인이 있어도 **요청 시 다시 검증한다.** 승인 철회 · 결속 폐지 · 부서 폐지 · 원장 장애는
  모두 이미 만들어진 색인 뒤에서 일어난다. 물질화 시점의 판단을 영구히 믿으면 그것이 곧
  「회수해도 계속 유효한 권한」이다(SSE 티켓에서 같은 실수를 이미 고쳤다).

## FND-01 은 조직 정본일 뿐이다

부서가 **존재하는가**는 조직 정본(`org_directory`)이 답한다. 그러나 **어느 부서가 이
데이터셋을 소유하는가**는 조직 정본에 없다 — 그것이 이 파일이 있는 이유다. 둘을 섞으면
「조직도에 부서가 있으니 소유도 정해졌다」로 읽힌다.

## 중첩은 임의로 고르지 않는다

같은 키·겹치는 유효기간에 ACTIVE 결속이 둘이면 **무결성 오류**다. 하나를 골라 답하면
그 선택은 아무 근거가 없고, 다음 조회에서 다른 것이 뽑힐 수도 있다 — 같은 질문에 다른
답을 주는 통제는 통제가 아니다.

LLM 0콜. 결정론적.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ACTIVE = "ACTIVE"
REVOKED = "REVOKED"
RETIRED = "RETIRED"
STATUSES = (ACTIVE, REVOKED, RETIRED)

#: 무기한 끝점을 비교할 때 쓰는 상한. `''` 를 그대로 비교하면 «가장 작은 값» 이 되어
#: 무기한이 오히려 «이미 끝난 것» 으로 읽힌다.
_OPEN_END = "9999-12-31T23:59:59+00:00"

DDL = """
CREATE TABLE IF NOT EXISTS dataset_ownership_bindings (
    binding_id           TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    entity_mode          TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL,
    scope_node_id        TEXT NOT NULL,
    owner_dept_id        TEXT NOT NULL,
    effective_from       TEXT NOT NULL,
    effective_to         TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'ACTIVE',
    approved_by          TEXT NOT NULL,
    approved_at          TEXT NOT NULL,
    evidence_ref         TEXT NOT NULL DEFAULT '',
    fingerprint          TEXT NOT NULL,
    revoked_by           TEXT NOT NULL DEFAULT '',
    revoked_at           TEXT NOT NULL DEFAULT '',
    revoked_reason       TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ownership_key
    ON dataset_ownership_bindings(tenant_id, entity_mode, dataset_contract_key,
                                  scope_node_id, status);
"""


class OwnershipError(ValueError):
    """계약 위반 — 4xx 로 전달한다."""


class OwnershipIntegrityError(RuntimeError):
    """자료가 어긋났다(중첩 결속 · 없는 부서 · 색인과 결속 불일치) — **503**.

    ⚠️ 「안 보인다」와 섞지 않는다. 전자는 정상적인 비노출이고 이것은 **고쳐야 할 것**이다.
      뭉개면 아무도 고치지 않는다."""


class OwnershipUnavailable(RuntimeError):
    """정본을 읽지 못했다(저장소·조직 원장 장애) — **503**.

    ⚠️ 읽기 실패를 「결속 없음」으로 답하지 않는다. 그러면 장애가 곧 **조용한 통제 해제**가
      된다 — 저장소가 흔들리는 순간에 모든 데이터가 «소유자 없음» 이 된다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_of(tenant_id: str, entity_mode: str, dataset_contract_key: str,
                   scope_node_id: str, owner_dept_id: str,
                   effective_from: str, effective_to: str,
                   approved_by: str, evidence_ref: str) -> str:
    """결속 내용의 지문. **승인자와 근거까지 넣는다** — 같은 부서를 다른 근거로 승인한 것은
    다른 결속이다."""
    blob = json.dumps({
        "tenant_id": tenant_id, "entity_mode": entity_mode,
        "dataset_contract_key": dataset_contract_key, "scope_node_id": scope_node_id,
        "owner_dept_id": owner_dept_id,
        "effective_from": effective_from, "effective_to": effective_to,
        "approved_by": approved_by, "evidence_ref": evidence_ref,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _overlaps(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    """두 유효기간이 겹치는가. 빈 끝점은 **무기한**이다."""
    return a_from <= (b_to or _OPEN_END) and b_from <= (a_to or _OPEN_END)


def ensure_schema(conn: Any) -> None:
    conn.executescript(DDL)


def declare(conn: Any, *, tenant_id: str, entity_mode: str, dataset_contract_key: str,
            scope_node_id: str, owner_dept_id: str, approved_by: str,
            effective_from: str = "", effective_to: str = "",
            evidence_ref: str = "") -> Dict[str, Any]:
    """소유권 결속을 승인 등록한다.

    ⚠️ 승인자·근거 없이 만들 수 없다 — 「누가 왜 이 부서로 정했나」에 답할 수 없는 결속은
      나중에 아무도 뒤집을 수 없다.
    ★ **같은 지문의 재적용은 멱등이다.** 시드·마이그레이션을 두 번 돌려도 중첩이 되지 않는다.
    ⚠️⚠️ 같은 키·겹치는 기간에 다른 ACTIVE 결속이 있으면 **무결성 오류**다. 하나를 골라
      덮어쓰지 않는다 — 그 선택은 근거가 없고, 덮어쓴 쪽은 아무 기록도 남지 않는다."""
    for name, val in (("tenant_id", tenant_id), ("entity_mode", entity_mode),
                      ("dataset_contract_key", dataset_contract_key),
                      ("scope_node_id", scope_node_id), ("owner_dept_id", owner_dept_id),
                      ("approved_by", approved_by)):
        if not str(val or "").strip():
            raise OwnershipError(
                f"{name} 은 필수입니다 — 소유권 결속은 추측으로 만들 수 없습니다.")
    eff_from = str(effective_from or "").strip() or _now()
    eff_to = str(effective_to or "").strip()
    if eff_to and eff_to < eff_from:
        raise OwnershipError(f"유효기간이 뒤집혀 있습니다({eff_from} → {eff_to}).")

    fp = fingerprint_of(tenant_id, entity_mode, dataset_contract_key, scope_node_id,
                        owner_dept_id, eff_from, eff_to, approved_by, evidence_ref)
    ensure_schema(conn)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM dataset_ownership_bindings WHERE tenant_id=? AND entity_mode=? "
        "AND dataset_contract_key=? AND scope_node_id=? AND status=?",
        (tenant_id, entity_mode, dataset_contract_key, scope_node_id, ACTIVE))]
    for r in rows:
        if r["fingerprint"] == fp:
            return r                            # 멱등 — 같은 결속을 다시 적었다
        if _overlaps(eff_from, eff_to, r["effective_from"], r["effective_to"]):
            raise OwnershipIntegrityError(
                f"같은 키에 유효기간이 겹치는 ACTIVE 결속이 이미 있습니다"
                f"(기존 {r['binding_id']}: {r['owner_dept_id']} "
                f"{r['effective_from']}~{r['effective_to'] or '무기한'}). "
                f"하나를 임의로 고르지 않습니다 — 기존 결속을 먼저 철회하십시오.")

    now = _now()
    bid = f"own_{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, evidence_ref, fingerprint, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (bid, tenant_id, entity_mode, dataset_contract_key, scope_node_id, owner_dept_id,
         eff_from, eff_to, ACTIVE, approved_by, now, evidence_ref, fp, now, now))
    return {"binding_id": bid, "fingerprint": fp, "owner_dept_id": owner_dept_id,
            "status": ACTIVE, "effective_from": eff_from, "effective_to": eff_to,
            "tenant_id": tenant_id, "entity_mode": entity_mode,
            "dataset_contract_key": dataset_contract_key, "scope_node_id": scope_node_id}


def revoke(conn: Any, binding_id: str, actor: str, reason: str = "") -> bool:
    """승인을 철회한다. **행을 지우지 않는다** — 무엇이 있었는지는 남아야 한다."""
    if not str(actor or "").strip():
        raise OwnershipError("철회에도 행위자가 필요합니다.")
    ensure_schema(conn)
    now = _now()
    return conn.execute(
        "UPDATE dataset_ownership_bindings SET status=?, revoked_by=?, revoked_at=?, "
        "revoked_reason=?, updated_at=? WHERE binding_id=? AND status=?",
        (REVOKED, actor, now, str(reason or ""), now, binding_id, ACTIVE)).rowcount == 1


def _dept_alive(owner_dept_id: str) -> Tuple[bool, bool]:
    """부서가 **지금** 존재하고 살아 있는가. 돌려주는 것: `(살아있는가, 조회실패인가)`.

    ⚠️ 조회 실패를 «없다» 로도 «있다» 로도 뭉개지 않는다 — 호출부가 503 과 차단을 갈라야 한다.
    ★ 조직 미도입(부트스트랩) 환경에서는 부서가 아예 없다. 그때 이 검사를 적용하면 모든
      결속이 «없는 부서» 가 되어 통제가 아니라 고장이 된다(저장소 공통 계약)."""
    try:
        from core.org_directory import org_directory
        if org_directory.is_bootstrap():
            return True, False
        getter = getattr(org_directory, "get_department", None)
        if getter is None:
            #: 없는 API 를 «통과» 로 읽지 않는다 — 조회 실패로 본다.
            return False, True
        d = getter(owner_dept_id)
        if not d:
            return False, False
        status = (d.get("status", "active") if isinstance(d, dict)
                  else getattr(d, "status", "active"))
        return str(status) == "active", False
    except Exception:
        return False, True


def resolve(conn: Any, *, tenant_id: str, entity_mode: str, dataset_contract_key: str,
            scope_node_id: str, as_of: str = "") -> Optional[Dict[str, Any]]:
    """**정본 해석.** 결속이 없으면 `None`(→ 호출부가 `RESOURCE_UNBOUND`).

    · 정확히 하나 → 그 결속
    · 둘 이상      → `OwnershipIntegrityError`(503) — 임의로 고르지 않는다
    · 부서 미존재·폐지 → `OwnershipIntegrityError`(503) — 결속은 있는데 가리키는 곳이 없다
    · 저장소·원장 장애 → `OwnershipUnavailable`(503)

    ⚠️ `as_of` 가 비면 «지금» 이다. 과거 시점 조회는 그 시점에 유효했던 결속을 본다 —
      「지금 기준으로 과거를 판정」하면 그때의 결정을 다시 쓰는 것이 된다."""
    at = str(as_of or "").strip() or _now()
    try:
        ensure_schema(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM dataset_ownership_bindings WHERE tenant_id=? AND entity_mode=? "
            "AND dataset_contract_key=? AND scope_node_id=? AND status=?",
            (tenant_id, entity_mode, dataset_contract_key, scope_node_id, ACTIVE))]
    except (sqlite3.Error, OSError) as e:
        raise OwnershipUnavailable(f"소유권 정본을 읽지 못했습니다: {e}")

    live = [r for r in rows
            if r["effective_from"] <= at and at <= (r["effective_to"] or _OPEN_END)]
    if not live:
        return None
    if len(live) > 1:
        raise OwnershipIntegrityError(
            f"같은 키에 유효한 소유권 결속이 {len(live)}건입니다 "
            f"({[r['binding_id'] for r in live]}) — 임의로 고르지 않습니다.")
    r = live[0]
    ok, failed = _dept_alive(r["owner_dept_id"])
    if failed:
        raise OwnershipUnavailable(
            f"소유 부서({r['owner_dept_id']})가 지금 유효한지 확인할 수 없습니다.")
    if not ok:
        raise OwnershipIntegrityError(
            f"결속({r['binding_id']})이 가리키는 부서 «{r['owner_dept_id']}» 가 없거나 "
            f"폐지됐습니다 — 색인이 있어도 막습니다.")
    return r


def list_bindings(conn: Any, *, tenant_id: str = "", status: str = "") -> List[Dict[str, Any]]:
    ensure_schema(conn)
    sql = "SELECT * FROM dataset_ownership_bindings WHERE 1=1"
    args: List[Any] = []
    if tenant_id:
        sql += " AND tenant_id=?"
        args.append(tenant_id)
    if status:
        sql += " AND status=?"
        args.append(status)
    return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", args)]
