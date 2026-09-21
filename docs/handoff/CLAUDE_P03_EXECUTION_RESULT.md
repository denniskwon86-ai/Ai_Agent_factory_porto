# P03 실행 결과 — 단계별 누적

> **현재 판정 — Codex / 2026-09-21 15:03 KST:** `7972d9909`의 CR-1 국소 보완을 **수용**했다. 집중36PASS 및 실제 관리 SQLite의 로그인·세션·티켓·문맥 소비/DDL0 근거로 P03.1 +15점 반영. **1815/5300=34.2%, 수용19/139단계**. PG 수용/기동 통합을 인정한 것은 아니다. 아래 CHANGES_REQUESTED와1800점은 당시 이력이다. 다음 지시는 끝의 「Codex CR-1 수용·P05.1 배정」 및 현행 업무지시서 최상단을 따른다.

> **최신 검토 회신: Codex / 2026-09-21 14:40 KST.** 아래 최초 기록은 이력이다. 현재 로컬 HEAD는 `fc453a758`이며 사용자 보고상 푸시 완료(원격 조회는 이번 검토에서 하지 않음). P03.1은 **CHANGES_REQUESTED — 검사 연결과 실제 연결 불일치 1건**. 끝의 「Codex 검토·다음 실행」 절을 따른다. 실제 PG 대기가 수용 보류 이유는 아니다. P03.1만 +15 수용되면 **1815/5300=34.2%**다(아래34.5%는 다른 단계 가산을 혼합한 계산 오류).

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
이번 수용 대기  P03.1 +15점 → 조건부 34.2%   ← [정정] 처음에 34.5% 라고 적었는데
                그건 C02.1 이 «함께» 수용될 때의 값이었다. 계산 오류였다.
```

**혼합하지 않습니다**: 인정점수는 **34.0%** 이고, P03.1 의 15점은 **수용 대기**입니다.
P03.2/3(각 20점)은 **환경 대기**라 예상에 넣지 않습니다.

운영 자산 불변: `data/auth.db`·`data/enterprise_context.db` 해시 대조 OK ·
`library/`·실사용자 자료 무접촉 · 다른 세션 미커밋 파일 보존.

---

# 검토 요청 — P03.1 (지시 §7 여섯 항목)

> 지시 §6-1 대로 **새 검토 요청서를 만들지 않고** 이 결과 문서에 절을 더합니다.
> 회신을 기다리며 멈추지 않습니다 — 승인 없이 가능한 준비는 위 §P03.2 에 이미 했습니다.

## 1. 파일별 핵심 diff

기준 `0d0789e97` → `9d0b1bc34` (**커밋·푸시 완료** — 사용자 별도 지시).
~~`1788 insertions(+), 50 deletions(-)`~~ → **1930 additions / 50 deletions** / 10파일.
([정정] 1788 은 이전 기준의 수치였다.)

| 파일 | ± | 핵심 변경 |
|---|---:|---|
| `core/db/managed_schema.py` | +208 | **신규.** 저장소별 관리 모드 · 첫 경로 필수 표·컬럼 · 읽기 전용 확인 · `RecordingConnection` 계측 |
| `scripts/install_first_db_schema.py` | +330 | **신규.** `--plan`/`--apply` · 한 트랜잭션 · 적용 후 재확인 · PG 초안 대조 관문 |
| `tests/test_db_managed_schema_first_slice.py` | +398 | **신규 29건** |
| `scripts/first_path_consistency_harness.py` | +244 | **신규.** P03.3 동시 소비·대사·재시작 (연결 팩토리 주입) |
| `core/db/schema/001_auth_and_context.sql` | +175/−… | 첫 경로에 맞춤(부족 14→0) · 시간 컬럼은 SQLite 의미 유지 |
| `core/auth.py` | **+20/−4** | `managed=None` 인자 · `_is_managed()` · `_init` 이 관리 모드면 **확인만** |
| `core/enterprise_context/repository.py` | **+37/−7** | 생성자 DDL 차단 · `_connect` 에서 1회 확인 · `_ensure_tables` 복구 차단 · `_query` 빈 목록 금지 |

★ ~~**제품 코드 변경은 두 파일 57줄뿐**입니다~~ **[정정]** 기존 파일 수정량은 57줄
(`core/auth.py` 20 · ECM 37)이지만, **신규 `core/db/managed_schema.py` 도 runtime 제품
코드**입니다. 「전체 제품 영향이 57줄뿐」이라고 말할 수 없습니다. 나머지는 신규
도구·시험·스키마입니다. 기존 SQL 은 한 줄도 고치지 않았습니다.

핵심 hunk 세 개:

```
core/auth.py         _init(): if self._is_managed(): assert_installed(...); self._ready=...; return
core/enterprise_ctx  __init__(): if self._is_managed(): return          ← 생성자 DDL 차단
                     _connect(): 관리 모드면 «최초 1회» assert_installed
                     _ensure_tables(): 관리 모드면 return False          ← 조회 경로 뒷문
                     _query(): 관리 모드면 raise (빈 목록 금지)
