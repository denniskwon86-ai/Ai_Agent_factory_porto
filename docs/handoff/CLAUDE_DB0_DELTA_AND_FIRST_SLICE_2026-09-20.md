# DB-0 차이 지도 · DB-1 첫 수직 경로 — **조사**

작성: Claude Code · 2026-09-21 KST. 지시: `CODEX_REVIEW_B_AND_DB_START_2026-09-20.md` §3.
**이 문서는 조사다 — 코드·스키마·DSN 을 만들지 않았다.**
원본 DB **읽기 전용**(`scripts/sqlite_inventory.py`, `--write` 없이 실행). 제품 기동·seed·DDL 0.
값·토큰·실자료 원문은 싣지 않는다. 전체 **21/40=52.5%** 마지막 인정치 유지.

---

## 1. 기준선 대비 차이 (실측 2026-09-21)

`docs/architecture/SQLITE_INVENTORY.md` 는 **봉인된 기준선**이며 아래 수치로 덮어쓰지 않았다.

```
기준선  파일 18 · 표 71 · 기동 시 열 추가  9곳
현재    파일 20 · 표 95 · 기동 시 열 추가 16곳
```

| 변화 | 내용 |
|---|---|
| **새 파일 2** | `app_data_preview.db`(표 4) · `policy_shadow.db`(표 2) |
| 사라진 파일 | 없음 |
| **표 증가 +24** | `external_intelligence.db` 4→12 · `enterprise_context.db` 12→16 · `data_preparation.db` 9→11 · `app_data.db` 2→4 · `planning.db` 8→10 (나머지는 새 파일 6) |
| **기동 DDL +7** | 9곳 → 16곳. 「표를 만들고 열을 늘리는 일이 **제품 기동 중에** 일어난다」가 더 늘었다 |

### 성격 구분

| 성격 | 파일 |
|---|---|
| **업무 정본** | `enterprise_context.db`(테넌트·조직) · `auth.db`(주체·세션) · `data_preparation.db` · `decision_ledger.db` · `planning.db` · `program_lifecycle.db` · `workspace.db` · `collaboration.db` · `ontology.db` · `external_intelligence.db` · `advisor.db` · `app_data.db` · `asset_usage.db` · `connectors.db` |
| **캐시/파생** | `llm_cache.db`(9.8MB) · `mcp_cache.db` · `app_data_preview.db`(Preview 사본) · `policy_shadow.db` · `shadow_runs.db` |
| **빈 껍데기** | `knowledge.db` — 0바이트·표 0·**코드에서 이름을 찾지 못함**. 이관 대상에서 빼고 삭제 여부는 별도 결정 |

★ **DB 밖에 있는 정본도 있다** — 이관 계획이 DB 만 보면 절반을 놓친다.

```
프로젝트 상태·WBS   projects/<project_id>/latest_state.json  등 파일
릴리스 본문         library/<release_id>/release.json        ← 파일
릴리스 «상태»       program_lifecycle.db                     ← DB
릴리스 승격         workspace.db                             ← DB(별도 표)
```

⚠️ **릴리스는 본문(파일)과 상태(DB)가 갈라져 있고 그 둘을 묶는 트랜잭션이 없다.**
이관에서 가장 먼저 부딪힐 경계다.

## 2. 주체·세션·문맥·영수증·릴리스의 저장 위치와 결속

| 것 | 저장소 | 표/파일 | 쓰기 결속 |
|---|---|---|---|
| 자격증명·주체 | `auth.db` | `auth_credential` | — |
| 세션 | `auth.db` | `auth_session` | 조회는 헤더 토큰 기준 |
| **SSE 티켓** | `auth.db` | `auth_sse_ticket` | **원자적 1회 소비 이미 구현** (아래 §3) |
| 테넌트·조직 문맥 | `enterprise_context.db` | `tenants`, `organization_nodes`, `organization_edges`, `organization_node_code_aliases` | — |
| **명령 영수증** | **`advisor.db`**(AdvisorStore 연결 공유) | `studio_execution_commands` | `CREATE TABLE IF NOT EXISTS` 로 **최초 사용 시** 생성 — 운영본 측정에는 **아직 없었다** |
| 제작 작업 상태 | **파일** | `projects/<id>/latest_state.json` 등 | 트랜잭션 없음 |
| 릴리스 본문 | **파일** | `library/<id>/release.json` | 트랜잭션 없음 |
| 릴리스 상태·이력 | `program_lifecycle.db` | `program_status`, `program_status_history` | **이번에 `BEGIN IMMEDIATE` + CAS 로 묶음**(R3) |
| 승격·준비도 | `workspace.db` | 4표 | 별도 |

