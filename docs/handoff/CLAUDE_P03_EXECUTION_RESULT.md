# P03 실행 결과 — 단계별 누적

지시 `CLAUDE-P03-R3-01` · 작성: Claude Code · 기준 HEAD `0d0789e97`.
**커밋·푸시 없음 · 운영 DB 무접촉 · 클라우드 미배포 · LLM 0 · 실제 PG NOT_RUN.**

---

## P03.1 — 명시 설치 명령 · runtime DDL 분리

```
지시 CLAUDE-P03-R3-01 / 단계 P03.1 / 상태 READY_FOR_REVIEW
현재 HEAD: 0d0789e97 (작업 트리 dirty, 커밋 안 함)
내 변경 파일: core/db/managed_schema.py(신규) · core/auth.py · core/enterprise_context/repository.py
             scripts/install_first_db_schema.py(신규) · tests/test_db_managed_schema_first_slice.py(신규)
다른 세션 변경 보존: ✅ .agents/DECISIONS.md · AI_HANDOFF.md · PROGRESS.md ·
             DECISION_CREATION_CONTRACT_REPAIR_*.json · WEB_DEMO_*.md — 열지 않았습니다
```

### 이번에 가능해진 것 (한 문장)

**스키마를 만드는 주체가 「먼저 쓰는 요청」이 아니라 「명시적인 설치 명령」이 되었고,
관리 모드로 켠 저장소는 기동·첫 조회·재조회에서 DDL 을 한 줄도 돌리지 않습니다.**

### As-Is — 실제 코드에서 확인한 것

| 자리 | 지금까지 |
|---|---|
| `AuthStore._init` | ALTER 4건 → `executescript(_DDL)` |
| `EcmRepository.__init__` | **생성자에서** `executescript` 2회 + ALTER 3건 |
| `EcmRepository._ensure_tables` | 조회 실패 시 **DDL 을 다시** 돌림(조회 경로의 뒷문) |
| `EcmRepository._query` | 그래도 안 되면 **`[]` 를 돌려줌** |
| `ecm_repository = EcmRepository()` | 모듈 수준 — **import 만으로 DDL 이 돈다** |

★★ `_query` 가 제일 나쁩니다. 스키마가 없는데 화면에는 **「자료가 없음」**으로 보입니다.
사람은 「아직 안 넣었나 보다」로 읽고 **아무도 설치 실패를 모릅니다.**

### 완료한 코드

| 파일 | 무엇 |
|---|---|
| `core/db/managed_schema.py` (신규) | 저장소별 관리 모드 · 첫 경로 필수 표·컬럼 · 읽기 전용 확인 · **SQL 계측** |
| `scripts/install_first_db_schema.py` (신규) | `--plan`/`--apply` · 원자적 설치 · 적용 후 재확인 · PG 경로 |
| `core/auth.py` | 관리 모드면 `_init` 이 **DDL 대신 확인**. 실패는 캐시하지 않음 |
| `core/enterprise_context/repository.py` | 생성자 DDL 차단 · **연결 길목에서 1회 확인** · `_ensure_tables` 복구 차단 · 빈 목록 금지 |

**전역 스위치를 쓰지 않았습니다.** `AFS_DB_MANAGED_STORES=auth,enterprise_context` 처럼
**이름을 하나씩** 적습니다 — 아직 이관 안 된 11저장소가 「준비됨」으로 표시되면 안 됩니다.
모르는 이름은 거절합니다(오타 하나로 관리 모드가 조용히 꺼지면 기동 DDL 이 되살아납니다).

### 실행 증거 (명령 / 결과)

**① 설치 — 계획은 쓰지 않고, 적용은 확인까지 한다**

```
install_first_db_schema.py --backend sqlite --sqlite-dir <격리> --plan
  → wrote_anything=false · 디렉터리 생성 0
install_first_db_schema.py --backend sqlite --sqlite-dir <격리> --apply
  → auth 6문장 verified · enterprise_context 29문장 verified · 종료코드 0
운영 DB 해시 대조: data/auth.db OK · data/enterprise_context.db OK (불변)
```

