# Claude Code 세션 인수인계서 — 2026-09-22

작성: Claude Code (구현 담당) / 대상: **다른 PC 의 Claude Code 세션**
목적: 이 세션의 작업을 **처음부터 다시 하지 않고** 그대로 이어받는 것.

> ⚠️ 이 문서는 «무엇을 했는가» 보다 **«무엇을 믿어도 되고 무엇을 다시 확인해야 하는가»**
> 를 적는다. 환경 의존이 큰 작업이 섞여 있어, 다른 PC 에서는 **재현 불가한 항목**이 있다.

---

## 0. 30초 요약 — 지금 상태

```
전체 진척   1855/5300 = 35.0% (수용분)   수용 20/139단계 · 잔여 3445점/119단계
제출·대기   P03.2 +20 · P03.3 +20  → Codex 수용검토 대기 (수용 시 35.8%)
            W03.1 +45              → Codex 가산 대상
지금 할 일  W03.2 원자 저장  ← 여기서 시작하면 된다
```

**내 담당 lane**: 백엔드 설계·구현·검증(업무 DB 이관, 파일 공유/원자성).
**내 담당이 아닌 것**: UI/프론트(Codex), C02/C03/OPS-P1·P2(Codex), 배포관리 콘솔(Codex).

---

## 1. 먼저 읽어야 할 문서 — **이 순서로**

★★★ 이 세션에서 가장 비싼 실수가 **담당 확인 없이 점수 큰 항목을 집어 든 것**이었다.
계산기의 「착수 가능」 목록에는 **담당이 없다.** 반드시 아래를 먼저 본다.

| 순서 | 문서 | 여기서 얻을 것 |
|---|---|---|
| 1 | `docs/handoff/CLAUDE_CURRENT_WORK_ORDER.md` | **현재 지시.** 맨 위 인용구가 최신이다 |
| 2 | `docs/roadmap/OPERATIONAL_TRIAL_GAP_PLAN.md` | 항목별 **담당/선행** 과 **「할 일」 칸 안의 금지문** |
| 3 | `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` **끝 절** | 이 세션 결과 전부(P03.2/3 · C03 철수 · W03.1) |
| 4 | `.agents/TEAM_BOARD.md` 끝 | Codex 와의 최신 주고받음 |
| 5 | `docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md` | 배포관리 정본 — **내 lane 아님**. 경계 확인용 |

⚠️ **금지문은 제목이나 점수에 안 보이고 「Gap/할 일」 칸 «안» 에 숨어 있다.** 예:
`C03 … 구 원장 재완성 금지. 담당: Codex`.

---

## 2. 이 세션에서 한 일 — 믿어도 되는 것

### 2.1 P03.2 / P03.3 — 실제 PostgreSQL 에서 제품 경로 소비 ✅ 제출됨

격리 로컬 PG **16.15** 에서 제품 함수로 전부 돌렸다. 증거는 결과 문서에 있다.

- 설치(installer 역할): store 당 22문장, **commit 전** 확인 통과
- 로그인·세션·조직 문맥 **조회와 쓰기**(`upsert_tenant/entity/node`·`add_edge`·`approve_entity`)
- 복합 충돌 대상 2종이 PG 에서 성립: 엣지 4항, 별칭 `ON CONFLICT(node_id, code)` (`DO UPDATE` 가지 포함)
- SSE 티켓 단일 소비 / **동시 소비 정확히 1건** + **음성 대조군 4건 통과**(경쟁 실재 증명)
- 프로세스 재시작 후 전주기 재현
- runtime DDL **0건**(계측 51~60문장·계측기 DDL 포착 확인) **그리고** DB 가 `InsufficientPrivilege` 로 거절

**발견·수정한 제품 결함 1건**: 번역기가 **주석 안의 `?`** 까지 자리표시자로 바꿔 실제 PG
첫 설치가 거절당했다(`자리표시자 4개인데 파라미터 0개`). 두 층으로 수정 + 회귀 5건.
변이로 4+1건 물림 확인. ★ **기존 21건은 변이에도 전부 초록**이었다 — 그 분기를 보는
시험이 하나도 없었다는 뜻이다.

### 2.2 C03 철수 ✅ 완료

C03 은 **Codex 담당**이고 「구 원장 재완성 금지」였는데 내가 착수했다. 지시대로
**이번 추가분만** 조각 단위로 철수했다(파일 전체 되돌리기 아님). 상세 표는 결과 문서에.

- `ops_control/deploy_ledger.py` → HEAD 복원(파일 하나만). 기존 DEP-R 보완·반례 보존
- `ops_control/db_target.py` · `core/db/schema/002_deploy_ledger.sql` ·
  `tests/test_ops_ledger_separation.py` → 제거(**Git 밖 scratch 에 사본 보존**)
- `core/db/managed_schema.py` · `scripts/install_first_db_schema.py` → C03 분기만 제거,
  **`DEFAULT_STORES=(auth, enterprise_context)` 는 유지**(지시)

### 2.3 W03.1 — 공유 읽기 ✅ 완료