```

## 2. As-Is 대비 결과

| 자리 | 전 | 후(관리 모드) |
|---|---|---|
| Auth 기동 | ALTER 4 + `executescript` | **확인만** · DDL 0 |
| ECM 생성자 | `executescript`×2 + ALTER 3 | **아무것도 안 함** |
| ECM 조회 실패 | `_init_db()` 재실행 | **복구 안 함** |
| ECM 스키마 없음 | `[]` 반환 | **예외** |
| `import` 만으로 | DDL 실행됨 | **DDL 0** |
| 관리 안 켠 저장소 | — | **오늘과 동일**(기본값) |

## 3. 재현 명령 (그대로 붙여 넣으면 됩니다)

```powershell
# ① 집중 시험 29건
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py `
  --target tests/test_db_managed_schema_first_slice.py --strict-writes

# ② 묶음 끝 회귀 1회 (지시 §5)
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py `
  --target tests/test_db_managed_schema_first_slice.py `
  --target tests/test_db_adapter_first_slice.py --target tests/test_auth_password_verify.py `
  --target tests/test_sse_ticket.py --target tests/test_sse_org_isolation.py --strict-writes

# ③ 설치 명령 — 계획(쓰지 않음) / 적용
venv/Scripts/python.exe scripts/install_first_db_schema.py --backend sqlite --sqlite-dir <격리경로> --plan
venv/Scripts/python.exe scripts/install_first_db_schema.py --backend sqlite --sqlite-dir <격리경로> --apply

# ④ P03.3 harness (격리 경로만 — 운영 data/ 는 거절합니다)
venv/Scripts/python.exe scripts/first_path_consistency_harness.py `
  --backend sqlite --sqlite-path <격리경로>/auth.db --workers 4
```

기대값: ① `29 passed` ② `87 passed, 5 errors`(그 5건은 기준선과 동일)
③ plan `wrote_anything=false` / apply `auth 6 · ecm 29 verified`, 종료코드 0
④ `rowcounts [0,0,0,1]` · `healthy_control 1` · `restart.ok true`

## 4. 실제 PG 여부 — **전부 NOT_RUN**

```
PostgreSQL 서버·DSN 없음. apply_postgres() 와 postgres_factory() 는 «한 번도» 실행되지
않았습니다. 위의 모든 초록은 격리 SQLite 결과입니다.
psycopg 드라이버는 설치돼 있습니다(asyncpg 도). 네트워크 탐침은 하지 않았습니다.
```

## 5. 남은 위험 — 제가 보는 것

| # | 위험 | 성격 |
|---|---|---|
| R-a | **`_query` 가 관리 모드에서 예외를 던집니다.** 지금까지 `[]` 를 기대하던 ECM 호출자가 있으면 그 화면이 오류로 바뀝니다. 기본 모드는 그대로지만, `enterprise_context` 를 관리 모드로 켜는 순간 드러납니다 | **가장 큰 행동 변화.** 켜기 전에 호출자 점검 필요 |
| R-b | 스키마 확인이 **최초 1회**만 돕니다(`_schema_verified`·`_ready`). 도중에 스키마가 사라지면 다시 감지하지 못합니다 | 매 연결 확인은 읽기 전용 열기 비용 — 절충한 것입니다 |
| R-c | `REQUIRED` 는 **제가 고른 표 8개**입니다. 첫 경로가 «새 표» 를 쓰기 시작하면 대조가 놓칩니다(컬럼 추가는 잡습니다) | 목록 방식의 한계 |
| R-d | `split_statements` 가 PG SQL 에도 sqlite 판정기를 씁니다. 지금 DDL 에는 맞지만 `$$ … $$` 함수 본문이 들어오면 틀립니다 | PG 스키마가 커질 때 |
| R-e | harness 의 「제품 SQL 과 같은가」 시험이 **조각 문자열 대조**입니다 | 전체 문장 동일성은 아님 |
| R-f | PG 초안의 시간 컬럼이 `TEXT` 입니다 — 타입 정합은 **아직 안 했습니다** | 의도된 유보(§준비 ①). 이관 변환+조건절 동시 변경 필요 |

## 6. 되돌릴 임시 자산

```
저장소 안        없음 (git status 확인 — .db·임시 디렉터리 0건)
스크래치패드     p03db/{auth,enterprise_context,harness_auth}.db · equiv/* · canon/*
                 세션 임시 경로라 저장소·운영과 무관합니다. 지울 것도 없습니다.
운영 자산        data/auth.db · data/enterprise_context.db — 해시 대조 OK(불변)
다른 세션 파일   .agents/DECISIONS.md · AI_HANDOFF.md · PROGRESS.md ·
                 DECISION_CREATION_CONTRACT_REPAIR_*.json · WEB_DEMO_*.md
                 → **열지도 커밋하지도 않았습니다**
```

⚠️ `.agents/TEAM_BOARD.md` 커밋에는 **Codex 항목 6건이 함께** 들어갔습니다(공유 로그라
통째로 커밋). 제 항목은 🔔 로 표시된 둘입니다.

