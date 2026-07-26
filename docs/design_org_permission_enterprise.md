# 조직 구성 · 권한 · 부서별 게시 · 전사 데이터 표준 · 전사 검색/시뮬레이션

> ⚠️ **후속 문서 있음**: `docs/design_backbone_system_platform.md` (기간계 업무시스템 전환).
> 그 문서가 이 설계의 **암묵 전제 하나를 뒤집는다** — 이 문서의 "한 판 DB"는 *팩토리의* 데이터이며,
> **생성된 앱들의 업무 데이터는 아직 존재하지 않는다.** 또한 Phase 6(생성 시 권장·게시 시 정합화)은
> 공용 쓰기 저장소 단계에서 "생성 시 강제"로 **재판정 대상**이고, Phase 8(재사용·포크)은
> 다부서 기간계보다 **하위 개념으로 우선순위가 내려간다.** 착수 전 그 문서를 먼저 읽을 것.
>
> **그 문서 §10(제3자 검토)이 이 설계서에 직접 지시하는 정정 3건** —
> ① **`ownership.nature` 컬럼 삭제**(분류축이 4개로 난립. `app_class`/`visibility`/`relevance` 3축으로 확정)
> ② **`key_crosswalk` PK 확장을 "리스크"가 아니라 "③ 진입 시 필수"로 승격**(한 앱의 여러 엔티티×표준필드 매핑 표현 불가)
> ③ **Phase 5 프롬프트 주입 규칙 개정** — 현 "자기 부서+조상만" fail-closed 는 **다부서 앱 생성을 막는다.**
> `participants` 에 등록된 부서 스코프도 주입 허용에 포함해야 한다.

> **문서 상태**: 설계 확정 (사용자 승인 완료) · **미착수**
> **작성일**: 2026-07-25
> **기준 커밋**: `a18242fb7`
> **선행 조건**: 이 설계는 A-1 완주 실측 이후에 착수한다(방향 선언 §2 "기능 동결 + 완주 우선").
> 라인 번호 참조는 위 커밋 기준이며, 착수 시점에 재확인할 것.

## Context

### 왜 지금 이 작업인가

이 시스템의 두 주요 기능(SW 생성 / 시뮬레이터 생성·시뮬레이션)에는 **누가 만들었고 누가 쓸 수 있는지에 대한 개념이 전혀 없다.** 인증·사용자·권한 코드가 저장소에 단 한 줄도 없고(전수 grep 확인), 모든 프로젝트가 `projects/` 디렉터리 스캔으로 전원에게 동일하게 노출된다.

목표는 **부서별로 산출물을 게시·격리해서 쓰면서도, 그 아래 데이터베이스는 한 판으로 유지**하는 것이다. 그래야 부서별 개별 인터페이스 없이 전사 기준으로 데이터가 자동 취합되고, 전사 검색·전사 시뮬레이션·경영진 총괄이 가능해진다.

### 확정된 요구사항 (사용자)

1. **인증 = 경량 사용자 전환.** 비밀번호/세션 없음. 헤더로 식별. 나중에 진짜 로그인/SSO로 교체 가능하게 추출 지점 단일화.
2. **권한은 백엔드 API 레벨 강제.** 목록은 서버가 걸러 반환, 무권한 접근 403, **LLM 프롬프트·검색 경로에도 같은 규칙**.
3. **조직 = 계층 조직도** (본부→팀 트리, 상위가 하위 산출물을 봄).
4. **부서는 절대 하드코딩 금지 — 기준정보로 관리.** 언제든 변경 가능.
5. **데이터 표준: 생성 시점엔 권장, 게시 시점에 정합화.** 생성할 때는 표준을 참고자료로 제공하되 강제·차단하지 않는다. **결과물을 게시할 때 전체 DB 기준으로 표준화 매핑과 신규 필드 편입을 수행**한다.
6. **권한 3축 분리** — `executive`(전사 업무 총괄) / `admin`(시스템 설정) / **`DA`(데이터 관리자 — 전체 DB 확인 + 표준화 관리, 시스템 공통 기능)**.
7. **일반 사용자는 전체 DB를 검색엔진으로 검색해 정보 추출**할 수 있어야 한다.
8. **전사 시뮬레이션 3종** — (a) 부서 결과 롤업·불일치 대조, (b) 전사 단일 시뮬 신규 실행, (c) 전사 검색.
9. **재사용·포크로 사일로 중복 생성 방지** — 부서마다 유사 기능을 각자 만드는 것을 막기 위해, **기존 결과물을 복사해 가져오고 그 복사본을 추가 수정·보완**할 수 있어야 한다.
10. **PRD 기준 유사 산출물 판정** — 요구사항 분석 에이전트가 PRD를 작성하면 **그 PRD로 기존 산출물과 유사도를 판정**해, 임계(기본 90점) 이상이면 **"이미 유사한 기능이 있다"고 안내하고 재생성 대신 복사·수정하도록 유도**한다. (Phase 8-2)

### 이미 갖춰져 있는 것 (설계의 출발점)

**"한 판 DB"는 새로 만들 게 아니라 이미 현실이다:**

| 저장소 | 스코프 | 근거 |
|---|---|---|
| `data/master/master.db` | **전역** — M1 기준정보 + M2 크로스워크가 같은 파일, project_id 컬럼 자체가 없음 | `core/master_data.py:32-102` |
| `data/chroma_db` | 전역 `project_releases` + 팩별 `kp_<pack_id>` | `core/knowledge_base.py:69-72, 96-116` |
| `data/mcp_cache.db` | **전역** | `core/mcp_broker.py:17` |

프로젝트별 차별화는 **`master_domains` 태그 하나**로만 이뤄진다(`core/master_data.py:501`). 즉 격리 계층을 만드는 게 아니라 **이미 통합된 데이터 위에 권한 뷰를 씌우는** 작업이다.

**데이터 표준의 원천이 이미 M1에 데이터로 적재되어 있다** (`docs/master_data/global_standard_m3.json` → `scripts/api_data_loader.py:164-191`):

| 표준 | M1 타입 | 역할 |
|---|---|---|
| KS X 9101 `data_model_dictionary_part1` | `standard_field` | **필드명 표준** — `standard_field_code` + `legacy_mappings`(별칭으로 적재) |
| ISO 22400 `iso22400_kpi_dictionary` | `kpi` | **KPI 산식 표준** — `kpi_id/formula/threshold_alert_below` |
| ESG/CBAM `emission_factors` | `emission_factor` | **단위 표준** |
| PdM `pdm_sensor_schema` | `sensor_spec` | **단위·임계 표준** |
| AAS `semantic_id_dictionary` | (지식허브) | **식별자 표준** |
| KS X 9101 Part2 | (지식허브) | `data_ownership`·`security_level`·`retention_period_years` — **거버넌스 표준** |

로더 주석(`scripts/api_data_loader.py:189`)에 이미 **"`legacy_mappings`를 별칭으로 → 크로스워크(M2) 자동 매핑 후보로 활용"** 이라는 의도가 적혀 있다. 이 설계는 그 의도를 실행하는 것이다.

**🔑 데이터 카탈로그를 위한 신규 테이블이 필요 없다.** M2 스키마 레지스트리가 정확히 그 구조다:

| 테이블 | DDL | 카탈로그에서의 역할 |
|---|---|---|
| `external_systems` | `master_data.py:66-69` | **등록된 DB 1건** = 게시된 앱 1건 (`system_id`, `scope`, `status`) |
| `external_schemas` | `:77-89` | 그 DB의 **스키마**(entity/field/type/is_key) + **`mapped_type`/`mapped_attr` = 대응 표준** |
| `crosswalk_proposals` | `:91-101` | **표준 편입 대기 큐** (pending/approved/rejected) |
| `key_crosswalk` | `:70-74` | **승인된 매핑** — `(master_code, system_id)` PK로 "우리 표준코드 ↔ 그 앱의 필드" |

즉 **게시된 앱을 `external_systems`에 등록하면 그대로 전사 데이터 카탈로그가 되고**, DA 콘솔은 기존 `CrosswalkPanel`의 확장이 된다.

**부서 taxonomy·게시판·경영진 화면의 씨앗도 있다**: `create_mega_project`의 8부서 하드코딩(`factory_control.py:304-337`), `library/` + 런처 "📦 결과물 라이브러리" 탭(`App.tsx:525-565`), `MegaBoardroomPanel`, `skills/sim_supervisor.md`(CEO Go/No-Go + 부서별 지시).

### 반드시 먼저 해결해야 하는 것

**권한을 얹는 순간 정보 유출이 된다.** `get_relevant_context()`(`core/knowledge_base.py:401-423`)가 전역 `project_releases` 컬렉션을 **프로젝트 필터도 거리 임계값도 없이** 검색해 상위 3건을 **모든 프롬프트에 주입**한다(`core/context_engine.py:50`). 같은 파일의 `get_grounding_context()`(`:282-327`)는 팩 화이트리스트 + `RELEVANCE_CUTOFF=0.65` 이중 방어가 이미 되어 있으므로 **그 검증된 패턴을 이식하는 것이 해법**이다.

---

## 핵심 설계 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 조직/권한/카탈로그 저장소 | **`data/master/master.db`에 추가** (모듈은 `core/org_directory.py`로 분리) | "한 판" 철학. `_init_db()`가 `executescript(_DDL)` + 전부 `IF NOT EXISTS`(`master_data.py:124-131`)라 **새 테이블 추가가 곧 멱등 마이그레이션** |
| 부서 관리 | **`master_records`와 동일 거버넌스** — PK `(dept_id, version)` / `valid_from·to` / `supersedes` / soft-retire + `entity_types`에 `department` 등록. **하드코딩 맵 3개 삭제** | 요구 4. 부서 개편 이력이 보존돼야 과거 산출물의 소유 부서 해석이 가능 |
| 부서 트리 | **materialized path** (`path`, `depth`) | 권한 상속이 접두 매칭 1쿼리, 순환 검사 O(1) |
| 접두 매칭 | **GLOB (LIKE 금지)** | `dept_id`가 `_`를 허용하는데 LIKE에서 `_`는 와일드카드. **동일 근거 선례**: `factory_control.py:527,537` |
| 데이터 표준 | **생성=권장(차단 없음) / 게시=정합화 / DA 배치=전사 정리** | 요구 5 (아래 Phase 6) |
| 표준화 수행 방식 | **코드를 고치지 않고 `key_crosswalk` 매핑으로 해결** | 게시 시점에 필드명을 바꾸면 이미 동작하는 앱이 깨진다. 앱은 `cust_nm`을 계속 쓰되 전사 DB가 그것이 `STD-CUSTOMER-NAME`임을 안다 — **M2 크로스워크의 원래 목적** |
| 데이터 카탈로그 | **M2 스키마 레지스트리 재사용** (신규 테이블 0) | 위 표 참조 |
| **관련성 판정** | **앱을 분류하지 않고 데이터 겹침을 계산** — 등록은 전부, 표준화 큐는 신호 있는 것만. 분류는 저장 상태가 아니라 `reconcile` 마다 **재계산** | 요구 5 후속 질문. "이 앱이 의미 있나"는 주관적이라 오판하지만 "다른 곳도 같은 데이터를 쓰나"는 계산 가능. 오분류가 영구 손실이 되지 않도록 자동 승격 (Phase 6-7) |
| **사일로 방지** | **차단이 아니라 "가져다 고치는 게 새로 만드는 것보다 쉽게"** + 중복 생성은 막지 않되 **지표로 가시화** | 요구 9. 차단은 우회를 낳지만 가시성은 행동을 바꾼다 (Phase 8) |
| 권한 축 | `viewer<member<manager`(부서) ⟂ **`executive`**(전사 업무) ⟂ **`admin`**(시스템 설정) ⟂ **`DA`**(전체 DB·표준 관리) | 요구 6 |
| 카탈로그 가시성 | **메타데이터(스키마·필드·소유부서)는 전사 공개 / 산출물 본문은 dept 스코프** | 요구 7 "일반 사용자가 전체 DB 검색". 어떤 데이터가 어디 있는지는 알아야 찾고, 내용 열람은 권한을 따른다 |
| 식별 추출 | **`api/deps.py`의 `current_principal` 단일 함수** | SSO 이행 시 이 함수 1곳 + 미들웨어 1개, 라우트 무수정 |
| 하위호환 스위치 | `config.ORG_ENFORCE` **기본 False** + `departments` 비면 `unrestricted` | 하위호환 계약 = 테스트 호환 계약 |
| react-router | **도입하지 않음** | fetch 78곳 + early-return 체인에 URL 라우팅은 회귀 위험 > 이득 |

---

