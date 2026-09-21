# 기동 DDL 16곳을 설치 단계로 — **조사와 최소 분리안**

작성: Claude Code · 2026-09-21 KST. **조사다 — 코드를 만들지 않았다.**
운영 DB 무접촉 · 클라우드 미배포 · 커밋·푸시 없음. 전체 **21/40=52.5%** 마지막 인정치 유지.

## 1. 현상

```
ALTER TABLE ADD COLUMN  16곳 / 13모듈   (기준선 9곳 → 현재 16곳)
CREATE TABLE IF NOT EXISTS · CREATE [UNIQUE] INDEX  각 store 의 _init/_connect 안
설치 진입점             «없다» — 스키마를 만드는 주체가 「먼저 쓰는 요청」이다
```

`run.py::_apply_installation_settings` 는 **설치 설정**(인스턴스·테넌트)이지 스키마가 아니다.

| 모듈 | 자리 |
|---|---|
| `advisor_store` · `agent_assets` · `app_data_store` · `auth` | 각 1 |
| `data_preparation/store` | **3** (`dataset_snapshots` 2 · `object_scope_index` 1) |
| `decision_case` | **2** (`evidence_basis` · `record_purpose`) |
| `enterprise_context/repository` · `external_intelligence/acquisition_store` · `master_data` · `planning_model` · `release_readiness` | 각 1 |
| `org_directory` | **2** (`departments` · `users`) |

## 2. 왜 이것이 무중단 배포의 **직접적 차단 조건**인가

1. **인스턴스가 둘 이상이면 같은 DDL 이 동시에 돈다.** `IF NOT EXISTS` 가 경쟁을 줄이지만
   PostgreSQL 의 DDL 은 잠금을 잡는다 — 기동 중 잠금 대기·교착이 곧 기동 실패다.
2. **Blue/Green 에서 새 버전이 켜지는 순간 옛 버전이 모르는 열이 생긴다.** 롤백해도 그 열은
   남는다. 즉 **스키마 변경이 코드 롤백을 따라오지 않는다** — 구/신 호환이 기본이라는
   배포 정본과 정면으로 부딪힌다.
3. **`executescript()` 는 조기 커밋**을 낸다(감싼 트랜잭션을 끊는다). 중간에 죽으면
   **반쪽만 적용된 스키마**가 남고, 다음 기동은 그 위에서 또 `IF NOT EXISTS` 를 돈다.
4. 기동 경로가 스키마를 만드는 한, **「스키마를 언제 누가 바꿨는가」에 답할 수 없다.**

## 3. 최소 분리안 (제안 — 구현하지 않았다)

한 번에 13모듈의 DDL 을 들어내지 않는다. **문을 하나 만들고 기본은 지금 그대로** 둔다.

```
① core/db 에 «스키마를 누가 관리하는가» 한 줄
      schema_is_managed()  ← 환경변수. 기본 False = 지금 동작 그대로

② 각 store 의 DDL 블록을 그 문으로 감싼다        13곳에 «한 줄씩», SQL 이동 0
      if not schema_is_managed():
          <기존 DDL 그대로>

③ 설치 커맨드 하나 (신규)                        제품 기동 경로 «밖»
      SQLite → 기존 `_DDL` 재사용
      PostgreSQL → core/db/schema/*.sql

④ 배포 순서                                      스키마 설치 → 새 버전 기동
```

* **되돌리기 쉽다** — 문을 닫으면(기본값) 오늘과 한 글자도 다르지 않다.
* **SQL 을 옮기지 않는다** — 옮기는 순간 두 벌이 되고 한쪽만 고쳐진다.
* 시험: 문이 열린 상태로 store 를 만들면 **DDL 을 돌지 않는다**(그리고 표가 없으면
  정직하게 실패한다 — 조용히 만들지 않는다) / 문이 닫히면 지금과 같다.

## 4. 분리 전에 **정해야 하는** 것 두 가지

### ① 열 추가 규칙 — 구 버전 호환

지금 ALTER 들은 `NOT NULL DEFAULT ''` 를 쓴다. Blue/Green 에서 옛 버전은 그 열을 모르고
INSERT 한다 — **기본값이 없으면 옛 버전의 쓰기가 죽는다.** 반대로 기본값을 주면 큰 표에서
PostgreSQL 이 재작성을 할 수 있다(버전에 따라 다르다).
→ 「새 열은 NULL 허용 또는 DEFAULT 필수」를 **스키마 리뷰 규칙**으로 둘지 정해야 한다.

### ② `julianday()` 트리거 — 옮기면 **동작이 바뀐다**

`core/data_preparation/ownership_binding.py` 의 기간 겹침 방지 트리거가 SQLite 함수를 쓴다.
PostgreSQL 에는 없고 `tstzrange` + 배제 제약으로 옮겨야 한다.
**그것은 이관이 아니라 제약의 재작성**이다 — 같은 것을 막는지 따로 증명해야 하고,
승인 없이 바꾸지 않는다. **배포 차단 항목으로 남긴다.**

## 5. 이번에 하지 않은 것

- 코드·스키마·설치 커맨드를 **만들지 않았다**(지시: 조사).
- 13모듈의 DDL 을 건드리지 않았다. 운영 DB 를 열지 않았다.
- `julianday` 트리거·부분 인덱스를 바꾸지 않았다.

## 6. 다음

| 항목 | 예상 | 선행 |
|---|---:|---|
| ①②③ 문 + 13곳 감싸기 + 설치 커맨드 | 60~90분 | §4-① 규칙 결정 |
| SQLite 로 문 열고 닫아 동등성 검사 | 20~30분 | 위 |
| PostgreSQL 실제 설치·대사 | — | **DSN** |
| `julianday` 트리거 재작성 | — | **승인** |