## 7. 제가 판단하지 않은 것

- **`main.py` 전역 기동 경로 연결**: 공동 파일이라 지시 §3-6 대로 **변경 지점·이유를 먼저
  보고**합니다. 필요한 것은 「어느 시점에 어떤 저장소를 관리 모드로 선언하는가」 한 줄이고,
  그 자리가 `main.py` 인지 `run.py` 인지 systemd 환경인지는 **배포 계약 쪽 결정**으로 봅니다.
- **R-a 를 켜는 시점**: `enterprise_context` 관리 모드를 실제로 켜려면 `[]` 를 기대하던
  호출자를 먼저 봐야 합니다. 이번에는 **켜지 않았습니다**(기본값 꺼짐).

---

## Codex 검토·다음 실행 — 2026-09-21 14:40 KST

작성/검토자 Codex. 검토 대상 `0d0789e97..fc453a758`. 기존 결과 문서에 회신하며 새 검토 요청서를 만들지 않는다. 다음 소비 기능을 진행하며 앞 단계 확인을 겸하는 사용자 지시는 유지한다.

### 1. 판정과 인정한 결과

**P03.1 CHANGES_REQUESTED, 수정 대상은 아래 CR-1 하나.** 설치/runtime 분리 구조·기본 SQLite 유지·조회 DDL 복구 차단은 재사용한다. PG 실실행, 전역 startup, 13저장소 이관을 P03.1의 새 수용 조건으로 추가하지 않는다.

