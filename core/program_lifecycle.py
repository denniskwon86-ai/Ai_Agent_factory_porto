"""[사용자 결정 2026-07-30] 프로그램 사용여부 — **삭제하지 않고 비활성화한다.**

## 결정의 배경

`release_readiness.rollback()` 은 "이 시스템은 배포된 코드를 되돌리지 못한다"는 한계를
정직하게 기록만 했다. 제품 책임자의 결정은 되돌리기가 아니라 **사용여부 제어**다:

> "이미 생성되어 다른 사용자가 기록을 남긴 코드(프로그램)을 삭제하면 꼬일 수 있으니
>  그냥 사용여부만 제어해서 더이상 사용하지 않는 프로그램이라고 비활성화 조치만 하는 것이
>  좋을 것 같습니다."

이것이 옳다. 삭제는 **다른 사용자가 그 프로그램을 근거로 남긴 기록을 고아로 만든다** —
결재 이력, 감사 로그, 지식팩 인덱스, 파생(fork) 프로그램의 출처가 전부 끊긴다.
사용을 막는 것과 존재를 지우는 것은 다른 조치이며, 필요한 것은 전자다.

## 상태

  · `active`     — 사용 가능
  · `deprecated` — 사용 가능하되 **신규 사용 자제**(경고). 예고 없이 죽이면 그 자체가 사고다.
  · `disabled`   — 사용 차단. **기록은 그대로 남는다.**

⚠️ `deprecated` 는 소비자가 경고를 **표시하지 않으면 장식**이다. 그래서 `assert_usable()` 이
   경고를 반환값으로 돌려주고, API 응답에 실어 보낸다.

## 미기록은 `active` 로 본다 — 다만 "관리자가 승인했다"고 말하지 않는다

이 기능 이전에 게시된 프로그램은 사용 중이다. 기본을 `disabled` 로 두면 전부 죽는다.
그래서 미기록은 사용 가능으로 보되 `recorded=False` 를 함께 준다 —
**추정과 관리자의 결정을 같은 것으로 표시하면 감사에서 거짓이 된다.**

## 대체 프로그램

비활성화만 하고 갈 곳을 알려주지 않으면 사용자는 막다른 길에서 **같은 프로그램을 다시
만든다** — 중복은 그렇게 태어난다. 그래서 `replacement_release_id` 를 받고, 그 대체본이
존재하며 스스로 비활성이 아닌지 검사한다(또 다른 막다른 길로 보내지 않는다).

LLM 0콜.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 라이브러리 경로는 **단일 지점**에서 온다(`core/library_paths.py`). 이 모듈이 경로를 따로
#   들고 있으면 게시된 프로그램을 "존재하지 않는다"며 제어를 거부한다 — 그러면 사고를 낸
#   프로그램을 IT 관리자가 끌 수 없다.
from core import library_paths
from core.paths import data_path

_DB_PATH = data_path("program_lifecycle.db")

ACTIVE = "active"
DEPRECATED = "deprecated"
DISABLED = "disabled"
#: ★★★ [I-4 6 / Wave F-1] **아직 승인되지 않은 후보 판.** Preview 에서만 돈다.
#:
#: ⚠️ 상태값을 «먼저» 더한다 — 게시 기본값을 바꾸는 것과는 다른 일이다. 아무도 이
#:   상태로 만들지 않으면 동작은 그대로이고, 대신 **Preview 경로를 실제로 태워 볼 수
#:   있게** 된다. 값이 없으면 그 경로는 시험에서도 한 번도 실행되지 않는다(실측:
#:   변이 검사가 7건을 놓쳤고, 원인이 전부 이것이었다).
#: ⚠️ 게시 기본값 전환은 **승격 경로와 같은 커밋**에서 한다(Wave F-2) — 나누면 그
#:   사이에 만들어진 릴리스가 전부 후보로 갇힌다.
CANDIDATE = "candidate"
STATUSES = (ACTIVE, DEPRECATED, DISABLED, CANDIDATE)
#: 사용을 허용하는 상태. `deprecated` 는 경고를 달고 통과한다.
#:
#: ⚠️⚠️ `CANDIDATE` 는 **여기 없다.** 후보 판은 «운영에서 쓸 수 있는 것» 이 아니다 —
#:   Preview 청중으로만 열린다(`core/app_preview.audience_for_state`). 여기 넣으면
#:   승인되지 않은 판이 일반 실행 경로로 열린다.
USABLE = (ACTIVE, DEPRECATED)

_DDL = """
CREATE TABLE IF NOT EXISTS program_status(
    release_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    reason TEXT NOT NULL DEFAULT '',
    replacement_release_id TEXT NOT NULL DEFAULT '',
    changed_by TEXT NOT NULL DEFAULT '',
    changed_at TEXT NOT NULL DEFAULT '',
    dependents_at_change TEXT NOT NULL DEFAULT '{}'
);
-- append-only. 상태 변경 이력은 지우지 않는다 — "언제부터 못 쓰게 됐나"에 답해야 한다.
CREATE TABLE IF NOT EXISTS program_status_history(
    event_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    from_status TEXT NOT NULL DEFAULT '',
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    replacement_release_id TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL DEFAULT '',
    dependents TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pl_hist ON program_status_history(release_id, at);
"""


class ProgramLifecycleError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgramLifecycle:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DB_PATH
        # 라이브러리 경로 주입 인자(`library_dir`)는 제거했다 — 그 인자는 세 모듈이 경로를
        #   각자 선언하던 시절에 테스트가 어긋남을 우회하려고 있던 것이고, 단일 지점
        #   (`library_paths`)이 생긴 뒤로는 **우회 경로가 곧 새로운 어긋남**이다.
        self._ready = ""

    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        # 경로가 런타임에 바뀌면(테스트 격리) DDL 을 다시 돌려야 한다 — 안 하면 "no such table".
        if self._ready != self.db_path:
            conn.executescript(_DDL)
            conn.commit()
            self._ready = self.db_path
        return conn

    # ── 조회 ──────────────────────────────────────────────────────────
    def get_status(self, release_id: str) -> Dict[str, Any]:
        """현재 사용여부. 미기록은 `active` + `recorded=False`.

        ★ 추정(`recorded=False`)과 관리자의 결정(`recorded=True`)을 구분해서 준다.
          같은 것으로 표시하면 "관리자가 사용을 승인했다"는 거짓 기록이 된다."""
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM program_status WHERE release_id=?",
                             (release_id,)).fetchone()
        finally:
            conn.close()
        if not r:
            return {"release_id": release_id, "status": ACTIVE, "recorded": False,
                    "reason": "", "replacement_release_id": "", "changed_by": "",
                    "changed_at": "",
                    "note": ("사용여부가 기록되지 않았습니다 — 사용 가능으로 간주하지만 "
                             "관리자가 승인한 상태는 아닙니다(이 기능 이전에 게시된 "
                             "프로그램입니다).")}
        d = dict(r)
        d["recorded"] = True
        try:
            d["dependents_at_change"] = json.loads(d.get("dependents_at_change") or "{}")
        except Exception:
            d["dependents_at_change"] = {}
        d["note"] = ""
        return d

    def history(self, release_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM program_status_history WHERE release_id=? ORDER BY at",
                (release_id,))]
        finally:
            conn.close()
        for d in rows:
            try:
                d["dependents"] = json.loads(d.get("dependents") or "{}")
            except Exception:
                d["dependents"] = {}
        return rows

    def list_statuses(self, status: str = "") -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            q = "SELECT * FROM program_status"
            args: tuple = ()
            if status:
                q += " WHERE status=?"
                args = (status,)
            rows = [dict(r) for r in conn.execute(q + " ORDER BY changed_at DESC", args)]
        finally:
            conn.close()
        for d in rows:
            d["recorded"] = True
        return rows

    def statuses_for(self, release_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """목록 화면용 일괄 조회 — 건별 조회는 N+1 이 되어 목록이 느려진다."""
        return {rid: self.get_status(rid) for rid in release_ids}

    # ── 사용 시점의 강제 ──────────────────────────────────────────────
    def assert_usable(self, release_id: str) -> Dict[str, Any]:
        """사용 시점에 호출한다. 차단이면 예외, 예고면 경고를 돌려준다.

        ★ 이 함수를 호출하는 소비자가 없으면 이 모듈 전체가 장식이다. 호출 지점:
          `factory_control.get_release`(실행 payload 제거) · `delete_release`(삭제 거부)."""
        st = self.get_status(release_id)
        if st["status"] == DISABLED:
            rep = st.get("replacement_release_id") or ""
            raise ProgramLifecycleError(
                f"이 프로그램은 IT 관리자가 사용을 중단시켰습니다"
                + (f"(사유: {st['reason']})" if st.get("reason") else "")
                + ". 기록은 그대로 보존되어 있으며 조회는 가능합니다."
                + (f" 대체 프로그램: {rep}" if rep else
                   " 대체 프로그램이 지정되지 않았습니다 — 관리자에게 문의하십시오."))
        warning = ""
        if st["status"] == DEPRECATED:
            rep = st.get("replacement_release_id") or ""
            warning = ("사용 중단이 예고된 프로그램입니다"
                       + (f"(사유: {st['reason']})" if st.get("reason") else "")
                       + ". 신규 사용은 자제하십시오."
                       + (f" 대체 프로그램: {rep}" if rep else ""))
        return {"usable": True, "status": st["status"], "recorded": st["recorded"],
                "warning": warning}

    # ── 의존 관계 ─────────────────────────────────────────────────────
    def dependents(self, release_id: str) -> Dict[str, Any]:
        """이 프로그램을 끄면 누가 영향을 받는가.

        ⚠️ 조회 실패를 0 으로 두지 않는다 — "영향 없음"과 "영향을 못 셌음"은 다르다."""
        out: Dict[str, Any] = {"forks": [], "shared_to": [], "is_enterprise": False,
                               "unmeasured": []}
        try:
            from core.workspace_promotion import workspace
            out["forks"] = [f.get("new_project_id", "")
                            for f in workspace.list_forks(release_id) or []]
        except Exception as e:
            out["unmeasured"].append(f"파생(fork) 조회 실패: {e}")
        try:
            from core.workspace_promotion import workspace
            out["shared_to"] = sorted({s.get("to_scope", "")
                                       for s in workspace.list_shares(release_id) or []
                                       if s.get("to_scope")})
        except Exception as e:
            out["unmeasured"].append(f"공유 대상 조회 실패: {e}")
        try:
            from core.workspace_promotion import workspace
            pr = workspace.get_promotion(release_id)
            out["is_enterprise"] = bool(pr and pr.get("status") == "promoted")
        except Exception as e:
            out["unmeasured"].append(f"전사 승격 여부 조회 실패: {e}")
        n = len(out["forks"]) + len(out["shared_to"]) + (1 if out["is_enterprise"] else 0)
        out["count"] = n
        out["blast_radius"] = ("enterprise" if out["is_enterprise"]
                               else "department" if n else "none")
        return out

    # ── 변경 ──────────────────────────────────────────────────────────
    def set_status(self, release_id: str, status: str, actor: str, reason: str = "",
                   replacement_release_id: str = "",
                   acknowledge_dependents: bool = False) -> Dict[str, Any]:
        """사용여부를 바꾼다. IT 관리자 권한 검사는 **API 계층**에서 한다."""
        if status not in STATUSES:
            raise ProgramLifecycleError(
                f"허용되지 않은 상태입니다: {status} (허용: {', '.join(STATUSES)})")
        if not (actor or "").strip():
            raise ProgramLifecycleError(
                "변경자 식별 정보가 없습니다 — 누가 껐는지 모르는 비활성화는 감사 대상이 "
                "될 수 없습니다.")
        if status != ACTIVE and not (reason or "").strip():
            # 사유 없는 비활성화는 나중에 "왜 껐지?"에 답할 수 없고, 그러면 아무도 다시
            # 켜지 못한다(되돌릴 근거가 없으니까).
            raise ProgramLifecycleError(
                f"'{status}' 로 바꿀 때는 사유가 필요합니다 — 사유가 없으면 나중에 "
                f"되돌릴 근거도 없어 아무도 다시 켜지 못합니다.")
        if not self._release_exists(release_id):
            raise ProgramLifecycleError(
                f"존재하지 않는 프로그램입니다: {release_id} — 라이브러리에 게시된 "
                f"릴리스만 사용여부를 제어할 수 있습니다.")

        if replacement_release_id:
            if replacement_release_id == release_id:
                raise ProgramLifecycleError("자기 자신을 대체 프로그램으로 지정할 수 없습니다.")
            if not self._release_exists(replacement_release_id):
                raise ProgramLifecycleError(
                    f"대체 프로그램이 존재하지 않습니다: {replacement_release_id}")
            rep_st = self.get_status(replacement_release_id)
            if rep_st["status"] == DISABLED:
                # 막다른 길에서 또 막다른 길로 보내면 사용자는 결국 같은 프로그램을 새로 만든다.
                raise ProgramLifecycleError(
                    f"대체 프로그램({replacement_release_id})도 비활성 상태입니다 — "
                    f"사용자를 또 다른 막다른 길로 보내게 됩니다.")

        dep = self.dependents(release_id)
        if status == DISABLED and dep["count"] and not acknowledge_dependents:
            # 의존이 있는 프로그램을 조용히 끄면, 끊긴 쪽은 원인을 모른 채 고장난다.
            parts = []
            if dep["is_enterprise"]:
                parts.append("전사 승격된 프로그램입니다(전 부서 영향)")
            if dep["forks"]:
                parts.append(f"파생 프로그램 {len(dep['forks'])}건: "
                             f"{', '.join(dep['forks'][:5])}")
            if dep["shared_to"]:
                parts.append(f"공유 대상 {len(dep['shared_to'])}곳: "
                             f"{', '.join(dep['shared_to'][:5])}")
            raise ProgramLifecycleError(
                "의존하는 대상이 있어 그대로 비활성화하지 않았습니다 — "
                + " / ".join(parts)
                + f". 영향 범위: {dep['blast_radius']}. 확인했다면 "
                  "acknowledge_dependents=true 로 다시 요청하십시오."
                + (f" ⚠️ 세지 못한 항목: {'; '.join(dep['unmeasured'])}"
                   if dep["unmeasured"] else ""))

        prev = self.get_status(release_id)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO program_status(release_id,status,reason,"
                "replacement_release_id,changed_by,changed_at,dependents_at_change) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(release_id) DO UPDATE SET "
                "status=excluded.status, reason=excluded.reason, "
                "replacement_release_id=excluded.replacement_release_id, "
                "changed_by=excluded.changed_by, changed_at=excluded.changed_at, "
                "dependents_at_change=excluded.dependents_at_change",
                (release_id, status, reason or "", replacement_release_id or "",
                 actor, _now(), json.dumps(dep, ensure_ascii=False)))
            conn.execute(
                "INSERT INTO program_status_history(event_id,release_id,from_status,"
                "to_status,reason,replacement_release_id,actor,at,dependents) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex[:16], release_id, prev["status"], status, reason or "",
                 replacement_release_id or "", actor, _now(),
                 json.dumps(dep, ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()

        self._audit(release_id, prev["status"], status, actor, reason, dep)
        out = self.get_status(release_id)
        out["from_status"] = prev["status"]
        out["dependents"] = dep
        out["note"] = (
            "프로그램은 삭제되지 않았습니다 — 사용만 차단했고 기록·이력은 그대로 남습니다."
            if status == DISABLED else
            "사용 중단이 예고되었습니다. 아직 사용은 가능하지만 소비 화면에 경고가 표시됩니다."
            if status == DEPRECATED else
            "사용이 재개되었습니다.")
        return out

    def disable(self, release_id: str, actor: str, reason: str,
                replacement_release_id: str = "",
                acknowledge_dependents: bool = False) -> Dict[str, Any]:
        return self.set_status(release_id, DISABLED, actor, reason,
                               replacement_release_id, acknowledge_dependents)

    def reactivate(self, release_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
        """다시 켠다. 되돌릴 수 있어야 관리자가 겁내지 않고 끌 수 있다."""
        return self.set_status(release_id, ACTIVE, actor, reason or "사용 재개")

    # ── 내부 ──────────────────────────────────────────────────────────
    def _release_exists(self, release_id: str) -> bool:
        if not release_id or any(c in release_id for c in ("/", "\\", "..")):
            return False
        return os.path.exists(library_paths.release_json(release_id))

    def _audit(self, release_id: str, frm: str, to: str, actor: str, reason: str,
               dep: Dict[str, Any]) -> None:
        try:
            from core.enterprise_context import audit
            audit.record(audit.PROGRAM_STATUS_CHANGED, resource_type="program",
                         resource_id=release_id, actor=actor,
                         outcome="allowed", reason=reason or "",
                         detail=f"{frm}->{to} blast_radius={dep.get('blast_radius')} "
                                f"dependents={dep.get('count')}")
        except Exception as e:                                     # pragma: no cover
            print(f"⚠️ [program_lifecycle] 감사 기록 실패: {e}")


program_lifecycle = ProgramLifecycle()