★ 영수증이 상담용 `advisor.db` 안에 얹혀 있는 것은 이관 시 **경계를 다시 그어야 할 지점**이다
(상담 자료와 실행 영수증은 수명·소유·삭제 정책이 다르다).

## 3. 첫 수직 경로 — **로그인/문맥 → 세션 조회 → SSE 티켓 1회 소비** (권고 유지)

지시가 제안한 경로를 그대로 첫 슬라이스로 둔다. **더 작은 대안을 찾지 못했다** —
이 경로가 가장 작으면서도 「동시성이 실제로 걸리는」 곳을 포함한다.

### 이미 맞게 되어 있는 것 (이관에서 **잃으면 안 되는** 계약)

```python
UPDATE auth_sse_ticket SET consumed_at=?
 WHERE token_hash=? AND consumed_at='' AND expires_at>=? AND audience=?
# rowcount != 1 이면 실패 — 「읽고 확인하고 쓰기」로 나누면 두 요청이 같은 표로 붙는다
```

* 실패 사유를 **나누지 않는다**(없음·만료·이미 씀 모두 빈 결과) — 존재 누설 방지.
* 티켓에 **발급 시점 문맥**(tenant·scope·entity_mode)을 묶어 두고 소비 때 함께 돌려준다.
  구독 뒤에 화면이 문맥을 바꿔 신고할 수 없게 하는 통제다.
* ⚠️ 코드에 `self._lock`(인프로세스)이 함께 있으나 **원자성은 단일 UPDATE 가 진다.**
  PostgreSQL·다중 인스턴스에서는 `_lock` 이 아무것도 보장하지 않으므로 **UPDATE 조건절이
  그대로 옮겨져야 한다.**

### 이 슬라이스가 필요로 하는 정본 (auth 표만 옮기면 안 된다)

```
auth.db               auth_credential · auth_session · auth_sse_ticket
enterprise_context.db tenants · organization_nodes · organization_edges
                      · organization_node_code_aliases
```
문맥 확인이 조직 계층을 타므로 **조직 정본이 같이 가야** 로그인 후 화면이 성립한다.

## 4. PostgreSQL 첫 adapter — 수정 파일 목록과 검사 계획 (**아직 만들지 않음**)

| 대상 | 예상 작업 |
|---|---|
| `core/auth.py` | 연결 획득을 주입 가능하게. SQL 은 유지하되 파라미터 스타일(`?`→`%s`)과 `BEGIN IMMEDIATE` 대응 분기 |
| `core/enterprise_context/repository.py` | 같은 방식 |
| 신규 `core/db/` (가칭) | 연결 팩토리 · 방언 차이(UPSERT·파라미터·트랜잭션) 한 곳 |
| 신규 스키마/마이그레이션 | 위 7표. **기동 중 DDL 을 옮겨 심지 않는다** — 설치 단계로 분리 |

검사 계획: 빈 DB 설치 → 사본 대사(행 수·키) → 권한 거절 → **동시 티켓 소비**(두 요청 중 정확히
하나만 성공) → 복구. 예상 **90~150분**(코드 작성 60~90 + 검사 30~60). 추정이며 약속이 아니다.

⚠️ **PostgreSQL 실행 환경이 없다.** DSN·도구가 준비되지 않았으므로 로컬 코드와 합성 검증까지만
진행한다. 클라우드 생성·실자료 이전은 승인 대상이며 추정하지 않는다.
`scripts/data_migration.py` 는 PostgreSQL 이관 도구가 아니므로 **실행하지 않았다.**

## 5. 첫 경로 완료 ≠ 전체 이관 — 남는 필수 항목

```
큐/lease/fencing        제작 작업 실행권. 지금은 단일 프로세스 가정
durable SSE 이벤트      현재 이벤트는 메모리 경유 — 인스턴스가 늘면 유실·중복
파일 저장               릴리스 본문·프로젝트 상태가 로컬 파일. 공유 저장소 필요
기동 DDL/seed 제거      16곳. 다중 인스턴스에서 동시에 도는 DDL 은 사고의 씨앗
릴리스 본문↔상태 트랜잭션  파일과 DB 가 갈라져 있다(§1)
```

## 6. 다음 묶음

| 작업 | 담당 | 예상 | 결정이 필요한 것 |
|---|---|---:|---|
| 첫 슬라이스 adapter·스키마·집중 시험 | Claude | 90~150분 | PostgreSQL DSN 준비 여부 |
| 일반 `status` 경로 차단 | Claude | 20~30분 | **승격 근거의 정의**(배포 차단 항목) |
| 재개 제품 HTTP 재확인 | Claude | 5분 | 격리 로그인 |