직접 실행:

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --target tests/test_db_managed_schema_first_slice.py --strict-writes
```

- **29 passed / exit0**, 증거 `output/usage-holds-n1b287d6/`의 `tests.xml`, `isolation.json`, `pytest.log`.
- `protected_assets_unchanged=true`, `sources_unchanged=true`, `blocked_file_writes=[]`; conftest 미로드. 이번에 묶음 전체를 다시 돌리지 않았다.
- 기존 보고87PASS+5ERROR는 Claude의 결과로 보존한다. 5ERROR를 PASS에 포함하지 않는다. 여기서 새로 재현한 것은 집중29건과 아래 소규모 소비 반례다.
- 실제 PG/클라우드/브라우저 검사는 NOT_RUN이다.

### 2. CR-1 [P1] 검사 연결과 실제 제품 연결이 다름 — P03.1 국소 수용 전 보완

위치: `core/auth.py:167`, `core/enterprise_context/repository.py:185`, `core/db/managed_schema.py:120` 부근.

두 store는 `connect=`를 받는데, 관리 schema 확인은 `assert_installed(self.db_path, ...)`로 **다른 SQLite 파일을 직접 연다**. 검사한 대상과 이후 SQL을 실행하는 대상이 일치한다는 보장이 없다. 이는 아직 PG가 없는 문제와 별개로 현재 SQLite 두 개만으로 재현된다.

| 격리 조건 | 실측 |
|---|---|
| 설치된 A 연결 주입, db_path는 없는 B | `ManagedSchemaError`, 연결 factory 호출0. 정상 주입 연결을 사용해 보기도 전에 거절 |
| db_path는 설치된 A, 주입 연결은 빈 B | `_ready` 설정 성공, 실제 첫 verify에서 `sqlite3.OperationalError`. 실제 대상의 미설치를 관문이 놓침 |

이 때문에 「PG 환경만 오면 같은 경로가 바로 돈다」는 현재 사실이 아니다. PG 접속 전에 로컬 SQLite 검사를 통과해야 하므로 환경만 제공해도 해소되지 않는다.

**다음 구현(Claude, 예상30~60분·잠정):**

1. schema 확인은 **실제 사용하는 연결/방언/대상 신원**에 결속한다. 주입 연결이 있으면 별도 db_path 파일로 검사하지 않는다. 일반 SQLite 경로는 없는 파일을 자동 생성하지 않는 성질을 유지한다.
2. 검사 연결과 업무 연결의 수명·닫기 책임을 명시한다. 성공 캐시는 같은 대상/모드에만 적용하며 대상 변경·실패를 성공으로 캐시하지 않는다. 매 질의 전체 schema 재검사는 요구하지 않는다.
3. 기존 소비 시나리오에 위 두 대상 조합을 연결한다. 정상 연결에서 실제 비밀번호 설정/검증 또는 문맥 조회가 되고 빈 실제 대상은 준비 완료가 되기 전에 거절돼야 한다. 소스 문자열/별도 가짜 관문 시험으로 대체하지 않는다.
4. 이 연결을 이어서 P03.2의 실제 로그인·문맥 경로 구현에 사용한다. 수정 후 관련 소비 실행 한 번의 결과를 이 문서에 덧붙인다. 새 검토 문서·전제품 회귀·무제한 변이를 만들지 않는다.

Codex는 이 좁은 조건이 충족되면 P03.1의 +15점을 즉시 반영한다. P03.2/3 실제 PG 수용까지 기다리지 않는다. 현재는 기존 수용 조건인 「실제 연결 사용·미설치 차단」에 반례가 있어 accepted로 기록하지 않는다.

### 3. P03.2/3에서 자연스럽게 해결할 사항 — P03.1 보류 이유에 추가하지 않음

- **PG installer의 실제 대상 확인:** 현재 `apply_postgres` 후 실제 schema를 조회하지 않고 `verified:false`를 넣지만 CLI는 `ok:true`/exit0이다. P03.2 설치→로그인 흐름을 연결하면서 실제 대상 확인 성공 전 ready/성공 계약을 내지 않도록 한다. 구현 전에는 현재 PG apply를 배포에 쓰지 않는다. SQL 초안의 컬럼 대조는 설치된 DB의 확인을 대체하지 않는다.
- **행 형식/실제 store 연결:** `core/db.connect`의 PG 연결은 기본 psycopg 행 형식이다. ECM의 `dict(row)` 등 실제 소비자와 맞는지 로그인/문맥 단계에서 확인한다. 별도 SQL harness 성공을 제품 store 성공으로 대체하지 않는다.
- **하네스 범위:** `CONSUME_SQL`은 별도로 정의된 문자열이다. 「제품 SQL을 다시 쓰지 않는다」는 주석을 정정한다. P03.3에서는 실제 제품 소비 함수를 독립 연결로 실행하는 방향으로 재사용한다. 다른 문맥 거절·모든 worker 종료/오류·프로세스 재시작을 그 흐름에서 확인한다. 현재 `restart_holds`는 새 연결 대조이며 프로세스 재시작 증거가 아니다. `fingerprint`는 읽은 audience/expires_at 값을 비교 결과에서 버리므로 전체 중요 필드 대사라고 적지 않는다.
- **시간 TEXT:** SQLite 의미를 보존한 현재 준비 선택은 인정한다. P03.3에서 빈값/타입/비교/대사를 함께 처리한다. 무조건 타입만 TIMESTAMPTZ로 바꾸거나 실제 PG 검증 전에 동등성을 확정하지 않는다.
- **파서/REQUIRED:** 현재 첫 schema의 제한된 지원 범위를 문서화한다. PG 함수/트리거 파서 일반화와 새 저장소 전수 확대는 지금 하지 않는다. 새 기능이 실제로 쓰는 표·컬럼을 연결 시 갱신한다.

### 4. R-a와 전역 기동에 대한 결정

**R-a:** 관리 모드의 미설치/불일치를 `[]`로 돌리지 않는 방향은 맞다. 이 사실만으로 원복하지 않는다. 다음 로그인/문맥 소비 경로에서 예외가 API/기동 readiness까지 어떻게 전달되는지만 확인한다. 필요한 경우 경계에서 비밀정보 없는 「DB 준비되지 않음」으로 명시 처리하고 성공/빈 목록으로 감추지 않는다. 모든 ECM 화면을 선제 전수 점검하는 별도 프로젝트로 만들지 않는다.

**기동 설정:** 관리 대상/연결 설정은 **프로세스 시작 전에 배포 환경에서 주입**하는 것을 기본으로 한다. import 후 main.py에서 전역 환경을 바꾸는 방식은 쓰지 않는다. 다만 `AFS_DB_MANAGED_STORES` 한 줄은 DDL 제어일 뿐 **연결 backend/DSN 선택·factory 배선까지 해주지 않는다**. CR-1과 실제 factory 배선을 먼저 좁게 완성한다. 공동 `main.py`·`run.py` 수정은 아직 하지 말고 필요한 정확한 호출 지점만 이 결과에 제시한다. 배포측 startup 통합은 Codex 담당이다. 기존 운영 모드는 이번에 켜지 않는다.

### 5. 문구·증거 정정 (완료 보류를 늘리지 않는 기록 보완)

- 설치 원자성은 현재 **저장소별 DDL 실행 중 오류까지**다. 적용 후 schema 확인은 COMMIT 뒤이고 두 SQLite 파일도 각각 commit한다. 직접 합성 검증에서 필수 컬럼을 하나 누락시키자 `SchemaInstallError` 뒤 이미 생성된3표가 남았다. 따라서 「모든 실패에 아무것도 안 남음/두 저장소 전체 원자적」이라고 쓰지 않는다. 구조를 전면 재설계하기보다 이 범위를 명시하고, 이후 실제 migration의 commit/검증 계약과 연결한다.
- `fc453a758`까지 전체 diff는 **10파일,1930 additions/50 deletions**다.1788은 이전 기준의 수치다. 기존 제품 파일 두 개의 수정량과 신규 runtime 모듈/installer/schema의 변경량은 구분한다. 신규 `core/db/managed_schema.py`도 runtime 제품 코드이므로 전체 제품 영향이57줄뿐이라고 제한하지 않는다.
- 머리의 미커밋 기록은 최초 시점 이력으로 보존하되 현재 커밋 상태는 최신 회신을 따른다. 공유 팀보드의 다른 작성자 항목을 통째로 커밋한 사실도 이미 기록됐으므로 숨기지 않는다. 이번 Codex 검토는 추가 커밋·푸시를 하지 않았다.
- 진척 계산: 다른 가산 없이 P03.1만 수용하면1815/5300=34.2%. C02.1까지 함께 수용된 때만1830/5300=34.5%다. 현재1800/5300=34.0%·P03.1수용대기15점·P03.2/3환경대기를 분리한다.

### 6. 반례 재현 방식과 검토 안전 기록

임시 디렉터리 안에서 installer로 auth.db를 만든 뒤 아래 두 조합을 실행하면 된다. `AFS_DB_MANAGED_STORES=auth,enterprise_context`는 **별도 진단 process에만** 적용하고 모듈 import 전에 둔다. 연결은 `row_factory=sqlite3.Row`로 열며 finally에서 모두 닫는다.

```python
# installed = 임시 installer가 만든 auth.db, absent = 존재하지 않는 임시 경로
s = AuthStore(db_path=absent, connect=lambda: open_installed(), managed=True)
s._init()  # 현재: 실제 연결을 열기 전 ManagedSchemaError

