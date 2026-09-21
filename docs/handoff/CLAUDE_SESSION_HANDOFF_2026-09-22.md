# Claude Code 세션 인수인계서 — 2026-09-22

> **다른 PC 재개 정본 보완 — Codex / 2026-09-22 00:50 KST.** 사용자 요청에 따라 남은 조율 문서·격리 시험 하네스·진척원장의 비데이터 증거6개를 함께 커밋/푸시하는 인계다. 아래 §10의 checkout/환경/데이터 재생성 절차부터 사용한다. 코드 기준 `cee6423aa`(조율), `4af54ef42`(P03/W03). 이 인계가 포함된 후속 커밋을 받는다. **현재수용35.0%, P03.2/3 +40 검토대기, W03.1은 제한된 로컬증거 제출이며 가산미확정**. 원격동기화와 실제기능수용을 구분한다.

작성: Claude Code (구현 담당) / 대상: **다른 PC 의 Claude Code 세션**
목적: 이 세션의 작업을 **처음부터 다시 하지 않고** 그대로 이어받는 것.

> ⚠️ 이 문서는 «무엇을 했는가» 보다 **«무엇을 믿어도 되고 무엇을 다시 확인해야 하는가»**
> 를 적는다. 환경 의존이 큰 작업이 섞여 있어, 다른 PC 에서는 **재현 불가한 항목**이 있다.

---

## 0. 30초 요약 — 지금 상태

```
전체 진척   1855/5300 = 35.0% (수용분)   수용 20/139단계 · 잔여 3445점/119단계
제출·대기   P03.2 +20 · P03.3 +20  → Codex 수용검토 대기 (수용 시 35.8%)
            W03.1 +45              → 로컬 릴리스 공유 읽기 증거 제출·수용 범위 검토 대기(자동 가산 아님)
지금 할 일  W03.2 원자 저장  ← 여기서 시작하면 된다
```

**내 담당 lane**: 백엔드 설계·구현·검증(업무 DB 이관, 파일 공유/원자성).
**내 담당이 아닌 것**: UI/프론트(Codex), C02/C03/OPS-P1·P2(Codex), 배포관리 콘솔(Codex).

---

## 1. 먼저 읽어야 할 문서 — **이 순서로**

★★★ 이 세션에서 가장 비싼 실수가 **담당 확인 없이 점수 큰 항목을 집어 든 것**이었다.
당시 계산기의 「착수 가능」 목록에는 담당이 없었다. **현재는 Codex가 ready_work/Markdown에 정본 담당을 추가했다.** 목록은 업무배정이 아니므로 아래 문서도 함께 본다.

| 순서 | 문서 | 여기서 얻을 것 |
|---|---|---|
| 1 | `docs/handoff/CLAUDE_CURRENT_WORK_ORDER.md` | **현재 지시.** 맨 위 인용구가 최신이다 |
| 2 | `docs/roadmap/OPERATIONAL_TRIAL_GAP_PLAN.md` | 항목별 **담당/선행** 과 **「할 일」 칸 안의 금지문** |
| 3 | `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` **끝 절** | 이 세션 결과 전부(P03.2/3 · C03 철수 · W03.1) |
| 4 | `.agents/TEAM_BOARD.md` 맨 위 | Codex 와의 최신 주고받음(아래는 이력) |
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

### 2.3 W03.1 — 로컬 릴리스 공유 읽기 구현·증거 제출 (단계 수용 미확정)

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
| 격리 로컬 PostgreSQL | **이 PC 에만 있다** | Git으로 이동 안 됨. 필요 시 §10으로 새 격리환경/합성데이터 재생성 |
| launcher 자격증명 | 현재 Windows 사용자 DPAPI/LOCALAPPDATA에 결속 | 복사 불가. 새 PC에서 setup으로 새 자격증명 생성 후 같은 launcher 사용 가능 |
| `library/` 릴리스 29건 · `projects/` 73건 | 이 PC 의 로컬 자료 | 개수가 다르다. **개수를 단언하는 시험을 쓰지 말 것** |
| 기존 실패 111건 | §6의 Claude A/B 보고 | 새PC 재현은 미확인. 동일원인이라고 단정하지 말고 당시 보고와 새관측을 구분 |

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
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes `
  --target tests/test_w03_shared_release_read.py `
  --target tests/test_program_lifecycle.py --target tests/test_release_readiness.py
