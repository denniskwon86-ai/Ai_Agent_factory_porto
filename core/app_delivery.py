"""[CL-1] 개인 앱 전달·수락·내 앱 주머니 — **수락은 권한을 넓히지 않는다.**

## 이 모듈이 지키는 다섯 가지 (작업서 §3·§CL-BE-02)

1. **개인 전달은 조직 공유·업무 배정·전사 승격과 다른 것이다.** 여기서 만든 상태는
   `workspace_shares` 나 Promotion 에 섞이지 않는다. 네 가지를 한 enum 으로 만들면 "이 사람이
   왜 이걸 볼 수 있나"에 답할 수 없게 된다.
2. ★★★ **수락만으로 수신자의 데이터 접근 범위가 늘지 않는다.** 앱을 받는 것과 데이터를 볼 수
   있는 것은 별개다. 앱은 호스트 권한으로 돌므로, 수신자가 원래 못 보던 데이터는 앱을 통해서도
   보이지 않는다. 이 규칙이 무너지면 앱 전달이 **권한 우회 경로**가 된다.
3. **남의 것은 404 로 은폐한다**(§3-10). 403 은 "있지만 못 본다"를 알려주므로 존재가 새어나간다.
   인증 실패(401)와 요청 형식 오류(422)는 그대로 구분한다.
4. **같은 idempotency key 는 한 건이다.** 중복 클릭·재시도로 전달이 두 개 생기면 수신자는 같은
   앱을 두 번 수락하게 되고, 어느 것이 유효한지 아무도 모른다.
5. **자체 인증을 가진 앱은 전달되지 않는다.** CL-0 의 정적 검사 결과를 전달 시점에 확인한다 —
   게시 때 막지 않은 이유는 이미 만든 산출물을 지우면 다음 사람이 검사를 끄기 때문이다.
   전달은 사람에게 넘기는 행위이므로 여기가 차단 지점이다.

## 만료

전달에는 만료가 있다. ⚠️ 만료 없는 대기 요청은 영구히 남아 "받은 앱"을 채우고, 결국 아무도
읽지 않는 목록이 된다(이 저장소가 '한시 예외'에서 겪은 것과 같은 유형). 만료는 **읽는 시점에
판정**하고 상태를 덮어쓰지 않는다 — 배치가 없어도 정확해야 한다.

LLM 0콜.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.collaboration_events import (APP_DELIVERY_RECEIVED, APP_DELIVERY_UPDATED,
                                       collaboration_events)
from core.collaboration_store import (CollaborationStoreError, canonical_json,
                                      collaboration_store, now_iso, snapshot_hash)

PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"
REVOKED = "REVOKED"
STATUSES = (PENDING, ACCEPTED, REJECTED, EXPIRED, REVOKED)

#: 기본 만료(일). 짧게 두는 것이 요점이다 — 길면 대기 목록이 쌓이고 아무도 읽지 않는다.
DEFAULT_EXPIRY_DAYS = 14
MAX_EXPIRY_DAYS = 90


class AppDeliveryError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


class NotFoundOrHidden(LookupError):
    """없거나, 있어도 보여줄 수 없다 — 라우트가 **404** 로 바꾼다.

    ★ 두 경우를 한 예외로 묶는 것이 의도다. 호출부가 구분할 수 있으면 응답도 갈라지고,
      그 차이로 남의 자원의 존재가 새어나간다."""


class AppDelivery:
    def __init__(self, store=None, ledger=None):
        self._store_override = store
        self._ledger_override = ledger

    @property
    def _store(self):
        return self._store_override or collaboration_store

    @property
    def _ledger(self):
        if self._ledger_override is not None:
            return self._ledger_override
        from core.decision_ledger import decision_ledger
        return decision_ledger

    # ── 생성 ──────────────────────────────────────────────────────────────
    def create(self, release_id: str, sender_user_id: str, recipient_user_id: str,
               purpose: str = "", expires_in_days: int = DEFAULT_EXPIRY_DAYS,
               idempotency_key: str = "", tenant_id: str = "tenant_default",
               enterprise_scope_id: str = "", release_lookup=None,
               permission_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """전달 요청을 만든다.

        `release_lookup(release_id) -> dict|None` 로 릴리스를 읽는다(기본은 `library/`).
        ⚠️ 릴리스를 못 읽으면 만들지 않는다 — 존재하지 않는 앱을 전달하면 수신자는 수락할 수
          없는 요청을 받는다."""
        if not (release_id or "").strip():
            raise AppDeliveryError("release_id 는 필수입니다.")
        if not (sender_user_id or "").strip():
            raise AppDeliveryError("보내는 사람(sender_user_id)이 필요합니다.")
        if not (recipient_user_id or "").strip():
            raise AppDeliveryError("받는 사람(recipient_user_id)이 필요합니다.")
        if sender_user_id == recipient_user_id:
            # 자기에게 보내는 전달은 상태만 늘리고 아무 것도 바꾸지 않는다.
            raise AppDeliveryError("자기 자신에게는 전달할 수 없습니다.")
        if not (purpose or "").strip():
            raise AppDeliveryError(
                "전달 목적(purpose)은 필수입니다 — 목적 없는 앱을 받은 사람은 수락 여부를 "
                "판단할 근거가 없습니다.")
        try:
            days = int(expires_in_days)
        except (TypeError, ValueError):
            raise AppDeliveryError(f"expires_in_days 는 숫자여야 합니다: {expires_in_days}")
        if days <= 0 or days > MAX_EXPIRY_DAYS:
            raise AppDeliveryError(
                f"만료는 1~{MAX_EXPIRY_DAYS}일이어야 합니다({days} 요청) — 만료 없는 대기 요청은 "
                f"영구히 남아 목록을 채우고, 결국 아무도 읽지 않습니다.")

        lookup = release_lookup or _default_release_lookup
        rel = lookup(release_id)
        if not rel:
            raise NotFoundOrHidden(release_id)

        # ★ CL-0 정적 검사 결과를 **여기서** 확인한다(게시 때가 아니라 전달 때).
        scan = rel.get("platform_auth_scan") or {}
        if scan.get("ok") is False:
            n = (scan.get("summary") or {}).get("blocking", "?")
            raise AppDeliveryError(
                f"이 앱에는 자체 인증 코드가 {n}건 있어 전달할 수 없습니다 — 앱은 호스트 인증을 "
                f"상속해야 합니다. 로그인 화면 대신 현재 사용자·조직·역할을 표시하도록 고친 뒤 "
                f"다시 게시하십시오.")
        man = rel.get("manifest") or {}
        if man.get("valid") is False:
            raise AppDeliveryError(
                f"이 앱의 Capability Manifest 가 유효하지 않아 전달할 수 없습니다: "
                f"{man.get('errors')} — 수신자가 무엇을 수락하는지 알 수 없습니다.")

        key = (idempotency_key or "").strip()
        if key:
            prior = self._store.one(
                "SELECT * FROM app_deliveries WHERE tenant_id=? AND sender_user_id=? "
                "AND idempotency_key=?", (tenant_id, sender_user_id, key))
            if prior:
                # 같은 키의 재시도 — **같은 결과**를 준다(새로 만들지 않는다).
                return self._view(prior, viewer_user_id=sender_user_id, replayed=True)

        did = f"del_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
        snap = man.get("manifest") or {}
        perm = permission_snapshot or {}
        row = {
            "delivery_id": did, "tenant_id": tenant_id,
            "enterprise_scope_id": enterprise_scope_id or "",
            "release_id": release_id,
            "release_version": str(rel.get("version") or rel.get("release_version") or ""),
            "sender_user_id": sender_user_id, "recipient_user_id": recipient_user_id,
            "purpose": purpose.strip(), "status": PENDING, "expires_at": expires_at,
            "manifest_snapshot": canonical_json(snap),
            "manifest_fingerprint": str(man.get("fingerprint") or ""),
            "permission_snapshot": canonical_json(perm),
            "idempotency_key": key, "responded_at": "", "response_note": "",
            "created_at": now, "updated_at": now,
        }
        try:
            self._store.execute(
                "INSERT INTO app_deliveries (delivery_id, tenant_id, enterprise_scope_id, "
                "release_id, release_version, sender_user_id, recipient_user_id, purpose, "
                "status, expires_at, manifest_snapshot, manifest_fingerprint, "
                "permission_snapshot, idempotency_key, responded_at, response_note, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[k] for k in (
                    "delivery_id", "tenant_id", "enterprise_scope_id", "release_id",
                    "release_version", "sender_user_id", "recipient_user_id", "purpose",
                    "status", "expires_at", "manifest_snapshot", "manifest_fingerprint",
                    "permission_snapshot", "idempotency_key", "responded_at",
                    "response_note", "created_at", "updated_at")))
        except Exception as e:
            if "UNIQUE" in str(e).upper() and key:
                prior = self._store.one(
                    "SELECT * FROM app_deliveries WHERE tenant_id=? AND sender_user_id=? "
                    "AND idempotency_key=?", (tenant_id, sender_user_id, key))
                if prior:
                    return self._view(prior, viewer_user_id=sender_user_id, replayed=True)
            raise
        self._ledger_append("APP_DELIVERY_CREATED", did, sender_user_id,
                            decision=f"{recipient_user_id} 에게 {release_id} 전달 요청",
                            rationale=purpose.strip(),
                            evidence=[{"release_id": release_id,
                                       "manifest_fingerprint": row["manifest_fingerprint"]}],
                            tenant_id=tenant_id, scope=enterprise_scope_id)
        out = self._view(row, viewer_user_id=sender_user_id)
        # [CL-4] **보낸 사람과 받는 사람 둘에게만.** 부서 전체가 아니다.
        self._notify(APP_DELIVERY_RECEIVED, out, sender_user_id)
        return out

    # ── 응답 ──────────────────────────────────────────────────────────────
    def accept(self, delivery_id: str, user_id: str, display_name: str = "",
               today: str = "") -> Dict[str, Any]:
        """수신자가 수락한다. **재호출은 같은 결과를 주고 주머니를 중복 생성하지 않는다.**

        ⚠️ 수락은 데이터 권한을 넓히지 않는다. 이 함수는 주머니에 앱을 넣을 뿐이고, 권한은
          실행 시점에 호스트가 다시 판정한다 — 그것이 App-in-App 계약이다."""
        row = self._require_for_recipient(delivery_id, user_id)
        eff = self._effective_status(row, today)
        if eff == ACCEPTED:
            pocket = self._store.one(
                "SELECT * FROM user_app_pocket WHERE user_id=? AND release_id=? AND delivery_id=?",
                (user_id, row["release_id"], delivery_id))
            out = self._view(row, viewer_user_id=user_id, replayed=True)
            out["pocket"] = pocket
            return out
        if eff != PENDING:
            raise AppDeliveryError(
                f"이미 {eff} 상태인 요청은 수락할 수 없습니다 — "
                f"{'만료됐습니다.' if eff == EXPIRED else '보낸 사람이 회수했거나 이미 응답했습니다.'}")

        now = now_iso()
        pid = f"pkt_{uuid.uuid4().hex[:12]}"
        name = (display_name or "").strip() or row["release_id"]
        # ★ 상태 변경과 주머니 생성은 **하나의 트랜잭션**이다 — 하나만 남으면 "수락했는데 앱이
        #   없다" 또는 "앱이 있는데 수락 기록이 없다"가 된다.
        self._store.executemany_tx([
            ("UPDATE app_deliveries SET status=?, responded_at=?, updated_at=? "
             "WHERE delivery_id=? AND status=?", (ACCEPTED, now, now, delivery_id, PENDING)),
            ("INSERT OR IGNORE INTO user_app_pocket (pocket_id, tenant_id, "
             "enterprise_scope_id, user_id, release_id, delivery_id, display_name, status, "
             "pinned, accepted_at, last_opened_at, created_at, updated_at) "
             "VALUES (?,?,?,?,?,?,?,'ACTIVE',0,?,'',?,?)",
             (pid, row["tenant_id"], row["enterprise_scope_id"], user_id, row["release_id"],
              delivery_id, name, now, now, now)),
        ])
        self._ledger_append("APP_DELIVERY_ACCEPTED", delivery_id, user_id,
                            decision=f"{row['release_id']} 수락",
                            rationale="수신자 수락 — 데이터 접근 범위는 변경되지 않는다",
                            evidence=[{"manifest_fingerprint": row["manifest_fingerprint"]}],
                            tenant_id=row["tenant_id"], scope=row["enterprise_scope_id"])
        fresh = self._store.one("SELECT * FROM app_deliveries WHERE delivery_id=?",
                                (delivery_id,))
        out = self._view(fresh, viewer_user_id=user_id)
        out["pocket"] = self._store.one(
            "SELECT * FROM user_app_pocket WHERE user_id=? AND release_id=? AND delivery_id=?",
            (user_id, row["release_id"], delivery_id))
        out["scope_unchanged"] = True
        out["scope_note"] = ("앱을 받았을 뿐 데이터 접근 범위는 넓어지지 않았습니다 — 앱은 "
                             "호스트 권한으로 실행되며, 원래 보이지 않던 자료는 앱에서도 "
                             "보이지 않습니다.")
        self._notify(APP_DELIVERY_UPDATED, out, user_id)
        return out

    def reject(self, delivery_id: str, user_id: str, note: str = "",
               today: str = "") -> Dict[str, Any]:
        row = self._require_for_recipient(delivery_id, user_id)
        eff = self._effective_status(row, today)
        if eff == REJECTED:
            return self._view(row, viewer_user_id=user_id, replayed=True)
        if eff != PENDING:
            raise AppDeliveryError(f"이미 {eff} 상태인 요청은 거절할 수 없습니다.")
        now = now_iso()
        self._store.execute(
            "UPDATE app_deliveries SET status=?, responded_at=?, response_note=?, updated_at=? "
            "WHERE delivery_id=? AND status=?",
            (REJECTED, now, (note or "").strip(), now, delivery_id, PENDING))
        self._ledger_append("APP_DELIVERY_REJECTED", delivery_id, user_id,
                            decision=f"{row['release_id']} 거절",
                            rationale=(note or "").strip() or "(사유 없음)",
                            tenant_id=row["tenant_id"], scope=row["enterprise_scope_id"])
        out = self._view(self._store.one(
            "SELECT * FROM app_deliveries WHERE delivery_id=?", (delivery_id,)),
            viewer_user_id=user_id)
        self._notify(APP_DELIVERY_UPDATED, out, user_id)
        return out

    def revoke(self, delivery_id: str, user_id: str, reason: str = "",
               today: str = "") -> Dict[str, Any]:
        """보낸 사람이 회수한다. **이미 수락된 것은 회수로 지우지 않는다.**

        ⚠️ 수락된 앱을 조용히 사라지게 하면 수신자는 자기 주머니에서 앱이 없어진 이유를 알 수
          없다. 수락 이후의 회수는 주머니 상태를 `REVOKED` 로 표시하고 이유를 남긴다."""
        row = self._require_for_sender(delivery_id, user_id)
        eff = self._effective_status(row, today)
        if eff == REVOKED:
            return self._view(row, viewer_user_id=user_id, replayed=True)
        now = now_iso()
        stmts = [("UPDATE app_deliveries SET status=?, updated_at=?, response_note=? "
                  "WHERE delivery_id=?",
                  (REVOKED, now, (reason or "").strip(), delivery_id))]
        if eff == ACCEPTED:
            stmts.append(("UPDATE user_app_pocket SET status='REVOKED', updated_at=? "
                          "WHERE delivery_id=?", (now, delivery_id)))
        self._store.executemany_tx(stmts)
        self._ledger_append("APP_DELIVERY_REVOKED", delivery_id, user_id,
                            decision=f"{row['release_id']} 전달 회수",
                            rationale=(reason or "").strip() or "(사유 없음)",
                            tenant_id=row["tenant_id"], scope=row["enterprise_scope_id"])
        out = self._view(self._store.one(
            "SELECT * FROM app_deliveries WHERE delivery_id=?", (delivery_id,)),
            viewer_user_id=user_id)
        self._notify(APP_DELIVERY_UPDATED, out, user_id)
        return out

    # ── 조회 ──────────────────────────────────────────────────────────────
    def inbox(self, user_id: str, today: str = "",
              include_responded: bool = True) -> List[Dict[str, Any]]:
        """받은 요청. **본인 것만** 돌려준다."""
        rows = self._store.query(
            "SELECT * FROM app_deliveries WHERE recipient_user_id=? ORDER BY created_at DESC",
            (user_id,))
        out = [self._view(r, viewer_user_id=user_id, today=today) for r in rows]
        if not include_responded:
            out = [d for d in out if d["status"] == PENDING]
        return out

    def outbox(self, user_id: str, today: str = "") -> List[Dict[str, Any]]:
        rows = self._store.query(
            "SELECT * FROM app_deliveries WHERE sender_user_id=? ORDER BY created_at DESC",
            (user_id,))
        return [self._view(r, viewer_user_id=user_id, today=today) for r in rows]

    def get(self, delivery_id: str, user_id: str, today: str = "") -> Dict[str, Any]:
        """상세. **당사자가 아니면 404**(존재를 알리지 않는다)."""
        row = self._store.one("SELECT * FROM app_deliveries WHERE delivery_id=?",
                              (delivery_id,))
        if not row or user_id not in (row["sender_user_id"], row["recipient_user_id"]):
            raise NotFoundOrHidden(delivery_id)
        return self._view(row, viewer_user_id=user_id, today=today)

    def my_apps(self, user_id: str, include_revoked: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM user_app_pocket WHERE user_id=?"
        params: tuple = (user_id,)
        if not include_revoked:
            sql += " AND status='ACTIVE'"
        rows = self._store.query(sql + " ORDER BY pinned DESC, updated_at DESC", params)
        return rows

    def update_pocket(self, pocket_id: str, user_id: str, display_name: Optional[str] = None,
                      pinned: Optional[bool] = None,
                      mark_opened: bool = False) -> Dict[str, Any]:
        row = self._store.one("SELECT * FROM user_app_pocket WHERE pocket_id=?", (pocket_id,))
        if not row or row["user_id"] != user_id:
            raise NotFoundOrHidden(pocket_id)
        sets, params = [], []
        if display_name is not None:
            if not display_name.strip():
                raise AppDeliveryError("display_name 은 비울 수 없습니다.")
            sets.append("display_name=?"); params.append(display_name.strip())
        if pinned is not None:
            sets.append("pinned=?"); params.append(1 if pinned else 0)
        if mark_opened:
            sets.append("last_opened_at=?"); params.append(now_iso())
        if not sets:
            return row
        sets.append("updated_at=?"); params.append(now_iso())
        params.append(pocket_id)
        self._store.execute(f"UPDATE user_app_pocket SET {', '.join(sets)} WHERE pocket_id=?",
                            tuple(params))
        return self._store.one("SELECT * FROM user_app_pocket WHERE pocket_id=?", (pocket_id,))

    # ── 공통 ──────────────────────────────────────────────────────────────
    def _require_for_recipient(self, delivery_id: str, user_id: str) -> Dict[str, Any]:
        row = self._store.one("SELECT * FROM app_deliveries WHERE delivery_id=?",
                              (delivery_id,))
        if not row or row["recipient_user_id"] != user_id:
            # 남의 요청을 수락·거절하려는 시도 — 존재를 알리지 않는다.
            raise NotFoundOrHidden(delivery_id)
        return row

    def _require_for_sender(self, delivery_id: str, user_id: str) -> Dict[str, Any]:
        row = self._store.one("SELECT * FROM app_deliveries WHERE delivery_id=?",
                              (delivery_id,))
        if not row or row["sender_user_id"] != user_id:
            raise NotFoundOrHidden(delivery_id)
        return row

    @staticmethod
    def _effective_status(row: Dict[str, Any], today: str = "") -> str:
        """**읽는 시점에** 만료를 판정한다. 상태를 덮어쓰지 않는다.

        ★ 배치가 없어도 정확해야 한다 — 만료 처리를 배치에 맡기면 배치가 멈춘 동안 만료된 요청이
          수락 가능해진다."""
        st = row.get("status") or PENDING
        if st != PENDING:
            return st
        exp = (row.get("expires_at") or "").strip()
        if not exp:
            return st
        try:
            ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
            return EXPIRED if date.fromisoformat(exp) < ref else PENDING
        except ValueError:
            return st

    def _view(self, row: Dict[str, Any], viewer_user_id: str = "", today: str = "",
              replayed: bool = False) -> Dict[str, Any]:
        """응답 형태. 저장된 상태 대신 **유효 상태**를 싣는다."""
        import json as _json
        d = dict(row)
        for k in ("manifest_snapshot", "permission_snapshot"):
            try:
                d[k] = _json.loads(d.get(k) or "{}")
            except Exception:
                d[k] = {}
        eff = self._effective_status(row, today)
        d["status"] = eff
        d["stored_status"] = row.get("status")
        d["role"] = ("recipient" if viewer_user_id == row.get("recipient_user_id")
                     else "sender" if viewer_user_id == row.get("sender_user_id") else "")
        d["can_respond"] = (d["role"] == "recipient" and eff == PENDING)
        d["can_revoke"] = (d["role"] == "sender" and eff in (PENDING, ACCEPTED))
        d["replayed"] = bool(replayed)
        if eff == EXPIRED:
            d["note"] = f"{row.get('expires_at')} 에 만료됐습니다 — 보낸 사람이 다시 전달해야 합니다."
        return d

    @staticmethod
    def _notify(event: str, delivery: dict, actor: str) -> None:
        """[CL-4] 보낸 사람·받는 사람에게만 알린다. **manifest·권한 스냅샷을 싣지 않는다.**"""
        collaboration_events.emit(
            event, collaboration_events.delivery_recipients(delivery),
            {"id": delivery.get("delivery_id", ""), "status": delivery.get("status", ""),
             "at": delivery.get("responded_at") or delivery.get("created_at", ""),
             "title": delivery.get("release_id", ""), "actor": actor})

    def _ledger_append(self, event: str, subject_id: str, actor_id: str, decision: str = "",
                       rationale: str = "", evidence: Optional[List[Any]] = None,
                       tenant_id: str = "tenant_default", scope: str = "") -> None:
        """원장 기록. **실패를 삼키지 않는다**(§5.2).

        ⚠️ 여기서 예외를 잡아 로그만 남기면 "수락 기록이 없는 수락"이 생긴다. 상태는 이미 바뀐
          뒤이므로 호출자가 그 사실을 알아야 한다 — 원자성은 §12 독립 검토 대상으로 보드에 올렸다."""
        self._ledger.append(
            event, subject_type=_SUBJECT_BY_EVENT.get(event, "app_delivery"),
            subject_id=subject_id, actor_type="user", actor_id=actor_id or "",
            decision=decision, rationale=rationale, evidence_refs=evidence or [],
            tenant_id=tenant_id, enterprise_scope_id=scope)


_SUBJECT_BY_EVENT = {
    "APP_DELIVERY_CREATED": "app_delivery", "APP_DELIVERY_ACCEPTED": "app_delivery",
    "APP_DELIVERY_REJECTED": "app_delivery", "APP_DELIVERY_REVOKED": "app_delivery",
}


def _default_release_lookup(release_id: str) -> Optional[Dict[str, Any]]:
    """`library/<release_id>/release.json` 을 읽는다.

    경로는 `core/library_paths.py` 단일 지점에서 온다 — 상수를 다시 선언하지 않는다."""
    import json as _json

    from core import library_paths
    p = library_paths.release_json(release_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as e:
        print(f"⚠️ [app_delivery] 릴리스 읽기 실패({release_id}): {e}")
        return None


app_delivery = AppDelivery()