## Phase 0 — 선행 결함 수정 (기능 변화 0)

**P0-1. `_write_project_meta`의 `knowledge_pack_ids` 유실** — `factory_control.py:112-137`. `master_domains`/`mcp_live_grounding`은 None이면 보존(`:117-126`)하는데 `knowledge_pack_ids`는 보존 로직이 없어 `:132`에서 `[]`로 초기화. **Phase 3 ownership 라우트가 이 함수를 부르면 지식팩 연결이 날아간다.** → `_prev` 보존 대상에 편입. **Phase 3 블로커.**

**P0-2. `create_release`가 `artifacts`를 담지 않음** — `:932-949`. `artifacts`는 `:975-978`에서 Chroma 인덱싱 입력으로만 소비되고 파일에 안 남는다. → `artifacts`/`artifact_summaries` 추가. **Phase 6 게시 정합화 + Phase 9 롤업의 입력원. 블로커.**

**P0-3. `GET /{pid}/traceability`의 파일 생성 부수효과** — `:821-831`. `TraceabilityManager` 생성자가 `os.makedirs` + `_init_if_not_exists()`(`nodes/utils/traceability_manager.py:211-217`)를 해서 조회만 해도 파일을 만든다. → 순수 로더 `read_mappings()`(`:55`)로 교체. **Phase 4 블로커.**

**P0-4. `master.db` 동시성** — `master_data.py:117-122`가 `PRAGMA foreign_keys = ON`만. → `journal_mode=WAL`, `busy_timeout=5000`.

**검증**: `pytest -q` 258건 그린 + `tests/test_project_meta_preserve.py`, `tests/test_release_artifacts.py`.

---

## Phase 1 — 조직·사용자·권한 (부서 = 기준정보)

### 신규 `core/org_directory.py`

`MasterData` 구조 미러링: 자체 `_ORG_DDL` + `executescript` + `_lock`/`_cache`/`_invalidate()`(`master_data.py:136-139`) + 모듈 말미 싱글턴. `dept_id` 검증은 **`_TYPE_OR_DOMAIN_RE`(`master_data.py:24`) 재사용**.

```sql
-- 부서: master_records(:41-57) 와 동일한 기준정보 거버넌스
CREATE TABLE IF NOT EXISTS departments (
    dept_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    name_ko TEXT NOT NULL,
    parent_id TEXT NOT NULL DEFAULT '',        -- '' = 루트
    path TEXT NOT NULL DEFAULT '',             -- '/hq/sales/domestic/'
    depth INTEGER NOT NULL DEFAULT 0,
    master_domains TEXT DEFAULT '[]',          -- 담당 M1 도메인
    default_template_id TEXT DEFAULT '',       -- 구 domain_templates_map
    domain_agents TEXT DEFAULT '[]',           -- 구 domain_agents_map
    legacy_domain TEXT DEFAULT '',             -- 구 <mega>_<domain> 매핑키
    valid_from TEXT NOT NULL, valid_to TEXT,   -- NULL = 현행
    supersedes TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dept_id, version)
);
CREATE INDEX IF NOT EXISTS idx_dept_parent ON departments(parent_id, status);
CREATE INDEX IF NOT EXISTS idx_dept_path   ON departments(path);

CREATE TABLE IF NOT EXISTS dept_aliases (      -- '원료구매부' = 'procurement'
    alias TEXT NOT NULL, dept_id TEXT NOT NULL, source TEXT DEFAULT 'user',
    PRIMARY KEY (alias, dept_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,                  -- ^[A-Za-z0-9_.@-]{1,64}$
    display_name TEXT NOT NULL,
    primary_dept_id TEXT NOT NULL DEFAULT '',
    is_executive INTEGER NOT NULL DEFAULT 0,   -- 전사 업무 총괄
    is_admin     INTEGER NOT NULL DEFAULT 0,   -- 시스템 설정(조직·사용자)
    is_data_admin INTEGER NOT NULL DEFAULT 0,  -- DA: 전체 DB 확인 + 표준화 관리
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_dept_roles (
    user_id TEXT NOT NULL, dept_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',       -- viewer | member | manager
    PRIMARY KEY (user_id, dept_id)
);
CREATE INDEX IF NOT EXISTS idx_udr_user ON user_dept_roles(user_id);

-- 소유권 미러 (진실원본은 project_meta.json / release.json — 검색 가능한 인덱스)
CREATE TABLE IF NOT EXISTS ownership (
    resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL,
    dept_id TEXT NOT NULL DEFAULT '', owner_user_id TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'dept',   -- 'dept' | 'company' | 'personal'
    nature TEXT NOT NULL DEFAULT '',           -- 사용자 선언: enterprise|local|personal ('' = 미선언)
    relevance TEXT NOT NULL DEFAULT '',        -- 자동 판정(6-7). reconcile 마다 재계산되는 캐시값
    -- 계보(Phase 8): 어디서 포크해 왔는가. 사일로 지표·공용 컴포넌트 후보 산출의 근거
    forked_from_kind TEXT NOT NULL DEFAULT '', -- 'project' | 'release'
    forked_from_id   TEXT NOT NULL DEFAULT '',
    forked_at        TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (resource_kind, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_own_dept ON ownership(dept_id, resource_kind);
CREATE INDEX IF NOT EXISTS idx_own_fork ON ownership(forked_from_id);
```

부팅 시 `entity_types`에 `department`를 멱등 등록(`master_data.create_type` 재사용) → 온톨로지·크로스워크가 부서를 참조할 수 있고 MasterDataPanel과 같은 거버넌스 아래 놓인다.

**`ownership` 미러가 필요한 이유**: ① Chroma 결과는 `project_id`만 갖고 과거 인덱스에 dept가 없어 O(1) 폴백 필요, ② `get_projects()`·`list_releases()`가 이미 전량 `os.listdir` + 파일 오픈이라 정렬·페이지네이션을 얹으면 감당 불가, ③ 어긋날 때 `POST /api/v1/org/reconcile`로 재구축.

### 🔥 하드코딩 제거 (요구 4의 핵심)

`factory_control.py:304-337`의 맵 3개(`domain_agents_map:304-313`, `domain_templates_map:317-326`, `domain_ko_map:328-337`)를 **코드에서 완전히 삭제**하고 `create_mega_project`가 `departments`를 조회하도록 바꾼다. 최초 1회 `POST /api/v1/org/seed`가 적재(멱등). 부서를 추가·개명·이동·폐지해도 코드 수정이 없어진다.
**부서 삭제는 물리 삭제가 아니라 soft-retire**(`master_data.retire_record:376-393` 패턴) — `ownership.dept_id`가 참조하므로 과거 산출물의 소유 부서 해석이 깨지면 안 된다.

### 순환 참조 방지 (3중)

**가드1** `parent_id == dept_id` 거부 / **가드2(핵심)** 이동 시 `new_parent.path.startswith(self.path)`면 거부 — 자기 자손을 부모로 삼는 것을 O(1) 차단 / **가드3** 부모 미존재·`ORG_MAX_DEPTH`(=8) 초과 거부.
이동 시: `UPDATE departments SET path = ? || substr(path, length(?)+1), depth = depth + ? WHERE path GLOB ? || '*' AND status='active'`

### 권한 해석 — `AccessScope`

```python
@dataclass(frozen=True)
class AccessScope:
    user_id: str; display_name: str
    is_executive: bool; is_admin: bool; is_data_admin: bool
    readable_dept_ids: frozenset[str]; writable_dept_ids: frozenset[str]
    primary_dept_id: str
    unrestricted: bool           # 모든 필터 no-op (하위호환)
    can_run_enterprise: bool     # 전사 롤업·시뮬·승인
    can_edit_org: bool           # 조직·사용자 편집
    can_manage_standard: bool    # DA: 표준 사전·카탈로그·매핑 승인
```

1. `departments`가 비면 → `unrestricted=True` 즉시 반환. **조직 미도입 상태에서 지금과 100% 동일 동작.**
2. `is_admin` → `unrestricted`, `can_edit_org`, `can_run_enterprise`, `can_manage_standard` 전부 True.
3. **`is_executive`** → 전 부서 read + `can_run_enterprise=True`. **`can_edit_org=False`, `can_manage_standard=False`.**
4. **`is_data_admin`(DA)** → **전체 DB 카탈로그·표준 전권**(`can_manage_standard=True`) + 카탈로그 메타 전사 열람. **조직 편집·전사 시뮬 실행 권한은 없음.**
5. 일반: 부서 집합 `D`의 각 `path`로 **GLOB 접두 확장** → `d`와 모든 하위가 readable(상위→하위 상속). `writable` = `role ∈ ('member','manager')`. `viewer`는 읽기만.
6. 무소속 등록 사용자 → `readable={}` + `ownership.owner_user_id` 매칭분.

캐시 `_scope_cache`, 조직 쓰기 시 `_invalidate()`.

### 신규 `api/routes/org_control.py` (prefix `/api/v1/org`)

응답 봉투는 리포 관례 `{"status":"success","data":...}`, 오류 매핑은 **`master_control.py:20-25` `_domain_err` 복제**, 동기 SQLite는 `to_thread`.

```
GET  /tree · /departments · /departments/{id}/history     조회(스코프 내) · 개편 이력
POST/PUT/DELETE /departments[/{dept_id}]                  (can_edit_org, 순환 검사, soft-retire)
GET/POST/PUT/DELETE /users[/{user_id}] · PUT /users/{id}/roles   (can_edit_org)
GET  /me            현재 principal + 스코프 (프론트 게이팅)
POST /seed          하드코딩 맵 → departments 최초 적재 (멱등)
POST /reconcile     파일 → ownership 미러 재구축
```

### `config.py` 추가

```python
ORG_ENFORCE             = os.getenv("ORG_ENFORCE", "false").lower() == "true"   # 기본 off
ORG_USER_HEADER         = os.getenv("ORG_USER_HEADER", "X-Factory-User")
ORG_TRUST_HEADER        = os.getenv("ORG_TRUST_HEADER", "true").lower() == "true"
ORG_DEFAULT_USER_ID     = os.getenv("ORG_DEFAULT_USER_ID", "")
ORG_UNASSIGNED_POLICY   = os.getenv("ORG_UNASSIGNED_POLICY", "public")
ORG_MAX_DEPTH           = int(os.getenv("ORG_MAX_DEPTH", "8"))
RAG_PAST_CASES_ENABLED  = os.getenv("RAG_PAST_CASES_ENABLED", "true").lower() == "true"
RAG_PAST_CASES_CUTOFF   = float(os.getenv("RAG_PAST_CASES_CUTOFF", "0.65"))
MASTER_INJECT_ITEMS_CAP = int(os.getenv("MASTER_INJECT_ITEMS_CAP", "60"))
MASTER_INJECT_CHARS_CAP = int(os.getenv("MASTER_INJECT_CHARS_CAP", "15000"))
STANDARD_ADVISORY_ONLY  = os.getenv("STANDARD_ADVISORY_ONLY", "true").lower() == "true"  # 생성 시 권장만
STANDARD_AUTOMAP_MIN_CONF = float(os.getenv("STANDARD_AUTOMAP_MIN_CONF", "0.9"))         # 게시 자동매핑 하한
```

---

## Phase 2 — 사용자 식별 주입 (강제는 아직 안 함)

### 백엔드: `api/deps.py` — 단일 추출 지점

```python
def _extract_user_id(request: Request) -> str:
    uid = getattr(request.state, "principal_user_id", "") or ""   # ① 미래 SSO 슬롯(최우선)
    if uid: return uid
    if config.ORG_TRUST_HEADER:
        uid = request.headers.get(config.ORG_USER_HEADER, "") or ""       # ② 경량 전환 헤더
        uid = uid or (request.query_params.get("as_user") or "")          # ③ EventSource/iframe 폴백
    return uid or config.ORG_DEFAULT_USER_ID

async def current_principal(request: Request) -> Principal:
    uid = _extract_user_id(request)
    scope = await asyncio.to_thread(org_directory.scope_of, uid)
    if config.ORG_ENFORCE and not scope.unrestricted and not scope.user_id:
        raise HTTPException(401, "사용자 식별 정보가 없습니다.")
    return Principal(scope)
```

헬퍼: `assert_can_read_dept` / `assert_can_write_dept` / `assert_project_readable` / `assert_project_writable` / `assert_release_readable` / `assert_enterprise` / `assert_can_edit_org` / **`assert_can_manage_standard`** (403), `dept_visible(p, dept_id) -> bool`(목록 필터).

**SSO 이행(라우트 무수정)**: ① `main.py`에 `AuthMiddleware`로 `request.state.principal_user_id` 세팅 → ② `ORG_TRUST_HEADER=false` → ③ `user_id`를 IdP `sub`/사번으로.

