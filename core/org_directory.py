"""조직·사용자·권한 디렉터리 (설계서 Phase 1).

부서를 **기준정보로** 다룬다 — `master_records` 와 동일한 거버넌스(버전·시행일·supersedes·
소프트 폐지)를 부서에도 적용한다. 부서 개편 이력이 보존돼야 과거 산출물의 소유 부서 해석이
깨지지 않기 때문이다.

저장소는 `master.db` 를 공유한다('한 판' 철학). `MasterData` 의 구조를 그대로 미러링한다 —
자체 DDL + executescript + _lock/_cache/_invalidate + 모듈 말미 싱글턴.

⚠️ 하위호환 계약: `departments` 가 비어 있으면 권한 해석이 `unrestricted=True` 를 즉시 반환해
   **조직 미도입 상태에서 지금과 100% 동일하게 동작**한다. 이것이 깨지면 기존 테스트가 전부 깨진다.
"""
import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config
from core.master_data import _DB_PATH, _TYPE_OR_DOMAIN_RE, MasterDataError

# 사용자 ID 는 이메일·SSO subject 를 담을 수 있어야 하므로 부서 ID 보다 넓게 허용한다.
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")
_ROLES = ("viewer", "member", "manager")
_VISIBILITY = ("dept", "company", "personal")

_ORG_DDL = """
CREATE TABLE IF NOT EXISTS departments (
    dept_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    name_ko TEXT NOT NULL,
    parent_id TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    depth INTEGER NOT NULL DEFAULT 0,
    master_domains TEXT DEFAULT '[]',
    default_template_id TEXT DEFAULT '',
    domain_agents TEXT DEFAULT '[]',
    legacy_domain TEXT DEFAULT '',
    valid_from TEXT NOT NULL, valid_to TEXT,
    supersedes TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dept_id, version)
);
CREATE INDEX IF NOT EXISTS idx_dept_parent ON departments(parent_id, status);
CREATE INDEX IF NOT EXISTS idx_dept_path   ON departments(path);

CREATE TABLE IF NOT EXISTS dept_aliases (
    alias TEXT NOT NULL, dept_id TEXT NOT NULL, source TEXT DEFAULT 'user',
    PRIMARY KEY (alias, dept_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    primary_dept_id TEXT NOT NULL DEFAULT '',
    is_executive INTEGER NOT NULL DEFAULT 0,
    is_admin     INTEGER NOT NULL DEFAULT 0,
    is_data_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_dept_roles (
    user_id TEXT NOT NULL, dept_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    PRIMARY KEY (user_id, dept_id)
);
CREATE INDEX IF NOT EXISTS idx_udr_user ON user_dept_roles(user_id);

CREATE TABLE IF NOT EXISTS ownership (
    resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL,
    dept_id TEXT NOT NULL DEFAULT '', owner_user_id TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'dept',
    nature TEXT NOT NULL DEFAULT '',
    relevance TEXT NOT NULL DEFAULT '',
    forked_from_kind TEXT NOT NULL DEFAULT '',
    forked_from_id   TEXT NOT NULL DEFAULT '',
    forked_at        TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (resource_kind, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_own_dept ON ownership(dept_id, resource_kind);
CREATE INDEX IF NOT EXISTS idx_own_fork ON ownership(forked_from_id);
"""


def _org_enforce_effective() -> bool:
    """권한 강제 여부 — **관리자가 화면에서 바꾼 값이 있으면 그것을, 없으면 코드 기본값을** 쓴다.

    ★ [2026-07-30] 이 값이 False 면 `resolve_scope` 가 전원 무제한을 돌려주므로, 조직 범위·등급·
      드릴다운 통제가 **하나도 작동하지 않는다.** 그래서 켜고 끄는 것은 배포가 아니라 관리자
      결정이어야 한다(`core/scope_policy.set_org_enforce`).
    ★ 호출 시점에 읽는다. 캐시하면 스위치를 켜도 재시작해야 하고, 재시작이 필요한 스위치는
      사고 상황에서 되돌림 장치가 되지 못한다."""
    try:
        from core.scope_policy import org_enforce
        v = org_enforce()
        if v is not None:
            return v
    except Exception:
        pass                          # 정책 저장소 장애 → 코드 기본값으로
    return bool(getattr(config, "ORG_ENFORCE", False))


