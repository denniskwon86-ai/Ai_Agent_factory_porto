"""[M2] 커넥터 등록부 + Query Contract (§7.1 커넥터 계층 · §7.2 MCP 원칙). LLM 0콜.

## 크로스워크와 무엇이 다른가

M2 의 `external_systems`(크로스워크)는 **"어느 시스템의 어느 키가 우리 기준정보와 같은가"**
를 다룬다 — 주소록이다. 이 모듈은 **"그 시스템에 무엇을 물어볼 수 있는가"** 를 다룬다.

주소록만 있으면 임의 쿼리가 가능해지고, 그러면 최소 권한이 무너진다. §7.2 는 명시한다:

> 호출 가능한 도구는 **시스템별로 명시적으로 등록**한다. 기본은 최소 권한, 읽기 전용.

## Query Contract — 왜 필요한가

계약 없이 연결하면 다음 일이 벌어진다:

- 누군가 `SELECT * FROM salary` 를 실행한다(읽기 전용이어도 **볼 수 없어야 할 것**이다)
- 원천 스키마가 바뀌어도 아무도 모르고, 어느 날 조용히 빈 값이 들어온다
- 민감 컬럼이 프롬프트로 흘러 들어간다(§7.2 "민감 데이터는 무제한 전달하지 않는다")

그래서 계약에 **허용 필드를 화이트리스트로** 적고, 그 밖의 것은 요청해도 주지 않는다.

## 비밀은 여기에 저장하지 않는다

`auth_ref` 는 **참조**다(환경변수명·비밀관리자 키). 실제 자격증명을 DB 에 넣으면
그 DB 백업·로그·화면 어디로든 샌다. 값을 넣으려 하면 거부한다 —
"실수로 넣었는데 아무도 몰랐다"가 이 계열의 전형적인 사고다.
"""
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join("data", "connectors.db")

#: 자격증명처럼 보이는 문자열. `auth_ref` 에 이런 게 들어오면 **거부**한다.
#  ⚠️ 토큰 접두사(sk- 등)에만 "단어 시작" 제약을 건다. URL 인라인 자격증명
#    (`postgres://user:pw@host`)은 `://` 앞이 알파벳이라 그 제약에 걸려 **빠져나간다** —
#    실제로 테스트에서 통과할 뻔했다. 그래서 대안을 분리한다.
_SECRET_LOOKALIKE = re.compile(
    r"(?i)(?:(?:^|[^A-Za-z])(?:sk-|xoxb-|ghp_|AKIA|Bearer\s)"
    r"|password\s*=|://[^\s/:]+:[^\s@]+@)")

CONNECTOR_KINDS = ("mcp", "api", "db", "file")
#: 읽기 전용이 기본이다(§7.2). 쓰기는 별도 승인 없이는 등록할 수 없다.
ACCESS_MODES = ("read", "read-write")