★ 첫 `--apply` 는 **실패했습니다**(종료코드 1). 제가 요구 컬럼을 기억으로 적어
`auth_session.session_id` 라고 썼는데 정본 주키는 `token` 이었습니다 — **적용 후 재확인이
그 자리에서 잡았습니다.** 실패를 성공으로 적지 않았습니다.

**② runtime DDL 0 — 세어서 확인**

```
관리 ON        : 실행 SQL  4건 · DDL  0건
관리 OFF(대조군): 실행 SQL 15건 · DDL 39건   ← ALTER TABLE auth_sse_ticket ADD COLUMN …
판정: 관리 모드 DDL 0 · 대조군은 DDL 있음
```

★★ **대조군이 진짜 대조군인지 먼저 증명했습니다.** 같은 경로를 관리 모드만 끄고 돌려
39건의 DDL 이 실제로 나오는 것을 봤습니다 — 안 그러면 「원래 DDL 이 없던 경로」를
막았다고 착각합니다. 소스 문자열 검사가 아니라 **연결 wrapper 로 실행 SQL 을 셌습니다.**

**③ 집중 시험 · 묶음 끝 회귀 1회** (격리 러너)

```
tests/test_db_managed_schema_first_slice.py            22 passed
묶음: + db_adapter · auth_password · sse_ticket · sse_org_isolation
      80 passed, 5 errors     ← 5건은 기준선과 «동일»
sources_unchanged true · protected_assets_unchanged true · blocked_file_writes []
```

⚠️ **5 errors 는 제 것이 아닙니다.** `tests/test_sse_ticket.py` 의 `seeded_org` fixture 가
저장소 `conftest.py` 에 있고 **격리 러너는 그것을 읽지 않습니다**. 제 변경 전 같은 묶음이
`58 passed, 5 errors` 였고 지금은 `80 passed, 5 errors` 입니다 — 제 시험 22건이 더해졌고
**새 실패는 0** 입니다.

### 확인표 대조

| 사례 | 결과 |
|---|---|
| 명시 installer 적용 | ✅ 격리 임시 DB 에 실제 생성 · 재실행 안전 · 중간 실패 시 **아무것도 안 남음** |
| 관리 모드 기동·첫 조회·재조회 | ✅ **DDL 0** (계측) |
| 없는/불일치 schema | ✅ 실패 · 자동 보강 0 · **다른 DB 생성 0**(파일이 안 생김) |
| 기존 기본 SQLite 새 DB/구 schema | ✅ 새 DB 생성 유지 · **구 schema 보강 순서 회귀 시험** 추가 |
| 연결/backend 선택 | ✅ 주입 연결 실제 사용 · 미설정 PG 가 SQLite 로 바뀌지 않음 |
| 핵심 실패 대조 | ✅ 미설치에서 실제 실패·DDL 0 관측 |

### ⚠️ 이 단계에서 찾은 것 — 제 결함 셋

1. **분할기를 직접 만들었다가 DDL 을 먹었습니다.** 정규식으로 `BEGIN`/`END` 깊이를
   세었더니 18문장짜리 DDL 을 **2문장**으로 잘랐습니다. 그대로 설치했으면 「표가 없다」로
   죽었습니다 → `sqlite3.complete_statement()`(엔진이 가진 판정기)로 바꾸고,
   `executescript` 와 **같은 개체 29개**를 만드는지 대조했습니다.
2. **설치 명령이 import 시점에 전역 환경변수를 썼습니다.** 그것이 pytest 세션 전체로 새어
   무관한 시험 **22건**을 무너뜨렸습니다 → import 하는 «그 순간에만» 켜고 되돌립니다.
   라이브러리 import 는 전역을 바꾸면 안 됩니다.
3. **요구 컬럼을 기억으로 적었습니다**(위 ①).

### 남은 기능 / 미실행

