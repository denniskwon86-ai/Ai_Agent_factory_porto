# DB-1 첫 adapter — 방언 흡수 계층 · 설치 스키마 · 계약 시험

작성: Claude Code · 2026-09-21 KST. 지시: `CODEX_REVIEW_B_AND_DB_START_2026-09-20.md` §3.
**커밋·푸시 없음 · 클라우드 미배포 · 운영 DB 무접촉 · LLM 0.**
전체 **21/40=52.5%** 마지막 인정치 유지.

> ⚠️⚠️ **PostgreSQL 서버는 없다.** 아래 PG 경로는 **한 번도 실행되지 않았다.**
> 잠근 것은 번역 정확성·기본값 불변·1회 소비 계약 셋뿐이고, 「PostgreSQL 에서 된다」는
> 증거가 아니다. `scripts/data_migration.py` 는 실행하지 않았다.

## 만든 파일

| 파일 | 무엇 |
|---|---|
| `core/db/__init__.py` (신규) | 방언 한 곳 — 자리표시자 번역 · 연결 팩토리 · 번역 wrapper |
| `core/db/schema/001_auth_and_context.sql` (신규) | 첫 슬라이스 7표의 **설치** DDL (기동 DDL 아님) |
| `tests/test_db_adapter_first_slice.py` (신규) | 13건 |
| `core/auth.py` | **주입점 한 곳만** — `AuthStore(db_path, connect=None)`. SQL 무변경 |

## 설계에서 일부러 하지 않은 것

* **기존 SQL 을 고치지 않았다.** store 는 `?` 를 그대로 쓰고, 연결 wrapper 가 실행 직전에
  옮긴다. 로그인 경로의 SQL 을 손으로 다시 쓰는 것이 이관의 첫 걸음에서 가장 위험하다.
* **기동 중 DDL 을 옮겨 심지 않았다.** 스키마는 설치 산출물이고, 제품 코드가 그 파일을
  읽지 않는 것을 시험으로 잠갔다.
* **기본값은 지금 그대로 SQLite.** 설정을 주지 않으면 동작이 한 글자도 달라지지 않는다.
* DB-API 전체를 흉내 내지 않았다 — 흉내 내기 시작하면 그것이 두 번째 드라이버가 된다.

## 조용한 실패를 막은 두 곳

```
AFS_DB_BACKEND 오타       → 값 오류로 «거절». SQLite 로 조용히 돌아가지 않는다
PostgreSQL 인데 DSN 없음  → RuntimeError 로 «멈춘다». 접속 정보 값은 메시지에 싣지 않는다
```

⚠️ 조용히 SQLite 로 떨어지면 「PG 로 돌고 있다」고 믿는 채 파일 DB 에 쓰게 되고,
그 사고는 한참 뒤에야 발견된다.

## 번역이 단순 치환이면 안 되는 이유

```
SELECT * FROM t WHERE note='왜?' AND id=?     ← 리터럴 안의 ? 까지 바꾸면 파라미터 수가 어긋난다
SELECT * FROM t WHERE n LIKE '%수%' AND id=?  ← psycopg format 에서 % 는 자리표시자로 읽힌다
```
리터럴을 추적하며 옮기고 `%` 는 `%%` 로 escape 한다. 겹따옴표 escape(`''`)도 처리한다.

## 시험 13건 (격리 러너)

```
번역   기본 치환 · 리터럴 안 ? 보존 · '' escape · % escape · SQLite 는 «변환하지 않음»
기본값 설정 없으면 SQLite · 모르는 값은 거절 · 연결이 그냥 sqlite3.Connection
       PostgreSQL + DSN 없음 → 거절(값 비노출)
계약   1회 소비: 첫 UPDATE rowcount 1 · 두 번째 0
       ★ 음성 대조: 만료·다른 청중은 통과하지 않는다(늘 1이 아님을 보인다)
       ★ 두 스레드 동시 소비 → 정확히 하나만 성공 (응용 lock 없이)
설치   스키마에 7표가 모두 있고, 제품 코드가 그 파일을 기동 중에 읽지 않는다
```

### 극성 — 세 변이가 각각 물린다

```
① 단순 replace 로 번역            3 failed / 10 passed
② 모르는 backend 를 SQLite 로     1 failed / 12 passed
③ DSN 없으면 SQLite 로 떨어짐     1 failed / 12 passed      전부 원복 해시 일치
```