```

이 세션 마지막 결과: **100 passed / exit 0 / `sources_unchanged: true`**
(9개 스위트 묶음). 첫 경로 묶음은 **178 passed**.

두 프로세스 공유 읽기 증거(러너 밖):

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare
```

### PG (원래 PC의 경로 차이 사례 — 다른 PC는 §10을 사용)

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

> **§9 정정 / Codex:** 위 목록은 Claude의 앞선 커밋 당시 구분이다. 이번 사용자 승인 커밋에는 `.agents/DECISIONS.md`, `AI_HANDOFF.md`, `PROGRESS.md`, 과거지표 대체표시2파일, `tests/b6_sse_probe.py`도 포함한다. **data/interaction_log.jsonl은 런타임 대화·업무로그라 제외·로컬보존**한다. 운영DB/자료/비밀은 커밋하지 않는다.

## 10. 다른 PC에서 그대로 이어가는 실행 순서 — Codex 보완

### 10.1 소스 받기와 첫 10분

- 원격: `https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git`
- **브랜치: codex/l2-unified-studio-20260912**. 오래된 AI_HANDOFF 본문의 dev/main 안내는 이번 인계 대상이 아니다.
- 새 디렉터리:

```powershell
git clone --branch codex/l2-unified-studio-20260912 --single-branch https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git
Set-Location Ai_Agent_factory_porto
git status --short
git log -3 --oneline
```

기존checkout은 먼저 dirty/현재branch를 확인한다. 보존할 변경이 있으면 덮어쓰거나 reset하지 않는다. clean일 때만 `git switch codex/l2-unified-studio-20260912` 후 `git pull --ff-only origin codex/l2-unified-studio-20260912`. fast-forward가 안 되면 병합/force하지 말고 차이부터 확인한다. 새 PC의 절대경로는 달라도 된다. 원래PC의 `C:\WorkSpace`/사용자폴더/워크트리를 하드코딩하지 않는다.

읽기순서: AI_HANDOFF 최신블록→본서→현행업무지시→원장/결과문서 해당절. 최신지시의 **C03철수는 이미4af54ef42에 반영**돼 있으므로 다시 철수하지 않는다. 아래 파일/기호가 없는 것이 정상이다: `ops_control/db_target.py`, `core/db/schema/002_deploy_ledger.sql`, `STORE_DEPLOY_LEDGER`. 원래 미연결 `ops_control/deploy_ledger.py`는 남는 것이 정상이다.

### 10.2 의존성·데이터 없는 재개 확인

이 PC 실측: **Python3.14.3, psycopg/psycopg-binary3.3.4**. 새 환경은 같은 Python을 우선하며 다른버전 성공을 미리 주장하지 않는다. Docker Desktop은 아래Windows경로 전제의 로컬도구다. Linux/macOS에서는 그대로 실행할 수 없으므로 Windows전용helper를 임의로 우회하지 말고 역할/네트워크/비밀경계를 유지하는 별도 준비가 필요하다.

```powershell
py -3.14 -m venv venv
venv/Scripts/python.exe -m pip install -r requirements-pg-trial.txt
venv/Scripts/python.exe -X utf8 -B scripts/check_trial_progress.py --self-test --markdown
```

Python/의존성 설치는 새PC의 정책/허용망을 따른다. pip실패를 건너뛴 채 준비됐다고 쓰지 않는다. UI 작업 시에만 별도로 `frontend`에서 기존 lockfile 기준 `npm ci`를 실행한다. LLM/API키는 이번 로컬합성 재현에 불필요하며 실키를 요청하지 않는다.

진척계산 예상: **1855/5300=35.0%,20/139,잔여3445점/119단계**. 수용증거 경로를 검사하므로 이번 커밋에 원장이 참조하는 기존 output보고서6개를 명시적으로 포함했다(검사명/결과/경로/해시만; DB/자료 본문 아님). 원래 절대경로는 당시 증거의 출처이며 새PC에서 그 경로가 존재해야 한다는 뜻이 아니다. 이 보고서를 새PC에서 실행한 결과로 재표기하지 않는다.

