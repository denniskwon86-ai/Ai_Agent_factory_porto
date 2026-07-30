"""[M2 §2.1/§2.2] 범위 계약 쓰기 경로 — **조직 간 공유를 명시적 상태로 만든다.**

## 왜 이 모듈이 필요한가

관문 A(2026-07-30)로 "범위 미지정 = 전사 공용"이 폐기되고 미지정은 비노출이 됐다. 그런데
**전사 공용으로 전환하는 문을 만들지 않았다.** 그래서 기존 데이터 29건이 한시 예외
(`LEGACY_UNSCOPED`)로 버티는 상태가 됐고, 만료일이 지나면 그대로 사라진다.

판정(`scoping.is_visible`)은 이미 다섯 상태를 읽는다. 없는 것은 **그 상태를 만드는 경로**다:
누가 소유자인지 적고, 어느 조직에 공유하고, 누가 전사 공용을 승인했는지 남기는 일.

## 지키는 것

1. **자기 승인은 승인이 아니다.** 신청자와 승인자가 같으면 거부한다. 한 사람이 자기 데이터를
   전사에 열 수 있으면 승인 절차는 서류 작업일 뿐이다.
2. **책임 조직 없이 공유하지 않는다.** 소유 조직이 비어 있으면 공유·전사 전환을 거부한다 —
   문제가 생겼을 때 물어볼 곳이 없는 데이터를 전 조직에 뿌리는 것이 사고의 시작이다.
3. **공유 대상 없는 공유는 공유가 아니다.** `ORG_SHARED` 로 바꿀 때 대상 목록을 요구한다.
   빈 목록을 허용하면 "공유했다고 믿는 쪽"과 "소유 조직만 보는 실제"가 갈린다.
4. **`LEGACY_UNSCOPED` 는 신규에 쓸 수 없다**(§2.3-4). 이행용 표시를 새 데이터에 허용하면
   이행이 끝나지 않는다 — 한시 예외가 영구 규칙이 되는 경로가 정확히 그것이다.
5. **모든 변경은 감사에 남는다.** 범위·소유 변경은 `SCOPE_BINDING_CHANGED`, 승인은
   `APPROVAL_GRANTED`. 누가 언제 무엇을 열었는지 남지 않으면 되돌릴 근거도 없다.
6. **되돌릴 수 있다.** `revoke_sharing()` 으로 `ORG_PRIVATE` 로 되돌린다. 되돌릴 수 없는
   기능은 아무도 쓰지 않는다(사용여부 제어와 같은 판단).

LLM 0콜.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from core.enterprise_context.scoping import (ENTERPRISE_SHARED, LEGACY_UNSCOPED,
                                             NOT_FOR_NEW_ROWS, ORG_PRIVATE, ORG_SHARED,
                                             SANDBOX, SCOPE_TYPES, assigned_scopes,
                                             is_expired, owner_of)

#: 등급. 낮은 등급 사용자에게는 목록에서도 감춘다(§2.1) — 등급 판정 주체 배선은 `viewer_clearance`.
CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL")

APPROVAL_NONE = ""
APPROVAL_PENDING = "PENDING"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

#: 자원 종류 → (테이블, 기본키). 자유 문자열로 테이블명을 받지 않는다 — 그러면 이 모듈이
#: 임의 테이블 UPDATE 도구가 되고, 그 순간 SQL 주입 표면이 된다.
RESOURCES: Dict[str, tuple] = {
    "data_asset": ("data_assets", "asset_id"),
    "business_term": ("business_terms", "term_id"),
    "data_contract": ("data_contracts", "contract_id"),
    "external_system": ("external_systems", "system_id"),
}

#: 범위 계약 필드(§2.1). 조회·응답에서 이 목록을 그대로 쓴다.
CONTRACT_FIELDS = ("owner_organization_id", "enterprise_scope_id", "scope_type",
                   "scope_assignments", "classification", "effective_from", "effective_to",
                   "approval_status", "approved_by", "tenant_id", "entity_mode")


class ScopeContractError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_orgs(orgs) -> List[str]:
    """공유 대상 정규화. 중복·공백을 제거하고 **정렬**한다.

    정렬하는 이유: 저장 문자열이 입력 순서에 따라 달라지면 같은 공유 상태가 서로 다른 값으로
    저장되고, 변경 이력 비교("무엇이 바뀌었나")가 순서 차이를 변경으로 오독한다."""
    if isinstance(orgs, str):
        orgs = orgs.replace("\n", ",").split(",")
    return sorted({str(o).strip() for o in (orgs or []) if str(o).strip()})


def validate_new_scope_type(scope_type: str) -> str:
    """신규 생성에 쓸 수 있는 값인가(§2.3-4).

    ★ `LEGACY_UNSCOPED` 를 신규에 허용하면 이행이 영구히 끝나지 않는다. 새 데이터는 처음부터
      소유 조직을 적을 수 있으므로 예외가 필요할 이유가 없다."""
    st = (scope_type or ORG_PRIVATE).strip().upper()
    if st not in SCOPE_TYPES:
        raise ScopeContractError(
            f"scope_type 은 {', '.join(SCOPE_TYPES)} 중 하나여야 합니다: {scope_type}")
    if st in NOT_FOR_NEW_ROWS:
        raise ScopeContractError(
            f"'{st}' 는 관문 A 이전 데이터를 위한 **한시 이행 표시**이므로 신규 생성에는 쓸 수 "
            f"없습니다(§2.3-4). 소유 조직을 지정하고 '{ORG_PRIVATE}' 로 만드십시오 — "
            f"이행용 표시를 신규에 허용하면 이행이 끝나지 않습니다.")
    return st


class ScopeContract:
    def __init__(self, md=None):
        # 4개 표는 모두 기준정보 DB 에 있다. 연결·잠금을 재사용한다(스키마 소유는 M1).
        if md is None:
            from core.master_data import master_data
            md = master_data
        self.md = md

    # ── 내부 ──────────────────────────────────────────────────────────────
    def _table(self, resource_type: str) -> tuple:
        t = RESOURCES.get((resource_type or "").strip())
        if not t:
            raise ScopeContractError(
                f"지원하지 않는 자원 종류입니다: {resource_type} "
                f"(허용: {', '.join(RESOURCES)})")
        return t

    def _row(self, conn, resource_type: str, resource_id: str) -> Dict[str, Any]:
        table, pk = self._table(resource_type)
        r = conn.execute(f"SELECT * FROM {table} WHERE {pk}=?", (resource_id,)).fetchone()
        if not r:
            raise ScopeContractError(f"존재하지 않는 자원입니다: {resource_type}/{resource_id}")
        return dict(r)

    def _update(self, resource_type: str, resource_id: str, changes: Dict[str, Any],
                actor: str, event: str, reason: str) -> Dict[str, Any]:
        """변경을 적용하고 **감사에 남긴다.** 기록 없는 권한 변경은 되돌릴 근거가 없다."""
        table, pk = self._table(resource_type)
        with self.md._lock, self.md._connect() as conn:
            conn.row_factory = sqlite3.Row
            before = self._row(conn, resource_type, resource_id)
            missing = [c for c in changes if c not in before]
            if missing:
                # 컬럼이 없으면 조용히 무시되어 "설정했는데 안 걸린다"가 된다.
                raise ScopeContractError(
                    f"{table} 에 범위 계약 컬럼이 없습니다: {', '.join(missing)}. "
                    f"기준정보 DB 마이그레이션(`MasterData._migrate_columns`)이 필요합니다.")
            sets = ", ".join(f"{c}=?" for c in changes)
            conn.execute(f"UPDATE {table} SET {sets} WHERE {pk}=?",
                         (*changes.values(), resource_id))
            after = self._row(conn, resource_type, resource_id)
        self._audit(event, resource_type, resource_id, actor, before, after, reason)
        return self.contract(resource_type, resource_id)

    @staticmethod
    def _audit(event: str, resource_type: str, resource_id: str, actor: str,
               before: Dict[str, Any], after: Dict[str, Any], reason: str) -> None:
        try:
            from core.enterprise_context import audit
            diff = "; ".join(
                f"{f}: {before.get(f, '')!r}→{after.get(f, '')!r}"
                for f in CONTRACT_FIELDS if before.get(f, "") != after.get(f, ""))
            audit.record(event, resource_type=resource_type, resource_id=resource_id,
                         actor=actor or audit.ANONYMOUS, outcome="allowed",
                         reason=reason or "", detail=diff)
        except Exception as e:                                       # pragma: no cover
            # 감사 실패가 요청을 죽이지는 않지만(§3.2-3) 조용히 넘기지도 않는다.
            print(f"⚠️ [scope_contract] 감사 기록 실패: {e}")

    # ── 조회 ──────────────────────────────────────────────────────────────
    def contract(self, resource_type: str, resource_id: str) -> Dict[str, Any]:
        """이 자원의 범위 계약 + **지금 어떻게 보이는지에 대한 설명.**

        ★ 값만 주면 "왜 안 보이는지"를 사람이 조립해야 한다. 그 조립을 사람에게 맡기면
          `ORG_SHARED` 인데 대상이 비어 있는 상태 같은 것을 아무도 눈치채지 못한다."""
        with self.md._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = self._row(conn, resource_type, resource_id)
        st = (row.get("scope_type") or "").strip().upper() or ORG_PRIVATE
        out = {"resource_type": resource_type, "resource_id": resource_id,
               "scope_type_effective": st}
        for f in CONTRACT_FIELDS:
            out[f] = row.get(f, "")
        out["assignments"] = sorted(assigned_scopes(row))
        out["owner"] = owner_of(row)
        out["expired"] = is_expired(row) if st == LEGACY_UNSCOPED else False
        out["visibility"] = self._explain(st, row, out)
        return out

    @staticmethod
    def _explain(st: str, row: Dict[str, Any], out: Dict[str, Any]) -> str:
        owner = out["owner"]
        if st == ENTERPRISE_SHARED:
            if (row.get("approval_status") or "").upper() == APPROVAL_APPROVED and \
                    (row.get("approved_by") or "").strip():
                return f"전 조직에서 보입니다(승인자: {row.get('approved_by')})."
            return ("⚠️ 전사 공용으로 표시됐으나 **승인 이력이 없어 아무에게도 보이지 않습니다** — "
                    "승인 없는 전사 공용을 통과시키면 승인 절차가 장식이 되기 때문입니다.")
        if st == ORG_SHARED:
            if not out["assignments"]:
                return ("⚠️ 조직 공유로 표시됐으나 **공유 대상이 비어** 소유 조직만 봅니다 — "
                        "공유했다고 믿는 쪽과 실제 동작이 갈립니다.")
            return (f"소유 조직({owner or '미지정'}) + 공유 대상 "
                    f"{', '.join(out['assignments'])} 에서 보입니다.")
        if st == SANDBOX:
            return ("가상 문맥 전용입니다. capability token 검증 경로가 붙기 전까지는 "
                    "일반 조회에서 보이지 않습니다(fail-closed).")
        if st == LEGACY_UNSCOPED:
            if out["expired"]:
                return ("⚠️ 한시 예외가 **만료되어 보이지 않습니다** — 소유 조직을 지정하거나 "
                        "승인된 전사 공용으로 전환하십시오.")
            return (f"한시 예외로 전 조직에서 보입니다(만료: "
                    f"{(row.get('effective_to') or '기본 만료일')}). 만료 후에는 비노출입니다.")
        if not owner:
            return ("소유 조직이 비어 있어 **아무에게도 보이지 않습니다**(관문 A · fail-closed). "
                    "빈 값은 설정 누락이지 공유 의사가 아닙니다.")
        return f"소유 조직({owner}) 과 그 하위 조직에서 보입니다."

    # ── 소유 ──────────────────────────────────────────────────────────────
    def set_owner(self, resource_type: str, resource_id: str, owner_organization_id: str,
                  actor: str, reason: str = "") -> Dict[str, Any]:
        """책임 조직을 지정한다. **모든 공유의 전제**다."""
        if not (actor or "").strip():
            raise ScopeContractError("actor 는 필수입니다 — 누가 바꿨는지 없는 권한 변경은 "
                                     "감사 대상이 될 수 없습니다.")
        if not (owner_organization_id or "").strip():
            raise ScopeContractError(
                "소유 조직을 빈 값으로 둘 수 없습니다 — 관문 A 이후 빈 소유는 '전사 공용'이 "
                "아니라 '아무에게도 보이지 않음'입니다. 지우려면 공유를 회수하십시오.")
        return self._update(resource_type, resource_id,
                            {"owner_organization_id": owner_organization_id.strip()},
                            actor, self._event_scope(), reason or "소유 조직 지정")

    # ── 조직 간 공유 (ORG_SHARED) ─────────────────────────────────────────
    def share_with(self, resource_type: str, resource_id: str, organizations: Iterable[str],
                   actor: str, reason: str = "") -> Dict[str, Any]:
        """지정한 조직들에 공유한다(§2.2 `ORG_SHARED`).

        ⚠️ 대상 목록을 요구한다 — 빈 목록으로 `ORG_SHARED` 를 만들면 소유 조직만 보게 되는데
          화면에는 "공유됨"으로 표시되어, 공유했다고 믿는 쪽과 실제가 갈린다."""
        orgs = _norm_orgs(organizations)
        if not orgs:
            raise ScopeContractError(
                "공유 대상 조직을 지정하십시오 — 대상 없는 공유는 공유가 아니고, 화면에만 "
                "'공유됨'으로 남아 실제와 갈립니다.")
        with self.md._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = self._row(conn, resource_type, resource_id)
        owner = owner_of(row)
        if not owner:
            raise ScopeContractError(
                "소유 조직을 먼저 지정하십시오 — 책임 조직 없는 데이터를 공유하면 문제가 생겼을 "
                "때 물어볼 곳이 없습니다.")
        if owner in orgs:
            # 소유 조직은 이미 본다. 목록에 남겨 두면 "공유 대상 3곳"이 실제로는 2곳이 된다.
            orgs = [o for o in orgs if o != owner]
            if not orgs:
                raise ScopeContractError(
                    "소유 조직 자신에게만 공유할 수는 없습니다 — 이미 보이는 상태입니다.")
        return self._update(resource_type, resource_id,
                            {"scope_type": ORG_SHARED,
                             "scope_assignments": ",".join(orgs)},
                            actor, self._event_scope(),
                            reason or f"조직 공유: {', '.join(orgs)}")

    def revoke_sharing(self, resource_type: str, resource_id: str, actor: str,
                       reason: str = "") -> Dict[str, Any]:
        """공유를 회수해 `ORG_PRIVATE` 로 되돌린다.

        ★ 되돌릴 수 있어야 사람들이 공유를 겁내지 않는다. 승인 이력도 함께 비운다 — 회수 후에
          남은 승인 기록은 "승인됐으니 다시 열어도 된다"는 잘못된 근거가 된다."""
        return self._update(resource_type, resource_id,
                            {"scope_type": ORG_PRIVATE, "scope_assignments": "",
                             "approval_status": APPROVAL_NONE, "approved_by": ""},
                            actor, self._event_scope(), reason or "공유 회수")

    # ── 전사 공용 (ENTERPRISE_SHARED) ─────────────────────────────────────
    def request_enterprise_shared(self, resource_type: str, resource_id: str, actor: str,
                                  reason: str = "") -> Dict[str, Any]:
        """전사 공용 전환을 **신청**한다. 신청만으로는 보이지 않는다."""
        if not (actor or "").strip():
            raise ScopeContractError("actor 는 필수입니다 — 신청자를 모르면 자기 승인을 막을 "
                                     "수 없습니다.")
        with self.md._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = self._row(conn, resource_type, resource_id)
        if not owner_of(row):
            raise ScopeContractError(
                "소유 조직을 먼저 지정하십시오 — 전사 공용은 책임 조직을 지우는 것이 아니라 "
                "'책임은 그대로 두고 열람 범위만 넓히는' 조치입니다.")
        return self._update(resource_type, resource_id,
                            # 신청자를 `approved_by` 에 넣지 않는다 — 넣으면 신청이 곧 승인이 된다.
                            {"scope_type": ENTERPRISE_SHARED,
                             "approval_status": APPROVAL_PENDING, "approved_by": "",
                             "effective_from": _now()[:10]},
                            actor, self._event_scope(),
                            # 표지를 **항상** 앞에 붙인다. 호출자의 사유가 표지를 밀어내면
                            #   신청 기록을 찾을 수 없게 된다(실측으로 확인한 결함).
                            f"전사 공용 신청(신청자: {actor})"
                            + (f" — {reason}" if reason else ""))

    def approve_enterprise_shared(self, resource_type: str, resource_id: str, approver: str,
                                  reason: str = "", requested_by: str = "") -> Dict[str, Any]:
        """전사 공용을 **승인**한다 — 이 순간부터 전 조직에서 보인다.

        ⚠️ 신청자와 승인자가 같으면 거부한다. 한 사람이 자기 데이터를 전사에 열 수 있으면
          승인은 절차가 아니라 서류 작업이다. 신청자 확인은 감사로그가 진실원본이므로,
          호출자가 알려주지 않으면 거기서 찾는다."""
        if not (approver or "").strip():
            raise ScopeContractError("승인자 식별 정보가 없습니다 — 누가 승인했는지 없는 승인은 "
                                     "감사에서 근거가 되지 못합니다.")
        with self.md._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = self._row(conn, resource_type, resource_id)
        st = (row.get("scope_type") or "").strip().upper()
        if st != ENTERPRISE_SHARED:
            raise ScopeContractError(
                f"전사 공용 신청 상태가 아닙니다(현재: {st or '미지정'}). "
                f"먼저 신청하십시오 — 신청 없는 승인은 무엇을 승인했는지 알 수 없습니다.")
        requester = (requested_by or "").strip() or self._find_requester(
            resource_type, resource_id)
        if requester and requester == approver.strip():
            raise ScopeContractError(
                f"신청자와 승인자가 같습니다({approver}) — 자기 승인은 승인이 아닙니다. "
                f"다른 승인 권한자가 승인해야 합니다.")
        out = self._update(resource_type, resource_id,
                           {"approval_status": APPROVAL_APPROVED,
                            "approved_by": approver.strip()},
                           approver, self._event_approval(),
                           reason or f"전사 공용 승인(신청자: {requester or '미확인'})")
        return out

    def reject_enterprise_shared(self, resource_type: str, resource_id: str, approver: str,
                                 reason: str) -> Dict[str, Any]:
        """전사 공용 신청을 반려한다. 반려는 `ORG_PRIVATE` 로 되돌리는 것과 같다 —
        `ENTERPRISE_SHARED` + 미승인 상태로 남겨 두면 화면에 '전사 공용'으로 보인다."""
        if not (reason or "").strip():
            raise ScopeContractError(
                "반려 사유는 필수입니다 — 사유 없는 반려는 신청자가 무엇을 고쳐야 하는지 "
                "알 수 없게 만들고, 결국 같은 신청이 반복됩니다.")
        return self._update(resource_type, resource_id,
                            {"scope_type": ORG_PRIVATE,
                             "approval_status": APPROVAL_REJECTED, "approved_by": ""},
                            approver, self._event_approval(), f"전사 공용 반려: {reason}")

    def _find_requester(self, resource_type: str, resource_id: str) -> str:
        """감사로그에서 이 자원의 마지막 전사 공용 신청자를 찾는다.

        ★ 신청자를 별도 컬럼에 두지 않은 이유: 그러면 감사로그와 두 곳에 같은 사실이 남고,
          두 곳은 어긋난다. 감사로그가 진실원본이다(append-only).

        ⚠️ **[2026-07-30 브라우저 실측으로 잡은 결함]** 처음에는 사유 문구
          ("전사 공용 신청")로 찾았다. 그런데 호출자가 `reason` 을 주면 그 문구가 사라져
          신청자를 못 찾고, **자기 승인이 그대로 통과했다**(API 로 확인: 200). 단위 테스트는
          사유 없이 호출해서 통과했다 — 사람이 쓰는 자유 텍스트에 보안 판정을 걸면 그 판정은
          문구가 바뀌는 순간 사라진다.
          → 이제 **구조적 신호**로 찾는다: 이 자원의 `approval_status` 를 `PENDING` 으로 바꾼
            변경 이벤트(diff 는 감사 `detail` 에 남는다). 문구가 무엇이든 상태 전이는 남는다."""
        try:
            from core.enterprise_context import audit
            for e in audit.recent(limit=500):
                if (e.get("resource_id") != resource_id
                        or e.get("resource_type") != resource_type):
                    continue
                detail = e.get("detail") or ""
                if "approval_status" in detail and f"'{APPROVAL_PENDING}'" in detail:
                    return e.get("actor") or ""
                # 하위호환: 예전 기록은 사유 문구만 갖고 있다.
                if "전사 공용 신청" in (e.get("reason") or ""):
                    return e.get("actor") or ""
        except Exception as e:
            print(f"⚠️ [scope_contract] 신청자 조회 실패(자기 승인 검사 불가): {e}")
        return ""

    # ── 한시 예외 이행 ────────────────────────────────────────────────────
    def legacy_pending(self, resource_type: str = "") -> Dict[str, Any]:
        """한시 예외로 버티는 자원 목록 — **만료 전에 정리해야 하는 일감**이다.

        ★ 이 목록이 없으면 만료일에 데이터가 한꺼번에 사라진다. "언제까지 봐주는가"를 아는 것과
          "무엇을 정리해야 하는가"를 아는 것은 다르고, 사람은 후자로만 움직인다."""
        from core.enterprise_context.scoping import LEGACY_GRANDFATHER_UNTIL
        types = [resource_type] if resource_type else list(RESOURCES)
        items: List[Dict[str, Any]] = []
        for rt in types:
            table, pk = self._table(rt)
            try:
                with self.md._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    rows = [dict(r) for r in conn.execute(
                        f"SELECT * FROM {table} WHERE scope_type=?", (LEGACY_UNSCOPED,))]
            except sqlite3.Error as e:
                print(f"⚠️ [scope_contract] {table} 조회 실패: {e}")
                continue
            for r in rows:
                items.append({
                    "resource_type": rt, "resource_id": r.get(pk, ""),
                    "name": r.get("name") or r.get("canonical_name") or r.get(pk, ""),
                    "deadline": (r.get("effective_to") or "").strip() or LEGACY_GRANDFATHER_UNTIL,
                    "expired": is_expired(r),
                })
        items.sort(key=lambda i: (not i["expired"], i["deadline"]))
        expired = [i for i in items if i["expired"]]
        return {
            "total": len(items), "expired": len(expired), "items": items,
            "default_deadline": LEGACY_GRANDFATHER_UNTIL,
            "note": ("한시 예외는 관문 A 이전 데이터를 위한 **이행 상태**입니다. 만료 후에는 "
                     "비노출이므로, 만료 전에 소유 조직을 지정(`set_owner`)하거나 승인된 전사 "
                     "공용으로 전환하십시오."
                     + (f" ⚠️ **{len(expired)}건은 이미 만료되어 보이지 않습니다.**"
                        if expired else "")),
        }

    def adopt_legacy(self, resource_type: str, resource_id: str,
                     owner_organization_id: str, actor: str,
                     reason: str = "") -> Dict[str, Any]:
        """한시 예외를 정상 상태로 **이행**한다 — 소유 조직을 적고 `ORG_PRIVATE` 로 내린다.

        ⚠️ 이 조치는 가시성을 **좁힌다**(전 조직 → 소유 조직 + 하위). 그것이 관문 A 의 의도이며,
          응답에 그 사실을 적어 "정리했더니 안 보인다"는 놀람을 없앤다."""
        if not (owner_organization_id or "").strip():
            raise ScopeContractError(
                "소유 조직이 필요합니다 — 한시 예외를 푸는 것은 '책임 조직을 적는 일'입니다.")
        out = self._update(resource_type, resource_id,
                           {"owner_organization_id": owner_organization_id.strip(),
                            "scope_type": ORG_PRIVATE, "effective_to": ""},
                           actor, self._event_scope(),
                           reason or f"한시 예외 이행 → 소유 조직 {owner_organization_id}")
        out["note"] = ("한시 예외를 해제했습니다. 이제 이 자원은 **소유 조직과 그 하위에서만** "
                       "보입니다 — 다른 조직도 봐야 한다면 `share_with`(조직 공유) 또는 승인된 "
                       "전사 공용으로 전환하십시오.")
        return out

    # ── 감사 이벤트 이름(모듈 임포트 실패에도 죽지 않게 분리) ─────────────
    @staticmethod
    def _event_scope() -> str:
        try:
            from core.enterprise_context import audit
            return audit.SCOPE_BINDING_CHANGED
        except Exception:                                            # pragma: no cover
            return "SCOPE_BINDING_CHANGED"

    @staticmethod
    def _event_approval() -> str:
        try:
            from core.enterprise_context import audit
            return audit.APPROVAL_GRANTED
        except Exception:                                            # pragma: no cover
            return "APPROVAL_GRANTED"


scope_contract = ScopeContract()
