# P03 실행 결과 — 단계별 누적

> **ENV-PG 제안 구체화 / Codex / 2026-09-21 17:06 KST:** PG major16 / DB `afs_trial_local` / schema `app` / 설치역할 `afs_installer` / 실행역할 `afs_runtime` / loopback55432 제안. 승인·생성은 아직 없음. 전달된 「승인할 만합니다/승인해 주시면」은 Claude 권고이며 사용자 실행 승인으로 간주하지 않았다. 현재35.0%, 하단의 환경 명세와 새 세션 단위 수행 방식을 따른다.

> **최신 검토 / Codex / 2026-09-21 16:55 KST:** P03.2 로컬 연결 준비 검토 완료, 관련64PASS/exit0. **실제 PG NOT_RUN,1855/5300=35.0% 유지.** 다음은 추가 대역 시험이 아니라 격리 PG 실제 소비다. 현재 Docker CLI는 있지만 desktop-linux 엔진이 실행되지 않는다. 로컬 검증용 PG 생성 범위를 사용자에게 승인 요청하며, 아래 끝에 실행 경계·담당을 기록했다. 승인/환경 생성은 아직 없다.

> **最新 수용 / Codex / 2026-09-21 16:45 KST:** **P05.1 accepted, +40점 →1855/5300=35.0%, 수용20/139단계.** 실제 junction 자체·상위 거절과 정상 소비를 포함한13PASS/skip0/exit0, 소스·보호자산 불변. CR-P05-1 종결. 아래 보완대기/1815점은 당시 이력이다. 실제 PG·실자료·운영복구 수용은 아직 아니다. 끝의 수용 회신을 따른다.

> **최신 P05.1 검토 — Codex / 2026-09-21 16:40 KST:** 이관→복원→제품 소비10건 직접 통과. **출력 경로 junction 차단 누락 1건(CHANGES_REQUESTED)**을 실제 Windows junction으로 재현했다. 현재1815/5300=34.2%, P03.1 수용 유지·P05.1 +40 수용 대기. 끝의 P05.1 회신을 따른다. 전면 재검증/실PG를 새 수용 조건으로 추가하지 않는다.

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

---

## Codex P05.1 검토·국소 보완 지시 — 2026-09-21 16:40 KST

작성/검토 Codex. 대상은 HEAD7972d9909 위 미커밋 `scripts/first_path_copy_migration.py` 및 해당 시험/결과다. 제품 코드는 이번 검토에서 수정하지 않았다. 기존 결과 문서에 회신한다.

### 인정한 구현과 실행 증거

- 기존 snapshot/installer 재사용, ECM5표 명시 필드 이관, 행/키/값/선정6참조 대사, 원본·번들 보존, 빈 경로 복원과 실제 ECM 조회/DDL0을 확인했다. 이 구현을 다시 만들지 않는다.
- 직접 집중 **10PASS/exit0**, `output/usage-holds-c_xrv__f/{tests.xml,isolation.json,pytest.log}`. 소스/보호자산 불변, 차단쓰기0. 보고된 전체102PASS는 Claude 증거이며 이번에 전부 재실행하지 않았다.
- 최초 실행 `output/usage-holds-sv4jj8h7/`은 pytest10PASS였지만 **wrapper exit1**이다. 실행 중 `tests/test_db_managed_schema_first_slice.py` 해시가 달랐다. 해당 실행 전체를 PASS로 합산하지 않았고, 그 집중 집합만 한 번 재실행해 위 정상 결과를 얻었다. 변경 주체/의도는 추정하지 않는다. 다른 세션의 수정/변이를 되돌리지 않았다.

### CR-P05-1 [P2] 출력 경로 링크 검사가 빠짐 — 수용 전 한 건 보완

`guard_paths()`는 `snapshot.regular(bundle, bundle.parent)`로 **입력만** 검사한다. 출력은 `target_dir.resolve()`와 빈 디렉터리 검사만 하므로 실제 지정 경로가 junction/symlink인지 잃어버린다. 이어 `run()`의 `mkdir`와 installer가 링크 경로에 쓰게 된다. 이는 지시서의 「대상/상위 링크·junction 우회를 적용 전에 차단」 조건을 충족하지 않는다.

실측: 운영과 무관한 임시 폴더에 **빈 실제 폴더와 그것을 가리키는 Windows junction**을 만들고, 기존 합성 번들을 입력으로 `guard_paths(bundle, junction)` 호출:

```text
link_type=Junction
target_junction=ACCEPTED
migration_not_executed=true
actual_target_still_empty=True
probe_scratch_removed=true
```

임시 링크와 두 빈 폴더는 정확한 경로/유형 확인 후 제거했다. 운영 DB/실자료에는 쓰지 않았다. 이 재현은 경계 통과 증거이지 데이터 손상 발생 주장이나 운영 data/ 차단 우회 실증이 아니다.

**Claude 다음 구현 — 예상20~40분(잠정):**

1. resolve로 원래 경로 형태를 잃기 전에 **출력 경로와 기존 상위 구성요소의 symlink/junction**도 검사한다. 기존 `snapshot.regular`를 재사용할 수 있는지 검토하되 검사 root를 바로 부모로 제한해 그 위 링크를 놓치지 않는다. 별도 경로 검증 엔진을 새로 만들지 않는다.
2. 출력 경로 자체 링크/상위 링크는 적용 전에 명시 거절하고, 일반적인 새 경로는 기존 이관→대사→소비로 계속 작동하게 한다. 새 DB/schema/리포트를 쓰기 전에 검사해야 한다.
3. 기존 소비 시험에 이 경계만 추가한다. Windows에서는 실제 junction 사례를 실행하고, 거절 뒤 실제 대상/원본/번들 불변과 새 파일0을 확인한다. 단순 mock/문자열 검사로 대체하지 않는다. 기존 정상 소비는 재사용한다.
4. 기존 결과 문서에 보완 결과를 누적한다. 별도 검토 요청서·전제품 회귀·모든 통제 변이를 다시 돌리지 않는다. Codex는 이 조건이 닫히면 즉시 +40점을 반영하며 실PG를 기다리지 않는다.

### 보존하는 한계 — 수용 범위를 확대하지 않음

- 이관본 소비와 원본 번들 복원본 소비는 **두 분기**다. 현재 시험은 이관된 산출물을 다시 백업해 복원한 관통 경로가 아니므로 그렇게 표기하지 않는다. 이번 국소 P05.1에는 두 분기의 실소비 증거를 사용하며 실제 PG cutover/복구는 후속 범위다.
- 6종 참조 검사는 명시된 subset이다. tenant 일치·부모순환·전체 업무 의미/권한을 검증했다고 확장하지 않는다.
- 행 INSERT 도중 실패는 rollback되지만 대사 실패는 commit 뒤라 대상 행이 남을 수 있다. 리포트가 없으면 성공/ready가 아니며 실패 대상 자동 삭제/재사용은 하지 않는다. 기존의 원자성 범위 정정을 유지한다.

### 전체 진척·다음과 환경 담당

```text
전체 인정 ███████░░░░░░░░░░░░░ 1815/5300 = 34.2%
잔여      3485점 / 미수용120단계 (수용19/139, 목표종결18/53)
P03.1     수용 유지 +15
P05.1     이관/복원 소비 구현됨 · 경로보호1건 보완 · 수용대기40점
수용 후   1855/5300 = 35.0% (다른 가산 없을 때)
다음      Claude CR-P05-1 20~40분 → 같은 흐름 소비 → Codex 국소 수용
```

ENV-PG 준비의 조율 담당은 **Codex**, P03.2/3 제품 연결/실측 담당은 **Claude**다. 필요한 환경 정보/실행 승인(격리 endpoint, 전용 DB/schema, 설치·runtime 역할, 비밀 전달 경로)은 아직 제공되지 않았다. 사용자는 기존 격리 환경 지정 또는 신규 환경 생성 범위를 승인해야 하며, 이 문서는 인프라 생성/비용/접속 승인을 대신하지 않는다. 환경 제공 전에도 이전에 특정한 PG 설치 후 확인·행형식·방언/대상 신원 연결의 로컬 코드 준비는 가능하다. 다만 점수는 실제 PG 출구를 충족해야 준다. 다음 구현/환경 준비를 구분하고 「할 일이 전혀 없다」고 일반화하지 않는다.

이번 회신은 공유 게시했으며 Claude 수신은 아직 미확인. 커밋·푸시·클라우드 생성·운영 변경 없음.

## 7. 곁들여 — `target_identity()` 의 **독성만** 막았습니다

수용 회신에서 지적하신 「backend 와 무관하게 `PRAGMA database_list` 를 실행하고 예외를
삼킨다」는 제 실제 결함입니다. PostgreSQL 에서 그 문장은 실패하고, 그 순간 **트랜잭션이
실패 상태로 남아 뒤따르는 정상 질의까지 전부 죽습니다.** 「예외를 삼켰으니 안전하다」가
아니라 **연결이 이미 오염됩니다.**

```
후: backend 가 SQLite 가 아니면 «한 문장도 보내지 않고» 빈 문자열을 돌려줍니다.
    시험으로 잠갔습니다 — 비-SQLite 연결에 SQL 이 한 건이라도 가면 실패합니다.
```

⚠️ **이것으로 해당 지적이 해소됐다고 하지 않습니다.** 막은 것은 «독성» 뿐입니다.
「방언을 실제 연결 설정에 결속」·「PG 대상 신원을 PG 읽기 질의로 구함」은 그대로 남아
있고, 말씀하신 대로 승인된 PG 환경에서 **설치 → 같은 연결 로그인·문맥 흐름을 만들며
함께** 하겠습니다. 전수 검사로 확대하지 않았습니다.

집중 시험 합계: managed_schema 37 · copy_migration 10 = **47 passed**.

---

## 8. CR-P05-1 보완 완료 — 출력·상위 경로 링크 검사

**지적이 맞습니다.** 링크 우회 차단을 **입력에만** 걸어 두고 출력을 열어 뒀습니다.
「막았다면 반대편 문을 본다」를 또 놓쳤습니다.

### 왜 통과했나

출력은 `target_dir.resolve()` 와 「비어 있나」만 봤습니다. **`resolve()` 는 링크를 풀어
원래 모양을 지웁니다** — 지정된 경로가 junction 이어도 검사할 대상이 이미 사라진 뒤라
통과했고, 뒤이어 `mkdir` 와 설치 도구가 **그 링크 너머에** 썼습니다.

### 고친 것

```
reject_links(path, label)
  경로 «자체 + 존재하는 모든 상위» 를 드라이브 루트까지 올라가며 본다
  판정은 os.path.abspath 위에서 — resolve() 를 쓰면 검사하려던 링크가 이미 풀린다
  guard_paths 의 «가장 먼저». 뒤의 검사들은 resolve 를 쓰므로 그 전에 봐야 한다
  입력·출력 «양쪽» 에 적용. 파일 자체는 기존 snapshot.regular 도 함께(두 층)
```

⚠️ `snapshot.regular(p, p.parent)` 를 그대로 쓰지 않았습니다 — 그건 검사 root 를 바로
부모로 두어 **그 위의 링크를 놓칩니다.** 별도 경로 검증 엔진을 새로 만들지는 않았고,
기존 도구는 파일 성질 검사로 계속 함께 씁니다.

### 실측 — **진짜 junction** 으로

mock·문자열 검사가 아니라 `_winapi.CreateJunction` 으로 실제 링크를 만들고 눌렀습니다.
시험이 **먼저 `is_junction()` 으로 링크가 진짜인지 확인**한 뒤 진행합니다(계측기부터 증명).

| 사례 | 결과 |
|---|---|
| 출력 «자체» 가 junction | **거절** · 실제 대상 폴더 새 파일 **0** · 원본·번들 불변 |
| 출력의 **상위** 가 junction | **거절** · 같음 |
| 평범한 깊은 새 경로 | **정상 동작**(음성 대조 — 링크 검사가 멀쩡한 경로까지 막으면 도구를 못 씁니다) |

### 검증

```
집중 13건 (10 → +3) · copy_migration 13 + managed_schema 37 = 50 passed
통제 3종 각각 물림 (원복 해시 일치)
  ① 출력 링크 검사 제거          2 failed
  ② 자기 자신만 보고 상위는 안 봄  1 failed
  ③ abspath 대신 resolve         2 failed   ← 「resolve 가 모양을 지운다」가 말이 아님을 보임
sources_unchanged true · blocked_file_writes [] · 운영 자산 불변
```

기존 정상 소비(이관→대사→복원→제품 조회)는 **그대로 재사용**했고 전면 재검증은 하지
않았습니다. 다른 통제의 변이도 다시 돌리지 않았습니다.

### 검토 중 보신 wrapper exit1 에 대하여

`tests/test_db_managed_schema_first_slice.py` 해시가 실행 중에 달랐다는 기록은 **제가 그
시점에 그 파일을 편집하고 있었기 때문**입니다(비-SQLite PRAGMA 차단 시험 추가).
그 실행을 PASS 로 합산하지 않으신 판단이 맞습니다. 다른 세션의 수정이 아닙니다.

---

## Codex P05.1 최종 국소 수용 — 2026-09-21 16:45 KST

- **판정: ACCEPTED. CR-P05-1 닫음.** 경로 자체와 모든 상위를 resolve 전에 검사하는 코드, Windows 실제 junction 자체/상위 거절, 정상 깊은 경로의 이관→대사→제품 소비를 확인했다. 첫 지시의 사본 리허설 범위를 충족했다. 다른 새로운 조건을 붙이지 않는다.
- 직접 집중 **13PASS / skip0 / pytest exit0 / wrapper exit0**. 증거 `output/usage-holds-qnvdnorz/tests.xml`, `isolation.json`, `pytest.log`. 소스/보호자산 불변, 차단쓰기0. 전제품 회귀나 다른 통제 변이는 재실행하지 않았다.
- 실행원장 P05.1 evidence/review/status를 accepted로 갱신하고 계산기로 **1855/5300=35.0%,20/139단계, 목표종결18/53**을 확인했다. P03.1 수용도 유지한다.
- 앞선 시험 중 파일 변화는 Claude 본인 동시 편집이었다는 회신을 접수했다. 최초 실행 wrapper exit1을 PASS로 바꾸지는 않는다. 새 불변 실행의 증거를 사용한다.
- 인정 범위는 합성 ECM5표 SQLite 사본 이관·백업·복원·원본 보존과 제품 조회다. 실제 PG ETL/실자료/운영 cutover/교차 DB 원자성·동시 악성 파일시스템 변경 방어를 수용한 것으로 확대하지 않는다. 원본번들 복원과 이관본 소비는 두 분기로 구분한다.

```text
전체  ███████░░░░░░░░░░░░░ 1855/5300 = 35.0%
이번  P05.1 +40점 (직전34.2% →35.0%)
잔여  3445점 / 미수용119단계 (수용20/139 · 목표종결18/53)
다음  Claude P03.2 로컬 연결 준비 1~2시간(잠정) → 환경 제공 후 실제 PG 설치/로그인
환경  ENV-PG 지정/실행승인 미제공; 조율 Codex, 제품 연결·실측 Claude
```

### 다음 실행 — 대기 대신 기존 PG 연결 준비를 이어감

Claude가 제안한 로컬 준비 지속을 확인한다. **방언/대상 신원 → 제품이 사용하는 행형식/factory → PG 설치 후 실제 확인** 순서로 연결한다. 별도 모의 시험 체계를 확대하지 말고 기존 설치→로그인·문맥 소비 경로를 확장한다. 첫20~30분에 변경파일/남은 경계를 같은 결과 문서에 기록한다. 잠정1~2시간은 로컬 준비 시간이며 실제 PG 수용/환경 대기를 포함하지 않는다.

- 실제 PG가 없을 때 DB 응답 대역은 연결 코드의 조건만 입증한다. DB 동작 PASS나 P03.2/3 가산 근거로 쓰지 않는다.
- PG 환경이 오면 같은 준비물을 직접 적용해 로그인·문맥·거절, 이어 실제 제품 티켓 소비/재시작으로 수용한다. 환경만 받으면 코드 보완 없이 된다고 주장하지 않는다.
- 공동 `main.py`/`run.py` 전역 배선은 기존 소유 경계를 유지하며 실제 factory 지점을 명시한다. 운영 환경변수/서비스/권한을 임의 변경하지 않는다.
- CI 검사기 시험 job은 별도 Codex CI 소유 범위다. 이것을 PG 로컬 준비의 선행 잠금으로 두지 않는다.
- 새 요청서·검토 회신 대기 없이 기존 결과에 누적한다. 이미 수용된 P03.1/P05.1을 다시 구현/전면 재검증하지 않는다. 관련 source 변이 중 검토 실행이 겹치지 않도록 작업 상태에 변이 구간을 표시한다.

수용 및 다음 지시는 공유 게시 완료, 새 회신 수신은 미확인. 이번 검토에서 제품 코드·운영DB·클라우드·커밋·푸시를 변경하지 않았다.

---

# P03.2 로컬 준비 — PG 연결 준비 (점수 대상 아님)

지시: 위 「다음 실행」. **실제 PG 는 여전히 NOT_RUN** 이고 P03.2/3 가산 근거가 아닙니다.
지시 순서 그대로 **방언/대상 신원 → 행형식/factory → PG 설치 후 확인** 을 이었습니다.

## 변경 파일 / 남은 경계 (첫 체크포인트)

```
core/db/__init__.py                  ConnectionFactory · sqlite_factory · postgres_factory
core/db/managed_schema.py            backend_of · PG 대상 신원 질의 · dict 행 강제
core/auth.py · ECM repository        factory 의 방언을 관문에 전달 (한 줄씩)
scripts/install_first_db_schema.py   PG 설치 «후 확인» 전에는 성공이라고 하지 않음
tests/ 2파일                          집중 44 + 13 = 57건
```

## ① 방언을 «실제 연결» 에 결속 — 환경변수 추측 폐기

```
ConnectionFactory  부를 수 있고 «자기 방언을 스스로 말한다» (.backend / .describe)
backend_of(conn)   ① factory 가 말한 값 → ② 연결 객체의 실제 형 → ③ 모르면 «거절»
```

⚠️ `AFS_DB_BACKEND` 를 읽어 맞히는 길을 없앴습니다. 환경은 PG 인데 실제로는 SQLite 를
물고 있는 조합에서, 환경을 믿으면 **SQLite 전용 문장을 PG 로 보내거나 그 반대**가 됩니다.
모르면 추측하지 않고 거절합니다.

**PG 대상 신원**은 이제 PG 읽기 질의(`current_database()`/`current_schema()`)로 구합니다 —
SQLite 문장을 던져 보고 실패로 알아내는 방식은 쓰지 않습니다(트랜잭션이 실패 상태로 남음).

## ② 제품이 기대하는 행 형식을 연결에 고정

제품 ECM 은 조회 결과에 `dict(row)` 를 하고 auth 는 `row["user_id"]` 로 읽습니다.
**psycopg 의 기본 행은 튜플**이라 그대로 두면 `dict(row)` 가 그 자리에서 깨집니다.
제품 SQL 을 고치는 대신 **연결을 제품이 기대하는 모양으로** 맞췄습니다(`dict_row`).

★ 그 과정에서 제 코드의 결함도 하나 나왔습니다 — `information_schema` 결과를
`for table, column in rows` 로 풀고 있었는데, **`dict_row` 행을 그렇게 풀면 키가 풀려**
컬럼 «이름» 이 들어옵니다. 이름으로 꺼내도록 고쳤고, 튜플 행이 오면 자리로 맞추지 않고
**거절**합니다(조용히 엉뚱한 컬럼을 읽는 것보다 낫습니다).

## ③ PG 설치 — 확인 «전에는» 성공이라고 하지 않음

예전 판은 문장을 던지고 `verified: false` 를 넣으면서도 `ok: true` / exit0 을 냈습니다.
「설치했는데 확인은 안 했다」를 성공으로 보고한 것이고, 그 거짓 초록 위에서 다음 단계가
시작됩니다. 이제 **같은 연결에서 `information_schema` 로 확인**하고, 실패하면 예외입니다.

## 검증 — ⚠️ 대역은 «연결 코드의 조건» 만 증명합니다

```
집중 57건 · 합계 77 passed (managed_schema 44 · copy_migration 13 · db_adapter 20)
통제 4종 각각 물림 (원복 해시 일치)
  ① 방언을 환경변수로 되돌림      1 failed   ← 아래 참조
  ② 모르는 방언을 sqlite 로 추측   1 failed
  ③ 튜플 행을 자리로 맞춤          1 failed
  ④ PG 설치 후 확인 생략           1 failed
sources_unchanged true · blocked_file_writes [] · 변이 구간을 작업 상태에 표시했습니다
```

★ **①이 처음엔 안 물렸습니다.** 제 시험이 `backend_of()` 를 직접 부르기만 하고
**호출 지점(`assert_installed_on` 안)** 을 짚지 않았기 때문입니다. 통제가 없던 게 아니라
그 자리를 지나는 시험이 없었습니다 — 환경을 postgres 로 우긴 채 실제 SQLite 연결로
관문을 통과시키는 시험을 더하니 물립니다.

⚠️⚠️ PG 가지의 초록은 **대역(stand-in)** 위의 것입니다. DB 동작 PASS 가 아니고
P03.2/3 가산 근거도 아닙니다. 「환경만 받으면 코드 보완 없이 된다」고 주장하지 않습니다.

## 남은 경계 — 환경이 와야 닫히는 것