**결함**: `projects/` 는 저장소 기준 절대경로인데 **`library/` 만 작업 디렉터리 상대**였다.
루트에 릴리스 29건이 있어도 다른 디렉터리에서 뜬 프로세스는 **0건**으로 본다.

**고침**: `core/library_paths.py` — `_LIBRARY_DIR = project_path("library")`.

**증거**: `scripts/w03_shared_read_probe.py compare` — 서로 다른 cwd 의 프로세스 둘이
제품 함수로 읽어 digest·소유문맥 6필드 일치. **음성 대조군**(옛 해석)에서는 B 가 아예
못 찾는다. ⚠️ **단일 PC 두 프로세스 증거이며 두 호스트·공유 마운트 증거가 아니다.**

---

## 3. ⚠️ 다른 PC 에서 **재현 불가/재확인 필요**한 것

| 항목 | 상태 | 다른 PC 에서 |
|---|---|---|
| 격리 로컬 PostgreSQL | **이 PC 에만 있다** | 컨테이너 없음. P03 증거를 재현하려 하지 말 것 |
| Codex launcher 자격증명 | 이 PC 의 MSIX 경로 | `local_pg_trial.py` 못 씀 |
| `library/` 릴리스 29건 · `projects/` 73건 | 이 PC 의 로컬 자료 | 개수가 다르다. **개수를 단언하는 시험을 쓰지 말 것** |
| HEAD 기존 실패 111건 | §6 참조 | 재현될 것이다. **내 작업 탓 아님** |

★ P03.2/3 은 **이미 제출**됐다. 다른 PC 에서 PG 가 없다고 해서 **다시 하지 않는다.**
Codex 수용검토 결과만 받으면 된다.

---

## 4. 다음 작업 — W03.2 원자 저장 (여기서 시작)

지시 원문: `CLAUDE_P03_EXECUTION_RESULT.md` 의 「Codex C03 판정·철수 범위·W03 다음 실행」 §4-2.

> W03.2: 앞 단계가 읽는 **같은 경로**의 저장을 원자화한다. 부분파일 방지와 동시 writer 의
> 낡은 revision 덮어쓰기 방지는 **다른 문제**다. rename 만으로 두 가지를 다 달성했다고
> 쓰지 않는다. 제품 쓰기→두 소비자 재조회로 정상경로 확인, 실제 독립 writer 경쟁·중간
> 실패 한 흐름으로 음성 확인한다. 임시파일은 같은 filesystem, 대상/상위 링크·문맥경계
> 보존. 정상 반환한 성공 버전의 소실을 허용하지 않는다.

### 시작 지점 (내가 확인해 둔 것)

| 쓰는 곳 | 파일·위치 | 지금 방식 |
|---|---|---|
| 릴리스 | `core/kit_app_builder.py:423~426` | `makedirs` 후 `open(...,"w")` + `json.dump` — **원자성 없음** |
| 프로젝트 상태 | `core/async_orchestrator.py:96~101` (`_save_latest_state`) | `os.path.join(workspace_root,"latest_state.json")` |
| 프로젝트 상태(다른 경로) | `api/routes/factory_control.py:749` | 같은 파일명 |
| 읽는 곳 | `core/app_delivery.py:571` · `core/program_lifecycle.py:517` · `core/app_proof.py:95` · `core/promotion_advisor.py:61` | 모두 `library_paths` 단일 지점 경유 |

경로 단일 지점: `core/library_paths.py`(보관소) · `core/paths.py`(`workspace_path`).

### ⚠️ 착수 전 주의 — 내가 이미 밟은 지뢰

1. **격리 러너는 `subprocess.Popen` 을 막는다.** 두 프로세스 증거는 pytest 안에서 못
   만든다. probe 스크립트로 만들고 러너 밖에서 돌린 뒤 결과를 문서에 남긴다.
   **그 통제를 끄지 말 것.**
2. **시험이 제품 모듈을 `importlib.reload` 하면 세션이 오염된다.** 단독 15건 통과하던
   스위트가 묶음에서 4실패·9오류가 됐다. 필요하면 `runpy.run_path` 로 새 이름공간에서만.
3. **격리 러너는 `library_paths._LIBRARY_DIR` 을 자기 실행 뿌리로 갈아끼운다**(cwd 가
   아니다). 그래서 시험 안에서 「살아 있는 값 == PROJECT_ROOT/library」를 단언하면 깨진다.
4. **검사가 도는 중에 소스를 만들거나 고치지 말 것.** 러너가 `sources_unchanged: false`
   를 찍고 그 실행 전체가 증거로 못 쓰이게 된다. (내가 한 번 버렸다.)

---

## 5. 환경·명령

### 검증 (어디서나 가능)

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes ^
  --target tests/test_w03_shared_release_read.py ^
  --target tests/test_program_lifecycle.py --target tests/test_release_readiness.py
```

이 세션 마지막 결과: **100 passed / exit 0 / `sources_unchanged: true`**
(9개 스위트 묶음). 첫 경로 묶음은 **178 passed**.

두 프로세스 공유 읽기 증거(러너 밖):

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare
```

### PG (이 PC 전용 — 다른 PC 에서는 건너뛴다)