### 프론트: `frontend/src/lib/api.ts` + 인터셉터

공통 클라이언트가 없고 raw `fetch()`가 **78곳** 산재, `API_BASE_URL`이 6곳 중복 선언(`ControlPanel.tsx:4`, `CrosswalkPanel.tsx:3-4`, `HOTLInput.tsx:4`, `KnowledgeHubPanel.tsx:3`, `MasterDataPanel.tsx:3-4`, `App.tsx:66`; 정본 `useFactoryStore.ts:132`).

- **2-3a (코드 수정 0으로 전체 커버)** — `main.tsx`에서 `installFetchInterceptor()` 1회. `window.fetch`를 래핑해 **URL이 `API_BASE_URL`로 시작하는 요청에만** `X-Factory-User` 주입. 이 한 줄로 78곳 커버. 최종적으로도 안전망으로 남긴다.
- **2-3b (순수 리팩터링)** — 중복 선언 6곳을 `lib/api.ts` import로 통합. `useFactoryStore.ts:132`의 export는 re-export로 유지해 기존 import 경로를 안 깬다.
- **2-3c (점진 `apiFetch` 치환)** — 403 UX 필요 순. **어느 파일에서 멈춰도 정상.**

`apiUrl(path)`는 SSE/iframe/ZIP 링크용 `?as_user=` 부착.

### `UserSwitcher.tsx` / SSE 필터

`GET /api/v1/org/users` + `/me` 셀렉트. 변경 시 `setActingUser()` → `fetchProjects()`/`fetchReleases()` → **`connectSSE()` 재호출**(SSE는 `?as_user=`가 URL에 박히므로 재연결 필수). 배치는 **런처(`App.tsx:157-571`)·통제실(`:583-641`) 두 곳에 명시 삽입**(fragment로 감싸면 `react-resizable-panels` 레이아웃이 깨질 위험).

SSE: `realtime.py:7-17`에 `Depends(current_principal)` + `subscribe(predicate=...)`. `core/broadcaster.py`의 `self.clients: list[asyncio.Queue]`(`:15`)를 `list[_Client]`로. `broadcast()`는 **직렬화를 여전히 1회만**(`:52-57`) 하고 `put_nowait` 앞에 판정 1줄, `finally` 큐 회수(`:36-42`) 유지. **predicate 예외는 전부 통과 처리** — 필터 버그가 실시간 로그를 죽여선 안 된다. 프론트 기존 필터(`useFactoryStore.ts:732-734`)는 **그대로 둔다**(이중 방어).

---

## Phase 3 — 부서 소유권 1급 속성화 + 게시

**`project_meta.json` (6 → 11 필드)**: `owner_dept_id`, `owner_user_id`, **`visibility`(`dept`|`company`|**`personal`**)**, `nature`(사용자 선언), **`forked_from`**(Phase 8 계보 `{kind, id, release_id, at}`). `_write_project_meta`(`:112-137`)에 파라미터 추가, **모두 None이면 보존**(P0-1의 `_prev`에 편입). `_read_project_meta`(`:96-105`)의 3-튜플 반환은 **바꾸지 않고**(호출부 다수) `_read_project_packs`(`:140-148`) 패턴 그대로 `_read_project_ownership()` 신설. 신규 `PUT /projects/{id}/ownership`(write).

**`ProjectState`** — `state_models.py:66`이 `extra='forbid'`라 **정식 선언 없이는 ValidationError로 즉사**:
```python
owner_dept_id: str = Field(default="", description="소유 부서(권한 스코프 기준). project_meta 가 진실원본")
owner_user_id: str = Field(default=""); visibility: str = Field(default="dept")
```
주입 3곳: ① `_ACCUMULATED_FIELDS`(`:76-81`)에 추가, ② `start_sprint`(`:576-583`) 권위 주입 1줄, ③ **`mega/start_all`(`:449-470`)은 `start_sprint` 라우트를 안 타고** `sub_state`를 직접 쓰므로 **별도 주입 필요**.

**`release.json`** — `create_release`(`:932-949`)에 `owner_dept_id`/`owner_user_id`/`visibility`(**meta가 진실원본**) + P0-2의 `artifacts`. `index_release` 메타(`:995-998`)에도 `owner_dept_id` → **Chroma `where` 필터의 기반**(`knowledge_base.py:355-356`이 str 통과).

**`ownership` 동기화**: `create_project:238` / `create_mega_project:281` / `copy_project:550` / `delete_project:487`(`:496-498` 재사용) / `create_release:904` / `delete_release:1172` / ownership 라우트.

**마이그레이션 `scripts/migrate_org_ownership.py`(멱등)**: 부서 시드 → `projects/*`에서 `<mega>_<domain>` 규약(`:341`)으로 `legacy_domain` 추론 → 메가 마스터는 `hq`+`company` → 독립은 `""` 유지 → `library/*` 동일 → `ownership` upsert. **Chroma 재인덱싱은 하지 않는다**(임베딩 비용); 과거 청크는 `project_id → ownership` 폴백, 선택적 `POST /api/v1/org/reindex-releases`.

**게시판**: `library/`를 확장. `GET /library/list`(`:1133-1155`)에 `dept_id` 쿼리 + 스코프 교집합, 반환에 `owner_dept_id`/`owner_dept_name_ko`. 스캔 루프를 **`_iter_releases()` 순수 제너레이터로 추출** → Phase 7 전사 검색 재사용.

---

## Phase 4 — 백엔드 권한 강제 (`ORG_ENFORCE=True`로 켤 수 있는 상태)

**목록 필터링**: `GET /projects`(`:187-236`)는 루프에서 이미 `_read_project_meta`로 파일을 열므로 `_read_project_ownership()`을 같은 자리에(추가 I/O 실질 0) → `dept_visible()` False면 `continue`. 반환 8 → 10 필드. 지식팩은 `manifest.json`(`knowledge_base.py:130-154`)에 `owner_dept_id` + `list_packs`(`:160-168`) 필터. **템플릿·기준정보·데이터 표준·카탈로그 메타는 전사 공유로 두고 문서화.**

**단건 403** — `_safe_id(...)` 다음 줄에 assert 1줄, 약 21곳:
write `mega/plan:382`·`start_all:430`·`DELETE:487`·`copy:550`·`sprint/start:570`·`pause:626`·`stop:632`·`hotl/resume:639`·`resume-quota:647`·`revision:731`·`heal:745`·`replan:778`·`release:904`·`resimulate:1064` / read `supervisor/chat:658`·`hotl/check:701`·`wbs:808`·`traceability:821`·`impact:833`·`feed:853`·`state/latest:867`·`export:1019`·`library/item:1158,1172`

**🚨 `supervisor_chat()` 부서 유출** — `:688-692`가 **전체 프로젝트 이름(앞 25개)을 LLM 브리핑에 동봉**한다. → `dept_visible` 통과 목록으로 교체, `get_projects()`와 겹치므로 **`_iter_visible_projects(principal)` 공용 헬퍼 추출**.

**🚨 텔레메트리 전역 롤업** — `telemetry_control.py:20-40, 93-121`이 전량 파싱하는데 키가 `project_id`가 아니라 **`project_name`**(`core/llm_gateway.py:197`)이라 dept 매핑 불가. → 단기: **executive/admin 전용 게이트**. 근본 수정은 별도 항목.

**SSE 필터 활성.**

---

## Phase 5 — LLM 프롬프트/검색 경로 권한 ★ Phase 6·7·8·10보다 먼저

**최대 유출 경로**: `context_engine.py:50` → `get_relevant_context`(`knowledge_base.py:401-423`) → `search_similar`(`:377-399`) → `collection.query(...)` ← 전역 `project_releases`, `where` 없음, 거리 임계값 없음.

**3중 방어**
1. **Chroma `where` 필터** — `search_similar(query, n_results=5, where=None, include_distances=False)` **하위호환 파라미터 추가**. `get_relevant_context`가 조립하되 허용 dept = **프로젝트 소유 부서 + 조상 체인**(상속은 "사람의 조회" 규칙, **프롬프트 주입은 자기+조상만** — 횡방향 유출 원천 차단). `""`(레거시 미태깅)는 **여기서 제외**(fail-closed). **폴백**: `$in`/`$or` 미지원 시 `n_results*5` over-fetch → 파이썬 필터 (**`search_packs:256-281`이 이미 이 패턴**).
   ※ `where` 는 dept 필터 외에 **`filename` 필터와 AND 결합**해서도 쓴다 — Phase 8-2 의 PRD 대 PRD 후보 추리기가 `{"filename": "prd.md"}` 로 문서 종류를 좁힌다.
2. **거리 임계값** — `RAG_PAST_CASES_CUTOFF`(기본 0.65 — `get_grounding_context:303-306`과 동일).
3. **전역 킬스위치** — `RAG_PAST_CASES_ENABLED`.

**나머지 경로**(`context_engine.py:47-77`): 기업프로필 전사 공유 / **M1 기준정보**(`:56`) **전사 공유 — dept 컬럼이 없는 것이 곧 "한 판" 설계 의도, 실질 필터는 `master_domains`** / M3 MCP(`:65-72`) 전사 공유(기본 off) / 지식팩(`:53`) **이미 안전**, 유출은 연결 시점 차단(`PUT /projects/{id}/knowledge`에서 팩의 `owner_dept_id` 검증) / 과거사례 RAG 위 3중 방어.

---

## Phase 6 ★ — 데이터 표준: 권장 → 게시 정합화 → DA 배치

### 타이밍 설계 (요구 5 + 제안 2건)

| # | 타이밍 | 성격 | 하는 일 |
|---|---|---|---|
| **T1** | 생성 시점 (Architect·Tech_Lead·개발) | **권장, 차단 없음** | 표준 계약을 참고자료로 프롬프트에 주입. 스캐폴드는 "참조용" 제공이지 강제 아님 |
| **T2 (제안)** | **아키텍처 확정 직후, 코드 작성 전** | **리포트만, 차단 없음** | 아키텍처 산출물의 데이터 엔티티를 표준과 결정론 대조해 **프리뷰**. LLM 0콜. 여기서 미리 보면 T3에서 대량 정합화가 안 생긴다 |
| **T3** | **게시(release) 시점** ★ 주 게이트 | **정합화 수행** | 산출물 스키마를 카탈로그에 등록 + 자동 매핑 + 신규 필드 표준 편입 제안 |
| **T4 (제안)** | **DA 정기 배치** | **전사 정리** | 게시는 프로젝트 단위라 *프로젝트 간* 충돌(영업 `client_id` vs 재무 `customer_no`)이 안 보인다. **DA만 잡을 수 있는 고유 업무** |

### 6-1. 표준 계약 조립기 — 신규 `core/data_standard.py` (LLM 0콜)

```python
def build_standard_contract(domains) -> dict
    """{fields, kpis, units, id_rules, naming} — master.db 결정론 조회.
    fields: master_records[type_id='standard_field'] + aliases(=legacy_mappings)
    kpis  : type_id='kpi' (ISO22400 formula/threshold)
    units : type_id in ('emission_factor','sensor_spec') 의 attributes.unit"""

def normalize_field(name, contract) -> tuple[str, float, str]
    """레거시/변형 필드명 → (표준코드, confidence, 사유).
    1차 aliases 정확일치 = 0.95  (master_data.aliases:58-64, idx_alias:64)
    2차 대소문자·구분자 정규화 후 일치 = 0.9
    3차 3자 이상 양방향 부분포함 = 0.6
    ※ crosswalk._name_match(:237-251) 의 점수 체계와 동일하게 맞춰 재사용성 확보"""

def extract_schema_from_artifacts(workspace_root, files) -> list[dict]
    """생성된 산출물에서 {entity, field, field_type, is_key} 추출(정규식 순수함수).
    SQL DDL / Pydantic / TS interface / JSON 키 4종 패턴.
    traceability_manager.py:15 extract_ids 의 순수함수 스타일."""

def render_contract_block(contract) -> str
    """T1 프롬프트 주입용. master_data._INJECT_HEADER:519-522 의 인젝션 방어 헤더 패턴 +
    '권장' 문구(강제 아님). 표준 필드코드·단위·KPI 산식을 참고로 제시."""

def scaffold_reference_types(contract, domains) -> list[dict]
    """참조용 타입 정의(권장). SQL DDL / Pydantic / TS interface.
    T1 에서 '참고하라'로 제공만 하고 수정 금지 가드는 걸지 않는다."""
```

### 6-2. T1 — 생성 시점: 권장 (차단 없음)