### 10.3 PG 환경·합성 데이터 재생성(새 PC에서만 최초1회)

**Git pull은 Docker volume·DB·토큰·로컬자료를 복사하지 않는다.** 이번 인계는 원래인증토큰/세션을 이식하지 않고, Git에 있는 installer/seed성격 소비script로 동일한 합성 업무시나리오를 재생성한다. 시각/세션ID/티켓값까지 byte동일복제가 아니다. 기존 운영29릴리스/73프로젝트를 옮기지 않으며, 해당실자료가 필요한 후속작업은 승인된 별도 데이터인계가 필요하다.

사용자 승인 범위는 로컬loopback·합성자료·전용volume·설치/runtime역할 분리다. 새PC 설치/서비스기동에 OS관리승인 등이 필요하면 그 권한만 요청한다. **NCP/관리용PG/운영자료/유료LLM 생성승인은 포함되지 않는다.** 새PC에서 같은 이름의 자산이 있으면 확인 없이 덮어쓰지 않는다.

```powershell
docker version
docker ps -a --format '{{.Names}}'
docker volume ls --format '{{.Name}}'
# 원래 검증 이미지. 빈 준비환경에서만 postgres:16 별칭을 이digest로 맞춘다.
docker pull postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6
docker tag postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6 postgres:16
venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py setup
venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py check
```

Docker가 없으면 공식 설치/기동 및 관리자권한이 선행이다. 기존postgres:16을 쓰는 작업이 있으면 위tag를 자동변경하지 않는다. `setup`은 기존`afs-pg-local`/`afs-pg-local-data`/비밀폴더가 있으면 거절한다. **원래PC에서는 setup하지 않는다.** localhost55432 충돌도 자동점유해제하지 않는다. setup실패 시 생성된 일부자산은 보존되므로 무조건재실행/삭제하지 않는다.

`LOCALAPPDATA/AFS/pg-trial-local`에 **그 PC/그 사용자**의 새 자격증명을 만든다. DPAPI파일·admin.password·DSN을 복사/Git추가/출력하지 않는다. setup과run은 같은Windows사용자 및 같은LOCALAPPDATA환경에서 실행해야 한다. MSIX앱/일반터미널의 LOCALAPPDATA가 다르면 새 비밀을 또 만들지 말고 실제 생성 위치를 확인해 해당프로세스에만 결속한다. 앞 §5의denni/MSIX경로를 다른PC에 붙여넣지 않는다.

새 격리DB에서 다음 순서로 schema/합성조직/합성계정/세션을 재생성한다. 소비script는 제품API를 호출하며 login단계가 다음 concurrent/restart의 입력을 만든다.

```powershell
# import 시 글로벌 ECM singleton의 SQLite 자동DDL을 막는다. 자식들에만 전달된다.
$taskManagedBefore = $env:AFS_DB_MANAGED_STORES
try {
  $env:AFS_DB_MANAGED_STORES = 'auth,enterprise_context'
  venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py run installer -- venv/Scripts/python.exe -X utf8 -B scripts/install_first_db_schema.py --backend postgres --plan
  if ($LASTEXITCODE -ne 0) { throw 'PG plan failed' }
  venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py run installer -- venv/Scripts/python.exe -X utf8 -B scripts/install_first_db_schema.py --backend postgres --apply
  if ($LASTEXITCODE -ne 0) { throw 'PG apply failed' }
  foreach ($taskPhase in @('identity','login','concurrent','restart')) {
    venv/Scripts/python.exe -X utf8 -B scripts/local_pg_trial.py run runtime -- venv/Scripts/python.exe -X utf8 -B scripts/p03_pg_consumption.py $taskPhase
    if ($LASTEXITCODE -ne 0) { throw "PG phase failed: $taskPhase" }
  }
} finally { $env:AFS_DB_MANAGED_STORES = $taskManagedBefore }
```

runtime 대상은 afs_trial_local/app/afs_runtime, installer는 afs_installer다. PG 사양 차이와 미지원 ECM 관리표는 기존 결과의 미해결 항목을 따른다. 전체 저장소 이관·NCP 실행·제품 로그인 UI까지 검증한 것은 아니다. 다른 PC 재현은 기존 결과를 처음부터 다시 심사하라는 지시가 아니라 후속 구현 환경을 준비하는 절차다. Codex는 필요한 출력을 P03 수용 판단에 사용한다.

