-- [DB-1 / P03.1] 첫 수직 경로의 PostgreSQL 스키마 — 로그인 / 세션 / SSE 티켓 / 조직 문맥
--
-- ⚠️⚠️ 이것은 **설치 산출물**이다. 제품이 뜨면서 돌리지 않는다.
--   SQLite 쪽은 기동 중 `CREATE TABLE IF NOT EXISTS` 와 `ALTER TABLE ADD COLUMN` 을
--   16곳에서 돌린다. 인스턴스가 둘 이상이면 그 DDL 이 **동시에** 돌고, 그때 무엇이
--   남는지는 아무도 보장하지 않는다. 이관의 목적 하나가 그 경로를 없애는 것이다.
--
-- ⚠️ 실행된 적이 **없다.** 이 저장소에 PostgreSQL 환경이 없다(DSN 미준비).
--   문법·제약은 검토 대상이며 「PostgreSQL 에서 된다」는 증거가 아니다.
--
-- ══════════════════════════════════════════════════════════════════════
-- ★★ [2026-09-21 P03.1] **첫 판은 첫 경로와 맞지 않았다.**
--
--   「표가 7개 있다」를 호환 증거로 썼던 것이 잘못이었다. 실제로 첫 경로가 읽고 쓰는
--   컬럼과 대조해 보니 **컬럼 14개가 없고 `enterprise_entities` 는 표 자체가 없었다.**
--   이 초안으로 설치했다면 로그인 뒤 문맥 조회가 **첫 요청에서** 죽었다.
--   이제 정본 DDL(`core/auth.py`, `core/enterprise_context/repository.py`)을 옆에 두고
--   **컬럼 이름·기본값까지 그대로** 맞춘다. 설치 명령이 접속 전에 이 대조를 다시 한다.
--
-- ★★ **시간 컬럼을 `TIMESTAMPTZ` 로 «아직» 바꾸지 않는다.**
--   제품 SQL 은 시각을 ISO 문자열로 넣고 «없음» 을 `''` 로 쓴다
--   (`consumed_at=''`, `effective_from DEFAULT ''`). 타입만 먼저 바꾸면 그 SQL 이
--   그 자리에서 깨진다 — `timestamptz` 는 `''` 와 비교되지 않는다.
--   ⚠️ 그 전환은 **이관 변환과 조건절을 «함께»** 고쳐야 하는 별건이다. 한쪽만 바꾸면
--     모든 티켓이 이미 쓴 것으로 보이거나 반대로 무한 재사용된다. 실제 PG 에서
--     대조하며 할 일로 남긴다(P03.3). 지금은 **첫 경로가 SQL 무변경으로 도는 것**이 목표다.
--
-- ⚠️ 외래키를 걸지 않는다. SQLite 정본에 없고, 여기서만 걸면 **PG 에서만 INSERT 가
--   실패하는** 경로가 생긴다. 제약을 더하는 것은 동등성을 깨는 변경이라 따로 다룬다.
--
-- ⚠️ 값·토큰은 담지 않는다. 티켓은 **해시만** 저장한다(원문은 URL 로 오가므로 접근 로그·
--   리퍼러에 남는다 — 저장소까지 원문을 두면 유출면이 하나 더 는다).
-- ══════════════════════════════════════════════════════════════════════

BEGIN;

