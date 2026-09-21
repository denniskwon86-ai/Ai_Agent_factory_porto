# Codex 검토 인계 — 2026-09-21 · 재개 마감 + DB-0/DB-1 + 기동 DDL

작성: Claude Code · 2026-09-21 KST. **푸시 없음.** 기준 HEAD `c9623f286`.
**전체 21/40=52.5% · 로컬 18/28=64.3% 마지막 인정치 유지.**
지시: `CODEX_REVIEW_B_AND_DB_START_2026-09-20.md` §2·§3 — **전부 마쳤습니다.**
`CODEX_DEPLOYMENT_PREP_PACKET_2026-09-21.md` **수신·반영**(§4 에 경계 합침).

---

## 0. 읽는 순서

| 순서 | 문서 | 성격 |
|---|---|---|
| 1 | `CLAUDE_REACTIVATE_R1R2R3_2026-09-21.md` | 지적 3건 수용·수정 · 일반 `status` 배포 차단 |
| 2 | `CLAUDE_DB0_DELTA_AND_FIRST_SLICE_2026-09-20.md` | 차이 지도 · 첫 수직 경로(조사) |
| 3 | `CLAUDE_DB1_FIRST_ADAPTER_2026-09-21.md` | 첫 adapter + **후속 주입점 확장** |
| 4 | `CLAUDE_DB0_BOOT_DDL_SEPARATION_2026-09-21.md` | 기동 DDL 16곳(조사) — **결정 2건 대기** |

---

## 1. 재개 — 지적 3건 모두 **제 코드의 실제 결함**이었습니다

| # | 무엇이었나 | 고친 것 |
|---|---|---|
| R1 | 앞선 「중단 아니면 ACTIVE」가 **같은 구멍을 다시 열었다** | 중단이 아니면 **상태·지문·대체 대상 불변 반환**(`restored: False`). 복원 안 했으면 **말하지도 않는다**. `deprecated` 경고 해제도 이 명령에서 안 함 |
| R2 | 지문을 「이력 전체의 마지막 비어있지 않은 값」에서 골랐다 | **중단 직전 그 한 행**에서 상태·지문·대체 대상을 통째로. **빈 값도 값** |
| R3 | 읽기·쓰기가 별도 트랜잭션 | `BEGIN IMMEDIATE` 로 잠그고 직전 상태를 **트랜잭션 안에서** 읽음 + `expected_status` CAS |

```
집중 시험 13 passed (7→13) · 회귀 48 · 극성 3종 각각 물림
R1 을 고치자 「종전 동작 유지」를 고정하던 제 기존 시험이 빨강이 됐고, 지시대로 계약에 맞게 다시 썼습니다.
```

⚠️ **배포 차단으로 표시**: `POST /programs/{id}/status` 는 여전히 `candidate → active` 를
통과시킵니다. **제품 프런트 소비자는 없습니다**(관리 API 전용). 최소 차단안만 제시했고
**승격 근거의 정의는 승인 경계 결정이라 제가 정하지 않았습니다.**

## 2. DB-0 차이 지도 (조사 · 원본 읽기 전용)

```
기준선 18파일 / 71표 / 기동 DDL  9곳
현재   20파일 / 95표 / 기동 DDL 16곳    새 파일: app_data_preview.db · policy_shadow.db
```

★ **DB 만 보면 절반을 놓칩니다.** 프로젝트 상태·릴리스 **본문**은 파일, 릴리스 **상태**는 DB이고
**둘을 묶는 트랜잭션이 없습니다.** 명령 영수증은 상담용 `advisor.db` 에 얹혀 있고 그 표는
운영본에 **아직 만들어지지도 않았습니다**(최초 사용 시 생성).

## 3. DB-1 첫 adapter + 주입점 (구현)

| 파일 | 무엇 |
|---|---|
| `core/db/__init__.py` (신규) | 방언 한 곳 — 자리표시자 번역·연결 팩토리·wrapper |
| `core/db/schema/001_auth_and_context.sql` (신규) | 첫 슬라이스 7표 **설치** DDL |
| `tests/test_db_adapter_first_slice.py` (신규) | **20건** |
| `core/auth.py` · `enterprise_context/repository.py` · `core/program_lifecycle.py` | **주입점만** — SQL 무변경 |

* **기존 SQL 을 고치지 않았습니다.** store 는 `?` 를 그대로 쓰고 wrapper 가 실행 직전에 옮깁니다.
* **기본값은 지금 그대로 SQLite** — 설정을 주지 않으면 동작이 한 글자도 안 바뀝니다.
* 조용한 실패를 두 곳에서 막았습니다: backend 오타 → 거절, PG 인데 DSN 없음 → 멈춤.

⚠️ **제가 어제 R3 에서 넣은 `BEGIN IMMEDIATE` 는 SQLite 전용 문장**이었습니다 — 방언 상수로
바꿨습니다. 그리고 **주입이 DDL 부트스트랩을 건너뛰게 만들 뻔했고**(`no such table`)
시험이 그 자리에서 잡았습니다.