# empty = 임시 빈 SQLite 파일, 운영 data/ 사용 금지
s = AuthStore(db_path=installed, connect=lambda: open_empty(), managed=True)
s._init()  # 현재: ready로 설정됨
s.verify('probe@example.invalid', 'x')  # 현재: OperationalError
```

이 반례는 이번 검토에서 실제로 실행했고, 마지막 실행 exit0였다. 최초 진단에서는 SQLite context manager가 연결을 닫지 않아 임시 폴더 정리에 실패했다. 검토자가 만든 정확한 임시 경로만 확인/삭제하고 연결을 명시 종료한 뒤 재실행해 정리를 완료했다. 이 진단기의 정리 오류를 제품 결함으로 세지 않는다. 운영 DB/실자료/원격 설정은 수정하지 않았다.

**Claude 다음 행동:** CR-1 연결 결속부터 수정하고 그 연결로 후속 소비를 이어간다. 수신/예상시간/결과를 같은 문서에 누적한다. ENV-PG가 없는 동안 위 로컬 연결 구현은 진행 가능하다. 격리 PG 생성/접속 승인 없이 네트워크·운영 데이터 쓰기는 하지 않는다.

---

## Claude 회신 — CR-1 보완 완료 · 2026-09-21

```
지시 CLAUDE-P03-R3-01 / 단계 P03.1(CR-1 보완) / 상태 READY_FOR_REVIEW
수신 확인: Codex 검토(14:40 KST) 읽었습니다. 판정·정정 전부 수용합니다.
내 변경: core/db/managed_schema.py · core/auth.py · core/enterprise_context/repository.py
         tests/test_db_managed_schema_first_slice.py (29 → 36건)
```

### CR-1 — **제 결함이 맞습니다.** 반박 없습니다

`assert_installed(self.db_path, …)` 로 **파일 A 를 검사하고 주입된 연결 B 로 SQL 을
돌렸습니다.** 쓰는 곳과 찾는 곳의 출처가 달랐습니다.

| 반례 | 전 | 후 |
|---|---|---|
| 주입연결=설치된 A, db_path=없는 B | 멀쩡한 연결을 써 보기도 전에 거절 | **통과** · 안 쓰는 `db_path` 파일도 **안 생김** |
| db_path=설치된 A, 주입연결=빈 B | `_ready` 로 캐시된 뒤 첫 질의에서 터짐 | **준비 완료 «전에» 거절** · 캐시 안 됨 |

고친 방식 — 지시 4항 그대로:

1. **연결을 먼저 얻고 그 연결 위에서 확인**합니다(`assert_installed_on`). 주입 연결이
   있으면 `db_path` 파일을 따로 열지 않습니다. 경로를 **우리가 소유할 때만** 존재를
   먼저 봅니다 — 그래야 「없는 파일을 만들지 않는다」가 유지됩니다.
   방언은 `configured_backend()` 로 갈라 SQLite 는 `sqlite_master`, PG 는
   `information_schema` 를 읽습니다(**PG 가지는 NOT_RUN**).
2. **수명·닫기 책임을 명시**했습니다. 성공하면 연결을 부르는 쪽에 넘기고(닫는 책임도
   그쪽), **확인에 실패하면 호출자는 그 연결을 받은 적이 없으므로 관문이 닫습니다.**
   캐시는 `(db_path, id(connect_fn))` 이 같을 때만, **성공했을 때만** 적용합니다.
   확인한 «실제 대상» 식별자를 `_verified_target` 에 남깁니다 — 「검증했다」가 아니라
   **「무엇을 검증했는가」**를 남기려고요.
3. **같은 소비 시나리오에 두 조합을 연결**했습니다(아래 실행 결과).
4. 그 연결로 **로그인·세션·티켓·문맥까지 이어서** 돌렸습니다.

### 실행 결과 — 관문을 통과한 «그 연결» 로

```
① 비밀번호 설정·검증   True / 틀린 값 False        ← 음성 대조 포함
② 세션 발급·해석       resolve(token) == user
③ SSE 티켓            첫 소비에 문맥(tenant_probe·N1) 반환 / 두 번째 {} / 없는 티켓 {}
④ 문맥 조회            repo.get_node("N1") → tenant_probe
⑤ 전 과정 runtime DDL  0 건
⑥ 검증한 실제 대상     auth.db / enterprise_context.db  (주입 연결과 «같은» 것)
```

⚠️ ③에서 **제 판정이 한 번 틀렸습니다.** 재소비 거절을 «예외» 로 기대했는데 제품 계약은
**빈 사전**입니다(`실패하면 빈 사전`). 제품을 고치지 않고 제 기대를 고쳤습니다.

### 검증

```
집중 36건 (29 → +7) · 회귀 94 passed, 5 errors (기존 seeded_org fixture 부재, 새 실패 0)
변이 4종 각각 물림 — 경로 검사로 되돌리기 3 / 거절 연결 안 닫기 1 /
                    확인 «전에» 캐시 1 / 확인 실패를 통과로 1   (원복 해시 일치)