@dataclass(frozen=True)
class AccessScope:
    """한 사용자가 무엇을 읽고 쓸 수 있는가에 대한 확정 해석.

    `unrestricted=True` 면 모든 필터가 no-op 이어야 한다 — 조직 미도입 상태의 하위호환 계약."""
    user_id: str = ""
    display_name: str = ""
    is_executive: bool = False
    is_admin: bool = False
    is_data_admin: bool = False
    readable_dept_ids: frozenset = frozenset()
    writable_dept_ids: frozenset = frozenset()
    primary_dept_id: str = ""
    unrestricted: bool = True
    can_run_enterprise: bool = False
    can_edit_org: bool = False
    can_manage_standard: bool = False
    #: 읽기 가능한 부서들이 대응하는 **ECM 조직 노드**들. 자료(지식팩·참고문서·기준정보)의
    #: 소유 조직은 부서가 아니라 이 노드로 적혀 있으므로, 행 단위 필터는 이 집합을 쓴다.
    #: ⚠️ 비어 있다 = "이 사용자에 대응하는 조직 노드를 모른다"이지 "전부 볼 수 있다"가 아니다.
    #:   판정 함수는 비어 있으면 **닫는다**(관문 A). `unrestricted` 만이 전면 통과의 근거다.
    readable_scope_nodes: frozenset = frozenset()

    def can_read(self, dept_id: str) -> bool:
        return self.unrestricted or not dept_id or dept_id in self.readable_dept_ids

    def can_write(self, dept_id: str) -> bool:
        return self.unrestricted or not dept_id or dept_id in self.writable_dept_ids

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id, "display_name": self.display_name,
            "is_executive": self.is_executive, "is_admin": self.is_admin,
            "is_data_admin": self.is_data_admin,
            "readable_dept_ids": sorted(self.readable_dept_ids),
            "writable_dept_ids": sorted(self.writable_dept_ids),
            "primary_dept_id": self.primary_dept_id,
            "unrestricted": self.unrestricted,
            "can_run_enterprise": self.can_run_enterprise,
            "can_edit_org": self.can_edit_org,
            "can_manage_standard": self.can_manage_standard,
            "readable_scope_nodes": sorted(self.readable_scope_nodes),
        }