`render_contract_block()`을 `ContextEngine.build_reference_context`(Phase 10에서 신설)에 포함해 Architect·Tech_Lead·개발·시뮬 노드 프롬프트에 주입한다. `scaffold_reference_types()` 결과는 **참고 자료로 제시**하되 `_INCREMENTAL_GUARD` 같은 금지 가드는 걸지 않는다. `STANDARD_ADVISORY_ONLY=true`(기본)면 어떤 게이트도 실패시키지 않는다.

### 6-3. T2 — 아키텍처 직후 프리뷰 (리포트만)

`nodes/planning.py`의 Architect 산출 직후 `extract_schema_from_artifacts()` + `normalize_field()`로 대조해 `state.artifacts["_standard_preview"]`에 리포트를 남긴다(LLM 0콜). 통제실에서 "표준 대조 미리보기"로 노출. **점수·게이트에 반영하지 않는다.**

### 6-4. T3 — 게시 시점 정합화 ★ (요구 5의 본체)

`create_release`(`factory_control.py:904-1009`) 흐름에 정합화 단계를 추가한다. **코드는 절대 고치지 않는다** — 이미 동작하는 앱을 깨뜨리기 때문. 대신 **매핑으로 해결**한다.

```
1. extract_schema_from_artifacts()        산출물에서 entity/field 추출 (LLM 0콜)
2. crosswalk.create_system(               ★ 게시되는 전부, 예외 없이 카탈로그 등재
       system_id=release_id, name=프로젝트명, scope='read', status='inactive')
   crosswalk.add_schema_field(...)        필드마다 등록 (source='release_scan')
3. classify_relevance()                   ★ 6-7 — enterprise | local | island 자동 분류
4. island 면 여기서 끝 (DA 큐 진입 안 함).  enterprise/local 만 아래로:
5. normalize_field() 로 표준 자동 매핑
   confidence >= STANDARD_AUTOMAP_MIN_CONF(0.9) → key_crosswalk 즉시 등록(confirmed=1)
   그 미만 / 미매칭                        → crosswalk_proposals 에 pending 등록
6. 게시는 차단하지 않는다 — 완료하되 릴리스에 '표준 정합화 대기 N건' 배지
```

**★ 등록과 표준화는 분리한다.** 카탈로그 등재는 **예외 없이 전부**(LLM 0콜·사람 0명) — 개인 도구여도 "누가 뭘 만들었는지"는 알아야 중복 개발을 막고 DA의 "전체 DB 확인" 요구가 충족된다. 반면 **DA 검토 큐에는 신호가 있는 것만** 올린다. 전부 큐에 넣으면 DA가 익사하고, 마찰 때문에 사람들이 게시를 회피하게 된다 — **그게 최악이다(섀도 IT).**

2~3단계는 **`crosswalk.create_system`(`:66-82`) / `add_schema_field`(`:134-151`) / `_save_proposals`(`:282-305`) / `approve_proposal`(`:321-342`)을 그대로 재사용**한다. 신규 테이블 0개.
`external_systems.status`가 기본 `inactive`이고 **승인된 매핑이 1건 이상 없으면 활성화가 거부되는 기존 게이트**(`crosswalk.update_system:92-96`)가 그대로 "정합화 완료 판정"으로 쓰인다.

**표준 편입 승인은 DA**(`can_manage_standard`). 승인 시 두 갈래:
- **기존 표준에 병합** → 그 필드명을 `aliases`에 추가(다음부터 자동 매핑됨)
- **신규 표준으로 승격** → `standard_field` 레코드 신규 생성(`master_data.upsert_record`)

### 6-5. T4 — DA 정기 배치 (전사 정리)

`POST /api/v1/catalog/reconcile` — 전 카탈로그를 가로질러:
- **동의어 충돌 탐지**: 서로 다른 `system_id`의 필드가 같은 `master_code`로 매핑됐는데 이름이 다른 경우 → 정규화 후보
- **★ island 승격 감지**: 이전에 island로 분류됐던 것 중 **이제 교차 히트가 생긴 것** → 표준 편입 후보로 승격
- **★ 공용 컴포넌트 후보**: 같은 원본에서 N개 부서가 포크한 것(Phase 8-5)
- **미매핑 누적 리포트**: 부서·시스템별 pending 건수
- **고아 매핑**: 삭제된 릴리스를 가리키는 `key_crosswalk` 행
LLM 0콜 결정론. 결과는 DA 콘솔에 표시.

**★ 승격이 이 설계의 핵심이다.** 오늘 개인 도구였던 것이 내일 다른 부서가 비슷한 걸 만들면 **그 순간 전사 개념이 된다.** 최초 판정의 정확도에 의존하지 않고 시간에 맡기는 구조라, 오분류가 영구적 손실이 되지 않는다. 그래서 **분류는 저장된 상태가 아니라 `reconcile` 마다 재계산되는 값**이어야 한다.

### 6-6. 시뮬레이션 산출물의 표준

**`templates/output_formats.json`에 `enterprise_kpi_json` 포맷 신설**하고 도메인 6 에이전트(`sim_sales`~`sim_finance`)에 바인딩. `_get_format_injection`(`nodes/universal.py:52-59`)이 이미 훅이고 `api/routes/format_control.py`가 레지스트리다. ISO22400 `kpi_id`와 표준 단위를 키로 쓰게 하므로 **Phase 9 롤업의 `extract_kpis` 신뢰도 문제가 근본 해결된다.** 이것도 **권장**(포맷 지시)이지 하드 검증은 아니다.

### 6-7 ★ — 관련성 판정: 앱을 분류하지 말고 데이터의 겹침을 측정한다

**문제**: 사용자가 기준정보와 아무 관련 없는 것(단순 편의 기능, 개인 도구)을 만들어 게시하면 표준화 대상인가? 관련성이 떨어지는지 **어떻게 판단**하나?
실제 사례가 이미 있다 — **A-1 단위 변환기**의 `value`/`fromUnit`/`toUnit`은 제련 기준정보와 무관하다. 그리고 트래커 규칙상 모든 테스트 시나리오가 게시까지 하므로 이런 산출물이 카탈로그에 계속 유입된다.

**"이 앱이 전사적으로 의미 있나"는 주관적이라 반드시 오판한다.** 그런데 중앙 DB 입장에서 실제로 중요한 건 하나뿐이다 — **이 산출물의 데이터를 회사의 다른 곳도 만들거나 쓰는가.** 이건 판단이 아니라 계산이며, `normalize_field` 기계를 그대로 쓴다.

`core/data_standard.py`에 추가 (LLM 0콜):

```python
def classify_relevance(schema_rows, contract, catalog, owner_ctx) -> tuple[str, dict]:
    """'enterprise' | 'local' | 'island' + 신호별 근거. 저장하지 않고 매번 재계산."""
```

| # | 신호 | 산출 |
|---|---|---|
| 1 | **표준 사전 히트율** | 필드 중 `standard_field`/`aliases`에 매칭되는 비율 |
| 2 | **카탈로그 교차 히트** ★ | 다른 `system_id`가 이미 쓰는 `(entity, field)` 와 겹치는 수 |
| 3 | **기준정보 개체 참조** | 엔티티·필드가 M1 골든레코드 별칭과 겹치나 |
| 4 | **소유 맥락** | 프로젝트에 `master_domains`가 있나, 소유 부서가 실 업무 부서인가 |
| 5 | **규모** | 엔티티·필드 수 (3필드짜리 메모장은 애초에 대상 아님) |

**신호 2가 가장 강력하다** — 두 부서가 같은 `(entity, field)`를 쓰면 그건 정의상 전사 개념이고, 한 곳만 쓰면 아니다. **동음이의 방어를 위해 필드 단독이 아니라 `(entity, field)` 쌍으로 본다**(`status`가 주문상태인지 설비상태인지 구분).

| 분류 | 조건 | 처리 |
|---|---|---|
| **enterprise** | 히트율 높음 **또는** 교차 히트 존재 | 정합화 큐 진입, DA 검토 |
| **local** | 약한 신호 | 카탈로그 등재 + **관찰 대상** 표시. `reconcile` 때 승격 재평가 |
| **island** | 신호 없음 + 소규모 | 카탈로그 등재만, 큐 제외 |

A-1을 넣으면 히트율 0% · 교차 히트 0 · 도메인 없음 · 3필드 → **island**. 큐에 안 들어간다.

**사용자 선언**: 게시 폼에 "결과물 성격"(전사 업무 / 부서 내부 / 개인 편의)을 두되 **기본값을 자동 판정으로 프리필**한다. 사람은 틀렸을 때만 고친다. 선언과 자동 판정이 어긋나면 **그 사실을 DA 화면에 표시한다**(숨기지 않는다).

**개인 산출물의 프라이버시** — "매우 개인적인 기능"이라면 그 스키마가 전사 검색에 뜨는 것 자체가 과하다. `visibility`에 **`personal`**을 추가해 **카탈로그에는 등재하되**(승격 감지를 놓치지 않으려면 필수) **전사 검색에서는 소유자와 DA에게만** 보이게 한다.

**초기 상태 주의**: 표준 사전이 3건뿐이라 처음에는 거의 모든 것이 island로 나온다. **이건 오작동이 아니라 정상**이며, 표준 사전이 차고 교차 히트가 쌓이면서 자연히 개선된다.

### 신규 `api/routes/catalog_control.py` (prefix `/api/v1/catalog`) — 시스템 공통 기능

```
GET  /systems                    등록된 전체 DB 목록 (external_systems + 게시 앱 + M1 + 지식팩)
GET  /systems/{id}/schema        해당 DB 의 스키마 (external_schemas)
GET  /standard/contract?domains= 현재 표준 계약
GET  /standard/coverage          표준 사전 커버리지 리포트
GET  /proposals                  표준 편입 대기 큐 (crosswalk_proposals 뷰)
POST /proposals/{id}/approve     병합 or 신규 승격 (can_manage_standard)
POST /reconcile                  T4 전사 정리 배치 (can_manage_standard)
GET  /violations?release_id=     릴리스별 미정합 필드
```

**가시성**: `GET /systems` · `/schema` · `/standard/*` 는 **전사 공개**(메타데이터). 쓰기·승인·배치는 `can_manage_standard`.

**검증**: `tests/test_data_standard.py` — `normalize_field`가 `legacy_mappings`로 교정하고 confidence 점수가 `crosswalk._name_match:237-251`과 일치, `extract_schema_from_artifacts` 4종 패턴, **표준 사전이 비면 게시가 정상 완료되고 전부 pending으로만 쌓임**, 자동매핑 임계값 경계, 승인 시 병합/승격 두 갈래.

---

## Phase 7 — 전사 데이터 검색 (요구 7·8-c)

### 신규 `api/routes/search_control.py` (prefix `/api/v1/search`)

```
GET /api/v1/search?q=&kinds=artifact,record,release,schema,standard&dept_id=&limit=20
```

`asyncio.gather` + `to_thread` 병렬(`master_control.py` 관례):

- **① 산출물** — `search_similar(q, n_results=limit*3, where=scope_where, include_distances=True)` — **Phase 5의 `where` 재사용**. **사람의 조회**이므로 `readable_dept_ids` 전체(상속 포함) 허용. 과거 청크는 `project_id → ownership` 폴백.
- **② 기준정보** — `master_data.list_records(q=q)`(`:271-301`) **그대로 재사용**. 전사 공유. ⚠️ 전건 메모리 로드 후 파이썬 부분일치(`:291-296`)라 느림 → 선택적으로 `name`에 SQL `LIKE` 추가(시그니처 불변).
- **③ 릴리스 메타** — Phase 3의 `_iter_releases()` 재사용.
- **④ 스키마/카탈로그 (요구 7의 본체)** — `external_schemas`를 `entity`·`field`·`mapped_attr`로 검색. **전사 공개** — "어느 부서 어느 앱에 이런 필드가 있다"를 누구나 찾을 수 있다.
- **⑤ 데이터 표준** — 표준 필드코드·KPI 사전 검색.

응답: `{q, scope, artifacts[], records[], releases[], schemas[], standards[], counts{}, elapsed_ms}`.

**가시성 원칙(명시)**: **카탈로그 메타데이터(스키마·필드·소유 부서·표준 매핑)는 전사 공개**, **산출물 본문은 dept 스코프**. 일반 사용자가 전체 DB에서 "무엇이 어디 있는지"는 찾되, 열람은 권한을 따른다.

⚠️ Chroma 임베딩은 지연 로드(`knowledge_base.py:77-95`)라 재기동 후 첫 검색이 수 초 → `elapsed_ms` 반환 + 로딩 인디케이터.

---

## Phase 8 ★ — 재사용·포크 (사일로 중복 생성 방지, 요구 9)