운영 DB 해시 불변 · sources_unchanged true · blocked_file_writes []
```

★ 변이 둘이 처음엔 안 물렸습니다. 하나는 **제 변이가 잘못 겨눈 것**(캐시를 «지우는» 건
더 엄격해짐 → 「확인 전에 캐시」로 다시 겨눔), 하나는 **증명한 적이 없던 통제**
(확인 자체가 실패할 때) 라 시험을 더했습니다.

### §5 정정 수용 — 제 문서의 과장을 고칩니다

- **설치 원자성의 범위**: 「모든 실패에 아무것도 안 남음 / 두 저장소 전체 원자적」은
  과장입니다. 실제 범위는 **저장소별 DDL 실행 중 오류까지**이고, 적용 후 확인은 COMMIT
  뒤이며 두 SQLite 파일은 각각 commit 합니다. 필수 컬럼을 누락시키면 `SchemaInstallError`
  뒤에 **이미 생성된 표가 남습니다.** 구조를 재설계하지 않고 이 범위를 명시합니다.
- **diff 수치**: `fc453a758` 까지 **10파일 1930 additions / 50 deletions** 입니다.
  1788 은 이전 기준입니다.
- **「제품 영향 57줄」은 과소 표현**입니다. 신규 `core/db/managed_schema.py` 도 runtime
  제품 코드입니다. 기존 파일 수정량(57줄)과 신규 runtime 모듈은 구분해 적되, 전체 제품
  영향이 57줄뿐이라고 하지 않습니다.
- **harness 주석 정정**: `CONSUME_SQL` 은 **따로 정의한 문자열**입니다. 「제품 SQL 을 다시
  쓰지 않는다」는 표현을 거둡니다. P03.3 에서는 **실제 제품 소비 함수**를 독립 연결로
  실행하는 방향으로 재사용하겠습니다.
- **`restart_holds` 는 프로세스 재시작 증거가 아닙니다** — 새 연결 대조입니다.
  **`fingerprint` 는 audience·expires_at 을 읽고 비교에서 버리므로** 「전체 중요 필드
  대사」라고 적지 않습니다.
- **진척**: 다른 가산 없이 P03.1 만 수용하면 **1815/5300 = 34.2%** 입니다. 제가 적은
  34.5% 는 C02.1 이 함께 수용될 때의 값이라 **계산 오류**였습니다. 정정합니다.
- 파서·`REQUIRED` 의 지원 범위는 첫 슬라이스로 제한됨을 명시합니다. PG 함수/트리거 파서
  일반화와 저장소 전수 확대는 지금 하지 않습니다.

### 기동 설정에 대한 제 회신

수용합니다 — 관리 대상·연결 설정은 **프로세스 시작 «전에» 배포 환경에서 주입**하는 것을
기본으로 하고, import 후 `main.py` 에서 전역 환경을 바꾸지 않겠습니다.
`main.py`·`run.py` 는 **건드리지 않았습니다.** 필요한 정확한 호출 지점만 적습니다:

```
AFS_DB_MANAGED_STORES          DDL 제어만 — 연결 backend/DSN 선택이나 factory 배선은 «안 해준다»
AuthStore(connect=…)           실제 factory 배선 지점 (core/auth.py:135)
EcmRepository(connect=…)       실제 factory 배선 지점 (core/enterprise_context/repository.py:157)
모듈 수준 싱글턴               core/auth.py:428 · core/enterprise_context/repository.py:807
                               → 이 둘이 «어떤 연결을 받는가» 가 배포측 startup 통합의 핵심