class OrgDirectory:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._scope_cache: Dict[str, AccessScope] = {}
        self._init_db()

    # ── 인프라 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    #: 부서 표에 나중에 추가된 컬럼 — `_init_db` 가 매번 확인해 없으면 붙인다.
    #: ★ 선언을 DDL 과 여기 두 곳에 두지 않는다. DDL 은 새 DB 를, 이 표는 기존 DB 를 담당하고,
    #:   값의 의미는 한 곳(아래 주석)에만 적는다.
    _ADDED_DEPT_COLUMNS = (
        # 이 부서가 대응하는 **ECM 조직 노드**(예: LS_MNM, MNM_BATTERY).
        # 왜 부서에 두는가 — 사용자마다 따로 적으면 같은 부서의 두 사람이 다른 조직 범위를 갖게
        # 되고, 그 차이는 아무도 의도하지 않은 채 생긴다. 부서는 기준정보이므로 조직 범위도
        # 부서가 들고 사용자는 **상속**한다(단일 판정 지점).
        ("scope_node_id", "TEXT NOT NULL DEFAULT ''"),
    )

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(_ORG_DDL)
            have = {r[1] for r in conn.execute("PRAGMA table_info(departments)")}
            for col, decl in self._ADDED_DEPT_COLUMNS:
                if col not in have:
                    conn.execute(f"ALTER TABLE departments ADD COLUMN {col} {decl}")
                    print(f"ℹ️ [org] departments.{col} 컬럼을 추가했습니다(기존 행은 미지정).")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _invalidate(self):
        self._scope_cache.clear()

    # ── 감사 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _audit(event: str, resource_id: str, actor: str, reason: str,
               detail: str = "", resource_type: str = "department") -> None:
        """조직 변경을 감사로그에 남긴다.

        ★★★ **왜 코어에서 남기는가**(라우트가 아니라). 실측된 사고가 근거다: 최상위 부서 `hq` 가
          2026-07-27 23:39:53 에 "본사" → "해킹" 으로 바뀌었는데 **누가 바꿨는지 알 수 없었다.**
          부서 표의 버전 이력은 *무엇이* 바뀌었는지만 담고, 감사로그에는 조직 변경이 한 줄도
          없었다. 그리고 그 변경은 화면이 아니라 시드/스크립트 경로였을 가능성이 크다 —
          라우트에만 기록을 붙이면 **바로 그 경로가 계속 기록되지 않는다.**
        ⚠️ `actor` 가 비면 `anonymous` 로 남는다. 그것도 정보다 — "식별되지 않은 경로로 조직이
          바뀌었다"는 사실 자체가 조사 대상이다. 비었다고 기록을 건너뛰지 않는다."""
        try:
            from core.enterprise_context import audit
            audit.record(getattr(audit, event, event), resource_type=resource_type,
                         resource_id=resource_id or "?", actor=actor or "",
                         outcome="allowed", reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            # 조용히 넘기지 않는다 — 권한을 정의하는 변경의 기록 유실은 그 자체가 사건이다.
            print(f"⚠️ [org] 조직 변경 감사 기록 실패({resource_id}): {e}")

    @staticmethod
    def _check_dept_id(v: str):
        if not _TYPE_OR_DOMAIN_RE.match(v or ""):
            raise MasterDataError("잘못된 dept_id 형식입니다 (^[a-z0-9_-]{2,32}$).")

    @staticmethod
    def _check_user_id(v: str):
        if not _USER_ID_RE.match(v or ""):
            raise MasterDataError("잘못된 user_id 형식입니다 (^[A-Za-z0-9_.@-]{1,64}$).")

    @staticmethod
    def _row_to_dept(r: sqlite3.Row) -> Dict[str, Any]:
        d = dict(r)
        for k in ("master_domains", "domain_agents"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except Exception:
                d[k] = []
        return d

    # ── 부서 조회 ─────────────────────────────────────────────────────────
    # ⚠️ 두 조회 모두 `has_any_department` 와 **같은 복원력 규약**을 따른다(`_ensure_tables` 주석 참조):
    #   한 번 스키마 복구를 시도하고, 그래도 안 되면 '조직 미도입'으로 간주해 빈 값을 준다.
    #   이게 없으면 조직 DB 가 없는 환경(신규 클론·시드 전·작업 디렉터리 변경)에서
    #   `create_mega_project` 가 `no such table: departments` 로 **500 으로 죽는다** — 그 함수는
    #   미등록 부서를 이미 `_LEGACY_DEPARTMENTS` 로 폴백하도록 설계돼 있으므로, 테이블 부재도
    #   같은 '미도입'으로 흘러가야 설계 의도(하위호환 계약)와 맞는다.
    def list_departments(self, include_retired: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM departments WHERE valid_to IS NULL"
        if not include_retired:
            sql += " AND status='active'"
        sql += " ORDER BY path, dept_id"
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [self._row_to_dept(r) for r in conn.execute(sql).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def get_department(self, dept_id: str) -> Optional[Dict[str, Any]]:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute(
                        "SELECT * FROM departments WHERE dept_id=? AND valid_to IS NULL", (dept_id,)
                    ).fetchone()
                return self._row_to_dept(r) if r else None
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return None
        return None

    def get_department_history(self, dept_id: str) -> List[Dict[str, Any]]:
        """개편 이력(구판 포함) — 과거 산출물의 소유 부서를 해석하려면 이력이 필요하다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM departments WHERE dept_id=? ORDER BY version DESC", (dept_id,)
            ).fetchall()
        return [self._row_to_dept(r) for r in rows]

    def get_tree(self) -> List[Dict[str, Any]]:
        """계층 트리(children 중첩). 화면의 조직도 렌더용."""
        flat = self.list_departments()
        by_id = {d["dept_id"]: {**d, "children": []} for d in flat}
        roots = []
        for d in flat:
            node = by_id[d["dept_id"]]
            parent = by_id.get(d.get("parent_id") or "")
            (parent["children"] if parent else roots).append(node)
        return roots

    def descendants_of(self, dept_id: str) -> List[str]:
        """자기 자신 + 모든 하위 부서 id. materialized path 접두 매칭 1쿼리.

        ⚠️ GLOB 을 쓴다(LIKE 금지) — dept_id 가 `_` 를 허용하는데 LIKE 에서 `_` 는 와일드카드라
          `sales_kr` 이 `salesXkr` 에도 매칭돼 권한이 새어나간다."""
        me = self.get_department(dept_id)
        if not me:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT dept_id FROM departments WHERE valid_to IS NULL AND status='active' "
                "AND path GLOB ? ORDER BY path", (me["path"] + "*",)
            ).fetchall()
        return [r["dept_id"] for r in rows]

    # ── 부서 쓰기 ─────────────────────────────────────────────────────────
    def _compute_path(self, conn, dept_id: str, parent_id: str) -> tuple:
        if not parent_id:
            return f"/{dept_id}/", 0
        p = conn.execute(
            "SELECT path, depth FROM departments WHERE dept_id=? AND valid_to IS NULL AND status='active'",
            (parent_id,)
        ).fetchone()
        if not p:
            raise MasterDataError(f"상위 부서 '{parent_id}' 가 없습니다.")
        depth = int(p["depth"]) + 1
        if depth > getattr(config, "ORG_MAX_DEPTH", 8):
            raise MasterDataError(f"조직 깊이 상한({getattr(config, 'ORG_MAX_DEPTH', 8)})을 초과합니다.")
        return f"{p['path']}{dept_id}/", depth

    def create_department(self, dept_id: str, name_ko: str, parent_id: str = "",
                          master_domains: List[str] = None, default_template_id: str = "",
                          domain_agents: List[str] = None, legacy_domain: str = "",
                          aliases: List[str] = None, scope_node_id: str = "",
                          actor: str = "") -> Dict[str, Any]:
        self._check_dept_id(dept_id)
        if not (name_ko or "").strip():
            raise MasterDataError("name_ko 는 필수입니다.")
        if parent_id:
            self._check_dept_id(parent_id)
            if parent_id == dept_id:                       # 가드1
                raise MasterDataError("자기 자신을 상위 부서로 지정할 수 없습니다.")
        with self._lock, self._connect() as conn:
            if conn.execute("SELECT 1 FROM departments WHERE dept_id=? AND valid_to IS NULL",
                            (dept_id,)).fetchone():
                raise MasterDataError(f"부서 '{dept_id}' 가 이미 존재합니다.")
            path, depth = self._compute_path(conn, dept_id, parent_id)   # 가드3
            now = self._now()
            conn.execute(
                "INSERT INTO departments (dept_id, version, name_ko, parent_id, path, depth, "
                "master_domains, default_template_id, domain_agents, legacy_domain, "
                "valid_from, valid_to, supersedes, status, updated_at, scope_node_id) "
                "VALUES (?,1,?,?,?,?,?,?,?,?,?,NULL,'','active',?,?)",
                (dept_id, name_ko, parent_id, path, depth,
                 json.dumps(master_domains or [], ensure_ascii=False), default_template_id,
                 json.dumps(domain_agents or [], ensure_ascii=False), legacy_domain, now, now,
                 (scope_node_id or "").strip()))
            for a in (aliases or []):
                if str(a).strip():
                    conn.execute("INSERT OR IGNORE INTO dept_aliases (alias, dept_id) VALUES (?,?)",
                                 (str(a).strip(), dept_id))
            conn.commit()
        self._invalidate()
        self._audit("ORG_STRUCTURE_CHANGED", dept_id, actor, "부서 생성",
                    f"name={name_ko} parent={parent_id or '(최상위)'} "
                    f"scope={scope_node_id or '(미지정)'}")
        return self.get_department(dept_id)

    def update_department(self, dept_id: str, name_ko: str = None, parent_id: str = None,
                          master_domains: List[str] = None, default_template_id: str = None,
                          domain_agents: List[str] = None, legacy_domain: str = None,
                          scope_node_id: str = None, actor: str = "") -> Dict[str, Any]:
        """부서 개정. **새 버전**을 만들고 구판은 `valid_to` 로 닫아 이력을 보존한다.
        `parent_id` 가 바뀌면 하위 트리의 path/depth 를 일괄 갱신한다.

        ★ `scope_node_id`(ECM 조직 노드) 도 개정 대상이다 — 바뀌면 그 부서 사람들이 보는 자료가
          바뀌므로, 조용히 덮지 않고 새 버전으로 남긴다("언제부터 이 부서가 이 범위였나"에 답한다)."""
        cur = self.get_department(dept_id)
        if not cur:
            raise MasterDataError(f"부서 '{dept_id}' 가 없습니다.")
        moving = parent_id is not None and parent_id != cur["parent_id"]
        if moving and parent_id:
            self._check_dept_id(parent_id)
            if parent_id == dept_id:                                     # 가드1
                raise MasterDataError("자기 자신을 상위 부서로 지정할 수 없습니다.")

        with self._lock, self._connect() as conn:
            new_parent = cur["parent_id"] if parent_id is None else parent_id
            if moving:
                if new_parent:
                    np = conn.execute(
                        "SELECT path FROM departments WHERE dept_id=? AND valid_to IS NULL AND status='active'",
                        (new_parent,)).fetchone()
                    if not np:
                        raise MasterDataError(f"상위 부서 '{new_parent}' 가 없습니다.")
                    # 가드2(핵심): 자기 자손을 부모로 삼는 것을 O(1) 차단
                    if str(np["path"]).startswith(cur["path"]):
                        raise MasterDataError("자기 하위 부서를 상위로 지정할 수 없습니다(순환).")
                new_path, new_depth = self._compute_path(conn, dept_id, new_parent)
            else:
                new_path, new_depth = cur["path"], cur["depth"]

            now = self._now()
            ver = int(cur["version"]) + 1
            conn.execute("UPDATE departments SET valid_to=?, status='superseded' "
                         "WHERE dept_id=? AND valid_to IS NULL", (now, dept_id))
            conn.execute(
                "INSERT INTO departments (dept_id, version, name_ko, parent_id, path, depth, "
                "master_domains, default_template_id, domain_agents, legacy_domain, "
                "valid_from, valid_to, supersedes, status, updated_at, scope_node_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?,'active',?,?)",
                (dept_id, ver,
                 cur["name_ko"] if name_ko is None else name_ko,
                 new_parent, new_path, new_depth,
                 json.dumps(cur["master_domains"] if master_domains is None else master_domains, ensure_ascii=False),
                 cur["default_template_id"] if default_template_id is None else default_template_id,
                 json.dumps(cur["domain_agents"] if domain_agents is None else domain_agents, ensure_ascii=False),
                 cur["legacy_domain"] if legacy_domain is None else legacy_domain,
                 now, f"{dept_id}#v{cur['version']}", now,
                 (cur.get("scope_node_id", "") if scope_node_id is None
                  else (scope_node_id or "").strip())))

            if moving:
                # 하위 트리 일괄 이동 — 접두 치환. GLOB 으로 안전하게 범위를 잡는다.
                old_prefix, shift = cur["path"], new_depth - int(cur["depth"])
                conn.execute(
                    "UPDATE departments SET path = ? || substr(path, ?), depth = depth + ?, updated_at=? "
                    "WHERE path GLOB ? AND dept_id <> ? AND valid_to IS NULL AND status='active'",
                    (new_path, len(old_prefix) + 1, shift, now, old_prefix + "*", dept_id))
            conn.commit()
        self._invalidate()
        # 무엇이 바뀌었는지를 **바뀐 것만** 적는다 — 전부 적으면 변경점이 묻힌다.
        chg = []
        if name_ko is not None and name_ko != cur["name_ko"]:
            chg.append(f"name: {cur['name_ko']} → {name_ko}")
        if moving:
            chg.append(f"parent: {cur['parent_id'] or '(최상위)'} → {new_parent or '(최상위)'}")
        if scope_node_id is not None and scope_node_id != cur.get("scope_node_id", ""):
            chg.append(f"scope: {cur.get('scope_node_id') or '(미지정)'} → "
                       f"{scope_node_id or '(미지정)'}")
        self._audit("ORG_STRUCTURE_CHANGED", dept_id, actor,
                    f"부서 개정(v{cur['version']}→v{ver})",
                    " / ".join(chg) or "변경 내용 없음(버전만 증가)")
        return self.get_department(dept_id)

    def retire_department(self, dept_id: str, actor: str = "") -> bool:
        """소프트 폐지. **물리 삭제하지 않는다** — `ownership.dept_id` 가 참조하므로
        과거 산출물의 소유 부서 해석이 깨지면 안 된다."""
        with self._lock, self._connect() as conn:
            kids = conn.execute(
                "SELECT COUNT(*) c FROM departments WHERE parent_id=? AND valid_to IS NULL AND status='active'",
                (dept_id,)).fetchone()
            if kids and int(kids["c"]) > 0:
                raise MasterDataError("하위 부서가 있어 폐지할 수 없습니다. 먼저 이동하거나 폐지하십시오.")
            cur = conn.execute("UPDATE departments SET status='retired', updated_at=? "
                               "WHERE dept_id=? AND valid_to IS NULL", (self._now(), dept_id))
            conn.commit()
            ok = cur.rowcount > 0
        self._invalidate()
        if ok:
            self._audit("ORG_STRUCTURE_CHANGED", dept_id, actor, "부서 폐지(soft-retire)",
                        "이 부서에 매인 사람들의 권한이 사라진다")
        return ok

    # ── 사용자 ────────────────────────────────────────────────────────────
    def upsert_user(self, user_id: str, display_name: str, primary_dept_id: str = "",
                    is_executive: bool = False, is_admin: bool = False,
                    is_data_admin: bool = False, actor: str = "") -> Dict[str, Any]:
        self._check_user_id(user_id)
        if not (display_name or "").strip():
            raise MasterDataError("display_name 은 필수입니다.")
        was = bool(self.get_user(user_id))
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, display_name, primary_dept_id, is_executive, is_admin, "
                "is_data_admin, status, created_at) VALUES (?,?,?,?,?,?, 'active', ?) "
                "ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name, "
                "primary_dept_id=excluded.primary_dept_id, is_executive=excluded.is_executive, "
                "is_admin=excluded.is_admin, is_data_admin=excluded.is_data_admin",
                (user_id, display_name, primary_dept_id, int(is_executive), int(is_admin),
                 int(is_data_admin), self._now()))
            conn.commit()
        self._invalidate()
        # ⚠️ 권한 플래그는 별도로 적는다 — is_admin 부여는 **전권 부여**이고, 그 한 줄이
        #   나중에 "왜 이 사람이 전부 볼 수 있었나"의 유일한 답이 된다.
        flags = [n for n, v in (("executive", is_executive), ("admin", is_admin),
                                ("data_admin", is_data_admin)) if v]
        self._audit("ORG_USER_CHANGED", user_id, actor,
                    ("사용자 등록·갱신" if not was else "사용자 갱신"),
                    f"dept={primary_dept_id or '(미배정)'} "
                    f"권한={'+'.join(flags) or '(없음)'}", resource_type="user")
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not r:
                return None
            roles = conn.execute("SELECT dept_id, role FROM user_dept_roles WHERE user_id=?",
                                 (user_id,)).fetchall()
        u = dict(r)
        for k in ("is_executive", "is_admin", "is_data_admin"):
            u[k] = bool(u.get(k))
        u["roles"] = {x["dept_id"]: x["role"] for x in roles}
        return u

    def list_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            ids = [r["user_id"] for r in conn.execute(
                "SELECT user_id FROM users WHERE status='active' ORDER BY user_id").fetchall()]
        return [self.get_user(u) for u in ids]

    def set_user_roles(self, user_id: str, roles: Dict[str, str],
                       actor: str = "") -> Dict[str, Any]:
        if not self.get_user(user_id):
            raise MasterDataError(f"사용자 '{user_id}' 가 없습니다.")
        for d, r in (roles or {}).items():
            self._check_dept_id(d)
            if r not in _ROLES:
                raise MasterDataError(f"role 은 {_ROLES} 중 하나여야 합니다: {r}")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM user_dept_roles WHERE user_id=?", (user_id,))
            for d, r in (roles or {}).items():
                conn.execute("INSERT INTO user_dept_roles (user_id, dept_id, role) VALUES (?,?,?)",
                             (user_id, d, r))
            conn.commit()
        self._invalidate()
        # 역할이 곧 열람·쓰기 범위다(상위 부서 역할은 하위로 상속된다) — 변경을 남긴다.
        self._audit("ORG_USER_CHANGED", user_id, actor, "부서 역할 변경",
                    ", ".join(f"{d}={r}" for d, r in sorted((roles or {}).items()))
                    or "(전부 해제 — 읽을 수 있는 부서가 없어진다)", resource_type="user")
        return self.get_user(user_id)

    def delete_user(self, user_id: str, actor: str = "") -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE users SET status='retired' WHERE user_id=?", (user_id,))
            conn.commit()
            ok = cur.rowcount > 0
        self._invalidate()
        if ok:
            # 폐지는 권한 회수다 — 남기지 않으면 "이 사람 계정이 왜 안 되나"에 답할 수 없다.
            self._audit("ORG_USER_CHANGED", user_id, actor, "사용자 폐지(권한 회수)",
                        "이후 이 계정은 미등록과 같게 처리된다", resource_type="user")
        return ok

    # ── 권한 해석 ─────────────────────────────────────────────────────────
    def _ensure_tables(self):
        """스키마가 없으면 만든다.

        ⚠️ `db_path` 가 상대 경로라 **작업 디렉터리가 바뀌면 다른 파일을 가리킨다**(테스트가
          tmp 로 chdir 하는 경우 등). 그때 `no such table` 로 죽으면 권한 조회가 전 API 를
          500 으로 만든다. 조회 경로에서 한 번 복구를 시도하고, 그래도 안 되면 '조직 미도입'
          으로 간주해 통과시킨다 — 권한 인프라 장애가 기능 전체를 멈추면 안 된다."""
        try:
            self._init_db()
            return True
        except Exception:
            return False

    def has_any_department(self) -> bool:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT 1 FROM departments WHERE valid_to IS NULL "
                                     "AND status='active' LIMIT 1").fetchone()
                return bool(r)
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return False
        return False

    def has_any_user(self) -> bool:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT 1 FROM users WHERE status='active' LIMIT 1").fetchone()
                return bool(r)
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return False
        return False

    def is_bootstrap(self) -> bool:
        """아직 조직이 '가동'되지 않은 상태인가.

        ⚠️ [부트스트랩 잠금 방지] 부서만 등록하고 사용자가 하나도 없으면, 권한을 강제하는 순간
          **첫 관리자를 만들 권한을 가진 사람이 아무도 없어 시스템이 잠긴다**(실측: /seed 직후
          /users POST 가 403). 사용자가 0명이면 권한 강제는 의미가 없으므로 무제한으로 둔다.
          첫 사용자가 등록되는 순간부터 정상 강제된다."""
        return not self.has_any_department() or not self.has_any_user()

    def resolve_scope(self, user_id: str = "") -> AccessScope:
        """사용자의 확정 권한 스코프. 캐시되며 조직 쓰기 시 무효화된다."""
        key = user_id or "__anon__"
        cached = self._scope_cache.get(key)
        if cached is not None:
            return cached

        # ① 조직 미도입/부트스트랩/강제 해제 → 전면 무제한. 지금과 100% 동일 동작.
        #   · 부서가 없다 = 조직을 도입하지 않았다
        #   · 사용자가 없다 = 부서만 만들고 아직 가동하지 않았다 → 여기서 강제하면 첫 관리자를
        #     만들 수 없어 시스템이 잠긴다(실측)
        #   · ORG_ENFORCE=False = 단계적 도입을 위한 안전판
        if self.is_bootstrap() or not _org_enforce_effective():
            scope = AccessScope(user_id=user_id, display_name=user_id, unrestricted=True,
                                can_edit_org=True, can_run_enterprise=True, can_manage_standard=True)
            self._scope_cache[key] = scope
            return scope

        u = self.get_user(user_id) if user_id else None
        # ★★ [2026-07-30 실측 결함] **폐지된 사용자를 권한 판정에서 걸러야 한다.**
        #   `list_users()` 는 `status='active'` 를 거르는데 `get_user()` 는 거르지 않는다.
        #   그래서 폐지한 계정이 **권한을 그대로 유지**했다 — 실측: 테스트 계정 `admin` 을
        #   폐지한 뒤에도 `resolve_scope('admin')` 이 `unrestricted=True`(전권)를 돌려줬다.
        #   폐지가 권한을 제거하지 않으면 그것은 폐지가 아니고, 화면 목록에서만 사라져 **더
        #   위험하다**(관리자는 정리했다고 믿는다).
        #   ⚠️ `get_user` 쪽을 고치지 않은 이유: 이력·감사 화면은 폐지된 사용자도 읽어야 한다.
        #     걸러야 하는 곳은 **권한 판정**이다.
        if u and str(u.get("status", "active")) != "active":
            print(f"ℹ️ [org] 폐지된 사용자의 접근 시도 — 권한 없음으로 처리: {user_id}")
            u = None
        if not u:
            # 미등록·폐지 사용자: 아무 부서도 못 읽는다(소유 자원만 별도 매칭).
            scope = AccessScope(user_id=user_id, display_name=user_id, unrestricted=False)
            self._scope_cache[key] = scope
            return scope

        is_admin = bool(u["is_admin"])
        is_exec = bool(u["is_executive"])
        is_da = bool(u["is_data_admin"])

        # ② 시스템 관리자 → 전권
        if is_admin:
            scope = AccessScope(
                user_id=user_id, display_name=u["display_name"], is_admin=True,
                is_executive=is_exec, is_data_admin=is_da,
                primary_dept_id=u.get("primary_dept_id", ""), unrestricted=True,
                can_run_enterprise=True, can_edit_org=True, can_manage_standard=True)
            self._scope_cache[key] = scope
            return scope

        all_ids = frozenset(d["dept_id"] for d in self.list_departments())

        # ③ 경영진 → 전 부서 read + 전사 실행. 조직 편집·표준 관리 권한은 **없다**.
        if is_exec:
            own = frozenset(self._writable_from_roles(u))
            scope = AccessScope(
                user_id=user_id, display_name=u["display_name"], is_executive=True,
                is_data_admin=is_da, readable_dept_ids=all_ids, writable_dept_ids=own,
                readable_scope_nodes=self._scope_nodes_of(all_ids),
                primary_dept_id=u.get("primary_dept_id", ""), unrestricted=False,
                can_run_enterprise=True, can_edit_org=False,
                can_manage_standard=is_da)
            self._scope_cache[key] = scope
            return scope

        # ④ DA → 카탈로그·표준 전권 + 메타 전사 열람. 조직 편집·전사 실행 권한은 없다.
        readable = set()
        writable = set(self._writable_from_roles(u))
        for d in (u.get("roles") or {}):
            readable.update(self.descendants_of(d))      # ⑤ 상위→하위 상속
        if u.get("primary_dept_id"):
            readable.update(self.descendants_of(u["primary_dept_id"]))
        if is_da:
            readable = set(all_ids)

        scope = AccessScope(
            user_id=user_id, display_name=u["display_name"], is_data_admin=is_da,
            readable_dept_ids=frozenset(readable), writable_dept_ids=frozenset(writable),
            readable_scope_nodes=self._scope_nodes_of(readable),
            primary_dept_id=u.get("primary_dept_id", ""), unrestricted=False,
            can_run_enterprise=False, can_edit_org=False, can_manage_standard=is_da)
        self._scope_cache[key] = scope
        return scope

    def _scope_nodes_of(self, dept_ids) -> frozenset:
        """부서들이 대응하는 ECM 조직 노드 집합. 미지정 부서는 아무것도 보태지 않는다.

        ⚠️ 미지정을 "상위 노드로 추측"하지 않는다 — 추측이 한 번 맞으면 그 뒤로는 아무도 검증하지
          않고, 틀리면 다른 사업부 자료가 열린다. 미지정은 미지정으로 두고 화면이 말하게 한다."""
        if not dept_ids:
            return frozenset()
        try:
            with self._connect() as conn:
                q = ",".join("?" for _ in dept_ids)
                rows = conn.execute(
                    f"SELECT scope_node_id FROM departments WHERE dept_id IN ({q}) "
                    f"AND valid_to IS NULL AND status='active' AND scope_node_id <> ''",
                    tuple(dept_ids)).fetchall()
            return frozenset(str(r[0]).strip() for r in rows if str(r[0]).strip())
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [org] 부서→조직노드 해석 실패(범위 없음으로 처리): {e}")
            return frozenset()

    def _writable_from_roles(self, u: Dict[str, Any]) -> List[str]:
        """쓰기 가능 부서 = role 이 member/manager 인 부서와 그 하위. viewer 는 읽기만."""
        out = set()
        for d, r in (u.get("roles") or {}).items():
            if r in ("member", "manager"):
                out.update(self.descendants_of(d))
        return sorted(out)

    # ── 소유권 미러 ───────────────────────────────────────────────────────
    def set_ownership(self, resource_kind: str, resource_id: str, dept_id: str = "",
                      owner_user_id: str = "", visibility: str = "dept",
                      nature: str = "", forked_from_kind: str = "",
                      forked_from_id: str = "", forked_at: str = "") -> Dict[str, Any]:
        if visibility not in _VISIBILITY:
            raise MasterDataError(f"visibility 는 {_VISIBILITY} 중 하나여야 합니다.")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO ownership (resource_kind, resource_id, dept_id, owner_user_id, visibility, "
                "nature, relevance, forked_from_kind, forked_from_id, forked_at, updated_at) "
                "VALUES (?,?,?,?,?,?,'',?,?,?,?) "
                "ON CONFLICT(resource_kind, resource_id) DO UPDATE SET dept_id=excluded.dept_id, "
                "owner_user_id=excluded.owner_user_id, visibility=excluded.visibility, "
                "nature=excluded.nature, forked_from_kind=excluded.forked_from_kind, "
                "forked_from_id=excluded.forked_from_id, forked_at=excluded.forked_at, "
                "updated_at=excluded.updated_at",
                (resource_kind, resource_id, dept_id, owner_user_id, visibility, nature,
                 forked_from_kind, forked_from_id, forked_at, self._now()))
            conn.commit()
        return self.get_ownership(resource_kind, resource_id)

    def get_ownership(self, resource_kind: str, resource_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                r = conn.execute("SELECT * FROM ownership WHERE resource_kind=? AND resource_id=?",
                                 (resource_kind, resource_id)).fetchone()
        except sqlite3.OperationalError:
            return None   # 미러가 없으면 '소유권 미기록' — 하위호환상 막지 않는다
        return dict(r) if r else None

    def visible_resources(self, scope: AccessScope, resource_kind: str) -> Optional[List[str]]:
        """스코프에서 볼 수 있는 자원 id 목록. `None` = 제한 없음(전부 보임).

        ⚠️ `None` 과 빈 리스트를 구분해야 한다. 빈 리스트는 '볼 게 없다'이고
          `None` 은 '필터하지 말라'다. 이걸 섞으면 무제한 모드에서 아무것도 안 보인다."""
        if scope.unrestricted:
            return None
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT resource_id, dept_id, owner_user_id, visibility FROM ownership "
                "WHERE resource_kind=?", (resource_kind,)).fetchall()
        out = []
        for r in rows:
            if r["visibility"] == "company":
                out.append(r["resource_id"])
            elif r["owner_user_id"] and r["owner_user_id"] == scope.user_id:
                out.append(r["resource_id"])
            elif r["dept_id"] and r["dept_id"] in scope.readable_dept_ids:
                out.append(r["resource_id"])
        return out


# 싱글턴 (master_data 와 동일 패턴)
org_directory = OrgDirectory()