W03 합성 릴리스는 DB 복사 없이 `venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare`로 임시 디렉터리에 재생성한다. 원래29/73건은 불필요하다. 같은PC의 두 프로세스 증거이지 두 호스트 공유 증거는 아니다. 기존 `library/`에 합성물을 섞지 않는다.

### 10.4 담당별 재개 지점

| 담당 | 첫 작업 | 주의사항 |
|---|---|---|
| 다음 Codex | P03.2/3 제출 증거·harness를 기존 출구로 수용 판단, 충족 시 각20점 즉시 반영. 이후 C02.1 정식manifest→C02후속→C03 | 시험 수·문서만으로 가산하지 않는다. 관리PG는 ENV-PG-OPS pending |
| 다음 Claude | C03 철수를 반복하지 않고 W03.2로 진행. W03.1의 프로젝트측·접근거절·공유실체 등 부족분은 기존 조건과 대조해 같은 소비 과정에서 보완 | 릴리스1건의digest 일치만으로 W03.1 전체조건 충족이라 하지 않는다 |
| 공통 | 같은 파일 동시편집 금지. P03 제품수정은 Claude, 진척원장·수용은 Codex | READY목록은 담당 지시가 아니다. 새 관리 상태 어휘를 발명하지 않는다 |

W03.2 예상2~4시간, P03 수용 검토30~60분(환경 미준비·새 결함은 별도). 다음 단계가 앞 산출물을 소비하는 순서로 진행하며, 단계마다 새 검토문서·변이 캠페인을 만들지 않는다. 중간 연락은 주요 결정·안전·외부권한·실제 장애에 집중하고, 완료 보고에는 인정 진척·잔여·다음 예상 시간을 함께 적는다.

### 10.5 미해결 사항·사고 예방

- P03.2/3 미수용, W03.1 클라우드공유·프로젝트측·권한 검증 범위 미수용. C03 미구현, C02/C04 후속은 원장 참조.
- DEC-PG-TRIGGER는 PG에서도 불변성 통제를 유지할 방침 결정이 필요하다. 첫 경로 출구에 전체제품 조건을 뒤늦게 덧붙이지 않는다.
- 111실패는 Claude의 원래 환경 A/B 보고다. 새PC에서는 미재현이며 원인을 모른 채 skip/xfail·보호해제를 하지 않는다.
- Docker 소켓 재발 시 엔진 종료·정확한 run/Secrets Engine 경로 확인 후 승인된 백업rename 범위로 한정한다. WSL전체종료·volume삭제·공장초기화 금지. 원래PC 사용자 경로를 새PC 대상으로 오인하지 않는다.
- 이전 SSE하네스 `tests/b6_sse_probe.py`는 격리 런처 전용이다. `main.py` 등 정상 제품 라우터에 등록하지 않는다.
- 이번 공유 제외: interaction_log 변경, DB/volume, DPAPI/admin비밀, .env, library/projects실자료, scratch. 삭제하지 않았으며 원래PC에 남긴다.
- 과거의 「커밋없음/미승인/미착수」는 당시 이력이다. 현재는 이 인덱스와 최신HEAD를 우선한다. 수용 증거와 push 완료는 별개이며 Git동기화만으로 진척을 가산하지 않는다.

### 10.6 이번 인계 검증

Codex가 **Git index에 담긴 계산기·원장·수용증거만** 새 임시 폴더로 checkout-index하여 `check_trial_progress.py --self-test --markdown`을 실행했다. 로컬의 미추적 output에 의존하지 않고1855/5300=35.0% 계산/자기검사 통과. 포함 보고서6개는 자격증명 패턴 검사와 구조 확인을 했으며 기존실행 증거임을 유지했다. 실제 다른PC의 Docker/PG 재구성 및 전체제품회귀는 이번 인계에서 NOT_RUN이다. 커밋은16파일 범위(본문·인덱스·개발의존성·격리하네스·선별증거), runtime interaction_log 변경은 제외한다.