-- ── 주체 ─────────────────────────────────────────────────────────────
-- ⚠️ 컬럼 이름은 `hash` 다. 첫 판에 `password_hash` 라고 «더 좋은 이름» 으로 적었는데,
--   제품 SQL 은 `hash` 를 읽는다 — 이름을 고치려면 SQL 도 같이 고쳐야 한다.
CREATE TABLE IF NOT EXISTS auth_credential (
    user_id     TEXT PRIMARY KEY,
    salt        TEXT NOT NULL,
    hash        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- ── 세션 ─────────────────────────────────────────────────────────────
-- ⚠️ 주키는 `token` 이다(첫 판은 `session_id` 였다). 원문 토큰으로 지우고, 조회는
--   `token_hash` 로 한다 — 이벤트마다 「그 세션이 살아 있는가」를 물어야 하는데
--   원문으로만 찾을 수 있으면 전 세션을 훑어야 한다.
CREATE TABLE IF NOT EXISTS auth_session (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    token_hash  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_session_hash ON auth_session(token_hash);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_session(user_id);

-- ── SSE 접속표 ───────────────────────────────────────────────────────
-- ★★★ 이 표의 계약이 이관에서 **가장 잃기 쉬운 것**이다.
--   소비는 «정확히 한 번» 이어야 하고, 그것을 보장하는 것은 아래 한 문장이다:
--
--     UPDATE auth_sse_ticket SET consumed_at = ?
--      WHERE token_hash = ? AND consumed_at = '' AND expires_at >= ? AND audience = ?
--     -- 그리고 «바뀐 행 수» 로 판정한다.
--
--   「읽고 → 확인하고 → 쓰기」로 나누면 두 요청이 그 사이를 통과해 **같은 표로 둘 다
--   연결**된다. 인스턴스가 늘수록 쉬워진다.
--   ⚠️ 응용 메모리 lock 은 다중 인스턴스에서 **아무것도 보장하지 않는다.** 조건절이 진짜다.
CREATE TABLE IF NOT EXISTS auth_sse_ticket (
    token_hash      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT '',
    scope_node_id   TEXT NOT NULL DEFAULT '',
    entity_mode     TEXT NOT NULL DEFAULT '',
    context_version TEXT NOT NULL DEFAULT '',
    audience        TEXT NOT NULL DEFAULT 'sse',
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    consumed_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ticket_expires ON auth_sse_ticket(expires_at);
-- 미사용 표만 자주 찾는다 — 부분 인덱스가 그 질의에 맞는다.
-- ⚠️ 조건이 `IS NULL` 이 아니라 `= ''` 인 것은 위 타입 결정과 «짝» 이다. 하나만 바꾸면
--   인덱스가 질의에 안 맞아 조용히 느려지거나 안 쓰인다.
CREATE INDEX IF NOT EXISTS idx_ticket_unconsumed
    ON auth_sse_ticket(token_hash) WHERE consumed_at = '';

-- ── 조직 문맥 ────────────────────────────────────────────────────────
-- ★ auth 표만 옮기면 로그인 뒤 화면이 성립하지 않는다. 문맥 확인이 조직 계층을 탄다.
-- ⚠️ 회사 이름 컬럼은 `name_ko` 다(첫 판은 `name`). tenant 이름은 tenant 가 갖는다 —
--   법인이 여럿일 때 「어느 법인 이름을 회사 이름으로 쓸까」는 답이 없기 때문이다.
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name_ko     TEXT NOT NULL,
    legal_name  TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- ⚠️ 첫 판에 **통째로 빠져 있던 표.** 문맥 조회가 법인을 타므로 이것이 없으면
--   로그인은 되는데 화면이 서지 않는다.
CREATE TABLE IF NOT EXISTS enterprise_entities (
    entity_id       TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    entity_type     TEXT NOT NULL DEFAULT 'legal_entity',
    entity_mode     TEXT NOT NULL DEFAULT 'REAL',
    legal_name      TEXT DEFAULT '',
    name_ko         TEXT NOT NULL,
    industry_code   TEXT DEFAULT '',
    base_entity_id  TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    effective_from  TEXT DEFAULT '',
    effective_to    TEXT DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 1,
    approved_by     TEXT DEFAULT '',
    approved_at     TEXT DEFAULT '',
    source_ref      TEXT DEFAULT '',
    evidence_ref    TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_ctx ON enterprise_entities(tenant_id, entity_mode, status);
CREATE INDEX IF NOT EXISTS idx_ent_base ON enterprise_entities(base_entity_id);

CREATE TABLE IF NOT EXISTS organization_nodes (
    node_id           TEXT PRIMARY KEY,
    entity_id         TEXT NOT NULL,
    tenant_id         TEXT NOT NULL DEFAULT 'tenant_default',
    node_type         TEXT NOT NULL,
    code              TEXT DEFAULT '',
    name_ko           TEXT NOT NULL,
    default_parent_id TEXT DEFAULT '',
    path_hint         TEXT DEFAULT '',
    dept_id           TEXT DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'DRAFT',
    effective_from    TEXT DEFAULT '',
    effective_to      TEXT DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_node_parent ON organization_nodes(default_parent_id);
CREATE INDEX IF NOT EXISTS idx_node_entity ON organization_nodes(entity_id);
CREATE INDEX IF NOT EXISTS idx_node_dept   ON organization_nodes(dept_id);
CREATE INDEX IF NOT EXISTS idx_node_ctx    ON organization_nodes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_node_code   ON organization_nodes(code, status);

-- 업무 코드의 **변경 이력과 별칭.** 옛 코드로 저장된 외부 연계·문서·사람의 기억은
-- 코드가 바뀌는 순간 끊기고, 끊긴 참조는 «없음» 으로 보여 «권한 없음» 과 구분되지 않는다.
-- ⚠️ 첫 판은 `(alias, node_id)` 두 컬럼뿐이었다. 정본은 별칭에 이력(누가 언제 왜)을 담는다.
CREATE TABLE IF NOT EXISTS organization_node_code_aliases (
    alias_id     TEXT PRIMARY KEY,
    node_id      TEXT NOT NULL,
    code         TEXT NOT NULL,
    tenant_id    TEXT NOT NULL DEFAULT 'tenant_default',
    replaced_by  TEXT NOT NULL DEFAULT '',
    reason       TEXT NOT NULL DEFAULT '',
    recorded_at  TEXT NOT NULL,
    UNIQUE (node_id, code)
);
CREATE INDEX IF NOT EXISTS idx_alias_code ON organization_node_code_aliases(code, tenant_id);

-- ⚠️ 계층은 «간선» 으로 둔다. 부모 컬럼 하나로 두면 다중 소속·이력을 못 담는다.
--   첫 판의 `parent_id/child_id/edge_type` 은 제품이 쓰는 이름이 아니었다 —
--   정본은 `from_node_id/to_node_id/relation_type` 이고 유효기간·상태를 함께 갖는다.
CREATE TABLE IF NOT EXISTS organization_edges (
    edge_id         TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    from_node_id    TEXT NOT NULL,
    to_node_id      TEXT NOT NULL,
    relation_type   TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    effective_from  TEXT DEFAULT '',
    effective_to    TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TEXT NOT NULL,
    UNIQUE (from_node_id, to_node_id, relation_type, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_edge_from ON organization_edges(from_node_id, relation_type, status);
CREATE INDEX IF NOT EXISTS idx_edge_to   ON organization_edges(to_node_id, relation_type, status);

COMMIT;

-- ⚠️ 여기에 없는 것: `enterprise_profiles`·process schema(첫 경로 밖) · 큐/lease/fencing ·
--   durable SSE 이벤트 · 파일 manifest. **첫 경로 완료와 전체 이관 완료는 다르다.**
