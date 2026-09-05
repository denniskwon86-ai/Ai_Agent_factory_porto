# 격리 공백 — **시험이 운영 결정 안건을 만들고 있었다**

작성: Claude Code (백엔드) · 2026-08-23
**상태: 원인 확정 · 격리·감시 보정 완료 · 기존 오염 행은 손대지 않았다(정리는 별도 승인).**

> **한 줄로** — 시험이 운영 `data/collaboration.db` 에 결정 안건 **237행**을 만들었다.
> 그리고 그동안 불변식 검사기는 **「운영 데이터 영역이 회귀 전과 같습니다」라고 초록**을
> 냈다 — 그 파일을 안 보고 있었기 때문이다.

---

## 1. 무엇이 오염됐나

```
data/collaboration.db
  decision_cases         253행   ← owner@afs.invalid 237 · runner@afs.invalid 12 · hikwon@lsmnm.com 4
  decision_participants  257행
  publications            76행
  publication_versions    76행
  publication_reviews      4행
  publication_distributions 2행
  decision_actions         2행

가장 오래된 행  2026-08-03T15:21:36
가장 최근 행    2026-08-23T02:48:02
```

가장 최근 세 건의 제목이 결정적이다:

```
지연 영향 — 근거 안건(숫자 없음)
지연 영향(fp_b)
지연 영향(fp_a)
```

**`tests/test_ontology_path_adapter.py` 가 만든 것이다.** `owner@afs.invalid` 는 그
시험이 쓰는 계정이다.

`data/llm_cache.db` 도 회귀 중에 바뀌었다(`core/cache_manager` 가 import 시점에 파일을
만들었다).

---

## 2. ⚠️⚠️ 왜 아무도 못 봤나 — 통제 셋이 **같은 자리**를 비워 뒀다

**① `tests/conftest.py` 가 협업 저장소를 격리하지 않았다.** 격리 목록에 한 줄도 없었다.

**② 시험이 «제품 싱글턴을 쓴다»는 판단만 하고 격리를 확인하지 않았다.** 충실도를 위해
`decision_case` 싱글턴을 쓴 것은 옳지만, 그 싱글턴이 어디를 가리키는지 보지 않았다.

**③ `scripts/check_operational_invariants.py` 가 그 파일을 감시하지 않았다.**
`WATCH` 에 `collaboration.db` 가 없었다. 그래서 검사기는 **오염이 일어나는 동안 초록**
이었다.

★ 통제가 셋이어도 **같은 자리를 비워 두면 0 이다.**

### 2.1 이미 적혀 있던 경고

`tests/conftest.py` 의 바로 그 자리에 이런 주석이 있었다:

> ⚠️ 결정 원장은 격리 목록에 없어서 11,633행이 오염됐다. 새 저장소를 만들 때 격리를
> 나중으로 미루면 같은 일이 반복된다 — 목록에 넣는 것이 저장소를 만드는 일의 일부다.

**같은 일이 반복됐다.** 경고를 적는 것과 목록에 넣는 것은 다른 일이다.

---

## 3. 고친 것

### 3.1 격리 (`tests/conftest.py`)

```
collaboration_store   모듈 기본값 + 전역 싱글턴 두 곳
paths.DATA_DIR        뿌리 자체를 임시 폴더로 — import 시점에 파일을 만드는 곳까지 따라오게
```

### 3.2 감시 (`scripts/check_operational_invariants.py`)

```
WATCH            + collaboration.db(+wal/shm) · llm_cache.db
TABLES           + decision_cases · publications · publication_versions
PROTECTED_ROWS   + 위 셋 (행이 하나라도 늘거나 줄면 실패)
```

### 3.3 캐시의 import 부작용 (`core/cache_manager.py`)

`_init_db()` 를 **import 시점에 한 번만** 부르고 있었다. 뿌리를 돌리면 표가 없는 DB 를
열게 되어 회귀가 `no such table: exact_cache` 로 멈췄다.

★ 열 때마다 `CREATE TABLE IF NOT EXISTS` 로 보장한다. 「한 번만 만들면 된다」는 **뿌리가
절대 안 바뀐다**는 가정 위에 서 있었고, 그 가정은 격리를 넣는 순간 깨진다.
★ 그리고 이제 **import 만으로는 파일이 생기지 않는다**(실측 확인).

---

## 4. 실측

```
같은 시험 44건 재실행
  data/collaboration.db  581,632B  ad3754f4d33e98e7  →  동일
  data/llm_cache.db    2,142,208B  362e5def32c7c475  →  동일

import 부작용 검사
  paths.DATA_DIR 를 빈 폴더로 돌리고 core.cache_manager import  →  폴더 없음(파일 0)
  쓰기 뒤에만 llm_cache.db 생성 · 읽기 정상
```

---

## 5. ⚠️ 손대지 않은 것 — 기존 오염 행

**253행·76행을 지우지 않았다.**

「아무것도 지우지 말고 상태를 기록하라」는 규칙대로다 — 지우면 증거가 사라지고, 같은 일이
또 나도 처음처럼 보인다. **정리는 별도 승인 사항**이다.

정리할 때 판단이 필요한 것:

1. `owner@afs.invalid`·`runner@afs.invalid` 행(249건)은 명백히 시험 산출물이다
2. `hikwon@lsmnm.com` 4건은 **사람이 화면에서 만든 것일 수 있다** — 먼저 확인해야 한다
3. `decision_participants`·`publication_*` 는 위 행들에 딸린 것이므로 함께 봐야 한다
4. 지우기 전에 **사본과 지문을 보관**한다(G7-2 Lite 와 같은 규칙)

---

## 6. 남은 위험

### 6.1 오염 범위는 **두 파일로 한정**된다 (실측)

회귀 두 번(11:32~11:41 · 11:42~11:51) 창 안에서 바뀐 운영 파일은 `collaboration.db` 와
`llm_cache.db` 뿐이다. 같은 날 mtime 이 움직인 `asset_usage.db`(11:03)·
`program_lifecycle.db`(10:24) 는 **회귀 창 밖**이고, 행도 늘지 않았다
(`asset_usage` 18행 · 최근 행 `2026-08-08`) — 읽기 흔적이다.

★ mtime 만으로 판정하지 않는다. **행 수와 시각을 함께** 봐야 「읽었다」와 「썼다」가
갈린다.

### 6.2 그래도 남는 위험

⚠️ 이번에 찾은 것은 **감시 목록에 없던 두 파일**이다. 다른 저장소도 같은 상태일 수 있다.

지금 감시하는 것: `ontology` · `data_preparation` · `decision_ledger` ·
`enterprise_context` · `collaboration` · `llm_cache` · `app_data` ·
`app_data_preview` · `program_lifecycle`.

`data/` 에 있는 것 중 **감시 밖**: `advisor` · `asset_usage` · `auth` · `connectors` ·
`external_intelligence` · `knowledge` · `mcp_cache` · `planning` · `shadow_runs` ·
`workspace`.

★ 다음에 할 일로 남긴다 — **열거 방식은 새 저장소가 생길 때 조용히 샌다.** 뿌리
하나(`paths.DATA_DIR`)를 돌리는 격리가 근본이고, 감시는 그것이 통하는지 확인하는
두 번째 겹이다.