| | |
|---|---|
| 실제 PostgreSQL 설치·로그인·문맥 | ❌ **NOT_RUN** — 서버·DSN 없음 (P03.2) |
| `main.py` 전역 기동 경로 연결 | ❌ 안 함 — 공동 파일이라 보고 후 조율(지시 §3-6) |
| 나머지 11저장소 | ❌ 범위 밖 — 이번에 확대하지 않음 |
| PG 설치 SQL 의 첫 경로 충족 | ✅ 부족 14 → **0** 으로 맞춤(아래 §P03.2 준비 ①) · 단 **실제 PG 실행은 NOT_RUN** |

---

## P03.2 — 실제 PG 로그인·문맥 : **환경 대기 (BLOCKED)**

### 선행 조건 확인 (읽기만)

```
psycopg 드라이버   있음        asyncpg 있음 · psycopg2 없음
AFS_DB_DSN         없음        DATABASE_URL·PGHOST·PGDATABASE 전부 없음
ENV-PG 승인        미확인
```

네트워크 탐침은 하지 않았습니다(임의 URL·사설망 접근 금지).

### ★ 막히지 않은 것은 했습니다 — PG 초안 ↔ 첫 경로 **대응표**

지시 §2 「표가 7개라는 사실을 호환성 증거로 쓰지 않는다」에 따라 실제로 대조했습니다.

> 🔴 **아래 표는 «고치기 전» 상태입니다.** 지금은 부족 0 입니다(§준비 ①). 무엇이
> 어긋나 있었는지 남겨 두려고 지우지 않습니다.

| 저장소 | 표 | 첫 경로 필수 | **PG 초안에 없음** |
|---|---|---|---|
| auth | `auth_credential` | 4 | `hash` |
| auth | `auth_session` | 5 | `token` |
| auth | `auth_sse_ticket` | 10 | — |
| ecm | `tenants` | 1 | — |
| ecm | `enterprise_entities` | 4 | **표 자체가 없음** |
| ecm | `organization_nodes` | 5 | `entity_id`, `status` |
| ecm | `organization_edges` | 4 | `from_node_id`, `to_node_id`, `relation_type`, `status` |
| ecm | `organization_node_code_aliases` | 3 | `code`, `tenant_id` |

**총 부족 14 · 표 1개 누락.** 제가 DB-1 에서 쓴 초안은 **이대로면 첫 요청에서 죽습니다.**

→ 설치 명령의 PG 경로는 **접속하기 전에 이 대조를 하고 막습니다.** 안 맞는 초안을 깔고
「설치 성공」이라고 적으면 그 거짓 초록 위에서 P03.2 가 시작됩니다.

### 필요한 조치 한 가지 (담당: 사용자/Codex)

**승인된 격리 PostgreSQL 한 벌**이 필요합니다. 필요한 것은 넷입니다.

```
① endpoint (호스트·포트)         ② 전용 DB/schema 이름
③ 설치 권한 계정 / runtime 권한 계정 (분리)   ④ 접속정보 «전달 방식»
```

⚠️ **DSN·비밀번호는 이 문서에도 채팅에도 Git 에도 적지 않습니다.** 환경변수
`AFS_DB_DSN` 으로만 받습니다(인자로도 받지 않습니다 — 셸 기록·프로세스 목록에 남습니다).

### 승인 없이 할 수 있는 준비 — **둘 다 끝냈습니다** (실PG 점수 없음)

#### ① PG 초안을 첫 경로에 맞췄습니다 — 부족 **14 → 0**

`core/db/schema/001_auth_and_context.sql` 을 정본 DDL 을 옆에 두고 다시 썼습니다.
이제 **정본 SQLite 스키마와 컬럼 단위로 일치**합니다(내 `REQUIRED` 목록 기준이 아니라
설치된 실제 스키마를 읽어 대조).

| 표 | 정본 | PG 초안 | 부족 |
|---|---|---|---|
| `auth_credential` · `auth_session` · `auth_sse_ticket` | 4 · 5 · 11 | 4 · 5 · 11 | — |
| `tenants` · `enterprise_entities` | 6 · 18 | 6 · 18 | — |
| `organization_nodes` · `organization_edges` · `..._code_aliases` | 14 · 10 · 7 | 14 · 10 · 7 | — |