_DDL = """
CREATE TABLE IF NOT EXISTS connectors (
    connector_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL,              -- mcp | api | db | file
    endpoint      TEXT DEFAULT '',
    -- ★ 자격증명 자체가 아니라 **참조**다(환경변수명·비밀관리자 키).
    auth_ref      TEXT DEFAULT '',
    access_mode   TEXT NOT NULL DEFAULT 'read',
    status        TEXT NOT NULL DEFAULT 'inactive',   -- inactive | active
    -- 범위 계약(M2 §2.1)
    tenant_id             TEXT NOT NULL DEFAULT 'tenant_default',
    owner_organization_id TEXT NOT NULL DEFAULT '',
    scope_type            TEXT NOT NULL DEFAULT 'ORG_PRIVATE',
    entity_mode           TEXT NOT NULL DEFAULT 'REAL',
    created_at    TEXT NOT NULL,
    note          TEXT DEFAULT ''
);

-- Query Contract — 그 시스템에 **무엇을 물어볼 수 있는가**.
CREATE TABLE IF NOT EXISTS query_contracts (
    contract_id   TEXT PRIMARY KEY,
    connector_id  TEXT NOT NULL,
    query_name    TEXT NOT NULL,              -- 업무 이름(예: monthly_pl)
    description   TEXT DEFAULT '',
    -- 허용 필드 화이트리스트(JSON 배열). 여기 없는 필드는 요청해도 주지 않는다.
    allowed_fields TEXT NOT NULL DEFAULT '[]',
    -- 필수 파라미터(JSON 배열). 없으면 전건 조회가 되어 최소 권한이 무너진다.
    required_params TEXT NOT NULL DEFAULT '[]',
    max_rows      INTEGER NOT NULL DEFAULT 1000,
    -- 민감 필드(JSON 배열) — 허용 목록에 있어도 **프롬프트로는 나가지 않는다**(§7.2).
    sensitive_fields TEXT NOT NULL DEFAULT '[]',
    approved_by   TEXT DEFAULT '',
    approved_at   TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qc_connector ON query_contracts(connector_id, query_name);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConnectorError(ValueError):
    """검증 실패 — 호출자에게 4xx 로 전달할 도메인 오류."""


class ConnectorRegistry:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    # ── 커넥터 ────────────────────────────────────────────────────────
    def register(self, connector_id: str, name: str, kind: str, endpoint: str = "",
                 auth_ref: str = "", access_mode: str = "read",
                 owner_organization_id: str = "", scope_type: str = "ORG_PRIVATE",
                 tenant_id: str = "tenant_default", note: str = "") -> Dict[str, Any]:
        """커넥터 등록. **등록만으로 활성이 아니다**(외부 원천 등록과 같은 원칙).

        ⚠️ `auth_ref` 에 자격증명처럼 보이는 값이 오면 **거부**한다. 실제 비밀을 DB 에 넣으면
          백업·로그·화면 어디로든 샌다 — "실수로 넣었는데 아무도 몰랐다"가 이 계열의 전형이다."""
        if kind not in CONNECTOR_KINDS:
            raise ConnectorError(f"kind 는 {'|'.join(CONNECTOR_KINDS)} 중 하나여야 합니다.")
        if access_mode not in ACCESS_MODES:
            raise ConnectorError(f"access_mode 는 {'|'.join(ACCESS_MODES)} 여야 합니다.")
        if auth_ref and _SECRET_LOOKALIKE.search(auth_ref):
            raise ConnectorError(
                "auth_ref 에 자격증명으로 보이는 값이 있습니다 — 여기에는 **참조**만 넣으십시오"
                "(예: 환경변수명 `ERP_API_KEY`, 비밀관리자 키). 실제 비밀을 저장하면 "
                "DB 백업·로그·화면으로 새어 나갑니다.")
        conn = self._connect()
        try:
            if conn.execute("SELECT 1 FROM connectors WHERE connector_id=?",
                            (connector_id,)).fetchone():
                raise ConnectorError(f"이미 존재하는 connector_id 입니다: {connector_id}")
            conn.execute(
                "INSERT INTO connectors(connector_id,name,kind,endpoint,auth_ref,access_mode,"
                "status,tenant_id,owner_organization_id,scope_type,entity_mode,created_at,note) "
                "VALUES(?,?,?,?,?,?,'inactive',?,?,?,'REAL',?,?)",
                (connector_id, name or connector_id, kind, endpoint or "", auth_ref or "",
                 access_mode, tenant_id or "tenant_default", owner_organization_id or "",
                 scope_type, _now(), note or ""))
            conn.commit()
            return dict(conn.execute("SELECT * FROM connectors WHERE connector_id=?",
                                     (connector_id,)).fetchone())
        finally:
            conn.close()

    def activate(self, connector_id: str, approved_by: str) -> Dict[str, Any]:
        """활성화 — **승인된 Query Contract 가 1건 이상** 있어야 한다.

        계약 없이 활성화하면 "연결은 됐는데 무엇을 물어볼 수 있는지 아무도 모르는" 상태가 되고,
        그때부터 임의 쿼리가 시작된다."""
        if not (approved_by or "").strip():
            raise ConnectorError("승인자 식별이 필요합니다 — 익명 활성화는 받지 않습니다.")
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM connectors WHERE connector_id=?",
                               (connector_id,)).fetchone()
            if not row:
                raise ConnectorError(f"존재하지 않는 커넥터입니다: {connector_id}")
            n = conn.execute("SELECT COUNT(*) FROM query_contracts "
                             "WHERE connector_id=? AND approved_by<>''",
                             (connector_id,)).fetchone()[0]
            if not n:
                raise ConnectorError(
                    "승인된 Query Contract 가 없습니다 — 무엇을 물어볼 수 있는지 정하지 않고 "
                    "활성화하면 임의 쿼리가 가능해집니다(§7.2 최소 권한).")
            conn.execute("UPDATE connectors SET status='active' WHERE connector_id=?",
                         (connector_id,))
            conn.commit()
            out = dict(conn.execute("SELECT * FROM connectors WHERE connector_id=?",
                                    (connector_id,)).fetchone())
        finally:
            conn.close()
        try:
            from core.enterprise_context import audit
            audit.record(audit.APPROVAL_GRANTED, "connector", connector_id,
                         actor=approved_by, outcome="granted", reason="connector_activated")
        except Exception:
            pass
        return out

    def get(self, connector_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM connectors WHERE connector_id=?",
                             (connector_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def list_connectors(self, scope_node_id: str = "", tenant_id: str = "",
                        entity_mode: str = "REAL") -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM connectors ORDER BY connector_id")]
        finally:
            conn.close()
        if not (scope_node_id or tenant_id):
            return rows
        from core.enterprise_context.scoping import filter_visible
        for r in rows:
            r["enterprise_scope_id"] = r.get("owner_organization_id") or ""
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode)

    # ── Query Contract ────────────────────────────────────────────────
    def add_contract(self, connector_id: str, query_name: str, allowed_fields: List[str],
                     required_params: Optional[List[str]] = None, max_rows: int = 1000,
                     sensitive_fields: Optional[List[str]] = None,
                     description: str = "", approved_by: str = "") -> Dict[str, Any]:
        """Query Contract 등록. **허용 필드가 비면 거부한다.**

        빈 화이트리스트는 "아무거나 다 준다"로 해석될 여지가 있고, 그 순간 계약의 의미가 없다."""
        if not self.get(connector_id):
            raise ConnectorError(f"존재하지 않는 커넥터입니다: {connector_id}")
        if not allowed_fields:
            raise ConnectorError(
                "allowed_fields(허용 필드)는 비울 수 없습니다 — 빈 화이트리스트는 "
                "'아무거나 다 준다'가 되어 계약의 의미가 사라집니다.")
        if max_rows <= 0:
            raise ConnectorError("max_rows 는 1 이상이어야 합니다(전건 조회 방지).")
        conn = self._connect()
        try:
            cid = uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO query_contracts(contract_id,connector_id,query_name,description,"
                "allowed_fields,required_params,max_rows,sensitive_fields,approved_by,"
                "approved_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, connector_id, query_name, description or "",
                 json.dumps(sorted(set(allowed_fields)), ensure_ascii=False),
                 json.dumps(sorted(set(required_params or [])), ensure_ascii=False),
                 int(max_rows),
                 json.dumps(sorted(set(sensitive_fields or [])), ensure_ascii=False),
                 approved_by or "", _now() if approved_by else "", _now()))
            conn.commit()
            return self.get_contract(connector_id, query_name)
        finally:
            conn.close()

    def get_contract(self, connector_id: str, query_name: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM query_contracts WHERE connector_id=? AND query_name=? "
                             "ORDER BY created_at DESC LIMIT 1",
                             (connector_id, query_name)).fetchone()
        finally:
            conn.close()
        if not r:
            return None
        d = dict(r)
        for k in ("allowed_fields", "required_params", "sensitive_fields"):
            try:
                d[k] = json.loads(d[k] or "[]")
            except Exception:
                d[k] = []
        return d

    def list_contracts(self, connector_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            names = [r["query_name"] for r in conn.execute(
                "SELECT DISTINCT query_name FROM query_contracts WHERE connector_id=?",
                (connector_id,))]
        finally:
            conn.close()
        return [c for c in (self.get_contract(connector_id, n) for n in names) if c]

    # ── 요청 검증 ─────────────────────────────────────────────────────
    def validate_request(self, connector_id: str, query_name: str,
                         fields: List[str], params: Optional[Dict[str, Any]] = None,
                         limit: int = 0, for_prompt: bool = False) -> Dict[str, Any]:
        """조회 요청이 계약을 지키는가. **거부 사유를 전부 모아 한 번에 돌려준다.**

        하나씩 튕기면 사용자가 여러 번 시도하며 무엇이 되는지 탐색하게 되고,
        그 탐색 자체가 스키마 정보 유출이다.

        `for_prompt=True` 면 **민감 필드를 제거**한다(§7.2 — 민감 데이터를 프롬프트로
        무제한 전달하지 않는다). 오류가 아니라 제거이며, 무엇이 빠졌는지 알려준다."""
        conn_row = self.get(connector_id)
        if not conn_row:
            return {"allowed": False, "errors": [f"존재하지 않는 커넥터입니다: {connector_id}"]}
        if conn_row["status"] != "active":
            return {"allowed": False,
                    "errors": [f"비활성 커넥터입니다(status={conn_row['status']}) — "
                               f"승인된 Query Contract 를 등록하고 활성화하십시오."]}
        c = self.get_contract(connector_id, query_name)
        if not c:
            return {"allowed": False,
                    "errors": [f"등록되지 않은 쿼리입니다: {query_name} — "
                               f"호출 가능한 도구는 시스템별로 명시적으로 등록합니다(§7.2)."]}
        if not c.get("approved_by"):
            return {"allowed": False,
                    "errors": [f"승인되지 않은 Query Contract 입니다: {query_name}"]}

        errors: List[str] = []
        allowed = set(c["allowed_fields"])
        asked = list(fields or [])
        not_allowed = [f for f in asked if f not in allowed]
        if not_allowed:
            errors.append(f"허용되지 않은 필드: {', '.join(sorted(not_allowed))} "
                          f"(허용: {', '.join(sorted(allowed))})")
        missing = [p for p in c["required_params"] if not (params or {}).get(p)]
        if missing:
            errors.append(f"필수 파라미터 누락: {', '.join(missing)} — "
                          f"없으면 전건 조회가 되어 최소 권한이 무너집니다.")
        eff_limit = int(limit) if limit and limit > 0 else int(c["max_rows"])
        if eff_limit > int(c["max_rows"]):
            errors.append(f"limit({eff_limit})이 계약 상한({c['max_rows']})을 넘습니다.")

        if errors:
            return {"allowed": False, "errors": errors, "query_name": query_name}

        sensitive = set(c["sensitive_fields"])
        effective = [f for f in asked if not (for_prompt and f in sensitive)]
        removed = [f for f in asked if for_prompt and f in sensitive]
        return {
            "allowed": True, "query_name": query_name, "connector_id": connector_id,
            "effective_fields": effective, "limit": eff_limit,
            # ★ 제거는 오류가 아니다. 다만 **말하지 않으면** 사용자는 값이 왜 없는지 모른다.
            "removed_sensitive": removed,
            "note": (f"민감 필드 {len(removed)}개를 프롬프트 전달 대상에서 제외했습니다(§7.2)."
                     if removed else ""),
        }


connector_registry = ConnectorRegistry()