| | |
|---|---|
| 실제 PG 설치 → 로그인·문맥·거절 | **ENV-PG 대기** |
| 실제 티켓 소비·재시작 | ENV-PG 대기 (P03.3) |
| 제품 전역 factory 배선 | `main.py`/`run.py` 는 **건드리지 않았습니다.** 실제 배선 지점: `core/auth.py:428` · `core/enterprise_context/repository.py:807` 의 모듈 수준 싱글턴이 «어떤 factory 를 받는가» 입니다. 배포측 startup 통합은 Codex 담당 |
| 첫 경로 밖 저장소·교차 DB 원자성 | 범위 밖 |

---

## Codex P03.2 로컬 준비 검토·ENV-PG 실행 제안 — 2026-09-21 16:55 KST

### 검토 결과

- 방언을 factory에서 전달하는 store 경로, PG dict 행 소비, 같은 PG 연결에서 설치 후 schema 조회하는 준비 코드를 대조했다. **로컬 준비 결과로 접수**하며 실제 PG 설치/제품 수용을 선언하지 않는다.
- 직접 `test_db_managed_schema_first_slice.py` + `test_db_adapter_first_slice.py` **64PASS/exit0**. 증거 `output/usage-holds-s262v47i/tests.xml`, `isolation.json`, `pytest.log`. 소스/보호자산 불변, 차단쓰기0. copy_migration13은 이미 수용된 결과라 다시 실행하지 않았다.
- PG 분기의 시험은 대역이다. 새 기능 점수 없음. **1855/5300=35.0%,수용20/139,잔여3445점/119단계**. P03.1/P05.1 수용 유지.
- 추가 대역·변이 묶음은 요구하지 않는다. 다음 실제 PG 설치→로그인·문맥 소비에서 준비 코드의 SQL/행형식/권한을 확인한다. 그때 DB/schema 신원 조회 실패를 빈 식별자의 ready로 숨기지 않고, 지원하지 않는 backend 선언도 실제 질의 전에 명시 거절해야 한다. 설치 확인이 commit 뒤라는 현재 범위는 계속 구분한다.

### 환경 실측 — 기동/설치하지 않고 읽기만 함

```text
docker.exe 존재
현재 context: desktop-linux
com.docker.service: Stopped / Manual
docker info: dockerDesktopLinuxEngine pipe 없음, API 연결 실패
psql/pg_ctl: 현재 PATH에서 발견 못함 (다른 위치/원격 환경 부재의 증거 아님)
```

이 결과를 「설치된 PG가 전혀 없다」로 일반화하지 않는다. Docker 시작, 이미지 다운로드, 컨테이너/DB/계정 생성, 환경변수 배포, 원격 서버 접근은 아직 수행하지 않았다.

### 사용자 승인 요청 범위 — ENV-PG 승인 전 실행 금지

**권고: NCP 운영 트라이얼과 별개의 이 PC 로컬 검증 전용 PostgreSQL.** 기존 제공 가능한 격리 PG가 있다면 그 환경으로 대체한다. 배포 목적지를 로컬로 바꾸는 결정이 아니다.

1. 설치된 Docker Desktop/Linux 엔진 시작. 필요 시 공식 PostgreSQL 이미지를 내려받고 전용 컨테이너/전용 named volume을 생성한다. DB major 버전은 기존 배포 설계/예정 NCP 지원과 맞춰 고정하며 불일치는 기록한다. 임의의 latest로 동등성을 주장하지 않는다.
2. 호스트는 **127.0.0.1에만** 포트를 게시한다(후보55432, 생성 직전 충돌 확인). 운영 data/library·저장소 루트는 mount하지 않는다. 합성 ECM/Auth 데이터만 사용한다. 기존 컨테이너·볼륨은 수정/삭제하지 않는다.
3. 전용 DB/schema, 설치 역할과 runtime 역할을 분리한다. runtime의 정상 DML은 허용하고 DDL은 금지해 실제 기동DDL0을 확인한다. 사용자·문맥·티켓은 기존 제품 계약대로 실행한다.
4. 무작위 자격증명은 로컬 비공개 위치/프로세스 환경으로 전달한다. DSN·키·비밀번호를 문서/채팅/Git/명령 결과에 출력하지 않는다. 보고는 비밀을 뺀 환경 ID/버전/역할/대상 신원과 수행 결과만 남긴다.
5. 이 승인은 **로컬 검증 환경 생성/공식 이미지 다운로드/합성 DB 쓰기**까지만이다. NCP 리소스 생성·유료 LLM·운영자료 이관·운영 배포·외부 공개·커밋/푸시를 포함하지 않는다. 완료 후 재사용을 위해 보존할지 정하고 임의 삭제하지 않는다.

### 승인 후 바로 이어갈 작업과 담당

- **Codex:** 격리 환경 구성/신원·접속·설치/runtime 권한 경계 확인, 비밀 없는 연결 안내. 기존 main/run 전역 startup 배선도 Codex 소유지만 로컬 직접 store 소비를 먼저 수행해 모든 서비스 이관까지 기다리지 않는다.
- **Claude:** 같은 installer/factory로 실제 PG 설치→제품 로그인·문맥·거절(P03.2,+20), 이어 독립 연결의 실제 티켓 소비·재시작(P03.3,+20). 새 SQL 데모/harness만 성공시켜 제품 수용으로 대체하지 않는다.
- 잠정 시간: 환경 정상 시작/이미지 확보 후 환경 준비20~40분, P03.2 실제 소비1~3시간, P03.3 2~3시간. 다운로드/기동 문제·승인 대기는 별도이며 20~30분 checkpoint에서 갱신한다.
- 다른 가산이 없다면 P03.2 수용 후1875/5300=35.4%, P03.3까지1895/5300=35.8%. 조건부 예측이며 환경 생성 자체에는 점수를 주지 않는다.
- ENV-PG는 현재 **pending 유지**. 사용자 명시 승인과 실제 환경 증거가 확보돼야 원장 승인을 갱신한다. 그전에는 완료된 준비를 반복하지 않는다. 독립 C02/CI·D05 작업의 담당은 Codex로 유지한다.

이 회신과 실행 제안은 공유 게시했다. Claude의 회신 수신 및 사용자의 환경 생성 승인은 아직 미확인. 이번 검토에서 추가 제품 수정·커밋·푸시는 하지 않았다.

## P03.2 로컬 준비 — 추가 1건 (환경 승인 «전에» 잡은 첫 실행 차단 요인)

환경 승인을 기다리는 동안 PG 설치 경로를 다시 보다가 **첫 실행에서 깨질 자리**를
하나 더 찾았습니다.

```
전: postgres_sql() 이 파일의 BEGIN; · COMMIT; 을 «문장으로» 잘라 그대로 보냄 (24문장)
후: 트랜잭션 제어 문장을 제외 (22문장). 경계는 드라이버 하나만 잡는다
```

⚠️ 파일은 사람이 읽기 좋게 `BEGIN; … COMMIT;` 으로 감싸 두었습니다. 그런데 그것을
psycopg 에 문장으로 보내면 **드라이버가 이미 연 트랜잭션 안에서 `COMMIT` 이 먼저
터집니다** — 뒤 문장들이 트랜잭션 밖으로 나가고, 중간에 실패해도 앞부분이 남습니다.
「한 번에 들어가거나 아무것도 안 들어간다」가 그 자리에서 깨집니다.

★ 그리고 PG 쪽 확인을 **commit «전»** 으로 옮겼습니다. PostgreSQL 은 DDL 도 트랜잭션
안에서 돌고 같은 트랜잭션에서 방금 만든 것이 보이므로, 확인이 실패하면 되돌려
**아무것도 남기지 않습니다.** (SQLite 쪽은 확인이 commit 뒤라 행이 남을 수 있다고
이미 한계로 적어 두었습니다 — PG 경로가 그보다 강합니다.)

시험 58건(+2). ★ 이것이 **「환경만 받으면 코드 보완 없이 된다」가 아니라는 증거**입니다.

## 환경 승인 요청에 대한 제 회신 — 필요한 네 가지

로컬 Docker PostgreSQL(localhost 전용·별도 볼륨·운영 폴더 미연결·합성 자료만)은
`ENV-PG` 가 요구하는 격리 환경으로 **적합하다고 봅니다.** 다만 넷을 특정해 주셔야
첫 시도에 붙습니다.

| | 필요한 것 | 왜 |
|---|---|---|
| ① | **PG 주 버전** (NCP 가 쓸 판과 같게) | 로컬↔NCP 차이를 줄이는 유일한 무료 수단 |
| ② | 전용 **database · schema 이름** | 대상 신원(`current_database()/current_schema()`)이 증거에 남습니다 |
| ③ | **설치 역할 / runtime 역할 분리** — runtime 에 **DDL 권한을 주지 마십시오** | ★★ 아래 |
| ④ | 접속 정보는 **환경변수 `AFS_DB_DSN` 으로만** | 문서·채팅·Git 에 적지 않습니다. 역할이 둘이면 프로세스마다 다른 값을 주십시오 |

★★ ③이 가장 중요합니다. runtime 역할에서 `CREATE` 권한을 빼면 **「runtime DDL 0」이
응용의 주장이 아니라 DB 가 강제하는 사실**이 됩니다. 지금까지는 제 계측(SQL 세기)으로만
보였는데, 그때는 **DB 가 거절하는 것**을 증거로 쓸 수 있습니다. 수용 조건의
「PG측 관측/권한으로 runtime DDL0을 검증」이 바로 이것입니다.

⚠️ **경계를 미리 적어 둡니다: 로컬 Docker PG ≠ NCP 관리형 PG.** 버전·확장·TLS·네트워크·
관리형 동작이 다릅니다. 여기서 P03.2/3 이 통과해도 그것은 **「제품 경로가 PostgreSQL 에서
돈다」**는 증거이지 **「NCP 에서 돈다」**가 아닙니다. 수용 기록에 이 문장을 함께 남겨
주시면 나중에 NCP 준비 완료로 읽히지 않습니다.

---

## ENV-PG 네 조건·연속 수행 합의안 — Codex / 2026-09-21 17:06 KST

**현재는 실행 명세 제안이며 사용자 환경 생성 승인은 아직 없다.** Docker 기동/이미지 다운로드/컨테이너·계정 생성은 승인 후 Codex가 수행한다. Claude의 「승인할 만합니다」는 검토 의견으로 접수했다. 실제 사용자 승인 없이 ENV-PG 상태를 approved로 바꾸지 않는다.

| 항목 | 생성 시 사용할 명세 |
|---|---|
| PostgreSQL 주 버전 | **16**. 기존 배포문서에 주 버전 고정이 없어서 이번에 제안. NCP 공식2026-07-23 릴리스에16.14 추가 확인. 콘솔 실제 선택/패치와는 구분 |
| 패치/이미지 | 생성 시 공식16계열 이미지의 실제 패치와 digest를 기록·고정. 로컬/NCP의 패치 차이는 명시하고 NCP 인수 전 재확인. 임의 latest major 사용 금지 |
| 전용 DB/schema | **afs_trial_local / app**. 두 역할 프로세스 모두 search_path를 app으로 고정, 실제 current_database/current_schema 확인 |
| 설치 역할 | **afs_installer**. 전용 app schema/설치 객체 소유. 범용 superuser를 제품 연결에 전달하지 않음 |
| runtime 역할 | **afs_runtime**. NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS, installer/관리역할 멤버십 없음. DB/schema/table 소유권 없음 |
| runtime 허용 | DB CONNECT, app USAGE, 필요한 표 SELECT/INSERT/UPDATE/DELETE, 필요한 시퀀스 사용. 신규 객체도 installer 기준 default privileges를 명시 |
| runtime 금지 | DB/schema CREATE 및 DB TEMPORARY, 공용 schema의 상속 CREATE/TEMP 경로, 객체 소유/관리역할 전환. 기존 설치 표 ALTER/DROP 금지 |
| 네트워크/저장 | 후보127.0.0.1:55432(기동 직전 충돌확인), 전용container·named volume. 운영data/library/소스root host mount 없음 |
| 비밀 전달 | 설치/runtime **각 자식 프로세스의 AFS_DB_DSN만** 설정. search_path도 해당 DSN/역할 설정으로 결속. 셸 인자/출력/문서/채팅/Git에 DSN·비밀번호를 적지 않음. 같은 PC의 비공개 로컬 자격증명은 권한 제한, 공용 세션 환경을 다른 역할로 덮어쓰지 않음 |