⚠️⚠️ **이관 대사 1순위**: SQLite `consumed_at=''`(빈 문자열=미사용) ↔ PG `TIMESTAMPTZ NULL`.
`'' → NULL` 이관과 조건절(`=''` → `IS NULL`)이 **함께** 가야 합니다. 어긋나면 **모든 티켓이
이미 쓴 것으로 보이거나 반대로 무한 재사용**됩니다.

```
극성 7종 각각 물림 (단순 replace 번역 3 failed · 주입점 제거 3 failed · BEGIN 재고정 1 · 그 외)
회귀 95건 무변경
```

## 4. 프렙 패킷과 경계 합치기 (지도를 두 번 쓰지 않기)

| DEP | Codex 정적 확인 | **제 DB-0 조사가 더하는 것** |
|---|---|---|
| DEP-03 영속 경계 | 외부 링크는 `data/projects/output` 뿐, library 는 상대 경로 | **릴리스 본문이 그 `library/` 에 있습니다.** 상태는 DB(`program_lifecycle.db`)에 있고 **둘을 묶는 트랜잭션이 없습니다** — 릴리스 디렉터리 교체 시 본문만 사라지면 상태 행이 고아가 됩니다 |
| DEP-05 bootstrap | systemd 가 `uvicorn main:app` 직접 실행 → `run.py` 의 설치 문맥 적용을 건너뜀 | **단순히 `run.py` 로 바꾸면 위험합니다** — `_apply_installation_settings` 가 `data/instance.json` 으로 **`organization_nodes` 를 다시 씁니다**(제가 격리에서 실측해 트랩으로 기록한 그 동작). 「읽기 설정 검증」과 「승인된 초기 설치」를 나누라는 DEP-05 판단이 맞습니다 |
| DEP-07 기동 warmup·seed | startup 에서 warmup·표준 seed | **같은 계열에 DDL 16곳/13모듈이 더 있습니다.** 수와 자리, 최소 분리안을 문서 4에 적었습니다 |

## 5. ★ 결정이 필요합니다 — 없으면 제가 더 밀 수 없습니다

1. **새 열 추가 규칙.** 지금 ALTER 는 `NOT NULL DEFAULT ''` 입니다. Blue/Green 에서 옛 버전은
   그 열을 모른 채 INSERT 하므로 **기본값이 없으면 옛 버전 쓰기가 죽고**, 반대로 큰 표에서는
   기본값이 재작성을 부를 수 있습니다. 「NULL 허용 또는 DEFAULT 필수」를 스키마 리뷰 규칙으로
   둘지.
2. **`julianday()` 트리거 재작성 승인.** `data_preparation/ownership_binding.py` 의 기간 겹침
   방지 트리거는 PG 에 없어 `tstzrange`+배제 제약으로 **재작성**해야 합니다. 이관이 아니라
   **제약의 재작성**이라 같은 것을 막는지 따로 증명해야 합니다. **배포 차단 항목.**
3. **일반 `status` 경로의 승격 근거 정의**(§1).
4. **PostgreSQL DSN** — 설치·대사·복구 검사는 전부 이것 뒤입니다.

## 6. 다음 묶음 — 프렙 패킷 §2 를 따릅니다

지시대로 인계 후 첫 후속은 **P1: CI/산출물 계약**으로 잡겠습니다(60~90분 첫 초안,
Linux 환경 없으면 실행은 미검증). DDL 분리는 §5-①이 정해지면 60~90분 + 동등성 20~30분.

## 7. 나무 상태 / 환경

```
로컬 커밋 4건 (푸시 없음)
미커밋(제 것)  api/routes/factory_control.py · core/auth.py · core/program_lifecycle.py
               core/enterprise_context/repository.py · core/db/(신규)
               frontend 4파일 · frontend/scripts/check-project-entry.mjs
               tests/test_{db_adapter_first_slice,program_reactivate_restores_prior_state,
                            release_item_visibility}.py
일부러 제외    data/interaction_log.jsonl(운영 사용자 로그) · tests/b6_sse_probe.py(원복 대상)
제 것 아님     docs/roadmap/NCP_*.md · docs/handoff/CODEX_*.md ·
               docs/roadmap/WEB_DEMO_DEPLOYMENT_EXECUTION_PLAN_2026-08-21.md(수정됨)
원복 대상      워크트리 동기화 3파일(factory_control·program_lifecycle·프런트 사본)
               격리 fixture(`latest_state.json` 의 project_name 등) · 격리 릴리스 상태
```

미검증 보존: native dialog · 디스크 저장 · 실사용 반복 업무 · 유료 제작 ·
**재개 제품 HTTP 재확인**(격리 로그인 대기 5분). LLM 0 · 클라우드 미배포 · 운영 DB 무접촉.