부서마다 비슷한 기능을 각자 만드는 것을 막는 실질 수단. **금지가 아니라 "이미 있는 걸 가져다 고치는 게 새로 만드는 것보다 쉽게" 만드는 것**이 설계 목표다.

### 8-1. 발견 게이트 ① — 아이디어 입력 시 (값싼 사전 경고)

포크 기능보다 **발견이 먼저**다. 있는 줄 몰라서 또 만드는 것이 사일로의 실제 원인이다.

`POST /api/v1/search/similar` — 프로젝트 생성 폼에서 아이디어를 입력하는 순간(디바운스) 호출:
- Chroma `project_releases` 시맨틱 검색 — **Phase 5의 `where` + Phase 7 `search_similar` 재사용**
- 카탈로그 스키마 겹침 — Phase 6-7의 교차 히트 계산 재사용
- 결과 카드: 프로젝트명 · 소유 부서 · `deliverable_type` · 유사도 · **[그대로 사용] [포크해서 수정] [무시하고 새로 만들기]**

**"무시하고 새로 만들기"를 막지 않는다.** 대신 그 선택을 `ownership` 메타에 기록해 DA·경영진 대시보드의 **"중복 생성 강행" 지표**로 집계한다. 차단은 우회를 낳지만 가시성은 행동을 바꾼다.

⚠️ **한 줄 아이디어는 신호가 약하다.** 이 게이트는 값싼 사전 경고일 뿐이며, 여기서 놓친 것은 **8-2 게이트 ②(PRD 확정 직후)** 가 정밀하게 잡는다.

### 8-2 ★ — 발견 게이트 ② : PRD 확정 직후 정밀 판정

**요구**: 요구사항 분석 에이전트가 PRD를 작성하면 그 PRD 기준으로 기존 산출물과 유사도를 판정해, **임계(기본 90점) 이상이면 "이미 유사한 기능이 있다"고 안내**하고 재생성 대신 **복사·수정하도록 유도**한다.

**게이트 ①과의 관계 — 대체가 아니라 2단 구성**

| | 시점 | 입력 신호 | 정확도 | 비용 |
|---|---|---|---|---|
| 게이트 ① (8-1) | 아이디어 입력 | 한 줄 아이디어 | 낮음 | 0 |
| **게이트 ② (여기)** | **PRD 확정 직후** | **FR 목록 · 데이터 엔티티 · 수용기준** | **높음** | 이미 CLARIFICATION→RFP→PRD 콜 소비 |

#### 판정 위치 — 새 노드도 새 인터럽트도 필요 없다

**`Master_PM` 노드에 이미 `hotl_after: True` 가 걸려 있다**(`core/agent_registry.py:66`, stage `PLANNING`). PRD 직후 인터럽트 지점이 이미 존재하므로 **그래프 토폴로지를 건드리지 않고 기존 HOTL 게이트의 payload 만 채운다.**

#### 비교 대상 — PRD 문서 대 PRD 문서

기존 산출물에는 **PRD 원문이 이미 보관돼 있다**: `release.json.prd_summary`(`factory_control.py:940`). 별도 데이터 소스를 섞을 필요 없이 **PRD 대 PRD 한 가지 비교**로 점수가 나온다. FR 목록도 데이터 엔티티도 전부 PRD 안에 있다.

> ⚠️ **Chroma 는 진실원본이 아니라 인덱스로만 쓴다.** `prd.md` 가 인덱싱되지만(`factory_control.py:963`) 1000자 청크로 쪼개져(`core/knowledge_base.py:119-125`) 문서 단위 비교에 부적합하다. **Chroma 는 "어느 릴리스를 볼지" 후보를 추리는 용도**이고, 실제 비교는 `release.json.prd_summary` 전문으로 한다.

**2단 조회**
1. **후보 추리기** — `search_similar(prd_text, where={"filename": "prd.md", ...dept 스코프}, include_distances=True)` 로 상위 N개 `release_id` 확보 (Phase 5-2 의 `where` 재사용, dept 필터와 **AND 결합**)
2. **정밀 비교** — 각 후보의 `release.json.prd_summary` **전문**을 로드해 아래 3요소 대조

릴리스가 적은 초기에는 1단계를 건너뛰고 **`_iter_releases()`(Phase 3에서 추출) 전량 순회**로 충분하다. Chroma 후보 추리기는 릴리스가 많아졌을 때의 최적화이며, 따라서 **콜드 스타트 구간에서는 임베딩 의존이 아예 없다**(재기동 후 첫 검색 수 초 지연도 안 겪는다).

#### 점수 구성 (100점 만점, 전부 PRD 내부 요소, LLM 0콜)

| 요소 | PRD 내 위치 | 배점 | 계산 |
|---|---|---|---|
| **기능 요구(FR) 집합 겹침** | FR-ID 목록 | **60** | 신규 PRD 의 FR 각 항목을 기존 PRD 의 FR 항목들과 임베딩 매칭 → `매칭 FR 수 / 전체 FR 수`. FR 추출은 **`extract_ids`(`nodes/utils/traceability_manager.py:15`) 재사용** |
| 데이터 엔티티 겹침 | 데이터 도메인 절 | 20 | 엔티티명 집합 교집합 비율 |
| 문서 전체 의미 유사도 | PRD 전문 | 20 | 문서 임베딩 코사인 |

FR 집합에 최대 배점을 두는 이유: **사용자에게 설명 가능한 유일한 축**이고, 그대로 gap list 가 되기 때문이다.

**소유 부서·도메인은 점수에 넣지 않는다** — 메타데이터가 유사도를 부풀리면 안 된다. 결과 카드에 "같은 부서 산출물입니다" 같은 **표시 힌트**로만 쓴다.

집합 대조 방식은 **`criteria.py:86-103 _check_fr_coverage`** 와 동일 패턴(정의 집합 vs 구현 집합의 결정론 대조)이다.

#### ★ 진짜 산출물은 점수가 아니라 gap list

임계 통과 여부보다 **"무엇이 이미 있고 무엇이 없는가"** 가 핵심이다. 그것이 곧 다음 행동이 된다.

> **유사 기능 발견 (92점)** — `구매팀 / 원료수입관리 v2`
> 요구한 기능 12개 중 **10개가 이미 구현**되어 있습니다.
> **없는 것 2개**: `FR-005 관세 자동계산`, `FR-011 환율 스냅샷`

#### 사용자 선택 3지

| 선택 | 동작 |
|---|---|
| **그대로 사용** | 파이프라인 종료, 해당 릴리스로 안내 |
| **포크해서 수정** ★ | 파이프라인 종료 → 8-3 포크 실행 → **gap list 를 `sprint/revision`(`factory_control.py:731-744`) feedback 으로 자동 주입** → 기존 앱 + 부족한 2개 기능으로 증분 개발 |
| **무시하고 새로 생성** | 계속 진행. 단 `ownership` 에 기록 → **중복 생성 강행 지표**(8-5) |

**포크 선택 시 gap list 가 그대로 revision 지시가 되는 것**이 이 설계의 핵심 연결이다. 요구된 "카피해서 수정하여 사용"이 수작업 없이 성립한다. 8-4 에서 보듯 REVISION 경로는 Architect 를 건너뛰고 Tech_Lead 로 직행하므로 기획을 다시 돌리지 않는다.

#### LLM 확증 1콜 (선택)

결정론 점수로 임계 이상 후보를 추린 뒤, **상위 1건의 PRD 전문과 신규 PRD 전문을 나란히 주고** `output_mode="json"` 1콜로 "정말 동일 기능인가 + 누락 항목은 무엇인가"를 확증한다. **두 문서를 통째로 비교하므로 임베딩 매칭보다 정확하며** gap list 품질이 이 콜에서 결정된다. 후보가 없으면 콜 0.

**점수는 결정론이 매기고 LLM 은 확증·gap 정제만 한다** — LLM 이 점수를 매기면 같은 입력에 다른 값이 나와 임계값 보정이 불가능해진다.

#### 설정값 (`config.py`)

```python
SIMILARITY_GATE_ENABLED   = True   # 게이트 자체
SIMILARITY_GATE_THRESHOLD = 90     # 안내 임계 (0~100)
SIMILARITY_GATE_SHADOW    = True   # ★ 초기 기본: 판정은 하되 게이트를 띄우지 않고 로그만
SIMILARITY_LLM_CONFIRM    = True   # 상위 후보 LLM 확증 1콜
```

**`SHADOW=True` 를 초기 기본으로 둔다** — 90점의 의미가 경험적으로 보정되기 전에는 오탐이 사용자를 막는다. 로그를 쌓아 임계값을 정한 뒤 켠다.

#### 이 게이트의 한계 (반드시 인지할 것)

1. **콜드 스타트** — 검색 대상은 **게시된 릴리스뿐**이다(`index_release`). 현재 `library/` 가 사실상 비어 있어 **초기에는 항상 "유사 없음"** 이 나온다. 오작동이 아니며 자산이 쌓이며 유용해진다.
2. **진행 중 프로젝트는 안 잡힌다** — 두 부서가 동시에 비슷한 것을 만들면 둘 다 미게시라 서로를 못 본다. 게이트 ①도 동일한 사각지대다.
3. **90점은 보정 전까지 임의값** — 임베딩 코사인은 "90 = 같은 기능"으로 교정돼 있지 않다. shadow 모드와 gap list 병기가 그래서 필수다.
4. **FR 체계를 안 쓰는 PRD** — 비SW 템플릿 등에서는 FR 축(60점)이 계산 불가 → **공허 통과**(`_check_fr_coverage:93-94` 와 동일 정책). 최대 40점이라 임계 미달로 게이트가 뜨지 않는다.

**검증**: `tests/test_similarity_gate.py` (Phase 10 표 참조).

### 8-3. 포크 — 기존 `copy_project`는 그대로 쓰면 안 된다

`copy_project`(`factory_control.py:550-568`)는 `shutil.copytree` 통짜 복사라 포크용으로는 결함이 4개다:

| 문제 | 결과 | 해결 |
|---|---|---|
| `.archive/`·`.git/`·`node_modules` 통째 복사 | 저장소 비대 | **`_EXPORT_EXCLUDE_DIRS`(`:1016`)가 이미 있는데 여기선 안 쓴다** → 재사용 |
| `project_meta.json` verbatim | **포크가 원본의 `owner_dept_id`를 물려받음**(Phase 3 이후) | 포크한 부서 소유로 재작성 |
| `latest_state.json`의 `project_name`이 원본 그대로 | 포크 후 이름·경로 불일치 | `project_name`/`workspace_root` 갱신 |
| 계보 기록 없음 | 사일로 지표 산출 불가 | `forked_from` 기록 |

신규 **`POST /api/v1/factory/library/item/{release_id}/fork`** (게시된 릴리스 기준이 기본 — **검증된 것만 재사용**). 프로젝트 직접 포크는 `POST /projects/{pid}/fork`로 병행 제공.

```
1. 제외 목록 적용 복사              (_EXPORT_EXCLUDE_DIRS:1016 재사용)
2. project_meta.json 재작성          owner_dept_id=포크 부서, owner_user_id=포크한 사람,
                                     visibility='dept', forked_from={kind, source_id, release_id, at}
3. latest_state.json 재작성          project_name·workspace_root 갱신, factory_mode='EXECUTION',
                                     current_sprint_task_id 초기화
4. 체크포인트는 복사하지 않는다      thread_id 가 `sprint_<pid>__<task>` 라 새 pid 면 자연히 빈 상태(깨끗)
5. ownership upsert + 원본 fork 카운트 증가
```

**권한**: 원본 read + 대상 부서 write. 즉 **볼 수 있는 것만 포크할 수 있다** — 권한 모델이 그대로 재사용된다.

### 8-4. 수정보완 — 신규 구현 불필요, 기존 REVISION 경로 그대로

포크 직후 `POST /{new_pid}/sprint/revision {feedback}`(`:731-744`) → `wbs_manager.add_revision_task`가 `TASK_REV_*` 생성 → `start_sprint`가 `:597-598`에서 `factory_mode`를 REVISION으로 강제 → **Architect를 건너뛰고 Tech_Lead 직행**(기획 산출물 재사용). 즉 포크한 앱을 처음부터 다시 만들지 않고 **증분 개선**한다.
`_INCREMENTAL_GUARD`(`nodes/execution.py:161-167`)가 "기존 기능을 하나도 빠뜨리지 말 것"을 강제하므로 포크해온 자산이 재작성 과정에서 유실되지 않는다.

### 8-5. 계보와 사일로 지표