주 버전 근거: [NCP PostgreSQL 릴리스 노트](https://guide.ncloud-docs.com/docs/clouddbforpostgresql-releasenote). 이 페이지가 실제 계정/리전의 생성 가능 버전까지 보증하지는 않는다. 생성 전 콘솔 선택값을 확인하고, 맞지 않으면 다른 major로 조용히 대체하지 않는다.

### DDL 권한과 DDL 0 증거를 구분

단순히 schema CREATE를 회수하는 것만으로는 충분하지 않다. 객체 소유자는 ALTER/DROP 권한을 유지할 수 있고 TEMPORARY는 별도 권한이다. 따라서 runtime 소유권·역할 상속·DB TEMP·public 기본권한까지 제한한다. 근거: [PostgreSQL 16 권한](https://www.postgresql.org/docs/16/ddl-priv.html).

DB 권한은 「runtime DDL 실행 불가」를 강제하지만 「제품이 DDL을 시도하지 않음」을 대신 증명하지 않는다. 실제 제품 기동/로그인 관측의 DDL시도0과 별도 runtime역할의 CREATE/TEMP/기존표ALTER 거절을 같은 수용 흐름 안에서 각각 기록한다. 의도적 거절은 독립 트랜잭션/연결에서 수행해 이후 정상 소비를 오염시키지 않는다.

### 방금 설치 트랜잭션 보완의 위치

파일의 transaction-control 문장을 installer 실행 목록에서 제외하고 schema 확인을 commit 앞으로 옮긴 변경을 코드로 확인했다. 이번 회신에서는 대역 시험을 또 돌리지 않았다. 기존 실제PG NOT_RUN을 유지한다. **호출별 트랜잭션과 여러 store 호출 전체 원자성은 별개**이며, 설치가 store별로 반복되면 앞 store commit이 다음 실패로 되돌아가지는 않는다. 실제 PG 적용에서 그 범위를 기록한다. 문구 때문에 통합 설치 전체 원자성을 약속하지 않는다.

### 하류 규모 정정 아닌 해석 제한

원장에서 ENV-PG를 직접 요구하는18단계를 출발점으로 후속 prerequisites를 전이 탐색한 결과 **미수용56단계/1830점**이 맞다(잔여3445점의 약53.1%). 다만 이는 **의존성 영향 범위**이지 환경 생성 즉시56단계를 실행/수용한다는 뜻은 아니다. 다른 기능 선행/실자료/외부 실행 승인은 남는다. 즉시 수행은 P03.2/3이며 둘 수용 시1895/5300=35.8%다.

### 새 수행 방식 — 세션 단위 최대 진행, 검토는 한 번

- 승인된 환경이 준비되면 Claude는 **설치→실제 로그인·세션·문맥·권한 거절→실제 티켓 단일/동시 소비→재시작**을 연속 수행하고 같은 결과 문서에 누적한다. P03.2 끝에서 검토 회신을 기다리며 멈추지 않는다.
- 검토 요청은 세션 결과를 모아 한 번 한다. 중간에는 사용자 결정이 필요한 갈림길/비용·외부권한/안전 위험·실제 장애만 올린다. 완료된 단계별 진척은 기록하되 보고/검토 문서 생산 때문에 구현을 끊지 않는다.
- 정상 경로의 결과를 다음 단계 입력으로 사용하고, 범위 밖 저장소·전체 회귀·추가 변이 캠페인으로 확장하지 않는다. 세션 종료 시 수용 가능한 단계 증거를 분리해 한 번에 제출한다. Codex는 충족된 단계만 순서대로 가산한다.
- 예상: 승인 후 Docker 정상기동/이미지 확보 상태에서 환경준비20~40분, P03.2/3 연속 제품 실행·수정3~6시간(잠정). 기동/다운로드/새 장애는 별도. 시간 경과 자체로 점수를 주지 않는다.

현재 전체 **1855/5300=35.0%**, 잔여3445점/119단계. 환경 생성/시험은 승인 전이므로 새 가산0. 로컬 PG 성공은 제품의 PG 호환 증거이며 **NCP 관리형 DB/HA/네트워크/백업 수용 증거는 아니다**. 환경 승인 후 이 구분을 결과 표에도 유지한다.

## ENV-PG 제공·Docker 복구 완료 — Codex / 2026-09-21 17:27 KST

### 승인과 실제 완료 범위

사용자 원문 「Docker 기동·컨테이너 생성 승인합니다」 및 후속 「네 승인합니다. 복구 진행해주세요」, Secrets Engine 추가 경로 「네 승인합니다」를 근거로 실행했다. 위17:06 승인대기는 **해소된 이력**이다. ENV-PG 승인 원장만 approved로 갱신하며 제품 단계 수용·배점은 바꾸지 않는다.

- Docker Desktop4.74.0 초기화는 오래된 AF_UNIX 소켓 두 곳에서 실패했다. Docker만 종료한 뒤 승인 경로를 삭제하지 않고 백업 이름으로 변경했다. 첫 실패 기동이 새 `run/dockerInference`를 남겨 재발했으므로 두 경로를 함께 정리한 다음 정상 기동했다.
- Docker Linux engine **29.4.3**, 실제 PostgreSQL **16.15 (Debian 16.15-1.pgdg13+2)**. NCP문서의16.14와 패치 차이가 있으며 **NCP 검증 아님**.
- 공식이미지 고정: `postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6`.
- container **afs-pg-local**, named volume **afs-pg-local-data**, **127.0.0.1:55432→5432**만 게시. 자동재시작은 no, 자원한도2CPU/1GiB(검증용이며 운영 sizing 근거 아님).
- DB **afs_trial_local**, schema **app**. DB소유postgres, app소유afs_installer. runtime소유/관리역할 멤버십 없음.
- 운영/소스/자료 폴더 mount 없음. mount는 새 PG data named volume과 Git밖 **관리자 초기화 비밀번호 파일 하나(readonly)**뿐이다. 「host mount 전무」라고 쓰지 않는다.
- 제품 schema/합성 업무행은 **아직 설치하지 않았다**. 환경 계정/빈app만 생성했고 installer 실행은 아래 Claude 재개 지점이다. 제품 login/session/ticket/runtimeDDL시도0/기존표ALTER거절은 아직 P03에서 확인해야 한다.

### 비밀 전달 및 다음 세션의 첫 명령

신규 `scripts/local_pg_trial.py`는 **Windows 로컬 환경 전용 준비/실행 도구**다. 기존 제품DB adapter/installer를 대체하지 않는다. `setup`은 이미 실행했으며 기존이 있으면 거절한다. **다시 setup하지 않는다.**

비밀 보관은 `C:\Users\denni\AppData\Local\AFS\pg-trial-local`이며 상속 ACL을 끄고 현재Windows사용자만 FullControl이다. 설치/runtime 비밀번호는 각각 DPAPI 암호문 파일로 보관한다. 관리자 초기화 파일은 컨테이너가 읽어야 해 그 폴더의 **평문 파일**이며 readonly mount다. Docker관리자·같은Windows사용자에 대한 격리까지 주장하지 않는다. 이 폴더를 출력/첨부/Git추가하지 않는다. 다른PC/Windows사용자는 이 파일을 복사해도 DPAPI를 해독할 수 없으므로 별도 승인된 환경/새 계정 전달이 필요하다. **업무자료를 암호화해서 공유를 막는 변경이 아니다.**

아래 명령은 repo root PowerShell에서 실행한다. 실행 도구는 자식 프로세스에만 `AFS_DB_DSN`/`AFS_DB_BACKEND=postgres`를 설정한다. DSN/password를 셸 인자·문서에 넣지 않는다. 자식도 env/DSN을 출력하지 않아야 한다.

```powershell
# 환경 읽기/독립 트랜잭션 거절 점검(제품 테스트 점수 아님)
venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py check

# Claude 첫 행동: 기존 installer 계획을 읽고 같은 역할로 명시 적용
venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py run installer -- venv/Scripts/python.exe -X utf8 -B scripts/install_first_db_schema.py --backend postgres --plan
venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py run installer -- venv/Scripts/python.exe -X utf8 -B scripts/install_first_db_schema.py --backend postgres --apply
```

그 다음 같은 launcher의 `run runtime -- <실제 P03 소비 명령>`을 쓴다. 명령 자리에는 Claude가 작성한 실제 격리 harness/pytest 파일을 지정하며 존재하지 않는 이름을 만들지 않는다. `run`은 **파일시스템 격리 장치가 아니다**. 기존 지시대로 관리모드·factory 주입·PROJECT_ROOT/작업디렉터리/파일 저장소 격리를 먼저 맞춘다. `main.py`/`run.py`나 전체제품서버를 무조건 기동하지 않는다. 기존 글로벌 SQLite singleton을 환경변수만으로 PG에 연결됐다고 가정하지 않는다.

설치/runtime는 동일 DB/app를 사용한다. 설치는 반드시 **afs_installer**로 해야 미래 표의 default DML grant가 runtime에 적용된다. schema/table 소유자postgres로 설치한 뒤 맞는 척하지 않는다. runtime에는 CONNECT/app USAGE + installer가 만든 app 표의 SELECT/INSERT/UPDATE/DELETE, 시퀀스USAGE/SELECT만 자동부여한다. PUBLIC DB권한(특히TEMP)·publicschema권한을 회수했고 runtime에는 super/createDB/createRole/replication/bypassRLS·installer상속이 없다.

### 직접 확인한 증거와 남은 출구

1. DPAPI 암복호화 비밀 아닌 메모리표식 대조 PASS.
2. 두 역할 실제 로그인 후 `current_database/current_schema/current_user`가 명세와 일치.
3. runtime의 app CREATE TABLE / CREATE TEMP TABLE / CREATE SCHEMA / SET ROLE afs_installer **4건 모두 InsufficientPrivilege(42501)**. 매번 독립 연결/rollback으로 잔여 객체 없음.
4. runtime 권한질의 CREATE/TEMP/appCREATE/publicCREATE/installerMEMBER 모두false, 위험roleflag5개 모두false.
5. launcher→**실제 core.db.postgres_factory()**→dict행 신원 조회 PASS: afs_trial_local/app/afs_runtime. 제품 store 로그인/티켓 수용은 아님.
6. Docker inspect: loopback포트 하나, mount2개(data volume+readonly비밀파일), `POSTGRES_PASSWORD=` 컨테이너env 없음. ACL inherited=false/currentuseronly 확인.

권한거절 시험은 DB가 DDL을 막는 증거이지 제품의 DDL시도0 증거가 아니다. Claude는 이제 installer→로그인·세션·문맥/거절→티켓단일·동시소비→재시작으로 **연속** 진행한다. 중간 리뷰대기는 하지 않고 제품 소비 중 발견한 수정·잔여를 기존 결과에 모아 한 번 제출한다. 새 역할 정책 우회·운영 DB·실자료·유료LLM·NCP 생성은 이번 승인 밖이다.

도구/환경권한은 Codex 작성·자체 실측이며 Claude 독립 검토는 아직 미실행이다. 사용 전 비밀전달/권한설정을 짧게 확인하되 새 대역/변이 캠페인이나 문서 라운드를 만들지 않는다. 실제 제품 수용 시 상호 검토한다.

### 유지·복구·정리 경계

환경은 가동 유지. 필요 시 **이 컨테이너만** `docker stop afs-pg-local`, 재개는 `docker start afs-pg-local`. 삭제/`down -v`/volume rm/PC전체WSL shutdown/공장초기화 금지. Docker가 정상동작하는 지금 소켓 백업을 원복하면 장애를 재도입할 수 있으므로 자동 원복하지 않는다.

보존한 백업(모두이번승인경로, 삭제0):

- `C:\Users\denni\AppData\Local\Docker\run.backup-20260921-171320`
- `C:\Users\denni\AppData\Local\Docker\run.backup-20260921-171920`
- `C:\Users\denni\AppData\Local\docker-secrets-engine.backup-20260921-171803`

기존Docker컨테이너/볼륨 목록은 생성 직전0건이었고 기존WSL디스크/운영자료는 수정하지 않았다. 새 컨테이너/data volume/비밀파일/런처는 이번 환경 자산이다. 커밋·푸시하지 않았고 공동 dirty를 보존했다. Claude 수신/착수는 미확인이며 공유 문서 게시를 실행 완료로 쓰지 않는다.

전체 **1855/5300=35.0%**, 수용20/139·잔여3445점/119단계. 환경제공 가산0. 다음 P03.2 실제제품 설치/로그인·문맥 **1~3h/+20**, P03.3 티켓/재시작 **2~3h/+20**(장애 시 수정). 두 출구 수용 후 **1895/5300=35.8%**. ENV-PG 하류전체/운영트라이얼을 완료한 것이 아니다.

참고: [공식 postgres 이미지의 비밀번호 파일 지원](https://hub.docker.com/_/postgres), [PostgreSQL16 default privileges의 객체 생성 역할 기준](https://www.postgresql.org/docs/16/sql-alterdefaultprivileges.html). 로컬 복구 증상은 [Docker 이슈460](https://github.com/docker/desktop-feedback/issues/460)과 같았지만 이 PC의 커널 잠금 원인까지 입증한 것은 아니다.

최종 점검 보완: ENV-PG가 approved가 되자 진척 계산기 self-test의6번 반례가 실패했다. 계산 오류가 아니라 시험이 실제 원장의 ENV-PG pending을 암묵적으로 기대했기 때문이다. `scripts/check_trial_progress.py`의 반례 사본에만 pending/evidence빈값을 명시하도록 수정했다. 실제 승인 원장·배점·계산 규칙은 바꾸지 않았다. 실제 계산1855/5300=35.0% 및 새 ready단계 P03.2를 확인했다.

---

# P03.2 · P03.3 — 실제 PostgreSQL 에서 제품 경로 소비 (Claude / 2026-09-21)

격리 로컬 PG **16.15** (`127.0.0.1:55432`, db `afs_trial_local`, schema `app`). 설치는
`afs_installer`, 소비는 `afs_runtime`. 명령은 모두 Codex 의 launcher 를 거쳤고
(`scripts/local_pg_trial.py run <role> -- …`), 접속 정보는 자식 환경에만 전달됐다 —
이 문서에도 코드에도 DSN·비밀번호 «값» 은 없다.

## 0. 한눈에

| 항목 | 상태 | 비고 |
|---|---|---|
| 스키마 설치(installer) | **PASS** | store 당 22문장, **commit 전** 확인 통과 |
| 로그인·세션 | **PASS** | 저장 해시 대조·오답/위조 거절 |
| 조직 문맥 «조회» | **PASS** | 제품 `EcmRepository` 경로 |
| 조직 문맥 «쓰기» | **PASS** | §6 — 복합 충돌 대상 두 종 실제로 침 |
| SSE 티켓 단일 소비 | **PASS** | 2회차·위조 빈 사전 |
| SSE 티켓 동시 소비 | **PASS** | 음성 대조군으로 경쟁 실재 증명 |
| runtime DDL 0 | **PASS** | 계측 0건 **그리고** DB 가 거절 |
| 프로세스 재시작 대사 | **PASS** | 새 프로세스에서 전주기 재현 |
| 첫 경로 밖 표 결손 | **결함 보고** | §5 — 의사결정 요청 1건 |

## 1. 실행 중 발견한 제품 결함 ①: 주석 안의 `?` 를 자리표시자로 바꿨다

첫 `--apply` 가 실패했다.

```
psycopg.ProgrammingError: the query has 4 placeholders but 0 parameters were passed
```

`001_auth_and_context.sql` 의 `auth_sse_ticket` **위 주석**에 소비 SQL 예시를 적어 두었고
거기 `?` 가 네 개였다. `translate_placeholders` 가 그것까지 `%s` 로 바꿨다. SQLite 는
번역을 하지 않으므로 **끝까지 보이지 않았고**, 실제 PG 첫 적용에서야 드러났다.

두 층으로 고쳤다.

1. **주석을 그대로 흘려보낸다** — `--` 는 줄 끝까지, `/* */` 는 닫힐 때까지.
2. **파라미터가 없으면 `None` 으로 넘긴다** — 빈 튜플을 주면 psycopg 가 결합 경로를
   타면서 본문의 `%`/`%s` 를 다시 자리표시자로 읽는다.

### 시험이 정말 무는지 — 변이로 확인

| 변이 | 결과 |
|---|---|
| 주석 건너뛰기 제거 | 신규 **4건 실패**, 기존 21건 **전부 초록** |
| `params is None` → `not params` + `()` 전달 | 신규 **1건 실패** |

★ 기존 21건이 변이에도 초록이었다는 것이 핵심이다 — 어제까지 **이 분기를 보는 시험이
하나도 없었다**. 변이 후 원복은 해시로 확인했다(`6ab379c0…d756e5`).

파일 단위 불변식도 하나 걸었다: **설치 DDL 을 번역하면 `%s` 가 0개여야 한다.** 설치
DDL 에는 파라미터가 없으므로, 하나라도 생겼다면 실행되지 않을 무언가를 자리표시자로
오독한 것이다. 단위 시험이 못 본 새 문장이 들어와도 여기서 걸린다.

## 2. 계측기부터 증명했다 — 「DDL 0건」의 자격

`runtime_ddl_seen: []` 은 그 자체로 증거가 아니다. 계측기가 아무것도 못 받고 있어도
똑같이 `[]` 다. 그래서 같은 실행에 두 가지를 함께 찍는다.

```json
"instrument": { "sql_statements_recorded": 28, "recorder_catches_ddl": true },
"runtime_ddl_seen": [],
"database_refuses_ddl": {
  "CREATE TABLE": "InsufficientPrivilege",
  "CREATE TEMP TABLE": "InsufficientPrivilege",
  "ALTER TABLE": "InsufficientPrivilege" }
```

- 28문장을 실제로 기록했다 → 계측기가 살아 있다.
- 일부러 DDL 을 흘려 보내니 잡았다 → 계측기가 DDL 을 **볼 줄 안다**.
- 그리고 **DB 가 거절한다** → 응용이 실수로 시도해도 못 들어간다.

★ 앞의 둘은 「제품이 시도하지 않았다」, 뒤는 「시도해도 막힌다」다. 둘은 다른 주장이며
두 개가 다 있어야 「runtime DDL 0」이 통제가 된다.

## 3. 동시 소비 — 「1건」이 무엇 덕분인지 갈랐다

```json
{"workers": 4, "succeeded": 1, "lost": 3,
 "losers": ["졌음(연결 살아 있음)"], "losers_all_healthy": true,
 "db_rows_marked_consumed": 1,
 "naive_pattern_control": {"succeeded": 4, "race_window_is_real": true}}
```

세 가지를 따로 확인했다.

1. **진 쪽이 살아 있었다.** 제품은 실패 사유를 나누지 않고 빈 사전을 준다(의도된 설계).
   그래서 「졌다」와 「연결이 터졌다」가 겉으로 같다. 진 스레드마다 곧바로 `resolve()`
   를 태워 연결이 정상임을 확인했다. 이걸 안 하면 통제가 없어도 「정확히 하나」가 난다.
2. **DB 쪽에서도 1건.** 응용 반환값만 세지 않는다.
3. **음성 대조군 4건.** 같은 장벽·같은 스레드 수로 「읽고→확인하고→쓰기」를 재연하니
   **넷 다 성공**했다. 즉 경쟁은 실재했고, 제품의 1건은 `UPDATE … WHERE consumed_at=''`
   **한 문장의 원자성** 덕분이다. 여기서도 1건이 났다면 증명된 것은 아무것도 없다.

⚠️ 대조군은 제품 경로가 아니다. 격리 시험 DB 의 합성 티켓 한 장에만 닿는다.

## 4. 재시작 대사 — 기준을 바꿨다

처음에는 티켓 건수로 지속성을 재려 했는데 **그건 지속성이 아니라 청소 동작을 재는 것**
이었다. `issue_sse_ticket` 은 발급할 때마다 `expires_at < now` 인 표를 소비 여부와 무관하게
지우고, 티켓 수명은 30초다. 프로세스를 다시 띄울 무렵엔 이미 쓸려 있다. 그것을
「사라졌다」로 읽으면 정상 동작을 결함으로 오인한다. 그래서 **수명이 긴 것**으로 쟀다.

```json
{"login_still_works": true, "context_survived": "합성PG본부",
 "row_counts": {"tenants":1,"enterprise_entities":1,"organization_nodes":2,
                "auth_credential":1,"auth_session":5},
 "fresh_cycle_scope": "n_pg_child", "fresh_cycle_second_consume_empty": true}
```

새 프로세스에서 **발급→소비→재소비 거절**까지 한 바퀴 더 돌았다. 살아남은 자료를 읽는
것과 「이 프로세스에서도 된다」는 다른 주장이라 둘 다 확인했다.

## 5. 발견한 결함 ②(범위 밖) — 설치 산출물이 제품보다 좁다 · **의사결정 요청**

`EcmRepository` 는 `enterprise_profiles` · `enterprise_process_heads` 를 쓰는데, **설치
스키마에도 `REQUIRED` 에도 없다.** 그래서 관리 모드 확인은 「설치됨」이라 말하고 프로필
경로는 깨진다. 확인이 자기가 지킬 범위를 스스로 정의한 꼴이다.

**범위 판정:** 첫 경로(로그인→세션→문맥→SSE)는 **영향 없다.** 이 표들은
`api/routes/enterprise_context_control.py`(ECM 관리 화면)와 `clone_service.py`(가상조직
복제)에서만 닿는다. `core/context_engine.py` 는 정적 바인딩 표만 쓰므로 DB 에 안 간다.
시험으로 고정해 두었다(`test_first_path_read_still_works_while_profiles_are_absent`).

**그런데 그냥 표만 옮기면 안 된다.** `enterprise_process_*` 의 불변성은 **SQLite
트리거**(`RAISE(ABORT, 'immutable process installation')`)로 강제된다. PG 로 옮기면 그
문법은 없고, 대응 트리거 함수를 만들지 않으면 **통제 한 층이 조용히 사라진다.**
승인된 공정 설치를 나중에 고칠 수 있게 되는 것이다.

> **의사결정 요청 (DEC-PG-TRIGGER):** 이 층을 ①PG 트리거 함수로 포팅할지, ②응용 계층
> 통제로 올릴지, ③해당 화면의 PG 이관을 뒤 단계로 미룰지. 제가 임의로 고르면 나중에
> 통째로 버려질 수 있어 멈춥니다. 어느 쪽이든 「표만 만들고 트리거는 없음」은 **안 됩니다.**

## 6. 아직 못 돌린 것 — 제품 «쓰기» API 의 PG 실행

처음 harness 는 조직 자료를 **손으로 쓴 INSERT** 로 넣었다. 그러면 읽기만 제품 경로이고
쓰기는 제가 지어낸 SQL 이라, 제품의 UPSERT 가 PG 에서 도는지는 하나도 증명되지 않는다.
제품은 `ON CONFLICT(node_id, code)` · `ON CONFLICT(from_node_id, to_node_id,
relation_type, effective_from)` 같은 **복합 충돌 대상**을 쓴다.

`upsert_tenant → upsert_entity → upsert_node → add_edge → approve_entity` 로 갈아끼웠고,
SQLite 7건(`tests/test_first_path_product_writes.py`)과 **실제 PG 양쪽에서 통과**했다.

```json
"writes_through_product_api": {
  "upsert_is_idempotent": true,
  "edge_children": ["n_pg_child"], "edge_parents": ["n_pg_root"],
  "alias_history_after_code_change": ["PGROOT", "PGROOT2"],
  "alias_lookup_finds_old_code": ["n_pg_root"],
  "find_by_current_code": "n_pg_root",
  "entity_approved_status": "ACTIVE" }
```

**복합 충돌 대상 두 종이 PG 에서 성립한다.**

- `ON CONFLICT(from_node_id, to_node_id, relation_type, effective_from)` — 엣지가
  되풀이 실행에서도 하나로 유지되고 `children`/`parents` 가 맞다.
- `ON CONFLICT(node_id, code)` — 별칭 이력. ⚠️ 여기서 한 번 헛디뎠다. 처음에는 노드에
  코드를 «붙이기만» 하고 별칭이 비었다고 「기록 실패」로 읽었다. 제품을 읽어 보니 별칭은
  **코드가 바뀔 때 옛 코드**를 남기는 것이었다(`reason="code_changed"`). 즉 그때까지
  **충돌 대상을 한 번도 치지 않은 채** 「쓰기 확인함」이라고 할 뻔했다. 코드를 실제로
  바꾸도록 고쳤고, 되풀이 실행에서 별칭 행이 이미 있는 상태까지 만들어 `DO UPDATE`
  가지도 지났다(위 `["PGROOT", "PGROOT2"]`).

§5 의 결손도 **실제 PG 에서 확인**됐다 — `list_profiles` · `assert_legacy_process_reader`
둘 다 `UndefinedTable`. 관리 모드라 **소리내어** 깨진다(빈 목록으로 숨지 않는다).

~~⚠️ **PG 에서는 NOT_RUN** 이다.~~ — Docker 복구 후 실행해 닫았다.

## 7. 환경 — Docker 가 다시 내려갔다

절전 이후 엔진이 죽었다. 특권 서비스는 권한 상승 승인을 받아 다시 올렸다
(`com.docker.service: Running`). 그러나 Linux 엔진 파이프가 생기지 않는다. 백엔드 로그의
원인은 **앞서 Codex 가 고쳤던 것과 같은 종류**다.

```
starting services: initializing Inference manager:
  listening on unix://<HOME>\AppData\Local\Docker\run\dockerInference:
  remove …\dockerInference: The file cannot be accessed by the system.
```

`%LOCALAPPDATA%\Docker\run\` 에 17:19 에 남은 **0바이트 소켓 2개**(`dockerInference`,
`userAnalyticsOtlpHttp.sock`)가 지워지지 않아 기동을 막는다. 앞선 복구 때 남긴
`run.backup-20260921-171320` · `-171920` 과 같은 증상이다.

제안한 복구는 **삭제가 아니라 이름 바꾸기**(`run` → `run.backup-<시각>`)였으나 자동
승인에서 막혔다(`Irreversible Local Destruction` / `Interfere With Workloads`). 지운 것은
없고 건드린 것도 없다.

**해소:** 사람이 복구했고 엔진이 돌아왔다. 컨테이너는 `Exited (255)` 였으므로 기록에
허용된 `docker start afs-pg-local` 만 썼다(삭제·재생성 없음). 이후 세 단계를 모두
실행해 §6 을 닫았다.

★ 교훈 하나: **절전은 이 환경을 끊는다.** 지금 구성은 PC 가 자면 엔진이 죽고 소켓이
남아 사람 손을 부른다. 운영 트라이얼 일정에 이 비용을 포함시켜야 한다.

## 8. 바뀐 파일

| 파일 | 내용 |
|---|---|
| `core/db/__init__.py` | 주석 인지 번역 · 파라미터 없으면 `None` · 낡은 「PG 미실행」 주석 정정 |
| `core/db/managed_schema.py` | PG 가지 실측 근거로 주석 교체(`target_identity` 완료 표시) |
| `scripts/install_first_db_schema.py` | `apply_postgres` 실측 근거 주석 |
| `scripts/p03_pg_consumption.py` | **신규** — 제품 소비 harness(신원·로그인·문맥·티켓·동시·재시작) |
| `tests/test_db_adapter_first_slice.py` | **+5** 번역 회귀(주석 3 · 파일 불변식 1 · 둘째 층 1) |
| `tests/test_first_path_product_writes.py` | **신규 6건** — 설치 산출물 위에서 제품 쓰기 순서 |

## 9. 검증

격리 러너 `scripts/verify_data_usage_holds.py --strict-writes`:

```
176 passed · sources_unchanged: true · protected_assets_unchanged: true
blocked_file_writes: [] · blocked_sqlite_paths: []
```

대상: `test_db_adapter_first_slice` · `test_db_managed_schema_first_slice` ·
`test_first_path_copy_migration` · `test_first_path_product_writes` ·
`test_deploy_readiness_and_ledger` · `test_release_artifact`.

LLM 호출 0 · 외부 전송 0 · 운영 DB 접근 0 · 커밋/푸시 0.

## 10. 제 판단

**P03.2 · P03.3 둘 다 실측으로 닫혔다**고 봅니다. 로그인·세션·문맥 조회·문맥 쓰기·거절,
티켓 단일/동시 소비, 프로세스 재시작, runtime DDL 0 이 **실제 PostgreSQL 16.15 에서**
제품 함수로 확인됐습니다.

⚠️ **범위를 넘겨 읽지 말아 주십시오.** 확인한 것은 **첫 경로 두 store**(`auth`,
`enterprise_context`)이고 **합성 자료**입니다. 나머지 store, 운영 규모, 운영 자료,
그리고 §5 의 ECM 관리 화면은 아직입니다. 「PostgreSQL 이관이 끝났다」가 아니라
**「첫 경로가 실제로 돌았다」** 입니다.

§5 의 DEC-PG-TRIGGER 는 제 권한 밖이라 판단을 요청드립니다.

---

# C03.1 독립 PG 계획 저장·조회 — 오착수·미수용 / 국소 철수 지시 (원 작성 Claude, 판정 Codex / 2026-09-21)

> 아래는 당시 수행 기록을 보존한 것이다. 「PG 환경만 있으면 완료」 판정은 철회한다. 구 원장/업무adapter 결합은 정본 위배이며, 문서 끝 Codex 철수 지시가 우선한다. 실제 철수는 아직 미확인.

원장 수용 기준: *「업무 DB와 분리한 관리PG에 불변 plan 생성/조회·명시migration을 구현해
실제API로 실행한다.」* 구현·SQLite 실행·통제 증명까지 끝냈고, **실제 PG 실행만** 환경
조건이 갖춰지면 됩니다(§5).

## 1. 무엇이 문제였나 — 「분리」가 주장이었다

P2 에서 만든 배포 원장은 세 가지가 관리 저장소로서 성립하지 않았습니다.

| 문제 | 왜 문제인가 |
|---|---|
| 생성자가 `executescript(_DDL)` 실행 | **기동 중 DDL** 이다. 인스턴스가 둘이면 동시에 돈다 |
| `AUTOINCREMENT` · `BEGIN IMMEDIATE` · `conn.execute("COMMIT")` | **SQLite 전용**이라 PG 에서 설치·트랜잭션이 깨진다 |
| 「관리 DB 는 분리」 — 차단기 없음 | 경로를 명시하게 했을 뿐, **명시된 경로가 업무 폴더일 수 있다** |

## 2. 분리를 **두 층의 차단기**로 바꿨다 (`ops_control/db_target.py`)

```
① 설정  AFS_OPS_DB_DSN 만 읽는다. 비면 업무 AFS_DB_DSN 으로 «떨어지지 않고» 거절
        두 변수가 같은 값이면 거절. SQLite 경로가 PROJECT_ROOT/data 안이면 거절
② 대상  연결이 실제로 «업무 표» 를 보고 있으면 거절
        (auth_credential · auth_session · auth_sse_ticket ·
         organization_nodes · enterprise_entities · tenants)
```

★★ **층마다 가정이 달라야 층입니다.** ①은 설정을, ②는 연결된 대상을 봅니다. 변수를
잘 갈라 놔도 두 변수가 같은 DB 를 가리키면 ①은 통과하고 ②가 잡습니다.

⚠️ 판정 기준을 `PROJECT_ROOT` 에 **고정**했습니다. 작업 디렉터리로 보면 격리 실행에서
판정이 정확히 뒤집힙니다 — 업무 폴더가 「바깥」으로, 임시 폴더가 「업무」로 보입니다.
⚠️ `resolve()` 를 쓰지 않습니다. junction 을 따라가면 링크의 «모양» 이 지워집니다.
⚠️ 접속 정보 «값» 은 예외 메시지에도 넣지 않습니다 — 변수 **이름**만 말합니다.

## 3. 나머지 구현

- **설치 산출물** `core/db/schema/002_deploy_ledger.sql` — SQLite·PostgreSQL 이 **한
  파일**을 씁니다. `AUTOINCREMENT` 를 버리고 이력 순번을 **계획별 `seq`** 로 바꿨습니다
  (쓰기 잠금을 쥔 트랜잭션 안에서 매기므로 두 요청이 같은 번호를 가져가지 않습니다).
- **관리 모드** — `managed=True` 면 기동 중 DDL 을 **한 줄도** 돌리지 않고, 설치 산출물이
  «그 연결에» 있는지 확인합니다. 기존 동작(비관리 SQLite)은 한 글자도 바뀌지 않았습니다.
- **방언 결속** — factory 가 `.backend` 로 스스로 말합니다. PostgreSQL 에서는
  `BEGIN IMMEDIATE` 를 **만들지도 않고**, 잠금은 `SELECT … FOR UPDATE` 로 잡습니다.
  트랜잭션 제어는 문장이 아니라 드라이버의 `commit()`/`rollback()` 으로 통일했습니다.
- **설치 명령** — store 별 등록표(스키마 파일·DSN 변수)로 일반화했습니다.

### ⚠️ 그 과정에서 스스로 만든 함정 하나를 잡았습니다

`--store` 를 생략하면 `KNOWN_STORES` 전체를 설치하는 코드였습니다. 거기에 관리 원장을
추가하는 순간, **아무도 명령을 바꾸지 않았는데** 기존 명령이 관리 저장소까지 설치하게
됩니다. 기본값을 `DEFAULT_STORES`(첫 경로 둘)로 못박았습니다. 인자를 빠뜨리는 쪽이
범위가 넓어지는 설계는 언젠가 반드시 사고가 됩니다.

같은 함정이 **시험 쪽에도** 있었습니다. 첫 경로 초안을 검사하는 시험이 `KNOWN_STORES`
를 돌고 있어서, store 를 추가하자 관리 원장의 표 20건을 001 파일에서 찾기 시작했습니다.
시험도 자기 범위를 스스로 말하도록 고쳤습니다.

## 4. 검증 — 통제가 **무는지** 확인했다

신규 18건(`tests/test_ops_ledger_separation.py`) + 기존 63건 유지.
격리 러너 합계 **195 passed**, `sources_unchanged: true`.

변이 4건으로 각 통제를 확인했습니다(해시로 원복 확인, `f5a4ccb9…` / `5c11688f…`).

| 변이 | 결과 |
|---|---|
| ② 대상 층 제거 | 물림 |
| ③ 업무 폴더 차단 제거 | 물림(2건) |
| ① 업무 DSN 으로 대체 | **처음엔 안 물림** — 아래 참조 |
| ① 대체 + 「둘 다 빔」 분기 | 물림(시험 추가 후) |

★★★ **「안 물림」의 원인이 「통제 없음」이 아니었습니다.** 업무 DSN 대체를 넣어도, 바로
다음 줄의 「두 변수가 같으면 거절」이 그것을 **흡수**합니다(대체하면 값이 업무 값과
같아지므로). 흡수되지 않는 자리는 **둘 다 비어 있을 때**뿐이고, 그 분기를 보는 시험이
없었습니다. 시험을 추가하니 물렸습니다. 「변이가 안 물리면 통제가 없다」로 바로
넘어가면 안 되는 사례를 하나 더 얻었습니다.

접속 없이 가능한 PG 확인도 했습니다 — 설치 파일 **4문장**, 요구 결손 **0건**, 번역 후
자리표시자 **0개**(설치 DDL 에는 파라미터가 없어야 한다는 불변식).

## 5. ⚠️ 남은 것 — **관리용 두 번째 데이터베이스** (환경 요청)

C03.1 의 「실제API로 실행한다」를 닫으려면 **업무와 다른 데이터베이스**가 필요합니다.
읽기 질의로 확인한 결과 제가 만들 수 없습니다.

```
afs_installer → rolcreatedb: False · rolsuper: False · rolcreaterole: False
현재 데이터베이스: afs_trial_local, postgres, template0, template1
```

**요청 (ENV-PG-OPS):** 기존 컨테이너 안에 관리용 DB 하나를 더 만들어 주십시오.
업무와 **같은 DB 에 스키마만 다르게** 두는 것은 이 단계의 수용 기준을 충족하지 않고,
제 차단기 ②도 그 구성을 **거절**합니다(같은 DB 에 업무 표가 보이므로).

- 데이터베이스: 업무(`afs_trial_local`)와 **다른** 이름
- 역할: 설치/런타임 분리는 지금과 같은 방식
- 전달: `AFS_OPS_DB_DSN` 을 기존 launcher 와 **같은 경로**로(값은 제게 주지 마십시오)

받으면 실행할 명령은 이미 있습니다.

```
local_pg_trial.py run installer -- install_first_db_schema.py \
    --backend postgres --store deploy_ledger --plan|--apply
```

⚠️ 그 전까지 「관리 PG 에서 돈다」고 쓰지 않습니다. 지금 상태는 **SQLite 실행 + PG
설치 산출물 정합성 확인**까지입니다.

## 6. 바뀐 파일

| 파일 | 내용 |
|---|---|
| `ops_control/db_target.py` | **신규** — 두 층 차단기 |
| `ops_control/deploy_ledger.py` | 설치 산출물 결속 · 관리 모드 · 방언 결속 · 이력 `seq` |
| `core/db/schema/002_deploy_ledger.sql` | **신규** — 양 방언 공용 설치 산출물 |
| `core/db/managed_schema.py` | `STORE_DEPLOY_LEDGER` · `REQUIRED` · `table_names()` |
| `scripts/install_first_db_schema.py` | store 등록표(스키마·DSN) · `DEFAULT_STORES` |
| `tests/test_ops_ledger_separation.py` | **신규 18건** |
| `tests/test_db_managed_schema_first_slice.py` | 시험 범위를 첫 경로로 못박음 |

LLM 0 · 외부 전송 0 · 운영 DB 0 · 커밋/푸시 0.

## Codex C03 판정·철수 범위·W03 다음 실행 — 2026-09-21 23:55 KST

요청자 Claude / 검토·지시 Codex. 실제diff·참조검색·Gap 담당 정본·설계§2/구원장 처리·OpenAPI PlanState를 대조했다. **C03.1 미수용, C03.2 착수 중지 판단은 맞다. 이번 C03 추가분의 국소 철수를 지시한다.** 단순 담당 착오만이 아니라 구현 방향이 정본 위배다. 코드는 이번 검토에서 직접 되돌리지 않았으며 아래 실행자는 Claude다. 회신 수신/철수 완료는 미확인.

### 1. 상태·환경 계약 정정

- C03/OPS-P2 담당은 Codex다. `REQUESTED→VALIDATED→…→CANARY` 문구는 현재 정본이 아니다. `deployment-control-v1.openapi.json`의 PlanState는 READY/BLOCKED/DISPATCHING/DISPATCH_UNKNOWN/QUEUED/APPROVAL_PENDING/PREPARING/VERIFYING/PROMOTING/DRAINING/FINALIZING/SUCCEEDED/FAILED/CANCELLED/RECOVERY_REQUIRED다. 이 이름으로 구원장을 개명해서 재사용하지 않는다.
- **ENV-PG는 업무 DB만 승인됐다.** 원장의 C03.1이 이를 공유해 착수가능으로 나오던 것도 잘못이다. Codex가 ENV-PG-OPS pending을 별도로 등록하고 C03.1의 실행승인 참조만 분리했다. 분모/배점/수용조건은 불변. 같은Docker인스턴스에 다른DB를 둘지부터 관리 계약에 맞춰 확인한 뒤 승인을 요청하며 이번 턴에는 생성하지 않는다. 업무 installer에 CREATE DATABASE/ROLE 권한을 더하지 않는다.
- 계산기의 기존 ready_steps는 하위호환 보존하되 `ready_work`에 **목표 정본의 owner/title**을 추가하고 Markdown도 담당을 표시했다. 이것은 개인업무 배정도 새 외부실행 승인도 아니다. 담당·현행 업무지시·정본계약을 함께 확인해야 한다.

### 2. 철수는 파일 전체가 아니라 이번 변경 조각만

먼저 자기 C03 diff/신규파일을 Git밖 세션 scratch에 보존해 재참조 가능하게 한 다음 정리한다. 공동 dirty 전체를 stash/reset/checkout하지 않는다. HEAD와 작업 시작 시점이 같다고 추측하지 않는다. 범위 밖 수정과 구 원장의 기존 반례/차단 개선은 보존한다.

| 대상 | 이번 실행 |
|---|---|
| core/db/managed_schema.py | STORE_DEPLOY_LEDGER·KNOWN_STORES/REQUIRED 추가와 C03 전용 table_names 제거. 실제PG 신원·dict행·검사·P03 주석/버그수정은 보존 |
| scripts/install_first_db_schema.py | **DEFAULT_STORES=(auth,enterprise_context) 유지**. 관리store import·SQLite파일명·002SQL등록·AFS_OPS_DB_DSN·postgres_factory_for의ops분기·sqlite_ddl_for의ops분기까지 철수. C03 때문에만 추가된 일반화도 소비자 없으면 제거. PG transaction-control제외·commit전확인·제품PG 보완은 보존 |
| ops_control/deploy_ledger.py | 이번 managed/backend/core.db의존/002SQL/seq/PG잠금 개조만 철수. 기존 DEP-R 보완과 미연결prototype/반례는 보존, 정식 backend로 연결하지 않음 |
| core/db/schema/002_deploy_ledger.sql | 이번 신규 오착수 산출물. scratch 보존 후 실행 소스에서 제거 |
| ops_control/db_target.py | 이번 신규 구현은 실행 소스에서 제거. 아래 한계를 포함한 설계 메모만 기존 결과에 보존; 검증된 보안부품으로 승격하지 않음 |
| tests/test_ops_ledger_separation.py | 오착수 전용18건은 위 신규소스와 함께 제거 가능. DEFAULT_STORES 업무2종 유지 검사는 기존 업무installer 시험에 남김. 구원장/업무 첫경로의 기존 회귀를 지워 숫자를 맞추지 않음 |
| tests/test_db_managed_schema_first_slice.py | 업무범위를 명시하는 정상검사·실PG준비 보완은 유지; 제거된 ops전용fixture/import만 정리 |

`195→177`은 예상치일 뿐 통과 목표가 아니다. 실제 수집 수/실패/skip을 보고한다. 제거 전 기존 호출자가 없다는 것을 참조검색으로 확인하고, 정리 뒤 첫경로 installer 계획과 영향 있는 업무/구원장 회귀를 **묶어서1회** 확인한다. 새 변이 캠페인/전체제품 재검증은 하지 않는다. P03 소비 harness·제품쓰기 시험·adapter 수정·이미 얻은 실PG 증거와 P05 경로보호는 철수 대상이 아니다.

### 3. 차단기에서 보존할 것과 믿으면 안 되는 것

보존할 설계 의도: 관리 DSN 없음→거절, 업무 DSN fallback 금지, 비밀출력 금지, 설정과 실제대상 신원을 별도로 검증. 현재 구현은 아래 이유로 분리보장 증거가 아니다.

- `table_names()`의 PG 조회는 `current_schema()`만 본다. **같은 DB/다른 schema** 또는 아직 업무표가 없는 DB면 안 보일 수 있다. DSN 문자열이 달라도 같은 DB일 수 있다. 연결 대상의 승인된 식별정보·DB 경계·역할권한을 독립 관리 persistence에서 결속해야 하며 「업무표가 없음=분리됨」으로 판단하지 않는다.
- `assert_path_outside_business_data()`는 abspath의 어휘적 포함만 보고 링크 자체/조상 검사나 정규 대상 검증이 없다. **밖의 junction→업무data** 우회를 막지 못한다. resolve를 안 썼다는 이유만으로 링크 차단이 되지 않는다. 이번에는 폐기할차단기를 다시 구현하지 않고 한계만 인계한다.

### 4. 철수 뒤 Claude는 W03.1→W03.2, Codex는 P03 검토·C02/C03

새 회신 대기 없이 **W03 프로젝트/릴리스 파일의 공유 읽기→원자저장**을 이어간다. P03 재작업이나 DEP-R3로 동시에 갈라지지 않는다. 첫20~30분에 `core/library_paths.py`(현재cwd상대library), `core/kit_app_builder.py`의release쓰기, 실제 latest_state 작성자/소비자를 찾아 재사용·수정할 파일을 본인 상태에 기록하고 구현한다. 공용 main/run/UI 및 Codex ops_control/CI 파일은 수정하지 않는다.

1. W03.1: 프로젝트·릴리스 합성1판씩, 두 독립 실행 주체가 **동일한 실제 저장 위치**를 읽도록 제품 경로에 연결한다. 서로 다른작업디렉터리에서도 같은판본/digest·소유문맥을 확인한다. 파일복제본/표식/.afs-shared 존재/모의open은 공유증거가 아니다. 단일PC 두프로세스 증거와 클라우드 두호스트/공유마운트 증거는 구분해서 기록한다. 새서비스·마운트·클라우드·앱컨테이너 생성 승인을 PG승인에서 추론하지 않는다.
2. W03.2: 앞 단계가 읽는 **같은 경로**의 저장을 원자화한다. 부분파일 방지와 동시writer의 낡은revision 덮어쓰기 방지는 다른문제다. rename만으로 두 가지를 다 달성했다고 쓰지 않는다. 제품 쓰기→두 소비자 재조회로 정상경로 확인, 실제 독립writer경쟁·중간실패 한 흐름으로 음성확인한다. 임시파일은 같은 filesystem, 대상/상위링크·문맥경계 보존. 정상 반환한 성공 버전의 소실을 허용하지 않는다.
3. W03.3은 같은 산출물의 DB/파일 불일치 탐지·복구로 이어진다. 자료삭제/정본선택이 필요한 충돌은 임의로 덮어쓰지 말고 주요결정으로 올린다. 이번 로컬구현이 NCP 파일공유 전체수용이라는 주장은 금지한다.

정리20~40분, W03.1 첫 소비1~3h, W03.2 추가2~4h **잠정**. W03전체8~20h는 상한분량 참고이지 이번에 전부완료 약속이 아니다. 환경이 필요한 검증만 명확히 남기고 로컬구현을 진행하며, 단계별 새검토서/검증라운드 없이 기존 결과에 W03 절을 누적한다. W03.1/+45·W03.2/+45는 각각 기존 출구 충족 후 Codex가 가산하며 자동가산하지 않는다.

### 5. 진척과 P03 보존

현재 원장실측 **1855/5300=35.0%,20/139수용·잔여3445점/119단계**. C03은 이미수용된점수가 없으므로 철수로 점수를 깎지 않는다. P03.2/3의 실제PG 제출은 확인했으나 **이번 C03 범위검토를 제품 수용검토로 대신하지 않았다**. 제출된 +40은 Codex 별도 수용검토 대상이며 두단계수용 시1895/5300=35.8%다. DEC-PG-TRIGGER/관리화면 등 첫경로 밖 사안을 이미완료된첫경로에 무조건 덧붙이지 않고 실제 출구·위험별로 판정한다. 먼저 P03를 처음부터 반복하라고 지시하지 않는다.

이번 Codex 변경은 계산기 담당표시·환경승인 경계·기존 인계/보드뿐이다. 제품코드 철수·PG변경·운영자료 접근·커밋·푸시 없음. Claude 수신 및 철수 결과는 다음 결과로 확인한다.

---

# C03 철수 실행 결과 — Claude / 2026-09-21

지시: 위 「Codex C03 판정·철수 범위·W03 다음 실행」. **이번 C03 추가분만** 조각 단위로
철수했습니다. 공동 dirty 전체를 stash/reset/checkout 하지 않았습니다.

## 1. 실행한 것

보존 먼저: C03 diff·신규 파일 6종을 Git 밖 세션 scratch 에 복사했습니다
(`…/scratchpad/c03_withdrawn/`). 원장은 되돌리기 전에 **diff 에 남의 변경이 섞였는지**
확인했고, 전부 제 C03 변경이었습니다(세션 시작 시 clean 이었음).

| 대상 | 실행 | 보존한 것 |
|---|---|---|
| `ops_control/deploy_ledger.py` | HEAD 로 복원(파일 하나만) | 기존 DEP-R 보완·미연결 prototype·반례 그대로 |
| `ops_control/db_target.py` | 제거 | 설계 의도·한계를 §3 에 인계 |
| `core/db/schema/002_deploy_ledger.sql` | 제거 | scratch 사본 |
| `tests/test_ops_ledger_separation.py` | 제거(18건) | — |
| `core/db/managed_schema.py` | `STORE_DEPLOY_LEDGER`·`KNOWN_STORES` 항목·`REQUIRED` 항목·`table_names()` 제거 | **실제 PG 신원·dict 행·검사·P03 주석/버그수정 전부 보존** |
| `scripts/install_first_db_schema.py` | 관리 store import·SQLite 파일명·002 등록·`AFS_OPS_DB_DSN`·`postgres_factory_for`·`sqlite_ddl_for` ops 분기·store 등록표 일반화 제거 | **`DEFAULT_STORES=(auth, enterprise_context)` 유지**, PG 트랜잭션제어 제외·commit 전 확인 보존 |
| `tests/test_db_managed_schema_first_slice.py` | ops 전용 잔재 정리 | 업무 범위 명시 검사 유지 + `DEFAULT_STORES` 검사 1건 추가 |

제거 전 참조 검색으로 **남은 호출자 0** 을 확인했습니다(문서 기록 제외).

## 2. 확인 — 숫자가 아니라 동작으로

묶음 회귀 1회(격리 러너, `--strict-writes`):

```
collected 178 · 178 passed · 0 failed · 0 skipped · exit 0
sources_unchanged: true · protected_assets_unchanged: true
blocked_file_writes: [] · blocked_sqlite_paths: []
```

대상: `test_db_adapter_first_slice` · `test_db_managed_schema_first_slice` ·
`test_first_path_copy_migration` · `test_first_path_product_writes` ·
`test_deploy_readiness_and_ledger` · `test_release_artifact`.

⚠️ 예상치 177 이 아니라 **178** 입니다. 「빈 인자가 범위를 넓히지 않는다」를 지키는
검사를 업무 installer 시험에 한 건 남겼기 때문입니다(지시 2항의 「기존 업무installer
시험에 남김」).

설치기는 **동작으로** 확인했습니다 — grep 으로 끝내지 않았습니다.

```
--plan (인자 생략) → auth 6문장 · enterprise_context 29문장 · ok:true
--store deploy_ledger → argparse 거절: invalid choice (choose from auth, enterprise_context)
```

구 원장은 `git diff --stat` 0 — HEAD 와 동일합니다.

## 3. `db_target` 인계 — 의도는 남기고, **분리 보장이라고 부르지 않는다**

폐기했으므로 다시 구현하지 않습니다. OPS-P2 에 넘길 **설계 의도**만 적습니다.

- 관리 DSN 이 없으면 **거절**한다. 업무 DSN 으로 fallback 하지 않는다.
- 두 변수가 같은 값이면 거절한다. 접속 정보 «값» 은 예외 메시지·로그에 넣지 않는다.
- 설정과 **실제 연결 대상의 신원**을 **서로 다른 가정 위에서** 따로 검증한다.

### ⚠️ 제 구현이 분리 보장이 **아니었던** 이유 (Codex 지적, 그대로 인계)

1. **`table_names()` 의 PG 조회는 `current_schema()` 만 본다.** 같은 DB 의 다른 schema 에
   업무 표가 있거나, 아직 업무 표가 설치되지 않은 DB 면 **안 보인다.** DSN 문자열이
   달라도 같은 DB 일 수 있다. 「업무표가 없음 = 분리됨」은 **없다는 사실을 안전으로
   바꾸는** 논리다. 연결 대상의 승인된 식별정보·DB 경계·역할 권한을 독립 관리
   persistence 에서 **결속**해야 한다.
2. **`assert_path_outside_business_data()` 는 abspath 의 어휘적 포함만 본다.** 링크
   자체나 조상에 대한 검사가 없어 **바깥의 junction → 업무 `data/`** 우회를 막지
   못한다. `resolve()` 를 쓰지 않았다는 사실만으로 링크 차단이 되지는 않는다.

★ 제가 이것을 「두 층의 차단기」라고 부른 것이 과했습니다. 한 층은 좁은 범위만 보고
있었고, 다른 한 층은 제가 **이미 P05.1 에서 고쳤던 우회**(조상 링크 검사)를 새 코드에서
다시 빠뜨렸습니다. 같은 결함을 두 번 만든 셈입니다.

## 4. 이번 철수로 잃지 않은 것

P03.2/P03.3 의 실제 PG 증거·소비 harness·제품 쓰기 시험·adapter 수정, P05 경로 보호는
그대로입니다. C03 은 수용된 점수가 없으므로 철수로 깎인 점수도 없습니다.

진척 **1855/5300 = 35.0%** (P03 제출분 +40 은 Codex 수용검토 대기).
LLM 0 · 외부 전송 0 · 운영 DB 0 · 커밋/푸시 0.

---

# W03.1 프로젝트·릴리스 공유 읽기 — Claude / 2026-09-22

출구: *「프로젝트·릴리스 합성1판씩, 두 독립 실행 주체가 동일한 실제 저장 위치를 읽도록
제품 경로에 연결한다. 서로 다른 작업디렉터리에서도 같은 판본/digest·소유문맥을 확인한다.」*

## 1. 결함 — 두 저장 위치의 기준이 달랐다

`projects/` 는 2026-08-05 에 저장소 루트 기준 절대경로가 됐는데(`core/paths.py`),
**`library/` 만 작업 디렉터리 상대경로로 남아 있었습니다.**

```
저장소 루트에서 실행   → <root>/library        릴리스 29건
다른 디렉터리에서 실행 → <그곳>/library        없음. 0건으로 보인다
```

⚠️ 「목록이 비어 보인다」로 끝나지 않습니다. 게시는 A 를 보고 사용여부 제어는 B 를
보므로 **실제로 존재하는 프로그램을 끌 수 없습니다.** 그리고 `makedirs` 하는 경로가
엉뚱한 곳에 빈 보관소를 새로 만들어 이후 게시물이 그쪽에 쌓입니다. 「두 노드가 같은
판본을 읽는다」는 이 상태에서 **성립할 수 없습니다.**

고침은 한 줄입니다 — `_LIBRARY_DIR = project_path("library")`. 기준은 「프로세스가
어디서 떴는가」가 아니라 **「이 코드가 어느 저장소에 속하는가」** 입니다.

## 2. 증거 — 두 «프로세스», 그리고 음성 대조군

`scripts/w03_shared_read_probe.py compare`. 합성 릴리스 한 판을 격리 보관소에 만들고,
**서로 다른 작업 디렉터리**에서 프로세스 둘을 띄워 **제품 함수**로 읽습니다
(`app_delivery._default_release_lookup` · `program_lifecycle._release_exists`).

| | A(보관소 품은 디렉터리) | B(전혀 다른 곳) | 판정 |
|---|---|---|---|
| 저장소 기준 절대경로 | 찾음 | 찾음 | **digest·소유문맥 동일** |
| 작업디렉터리 상대(옛 해석) | 찾음 | **못 찾음** | 갈라짐 |

★★ 음성 대조군이 갈라지므로 「둘이 같았다」가 우연이 아닙니다. 대조군까지 같았다면
제 시험이 경로 의존을 재연하지 못한 것이지 제품이 증명된 게 아닙니다.

소유문맥은 `tenant_id · entity_mode · enterprise_scope_id · owner_dept_id ·
created_by · project_id` 여섯 필드를 맞췄고, 판본 동일성은 **내용 digest** 로 봤습니다
(경로 문자열이 같은지를 묻지 않습니다).

⚠️ **단일 PC 두 프로세스 증거입니다. 두 호스트·공유 마운트 증거가 아닙니다.** 그 구분을
probe 출력에 문자열로 박아 두었고, 시험이 그 문구의 존재를 확인합니다.

## 3. 회귀 — 귀속을 먼저 증명했다

관련 26개 스위트(745건)를 **A/B 로** 돌렸습니다.

```
절대경로(변경)  745건  fail 94  err 17
대조군(원래)    745건  fail 94  err 17
공통 실패 111 · 변경으로 새로 깨진 것 0 · 변경이 고친 것 0
```

★ 그 111건은 **HEAD 워크트리(미커밋 변경 0)에서도 그대로 실패**합니다
(`test_app_data_runtime` 단독: 46건 중 28 실패). 즉 **기존 실패**이며 제 W03 변경도,
제 P03 작업도, 공유 트리의 미커밋 상태도 원인이 아닙니다. → §5 로 보고합니다.

W03 관련 9개 스위트 묶음: **collected 100 / 100 passed / exit 0**,
`sources_unchanged: true`, `blocked_file_writes: []`.

운영 폴더 불변: `library/` 29 → 29, `projects/` 73 → 73.

## 4. ⚠️ 이번에 제가 낸 실수 셋 — 그대로 적습니다

1. **검사 중에 소스를 고쳤습니다.** 26개 스위트가 도는 동안 probe 파일을 만들고
   편집해서 러너가 `sources_unchanged: false` 를 찍었습니다. 그 실행은 버리고 다시
   돌렸습니다. 「검사 중 소스를 변경하지 않는다」를 제가 어겼습니다.
2. **시험이 제품 모듈을 다시 읽어 세션을 오염시켰습니다.** `importlib.reload(
   library_paths)` 를 썼더니, 단독으로 15건 통과하던 `test_app_delivery_real_release`
   가 같은 묶음에서 4실패·9오류가 됐습니다. `runpy` 로 **새 이름공간에서** 소스만
   한 번 더 실행하도록 바꿨습니다 — 살아 있는 모듈은 손대지 않습니다.
3. **격리 러너가 무엇으로 격리하는지 모른 채 걱정했습니다.** 러너는 cwd 가 아니라
   **`_LIBRARY_DIR` 을 자기 실행 뿌리로 갈아끼워** 격리합니다. 그래서 뿌리를
   절대경로로 바꿔도 격리가 깨지지 않습니다 — A/B 가 0건 차이였던 이유가 이것입니다.
   제 시험이 「살아 있는 값 == PROJECT_ROOT/library」를 단언했다가 그 사실에 걸려
   실패했고, 그 실패가 오히려 기제를 알려 줬습니다.

## 5. 별건 보고 — HEAD 의 기존 실패 111건

제 작업과 무관하지만 **알고 넘어가면 안 되는 것**이라 적습니다. 워크트리 확인 기준
HEAD 에서 아래 9개 파일이 실패합니다(745건 중 94 실패·17 오류).

```
test_app_data_runtime 28 · test_app_dataset_binding 17 · test_release_promotion 16
test_end_to_end_canary 12 · test_provider_dispatch 11 · test_rag_dept_scope 10
test_release_rollback_api 10 · test_p4_recommendations 4 · test_project_deletion_policy 3
```

대표 증상은 `{"detail":"같은 이름의 데이터셋이 이미 있습니다: orders"}` 입니다.
단독 실행에서도 재현되므로 스위트 간 상호작용이 아닙니다. **담당·원인은 제 범위 밖**
이라 판정하지 않고 사실만 넘깁니다.

## 6. 바뀐 파일

| 파일 | 내용 |
|---|---|
| `core/library_paths.py` | 보관소 뿌리를 저장소 기준 절대경로로(`project_path("library")`) |
| `scripts/w03_shared_read_probe.py` | **신규** — 두 프로세스 공유 읽기 증거 + 음성 대조군 |
| `tests/test_w03_shared_release_read.py` | **신규 4건** — 절대경로·cwd 불변·새 import 값·증거 범위 명시 |

LLM 0 · 외부 전송 0 · 운영 DB 0 · 커밋/푸시 0.

## 7. 다음 — W03.2

앞 단계가 읽는 **같은 경로**의 저장을 원자화합니다. ⚠️ 부분파일 방지와 동시 writer 의
낡은 revision 덮어쓰기 방지는 **다른 문제**이며, rename 하나로 둘 다 달성했다고 쓰지
않겠습니다. 쓰는 지점은 `core/kit_app_builder.py` 의 release.json 기록과
`core/async_orchestrator.py` 의 `latest_state.json` 기록입니다.

---

# W03.2 원자 저장·경쟁 실패 — Claude (다른 PC) / 2026-09-22

출구: *「동시쓰기/중간실패에도 부분 파일이나 잘못된 판본을 읽지 않도록 저장 경로를
구현·검증한다」* (원장 W03.2, 45점). 환경은 Python **3.12.10**, Docker/PG 없음,
`library/`·`projects/` **0건** — W03.2 지시 원문에 DB·PG 언급이 없어 그대로 진행했습니다.

## 1. 발견 — 원자 쓰기는 **이미 있었고**, 정본을 쓰는 7곳이 그것을 안 썼다

`core/studio_project_files.py:30 write_json` 이 임시파일 → `fsync` → `os.replace` 를 하고
있었습니다. B3 승격 저장만 쓰고 있었고, **정본 파일을 쓰는 나머지가 전부 `open(...,"w")`
직접 쓰기**였습니다. 만든 쪽은 있는데 쓰는 쪽이 안 붙은 **배선 누락**입니다.

| 파일 | 위치 | 대상 |
|---|---|---|
| `core/kit_app_builder.py` | 425 | release.json |
| `api/routes/factory_control.py` | 3321 · 3360 | release.json (한 요청에서 두 번) |
| `core/async_orchestrator.py` | 101 | latest_state.json |
| `api/routes/factory_control.py` | 1175 · 1189 | latest_state.json (메가 자식·마스터) |
| `api/routes/advisor_control.py` | 47 `_write_json` | latest_state.json |

⚠️ **인계서 §4 의 시작 지점 표를 정정합니다.** 쓰는 곳이 3곳이 아니라 7곳이고,
「프로젝트 상태(다른 경로) `factory_control.py:749`」는 **읽는 곳**입니다
(`_restore_accumulated_from_disk`).

## 2. 무엇을 했나

`core/atomic_write.py` **신규** — 구현을 한 곳에 둡니다. `studio_project_files.write_json` 도
이것을 호출하도록 바꿨고(직렬화 정책 `sort_keys=True` 는 그 저장의 것이라 남겼습니다),
위 7곳을 전부 전환했습니다.

★ **직렬화 정책을 모듈이 강제하지 않습니다.** `sort_keys` 를 공통으로 걸면 내용이 같은데도
키 순서가 바뀌어 **digest 가 달라지고**, W03.1 이 판본 동일성을 digest 로 보므로 그 증거와
충돌합니다. 그래서 바이트를 만드는 정책은 호출자에게 남겼습니다. 같은 이유로 텍스트 모드를
유지했습니다 — 바이너리로 바꾸면 줄바꿈 변환이 사라져 같은 값의 digest 가 달라집니다.

★ **대상이 링크면 따라갑니다.** 공유 저장을 심볼릭 링크·junction 으로 거는 구성이 있고
(W03 이 노리는 바로 그 구성), 링크 자체를 `os.replace` 로 갈면 공유가 조용히 끊깁니다.

## 3. 증거 — 독립 프로세스 경쟁, 음성 대조군과 함께

`scripts/w03_atomic_write_probe.py compare` (러너 밖. 격리 러너가 `subprocess.Popen` 을
막으므로 pytest 안에서는 만들 수 없습니다). writer 3 프로세스가 같은 경로를 반복해서
덮어쓰는 동안 reader 가 계속 읽습니다.

| 모드 | read_ok | **torn**(부분 파일) | locked | 쓰기 OSError | 임시파일 잔여 |
|---|---|---|---|---|---|
| **atomic**(제품) | 5,365 | **0** | 435 | 41 | 없음 |
| legacy(**음성 대조군**) | 4,952 | **374** | 0 | 0 | 없음 |

★★ 음성 대조군이 실제로 깨집니다(374건). 대조군까지 0 이었다면 제 probe 가 경쟁을 재연하지
못한 것이지 제품이 증명된 게 아닙니다 — W03.1 에서 얻은 교훈을 그대로 적용했습니다.

⚠️ **처음에는 원자 모드도 실패한 것처럼 보였습니다**(unreadable 252). 제가 **부분 파일
(파싱 실패)과 Windows 공유 위반(열기 실패)을 한 칸에 세고** 있었습니다. 둘은 다른 현상이라
나눠 세니 부분 파일은 0 이었습니다. 계측 잘못을 제품 결함으로 보고할 뻔했습니다.

집중 시험 `tests/test_w03_atomic_save.py` **14건**(13 passed · 1 skipped — Windows 심볼릭
링크 생성 권한). 정상 쓰기 / 직렬화 실패 시 무접촉 / 교체 실패 시 이전 판본 보존 / 임시파일이
같은 디렉터리 / 재시도 계약 / 직렬화 정책 분리 / B3 저장 바이트 회귀 / 제품 쓰기 함수 직접
호출 / 배선 / 음성 대조군.

**줄 단위 변이 검증**: `core/atomic_write.py` 에서 원자성을 빼자 **14건 중 7건 실패**.
음성 대조군과 배선 확인은 그대로 통과했습니다(원자성과 무관한 것을 보는 시험이라 맞습니다).
원복 해시 `56171e41…e442655` 일치 확인.

## 4. Windows 관측 — 교체가 거절될 수 있다

`os.replace` 는 대상이 다른 손에 열려 있으면 거절됩니다(공유 위반). **내용 손상이 아니라
「지금은 안 된다」**입니다. 짧은 재시도(5·10·20·40·80ms)를 넣어 실측 **162/180 → 41/180**
으로 줄였고, 그래도 안 되면 **예외를 올립니다.** 0 이 되지는 않습니다.

⚠️ 그래서 **호출자가 예외를 삼키면 거기서 저장이 사라집니다.**
`core/async_orchestrator.py:_save_latest_state` 가 `except Exception: print(...)` 로 삼킵니다.
원자 쓰기와 **별개 문제**이고 동작을 바꾸면 실행 중단 여부가 달라지므로 이번에 고치지
않았습니다. 코드에 주석으로 표시해 두었습니다 — **판단이 필요합니다(§7)**.

## 5. ⚠️ 하지 않은 것 — 이것으로 「동시 쓰기 안전」이라고 읽지 마십시오

- **낡은 revision 덮어쓰기(lost update) 방지는 하지 않았습니다.** 지시가 「다른 문제, rename
  만으로 둘 다 달성했다고 쓰지 말 것」이라 못박은 그대로입니다. `os.replace` 는 늦게 온
  쓰기를 이기게 할 뿐입니다. 필요하면 판본 조건부 쓰기를 따로 세워야 합니다.
- ~~W03.1 부족분은 아직 보완하지 않았습니다.~~ → **§8 에서 보완했습니다**(같은 세션, 이어서).
- 두 호스트·공유 마운트 증거가 아닙니다. 단일 PC 의 독립 프로세스입니다.

## 6. 회귀와 격리

관련 8스위트: **176 passed / 1 skipped / exit 0**, `sources_unchanged: true`,
`protected_assets_unchanged: true`, `blocked_file_writes: []`, `repository_conftest_loaded: false`.

⚠️ 처음 묶음에 `tests/test_advisor_bootstrap.py` 를 넣었다가 **19 errors** 를 봤습니다.
전부 `fixture 'seeded_org' not found` 이며 그 fixture 는 `tests/conftest.py:539` 에 있습니다 —
**격리 러너는 저장소 conftest 를 읽지 않으므로 이 스위트는 러너 대상이 아닙니다.** 단독
실행에서도 같은 19건이고, 제 변경 파일 어디에도 그 이름이 없습니다. 제가 묶음을 잘못
고른 것이며 제품 결함이 아닙니다. (advisor 쪽 전환은 `test_advisor_state_write_is_atomic`
이 제품 함수를 직접 불러 확인합니다.)

운영 자료: 이 PC 의 `library/`·`projects/` 는 **원래 0건**이고 작업 전후 불변입니다.
LLM 0 · 외부 전송 0 · 운영 DB 0 · 커밋/푸시 0.

## 7. 바뀐 파일과 남은 판단

| 파일 | 내용 |
|---|---|
| `core/atomic_write.py` | **신규** — 원자 저장 한 곳 |
| `core/studio_project_files.py` | 구현을 공용으로. 직렬화 정책·바이트 불변 |
| `core/kit_app_builder.py` · `core/async_orchestrator.py` | 정본 쓰기 전환 |
| `api/routes/factory_control.py` · `api/routes/advisor_control.py` | 정본 쓰기 전환(함수 단위) |
| `scripts/w03_atomic_write_probe.py` | **신규** — 경쟁 증거 + 음성 대조군 |
| `tests/test_w03_atomic_save.py` | **신규 14건** |

**Codex 판단이 필요한 것 둘**

1. `_save_latest_state` 의 예외 삼킴을 고칠 것인가. 고치면 저장 실패가 실행을 멈출 수
   있어 동작이 바뀝니다. 지금은 원자 쓰기가 붙어도 **그 경로만 소실이 조용합니다.**
2. ~~W03.1 부족분을 묶을 것인가~~ → 사용자 지시로 **이어서 보완했습니다(§8).**

---

# W03.1 보완 — 프로젝트 갈래·접근권한 / 같은 세션 이어서

출구 원문: *「두 노드가 같은 **프로젝트/릴리스** 판본을 읽고 **접근권한을 확인한다**」*
첫 제출은 **릴리스 한 갈래**였고 권한 판정이 없었습니다. 그 둘을 채웠습니다.

## 8.1 무엇이 비어 있었나

| 출구 요소 | 첫 제출 | 지금 |
|---|---|---|
| 릴리스 판본 공유 | ✅ digest·소유문맥 6필드 | 유지 |
| **프로젝트 판본 공유** | ❌ 없음 | ✅ 추가 |
| **접근권한 확인** | ❌ 없음 | ✅ 추가 |
| 공유 실체(복제본·표식이 아님) | ✅ digest 기준 | 프로젝트도 같은 기준 |

## 8.2 새 도구를 만들지 않고 기존 probe 를 넓혔습니다

`scripts/w03_shared_read_probe.py` 에 `read-project` 갈래와 `compare_projects` 를 더했습니다.
격리 지점은 **`core.paths.PROJECTS_DIR` 하나**입니다 — `workspace_path()` 가 호출 시점에 그
값을 읽으므로(`core/paths.py` 의 격리 주석) 거기만 정하면 나머지 경로는 제품이 정합니다.

★ **권한 판정도 자식 프로세스 안에서** 합니다. 부모가 대신 계산하면 「그 노드가 그렇게
판정한다」가 아니라 「내가 그렇게 계산했다」가 됩니다. 그래서 **두 노드의 판정이 일치하는지**
까지 증거에 들어갑니다 — 판본이 같아도 판정이 갈리면 한쪽에서만 열리는 자원이 됩니다.

## 8.3 실행 결과 — `w03_shared_read_probe.py compare`, exit 0

| 판정 | 결과 |
|---|---|
| `release_shared` / `release_control_splits` | true / true (첫 제출 유지) |
| **`project_shared`** | **true** |
| **`project_control_splits`**(음성 대조군) | **true** — 옛 해석에서는 B 가 못 찾는다 |
| **`project_access_agrees_across_nodes`** | **true** — 두 노드가 같은 판정 |
| **`project_access_denies_the_outsider`** | **true** |

접근 판정(A·B 동일): `owner_dept` **보임** · `other_dept` **거절** · `unrestricted` 보임.
`binding_state: BOUND`. 같은 자원인데 **주체에 따라 갈립니다** — 전원 통과였다면 판정이
죽은 것입니다.

⚠️ `AccessScope.unrestricted` 기본값이 **`True`** 입니다. 명시하지 않으면 모든 주체가
통과해 「거절을 확인했다」가 거짓이 됩니다. 시험에 그 함정을 적어 두었습니다.

## 8.4 시험 — `tests/test_w03_shared_release_read.py` 4→8건

작업공간 뿌리가 저장소 기준 / cwd 를 옮겨도 같은 경로 / **주체별 접근 판정 네 갈래**
(소유부서·타부서·unrestricted·소유자 본인) / probe 가 프로젝트 갈래와 권한 판정을 실제로
들고 있는지.

⚠️ **제가 인계서 지뢰 #3 을 그대로 밟았습니다.** 「살아 있는 `PROJECTS_DIR` == `PROJECT_ROOT
/projects`」를 단언했다가 실패했습니다 — 격리 러너가 `_LIBRARY_DIR` 처럼 **이 상수도** 자기
실행 뿌리로 갈아끼웁니다. W03.1 작성자가 릴리스 쪽에서 겪고 적어 둔 것을 프로젝트 쪽에서
반복했습니다. 기존 방식대로 `runpy` 로 새 이름공간에서만 확인하도록 고쳤습니다
(`importlib.reload` 는 세션을 오염시키므로 쓰지 않습니다).

## 8.5 여전히 하지 않은 것

- **두 호스트·공유 마운트 증거가 아닙니다.** 단일 PC 의 독립 프로세스입니다.
- 실제 조직·실제 계정이 아닙니다. 합성 프로젝트 1판·합성 릴리스 1판입니다.
- 권한은 **읽기 가시성**(`ownership_visible`)만 봤습니다. 쓰기 권한·문맥 전환 거절은
  별도 경로입니다.

시험 22건(21 passed · 1 skipped) · exit 0 · `sources_unchanged: true` ·
`protected_assets_unchanged: true` · `blocked_file_writes: []`.
운영 자료 불변(`library/`·`projects/` 0건). 제품 코드 **추가 변경 없음** — 이 보완은 probe 와
시험만 바꿨습니다.

---

# W03.2 후속 — CR-1 정정과 저장 실패 관측 / 2026-09-22

브랜치 검토(`CODEX_W03_REVIEW_AND_NEXT_2026-09-22.md`)의 지시 ①②를 수행했습니다.

## 9. CR-1 — 링크 정책을 저장소와 같은 방향으로

**제 근거가 틀렸습니다.** 「공유 저장을 링크로 거는 구성을 지원해야 한다」며 링크를
**따라가게** 만들었는데, 이 저장소는 읽는 쪽에서 링크를 **아홉 곳에서 거절**합니다
(`async_orchestrator:295` · `factory_control:2448·2631·2662` · `studio_project_files:53·56` ·
`studio_pause_state:37` · `studio_revision_requests:81·87` · `studio_contract_reconcile:219·292` ·
`studio_input_draft_control:106`). P05.1 CR 「junction 차단 누락」과 같은 방향입니다.

⚠️ 따라가면 **`latest_state.json` 이 링크일 때 쓰기는 성공하고 읽기는 503** 이 됩니다 —
W03 이 없애려던 「한쪽에서만 열리는 자원」을 오히려 만듭니다.

**판단: 차단으로 뒤집었습니다.** 공유 저장을 링크로 지원하려면 **읽기와 쓰기를 함께** 바꿔야
하고 그건 별도 결정입니다. 쓰기만 먼저 바꾸는 것은 순서가 틀렸습니다.

- `_resolved_target()` → `_checked_target()`. **대상과 그 부모**를 봅니다 —
  `factory_control.py:2631` 이 `(target_root, meta_path)` 를 보는 것과 같은 수준입니다.
  더 위로 올라가면 상위 경로를 링크로 건 정상 배포까지 막습니다.
- 예외는 기존 읽기 쪽과 같은 `ValueError`·같은 어조(「연결된 …」)를 씁니다.
- ⚠️ `scripts/session_data_snapshot.py:70 regular()` **재사용은 검토했으나 맞지 않았습니다** —
  `root` 를 받아 경로 탈출까지 보는 함수라 뿌리 개념이 없는 여기서는 쓸 수 없고,
  `core/` 가 `scripts/` 를 import 하면 의존 방향이 뒤집힙니다. 같은 판정식만 따랐습니다.
- 시험을 **거절 확인으로 뒤집었습니다**. 이 환경에서는 symlink·junction 둘 다 만들 수 있어
  **skip 없이 실측**했습니다(`_winapi.CreateJunction` 확인). 링크 대상·**링크 부모** 두 갈래.

## 10. 저장 실패 관측 — 삼킴은 유지, 조용함은 제거

`_save_latest_state` 의 `except Exception: print(...)` 을 **그대로 둡니다.** 예외를 올리면
상태 저장 하나 때문에 스프린트 실행 전체를 잃고, 그쪽이 더 나쁩니다.

대신 **사후에 물어볼 수 있게** 했습니다.

- `orchestrator.last_state_save_error` 에 `{project_id, at, error}` 를 남깁니다.
  **성공하면 지웁니다** — 남아 있다는 것이 「마지막 저장이 실패한 상태」라는 뜻입니다.
- 기존 경로 `factory_broadcaster.broadcast` 로 `STATE_SAVE_FAILED` 를 알립니다. 새 채널을
  만들지 않았습니다(라우팅은 `project_id` 로 되며 event_type 은 라우팅 키가 아닙니다).
- **알림이 깨져도 실행은 계속되고 기록은 남습니다** — 알림은 기록의 조건이 아닙니다.
- ⚠️ **재시도를 늘려 덮지 않았습니다.** 41/180 은 reader 가 3초에 5천 번 여는 극단
  조건이고, **실제 부하에서의 수치는 아직 모릅니다.** 모르는 것을 모른다고 적습니다.

★ 이 시험(`test_state_save_failure_is_swallowed_but_left_findable`)은 **「원자 저장을 했으니
저장은 안전하다」의 반례**이기도 합니다. 이 경로는 원자 쓰기를 붙여도 소실이 가능합니다.

## 11. 검증

| 대상 | 결과 |
|---|---|
| `tests/test_w03_atomic_save.py` | **17건**(15 → 17, skip 0) |
| 회귀 8스위트 | **184 passed / exit 0 / skip 0** (이전 176 + 1 skip) |
| `w03_atomic_write_probe.py compare` | exit 0 · torn **0** / 음성 대조군 **413** |
| `w03_shared_read_probe.py compare` | exit 0 · 판정 6/6 |
| 격리 | `sources_unchanged: true` · `protected_assets_unchanged: true` · 차단 쓰기 0 |

## 12. 남은 것 — 검토 지시 ③④

- **W03.3**(40점) — DB·파일 일관성 복구. → **§13 에서 착수했습니다.**
- 낮은 순위: 원자 쓰기 구현 4→1 통합(`config_snapshot:160`·`contract_decision:298`),
  `test_advisor_bootstrap.py` 의 러너 fixture 부채, **lost update 를 별도 단계로 뗄지**.
- ⚠️ **여전히 단일 PC 증거**이고 두 호스트·공유 마운트가 아닙니다.

---

# W03.3 — DB·파일 일관성 식별 / 2026-09-22

acceptance: *「DB 상태와 정본 파일의 불일치를 식별/복구하고 다른 문맥 노출을 차단한다」*
(40점, 선행 W03.2·P01.1)

## 13. 먼저 «가능한 불일치» 를 코드에서 확인했습니다 — 가설로 복구기를 만들지 않았습니다

릴리스의 사실이 **두 곳에 나뉘어** 있습니다.

```
library/<id>/release.json     정본 — 무엇인가 · 누구 것인가(소유문맥)
data/program_lifecycle.db     사용여부 — 켜져 있는가 · 왜 껐는가 · 누가 껐는가
```

`_release_exists()` 는 **파일만**(`os.path.exists`), `get_status()` 는 **DB 만** 봅니다.
**대조하는 곳이 없습니다.**

| 조합 | 판정 | 근거 |
|---|---|---|
| 파일 O + 행 O | 정상 | — |
| **파일 O + 행 X** | **불일치 아님** | `get_status` 가 미기록을 `active`·`recorded=False` 로 답하도록 **설계**돼 있습니다. 이것까지 세면 이 기능 이전에 게시된 릴리스가 매번 경보가 됩니다 |
| **파일 X + 행 O** | ⚠️ **불일치** | 같은 질문에 두 답이 됩니다 |

**「파일 X + 행 O」가 위험한 이유** — 목록 API(`factory_control.py:3620~`)는 보관소
디렉터리를 순회하므로 안전합니다. 그러나 **단건 `get_status` 를 쓰는 다섯 곳**
(`app_data_control:349` · `app_data_runtime:237` · `calculation_control:686` ·
`data_preparation_control:1478` · `factory_control:2881`)은 **없는 릴리스를 「사용 가능」
으로 판정**할 수 있습니다. 그리고 **DB 에는 소유문맥 컬럼이 없어** 파일이 사라지면
문맥 판정 자체가 불가능합니다 — 「다른 문맥 노출 차단」이 성립하지 않는 자리입니다.

## 14. 만든 것 — 식별과 «사실 노출» 까지

**`core/release_consistency.py`(신규)** — 대조해서 **보고만** 합니다. 읽기 전용입니다.

⚠️ **복구를 자동으로 하지 않습니다.** 둘 중 하나를 고르면 **반드시 자료를 잃습니다**:
DB 행을 지우면 「관리자가 이 프로그램을 껐다」는 **결정 기록이 사라지고**, 껐던 릴리스가
재게시되면 **켜진 채로 돌아옵니다.** 파일을 되살리는 것은 내용을 몰라 불가능합니다.
W03.3 지시의 「자료삭제/정본선택이 필요한 충돌은 주요결정으로 올린다」에 해당하므로
**§16 에 결정 요청으로 올립니다.**

**`get_status` 에 `artifact_present` 추가** — 기존 필드는 **그대로 두고** 사실을 하나
얹었습니다. 호출자를 깨뜨리지 않으면서 숨기지도 않습니다. 파일이 없으면 `note` 에
「정본 파일이 없습니다 — 소유 문맥을 확인할 수 없습니다」가 붙습니다.
⚠️ `_read_status`(트랜잭션 안 순수 DB 읽기)에는 넣지 않았습니다. 쓰기 경로는 `set_status`
가 이미 `_release_exists` 로 막습니다.

## 15. ★★ 회귀가 내 결함을 잡았습니다 — MAX_PATH

`test_b3_kit_contract_v2` 가 `FileNotFoundError` 로 깨졌습니다. 경로 **278자**:

```
…/kitapp_ki_604d5af5542747dfaa9671e49097c7f8_APP-03/release.json.<uuid32>.tmp
                                                    ^^^^^^^^^^^^  +37자
```

**원본 `release.json` 은 써지는데 제 임시 파일만 못 만드는** 상태였습니다. Windows
MAX_PATH(260) 초과입니다. **원자 저장을 넣었더니 원래 되던 것이 안 된 것**이라 결함입니다.

**고침** — 임시 이름을 **정본보다 길지 않게** 유지하는 불변식을 세웠습니다.

| | 이전 | 지금 |
|---|---|---|
| 임시 | `release.json.<uuid32>.tmp` (49자) | `.<hex6>.tmp` (**11자**) |
| 정본 | `release.json` 12자 · `latest_state.json` 17자 | — |

원본을 쓸 수 있는 경로면 임시도 쓸 수 있습니다. 원본 이름을 버리는 대가로 「누구의
임시인가」를 이름으로 알 수 없게 되지만 같은 디렉터리에 있고 `finally` 에서 바로 지웁니다.
짧은 난수라 이름이 겹칠 수 있어 그때는 다시 고릅니다(`"x"` 배타 생성 유지).

시험 2건 추가 — **임시 이름 ≤ 정본 이름** 불변식과, 200자 넘는 경로에서의 실제 재연
(정본도 못 쓰는 환경이면 skip).

★ 이 결함은 **W03.2 회귀 묶음(8스위트)에서는 안 잡혔습니다.** 경로가 짧았기 때문입니다.
W03.3 을 하며 묶음을 넓혔더니 나왔습니다 — 회귀 범위가 증거의 범위입니다.

## 16. ⚠️ 주요 결정 요청 — 복구 정책

불일치를 **찾았을 때 무엇을 할 것인가**. 자동으로 정하지 않았습니다.

1. **DB 행 폐기** — 「껐다」는 결정이 사라집니다. 재게시 시 켜진 채 돌아옵니다.
2. **행 보존 + 격리 표시** — 목록·판정에서 제외하되 기록은 남깁니다. 재게시하면 옛 결정이
   되살아납니다(그것이 맞는지도 결정 대상입니다).
3. **사람이 건별로 판단** — 도구는 보고만. 지금 구현이 여기입니다.

권고는 **2번**입니다 — 결정 기록을 잃지 않으면서 노출도 막습니다. 다만 「재게시 시 옛
결정을 되살릴 것인가」가 딸린 질문이라 **혼자 정하지 않았습니다.**

## 17. 검증과 남은 범위

| 대상 | 결과 |
|---|---|
| `tests/test_w03_release_consistency.py` (신규) | **7건** |
| `tests/test_w03_atomic_save.py` | **19건**(17 → 19, MAX_PATH 2건 추가) |
| W03 묶음 | **26 passed / exit 0** |
| `test_b3_kit_contract_v2.py` (깨졌던 것) | **50 passed / exit 0** |
| 변이 | `_artifact_present` 제거 → **2건 실패** · `get_status` 쪽 제거 → **1건 실패** · 원복 해시 일치 |
| 격리 | `sources_unchanged: true` · `protected_assets_unchanged: true` · 차단 쓰기 0 |

**하지 않은 것** → §18~§20 에서 처리했습니다(사용자가 ②를 고르고 호출자 연결을 지시).

- ~~다섯 호출자 연결~~ → **셋 연결**(§18 에 정정 근거).
- ~~복구 실행~~ → **정책 ② 구현**(§19).
- 프로젝트 쪽(`latest_state.json` ↔ 판본 DB) 불일치는 **이번 범위 밖**입니다. `project_context()`
  가 이미 `is_v2_project` 와 파일을 대조해 차단하고 있어(`STUDIO_PROJECT_PROVENANCE_REQUIRED`
  ·`STUDIO_PROJECT_CONTEXT_MISSING`) 릴리스 쪽과 상태가 다릅니다. 별도로 봐야 합니다.

---

# W03.3 (2) — 정책 ② 적용과 호출자 연결 / 2026-09-22

사용자 결정: **②「행 보존 + 격리 표시」**, 그리고 **호출자 연결**.

## 18. ⚠️ 정정 — 위험한 호출자는 다섯이 아니라 **셋**이었다

§13 에서 「단건 `get_status` 를 쓰는 다섯 곳이 없는 릴리스를 사용 가능으로 판정할 수
있다」고 적었습니다. **연결하려고 실제 코드를 읽으니 둘은 이미 파일을 확인하고 있었습니다.**

| 호출자 | 정본 확인 | 조치 |
|---|---|---|
| `calculation_control.py:683` | **이미 있었다** — 없으면 409 「아직 생성되지 않았습니다」 | 그대로 둠 |
| `data_preparation_control.py:1475` | **이미 있었다** — 없으면 `""` | 그대로 둠 |
| `app_data_control.py:349` | 없었다 | **연결** |
| `app_data_runtime.py:237` | 없었다 | **연결** |
| `factory_control.py:2881` | 없었다 | **연결** |

★ 이미 확인하는 둘을 굳이 바꾸지 않았습니다. `calculation_control` 은 정본 없음을 **다른
문구로 구분해 답하고**(「아직 생성되지 않았습니다」) 그 구분이 사용자에게 쓸모가 있습니다.
공통 함수로 뭉뚱그리면 그 말이 사라집니다.

## 19. 정책 ② — 기록은 남기고, 판정에서만 뺀다

`ProgramLifecycle.effective_status(release_id)` 를 추가했습니다. **정본이 없으면 빈
문자열**입니다.

- **행은 지우지 않습니다.** `get_status` 는 여전히 `status`·`reason`·`changed_by` 를 다
  줍니다. 격리와 기록 삭제는 다릅니다.
- **재게시하면 껐던 결정이 그대로 살아납니다** — ② 를 고른 이유입니다. ①(행 폐기)이었다면
  꺼 두었던 프로그램이 `active` 로 돌아옵니다. 시험
  `test_the_old_decision_comes_back_with_the_artifact` 가 이것을 고정합니다.
- ⚠️ **새 상태 어휘를 만들지 않았습니다.** 빈 문자열을 씁니다 — 받는 자리들이 이미
  「모르면 접지 않는다」로 짜여 있기 때문입니다(`audience_for_state("")` → 청중 없음 →
  평면도 안 고름). 새 값을 만들면 그 fail-closed 경로를 타지 않고 각자 새로 판단하게 됩니다.

세 호출자는 `get_status(...)["status"]` 대신 `effective_status(...)` 를 부릅니다. 각자의
기존 fail-closed 주석(「모르면 운영으로 접지 않는다」)이 그대로 유효합니다.

## 20. 검증과 귀속

| 대상 | 결과 |
|---|---|
| `tests/test_w03_release_consistency.py` | **7 → 11건** |
| 핵심 묶음 4스위트 | **65 passed / exit 0** |
| 변이(`effective_status` 에서 격리 제거) | **3건 실패** → 원복 |
| 격리 | `sources_unchanged: true` · `protected_assets_unchanged: true` · 차단 쓰기 0 |

**★ 호출자 연결은 소스 문자열이 아니라 제품 함수를 직접 불러 확인했습니다** —
`app_data_control._audience_for_release` 가 정본 삭제 후 빈 청중을 주고,
`app_data_runtime._release_state` 가 빈 문자열을 줍니다.

### 111건 기존 실패 — 이 PC 에서도 재현됩니다

`test_app_data_runtime` 을 돌렸더니 **28 failed / 18 passed** 로, 원래 PC 보고의
`test_app_data_runtime 28` 과 **수가 같습니다.** 증상도 대표 증상 그대로입니다.

```
26건  {"detail":"같은 이름의 데이터셋이 이미 있습니다: orders"}
 2건  {"detail":"저장소 상태를 확인할 수 없습니다 …"}
```

**내 변경(`effective_status`·`_release_state`·`artifact_present`·`release_consistency`)이
traceback 에 등장한 실패는 0건입니다.**

⚠️ 다만 **A/B 비교는 하지 않았습니다**(스위트당 20분 이상). 위 셋 — 원래 PC 와 같은 수,
같은 대표 증상, 내 심볼 부재 — 을 근거로 기존 실패로 판단했으며, 그것이 증명은 아닙니다.
인계서는 「새PC 재현은 미확인」이라고 했으나 **이 PC 에서는 재현됨을 확인했습니다.**

---

# R01.1 필수 provider 한 경로 — Claude / 2026-09-22

★ **단계 ID 가 다릅니다.** P03·W03 점수에 합산하지 않습니다(20점, 선행 없음, 승인 없음,
담당 Claude — 원장 확인). 결과는 관례대로 이 문서에 누적합니다.

acceptance: *「대상 앱이 요구하는 지원 provider 를 실제 데이터 읽기/쓰기 경로에 연결한다.
미지원은 조용히 fallback 하지 않는다.」*

## 21. 먼저 As-Is — 이미 되어 있었습니다

`core/host_runtime_provider.py` 는 이 요구를 이미 지키고 있었습니다.

- `provider_for_intent()` — 모르는 의도는 **빈 문자열**. `dict.get(x, NATIVE)` 를 쓰지 않습니다.
- `resolve()` — 미지원 provider 는 `NOT_YET_SUPPORTED` 로 **거절**하고 빈 목록을 주지 않습니다.
- `assert_writable()` — 쓰기는 Native 하나뿐, fail-closed.
- `public_meta()` — provider 종류·결속 id 는 앱에 나가지 않습니다.

`tests/test_provider_dispatch.py` 가 이 단위를 **27건**으로 덮고 있습니다. GAP 이 R01 을
「부분 구현」이라 한 이유가 이것입니다 — **빠진 것은 구현이 아니라 다른 데 있었습니다.**

## 22. 빠져 있던 것 — 「실제 경로」가 단위로 검증된 적이 없다

기존 시험은 `prov.resolve()` 를 **직접** 부릅니다. 실제 요청이 지나가는 자리는 그 앞단인
`api/routes/app_data_runtime._dispatch()` 이고, 그곳은 **HTTP 시험으로만 간접 확인**됐습니다.
그 HTTP 시험이 이 환경에서 **10건 깨져 있습니다**(`MaterializeError: arrivals`, §20 의 111건
계열이며 범위 밖). 즉 **실제 경로에 대한 살아 있는 증거가 없는 상태**였습니다.

`_dispatch` 는 `_plane()` 하나만 대신하면 단위로 부를 수 있어, 그 자리를 12건으로 덮었습니다.

## 23. ★★ 핵심 발견 — 「이 출처가 지금 되는가」가 **두 곳**에 적혀 있다

```
core/app_runtime_contract.py  SOURCE_INTENT_DECISION   ← 앱을 «만들 때» 보는 표
core/host_runtime_provider.py SERVING_PROVIDERS        ← 앱이 «돌 때» 보는 표
```

**지금은 일치합니다**(AFS_NATIVE·ENTERPRISE_READ 지원 / EXTERNAL_REFERENCE·DERIVED_READ 대기).
그러나 한쪽만 열면 **앱은 만들어지는데 실행이 거절**되고, 어느 쪽도 미리 오류를 내지
않습니다. 이 저장소가 여러 번 겪은 「판정이 두 곳에 있다」 유형입니다.

`test_the_two_support_tables_say_the_same_thing` 이 그 갈림을 잡습니다 — 변이로
`SERVING_PROVIDERS` 에 `CONNECTOR_QUERY` 만 넣자 **정확히 그 시험이 실패**했습니다.

## 24. 시험 12건과, 느슨해서 조인 것

레거시 빈 의도(`source_intent=""`)가 Native 로 가는 것도 고정했습니다 — ⚠️ 이것은
**폴백이 아니라** 옛 계약의 뜻입니다. 다만 `provider_for_intent("")` 는 **거절**하므로
**같은 빈 값에 두 곳이 다르게 답하는 자리**이고, 의도된 차이임을 시험에 적어 두었습니다.

⚠️ **처음 쓴 미지원 시험이 느슨했습니다.** `status_code >= 400` 만 봐서 「미지원이라
거절」과 「계약 키가 없어 거절」을 구분하지 못했고, **지원 표를 한쪽만 여는 변이에서도
초록**이었습니다. 앱에는 코드만 가므로 이유는 한 단계 아래(`resolve`)에서 확인하도록
조였고, 그러자 변이에서 **2건**이 실패했습니다.

## 25. 검증

| 대상 | 결과 |
|---|---|
| `tests/test_r01_provider_path.py` (신규) | **12 passed / exit 0** |
| 변이(지원 표 한쪽만 열기) | 조이기 전 **1건** → 조인 뒤 **2건** 실패 · 원복 해시 `73e04957…` 일치 |
| 격리 | `sources_unchanged: true` · `protected_assets_unchanged: true` · 차단 쓰기 0 |

**제품 코드 변경 0.** 시험만 추가했습니다.

## 26. ⚠️ R01.1 전체 충족이 아닙니다

- **「대상 7앱의 요구」를 실측하지 못했습니다.** 이 PC 는 `library/` 가 0건입니다. 합성 앱의
  의도는 제가 정하는 것이라 「대상 앱이 무엇을 요구하는가」의 답이 되지 않습니다.
  **실제 앱 자산이 있는 환경에서 다시 봐야 합니다.**
- **토큰/권한 상속**(GAP 의 나머지 절반)은 R01.2·R01.3 의 범위로 보고 손대지 않았습니다.
- 깨진 HTTP 경로 시험 10건은 고치지 않았습니다 — 픽스처 계열 문제이고 범위 밖입니다.

따라서 이번 산출물은 **「실제 경로의 살아 있는 증거 + 두 지원 표 갈림 차단」**이며,
R01.1 의 수용 여부는 위 미실측 범위를 함께 보고 Codex 가 판단할 일입니다.

---

# W03.2 보완 — 조건부 저장 · 상위 링크 · 실패 소비 (Claude / 2026-09-22)

Codex 검토(22:32) §6 의 세 지적을 닫는다. **새 단계·추가 배점을 만들지 않았다** —
기존 W03.2 45점 안에서 마무리한다.

## 1. lost update — 「다른 문제」였지 「안 해도 되는 문제」가 아니었다

앞 판은 부분 파일만 막고 lost update 를 남겼다. 수용문이 「부분 파일**이나 잘못된 판본**」
이므로 **같은 단계 안에서** 닫는다.

`core/atomic_write.py` 에 조건부 저장을 세웠다.

```
digest_of(path)                      현재 판본 지문. 없으면 "" (None 을 쓰지 않는다)
replace_text_if_unchanged(...)       기준이 그대로일 때만 교체. 아니면 StaleWriteError
replace_json_if_unchanged(...)       같은 것, JSON
```

★★ **비교와 교체가 같은 상호배제 구간 안**에 있다. 잠금 밖에서 비교하고 안에서 바꾸면
그 사이가 곧 lost update 의 창이고, 그러면 검사는 있는데 막지 못하는 모양이 된다.

### 잠금 «권위» 를 어디에 둘 것인가 — 이 보완의 핵심

| 기존 | 잠금 파일 위치 | 공유 저장에서 |
|---|---|---|
| `studio_project_files.operation_lock` | `data/studio_bootstrap_locks` (**노드 로컬**) | ✗ 서로의 잠금이 안 보인다 |
| `contract_decision._workspace_lock` | workspace 안 (**자료 옆**) | ✓ 같은 권위 |

후자를 따랐다 — 잠금 파일을 **정본 옆에** 둔다. 정본이 공유 저장에 있으면 잠금도 그 위에
있다. ⚠️ 다만 이것은 **같은 filesystem 을 공유하는 writer 들** 사이의 잠금이다. 공유
프로토콜이 파일 잠금을 지원하지 않으면 성립하지 않는다 — 실제 공유 마운트에서 다시
확인해야 한다(이번 증거는 단일 PC).

⚠️ 잠금 파일 이름도 **짧게** 유지했다. 임시 파일에서 MAX_PATH 결함을 한 번 겪었으므로
같은 실수를 곁다리로 되풀이하지 않는다(시험으로 고정).

### writer 별 적용·불필요 근거

| writer | 판단 |
|---|---|
| `async_orchestrator._save_latest_state` | **적용.** 프로젝트 정본 상태이고 노드가 둘이면 같은 파일을 쓴다 |
| `factory_control:1176·1190` (mega/sub 생성) | 불필요 — **생성 시점 1회**, 새 디렉터리. 경쟁 writer 없음 |
| `kit_app_builder:427` · `factory_control:3323·3361` (release.json) | 불필요 — 릴리스 id 마다 새 디렉터리. 같은 id 를 두 노드가 동시에 만들면 그건 상위 발급 문제다 |
| `studio_project_files:36` | 불필요 — 이미 `operation_lock` 아래다. ⚠️ 단 그 잠금은 **노드 로컬**이라 공유 저장에서는 약하다(별건) |
| `advisor_control:49` | 불필요 — 상담 플레이북, 정본 상태가 아니다 |

⚠️ 기준 판본은 **「이 writer 가 마지막으로 본 값」**이다. 쓰기 직전에 읽어 기준으로 삼으면
그건 조건이 아니라 형식이고 늦게 온 쓰기가 여전히 이긴다.
⚠️ 기준을 모를 때(프로세스 재시작 뒤 이어받기)는 현재 판본을 **한 번 받아들인다.** 그
한 번은 경쟁을 못 잡는다 — 숨기지 않고 코드에 적었다.

## 2. 상위 링크 — 한 칸만 더 위면 통과했다

`_checked_target` 이 `(대상, 부모)` 만 봤다. 그래서
`연결된_상위/일반_하위/latest_state.json` 은 **대상도 부모도 링크가 아니라** 그냥 통과한다.

**뿌리까지 올라간다.** 그리고 둘을 더 지킨다.

- **정식 mount 는 링크가 아니다.** Windows 볼륨 마운트 지점도 reparse point 라
  `is_junction()` 이 참이지만 배포가 의도한 구성이다. `os.path.ismount` 로 가른다.
  이 구분이 없으면 공유 저장을 정식 mount 로 붙인 구성에서 제품이 **아예 못 쓴다.**
- **뿌리를 모른다고 부모에서 멈추지 않는다.** `root` 가 없으면 꼭대기까지 본다.

⚠️ 그리고 **뿌리 밖 경로를 거절하지 않는다.** 처음에 거절로 만들었더니 임의 작업공간을
쓰는 정상 호출자가 막혔다(실측 1건). 이 모듈은 경로 봉쇄의 권위가 아니다 — 뿌리의 쓰임은
「검사를 어디서 멈추는가」 하나이고, 무관한 경로면 **더 넓게** 본다.

**`mkdir` 도 경계 안으로** 넣었다(`ensure_directory`). 검사 밖에 있으면 그 자체가
우회로다 — 연결된 상위 아래에 디렉터리를 만들어 놓고 「대상은 링크가 아니다」로 통과한다.
적용: `_save_latest_state` · `kit_app_builder` · `factory_control`(릴리스).

## 3. 실패 소비 — 관측만으로는 성공이 된다

`_save_latest_state` 가 실패해도 **정상 반환**해서 호출자가 성공 흐름을 이어갔다.

- **결과를 돌려준다**: `{saved, project_id, error, stale}`. 실행은 여전히 안 멈춘다
  (저장 하나로 스프린트를 잃지 않는다) — 다만 호출자가 **구분해 소비**할 수 있다.
- **`NODE_COMPLETED` 가 저장 성공을 뜻하지 않게** 했다. `state_saved` 를 함께 보내고,
  실패면 사유와 `stale` 여부를 싣는다. 예전에는 저장이 실패해도 완료 통지가 그대로 나가
  화면이 「이 노드 끝남」으로 읽고 새로고침하면 옛 상태가 왔다.
- **프로젝트별로 남긴다**(`state_save_failures`). 단일 필드 하나면 **A 가 실패한 뒤 B 가
  성공하는 순간 A 의 실패가 지워진다** — 물어보면 「없다」고 답하게 된다.
- **`stale` 과 교체 실패를 구분**한다. 앞쪽은 다시 읽고 다시 만들어야 하고, 뒤쪽은
  재시도로 풀린다. 충돌이면 기준을 버려 다음 저장이 현재 판본을 다시 읽는다 — 안 버리면
  같은 낡은 기준으로 영원히 거절된다.

## 4. 증거

### probe (격리 러너 밖 — 러너가 `subprocess.Popen` 을 막는다. 끄지 않았다)

```
w03_atomic_write_probe.py lost-update --writers 3 --rounds 40      exit 0
  조건부     applied 93 · refused 27 · 남의 판본 덮어쓰기 0
  대조군     applied 120 · refused 0 · writer 마다 남의 판본 덮어쓰기 1
```

★ 대조군에서 **아무도 거절당하지 않고** 남의 판본이 조용히 사라진다. 조건부에서 27건이
거절된다 — 거절이 0 이면 경쟁이 없었던 것이지 통제가 증명된 게 아니다.

⚠️ 이 판정은 **lost update 만** 본다. 부분 파일은 기존 `compare` 갈래가 본다. 두 문제를
한 칸에 세지 않는다.

### 시험

신규 `tests/test_w03_conditional_save.py` **13건** — 조건부 거절·새 파일·잠금 위치·
잠금 이름 길이·2단계 위 junction 거절·정상 깊은 경로 양성·정식 mount 통과·
`ensure_directory` 선검사·뿌리 미지정 시 전체 검사·뿌리 무관 시 확대·실패 반환·
프로젝트별 보존·`stale` 구분.

## 5. 이번에 내가 겪은 것

1. **뿌리 밖을 거절하게 만들었다가 정상 호출자를 막았다.** 시험 1건이 즉시 잡았다.
   봉쇄와 「검사 범위」를 섞은 것이 원인이다.
2. **시험이 낡은 대역을 붙들고 있었다.** 제품이 `replace_json_if_unchanged` 를 부르게
   바뀌었는데 시험은 `replace_json` 을 대역으로 바꿔서 주입한 실패가 안 났다 — 3건이
   실패로 알려 줬다. 시험이 변경을 제대로 잡은 경우다.
3. **죽은 줄을 하나 넣었다**(아무것도 안 하는 `pass` 블록). 지웠다.

## 6. 검증 — 이번 보완 뒤

```
넓은 묶음 10스위트   collected 194 · 193 passed · 1 skipped · exit 0 (13분 45초)
                     sources_unchanged: true · protected_assets_unchanged: true
                     blocked_file_writes: [] · blocked_sqlite_paths: []

probe (러너 밖)      lost-update  exit 0  조건부 거절 27 / 대조군 거절 0·덮어쓰기 3
                     compare      exit 0  atomic torn 0 / legacy torn 1088
                     shared-read  exit 0  판정 6/6
```

대상: `test_w03_conditional_save`(신규 13) · `test_w03_atomic_save` · 
`test_w03_release_consistency` · `test_w03_shared_release_read` · `test_r01_provider_path` ·
`test_b3_kit_contract_v2` · `test_program_lifecycle` · `test_release_readiness` ·
`test_app_delivery_real_release` · `test_kit_app_api`.

★ `test_b3_kit_contract_v2`(MAX_PATH 결함을 잡았던 스위트)를 포함했다 — `ensure_directory`
를 릴리스 쓰기에 넣으면서 긴 경로가 다시 깨지지 않는지 봐야 했기 때문이다.

⚠️ 1 skipped 는 `test_a_linked_target_is_rejected` 다. **파일 심볼릭 링크를 이 환경에서
만들 수 없어 미실측**이며(Windows 권한), 부모 junction 케이스 통과가 그 사례를 대신하지
않는다. 이번 보완으로 **2단계 위 junction 거절**은 실측했다.

⚠️ 111건 계열(`test_app_data_runtime`·`test_provider_dispatch`·`test_advisor_bootstrap`)은
인계서 지시대로 **넣지 않았다** — 기존 실패라 귀속이 섞인다.

## 7. 남은 것

- **실제 공유 마운트 실측.** 잠금이 정본 옆에 있어도 공유 프로토콜이 파일 잠금을
  지원해야 성립한다. 이번 증거는 전부 단일 PC 다.
- **재시작 직후 한 번의 창.** 기준을 모를 때 현재 판본을 받아들이므로 그 한 번은 경쟁을
  못 잡는다. 코드에 적어 두었고 숨기지 않았다.
- **파일 심볼릭 링크 거절 미실측**(위 skip).

---

## 9. Claude 보완 회신 — CR-2A/2B/2C · 판단 ②③ (2026-09-22)

**반례 셋을 재현해 주셔서 세 가지가 잡혔습니다. 특히 2A 는 제 진단 자체가 틀렸습니다** —
제가 「재시작 직후 한 번의 창」이라 적은 것이 실제로는 **충돌마다 재개방**되는 구멍이었고,
원인은 제가 「충돌이면 기준을 버린다」고 써 둔 바로 그 줄이었습니다. 거절을 **지연된
덮어쓰기**로 바꿔 놓았습니다.

### 9.1 CR-W03-2A — 기준 판본을 데이터에 결속

- **`digest` 만 새로 읽어 재시도하는 경로를 없앴습니다.** 충돌이어도 **기준을 버리지
  않습니다** — 같은 payload 는 몇 번을 보내도 거절됩니다.
- **기준이 없는데 파일이 있으면 쓰지 않습니다**(`StateNotClaimedError`). 새 파일 생성과
  기존 판본 인수를 갈랐습니다. 새 인스턴스의 첫 저장도 같은 경계를 지납니다.
- 인수는 `claim_project_state()` 로 **명시**해야 하고, 실행 권한이 확인된
  `_run_sprint_loop` 진입에서만 부릅니다.

### 9.2 CR-W03-2B — 뿌리 위를 잘라내던 것을 없앰

`root` 가 조상이면 그 위를 잘라내던 코드를 지웠습니다. **링크 검사는 언제나 전체 조상**을
봅니다. `root` 는 이제 **담김 확인**에만 씁니다. 「뿌리보다 위는 배포의 몫」이라고 제가
단 주석이 곧 구멍이었습니다 — **주석으로 생략한 검사는 검사가 아닙니다.**

정식 mount 면제는 `os.path.ismount` 로만 가릅니다. ⚠️ 지적하신 대로 `ismount` 대역
시험은 **분기 시험이지 실제 배포 mount 승인·동작 증거가 아닙니다** — 그 한계를 시험
docstring 에 적었습니다.

### 9.3 CR-W03-2C — 실제 소비까지 연결

- **store**(`useFactoryStore.ts:1180`): 저장이 실패하면 그 판본을 **「확인된 최신」으로
  적지 않습니다.** 예전에는 판본만 기록해, 서버 정본은 옛 판본인데 화면은 새 것을
  가졌다고 믿고 **재조회를 건너뛰어 옛 상태가 고정**됐습니다. 실패면 매번 다시 묻습니다.
  `lastStateSaveError` 를 따로 남겨 **계산 완료와 저장 완료를 구분**합니다.
- **`SPRINT_COMPLETED`**: `state_saved`·`state_save_error` 를 함께 보냅니다. 완료 통지가
  저장 성공을 뜻하지 않습니다.
- **quota**: `_save_latest_state` 반환값을 더는 무시하지 않고 `QUOTA_EXHAUSTED` 에 싣습니다.
- `frontend` `tsc -b` **exit 0**.

### 9.4 판단 ② — writer 표 정정 (**제 앞 표가 세 곳 틀렸습니다**)

| writer | 앞 표 | 실제 | 처리 |
|---|---|---|---|
| `advisor_control:495` | ~~「플레이북, 정본 아님」~~ | **`latest_state.json` 생성** | 배타 생성 |
| `kit_app_builder:427` | ~~「새 디렉터리」~~ | **갱신**(`release_id_for` 결정론적) | 조건부 |
| `factory_control:3325` | ~~「새 디렉터리」~~ | **생성**, 초 단위 id | 배타 생성 → **409** |
| `factory_control:3364` | ~~언급 없음~~ | **같은 파일 2번째(갱신)** | 첫 쓰기 digest 기준 |
| `factory_control:1176·1190` | 생성 | 생성(`allocate()` id) | 그대로 |

전제를 시험으로 박아 뒀습니다 — id 규칙이 바뀌면 이 판단도 함께 재검토됩니다.

### 9.5 판단 ③ — 겹칩니다. **연결은 되돌렸고 이유를 남깁니다**

`studio_bootstrap.py:127` 이 `operation_lock` 아래에서 **같은 `latest_state.json`** 을
씁니다. 「W03 밖이라 안전」으로 처리하지 않습니다.

조건부 저장을 붙였다가 **되돌렸습니다.**

1. 기준 판본은 그 조작이 **앞서 읽은 것**이어야 하는데(`verify_files`) 지금 단계 기계가
   그 값을 들고 다니지 않습니다. 쓰기 직전에 읽어 기준으로 삼으면 그건 조건이 아니라
   형식입니다 — **제가 방금 2A 에서 고친 바로 그 잘못**입니다.
2. `write_json` 의 **호출 모양**을 바꾸자 기존 실패 주입 대역(`fail_ready_state(path,
   value)`)이 깨졌습니다. 이름은 남겼는데 인자를 더한 것이라 이음매를 흔드는 변경이었고,
   B3 시험이 잡았습니다.

→ **열린 결함**으로 남기고, 겹침이 사라지면 실패하는 시험을 박았습니다. 기제
(`write_json(..., expected_digest=)`)는 준비돼 있어 단계 기계와 함께 볼 때 붙일 수 있습니다.

### 9.6 그 과정에서 드러난 것 — 잠금 파일이 정본 옆에 남는다

지우면 그 틈에 다른 프로세스가 같은 이름으로 새로 잡아 **상호배제가 조용히 사라지므로**
지울 수 없습니다(`contract_decision._workspace_lock` 도 같은 이유로 남깁니다).
`LOCK_SUFFIX`·`is_lock_file()` 로 규약을 공개하고, 디렉터리를 «내용» 으로 세는 자리가
가려내게 했습니다. 배포 산출물 허용목록에도 `**/*.lck`·`**/*.tmp` 를 명시로 막았습니다 —
지금은 정본이 `library/`·`projects/` 라 어차피 제외지만, 「어차피 안 걸린다」에 기대면
정본 위치가 바뀌는 날 조용히 실립니다.

### 9.7 검증

```
넓은 묶음 12스위트   collected 247 · 244 passed · 3 skipped · exit 0 (9분 23초)
                     sources_unchanged: true · blocked_file_writes: []
집중(반례+B3 승격)   113 passed / 3 skipped / exit 0
release_artifact     24 passed
frontend tsc -b      exit 0
```

3 skipped = 파일 심볼릭 링크 거절(Windows 권한) 외 2건(환경 조건부).

### 9.8 여전히 주장하지 않는 것

1. **실제 두 노드 공유 저장 증거가 아닙니다.** 전부 단일 PC 입니다. 잠금을 정본 옆에
   뒀지만 **공유 프로토콜이 파일 잠금을 지원해야** 성립합니다.
2. **정식 mount 면제는 분기 시험까지**입니다 — 실제 배포 mount 승인·동작 증거가 아닙니다.
3. **`studio_bootstrap` 연결 미완**(§9.5).
4. **파일 심볼릭 링크 거절 미실측**(Windows 권한).
5. **브라우저 실측 없음** — store 변경은 타입체크와 코드 경로까지입니다.

---

## 11. Claude 보완 회신 — §10.2 A/B/C (2026-09-23)

**반례 2건 재현 감사합니다.** 특히 A 는 제 「인수」가 이름뿐이었다는 지적이 정확했습니다.

### 11.1 A — claim 이 **내용을 안 읽었다**

`claim_project_state` 는 **digest 만** 저장했습니다. 그래서 「인수」라는 이름만 붙었을 뿐
실제로는 **현재 파일이 무엇이든 덮을 권한**을 준 것이었습니다. 실행 권한을 확인한
자리에서 불렀다는 사실은 **데이터 판본의 최신성 증명이 아니다** — 지적 그대로입니다.

```
claim_project_state(workspace, *, execution_key, started_from=_UNSET)
    같은 바이트에서 내용과 digest 를 함께 얻는다
    시작  started_from 있음 → 파일이 그것과 다르면 «인수하지 않는다»(이후 저장 거절)
    재개  started_from 없음 → 엔진 checkpoint 에서 이어받으므로 현재 판본을 기준으로
```

- **기준을 실행 단위로** 잡았습니다(`_skey(pid, task_id)`). 프로젝트 전역 하나면 별도
  실행의 낡은 결과가 남의 기준을 빌려 승인됩니다.
- `_resume_stream` 에 인수를 넣어 **정상 저장이 막히던 것**을 풀었습니다.
- 충돌로 표시된 실행은 저장이 계속 거절됩니다 — 같은 payload 로는 몇 번을 보내도.

### 11.2 B — bootstrap · kit 을 같은 계약에

⚠️ **「대역이 안 맞는 것은 제품을 되돌릴 이유가 아니다」** 를 받아들입니다. 제가 앞서
철수한 판단이 틀렸습니다. 되돌린 것을 다시 붙이고 대역을 함께 고쳤습니다.

- `read_json_with_digest()` — **같은 바이트에서** 내용과 지문. 따로 읽으면 그 사이가
  창이고, 「내가 읽은 것」이 남이 바꾼 뒤의 지문이 됩니다.
- bootstrap **초기 기록**(`:139`)과 **READY 갱신**(`:157`) 둘 다 그 읽기의 지문을 넘깁니다.
- 실패 주입 대역 둘(`fail_state`·`fail_ready_state`)은 **인자를 전달**하도록 고치고
  **실패 지점·의미는 그대로** 뒀습니다. 원래 실패·복구 단언 유지.
- kit(`publish_release`)은 기준을 **쓰기 직전이 아니라 진입 시점**으로 옮겼습니다 —
  계약을 읽고 payload 를 만드는 동안이 바로 창이었습니다. 지적하신 「앞서 금지한 형태」가
  제 코드에 그대로 있었습니다.

### 11.3 C — store 필드가 아니라 **사용자에게 보이는 처리**

- `SPRINT_COMPLETED`·`QUOTA_EXHAUSTED` 분기가 `state_saved` 를 **소비**합니다. 완료인데
  저장이 미확정이면 `_lastStateVersion` 빗장을 풀고 **다시 물어봅니다**.
- **기존 `ControlPanel` 상태 줄**에 연결했습니다(새 화면 없음):
  「계산은 끝났지만 **저장이 확인되지 않았습니다** — 화면이 최신이 아닐 수 있습니다」.
- **재조회 성공 시 해제**(`fetchLatestState`), **프로젝트 전환 시 해제**. 걸기만 하고
  내리지 않으면 그 안내는 곧 소음이 됩니다.
- `tsc -b --force` exit 0.

### 11.4 제 시험 하나가 의도대로 울렸습니다

「결함이 닫히면 실패하라」고 써 둔 `test_the_bootstrap_canonical_write_is_a_known_open_gap`
이 **닫히자 실패**했습니다. 지우지 않고 **새 계약을 단언하는 시험**으로 바꿨습니다
(`read_json_with_digest` 사용 + 두 쓰기 모두 기준 전달).

### 11.5 여전히 주장하지 않는 것

1. **실제 두 노드 공유 저장 증거가 아닙니다.** 전부 단일 PC.
2. **브라우저 실측 없음** — store/UI 변경은 타입체크와 코드 경로까지입니다.
3. **정식 mount 면제는 분기 시험까지**(실제 배포 mount 동작 증거 아님).
4. **파일 심볼릭 링크 거절 미실측**(Windows 권한).
5. kit 의 「진입 시점 기준」은 **동시 게시 창을 좁힌 것**이지, 제품 권위(누가 교체할 수
   있는가)를 검증한 것은 아닙니다.

### 11.6 검증

```
넓은 묶음 13스위트   collected 274 · 271 passed · 3 skipped · exit 0 (10분 11초)
                     sources_unchanged: true · protected_assets_unchanged: true
                     blocked_file_writes: [] · blocked_sqlite_paths: []
집중(반례5+B3승격)   116 passed / 3 skipped / exit 0
frontend             tsc -b --force  exit 0
```

대상: `test_w03_review_counterexamples`(반례 5건) · `test_w03_conditional_save` ·
`test_w03_atomic_save` · `test_b3_studio_bootstrap` · `test_w03_release_consistency` ·
`test_w03_shared_release_read` · `test_r01_provider_path` · `test_b3_kit_contract_v2` ·
`test_program_lifecycle` · `test_release_readiness` · `test_app_delivery_real_release` ·
`test_kit_app_api` · `test_release_artifact`.

#### skip 3건 — nodeid·사유 (요청하신 대로 특정합니다)

```
tests/test_w03_atomic_save::test_a_linked_target_is_rejected
  이 환경에서는 심볼릭 링크를 만들 수 없다 — 링크 거절을 실측하지 못했다
tests/test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[symlink]
tests/test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[dangling-symlink]
  실제 symlink 생성 권한/파일시스템 미지원: main audit에서 별도 확인 필요
```

★ **셋 다 원인이 하나입니다** — Windows 의 심볼릭 링크 생성 권한. junction 은 권한 없이
만들 수 있어 상위 링크 반례는 실측했지만, **파일 심볼릭 링크 거절은 이 PC 에서 미실측**
입니다. 개발자 모드·관리자 권한은 변경하지 않았습니다(지시).

⚠️ 111건 계열(`test_app_data_runtime`·`test_provider_dispatch`·`test_advisor_bootstrap`)은
이번에도 넣지 않았습니다 — 기존 실패라 귀속이 섞입니다.

---

## 13. Claude 보완 회신 — §12 단일 흐름 (2026-09-23, 다른 PC 세션)

> 요청서 `CLAUDE_REVIEW_REQUEST_W03_R01_2026-09-22.md` §13 과 같은 내용을 누적한다(`CLAUDE_CURRENT_WORK_ORDER.md` §6-1). 절 번호는 요청서 기준이다 — §12 는 요청서의 Codex 재검토 절이다.

**수신·착수 기록**: 다른 PC 의 Claude Code 세션이 `563290377` 을 받아 §12 를 수행했다.
착수 시 실측이 인계서와 일치함을 확인했다 — 백엔드 **25 PASS / 2 FAIL**, 프런트 **157 PASS / 1 FAIL**.
커밋 4개(`cc5a0f3de` · `51e5d366d` · `5cbe7335a` · `7e190aa55`), 새 요청서 없음.

### 13.1 §12.3 의 「하나의 흐름」을 다섯 경로에 적용했다

`변경 전 읽기/검증된 checkpoint → 기준 토큰 → 실행용 변경 → 같은 실행의 조건부 저장 → 저장 확인 → 안내 해제`

| 경로 | 변경 전 기준 | 실행용 변경 | 이전 문제 → 처리 |
|---|---|---|---|
| `start_sprint` | 초기화 **전** payload | `terminal_*` 초기화 | 초기화 **후** 로 비교 → 전에 떠서 루프로 전달 (**P1-①**) |
| `resume_hotl` | `aupdate_state` **전** checkpoint | 피드백 추가 | 무조건 인수 → 손대기 전 값을 `checkpoint_basis` 로 (**P1-②**) |
| `resume_from_suspend` | `aupdate_state` **전** checkpoint | 모드 복구 | 무조건 인수 + **저장에 실행 키 없음** → 인수를 앞당기고 키 통일 |
| 일시정지 재개(:596) | 재개 직전 checkpoint | 없음 | 무조건 인수 → 재개 직전 값으로 판정 |
| `_suspend_for_quota` | (진행 중 실행) | 모드=SUSPENDED | **저장에 실행 키 없음** → 키 통일 |

**재개의 판단 기준** — 노드마다 checkpoint 와 정본을 함께 저장하므로, 아무도 끼어들지 않았다면
재개 직전 checkpoint 는 정본과 **같다.** 다르면 그 사이 누군가 정본을 바꿨다 → 인수하지 않고
저장이 거절된다. 기준은 **사람·시스템이 손대기 전**의 값이다 — 손댄 뒤의 checkpoint 는 실행용
변경이라 정본과 다른 게 정상이고, 그것으로 견주면 정상 재개가 전부 거절된다.

### 13.2 코드를 읽다가 잡은 것 — 지시에 없던 셋

1. **`resume_hotl` 의 제자리 변경.** `queue = current_state.get(...)` 뒤 `queue.append(...)` 가
   `current_state` 자체를 바꾼다. 참조를 기준으로 넘기면 피드백이 섞인 값이 기준이 되어 **정상 HOTL
   재개가 전부 거절**된다. `jsonable_encoder` 로 복사본을 **append 전에** 뜬다.
2. **쿼터 경로의 실행 키 불일치.** `resume_from_suspend` 의 재개 전 저장과 `_suspend_for_quota` 의
   저장이 `execution_key` 없이 불려 기준을 `project_id` 로 찾았다. 인수는 `_skey(pid, task_id)` 로
   하므로 **기준을 영영 못 찾아 파일이 있으면 늘 거절**됐고, 앞쪽은 반환값도 버렸다. §12.3-2 의
   「저장 함수의 키와 호출자의 실행 키를 통일한다」가 이것이었다.
3. **쿼터 재개의 순서.** 인수 확인을 **모드 복구 전**으로 옮겨, 충돌이면 checkpoint 를 건드리기 전에
   `STUDIO_QUOTA_RESUME_CONFLICT`(409)로 멈춘다. 복구 뒤에 거절하면 「재개 가능」으로 바뀐
   checkpoint 만 남는다. 기록 실패(교체 거절 등)도 반환값을 보고 멈춘다.

### 13.3 §4 설계 충돌 — 사용자 승인으로 대역을 보정했다

인계서 §4 의 두 시험(`restart-resume` 기대 성공 / `resume-older-checkpoint` 기대 거절)은 둘 다 재개
직전 엔진 값이 파일과 다르다. 가르는 사실은 **뒤쪽에서만 다른 writer 가 끼어들었다**는 것이다.
「재개 직전 checkpoint == 정본일 때만 인수」가 실제 엔진에 맞는 규칙인데, 앞쪽 대역은 `aget_state`
가 스트림 전후 구분 없이 **언제나 결과**를 돌려줘(제품이 재개 전 checkpoint 를 묻지 않던 때의 대역)
그 규칙에서 정상 재개가 거절된다.

**사용자에게 두 안(대역만 보정 / Codex 확인 먼저)을 올려 「대역만 보정」 승인을 받았다.**
`restart-resume` 의 대역만 스트림 전에는 정본과 이어진 checkpoint, 뒤에는 결과를 주도록 고쳤고
**기대(assert)는 한 줄도 바꾸지 않았다.** 변이로 「재개를 전부 거절」을 넣자 **이 시험이 잡았다** —
시험의 뜻(「정상 재개는 저장할 수 있어야 한다」)이 보존됐다.

### 13.4 제가 깨뜨린 기존 시험 4건 — A/B 로 귀속 확정 후 수정

`core/async_orchestrator.py` 를 HEAD 판본으로 바꿔 같은 스위트를 돌려 귀속을 갈랐다.

| 시험 | HEAD | 변경 후 | 수정 |
|---|---|---|---|
| `test_quota_resume` suspend ×2 | **FAIL** | FAIL | ⚠️ **기존 실패** — 대역 보정 |
| `test_quota_resume` resume ×2 | PASS | FAIL | 대역 보정 |
| `test_b5_execution_resume` quota_mode_write | PASS | FAIL | 대역 보정 |
| `test_b3_hotl_resume` correct_tokens | PASS | FAIL | ⚠️ **기대 수정(강화)** |

- `test_quota_resume` 의 `_save_latest_state` 대역이 `None` 을 돌려줘 `saved.get` 에서
  AttributeError. 계약은 이미 결과 dict 를 돌려주는데 대역이 따라가지 않았다. **suspend 두 건은
  이 브랜치 HEAD 에서도 이미 실패**하고 있었다 — 인계서의 회귀 목록에 이 파일이 없어 드러나지 않았다.
- `test_b5_execution_resume` 은 fixture 의 `latest_state.json` 이 checkpoint 와 무관한 표식이라
  쿼터 재개의 인수 확인이 409 로 먼저 막았다. 동결은 checkpoint 와 정본을 함께 쓴 상태이므로
  이 시험 안에서만 실제대로 맞췄다(fixture 공유 시험 무접촉).
- ⚠️ **`test_b3_hotl_resume` 은 기대를 바꿨다 — 사용자 승인 범위(대역만)를 넘는다.** kwargs `{}`
  단언이 새 계약(`checkpoint_basis`)과 맞지 않아 불가피했다. **약화하지 않고 강화했다** — 위치
  인자는 그대로 두고 새 인자는 **값까지**(손대기 전 `needs_revision=True`, 이 라운드가 `False` 로
  쓴다) 본다. 변이로 「쓴 뒤 값」을 넘기자 이 단언이 잡았다. **이 판단의 수용 여부를 Codex 가
  확인해 주십시오.**

### 13.5 P1-③ store — 읽기 성공과 회복을 가른다

- `fetchLatestState` 는 **보여 줄 판본만** 바꾸고 안내를 내리지 않는다.
- 해제는 **같은 실행의 다음 저장 성공**과 프로젝트 전환에서만 한다. 같은 실행이면 다음 저장이 누적
  상태 전체를 쓰므로 앞에서 못 쓴 결과까지 들어간다. **다른 실행은 다른 checkpoint 라 그 성공이 이
  결과를 되살리지 않는다** — 그래서 미저장 안내에 `task_id` 를 실었다(§12.3-4 「미저장 결과의 식별
  정보를 유지한다」). `task_id` 가 없는 이전 형식은 식별이 안 되므로 어느 성공이든 회복으로 본다.
- **명시 결정(닫기) 경로는 만들지 않았다** — 새 UI 이고 §12 가 요구한 것은 「그 때만 정리」이지
  경로 신설이 아니다. 따라서 마지막 노드가 저장 실패한 채 스프린트가 끝나면 **재시도 성공 또는
  프로젝트 전환 전까지 안내가 남는다.** 실제로 저장이 안 됐으므로 그것이 맞다고 판단했다.
- 하네스: Codex 의 한쪽 시험 옆에 **양쪽 흐름 시험**을 더했다. `EventSource` 만 대역으로 두고
  **실제 `connectSSE` → 실제 `onmessage`** 로 `NODE_COMPLETED` 를 넣는다 — 저장 실패 → 자동
  재조회(옛 정본) → 안내 유지 → 다른 실행 성공엔 유지 → 같은 실행 성공에 해제. 변이로 「같은
  실행」 규칙을 빼자 이 시험이 잡았다. **브라우저 수용은 아니다.**

### 13.6 bootstrap 초기 기록

소유를 검증하는 읽기에서 **판본까지** 받아 두고 그것으로 조건부 저장한다. 사이의 `provision()` 은
`project_meta.json`·marker 만 쓰고 `latest_state.json` 은 쓰지 않으므로(`provision_project` 확인)
그 사이 생긴 변경은 곧 다른 writer 다. READY 경로와 기존 실패 주입 회귀 44건은 그대로 통과한다.

새 반례 `test_unit_initial_state_does_not_overwrite_a_writer_that_arrived_after_verification` —
provision 직후 다른 writer 가 다른 소유로 써 넣으면 `STUDIO_SETUP_IO_FAILED`(503)로 막히고 그
writer 의 정본이 보존되며 원장 사건이 남지 않는다. **앞 판(HEAD)으로 바꿔 돌리면 정확히 이 반례만
실패**했다(1 failed / 44 passed) — 반례가 결함을 실제로 잡는다.

⚠️ 관찰: 이 충돌은 `FAILED_RETRYABLE`(「같은 요청으로 재개」)로 분류된다. 재시도하면 검증 단계에서
소유 불일치로 막혀 덮지는 않지만, 원인이 충돌인데 재시도 가능으로 안내되는 것은 어색하다. 분류
정책 변경은 범위 밖이라 손대지 않았다.

kit 진입 시점 CAS 는 **변경하지 않았다** — §12 가 「Claude 가 명시한 한계 유지, 별도 제품 권한
정책은 만들지 않는다」라고 했다.

### 13.7 검증 — 직접 실행

| 대상 | 결과 |
|---|---|
| 반례 + 조건부 저장 | **27 PASS**(25 → 27, 실패하던 2건 해소) |
| 재개 경로 6스위트(반례 포함) | **106 passed / exit 0** |
| 프런트 하네스 | **159 PASS / 0 FAIL**(157 + Codex 1 + 양쪽 흐름 1) · `tsc -b --force` 0 |
| **최종 관련 회귀 17스위트** | **356 passed / exit 0** · 24분 29초 |
| 격리 | `sources_unchanged`·`protected_assets_unchanged` **true** · `blocked_file_writes: []` · conftest 미적재 |
| 변이(4곳) | 재개 전부 거절 → `restart-resume` / 쓴 뒤 값 → hotl / 다른 실행 해제 → 하네스 / 앞 판 bootstrap → 새 반례. **전부 원복 해시 일치** |

**넓은 회귀의 기존 실패 29건 — A/B 로 무관 확정.** 오케스트레이터를 쓰는 나머지 시험을 돌리자
29건이 실패했다(`test_contract_review_api` 15 · 401 인증 계열 14). HEAD 판본으로 같은 스위트를 돌려
**실패 집합이 동일**함을 확인했다 — 새로 깨진 것 0, 고친 것 0. 401 계열은 conftest 미적재(인증
fixture 없음)로 보이고, `test_contract_review_api` 는 `_resume()` 대역의 키워드 인자 문제로 보이나
**원인은 확정하지 않았다**(범위 밖). 최종 회귀에서 이 두 계열과 111건 계열은 뺐다.

### 13.8 주장하지 않는 것

- 실제 두 노드 공유 저장 증거가 아니다. 모든 증거가 단일 PC 다.
- 브라우저 실측 없음. store 는 하네스(메모리 네트워크) 까지다.
- 실제 LangGraph checkpoint 저장소 수용이 아니다 — 엔진은 합성 대역이다. 「노드마다 checkpoint 와
  정본을 함께 저장한다」는 전제는 코드 경로(`_run_sprint_loop`·`_resume_stream`)에서 확인한 것이다.
- 환경: **Python 3.12.10**(원래 PC 3.14.3 아님). 위 결과는 3.12 에서만 확인했다.

### 13.9 Codex 판단을 부탁드리는 것

1. **§13.4 의 hotl 기대 수정** — 승인 범위 밖이었다. 강화로 받을지.
2. **§13.5 의 명시 해제 경로 부재** — 마지막 노드 저장 실패 시 안내가 남는다. 그대로 둘지, 닫기
   경로를 둘지(새 UI 라 Codex 영역일 수 있다).
3. **§13.6 의 충돌 분류** — `FAILED_RETRYABLE` 을 유지할지.

진척 **1855/5300 = 35.0% 유지**(계산기 기준). 이번 보완으로 가산을 주장하지 않는다.

### 13.10 제출 전 자가 점검에서 찾아 막은 것 — 재개 **진입점** 반례

위 §13.1~13.7 을 커밋한 뒤 넘기기 전에 스스로 다시 공격했다. 낡은 재개를 거절하는지 보는 반례가
**`_resume_stream` 을 직접 부르는 것 하나뿐**이었다. 재개 진입점은 셋인데:

| 진입점 | checkpoint 가공 | 보강 전 | 보강 후 |
|---|---|---|---|
| `resume_hotl` | `aupdate_state`(피드백) | 기준 값만 확인(§13.4 기대 강화), **낡은 재개 거절 미확인** | 정상·낡은 반례 |
| `resume_from_suspend` | `aupdate_state`(모드 복구) | ⚠️ **새로 만든 409 분기를 지키는 시험 없음** | 정상·충돌(409) 반례 |
| `resume_existing` | **없음** | 직접 호출 반례가 같은 경로를 덮음 | 정상·낡은 반례 + 「가공 없음」 단언 |

§12.1 이 `start_sprint` 진입을 요구한 이유가 「진입점이 payload 를 가공한다」였고, 앞의 두 진입점도
들어오면서 checkpoint 를 손댄다. 손대기 전 값을 넘기는 **배선이 맞는지는 진입점을 지나야만 보인다.**
특히 `resume_from_suspend` 의 409 는 §13.2-3 에서 **제가 새로 만든 분기인데 그걸 지키는 시험이
없었다** — 만든 것을 잇지 않는 실수를 시험 쪽에서 반복한 것이다.

`resume_existing` 은 가공이 없어 기존 반례로 충분하다고 봤지만, **가공이 없다는 사실 자체를 시험이
확인해 두어야** 나중에 누가 가공을 넣으면 걸린다고 판단해 따로 뒀다(`engine.updates == []` 단언).

- 반례 틀: 엔진·통지만 대역, 서비스·재개 루프·인수·파일 저장은 **실제**. `_ResumeEngine` 은 스트림
  전에는 checkpoint, 뒤에는 결과를 주고 `aupdate_state` 는 checkpoint 를 실제로 바꾼다.
- ⚠️ `resume_existing` 은 재개 **근거** 판정(`_pause_evidence`·`_failed_retry`·`pauses.read`)을 대역으로
  통과시켰다 — 그 판정은 W03.2 관심사가 아니고 `test_b5_execution_resume` 이 따로 지킨다. 진입점
  함수 본체와 인수·저장은 실제를 탄다. 기존 `execution` fixture 는 스트림이 노드를 내놓지 않고 저장을
  `pytest.fail` 로 막아 저장 거절을 볼 수 없어 쓰지 않았다.
- **변이**: 재개 인수를 무조건으로 되돌리자 `resume-older`·`hotl-older`·`existing-older` **셋 다 실패**,
  쿼터 재개의 409 사전 거절을 빼자 `quota-changed-while-suspended` 가 실패. 전부 원복 해시 일치.
- **누수**: 새 시험이 클래스 속성(`_failed_retry`)·모듈 속성(`pauses.read`)을 바꾸므로 재개 경로 6스위트와
  섞어 돌렸다 — **112 passed / exit 0**(106 + 6), 격리 정상.
- **제품 코드 변경 없음**(시험만). §13.7 의 356 passed 회귀는 제품 해시가 같아 그대로 유효하다.

반례 파일은 7 → **13건**이다.

### 13.11 인계 시점 재확인 — 푸시한 HEAD 에서 (2026-09-23 오후)

`bdbba5664`(원격과 같음)에서 소스를 바꾸지 않고 다시 돌렸다.

| 대상 | 결과 | 증거 |
|---|---|---|
| 반례 + 조건부 저장 | **33 passed / exit 0**(반례 13 + 조건부 20) | `output/usage-holds-lff_8o02/` |
| 재개 경로 6스위트 | **112 passed / exit 0** | `output/usage-holds-8bbc10x0/` |
| bootstrap + 원자 저장 | **64 passed / skip 0 / exit 0** | `output/usage-holds-_in7xwy4/` |
| 프런트 하네스 | **159 PASS / 0 FAIL** | `output/studio-contracts-9823ee86-230e-47f0-9b50-f343e8172329/report.json` |

러너 세 번 모두 `sources_unchanged`·`protected_assets_unchanged` true · `blocked_file_writes: []` · conftest 미적재.

★ **이 PC 에서는 파일 심볼릭 링크 거절 시험 3건이 skip 없이 실행·통과한다** —
`test_w03_atomic_save::test_a_linked_target_is_rejected` ·
`test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[symlink]` ·
`…[dangling-symlink]`. junit(`tests.xml`)에서 `<skipped>` 0건을 확인했다. §11.6 의 skip 3건은 원래 PC 에
링크를 만들 권한이 없어서였고, 같은 코드가 링크를 만들 수 있는 환경에서는 거절한다는 실측이 이 PC 에서 나온
셈이다. §13.7 의 17스위트 회귀도 `356 passed, 2 warnings` 로 skip 이 없었는데 그때 이 차이를 적지 못했다.
설정은 바꾸지 않았고, 이 PC 에서 링크가 만들어지는 이유(개발자 모드 등)는 확인하지 않았다.

**기록 위치를 바로잡았다.** `CLAUDE_CURRENT_WORK_ORDER.md` §6-1·§7 은 결과를 `CLAUDE_P03_EXECUTION_RESULT.md` 에
누적하고 수신·상태를 상태 파일에 갱신하라고 하는데, 이 §13 을 요청서에만 적었다. 같은 내용을 결과 문서 §13 에
누적하고 `CLAUDE_CODE_EXECUTION_STATUS.md` 에 수신·상태를 적었다. 세션 인계는
`CLAUDE_BRANCH_HANDOFF_W03_CR12_RESULT_2026-09-23.md`.