### 회귀 — 로그인·SSE 경로 무변경

```
test_auth_password_verify 14 · test_auth_self_display_name 7 · test_sse_org_isolation 14
= 35 passed  (주입점 추가 뒤에도 그대로)
```

## 스키마에서 드러난 **이관 대사 항목** 하나

SQLite 는 `consumed_at TEXT NOT NULL DEFAULT ''`(빈 문자열 = 미사용)이고 PostgreSQL 판은
`TIMESTAMPTZ NULL` 이다. 「없음」을 빈 문자열로 두면 타입이 시간이 아니게 되기 때문이다.

⚠️ 따라서 **이관 도구가 `'' → NULL` 을 옮겨야 하고, 응용의 조건절도 그에 맞춰야 한다**
(`consumed_at=''` → `consumed_at IS NULL`). 이 한 줄이 어긋나면 **모든 티켓이 이미 쓴
것으로 보이거나 반대로 무한히 재사용된다.** 대사 검사의 첫 항목으로 둔다.

## 후속 — 주입점 확장 (2026-09-21)

첫 슬라이스의 나머지 절반과, **내가 어제 넣은 방언 의존**을 정리했다.

| 파일 | 무엇 |
|---|---|
| `core/enterprise_context/repository.py` | 같은 모양의 `connect=None` 주입점. SQL·DDL 무변경 |
| `core/program_lifecycle.py` | `connect=None` + **`begin_immediate` 주입** |

### ⚠️ `BEGIN IMMEDIATE` 는 SQLite 전용 문장이다

R3 에서 내가 넣은 `conn.execute("BEGIN IMMEDIATE")` 는 **PostgreSQL 에 없는 문장**이다.
문자열로 박아 두면 이관할 때 이 한 줄이 조용히 남아 터진다 — 방언 상수로 바꿨다.
쓰기 잠금을 먼저 잡는 «같은 효과» 를 PG 에서 어떻게 낼지(직렬화 수준 / `FOR UPDATE`)는
저장소마다 다르므로 **부르는 쪽이 준다.**

### ⚠️ 주입이 부트스트랩을 건너뛰게 만들 뻔했다

처음 판은 주입된 연결을 **바로 돌려줬고**, 그 바람에 DDL 부트스트랩을 지나치지 않아
`no such table: program_status` 가 났다. 시험이 그 자리에서 잡았다.
**주입은 「연결을 어디서 얻는가」만 바꾸는 것이지 준비 절차를 건너뛰는 문이 아니다.**

### 시험 (13 → 20건)

```
세 저장소가 «같은 이름·같은 기본값» 의 주입점을 갖는다        (모양이 갈리면 각자 다르게 고쳐진다)
주입한 factory 가 «실제로 불린다»                            (인자를 받는 것과 쓰는 것은 다르다)
program_lifecycle 이 주입한 트랜잭션 시작 문장을 쓴다
  · 그리고 "BEGIN IMMEDIATE" 가 더 이상 박혀 있지 않다
```

### 극성 — 네 변이가 각각 물린다

```
① program_lifecycle 주입점 제거   3 failed / 17 passed
② BEGIN 을 다시 박음              1 failed / 19 passed
③ Ecm 주입을 무시                 1 failed / 19 passed
④ Auth 주입을 무시                1 failed / 19 passed      전부 원복 해시 일치
```

### 회귀 — 95건 무변경

```
db_adapter 20 · program_lifecycle 22 · reactivate 13 · program_usable 4
auth_password 14 · sse_org_isolation 14 · release_item_visibility 8
```

---

## 남은 것 / 다음

| 항목 | 상태 |
|---|---|
| 빈 DB 설치 · 사본 대사 · 권한 거절 · 복구 검사 | **DSN 준비 후** — 지금은 실행 불가 |
| store 의 SQL 을 PG 에서 실제로 돌려 보기 | 미실행 |
| 큐/lease/fencing · durable SSE · 파일 저장 · 기동 DDL 제거 | 후속 필수 잔여 |
| 일반 `status` 경로 차단 | 배포 차단 표시 · 승격 근거 정의 대기 |
| 재개 제품 HTTP 재확인 | 격리 로그인 대기(5분) |

**첫 경로 완료와 전체 이관 완료는 다르다.** 이번 것은 「방언을 한 곳에 모으고, 잃으면
안 되는 계약을 시험으로 못박았다」까지다.