`forked_from`을 `ownership`에 함께 저장해 조회 가능하게 한다.
- `GET /api/v1/catalog/lineage/{resource_id}` — 조상·자손 트리
- **공용 컴포넌트 승격 후보**: 같은 원본에서 **N개 부서가 포크**했으면 그건 전사 공용 기능이다 → Phase 6 T4 `reconcile` 배치에 규칙 추가
- **중복 생성 후보**: 유사도가 높은데 포크가 아니라 새로 만든 것들 → 경영진 대시보드 지표.
  **"강행" 기록은 두 곳에서 발생한다** — 게이트 ①(아이디어 시점, 8-1)과 게이트 ②(PRD 시점, 8-2). 어느 게이트에서 무시했는지 구분해 집계해야 게이트별 실효성을 판정할 수 있다
- 이 두 지표가 8-1의 발견 품질을 사후 검증한다(발견이 잘 됐으면 중복 생성이 줄어야 한다)

### 8-6. 업스트림 드리프트 (정직한 한계)

**원본이 개선돼도 포크는 따라오지 않는다.** 자동 병합은 LLM 산출 코드라 신뢰할 수 없어 이 계획의 범위 밖이다.
최소 조치: 원본에 새 릴리스가 생기면 포크 목록에 **"원본이 v3으로 갱신됨(내 포크는 v1 기준)"** 배지를 띄운다. 반영 여부는 사람이 판단해 `sprint/revision`으로 처리한다.

**검증**: `tests/test_fork.py` — 제외 디렉터리가 복사되지 않음, `owner_dept_id`가 **원본이 아니라 포크 부서**로 설정됨, `forked_from` 기록, 새 pid 의 체크포인트가 비어 있음, read 권한 없는 원본은 403, 포크 후 `sprint/revision`이 REVISION 모드로 진입.

---

## Phase 9 — 전사 롤업 · 불일치 대조 (요구 8-a)

**서브 → 마스터 역방향 수집 신설.** `mega/start_all`(`:430-486`)은 단방향 fan-out이고 역방향이 없다.

**`shared_ledger`를 드디어 읽는 용도로 쓴다** — 이미 `ProjectState`에 선언(`state_models.py:87`)되고 `_ACCUMULATED_FIELDS`(`:80`)에 포함되어 **디스크 복원 경로가 존재**하는, `extra='forbid'`를 피해 새 필드 없이 쓸 수 있는 유일한 dict 슬롯. 키: `["master_data"]`(하향, 기존) / `["dept_results"][dept_id]`(상향, 신규) / `["conflicts"]` / `["directives"]`(Phase 11).

**LangGraph 상태 병합으로는 불가능** — 서브는 각자 별개 thread_id(`core/async_orchestrator.py:20-30`)라 프로세스 상태를 공유하지 않는다. → **디스크 수집**: `POST /api/v1/enterprise/rollup`이 서브들의 `latest_state.json`을 읽어 마스터 `shared_ledger`에 병합. fan-out과 대칭인 fan-in.

**신규 `core/enterprise_rollup.py`** — `traceability_manager.py`의 순수함수 스타일(`read_mappings:55`, `compute_coverage:69`, `impact_of:165`).

```python
def split_cycle_key(key) -> tuple[int, str]    # 'cycle_2_Sales_Agent' -> (2,'Sales_Agent'); :1086-1093 규약
def collect_department_artifacts(dept_ids, projects_dir, library_dir) -> dict
    # ① projects/<pid>/latest_state.json 의 artifacts (nodes/universal.py:108-112)
    # ② library/<rid>/release.json 의 artifacts (P0-2 선행)
    # 부서 매핑: owner_dept_id 우선, 없으면 <mega>_<domain> 폴백
def extract_kpis(text_or_json) -> dict         # enterprise_kpi_json 이면 파싱, 아니면 정규식 폴백
def detect_conflicts(rolled, rules) -> list    # 추출 실패 시 skip, 크래시 금지
```

`CONSISTENCY_RULES` 초기 4종: `DEMAND_VS_CAPA`(영업 수요예측 ≤ 생산 CAPA), `COST_VS_BUDGET`, `LEADTIME_VS_LOGIS`, `YIELD_VS_QUALITY` — 허용오차 포함. **비교 기준은 ISO22400 `kpi_id`**(Phase 6)라 부서마다 다른 지표명 문제가 줄어든다. 다만 표준 정합화가 T3(게시) 이후에야 붙으므로 **미게시 산출물은 정규식 폴백에 의존**한다(한계 명시).

**LLM 대조 1콜로 보강** — **`mega/plan`(`:382-429`)이 정확히 이 패턴**(상태 로드 → 프롬프트 → json 파싱 → 저장)이므로 구조 복제.

---

## Phase 10 — 전사 단일 시뮬레이션 (요구 8-b)

### 실행 엔진은 코드 변경 0으로 이미 존재

`core/agent_graph.py:409-421`의 `domain_agents` 필터는 `if domain_agents and next_node not in framework_agents and next_node not in domain_agents: continue` — **비어 있으면 필터가 안 걸려 전 도메인이 order 순으로 순차 실행된다.** `templates/mfg_sim.json`이 `simulation_framework: true` + `framework_agents`(prep 4/eval 5) + `resim_entry: "Sim_Validator"`를 갖춘 유일한 템플릿이고, `sim_sales → sim_purchase → sim_production → sim_quality → sim_logistics → sim_finance`가 `[Input]/[Output]`으로 **가치사슬 선형 체인을 프롬프트로 강제**한다.

`POST /api/v1/enterprise/simulate` (권한 `can_run_enterprise`):
1. `enterprise_<ts>` 프로젝트를 **`mfg_sim` 하드 지정**으로 생성(`create_project:238-257` 재사용). `owner_dept_id="hq"`, `visibility="company"`.
2. `master_domains` = **전 부서 `departments.master_domains` 합집합** → M1 주입 필터가 전사로 열림.
3. `initial_idea` = 시나리오 + `collect_department_artifacts()` 요약 + `detect_conflicts()` 결과. **(a)의 산출물이 (b)의 입력.**
4. `master_data` = 전사 마스터 데이터 JSON. **universal 노드가 유일하게 읽는 전역 슬롯**(`nodes/universal.py:86-88`).
5. `shared_ledger = {master_data, dept_results, conflicts}`. 6. **`domain_agents = []`**. 7. `orchestrator.start_sprint(...)`.

**What-if는 별도 구현 불필요** — `POST /{pid}/resimulate`(`:1064-1131`)가 그대로 동작(`resim_entry` 덕에 `route_universal:396-401`이 설계 단계를 건너뜀).

### 🚨 F3: universal 노드에 기준정보·표준 주입

`build_core_context`를 그대로 붙이면 안 된다 — 디스크 workspace walk + SW 전용 `*_summary`가 시뮬 프롬프트를 오염시키고 토큰이 폭발한다.
→ **`core/context_engine.py`에 `build_reference_context(state) -> str` 신설(순수 추출 리팩터링)**: `build_core_context`의 3블록(`:47-72` M1 → M3 MCP → 지식팩)을 추출하고 `build_core_context`가 호출. **동작 100% 동일** → `tests/test_context_full_files.py` 무영향. 여기에 Phase 6-1의 `render_contract_block()`을 더한다.
`nodes/universal.py`의 prompt 조립(`:89-100`)에 `reference_block` 추가(지연 임포트로 순환 방지). 이것으로 `sim_production.md`/`sim_quality.md`가 선언한 "M1/M3 기준정보 기반"이 **처음으로 사실이 된다.**
⚠️ **과거사례 RAG는 universal 노드에 넣지 않는다** — 유출 위험 최고 경로이고 시뮬 품질 기여가 불확실.

### 🚨 F4: M1 주입 상한 12건/3000자

`master_data.py:28-30` + `:512-518`의 `break`. 전 부서 기준정보에 절대 부족하고 **`break`(continue 아님)라 긴 레코드 하나가 뒤를 전부 잘라낸다.**
→ **기존 동작을 바이트 단위로 보존하는 파라미터화**: `select_for_injection(..., max_items=None, max_chars=None, skip_oversize=False)`, 기본값은 상수 그대로, `skip_oversize=True`일 때만 `continue`. `render_grounding`(`:524-529`)·`get_master_context`(`:531-547`)에 전달.
**예산 자동 스케일(새 상태 필드 0개)**: 도메인 수 `n`으로 `min(12+8*(n-1), MASTER_INJECT_ITEMS_CAP)` → 1개면 12 그대로, 8개면 60. chars 3000 → 15000. `skip_oversize=(n>=3)`. 스캔 텍스트도 전사 모드에서 각 1500 → 3000자(`:537-542`).

### 부수 결함

- **F5** `manufacturing-production.json`은 `hybrid_simulation`인데 `simulation_framework`가 없어 What-if 미작동, 하필 **메가 기본 템플릿**(`:279`). → 기본값 변경은 파괴적이라 하지 않고 `default_template_id`를 부서 기준정보로 이관(Phase 1) + 프론트에서 `mfg_sim` 기본 제시 + **전사 시뮬은 `mfg_sim` 하드 지정으로 우회**.
- **F6** `default` 외 **모든 템플릿의 참조 skill 30/30 미존재**하고 `_load_skill`(`nodes/universal.py:18-25`)이 조용히 `""`를 반환해 role 한 줄로 실행. → **`skills/sim_marketing.md` 1개 신설** + **관측 먼저**: `GET /templates/{id}`(`:1445`)에 `missing_skills[]` + `AgentMasterPanel` 배지.
- **시뮬 결과 화면** — `isHybrid` PREVIEW 탭이 `frontend_code_summary`를 봐서(`App.tsx:635`) **항상 빈 화면**. → `PreviewPanel.tsx:552-560`에서 `hybrid_simulation`이면 **기본 활성 탭을 `Sim_Insight`로**. 에이전트별 탭 렌더는 이미 존재(`:562-565`).

---

## Phase 11 — 경영진 총괄 (요구 6)

신규 `api/routes/enterprise_control.py` (prefix `/api/v1/enterprise`), 권한 `can_run_enterprise`:
```
POST /rollup · GET /rollup/{mega_id}     부서 결과 수집 + 불일치 대조 (Phase 9)
POST /simulate · GET /simulations        전사 단일 시뮬 (Phase 10)
GET  /dashboard                          전사 총괄: 부서별 진행·산출물 수·표준 정합률·미해결 불일치·쿼터 소비
POST /decision                           CEO Go/No-Go 기록 + 부서별 경영 지시사항 하달
GET  /approvals · POST /approvals/{id}   전사 HOTL 승인 큐
```

**`skills/sim_supervisor.md`를 재사용한다** — 이미 "CEO 관점 Go/No-Go + Executive Summary + **부서별 즉각 실행 조치사항**"을 출력하도록 작성되어 있다. Phase 9의 LLM 대조 1콜과 `/decision`이 이 스킬을 그대로 쓴다.

**하달 경로**: `/decision`의 부서별 지시를 각 부서 프로젝트의 `shared_ledger["directives"]`에 기록 → 다음 스프린트에서 `master_data` 슬롯과 함께 프롬프트에 주입. 즉 **경영진 판단이 실제로 부서 에이전트의 입력이 된다**(현재 `shared_ledger`는 하향으로만, 그것도 `master_data`만 쓰이고 읽는 코드가 0곳).

**프론트**: `MegaBoardroomPanel`(3초 폴링 + 서브 병렬 fetch `:14-43`)을 **`ExecutiveBoardroom`으로 확장** — 부서 카드 그리드 + KPI 롤업 + 불일치 배지 + **표준 정합률** + 전사 시뮬 실행 + Go/No-Go. 런처 탭으로 노출하되 `can_run_enterprise`가 아니면 숨김.

---

## Phase 12 — 프론트엔드 통합

기존 관례(store 플래그 + early-return / 오버레이 모달) 확장. **react-router 미도입.**

