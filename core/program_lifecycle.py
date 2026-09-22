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
    dependents_at_change TEXT NOT NULL DEFAULT '{}',
    -- ★★★ 이 상태가 «어느 업무 데이터 위에서» 정해졌는가.
    --   빈 문자열은 「봉인하지 않음」이고, 그것은 「데이터를 안 쓴다」와 다르다 —
    --   후자는 NOT_APPLICABLE 로 적는다.
    data_fingerprint TEXT NOT NULL DEFAULT ''
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
    dependents TEXT NOT NULL DEFAULT '{}',
    data_fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pl_hist ON program_status_history(release_id, at);
"""


class ProgramLifecycleError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgramLifecycle:
    def __init__(self, db_path: str = None, connect=None, begin_immediate: str = ""):
        self.db_path = db_path or _DB_PATH
        #: ★ [DB-1 · 2026-09-21] 연결 획득과 «쓰기 잠금 시작 문장» 만 주입 가능하게 둔다.
        #:   SQL 은 그대로다 — 방언 차이는 `core/db` 한 곳에서 온다.
        self._connect_fn = connect
        self._begin_immediate = begin_immediate or "BEGIN IMMEDIATE"
        # 라이브러리 경로 주입 인자(`library_dir`)는 제거했다 — 그 인자는 세 모듈이 경로를
        #   각자 선언하던 시절에 테스트가 어긋남을 우회하려고 있던 것이고, 단일 지점
        #   (`library_paths`)이 생긴 뒤로는 **우회 경로가 곧 새로운 어긋남**이다.
        self._ready = ""

    def _connect(self):
        #: ⚠️ [DB-1] 주입된 연결도 **같은 부트스트랩을 지나야 한다.** 여기서 바로 돌려주면
        #:   DDL 을 건너뛰고 「no such table」이 난다(실제로 한 번 그렇게 났다).
        #:   주입은 «연결을 어디서 얻는가» 만 바꾸는 것이지 준비 절차를 건너뛰는 문이 아니다.
        if self._connect_fn is not None:
            conn = self._connect_fn()
        else:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=15000")
        # 경로가 런타임에 바뀌면(테스트 격리) DDL 을 다시 돌려야 한다 — 안 하면 "no such table".
        if self._ready != self.db_path:
            conn.executescript(_DDL)
            #: ⚠️ 이미 만들어진 DB 에는 `CREATE TABLE IF NOT EXISTS` 가 컬럼을 더해
            #:   주지 않는다. 없으면 여기서 붙인다 — 없는 채로 두면 봉인이 조용히
            #:   버려지고, 「봉인했다」는 기록만 남는다.
            for table in ("program_status", "program_status_history"):
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                if cols and "data_fingerprint" not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN "
                                 f"data_fingerprint TEXT NOT NULL DEFAULT ''")
            conn.commit()
            self._ready = self.db_path
        return conn

    # ── 조회 ──────────────────────────────────────────────────────────
    @staticmethod
    def _read_status(conn, release_id: str) -> Dict[str, Any]:
        """**이미 열린 연결**로 현재 상태를 읽는다 — 트랜잭션 안에서 쓰기 위한 것.

        ⚠️ 기본값은 `get_status` 와 **같아야 한다**(미기록 = active·recorded False).
          여기서 다르게 판단하면 같은 질문에 두 답이 생긴다."""
        r = conn.execute("SELECT * FROM program_status WHERE release_id=?",
                         (release_id,)).fetchone()
        if not r:
            return {"release_id": release_id, "status": ACTIVE, "recorded": False,
                    "reason": "", "replacement_release_id": "", "data_fingerprint": ""}
        d = dict(r)
        d["recorded"] = True
        return d

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
        #: ★ [W03.3] **정본 파일이 있는지 함께 답한다.** 이 DB 는 사용여부만 알고 릴리스가
        #:   실제로 있는지는 모른다. 파일이 사라져도 행은 남으므로, 그것만 보고 답하면
        #:   **없는 프로그램을 「사용 가능」이라고 말하게 된다.** 기존 필드는 그대로 두고
        #:   사실을 하나 더 얹는다 — 호출자를 깨뜨리지 않으면서 숨기지도 않는다.
        #:   ⚠️ `_read_status` 에는 넣지 않는다. 그쪽은 트랜잭션 안의 순수 DB 읽기이고,
        #:     쓰기 경로는 `set_status` 가 이미 `_release_exists` 로 막는다.
        present = self._release_exists(release_id)
        if not r:
            return {"release_id": release_id, "status": ACTIVE, "recorded": False,
                    "reason": "", "replacement_release_id": "", "changed_by": "",
                    "changed_at": "", "artifact_present": present,
                    "note": ("사용여부가 기록되지 않았습니다 — 사용 가능으로 간주하지만 "
                             "관리자가 승인한 상태는 아닙니다(이 기능 이전에 게시된 "
                             "프로그램입니다).")}
        d = dict(r)
        d["recorded"] = True
        d["artifact_present"] = present
        try:
            d["dependents_at_change"] = json.loads(d.get("dependents_at_change") or "{}")
        except Exception:
            d["dependents_at_change"] = {}
        #: 파일이 없는데 기록만 남은 상태 — 「같은 질문에 두 답」이 되는 자리다.
        #: `core/release_consistency.py` 가 이것을 모아서 보고한다.
        d["note"] = ("" if present else
                     "정본 파일이 없습니다 — 사용여부 기록만 남아 있습니다. "
                     "이 상태로는 소유 문맥을 확인할 수 없습니다.")
        return d

    def effective_status(self, release_id: str) -> str:
        """지금 **쓸 수 있는가**를 묻는 자리의 상태. 정본이 없으면 **빈 문자열**이다.

        ★ [W03.3 / 격리 표시] 사용여부 기록은 **지우지 않는다**(관리자가 껐다는 결정이
          사라지면 재게시 때 켜진 채 돌아온다). 대신 정본이 없는 동안 **판정에서 뺀다.**
          그것이 「행 보존 + 격리 표시」다.

        ⚠️ 새 상태 어휘를 만들지 않고 **빈 문자열**을 쓴다. 이 값을 받는 자리들이 이미
          「모르면 접지 않는다」로 짜여 있기 때문이다 — `app_preview.audience_for_state("")`
          는 청중을 못 고르고, 청중이 없으면 평면도 안 고른다. 새 값을 만들면 그 fail-closed
          경로를 타지 않고 각자 새로 판단하게 된다.

        ⚠️ 상태를 **구분해서 답해야 하는** 자리는 이것을 쓰지 않는다. `calculation_control`
          은 정본 없음을 「아직 생성되지 않았습니다」(409)로 따로 말하고, 그 구분은 사용자에게
          쓸모가 있다. 여기로 뭉뚱그리면 그 말이 사라진다.
        """
        row = self.get_status(release_id)
        return str(row.get("status") or "") if row.get("artifact_present") else ""

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
                   acknowledge_dependents: bool = False,
                   data_fingerprint: str = "",
                   expected_status: Optional[str] = None) -> Dict[str, Any]:
        """사용여부를 바꾼다. IT 관리자 권한 검사는 **API 계층**에서 한다.

        ★★★ `data_fingerprint` 는 이 결정이 **어느 업무 데이터 위에서** 내려졌는지다.
          운영 승격 뒤에 원천 데이터가 바뀌면, 도는 앱은 «승인받은 것과 다른 숫자» 를
          그리기 시작한다. 그 순간 아무 오류도 나지 않는다 — 그래서 승인 시점의
          데이터 집합을 여기 못박아 두고, 나중에 대조할 수 있게 한다."""
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

        conn = self._connect()
        try:
            #: ★★★ [R3 · 2026-09-20] **직전 상태 읽기와 쓰기를 한 트랜잭션에 넣는다.**
            #:   ⚠️ 종전에는 밖에서 `get_status` 로 읽고 안에서 썼다. 그 사이 다른 요청이
            #:     상태를 바꾸면 **낡은 판단으로 덮어쓴다.** append-only 이력은 「과거 행이
            #:     안 바뀐다」는 뜻이지 「현재 상태가 그대로다」가 아니다.
            #:   ★ `BEGIN IMMEDIATE` 로 쓰기 잠금을 먼저 잡는다 — 프로세스가 달라도 유효하다.
            conn.isolation_level = None
            #: ⚠️ [DB-1] `BEGIN IMMEDIATE` 는 **SQLite 전용 문장**이다 — PostgreSQL 에는 없다.
            #:   문자열로 박아 두면 이관할 때 이 한 줄이 조용히 남아 터진다. 쓰기 잠금을
            #:   먼저 잡는 «같은 효과» 를 어떻게 낼지는 저장소마다 다르므로 부르는 쪽이 준다.
            conn.execute(self._begin_immediate)
            prev = self._read_status(conn, release_id)
            #: ★ CAS — 부른 쪽이 「이 상태일 때만 바꿔라」를 건 경우, **여기서** 확인한다.
            if expected_status is not None and prev["status"] != expected_status:
                conn.execute("ROLLBACK")
                raise ProgramLifecycleError(
                    f"그 사이 사용여부가 '{prev['status']}' 로 바뀌었습니다 — 낡은 판단으로 "
                    f"덮어쓰지 않았습니다. 현재 상태를 다시 확인한 뒤 요청하십시오.")
            conn.execute(
                "INSERT INTO program_status(release_id,status,reason,"
                "replacement_release_id,changed_by,changed_at,dependents_at_change,"
                "data_fingerprint) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(release_id) DO UPDATE SET "
                "status=excluded.status, reason=excluded.reason, "
                "replacement_release_id=excluded.replacement_release_id, "
                "changed_by=excluded.changed_by, changed_at=excluded.changed_at, "
                "dependents_at_change=excluded.dependents_at_change, "
                "data_fingerprint=excluded.data_fingerprint",
                (release_id, status, reason or "", replacement_release_id or "",
                 actor, _now(), json.dumps(dep, ensure_ascii=False),
                 str(data_fingerprint or "")))
            conn.execute(
                "INSERT INTO program_status_history(event_id,release_id,from_status,"
                "to_status,reason,replacement_release_id,actor,at,dependents,"
                "data_fingerprint) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex[:16], release_id, prev["status"], status, reason or "",
                 replacement_release_id or "", actor, _now(),
                 json.dumps(dep, ensure_ascii=False), str(data_fingerprint or "")))
            conn.execute("COMMIT")
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

    def _restore_point(self, release_id: str, conn=None) -> Dict[str, str]:
        """사용 중단 «직전» 스냅샷 — 상태·지문·대체 대상을 **한 행에서 통째로** 읽는다.

        ★★★ [R2 · 2026-09-20] 세 값은 **같은 시점**의 것이어야 한다.
          ⚠️⚠️ 종전에는 지문을 「이력 전체에서 마지막으로 비어 있지 않은 값」으로 골랐다.
            그러면 지문 F1 뒤에 **빈 지문을 가진 상태 기록**이 오고 그 뒤 중단한 경우,
            빈 값을 건너뛰고 F1 을 붙인다 — **다른 시점의 데이터가 현재 상태에 결속된다.**
          ★ **빈 값도 값이다.** 과거의 비어 있지 않은 값으로 채우지 않는다.

        중단 «직전» 의 값은 그 중단 바로 앞 이력 행이 남긴 것이다(그 행이 그때
        `program_status` 에 쓴 값이 곧 중단 시점의 현재 값이었다).

        ⚠️ 중단이 그 릴리스의 **첫 기록**이면 앞 행이 없다 — 그때는 지문·대체 대상이
          «없었던» 것이므로 빈 값으로 둔다. 만들어 채우지 않는다.
        ⚠️ 이력이 어긋나면(앞 행의 도착 상태 ≠ 중단 행의 출발 상태) **모른다**로 답한다.
        """
        own = conn is None
        conn = conn or self._connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT from_status,to_status,replacement_release_id,data_fingerprint "
                "FROM program_status_history WHERE release_id=? ORDER BY at, rowid",
                (release_id,))]
        finally:
            if own:
                conn.close()
        last = -1
        for idx, row in enumerate(rows):
            if row["to_status"] == DISABLED:
                last = idx
        if last < 0:
            return {"status": "", "data_fingerprint": "", "replacement_release_id": ""}
        target = str(rows[last].get("from_status") or "").strip()
        if last == 0:
            #: 중단이 첫 기록 — 그 앞에는 스냅샷이 없다. 지문·대체 대상은 «없었다».
            return {"status": target, "data_fingerprint": "", "replacement_release_id": ""}
        snap = rows[last - 1]
        if str(snap.get("to_status") or "").strip() != target:
            #: 이력이 어긋난다 — 추정하지 않는다.
            return {"status": "", "data_fingerprint": "", "replacement_release_id": ""}
        return {"status": target,
                "data_fingerprint": str(snap.get("data_fingerprint") or ""),
                "replacement_release_id": str(snap.get("replacement_release_id") or "")}

    def reactivate(self, release_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
        """**중단 해제**다 — 승격 명령이 아니다.

        ★★★ 중단 «직전» 상태로 되돌린다. 무조건 `ACTIVE` 가 아니다.

        ⚠️⚠️ 종전에는 `set_status(ACTIVE)` 하나였다. 그러면 `candidate`(아직 승인되지 않은
          Preview 후보)를 껐다 켜는 것만으로 **운영 청중**이 된다 —
          `core/app_preview.audience_for_state` 가 candidate→Preview, active→운영으로 갈라
          놓은 의미가 이 문으로 사라진다.
        ⚠️⚠️ [R1 · 2026-09-20] **중단 상태가 아니면 아무것도 바꾸지 않는다.** 앞선 판은
          「중단이 아니면 종전대로 ACTIVE」였는데, 그것이 같은 구멍을 다시 열었다 —
          `candidate` 로 복원한 **뒤 한 번 더** 부르면(또는 중단한 적 없는 후보에 바로
          부르면) `active` 가 됐다. 관리자의 재시도·중복 요청만으로 청중이 바뀐다.
          이제 **상태·지문·대체 대상을 그대로 둔 채** 돌려주고, 복원하지 않았으면
          복원했다고 **말하지도 않는다.**
        ★ `deprecated` 의 경고 해제도 이 명령으로 하지 않는다 — 중단 해제와 명시적 상태
          변경은 다른 일이다. 필요하면 `set_status` 로 명시한다.
        ⚠️ 이력이 없거나 어긋나면 **추정하지 않고 거절한다.** 「모르면 활성」이 그 사고다.
        ★ [R3] 읽기·판정·쓰기는 `set_status` 의 CAS(`expected_status`)로 묶는다 — 그 사이
          다른 요청이 상태를 바꿨으면 **덮어쓰지 않고 거절**한다.
        """
        base = (reason or "").strip() or "사용 재개"
        #: 존재·행위자 검증을 조기 반환으로 건너뛰지 않는다.
        if not (actor or "").strip():
            raise ProgramLifecycleError(
                "변경자 식별 정보가 없습니다 — 누가 켰는지 모르는 재개는 감사 대상이 "
                "될 수 없습니다.")
        if not self._release_exists(release_id):
            raise ProgramLifecycleError(
                f"존재하지 않는 프로그램입니다: {release_id} — 라이브러리에 게시된 "
                f"릴리스만 사용여부를 제어할 수 있습니다.")

        current = self.get_status(release_id)
        if current["status"] != DISABLED:
            #: ★ 불변 반환 — 오류 계약을 늘리지 않되 **아무것도 바꾸지 않는다.**
            out = dict(current)
            out["from_status"] = current["status"]
            out["restored"] = False
            out["note"] = ("사용 중단 상태가 아니어서 아무것도 바꾸지 않았습니다 — "
                           "이 명령은 중단 해제이며 상태를 올리는 명령이 아닙니다.")
            return out

        point = self._restore_point(release_id)
        restored = point["status"]
        if restored not in STATUSES or restored == DISABLED:
            raise ProgramLifecycleError(
                "중단 직전 상태를 확인할 수 없어 재개하지 않았습니다 — 무엇으로 되돌릴지 "
                "모르는 채 활성으로 켜면 승인되지 않은 판이 운영으로 열릴 수 있습니다. "
                "상태를 직접 지정해 변경하십시오.")
        out = self.set_status(
            release_id, restored, actor,
            f"{base} — 중단 직전 상태로 되돌림({restored})",
            replacement_release_id=point["replacement_release_id"],
            data_fingerprint=point["data_fingerprint"],
            expected_status=DISABLED)
        out["restored"] = True
        return out

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