고친 것: `password_hash`→`hash` · `session_id`→`token` · `name`→`name_ko` ·
`parent_id/child_id/edge_type`→`from_node_id/to_node_id/relation_type`(+유효기간·상태) ·
별칭표에 이력 컬럼 · **`enterprise_entities` 표 신설**.

★★ **시간 컬럼을 `TIMESTAMPTZ` 로 «아직» 바꾸지 않았습니다.** 제품은 «없음» 을 `''` 로
씁니다(`consumed_at=''`, `effective_from DEFAULT ''`). 타입만 먼저 바꾸면 그 SQL 이
그 자리에서 깨집니다 — `timestamptz` 는 `''` 와 비교되지 않습니다. 그 전환은 **이관 변환과
조건절을 «함께»** 고쳐야 하는 별건이라 실제 PG 에서 대조하며 할 일로 남깁니다(P03.3).
부분 인덱스 조건도 `= ''` 로 맞춰 두었습니다 — 한쪽만 바꾸면 인덱스가 질의에 안 맞습니다.

⚠️ 외래키를 걸지 않았습니다. SQLite 정본에 없어서, 여기서만 걸면 **PG 에서만 INSERT 가
실패하는** 경로가 생깁니다. 제약 추가는 동등성을 깨는 변경이라 따로 다룹니다.

#### ② 동시 소비·대사·재시작 harness — `scripts/first_path_consistency_harness.py`

**연결 팩토리만 받습니다.** 지금은 SQLite 로 돌려 harness 자신이 맞는지 보이고,
PG 가 생기면 **같은 코드에 DSN 만** 끼웁니다(`TranslatingConnection` 경유).

```
격리 SQLite 실행 결과
  동시 소비(독립 연결 4) : rowcounts [0,0,0,1] · 성공 «정확히 1»
  거절 행렬              : 만료 0 · 다른 audience 0 · 재소비 0 · 정상 대조 1
  재시작 지문            : 키·건수·소비목록 전부 보존
  운영 data/ 를 가리키면 : 거절 (기준을 PROJECT_ROOT 로 «고정»)
```

★ **스레드마다 연결을 새로 엽니다.** 하나를 공유하면 드라이버가 직렬화해서 「정확히
하나」가 «DB 덕분» 인지 «연결 덕분» 인지 구분할 수 없습니다. 같은 Python lock 으로
직렬화한 시험은 P03.3 의 증거가 되지 못합니다.
★ 소비 문장을 harness 가 **다시 쓰지 않습니다** — 제품 SQL 과 같은지 시험이 대조합니다.

⚠️ **PostgreSQL 로는 한 번도 돌리지 않았습니다(NOT_RUN).** 위 초록은 SQLite 결과이고
P03.2/3 점수의 근거가 아닙니다.

### 이 준비로 바뀐 시험 수

```
tests/test_db_managed_schema_first_slice.py   22 → 29건
묶음 끝 회귀                                   80 → 87 passed, 5 errors(기준선과 동일)
운영 DB 해시 대조 OK · sources_unchanged true · blocked_file_writes []
```

★ 그중 한 시험은 **오늘의 값을 박고 있어서** 고쳤습니다 — 「PG 초안에 구멍이 있다」를
단언했는데, 제가 그 구멍을 메우는 순간 깨졌습니다. 단언할 것은 「지금 구멍이 있다」가
아니라 **「구멍이 있으면 접속 전에 막는다」**는 불변식입니다.

---

## 진척

```
계산기 실측    1800/5300 = 34.0%   (scripts/check_trial_progress.py)
이번 수용 대기  P03.1 +15점 → 조건부 34.5%
```

**혼합하지 않습니다**: 인정점수는 **34.0%** 이고, P03.1 의 15점은 **수용 대기**입니다.
P03.2/3(각 20점)은 **환경 대기**라 예상에 넣지 않습니다.

운영 자산 불변: `data/auth.db`·`data/enterprise_context.db` 해시 대조 OK ·
`library/`·실사용자 자료 무접촉 · 다른 세션 미커밋 파일 보존.