| 신규 컴포넌트 | 얹는 방식 | 복제할 패턴 |
|---|---|---|
| `UserSwitcher.tsx` | 런처·통제실 상단 인라인 | — |
| `OrgAdminPanel.tsx` | `showOrgPanel &&` early-return | `AgentMasterPanel`(`App.tsx:120-126`) |
| **`DataCatalogPanel.tsx` (DA 콘솔)** | early-return 전체화면 | **`CrosswalkPanel` 확장** — 등록된 전체 DB 목록 · 스키마 뷰어 · 표준 사전 · 편입 승인 큐 · 충돌 리포트 |
| `EnterpriseSearchPanel.tsx` | 오버레이 모달 | `KnowledgeHubPanel`/`MasterDataPanel` |
| `ExecutiveBoardroom.tsx` | 런처 탭 (`can_run_enterprise` 게이팅) | `MegaBoardroomPanel:14-43` |
| `DeptTree.tsx` | 프리젠테이션 (릴리스 탭 + OrgAdminPanel 공용) | — |
| **`SimilarArtifactHint.tsx`** (Phase 8-1) | 생성 폼 아이디어 입력 **아래 인라인**(디바운스 호출) | — · 카드에 [그대로 사용]/[포크해서 수정]/[무시하고 새로 만들기] |
| **`ForkDialog.tsx`** (Phase 8-3) | 오버레이 모달 — 새 ID·소유 부서 선택 → 포크 후 통제실 진입 | 생성 폼 필드 재사용 |
| **`LineageView.tsx`** (Phase 8-5) | 프로젝트 카드·릴리스 카드에서 펼침 | 조상·자손 트리, 원본 갱신 배지 |
| **`SimilarityGateCard.tsx`** (Phase 8-2) | **신규 패널 아님 — 기존 HOTL 승인 UI(`HOTLInput.tsx`) 안에 카드로 렌더** | 점수·gap list·3지 선택 버튼. 백엔드가 새 인터럽트를 안 만드는 것과 같은 이유로 프론트도 새 화면을 안 만든다 |

**기존 화면 수정**
1. 런처 탭 3 → 5개: `App.tsx:53`에 `"enterprise"`, `"search"` 추가(검색은 모달로 갈 수도).
2. 결과물 라이브러리 탭(`:525-565`) → 부서 게시판: 좌 `DeptTree` + 우 카드 그리드, `GET /library/list?dept_id=`, 부서 배지 + **"표준 정합화 대기 N건" 배지** + **[포크] 버튼**(Phase 8-3) + 포크 수 배지.
3. 프로젝트 생성 폼(`:241-379` 인라인)에 **"소유 부서" 셀렉트** + **선택 시 그 부서의 `master_domains`를 `masterDomainsInput`에 자동 프리필** — 오타로 도메인 필터가 조용히 실패하는 현 문제 완화. 아이디어 입력 시 **`SimilarArtifactHint` 표시**.
3-1. **게시 시 "결과물 성격" 선택**(전사 업무 / 부서 내부 / 개인 편의) — **기본값은 6-7 자동 판정으로 프리필**, 사람은 틀렸을 때만 수정. `personal` 선택 시 전사 검색에서 소유자·DA 외 비노출.
4. **`PUT /projects/{id}/knowledge`를 드디어 호출** — 현재 프론트 호출부 0곳. 프로젝트 카드에 "지식팩·기준정보 편집" 버튼. **P0-1 선행 필수.**
5. `App.tsx:71 isSubProject`는 **그대로 둔다**(하위호환).
6. 403 토스트: `permissionErrors`를 `App.tsx` 최상단에 1개 렌더.

---

## Phase 13 — 하드닝 (본 설계와 독립, 여유 있을 때)

- **텔레메트리 근본 수정** — `core/llm_gateway.py:197`이 `project_name`을 키로 쓰는 것을 `project_id`로 교체(+ 기존 로그 하위호환 파싱). Phase 4의 admin 게이트를 풀 수 있게 된다.
- **`missing_skills[]` 관측** — `GET /templates/{id}`(`:1445`) 응답에 추가 + `AgentMasterPanel` 경고 배지. `default` 외 템플릿의 참조 skill 30/30이 미존재하고 `_load_skill`(`nodes/universal.py:18-25`)이 조용히 `""`를 반환하는 문제를 **보이게** 만든다.
- **`skills/sim_marketing.md` 신설** — `templates/mfg_sim.json`의 `Marketing_Agent`가 참조하는데 파일이 없다.
- **`golden_benchmark`가 `state.artifacts`를 채점하도록 확장** — `_STAGE_ARTIFACT_FIELDS`(`core/golden_benchmark.py:32-38`)가 SW 전용 `*_summary`라 시뮬 산출물이 채점에서 통째로 빠진다.
- **체크포인트 보존 정책** — `pipeline_state.db`가 이미 110MB. 전사 시뮬은 16에이전트 × 사이클이라 증식이 빠르다.

---

## 검증 계획

### 하위호환이 깨지지 않는 구조적 근거

1. `tests/`에 **conftest.py 없음**. `pytest.ini`는 `pythonpath=.` / `testpaths=tests` / `addopts=-q`뿐.
2. `TestClient` 사용 파일은 **`tests/test_template_binding.py` 1개**(전수 확인). 자체 `FastAPI()`에 `include_router(fc.router)`만 하므로 **`main.py` 미들웨어를 타지 않는다**.
3. `Depends(current_principal)`를 붙여도 **헤더 없으면 unrestricted Principal**이라 기존 테스트가 통과.
4. ⚠️ **함정**: `OrgDirectory` 싱글턴이 import 시점에 `data/master/master.db`(상대경로)를 열면 `monkeypatch.chdir(tmp_path)`(`test_template_binding.py:13`) 이후에도 개발자 로컬 실제 DB를 본다. → **`ORG_ENFORCE` 기본 False** + 커넥션 지연 초기화 + `_connect()`마다 경로 재계산.

### 신규 테스트 (전부 LLM 0콜)

| 파일 | 핵심 검증 |
|---|---|
| `test_org_directory.py` | `path`/`depth`, **순환 참조 거부**(A→B→C 후 A의 부모를 C로), 자기참조, `ORG_MAX_DEPTH`, 이동 시 하위 일괄 갱신, **개편이 version 계보로 보존**, soft-retire 후에도 과거 `ownership` 해석 유지 |
| `test_org_scope.py` | 상위→하위 read / 하위→상위·**형제** 불가 / `viewer` write 불가 / **`executive`는 전 부서 read + `can_edit_org=False`·`can_manage_standard=False`** / **`DA`는 `can_manage_standard=True`이나 `can_run_enterprise=False`** / `admin`은 unrestricted / **`departments` 비면 unrestricted** / **`sales` 스코프가 `sales_x` 미포함**(GLOB 회귀) |
| `test_org_enforcement.py` | `ORG_ENFORCE=True`에서 목록 제외·403, **False에서 전부 200** |
| `test_context_leak.py` ★ | fake collection monkeypatch → `collection.query`의 `where`에 dept 필터 **직접 assert**, cutoff, 킬스위치, `where` 미지원 폴백 |
| `test_data_standard.py` ★ | `normalize_field` confidence가 `crosswalk._name_match:237-251`과 일치, `extract_schema_from_artifacts` 4종 패턴, **표준 사전이 비어도 게시가 정상 완료**되고 전부 pending, 자동매핑 임계값 경계, 승인 시 병합(alias 추가)/승격(신규 레코드) 두 갈래 |
| `test_release_catalog.py` | 게시 시 `external_systems`+`external_schemas` 등재, 고신뢰 매핑은 `key_crosswalk` 즉시·저신뢰는 `crosswalk_proposals`, **게시가 차단되지 않음**, `artifacts`/`owner_dept_id` 기록 |
| `test_enterprise_rollup.py` | 수집 정확성, `split_cycle_key` 양방향, dept 폴백, 수요>CAPA면 conflict 1건·오차 내면 0건, `extract_kpis` 실패 시 **크래시 없음** |
| `test_master_inject_budget.py` | 기본 호출이 **파라미터 추가 전과 바이트 단위 동일**, 확대 예산, `skip_oversize`, 도메인 3개↑ 자동 확대 |
| `test_broadcaster_filter.py` | 타 부서 미전달, 전역 통과, **predicate 예외가 broadcast를 안 죽임**, **직렬화 여전히 1회**(`json.dumps` spy), `finally` 큐 회수 |
| `test_search_control.py` | 5소스 병합, **카탈로그 메타는 전사 공개·산출물 본문은 dept 스코프**, 빈 `q`·`kinds` 필터 |
| **`test_relevance_classify.py`** ★ | A-1 스키마(`value`/`fromUnit`/`toUnit`)가 **island** 로 분류, 교차 히트 생기면 **enterprise 로 승격**, `(entity,field)` 쌍이라 동음이의(`order.status` vs `equipment.status`)를 구분, 표준 사전 비면 전부 island(정상) |
| **`test_fork.py`** ★ | 제외 디렉터리 미복사, **`owner_dept_id`가 원본이 아니라 포크 부서**, `forked_from` 기록, 새 pid 체크포인트 비어 있음, read 권한 없는 원본 403, 포크 후 `sprint/revision`이 REVISION 진입 |
| **`test_similarity_gate.py`** ★ | fake Chroma monkeypatch(`test_context_leak.py` 기법). 동일 PRD 2건 → 임계 이상·gap 비어있음 / FR 12개 중 10개 겹침 → FR 축 `60×10/12=50`·gap 2건 정확 열거 / FR 없는 PRD → 축 0점 **공허 통과**(최대 40점, 게이트 미발동) / **Chroma 없이 `_iter_releases()` 전량 순회 경로 동치성** / `SHADOW=True` 면 판정은 하되 게이트 미표시 / 릴리스 0건 콜드스타트 예외 없음 / 스코프 밖 릴리스 후보 제외 / 포크 선택 시 gap list 가 `sprint/revision` feedback 문자열로 변환 |
| `test_project_meta_preserve.py` | `knowledge_pack_ids=None`·`owner_dept_id=None` 시 **보존** |

**최종 목표**: `pytest -q` → 258 + 약 60건 그린.

### 수동 E2E

1. `POST /api/v1/org/seed` → `GET /api/v1/org/tree` → **UI에서 부서 추가·개명·이동** 후 `create_mega_project`가 반영하는지(하드코딩 제거 검증).
2. `scripts/migrate_org_ownership.py` → `GET /projects`가 `owner_dept_id` 반환 + **기존 프로젝트가 하나도 사라지지 않음**.
3. `UserSwitcher`로 영업 사용자 전환 → 네트워크 탭에서 **78곳 요청 전부에 `X-Factory-User`**.
4. `ORG_ENFORCE=true` → 영업 사용자로 재무 프로젝트 `state/latest` **403**, 릴리스 탭에 재무 게시물 미노출.
5. 부서 SW 1건 생성 → **생성은 표준과 무관하게 정상 완료**(권장만) → T2 프리뷰 리포트 확인 → **게시** → `GET /api/v1/catalog/systems`에 그 앱이 등록되고 스키마가 보이는지, 고신뢰 필드는 `key_crosswalk`에 자동 매핑되고 나머지는 `/catalog/proposals`에 뜨는지.
6. **DA 계정**으로 proposal 승인(병합 1건 + 신규 승격 1건) → 다음 게시에서 같은 필드가 **자동 매핑**되는지 → `POST /catalog/reconcile`로 프로젝트 간 동의어 충돌 리포트.
7. **일반 사용자**로 `GET /api/v1/search?q=<필드명>&kinds=schema` → 타 부서 앱의 스키마가 **검색은 되지만** 산출물 본문은 403인지.
8. 경영진 계정으로 `POST /enterprise/rollup` → `POST /simulate` 완주 → `Sim_Insight` 탭 → `POST /decision`으로 부서별 지시 하달 → 해당 부서 다음 스프린트 프롬프트에 반영 확인.

---

## 재사용 자산 (신규 작성 대신)