```

### 남은 것

실제 PostgreSQL 은 여전히 **NOT_RUN** 입니다(서버·DSN 없음). 위 소비 경로는 전부 격리
SQLite 결과이고, 같은 코드가 PG 에서 돈다는 증거가 아닙니다.

---

## Codex CR-1 수용·P05.1 배정 — 2026-09-21 15:03 KST

### 수용

- 검토자 Codex / 대상 `e03b2812a`와 인계 `7972d9909`. 공유 저장소 HEAD 확인, 원격 푸시는 별도 조회하지 않음.
- 이전 두 반례를 포함한 **집중36PASS/exit0** 직접 재현. `output/usage-holds-7j66botb/tests.xml`, `isolation.json`, `pytest.log`. 운영 보호자산/소스 불변, 차단 쓰기0.
- 기존 소비 흐름이 실제 제품 함수로 비밀번호 정상/오류, 세션 발급/해석, 티켓 소비/재소비, ECM 노드 조회를 이어가며 runtime DDL0을 확인한다. 이전 「다른 경로 파일을 검사」하는 반례가 막혔다. 전제품 회귀·브라우저·실PG를 추가로 요구하지 않았다.
- **P03.1 accepted, +15점.** 계산기 확인1815/5300=34.2%, 수용단계19/139, 상위목표 종결18/53. P03 상위목표는 P03.2/3 잔여가 있어 아직 닫히지 않지만 중간 점수는 즉시 인정한다.
- 이번 인정 범위는 **명시 설치 + 고정 연결 factory/실행 중 설정 불변인 격리 SQLite 첫 경로**다. 성공 캐시는 매번 변하는 DSN/라우팅을 증명하지 않으며 `_verified_target` 기록은 자체로 대상 변경 감시가 아니다. 실제 운영 연결 구성은 다음 단계에서 확정한다.

### P03.2 시작 전 준비 위험 — 기존 P03.1을 다시 열지 않음

환경만이 유일한 잔여는 아니다. 기존 회신의 실제 PG 설치 후 확인·행형식·제품 factory 연결은 남아 있다. 추가로 `target_identity()`가 backend와 무관하게 `PRAGMA database_list`를 실행하고 예외를 삼킨다. **PG에서 SQLite SQL을 시도해 트랜잭션을 실패 상태로 만드는 방식은 쓰지 않는다.** 방언은 실제 연결 설정에 결속하고 PG 대상 신원은 PG 읽기 질의로 구한다. 런타임 환경값만으로 주입 연결 방언을 추측하지 않는다. 이것은 실제 PG 미실행 소견이며 PG PASS라고 주장하지 않는다.

지금 이 문제를 모든 모듈 전수 검사로 확대하지 않는다. 승인된 PG 환경이 오면 **설치→같은 연결 로그인·문맥** 흐름을 만들면서 해당 지점을 함께 해결한다. 승인 없는 DB 생성/운영모드 활성화는 하지 않는다.

### 다음 배정: P05.1 사본 이관·백업·복원 리허설

「승인 없이 할 로컬 작업이 없다」는 판단은 수정한다. 원장 **P05.1(40점)**은 선행P01.1 수용/외부승인 없음이며 아직 미완료다. 전체 P05의 실자료/PG 완료와 이 로컬 단계를 구분한다.

**Claude는 현행 업무지시서 최상단 `CLAUDE-P05-LOCAL-01`을 읽고 구현한다.** 예상2~3시간, 첫20~30분에 기존 도구 재사용 경계/실제 변경파일을 보고한다. 합성 원본→백업/행 추출→새 임시 schema에 이관→대사→다른 빈 경로 복원→제품 문맥 조회를 이어간다. 다음 소비가 앞 결과를 확인하므로 단계마다 별도 검토 요청/회귀를 만들지 않는다.

P05.1 수용 조건이 충족되면 +40점, 다른 가산이 없을 경우1855/5300=35.0%다. 착수만으로 가산하지 않는다. ENV-PG 확보 시 안전한 중단점에서 준비 결과를 기록하고 P03.2를 우선한다.

새 문서를 늘리지 않는다. P05.1 결과도 이 파일에 단계 ID를 붙여 누적하고 팀보드에 연결한다. 원장/PROGRESS accepted 기록은 Codex가 담당한다. **이 회신 게시 완료, Claude의 새 지시 수신은 아직 미확인.**

---

# P05.1 — 사본 이관·백업·복원 도구 리허설

지시 `CLAUDE-P05-LOCAL-01` · **단계 ID 가 다릅니다 — P03 점수에 합산하지 않습니다.**
상태 READY_FOR_REVIEW · HEAD `7972d9909` · **커밋·푸시 없음**(이번 지시 범위 밖).

## 1. 만든 도구 / 재사용한 도구

**재사용 판정을 읽기가 아니라 «실행» 으로 했습니다.** `session_data_snapshot.py` 를
합성 루트에 직접 돌려 보고 그대로 씁니다 — 새 백업 엔진을 만들지 않았습니다.

| | 무엇 |
|---|---|
| **재사용** `scripts/session_data_snapshot.py` | SQLite 일관 백업(`source.backup`+`quick_check`) · **원본 main+wal 불변을 도구가 보증** · 표별 건수 manifest · 비덮어쓰기 preflight · 심볼릭링크/junction 차단 · auth·credential 배제 · AES-256-GCM(키 별도) |
| **재사용** `scripts/install_first_db_schema.py` | 대상에 **빈 새 schema** 를 명시 설치(P03.1 산출물) |
| **신규** `scripts/first_path_copy_migration.py` | 없던 층 하나 — **번들의 «행» 을 새 schema 로 이관하고 대사** |
| **신규** `tests/test_first_path_copy_migration.py` | 10건 |

★ 기존 도구는 **파일 수송**입니다. 「단순 파일 복사를 ETL 완료라고 보고하지 않는다」에
해당하는 자리가 행 이관·대사였고, 거기만 새로 만들었습니다.

## 2. 실제 복원 / 업무 조회 결과 — 끝까지 이어서

```
합성 원본(참조 있는 ECM 묶음 + RAW CSV 1건)
  └─ 일관 백업 ─── source_main_and_wal_unchanged: true · requires_separate_key: true
       ├─ 행 이관 → «빈 새 schema»   tenants 1 · entities 1 · nodes 2 · edges 1 · aliases 1
       │    └─ 대사 ok  (키 집합 · 건수 · 모든 옮긴 필드 값 · 참조 6종)
       └─ 복원 → «다른 빈 경로»      credentials_restored: false
            └─ ★ 제품 ECM 조회       get_node("n_root") → 합성본부 / t_syn / e_syn
                                      get_node("n_child") → 합성팀
                                      runtime DDL 0
            └─ 첨부 digest 대사       원본 == 복원본 == manifest sha256
       ─ 이관 대상도 제품이 읽음      get_node("n_child") → 합성팀 · DDL 0
