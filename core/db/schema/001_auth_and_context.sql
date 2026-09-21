-- [DB-1] 첫 수직 경로의 PostgreSQL 스키마 — 로그인 / 세션 / SSE 티켓 / 조직 문맥
--
-- ⚠️⚠️ 이것은 **설치 산출물**이다. 제품이 뜨면서 돌리지 않는다.
--   지금 SQLite 쪽은 기동 중 `CREATE TABLE IF NOT EXISTS` 와 `ALTER TABLE ADD COLUMN` 을
--   16곳에서 돌린다. 인스턴스가 둘 이상이면 그 DDL 이 **동시에** 돌고, 그때 무엇이
--   남는지는 아무도 보장하지 않는다. 이관의 목적 하나가 그 경로를 없애는 것이다.
--
-- ⚠️ 실행된 적이 **없다.** 이 저장소에는 PostgreSQL 환경이 없다(DSN 미준비).
--   문법·제약은 검토 대상이며 「PostgreSQL 에서 된다」는 증거가 아니다.
--
-- ⚠️ 값·토큰은 담지 않는다. 티켓은 **해시만** 저장한다(원문은 URL 로 오가므로 접근 로그·
--   리퍼러에 남는다 — 저장소까지 원문을 두면 유출면이 하나 더 는다).

BEGIN;

-- ── 주체 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth_credential (
    user_id        TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    salt           TEXT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL
);

-- ── 세션 ─────────────────────────────────────────────────────────────
-- ⚠️ 원문 토큰이 아니라 해시로 찾는다. 인덱스도 해시에 건다.
CREATE TABLE IF NOT EXISTS auth_session (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    token_hash  TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_session_hash ON auth_session(token_hash);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_session(user_id);

-- ── SSE 접속표 ───────────────────────────────────────────────────────
-- ★★★ 이 표의 계약이 이관에서 **가장 잃기 쉬운 것**이다.
--   소비는 «정확히 한 번» 이어야 하고, 그것을 보장하는 것은 아래 한 문장이다:
--
--     UPDATE auth_sse_ticket SET consumed_at = now()
--      WHERE token_hash = ? AND consumed_at IS NULL
--        AND expires_at >= now() AND audience = ?
--     -- 그리고 «바뀐 행 수» 로 판정한다.
--
--   「읽고 → 확인하고 → 쓰기」로 나누면 두 요청이 그 사이를 통과해 **같은 표로 둘 다
--   연결**된다. 인스턴스가 늘수록 쉬워진다.
--   ⚠️ 응용 메모리 lock 은 다중 인스턴스에서 **아무것도 보장하지 않는다.** 조건절이 진짜다.
--
-- ⚠️ SQLite 판은 `consumed_at TEXT NOT NULL DEFAULT ''`(빈 문자열 = 미사용)이다.
--   여기서는 NULL 을 쓴다 — 「없음」을 빈 문자열로 표현하면 타입이 시간이 아니게 된다.
--   ★ 이관 도구가 `'' → NULL` 을 옮겨야 하며, 응용의 조건절도 그에 맞춰야 한다.
--     이 차이를 대사 검사 항목으로 둔다.
CREATE TABLE IF NOT EXISTS auth_sse_ticket (
    token_hash      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT '',
    scope_node_id   TEXT NOT NULL DEFAULT '',
    entity_mode     TEXT NOT NULL DEFAULT '',
    context_version TEXT NOT NULL DEFAULT '',
    audience        TEXT NOT NULL DEFAULT 'sse',
    created_at      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    consumed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ticket_expires ON auth_sse_ticket(expires_at);
-- 미사용 표만 자주 찾는다 — 부분 인덱스가 그 질의에 맞는다.
CREATE INDEX IF NOT EXISTS idx_ticket_unconsumed
    ON auth_sse_ticket(token_hash) WHERE consumed_at IS NULL;

-- ── 조직 문맥 ────────────────────────────────────────────────────────
-- ★ auth 표만 옮기면 로그인 뒤 화면이 성립하지 않는다. 문맥 확인이 조직 계층을 탄다.
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS organization_nodes (
    node_id     TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(tenant_id),
    name        TEXT NOT NULL DEFAULT '',
    node_type   TEXT NOT NULL DEFAULT '',
    entity_mode TEXT NOT NULL DEFAULT 'REAL',
    dept_id     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_org_node_tenant ON organization_nodes(tenant_id);

-- ⚠️ 계층은 «간선» 으로 둔다. 부모 컬럼 하나로 두면 다중 소속·이력을 못 담는다.
CREATE TABLE IF NOT EXISTS organization_edges (
    parent_id  TEXT NOT NULL REFERENCES organization_nodes(node_id),
    child_id   TEXT NOT NULL REFERENCES organization_nodes(node_id),
    edge_type  TEXT NOT NULL DEFAULT 'operational',
    PRIMARY KEY (parent_id, child_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_org_edge_child ON organization_edges(child_id);

CREATE TABLE IF NOT EXISTS organization_node_code_aliases (
    alias      TEXT NOT NULL,
    node_id    TEXT NOT NULL REFERENCES organization_nodes(node_id),
    PRIMARY KEY (alias, node_id)
);

COMMIT;

-- ⚠️ 여기에 없는 것: 큐/lease/fencing, durable SSE 이벤트, 파일 manifest.
--   **첫 경로 완료와 전체 이관 완료는 다르다.**