| 자산 | 위치 | 용도 |
|---|---|---|
| `_DDL` + `executescript` + `IF NOT EXISTS` | `master_data.py:32-102, 124-131` | 조직 테이블 멱등 마이그레이션 |
| `master_records` 버전 계보 (PK `(code,version)`, soft-retire) | `master_data.py:41-57, 343-393` | `departments`를 기준정보로 |
| `aliases` + `idx_alias` | `master_data.py:58-64` | **`legacy_mappings` 기반 필드 자동 매핑** — `api_data_loader.py:189`의 원래 의도 |
| **M2 스키마 레지스트리 4테이블** | `master_data.py:66-101`, `core/crosswalk.py` 전체 | **전사 데이터 카탈로그 — 신규 테이블 0** |
| `crosswalk.create_system`/`add_schema_field`/`_save_proposals`/`approve_proposal` | `crosswalk.py:66-82, 134-151, 282-305, 321-342` | 게시 시 카탈로그 등재·매핑·승인 |
| `crosswalk._name_match` 점수 체계(0.95/0.9/0.6) | `crosswalk.py:237-251` | `normalize_field` confidence 일치 |
| `update_system` 활성화 게이트(승인 매핑 ≥1) | `crosswalk.py:92-96` | "정합화 완료" 판정 |
| `_TYPE_OR_DOMAIN_RE`, `_invalidate()`, `_domain_err` | `master_data.py:24, 136-139`, `master_control.py:20-25` | 검증·캐시·오류 매핑 |
| **GLOB 선례(`_` 오매칭 회피)** | `factory_control.py:527,537` | 부서 path 접두 매칭 |
| `domain_agents_map`/`domain_templates_map`/`domain_ko_map` | `factory_control.py:304-337` | 최초 시드 후 **코드에서 삭제** |
| **`domain_agents` 필터(비면 전 도메인 실행)** | `core/agent_graph.py:409-421` | **전사 단일 시뮬 엔진 — 코드 변경 0** |
| `mfg_sim` `simulation_framework`/`resim_entry` | `templates/mfg_sim.json:5-22` | 전사 시뮬 + What-if |
| `resimulate` | `factory_control.py:1064-1131` | 전사 What-if — **신규 구현 불필요** |
| **`shared_ledger`**(선언·복원만, 읽는 코드 0) | `state_models.py:87`, `factory_control.py:80,466-470` | `dept_results`/`conflicts`/`directives` 버스 |
| **`skills/sim_supervisor.md`** | 그대로 | 경영진 `/decision` 스킬 |
| `mega/plan` LLM+JSON / `start_all` fan-out | `factory_control.py:382-429 / 430-486` | 대조 1콜 / 대칭 fan-in |
| `_get_format_injection` + `output_formats.json` | `nodes/universal.py:52-59`, `format_control.py` | `enterprise_kpi_json` |
| `RELEVANCE_CUTOFF=0.65` / `search_packs` over-fetch | `knowledge_base.py:285,303-306 / 256-281` | RAG 이식 / `where` 폴백 |
| `index_release` 메타 str 통과 | `knowledge_base.py:355-356` | `owner_dept_id`를 Chroma 메타에 |
| `list_records(q=)` / `list_releases` 루프 | `master_data.py:271-301` / `factory_control.py:1133-1155` | 전사 검색 / `_iter_releases()` 추출 |
| `library/` + 런처 릴리스 탭 | `library/`, `App.tsx:525-565` | **이미 게시판** — 부서 탭으로 확장만 |
| **`copy_project`(통짜 copytree)** | `factory_control.py:550-568` | **포크의 출발점 — 단 4개 결함 수정 필요**(Phase 8-3) |
| **`_EXPORT_EXCLUDE_DIRS`** | `factory_control.py:1016` | 포크 시 `.archive`/`.git`/`node_modules` 제외 — **이미 있는데 copy 에선 안 씀** |
| **`add_revision_task` + `TASK_REV_*` REVISION 경로** | `factory_control.py:731-744`, `:597-598` | **포크본 수정보완 — 신규 구현 불필요**(Architect 건너뛰고 Tech_Lead 직행) |
| **`_INCREMENTAL_GUARD`** | `nodes/execution.py:161-167` | 포크 자산이 재작성에서 유실되지 않게 강제 |
| `read_mappings`·`extract_ids` 순수함수 | `traceability_manager.py:55, 15` | P0-3 / `extract_schema_from_artifacts`·`extract_kpis` 모델 |
| `_read_project_packs` / `start_sprint` 권위 주입 / `_ACCUMULATED_FIELDS` | `factory_control.py:140-159 / 576-583 / 76-81` | dept 주입·복원 |
| `CrosswalkPanel` / `MegaBoardroomPanel` / early-return·모달 패턴 | `CrosswalkPanel.tsx`, `MegaBoardroomPanel.tsx:14-43`, `App.tsx:120-126` | DA 콘솔 / ExecutiveBoardroom / 신규 패널 |
| tmpdir fixture / 자체 FastAPI+TestClient | `tests/test_master_data.py:15-20`, `test_template_binding.py:11-17` | 신규 테스트 |

---

## 단계 의존관계

```
Phase 0 선행 결함 (P0-1 · P0-2 · P0-3 · P0-4)
   ↓
Phase 1 조직·권한 (부서=기준정보, 하드코딩 삭제, executive/admin/DA 3축)
   ↓
Phase 2 식별 주입(강제 off)        ← "누구로 접속 중"이 보임
   ↓
Phase 3 소유권 1급 속성 + 게시      [P0-1 필수]
   ↓
Phase 4 백엔드 강제 + SSE          [P0-3 필수]   ← ORG_ENFORCE=True 로 켤 수 있음
   ↓
Phase 5 ★ LLM/검색 경로 권한        ← 반드시 6·7·8·10 보다 먼저
   ├────────────────┬────────────────────────────────┐
   ▼                ▼                                ▼
Phase 6 데이터 표준   Phase 7 전사검색            Phase 9 롤업(a) [P0-2 필수]
 (T1권장·T2프리뷰·   (kinds=schema 는                    │
  T3게시정합화·      Phase 6 카탈로그 등재에 의존)        │
  T4 DA배치·         │                                   │
  6-7 관련성판정)     │                                   │
   │                 │                                   │
   ├─────────────────┤                                   │
   ▼                 ▼                                   │
Phase 8 재사용·포크 (사일로 방지)                          │
 (8-1 발견 = Phase 7 검색 + 6-7 교차히트 재사용,          │
  8-2 포크 = 권한 모델 재사용, 8-3 개선 = REVISION 재사용) │
   │                                                     │
   └──────────────────────┬──────────────────────────────┘
                          ▼
                   Phase 10 전사 단일 시뮬(b)  [F3 · F4]
                          ▼
                   Phase 11 경영진 총괄
                          ▼
                   Phase 12 프론트 통합 (DA 콘솔 · 포크 UI 포함)
                          ▼
                   Phase 13 하드닝 (telemetry 게이트 · missing_skills · sim_marketing.md)
```

---

## 남는 리스크와 정직한 한계

1. **표준 정합화는 게시된 것만 커버한다** — T3가 주 게이트이므로 **미게시 진행 중 프로젝트의 필드는 카탈로그에 없다.** Phase 9 롤업이 미게시 산출물을 다룰 때는 정규식 폴백에 의존한다. T2 프리뷰가 이 공백을 부분적으로만 메운다.
1-1. **관련성 자동 판정은 필드명 기반이라 오분류한다** — `(entity, field)` 쌍으로 봐서 동음이의를 줄이지만 완전하지 않다. 그래서 **분류를 영구 상태로 저장하지 않고 `reconcile` 마다 재계산**하며, island 승격 규칙이 오분류를 시간이 지나 교정한다. 초기(표준 사전 3건)에는 거의 전부 island로 나오는 것이 정상이다.
1-2. **포크는 업스트림 개선을 따라오지 않는다** — 원본이 v3이 돼도 포크는 v1 기준으로 남는다. 자동 병합은 LLM 산출 코드라 신뢰할 수 없어 범위 밖이며, 배지로 **가시화만** 한다(Phase 8-6). 포크가 늘수록 이 부채가 누적되므로 "N개 부서 포크 = 공용 컴포넌트 승격" 규칙으로 원본 일원화를 유도하는 것이 완화책이다.
1-4. **유사도 게이트는 게시 자산이 쌓여야 작동한다**(8-2 한계 1·2) — 검색 대상이 게시 릴리스뿐이라 초기에는 항상 "유사 없음"이고, 진행 중 프로젝트끼리는 서로를 못 본다. 두 부서가 동시에 같은 것을 만드는 최악의 케이스를 **두 게이트 모두 놓친다.**
1-5. **임계 90점은 보정 전까지 임의값**(8-2 한계 3) — 임베딩 코사인이 "90 = 같은 기능"으로 교정돼 있지 않다. `SIMILARITY_GATE_SHADOW=True` 로 로그를 먼저 쌓아 임계를 정한 뒤 켜야 한다. 켜자마자 오탐이 나면 사용자가 게이트 자체를 불신하게 된다.
1-3. **사일로 방지는 강제가 아니다** — "무시하고 새로 만들기"를 막지 않고 지표로만 남긴다. 차단이 우회를 낳는다는 판단이지만, **가시화만으로 행동이 바뀐다는 보장은 없다.** 중복 생성 지표가 줄지 않으면 그때 정책(승인 게이트)을 얹을지 재판정해야 한다.
2. **매핑 방식의 트레이드오프** — 코드를 고치지 않고 `key_crosswalk`로 해결하므로 **각 앱은 계속 비표준 필드명을 쓴다.** 전사 취합은 되지만 앱 코드를 직접 읽는 사람에게는 여전히 제각각으로 보인다. 근본 통일을 원하면 별도 리팩터링 작업이 필요하다.
3. **표준 사전 커버리지가 곧 정합화 품질** — 현재 M1의 `standard_field`는 KS X 9101 **3건뿐**이다(`data_model_dictionary_part1` 길이 3). 초기에는 대부분의 필드가 pending으로 쌓여 DA 업무량이 폭증한다. **표준 사전 확충이 실질적 선행 과제**이며 `/catalog/standard/coverage`로 상태를 먼저 봐야 한다.
4. **`key_crosswalk` PK가 `(master_code, system_id)`** — 한 앱에서 같은 표준코드에 대응하는 필드가 2개 이상이면(예: `order_date`와 `order_dt`가 둘 다 존재) 하나만 매핑된다. 다중 매핑이 필요하면 PK 확장이 필요하다.
5. **수치 시뮬레이션 엔진이 없다** — "몬테카를로"는 프롬프트 지시어일 뿐 전부 `gateway.aexecute(output_mode="document")` 순수 LLM 호출(`nodes/universal.py:102`). 전사 시뮬은 **LLM 기반 정성·준정량 추론**이지 결정론적 수치 시뮬이 아니다.
6. **`golden_benchmark`가 시뮬 산출물을 평가하지 못한다** — `_STAGE_ARTIFACT_FIELDS`(`golden_benchmark.py:32-38`)가 SW 전용 `*_summary`라 `state.artifacts` 기반 시뮬 결과가 채점에서 빠진다. 전사 시뮬 품질 회귀를 자동 감시할 수단이 없다.
7. **Chroma 과거 인덱스** — 기존 청크에 `owner_dept_id`가 없어 `where`에서 자동 탈락(안전한 방향이지만 과거사례 RAG 효용이 일시적으로 0에 가까워짐). `POST /api/v1/org/reindex-releases`로 선택 복구.
8. **`pipeline_state.db`가 이미 110MB** — 전사 시뮬은 16에이전트 × 사이클이라 체크포인트가 빠르게 증식. 보존 정책 필요.
9. **MCP 병기는 전사 시뮬에서 기본 off 유지 권장** — `mcp_cache` 만료 행 미삭제 단조 증가(`mcp_broker.py:108-109`) + `_lock`(`:78`) 미사용 + `get_live_context`(`:201-236`) N+1에 상한 없음.

---

## 주요 수정 파일

- `api/routes/factory_control.py` — **하드코딩 맵 3개 삭제**(`:304-337`), **포크 라우트 신설 + `copy_project:550-568` 결함 4건 수정**(Phase 8-3), 소유권 필드(`:112-137` + `_read_project_ownership`), 목록 필터(`:187-236`, `:1133-1155`), 단건 403 약 21곳, **`create_release:904-1009`에 게시 정합화(T3) 훅**, `mega/start_all:430-486` fan-in. **P0-1/2/3 전부 이 파일**
- `core/master_data.py` — 조직 테이블 호스트 DB(`_DDL:32-102`, `_init_db:124-131`), 주입 예산 파라미터화(`:491-517, 531-547`), `_connect:117-122` WAL
- `core/crosswalk.py` — 게시 앱 등재·자동 매핑·승인(기존 함수 재사용, 전사 카탈로그 조회 함수만 추가)
- `core/knowledge_base.py` — 유출 차단(`get_relevant_context:401-423`, `search_similar:377-399`에 `where`/distance), `index_release:332-375` dept 메타
- `nodes/universal.py` — F3(`:81-100`에 `build_reference_context` + 표준 계약 권장 주입). **시뮬 품질의 유일한 레버**
- `state_models.py` — `extra='forbid'`(`:66`). 필드 3개 정식 선언 없이는 ValidationError 즉사
- `core/broadcaster.py` — SSE predicate(`clients:15`, `broadcast:43-73`)
- `core/context_engine.py` — `build_reference_context` 추출(`:47-77`)
- **신규**: `core/org_directory.py`, `core/data_standard.py`(계약·`normalize_field`·`classify_relevance`), `core/enterprise_rollup.py`, `api/deps.py`, `api/routes/{org,catalog,search,enterprise}_control.py`, `frontend/src/lib/api.ts`, `frontend/src/components/{UserSwitcher,OrgAdminPanel,DataCatalogPanel,EnterpriseSearchPanel,ExecutiveBoardroom,DeptTree,SimilarArtifactHint,ForkDialog,LineageView}.tsx`, `scripts/migrate_org_ownership.py`, `skills/sim_marketing.md`