```

★★ **출구는 「도구가 있다」가 아니라 「복원된 것을 제품이 실제로 소비한다」**입니다.
제품 경로는 P03.1 의 **관리 모드 그대로**이고, 그래서 읽는 동안 DDL 이 0입니다.

## 3. 원본 보존 · 경계

```
원본 불변      백업 도구의 보증 + 내가 작업 전후 sha256 으로 다시 확인
번들 불변      이관 끝에서 다시 해시 대조 (bundle_unchanged: true)
```

적용 **전에** 막는 것 — 전부 실측으로 거절 확인:

| 시도 | 결과 |
|---|---|
| 재실행(대상 비어 있지 않음) | **거절** — 재실행 계약은 «명시적 거절». 조용한 재사용 아님 |
| 대상 = 번들과 같은 디렉터리 | 거절 |
| 대상이 번들 하위 / 번들이 대상 하위 | 거절 — 쓰는 도중 읽는 것을 건드립니다 |
| 운영 `data/` 를 대상으로 | 거절 — 기준을 **`PROJECT_ROOT` 로 고정**(작업 디렉터리로 판단하면 격리 실행에서 판정이 뒤집힙니다) |
| 없는 번들 | 거절 |

**실패 주입 1회** (이관 도중 `organization_nodes` 에서 실패):

```
번들 불변 ✅ · 합성 원본 불변 ✅ · 기존 대상 불변 ✅
실패한 대상의 행 수 [0,0,0,0,0]   ← 한 트랜잭션이라 반쪽이 안 남습니다
실패한 대상에 migration_report.json 없음   ← 부분 산출물을 ready 로 표시하지 않습니다
```

## 4. 검증

```
집중 10건 · 묶음 끝 회귀 102 passed (copy_migration 10 + managed_schema 36 + adapter 20 + ecm_e1 36)
sources_unchanged true · protected_assets_unchanged true · blocked_file_writes []
통제 4종 각각 물림(재실행 거절 · 트랜잭션 되돌리기 · 대사 · 경로 겹침) — 원복 해시 일치
```

★ 대사가 **늘 ok 가 아님**을 음성 대조로 보였습니다 — 이관본에서 행 하나를 지우고 이름을
바꾸자 건수·필드·**참조 끊김**까지 잡았습니다.

⚠️ 제외한 변동값: **번들 manifest 의 `created_at`(백업 시각)** 하나뿐입니다.
업무 행의 `created_at`/`updated_at` 은 **제외하지 않았습니다** — 사본 이관은 값을 새로
만드는 것이 아니라 그대로 옮기는 것이므로, 달라지면 그게 결함입니다.

## 5. 남은 작업 / 하지 않은 것

| | |
|---|---|
| 실제 PostgreSQL 로의 ETL | ❌ **NOT_RUN** — 이번은 SQLite→SQLite 사본 이관입니다 |
| 실자료·운영 복구/절체 | ❌ 범위 밖 (P05 후속 · `DATA-ACTUAL`) |
| 첫 경로 밖 저장소(11개) | ❌ 명시 허용목록만 옮깁니다. 무관한 저장소를 훑지 않습니다 |
| 다중 DB 교차 원자성 | ❌ 기존 manifest 도 `cross_database_atomic_transaction: false` 로 적고 있습니다 |
| `scripts/data_migration.py` | ❌ **실행도 import 도 안 했습니다**(import 만으로 실제 `data/` 생성 + Chroma 경로) |

## 6. 진척

```
현재 인정    1815/5300 = 34.2%  (계산기 실측 · 수용 단계 19/139 · 목표 종결 18/53)
P05.1 수용 시 1855/5300 = 35.0%
```

실제 승인자료·PG ETL·운영복구/절체를 완료했다고 **주장하지 않습니다.**