컨테이너 `afs-pg-local` / `127.0.0.1:55432` / db `afs_trial_local` / schema `app` /
역할 `afs_installer`·`afs_runtime`.

```powershell
$real = $env:LOCALAPPDATA
$env:LOCALAPPDATA = "C:\Users\denni\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local"
try { venv\Scripts\python.exe -X utf8 -B scripts\local_pg_trial.py run runtime -- `
        venv\Scripts\python.exe -X utf8 -B scripts\p03_pg_consumption.py login }
finally { $env:LOCALAPPDATA = $real }
```

⚠️ **절전이 이 환경을 끊는다.** PC 가 자면 Docker 엔진이 죽고
`%LOCALAPPDATA%\Docker\run\` 에 0바이트 소켓이 남아 재기동을 막는다. 복구는 **삭제가
아니라 이름 바꾸기**(`run` → `run.backup-<시각>`)이며 **자동 승인에서 막히므로 사람에게
부탁해야 한다.** 컨테이너만 멈춘 경우는 `docker start afs-pg-local`.
⚠️ 비밀번호·DSN 을 요청·복사·출력하지 않는다. `setup` 재실행 금지. 삭제·`down -v`·
volume rm·WSL 전체 종료 금지.

---

## 6. ⚠️ HEAD 의 기존 실패 111건 — **내 작업과 무관**

미커밋 변경이 **전혀 없는** HEAD 워크트리에서도 재현된다(`test_app_data_runtime` 단독
46건 중 28 실패). 관련 26스위트 745건 A/B 비교에서 **내 변경으로 새로 깨진 것 0건**.

```
test_app_data_runtime 28 · test_app_dataset_binding 17 · test_release_promotion 16
test_end_to_end_canary 12 · test_provider_dispatch 11 · test_rag_dept_scope 10
test_release_rollback_api 10 · test_p4_recommendations 4 · test_project_deletion_policy 3
```

대표 증상 `{"detail":"같은 이름의 데이터셋이 이미 있습니다: orders"}`.
**담당·원인은 내 범위 밖**이라 판정하지 않았다. 다른 PC 에서도 이 실패를 보면
**자기 변경 탓으로 오인하지 말 것.**

---

## 7. 열려 있는 결정·요청

| ID | 내용 | 대기 대상 |
|---|---|---|
| **DEC-PG-TRIGGER** | `enterprise_process_*` 의 불변성이 **SQLite 트리거**(`RAISE(ABORT)`)로 강제됨. PG 이관 시 ①트리거 함수 포팅 ②응용 계층 격상 ③이관 연기 중 택일. **표만 옮기면 통제 한 층이 사라진다** | Codex |
| **ENV-PG-OPS** | 관리 PG 용 **별도 데이터베이스**. `afs_installer` 에 CREATEDB 없음(`rolcreatedb: False`). ⚠️ **C03 철수로 지금은 내 필요 없음** — Codex OPS-P2 의 것 | Codex/사용자 |
| P03.2/3 수용 | +40, 수용 시 35.8% | Codex |

---

## 8. 지켜야 할 경계 (이 세션 내내 유효했던 것)

- 운영 `data/`·`library/`·실사용자 자료를 **건드리지 않는다**. 이번 세션 내내 불변 확인:
  `library/` 29→29, `projects/` 73→73
- 서버 검증은 `scripts/verify_data_usage_holds.py --strict-writes --target ...` **격리 실행**만.
  운영 DB 에서 pytest·서버 기동·마이그레이션 금지
- **격리/쓰기 보호를 꺼서 통과시키지 않는다.** skip/xfail·단언 약화 금지
- 실제 브라우저를 안 했으면 **NOT_RUN**. 소스 문자열 검사를 동작 증거로 보고하지 않는다
- LLM 호출·외부 전송 0. 새 외부 DB 생성·서비스 설치·과금은 별도 승인
- **디렉터리째 `git add` 하지 않는다** — 공유 트리다. 남의 변경이 섞여 조용히 깨진다
- 변이 시험은 자기 변경 범위의 격리 사본에서, **원복 해시 확인**까지

---

## 9. 이 커밋에 들어간 것 / 들어가지 않은 것

**들어간 것**: 위 2절의 제품·시험·스크립트·결과 문서, 그리고 Codex 가 만든 **미추적
조율 문서·도구**(다른 PC 가 이어받으려면 반드시 필요하다 — 업무지시서·Gap 정본·
설계 정본·진척 계산기·PG launcher).

**들어가지 않은 것**(다른 작업자의 진행 중 변경 — 보존):
`.agents/DECISIONS.md` · `AI_HANDOFF.md` · `PROGRESS.md` ·
`docs/handoff/DECISION_CREATION_CONTRACT_REPAIR_2026-09-11.json` ·
`docs/roadmap/WEB_DEMO_DEPLOYMENT_EXECUTION_PLAN_2026-08-21.md` ·
`tests/b6_sse_probe.py` · `data/interaction_log.jsonl`(런타임 자료)

⚠️ 다른 PC 에서 `git pull` 한 뒤, 위 «들어가지 않은 것» 들은 **HEAD 판본**이다.
이 PC 에 남아 있는 미커밋 변경과 다르다.
