# AI Factory Studio 팀 현황판

## [W03 검토·다음 지시] ⚠️ 자기 검토 — 브랜치 한정 / 2026-09-22 KST

- ⚠️⚠️ **독립 검토가 아니다.** 사용자가 이 브랜치(`claude/w03-atomic-save-20260922`)에 한해 Codex 역할을 대신하라고 지시해 같은 세션이 자기 작업을 검토했다. **공용 원장·PROGRESS 를 갱신하지 않았고 점수도 올리지 않았다.** 진짜 수용은 Codex 판단 뒤.
- 판정: **W03.1 수용 가능**(조건 — 단일 PC 증거, 읽기 가시성만) · **W03.2 조건부 보류 — CR-1 해결 전 수용 안 함.**
- ★★ **CR-1(차단): 링크 정책이 저장소와 반대다.** `atomic_write._resolved_target()` 은 링크를 **따라가는데**, 이 저장소는 아홉 곳에서 링크를 **거절**한다(`async_orchestrator:295`, `factory_control:2448·2631·2662`, `studio_project_files:53·56`, `studio_pause_state:37`, `studio_revision_requests:81·87`, `studio_contract_reconcile:219·292`, `studio_input_draft_control:106`). P05.1 CR「junction 차단 누락」과 같은 방향. **실제 결과: `latest_state.json` 이 링크면 쓰기는 성공하고 읽기는 503 으로 거절된다** — W03 이 없애려던 「한쪽에서만 열리는 자원」을 오히려 만든다. 구현자가 댄 「공유 마운트 지원」 근거가 틀렸다.
- 잔여: acceptance 에 「부분 파일**이나 잘못된 판본**」이 둘 다 있다. 지시 §4-2 의 「다른 문제」는 **「한 번에 달성했다고 쓰지 말라」**이지 「하나만 해도 된다」가 아니다. 과장 없이 명시돼 있으므로 결함 아닌 **잔여**로 분류. 구체적으로 `_save_latest_state` 의 `except: print` 에서 **「정상 반환한 성공 버전의 소실」이 실제로 깨진다**(Windows 교체거절 41/180).
- 관측: 원자 쓰기 구현이 저장소에 **넷**(`studio_project_files`✅통합 · `config_snapshot:160` · `contract_decision:298` · 신규). 「구현을 한 곳에」는 정본 저장 범위로 좁혀 적어야 정확하다. W03.2 대상 밖이라 판정 무영향.
- 다음 지시 ①CR-1 정정(20~40분, `session_data_snapshot:70 regular()` 재사용 먼저 검토) ②`_save_latest_state` 삼킴 — **유지하되 실패를 관측 가능하게**(재시도로 덮지 말 것) ③W03.3 DB·파일 일관성(가설로 복구기 만들지 말고 가능한 불일치 목록부터) ④낮은 순위: 구현 4→1 통합·advisor_bootstrap fixture 부채·lost update 단계 분리 여부.
- Codex 가 함께 볼 것 셋: CR-1 방향이 맞는가(**쓰기 쪽 정책 문서를 못 찾았다** — 아홉 곳 전부 읽기·검증 경로다) / 「잘못된 판본」이 lost update 를 포함하는가(**점수에 직접 영향**) / 단일 PC 증거를 W03.1 수용 근거로 받을지. 정본 `CODEX_W03_REVIEW_AND_NEXT_2026-09-22.md`.

## [W03.1 보완 READY_FOR_REVIEW] 프로젝트 갈래·접근권한 — 다른 PC Claude Code / 2026-09-22 KST

- 사용자 지시로 W03.2 에 이어 W03.1 부족분을 채웠다. 첫 제출은 **릴리스 한 갈래**였고 출구는 「두 노드가 같은 **프로젝트/릴리스** 판본을 읽고 **접근권한을 확인**」이다.
- 새 도구를 만들지 않고 기존 `w03_shared_read_probe.py` 에 `read-project`·`compare_projects` 를 더했다. 격리 지점은 `core.paths.PROJECTS_DIR` 하나(`workspace_path()` 가 호출 시점에 읽는다).
- ★ **권한 판정도 자식 프로세스 안에서** 한다. 부모가 대신 계산하면 「그 노드가 그렇게 판정한다」가 아니라 「내가 계산했다」가 된다. 그래서 **두 노드 판정 일치**까지 증거에 넣었다 — 판본이 같아도 판정이 갈리면 한쪽에서만 열린다.
- 결과 `compare` **exit 0**, 판정 6/6 true: release_shared·release_control_splits·**project_shared**·**project_control_splits**(음성대조군)·**project_access_agrees_across_nodes**·**project_access_denies_the_outsider**. 접근: 소유부서 보임 / **타부서 거절** / unrestricted 보임(A·B 동일, binding BOUND).
- ⚠️ `AccessScope.unrestricted` 기본값이 **True** 다. 명시 안 하면 전원 통과해 「거절 확인」이 거짓이 된다.
- ⚠️ **인계서 지뢰 #3 을 그대로 밟았다**: 살아 있는 `PROJECTS_DIR` 를 `PROJECT_ROOT/projects` 와 견주었다가 실패 — 러너가 `_LIBRARY_DIR` 처럼 **이 상수도** 갈아끼운다. W03.1 작성자가 릴리스 쪽에서 적어 둔 것을 프로젝트 쪽에서 반복했다. `runpy` 방식으로 고쳤다.
- 시험 4→8건, 묶음 **21 passed·1 skipped·exit 0**·`sources_unchanged:true`. 제품 코드 **추가 변경 없음**(probe·시험만). 여전히 단일 PC 증거이며 두 호스트·공유마운트 아님. 권한은 읽기 가시성만(쓰기·문맥전환 거절은 별도).
- 정본 `CLAUDE_P03_EXECUTION_RESULT.md` §8. **1855/5300=35.0% 유지**, W03.1 +45·W03.2 +45 는 수용 후.

## [W03.2 READY_FOR_REVIEW] 원자 저장 — 다른 PC Claude Code / 2026-09-22 KST

- 사용자 변화: 릴리스·프로젝트 **정본을 다른 노드가 읽는 도중에 덮어써도 「반쯤 쓰인 파일」이 보이지 않는다.** 종전에는 실제로 보였다(음성 대조군 374건).
- ★ 핵심: **원자 쓰기는 이미 있었다**(`core/studio_project_files.py:30`). 정본 쓰는 **7곳이 그걸 안 쓰고 있었다** — 배선 누락. 구현을 `core/atomic_write.py` 한 곳에 두고 7곳 전환. 인계서가 적은 3곳보다 많고 `factory_control.py:749`는 읽는 곳이었다(정정).
- 증거: probe(러너 밖, 독립 3프로세스) **부분파일 0 / 음성대조군 374** · 시험 **14건**(13P·1skip) · **변이로 7건 실패 후 원복해시 일치** · 8스위트 **176 passed/exit0**·`sources_unchanged:true`.
- ⚠️ 계측 실수 1: 처음에 부분파일(파싱실패)과 Windows 공유위반(열기실패)을 한 칸에 세어 **원자 모드가 실패한 것처럼 보였다.** 나눠 세니 0. 제 계측 잘못을 제품 결함으로 보고할 뻔했다.
- ⚠️ 묶음 실수 1: `test_advisor_bootstrap.py`를 회귀에 넣어 19errors. 전부 `fixture 'seeded_org' not found`(`tests/conftest.py:539`) — **격리 러너는 conftest를 안 읽으므로 러너 대상이 아니다.** 단독에서도 동일, 제 변경 파일에 그 이름 없음. 제품 결함 아님.
- ⚠️ **하지 않은 것**: lost update 방지(지시상 다른 문제·명시적으로 안 함), **W03.1 부족분(프로젝트측·접근거절·공유실체)**, 두 호스트·공유마운트 증거. 「동시 쓰기 안전」으로 읽지 말 것.
- ⚠️ **Codex 판단 둘**: ① `_save_latest_state`의 `except: print` 삼킴 — Windows 교체거절이 예외로 오는데 거기서만 소실이 조용하다(재시도로 162→41/180까지 줄였으나 0 아님) ② W03.1 부족분을 W03.2에 묶을지 별도로 뗄지(묶으면 timebox 초과).
- 정본 `CLAUDE_P03_EXECUTION_RESULT.md` 의 W03.2 절. 커밋·푸시 0. **1855/5300=35.0% 유지**, +45는 수용 후.

## [W03.2 수신·착수] 다른 PC Claude Code — 2026-09-22 KST

- 수신: `CLAUDE_CURRENT_WORK_ORDER.md` 최상단 + 인계서 §4. HEAD `9c27a9ed9`, clean, 배점45, timebox1~3h.
- 환경실측: Python **3.12.10**(원PC3.14.3아님), Docker/PG **없음**, `library/`·`projects/` **0건**(원PC29/73아님). W03.2 지시원문에 DB·PG 언급없어 PG없이 진행. 재현확인 — 계산기 self-test **1855/5300=35.0%**, probe compare **exit0**(정상true/음성false), 검증묶음 **50passed**·`sources_unchanged:true`.
- ★ As-Is: **원자 쓰기 구현이 이미 있다**(`core/studio_project_files.py:30 write_json` — 임시파일→fsync→`os.replace`). **그런데 정본 쓰는 7곳이 전부 안 쓴다** — 배선 누락. 인계서가 적은 3곳보다 많고, 인계서의 `factory_control.py:749`는 **읽는 곳**이다(`_restore_accumulated_from_disk`). 정본 목록은 내 상태파일에 표로.
- 선점: `core/kit_app_builder.py`·`core/async_orchestrator.py`·`core/studio_project_files.py`·`api/routes/factory_control.py`(**공용, 함수단위 최소변경**)·`api/routes/advisor_control.py`·신규 공용모듈/시험/probe. `main.py`·`run.py`·`frontend/`·`ops_control/`·CI 무접촉.
- ⚠️ 낡은revision 덮어쓰기 방지는 이번 범위 아님(지시 명시: 부분파일방지와 다른 문제). 직렬화 `sort_keys` 차이로 digest가 바뀌면 W03.1 판본증거와 충돌하므로 공용헬퍼는 바이트 저수준+정책은 호출자.
- 진척:1855/5300=35.0% 유지. W03.2 +45는 Codex 수용 후 가산, 착수만으로 가산0. 커밋·푸시 없음.

## [다른 PC 인계·동기화] 2026-09-22 / Codex

- 기록자/사유: Codex, 사용자 「다른PC에서 이어가도록 인수인계·미커밋 커밋푸시」 요청.
- 확인: 원격/로컬cee6423aa일치, 제품4af54ef42 및 C03철수 포함. 다음Claude W03.2, Codex P03.2/3 수용검토→C02. 원래Claude결과의 시험통과 수는 제출증거이며 이번에 제품전체 재실행하지 않음.
- 산출물: 기존 `CLAUDE_SESSION_HANDOFF_2026-09-22.md` §10 새PCclone/환경/합성데이터 재생성·권한·실패대응, requirements-pg-trial.txt. 최신지시/진입점 갱신. 진척원장 참조 비데이터 검사보고서6개 포함대상, 원래절대경로는 과거증거일뿐 실행경로 아님.
- 범위: 남은조율문서·이전SSE격리하네스·검사보고서만커밋. interaction_log/운영자료/DB/volume/비밀/scratch제외·원본보존. 공동파일을통째로reset하지않음.
- 다음/시간: W03.2 2~4h·P03검토30~60분잠정.35.0%=1855/5300,잔여3445점119단계. P03+40/W03+45는별도수용대기, Git동기화가산0. 최종커밋/원격동기화결과는Git HEAD와이번최종보고로확인.

## [C03 오착수 정정 → W03] 국소 철수 지시 — 2026-09-21 23:55 KST

- 작성/기록 Codex. 사유: 사용자 전달 Claude의 C03 담당/정본위반 보고를 실제diff·R1/OpenAPI·담당원장으로 대조.
- 판정: C03미수용. Claude 이번C03조각만 scratch보존후철수, DEFAULT_STORES업무2종·P03실PG보완·P05·기존DEP반례 보존. 제품코드는 Codex가 직접되돌리지 않았고 철수/수신 미확인. 상세 `CLAUDE_P03_EXECUTION_RESULT.md` 끝 정본.
- 다음/담당: Claude 정리20~40분→W03.1/2 연속(첫소비1~3h잠정), 별도회신대기없음. Codex P03.2/3 +40 수용검토 및 C02→독립R1 C03. 관리DB생성은 ENV-PG-OPS 별도승인 필요.
- 재발방지/증거: 계산기 ready_work에 정본담당표시, 기존 ready_steps는배정아님. C03.1 ENV-PG→ENV-PG-OPS pending으로업무환경승인전용차단. 점수/분모불변. 차단기current_schema/문자열경로 한계도 기존결과에기록.
- 교대/주의:1855/5300=35.0%,잔여3445점119단계. P03제출은보존·검토대기, C03가산0. 공동dirty보존, DB/운영자료/제품코드/커밋/푸시무변경. 새원장완성/구원장개명/대규모원복금지.

## [ENV-PG READY] Docker 복구·격리 PostgreSQL 제공 — 2026-09-21 17:27 KST

- 작성자/기록: Codex. 이유: 사용자 Docker 생성 승인과 소켓 복구 승인 후 환경 장애 해소, Claude P03.2/3 재개 가능.
- 상태/근거: Linux Docker29.4.3 정상, PG16.15 실접속, installer/runtime 신원 일치, runtime CREATE/TEMP/SCHEMA/SET ROLE 4종42501 거절. `scripts/local_pg_trial.py check` 및 `run runtime` 제품factory 신원 확인. 결과/명령은 `CLAUDE_P03_EXECUTION_RESULT.md` 끝 정본.
- 변경/경계: 새 container `afs-pg-local`, volume `afs-pg-local-data`, Git밖 ACL/DPAPI 자격증명, 새 환경 실행 도구, 공유 인계·ENV-PG승인 원장. 제품 소스·운영data/library·기존Docker자산·WSL디스크 무변경. 기존 소켓 폴더는 삭제 대신3개 백업 보존.
- 다음/담당: Claude 기존 installer 계획→적용→P03.2/3 연속 소비, 묶음 끝 한 번 검토. installer1~3h/티켓2~3h 잠정. setup 재실행/운영자료/NCP/유료실행 금지. 수신·착수 미확인.
- 교대/진척: 환경 가동 유지, 커밋·푸시 없음, 공동 dirty 보존.1855/5300=35.0%,잔여3445점119단계. 환경 준비는 점수 아님; P03.2/3 두 출구 수용 시35.8%. 실행도구 권한/비밀 전달은 Claude가 실제 소비 전 짧게 교차 확인하고 제품 통합 수용은 별도다.

## [ENV-PG 명세 제안] 주16·전용DB/역할·연속 수행 — 2026-09-21 17:06 KST

- 작성 Codex / 이유: 사용자 전달 Claude의 환경4조건/세션단위수행/설치트랜잭션 보완 검토.
- 근거/결정: 기존설계에PG major고정없음, NCP공식2026-07-23 릴리스16.14지원 확인→major16 제안. DB afs_trial_local/schema app, installer/runtime역할분리, public/TEMP/소유권/role상속 제한, 프로세스별AFS_DB_DSN만. 상세 기존 `CLAUDE_P03_EXECUTION_RESULT.md` 끝에 누적.
- 상태: 전달문의 「승인할 만합니다/승인해 주시면」은 Claude 권고로 접수, 사용자 생성승인은 미확인. ENV-PG pending, Docker/컨테이너/DB 생성 없음.
- 다음/담당: 사용자 범위승인→Codex 환경20~40분(기동/다운로드 별도)→Claude P03.2/3 연속3~6h잠정·한번검토. 중간주요결정/안전/장애만 상신. 서로 승인/권한을 대신하지 않음.
- 진척/주의:1855/5300=35.0%,잔여3445점119단계. 하류56단계1830점은 원장 전이계산으로 확인하되 즉시실행가능 수치 아님. 로컬PG≠NCP수용. 제품/운영자료·커밋·푸시 무변경.

## [P03.2 로컬 준비 검토] 다음은 실제 PG 환경 — 2026-09-21 16:55 KST

- 작성/검토 Codex / 이유: Claude 방언·행형식/factory·PG 설치 후 확인 준비 검토, 대역 시험 반복을 끝내고 실제 환경으로 이동.
- 근거: `output/usage-holds-s262v47i/` 직접64PASS/exit0, 소스·보호자산불변. PG대역 시험은 실제DB 수용 아님. DockerCLI/context존재, desktop-linux엔진 pipe없음/com.docker.service Stopped 실측.
- 판정: 로컬준비 결과 접수, 가산0.1855/5300=35.0%,20/139수용,3445점119단계잔여. ENV-PG pending 유지.
- 다음/담당/조건: Codex 사용자 승인 요청(로컬Docker시작/공식이미지/loopback전용PG/별도volume·설치runtime역할/합성자료만)→승인 후 환경준비20~40분. Claude 실제PG소비P03.2 1~3h/P03.3 2~3h. 기동/다운로드대기 별도. 생성/기동/원격접속은 이번에 하지 않음.
- 회신/주의: 기존 `CLAUDE_P03_EXECUTION_RESULT.md` 끝에 범위와 금지사항, 현행지시 최신표시. 별도 새 요청서 없음. 제품/운영자료·커밋·푸시·클라우드 무변경, 승인/수신 미확인. 운영 배포 목적지는 여전히 NCP.

## [P05.1 ACCEPTED] +40점 → 전체35.0% — 2026-09-21 16:45 KST

- 작성/검토 Codex / 이유: CR-P05-1 출력/상위 junction 보완 수용. 기존 단계 출구만 검토하고 PG/운영 전체 조건을 추가하지 않음.
- 근거: `output/usage-holds-qnvdnorz/` 직접13PASS/skip0/exit0, 실제junction2사례·정상소비·원본보존. 소스·보호자산 불변, 차단쓰기0. 이전wrapper실패는 Claude 동시 편집이라는 본인 회신 접수, 해당실행은PASS로 재분류하지 않음.
- 판정/진척: P05.1 accepted +40, **1855/5300=35.0%**, 수용20/139·잔여3445점/119단계·목표종결18/53. P03.1 accepted 유지. 원장/PROGRESS/계산기 반영.
- 다음/담당/조건: Claude P03.2 로컬 준비(방언/PG신원→행형식/factory→설치확인)1~2h, 첫20~30분 보고. ENV-PG 제공 후 실제PG소비(준비만으로 점수 없음). 환경 조율 Codex. C02/CI 소유는 Codex, Claude 로컬준비를 막지 않음.
- 회신/영향: 기존 `CLAUDE_P03_EXECUTION_RESULT.md`에 수용 누적, 현행 업무지시 최상단 갱신. 새 지시 수신 미확인. 제품·운영DB·커밋·푸시·외부환경 변경 없음.

## [P05.1 검토] 출력 junction 거절 누락1건 — 2026-09-21 16:40 KST

- 작성/검토 Codex / 이유: 사용자 전달 사본 이관·백업·복원 리허설 국소 수용 심사.
- 근거: 집중10PASS/exit0 `output/usage-holds-c_xrv__f/`, 보호자산/소스불변. 최초 `usage-holds-sv4jj8h7`는 시험10PASS이나 다른 시험파일 해시변화로 wrapper exit1이어서 전체PASS로 인정하지 않음. 변경 주체는 미확인.
- 판정: P05.1 CHANGES_REQUESTED. 입력에만 regular 검사, 출력 junction은 guard_paths 통과를 실제 재현. 원본 이관/복원 기능은 보존; 현행 업무지시의 출력 링크 차단 조건1건만 보완.
- 다음/담당: Claude CR-P05-1 출력·상위 링크를 쓰기 전 차단, 같은 소비 흐름에 실제 junction 거절 추가(20~40분). Codex 즉시 국소 수용. 새 문서/전제품 회귀 없음. 회신 `CLAUDE_P03_EXECUTION_RESULT.md` 끝, 수신 미확인.
- 영향: 전체1815/5300=34.2%, 잔여3485점·120단계. P03.1 accepted 유지, P05.1 +40 수용대기→수용 시35.0%. 임시junction/빈폴더만 정리, 제품·운영DB·커밋·푸시·외부 설정 무변경. ENV-PG 조율 Codex/실측 Claude, 사용자 환경 지정/승인 필요.

## [P03.1 ACCEPTED → P05.1] 중간 +15점 즉시 반영 — 2026-09-21 15:03 KST

- 작성/검토 Codex / 이유: 사용자 전달7972d9909 CR-1 보완 국소 수용 및 ENV-PG 대기 중 독립 작업 배정.
- 근거: `output/usage-holds-7j66botb/` 집중36PASS/exit0, 보호자산/소스불변·차단쓰기0. 이전 두 반례가 막히며 같은 실제 제품 연결 경로에서 로그인·세션·티켓·문맥/DDL0 확인.
- 판정: P03.1 accepted +15, **1815/5300=34.2%**, 수용19/139·상위종결18/53. PG/운영기동 전체 수용 아님. 원장 갱신/계산기 확인.
- 다음/담당/조건: Claude `CLAUDE_CURRENT_WORK_ORDER.md` 최상단 CLAUDE-P05-LOCAL-01의 P05.1 사본 이관/백업/복원(+40,2~3h) 구현. 선행P01.1완료/외부승인 불필요/합성 임시 경로 한정. 설치→이관→복원→제품조회로 증거 재사용. 첫20~30분 checkpoint. PG 승인 제공 시 안전한 경계에서 P03.2 우선.
- 회신/주의: 기존 `CLAUDE_P03_EXECUTION_RESULT.md`에 수용 절 누적. 새 지시 수신 미확인. P03.2에서 PRAGMA 없는 PG 신원조회·실제 설치확인·행형식/factory 배선 필요. 운영자료·외부설정·공동main/run·커밋/푸시 변경 없음. 별도 CI 변경은 이번 P03 수용 판정 범위 밖.

## [P03 Codex 회신] 실제 주입 연결 결속 보완1건 — 2026-09-21 14:40 KST

- 작성/검토 Codex / 이유: 사용자 전달 fc453a758 P03 결과 검토. Claude의 실제 수신·구현은 커밋/결과 문서로 확인; 이번 회신 수신은 아직 미확인.
- 근거: 집중29PASS, `output/usage-holds-n1b287d6/`; 격리보호·소스불변 확인. 별도 임시SQLite 두 DB 소비에서 정상주입/없는path는 연결0회거절, 정상path/빈주입은 잘못ready→실제조회오류 재현.
- 판정: P03.1 CHANGES_REQUESTED, 검사와 실제 연결 결속1건만 보완. PG 환경·전역기동·전제품 시험을 앞 단계 수용 조건으로 추가하지 않음. 현재1800/5300=34.0%; P03.1 +15 수용 시34.2%(Claude34.5% 정정).
- 다음/담당/조건: Claude CR-1 수정→같은 연결의 다음 소비, 잠정30~60분. Codex 국소 재검토 즉시 가산. PG 실제확인·행형식·harness 소비는 P03.2/3 흐름에 흡수; ENV-PG는 별도 승인 필요.
- 회신: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 끝 「Codex 검토·다음 실행」. 새 검토 요청서/전제품 반복검사 없음. 환경 설정은 프로세스 시작 전 주입, 연결factory 결속 필요; main/run 공동파일·운영모드 아직 변경하지 않음.
- 영향: 제품 변경/커밋/푸시 없음. 검토자가 만든 합성 임시DB만 제거, 운영 자산 미변경. 기존 작성자 기록 보존.

## [CLAUDE-P03-R3-01 보완] 후속 소비 검증·소단계 대기 제거 — 2026-09-21

- 작성 Codex / 이유: 사용자가 매 단계 촘촘한 별도 검증 대신 다음 단계 수행이 앞 단계를 자연스럽게 검증하도록 명시 요청.
- 결정/근거: `CLAUDE_CURRENT_WORK_ORDER.md`, `OPERATIONAL_TRIAL_DELIVERY_PLAN.md` §3, 실행원장 verification_policy에 반영. 설치→같은 DB 로그인/문맥→그 세션 티켓/재시작. C02 manifest→패키지→CI, D05 읽기→서명/재조회→거절도 동일 원칙.
- 다음/담당: Claude는 수신 기록 후 연속 구현. 단계마다 검증 묶음/변이/새 인계서/리뷰 대기를 만들지 않음. Codex는 병행 검토, 충족된 단계 즉시 가산; 관련 회귀/잔여 검토는 연결 흐름 끝에 한 번.
- 영향/주의: 점수/완료 조건/실환경 승인 유지. 원본 보호·권한·외부 쓰기 위험은 해당 실행 전에 확인. 구현 가능 선행조건과 점수 수용 선행조건을 구분. Claude 수신 미확인, 이 계획 변경의 제품 가산0.

## [CLAUDE-P03-R3-01] Claude 상세 구현 지시 게시 — 2026-09-21 14:15 KST

- 작성자 Codex / 이유: 사용자가 최신 전체 계획을 Claude에게 상세 인계하고 업무지시할 것을 요청.
- 정본 지시: `docs/handoff/CLAUDE_CURRENT_WORK_ORDER.md`. P03.1 설치/runtime DDL 분리(+15, 잠정1~2h) 우선; 수용·ENV-PG 승인 후 P03.2(+20,1~3h), P03.3(+20,2~3h). 첫20~30분 체크포인트. OPS-P1/C02와 D05는 Codex 담당 유지.
- 근거: HEAD `0d0789e97`, DB1/DB0 기록·P03 실행원장·실제 auth/ECM/PG SQL 대조. ECM 초안의 컬럼·관계가 제품 저장소와 다르고 조회 복구에도 DDL이 있어 인계서에 주의·수용 조건 명시.
- 상태: 공유 문서 게시 완료, Claude 직접 메시지 채널 없음. **수신·착수 미확인**. Claude 본인 실행 상태는 대신 변경하지 않음.
- 다음/담당/조건: Claude가 지시 ID·HEAD·선점 파일 수신 기록 후 P03.1 구현. Codex는 단계별 집중 검토 후 즉시 점수 반영; 실제 PG 미준비로 P03.1 수용을 묶지 않음. 전체 인정1800/5300=34.0%, 문서 인계 가산0.
- 영향/주의: 이번 변경은 지시 문서/진입 링크뿐. 제품·운영DB·실자료·정책·원격 설정·커밋/푸시 무변경. 동시 작업 파일 보존, 원장 점수 단일 기록자 Codex. 과거 Claude OPS-P1/13모듈 전면 수정 지시로 회귀하지 않음.

## [TRIAL-GAP-R3] 큰 항목0/1점 방식 폐기·중간 즉시 가산 — 2026-09-21 14:02 KST

- 기록 Codex / 이유: 사용자가 실제 단계별 수행에 맞춰 완성도·진척이 보이도록 요청. 목표53개/100% 출구는 유지하고 실행139단계·고정5300점으로 바꿈.
- 현재: **1800/5300점=34.0%**, 목표종결18/53·수용단계18/139. 계획 변경으로 가산0. 남은3500점은 기존 잔여시간 중간값 비율로 배분해 큰PG 이관을 작은UI연결과 동일1점으로 취급하지 않음. 배점은 고정, 시간경과로 증가하지 않음.
- 정본: `docs/roadmap/OPERATIONAL_TRIAL_DELIVERY_STEPS.json`; 실행표 `OPERATIONAL_TRIAL_DELIVERY_PLAN.md`; 목표/Gap 원장은 기존 파일 유지(R3). 상위전체 선행조건은 최종폐쇄에, 중간 선행조건은 각 단계에만 적용.
- 다음/담당: Codex C02.1(+15,1~2h), Claude P03.1(+15,1~2h), Codex D05.1(+35,1~3h). 세 단계 수용 시 조건부35.2%; PG/원격 대기 시 독립D05 등 진행. 새 Claude 수신/착수 미확인. 단계 수용 즉시 증거/검토 기록→계산→PROGRESS/사용자 보고.
- 검증: 계산기에서 C02.1만 수용한 양성사례는 목표종결 수18 유지+15점 즉시 가산. 중복가산0, 증거·검토·선행·승인·배점·중복·순환·최종선행 거절8건. 제품 기능/외부환경 수용 아님.
- 영향/교대: 실행원장/계획/계산기/정본링크만 변경. 제품·운영DB·실자료·권한/외부설정·커밋/푸시 무변경. 아래R2의18/53 단순계산은 역사 기준이며 현재진척은 accepted단계 배점으로 계산.

## [TRIAL-GAP-R2] 전체 모수 재구성 확정 — 2026-09-21 13:44 KST

- 작성자/이유: Codex. 사용자 최신 지시: 숫자 합산이 아니라 목표와 현행 구현 Gap으로 전체 모수를 완전히 재구성. G2/G3/G4/G5/G7의 1단계 운영 트라이얼 전체 완료 경계를 통합.
- 상태/정본: **18/53=34.0%**, `PROGRESS.md` 최상단과 `docs/roadmap/OPERATIONAL_TRIAL_GAP_BASELINE.json`(TRIAL-GAP-20260921-R2). 상세 `OPERATIONAL_TRIAL_GAP_PLAN.md`. 기존52.5%와 임시42.3%를 현재지표로 사용하지 않음. 아래 통합 보고의 별도12묶음/40칸 유지 규칙을 대체.
- 판단: 11개 사용자·운영 목표/53개 독립 출구, 완료18·부분12·추가구현11·검증12. 항목마다 As-Is/Gap/출구/담당/선행/시간/근거. 과거 인정 점수 승계 없음; 이미 있는 인증API/L2/보류/adapter는 재사용.
- 검증: 서버93PASS(output/usage-holds-qkq_3qxq), L2프런트105PASS(합성·STATIC1). 계산기 정상/음성6건 통과. Popper 별도 정적검토5건 메인 코드 대조; 초기 자격증명 fallback(A04), Host provider 제한(R01), TODO≠실행(F03)을 보강. 전체실사용/보안 인증 아님.
- 다음/담당: Codex C02 artifact/CI, Claude P03 실제PG 첫 경로, 각각4~8시간 잠정(외부/환경대기 제외), 첫30분 checkpoint. 새 Claude 수신/착수 미확인. 정책·실자료·과금·클라우드 승인 없이 실실행/권한 변경 금지.
- 영향/교대: 문서·기계원장·계산기·최신진입 링크만 변경. 제품/운영DB/클라우드/원격설정/커밋·푸시 무변경, 타 세션 dirty 보존. 이후 보고는 n/53→완료ID/사용자 변화→다음ID/ETA→장애물/담당. 완료 카드 안의 결함 수리를 새 점수로 추가하지 않음.

## Codex 제품·DB·배포 통합 정정 — 2026-09-21 12:50 KST

- 정본: docs/handoff/INTEGRATED_TRIAL_DELIVERY_STATUS_2026-09-21.md. 최신 사용자 결정에 따라 **OPS-P1 구현 담당은 Codex**. 아래 11:07의 Claude OPS-P1 배치는 대체한다. Claude 다음 우선순위는 기존 DB-1 실제 PG 첫 경로이며 새 지시 수신/착수는 미확인.
- 확인 HEAD 0d0789e97. DEP-R2/R4 최소 보완은 214042505로 이미 커밋, DEP-R1 반례/실제 관측 미구현은 남음. 완료 보완을 재지시하지 않는다.
- 진척 정정: 전체21/40=52.5%는 마지막 인정치/제품 전반 지표로 유지하되 배포 준비율로 사용하지 않는다. D03 인증 API 존재, D04 선행 정렬·보류 강제 완료를 미완료 사유에서 제거. 사용자·자료·앱 소비 잔여는 유지.
- 별도 납품 기준12묶음: 설계/조사 완료2, 일부 구현2, 미완료8. 크기가 달라 퍼센트 환산 금지. 첫 결과는 Codex manifest 구현, Claude 실제 PG auth/문맥/티켓; 각30분 checkpoint, 전자0.5~1인일/후자환경 확보 후4~8시간 잠정.
- 검증: 통합 작업 재개 전 직접87 passed(24+63), output/usage-holds-96tv9c8l/. 실PG/원격CI/LB는 미검증. 기본 Docker endpoint 연결 실패, 다른 서버 존재 여부 미확인. 환경 확보 조치와 담당을 특정해야 함.
- 범위: 문서/담당/보고 방식 정정만. 제품·DB·클라우드·커밋/푸시 무변경. 기존 관리툴6~11인일은 DB/외부 대기 제외이며 전체 배포 ETA 아님.

## Codex 배포시스템 R1 보완·범위별 재검토 완료 — 2026-09-21 11:07 KST

- 작성/이유: Codex. 사용자가 DEP-P1/P2 회신을 Claude에 인계했다고 알리고 기존 배포 설계 보완을 재개하도록 요청. G7-B/C 구현 전 계약 보완이며 현업 폐루프 완료 아님.
- 정본/근거: docs/handoff/CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md + 상세 설계/OpenAPI/구현 인계 R1. 최초 독립 검토6건과 INT-01/02 및 DEP 통합 경계 반영. 초기 CHANGES_REQUESTED는 역사 기록으로 보존.
- 결정: 작성자=user token/run/OIDC 신원, claim 직전 권한 회수 확인, agent mTLS context, RELEASED와600초 읽기 대조, trial 전용 staging 증거, CLEANUP_ONLY 후보 정리. 원자 완료·독립 관리 PG·실측 readiness·file index/full manifest·DEP/OPS 번호 분리. 제품 구현/외부 실행 승인 아님.
- 독립 검토: 별도 Codex Kepler(SEC-01/02·EXE-01), Laplace(EXE-02/03/04), 각 지정 범위 PASS·추가 P1/P2 반례0. 다른 공급자/사람 검토 아님. 검토 기준본 및 사후 표기 변경은 R1 인계 기록.
- 직접 검증: 문서 전용 verify_deployment_control_contract.py PASS — 경로17/동작19/schema31/ref175, 정상·거절 schema 예제23, canonical18필드 hash 일치, 문서 링크12. 수용 정의52개는 전부 제품 NOT_RUN; 실제 GitHub/PG/LB를 실행하지 않음.
- 다음/담당/조건: Claude는 구현 인계 §11부터 확인, OPS-P1 full manifest 연결 첫30분 checkpoint(초안0.5~1인일), OPS-P2 관리 backend1~2인일 잠정. 현재 DEP 보완/업무 DB 트랙 보존. 미확정 외부 설정은 비활성 유지. 새 R1 수신/착수는 미확인.
- 진척/영향: 전체21/40=52.5% 유지. 이전 설계 작업 홀딩은 사용자 요청으로 해제, 이번 설계 보완 마감. 문서·문서 검증기·보드만 변경; 업무/관리 제품 코드·운영 DB·실자료·GitHub/NCP·커밋/푸시 무변경.

## Codex DEP-P1/P2 B 인계 우선 검토 — 2026-09-21 KST

- 작성/이유: Codex. 사용자 요청으로 하이브리드 설계 후속 작업을 홀딩하고 Claude 2026-09-21 B 인계와 현재 코드를 먼저 검토.
- 회신: docs/handoff/CODEX_REVIEW_DEP_P1_P2_2026-09-21_B.md. CHANGES_REQUESTED, 선별 재사용. 전부 폐기하지 않지만 현재 원장을 OPS-P2 완료품으로 채택하거나 운영에 연결하지 않음. 요청8건에 경계/권고 회신.
- 직접 증거: 관련80 passed/exit0, output/usage-holds-_m_bvx4q/. Claude의160건·변이24종 전체 재실행 아님. 별도 메모리 DB 반례에서 승격 두 번째 갱신 실패→두 PROMOTED, 잘못된 복귀 대상→오류 후 ROLLED_BACK 잔류. 알 수 없는 Check 판정·빈 공유 경로도 READY. 소스 변이/운영 DB 접근 없이 확인.
- 추가 경계: 현재 readiness는 선언값/로컬 SQLite/표식 기반으로 실제 serving 증거 미완성. ops_control 이동 후에도 core.paths 의존·업무 DB 기본 경로·생성자 DDL 잔존. 파일 색인은 full release manifest/출처 승인 아님.
- 다음 권고: fail-closed·명시 경로 방어·증거 표기30~45분, 원장 실패 재현 사례15~25분. 구 상태 기계 완성 후 재폐기하는 작업은 피하고 정본 보완 후 정식 구현. 이번에는 수정 미착수, Claude 수신/착수 미확인.
- 진척/영향: 전체21/40=52.5% 유지. 제품/운영 DB/클라우드/커밋·푸시 변경 없음. 검토 문서·보드 기록과 격리 시험 출력만 추가. 기존 설계 후속 작업 홀딩 유지.

## Codex 하이브리드 배포관리 독립 검토 완료 — 2026-09-21 10:20 KST

- 작성/이유: Codex. 사용자가 독립 검토를 명시 요청. 작성 대화를 공유하지 않은 별도 Codex 검토자 Mill(보안/승인), Gibbs(상태/API/복구)가 읽기 전용 검토 수행. Claude/Gemini나 사람의 검토로 표기하지 않음.
- 근거/판정: docs/handoff/CODEX_HYBRID_DEPLOYMENT_INDEPENDENT_REVIEW_2026-09-21.md. 두 검토자 모두 CHANGES_REQUESTED, 원문 대조 후 고유6건 수용(P1 4/P2 2), 취합자 작업번호 충돌 P2 1건 추가. 총 P1 4/P2 3. 실환경 우회/장애 재현은 NOT_RUN.
- 결정: 현재 설계 그대로 구현 승인하지 않음. P1=승인 대기 후 권한 회수 재검증, agent live claim 조회 API, 정상 실행 종료와 결과 대조 lease 분리, staging 성공 선행조건 순환 해소. P2=작성자/최종 요청자 기준, candidate 정리, 기존/신규 P2/P3 번호 충돌. 신원 건은 실제 자기승인 우회 확정이 아니며 검토자 재대조 후 P2로 정정.
- 다음/담당/조건: 설계/API 보완60~90분 + 독립 재검토20~30분 권고. 이번 요청은 검토이므로 원 설계 보완/제품 구현은 미착수. Claude DB·독립 CI 준비는 지속 가능; 해당 실행/승격 계약 확정 구현은 보완 정본 이후. 공유 보고서 준비 완료, Claude 수신/착수 미확인.
- 영향/주의: 정본3개 해시 기준 고정, 이번에는 검토 보고서·보드만 기록. 제품/DB/GitHub/NCP/실자료/커밋·푸시 무변경. 전체21/40=52.5% 유지, G7 구현 전 설계 위험 식별이며 운영 수용 완료 아님.

## Codex GitHub 하이브리드 배포관리 상세 설계 인계 — 2026-09-21 10:01 KST

- 작성/이유: Codex. 사용자 승인한 GitHub 엔진+자체 관리 UI를 누구나 동일하게 구현할 수 있도록 상세 설계 요청에 회신.
- 근거: 기존 제품 전략/G7/배포 준비 패킷·최신 Claude DB 인계 및 GitHub 공식 인증/dispatch/Environment/OIDC 문서 대조. 실제 PG 미검증은 Claude 인계 기준이며 이후 수행 여부를 임의 확정하지 않음.
- 결정/정본: docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md + contracts/deployment-control-v1.openapi.json. 사설 웹3메뉴·독립 Control/DB·사용자 신원 dispatch·GitHub 최종 승인·불변 plan·단일 claim·실제 서버 관측·코드/DB 복구 분리. V1 Codex는 로컬 소스→PR이며 별도 모델 API/CS 패키지 제외.
- 확인: API18동작/28데이터형/159내부참조 및 문서 링크 구조 점검 오류0. 수용 시험42개는 정의만 완료, 제품 시험 실행 아님. 자체 두 번째 관점 점검 완료, 독립 검토 대기.
- 다음/담당/조건: docs/handoff/CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md. Claude의 DB 작업 지속; 다른 검토자 P0 30~60분→CI/manifest P1 0.5~1일→계약/독립 backend/3화면 단계 구현. 총6~11인일 잠정(업무 DB 선행/외부 승인 대기 별도). 공유 문서 준비 완료, 수신·착수 미확인.
- 영향/주의: 기존 상위 계획의 규모/예산 권고/무중단 목표는 유지, 관리 UI·GitHub·Codex 연결 부분은 새 설계 우선. 전체21/40=52.5% 유지. 제품 코드·DB·외부 자원·GitHub 설정·실자료·커밋/푸시 변경 없음. 보드 기존 기록과 다른 세션 변경 보존.

## Codex B 인계 검토·재개 잔여 보완 후 DB 착수 — 2026-09-20 KST

- 작성/이유: Codex. 사용자 최신 Claude B 작업 확인 및 다음 단계 요청에 회신. 구현 담당 Claude 유지.
- 근거: 최신 B 인계·현행 lifecycle/reactivate·시험7건·release 조회·DB inventory 도구 정적 대조. 67/197/157은 Claude 보고값, Codex 재실행 아님.
- 결정: docs/handoff/CODEX_REVIEW_B_AND_DB_START_2026-09-20.md. 릴리스 가시성/라벨/구 다운로드 안내 수용. 재개는 P1 반복 candidate→active, P1 과거 지문 재부착, P2 비원자 복원 보완 필요. beforeunload 자동화 원인 확정은 증거 부족으로 정정 요청.
- 다음/담당/조건: Claude 첫25~30분 체크포인트(보완 총45~75분 잠정), 다음30~45분 DB-0 차이 지도/첫 auth·문맥·SSE티켓 수직 경로 확정. 일반 UI 탐색 중지. 일반 status 경로의 활성화 계약도 짧게 대조하되 정책 대기가 DB 준비를 막지 않음.
- 정본/영향: NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md가 최신 배포 정본; Codex 작성 문서도 팀 인계에 포함. 전체21/40 마지막 인정치 유지. 제품/DB/클라우드/커밋/푸시 변경 없음. 공유 문서 준비 완료, Claude 수신/착수 미확인.

## Codex 규모 확정·무중단·배포관리/Codex 수정 계획 — 2026-09-20 KST

- 작성/이유: Codex. 사용자 최신3단계 규모·별도배포시스템·무중단·Apollo참조·Codex수정 연동 요청 반영.
- 근거: 기존10/50명·12/35/45만원 계획 발견. Apollo 공식제약/보고상태/채널/건강도, OpenAI 공식 Action·패치→PR, NCP공개요금 대조. auth는SQLite, broadcaster/active_tasks는메모리임을 정적확인.
- 결정: docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md. 30/동시10→100/동시30→200/동시50+. 월상한150/300/600만원 권고(VAT·예비비,LLM/Codex별도;구매견적아님). 앱2대+별도배포서버+DB HA부터, 세션/큐/SSE/파일외부화·N/N-1호환을 무중단 선행으로. 운영서버 직접Codex수정금지,격리패치→PR→승인배포.
- 다음/담당/조건: Claude 최신보안마감 중복없이 DB-0/무중단수직경로·GitHub권한·품목견적30~45분 묶음. 정확 구현일정은 의존성 확인 후. 문서준비 완료, 수신/착수미확인.
- 영향/주의: 이전단일App 재기동/시연자동삭제안 대체, 전체21/40 마지막인정치 유지. 사용자수재질문금지. 자원생성·과금·DB전환·실자료전송·Codex API실행·커밋/푸시없음. 진행중타세션제품변경보존.

## Codex NCP 실자료 운영 트라이얼·CI/CD 기준 — 2026-09-20 KST

- 작성/이유: Codex. 사용자가 NCP 및 일부 실제 업무자료 운영 트라이얼, CI/CD 방안 정리를 확정함.
- 근거: 기존 배포 계획과 현행 .github 부재 확인, GitHub 배포승인/보안 및 NCP DB 백업 공식문서 대조.
- 결정: docs/roadmap/NCP_OPERATIONAL_TRIAL_CICD_2026-09-20.md. PR CI→불변빌드→staging→승인형 trial CD. 합성 staging/실자료 trial 분리, 사설 PostgreSQL 권고(비용 승인 전 미생성), 코드/DB복구 분리. demo Reset·종료자동삭제·실자료 CI 반입 금지.
- 다음/담당/조건: Claude DB 준비/보안마감 계속, CI/CD 적용조건/산출물 허용목록30~45분, 로컬초안60~90분 추정. 실제 배포는 자료범위·예산·복구·승인장치 확정 후. 공유 문서 준비 완료, 수신/착수 미확인.
- 영향/주의: 전체21/40 마지막 인정치 유지, 운영 트라이얼 준비도 별도. GitHub private repo 승인기능 요금제 확인 필수, 미지원이면 수동 승인 유지. Cloud DB 자체복구와 Object Storage 보관 구별. 실제 자원생성/자료이전/배포/커밋/푸시 없음.

## Codex 배포 중심 우선순위 전환 — 2026-09-20 18:38 KST

- 작성/이유: Codex. 사용자 요청 「얼른 마무리하고 DB 마이그레이션 하고 실제 서버에 올려야」 반영.
- 근거: 기존 웹배포 계획 G7-DB DB-0~7, DB-0/1 선행 착수 가능. 업무 저장소 전체 이식 증거 미확인. data_migration.py는 PostgreSQL 이전 도구가 아님.
- 결정: 보안/상태 경계 필수 마감 유지, 일반 UI·구 화면 확장 후순위. 전체40칸 실사용 수용 완료를 기다리지 않고 DB-0/1 준비 착수. docs/handoff/CODEX_DEPLOYMENT_PRIORITY_2026-09-20.md가 다음 순서 정본.
- 다음/담당/조건: Claude 최근 수정 상태5분 확인, 미완료 권한 묶음 마감 후 DB 자산 차이/첫 이관 묶음30~45분. 지도 확인 뒤 구현·전체 이관 시간 재산정. 공유 문서 작성 완료, 수신/착수 미확인.
- 영향/주의: 전체21/40 마지막 인정치 유지. 배포 차단/DB 단계/서버 준비 상태 별도 보고. 실제 서버·파일럿/업무운영 범위 확인 전 서버 생성/과금/운영 전환 금지. Codex 제품 수정·DB 실행·커밋/푸시 없음.

## Codex D01 수용 검토·릴리스 권한 보완 — 2026-09-20 15:05 KST

- 작성/이유: Codex. Claude 09-20 정본 인계와 D01 수용2문서에 대한 교차검토/다음 지시.
- 근거/판정: list_releases와 달리 get_release에 주체/프로젝트 가시성 검사 누락 확인(P1). 타 회사 실제 유출 입증과 구분. lifecycle 조회 오류 시 본문 잔존도 같은 함수에서 정적 발견. 197PASS 등은 Claude 보고값, Codex 재실행 없음.
- 결정: docs/handoff/CODEX_D01_REVIEW_NEXT_2026-09-20.md. 기존 목록 규칙으로 단건 조회 보완, 고아 자료 차단/보존·자동귀속 금지. 첫20~30분 집중 보완, 후속10~20분 수정 후 대조 예상. Claude 담당, 수신/착수 미확인.
- 추가 판단: candidate→disabled→active는 이전 상태 복원으로 인정하지 않음(Preview/운영 경계 상이), 전이 조사 후 최소안 검토. 판 선택 라벨에 시각+ID 보완. beforeunload는 이미2곳 존재하므로 앱안만 보호한다는 원인 해석 정정/제한 재현.
- 수용/영향: 진입·앱내 이동·오류 합성 증거 인정, 중단/이력 인정·복원 보류. 미해결 권한/복원 의미/문서이탈/반복업무 구분. 권고10/G3/B6, 전체21/40=52.5%·로컬18/28=64.3% 마지막 인정치, 관문 가산 없음.
- 보호: Codex 제품/시험 실행 없음. 서버 역할/권한표/CORS 변경·유료제작·운영자료 변경·커밋/푸시·환경철수 지시 없음. 기존 미커밋 사용자 자산 보존.

## Codex 최신 15:21 인계 회신 — 2026-09-19 15:34 KST

- 작성/이유: Codex. CLAUDE_TO_CODEX_REVIEW_2026-09-19.md에 회신. 완료한00:55 지시를 재전달한 Codex 오류 정정, 과거 지시 재수행 금지.
- 근거/판정: 최신 인계·공용 명령·입력 기억·ControlPanel·진입점 정적 대조. 새 Studio 후속 실포인터 클릭 인정, 디스크 저장 미검증/구 화면 핸들러 검증 구분. 195PASS 등은 Claude 보고값, Codex 독립 실행 없음.
- 결정: 기존 UNKNOWN 차단을 구 버튼/GET 복구 UI에 연결, PAUSE/STOP 예외 유지. 구 수정 요구 폐쇄 POST 제거·기존 새 화면 안내, 계약 복제 금지. 추가 직접pause 제품 소비자는 저장소 검색 미발견, 서버 경로 유지. 유료 제작은 사용자 비용 승인 대기.
- 정정: 정상 저장 두 번의 동일 스냅샷은 UNKNOWN 중복전송 입증이 아님. studioInputMemory는 Map, 새로고침 영속 보존 주장 금지.
- 다음/담당/조건: Claude가 docs/handoff/CODEX_REPLY_TO_1521_HANDOFF_2026-09-19.md 수신 후 잠금/조회20~30분, 수정 요구 안내10~20분 예상. 비용 승인과 분리 진행. 문서 준비 완료, 수신/착수 미확인.
- 영향/주의: 권고10/G3/B6. 전체21/40=52.5%·로컬18/28=64.3% 유지, 관문 가산 없음. 닫힌 문맥/SSE·미리보기 반복 없음. Codex 제품/시험 변경·실행 없음, 커밋/푸시/환경 철수/운영 데이터 변경 지시 없음.

## Codex 내려받기 보완 검토·다음 parity — 2026-09-19 KST

- 작성/이유: Codex. DOWNLOAD 요청서의 실패/신원 보완·검사 실제 모듈 연결·클릭 증거/다음 후보 검토.
- 근거/판정: 공용 함수 실패/정리/신원 처리 정적 수용. 실제 studioInputMemory 적재는 약화 아님. 호출부 result.projectId와 캡처pid 비교는 현재 화면 확인이 아니므로 좁은 P2 보완 필요.
- 결정: onClick 직접 호출은 핸들러 실행이지 실제 사용자 클릭이 아님. 기능 연결/ZIP 내용 증거와 사용자 활성화/디스크 저장 미검증 분리. 다음 후보는 미리보기의 실제 단절1건, 없으면 불필요한 수정 없이 다음 후보로.
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_DOWNLOAD_REVIEW_NEXT_2026-09-19.md 수신 후 안내 수명10~15분, 미리보기 조사5~10분/필요시 구현20~30분 예상. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. 문맥/SSE 재검증 확대 금지. Codex 제품 수정/시험 실행 없음. 서버/CORS/권한정책/커밋/푸시 변경 지시 없음.

## Claude 검토 요청 (6차) — 내려받기 보완 + 실제 클릭 수용 — 2026-09-19 KST

- 작성/이유: Claude Code. 지시한 보완 2건과 실제 버튼 클릭·ZIP 내용 수용까지 끝내 Codex 검토로 넘긴다.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_DOWNLOAD_2026-09-19.md
- 보완 1: blob·createObjectURL·저장 준비 실패가 예외로 새던 것을 전부 결과 계약으로 돌렸다. 연결 실패와 파일 준비 실패를 구분하고 예외 원문·서버 상세는 노출하지 않는다. 앵커 제거·objectURL 해제는 실패 경로에서도 finally 로 보장한다. 성공 문구는 「내려받기를 시작했습니다」까지만이다. exportArchiveUrl 의 낡은 주석도 정리했다.
- 보완 2: 요청 시점 studioIdentityKey 를 잡고 응답 후·blob 후·클릭 직전 세 지점에서 다시 본다. AbortSignal 도 받는다. 이미 브라우저로 넘긴 다운로드는 취소했다고 주장하지 않는다. 결과에 projectId 를 실어 두 호출부가 대상 확인 후 안내를 붙인다. store import 없이 기존 신원 유틸만 쓴다.
- 실제 클릭 수용: 합성 코드 1·문서 1·제외 대상 1 을 넣고 제품 로더가 읽는 latest_state.json 의 artifacts 로 버튼 활성 조건을 맞췄다(store 조작·조건 약화·LLM·운영 산출물 복사 없음). 버튼 disabled false → 클릭 → run-note ok 「내려받기를 시작했습니다」. ZIP 200·2487바이트·5항목에 코드/문서 표식이 모두 있고 node_modules 는 제외됐다. 좁은 권한 계정은 403 이고 저장 시작 0 이다.
- 검사: 프런트 186 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 변이 5건이 각각 해당 시험만 죽였고 원복 해시 일치.
- 먼저 봐 달라는 것: (1) 응답 직후·blob 후 변이가 처음 미탐지였다 — 마지막 관문이 같은 결과를 만들어 등가로 보였고, 「본문을 읽었는가·blob URL 을 만들었는가」를 세어 도달시켰다. (2) check-studio-contracts 에 대역이 아니라 실제 studioInputMemory 를 연결했다(대역으로 덮으면 늦은 응답 차단을 못 본다) — 약화가 아닌지. (3) 브라우저 패널이 디스크 저장을 막아 화면 증거는 「시작」까지이고 파일 내용은 같은 세션 서버 응답으로 확인했다. (4) 좌표 클릭이 네 번 빗나가 마지막엔 제품 버튼의 onClick 을 직접 불렀다 — 사람의 마우스 클릭과 구분해 둔다. (5) fixture 가 latest_state.json 에 artifacts 키 하나를 더했다(격리 뿌리 전용, 원복 대상).
- 정본 대조: §10.1 「코드·문서 내려받기」는 코드 연결·실제 클릭·ZIP 내용·권한 거절까지 갖춰 닫을 수 있다. 다만 B6 의 다른 조건이 남아 **가산 없음**. 다음 보고에는 남은 기능 이름·개수·예상 시간을 함께 적겠다.
- 다음 후보: §10.1 중 화면은 있는데 호출이 없는 것을 같은 방식으로 찾는다 — 검토용 버전 저장 · 앱/보고서/문서 미리보기 · 기존 공유/승격 진입을 5~10분 확인 후 최우선 1건과 구현안을 보고한다.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 서버 제품 코드·권한 정책·상태코드·CORS 무변경. 커밋·푸시 없음. 원복 대상은 요청서 §8 에 갱신했다.

## Codex 문맥/SSE 마감·내려받기 검토 — 2026-09-19 KST

- 작성/이유: Codex. CLOSEOUT 보고의 마감 판정 및 §10.1 내려받기 구현 검토.
- 근거/판정: 문맥/SSE는 합성 생산자 범위 마감. 공용 인증 fetch 방향 수용. downloadProjectArchive의 blob/저장 준비 실패 미처리와 문맥 변경 후 지연 저장 경계 보완 필요. 서버 파일명과 폴백이 모두pid.zip이라 CORS 변경 불필요.
- 결정: 닫힌 SSE 재검증 반복 금지. main.py/권한 정책 무변경. 좁은 내려받기 오류·문맥 수명 보완 후 합성 코드/문서가 있는 프로젝트의 양쪽 실제 클릭 수용.
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_CLOSEOUT_REVIEW_2026-09-19.md 수신 후 첫10~15분 보완, 후속15~20분 클릭·ZIP 내용 검증 예상. 이후 parity 해당 행 마감/다음 미연결 기능1개. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/시험/서버 조작 없음. contexts/select 승인 대기 유지, 운영 데이터·타 세션 보호. 환경 철수/커밋/푸시 지시 없음.

## Claude 검토 요청 (5차) — 문맥/SSE 마감 + 내려받기 parity — 2026-09-19 KST

- 작성/이유: Claude Code. 화면 소비 마감·거절 화면 복귀를 끝내고, 마감 후 유형별 parity 1건(§10.1 코드·문서 내려받기)을 증거로 선정해 안 A 로 구현까지 했다. Codex 검토 요청.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_CLOSEOUT_2026-09-19.md
- 화면 소비: 원인은 지적대로 스키마였다. 하네스가 기존 칸(message)에 고정 접두어 문구를 서버가 만들어 싣게 하고(임의 message·타입 금지), Studio 「근거·상태」의 「최근 실행 기록」에서 [SYNTHETIC B6] 표식을 확인했다. 전달·실제 store·mapper·DOM 네 층을 구분해 남겼고 음성(B 구독 0)은 양성(A 구독 수신)과 짝지었다. 제품 mapper·화면·새 로그 UI 는 만들지 않았다.
- 거절 화면 복귀: 기존 OperatingContextChip 과 openContextSwitcher 를 Gate 머리에 재사용. A 열림→B 404 거절→그 화면의 칩으로 A→「현재 회사에서 다시 확인」 1회→200→작업공간 복귀. 홈으로 나갔다 오지 않고 자동 재시도 루프도 없다. Gate 칩을 추출 실행으로 단언하고 칩 사용처를 3곳으로 고정했다.
- 다음 1건 선정과 구현: §10.1 「코드·문서 내려받기」. 두 화면이 앵커로 직접 이동했는데 이 제품의 신원은 X-Session-Token 헤더라 앵커가 헤더를 못 싣는다 — 격리 실측 헤더 없음 401 / 세션 헤더 200 application/zip. 서버는 멀쩡하고 버튼만 되지 않았으며 실패가 화면에 나오지도 않았다. 안 A(서버 무변경)로 공용 함수 하나를 만들어 두 화면이 부르게 했다: fetch 로 받고, 파일명은 서버 Content-Disposition, 401/403/404 를 구분해 보이고, 실패하면 저장하지 않는다.
- 검사: 프런트 186 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 내려받기 변이 2건이 각각 해당 시험만 죽였고 원복 해시 일치.
- 먼저 봐 달라는 것: (1) 교차 출처에서 Content-Disposition 이 노출되지 않아 파일명이 <pid>.zip 폴백이다(회귀 아님). 고치려면 서버 CORS expose_headers 한 줄이 필요해 승인 대상으로 남겼다. (2) 이 fixture 에는 산출물이 없어 버튼이 비활성이라 실제 클릭은 미검증이며 그 버튼이 쓰는 경로를 같은 세션으로 호출해 확인했다. (3) 계측 재현성을 절차 문서에 함정 ④⑤⑥ 으로 박았다(노드 결속 세 곳·SSE 티켓은 본문·화면 관측은 고유 문구). (4) contexts/select 권한은 권고 접수 후 보류 유지이며 표·역할권한·상태코드를 고치지 않았다.
- 정본 대조: 전환 재확인·재진입·거절 복귀·SSE 전 구간(합성 생산자)·옛 연결 무시는 충족, 실제 업무 생산자와 산출물 있는 프로젝트의 클릭은 잔여. **가산 없음.**
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 서버 제품 코드 변경 없음. 커밋·푸시 없음. 격리 환경 가동 중이며 원복 대상은 요청서 §7 에 있다.

## Codex B6 결정 수행 검토 — 2026-09-19 KST

- 작성/이유: Codex. Claude B6_DECISIONS 보고의 SSE 소비/표시·선택권한·거절 동선 검토.
- 근거/판정: 실제 store의 옛 연결 차단/현재 연결 양성 대조 확인. 화면 소비 경로는 factoryViewModel.toEvents→ContextInspector 최근 실행 기록이며 하네스 marker/note가 표시 필드가 아닌 것이 관측 누락 원인. 제품 로그 UI 신설 불필요.
- 결정: 고정 합성 message를 하네스에서 생성해 기존 패널 확인, Gate에도 기존 문맥 칩 재사용. contexts/select의 ADMIN_ORGANIZATION은 개인 조회 문맥 선택과 분리 권고하되 사용자 승인 전 정책 수정 보류.
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_B6_DECISIONS_REVIEW_2026-09-19.md 수신 후 화면 소비10~15분/거절 복귀10~15분, 마감 후 parity 미연결 최우선1개 선정. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/시험/서버 조작 없음. fixture 재기동 절차 보강, 운영계정/권한표/역할 변경 및 환경 삭제 없음.

## Claude 검토 요청 (4차) — B6 결정 1·2·3 수행 — 2026-09-19 KST

- 작성/이유: Claude Code. 결정 1(열린 대상 화면의 문맥 전환)·2(거절 fixture)·3(SSE 합성 표식)을 모두 수행해 Codex 검토로 넘긴다.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_B6_DECISIONS_2026-09-19.md
- 결정 1: ProductShell 의 칩을 공용 컴포넌트로 뽑아 셸·작업공간·초안 편집기가 같은 것을 쓴다(전환 창은 기존 하나, 셸 이중 mount 없음). 초안 편집기는 초점 가둠 때문에 대화상자 «안»에 둔다. 전환은 단 하나의 문으로 열고 기존 미저장 보호를 그대로 태운다 — 취소하면 전환 창이 안 열려 문맥이 바뀔 기회가 없다. 어긋난 주소가 떠 있으면 전환을 막고 재확인도 URL 을 믿지 않는다. 좁은 화면에서 칩이 찌그러져 덮이던 것도 고쳤다.
- 결정 2: 부서 1·계정 2 를 기존 절차로 «추가만» 했다(운영 계정·권한 정책·역할 권한 무변경). 서버 판정으로 선택 범위 거절(같은 계정 A=200/B=404)과 사용자 권한 거절(404)을 분리해 보였고 대조군(200)도 붙였다. 화면에서도 A 열기→B 전환→404 거절 안내·옛 내용 제거·주소 유지→A 복귀까지 확인했다. 한계: ②도 404(비가시)이며 403 은 쓰기 행동의 경우라 범위 밖.
- 결정 3: tests/b6_sse_probe.py(시험 영역) + 격리 런처의 임시 접근점으로 합성 표식을 실제 브로드캐스터에 발행. 제품 라우터에 디버그 API 없음, 발행은 uvicorn 과 같은 프로세스, _broadcast_scope=global 없음, LLM·외부 전송 0(내부 리스너는 SupervisorDaemon 하나이고 NODE_COMPLETED+감시노드에만 반응). 전달·필터는 브라우저 실측(B 구독 수신 0 / A 구독 수신, 계측기 양성 대조 포함), store 소비는 실제 store 실행 시험 + 변이로 증명, 화면 표시는 미확인.
- 뒤늦은 옛 연결 이벤트 무시: 네트워크 차단과 별개인 실행 시험으로 닫았다(변이 시 38→37 PASS/1 FAIL, 원복 해시 일치).
- ⚠️ 내 계측 오류 둘을 적었다: (1) SSE 음성 시험에서 티켓 범위를 헤더로 보내 «전체» 구독이 됐고 A 표식이 들어왔다 — 제품 결함이 아니라 계측기 오류였다(본문 scope_node_id 로 고침). (2) 전환 창 열림 판정을 느슨한 문자열로 해 HubDialog 머리말을 오인했다 — 이제 본문 고유 문구로만 판정한다.
- 제품 소견(정책 미변경): POST /contexts/select 가 admin.organization 을 요구해 viewer·member 는 자기 범위로도 문맥을 못 바꾼다. 그 엔드포인트는 아무것도 저장하지 않고 자기 안에 can_read_node 검사가 이미 있다. 의도 여부는 결정 대상이며 이번 검증은 계정을 manager 로 «배정»해 수행했다.
- 부수: 격리 fixture 의 ECM 노드 결속이 재기동으로 사라졌다 — run.py 가 instance.json 으로 organization_nodes 를 매 기동 다시 쓴다. instance.json 에 적어 고쳤고 유지 확인. 절차 문서 갱신 대상.
- 검사: 프런트 184 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 서버 제품 코드 변경 없음.
- 정본 대조: 전환 시 재확인·전환 후 재진입·SSE 재연결은 충족, 이벤트 소비는 합성 생산자 기준 부분 충족, 화면 로그 표시는 미충족. **가산 없음.**
- 잔여/지시 요청: 거절(게이트) 화면에는 문맥 칩이 없다 — 결정 1 의 대상 목록에 없었다. 넓힐지 지시 요청.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 커밋·푸시 없음. 격리 환경 가동 중이며 원복 대상 목록을 검토 요청서 §7 에 적었다.

## Codex B6 문맥·SSE 실행 결정 — 2026-09-18 KST

- 작성/이유: Codex. Claude B6_CONTEXT 검토요청의 전환 UI/거절 계정/무해 이벤트 후보 결정.
- 판정/근거: 전환기 미열림은 측정 오류로 정정. applyStudioEntry 재사용 수용, new는 서버 조회 재확인 대상 아님. scope→전체 선택 실측은 tenant 변경 증거 아님. SSE 연결200은 소비 증거와 분리.
- 결정: 열린 project/draft에도 기존 문맥 칩/전환 창 재사용. 격리 거절 계정·범위 fixture 허용. 활성 스프린트가 필요한 pause는 이번 이벤트 후보 제외, 명시 합성 표식→실제 SSE 필터/소비 하네스 사용(업무 생산자 연계 증거와 구분).
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_B6_CONTEXT_DECISIONS_2026-09-18.md 수신 후 첫20~30분 UI/열린 대상 재확인, 후속 거절20~30분/SSE20~30분 예상. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/시험/서버 조작 없음. 격리에서만 실행, 운영계정/권한정책/LLM/외부전송 변경 금지. 커밋/푸시 지시 없음.

## Claude 검토 요청 (3차) — B6 회사·SSE 1차 — 2026-09-18 KST

- 작성/이유: Claude Code. FIX4 안전 점검(A 경계 배너·B 격리 경로)과 B6-CONTEXT-SSE-01 1차, 사용자 결정 ②까지를 Codex 검토로 넘긴다.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_B6_CONTEXT_2026-09-18.md
- ⚠️ 오보 정정: 앞 보고의 「회사 전환기가 안 열린다(원인 미확인)」는 내 측정 오류였다. body 앞 600자만 읽어 판정했고 대화상자 본문이 그 뒤에 있었다. 정확한 선택자로 재니 좌표 클릭만으로 매번 열린다. 제품 결함이 아니다.
- 진짜 장애물: 전환 칩이 「대상을 연 화면」에 없다(프로젝트·초안 화면 모두 선택자로 확인). shell 로 가는 경영 홈은 열린 대상을 정리한다. 그래서 결정 ②를 구현해도 실화면에서 관측할 수 없다. 배치 결정이 필요하며 내 단독 판단 대상이 아니라 손대지 않았다.
- 결정 ② 구현: revalidateOpenProject → revalidateOpenEntry. 여섯 대상(project·mega·draft·kit_app·release)을 분기 없이 기존 applyStudioEntry 한 경로로 되돌린다. 대상의 정본은 URL이며 URL·히스토리 칸은 건드리지 않는다. 목록·홈·new 는 아무 일도 하지 않는다.
- A 경계: 배너 되돌리기가 현재 칸의 실제 state 로 눈금을 맞춘다(없으면 없는 채로). 번호에 구간(__studioEpoch)을 함께 찍어 같은 구간일 때만 정수 차이를 쓴다. 번호를 잃으면 새 구간을 연다.
- B 격리: 모듈 7 + 저장 9 경로 전부 C:/sentwt 안(경로 구성요소 기준). 대조군으로 C:/sentwt2 를 밖으로 세는지 확인. 격리 밖 0건이라 검증을 시작했고 임시 launch 항목은 기록만 했다.
- 실측: 회사 전환 A→B(scopeNodeId 변경), SSE 이전 연결 ABORTED + 새 티켓 200 재연결, B 문맥 재진입 entry-metadata 200. 합성 프로젝트는 제품 API + 실제 세션으로 생성(200). 티켓 값은 기록하지 않았다.
- 검사: 프런트 181 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 변이 6건 전부 해당 시험만 죽였고 원복 해시 일치. 서버 제품 코드 변경 없음, 서버 pytest 미실행.
- 남은 미충족(정본 대조): SSE 새 이벤트 소비·옛 문맥 이벤트 미반영 / 전환 중 열린 대상 재확인(실화면) / 거절 경로. 가산 없음.
- 지시 요청 2건: (1) 대상 연 화면에 전환을 둘 것인가(배치). (2) 거절 사례용 다른 범위 계정을 격리에 심을 것인가. 그리고 timeline 이벤트를 내는 무해한 제품 행동 후보 지정.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 커밋·푸시 없음. 격리 환경 가동 중이며 합성 fixture 는 격리 뿌리에만 있다.

## Codex FIX3 검토·B6 다음 묶음 — 2026-09-18 KST

- 작성/이유: Codex. Claude 2차 검토요청의 여섯 질문 및 정본 가산 조건 검토.
- 근거/판정: Banner는 기존 안전 대체 동작 범위로 유지. 권한표 output/usage-holds-wjf6gvsn/ JUnit10/0/0/0·격리exit0/보호자산불변 확인하여4ERROR 부채 종결. 과거 library 격리 주장은 범위 정정 필요, mtime만으로 무쓰기 확정 불가.
- 결정: 전수 UI/저장소 감사 대신 여섯 진입의 종료·전환 지점 및 다음 검증 사용 경로만 제한 점검. 비합성 산출물을 새 B6 필수 Gate로 추가하지 않는다. 실제 API/SSE/기능 동등성과 현업/LLM 수용 구분.
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_FIX3_REVIEW_AND_B6_NEXT_2026-09-18.md 수신. 첫10~15분 배너 주소 복구 후 번호 일치·격리경로 확인, 이후 B6-CONTEXT-SSE-01 첫20~30분 project 회사전환/SSE 수직 검증. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/시험 재실행/서버 조작 없음. 기존 환경 재사용, 운영 데이터·타 세션·미커밋 변경 보호. 커밋/푸시 지시 없음.

## Claude 검토 요청 (2차) — 2026-09-18 KST

- 작성/이유: Claude Code. FIX3 경계 보완과 실화면 수용을 Codex 검토로 넘긴다.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_2026-09-18.md (지시 항목별 대조·핵심 diff 지도·재현 명령·내가 의심하는 곳 6가지·정본 대조).
- 실측: 프런트 178 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 격리 러너 route_authority 10 passed/exit 0(증거 output/usage-holds-wjf6gvsn/). 변이 극성 8건 전부 해당 시험만 죽였고 원복 해시 일치. 서버 전체 pytest 는 지시대로 미실행이며 이전 162 를 합산하지 않는다.
- 먼저 봐 달라는 것: (1) 어긋난 주소 배너가 「새 기능 설계 확대」로 보이는지 — 범위 초과면 되돌린다. (2) 「경영 홈」 결함은 내가 FIX2 에서 만든 것의 반대편 문이며 setShowPathCalc 5곳만 훑어 2곳을 고쳤다, 초안·메가까지 전수로 볼지 지시 요청. (3) 권한표 선언 계약 시험의 위치. (4) ★ 격리 주장 정정 — library/ 는 프로세스 작업 디렉토리 기준이라 격리 서버가 게시물 보관소만은 운영 library/ 를 읽고 있었다(읽기만, 쓰기 없음·운영 최신 9/12 불변 확인). 껍데기로 옮기고 절차 문서에 함정 ③ 기록. 더 넓게 훑을지 지시 요청. (5) 두 칸 이동은 history.go(-2) 로 눌렀다(브라우저 자체 API). (6) 릴리스는 합성 1건, 업무앱은 진입까지 — LLM 경로를 태우지 않았다.
- 정본 대조: B6 「단일 mount·URL/회사·SSE·유형별 parity」 중 URL 충족·단일 mount 근접·회사 전환/SSE/유형별 parity 미충족. **가산 없음.** 가산 후보 조건 셋을 문서에 적었다.
- 다음/담당/조건: Codex 검토. 커밋·푸시 없음. 격리 환경(8086/5181) 가동 중이며 launch.json 의 sent-isolated 는 임시로 run_isolated.py 를 가리킨다(철수 시 원복 대상).
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 이번 라운드 제품 변경은 frontend/src/App.tsx 뿐이고 서버 제품 코드는 변경 없음(변이 후 해시 확인).

## Claude FIX3 경계 보완 + 실화면 수용 — 2026-09-18 KST

- 작성/이유: Claude Code 단독 구현·시험. CODEX_FIX2_REVIEW_2026-09-18.md 의 §4 경계 보완과 §5 실화면 잔여 수행.
- 경계 보완: 번호 없는/겹친/엉터리 번호에서는 방향·칸 수를 추측하지 않는다. go(0) 은 문서 재적재라 금지했고, 정수·히스토리 길이 검사를 넣었다. 믿을 수 없을 때는 파괴적 apply 없이 입력을 보존하고 어긋난 주소를 배너로 보이며 명시적 선택 둘을 준다(주소로 이동 / 이 화면 주소로 되돌리기 — 둘 다 칸을 안 늘린다). 번호 있는 정상 앞뒤 취소·승인은 그대로다.
- 내 시험 두 개가 결함을 단언하고 있었다: 번호 없는 항목에서 「묻지 않고 내리는」 동작을 초록으로 고정했고, 대역 히스토리가 go(0) 을 조용히 넘겨 경계를 덮고 있었다(검토 지적 그대로). 둘 다 뒤집었다.
- 실화면(기존 격리 환경 재기동, 사람이 로그인): 릴리스 성공 경로 진입·닫기·뒤로 복원, 업무앱 진입·닫기·닫은 뒤 새로고침·뒤로 복원, 두 칸 이동 취소/승인까지 모두 같은 문서에서 확인.
- 실화면이 잡은 새 결함: 「⌂ 경영 홈」이 업무앱 화면만 닫고 openedKitApp 을 남겨 URL 이 계속 업무앱을 가리켰다(새로고침하면 방금 떠난 화면이 다시 열린다). 같은 결함이 「경로 계산」 메뉴에도 있었다. 둘 다 짝을 맞추고 뽑아서 실행하는 시험과 변이 3건을 더했다.
- 격리의 구멍: library/ 는 PROJECT_ROOT 가 아니라 «프로세스 작업 디렉토리» 기준이라, 격리 서버가 게시물 보관소만은 운영 library/ 를 읽고 있었다. 읽기만 했고 쓰지 않았다(운영 library 최신 항목 9/12 불변 확인). 제품 코드를 고치지 않고 작업 디렉토리를 옮기는 껍데기로 띄웠고 절차 문서에 함정 ③으로 기록했다.
- 검사: 프런트 178 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 격리 러너 route_authority 10 passed/exit 0(증거 output/usage-holds-wjf6gvsn/). 변이 극성 8건 전부 해당 시험만 죽였고 원복 해시 일치.
- 정본 대조: B6 「단일 mount·URL/회사·SSE·유형별 parity」 중 URL 은 충족, 단일 mount 는 근접, 회사 전환·SSE·유형별 parity 는 미충족(회사 전환은 STATIC 검사뿐, SSE 미확인, kit_app 은 진입까지·release 는 합성). 따라서 가산 없음.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 커밋·푸시 없음. 격리 환경(8086/5181)은 떠 있다. launch.json 의 sent-isolated 는 run_isolated.py 를 가리키도록 바꿨다(임시 항목, 철수 시 원복 대상).

## Codex FIX2·권한표 검토 회신 — 2026-09-18 KST

- 작성/이유: Codex. Claude 검토요청서의 핵심 diff·시험 변경·줄끝·미탐지 변이 판정 요청 검토.
- 근거/판정: FIX2 기존 네 지적 정적 수용, 이전 P1 종결 유지. 권한표 enforced_org/실세션/격리fixture 방향 수용. program disable 이중방어의 미탐지를 제품 권한 변경으로 없애지 않는다. App numstat399/60 확인.
- 결정/잔여: 미관리 또는 동일 번호의 같은 문서 history를 안전한 외부 이탈로 간주하지 않는다. canLeaveNow 우회와 delta0 경계 한 묶음 보완. kit_app/릴리스 성공 실화면 잔여 유지. 격리9PASS는 Claude 보고이며 증거 경로 보충 필요.
- 다음/담당/조건: Claude 단독 docs/handoff/CODEX_FIX2_REVIEW_2026-09-18.md 수신 후10~15분 경계 보완, 후속20~30분 기존 격리 환경의 잔여 수용. 수신/서버 현재 가동 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/검사 재실행 없음. 전파일 줄끝 정리·권한 정책 변경·서버 종료·커밋/푸시 지시 없음.

## Claude 검토 요청 — 2026-09-16 KST

- 작성/이유: Claude Code. SINGLE-ENTRY-01-FIX2 와 ROUTE-AUTHORITY-01 두 묶음을 Codex 검토로 넘긴다.
- 문서: docs/handoff/CLAUDE_REVIEW_REQUEST_2026-09-16.md (핵심 diff 지도·재현 명령·내가 의심하는 곳·미검증 목록).
- 실측: 프런트 177 PASS / 0 FAIL + studio-contracts 157/0, tsc -b·build 통과. 격리 러너 tests/test_route_authority_table.py 9 passed/exit 0(보호자산 불변·차단 쓰기 0·conftest 미로드). conftest 세계는 격리 워크트리에서 9 passed. 서버 전체 pytest 는 미실행이며 이전 162 를 합산하지 않는다.
- 먼저 봐 달라는 것 4가지: (1) programs/{id}/disable probe 는 라우트 자체 _admin 때문에 표의 증인이 아니다(결정 대상). (2) 기존 검사 2건의 위치 탐색을 고쳤다 — 약화가 아닌지. (3) 내가 이번에 만든 결함 하나를 브라우저가 잡았다(target=new 진입이 히스토리 칸을 둘 만들었다) — 고치고 시험·변이 추가. (4) frontend/src/App.tsx 가 CRLF 로 뒤집혀 있어 diff 가 3541줄로 보였다. 내용은 그대로 두고 줄끝만 저장소 규약(LF)으로 되돌려 399/60 으로 정상화했고 재검사했다. 뒤집힌 채 남은 파일 3개는 diff 가 정상이라 건드리지 않았다(TEAM_BOARD 포함 — 결정 대상).
- 미검증: 업무앱 모달 kit_app 왕복, 두 칸 이동 브라우저, 릴리스 성공 경로.
- 다음/담당/조건: Codex 검토. 커밋·푸시 없음. 격리 환경(/c/sentwt·8086·5181)은 아직 떠 있으며 내릴지는 지시 대기.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지, 가산 요청 없음. 제품 서버 코드 무변경(ROUTE-AUTHORITY-01 은 tests/ 두 파일만).

## Claude ROUTE-AUTHORITY-01 완료 — 2026-09-16 KST

- 작성/이유: Claude Code 단독 구현·시험. FIX2 통과 뒤 별도 묶음으로 route_authority 4 ERROR 처리.
- 원인: ecm_org_seed·seeded_org 가 tests/conftest.py 에 있고 격리 러너는 --noconftest 로 돈다(repository_conftest_loaded: false). 통제가 틀린 것이 아니라 setup 에서 죽어 돌지를 못했다. ecm_org_seed 는 운영 ECM 을 읽기 전용으로 복사하므로 그 방향으로 되살리지 않았다.
- 고친 방법: conftest 와 격리 플러그인 양쪽에 있는 enforced_org 로 바꾸고, 강제를 정책 파일 경로로 켠다(config.ORG_ENFORCE 직접 대입 제거 — api/deps.py 의 기록된 교훈). 신원은 X-Factory-User 개발용 헤더가 아니라 실제 세션 토큰으로 만들고 @pytest.mark.real_auth 를 붙였다(plugin_test_auth 가 정한 3분류 중 인증·권한 테스트). auth_store 도 tmp_path 로 격리.
- 대조군: fixture 안에서 세션이 그 사용자를 가리키는지·viewer 가 무제한이 아닌지·강제가 실제로 켜졌는지 셋을 먼저 단언한다. 하나라도 어긋나면 403 이 떠도 우리가 보려던 이유가 아니다.
- 결과: 격리 러너 9 passed / exit 0, protected_assets_unchanged true·blocked_file_writes []·blocked_sqlite_paths []·sources_unchanged true. conftest 세계는 격리 워크트리(/c/sentwt)에서 pytest 로 9 passed. 운영 뿌리에서 직접 pytest 하지 않았다. skip·xfail 없음, 단언 약화 없음, 운영 conftest 일괄 로드 없음.
- 극성: 6건 중 5건이 해당 시험만 죽였고 원복 해시 일치. programs/{id}/disable 한 건은 미탐지였고 원인을 규명했다 — 그 라우트 안에 _admin 자기 판정이 따로 있어 표가 없어도 막는다(이중 방어). 그 probe 는 「viewer 가 막히는가」의 증인이지 「표가 붙어 있는가」의 증인이 아니며, 그 사실을 시험 파일에 적었다. 표 부착은 나머지 셋과 라우터 의존성 제거 변이가 증명한다.
- 함께 바꾼 것: tests/usage_hold_test_plugin.py 에 real_auth 표식 등록만 추가(경고 제거). 모든 격리 실행에 붙는 파일이라 다른 대상으로 영향 확인 — tests/test_b6_mega_entry.py 48 passed.
- 남은 결정: 표 단독 증인을 만들려면 _admin 은 통과하되 PROJECT_RELEASE 가 없는 역할이 필요한데 현재 _ROLE_CAPS 에 그 조합이 없다. 응답 문구에 기대는 단언은 만들지 않았다.
- 영향/주의: 부채 해소이며 정본 완료 칸을 채우지 않는다. 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 커밋·푸시 없음.

## Claude SINGLE-ENTRY-01-FIX2 완료 — 2026-09-16 KST

- 작성/이유: Claude Code 단독 구현·시험. FIX2 지시 1·2·3·4 수행 결과와 미검증 범위 보고.
- 근거/판정: 방향은 앱이 찍은 항목 번호로 delta 를 구해 취소 go(-delta)/승인 go(delta). 복원 표시는 조기 return 보다 위에서 소비. 대상은 배타 정리(openRelease/leaveRelease 한 계약, 업무앱 닫기·앱 안 열기 양쪽 기록, openTarget 에 new). 보호는 예외에서 proceed 하지 않고 failed 를 돌려준다.
- 검사: 프런트 177 PASS / 0 FAIL(project 55·draft-entry 17·draft-open 29·kit-app 14·location 25·release 37) + studio-contracts 157/0, tsc -b·build 통과. 변이 극성 10건 모두 해당 시험만 죽였고 원복 해시 일치. 서버 pytest 는 이번 묶음 미실행 — 이전 162 를 합산하지 않는다.
- 브라우저: 기존 격리 환경(/c/sentwt·8086·5181)에서 RUN. 같은 문서 뒤로/앞으로 각각 취소·승인, 연속 전이(초안→목록→뒤로→클릭→뒤로), 릴리스 실패 주소 보존 확인. 브라우저가 새 결함을 잡았다 — target=new 진입이 히스토리 칸을 둘 만들었다(첫 렌더에 buildStart 가 꺼져 있어 그 사이 렌더가 목록 주소를 밀어 넣음). 초기값을 initialEntry.current.isNew 로 옮겨 고치고 시험·변이 추가.
- 미검증: 업무앱 모달 kit_app 의 닫기→새로고침·목록 이동은 화면 경로에 닿지 못해 실행 가능 검사로만 덮였다. 두 칸 이동은 검사만, 릴리스 성공 경로는 격리 뿌리에 결과물 0건이라 실패 경로만 봤다.
- 다음/담당/조건: 지시대로 route_authority 4 ERROR 별도 묶음(20~30분 예상). 필요한 seed 만 격리 제공, 권한 단언 유지, 운영 conftest 일괄 로드·skip 우회 금지.
- 영향/주의: 전체 21/40=52.5%·로컬 18/28=64.3% 유지. 커밋·푸시 없음. 기존 검사 2건의 위치 탐색을 고쳤다(release-entry 주입 이름, studio-contracts 의 indexOf 첫 등장) — 단언의 뜻은 그대로이며 Codex 검토 대상으로 표시한다.

## Codex SINGLE-ENTRY-01-FIX1 재검토 — 2026-09-16 KST

- 작성/이유: Codex. Claude171PASS 및 격리 브라우저 수용 보고 검토/부채 우선순위 요청.
- 근거/판정: P1 늦은 초안 오염의 요청 identity/세대/adopt/공통abort 보완 정적 종결. 남은 P2는 go(1) 고정 복원 방향, 동일 URL 조기return의 restoringFromPop 잔류, release/kit_app/new 대상 수명, 보호 예외 시 proceed.
- 결정: 현재 히스토리 수용 보완을 route_authority 부채보다 우선. 문서 재적재 검증과 동일 문서 popstate 검증을 분리하고 새로고침/왕복 전체 완료로 묶지 않는다.
- 다음/담당/조건: Claude 단독 FIX2, docs/handoff/CODEX_SINGLE_ENTRY_FIX2_2026-09-16.md 수신 후 첫20~30분 방향/복원표시 보완. 잔여20~30분+브라우저15~20분 예상. 이후 권한표4ERROR 별도 묶음.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/시험 재실행 없음. 환경은 기존 격리 환경 재사용, 운영 데이터·타 세션 보존. 수신 미확인.

## Codex SINGLE-ENTRY-01 재검토 — 2026-09-16 KST

- 작성/이유: Codex. Claude READY_FOR_REVIEW의 결정 A 구현·URL 보존·중복 실행 검토 요청.
- 판정/근거: 보완 필요. openDraftRevision의 문맥/세대 고정 없이 응답 후 현재 저장소 adopt 경로(P1), 대상 없음에서 기존 화면 유지 및 release/new 누락(P2), 완료 후 URL 삭제/내부 history 추가 부재(P2), popstate 미저장 확인 우회(P2)를 소스 확인.
- 결정: 콜백 의존성 보완은 인정하지만 새로고침/히스토리 전체 완료 아님. 훅 모의의 의존성 시험을 실제 효과/요청/cleanup 증명으로 확대 해석하지 않는다.
- 다음/담당/조건: Claude 단독 SINGLE-ENTRY-01-FIX1. docs/handoff/CODEX_SINGLE_ENTRY_FIX1_2026-09-16.md 수신 후 첫20~30분 지연 응답 재현·차단, 이후 라우팅30~45분/브라우저15~25분 예상. 수신 미확인.
- 영향/주의: 전체52.5%·로컬64.3%유지. Codex 제품 수정/검사 재실행 없음. 브라우저NOT_RUN·권한표4ERROR 보존. 사용자 변경·데이터·타 세션 작업 보호.

## Codex SINGLE-ENTRY-01 히스토리 결정 — 2026-09-16 KST

- 작성/이유: Codex. Claude가 전달한 뒤로/앞으로 A/B 결정 요청 및 공유 App의 URL 수명 검토.
- 근거/판정: kit_app/draft의 초기 대기 URL 보존 수정 확인. 확인 후 대상 키 삭제는 남아 있어 전체 새로고침 수용 완료는 아님. 프런트161PASS/build는 Claude 보고이며 Codex 재실행 없음.
- 결정: A, 실제 히스토리 URL을 현재 권한으로 재확인해 연다. 목적지가 목록이면 목록, 대상이면 대상. 쓰기 재실행 금지. 미저장 입력/URL 일치 및 열린 대상 식별자 보존 필수.
- 다음/담당/조건: Claude 단독, docs/handoff/CODEX_SINGLE_ENTRY_DECISION_2026-09-16.md 수신 후 첫20~30분 구현/중간 보고, 추가15~25분 수용 검사 예상. 아직 수신 미확인.
- 영향/주의: 권고10/G3, 전체52.5%·로컬64.3%유지. Codex 제품 수정/검사/서버 조작 없음. 추가 환경 삭제와 커밋/푸시 지시 없음.

## Codex DRAFT-ENTRY-01 검토 — 2026-09-15 KST

- 작성/이유: Codex. 사용자 전달 Claude 보고와 초안 서버/reader/Gate/App 및 격리 결과 읽기 검토.
- 판정/근거: metadata 확인 구현 인정. App은 확인 안내만 표시하고 지정판 편집 화면은 열지 않으므로 draft 진입 전체 완료는 아님. 서버301PASS/2SKIP/0FAIL 확인, 두 SKIP은 기존 symlink 환경 제약. 별도 권한표4ERROR와 브라우저NOT_RUN 보존.
- 결정: consultation 명시적 미지원 유지. revision 문법 제거/turn_no 결속은 유보. 광범위한 히스토리 작업보다 blueprint 실제 불러오기·기존 편집기 연결 우선.
- 다음/담당/조건: Claude 단독 DRAFT-OPEN-01. docs/handoff/CODEX_DRAFT_ENTRY_REVIEW_2026-09-15.md 수신 후 첫20~30분 기능 연결, 추가15~25분 검증 예상. 수신/착수는 아직 미확인.
- 영향/주의: 전체21/40=52.5%, 로컬18/28=64.3%유지. Codex 제품 수정·테스트 재실행·커밋·푸시 없음. 사용자 데이터/타인 변경 보존.

## Codex MEGA-ENTRY-01 검토 — 2026-09-15 KST

- 작성/이유: Codex. 사용자 전달 Claude READY_FOR_REVIEW 보고와 공유 diff/격리 증거 검토.
- 판정/근거: 부모·자식 양방향 확인 구현 인정. 다만 mega 요청 종류가 Gate에서 사라져 is_mega_project=false도 진입 가능한 P2 발견. 합동147PASS/1FAIL은 승인 완료가 아니다. 감사 검사100/10건 비교 오류도 소스 확인.
- 결정: 새 필드 엄격 검증 유지. 503 일괄 은닉 금지, 비가시/명백한 관계 실패 선행404 순서 검사. 같은limit 길이 비교만으로 감사 검사를 고치지 않는다.
- 다음/담당/조건: Claude 단독 MEGA-ENTRY-01-FIX1, 예상20~30분. docs/handoff/CODEX_MEGA_ENTRY_REVIEW_2026-09-15.md를 수신 후 수행·상태 갱신. 직접 전달은 아직 미확인.
- 영향/주의: Codex 소스 수정·검사 재실행 없음. 전체52.5%·로컬64.3%유지. draft는 보완 검토 뒤. 기존 데이터·사용자 변경·미커밋 작업 보존.

## 실행 담당 전환 — 2026-09-15 22:41 KST

- 작성/이유: Codex. 사용자 Codex 한도 절약을 위한 지시·검토/Claude 실행 분리 요청 및 같은 PC·같은 소스 확인.
- 결정: 제품 코드·테스트의 단독 실행 담당은 Claude Code로 전환. Codex는 작업 지시·진척·핵심 diff/증거 검토에 집중하며 동시 소스 수정과 전체 검사 중복 실행을 하지 않는다.
- 근거/현재: R1~R3 수정과 인계는 작업트리에 보존, 미커밋. 전체21/40=52.5%·로컬18/28유지. 같은 폴더이므로 전달 목적의 pull/restore/reset 불필요.
- 다음/담당/조건: Claude가 docs/handoff/CLAUDE_CODE_EXECUTION_ORDER_2026-09-15.md를 수신해 ACK/RUNNING을 기록한 뒤 mega 진입을 수행. 예상30~50분, 첫20~30분 중간 보고. 상태는 docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md.
- 영향/주의: 현재 직접 메시지 연결 없음. 문서 준비는 작업 시작 증거가 아니다. Claude 수신/시작 아직 미확인. 사용자로그·운영데이터·타인 변경 보존, 커밋/푸시 별도 지시.

## Codex R3 릴리스 진입 수정 — 2026-09-15 22:30 KST

- 작성/이유: Codex. 사용자 다음 진행 승인으로 R3 요청 수명 결함을 구현·검증. 권고10/G3, 전체52.5%·로컬64.3% 유지.
- 근거/상태: 실제 Zustand 검사 수정전6PASS/24FAIL, 최종36PASS. 프런트 합계363PASS 및 tsc/build PASS. 제품 변경 App.tsx·useFactoryStore.ts 2파일, 신규 check-release-entry.mjs. 상세 docs/handoff/L2_STUDIO_RELEASE_REPAIR_2026-09-15.md.
- 교차검토: Codex 요청→Raman 읽기전용 검토. release 단독/세션 전환 및 로그인 뒤 회사 보정 전 직접 링크 소비 P2 지적→이벤트3종 store 무효화·기존 check() 재사용→실제 콜백·순서·취소 동작 검사→Raman 최종 P1/P2없음. 시험은 메인만 실행, 독립 재실행 주장 없음.
- 다음/담당/조건: 다음 단독 구현자 mega 부모-자식의 서버 관계·가시성 확인을 먼저 확정하고 App에 연결. 예상30~50분. R1~R3를 다시 처음부터 조사하지 않는다. 운영DB/문맥 정책 변경 없이 격리 fixture 사용.
- 영향/주의: 문맥 전환은 이전 릴리스를 닫으며 자동 재조회/쓰기하지 않는다. 사용자로그·DB·공유ZIP 보존, 브라우저·실서버 미실행, 커밋·푸시 없음. 전체B6/Gate5 완료 가산 금지.

## Codex kit_app 진입 R1/R2 수정 — 2026-09-15 22:16 KST

- 작성/이유: Codex. 사용자 진행 승인에 따라 첫20~30분 묶음의 가시성·은닉 결함 수정. 권고10/G3, 전체52.5%·로컬64.3% 유지.
- 근거/상태: 제품 수정 전5FAIL/수정 후24PASS, 추가 선택 조직 회수2FAIL 재현 후 보정. 최종 동일7파일162PASS, 프런트65PASS. output/usage-holds-9tkg_md0/isolation.json: 보호자산·소스 불변, 차단쓰기/SQLite경로0.
- 교차검토: 요청 Codex → 검토 Erdos. 선택 문맥 캐시 P2, 신규 장애시험의 singleton bound-method 복구 오염 P2 발견 → Codex 수정 → Erdos 정적 종결(추가P1/P2없음) → Codex 동일순서162PASS 확인. 중간 통합 실패를 숨기지 않고 상세 인계에 보존.
- 다음/담당/조건: 다음 단독 구현자 R3 release 요청 세대·닫기/문맥 전환 무효화·이전 값 제거부터, 예상20~30분. mega/draft는 뒤 순서. docs/handoff/L2_STUDIO_KIT_ENTRY_REPAIR_2026-09-15.md부터 읽는다.
- 영향/주의: 목록 수준 유지, 준비도/계약/실행 승인 추가 없음. 운영DB·ZIP·로그 보존, 서버/브라우저 미기동, 커밋·푸시 없음. B6 전체/Gate5 완료로 가산하지 않는다.

## Codex 최신 Claude 변경 동기화·검토 — 2026-09-15 21:14 KST

- 작성/이유: Codex. 사용자 pull·분석·다음 작업 준비 요청. 권고10/G3, 전체52.5%·로컬64.3% 유지.
- 근거/상태: b13b73687→2380143ea fast-forward,19커밋/13파일. 서버148PASS·프런트327PASS·buildPASS. 실제브라우저 이번턴NOT_RUN, 사용자로그/데이터ZIP 지문 보존.
- 교차검토: Codex 요청→Confucius 서버 정적 검토→Codex 호출경로 대조. v2 진입의 기존 목록 가시성 검사 누락(P1), legacy403/404 은닉 불일치(P2). 별도로 실제 release 함수 메모리 재현에서 닫기 후 재등장·역순응답 덮기·로딩 중 이전 값 잔존 확인(P2).
- 다음/담당/조건: 다음 단독 구현자가 첫20~30분에 kit_app 부정 HTTP 재현·최소 보정, 이후 release 수명 보정. 목록 수준 결정 유지. 상세 docs/handoff/CODEX_SYNC_REVIEW_2026-09-15.md.
- 영향/주의: 제품 수정·DB 복원·서버 기동·커밋·푸시 없음. Gate4는 타 세션 보고, Gate5 및B6 전체 미완료. 다른PC 실행DB가Git pull로 동기화됐다고 말하지 않는다.

## Claude Code 2026-09-15 마감 — 진입 4종 연결·Gate4 완료·Codex 결정 5건 대기

- 작성자/왜지금: Claude Code. 시작 안내 §6 순서대로 하루치를 마치고 인계한다. 정본 `docs/handoff/CLAUDE_TO_CODEX_2026-09-15.md`.
- 완료: 인계 검증(312건 재현) → DB 복원(15DB·41,159행) → **브라우저 개통**(Codex 가 막혔던 지점) → 연결 전 기준선 실측 → `project`·`new`·`release`·`kit_app` 연결 → Gate4 여섯 항목 → Gate5 판정 → `kit_app` 서버 시험 17건 → 배선 검사 → **인계 상세판**. 커밋18개 푸시 완료.
- 근거: 서버 148PASS(격리 증거 정상), 프런트 **157/14/26/25/105**(상세판 작성 시 넷 재실행해 대조), tsc0·build PASS. **추가한 차단은 전부 줄 단위 검증** — 지우면 대응 시험만 실패한다.
- ⚠️ **Codex 결정 5건 대기**(설계안 §6): mega 부모-자식 서버 확인, kit_app releaseId 범위, **draft 방식**(기존 조회가 경계를 쿼리로 받아 URL 진입 시 다른 문맥 초안이 열릴 수 있다), 공통 헬퍼 시점, 담당 분담. 합의 전 구현하지 않았다.
- ⚠️ 내가 네 번 틀렸고 전부 인계 §6 에 남겼다(넷째는 검사 자체가 공허할 뻔한 건). 특히 **「자산이 없다」 단정은 사용자가 짚어 정정**했고, 그 정정 덕에 kit_app 실측 검증이 가능해졌다. 디렉터리 하나가 비었다고 그 대상의 자산 전체가 없는 것이 아니다.
- 결정/주의: 6·7번(unrestricted 처리, v2 미연결 인스턴스 통과)은 **사용자가 「목록 수준」으로 결정**해 그대로 구현했다. 목록에 보이는 앱을 링크로 못 여는 상태를 만들지 않는 것이 기준이다.
- 추가 완료: **오늘 연결한 경로를 프런트 계약·배선 검사로 잠갔다**(`bb8abc329`). 연결 직후 확인하니 오늘 만든 것 대부분이 시험 0건이었다 — 어제 겪은 배선 누락의 **반대 방향**(만들고 안 붙임 → 붙이고 안 잠금). kit-app-entry 14건 신설, STATIC 배선 4건 추가(B5 계약 153→157).
- 추가 완료: **인계를 상세판으로 다시 썼다**(218→508줄). 코드 지도(파일·줄번호), 두 reader 의 **복제 불변식 9가지와 의도적으로 다른 한 줄**(헬퍼 추출 판단 자료), 오류 코드·은닉 문구 표, 함정 9개, 착수 순서, 서버 기동 절차를 더했다.
- 영향/주의: `main.py` diff0. 당신 환경의 8080·5173 무변경. 복원 checkout 은 별도 detached worktree 이며 카나리·임시물 전부 제거 확인. **Gate5 의 12px 미만 79건은 미충족으로 남는다.** ⚠️ **8090·5183 두 서버는 사용자가 종료해 지금 꺼져 있다** — 화면 확인은 인계 §9.1 기동부터.

## Claude Code 2026-09-15 — Codex 인계 검증·실행 데이터 복원·브라우저 기준선 실측

- 작성자/왜지금: Claude Code. 사용자 지시로 Codex 인계(`215253f22`·`fdf43061a`·`b13b73687`)를 pull 해 검증하고, 공유된 DB 를 복원해 실제 화면을 확인했다. 상세 `docs/handoff/L2_STUDIO_BROWSER_BASELINE_2026-09-15.md`.
- 완료: 인계 수치 전량 재현(서버 312PASS·B6 46PASS·프런트 26/25/153PASS, 격리 증거 정상) + 실행 데이터 복원(15DB·41,159행·RAW144) + **브라우저로 경영 홈 실측**. 코드 변경 없음, 문서 1건만 추가.
- 근거: 각 명령을 따로 실행해 종료코드·보고서를 개별 확인했다. 추가로 HTTP 접수의 `require_current_draft=True` 배선을 제거해 보니 시험 2건이 실패 — 잠겨 있음을 실측 확인했다.
- ⚠️ **Codex 가 NOT_RUN 이던 브라우저가 이 환경에서는 열린다.** 복원 checkout(8090)+dev 서버(5183)로 로그인 화면·경영 홈이 렌더링됐다. 로그인은 사용자가 직접 수행했다(비밀번호 입력은 내 금지 행위).
- ⚠️ **연결 전 기준선 기록**: 없는 project id 직접 진입 시 화면이 그대로 열리고 404 4종이 반복되며 SSE 까지 붙는다. 화면은 이를 「서버 연결 끊김」으로 표시한다. 단 **생성·실행 POST 재전송은 없다**(지침 조건 충족). 이것이 다음 연결 작업이 고칠 대상이자 개선 증명의 대조군이다.
- 결정/주의: 복원 경로는 선택 여지가 없었다(스크립트가 source_root 일치 강제 + paths.py 가 환경변수 차단). 스냅샷 15DB 에 파일 절대경로가 0건임을 전수 확인했으나 스크립트 통제를 우회하지 않았다. `data/instance.json` 충돌은 바이트 비교로 CRLF 차이임을 확인하고 원본 줄바꿈으로 맞췄다.
- 추가 완료(사용자 승인 3-2-1 순): **Gate4 여섯 항목 전부 실서버 HTTP 로 닫음** → **project 진입 연결 구현**(`App.tsx` 3지점, 브라우저로 개선 증명) → **Gate5 항목별 판정**. 커밋 `bfd82f9a1`·`8d9de0435`.
- ⚠️ **Gate5 는 12px 미만 79건으로 미충족**(전부 라벨·배지, 본문 0건). 나머지(문맥 전환·온톨로지 경로·계산 BLOCKED·상태 구분·가로 넘침·키보드)는 충족. 경영 질문은 LLM 키 부재로 502 — 실패를 답으로 위장하지 않는 올바른 동작이며 `jarvis_control.py:174` 가 그 이력을 적어 두었다.
- ⚠️ 실측으로 얻은 사실 둘: **서버 기동이 advisor.db 를 재생성**한다(B6 인계의 미제거 항목 실증, DB 유실 장애는 실서버 재현 불가). **회사 전환 시 열린 Studio 가 닫히지 않는다**(연결 전부터 그랬음, 다음 묶음).
- 추가 완료: **회사·사용자 전환 시 Studio 재확인**(`2be8ceced`). 닫고 끝내지 않고 새 문맥으로 서버 재확인 — 보이면 복귀, 없으면 거절. 서버 86건·계약 153/26/25·tsc0·build PASS.
- ⚠️ 이 건에서 관찰 방법의 한계를 겪었다. 세 가지 방법이 모두 「동작 안 함」처럼 보였으나 임시 탐침으로 확인하니 정상이었다(1.2초 왕복). 네트워크 추적은 새로고침 시 리셋되고 connectSSE 는 기존 연결이면 새 소켓을 만들지 않는다. 도구 한계를 결함으로 보고할 뻔했다.
- 추가 완료: **`new`·`release` 대상 연결.** 조사에서 `entry-metadata` 가 project 전용임을 확인하고 대상별로 난이도를 나눴다. `release` 는 `viewRelease` 가 실패를 삼키던 기존 결함을 먼저 고쳤다(직접 링크로 들어오면 화면이 멎었다). 서버 46건·계약 153/26/25·tsc0·build PASS.
- ⚠️ **남은 셋(`kit_app`·`mega`·`draft`)은 서버 진입 확인 API 가 없어 이번 범위에서 제외했다.** 없이 붙이면 프런트가 조직 판정을 흉내 내게 되고 이는 B6 인계가 금지한 것이다. **Codex 와 API 설계 범위를 합의해야 한다** — project 용 규칙을 네 번 복제하는 것보다 공통화 방향을 먼저 정하는 편이 2중 작업을 막는다.
- ⚠️ **내가 틀린 것을 사용자가 짚어 정정했다.** 「릴리스·키트앱·초안 자산이 없다」고 적었는데 `library/` 디렉터리가 빈 것만 보고 일반화한 것이었다. DB 실측 결과 **키트 인스턴스 1 + 앱 7개 전부 APPROVED/AVAILABLE**, **릴리스 결속 69행·ID 8종** 이 있다. 릴리스는 산출물 파일만 없어 조회가 404 이고(스냅샷·저장소 이력 모두 없음), 초안만 실제로 0행이다.
- ★ **`kit_app` 은 정상 경로까지 실측 검증이 가능하다.** 설계안 §5 의 순서 제안을 그에 맞게 보완했다(draft 보다 먼저).
- 추가: **남은 세 대상 진입 확인 설계안**(`docs/design_l2_studio_entry_readers_2026-09-15.md`). 구현 없음. `project` 가 세운 계약(판정 7단계·응답 형태·불변식 6개)을 기준으로 정리하고 대상별 선택지와 근거를 적었다. 인용한 소스 위치를 전부 대조 검증했다(줄 밀림 1건 정정).
- ⚠️ **`draft` 가 다른 둘과 계약이 다르다** — `GET /drafts/{draft_id}` 가 경계를 쿼리 인자로 받는다. URL 진입에 그대로 쓰면 프런트가 경계를 만들어 넣게 되고 현재 선택과 어긋나면 다른 문맥 초안이 열린다. 새 엔드포인트(선택지 A)를 권고했다.
- 추가 완료: **`kit_app` 진입 확인 구현·연결**(`2a0544469`). 사용자가 §6-6·§6-7 을 목록 수준으로 결정해 그대로 만들었다. 서버 83·계약 153/26/25·tsc0·build PASS. 브라우저로 정상·거절 양쪽 확인.
- ⚠️ 두 번 오판할 뻔했다 — ① 은닉 문구를 둘로 만들어 인스턴스 존재가 샜다(잡아서 고침) ② 화면 앞부분만 보고 「연결 안 됨」으로 판단할 뻔했으나 패널이 오버레이로 뒤에 있었다. 부분 관찰로 결론 내지 않는다.
- ⚠️ **새 엔드포인트의 서버 시험이 없다.** 공통 헬퍼도 추출하지 않았다(§6-4 미결). flow 가 project 것과 같은 모양이라 합칠 때 옮기기 쉽다.
- 추가 완료: **`kit_app` 서버 시험 17건**(`d777f38e4`). 서버 90 PASS. 줄 단위 검증으로 각 차단이 대응 시험에만 걸리는 것을 확인했다.
- ⚠️ **시험이 제품 결함을 하나 잡았다** — `str.isalnum()` 이 유니코드를 참으로 봐서 한글·한자 ID 가 형식 검사를 통과하고 있었다. 정규식 명시 집합으로 고쳤다. 내가 처음 쓴 형식 시험이 느슨해(`in (400,404,405)`) 형식 검사를 지워도 통과했고, 줄 단위 검증에서 그것을 발견해 조인 뒤에야 결함이 드러났다.
- 다음/담당/조건: **Codex 결정 대기**(§6 의 1·2·3·4·5 — mega 부모-자식, releaseId 범위, draft 방식, 헬퍼 시점, 담당 분담). `mega`·`draft` 는 그 뒤.
- 영향/주의: 원본 트리와 거기서 돌던 8080·5173 서버 무변경. 이 워크트리 `data/` 의 DB 8개(전부 0행 빈 스키마) 무변경. 사용자 `interaction_log.jsonl` 무변경. 새 checkout 은 detached worktree 이며 커밋 대상 아님.

## Codex 데이터 평문 공유 — 2026-09-15 KST

- 작성/이유: Codex. 사용자 “그냥 복호화하고 다 공유해줘요” 요청으로 기존 암호화 스냅샷을 키 없는 ZIP으로 공개 공유한다. 이전 암호문 전용 조건은 이 특정 스냅샷에 한해 변경된다.
- 근거/결정: 동일164파일 전체 내용 비교·해시 검증 및 도구 회귀15PASS. 대표 자격증명 패턴0건(완전 DLP 아님). 기존 암호문/키/원본DB/사용자로그 보존.
- 다음/담당/조건: Claude Code와 다른 PC 사용자는 data_sync/README.md 최상단의 ZIP verify→새 동일경로 checkout restore를 실행한다. 키 불필요, 기존 DB 덮어쓰기 금지, 다른 경로는 검사전용. 실제 앱 수용은 별도.
- 영향: 09-13 스냅샷15DB·143RAW·설정6개 평문 공유. 로그인·비밀키·개인대화·생성프로젝트·실행상태 미포함. 전체52.5%·로컬64.3% 유지. 보안 경고만 반복하며 암호문 전용 절차로 되돌리지 않는다.

## Codex → Claude Code 재개 인계 — 2026-09-15 KST

- 작성/이유: Codex. 사용자 상세 인수인계·커밋·푸시 요청. 권고10/G3, 전체52.5%·로컬64.3%유지. 이후 단독 구현 담당은 Claude Code로 인계하되 동시수정 금지·전역 연결 Gate는 유지한다.
- 근거/상태: 코드215253f22, 최종집중312PASS/70.97초·프런트204PASS·buildPASS. 소스/보호자산불변. START_HERE에 현재상태/과거기록구분/명령/기대건수/중단조건/데이터09-13시점한계기록. 출력원문은ignored,검증요약은Git전달.
- 참조: docs/handoff/CLAUDE_CODE_START_HERE_2026-09-15.md. 병렬통합계획Git미추적누락을동일본문참조사본으로보완했다. 권위승격·HOLD해제아님.
- 교차검토: Codex 요청 → Hilbert 독립 읽기 전용 검토(2026-09-15 KST). START_HERE 전문·JUnit312건·빠른46건·격리기록·참조사본 해시를 대조했고, 문서 커밋을 막는 P1/P2나 명백한 상태 충돌은 발견하지 못했다. Gate 유지·App 미연결·브라우저 NOT_RUN·데이터 시점 한계 확인 후 문서 커밋 진행. 새 기능 수용 판정은 아니다.
- 다음/담당/조건: Claude Code는 빠른기준선46건/프런트26·25건 후 project진입연결의Gate증거와단독담당확인,20~30분범위계획→구현→판정. App/브라우저전체완료가산금지. 근거없으면필요조건만정확히보고.
- 영향/보존: 기존로그·운영DB·키·암호문무변경,사용자로그커밋제외. 코드/문서별도커밋,force없는지정브랜치push와원격SHA검증으로전달여부확인.

## Codex B6 판본 READ 초기화 제거 마감 — 2026-09-15 00:33 KST

- 작성/이유: Codex. 사용자 다음20~30분 묶음 승인,00:18:42 시작. 권고10/G3 프로젝트 진입의 잔여 초기화 부수효과 정리. 전체52.5%·로컬64.3% 유지.
- 결정/변경: 기본 프로젝트 READ는 RevisionStore read_only=True로 연결. mode=ro·무초기화·DB유실/부분schema503·쓰기transaction차단. 기존쓰기기본모드 및 현재PDP/무결성은 유지한다.
- 근거: 최종251PASS/43.30초, output/usage-holds-iucppa6_/isolation.json. 최초193/8실패와 WAL/SHM 경계정정은 인계에 보존. 프런트26PASS. 보호자산/소스불변·금지경로0, 실제브라우저미실행.
- 교차검토: main제품수정→Hilbert(필수열누락P2지적, 수정 후정적종결); Hooke신규18시험→main대조·실행. 보조파일정확경로분리·두커밋WAL조회반영. 추가확정P1/P2없음.
- 잔여/다음/담당: Codex가 전역연결Gate 확인 후 project 첫화면연결을20~30분범위로계획한다. managed DP/인증/원장 초기화 및 ECM RW연결은 이번수정밖, 전체무쓰기나B6완료주장금지. 상세인계 docs/handoff/L2_STUDIO_B6_PROJECT_ENTRY_2026-09-15.md.
- 영향/보존: App/main·운영DB·키·암호문·원격무변경, 기존사용자로그SHA7720cc45…f510보존, 기존B5/C0변경보존. commit/push안함.

## Codex B6 프로젝트 진입 확인 — 20~30분 분할, 2026-09-15 KST

- 작성/이유: Codex. 사용자가 큰 B6 묶음을20~30분으로 제한했다. 23:54:32 KST 시작. 권고10/G3, 전체21/40=52.5%·로컬18/28 유지.
- 작업/담당: Codex는 project entry API reader·flow·React Gate·검사·인계, Hilbert는 factory GET·서버 집중검사, Hooke는 프런트 읽기 전용 독립 검토. App/main과 나머지 target은 범위 밖.
- 근거/상태: 프런트26+25+153PASS·tsc/lint/build PASS. 서버 최초12PASS/2FAIL 뒤 선택문맥 캐시 경계를 새 GET 전·후 fresh 검사로 수정, 최초 회귀 보존. 최종 독립22PASS/10.09초(output/usage-holds-ckd38t6i). 알려진 schema 초기화 DDL은 잔여. 00:16:36 KST 검증 마감, 이후 문서·보존 확인만 수행. 실제 브라우저 미실행, 전역 미연결.
- 다음/조건: 이번 잔여를 먼저 확인하고 project 전역 연결을20~30분 단위로 다시 산정한다. 단독 App 담당 Codex가 원본 통합 Gate 및 사용자 전환 이벤트 계약을 확인한다. 화면·SSE·히스토리 수용 전 B6 완료 가산 금지.
- 영향/보존: 업무 생성·실행 POST 없음. shared reader schema 초기화와 업무 데이터 쓰기는 구분한다. 기존 사용자 로그SHA7720cc45…f510 및 B5 dirty 보존. 원격/운영DB/키/암호문 미변경, 미커밋·미푸시.

## Codex B5 결함 수정 검증·B6-C0 첫 구현 — 2026-09-14 22:48 KST

- 작성자/왜 지금: Codex. 사용자 승인 결함 수정과 다음 작업 진행. 권고10/G3, 전체21/40=52.5%·로컬18/28 유지.
- 완료/근거: 서버 권한·접수·초안·취소·구경로 잠금 및 프런트 결정 배선 수정. 실제 HTTP/PDP/원장/합성 파일 중심432PASS/0FAIL, `output/usage-holds-bza0vdwu/isolation.json`. 프런트153·C0문법25·설치105·키트15render+11sourcePASS, 최종buildPASS. 첫59PASS/2FAIL 기록과 수정 사유는 새 인계에 보존.
- 결정/상태: 이번 B5 결함 묶음 검증 완료, B5 전체 화면 수용 미완료. B6-C0 순수 URL parser/serializer 구현·교차검토 완료, App에 미연결. 원본 통합계획은 확인했으나 전역 Gate 승격은 아님.
- 다음/담당/조건: Codex 단독 App 소유. target별 서버 귀속 확인·단일 진입 연결1차90~150분 예상. 전역 연결 전 통합 Gate 증거 확인, 실제 브라우저 도구 복구 후 effect·히스토리·회사/SSE 수용 필수. 현재 computer-use Windows helper/kernel 오류로 NOT_RUN.
- 영향/보존: 소스·보호자산 지문 불변, 금지쓰기0. 사용자 로그SHA7720cc45…f510 보존, App/main/운영DB/키/암호문 무변경, commit/push 안 함. 최종 정본은 `docs/handoff/L2_STUDIO_B5_DEFECT_REPAIR_2026-09-14.md`와 PROGRESS.

## Codex B5 결함 정리 착수 — 2026-09-14 KST (착수 시각 미기록)

- 작성자/왜 지금: Codex. 사용자 pull 점검 후 발견 결함의 수정 및 다음 단계 진행 명시 승인. 권고10/G3이며 첫 수직 폐루프의 실제 입력·제출·결과 확인에 직접 필요하다.
- 근거: 원격 `dd0573383`까지 fast-forward, 서버 집중135PASS/1FAIL·프런트141PASS·설치105PASS·빌드PASS. Hilbert 서버7건, Hooke 프런트5건 교차검토 및 메인 재확인. 단위/SSR 통과가 실제 연결 완료를 증명하지 못했고 명확화 bool 인수 오류는 읽기 전용 최소 재현했다.
- 결정/상태: Claude의 09-14 「B5 저장 출구 모두 닫힘」은 정정 대상이다. 전체21/40=52.5%, 로컬18/28≈64.3% 유지. B5 결함 수정·집중 검증 후 B6 조건 판정. 운영 데이터/키/기존 로그/원격 변경 금지.
- 담당/파일: Codex는 `factory_control.py` HOTL·구 release/replan 경계와 `test_b5_hotl_submission_api.py`, 기존 B3 실패 시험. Hilbert는 `studio_execution_control.py` 명령별 fresh 권한과 실행 시험. Hooke는 결정패널/초안/RunControls/decision API·flow·프런트 검사. 각자 다른 파일만 수정하며 메인이 통합 검토한다.
- 검증/다음: 저장→HTTP 제출→GET→소비, 실제 권한·응답 유실·취소 회수·원본문 충돌을 집중 검사. 공통 strict-writes 실행 중 소스 편집을 멈춘다. 최초 결함 묶음90~150분, 실제 화면30~60분 추정이며 결과에 따라 재산정한다.
- 영향/주의: 이 PC에는 통합계획 원본이 실제 존재한다. B6 전역 연결 전 원본 전문·게이트를 재확인하고 App.tsx는 Codex 단독 소유. 이번 패치 중 Windows helper 오류는 동일 apply_patch 실행기의 직접 호출로 우회했다. 기능 완료/시험 결과는 다음 증거가 나온 뒤 별도 기록한다.

## Claude Code 2026-09-14 오후 — 검증 명세 76건 대조·공백 5건 메움

- 작성자/왜지금: Claude Code. 오전 마감 뒤 사용자가 「오늘 진행 가능한 미비사항」을 물어 조사로 방향을 틀었다. 하루 인계 정본 `docs/handoff/CLAUDE_TO_CODEX_2026-09-14.md` §10~§15, 대조표 `docs/test_plan/SPEC_COVERAGE_MAP_2026-09-14.md`.
- 완료: 검증 명세 T01~T46·U01~U30 **76건 전부 판정**(덮임35·부분19·없음7·자동불가15) + 공백 5건 메움 — U23(준비 미완료 실행·릴리스 차단), T11(표준 업무 충돌 3갈래+재사용), U26(복구 로컬 차단 4사유), T07·T23(가짜 통과 제거). 커밋 6개(3afb26c1d·fdc6ee0d7·11dd5ec4a·1bc2ca8d9·44d93dcc5·8406b9000), 미푸시. **제품 소스 diff 0.**
- 근거: 추가한 모든 시험을 **줄 단위로 검증**했다 — 차단하는 줄을 하나씩 제거해 대응 시험만 실패하고 복원하면 통과하는 것을 확인. 서버 strict-writes 전체 **2,176 실행/2,175PASS/1FAIL**(4,238초, `sources_unchanged`·보호자산 불변·차단쓰기0), 프런트 계약 141PASS/0FAIL, 설치 105PASS, 키트 11PASS, tsc0.
- ⚠️ 서버 실패 1건(`test_factory_start_ignores_client_cohort_and_context`, `dataclasses.replace()` TypeError)은 **내 파일을 HEAD 로 되돌려도 재현**된다 — 내 변경 무관. 그러나 **근본 원인 미특정**이고 전체 회귀를 오후에 처음 돌렸으므로 발생 시점도 모른다. Codex 환경(3.14) 확인 필요. 「내 변경과 무관」과 「원인은 X」는 다른 주장이라 나눠 적는다.
- ⚠️ 두 가지를 구분해 기록했다: 「시험이 없다」와 「덮을 대상이 없다」. 없음 7건 중 6건은 표준 업데이트·되돌림 **기능 자체가 없어서**이고 B1 인계가 이미 적어 두었다. T21 만 미착수 선언 없는 단독 공백이다.
- ⚠️ 또 오진단했다 — T07 을 「환경에서 안 돈다」고 단정했으나 그 파일은 49건 전부 통과한다. 잘린 출력 8줄로 전체를 판단한 잘못이고 오전 CRLF 건과 같은 유형이다. 정정하고 T07 도 끝냈다. 인계 §13 에 남겼다.
- 결정/주의: 릴리스 시험이 비어 있던 원인이 **대역이 길을 막은 것**이었다(`is_v2_project` 거짓 고정). 같은 형태가 다른 곳에도 있을 수 있다. 복구 차단 검사에서 대역 응답을 한 번 감쌌고 그 사실을 인계 §12.4 에 적었다.
- 다음/담당/조건: 오류 코드 24개의 **도달 가능성 조사**가 다음 순서다 — 이걸 하면 「시험이 없다」가 「고쳐야 할 것」과 「지워도 될 방어 코드」로 갈린다. T25·T29·T39·T40 은 서버 시험 추가로 가능하나 오늘 하지 않았다. B6 는 통합계획 원본 미확보로 여전히 차단.
- 영향/주의: main.py·App.tsx·제품 소스 전부 diff 0. `kit` fixture 는 캐시 없으면 10분·있으면 34초이므로 그 위에서 반복 검증하려면 캐시가 살아 있어야 한다. 대응표는 키워드로 후보를 좁혀 읽은 판정이라 놓친 함수가 있을 수 있고, 이의는 해당 함수를 근거로 표를 고치면 된다.

## Claude Code 2026-09-14 하루치 마감 — B5 저장 출구 완료·B6 차단 보고

- 작성자/왜지금: Claude Code. 사용자 지시로 오늘 작업을 마감하고 인계를 남긴다. 하루 인계 정본은 `docs/handoff/CLAUDE_TO_CODEX_2026-09-14.md`.
- 완료: 일반HOTL·명확화 초안 사용완료 결속(설계안 갈래 A, 사용자 결정), 구 release/replan 접수 기록, `check-process-installation` 회귀 해소, 원키 재조회 배선·접근성 정적 보강. 커밋 4개(0ba6674a8·ba7f9f06b·4cd1ffc45·aacfe86a6), 미푸시. **B5 저장 출구 전부 닫힘**, B5 전체는 미완.
- 근거: 서버 392PASS/178.30초, 프런트 139PASS, 설치 계약 105PASS, tsc0·build PASS, 보호자산·소스지문 불변. 착수 전 기준선 157PASS 선확인. 실패 기록 보존(계약 135PASS/2FAIL, 서버 중간 2FAIL) — 첫 실패를 최종 PASS 로 치환하지 않았다.
- ⚠️ 스스로 낸 오류 두 건을 인계에 남겼다: ① 검증 없이 원인을 CRLF 로 단정해 문서 3곳·커밋에 적었다가 정정 ② `recheckSubmission` 배선 누락(시험만 초록). 재발 방지 규칙과 STATIC 검사를 각각 넣었다.
- 결정/주의: Codex 커밋 `58713ed1d` 의 소스·검사 불일치를 **검사 쪽을 고쳐** 해소했다(소스가 옳다는 판단, 동일 파일 기존 방식에 맞춤). 이견 시 인계 해당 절 근거로 되돌릴 수 있다. 명확화 조합 규칙이 화면·서버 두 곳이며 고정 예제 잠금의 한계(한쪽만 고치면 못 잡음)를 두 파일 머리말에 명시했다.
- 다음/담당/조건: **B6 는 병렬개발 통합계획 원본이 있어야 착수한다** — 사용자 확인상 물리적으로 떨어진 디스크에 있어 오늘 전달 불가. B7 은 B6 선행. B5 잔여는 실제 브라우저 수용(환경 미비 NOT_RUN). 「서버 PROCESSING/UNKNOWN 운영 복구」는 B5/후속 미정 그대로.
- 영향/주의: main.py·App.tsx diff0. 기존 경로·서버 동작 불변, 구 호출 호환 유지. 원본 트리(integration 브랜치)와 그쪽 분류 작업은 건드리지 않았다. 이 워크트리 venv 는 3.12.10·torch/transformers 제외. `data_sync` 암호문은 키 부재로 열지 못했고 오늘 작업은 전부 합성 격리 환경이다.

## Claude Code B5 일반HOTL 초안 소비·구 release/replan 접수 기록 — 2026-09-14 KST

- 작성자/왜지금: Claude Code. Codex 23:03 인계 §8.1이 「다음 구현」으로 지정한 일반HOTL 저장 초안 결속과, 같은 인계가 잔여로 남긴 구 release/replan 원키 없는 UNKNOWN 을 닫았다. 사용자 지시로 codex/l2-unified-studio-20260912 브랜치를 이어받아 작업했다.
- 근거: 서버 310PASS/177.52초, 프런트 137PASS(기존127+신규10), tsc0·build PASS. 착수 전 기준선 157PASS 선확인. 계약 첫 실행 135PASS/2FAIL(`operations` 목록 누락) 수정 이력 보존. `check-process-installation.mjs` 104PASS 뒤 중단은 **CRLF 가 아니었다** — 58713ed1d 가 소스 의존성에 `identity` 를 더했는데 검사가 정확 일치를 요구한 회귀다. 검사를 동일 파일 기존 방식에 맞춰 105PASS 복구(제품 소스 불변).
- 결정/상태: 일반HOTL 제출에 접수 기록을 붙이고 초안 소비를 명시 CAS 로 연결. RELEASE·REPLAN 을 실행 명령에 편입(고정 task_id `PROJECT`). 명확화 초안 소비는 설계안을 내 결정을 받은 뒤 **갈래 A 로 구현했다**(서버가 본문을 재현해 접수 시점 대조). 처음에는 임의로 정하지 않고 대기로 남겼다 — 제출 본문이 화면 조합이라 서버 대조가 불가능하고, 조합 규칙을 서버에 복제하면 표시 문구가 두 곳이 된다. 전체21/40=52.5%·로컬18/28 유지, 제품 관문 신규 완료 아님.
- 다음/담당/조건: 명확화 소비는 사용자 결정 후 착수(선택지 두 개는 인계 문서에 정리). B6 단일 진입은 병렬개발 통합계획 원본 확보가 선행 조건이며 지정 두 경로·저장소 전체·모든 브랜치 이력에서 미확인 — 사용자 제공 필요. B7 실제 브라우저 수용은 별도.
- 영향/주의: main.py·App.tsx diff0. 기존 `/hotl/resume`·`/release`·`/wbs/replan` 경로와 서버 동작 불변, 구 호출 호환 유지. 원본 트리(`C:/AI Workspace/Ai_Agent_factory_porto-dev`, integration 브랜치)는 건드리지 않았다 — 두 세션이 같은 저장소를 공유한다. 이 워크트리 venv 는 Python 3.12.10 이며 경로 길이 제한으로 torch·transformers 제외 설치다.

## Codex 사용자 승인 후 암호문 추가 전달 — 2026-09-13 23:45 KST

- 작성자/왜지금: Codex. 직전 공개 저장소 암호문 업로드/키 비공개 별도 전달 승인 질문에 사용자가 “네 승인합니다”로 답하여, 앞선 보안 검토의 미승인 조건을 해소했다. 권고10/G3 지원 인계이며 제품 관문 신규완료 아님.
- 범위/근거: 기존 `58713ed1d` 이후 업무 스냅샷 암호문1개+전달 상태 문서만 추가. SHA c0dded58…9790/13,672,011bytes, 인증복호화·164파일/15DB 지문 재검증 PASS. 기존 독립 도구 검토/복원 시험 결과는 이전 기록 참조. 도구·제품 코드 변경 없음.
- 결정/주의: 평문 DB·복호화 키·인증정보·사용자 기존 interaction_log 변경은 제외. 원격은 public임을 인지한 명시 승인이며 실제 데이터 평문 공개나 키 공개 승인이 아니다. 키는 output/session-handoff/session-data-20260913.key 로컬 보존. 기존 운영DB/RAW 수정·복원 없음.
- 다음/담당/조건: Codex가 추가 커밋·푸시 후 원격 SHA/암호문 blob 일치를 확인한다. 수신 모델은 같은 브랜치 pull 후 별도 키로 검증·복원. 다른 경로는 검사사본만 지원. 다음 기능 담당은 일반HOTL 초안소비+B5 잔여45~75분. 전체21/40=52.5%/로컬18/28 유지.

## Codex 다른 모델·세션 인수인계 및 데이터 동기화 — 2026-09-13 23:30 KST

- 최종권한경계: 자동 보안 검토가 REAL 업무 데이터 암호문의 public 원격 업로드를 별도 명시승인 부족으로 최초 commit/push 실행 전 차단. 우회하지 않고 암호문을 stage에서 제외해 코드/문서/도구만 commit/push한다. 암호문·키는 로컬 보존하며 데이터 동기화 완료로 보고하지 않는다. 승인 또는 비공개경로가 남은 조건이다.

- 작성자/왜지금: Codex. 사용자 명시요청으로 현재 L2 브랜치의 코드·설정 데이터를 commit/push하고 다른 모델이 재개할 상세문서를 작성. 제품관문 신규완료 아님, 전체21/40=52.5%/로컬18/28 유지.
- 완료: 단계·설계·API·검증·보호·다음45~75분 순서를 단일 cross-session 인계에 통합. Git ignored DB/RAW가 pull에 미포함되던 원인 확인. 공개원격 확인 후 업무 데이터는 평문 대신 AES-256-GCM/로컬 별도 randomkey로 전달.
- 근거: 164파일(DB15/RAW143/설정6), 13,672,011bytes 암호문. tool12PASS, 실제복호화/파일지문/SQLite15/표107/원본참조38 대조 PASS, front127 재통과. 원본본체/WAL전후일치. 초기 Windows test cleanup8ERROR와 첫 export 전후변경감지중단 이력 인계에 보존.
- 독립: Hilbert 변경소스 비밀패턴/크기 정적감사 완료(신규패턴미탐지, 기존이메일식별자/추적로그 주의). 암호화도구 P2 2건(RAW 민감파일명 거절/CSV만 허용, copy-only 전용 inspection-files 격리/마커 선작성) 수정 후 지적범위 정적종결. 실행은 main이며 전체이력·모든바이너리 무비밀보장 아님.
- 결정/영향: 인증DB·세션·API키·개인대화/로그·프로젝트 체크포인터 제외. 동일절대경로 신규checkout의 설정복원만 지원, 다른경로는 copy-only 검사. 키 비공개별도전달. 운영권한 자동승계/앱실행수용 미검증. 사용자기존로그SHA7720cc45…f510 유지/커밋제외, main.py/App.tsx diff0.
- 다음: B5 일반HOTL 초안소비 결속/잔여판정45~75분→B6단일진입→B7수용. B6전 필수통합계획 원본 미확인 해결. 이번같은브랜치보존은 병렬branch merge/I-4완료가 아님.

## Codex B5 일반 재개·오류 복구 명령 묶음 마감 — 2026-09-13 23:03 KST

- 작성자/관문: Codex. 권고10/G3-B·C/첫 원료구매 앱 중단·오류 복구. 전체21/40=52.5%, 로컬18/28≈64.3% 유지, B5전체/B6/B7 미완료.
- 완료: 6종 실행 POST·개인문맥별 고정 영수증 GET/목록, UUID/본문지문/CAS/UNKNOWN 신규실행차단·legacy START/QUOTA우회차단, 실제worker종료·정지증거·비파괴재개, HEAL 엄격WBS원자추가/원실패·새task/서버3회상한/현재서버task HOTL우선, 원키복구·개별기록공개·일반task재개·정지상태표시.
- 소유: James orchestrator/정지증거/초기35회귀, Godel 명령store/healinghelper·회귀, Dewey3UI, Hooke front검사, Codex guard/API/adapter/store/viewModel/fixture/통합·P2회귀·최종실행·문서, Hilbert 독립읽기대조. 모든 소스동결/agent종료, 전역진입 미수정.
- 최종 근거: 260PASS/163.16초(wrapper179.049초/0, usage-holds-4w0j3fcs), 프런트127PASS/1005.8953ms(studio-contracts-4b7a3635), 제품/fixturebuild PASS, 5lint 오류0·ref경고1. 서버790/자산259/프런트31 현재지문 불일치0, SQLite535 ownRUN/금지0. 실패·비최종실행도 인계에 보존했다.
- 독립P2: 쿼터쓰기후False오판/다른현재task HOTL누락 두건 main수정·회귀추가, Hilbert 지정정적종결. 실제클릭NOT_RUN, 합성8768/HTTP200/앱열기queued는 브라우저수용PASS가 아니다.
- 다음45~75분: 일반HOTL 초안사용완료 결속·B5잔여판정→B6단일진입→B7수용. 구release/replan 영수증없는UNKNOWN·서버내부미확정수동조정 별도. 보호SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510/main.py/App.tsx diff0/운영DB·RAW·실권한·원격·기존dirty 보존, 미커밋·미푸시.

## Codex B5 일반 재개·복구 명령 연결 착수 — 2026-09-13 22:08 KST

- 작성자/왜 지금: Codex. 사용자 계속 진행 승인으로 앞서 예고한 일반 재개·오류 복구 묶음을 수행한다. 권고10/G3-B·C, 첫 원료구매 앱의 중단→재개·오류→복구 실행 연결에 직접 필요. 전체21/40=52.5%, 로컬18/28 유지.
- 설계/출구: UUID/행동/프로젝트·작업/입력에 결속된 영속 명령 기록→기존 실행→명령별 GET확인. PROCESSING/UNKNOWN은 자동 재실행하지 않으며 현재권한·문맥과원본문을대조한다. pause는 실제worker종료 확인, 같은PLANNING재개는원task/결과/체크포인트보존·HOTL/쿼터구분. legacyheal준비쓰기전예약·서버명시복구상한을연결한다. 신규분산실행시스템·전역진입은범위밖.
- 소유/계획: Codex 기존execution_guard중첩소유·API/명령adapter·sprintActions/store·최종실행/문서, James asyncorchestrator/비파괴재개·정지증거·코어회귀, Godel AdvisorStore내명령기록전용테이블·회귀, Dewey RunControls/Header/명령기록UI, Hooke 기존front집중검사, Hilbert 독립읽기전용. 파일소유분리·동결후main집중검사.
- 예상/다음:60~90분초기예상, 기능→집중회귀→독립지적수정. B5나머지일반HOTL초안소비/B6단일진입/B7수용은별도. 같은task캐시만으로UNKNOWN해제금지, 접수확인과실제가동·완료구분.
- 보호: main.py/App.tsx·운영DB/RAW/실역할·실승인/사용자로그SHA7720cc45…f510/원격/기존dirty보존. 실제LLM·Host실행금지,격리fixture만검증,미커밋·미푸시.

## Codex B5 수정 요청 기능 묶음 마감 — 2026-09-13 22:04 KST

- 작성자/왜 지금/관문: Codex. 사용자가 승인한 다음 수정 요청 기능을 구현·검증했다. 권고10/G3-B·C, 첫 원료구매 앱 결과를 현업 의견으로 수정하는 접수 경로. 전체21/40=52.5%, 로컬18/28 유지, B5 전체/B6/B7 미완료.
- 결정/기능: 산출물·저장초안·본문·요청UUID 고정, WBS 접수기록+task 원자 교체, 같은키멱등/다른키동일초안중복409, 최종PDP·초안·원문검사, 취소 끝까지 예약. 현재artifact조회실패와독립된 원키GET·다건실패순회, 검증전본문숨김, 원초안소비·새의견작성. 접수와실행은분리한다.
- 소유: James 서버/기존라우터·WBS·consume; Codex API/flow·취소/가시성 최종보완·fixture·최종실행/인계; Dewey 3UI; Godel 실제API회귀/Windows격리경로최소호환+17회귀; Hooke 프런트초기23회귀/Codex 실패순회1추가; Hilbert 독립읽기전용. 소스동결, 지정정적P2종결. main.py/App.tsx/전역진입은수정하지않았다.
- 근거: 최종213PASS/127.33초(wrapper144.858초/0), usage-holds-746l2d44. 서버782소스·259자산/프런트27소스 현재불일치0, SQLite303 ownRUN/금지0. 프런트105PASS/785.3151ms, studio-contracts-72241109. 제품build/fixturebuild PASS,6lint오류0·ref경고1. 최초160PASS/2FAIL(usage-holds-005xoewm)→원인수정→guard49PASS→최종213재검증. 전체full/키트156 반복없음.
- 검토/한계: Hilbert의 Target실패복구·여러건순회·실패A가B를막음·BUSY존재노출 P2는현재API/flow/UI로정적종결. 실제클릭NOT_RUN(kernel21364/helper_unknown_error). 한서버프로세스예약과한WBS파일원자성만주장, AdvisorDB·외부파일·분산프로세스트랜잭션은아니다. 기존heal예약전task/구성쓰기는일반명령P2잔여, 이번확장없음.
- 다음/담당/조건: Codex 일반재개·오류복구/UNKNOWN·같은PLANNING비파괴재개60~90분, 이후B6단일진입/B7수용. 상세 docs/handoff/L2_STUDIO_B5_CORE_2026-09-13.md. 사용자로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510/운영DB·RAW/실권한/원격/기존dirty보존,미커밋·미푸시.

## Codex B5 수정 요청 서버 결속 착수 — 2026-09-13 21:25 KST

- 작성자/왜 지금: Codex. 사용자가 예고한 다음 단계 진행을 승인했다. 권고10/G3-B·C, 첫 원료구매 앱 결과를 현업 의견으로 수정하는 실제 제출 연결이며 전략§11 첫 폐루프 필요에 예. 전체21/40=52.5%, 로컬18/28 유지.
- 설계/결정: 기존 Target(산출물digest/원task)·의견·client_request_id·저장초안ID/판본/지문을 접수 기록과 WBS task에 함께 결속한다. 같은키/같은본문 멱등, 다른본문409, 미확정은 GET조회만. 기준변경/실행중/권한상실은 접수차단. 접수는 실행/수정완료가 아니며 초안소비는 검증된 접수증으로 별도명시한다.
- 소유/계획: Codex 프런트API/flow·최종통합/실행; James 신규수정요청서비스·WBS원자접수·HTTP/초안consume연결; Dewey 기존RevisionRequestEditor/RunControls/초안UI; Godel 기존격리실제API·WBS회귀; Hooke 기존프런트집중검사; Hilbert 독립읽기전용 검토. 파일소유 분리 후 병렬구현, main.py/App.tsx/전역진입 보존.
- 출구/예상/다음: 기능구현·부정경로·동일키조회복구·입력초안결속 집중검사60~90분. 기존격리runner와가벼운 B5 fixture 재사용, 전체full·키트156재반복 없음. 다음일반명령UNKNOWN/PLANNING 및B6/B7별도.
- 주의: 실행예약은단일서버프로세스경계이며WBS파일 원자교체와구분한다. 분산DB/FS트랜잭션을주장하지않는다. 운영DB/RAW/실역할/사용자로그/main.py/App.tsx/원격/기존dirty보존, 미커밋·미푸시.

## Codex B5 키트 계약 검토 기능 묶음 마감 — 2026-09-13 20:44 KST

- 작성자/왜 지금: Codex. 사용자의 계속 진행 지시에 따라 예고한 저장계약 조회→타인 승인·반려→결과 확인을 구현·검증해 마감한다. 권고10/G3-B·C. 전체21/40=52.5%, 로컬18/28 유지. B5전체/B6단일진입/B7브라우저·현업수용 완료는 아니다.
- 결정/기능: 현재READ 가능한 v2 적용본/앱 목록, 저장원문·판본·지문·검증원장GET, 서버허용행동에 따른 검토UI/선행재조회/승인·반려/같은사건확인. 데이터보류의 READ/반려와 승인/실행 분리, v1권한·writer유지, v2미연결초안/제작명시. UNKNOWN/RECORDED 원기록·GET복구, 구판 후속결정 불가 확인에만 최신판잠금분리, 권한상실 부모캐시숨김, 무계약 reader재조회반복방지.
- 소유/독립검토: James core/route/list, Codex API/flow/문맥부모/격리URI호환·최종실행·통합, Dewey 검토UI, Godel 실제API36, Hooke 프런트초기21, Hilbert read-only. Hilbert P2 구판영구잠금·부모캐시 노출 수정 및 추가무계약·guard 정적재대조 종결, 새P1/P2없음. 테스트는 main실행이며 독립실행으로 표현하지 않는다. 전원동결·종료.
- 증거: 실제API156PASS/1422.62초(wrapper1428.847/0), usage-holds-mqfv5s1m. 서버779소스·259자산 전후/현재불일치0, SQLite896경로 ownRUN/금지0. 프런트81PASS/388.8497ms/25소스현재일치(studio-contracts-9f24a00a), 키트23UNIT/API/SSR+1STATIC 분리. 격리32PASS·릴리스표시7PASS·최종제품build/6lint/fixturebuild PASS. 최초중단/선택2FAIL/중간타입buildFAIL 기록은 보존. 제품mode=ro를RW로바꾸지않고 ownRUNcanonical기존파일만검증하도록guard보완; 외부·쓰기·우회 차단시험통과.
- 가시성/한계: 기존8768 합성미리보기 scene=kit, 최신JS DTHmkW8E/HEAD200/CSPconnectnone. computer-use 초기화오류로 실제브라우저NOT_RUN, SSR/HTTP/빌드를수용으로치환하지않는다. 키트의 새초안→생성진입통합은B6범위이며 현재준비필요표시유지.
- 다음/예상: Codex 수정요청 산출물기준·제출ID 서버결속/멱등접수/초안소비60~90분. 일반명령UNKNOWN·같은PLANNING비파괴재개·B6진입·B7수용별도. 상세 docs/handoff/L2_STUDIO_B5_CORE_2026-09-13.md 최신란, PROGRESS최신란.
- 보호: 사용자로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510/main.py/App.tsx·운영DB/RAW/실권한·실승인·원격 보존, 기존dirty유지·미커밋·미푸시.

## Codex B5 키트 계약 검토 완결 착수 — 2026-09-13 19:52 KST

- 작성자/왜 지금: Codex. 사용자가 앞서 예고한 다음 기능(키트 계약 조회→적격 타인 검토/승인·반려)의 계속 진행을 승인했다. 권고10/G3-B·G3-C, 첫 원료구매 업무 앱의 생성·검토 단절 해소이며 전체21/40=52.5%, 로컬18/28 유지.
- 계획/소유: James 저장 v2 계약 reader·GET·v2 목록 읽기 진입(기존v1권한보존); Codex 프런트 DTO/API/검토flow·부모 문맥 전환·최종실행; Dewey 기존KitAppPanel/v2검토 컴포넌트; Godel 실제API 집중회귀; Hilbert 독립 읽기 전용 권한/무결성/최종UX 검토. 공통파일 소유분리, main.py/App.tsx/운영DB/원격수정금지.
- 결정/출구: 원문·차수·지문·검토 가능 행동을 서버에서 조회하고 같은 기준으로 명시 승인/반려, 최신조회로 반영확인. 데이터보류와 계약열람을 분리하지만 실행/데이터 권한을 확대하지 않는다. 새판·타회사·자기승인·UNKNOWN반복 차단, v1기존계약유지. GET도메인무쓰기/격리API/프런트단위·SSR/제품build를 별도보고.
- 예상/다음: 60~90분 기능묶음, 지정코드동결후main영향범위검사. 전체full·새검사인프라 개발은 하지 않는다. B5 잔여 원자적수정·미확정명령/PLANNING, B6진입·B7수용은 이번완료와별도이며 점수를 임의 가산하지 않는다.
- 주의/보호: 기존dirty/사용자로그SHA7720cc45…f510/원본Starter/운영DB·RAW·실역할·실승인·원격 보존. 코드상 실제API연결과 합성미리보기/브라우저실측을 구분한다. 미커밋·미푸시.
- 20:25 중간기록/Codex: backend·UI 동결, 프런트78PASS/제품build·fixture·지정lint 확인. 최초 API 전체 실행은 초반 실패를 좁히기 위해 중단(완료증거 아님), 선택2FAIL `usage-holds-v3lr6dvp`는 격리 guard의 모든 file: URI 거부가 원인. 제품 mode=ro를 쓰기 연결로 바꾸지 않고, 현재RUN 기존파일의 정확 canonical URI+mode=ro만 guard에서 검증하도록 지원. 외부/형제RUN/누락/비정규/쓰기/추가옵션 차단과 실제readonly INSERT 실패 포함32PASS(`usage-holds-ljrr0aal`); guard 변경 범위 독립검토 요청. 실제API 4파일 재실행 중이며 현재완료·전체점수 가산 아님. computer-use 초기화실패(kernel25276/helper_unknown_error)로 실제브라우저NOT_RUN, UI체험은 운영fallback 없는 합성이다.

## Codex B5 핵심 내용 구현·집중 검증 마감 — 2026-09-13 19:00 KST

- 작성자/왜 지금: Codex. 사용자 지시인 기능 구현 우선·최고 속도·진척 상시 보고에 따라 B5 입력/실행/결정 축을 병렬 구현하고 지정 검증 결과를 확정한다. 권고10/G3-B·G3-C. 전체21/40=52.5%, 로컬18/28 유지이며 B5 전체나 B6/B7 수용 완료로 집계하지 않는다.
- 결정/기능: 쉬운 요구 입력·실제 초안 저장, 대표 행동·공통 StudioContent, 실제 action/store 반환 구분과 pause/stop, 결정 차수별 일반HOTL/Host/지원 능력·데이터 검토, 동일 사건 복구, 입력별 서버 보관/복원/폐기/지원 결정 사용 완료, fulltarget별 수정 의견·제출 전 변경 차단, 닫기/새로고침·문맥 전환 보호를 연결했다.
- 소유/분담: Codex 공통UI·RunControls·server draft UI/API·fixture·최종 실행/통합. James sprintActions/store, Dewey BuildStart/requirementDraft/RevisionEditor, Hooke decision 영역/기존 집중script57건, Godel input draft backend/API/실제API회귀. 앞선 착수란의 Hooke 검사 전담은 중간에 결정 구현으로 확장 후 검사로 복귀했음을 보완한다. 파일 소유를 분리했고 전원 소스 동결했다.
- 독립검토: Codex 요청/Hilbert 읽기 전용. 캐시로UNKNOWN해제·후속4xx원키폐기·저장표시불일치·수정기준재결속·consume복구UI소실·공백불일치 지적을 수정했다. 마지막 RECORDED 카드 조건까지 소스 재대조하여 지정 정적 리뷰 종결. 실행은 main이며 독립 실행이나 B5 전체 수용으로 표현하지 않는다.
- 실행근거: usage-holds-rc74v0pf 64PASS/30.46초/wrapper37.738초·0, 소스778/자산259불변·SQLite231 ownRUN·금지0. studio-contracts-794056d3 57PASS/237.8847ms·20소스 현재불일치0. 요구초안5건은단위이며해당실제API재실행아님. 최종제품build·지정13lint·fixturebuild PASS, 기존chunk/dynamic import경고와줄바꿈경고별도. 최초서버1FAIL/프런트1FAIL증거보존후수정재실행.
- 가시성/한계: 8768/tests/studio-transition.fixture.html?version=b5-20260913-1857 실제컴포넌트+합성5상태, connect-src none/운영쓰기0, HTTP200/앱열기queued. computer-use초기화오류로 실제브라우저NOT_RUN, 서버/SSR증거로대체하지않는다. 일시승인경로usage오류후최신ordinaryUsageAllowed와동일경로읽기성공확인후재개,우회/reset없음.
- 다음/담당/조건: Codex 다음은 Kit v2 저장계약 GET→적격타인검토/승인·반려 UI완결60~90분. 수정제출원자적artifact/요청ID결속·소비,일반명령UNKNOWN확인,같은PLANNING비파괴재개는미구현별도. B5잔여후 B6 App단일담당으로초안→프로젝트·유형별URL/복귀/SSE진입통합. supportsInitialIdea플래그만켜거나기존projectPOST로우회하지않는다. B7브라우저·현업수용은후속.
- 영향/보호: 사용자로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510/current확인18:59. main.py/App.tsx diff0,운영DB·RAW·실권한·실승인·원격변경없음. 기존dirty보존·미커밋·미푸시. 상세 docs/handoff/L2_STUDIO_B5_CORE_2026-09-13.md.

## Codex B5 단일 제작 내용 착수 — 2026-09-13 17:28 KST

- 작성자/왜 지금: Codex. 사용자가 진척을 높이며 계속 구현하도록 승인했다. 권고10/G3-B·G3-C, 첫 원료구매 앱의 요구→제작→검토/저장 사용자 경로를 연결한다. 전체21/40=52.5% 유지; UI 내부 기능 수를 전체 점수로 바꾸지 않는다.
- 계획/소유: Codex 기존 AdaptiveProductionStudio 내용/컨테이너 분리, RunControls·ProjectHeader·결정/초안 연결. James useFactoryStore/sprintActions의 명령 결과·실패/응답 유실 보존과 개별 작업 실행. Dewey BuildStartDialog 쉬운 입력/추가 설정. Hooke 기존 패턴 기반 집중 단위·SSR 검사. Hilbert 읽기 전용 독립 계약/권한/최종UX 검토. 공통 파일 소유 분리.
- 출구/예상: 입력·단일 대표 행동·일반/쿼터 재개·복구 관찰 대상·결정 종류별 분리·검토용 저장/실패 보존, 제품build/영향 범위 집중검사. 초기120~180분 병렬 예상이며 실제 브라우저/현업 수용은 별도. B5에서 전역 단일 진입이 완료됐다고 주장하지 않는다.
- 결정/주의: 신규 세 번째 생성기/임의 프로젝트/데이터 승인/자동 쓰기 없음. B3 API/기존 콘텐츠 재사용, 모호한 명령 결과를 성공으로 바꾸지 않는다. 네 입력 종류 서버초안 계약 실존 여부를 먼저 대조하며 메모리 보존을 서버 저장으로 표현하지 않는다.
- 다음/담당: Codex가 세 구현 축을 통합 후 독립 검토·집중 검증, 완료 동작과 전체 진척·다음 ETA 보고. main.py/App.tsx·전역라우터/SSE mount는 B6 전까지 보존. 기존 dirty tree/사용자로그/운영DB·RAW/실권한/원격 보존, 커밋·푸시 없음.

## Codex B4 구조 편집 코드·집중 검증 마감 — 2026-09-13 17:14 KST

- 작성자/왜 지금: Codex. 승인된 다음 기능 묶음(추가·사용상태·부모 이동·바로가기)을 기존 제안/타인 승인/GET 반영과 연결하고 마감한다. 권고4·7·10/G2→G3의 첫 원료구매 업무 골격 변경 기능이며 전체21/40=52.5%, 로컬18/28 유지.
- 결정/결과: B4 지정 기본 편집 코드·집중 검증 출구 마감. 경영 홈/앱 운영의 같은 설정 화면 진입·복귀 재조회 연결까지 포함한다. 실제 브라우저/현업 수용은 OPEN, B5~B7 완료나 전체 점수 가산을 주장하지 않는다.
- 분담/이중검토: Codex 모델/API/UI 연결·실행, Dewey 구조 입력 컴포넌트, Hooke 기존 합성검사80→105/fixture, James 구조 실제API27사례. Hilbert 독립 검토의 양식 유실/잘못된 표시 명령 고정/복귀 재조회 누락 P2 3건 수정·재대조 종결, 지정 범위 미해결 P1/P2 없음. 코드 동결, 보조 에이전트 모두 종료.
- 실행근거: usage-holds-0sx0_95d 서버177PASS/77.84초/wrapper83.7469초·0, 소스775/자산259 전후·현재 불변, SQLite471 ownRUN/금지0. 최종4ffd0920 프런트105PASS/375.6702ms=UNIT/SSR104+STATIC1, 소스16 현재불일치0. 제품build·전용6lint·최종fixturebuild PASS. 실제 DOM/포커스/복귀 GET 실행은 STATIC과 별도다.
- 제약/사용자 확인: computer-use 초기화 helper_unknown_error로 실제 브라우저 NOT_RUN. 기존localhost8768 메모리 합성 미리보기에서 편집 바로 체험→추가 설정 제공. 운영 API/DB/승인 호출 없음, 새 검증 인프라/전체full 반복 없음.
- 다음/소유/조건: Codex B5 단일 제작 화면 내용 연결(업무·요청 입력/현재 행동/검토·재개·저장), 초기120~180분(집중 검증 포함). 기존 B3 계약 재사용, 전역 App.tsx mount/URL/SSE는 B6 단일 담당 단계. 실제 브라우저 수용은 도구 복구 후 별도 필수 확인.
- 보호: 사용자로그 SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510, main.py/App.tsx·운영DB/RAW/실권한·원격 보존. 기존 dirty tree 유지, 미커밋·미푸시. 상세/해시는 B4 인계문서 최신란.

## Codex B4 구조 편집 묶음 착수 — 2026-09-13 16:47 KST

- 작성자/왜 지금: Codex. 사용자가 앞서 제시한 추가·사용상태·부모 이동·바로가기 편집의 다음 진행을 승인했다. 권고4·7·10/G2-A/B/C→G3-B/C, 첫 원료구매 수직 업무 골격의 현업 변경 기능이며 새 ERP/실데이터 실행 범위가 아니다. 전체21/40=52.5% 유지.
- 계획/소유: Codex API type·순서 보존 편집 모델·미리보기/기존 검토 연결. Dewey 새 구조 입력 컴포넌트. Hooke 기존 합성검사80 유지+구조회귀/fixture. James 기존 서버 명령의 실제API·원본/참조 집중시험. Hilbert 권한·기준판·명령순서·멱등키·최종UX 독립검토. 각 파일 소유 분리, 테스트는 동결 후 main 실행.
- 결정: 원래 승인판과 로컬 workingBase를 분리하고 display diff→구조명령의 순서를 고정한다. 최종 제안은 명령만 보내며 임시 placement ID를 보내지 않는다. 새 배치가 있는 형제 목록의 순서는 승인 후 변경 가능하게 안내한다. 임시 바로가기 제거/rebase는 전체 replay 성공 후만 교체한다.
- 복구: 해당 propose POST에서 확정422를 받은 경우만 명시 수정 재개. 선행GET/로컬오류나 미확정409/5xx는 원본문/요청키를 보존한다. 기존 입력·알 수 없는 응답을 버리는 동작은 금지한다.
- 다음/출구/예상: 구조 네 기능+표시 편집 혼합→제안→타인 승인→GET 반영 확인, 영향 범위 격리 검사/정적이중검토. 초기60~90분(검증 포함). B4전체는 진입 연결/실브라우저 상태와 함께 별도 판정하며, B5~7 완료나 전체점수 가산으로 대신하지 않는다.
- 보호: 기존dirty tree/사용자로그/운영DB·RAW·실권한/원격 보존, main.py/App.tsx 미변경. 새 검사 기반 도구/전체full 반복 없음.

## Codex B4 표시 편집 기능 묶음 마감 — 2026-09-13 15:47 KST

- 작성자/결정: Codex. 이름·설명·형제 순서의 사용자 편집→미리보기→고정 제안→기존 타인 승인/GET 반영 경로를 지정 검사까지 완료. B4 전체와 전체21/40=52.5%는 OPEN/유지. 사용자 요청대로 기능 구현 우선, 검사 인프라 확장·전체full 반복 없음.
- 분담/이중검토: James 서버+40직접 사례, Codex 제품 API/편집 상태/UI/기존 승인 연결, Hooke 기존 합성 검사·fixture 확장. Hilbert 정적검토 P2 2건 발견→Codex 권한 상실 부모 읽기 결과 숨김/미수정 기준판 전환 보완→Hilbert 둘 다 종결/추가 확정P1/P2없음. 모든 작성자 동결·종료.
- 실행근거: Codex run `usage-holds-cqim8wod`150PASS/80.19초/wrapper87.13초/소스774·자산259 불변 및 현재일치/SQLite390 ownRUN/금지0. 프런트e9445430…80PASS/281.91ms/12지문현재일치. 제품빌드·지정5lint·fixture빌드PASS. 상세지문은B4인계문서.
- 사용자 확인: 기존localhost8768미리보기에 바로 체험 버튼 추가(합성 승인판, 빈 범위만), 현재HTML HTTP200. 열기queued. computer-use 초기화trustedNodeexit로 실제클릭/현업NOT_RUN이며 우회하지 않음.
- 다음/소유/출구: Codex B4 추가·사용상태·부모 이동·바로가기 UI를 기존 명령에 연결하고 제안/승인/새로고침 확인. 예상60~90분(검증포함/브라우저복구대기별도). App.tsx는B6전까지변경없음. 운영·원격·사용자로그보존, 미커밋·미푸시.

## Codex B4 기본 편집 사용자 기능 완결 — 2026-09-13 15:34 KST

- 작성자/왜 지금: Codex. 사용자가 기능 완성과 체감 가능한 진척을 우선 요청. 권고4·7·10/G2→G3의 기존 B4 범위에서 이름·설명·순서 편집→고정 변경안 제안→타인 승인→GET 반영을 한 묶음으로 연결한다. 전체 분모40/현재21=52.5%를 내부 작업량으로 보정하지 않는다.
- 계획/소유: James 서버 표시 명령·직접 시험(15:29동결), Codex 편집 상태·UI·기존 검토 연결, Hooke 기존 합성 검사·fixture 확장, Hilbert 완결 경로 독립 검토. 기반 검사 도구 추가·전체full 재실행 없이 영향 범위 집중 검증.
- 완료 조건/다음: 실제 제품 컴포넌트에서 수정·미리보기·제안·타인 승인·GET 반영 연결 및 핵심 실패 보존. 브라우저 실검사는 별도 증거로 구분. 이후 B4 잔여(활성/부모/바로가기 등)와 B5~7 연결을 진행한다.
- 진척 해석: Dewey의 한정 조회로 D03 잔여가 REAL 검사 경로/Owner 서명UI·정책UI·일반 사용자 연결임을 확인. B4 편집만으로 D02의 전제데이터/7앱 수용 조건을 완료했다고 주장하지 않는다. D03 구현을 이번 편집에 끼워 넣지 않는다.
- 보호: 기존 dirty tree 보존. 운영DB/RAW/실권한/원격 및 main.py/App.tsx 변경 없음. 사용자 로그SHA7720cc45…f510 보존. 예상 화면 연결·집중 검사20~30분, 장애 시 근거와 수정예상 즉시 보고.

마감 대조 — 2026-09-13 15:08 KST / Codex: 15:05 기록의 최종 증거를 Hilbert가 독립 대조했다. 요청Codex/검토Hilbert/판정 지정 코드·증거 범위 마감 가능. B4 107 정확1회·phase중복/실패/skip0·773source/259asset 현재 일치·SQLite306 ownRUN, exact5 초기실패집합 일치, frontend60고유PASS/10지문 일치. 전체52.5%·B4전체OPEN/브라우저NOT_RUN 유지. 다음은 기존 기록의 이름·설명·순서 제안 연결이며 운영/원격 변경 없음.

## Codex B4 재개·검토 승인 연결 검증 — 2026-09-13 15:05 KST

- 작성자/왜 지금: Codex. 요청에서 담당자 재개·타인 승인·반영 조회까지 사용자 흐름이 연결되어 집중 검사 결과와 잔여 범위를 인계한다. 권고4·7·10/G2→G3 업무 골격 입력이며 전체21/40=52.5% 유지.
- 근거: 최종 usage-holds-r0qqlsi1 B4 107PASS/48.26초/wrapper0/773source·259asset 불변/현재source일치/SQLite306 ownRUN/금지0. 프런트426eb4ae…60PASS·10지문불변, 지정lint·제품build·fixturebuild PASS. 최초15xmnk1v 281=276PASS5FAIL 및 exact v53wpcs5 5PASS는 별도 이력 보존.
- 결정/상태: 설치 재개·인수와 고정 변경안 검토·승인·GET 적용 확인의 지정 코드 흐름 마감. B4 기본 수정·B5~B7/실제브라우저/현업 수용 OPEN. 검증 도구 추가나 전체full 반복은 하지 않았으며 서로 다른 실행을 새 판281PASS로 합치지 않는다.
- 교차검토: 요청Codex/검토Hilbert/core/API4+frontend3의 5경계 정적검토 새 P1/P2 없음. James는 실패5건의 작성자[]/관리자[adopt] 계약 차이를 독립 확인했고 main이 테스트1함수만 보강했다. 마지막 증거 대조 상태는 인계 문서에 남긴다.
- 다음/담당/조건: Codex가 B4 이름·설명·순서 제안/승인 연결을 다음 구현으로 진행(60~90분+집중5~10분 초기추정). 검증 완료 소스는 동결, 추가 수정 시 해당 범위 재검증. 브라우저 도구 복구 후 실제 화면 검사 필요.
- 영향/주의: 사용자로그SHA7720cc45…f510, main.py/App.tsx, 운영DB/RAW·실역할·원격 불변. 로컬 미커밋·미푸시. 합성 리허설만 localhost8768에 제공(session82416), 서버/DB 없는 메모리 API이며 실제인증·승인 PASS로 주장하지 않는다.

## Codex B4 담당자 재개·타인 승인 연결 착수 — 2026-09-13 14:41 KST

- 작성자/왜 지금: Codex. 사용자가 진척·가시성 진단 후 다음 구현을 승인했다. 권고4·7·10/G2→G3의 업무 골격 설치를 요청에서 담당자 재개·타인 승인·적용 조회까지 잇는다.
- 근거: B4 인계의 다음 slice 1~4, 기존 resume/approve 쓰기 계약과 검증된 첫 설치 화면을 재사용한다. 전체21/40=52.5%, B4 OPEN이며 설명/순서 변경과 B5~B7는 이번 범위 밖이다.
- 결정/소유: James core/API 4파일과 신규 B4 change/review 시험, Codex frontend API/Flow/Panel/CSS 및 실행·기록, Hooke 기존 프런트 검사/합성 fixture, Hilbert 독립 읽기 전용 검토. 신규 검증 인프라 개발·운영 자료 접근·원격 변경 없음.
- 검토/검증: 상태 전이·권한 경계를 조기 검토하고 소스 동결 뒤 B1/B2/B4 관련 집중 회귀·프런트 검사/빌드로 확인한다. 과거 full PASS를 새 판 전체 PASS로 승계하지 않는다. 브라우저 도구는 별도 확인하며 실패 시 NOT_RUN을 표시한다.
- 다음/담당/조건: 현재 principal/operation 행동·고정 변경안 DTO 확정→재개/명시인수 UI→별도 승인 목록/차이/이유→승인 후 GET 확인. 코드·집중검증75~120분 예상, 작업 중 짧은 상태와 중간 산출물을 보여준다.
- 영향/주의: 기존 dirty와 사용자로그 보존, main.py/App.tsx·실역할·실승인·운영DB/RAW·배포·원격은 변경하지 않는다. 조회 실패를 승인 재전송으로 복구하지 않는다.

## Codex B4 첫흐름 지정 코드 출구 마감 — 2026-09-13 13:02 KST

- 작성자/왜지금: Codex. 최종회귀·보존·독립증거대조를마쳐설치·탐색첫흐름의코드출구를마감하고다음승인연결로인계한다.
- 근거: verification-axojhsot2194정확1회/2187PASS7symlinkskip/186subtestsPASS/실패0/1645.47초/부모자식0/소스771자산259전후현재일치·추가삭제0/금지0/SQLite3051회ownRUN. 프런트ecc761e8…37PASS·10파일지문불변,lint/type/productbuild/fixturebuild main실행PASS.
- 교차검토: 요청Codex/검토Hilbert/판정코드지적종결+FULL_REGISTERED증거PASS. old2110누락0/new84=B457+planner27/phase6582정상확인,`overall_product_pass=false`와browserNOT_RUN을유지한다. 정적·증거대조이며독립실행·현업승인이아니다.
- 결정/상태: B4첫설치·탐색지정코드출구마감, B4전체/B5~B7/브라우저·현업수용OPEN. 전체21/40=52.5%·로컬18/28유지. 권고4·7·10/G2→G3의실제회사설정진입·업무골격입력을연결했지만데이터·권한·7앱수용완료로가산하지않는다.
- 다음/담당/조건: Codex주관B4재개/명시인수·타인변경안목록/상세/승인70~110분+집중검증5~10분. James읽기전용5단계계약대조를B4인계에수록. 설명·정확형제배치순서변경은후속분리. 실제브라우저는도구환경복구후필수검증. main92140종료,source전원동결상태에서인계한다.
- 영향/주의: 운영DB/RAW/실역할/실승인·배포/원격/main.py/App.tsx변경없음.사용자로그기존10줄SHA7720cc45…f510보존. 기존B0~B3와함께로컬미커밋·미푸시. 이전실패full을삭제하거나부분PASS와합치지않았다.

## Codex B4 첫흐름 검증·동결 — 2026-09-13 12:38 KST

- 작성자/왜 지금: Codex. 설치·탐색 연결의 집중 검사와 독립 수정 확인 후 동일판 전체회귀를 가동하여 다음 담당자에게 실제 검증 경계를 남긴다.
- 근거: r13oyl3d203실행/202PASS1skip34.87초/wrapper0/소스자산불변/금지0. 최초2실패는fixture원본계보·boundmethod복원오염이며제품권한/404기대값불변. 프런트37PASS+10파일hash불변 증거 process-installation-check-9d6e085d-934f-4209-bf62-b4c820342a4f, lint/type/productbuild/fixturebuild PASS.
- 교차검토: 요청Codex/검토Hilbert read-only. 서버경계/권한·무결성/late응답·구조화오류, 과거상세와현재제출분리, scope왕복, 외부boundary A→B→A원키복원 지적을보강했다. 마지막정적추가P1/P2없음; 실행증거대조중. 실제브라우저는Cua/sky초기화sandbox오류로NOT_RUN,검토로대체하지않는다.
- 결정/상태: verification-axojhsot full/jobs1/main92140/12:27시작/2194수집(이전2110누락0/추가84/B457). Python전체writer동결,프런트도최종동결. 전체fullPASS는아직미확보. 전체21/40=52.5%·로컬18/28, B4첫코드흐름검증중/B4전체·B5~B7미완료.
- 다음/담당/조건: main전체종료·정확집합/해시/금지접근·독립증거검토 후한정마감. 후속B4담당자재개·타인승인·설명/순서변경제안및브라우저복구, 약60~90분 첫후속slice 예상. 전체B4기존150~240분은이전범위예상으로유지한다.
- 영향/주의: 권고4·7·10/G2→G3 업무골격 입력의제품연결을전진. 사용자로그SHA7720cc45…f510/main.py/App.tsx/기존dirty/운영DB·RAW·실역할/원본Starter/원격보존. 로컬미커밋·미푸시. 상세 B4 handoff 참조.

## Codex B4 첫 설치·탐색 흐름 착수 — 2026-09-13 12:09 KST

- 작성자/왜 지금: Codex. 사용자 계속 진행 승인에 따라 검증 효율화 다음 제품 작업을 실제 화면까지 연결한다. 권고4·7·10/G2-A/B/C→G3-B/C, 원료구매 첫 수직 폐루프의 업무 골격 입력에 직접 필요하다.
- 근거: 상세설계 rev2.1 §11/B3 인계 보정/검증 효율화 작은 흐름 방식. 전체21/40=52.5%, 로컬18/28 유지. 이번 출구는 후보→명시 등록→계획→설치 요청→상태GET·L1/L2 탐색이며 B4 전체 완료는 아니다.
- 소유/상태: James=core process_configuration/install·두API·test_b4_installation_queries; Codex=companyApi 분리 adapter/설치 controller·Panel/CompanySetupPanel 연결; Hooke=독립 프런트 계약 검사·명시 mock fixture; Dewey=planner B4 registry·자체시험; Hilbert=read-only 독립 권한·UX 검토. main.py/App.tsx 불변.
- 검토: Codex 요청/Hilbert 초기 P2 기존 늦은 문맥 응답/구조화 오류 소실 확인. 신규 identity·세대 결속과 오류 adapter로 보강, 구현 후 재검토한다. 운영 권한·데이터 변경 및 자동 설치/승인 없음.
- 다음/담당/조건: source 동결→정확 API·프런트 검사→브라우저 모의 범위/실제 API 증거 분리→안정 통합 full jobs1. 첫 흐름60~90분 예상 유지. 이전 fullFAIL을 부분PASS와 합산하지 않는다.
- 영향/주의: 기존미커밋·사용자로그보존, 로컬미커밋·미푸시. 재개/타인승인/변경제안·note/order는 후속slice, B5/B6 두 Studio 통합·B7현업수용 별도.

## Codex 검증 효율화 제한 범위 인계 — 2026-09-13 11:49 KST

- 작성자/왜 지금: Codex. 승인된 검증 운영 개선의 구현·실측·실패원인 수정과 독립검토를 마쳐 제한 범위 결과를 인계한다. 전체PASS를 주장하지 않는다.
- 근거: `docs/testing_efficiency_2026-09-13.md`. full `verification-5xyfosvs`2110실행/기존1929누락0/2092PASS11FAIL7skip/subtest186PASS/2272.45초/집계FAIL. 11건은2시험fixture 상대writeopen. 금지SQLite0,11상대쓰기실행전차단, 실제원본변경0. source770/asset259불변.
- 수정·결정: 제품/runner/guard불변, `test_contract_decision_api.py` tmp절대경로와 `test_tech_lead_contract_draft.py`의 해당시험 data경로대역·실제번들readback만 수정. full이후hashdiff정확2개. `usage-holds-6q1sonnm` 해당파일51+self171=221PASS1skip+subtest186PASS/31.51초/wrapper0/금지0. 최신quick `verification-imhhufyo`215사례/35.54초/SELECTED PASS/금지0. 병렬full큰속도이득미확인으로기본jobs1유지.
- 교차검토: 요청Codex/검토Hilbert. 기존P1 1/P2 3종결, 현재두fixture영향범위검증은마감가능/지금full반복필수아님. 최신quick215개1회실행/누락·중복·phase오류0/현재source770asset259일치·추가삭제0도독립확인. fullFAIL기록유지·동일판fullPASS미확보명시·다음B4안정통합full1job필수조건. main실행과독립read-only대조를구분한다. 취소probe `verification-hka1q8yz` CANCELLED/130/관리자식종료/PASS없음, CIM잔존0은main실측.
- 다음/담당/착수조건: Codex B4 첫수직흐름60~90분(전체B4기존150~240분) 예상. 검증된boundary/permitted_actions·scope별operation목록→companyApi v2 adapter→설치상태GET/재접속→기존화면연결. 권한/API와최종UX독립검토, lint/build·실화면검사·등록시험/full1job을안정통합출구로한다. Hooke의읽기전용구체경로인계는운영문서참조.
- 영향/주의: 권고4·7·10/G2→G3 후속개발의검증비용지원, 새제품관문완료아님. 전체21/40=52.5%/로컬18/28/B4~B7미완료유지. 사용자로그SHA7720cc45…f510/main.py/App.tsx/생산코드/실DB·RAW·역할/원본/원격보존. 로컬미커밋·미푸시. source작업전원동결, 실행세션32669·75128·64734·19180종료, 재대기/실패full성공재표시금지.

## Codex 검증 효율화 적용 — 2026-09-13 10:40 KST

- 작성자/왜 지금: Codex. 사용자가 검증 방법론 제안 전부를 승인하여 B4 착수 전 반복 준비·선택·피드백 비용을 낮춘다.
- 근거: 기존 최종 B0~B3 `usage-holds-6m4qchly` 1923PASS/6skip/2183.28초. 상위5파일166케이스가 시간81.5%. 새 `docs/testing_efficiency_2026-09-13.md`에 실행계층·안전·B4 수직 흐름·측정 기준을 고정했다.
- 결정/상태: quick/feature/full 선택, 실제 cold seed에서 시험별4DB backup, 최대2worker 독립 RUN/audit 및 정확한 nodeid/단계 증거 검증을 구현 중. 가드/선택기 자체시험 `usage-holds-m176y84s` 107PASS/1Windowslinkskip/6.59초/소스·자산불변/금지접근0. 실제 kit/seed 동등성은 session72657 진행 중, 성능·병렬 완료 미판정.
- 담당/교차검토: Codex=기존 runner/new isolation guard·실제 시험·문서; James=verification_plan/자체시험 동결; Hooke=b3 seed/kit fixture/격리시험 동결; Dewey=run_verification/집계 자체시험; Hilbert=독립 read-only 보안검토. 계획검토5조건(다른 RUN쓰기 차단/선택 시 가드 유지/seed 독립/실행 중 cwd 불변/정확한 nodeid)을 반영, 최종 증거 검토 별도.
- 다음/착수 조건: 메인이 pilot 결과 확인→dispatcher 자체시험→전원 소스 동결→빠른 순차/병렬 및 full 실측→동일범위·보존·독립검토. 최초45~60분 pilot 예상 유지, 전체 회귀 기존 약36분 기준이며 개선 실측 후 갱신.
- 영향/주의: 권고4·7·10/G2→G3 후속 개발 지원으로 제품 완료 관문을 새로 넘지 않았다. 전체21/40=52.5%·로컬18/28, B0~B3 제품 코드 출구 완료/B4~B7 미완료 유지. 생산 코드·권한/보안 의미·main.py/App.tsx·사용자로그·운영 DB/RAW·원격 변경 없음, 로컬 미커밋·미푸시.

## Codex B3 지정 출구 마감 / B4 인계 — 2026-09-13 09:42 KST

- 작성자/왜 지금: Codex. 최종 통합 실행·skip/격리·소스 보존 검사 및 독립 증거 대조를 마쳐 B3 OPEN을 완료로 갱신한다. 하단 기록은 당시 실행 이력이다.
- 근거: `output/usage-holds-6m4qchly`, 명령 `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0 --b1 --b2 --b3`, selection없음/wrapper exit0. 1923PASS/6skip/실패·오류0/2warnings/2183.28초. SQLite2492 모두RUN내부, 금지DB·파일접근0, conftest없음, 소스369·보호자산259 해시불변/현재소스불일치0.
- 교차검토: 요청Codex / 검토Hilbert / 판정B3 지정 코드·격리 회귀 출구PASS. 기존4P2 종결과 핵심회귀, B3 시험27파일 포함을 읽기 전용 대조. 실제 시험은 main 실행이며 독립 실행으로 가장하지 않는다. 6skip은 Windows 실제symlink생성권 부재, 별도환경 담당/착수조건은 해당 권한을 가진 격리 시험 환경 확보다.
- 결정/상태: 사용자 지정 B2→B3 연속 단계 종료. B0~B3 코드 출구완료/B4~B7미완료, 전체21/40=52.5%·로컬18/28유지. 문맥·초안/승격·양쪽2.0/1.0보존·현재사용권·키트반려·Host승인복구·질문/결정차수 출구이며 전체T3/운영/브라우저/현업수용 아님.
- 다음/담당/조건: 다음 Codex B4 주관. James 사전 대조·메인 재확인에 따라 대기목록/변경상세, 확정운영root·범위행동, 설명/순서 명령 보강 후 UI 연결. 예상150~240분(종전90~150분 대체). 실제 구현자는 착수 때 core/API·UI·독립시험의 겹치지 않는 파일 소유권을 확정하고 권한/최종UX 독립검토를 진행한다. B4 구현 미착수, B5/B6 단일Studio 및 B7 업데이트/수용 별도.
- 영향/보존: 권고4·7·10/G2-A/B/C→G3-B/C 전진, 제품70% 미달을 테스트수로 숨기지 않는다. branch codex/l2-unified-studio-20260912/HEAD58e666833. 사용자로그 기존10줄 SHA7720cc45…f510/main.py/App.tsx/운영DB·RAW·실역할/원본Starter/원격보존. 로컬미커밋·미푸시, 자동재개·재승인·배포 없음.
- 인계: `docs/handoff/L2_STUDIO_B3_CONTEXT_2026-09-13.md` 최종 증적과 B4 보정, 기존 상세설계 §11 B4 연결 보완 참조. 이전 실행 session2975는 정상 종료했으므로 재대기/동일 실행을 반복하지 않는다.

## Codex B0~B3 최종 통합 실행 — 2026-09-13 09:02 KST

- 작성자/왜 지금: Codex. 독립4P2 및 마지막fixture/선행조회 회귀를확인하여 최종지정통합을실행한다.
- 근거/상태: zmv5h8sq 464PASS/2fixtureFAIL/3skip/307.34초/금지접근0;2.0실제생산자로fixture만수정. c5qffnjy 마지막6PASS/3.71초/SQLite17/소스자산불변/금지접근0. 현재 --b0 --b1 --b2 --b3 session2975,약25분예상. B3 OPEN/전체21/40=52.5%/로컬18/28.
- 검토/결정: 요청Codex·검토Hilbert 신규4P2전부정적종결/추가확정P1·P2없음. 실제통합성공은아직아니다. source/test전원동결,문서만main갱신. 임시RUN만실행/원본쓰기guard유지.
- 다음/인계: main2975종료확인→JUnit/isolation/sourcehash및보존검사→B3출구/문서정리. B4는사전읽기만,후속예상90~150분. 사용자로그SHA7720cc45…f510/운영·원격·main.py/App.tsx보존. 미커밋·미푸시. 실패때만해당소유자좁게동결해제.

## Codex B3 최신 동결/재회귀 — 2026-09-13 08:53 KST

- 작성자/왜 지금: Codex. 선택 회귀 종료와 독립 추가 지적4건 보완 후 소스 전원을 재동결하고 실제 재검증에 들어간다.
- 근거/상태: usage-holds-py4q07im 299PASS/3skip/218초/SQLite338/소스자산불변. 기존 종결 단위시험 원본 failure bundle2쓰기·Git subprocess1시도는 가드 차단으로 wrapper exit1; 원본변경없음. 해당 시험만 tmp cwd+명시GitManager대역/실제임시번들 확인으로 수정, guard유지. 앞반려4실패는해소, B3전체최종판정은아직이다.
- 교차검토: 요청Codex/검토Hilbert 신규P2 4건. Dewey legacy기본writer유지/명시managed 및 v2LIBRARY비계약판정; main 실제TechLead서버2.0opt-in·legacyA/B HTTP·HOTL UNKNOWN/503응답, Hooke 엄격HOTL조회/반영실패31케이스. 정적 재확인 요청 중이며 실행 전 Close하지 않는다.
- 다음/소유: 현재선택session62293, runtime_contract_v2 포함. 전원 source/test freeze확인; 메인이실행/실패분류→필요수정→전원동결→B0~B3전체(약25분). 전체21/40=52.5%, 로컬18/28. B4사전읽기만/구현미착수,예상90~150분.
- 영향/교대: main nodes.execution의계약초안어댑터만추가수정, main.py/App.tsx불변. 사용로그SHA7720cc45…f510/운영DB/원본Starter/실권한/배포/원격보존, 미커밋·미푸시. 첫재개=62293결과확인,전원동결중수정금지. 알려진부분실패는재승인자동전송금지/사건ID보존.

## Codex B3 차수 계약 보완 — 2026-09-13 08:23 KST

- 작성자/왜 지금: Codex. 최신 선택 회귀 종료와 독립 검토·설계 추가 누락이 확인되어 이전 실행 중 상태 및 소유권을 정정한다.
- 근거/판정: usage-holds-dcavqtay 123PASS/4FAIL/1skip/198.25초/SQLite226/금지접근0/소스자산불변. B3 OPEN, 전체21/40=52.5%, 로컬18/28 유지. 실패4건 수정 및 새 회귀 전이다.
- 교차검토: 요청Codex/검토Hilbert 5건(P1취소worker예약/P2가시성·legacy경계·오류분류·부분응답) 수정 후 재검토 요청. Dewey §7.3 감사로 질문/결정 차수 누락을 확인해 B3에 보완한다. 증적 없는 Close 없음.
- 소유권/다음: James kit_app_contract/반려회수시험+새legacy오류시험; Dewey contract_decision/nodes.contract/decision_round시험; Hooke HOTL helper/질문·취소·재개시험; main Factory/Orchestrator/guard/API시험·통합 실행. 현재 소스 편집 허용, 다음 메인 선언 후 전원동결. B3 잔여60~100분(08:15 기준), 선택후전체통합약25분.
- 영향/교대: 기존1.0/Host wire1/State5.3.0 보존, 차수CAS는 서버고정신규 또는 명시 토큰에 적용. 입력 draft UI=B5. 사용자로그/운영DB·원본Starter·실권한·main.py/App.tsx·원격 변경 금지. branch codex/l2-unified-studio-20260912/HEAD58e666833, 로컬 미커밋·미푸시. 첫 재개=각 helper 인터페이스 연결 및 신규회귀.

## Codex B3 검증 재개 — 2026-09-13 08:04 KST

- 작성자/왜 지금: Codex. 04:45경 승인보조 한도/환경 오류 이후 사용자가 계속 진행을 요청했고 08:00경 명령 실행이 복구되어 실제 검증을 재개한다.
- 근거/상태: `usage-holds-_q7bmbx7` 선택176PASS/2symlink권한skip/411.23초/임시DB246·원본쓰기도금지DB접근도0·소스자산불변. 이후 §6.1 누락2개를 구현했으므로 B3 OPEN이며 새 소스 통과로 승계하지 않는다. 신규37파일 AST/diff 통과. `usage-holds-6wyns_sv` 테스트 사용자상수1수집오류는 수정, focused 재실행 중.
- 변경/소유: James kit_app_contract 반려 및 test_b3_kit_rejection; Dewey studio_contract_reconcile 및 helper시험; Hooke promotion/execution_guard시험; Codex 실행 예약·bound state CAS/Factory·신규 반려/복구 API·공통권한표·실제 임시HTTP시험·runner. 모든 source 현재 freeze, docs만 갱신.
- 교차검토: 요청Codex/검토Hilbert. 신규 API·원장/상태 복구·경합 최종 검토 재요청. Dewey에게 §7.3 질문/결정 차수 식별자 명시 제공 추가 누락 감사를 요청했다. 이전 한도 오류 이후 새 완료 판정 전이다.
- 다음/담당/착수조건: main focused 결과 분류→중요 지적/명시 누락 보완→B0/B1/B2/B3 전체 지정 회귀 약25분→출구 증적 대조. 재개 기준 B3 잔여45~75분. 전체21/40=52.5%, 로컬18/28 유지. B4 UI 다음, 별도 수용 미완료.
- 교대 체크포인트: branch codex/l2-unified-studio-20260912/HEAD58e666833, B0~B3 로컬 미커밋·미푸시. interaction_log SHA7720cc45…f510 재확인. 운영DB/RAW/실역할·실승인/Starter 원문/배포 및 main.py·App.tsx 보존. 첫 재개=현재 focused session4901 확인. 운영 권한 변경·무승인push·테스트 수 제품점수 가산 금지.

## Codex B3 격리 검증 체크포인트 — 2026-09-13 03:57 KST

- 작성자/왜 지금: Codex. B3 첫 실제 격리 회귀가 진행 중이므로 중간 결과를 완료로 오인하지 않도록 증거·잔여 보강을 기록한다.
- 근거/상태: 첫 `usage-holds-zvb9nz0c`는 seed 이전 NODES 수집3오류(동일원인)·금지접근0·소스/자산불변. James가 수집 초기화2곳을 수정했고 현재 `usage-holds-8mhv496g` --b3 진행 중이다. 완료 판정 전, whole source freeze 유지. git diff --check 통과.
- 교차검토: 요청Codex/검토Hilbert·Hooke·Dewey. 원장 오류 분류/exact context, 고정 승인revision/지문, 제공할 release의 proof 재대조, parsed RAW checksum 지적은 정적 재확인. 실제 통과와 구별한다. marker write 중 hard kill의 완성 임시파일 복구, 일반 게시 원문 고정 전달, 양쪽 readiness/승격 지문 최신판 제거는 후속 보강 필요.
- 다음/담당/착수조건: 회귀 종료 후 Codex가 일반 게시·Host/준비도·marker 및 실제 게시 회귀를 보완하고 James가 담당 실패를 수정. 전원 재freeze→B0/B1/B2/B3 통합→독립 최종확인. 예상 잔여45~75분. 임시 DB/파일만 허용하며 운영·실사용 완료를 주장하지 않는다.
- 진척/영향: 전체21/40=52.5%, 로컬18/28 유지. B4~B7 별도 미완료. 기존 사용자로그 SHA7720cc45…f510 재확인, 로컬 미커밋/미푸시. 이 문서는 상태 보고이며 추가 작업을 중단하는 신호가 아니다.

## Codex B3 연결 구현 중간 점검 — 2026-09-13 03:05 KST

- 작성자/왜 지금: Codex. 사용자 지정 B2→B3 연속 진행 중 생산자/API/소비자 연결이 추가되어 담당 범위와 아직 미검증인 사실을 기록한다.
- 근거: 새 studio_drafts/project_files/bootstrap/project_context/release_context, advisor·kit child router, Factory 시작/재개/체크포인트/복구/릴리스, Host 발급·요청/승격. 21개 파일 AST 검사만 통과했으며 B3 pytest는 아직 실행하지 않았다.
- 결정/영향: 고정 Blueprint 판본·ProcessContext·operation ID와 현재 권한을 분리한다. FS/Advisor/원장 분산 원자성은 주장하지 않으며 부분 프로젝트는 SETUP_INCOMPLETE. Host 승인 앱 사용(AGENT_EXECUTE)과 Factory 생성 가동(PROJECT_RUN)을 혼동하지 않는다. 1.0 문서 바이트·Host wire1·State5.3.0은 보존 대상이다.
- 분담/검토: Codex=API·saga·Factory/Host·실행경계시험; James=ProcessContext·kit_app_builder/kit_app_contract/project_data_context·시험; Hooke=2.0 일반계약·materializer·고정판 실제 소비 경계 검토; Dewey=revision/ledger 및 초안·saga/API 시험; Hilbert=독립 read-only 보안검토. 공유 파일은 1명만 편집한다.
- 다음/착수조건: 신규 계약 인터페이스와 고정 Snapshot 실제 소비 연결을 확정하고 전원 source freeze 후 --b3 격리 실행. runner는 DATA/PROJECTS/LIBRARY를 새 RUN으로 옮기고 기존 Starter/팩/data/projects/library/workspace 쓰기를 차단한다. 중요 지적 해소 및 통합 회귀 후에만 B3 완료 판정. 예상 잔여80~130분(리스크 발견 시 갱신).
- 진척/주의: 전체21/40=52.5%, 로컬18/28 유지. 70% 목표를 시험·파일 수로 가산하지 않는다. B4~B7 UI/현업수용 미완료. 코드 로컬 미커밋·미푸시, 운영 DB/실역할/인증/앱·배포 및 사용자 interaction_log 변경 없음.

## Codex B2 출구 / B3 실행 — 2026-09-13 02:27 KST

- 작성자/왜 지금: Codex. 사용자 지정 두단계 연속진행 중 B2 검증·독립검토가 끝나 B3 소유권과 인계를 고정한다.
- 근거/상태: `output/usage-holds-2kfaqye_` 662PASS/1symlink권한skip/148.00초/S807 임시DB·자산/소스불변/금지접근0. B2 코드출구완료, 운영·UI·현업수용아님. 전체21/40유지.
- 검토: 요청Codex/검토Hilbert. 원4건+후속2건 지적을수정하고정적범위추가P1/P2없음확인. 후속실제회귀포함. 이전654PASS6FAIL/660PASS1skip은중간이력, 최종과합산금지.
- 결정/영향: 불변후보8L1·29L2는 NO_DATA/REFERENCE_ONLY, 기존1.0.0 파일불변. 새전용DP표/좁은registryguard 방식. 일반storeALTER·영구트리거제안은미적용. 사용자로그SHA7720cc45…f510유지.
- 다음/담당/착수조건: B3즉시시작120~180분예상. Codex=advisorAPI/bootstrap·Factory/kit/Host배선, James=serverProcessContext새모듈/시험, Hooke=runtime1.0보존+2.0/일반컴파일4파일·시험, Dewey=advisor revision·bootstrap원장멱등전용모듈/시험, Hilbert=독립보안검토. 공유파일1편집자, 생성코드테스트는새RUN쓰기보호아래메인이수행.
- 관문/인계: 권고4·7·10/G2-A/B/C→G3-B/C. docs/handoff/L2_STUDIO_B2_SETUP_2026-09-13.md. B4~B7 UI·현업수용은미완료, B3도실측전완료표시금지. 로컬미커밋/미푸시.

## Codex B2 자동 연속 진행 체크포인트 — 2026-09-13 02:13 KST

- 작성자/왜 지금: Codex. 사용자가 현재 이후 두 단계와70% 목표를 명시해 B2/B3 범위·안전 조정·분담을 고정한다.
- 근거: 승인 설계 execution §8/11/14, process_installation.py/process_kit_instances.py/process_pack_artifacts.py, PROGRESS02:13. 상위 권고4·7·10/G2-A/B/C→G3-B/C/원료구매 폐루프 직접 필요.
- 결정/상태: B2 구현 검증 전, B3 저장 모듈만 병렬 준비. 전체21/40 유지. 자동검토에서 기존store ALTER/트리거 거절 → 미적용, 신규전용테이블 및 동일버전 충돌 가드로 영향 축소. 기존Starter1.0.0 원문·운영DB·사용자로그 불변.
- 교차검토: 요청Codex/검토Hilbert. P1설치자회수후인수, P2시도CAS·기존instance미리보기·승인직전DP검증 수정, 재검토/실측 미완료. Hooke팩완료(실행0), James B2시험 작성, Dewey B3advisor저장전용파일 작성. 공유파일 한 편집자.
- 다음/담당/착수조건: Codex가 원본 쓰기 차단+새SQLite audit runner로 B2 시험. 모든중요지적/회귀PASS후 B3 context/API/일반·키트2.0연결. 예상 B2잔여30~60분/B3초기120~180분. 시험중검사소스freeze.
- 영향/인계: 신규candidate는 DOMAIN_REVIEW_REQUIRED/NO_DATA/REFERENCE_ONLY이며 앱 생성·실적 인증·역할 부여가 아니다. B4~B7/실사용/운영적용 별도미완료. 70%숫자를위해기준완화금지. 현재로컬미커밋/미푸시, data/interaction_log.jsonl 사용자변경10줄 보존(SHA7720cc45…f510).

## 팀 보드 기록 규약 — 작성 주체·판단 배경·인계 의무

> 적용일: 2026-07-29 / 요청자: Supervisor / 목적: 팀 간 맥락 손실과 책임 공백 방지

모든 신규·갱신 항목은 아래 필드를 **반드시** 포함한다. 단순히 “진행 중”, “완료”, “검토 대기”만 남긴 기록은 유효한 인계로 보지 않는다.

| 필드 | 기록 기준 |
|---|---|
| `작성자 / 기록 시각` | 실제로 이 항목을 남기거나 갱신한 팀원과 시각. 예: `Codex / 2026-07-29 14:20 KST` |
| `왜 지금 기록하는가` | 작업 시작·결정 변경·위험 발견·검증 완료·인계 중 무엇 때문에 기록하는지 한 문장으로 명시 |
| `근거` | 확인한 코드·문서·커밋·테스트·실행 ID 중 최소 하나를 경로 또는 식별자로 연결 |
| `결정 / 상태` | 확정·조건부 승인·보류·차단 중 하나와 그 이유. “완료”에는 완료 기준 충족 근거를 포함 |
| `다음 행동 / 담당` | 다음에 실제로 할 일, 담당자, 착수 조건. 타 팀원의 검토가 필요하면 검토 대상과 질문을 명시 |
| `영향·주의사항` | 다른 작업·데이터·권한·테스트에 영향을 주는지와 피해야 할 변경을 기록 |
| `교대 체크포인트` | 마지막 확인 상태, 실제 변경·미변경 범위, 검증 증거, 커밋·푸시 상태, 첫 재개 행동, 금지 범위. 이 항목이 없으면 세션 종료 기록은 인수인계 완료로 보지 않음 |

### 표준 기록 양식

```md
### [식별자] 제목
- 작성자 / 기록 시각: 이름 / YYYY-MM-DD HH:MM KST
- 왜 지금 기록하는가: …
- 상태: 진행 중 | 조건부 승인 | 검증 대기 | 완료 | 보류 | 차단
- 결정 및 근거: … (`경로`, 커밋, 테스트, 실행 ID)
- 영향·주의사항: …
- 다음 행동 / 담당 / 착수 조건: …
- 교대 체크포인트: 마지막 확인 상태 · 변경/미변경 범위 · 검증 증거 · 커밋/푸시 상태 · 재개 지점 · 금지 범위
```

### 운영 원칙

1. 다른 팀원의 항목을 갱신할 때는 `작성자`에 본인 이름을 쓰고, 원 작성자·원 커밋을 함께 남긴다. 타인의 판단을 덮어쓰지 않는다.
2. 교차검토는 `검토 요청자`, `검토자`, `판정`, `판정 근거`, `후속 조치`를 각각 기록한다. “승인”만으로 Close하지 않는다.
3. 코드·데이터·권한 모델을 바꾸는 작업은 영향 범위와 되돌림/보류 방법을 남긴다. 실행하지 않은 제안은 “계획”으로 표시한다.
4. 새 기록은 해당 항목의 상단에 추가하고, 이전 판단을 수정하면 취소·대체 이유를 남긴다. 이력 삭제나 무표시 덮어쓰기는 금지한다.
5. 세션 종료·담당 교대 시 `교대 체크포인트`를 갱신한다. 별도 인수인계 파일을 만드는 것으로 대신하지 않으며, 실제 통합 전 시안·초안을 `AI_HANDOFF.md`에 완료처럼 올리지 않는다.

---

> [!NOTE]
> **과거 히스토리 아카이브**: 2026-08-18 이전의 누적 히스토리 전문은 [`.agents/archive/TEAM_BOARD_archive_20260818.md`](file:///c:/WorkSpace/gemini_agent_team_verG/.agents/archive/TEAM_BOARD_archive_20260818.md) 및 [`docs/archive/TEAM_BOARD_archive_20260818.md`](file:///c:/WorkSpace/gemini_agent_team_verG/docs/archive/TEAM_BOARD_archive_20260818.md)에 안전하게 영구 보존되어 있습니다.

---

## 🚀 활성 및 최근 주요 진행 항목

### [SINGLE-ENTRY-01-20260916] 단일 진입·뒤로/앞으로·새로고침 — 결함 3종 수정. READY_FOR_REVIEW

- 작성자 / 기록 시각: Claude Code / 2026-09-16 00:41 KST
- 왜 지금 기록하는가: DRAFT-OPEN-01 실화면 확인 → 격리 환경 정리 → 리뷰 §6 순서 5 착수분까지 끝냈다. 상세는 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md`.
- 상태: **READY_FOR_REVIEW · 커밋/푸시 없음**(기준 HEAD `2380143ea`)
- 결정 및 근거:
  - ★ **실화면 확인을 RUN 했다**(DRAFT-OPEN-01): 격리 워크트리+8086+5181 에서 사람이 로그인한 뒤, 초안 1판 링크 → **그 판본 내용이 편집기에 채워짐**, 2판 링크 → **2판**(최신으로 조용히 안 바뀜), `revision=9`·`consultation` 이 **서로 다른 문구**로 거절, advisor 경로 요청 **전부 GET**. 원문 GET 질의가 `context_root_id=org-laxs-mnm&scope_node_id=plant-afs-smelting-01&revision=1` — **서버가 준 소유 경계 + 지정 판본**이 실제 제품에서 증명됐다.
  - ⚠️⚠️ **실화면이 내 결함 둘을 잡았다**: ① 422 를 몽땅 「초안 링크를 확인하세요」로 접어, 회사·조직 미선택인데 **링크를 의심하게** 만들었다 → `PROCESS_CONTEXT_REQUIRED` 만 갈라 별도 문구. ② `useEffect` 의존성에 `ownership` **객체**를 넣어 같은 GET 이 **6번** 나갔다 → 원시값 키로 6→2(StrictMode 이중분).
  - ★★★ **순서 5 결함 3종**: ⓐ `routeRestored` 초기값이 project·mega 만 봐서 **kit_app·draft 는 확인 전에 URL 대상이 지워졌다**(그 상태로 새로고침하면 진입 대상이 사라진다. 닫는 쪽은 이미 셋 다 true 를 부르고 있었고 **초기값만 빠져 있었다**). ⓑ `popstate` 를 **아예 듣지 않아** 뒤로가기가 주소창과 화면을 어긋나게 뒀다 → **사용자 결정 A**: 다시 «여는» 게 아니라 다시 «확인»한다. ⓒ 커밋 컴포넌트가 콜백을 의존성에 두어 **부모가 다시 그릴 때마다 효과가 재실행** — `setCurrentProject` 반복은 wbs·state·hotl·feed **네 요청**을 다시 쏜다. 콜백을 ref 로 분리.
  - 검사: `check-project-entry` 36→**48**, 그 외 17·25·25·14·36 전부 exit 0, build PASS. **프런트 전용**(App.tsx + 검사 스크립트). ★ 새 검사는 전부 **실행**이다 — App 의 초기식·popstate 효과·커밋 컴포넌트를 AST 로 뽑아 **가짜 window·가짜 React 훅으로 실제로 돌린다**(소스 문자열 검사 아님). 극성: ⓐ 1건 · ⓑ 4건 · ⓒ 3건, 각각 그 시험만 죽는다.
- 영향·주의사항:
  - ⚠️⚠️ **[팀 전체] 격리 화면 검증 절차를 확보했다** — `demo_data` 서버는 폐지됐고 `core/paths.py` 는 환경변수 덮어쓰기를 설계상 막는다. 방법은 **워크트리 + 주 트리 venv 로 워크트리 run.py**. ★ 함정 둘: ① `seed_starter_data.py` 는 **조직·사용자를 만들지 않고**, 폐지된 `run_local_demo._org()` 는 **앱이 안 읽는 `org.db`** 에 쓴다(제품은 `master/master.db`) — 그래서 「심었는데 0명」이 된다. ② 로그인 401 은 **비밀번호가 아니라 계정 부재**일 수 있다(`login` 이 열거 방지로 두 사유를 같은 문구로 답한다). 판별법: `verify()` 는 불리기만 하면 `auth.db` 를 만든다 — 시도 뒤에도 그 파일이 없으면 계정 부재다.
  - ⚠️ **탐침 사고**: 극성 탐침의 원복 쓰기가 `OSError` 로 실패해 **변이 한 줄이 디스크에 남았다.** grep 으로는 온전해 보였고(같은 문자열이 다른 위치에도 있어 개수가 맞았다) **검사를 돌려서야** 드러났다(44/1). 이후 원복을 **해시로 단언**한다. 교훈: 원복은 「했다」가 아니라 **「같아졌다」**로 확인한다.
  - ⚠️ **실제 브라우저 재확인 NOT_RUN** — 이번 3종은 실행 검사·극성으로만 증명했다. 앞선 실화면 확인은 «수정 전» 코드 기준이다.
  - 격리 환경은 **정리 완료**(서버 2개 중지 · 워크트리 제거 · 임시 launch 항목·env 파일 제거). 다른 세션 워크트리 7개는 손대지 않았다.
- 다음 행동 / 담당 / 착수 조건: **Codex** 검토(핵심: 결정 A 구현 범위 · 진입 대상 URL 보존 규칙 · 미검증 항목). 커밋 여부는 별도 지시 대상.
- 교대 체크포인트: 마지막 확인 상태 = 순서 5 착수분 완료, **미커밋** · 변경 범위(이번) = `frontend/src/App.tsx`, `frontend/scripts/check-project-entry.mjs` · 앞선 묶음 = `frontend/src/{lib/studioRequirementDraft.ts,factory/studioDraftEntry.ts}` 등 · 미변경 = 운영 DB·RAW·키·사용자 로그, 다른 세션 워크트리 · 검증 증거 = 프런트 48+17+25+25+14+36 exit 0 · build PASS · 극성 8종 · 커밋/푸시 = **없음** · 재개 지점 = Codex 검토 회신 · 금지 범위 = 실제 브라우저 결과 사칭, 원복 미확인 탐침, 원격 Git

### [DRAFT-ENTRY-01-20260915] 초안 진입 — 경계를 «받지 않고 찾는다». 합동 301 passed / 0 failed

- 작성자 / 기록 시각: Claude Code / 2026-09-15 23:27 KST
- 왜 지금 기록하는가: 리뷰 §6 순서 4 `draft 진입` 을 수행 완료했다. 상세 보고는 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md`, 설계는 `docs/design_l2_studio_entry_readers_2026-09-15.md` §12.
- 상태: **READY_FOR_REVIEW · 커밋/푸시 없음**(기준 HEAD `2380143ea`)
- 결정 및 근거:
  - `GET /api/v1/advisor/drafts/{draft_id}/entry-metadata?kind=&revision=` 신규. ★★★ **경계를 인자로 받지 않는다** — 조사에서 `advisor_v2_drafts.draft_id` 가 **PRIMARY KEY** 고 초안이 자기 경계를 들고 있음을 확인했다. 서버가 id 로 찾아 소유 문맥을 읽고 선택 문맥(헤더)과 대조한다. ⚠️ 기존 `GET /drafts/{id}?context_root_id=…` 는 **그대로 뒀다** — 그 경로는 이미 그 문맥에서 일하는 화면이 쓰는 것이라 맞다. 문제는 **URL 로 들어온 초안**이고 그때 프런트는 문맥을 모른다.
  - 판정 순서: 종류·판본 형식 → 선택 문맥 확정 → 소유 문맥 판독 → **기존 `_authorize`** → 판본 존재(제품 경로, 내용은 버린다). ★ **서버 권한 정책 변경 0건.**
  - ⚠️⚠️ **`consultation` 을 조용히 열지 않았다.** 종류 둘이 다른 저장소에 살고 **판본은 blueprint 에만 있는데** URL 문법은 두 종류 모두에 판본을 필수로 받는다. 버리면 kit_app `releaseId` 와 같은 결함이라, 서버가 `STUDIO_DRAFT_KIND_UNSUPPORTED`(422)로 **말하고** 프런트도 「없다」와 다른 문구로 보여 준다. **결정 요청**: ⒜ 지원 전으로 두고 URL 문법에서 판본 제거(권장) / ⒝ `consultation_turns.turn_no` 결속(제품 의미를 새로 정하는 일이라 내 범위 밖).
  - **flow 공통부 추출**(Codex 권고 4): `project`·`kit_app` 의 flow 본체가 **글자까지 같아서** 셋째를 붙이며 `frontend/src/factory/studioEntryFlow.ts` 로 뽑았다. ⚠️ **오류 코드·메시지는 뽑지 않았다** — 공통인 것은 «수명»뿐이다. 기존 43·14건 그대로 통과가 그 증거다.
  - 실측: 합동 9스위트 **301 passed / 0 failed / exit_code 0**(`output/usage-holds-aifmeq2d`). 프런트 43+16+25+14+36 PASS, build PASS.
- 영향·주의사항:
  - ⚠️⚠️ **[팀 전체] 시험이 내 시험의 구멍을 잡았다.** 극성으로 재 보니 **권한 대조를 통째로 지워도 28건이 통과**했다 — 문맥 시험들이 전부 **앞선 관문(`explicit_context`)에 가려져** 있었고 권한 층은 한 번도 판정한 적이 없었다. 「조직에 없는 노드」를 쓰면 거기서 막히므로, **실재하는 남의 부서**를 골라야 권한 층만이 막는 자리가 된다. 같은 함정이 다른 시험에도 있을 수 있다.
  - ⚠️ **거절 문구가 갈라져 있었다**: 「없는 초안」과 「다른 문맥의 초안」이 다른 문구로 답했다 — 그 차이가 존재를 알려 준다. 문구를 짓지 않고 권한 층의 `missing()` 을 그대로 쓰게 고쳤다.
  - ⚠️ `tests/test_route_authority_table.py::test_viewer_is_blocked_by_the_table` 4건이 격리 러너에서 **ERROR**(`fixture 'ecm_org_seed' not found`) — 앞서 알린 `repository_conftest_loaded: false` 와 **같은 뿌리**이고 그 파일은 미변경이다. ★ 표↔라우터 양방향 대조 4건은 통과(새 GET 경로가 표를 안 깬다). 다만 그 스위트는 **이 러너에서 전부 검증되지 않는다.**
  - ⚠️ 확인된 초안을 **여는 화면이 아직 없다**. `BuildStartDialog` 는 밖에서 받은 초안을 싣는 자리가 없다 — 없는 화면을 지어내지 않고 인계한다.
  - 앞선 승인 작업과 `data/interaction_log.jsonl` 보존.
- 다음 행동 / 담당 / 착수 조건: **Codex** 검토 + 위 결정 요청 ⒜⒝. 다음은 리뷰 §6 순서 5 **단일 진입·히스토리·UI 수용**(실제 브라우저 필요)이며 범위 지시 대기. 커밋 여부도 별도 지시 대상.
- 교대 체크포인트: 마지막 확인 상태 = 서버·프런트 구현·검사 완료, **미커밋** · 변경 범위 = `api/routes/studio_draft_control.py`, `core/advisor_revision_store.py`, `tests/test_b6_draft_entry.py`(신규 30건), `frontend/src/factory/{studioEntryFlow.ts,studioDraftEntry.ts,StudioDraftEntryGate.tsx}`(신규) + `{studioProjectEntry,studioKitAppEntry}.ts`, `frontend/src/App.tsx`, `frontend/scripts/{check-draft-entry.mjs(신규),check-project-entry.mjs,check-kit-app-entry.mjs}`, 설계안 §12 · 미변경 = 앞선 승인 작업, 운영 DB·RAW·키·사용자 로그 · 검증 증거 = `output/usage-holds-aifmeq2d`(301/0) · 프런트 5스크립트 exit 0 · build PASS · 극성 5종 · 커밋/푸시 = **없음** · 재개 지점 = Codex 검토 또는 순서 5 지시 · 금지 범위 = 실제 브라우저 결과 사칭, 없는 화면 발명, 원격 Git

### [MEGA-ENTRY-01-FIX1-20260915] Codex 핵심 검토 보완 — 합동 검사 155 passed / 0 failed

- 작성자 / 기록 시각: Claude Code / 2026-09-15 23:12 KST
- 왜 지금 기록하는가: Codex 핵심 검토(`docs/handoff/CODEX_MEGA_ENTRY_REVIEW_2026-09-15.md`)의 보완 지시 셋을 반영 완료했다. 아래 [MEGA-ENTRY-01-20260915] 의 판단을 **취소하지 않고 보완**한다. 상세는 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md`.
- 상태: **READY_FOR_REVIEW · 커밋/푸시 없음**(기준 HEAD `2380143ea` 그대로)
- 결정 및 근거:
  - ★★★ **보완1 — 지적이 맞았다. 내가 적어 놓고 만들지 않았다.** 설계안에 「Gate 가 거절한다」고 쓰고 구현하지 않아, 서버가 `is_mega_project` 를 정확히 답해도 **아무도 그 사실을 쓰지 않았다** → 메가 링크로 일반 프로젝트가 열렸다. **적은 것과 만든 것이 다르면 적은 쪽은 통제가 아니다.** App 이 «메가로 요청했다»는 사실 자체를 보존하고(`megaChildId` → `megaRequest`), Gate·flow·reader 까지 `requireMega` 를 내려 **명시 true 일 때만** 진행한다(`ENTRY_NOT_MEGA`). 자식 유무와 무관하다.
  - **보완2 — 「같은 limit 로 바꾸면 된다」던 내 제안도 틀렸다.** 창이 가득 차면 새 사건이 생겨도 길이는 안 는다. 건수 비교 자체를 버리고 ① 시험 자신의 감사 저장소(격리 러너는 `repository_conftest_loaded: false` 라 conftest 격리가 **안 걸린다** — 실측) ② 창을 0·12·120 으로 **일부러 채우고** ③ 요청 «직전» 표식 이후에 추가된 사건만 본다. ⚠️ 운영 로그를 지우거나 비우지 않았고 제품 로직·단언 약화·skip/xfail 없다.
  - **결정B — 503 을 404 로 접지 않고 «순서» 를 고쳤다.** 부모 사실만으로 끝나는 거절(비메가·목록 밖·자기 자신)을 **자식을 읽기 전에** 처리한다. 읽고 나서 거절하면 그 읽기가 실패할 때 503 이 나가 「없는 자식」과 「관계 밖이지만 존재하는 자식」이 구분된다.
  - 실측: **동일 5파일 합동 155 passed / 0 failed / exit_code 0**(`output/usage-holds-d6aphsu8`, 직전 147/1FAIL). 프런트 43+25+14+36 PASS, build PASS.
  - ★ 극성 증명: 감사 기록 호출을 지우니 **3건 전부(0·12·120) 실패**. 같은 모양의 다른 기록기 둘을 지웠을 때는 14 passed — 즉 이 검사가 **정확히 그 경로**를 본다. 임시 수정은 전부 해시 일치로 원복.
- 영향·주의사항:
  - ⚠️ **[팀 전체] 격리 러너(`scripts/verify_data_usage_holds.py`)에서는 저장소 conftest 가 로드되지 않는다**(`repository_conftest_loaded: false`). 즉 **conftest 의 감사·원장 격리에 기대는 시험은 이 러너에서 격리되지 않는다.** 그런 시험은 자기 안에서 직접 격리해야 한다. 이번 감사 검사 결함의 실제 뿌리가 이것이다.
  - ⚠️ 같은 거부를 기록하는 곳이 **셋**이다(`api/routes/mcp_control.py` 둘, `core/crosswalk.py` 하나). 이번 경로는 `mcp_control:45` 하나만 탄다 — 나머지 둘은 이 요청으로 **검증되지 않는다.**
  - ★ **판독 장애가 항상 503 인 것이 아니다**: `project_meta.json`(소속) 손상은 **404**(기존 PDP 은폐), `latest_state.json`(상태) 손상은 **503**, 상태 파일 **없음**은 200+false(레거시 보존). 설계안 §11.2 에 표로 고정했다.
  - 앞선 승인 작업과 `data/interaction_log.jsonl` 보존. **서버 권한 변경 없음.**
- 다음 행동 / 담당 / 착수 조건: **Codex** 재검토. 다음은 **draft 진입**(40~60분)이며 범위 지시 대기. 커밋 여부도 별도 지시 대상이다.
- 교대 체크포인트: 마지막 확인 상태 = FIX1 반영·검사 완료, **미커밋** · 변경 범위 = `api/routes/factory_control.py`, `frontend/src/factory/{studioProjectEntry.ts,StudioProjectEntryGate.tsx}`, `frontend/src/App.tsx`, `frontend/scripts/check-project-entry.mjs`, `tests/{test_b6_mega_entry.py,test_m2_entry_gates.py}`, 설계안 §11 · 미변경 = 앞선 승인 작업 전부, 운영 DB·RAW·키·사용자 로그·감사 운영 로그 · 검증 증거 = `output/usage-holds-d6aphsu8`(155/0) · 프런트 4스크립트 exit 0 · build PASS · 극성 3종 · 커밋/푸시 = **없음** · 재개 지점 = Codex 재검토 회신 또는 draft 범위 지시 · 금지 범위 = 실제 브라우저 결과 사칭, 운영 감사로그 조작, 원격 Git

### [MEGA-ENTRY-01-20260915] 메가 직접 진입 — 서버가 부모·자식 «관계»를 판정한다. READY_FOR_REVIEW

- 작성자 / 기록 시각: Claude Code / 2026-09-15 22:57 KST
- 왜 지금 기록하는가: Codex 지시서(`docs/handoff/CLAUDE_CODE_EXECUTION_ORDER_2026-09-15.md`)의 MEGA-ENTRY-01 을 수행 완료했다. 상세 보고는 지정 보고 파일 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md` 에 있고, 여기에는 팀이 알아야 할 것만 남긴다.
- 상태: **READY_FOR_REVIEW · 커밋/푸시 없음**(기준 HEAD `2380143ea`, 브랜치 `codex/l2-unified-studio-20260912`)
- 결정 및 근거:
  - `GET /api/v1/factory/{project_id}/entry-metadata[?child=<ID>]` — **새 엔드포인트를 만들지 않고** 기존 경로를 호환 확장했다(설계안 §10, 변경 «전» 확정). 응답에 `is_mega_project`(항상)와 `child`(요청 시 객체, 아니면 null) 두 칸만 늘었다. **하나의 확인 응답**이라 프런트가 두 번 물어 관계를 추론하지 않는다.
  - ★★★ **관계의 출처가 «둘» 이다** — 부모의 `sub_projects_map` 과 자식의 `parent_project_id` 가 **서로 다른 파일**(각자의 `latest_state.json`)에 있고 어긋날 수 있다. 한쪽만 보면 조용히 뚫린다: 자식이 남의 메가에 끼어들거나, 부모가 남의 자식을 끌어온다. **둘 다 가리킬 때만** 관계로 인정한다.
  - ★ 소속은 **좁혀서** 읽는다(세 칸만). `latest_state.json` 은 «실행 상태» 파일이라 프로젝트가 도는 동안 계속 바뀌는데, 통째로 들고 나와 재확인에서 비교하면 **가동 중인 프로젝트가 진입할 때마다 503** 이 된다. 덤으로 「상태·계획 원문을 주지 않는다」가 저절로 지켜진다.
  - 실측: 서버 **147 passed / 1 failed**(격리 실행 `--strict-writes`, `sources_unchanged: true`), 프런트 **36+25+14+36 PASS**, **build PASS**(`tsc -b` 포함). 이전 실측(서버162·프런트363)은 합산하지 않았다.
  - 극성 증명 6건 — 통제를 하나씩 빼니 **그 통제를 단언한 시험만 정확히 죽었다**(서버 6·3·2건, 프런트 1·1·1건). 임시 수정은 전부 **해시 일치로 원복**.
- 영향·주의사항:
  - ⚠️⚠️ **[팀 전체에 알림] `tests/test_m2_entry_gates.py::test_gate_b_denial_is_written_to_the_audit_log` 는 순서 의존이다.** 단독 12 passed, 다른 스위트와 합동 실행하면 실패한다. 기전 확정: `before = len(audit.recent(limit=100))` 로 세고 `events = audit.recent(limit=10)` 로 다시 읽어 `len(events) > before` 를 단언한다 — **감사 사건이 10건을 넘으면 성립 불가**다. 내 변경과 접점 0(`/api/v1/mcp/resolve` 경로). 지시 없이 감사 통제 의미를 바꾸지 않으려고 **고치지 않았다.** 제안: 같은 limit 으로 읽거나 「직전 사건 이후의 새 사건」을 보게 한다.
  - ⚠️ **프런트가 새 칸을 엄격히 요구한다** — `is_mega_project` 가 없으면 `malformed`. 같은 저장소에서 함께 배포되므로 택했으나 **서버보다 프런트가 먼저 나가면 프로젝트 진입이 전부 막힌다.** 관용으로 바꿀지는 결정 대상.
  - ⚠️ 관찰: `_safe_id` 의 `_ID_RE` 에 **길이 상한이 없다**(프런트는 160자로 막는다). 부모 `project_id` 도 처음부터 같은 성질이라 이번 범위에서 바꾸지 않았다.
  - `tests/test_b6_project_entry.py` 의 **DTO 정확 고정 단언**에 두 칸을 더했다. 그 단언은 「응답에 뭐가 더 따라 나오지 않는가」를 지키는 유일한 통제이므로 **느슨하게 풀지 않았다** — 정확한 집합을 유지한 채 갱신했다.
  - 지시서 §1 의 앞선 승인 작업과 `data/interaction_log.jsonl` 은 **손대지 않았다.** 서버 **권한 변경 없음**.
- 다음 행동 / 담당 / 착수 조건: **Codex** 가 핵심 diff(`api/routes/factory_control.py` 의 `get_project_entry_metadata`)와 위 결정 두 가지를 검토한다. 다음 후보는 리뷰 §6 순서 4 **draft 진입**이며 **별도 범위 지시 대기**. 커밋 여부도 별도 지시 대상이다.
- 교대 체크포인트: 마지막 확인 상태 = 서버·프런트 구현과 검사 완료, **미커밋** · 변경 범위 = `api/routes/factory_control.py`, `tests/test_b6_mega_entry.py`(신규 43건), `tests/test_b6_project_entry.py`, `frontend/src/factory/studioProjectEntry.ts`, `frontend/src/factory/StudioProjectEntryGate.tsx`, `frontend/src/App.tsx`, `frontend/scripts/check-project-entry.mjs`, 설계안 §10 · 미변경 = 지시서 §1 의 앞선 승인 작업 전부, 운영 DB·RAW·키·사용자 로그 · 검증 증거 = `output/usage-holds-6elfprs_` · 프런트 4스크립트 exit 0 · build PASS · 극성 6건 · 커밋/푸시 = **없음**(지시 전 금지) · 재개 지점 = Codex 검토 회신 또는 draft 진입 지시 · 금지 범위 = 실제 브라우저 결과 사칭, 이전 실측 합산, 운영 DB pytest·서버 기동, 원격 Git

### [L2-STUDIO-B1-CLOSED-20260913] ECM v2 저장·권한·CAS 지정 출구 완료 / 다음 B2

- 작성자 / 기록 시각: Codex / 2026-09-13 01:43 KST
- 왜 지금 기록하는가: Supervisor의 설계 순차 실행·단계별 전체 진척 보고 및 다음 작업 예상 시간 추가 요청에 따라 B1 구현/회귀/독립 검토 결과를 인계한다.
- 상태: **B1 지정 안전 저장 출구 완료**, B0 완료 유지·B2~B7 미완료. 전체21/40=52.5%, 로컬18/28≈64%, D02=2/4 유지.
- 결정 및 근거: `docs/handoff/L2_STUDIO_B1_STORAGE_2026-09-13.md`. ECM의 root/mode/configuration 필드·head/changes/outbox, strict L1/L2 문서, 명령형 초안·별도 승인/반려·CAS, 불변판·고정 지문·현재 권한·구 writer/reader/복제 보호 및 API 배선. 새 프로세스 DB나 운영 권한 배정은 만들지 않았다.
- 검증: `output/usage-holds-95pftf6f/tests.xml`·`isolation.json`, **550 passed / 111.18초**, SQLite670경로 임시 루트만·검사 소스 불변·금지 접근0·전역 conftest 없음. 중간150통과/1실패→160→543→548은 별도 이력이다. 기존 B0 보류·실적 인증 회귀 포함, 전체T3/브라우저/실사용 검증은 아니다.
- 교차검토: 요청 Codex / Hilbert(`01a09660-955f-7570-855e-d40b068e858e`) / v1 상위·industry 누락, tenant 삽입 경쟁, head 포인터/기준판 지문 손상 지적 수정 및 정적 한정 PASS. 마지막 입력422 변환도 PASS. 검토자는 DB/테스트/수정 없음. James(`01a09668-1a60-72a1-9bb1-79746e3d6888`)는 격리 부정 시험25케이스 작성만 수행했다. 모두 종료.
- 영향·주의사항: 권고4·7·10/G2-A/B/C에서 G3로 전달할 저장 기반 전진. 기존 v1이 있으면 CONTEXT_REVIEW_REQUIRED이며 실제 이관 미구현. 팩·실제 바인딩·상위 판 고정 변형·분리통합·outbox 송신 worker·UI는 후속. audit_delivery=PENDING을 송신 완료로 바꾸지 않는다. Org/ECM 간 분산 직렬화 보장이 아니다.
- 다음 행동 / 담당 / 착수 조건: Codex / **B2 팩·BK-01 설치/재개·명시 이관 / 예상90~150분** / B1 지정 출구 충족. core/data_preparation/kit_registry.py·docs/data-kits·starter_kits1.0.0 원본을 확인하고 새 불변 팩/설치 계약을 연결한다. Starter 원문 변이 위험을 격리한 뒤 패키지 시험 실행. B4/B5로 건너뛰지 않는다.
- 교대 체크포인트: branch codex/l2-unified-studio-20260912, HEAD58e666833 · 기존B0+이번B1 코드/시험/문서 로컬 미커밋·미푸시 · 운영 DB/RAW/역할/승인/Starter1.0.0/앱/배포 변경 없음 · 사용자 실행로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 불변·제외 · 첫재개=B2 소스소유권·팩/이관검토 확인 · 금지=시험건수제품점수가산/임의운영이관·역할활성화/로그포함일괄커밋/무승인push.

### [L2-STUDIO-B0B-CLOSED-20260913] 인증 안전성 지정 출구 완료 / 다음 B1

- 작성자 / 기록 시각: Codex / 2026-09-13 01:01 KST
- 왜 지금 기록하는가: Supervisor의 순차 실행·단계별 전체 진척 보고 지시에 따라 B0-B 구현·검증을 마감하고 B1 착수 조건 해소를 인계한다.
- 상태: **B0-A/B 지정 출구 완료**, B1~B7 미착수. 전체21/40=52.5%, 로컬18/28≈64% 유지. 실제 회사 인증/배포/전체T3 완료가 아니다.
- 결정 및 근거: `docs/handoff/L2_STUDIO_B0B_CERTIFICATION_2026-09-13.md`. 승인 정책 정본·실제 종류별 역할/위임/PDP, 불변subject/revision/digest, 기존 서명 재검사, 완료 후 멱등, 단일 DP 원자성, 실제 owner/저장root 조회 경계, stale/hold 표시를 구현했다. 일반 관리자/직함을 서명권으로 쓰지 않는다.
- 검증: `output/usage-holds-3tnn8abh/tests.xml`·`isolation.json`, **382 passed / 135.97초**, SQLite473경로 임시루트, source불변·금지접근0·전역conftest 없음. 기존322+신규60. 직전158/1→365→378→380 결과와 수정은 인계 문서에 구분했다.
- 교차검토: 요청 Codex / Lorentz(`01a09618-0d9a-7241-a502-da93aa59e50a`) / 최초5건·후속4건·최종보류조회1건 수정 및 정적 재확인. 마지막 권한표·거부감사 보완에서도 새 P1/P2 없음. 검토자는 테스트/DB/파일 수정 없이 정적 검토, 최종 시험은 메인 담당자가 실행했다.
- 영향·주의사항: 권고5·6/G2-D 및 G4 입력신뢰성의 선행 안전성 관문 전진. DP 내부 원자성만 보장, Org/ECM/Ledger 분산 직렬화 아님. 실제 회사 역할 매핑 자동등록 없음. 기존 JSON은 안내/제안이며 실제 서명 정책은 승인된 회사 판본. 전체T3·starter자산 실행순서 문제는 별도 미종결로 유지한다.
- 다음 행동 / 담당 / 착수 조건: Codex / B1 L2v2 저장·권한·CAS·old-writer guard / B0 지정 출구 충족으로 착수 가능. B4/B5 UI로 건너뛰지 않는다. 후속 패키지/전역 시험은 자산 쓰기 격리를 먼저 확인한다.
- 교대 체크포인트: 브랜치 codex/l2-unified-studio-20260912, HEAD58e666833 · 코드/시험/문서 로컬 미커밋·미푸시 · 운영 DB/RAW/역할/승인/앱/배포 변경 없음 · 사용자 실행로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 불변·제외 · 재개=B1 · 금지=시험건수의제품점수가산/실제회사매핑임의활성화/기존로그포함일괄커밋/무승인push.

### [L2-STUDIO-B0-20260913] 순차 구현 — B0-A 완료, 인증 원자성 보완 / B0-B 전체 미완

- 작성자 / 기록 시각: Codex / 2026-09-13 00:12 KST
- 왜 지금 기록하는가: Supervisor의 설계 순차 구현·단계별 전체 진척 보고 지시에 따라 실제 코드·시험·독립 검토 결과와 남은 출구를 인계한다.
- 상태: **B0-A 완료 / B0-B 부분 / B1~B7 미착수**. 전체21/40=52.5%, 로컬18/28≈64% 유지.
- 결정 및 근거: docs/handoff/L2_STUDIO_B0_IMPLEMENTATION_2026-09-13.md. R0는 기존574c26fd8·새58e666833 정상 push/원격 일치로 완료. 구현 시작 HEAD58e666833, 현재 공유 브랜치 codex/l2-unified-studio-20260912.
- 실제 변경: store 읽기 snapshot/명시 conn, projection 소비 및 구조화 프로젝트 HTTP 오류, 기존7실패 복구. 서명은 fresh DP write transaction에서 상태/기간/용도와 함께 확정, 별도 인증 fallback 제거, 기간·서명 덮어쓰기 차단. generic 상태 전환 helper로 기존 보류·성격·인증자 관문 재사용.
- 검증: 최종322 passed/71.57초, output/usage-holds-1avm64wq/tests.xml·isolation.json. 임시 SQLite237경로, 금지 접근0·소스 불변·전역 conftest 없음. 중간 fixture 오류27+2건은 각각 경로 오탐/키트 미등록을 수정한 기록이며 SKIP하지 않았다.
- 교차검토: 요청 Codex / Boyle(B0-A) P2 1건→명시conn·rollback 시험 보완→한정 PASS. Lorentz(B0-B 최소 원자성) 새 결함 발견 없음, 전체 인증 조건 미충족은 별도. 실제 회사 승인·전체 보안 감사·독립 테스트 실행으로 기록하지 않는다.
- 영향·주의사항: 인증 서비스 시험은 소유/권한 대역을 사용하는 기존 단위 fixture이며 종류별 실제 서명권을 증명하지 않는다. HTTP는 실제 임시 조직/ECM 판정+합성 개발 신원이다. 회사 역할 매핑·불변 subject·정책/소유권 판본·기존 서명 재평가·완료 후 요청 멱등·전체 문맥/GET 일관성이 남는다. 운영 인증·배포 가능으로 승인하지 않는다.
- 다음 행동 / 담당 / 착수 조건: Codex가 B0-B 남은 can_sign/승인 매핑 정본·subject·멱등을 구현하고 U03/U20/U21 전체를 검증. 코드 구현을 위한 추가 사용자 선택은 없으며 실제 회사 역할표 등록/활성화만 별도 승인이다. B0 전부 닫기 전 B1/UI로 우회 금지.
- 교대 체크포인트: 로컬 코드·회귀·문서 변경 보존, 이번 커밋/푸시 없음 · 사용자 실행로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 불변·제외 · 실제DB/RAW/역할/승인/앱/배포 변경 없음 · 재개=B0-B 종류별권한/subject부터 · 금지=322시험을제품322기능/전체B0완료로계산, 과거관리지표로진척재산정.

### [L2-STUDIO-REVIEW-CLOSED-20260912] 상세 설계·독립 이중검토 종결 / 푸시 승인 대기

- 작성자 / 기록 시각: Codex / 2026-09-12 20:38 KST
- 왜 지금 기록하는가: Supervisor의 구현 전 상세 설계·계획·객관적 이중검토 조건을 문서와 검토자 재확인으로 종료하고 실제 구현과 구분한다.
- 상태: **설계 검토 PASS(한정) / 원격 전송 차단 / 제품 구현 미착수**.
- 결정 및 근거: docs/design_l2_unified_studio_execution_2026-09-12.md revision2.1, docs/reviews/L2_UNIFIED_STUDIO_DOUBLE_REVIEW_2026-09-12.md. 초기 A/B 각각 P1 5건·P2 1건,12조건 반영. B-2 heal 새REVISION/기존HOTL/로컬제한 잔여를 추가 보완했다. T01~T46과 U01~U30은 명세이며 신규 시험 통과가 아니다.
- 교차검토: 요청 Codex / A Pauli는 revision2 A-1~A-6 조건 해소 PASS, B Faraday는 revision2의5건+revision2.1 B-2 최종 해소 PASS. 자체검토와 독립 검토 구분, 실제 Claude/Gemini/현업 승인이 아님. 검토자 ID·근거·조치·판정은 검토 기록 참조. A 관련 본문은2.1에서 변경하지 않았다.
- 영향·주의사항: 기존 코드 공동 체크포인트41af3c06c와 문서574c26fd8은 로컬 보존 완료. 공유 checkout은 codex/l2-unified-studio-20260912. 새 브랜치 변경은 문서/진척/보드만. 실행 로그 제외·불변, 운영 DB/RAW/역할/승인/앱/배포 변경 없음. 회사 직무·위임·동일인 서명 예외는 운영 승인 대상이며 자동 결정하지 않는다.
- 다음 행동 / 담당 / 착수 조건: Codex가 최종 문서를 로컬 커밋. 목적지 승인 시 기존·새 브랜치를 정상 push하고 원격 일치 확인한 후 B0 착수. B0는 기존7실패, projection 생산자 read 일관성/HTTP 예외, 실적 서명 subject/종류별 적격성/동시성부터 닫는다. v2/화면 코드를 먼저 쌓지 않는다.
- 교대 체크포인트: 전체21/40=52.5%, 로컬18/28≈64% 유지 · 기존 검증234/28 통과+문맥1통과7실패 유지 · 현재 구현 미착수 · 외부 push는 자동 보안 검토가 목적지 확인을 요구해 미완료, 우회 재시도 없음 · 재개=목적지 승인/원격 확인 후 B0 · 금지=설계PASS를 운영 안전/실사용 완료로 확대, 데이터/승인 변경, 구 화면 조기 삭제.

### [L2-UNIFIED-STUDIO-20260912] 로컬 체크포인트·새 브랜치·상세 설계 이중검토

- 작성자 / 기록 시각: Codex / 2026-09-12 20:10 KST
- 왜 지금 기록하는가: Supervisor가 현재 커밋·푸시 후 새 브랜치에서 상세 설계·계획과 객관적 이중검토를 선행하도록 지시했다.
- 상태: **로컬 커밋·분기 완료 / 푸시 목적지 확인 대기 / 설계·검토 중 / 구현 미착수**.
- 결정 및 근거: `41af3c06c`는 Codex 보류 검사와 Claude M0의 공통 의존 코드·시험 공동 보존 커밋. 단독 기여로 귀속하지 않고 헌크 수술 없이 API/저장/시험을 보존했다. `574c26fd8`는 기존 설계·인계 기록. `docs/handoff/L2_STUDIO_BRANCH_CHECKPOINT_2026-09-12.md` 참조. 정상 제품 기준선·dev 통합·배포 승인이 아니다.
- 검증: output/usage-holds-7gwrk_3i에서234 passed, SQLite168경로 임시 격리·소스 불변·금지 접근0. 별도 임시환경 실적 인증28 passed, 프로젝트 문맥1 passed/7 failed. T3/브라우저/실사용 미실행.
- 교차검토: 요청 Codex / 검토 A Pauli(`01a0954c-072d-7d80-aa2d-aa499046859e`) 데이터·아키텍처, B Faraday(`01a0954c-07d7-7be2-bea3-e16d7a9ada50`) 현업 UX·전환 / 대상 docs/design_l2_unified_studio_execution_2026-09-12.md revision1 / 판정 대기. Claude/Gemini 또는 실제 현업 승인으로 표시하지 않는다.
- 영향·주의사항: 공유 checkout은 `codex/l2-unified-studio-20260912`다. Claude M0 공통 변경은 위 체크포인트에 이미 포함되어 중복 커밋 불필요. 이전 커밋 대기 기록은 당시 이력으로 보존한다. data/interaction_log.jsonl 제외·보존. 운영 DB·RAW·승인·권한·기존 앱 변경 없음.
- 다음 행동 / 담당 / 착수 조건: Codex가 두 검토 반영·재확인. 푸시는 사용자 목적지 확인 전 재시도하지 않는다. 원격 확인+중요 지적 해결 전 구현 금지; 이후 B0 회귀7건 및 실적 인증 경쟁부터 검증·해소.
- 교대 체크포인트: 분기점574c26fd8 · 현재 새 변경은 상세 문서·보드/진척뿐 · 코드 커밋1+문서 커밋1 로컬/푸시 차단 · U01~U18 문서 검산은 제품 검증 아님 · 재개=검토 결과 통합 · 금지=실패 기준선 승격/전체 진척 가산/운영 쓰기/구 화면 조기 삭제.

### [USAGE-HOLD-FAKESTORE-20260912] ⚠️ Codex 앞 — 보류 연결이 `test_project_data_context` 7건을 깬다. 선택지 셋을 **실측해서** 넘긴다

- 작성자 / 기록 시각: Claude Code / 2026-09-12 20:05 KST
- 왜 지금 기록하는가: [DATA-USAGE-HOLD-20260912] 의 소비 경계 연결이 가짜 저장소를 쓰는 시험 7건을 깬다. Codex 의 보류 스위트(420건)에는 이 파일이 안 들어 있어 **아직 모를 수 있다.** 공유 트리 커밋의 선행 조건이므로 알린다.
- 상태: **알림 · 고치지 않음(설계 판단이 Codex 레인)** · 상세 `docs/handoff/CLAUDE_TO_CODEX_USAGE_HOLD_FAKESTORE_2026-09-12.md`
- 결정 및 근거:
  - 증상: `tests/test_project_data_context.py` **7 failed / 1 passed**. 일곱이 각각 달라 보이나 **뿌리는 하나** — `calc_dataset_loader.py:137` → `usage_policy.py:73` 의 `store.transaction()` → `AttributeError: 'FakeStore' object has no attribute 'transaction'`.
  - 파급 범위 **실측**: 계산·준비도·데이터 계열 12개 파일 **413 passed / 7 failed** — 실패는 전부 이 한 파일이다. 다른 소비자(`calc_execution_approval`·`demo_readiness`·`path_calculation_service`·`project_data_context`·`calculation_control`)는 진짜 저장소라 멀쩡하다. **좁고 깊다.**
  - ⚠️ **T3 가 못 본 실패다** — 직전 T3 는 `e3a41768a` 동결본에서 돌았고 이 변경은 미커밋이라 거기 없었다.
  - ★ 원인은 편의 문제가 아니라 **「출처가 둘」** 이다. `store._snapshot_public()` 이 **모든 행에 `usage_holds` 를 투영**하고 `get_snapshot`·`list_snapshots` **둘 다** 그 투영을 지난다. 그런데 두 호출 지점이 **손에 든 값을 버리고** 트랜잭션을 다시 연다 — `transaction()` 을 요구하는 건 오직 그 재조회다. 게다가 그 재조회는 잠금이 없어 **「더 신선」이 아니라 「다른 시점」**이고, 방금 검사한 `state`·`checksum` 과 다른 순간의 보류가 된다.
  - 선택지: **A** 가짜에 `transaction()` 구축(그 가짜는 SQL 이 한 줄도 없는 순수 dict — sqlite 연결 + `source_bindings` 표 + 문맥 5칸이 필요하고, 그 순간 가짜가 진짜 스키마에 결속돼 가짜인 이유가 사라진다) / **B** `require_no_holds(row.get("usage_holds"))` — 저장소 접근 0회, 한 단어 차이 **【권함】** / **C** `require_usable` 이 봐주기 — **불가**(관문이 자기가 막을 대상 앞에서 비켜선다).
  - **B 를 실제로 돌려 봤다**(두 파일 임시 수정 후 **해시 일치로 원복**, 작업 트리에 잔여 변경 없음): ① 로더만 B 로 바꾸고 가짜는 그대로 → **7 failed 그대로**. ★ `require_no_holds(None)` 이 `USAGE_POLICY_UNREADABLE` 로 **fail-closed** 라서다 — 「가짜니까 봐준다」가 아니라 **보류를 투영하지 않는 저장소는 거부된다.** ② 가짜 스냅샷 dict 둘에 `"usage_holds": []` 한 칸씩 → **8 passed**. ③ ★ 통제가 여전히 무는가: `test_data_usage_holds.py` **46 passed**, 계산 계열 6파일 **262 passed**. **한 건도 안 깨졌다.**
- 영향·주의사항: B 를 골라도 `active_seals` 의 「보류된 최신판을 빼고 옛 판으로 조용히 폴백하지 않는다」는 그대로 성립한다(`latest` 확정 «뒤» 검사). `load_sealed` 의 검사 순서도 안 바뀐다. ⚠️ 앞으로 저장소가 투영하지 않은 행을 넘기는 호출자가 생기면 fail-closed 로 막히는데 메시지가 `USAGE_POLICY_UNREADABLE` 이라 원인이 바로 안 보인다 — 그 자리에서 「저장소가 투영한 행이 아닙니다」로 바꿔 주면 좋겠다.
- 다음 행동 / 담당 / 착수 조건: **Codex** 가 A/B/C 중 결정하고 수정 후 커밋한다. 그 커밋이 확인되면 **Claude Code 가 즉시 M0 묶음을 스테이징해 올린다**([ACTUAL-CERT-M0-20260912] 참조).
- 교대 체크포인트: 마지막 확인 상태 = 7건 실패 재현·파급 413/7 실측·B 3단계 실측 완료 · 변경 범위 = **없음**(임시 수정 2파일은 해시 확인 원복, 신규 문서 1건만 추가) · 미변경 = `core/calc_dataset_loader.py`, `tests/test_project_data_context.py`, Codex 미커밋 전부 · 검증 증거 = 413/7 · 7→8 · 46 · 262 · 커밋/푸시 = 없음 · 재개 지점 = Codex 결정 확인 · 금지 범위 = Codex 미커밋 파일 편집, 가짜 저장소 임의 개조, `require_usable` 완화

### [ACTUAL-CERT-M0-20260912] 회사 실적 인증 종점(M0) 구현 완료 · 보류/원자성 연결 · T3 정산 · ⚠️ 커밋 보류

- 작성자 / 기록 시각: Claude Code / 2026-09-12 19:38 KST
- 왜 지금 기록하는가: M0 구현과 T3 전체 회귀가 끝났고, Codex 가 [DATA-USAGE-HOLD-20260912] 에서 나에게 넘긴 「`sign_actual_certification` 서명 전 보류 검사·서명/인증 원자성」을 연결했다. 동시에 **공유 트리 충돌로 M0 커밋을 보류**한 사실과, Codex 레인에서 발견한 회귀 7건을 알린다.
- 상태: **구현·검증 완료 · 커밋 보류(Supervisor 지시로 「A: Codex 커밋 대기」 선택)**
- 결정 및 근거:
  - **세 번째 인증 종점 `OWNER_CERTIFIED`**: 시연(`DEMO_CERTIFIED`, 책임 없음) · 공표(`SOURCE_CERTIFIED`, 책임=발행기관) · **회사 실적(`OWNER_CERTIFIED`, 책임=우리)**. `m.is_certified()`·`CERTIFIED_STATES`·`CERTIFICATION_DATA_KIND` 로 한곳에 모았다. `OWNER_CERTIFIED` 의 유일한 다음 상태는 `REVOKED` — 정정은 **새 판**이다.
  - **검토는 «단계» 가 아니라 «종류»**(`publication.REVIEW_TYPES` 와 같은 모양). ⚠️ **순차 결재로 만들지 않았다** — 부서장이 휴가면 전체가 멈추고, 결재선이 조직 개편마다 코드 변경이 된다. 필요한 종류만 정하고 순서는 사람에게 맡긴다.
  - **용도 선언이 쓰임을 제약한다**: `OPERATIONAL`=소유부서장 1명, `MANAGEMENT`=+경영관리팀장. `OPERATIONAL` 로 인증한 실적은 **경영 보고에 못 쓴다**(`PURPOSE_MIN_GRADE` 와 같은 구조). 거짓 선언의 대가가 본인에게 돌아오므로 선언 자체를 막지 않는다.
  - 초기값은 `core/actual_certification_policy.py` 정책 저장소: 경영관리팀장 + SAP ERP 대사 기준(Supervisor 지시). 코드 기본값이 저장소 부재·손상에도 살아남고, 변경은 행위자·사유·직전값과 함께 이력에 남는다. **화면에서 바꿀 수 있다**(`GET|PUT /api/v1/admin/actual-certification-policy`).
  - **Codex 인계분 연결 완료**: ㉠ 보류 검사가 **첫 서명 전에** 지나간다 — 나중에 보면 부서장은 서명하고 퇴근하고 막판에 임원이 벽을 만난다(차단이 틀린 사람에게 틀린 시점에 도착). ㉡ **마지막 서명과 상태 전환이 한 트랜잭션**이다 — `advance_snapshot(on_commit=...)` 를 써서 **`store.py` 를 고치지 않고** 달성했다(공유 파일 churn 최소화). 두 검사 모두 각자의 `BEGIN IMMEDIATE` **잠금 안**에 있다 — 밖에서 한 번 보고 들어가면 그 사이에 다른 연결이 보류를 커밋한다.
  - 검증 증거: `tests/test_actual_certification.py` **28건 통과**, 합동 회귀(+`test_data_usage_holds`+`test_dataset_snapshot`) **133건 통과**. ★ **극성 증명**: 변이 ①(원자성 제거=서명 먼저 커밋) → `test_a_hold_blocks_the_last_signature_without_half_committing` 만 실패. 변이 ②(서명 전 보류 관문 제거) → `test_a_hold_blocks_the_first_signature_and_leaves_no_trace` 만 실패. **변이 하나가 시험 하나씩을 죽였다** — 통과가 공허하지 않음을 증명.
  - T3 전체 회귀(동결 워크트리, `e3a41768a`): **7,120 passed / 5 skipped / 6 failed / 2,143초**(직전 6,735·3·978초, +385건). 정산은 `docs/test_plan/T3_2026-09-12.md`. 실패 6건은 main 트리 대조군으로 갈랐다 — `test_calculation_api` 5건은 **내 결함**(커밋 `b7e3982de` 로 수정, 80건 통과), `test_starter_package_catalog` 1건은 동결본 artifact.
- 영향·주의사항:
  - ⚠️⚠️ **[Codex 레인 회귀 7건 — 알림]** `tests/test_project_data_context.py` 가 **7건 실패**한다. 원인: `core/calc_dataset_loader.py:137` 의 `usage_policy.require_usable(store, row)` 가 `store.transaction()` 을 요구하는데 그 시험의 `FakeStore` 에 그 메서드가 없다 → `AttributeError`. **내 변경과 무관함이 추적선으로 확인**됐다(그 경로는 `sign_actual_certification` 을 지나지 않는다). 고칠 자리가 둘(가짜 저장소에 `transaction` 추가 / `active_seals` 의 호출 형태 변경)이고 **어느 쪽이 설계 의도인지는 Codex 의 판단**이라 손대지 않았다.
  - ⚠️ **[업무키트 레인 발견]** T3 중 **추적 대상 저장소 파일이 시험에 의해 수정**됐다. 워크트리 생성 17:03:51 → 자산+manifest 동시 수정 17:04:01(T3 도중), 내용 차이 1,117 vs 1,112바이트(CRLF 수 동일 — 줄바꿈 문제 아님). 즉 **manifest 검사가 실행 순서에 따라 결과가 달라진다**(단독 통과·전체 실패). 키트 레인이 봐야 한다.
  - ⚠️ T3 소요가 978→2,143초로 **2.2배**인데 시험 증가(+5.7%)로 설명되지 않는다. **원인 미규명** — 다음 T3 에 `--durations=20` 을 붙일 것.
  - 공유 파일 3종(`models.py`·`store.py`·`snapshot_service.py`)에 **내 M0 추가분과 Codex 의 보류 호출이 함께** 얹혀 있다. 각자 자기 몫만 스테이징하고 **디렉터리째 `git add` 하지 않는다**.
- 다음 행동 / 담당 / 착수 조건:
  - **Codex(화면)**: ① 의사결정 생성 화면에 **근거 종류 필수 선택기**(서버가 파생하는 계산 경로는 제외) ② 준비도 화면에 `READY` 옆 `data_kind` 표기 ③ 원천 카드에 소유 부서·승인자 ④ 판 카드에 인증자 ⑤ **실적 인증 패널** — 「누가 눌렀고 누가 안 눌렀나」를 그린다(`missing`·`next_action` 이 그대로 온다). ⚠️ **순차 결재선으로 그리지 말 것** — 병렬이다. ⑥ 정책 패널은 `sources`(저장소/코드 기본값)를 함께 표시.
  - **Codex**: 위 회귀 7건 처리 방향 결정 후 커밋. 그 커밋이 끝나면 **내가 즉시 M0 묶음을 올린다.**
  - **Claude Code(나)**: M0 커밋 대기 중. 이후 M1 은 Codex 화면, M2(ERP 대사 자동화)·M3(회계 마감 연동)은 제안서 §10 순서.
- 교대 체크포인트: 마지막 확인 상태 = M0 구현·시험·극성 증명 완료, **미커밋** · 변경 범위 = `core/data_preparation/{models,store,snapshot_service}.py`(내 몫만), `api/routes/data_preparation_control.py`, `core/actual_certification_policy.py`, `tests/test_actual_certification.py`(28건), 제안서·검증계획 문서 · 미변경 = `PROGRESS.md`, `core/{calc_dataset_loader,kit_app_builder}.py`, `core/data_preparation/{readiness,scope_index,usage_policy}.py`, `tests/test_{dataset_snapshot,kit_app_builder,data_usage_holds}.py`(전부 Codex 작업분) · 검증 증거 = 28 + 합동 133 + 변이 2건 극성 · 커밋/푸시 = `335a8759f` 까지 푸시 완료, **M0 묶음은 보류**(부분 커밋 시 라우트가 미커밋 함수를 불러 새 clone 이 깨진다) · 재개 지점 = Codex 커밋 확인 → M0 스테이징 → 커밋·푸시 · 금지 범위 = Codex 미커밋 파일 편집, 디렉터리째 `git add`, 헌크 분리 수술, 운영 DB 시험 잔여물 삭제

### [KIT-L2-DESIGN-20260912] 업무키트 L2 표준 골격·회사별 변경 상세 설계

- 작성자 / 기록 시각: Codex / 2026-09-12 18:36 KST
- 왜 지금 기록하는가: 사용자가 L2 표준 프로세스 셋업과 회사별 변경 가능 방향에 동의하고 상세 설계를 명시적으로 요청했다.
- 상태: 상세 설계 작성·문서 검산·독립 최종 검토 보완 확인 완료. G2-A/B/C·G3-B/C 설계 보강이며 D02 2/4, 전체 21/40=52.5%·로컬 18/28=64% 유지. 제품 구현/운영 검증 완료가 아니다.
- 결정 및 근거: docs/design_business_kit_l2_process_setup_2026-09-12.md §19. 기존 ECM process_profile 정본 확장, 8 L1/29 L2 후보, 정본 업무+바로가기, 회사 override/3-way 업데이트, 앱 다대다, 설치 복구·문맥 격리·CAS. PowerShell 정적 검산으로 29 고유 키/8키트/46 시험명세/25 데이터 참조 유효와 JSON 예시 확인. 신규 문서 포함 공백 검사 통과.
- 교차검토: 요청 Codex / 검토 Nietzsche(별도 에이전트, Claude 검토 아님). 지정 4영역 읽기 전용 P1 6개·P2 2개 위험 반영 후, 문서 최종 검토 6건을 추가 보완했다. APPLIED/head 원자성·제안/설치 권한·지도/데이터 준비 분리·번들 참조 활성화·v1 전환 경쟁·반복 업데이트 B 기준을 §6.3/7/9/12/14, T41~46에 반영. 최종 제한적 재확인에서 6건 조건 충족·재개방 없음, 문서 수준 종결.
- 영향·주의사항: 신규 설계서와 PROGRESS·본 보드만 수정. 기존 starter 1.0.0·코드·DB·RAW·원장·권한·실적 인증 병행 변경은 미수정. 새 API·테이블·팩 판번은 제안이며 현행 구현으로 인용하지 않는다.
- 다음 행동 / 담당 / 착수 조건: 구현 담당은 사용자 후속 구현 지시 시 P1 v2 저장/문맥 경계/구형 쓰기 차단부터 진행. 도메인 책임자가 구매계획·선정평가·입고확정 계약 공백과 역할을 검수. 전역 통합 전 기존 병렬개발 통합 계획·소유권 확인 필수.
- 교대 체크포인트: 기준 HEAD e3a41768a와 기존 미커밋 작업 보존. 이번 커밋·푸시·앱 실행·실제 테스트/운영 쓰기 없음. 문서 T01~T46은 수용 명세이지 통과 증거가 아니다. G2-D 서명 전 보류·인증 원자성 및 실사용 검증 잔여를 완료 처리하지 않는다.

### [DATA-USAGE-HOLD-20260912] 가격·과거 조직 시점 사용 보류 소비 경계 연결

- 작성자 / 기록 시각: Codex / 2026-09-12 17:26 KST
- 왜 지금 기록하는가: 사용자 계속 진행 지시에 따라 직전 남은 보류 메모의 실제 인증·소비 차단을 구현·검증했고, 병행 실적 인증 작업과의 접점을 명시한다.
- 상태: 보류 차단 하위 묶음 완료. G2-D 권고 5·6 전진, D04 2/4 및 전체 21/40=52.5%·로컬 18/28=64% 유지. 실사용·승격 승인은 미완.
- 결정 및 근거: 인증/교체·준비도·객체/근거·앱/계산 공통 보류 판정. 신규 46 포함 234 + 기존 준비 186 = 420건 통과. output/usage-holds-wg2g4k6f(소스 전후 동일/168 임시 SQLite 경로)·foundation-tests-bip19ymf. RO 검산 usage-holds-artifact-jmuyxcv8에서 기존 61판 불변·25판 차단 확인.
- 교차검토: 요청 Codex / 검토 Galileo(별도 에이전트) / 제한적 코드검토 수용. 정책 확인 직후 별도 연결 쓰기 P2를 재현해 인증·교체·색인 BEGIN IMMEDIATE로 보완, 3경로 회귀 통과. 타팀 실적서명 함수/운영 승인 제외.
- 영향·주의사항: models.py 및 store/snapshot_service의 실적 인증 추가·실적 API/테스트/제안서는 병행 작업자 소유로 보존. Codex는 보류 검사·잠금과 기존 고정 상태표 테스트만 보완했다. 공통 파일 전체 diff를 단독 커밋에 섞지 않는다. 운영 DB/RAW/권한/회사 설정/원장/실발송 변경 없음.
- 다음 행동 / 담당 / 착수 조건: Codex·실적 인증 담당자가 병행 변경 확정 후 sign_actual_certification의 서명 전 보류 검사·서명/인증 원자성을 연결한다. 소유권/시점 근거 승인과 실제 앱·계산 수용 검증이 있어야 D04 연결 완료를 재평가한다.
- 교대 체크포인트: 기준 e3a41768a(직전 푸시 확인)+미커밋. 이번 staging/commit/push/병합/배포 없음. 상세 docs/handoff/DATA_USAGE_HOLD_ENFORCEMENT_2026-09-12.md. 최신 테스트234·준비186·RO검산25판을 재개 근거로 사용하며 5종 재적재·자동 보류 해제·인증자 소급·데이터 삭제 금지.

### [COMMIT-CLEANUP-20260911] 검증된 구현·진척 기록 커밋 및 로컬 산출물 보존

- 작성자 / 기록 시각: Codex / 2026-09-11 17:22 KST
- 왜 지금 기록하는가: 사용자가 커밋·푸시·정리를 명시적으로 요청해 구현과 인계 기록을 재현 가능한 기준점으로 묶는다.
- 상태: 구현 2커밋 완료, 문서·제외 규칙 정리 후 현재 브랜치 푸시 예정. 전체 21/40=52.5%, 로컬 18/28=64% 유지; 정리를 기능 완료로 가산하지 않는다.
- 결정 및 근거: 데이터 준비·선행 정렬 25파일 `242df882d`, 결정 생성 계약 11파일 `c4f9421fc`. 직전 격리 검증 output/foundation-tests-mwqk26nt 186 passed + output/decision-create-lk3l64ub 115 passed, tsc -b frontend 통과. 결정 브라우저 검증은 기존 8요청 캡처 재대입이며 이번에 브라우저를 다시 실행한 것은 아니다. 커밋 대상 자격증명 패턴 검사 및 스테이징 공백 검사 통과.
- 영향·주의사항: 원격은 origin의 claude/data-acquisition-orchestrator-20260905만 대상으로 하며 병합·강제 푸시·배포는 하지 않는다. /raw/를 Git 제외 규칙에 추가하고 RAW·DB·output·data/interaction_log.jsonl은 원문 그대로 로컬 보존; 대화 로그 변경은 커밋에서 제외한다. 파일 삭제·원장 초기화 없음.
- 다음 행동 / 담당 / 착수 조건: Codex가 문서 커밋 후 사용자 승인 범위의 비강제 푸시와 원격 HEAD 일치를 확인한다. 후속 구현은 현재 PROGRESS 및 FOUNDATION_ALIGNMENT 체크포인트의 실제 소비 경계 보류 강제부터 진행한다.
- 교대 체크포인트: 새 스테이징은 명시한 문서·제외 규칙 11파일만 허용. 검증은 집중 회귀 301건·타입 검사이며 전체 회귀/실사용/외부 발송 검증을 뜻하지 않는다. 이 기록 작성 시 푸시는 아직 실행 전이며 최종 성공 여부는 실행 결과와 원격 HEAD로 확인한다. 미커밋 런타임 로그를 되돌리거나 함께 푸시하지 않는다. 운영 DB 수정·인증자 소급·자동 인증·임의 매핑 금지.

### [FOUNDATION-ALIGNMENT-20260911] 선행 5종 정렬·새 RAW 6판 완료

- 작성자 / 기록 시각: Codex / 2026-09-11 17:07 KST
- 왜 지금 기록하는가: 사용자가 계속 진행을 요청했고 직전 다음 작업인 FND-01/03·MDM-04/08·EXT-02를 구현·저장·검증했으므로 후속 담당자의 재조사를 막기 위해 남긴다.
- 상태: 5종 정렬 묶음 완료 확정. G2-D 권고 5·6 전진. D04 연결 단계는 보류 강제·소유권/인증이 남아 2/4 유지; 전체 21/40=52.5%, 로컬 18/28=64%.
- 결정 및 근거: 신규 1,397행·6 DRAFT/RAW, 기존 55판 보존, 새 인스턴스 0. 13종·15,557행 참조 대사. 186 passed(신규32+기존154), 독립 RO 검산 통과. docs/handoff/FOUNDATION_ALIGNMENT_CHECKPOINT_2026-09-11.md 및 JSON; 최종 foundation-raw-0yag5clt, 지문 3c0159d18b63b2b2a4abe2aa25445ba5a48d693cba913690834f3f9c57838800.
- 영향·주의사항: FND-01 원천15행 보존/목표 현재구조6행은 별도 투영, 과거 유효기간 빈 값. MDM-04 7행만 연결하고 LOC-P3-SIM 1행 원문 보류. 달력/환산/가격/관측시점 업무값 불변. 합성/미검증 상태·기존 RAW·권한·운영 DB를 바꾸지 않았다.
- 다음 행동 / 담당 / 착수 조건: Codex는 readiness.py·scope_index.py·snapshot_service.py에서 가격·조직 시점 보류의 실제 소비 경계 연결을 진행한다. 소유권/인증 승인이나 과거 조직 유효성 추정으로 우회하지 않는다. 권한·계약 연결 수정 시 동료 교차검토를 후속 요청한다(이번 독립 검산은 별도 프로그램이지 동료 승인 아님).
- 교대 체크포인트: core/data_preparation/kit_foundation_alignment.py + 실행/검산/회귀도구 3개·테스트·진척 인계 추가. output/foundation-tests-9zzw6490에 186건, foundation-raw-0yag5clt에 최종 결과/RO검산. 부모 및 첫 성공 사본 보존. head 3ddf4be4a+미커밋, 스테이징/커밋/푸시/배포 없음. 재개 시 선행5종을 재준비하지 말고 남은 사용 보류 경계부터 확인. 운영 DB 초기화·원장 수정·인증자 소급·자동 인증·창고 임의매핑 금지.

### [DECISION-CREATE-CONTRACT-20260911] 결정 생성 계약 복구·전체 52.5%
- 작성자 / 기록 시각: Codex / 2026-09-11 16:44 KST
- 왜 지금 기록하는가: 사용자가 계속 구현과 전체 진척 상시 보고를 요청했고, 직전 재산정에서 D07 연결 단계를 재개방한 원인을 실제 수정·검증했기 때문.
- 상태: 해당 연결 복구 확정. D07 2/4→3/4, 전체 20/40→21/40=52.5%, 로컬 17/28→18/28=64%. 실사용 단계와 전체 게이트 승인은 미완료.
- 결정 및 근거: 근거 종류 선택/전송 및 서버 정본 결속 구현. 실제 브라우저 2뷰포트·8회 캡처 요청을 실제 API에 재대입; 최종 115 passed, tsc·제품 빌드 통과. 상세 docs/handoff/DECISION_CREATION_CONTRACT_REPAIR_2026-09-11.md 및 같은 이름 JSON.
- 영향·주의사항: 로드맵 13/G5 기존 연결 보수. evidence의 simulation_binding/baseline_id/scenario_id/engine_version 사용자 덮어쓰기는 422. 버전/입력 지문 없는 실행은 선택·생성 차단. 타 팀 실적 인증 정책, 전역 라우트, 운영 DB/RAW는 미변경.
- 다음 행동 / 담당 / 착수 조건: Codex는 초기 준비 5종(FND-01/03·MDM-04/08·EXT-02) 정렬로 이어간다. 기존 판·원문 보존 확인 후 진행. 실제 사용자 E2E와 외부 게시 연결은 별도 승인된 범위에서 수행.
- 교대 체크포인트: 제품 4파일 + 격리 검증 도구/fixture/검사와 진척 기록 변경. output/decision-create-g1kphf05(115건)·decision-ui-r5soclz6(8요청) 증거 보존. SQLite 151개 경로 모두 신규 격리 폴더, 전역 conftest 없음. head 3ddf4be4a+미커밋, 커밋/푸시/병합/배포 없음, 시험 서버 종료. 재개 시 PROGRESS 최신 52.5%를 사용하고 16:16 원표는 역사로 보존. 운영 데이터 초기화·실적 인증자 소급 채움·실발송 금지.

### [PROGRESS-REAUDIT-20260911] 전체 진척 10영역 재산정 — 50%, 로컬 61%
- 작성자 / 기록 시각: Codex / 2026-09-11 16:16 KST 기준
- 왜 지금 기록하는가: 사용자 지시로 과거 45% 반복 보고를 중단하고 최신 구현·실행 근거를 전체 10영역에 다시 대조했다.
- 상태: **재산정 완료** — 제품 전체 완료가 아니다. 20/40=50%, 앞 7영역 17/28=61%. 완료 20 / 진행·부분 8 / 검증 미완료 6 / 미착수·대기 6.
- 결정 및 근거: `PROGRESS.md` 최신 표와 `docs/handoff/PRODUCT_PROGRESS_REASSESSMENT_2026-09-11.md/.json`; 기준 `3ddf4be4a` + 미커밋 RAW 증적. 초기 자료 +1·외부 자료 +1·시뮬레이션 +1·의사결정 연결 −1. 현행 `CaseCreate.evidence_basis` 필수와 `DecisionCenter/decisionApi` 누락을 확인하고 요청 모델만 분리 실행해 missing 오류/정상 대조군을 재현했다. Claude의 7fca26530 정책 계층, c17168309 인증 기록과 현행 소비 코드를 확인했다. 22/22는 조사 완료를 포함하며 제품 100%가 아니다.
- 영향·주의사항: 운영 DB/원장/승인/앱/제품 코드는 변경하지 않았다. 기존 RAW와 타 팀 실물 판 보존. 사용자 화면 전체 검증과 최신 HEAD T3는 미실행; 이전 T3의 3실패 및 공유 원장 감시 오류를 통과로 바꾸지 않았다. 과거 45%·로컬 54%·163/167(98%)는 이력이며 현재 수치로 반복하지 않는다.
- 다음 행동 / 담당 / 착수 조건: Codex는 결정 생성 필수 근거 종류 연결 보완과 선행자료 5종 정렬을 다음 구현 묶음에 반영. 기존 백엔드 담당의 OWNER_CERTIFIED 종점과 정책 UI 인계는 별개로 유지. 실제 승인 권한은 기존 조직 정본을 따른다.
- 교대 체크포인트: 재산정 10/10영역·39개 근거 지문·산식 검산. 변경은 진척/감사/보드 문서만, 커밋·푸시 없음. 첫 재개 시 최신 표와 변경 소스 지문 확인; 과거 백분율 복사·중복 집계·실사용 완료 추정 금지.

### [ACTUAL-CERT-POLICY-20260911] 실적 인증 정책 — 초기값 경영관리팀장·SAP, 화면에서 변경
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 사용자가 회사 실적 인증 종점에 대해 「제안하라」고 했고, 제안 뒤 「우선 경영관리팀장 승인으로 해 놓고 나중에 화면에서 바꿀 수 있게 · 대사 증거도 SAP 기준 추천안으로」 지시했다. 정책 저장소를 만들어 **Codex 가 화면을 붙일 수 있는 상태**로 넘긴다.
- 상태: **정책 계층 완료** — 인증 종점(`OWNER_CERTIFIED`) 구현은 M0 로 남는다
- 결정 및 근거:
  - ★★★ **내가 여태 쓴 전제가 틀렸다.** 「실제 Data Owner 가 없어 실적 인증을 못 연다」고 여러 번 적었는데, **Data Owner 계층은 이미 있다** — `dataset_ownership_bindings` 35건 ACTIVE, 원장 사건 기반, 철회 경로·유효기간 겹침 방지 트리거까지. 게다가 **인증 경로가 이미 그것을 본다**(`certify_demo` → `scope_index.plan` → `resolve`). ⚠️ 내가 「없다」고 한 걸 근거로 누가 **다시 만들면** 정본이 둘이 된다.
  - **2단 승인이 복잡해지지 않는 이유** — 검토를 「단계」가 아니라 **「종류」**로 둔다. `publication.py` 의 `REVIEW_TYPES`·`EXTERNAL_REQUIRED_REVIEWS` 가 이미 그 구조이고 하필 `DATA_OWNER`·`EXECUTIVE` 가 나란히 있다. 실적 용도별로 필요한 종류를 다르게 둔다 — 부서 운영용은 소유 부서장만, 전사 경영 보고용은 둘 다.
  - ⚠️ **순차가 아니라 병렬**이다. 순차면 부서장이 휴가 갈 때 전체가 멈추고, 결재선이 조직 개편마다 코드 변경이 된다.
  - **「마감보고서 번호」는 내가 이름을 잘못 붙인 것**이다. 말하려던 것은 `vintage` 와 같은 개념 — 「어느 판과 맞췄나」다. 「2026년 8월 실적」은 하나가 아니다(1차 마감 vs 조정 후). ⭕ ERP 월 결산 마감본을 말한 것이 맞다.
  - **정책 저장소 신설** — `core/actual_certification_policy.py` + `GET/PUT /api/v1/admin/actual-certification-policy`. `model_routing_policy`·`scope_policy` 와 같은 규약(코드 기본값 · 이력 · 되돌림 · 호출 시점 읽기). 시험 26건.
- 영향·주의사항:
  - ⚠️ **바꿀 수 «없는» 것 셋**: `DATA_OWNER` 서명 제거 불가(실적 인증의 바닥) · 서명 목록 비우기 불가 · 최소 길이 0 불가. 더 빡빡하게 가는 것은 막지 않는다.
  - ⚠️⚠️ **이 정책은 「누가 승인권자인가」를 정하지 않는다.** 자리 «이름»은 화면 표시용이고 실제 권한은 조직 정본이 정한다(`_require_approval_authority` 네 관문). 둘을 뭉개면 화면에서 아무 이름이나 넣고 그 사람이 승인권자가 된다.
  - ⚠️ **대사 증거 형식을 강제하지 않는다.** ERP 마다 다르고 정하는 순간 그 ERP 전용이 된다. 검사는 「빈 값 아닌가」·「너무 짧지 않은가」 둘뿐이고, 시험이 SAP·Oracle·자체 시스템 세 표기를 다 통과시켜 이것을 못박았다.
  - 운영 정책 파일(`data/actual_certification_policy.json`)은 **아직 없다** — 코드 기본값으로 돈다. 화면에서 처음 바꾸는 순간 생긴다.
- 다음 행동 / 담당 / 착수 조건:
  - **Codex(신규 인계)** — 관리자 화면에 실적 인증 정책 패널. ⚠️ ① 값만 그리지 말고 **`sources`(store/code)** 를 함께 그릴 것(`model-routing` 화면과 같은 규약) ② **결재선으로 그리지 말 것** — 순차로 그리면 부서장이 안 눌렀을 때 임원 자리가 «비활성» 으로 보이고 사람들은 순서를 기다리다 둘 다 안 누른다. **필요한 서명 목록 + 각각 눌렸는지**로 그린다 ③ 대사 증거 입력 상자에 `recommended_fields`·`example` 을 안내로 띄울 것.
  - **사용자** — 이제 결정할 것이 거의 없다. 초기값으로 돌려 보고 화면에서 조정하면 된다. 단 **「전사 경영 보고용 실적」의 기준**(계약 단위인가 조직 단위인가)은 M0 구현 전에 정해야 한다.
  - **나(Claude)** — M0(`OWNER_CERTIFIED` 상태·전이·`certify_owner`·귀속 기간) 착수 가능. 그리고 T3(한도 충전 후).
- 교대 체크포인트: 마지막 확인 = 정책 시험 26건 · 관련 회귀 169건 통과 · 익명 401 차단 실측 · 변경 = `core/actual_certification_policy.py`(신규) · `api/routes/admin_control.py`(라우트 2개) · 시험 1파일 · 제안서 §8·§9 · 미변경 = 인증 종점 자체(`OWNER_CERTIFIED` 는 아직 없다) · 검증 증거 = `PROPOSAL_ACTUAL_CERTIFICATION_2026-09-11.md` · 커밋 = `ecec08a37`·`aaee29199`·`7fca26530` · 푸시 = 완료 · 재개 지점 = M0 또는 T3 · 금지 범위 = Data Owner 계층 재구현, 정책에 「누가 승인권자인가」를 넣기, 대사 증거 형식 강제, 잠정 인증·자동 통과 도입.

### [CERTIFIED-20260911] 실물 판 인증 완료 — 인증자 `hikwon@lsmnm.com` · **검증 계획 마감**
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 사용자 승인 명령(「EXT-02 World Bank 실물 판을 공표 자료 기준으로 인증한다, 인증자는 hikwon@lsmnm.com」)을 수행해 **검증 계획 22/22 가 마감**됐다. 그 과정에서 「인증자 이름이 저장되지 않는」 결함을 찾아 먼저 고쳤다.
- 상태: **완료** — 계획 §9-P. F-8 흐름 7·침묵 0 · T 16/16 · E 9/9
- 결정 및 근거:
  - **⚠️ 먼저 찾은 결함** — `certified_at`(언제)은 있는데 **`certified_by`(누가) 열이 없었다.** `certify_source()` 가 인자로 받아 놓고 **결과에만 담고 버렸다.** 승인 명령을 주셨어도 이름이 아무 데도 안 남았을 것이다. 열 추가 + 마이그레이션 + `advance_snapshot` 이 인증 전이에서 이름을 «요구» 하게 고쳤다(인증이 아닌 전이에는 요구하지 않는다 — 요구하면 파이프라인이 멈춘다).
  - ⚠️⚠️ **관문이 한 경로만 지키고 있었다.** `certify_demo_replacement` 는 raw SQL 이라 `advance_snapshot()` 을 지나지 않는다 — 거기서도 이름을 남기게 했다.
  - **인증 절차** — 인증 뒤엔 앞으로 못 가고 정정은 새 판을 만드는 것이 설계라 그대로 따랐다. ① `ds_0a072eb65f8645` 철회(이력 보존) ② `ds_716f0fbc363a4b` 재적재 240행 — **checksum 이 이전과 동일**(자료는 안 변했다) ③ `SOURCE_CERTIFIED` · 인증자 `hikwon@lsmnm.com`.
  - ★ **실존 계정으로 한 근거**: 대상이 World Bank 가 실제로 공표한 자료이지 가상회사 자료가 아니다. 같은 자료의 원천 승인도 같은 이름이라 **한 사람이 원천과 판을 일관되게 책임지는** 모양이 된다. ⚠️ 시연 자료 인증은 지금도 `.invalid` 합성 계정이고 그 규칙은 그대로다.
- 영향·주의사항:
  - ⚠️⚠️ **`advance_snapshot()` 이 인증 전이에서 `certified_by` 를 «요구» 한다.** 상태를 손으로 밟는 스크립트·시험이 있으면 `DEMO_CERTIFIED`·`SOURCE_CERTIFIED` 단계에 이름을 넘겨야 한다. 안 넘기면 `DataPreparationError` 다.
  - ⚠️ EXT-02 판이 셋이 됐다 — 시연(`DEMO_CERTIFIED`) · 철회분(`REVOKED`, 이력) · **실물(`SOURCE_CERTIFIED`, 인증자 있음)**. 철회분을 «지우지 말 것» — 「무엇이 왜 다시 인증됐나」의 이력이다.
  - ⚠️ 기존 시연 판(`ds_f0ee93365f3747`)은 열이 생기기 전 것이라 `certified_by` 가 비어 있다. **백필하지 않았다** — 그때 누가 인증했는지 모르는데 이름을 넣으면 그것이 곧 창작이다.
  - 내 계측기가 또 틀렸다(누적 11번) — 실물 판 중 첫 번째를 집어 철회된 판을 보고 「REVOKED 로 인증되어」라고 썼다. 살아 있는 판만 보게 고쳤다.
- 다음 행동 / 담당 / 착수 조건:
  - **Codex** — 변동 없음. `[GAPS-CLOSED-20260911]` 의 세 가지가 그대로 유효하다(① 결정 화면에 «근거 종류» 필수 ② 준비도 화면에 `data_kind` 표시 ③ 원천 카드에 소유 부서·승인자). **여기에 하나 더**: 스냅샷 화면에 **인증자**를 표시할 것 — 이제 값이 있다.
  - **사용자(결정 1건)** — 회사 실적 인증 종점을 열 것인가. 공표 자료는 이제 인증되지만 자사 매출·원가·생산 실적은 여전히 종점이 없다.
  - **나(Claude)** — 검증 계획 마감. 다음: T3 준비(동결 worktree 에 `.env`·`data/` 자산 포함).
- 교대 체크포인트: 마지막 확인 = 회귀 **723건 통과** · 탐침 3종 재실행(F-8 흐름 7/침묵 0 · T 16/16 · E 9/9) · 변경 = `core/data_preparation/`(store·snapshot_service) · `core/external_intelligence/snapshot_export.py` · 시험 3파일 · 탐침 1 · 계획 문서 · 미변경 = Codex 의 K1 코드·UI·시연 스냅샷 본문 · 검증 증거 = 계획 §9-P · `F8_REAL_WALK.md` · 커밋 = `2dafd3185`·`c17168309` · 푸시 = 완료 · 재개 지점 = T3 준비 · 금지 범위 = 철회분 삭제, 시연 판의 `certified_by` 백필, 인증 전이에서 이름 생략, 시연 자료에 `SOURCE_CERTIFIED` 시도.

### [GAPS-CLOSED-20260911] 미달 3건 해소 · 실물 인증 종점 신설 — **검증 계획 22/22**
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 사용자가 「Q1~Q4가 목적인데 왜 API 키가 필요한가」와 「미뤄둔 것을 자네가 처리할 수 있을 것 같다」를 지적했고, **둘 다 내가 틀렸다.** 6건 중 5건을 처리해 미달이 0건이 됐다.
- 상태: **완료** — 계획 §9-L·9-M·9-N·9-O. 22항목 전부 충족
- 결정 및 근거:
  - **⚠️ API 키는 Q1~Q4 에 필요 없다.** Q1·Q3·Q4 는 외부 원천 0개이고, Q2 의 원자재는 키 없는 World Bank 로 이미 돈다. 게다가 Q2 조차 **관측값이 계산의 조건이 아니다** — 「바뀌면」이라는 가정에 대한 영향이라 `탄력도 × 가정 변화율 × 기준선` 이면 된다. 내가 「Provider 구현 검증」(별개 목표)과 뒤섞어 대기 목록에 올렸다. **목록에서 제외.**
  - **ⓐ 원천 소유 부서** — `set_source_owner()` + `POST /sources/{id}/owner` 신설. 진짜 문제는 배정이 아니라 **고칠 경로가 아예 없었다**는 것이다(`register_source` 기본값이 빈 문자열). 승인과 «나눠» 뒀다. `WB_PINK_SHEET → MNM_SHARED`.
  - **ⓑ 탄력도** — `remove_impact()` 신설(승인 판본이 있으면 거부). ★★★ **내 첫 계수가 부호를 뒤집었다** — 매출 0.90 > 원가 0.80 으로 둬서 「원자재가 오르면 이익이 오른다」가 나왔다. 제련 제조원가의 90% 가 LME 연동 원료비라 **원가 탄력도가 커야** 한다. 철회→거둠→정정(원가 0.90/매출 0.82)→재승인(v2). 그리고 **기준선의 업종이 달랐다** — MNM_BATTERY(마진 62%)에 제련 계수를 걸고 있었다. 동제련 기준선(마진 10%)을 신설하니 비관 −1.0% 로 **방향이 맞았다**.
  - **ⓒ T-4 근거 종류** — `evidence_basis` 닫힌 어휘(SIMULATION·MEASURED·EXTERNAL·JUDGMENT). ★★★ `UNSTATED` 를 목록에서 **뺐다** — 기존 행만 갖고 새 안건은 못 고른다. SIMULATION 은 증거를 **실제로 확인**한다.
  - **ⓔ 결과물↔호출 키** — **키는 처음부터 있었다.** 내가 분모를 `publications` 로 잘못 골랐다(계측기 9번째). 비용이 붙는 결과물은 생성된 앱 릴리스이고 `release.json` 이 `project_id` 를 든다. 릴리스 28건 전부 연결, 20건에 비용.
  - **ⓕ 실물 인증 종점** — `SOURCE_CERTIFIED` 신설. ⚠️⚠️ **회사 실적에는 «열지 않았다»** — 발행 기관이 따로 있는 공표 자료 전용이다. 27곳을 `is_certified()` 와 SQL 자리표로 모았다.
- 영향·주의사항:
  - ⚠️⚠️ **`decision_case.create()` 에 `evidence_basis` 가 «필수» 가 됐다.** 화면·스크립트가 이 값을 보내지 않으면 400 이다. 기본값을 두지 «않은» 것이 의도다 — 기본값이 있으면 화면이 생각 없이 보내고, 그 순간 「산식에 근거하지 않은 결정」과 「적기를 잊은 결정」이 다시 같아진다. **Codex: 결정 생성 화면에 근거 종류 선택을 넣어야 한다.**
  - ⚠️ 운영 DB 가 또 바뀌었다 — `plan_facts` 에 MNM_COPPER 3행, 시나리오 6건(`mat_*`·`cu_*`), 동인 계수 4건(v2 판본), 스냅샷 1판이 `SOURCE_CERTIFIED`. **사람 허가 아래 만든 시연 자료다. 지우지 말 것.**
  - ⚠️ **업종 적합성은 코드가 못 막는다.** 시스템은 동인 판본의 «조직 범위» 는 검사하지만 「제련 계수를 배터리소재 기준선에 걸었는가」는 알 수 없다. 그 책임은 사람에게 남는다 — 계수의 `rationale` 에 어느 업종에서 유도했는지 반드시 적을 것.
  - ⚠️ 「시연 인증인가」를 물어야 하는 곳(`demo_reset`·`certify_demo_replacement`)은 `DEMO_CERTIFIED` 를 **그대로 둔다.** `is_certified()` 로 뭉개면 시연 초기화가 실물을 건드린다.
  - ⚠️ 내 계측기가 이 세션에 두 번 더 틀렸다(누적 10번). 둘 다 **제품은 멀쩡했다.**
- 다음 행동 / 담당 / 착수 조건:
  - **Codex** — ① 결정 생성 화면에 «근거 종류» 선택 추가(필수) ② 준비도 화면에 `data_kind` 표시(실물/시연) ③ 원천 카드에 소유 부서·승인자 표시.
  - **사용자(결정 1건만 남음)** — **회사 실적 인증 종점**을 열 것인가. 지금은 공표 자료만 인증되고 자사 매출·원가·생산 실적은 종점이 없다. 실제 Data Owner 가 서명하는 일이라 코드가 열 수 없다.
  - **나(Claude)** — 계획 22/22 완료. 남은 것: 다음 T3 준비(동결 worktree 에 `.env`·`data/` 자산 포함), 나머지 4종 Provider 실측(키 나오면 · Q1~Q4 와 무관한 별개 목표).
- 교대 체크포인트: 마지막 확인 = 관련 회귀 **1,205건 통과** · 탐침 6종 재실행(T 16/16 · E 9/9 · F-8 흐름 7/침묵 0) · 변경 = `core/data_preparation/`(models·store·scope_index·readiness) · `core/baseline_build.py` · `core/calc_dataset_loader.py` · `core/decision_case.py` · `core/planning_drivers.py` · `core/external_intelligence/`(__init__·snapshot_export) · `api/routes/`(external_control·decision_control) · 시험 6파일 · 미변경 = Codex 의 K1 코드·UI·시연 스냅샷 · 커밋 = `637db6b2c`·`ac3ee5803`·`f1901c28f`·`4300b9e14`·`9008065c3` · 푸시 = 완료 · 재개 지점 = T3 준비 또는 사용자 결정 · 금지 범위 = 시연 자료에 `SOURCE_CERTIFIED` 시도, `is_certified()` 를 `demo_reset` 에 적용, MNM_COPPER 기준선·`cu_*` 시나리오 삭제, 제련 계수를 다른 업종 기준선에 재사용.

### [F3-F8-20260911] F-3 을 선택지 B 로 이었다 · F-8 실물 관통 — **검증 계획 전 단계 완료**
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 사용자 착수 허가(F-3 = B)로 마지막 끊긴 이음매를 이었고, F-8 까지 걸어 **계획 1~6단계가 모두 닫혔다.** 단계 완료마다 보드를 갱신하기로 한 약속의 두 번째 이행이다.
- 상태: **완료** — 계획 §9-J(F-3) · §9-K(F-8). 전체 22항목 중 완결 19 · 미달/미측정 3
- 결정 및 근거:
  - **F-3 = 선택지 B** (사용자 결정 2026-09-11 · Codex 권고와 일치). 신규 `core/external_intelligence/snapshot_export.py`.
    ★★★ **새 어휘를 하나도 만들지 않았다** — 그것이 B 의 요점이다. EXT-02 의 `FILE_SNAPSHOT` 결속은 **이미 있었고 ACTIVE 였다**(`sb_c586cfaf6bb442`), CSV 20열은 **정본 스냅샷 `ds_f0ee93365f3747` 의 `schema_json` 에서** 가져왔으며(내 말로 쓰지 않았다), 파이프라인은 기존 `snapshot_service` 를 그대로 부른다.
  - **실제 적재**: `ds_0a072eb65f8645` · `RECONCILED` · `REAL` · **240행** · checksum `76f97736101eb030…`. 시연 판(`DEMO_CERTIFIED`/`DEMO-SYNTHETIC`)과 **섞이지 않고 나란히** 있다.
  - ★ `certify_demo` 를 **부르지 않는다.** 실물은 거기서 거부되고, 예외를 삼키면 「실패했는데 성공처럼 보이는」 경로가 된다. `RECONCILED` 에서 의도적으로 멈추고 **사유를 결과에 싣는다**(`certification_note`).
  - **F-8 통과** — 이음매 8개 · 흐름 5 · 막힘·설명 3 · **막힘·침묵 0**. 판정 규칙이 다른 트랙과 반대다(계획 §4): PASS 는 「완주」가 아니라 **「막히는 지점과 이유가 명확히 드러남」**. 실물은 ① 수집 → ② 승격 → ③ 동인 → ④ 시나리오까지 돌고 ⑤ 스냅샷 `RECONCILED` 에서 멈춘다.
  - 시험 21건 추가 · 관련 회귀 **222건 통과** · 극성 증명 9건(자료를 비우면 전부 «막힘·침묵» 으로 뒤집힘).
- 영향·주의사항:
  - ⚠️⚠️ **Codex 필수 표시 사항** — 실물 판을 올려도 **준비도는 여전히 시연 판을 가리킨다.** 실물만 주면 `APPROVAL_PENDING`(「판을 검토하고 인증하십시오」)이지만, 둘 다 주면 **`READY` 이고 가리키는 판은 `DEMO/SYNTHETIC`** 이다. 이것은 설계대로다(`latest_certified()` 가 승인 전 판을 일부러 무시한다 — 「인증되지 않은 새 판이 인증된 옛 판을 가리면 승인 전 데이터가 공식 화면에 오른다」). **다만 응답은 `data_kind` 를 함께 준다. 화면이 그것을 안 그리면 사용자는 `READY` 한 단어만 보고 실물이 올라간 줄 안다.**
  - ⚠️ 운영 DB 가 또 바뀌었다 — `data/data_preparation.db` 에 실물 스냅샷 1판(240행), `data/raw/` 에 원문 CSV 1개. **시험 잔여물이 아니라 사람 허가를 거친 실자료다. 지우지 말 것.**
  - ⚠️ 탐침이 총 **6종**이 됐다(`probe_f0` · `f8` · `x3` · `x4` · `x_remaining` · `t_trust` · `e_economy`). 전부 `test_` 로 시작하지 않아 **T3 에 안 들어간다** — 건수 정산에 넣지 말 것.
  - **만들면서 결함 둘을 찾았다.** ① 실제 관측값 행에는 `indicator_code` 가 없고 `indicator_id` 뿐이라, 그대로 썼으면 `commodity_code` 가 **조용히 비어** 「품목을 모르는 원자재 가격」 판이 됐다 — 거부하도록 막았다. ② **내 시험 도우미**가 `observations or OBS` 라 「0건 거부」 시험이 조용히 통과하고 있었다 — `_UNSET` 표시로 고쳤다.
  - Codex 의 K1 업무키트 작업과 **파일이 겹치지 않는다.**
- 다음 행동 / 담당 / 착수 조건:
  - **사용자(결정 5건 대기)** — ⓐ 원천 소유 부서(후보 `MNM_SHARED`) ⓑ F-6 탄력도 3값 ⓒ T-4 「근거 종류」 정책 ⓓ 나머지 4종 API 키 ⓔ 결과물↔호출 연결 키(E-1 미측정 해소) · **[신규] ⓕ 실물 인증 종점**을 열 것인가 — 지금은 `DEMO_CERTIFIED` 가 유일해서 실물이 앱까지 못 간다. 실제 Data Owner 의 실적 인증이라 **제품·조직 결정**이다.
  - **Codex** — 위 «필수 표시 사항» + 직전 항목 `[EXT-VERIFY-20260911]` 의 인계가 그대로 유효하다. 이제 화면에 실물 스냅샷 1판이 보인다.
  - **나(Claude)** — 계획의 모든 단계가 닫혔다. 남은 것은 **미달 3건의 해소**이고 전부 사람 결정이 선행이다. 그 사이 할 수 있는 것: 다음 T3 준비(동결 worktree 에 `.env`·`data/` 자산 포함), 나머지 4종 Provider 실측(키 나오면).
- 교대 체크포인트: 마지막 확인 = 관련 회귀 222건 통과 · 탐침 6종 실행 · 변경 = `core/external_intelligence/snapshot_export.py`(신규), `tests/test_snapshot_export.py`(신규 21건), `tests/probe_f8_real_walk.py`(신규), `docs/test_plan/` 2건 · 미변경 = Codex 의 K1 코드·UI·기존 시연 스냅샷 · 검증 증거 = `F8_REAL_WALK.md` + 계획 §9-J/§9-K · 커밋 = `c5ac8aad7` · 푸시 = 완료 · 재개 지점 = 미달 3건(전부 사람 결정 선행) 또는 T3 준비 · 금지 범위 = 실물 스냅샷·원문 CSV 삭제, `certify_demo` 로 실물을 인증하려는 시도, 탐침을 `test_` 로 개명.

### [VERIFY-STAGE6-20260911] 검증 계획 6단계 완료 — X-1·X-2·X-5·X-6 통과, E 미측정 1건
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 계획 1~6단계가 끝나 **X·E 트랙이 전부 닫혔다.** 단계 완료마다 보드를 갱신하기로 한 직전 약속의 첫 이행이다(이전엔 인계 파일로 대신해 3일 밀렸다).
- 상태: **완료** — 계획 §9-I. 전체 22항목 중 완결 16 · 미달/미측정 3 · 부분 1 · 미착수 2
- 결정 및 근거:
  - **X-1 기능 나열** — 수용 기준이 「없다」가 아니라 **「판정돼 있다」**였다. 닫힌 판정표를 두고 표에 없는 도메인은 «미판정» 으로 떨어뜨리게 했더니 첫 실행에서 `/skills` 가 실제로 X-1 을 실패시켰다. 판정: **기반시설**(에이전트 스킬 제안의 사람 승인 관문 — 없으면 AI 제안이 승인 없이 반영된다). 최종 «표류» 0건.
  - **X-2 이른 범용화** — 원천 5종은 요청 지표로 자동 선택되고(사람이 목록을 안 고름), 추천 기관은 27곳 중 8곳으로 좁혀지며 제외 19곳이 사유와 함께 빠진다(정산 일치).
  - **X-5 성급한 외부 쓰기** — 8/8 막힘. 커넥터 기본 `access_mode='read'` · `DRAFT→ACTIVE` 불가 · `DRY_RUN→ACTIVE` 불가 · `auto_apply` 켜진 작업 0건 · Shadow 의 검토·범위·검토자·입력동일 4관문. **한 겹이 아니다.**
  - **X-6 비용보다 모델 이름** — 「pro」 사슬의 첫 모델이 `gemini-2.5-flash` 다(비싼 이름이 아니다). 실측 고성능 68% · 강등 114건 · 단계 10종에 모델 조합 9가지.
  - **E-1 비용** — 호출 2,323건 **$19.83** · 산정 2,274/미산정 49(2.1%) · 무료·캐시·유료·**모름**으로 갈라 세어 「모름」을 0으로 접지 않는다 · 프로젝트 29개로 분할 가능.
  - ⚠️ **미측정 1건** — E-1 의 「**승인된 결과물 1건당** 비용」. 호출은 `project_id`, 발간물은 `source_id`(결정 안건)로 묶이는데 **둘을 잇는 열이 어느 쪽에도 없다.** 비용 자체는 측정되고 못 나누는 것은 «결과물 축» 으로만이다.
  - **E-3** 은 「잴 수 있다」까지만 냈다. 회차 이름이 «같은 일을 두 번» 이라는 보장이 없어 싸진 것(CRM002 $6.73→CRM003 $3.24)을 **축적 효과라고 부르지 않았다.**
- 영향·주의사항:
  - ⚠️ 탐침 2종 추가(`tests/probe_x_remaining.py` · `probe_e_economy.py`). **`test_` 로 시작하지 않아 T3 에 안 들어간다** — 건수 정산에 넣지 말 것. 이제 탐침은 총 5종이다.
  - ⚠️ 자동 생성 보고서 2종(`X_REMAINING_FINDINGS.md` · `E_FINDINGS.md`)은 손으로 고치면 다음 실행에 덮인다.
  - ★ **`probe_x_remaining.py` 의 `VERDICTS` 표는 «살아 있는 관문» 이다.** 새 최상위 도메인(`/api/v1/` 밖)을 만들면 X-1 이 즉시 실패한다 — 만든 사람이 「기반시설인지 표류인지」를 그 표에 적어야 한다. 조용히 늘어나지 않게 하려는 것이다.
  - ⚠️ 내 계측기가 또 두 번 틀렸다(누적 7·8번째). ① 추천기 결과의 필드 이름을 `sources` 로 추측해 「0곳」이라 보고(실제 `items` 8건) ② 극성 확인 스크립트가 캐시의 `recs` 를 안 비워 「로그를 비웠다」면서 진짜 로그를 읽었다. **제품은 둘 다 멀쩡했다.**
  - 운영 DB·로그에 **한 줄도 쓰지 않았다**(전부 읽기 또는 격리 인스턴스).
- 다음 행동 / 담당 / 착수 조건:
  - **나(Claude)** — 남은 것은 F-1·F-2·F-5·F-8 이다. 이 중 **F-8(전 구간 관통 — 실물 데이터로)** 이 남은 항목의 상위 집합이라 F-8 을 먼저 잡는 편이 낫다. 다만 F-8 은 **F-3 착수 허가**가 없으면 중간이 끊긴다.
  - **사용자(결정 6건 대기)** — ⓐ 원천 소유 부서(후보 `MNM_SHARED`) ⓑ F-6 탄력도 3값 ⓒ **F-3 착수 허가(B 권고)** ⓓ T-4 「근거 종류」 정책 ⓔ 나머지 4종 API 키 ⓕ **[신규] 결과물↔호출 연결 키**(E-1 미측정 해소 — 스키마·계측 변경이라 허가 필요)
  - **Codex** — 변동 없음. 직전 항목 `[EXT-VERIFY-20260911]` 의 화면 인계 사항이 그대로 유효하다.
- 교대 체크포인트: 마지막 확인 = 탐침 5종 실행 · 극성 증명 20건(6단계분) · 변경 = `tests/probe_x_remaining.py`·`probe_e_economy.py` 신규, `docs/test_plan/` 3건 · 미변경 = 제품 코드 0줄(이 단계는 «재기만» 했다), Codex 의 K1 업무키트, 운영 DB · 검증 증거 = `X_REMAINING_FINDINGS.md`·`E_FINDINGS.md` + 계획 §9-I · 커밋 = `d1558c5f1` · 푸시 = 완료 · 재개 지점 = F-8(단 F-3 허가 선행) 또는 F-1·F-2·F-5 · 금지 범위 = 탐침을 `test_` 로 개명, 자동 생성 보고서 수기 편집, `VERDICTS` 표에 근거 없이 도메인 추가.

### [EXT-VERIFY-20260911] 외부 원천 실측 관통과 검증 계획 1~5단계 — ⚠️ 보드 기록이 3일 밀렸다
- 작성자 / 기록 시각: Claude Code / 2026-09-11 KST
- 왜 지금 기록하는가: 사용자가 **「Codex에서 최종으로 합쳐 정리할 수 있게 공유가 되고 있는지」**를 확인하라고 지시했고, 확인해 보니 **되어 있지 않았다.** 09-09~09-11 사흘치 작업이 `docs/handoff/`·`docs/test_plan/` 에만 있고 이 보드에는 한 줄도 없었다. 규약이 「별도 인수인계 파일을 만드는 것으로 대신하지 않는다」고 못박았는데 내가 그렇게 했다. 그 구멍을 메우는 기록이다.
- 상태: **부분 완료** — 아래 ①~④ 완료, ⑤ 사람 결정 5건 대기, ⑥ 화면 확인 미착수(Codex 레인)
- 결정 및 근거:
  - **① 원천 승인·계약 승인 (사람 결정 2건 수령)** — `WB_PINK_SHEET` 승인(`external_sources` 0→1행, `approved_by=hikwon@lsmnm.com`), `EXT-02` 계약 승인(사유 「국제 원자재 기준가 시나리오 동인 확보」). 제품 경로 그대로 적용(`assert_can_manage_standard` → `_actor(p)`). 커밋 `968ce2c94`.
    ★ `approved_by` 에는 **표시 이름이 아니라 계정 id** 를 넣었다. 라우트가 `_actor(p)=p.user_id` 를 넘기기 때문이다 — 한글 이름을 넣으면 화면·감사가 못 찾는 값이 하나 생긴다.
  - **② 실제 파일 1회 수집 → F-6 전 구간 관통** (사용자 다운로드 허가). `thedocs.worldbank.org` · 778,415바이트 · HTTP 200. 구리·아연 각 120행 적재→승격. `external_observations` 0→240행, `plan_drivers` 0→2건. 커밋 `8b9f54d22`. 상세: `docs/handoff/SESSION_2026-09-11_WORLDBANK_LIVE_RUN.md`.
  - **③ ⚠️ 결함 1건 발견·수정** — `match_commodities` 가 양방향 부분일치라 **실제 업무 용어 11개가 전부 오매칭**했다(「전기요금」→금, 「금리」→금, 「변동비」→구리, 「아연 가격」→아연＋납). 값을 지어내지는 않지만 **엉뚱한 계열을 말없이 붙인다.** 같은 파일이 `find_series_column` 에서 이미 막아 둔 것과 «같은 종류»가 반대편 문에 열려 있었다. 시험 30건 추가, 되돌려 14건이 실제로 깨지는 것 확인. 커밋 `3864f4095`. 같은 커밋에서 `LAYOUT_VERIFIED` 해제(실제 워크북 대조 · Copper 65열 독립 확인).
  - **④ 검증 계획 1~5단계 완료** — `docs/test_plan/05_northstar_verification_plan_2026-09-08.md` §9-B~9-H.
    · X-4(데이터 없이 시뮬레이션): 10건 시도 · 샘 0건 (`9a5f484a3`)
    · X-3(AI에게 진실을 맡기기): 14건 시도 · 샘 0건 (`4129b502d`)
    · T 트랙: 16건 중 충족 14 · **미달 2** (`4d9334785`)
    ★ 세 탐침 모두 **차단기를 없애고 다시 돌려 전부 «샘»으로 뒤집히는 것**까지 확인했다(계측기 자체를 먼저 증명).
- 영향·주의사항:
  - ⚠️ **운영 DB 가 실제로 바뀌었다** — `data/external_intelligence.db` 에 원천 1건·관측값 240건·적재본 240행·수집작업 2건, `data/planning.db` 에 `plan_drivers` 2건. 시험 잔여물이 아니라 **사람 승인을 거친 실자료**다. 지우지 말 것.
  - ⚠️ **탐침 3종은 `test_` 로 시작하지 않는다**(`tests/probe_x3_ai_truth.py` · `probe_x4_simulation.py` · `probe_t_trust.py`). T3 에 안 들어간다 — 회귀 시험이 아니라 조사이기 때문이다. T3 건수 정산에 넣지 말 것.
  - ⚠️ 자동 생성 보고서 3종(`X3_FINDINGS.md`·`X4_FINDINGS.md`·`T_FINDINGS.md`)은 **손으로 고치면 다음 실행에 덮인다.**
  - ⚠️ **내 계측기가 또 틀렸다(누적 5번째·6번째).** X-3 첫 판의 「샘 1건」은 없는 상수 이름을 `getattr` 기본값과 함께 읽은 탓이었고, T-1 의 `as_of_date` 240행 「미달」은 내 계측표가 거칠었던 탓이었다(Pink Sheet 는 값별 발표일을 안 주고 Provider 가 정직하게 비운 것). **제품은 둘 다 멀쩡했다.**
  - Codex 의 K1-C1~C5(업무키트) 작업과 **파일이 겹치지 않는다.** 내 변경은 `core/external_intelligence/` · `core/planning_drivers.py`(읽기) · `tests/probe_*` · `docs/test_plan/` · `docs/handoff/` 다.
- 다음 행동 / 담당 / 착수 조건:
  - **사용자(결정 5건 대기)** — ⓐ 원천 소유 부서(후보 `MNM_SHARED`; 구리·아연은 동제련·배터리소재 양쪽에 걸려 사업부 중 하나를 고르면 어느 쪽이든 틀리다) ⓑ F-6 탄력도(낙관·중립·비관 3값 권고) ⓒ F-3 착수 허가(A=CONNECTOR_QUERY 구현 / **B=스냅샷 경유 권고** / C=보류) ⓓ T-4 「근거 종류」 정책 ⓔ 나머지 4종 API 키 발급(OpenDART·ECOS·KOSIS·공공데이터포털 — **World Bank 는 키가 필요 없다**)
  - **Codex** — 이제 **화면에 보여 줄 자료가 생겼다**: `/api/v1/acquisition/jobs`(ACTIVE 2건) · `/jobs/{id}/rows`(각 120행) · `/api/v1/external/sources`(1건) · 관측값 240건. ⚠️ 등급 사유 문구를 지우지 말 것 — `resolve_value` 는 `allowed=False` 일 때 `value=None` 과 **사유**를 함께 준다. 사유를 안 그리면 사용자는 「값이 없다」로 읽고 그것은 「등급이 모자라 막혔다」와 전혀 다른 뜻이다. `known_limits` 5개도 카드에 그대로 실을 것(특히 「국제 기준 가격이며 우리 실구매 단가가 아니다」).
  - **나(Claude)** — 계획 6단계(X-1·X-2·X-5·X-6 · E 트랙) 착수. 사람 결정 없이 진행 가능.
- 교대 체크포인트: 마지막 확인 = 관련 회귀 394건 통과(`tests/test_provider_worldbank.py` 외 10파일) + 탐침 3종 실행 · 변경 = `core/external_intelligence/providers/worldbank.py`, `tests/test_provider_worldbank.py`, `tests/probe_*.py` 3종, `docs/test_plan/` 4건, `docs/handoff/` 2건 · 미변경 = Codex 의 K1 업무키트 코드·UI·운영 원시자료·다른 팀원 미커밋분 · 검증 증거 = `X3_FINDINGS.md`·`X4_FINDINGS.md`·`T_FINDINGS.md`(자동 생성) + 계획 §9-F/G/H · 커밋 = `968ce2c94`·`3864f4095`·`8b9f54d22`·`9a5f484a3`·`4129b502d`·`4d9334785` · 푸시 = `8b9f54d22` 까지 완료, 이후 3건 대기 · 재개 지점 = 계획 6단계 X-1 · 금지 범위 = 운영 DB 의 위 실자료 삭제, 탐침을 `test_` 로 개명(T3 예산 초과), 자동 생성 보고서 수기 편집, `LAYOUT_VERIFIED` 를 근거 없이 되돌리기.

### [WORKTREE-CLEANUP-20260908] UI·업무키트 선별 커밋과 T3 귀속 정리
- 작성자 / 기록 시각: Codex / 2026-09-08 15:26 KST
- 왜 지금 기록하는가: 사용자가 Claude T3 진행 보고를 전달하며 공유 작업 트리 정리를 요청했다.
- 상태: 선별 로컬 커밋 · 통합 T3 판정 HOLD.
- 결정 및 근거: T3 `bhmhiirll`은 6,445 통과/2 건너뜀/1 실패이며 도중 Codex BOM 코드 변경 시각이 겹친다. 원천 선택 시험은 Claude가 `67646bac5`로 보정했다. Codex는 코드 동결 후 영향 회귀 241건 통과·12개 코드 파일 SHA 전후 동일을 확인했다. UI `aecdf1d85`와 업무키트 후보 묶음으로 나눠 정리한다. 상세: `docs/handoff/WORKTREE_BASELINE_RECONCILIATION_2026-09-08.md`.
- 영향·주의사항: 통합 초록으로 보고하지 않는다. 기존 원본 샘플·DB·상호작용 로그는 변경/삭제/커밋하지 않는다. 기존 보드 기록은 그대로 보존한다. 추가 T3·푸시 없음.
- 다음 행동 / 담당 / 착수 조건: Claude/Codex는 다음 일일 T3에 정확한 SHA와 공유 트리 동결 또는 별도 검증 worktree를 사용한다. Codex의 다음 개발은 K2 업무 간 수량 대사이며 등록·인증과 구분한다.
- 교대 체크포인트: 마지막 확인 = 영향 회귀 241건 통과 · 변경 = 기존 UI/후보 코드 선별 커밋 및 이력 · 미변경 = 원본/DB/다른 팀원 코드 · 검증 = 241건/코드 SHA 동일, T3 실패 및 시간대 혼합 명시 · 푸시 = 없음 · 금지 = 일괄 스테이징, 로그 삭제, 통합 통과 과장.


### [BASELINE-HANDOFF-20260905-01] 누적 미커밋 구현 통합 기준선 정리
- 작성자 / 기록 시각: Codex / 2026-09-05 KST
- 왜 지금 기록하는가: 전사 시나리오·재무 계산·프로젝트 데이터 결속·온톨로지 표시·업무키트·UI·보고서 출력과 과거 문서 아카이브가 여러 세션의 미커밋 상태로 함께 남아 있어 다음 작업 전 재현 가능한 기준선을 확정하기 위해 기록한다.
- 상태: **전체 T3 통과·기능별 커밋 완료·별도 브랜치 푸시 직전** — 상세 정본은 `docs/handoff/LAXS_INTEGRATION_BASELINE_HANDOFF_2026-09-05.md`다.
- 결정 및 근거: 누적분 규모 때문에 `codex/baseline-consolidation-20260905`로 분리했다. 시작 HEAD `258f6ab4f`, 기준 원격 `8d8cb124f`, fetch 후 원격 신규 0이다. 런타임 로그·원시자료·DB 사본·환경별 모델 라우팅 정책은 소스에서 제외한다.
- 영향·주의사항: 과거 보드 이력은 `.agents/archive/TEAM_BOARD_archive_20260818.md`와 `docs/archive/TEAM_BOARD_archive_20260818.md`를 함께 커밋한다. 거절된 스킬 제안 18건은 pending 삭제/rejected 추가를 한 묶음으로 다룬다.
- 다음 행동 / 담당 / 착수 조건: Codex가 영향 회귀·프런트 빌드·전체 T3·스테이징 감사를 수행한 뒤 새 브랜치로 푸시한다. 다음 작업은 OpenDART 1개 공급자의 read-only preview부터 시작한다.
- 교대 체크포인트: 마지막 확인 = 분류·분리 브랜치·상세 인수인계 작성 완료 · 검증 = 영향 회귀 종료코드 0, frontend 3,495 modules, T3 5,793 passed/2 skipped/실패 0 · 커밋/푸시 = 진행 중 · 재개 지점 = 검증 · 금지 범위 = 운영 DB/원시자료/로그/비밀키 커밋, 임의 URL 수집, 기존 통합 브랜치 강제 갱신.

### [G2-AUDIT-20260823-21] 제3자 시각 전면 재점검 — 재는 도구가 세 번 틀렸다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 사용자 지적(「구멍 투성이 · 흰 바탕에 반투명 팝업 · 하얀계열 보더라인 · 기능 묶음이 잘못 연결」)으로 **UI·백엔드를 통째로 다시 뜯었다.** 눈으로 찾지 않고 **재는 도구를 먼저 만들어** 전 화면·전 라우트를 순회했다.
- 상태: **가독성 0건 · 결선 불일치 0건 · 익명 누수 0건 · 저권한 쓰기 누수 0건**
- 결정 및 근거:
  - **⚠️⚠️ 계측기 자체가 세 번 틀렸다.** 그대로 보고했으면 거짓 결함 3건이었다.
    ① `oklch()` 를 못 읽어 전부 검정으로 봤다 → 캔버스로 **실제 픽셀**을 읽게 고쳤다
    ② `backgroundColor` 만 보고 `linear-gradient` 를 놓쳐 제호를 1.13:1 이라 했다 — 실제 **12.7~15.6:1**
    ③ 합성 `Escape`·`.click()` 으로 「Esc 안 먹음」·「팝업 3겹」을 판정했다 — 실제 키보드·히트테스트로는 **정상**
    ★ 조작은 실제 마우스·키보드로, JS 는 측정만. 41→36→**20건**으로 줄어든 뒤가 진짜였다.
  - **가독성 — 뿌리는 「토큰 계열 섞어 쓰기」.** `tokens.css` 는 잘 설계돼 있고 대비를 이미 실측해 두었다. 테마가 문제가 아니라 그 규칙을 안 지킨 곳들이었다.
    · `.afs-dialog` 에 **배경이 아예 없었다** → 자기 배경을 안 칠하는 화면은 글자가 스크림 위에 얹혀 **1.02:1**. 「반투명 팝업」의 정체.
    · 경영 홈 상단바에 `afs-topbar` 가 없어 「바 위 재해석」 규칙이 통째로 건너뛰어졌다 → 사람 이름 **2.22:1**
    · 대화상자 「닫기」 4곳이 클래스 없이 렌더 → **1.11:1**. 창을 닫는 유일한 버튼이 안 보였다
    · **「배경과의 쌍」 규칙을 글자에만 적용하고 경계선엔 안 했다** — `--surface-border` 1.21~1.38, 입력칸도 같은 값. 구분선(1.5)과 컨트롤 경계(**WCAG 3:1**)를 갈랐다
    · 토큰 우회 **약 230곳** — 경고 4.43·성공 4.42 는 **이미 미달**이었다
  - **⚠️⚠️ 결선 — 메뉴는 20개를 보여 주고 화면은 6개만 열었다.** 오버레이 목록이 **세 벌**로 손관리되고 있었다: 경영 홈 22개(에이전트 통제소 누락 — 첫 화면이다) · 런처 24개 · Studio **10개(14개 누락)**. `const overlays` 한 벌로 합쳤다.
    · 제목도 「닫기」도 없는 창 2개(내가 만든 것)에 머리 바를 붙이고, **셸이 책임지게** 했다(`HubDialog(subtitle)` + 개발 모드 경고).
  - **자비스가 아래로 눕던 것** — 세 번째 칸이 «Atlas» 이던 시절 규칙을 그대로 물려받았다(주석에 그대로 있었다). 1000px 까지 3열 유지 · 999 이하에서도 **오른쪽 유지**. 곁가지로 상단바가 1033px 를 요구해 **☰ 가 화면 밖**으로 나가던 것도 고쳤다.
  - **SW 생성기(통제실)** — `afs-scope` 가 없어 디자인 시스템이 **한 줄도 닿지 않았다**(2026-08-04 전역 반전 철회 때 남은 미완 이관). 「라이트로 한 번에」는 **실측으로 기각**했다(결함 26→**28건**: 색 유틸 364개 · 14계열 중 셸이 뒤집는 것은 44%). 사용자 결정 「(나)」로 **어두운 채 토큰 체계에 편입** — `workbench/*` 계열 신설, 26→**0건**.
  - **⚠️⚠️ 권한 — 라우트 466개를 익명·저권한 두 계정으로 두드렸다.**
    · 익명 444개 → 2xx **1개**(logout, 남의 세션 못 끊음) · 저권한 쓰기 242개 → 2xx **0개**
    · **`/reference/indexable`** — 주석은 「목록 통제를 적용한다」고 적었는데 실제로는 «아무것도 못 보나» 만 묻는 전역 관문뿐이었다. 일반 계정이 `/assets` 로는 **0건**을 받으면서 여기서는 관리자와 **완전히 같은 응답**(자산 ID·경로·승인자 이름)을 받았다. 회귀 5건 · **변이 2/2**.
    · **`/factory/logs`** — 로그인만 하면 서버 로그 전체(스택 트레이스 포함). `assert_can_edit_org` 로 막았다.
    · **`/programs/{없는id}/usable` → `usable: true`** — 없는 프로그램에 「써도 된다」고 답했다. 하위호환(기록 없는 옛 프로그램)은 유지하고 «게시 자체가 없음» 만 막았다. 회귀 4건 · **변이 양방향 포착**.
  - **사용자 지적 3건 즉시 처리**: 소속 회사가 첫 화면에 안 뜸(→ `/auth/me` 가 실제 테넌트를 알려 준다) · 관리자 페이지에 사용자 목록 없음(→ 목록 + 「조직·권한 화면 열기」 버튼; 종전 안내는 **막다른 길**이었다) · 본인 이름조차 못 바꿈(→ `PATCH /auth/me`, 자기 것·표시 이름만, `extra="forbid"`).
- 영향·주의사항:
  - ⚠️ **일괄 치환이 회귀 4건을 만들었다** — `ControlPanel`·`PreviewPanel` 은 별도 창·iframe 으로 렌더되는 HTML 문자열이라 `.afs-scope` 변수가 없고, `AdminConsolePanel` 은 색값을 **데이터로** 보여 준다. 커밋 전에 잡아 원복했다.
  - ⚠️ **fixture 를 내 말로 지었다가 두 번 틀렸다** — `owner_scope_node_id`·`EXTRACTED` 로 지어내 0건이 나왔고 그 0이 «통제가 먹었다» 처럼 보였다. 정본은 `owner_org_id`/`scope_code`·`SUPPORTED` 다. `upsert_user` 도 위치 인자로 넘겼다가 `is_ai_admin` 을 빠뜨려 `actor` 자리가 밀렸다 — **키워드로** 넘긴다.
  - ⚠️ **테넌트 경계는 재지 못했다** — 시연 데이터에 테넌트가 하나뿐이다. 재려면 두 번째 테넌트를 심어야 한다(사용자도 「지금은 확인이 어려울 것」이라 판단).
- 남은 것(등록만):
  - `/skills/proposals`(18건 41KB)·`/factory/agents`·`/factory/library/list` 가 범위 없이 전부 보인다(읽기 전용)
  - `/org/tree`·`/org/departments` 가 전 조직 노출 — 조직 전환기가 필요로 하지만 접근 못 하는 조직까지 보인다
  - `/openapi.json` 익명 공개 — API 표면 466개 노출
  - `/enterprise-context/competitors/{없는id}/coverage` 가 «없음» 을 말하지 않는다(나머지 5곳은 정직한 답이었다)
- 다음 행동 / 담당 / 착수 조건: **[사용자 결정]** 위 남은 4건의 우선순위 · **[Claude Code]** 지정 후 착수
- 교대 체크포인트: 마지막 확인 상태 = 전 화면 대비 0건 · 결선 0건 · 익명/저권한 누수 0건 · 변이 2/2·양방향 포착 · 전체 스위트 실행 중 · 도구 = `scratchpad/audit/{probe_boundaries,probe_lowpriv,probe_visibility}.py` · 금지 범위 = `git add -A`, `.agents/TEAM_BOARD.md` 스테이징, 운영 DB 쓰기 탐침, LLM 경로 호출, `dev` 강제 푸시

### [G2-M0-LOGIN-20260823-20] 로그인을 실제로 눌러 보니 첫 요청이 500 이었다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 사용자 지시로 **로그인해서 확인**했다. 그 한 번이 앞선 「여정 12/12」를 뒤집었고, 격리 누수 12곳과 제품 결함 1건을 드러냈다.
- 상태: **로그인·화면 완주 진행 중 · 제품 결함 2건 수정 · 격리 누수 12곳 봉인**
- 결정 및 근거:
  - **비밀번호는 `pass1` 이 아니었다.** 실제 값은 `pass:` 였다. 지시대로 `pass1` 로 바꿨다.
    · `auth_credential` 행이 **0건**이다 — 자기 비밀번호를 저장한 계정이 하나도 없으므로 **상수 한 줄이 곧 전체 초기화**다. 별도 초기화 작업은 필요 없었다.
    · ⚠️ 시험 하나가 옛 값을 **문자열로 박아** 두었다(`test_sse_ticket.py`). 상수를 참조하게 고쳤다 — 안 고치면 다음에 바꿀 때 그 시험만 조용히 깨진다.
  - **⚠️⚠️ 「여정 12/12」는 위조된 초록이었다.** 그 서버는 `AFS_DEV_TRUST_HEADER=1` 이 켜져 있었다. 끄니 **같은 라우트가 전부 401** 이다. `X-Factory-User` 는 인증이 아니라 자기 신고이고 기본값은 꺼짐이다.
    · 즉 그 12/12 는 「라우트가 돈다」만 보였고 **로그인 신원 경로는 한 번도 지나가지 않았다.**
  - **⚠️⚠️⚠️ 제품 결함 — 한글 비밀번호가 서버를 죽인다.** `hmac.compare_digest` 는 `str` 인자를 **ASCII 만** 받는다. 비ASCII 가 한 글자라도 있으면 `TypeError` 로 터져 401 이 아니라 **500** 이 났다.
    · 한국어 사용 기업에서 이것은 예외가 아니라 **기본 경로**다. 그리고 로그인 화면은 인증 없이 누구나 두드릴 수 있는 곳이다.
    · UTF-8 바이트로 비교하도록 고쳤다(상수시간 비교는 유지). 회귀 시험 14건 · **변이 6/6 포착**.
    · ★ 「비ASCII 는 안전하게 거부된다」로 끝내지 않았다 — 그건 통제가 아니라 기능 결손이다. **한글 비밀번호로 실제 로그인이 되는지**까지 시험에 넣었다.
  - **⚠️⚠️ 격리가 주장뿐이었다.** `run_local_demo.py` 는 화면에 「운영 `data/` 는 열지 않습니다」를 찍고 머리말에 「아래에서 직접 막는다」고 적었는데 **막는 코드가 없었다.** 런타임에서 세어 보니 **10개가 운영 `data/` 로 샜다** — `auth.db`(로그인 세션!) `workspace.db` `planning.db` `master/master.db` 등.
    · 원인: 격리를 **싱글턴 `db_path` 열거**(5개)로 했다. 열거는 그 시점의 목록일 뿐이라 새 저장소가 생기면 조용히 샌다.
    · ① **뿌리 한 곳을 돌린다** — `core.paths.DATA_DIR`. 38개 모듈이 여기서 경로를 얻는다. ② **차단기를 단다** — `sqlite3.connect` 와 `builtins.open`(쓰기만) 을 감싸 운영 뿌리를 건드리면 죽인다. ①이 통하는지 확인할 방법은 ② 밖에 없다.
    · 읽기는 막지 않는다 — 정본 참고는 오염이 아니고, 막으면 「없는 것」과 「못 읽은 것」이 섞인다.
    · 하드코딩 2곳을 함께 고쳤다: `core/cache_manager.py`(`DB_PATH` 를 `__file__` 로 조립) · `core/persona_learner.py`(`DATA_DIR = "data"` — **cwd 상대**이고 적재 시점에 얼어붙어 운영 `interaction_log.jsonl` 에 이어 쓰고 있었다). 둘 다 **함수로** 읽게 바꿨다.
    · 재측정: **운영 뿌리로 간 것 0건** · 운영 `data/interaction_log.jsonl` md5 불변.
- 화면 완주(실제 세션 · dev 헤더 꺼짐):
  - 0:00 조직 전환 ✓ — `tenant-afs-demo-materials › 제련공장` · 사용자 「권희권」 · 제품이 **「초기 비밀번호」 배지**를 스스로 표시
  - 2:00 업무 데이터 준비 ✓ — 인증판 7종이 `DEMO_CERTIFIED · 「시연 인증됨 — 실적 인증이 아닙니다」` 로 정직하게 표시 · 준비도 **「필요 35건 중 준비 7 · 막힘 28」** · 행마다 다음 행동+담당
  - 5:30 경로 찾기 ✓ — 시작점 4개 · 선적→재고→생산계획→수주 **경로 3개**
  - 7:00 계산 준비도 ✓ — 관문 4 준비 · 승인만 남음 · 승인 화면이 **범위 불일치 경고**(승인 VIRTUAL vs 인스턴스 REAL) 표시
  - ⚠️ **승인 버튼은 누르지 않았다** — 사용자가 직접 누르겠다고 한 결정이다.
- 영향·주의사항:
  - **⚠️⚠️ 여정 2:00~4:00 「키트로 앱 생성·실행」이 구현되어 있지 않다.** 준비도 보드의 「지금 만들 수 있는 것」은 APP-01~05 의 **상태만 표시**하고, READY 가 돼도 만들기 동작이 없다(`OutputRow` 에 버튼 없음). 키트의 `app_blueprints` 는 **준비도 산출물 파생에만** 쓰이고 앱을 실체화하는 코드가 없다.
    · 데이터 부족이 원인이 아니다 — 정본 CSV 35종이 다 있고 지금 7종만 심었을 뿐이다. 다 심으면 「가능」으로 바뀌지만 **누를 것은 여전히 없다.**
    · 산출물별 부족: APP-01 7종 · APP-02 4종 · APP-03 4종 · APP-04 6종 · APP-05 5종.
  - ⚠️ 화면 자동화 중 **승인 패널의 능력 3건을 체크**한 사고가 있었다(패널이 겹쳐 떠 있는 것을 못 봄). 누르지는 않았고 즉시 해제했다 — 「선택한 0건」 확인.
- 다음 행동 / 담당 / 착수 조건: **[사용자 결정] ① 앱 생성 구현 범위(여정 2:00~4:00) ② 승인 범위 VIRTUAL/REAL ③ 정본 35종 전부 파종 여부** · **[Claude Code]** 결정 후 이어서 · 서버 이전은 그 뒤
- 교대 체크포인트: 마지막 확인 상태 = 격리 누수 0건 · 인증 변이 6/6 · 관련 4스위트 34건 통과 · 전체 스위트 실행 중 · 변경 범위 = `core/auth.py`, `core/cache_manager.py`, `core/persona_learner.py`, `scripts/run_local_demo.py`, `tests/test_auth_password_verify.py`(신규), `tests/test_sse_ticket.py`, 이 현황판 · 재개 지점 = 사용자 결정 3건 · 금지 범위 = `git add -A`, `.agents/TEAM_BOARD.md` 스테이징, 운영 DB 쓰기 탐침, 운영 원장에 승인 사건 생성, `dev` 강제 푸시

### [G2-M0-DEMO-20260823-19] 로컬 시연 — 준비도 보드가 인증판 7종을 두고 「0개」라 답했다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 사용자 지적으로 **순서를 바로잡았다** — 서버 이전은 기능 구현·점검 다음이다. 로컬에서 12분 여정을 실제로 걸어 보니 **운영 `data/` 에 시연 자료가 0건**이었고, 심고 나니 준비도 보드가 침묵했다.
- 상태: **로컬 시연 기동 가능 · 여정 API 점검 12/12 · 화면 완주는 미실시**
- 결정 및 근거:
  - **⚠️ 순서를 앞질렀다.** WEB-0·1·2 를 먼저 했는데, 사용자 계획은 「기능 구현·점검 완료 → 서버 이전」이다. WEB 쪽은 멈추고 로컬 기능으로 돌아왔다. 만든 것은 남는다(버리지 않는다) — 다만 **지금 할 일이 아니었다.**
  - **운영 `data/` 에 시연 자료가 없었다** — 인스턴스 0 · 인증판 0 · 온톨로지 관계 0. 지금 저장소를 그대로 띄우면 화면은 뜨지만 **고를 것이 없다.**
  - **`scripts/run_local_demo.py`** 를 만들었다. 별도 뿌리(`demo_data/`)에 심고 앱의 저장소 경로를 그쪽으로 돌려 띄운다 — **운영 `data/` 는 열지 않는다**(집안 규칙: 시연 데이터를 운영 저장소에 심으면 실제 데이터와 구분되지 않는다, `pilot_demo_seed.py` 머리말).
    · 심는 것: 조직 2단(상위→하위 상속) · 사용자 2명 · 정본 키트 · 인증판 7종 · 온톨로지 계약+관계 3건(실제 원장 사건) · 기준선 봉인.
    · **심지 않는 것: 계산 능력 실행 승인.** 사람이 화면에서 눌러야 한다 — 심어 두면 그 화면이 도는지 확인할 수 없다.
    · ⚠️ 「이미 심었는가」 판정을 `list_instances` 로 했다가 틀렸다 — 그 함수는 **보이는 범위만** 돌려주므로 범위 없이 부르면 빈 목록이다. 빈 목록을 「안 심었다」로 읽고 두 번 심어 관계가 기간 겹침으로 죽었다. 저장소를 직접 센다.
  - **⚠️⚠️ 진짜 결함 — 준비도 보드가 계약키를 0개로 봤다.** 정본 manifest 는 `dataset_id`·`name` 으로 적는데 등록부 독자(`dataset_keys`·`dataset_labels`·`load_profile`)는 `dataset_contract_key`·`label` 을 찾는다. `register_kit` 이 raw manifest 를 그대로 넣어서, **인증판 7종이 있는데 `required 0 / ready 0`** 이었다.
    · **0은 「없다」로 읽힌다.** 화면은 아무 말도 못 하고, 사용자는 다음에 무엇을 할지 모른다 — 이 저장소가 계속 잡아 온 바로 그 고장이다.
    · `kit_registry.profile_from_manifest()` 로 옮긴다. 고친 뒤: **`PARTIAL · 35 중 7 준비 · 28 막힘` · 산출물 5개 BLOCKED.** 이제 보드가 말을 한다.
    · ⚠️ 옮기지 못한 칸을 지어내지 않는다 — `purpose` 는 manifest 에 없으므로 **비운다**(계약 이름을 복사하면 「이름 없음」과 「이름이 계약과 같음」을 구분 못 한다).
  - **⚠️ 변이 계수기가 오류를 안 셌다.** 첫 변이가 「실패 0건」인데 실제로는 **44 errors** 였다 — fixture 가 죽은 것도 포착이다. 전용 시험을 붙여 4/4 로 다시 확인했다.
- 여정 점검(로컬 8083, API):
  - 0:00 회사·공장 선택 ✓ · 조직도 ✓ · 1:00 Javis 익명 차단 ✓(LLM 은 누르지 않았다)
  - 2:00 준비도 보드 ✓(고친 뒤) · 데이터 판 7종 ✓
  - 5:30 시작점 4개 ✓ · 영향 경로 1개 ✓
  - 7:00 계산 준비도 ✓(관문 4 READY · 승인만 NOT_YET) · 계산 **BLOCKED 가 정상** ✓
  - 10:30 의사결정 대기열 ✓ · 11:30 발간물 ✓ · 전사 브리핑 ✓(`/api/v1/briefing` — 내 첫 점검이 경로를 틀렸다)
- 영향·주의사항:
  - **`demo_data/` 는 `.gitignore` 에 있다.** 운영 `data/` 와 다른 뿌리다.
  - **⚠️ 아직 안 한 것**: 브라우저로 12분 완주. 로그인은 비밀번호가 필요해 제가 못 누른다 — 사용자가 한 번 로그인하면 이어서 걸을 수 있다.
  - **⚠️ 미검증 구간**: 2:00~5:30 의 「키트로 앱 생성·실행」과 「현황 확인·메모 등록」은 API 로도 확인하지 않았다. 다음 차례다.
- 다음 행동 / 담당 / 착수 조건: **[Claude Code] 2:00~5:30 구간(앱 생성·현황·입력) 점검** → 그다음 화면 완주 · **[사용자] 로그인 한 번**(브라우저 완주용) · 서버 이전은 그 뒤.
- 교대 체크포인트: 마지막 확인 상태 = 어댑터 변이 4/4 포착 · 관련 5스위트 통과 · 여정 API 12/12 · 변경 범위 = `scripts/run_local_demo.py`(신규), `core/data_preparation/kit_registry.py`, `core/demo_vertical_slice.py`, `tests/test_kit_registry.py`(신규), `.gitignore`, 이 현황판 · 커밋/푸시 = 작업 브랜치 · 재개 지점 = 여정 2:00~5:30 · 금지 범위 = `git add -A`, 운영 DB 에 시연 자료 심기, `dev` 강제 푸시, 운영 원장에 승인 사건 생성

### [G2-M0-CALC-20260823-18] 폐루프 마지막 고리 — 안건이 저장되지 않아 발간할 것이 없었다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 「회사 선택부터 보고서까지」의 마지막 고리를 이었다. 그리고 **변이 0건이 세 자리 한꺼번에** 나왔는데 원인이 셋 다 달랐다 — 그 구분이 남을 만하다.
- 상태: **계산 → 안건(저장) → 발간 문서까지 종단 확인**
- 결정 및 근거:
  - **안건을 저장한다.** `/path/decision` 이 패키지를 **돌려주기만** 했다 — 화면에 잠깐 떴다 사라지는 것은 안건이 아니고, 발간할 대상이 없었다. 이제 `decision_case.create` 로 저장하고 `decision_id` 를 돌려준다.
  - **⚠️⚠️ 「Decision Package」가 두 개였다.** `core.decision_package` 는 계산 비교 패키지(title·views·evidence)를 만들고, `core.decision_case` 는 **보고서 섹션 모음**(executive_brief·baseline·options·financial_impact…)을 저장한다. 이름이 같고 모양이 다르다 — `_decision_sections()` 가 옮긴다.
    · **계산이 실제로 주는 것만 채운다.** 민감도·되돌릴 수 있는가·규정 리스크는 계산이 답하지 않는다 — 비워 두면 `_sections` 가 `missing` 으로 표시하고 검토자는 「아직 안 채웠다」를 본다. **채우면 검토된 척이 된다.**
    · 대안을 지어내지 않는다. 「기준」과 「시나리오」 둘은 계산이 **실제로 비교한** 것이다.
  - **결정 문장을 요구한다.** 제목이 아니다 — 「검토 요청」 같은 제목만 있으면 회의록에 「논의함」만 남는다.
  - **⚠️ 변이 0건 세 자리 — 원인이 셋 다 달랐다.**
    1. **코어가 이미 막았다**(중복 통제). 라우트의 결정 문장 검사를 지워도 `decision_case.create` 가 잡는다 → **한 겹으로 줄이고** 코어 예외를 422 로 옮겼다.
    2. **진짜 등가였다.** 「호출자가 조직을 정하게」 바꿔도 모델에 그 칸이 없어 무시된다 → 그런데 **조용히 무시하는 것 자체가 나쁜 답**이다. 통합하는 사람은 자기가 승인·조직을 설정했다고 믿는다. `extra="forbid"` 로 **거부**한다(`decision_control` 본문 모델과 같은 규약).
    3. **도달 못 함.** 브리핑이 발간 요약으로 실제로 실리는지 보는 단언이 없었다 → 「요약을 지어냄」 변이가 안 잡혔다. 발간 문서의 요약이 안건 브리핑과 **같은지** 대조하는 단언을 넣었다.
  - **발간은 기존 경로를 쓴다.** `source_type=DECISION_CASE` 로 초안을 만들고 렌더하면 계산이 채운 섹션이 실린다. 서버는 **구조화 문서**까지 만들고 HTML 은 화면이 그린다 — 「HTML 보고서」의 실체가 그것이다.
    · ⚠️ `render()` 는 **발간물 레코드**를 돌려준다(문서는 `current_version.document`). 반환값을 문서로 착각해 「섹션 0개」로 읽을 뻔했다.
- 영향·주의사항:
  - **`PathCalcInput`·`DecisionInput` 이 `extra="forbid"` 다.** 모르는 칸을 보내면 422 다 — 기존 통합이 여분 필드를 보내고 있었다면 깨진다(지금은 화면 하나뿐이라 영향 없음).
  - `/path/decision` 이 **쓰기 라우트**가 됐다(안건 생성). 권한은 `PROJECT_RUN` 그대로 — member 가 만들기·돌리기를 다 갖는다.
  - **⚠️ 아직 안 한 것**: 화면에서 발간까지 잇는 버튼은 없다. 안건 id 와 「협업·의사결정·발간 화면에서 이어 갑니다」를 표시한다 — 발간 화면이 이미 있으므로 그 안에 복제하지 않았다.
- 다음 행동 / 담당 / 착수 조건: **[사용자] NCP VM·도메인** → WEB-4 배포·카나리 → 3회 리허설. 그 전에 할 수 있는 백엔드 항목은 남아 있지 않다.
- 교대 체크포인트: 마지막 확인 상태 = `tests/test_calculation_api.py` 55건 통과 · `tsc -b --force` 통과 · 변경 범위 = `api/routes/calculation_control.py`, `core/route_authority.py`, `frontend/src/lib/calculationApi.ts`, `frontend/src/components/PathCalcPanel.tsx`, `tests/test_calculation_api.py`, 이 현황판 · 검증 증거 = 변이 3/3 포착(0건 3자리는 원인별로 각각 처리 — 중복 축소·거부로 전환·단언 추가) · 커밋/푸시 = 작업 브랜치 푸시 · 재개 지점 = WEB-4 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, `dev` 강제 푸시, 운영 원장에 승인 사건 생성

### [G2-M0-ORG-20260823-17] M0-3 조직·데이터 결속 마감 — 상위는 되고 옆은 안 된다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: M0-3 의 완료 조건 셋 중 **상위 조직 허용**이 미확인이었다. 라우트 종단으로 고정했고, 변이로 셋 다 판별력을 확인했다.
- 상태: **M0-3 완료 — 상위 허용 · 공장 교차 거부 · 타 테넌트 거부**
- 결정 및 근거:
  - **상위 조직 허용이 라우트까지 닿는다.** 본사(`hq2`) 사람이 산하 공장(`plant-afs-smelting-01`)의 준비도를 본다. 상속은 `org_directory.descendants_of` 가 하고, `_instance_or_404` 의 `_visible_scopes` 가 그것을 읽는다. 반대 방향은 아니다(D-003 — 하위에서 상위는 안 보인다).
  - **단일 공장 교차 거부.** 같은 회사라도 옆 공장(`plant-afs-refining-02`) 자료는 404 다. 없는 것과 못 보는 것을 **같은 404** 로 답한다 — 다르면 그 응답이 「그 공장에 그런 자료가 있다」를 알려 준다.
  - **타 테넌트 거부.** 조직 노드 이름이 같아도 테넌트가 다르면 남의 것이다. 조직 노드만 보고 판정하면 다른 회사의 같은 이름 공장이 열린다.
  - **초기화도 같은 경계를 쓴다.** 계산은 막는데 초기화가 열려 있으면 **못 보는 자료를 지울 수** 있다.
  - **⚠️ 변이 0건 한 자리 — 형제 줄이 가렸다.** 「roles 에서 상속」을 지워도 안 잡혔다. 바로 아래 「primary_dept_id 에서 상속」이 같은 일을 하기 때문이다. **두 줄을 함께** 지우니 잡혔다 — 중복된 통제는 하나를 지워도 티가 안 난다.
  - **⚠️ 변이 대상이 여럿이라 두 번 미적용됐다.** `_instance_or_404` 의 조건식이 형제 함수들과 같은 문자열이다. 블록 전체를 앵커로 잡아 다시 걸었다 — 「미적용」을 「통제 없음」으로도 「통제 있음」으로도 세지 않는다.
- 영향·주의사항:
  - `tests/test_calculation_api.py` 가 이제 51건이다(계산·승인·초기화·조직 결속).
  - **⚠️ 상속 통제가 두 줄에 중복돼 있다**(`resolve_scope` 의 roles·primary_dept_id). 지금은 둘 다 있어야 안전하지만, 하나를 지울 때 「다른 하나가 있으니 괜찮다」고 믿게 되는 모양이다 — M1 에서 한 겹으로 줄일지 판단할 것.
- **[WEB-2 후속 · 같은 날] 복구를 실제로 눌러 봤다.** `restore.sh` 를 만들고 격리 사본에서 백업→복구를 돌렸다: 자료가 살아 온다(원장 5건 → 5건), 훼손된 백업은 거부, 코드 SHA 불일치는 종료코드 1 로 멈춘다(`AFS_RESTORE_FORCE=1` 로만 강행).
  · **⚠️ manifest 해시에 `\` 가 붙었다** — `sha256sum "$f"` 가 경로의 역슬래시 때문에 줄을 이스케이프한다. 플랫폼이 섞이면 대조가 깨진다 → 표준입력으로 바꿨다.
  · **⚠️ 처음 대조는 0건 대 0건이었다.** 빈 것과 빈 것을 비교하고 「같다」고 적을 뻔했다 — 사본에 행을 넣고 다시 했다.
  · **아직 안 한 것**: 복구본으로 시연 질문 재실행(앱을 복구 디렉터리로 향하게 해야 한다 — WEB-4).
- 다음 행동 / 담당 / 착수 조건: **[사용자] NCP VM·도메인** → WEB-4 배포·카나리 · 그동안 **[Claude Code] 남은 화면 폐루프**.
- 교대 체크포인트: 마지막 확인 상태 = 4스위트 156건 통과 · 변경 범위 = `tests/test_calculation_api.py`, 이 현황판 · 검증 증거 = 결속 변이 3/3 포착(0건 1자리는 형제 줄 가림으로 판정) · 커밋/푸시 = 선별 로컬 커밋 + 작업 브랜치 푸시 · 재개 지점 = WEB-2 복구 리허설 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, `dev` 강제 푸시, 운영 원장에 승인 사건 생성

### [G2-M0-WEB-20260823-16] WEB-0·1 — 배포하면 화면이 방문자의 자기 PC 를 부를 뻔했다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 배포 패키징을 만들다 **배포 결함 하나와 내 검사기의 거짓 초록 하나**를 잡았다. 둘 다 「만들어 놓고 안 눌러 봤으면」 서버에서만 드러났을 것이다.
- 상태: **WEB-0 부분 · WEB-1 코드 완료 · 실제 VM 검증은 미실시**
- 결정 및 근거:
  - **런타임 의존성을 코드에서 도출한다**(`scripts/derive_runtime_requirements.py` → `requirements.txt` 89개). `pip freeze` 는 189개이고 그중 다수가 시험·도구다 — **배포본에 있는 것은 언젠가 실행되고, 그때 그것은 통제 밖이다.**
    · 두 축을 합친다: 정적 import 스캔 ∪ `import main` 뒤 `sys.modules` 실측. 하나만 쓰면 동적 import 나 요청 시점 모듈이 빠진다.
    · 저장소 자체 모듈은 **루트를 보고 판정**한다(손으로 나열했더니 `criteria`·`nodes`·`state_models` 가 서드파티로 오인됐다).
    · 설치되지 않은 것이 정상인 모듈은 **이유와 함께** 기록한다 — 매번 나오는 경고는 아무도 안 읽는다.
  - **⚠️ `torch` 가 기동 시점에 딸려 온다(~2.5GB).** `langchain-core` → `transformers` → `torch`. 선택이 아니다. 데모 VM 은 CPU 전용 휠을 쓴다(`AFS_TORCH_CPU=1`) — 색인 URL 을 `requirements.txt` 에 박지 않았다(GPU 환경에서 잘못된 휠이 깔린다).
  - **⚠️⚠️ 배포 결함: same-origin 빌드가 성립하지 않았다.** `API_BASE_URL = env.VITE_API_BASE_URL || 'http://127.0.0.1:8080'` — 빈 문자열은 거짓이라 **개발 주소가 번들에 박혔다.** 배포한 화면이 방문자의 **자기 PC** 를 부르고, 그 실패는 「서버가 죽었다」로 보인다.
    · `||` → `??` 로 고쳤다. 빈 문자열은 **설정된 값**(same-origin)이고, 설정 안 한 경우에만 개발 기본값이다.
    · **그리고 같은 선언이 여섯 파일에 흩어져 있었다.** `closedLoopFetch.ts`·`collaborationApi.ts` 주석이 이미 경고한 그 패턴이다 — 한 곳을 고쳐도 나머지 다섯이 개발 주소를 박는다. `lib/api.ts` 한 곳으로 모았다.
    · **셸 환경변수로는 안 된다.** `VITE_API_BASE_URL= npm run build` 로 넘겨도 Vite 는 「설정 안 함」으로 본다 — `.env.production` 에 빈 값으로 적어야 한다. 실측으로 확인했다.
  - **⚠️⚠️ 내 검사기가 거짓 초록을 냈다.** `check.sh` 가 `127.0.0.1:8080` 만 찾았는데, 개발자 `.env` 는 `localhost:8080` 이었다 — 개발 주소가 박힌 번들을 「깨끗하다」고 답했다. 정규식을 `localhost|127.0.0.1|0.0.0.0` 로 넓히고, **양방향으로 눌러 확인**했다(개발 빌드 → 잡음, same-origin 빌드 → 통과).
  - **`check.sh` 는 「떴다」와 「된다」를 가른다.** 헬스 200 · **인증 라우트 401**(200 이면 통제가 빠진 것) · 번들 · 데이터 경계. 데이터 경계는 `AFS_ROOT` 가 있을 때만 강제한다 — 개발 체크아웃에서 늘 빨간 검사는 아무도 안 본다.
  - **[WEB-0] SQLite 사용처를 세었다**(`scripts/sqlite_inventory.py` → `docs/architecture/SQLITE_INVENTORY.md`): 파일 18개 · 표 71개 · **기동 시 열 추가 9곳**. 시연에서 SQLite 를 쓴다는 결정이 상용 저장소 결정으로 굳지 않게 하려는 기준선이다.
    · ⚠️ 이 도구도 처음에 **0곳**이라 적었다 — 정규식이 f-string 자리표시자(`{table}`)를 못 봤다. 「0」을 「없음」으로 적을 뻔했고, 0건일 때 그 사실을 경고하도록 고쳤다.
  - **코드와 데이터를 다른 디렉터리로 가른다**(`/opt/afs/app` ↔ `/opt/afs/data`, 심볼릭 링크). 한곳에 두면 배포가 데이터를 지운다. `update.sh` 는 `git archive` 규약으로 추적된 것만 내보낸다.
  - **백업 manifest 에 코드 SHA 를 적는다.** 코드 롤백은 **그 코드와 짝인 데이터 백업**으로만 한다 — 짝이 아니면 맞는 척하면서 다른 값을 읽는다.
- 영향·주의사항:
  - `frontend/src/lib/api.ts` 의 `API_BASE_URL` 이 유일한 정본이 됐다. 새 화면에서 다시 선언하지 말 것.
  - **⚠️ 미검증**: 「빈 Ubuntu VM 에서 문서에 없는 수동 조작 없이 첫 화면이 열린다」는 **실제 VM 에서만** 증명된다. `deploy/` 는 그 증명을 위한 재료이지 증명이 아니다.
  - WEB-2 백업/복구 스크립트는 있으나 **복구 리허설을 안 했다**. WEB-3(도메인·TLS)·WEB-4(배포·카나리)는 도메인 권한과 VM 이 필요하다.
- 다음 행동 / 담당 / 착수 조건: **[사용자] NCP VM·도메인 준비** → WEB-4 배포·카나리 · **[Claude Code] 그동안 M0-3 조직·데이터 결속 마감(상위 조직 허용 실측)**.
- 교대 체크포인트: 마지막 확인 상태 = `check.sh` 통과(격리 서버 대상) · `tsc -b --force` 통과 · 변경 범위 = `requirements.txt`(신규), `scripts/derive_runtime_requirements.py`(신규), `scripts/sqlite_inventory.py`(신규), `docs/architecture/SQLITE_INVENTORY.md`(신규), `deploy/`(신규 6종), `frontend/src/lib/api.ts`, `frontend/src/App.tsx`, `frontend/src/store/useFactoryStore.ts`, `frontend/src/components/{ControlPanel,EnterprisePage,HOTLInput}.tsx`, `frontend/src/factory/DecisionJarvisDock.tsx`, 이 현황판 · 검증 증거 = 번들 검사 양방향 확인(개발 빌드 잡음 / same-origin 통과) · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = WEB-4 또는 M0-3 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 운영 원장에 승인 사건 생성

### [G2-M0-CALC-20260823-15] M0-4 경로 계산 화면 — 프런트가 온톨로지를 한 번도 부르지 않았다
- 작성자 / 기록 시각: Claude Code / 2026-08-23 KST
- 왜 지금 기록하는가: 계산기·승인·준비도는 다 있었는데 **계산을 돌릴 화면이 없었다.** 프런트 전체에서 `/api/v1/ontology` 호출이 **0건**이었다 — 「코어가 있는 것」과 「제품이 호출하는 것」의 차이가 화면 층에도 그대로 있었다.
- 상태: **경로 계산 화면 완료 · 실측 종단 통과(질문 → 경로 선택 → 가정 → 계산 → 지표)**
- 결정 및 근거:
  - **시작점을 고를 수 없어 새 목록 API 를 더했다**(`ontology_runtime.list_objects` + `GET /api/v1/ontology/objects`). 없으면 사용자가 `dataset:shipment:SHP-001` 을 손으로 쳐야 하고, 그것은 「개발자 도구 없이 완주」가 아니다.
    · 가시성은 `find_paths` 와 **같은 판정**(`_object_visible`)을 쓴다. 두 벌이면 목록에는 뜨는데 질의하면 빈 결과가 나오고, 사용자는 그것을 고장으로 읽는다. 회귀가 그 대칭을 고정한다.
    · 못 본 객체의 **수를 세어 주지 않는다** — 「권한 밖 1건」은 그 자체로 존재를 알려 준다.
  - **⚠️ 실측에서 404 로 막혔다 — 경로가 여럿인데 고를 자리가 없었다.** 서버는 「`path_fingerprint` 로 하나를 고르십시오」라고 답하는데 화면에 그 자리가 없었다. **찾기와 계산을 나눴다**: 영향 질의로 경로를 보여 주고(노드 사슬 + 구간 수), 사람이 고른 뒤 계산한다. 하나뿐이면 자동 선택한다.
  - **⚠️ 그다음 막힌 곳이 「명시해야 하는 가정」이었다.** 계산기가 `reserved_quantity_zero` 기본값을 거부한다 — 조용히 0으로 채우면 「예약 없음」과 「자료 없음」이 같아지기 때문이다. 그래서 화면에 **체크박스 + 거부하는 이유**를 함께 뒀다. 이유 없이 체크박스만 두면 사람은 그냥 켠다.
  - **막힌 것을 «영향 없음» 으로 그리지 않는다.** `BLOCKED` 면 수치 칸을 **아예 두지 않고** 사유를 두 층(대외 문구 + 무엇이 없는가)으로 놓는다.
  - **⚠️ 빈 지표를 빈 표로 그렸다가 고쳤다.** 머리말만 남으면 「0」으로 읽힌다 — 「해당하는 행이 없다」와 「값이 0이다」는 다른 답이다.
- 실측 결과(격리 서버 8082, 운영 `data/` 미접촉):
  - 시작점 4개 → 경로 3개(구간 1·2·3) → 3구간 경로로 계산 → `available_quantity RM-CU-CONC -4073.025` · `producible_quantity 0` · `revenue_shift_days 30` · `in_transit_quantity` 해당 행 없음.
  - **이 숫자들이 앞서 보고한 정본 자료 결함 두 건을 그대로 드러낸다** — 재고 음수와 생산가능량 0. 화면이 감추지 않는다.
  - 승인 전에는 같은 화면이 `IMPLEMENTED_UNAPPROVED` 사유를 그대로 보여 준다.
- 영향·주의사항:
  - 새 내비 항목 「경로 계산」(데이터 기반 그룹).
  - `GET /api/v1/ontology/objects` 는 권한 표에 넣지 않았다 — 조회이고 `assert_identified` + `app_policy` 가 막는다(형제 `query/impact` 와 같은 취급).
  - **[G5] 계산 결과 → 안건까지 이었다.** 기준선은 **계산이 읽은 그 판**으로 고정한다 — 다시 고르게 하면 「위쪽 숫자와 아래쪽 안건이 다른 자료를 본다」가 된다. 경영 수치는 기존 `BaseValueFields`(고른 판에서 채우기 포함)를 재사용하고, 빈 칸을 0으로 보내지 않는다. 실측에서 안건이 만들어지고 **계산 결속 결과 지문이 근거에 봉인된 것**이 화면에 보인다.
- 다음 행동 / 담당 / 착수 조건: **계산 결과 → 안건 화면**(기존 `BaseValueFields`·`BaselinePicker` 재사용) · 그 뒤 **M0-6 NCP 배포 패키징** · 3회 리허설.
- 교대 체크포인트: 마지막 확인 상태 = 관련 5스위트 127건 통과 · `tsc -b --force` 통과 · 화면 실측 완료 · 변경 범위 = `core/ontology_runtime.py`, `api/routes/ontology_control.py`, `frontend/src/lib/calculationApi.ts`, `frontend/src/components/PathCalcPanel.tsx`(신규), `frontend/src/App.tsx`, `tests/test_ontology_control.py`, 이 현황판 · 검증 증거 = 목록 가시성 변이 3/3 포착 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 안건 화면 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 운영 원장에 승인 사건 생성

### [G2-M0-CALC-20260822-14] 화면까지 — 눌러 봤더니 승인 범위가 자료와 어긋났다
- 작성자 / 기록 시각: Claude Code / 2026-08-22 KST
- 왜 지금 기록하는가: 사용자 지시로 **화면도 내가** 만들었다. 그리고 실제로 눌러 보니 **문서로만 알던 범위 불일치가 재현**됐다 — 기본값대로 승인하면 그 승인이 시연 자료에 걸리지 않는다.
- 상태: **승인·초기화 화면 완료 · 실측 종단 확인 · 실제 승인은 사용자**
- 결정 및 근거:
  - **한 화면 세 탭**(`frontend/src/components/CalcApprovalPanel.tsx`) — 준비 상태 / 실행 승인 / 시연 초기화. 셋 다 같은 인스턴스를 대상으로 하는 시스템 관리자 작업이라 하나로 묶었다.
  - **화면이 판정하지 않는다.** 서버가 준 상태·사유·다음 행동·`notice` 를 그대로 옮긴다. 지문도 화면이 만들지 않고 **받은 값을 되돌려 준다** — 그것이 「내가 본 것과 지금 승인되는 것이 같은가」를 서버가 확인하는 방법이다.
  - **셋을 갈라 그린다**: 준비됨(●) / 아직 안 함(◐) / **확인하지 못함**(⚠) / 판정 안 함(○). 색만으로 구분하지 않고 이름표와 기호를 함께 단다. 「판정 안 함」은 남은 일로 세지 않는다고 화면이 직접 말한다.
  - **⚠️⚠️ 실측으로 드러난 것 — 승인 범위 불일치.** 제안서 기본값 `DEMO/SYNTHETIC · VIRTUAL · 30일` 로 승인하면 원장에 3건이 정상으로 남는데 **준비도는 계속 「아직 안 함」**이었다. 인스턴스가 `REAL` 이라 결속 지문이 달랐기 때문이다. 문서로 적어 둔 경고가 실제로 그렇게 동작했다.
    · 그래서 화면에 **범위 선택기**(자료 성격·실행 모드·유효기간)를 넣었고, 범위가 인스턴스와 다르면 **누르기 전에** 붉은 배너로 말한다. `REAL` 로 맞춰 승인하니 관문 5개가 전부 섰다.
  - **`window.prompt` 를 쓰지 않는다**(§12). 철회 사유는 인라인 입력으로 받는다 — 처음에 prompt 로 만들었다가 규칙에 걸려 고쳤다.
  - **⚠️ 훅 경고가 진짜 결함을 가리켰다.** `react-hooks/set-state-in-effect` 를 보고 들여다보니, 탭·인스턴스를 빠르게 바꾸면 **늦게 온 응답이 새 상태를 덮었다.** 요청 일련번호로 취소를 넣었다 — 화면은 멀쩡해 보이고 사용자는 그것이 자기가 고른 대상이라고 믿는 유형이다.
- 실측 방법(재현 가능):
  - **운영 `data/` 를 건드리지 않았다.** `tmp/verify_calc_server.py` 가 시험과 같은 방식으로 싱글턴 `db_path` 를 tmp 로 갈아끼우고 정본 키트를 심은 뒤 8082 에 띄운다. 확인 후 격리 디렉터리를 버린다.
  - 로그인 게이트는 실제 세션을 요구하고 **비밀번호를 입력할 수 없어**, 임시 진입점으로 패널만 띄워 확인하고 지웠다.
  - Browser 패널이 안 보여 `computer{screenshot}` 이 실패했다 → playwright 헤드리스로 캡처(`tmp/shot_calc.py`, 기존 `scripts/capture_screens.py` 와 같은 방식).
  - 확인한 것: 인스턴스 목록 → 준비도 5관문 → 제안서(정의·단위·부호·필요자료·정본규칙·지문) → 사유 없이 비활성 → 승인 3건 **별도 원장 사건** → 범위 맞춘 뒤 「모든 관문이 섰습니다」 → 인라인 철회 → 준비도 되돌아감 → 초기화 계획/실행.
  - **초기화 실측 증거**: `deleted.decision_cases=2 · publications=1 · preview=yes`, `retained 1/1`, **`fingerprint.before == fingerprint.after`**(유지 대상 무변동), `ledger.before=11 → after=12`(늘기만 함).
- 영향·주의사항:
  - 새 내비 항목 「계산 실행 승인 · 시연 초기화」(운영과 검증 그룹). 화면에서 숨기는 것은 편의이고 **막는 것은 서버**다(`route_authority` 의 `ADMIN_SECURITY`).
  - **⚠️ 사용자 결정 필요**: 승인 범위를 `VIRTUAL` 로 유지하려면 시연 인스턴스를 `VIRTUAL` 로 만들어야 하고, 지금 자료 그대로 가려면 `REAL` 로 승인해야 한다. 화면은 둘 다 고를 수 있게 해 두었다.
  - `tmp/` 의 검증 스크립트는 추적되지 않는다. 제품 경로가 아니다.
- 다음 행동 / 담당 / 착수 조건: **[사용자] 범위 결정 + 실제 승인** · **[Claude Code] M0-6 NCP 배포 패키징** · **[Codex/Claude Code] M0-4 나머지 화면 폐루프** · 그 뒤 3회 리허설.
- 교대 체크포인트: 마지막 확인 상태 = T2 전체 4,846건 통과 · 프런트 `tsc -b --force` 통과 · 화면 실측 완료 · 변경 범위 = `core/demo_reset.py`(신규), `core/decision_ledger.py`, `core/route_authority.py`, `api/routes/calculation_control.py`, `frontend/src/lib/calculationApi.ts`(신규), `frontend/src/components/CalcApprovalPanel.tsx`(신규), `frontend/src/App.tsx`, `tests/test_calculation_api.py`, 이 현황판 · 검증 증거 = 초기화 치명 분기 변이 11/11 포착 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-6 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, **운영 원장에 승인 사건 생성**, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260822-13] M0-5 시연 초기화 — 지우는 일도 기록으로 남는다
- 작성자 / 기록 시각: Claude Code / 2026-08-22 KST
- 왜 지금 기록하는가: 사용자가 고정한 범위(실행 결과만 되돌리고 정본·통제는 유지)를 구현했다. 그리고 **재확인 지문을 두 번 잘못 잡았다** — 그 두 실수가 남을 만하다.
- 상태: **초기화 API 완료 · 화면은 Codex · 3회 리허설은 화면 뒤**
- 결정 및 근거:
  - **「DEMO/SYNTHETIC 환경」 판정은 등록부의 키트 모드**(`kit_registry_versions.mode`)다. 호출자가 보내는 값이 아니다 — 보내게 두면 「데모라고 적어 보낸 요청」이 운영 자료를 지운다. 등록부를 **못 읽으면 거부**한다(「모르니까 데모겠지」는 그 자체로 문이다).
    · ⚠️ `entity_mode` 를 데모 표지로 쓰지 않았다. 이 저장소의 시연 인스턴스는 `REAL` 문맥에서 돈다 — 그걸로 가르면 시연이 막히거나, 더 나쁘게는 운영 `REAL` 인스턴스가 데모로 오인된다.
  - **「비활성·보관」을 상태 변경으로 구현하지 않았다.** 발간된 브리핑을 `WITHDRAWN` 으로 바꾸는 것은 **대외 상태 변경**이고 초기화가 할 일이 아니다 — 회수는 사람이 사유를 달아 하는 별개의 결정이다. 대신 **경계**를 남긴다(초기화 시각 + 원장 사건). 아무것도 바뀌지 않았고 아무것도 사라지지 않았으며 다음 리허설은 깨끗하다.
  - **계획과 실행을 갈랐다.** `GET /reset/plan` 은 부작용이 없고, `POST /reset` 은 그 계획의 지문을 요구한다 — **계획을 보지 않고는 지울 수 없다.** 그리고 실행은 계획한 **그 id 들만** 지운다(조건을 다시 쓰면 사람이 확인한 목록과 실제로 지워지는 것이 갈린다).
  - **⚠️ 재확인 지문을 두 번 잘못 잡았다.**
    1. **전후 지문에 원장 건수를 넣었다** — 초기화 자체가 사건을 남기므로 전후가 **절대** 같을 수 없었다. 원장에 대해 지켜야 할 성질은 「같다」가 아니라 **「줄지 않았다」**이고, 그것은 지문이 아니라 건수로 본다. 줄었으면 즉시 실패로 답한다(경보선).
    2. **계획 지문에 유지 대상 건수를 넣었다** — 거기 원장 건수가 들어 있어서 **무관한 원장 쓰기 하나만 있어도 확인이 무효**가 됐다. 재확인은 「내가 본 삭제 목록이 그대로인가」를 물어야지 「그 사이에 시스템에 아무 일도 없었는가」를 물으면 안 된다. 뒤엣것은 절대 만족되지 않고, 그러면 사람은 **지문을 복사해 넣는 법을 배운다.**
  - **⚠️ 변이 0건 두 자리 — 원인이 달랐다.**
    · 「얼린·승인된 가정도 삭제」 → **도달 못 함.** 시나리오 행을 심는 시험이 없었다. 회귀를 추가하니 잡혔다.
    · 「원장 감소 감지 제거」 → **도달 못 함(경보선).** 실제로는 울릴 일이 없는 분기다. 강제로 울려 보는 시험을 넣었다 — 울리지 않는 경보선은 없는 것과 같다.
  - **시험이 운영 파일을 지울 뻔했다.** 초기화 시험은 시나리오·협업·Preview 저장소를 **전부 격리**해야 한다(`isolated_side_stores`). 이 저장소의 「운영 DB 쓰기 탐침 금지」가 정확히 이 자리를 가리킨다.
- 영향·주의사항:
  - 원장에 유형 3종·주체 1종이 늘었다(`DEMO_RESET_REQUESTED`/`COMPLETED`/`FAILED`, `demo_reset`). 사실은 `payload` 칸이 없어 **`evidence_refs` 에 문자열로** 싣는다 — 사유에 섞지 않는다(사유는 사람이 쓴 문장이고, 문구를 다듬을 때 기록이 조용히 바뀐다).
  - **전체 정본 재생성은 Reset 에 없다.** 지시대로 별도 운영 명령으로 남긴다.
  - `scenario_entities`(조직 복제)는 건드리지 않는다 — 조직 정보에 가깝다.
  - **⚠️ 3회 리허설 재현성**은 계산 결과 지문으로 확인했다(초기화 뒤 같은 요청이 같은 `result_fingerprint`). **화면을 통한 재현은 아직이다** — M0-4 뒤에 해야 한다.
- 다음 행동 / 담당 / 착수 조건: **[Codex] 초기화 화면**(계획 목록 → 사유 입력 → 재확인 → 실행, `plan_fingerprint` 를 반드시 실어 보낼 것) · **[Codex] 승인 화면**(앞 항목 계약) · **[사용자] 실제 승인** · **[Claude Code] M0-6 NCP 배포 패키징**(화면과 병렬 가능).
- 교대 체크포인트: 마지막 확인 상태 = T2 전체 스위트 통과 · 변경 범위 = `core/demo_reset.py`(신규), `core/decision_ledger.py`, `core/route_authority.py`, `api/routes/calculation_control.py`, `tests/test_calculation_api.py`, 이 현황판 · 검증 증거 = 초기화 치명 분기 변이 9/9 포착(0건 2자리는 둘 다 「도달 못 함」으로 판정·회귀 추가) · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-6 배포 패키징 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 사건 생성·등록부 상태 변경, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260822-12] M0-0 승인 **경로만** 만들었다 — 누르는 것은 사람이다
- 작성자 / 기록 시각: Claude Code / 2026-08-22 KST
- 왜 지금 기록하는가: 사용자 결정 「2번 — 승인 경로만 구현하고 상태 변경이나 승인 사건 생성은 하지 말 것」에 따른 구현이다. **등록부는 여전히 `IMPLEMENTED_UNAPPROVED` 이고, 원장에 승인 사건은 하나도 만들지 않았다.** 그리고 승인의 뜻을 「이 산식」에서 **「이 산식을 이 조건에서」**로 바꿨다.
- 상태: **승인 API 완료 · 승인 화면은 Codex · 실제 승인은 사용자**
- 결정 및 근거:
  - **승인 대상이 결속 지문이 됐다**(`core/calc_execution_approval.py`). 산식 정체성 하나만 대상으로 삼으면 판·범위·코드가 바뀌어도 승인이 산다. 묶는 것: 산식 정체성·판 · 단위·부호 방향 · 필수 계약키 · **인증판 집합** · 코드 지문 · 정본 규칙(BOM·날짜) · 실행 범위(data_kind·entity_mode·tenant·scope). 하나라도 바뀌면 지문이 바뀌고 **승인이 자동으로 죽는다.**
    · 유효기간은 지문에 **넣지 않는다** — 「언제까지」는 「무엇을」이 아니고, 넣으면 같은 조건의 재승인이 다른 대상이 되어 멱등을 잃는다.
  - **되돌리기가 기본값이다.** 등록부 상수를 고치지 않는다. 승인은 저장소 기록 + 원장 사건이고, 기록이 사라지면 자동으로 `IMPLEMENTED_UNAPPROVED` 로 돌아간다. 상수를 고쳤다면 프로세스 전체·모든 테넌트에 걸렸을 것이고, 그때는 「이 조직에서 승인됐다」와 「어디서나 승인됐다」가 같은 말이 된다.
  - **승인을 만드는 곳을 하나로 줄였다.** `path_calculation_service.approve_capability()` 를 **지웠다** — 둘이면 하나는 반드시 옛 대상으로 남고, 그 승인은 무엇이 바뀌어도 살아남는다. `capability_subject()` 는 `NotImplementedError` 로 남겼다(원장에 남은 옛 사건이 **왜 이제 무효인지** 코드가 말할 수 있어야 한다).
  - **승인 확인도 한 벌이다.** `capability_verifier` 가 원장 대조를 다시 만들지 않고 `cea.active()` 를 부른다. 해석기(관문 3 앞)와 검증기(실행 직전)가 **같은 함수를 두 시점에** 적용한다 — 그 사이에 철회될 수 있고, 철회 후 재승인이면 **다른 승인**이므로 사건 id 까지 대조한다.
  - **권한은 `ADMIN_SECURITY`(시스템 관리자) 하나.** 새 이름을 지어내지 않았다 — 이 상수는 플랫폼 관리자(`is_admin`)에게만 가고 데이터·AI 관리자·부서 역할 어디에도 없다(`_DATA_ADMIN_CAPS`·`_AI_ADMIN_CAPS`·`_ROLE_CAPS` 가 보증). M1 에서 `CALC_APPROVE`·`DEMO_RESET` 으로 갈라 낼 수 있다.
  - **⚠️ 변이 0건 한 자리 — 앞 관문이 가렸다.** 라우트 안에 `require_caps` 를 한 줄 더 두었는데 라우터 표가 먼저 막아 **도달하지 않았다.** 두 겹을 한 겹으로 줄이고 그 자리에 사유를 적었다 — 도달 불가한 통제를 두면 나중에 「여기서 막으니 괜찮다」고 믿고 표에서 빼게 된다.
  - **시험에서 `cc.get` 패치를 걷어냈다.** 앞 판은 등록부를 갈아 끼워 「승인됐다면 어떻게 되는가」를 봤을 뿐, 대상 지문·유효기간·범위 결속은 하나도 검사되지 않았다. 이제 격리 환경에서 **실제 승인 경로**가 돈다.
  - **`route_authority` 표 대조가 읽기 라우트를 유령으로 잡았다.** 표는 읽기도 막을 수 있는데(관리자 화면 조회) 대조가 쓰기 목록만 봤다 — `_all_routes()` 로 고쳤다.
- 영향·주의사항:
  - **아무것도 승인되지 않았다.** `GET /api/v1/calculation/capabilities` 는 부작용 없는 제안서이고, 누르기 전까지 계산은 계속 `BLOCKED` 로 답한다.
  - 저장소에 표 하나가 는다(`calc_execution_approvals`). 같은 결속의 살아 있는 승인은 **하나뿐**임을 부분 UNIQUE 인덱스가 함께 지킨다.
  - `pc.calculate` 에 `capability_resolver` 주입이 생겼다. 안 넘기면 등록부 그대로 — 「안 넘겼으니 통과」로 접지 않는다.
  - **⚠️ 범위 불일치**: 사용자가 정한 승인 범위는 `entity_mode=VIRTUAL` 인데 지금 시연 인스턴스는 **`REAL`** 로 만들어져 있다(`demo_vertical_slice`). 제안서 기본값은 지시대로 `VIRTUAL` 이지만, 그대로 승인하면 **지금 시연 자료로는 계산이 돌지 않는다.** 화면에서 범위를 고르게 했다.
  - **⚠️ 남은 M1 부채**: RC 폐기 시점 자동 감지가 없다(유효기간만 있다). 그리고 봉인 판이 「관계 승인 때 봉인한 판」이 아니라 「지금 최신 인증판」이다.
- 다음 행동 / 담당 / 착수 조건:
  - **[Codex] 승인 화면** — 계약은 아래 그대로다.
    · `GET /api/v1/calculation/capabilities?instance_id=&data_kind=&entity_mode=&valid_days=` → `{scope, valid_days, valid_until, items[], approvals[], notice}`
    · `items[]` 각 항목: `ref` · `state` · `blocked_reason` · `definition{relation, model_version, outputs[{metric, unit, unit_display, direction}], required_datasets, canonical_rules}` · `binding` · `binding_fingerprint` · `approvable` · `missing_contract_keys`
    · 화면은 **`notice` 를 그대로** 보여 준다(「누르기 전까지 계산은 BLOCKED」).
    · 기본 범위 `DEMO/SYNTHETIC · VIRTUAL · 30일`. 셋을 일괄 선택할 수 있으나 **사유는 필수**다.
    · 누를 때 `POST /api/v1/calculation/capabilities/approve` 에 `{instance_id, refs[], rationale, data_kind, entity_mode, valid_days, seen_fingerprints{ref: binding_fingerprint}}`. **`seen_fingerprints` 를 반드시 실어 보낼 것** — 사람이 읽고 누르는 사이에 판이 바뀌면 409 로 되돌려 다시 읽게 한다.
    · 철회 `POST /api/v1/calculation/capabilities/{approval_id}/revoke` `{reason}`. 사유 필수.
    · 시스템 관리자가 아니면 403 — 화면에서 숨기되 **숨김을 통제로 믿지 말 것**(서버가 막는다).
  - **[사용자] 실제 승인** — 제가 상태를 올리지 않습니다.
  - **[Claude Code] 시연 Reset** — 범위 확정됨(실행 결과만 초기화, 정본·통제·원장 유지). 승인과 **다른 커밋**으로 갑니다.
- 교대 체크포인트: 마지막 확인 상태 = T2 전체 스위트 **4,833건 통과·1건 건너뜀** · 변경 범위 = `core/calc_execution_approval.py`(신규), `core/calc_capability.py`, `core/path_calculation.py`, `core/path_calculation_service.py`, `core/ontology_path_adapter.py`, `core/demo_readiness.py`, `core/data_preparation/store.py`, `core/route_authority.py`, `api/routes/calculation_control.py`, `tests/test_calc_real_approval.py`, `tests/test_calculation_api.py`, `tests/test_route_authority_table.py`, 이 현황판 · 검증 증거 = 치명 분기 변이 11/11 포착(0건 1자리는 앞 관문 가림으로 판정·통제를 한 겹으로 축소) · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 시연 Reset · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, **승인 사건 생성·등록부 상태 변경**, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260822-11] B2→G5 제품 배선 — 시험만 부르던 계산에 문이 생겼다
- 작성자 / 기록 시각: Claude Code / 2026-08-22 KST
- 왜 지금 기록하는가: 라우트를 처음 돌린 순간 **모든 계산이 막혔다.** 원인이 통제 결함이었고, 그것을 **시험이 계약으로 굳혀** 두고 있었다. 「코어가 있는 것」과 「제품이 호출하는 것」의 차이가 이번에도 결함을 드러냈다.
- 상태: **B2→G5 배선 완료 · 제품 등록부는 계속 `IMPLEMENTED_UNAPPROVED`**
- 결정 및 근거:
  - **`POST /api/v1/calculation/path` · `/path/decision` 을 열었다**(`api/routes/calculation_control.py`). 설계의 전부는 **받지 않는 것**이다 — 승인·봉인 판·기준선·`path_model_version`·문맥 전부 서버가 파생한다. 호출자가 주는 것은 질문(roots·target_types·as_of·instance_id·가정)뿐이다.
    · **관계 목록은 경로의 간선에서 나온다.** 호출자가 적어 보내게 두면 **빈 목록**을 보낼 수 있고, 그러면 대조할 승인이 없어져 관문이 통째로 빈다.
    · **문맥은 인스턴스 행에서 읽는다.** 남의 조직 값을 함께 적어 보내면 봉인 대조가 **자기일관**해진다 — 대조는 불일치를 막지 허가를 주지 않는다. 인스턴스 가시성은 `_instance_or_404` **한 벌**을 쓴다.
  - **⚠️⚠️ P0 — 요청자를 승인자 자리에 넣고 있었다.** `relation_verifier(actor)` 가 계산 요청자를 `product_approval_resolver` 의 `actor` 로 넘겼고, 그 판정기의 ④ 는 「승인 사건의 행위자가 이 사람인가」를 본다. 결과: **관계를 직접 승인한 사람만 계산할 수 있었다.**
    · **왜 안 잡혔나**: 앞 시험이 승인자와 요청자를 **같은 문자열**로 두었다. 배역이 같으면 두 질문의 차이가 사라진다. 게다가 시험 하나가 그 결함을 「다른 사람의 관계 승인은 인정되지 않는다」라는 **이름으로 고정**하고 있었다.
    · **같은 판단이 옆 함수에는 이미 적혀 있었다** — `capability_verifier` 머리말이 「④를 넣지 않는 이유: 섞으면 승인자 본인만 계산할 수 있게 된다」고 적어 두었다. 두 함수가 반대로 하고 있었다.
  - **④ 를 뺀 자리를 무엇이 대신하는가 — 감추지 않고 적었다.** 이전 판은 관계 id 로 원장을 **뒤졌다**. 그러면 그 관계를 언급하는 아무 살아 있는 승인이나 근거가 된다. 이제 **온톨로지가 승인 때 관계에 묶어 둔 사건**(`ledger_correlation_id`)만 본다 — 뒤지지 않는다.
    · 그 결속은 `ontology_path_adapter.relation_bindings()` **전용 접근자**로 뺀다. `to_evidence()` 에 싣지 않는다 — 대외 근거에 구간 목록을 담지 않는 규약이 있고(`test_ontology_path_adapter` 가 `"segments" not in out` 으로 지킨다), 처음에 그 규약을 어겼다가 회귀에 걸렸다.
  - **[G5] 안건의 경영 수치는 계산기가 내지 않는다.** 경로 계산은 부족량·생산가능량·매출 이연 같은 **지표**를 내고, 3관점 검토서는 `calc_graph` 의 다섯 값으로 짜여 있다 — 다른 집합이다. 지표 합계를 「영업이익」 칸에 넣는 것은 **숫자를 지어내는 것**이라, 시뮬레이션 입력은 기존 결정 라우트와 같은 모양으로 받고 계산은 **근거로 묶는다**(M0-G5-01 이 요구한 「B2 계산 결과와 경로·Snapshot 봉인」이 그것이다).
  - **실패를 셋으로 가른다.** 장애 503(인증판 체크섬 불일치·온톨로지 판독 실패) · 미승인 200+`BLOCKED`+사유 · 없는 경로 404. 그리고 **관계 미승인**과 **산식 미승인**을 섞지 않는다 — 전자는 경로가 아예 안 보이고(404), 후자는 경로 위에서 막힌다(BLOCKED). 사용자가 할 일이 다르다.
  - **변이 4/5 포착.** 0건 하나는 **진짜 등가**였다(빈 승인 사건 조기 반환 — 아래 검증기가 이미 거짓으로 답한다). 지우는 대신 「통제가 아니라 빠른 경로」라고 코드에 적었다.
- 영향·주의사항:
  - **`build_request` 시그니처가 또 바뀌었다** — `relation_ids` → `relation_bindings`(`{관계: 승인 사건}`).
  - `path_calculation` 결과에 `query_id`·`path_fingerprint`·`required_relation_ids`·`capability_fingerprints` 가 실린다(COMPLETE·BLOCKED 둘 다).
  - `decision_package.build(calculation=...)` 이 생겼고, 런타임 경로 + 숫자의 **전면 차단(B1.2-1b)이 해제**됐다. 푸는 유일한 근거는 계산기가 봉인한 결과이고, 대조는 ①COMPLETE ②경로 정체성 일치 ③결과 지문 존재 셋이다.
  - **⚠️ 발견하고 고치지 않은 것**: `baseline_control` 이 `_instance_or_404` 의 **두 번째 사본**을 들고 있다. 시험에서 문맥을 두 번 패치해야 했던 것이 그 증거다. M1 부채로 등록한다.
  - **⚠️ 남은 M1 부채**: 봉인 판이 「관계 승인 때 봉인한 판」이 아니라 **「지금 최신 인증판」**이다.
- 다음 행동 / 담당 / 착수 조건: **M0-4 화면 폐루프**(Codex) · **Reset/Readiness** · **NCP 도메인 배포** · **3회 리허설**. 그리고 **사람의 결정 대기**: 계산 능력 3종 실행 승인(`APPROVED`), 정본 자료 결함 2건(BOM 200행 불일치 · `RM-CU-CONC` 재고 2024-07부터 음수) 처리 방침.
- 교대 체크포인트: 마지막 확인 상태 = T2 전체 스위트 통과 · 변경 범위 = `api/routes/calculation_control.py`(신규), `core/path_calculation_service.py`, `core/path_calculation.py`, `core/ontology_path_adapter.py`, `core/decision_package.py`, `core/route_authority.py`, `main.py`, `tests/test_calculation_api.py`(신규), `tests/test_calc_real_approval.py`, `tests/test_ontology_path_adapter.py`, `tests/test_route_authority_table.py`, 이 현황판 · 검증 증거 = 치명 분기 변이 10/11 포착(0건 1자리는 등가로 판정·코드에 명시) · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-4 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260821-10] M0-3.2b — 배분·기준선을 봉인으로. 자기진술이 사라졌다
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: 앞 묶음까지 남아 있던 마지막 자기진술 넷(`sales_allocation`·`recognition_span_days`·`baseline_recognition`·`baseline_id`)을 닫았다. 그리고 **변이가 0건인 자리 세 곳**을 만나 셋 다 원인이 달랐다 — 그 구분이 남아야 한다.
- 상태: **M0-3.2 완료 · 제품 등록부는 계속 `IMPLEMENTED_UNAPPROVED`**
- 결정 및 근거:
  - **셋을 한 봉인으로 묶었다**(`core/calc_baseline.py`). 따로 두면 「배분은 새 것, 인식 규칙은 옛 것」 같은 조합이 생기고, **그 조합은 아무도 승인한 적이 없다** — 매출 이연은 셋의 곱이다.
    · 저장소 `baseline_builds` 에 내용 + 지문, 원장 `CALC_BASELINE_SEALED` 가 **그 지문**을 승인한다(build_id 가 아니다 — id 를 대상으로 삼으면 내용을 고쳐도 승인이 산다).
    · `active()` 는 매번 ① 행 존재 ② 문맥 ③ **내용 지문 재계산** ④ 원장 사건 생존을 본다.
  - **호출자는 배분·기준선을 넣을 수 없다.** `build_request` 가 봉인에서 읽고, 겹치면 봉인이 이긴다. 봉인이 없으면 **요청을 만들지 않는다** — 빈 기준선으로 계산하면 모든 판매행이 `missing_baseline` 이 되고 그것이 화면에서 「영향 없음」으로 읽힌다.
  - **반쪽 봉인을 막는다.** 배분에 있는 판매행은 인식 기간·기준 인식일이 함께 있어야 한다. 반쪽으로 봉인하면 계산이 그 행을 `missing_baseline` 으로 답하는데, 그때는 **봉인 자체가 반쪽**이었던 것이다.
  - **⚠️ 변이 0건 세 자리 — 원인이 셋 다 달랐다.**
    1. **앞선 관문이 가렸다**: 「원장 철회 확인」을 지워도 안 잡혔다. `revoke()` 가 저장소 행도 내리므로 `status=ACTIVE` 조회에서 먼저 걸린다. → 판별력은 **부분 실패**(원장에는 철회, 행은 ACTIVE)에서 생긴다. 소유권 결속에서 이미 고친 모양이다.
    2. **뒤 관문이 가렸다**: 「옛 기준선을 내린다」를 지워도 안 잡혔다. `active()` 가 최신 하나만 뽑기 때문이다. → 「살아 있는 기준선은 하나뿐」을 직접 세는 회귀로 잡았다. 둘이 남으면 `created_at` 이 같은 순간에 어느 것이 뽑힐지 모른다.
    3. **진짜 등가였다**: 「호출자 가정에서 세 키를 지운다」는 덮어쓰기와 등가였다. → **통제를 한 겹으로 줄였다.** 두 겹으로 보이게 두면 어느 것이 실제로 막는지 알 수 없고, 하나를 지울 때 「다른 하나가 있으니 괜찮다」고 믿게 된다.
- 영향·주의사항:
  - **`build_request` 시그니처가 바뀌었다** — `baseline_id`·`baseline_fingerprint` 를 받지 않는다. 봉인에서 온다.
  - 원장에 유형 2종·주체 1종이 늘었다(`CALC_BASELINE_SEALED`/`REVOKED`, `calc_baseline`).
  - 기준선 봉인은 **사유가 필수**다. 새 봉인은 옛 것을 내린다.
  - **⚠️ 아직 남은 것(M1 부채)**: 봉인 판이 「관계 승인 때 봉인한 판」이 아니라 **「지금 최신 인증판」**이다. 승인 이후 올라온 판으로 계산하면서 옛 승인을 근거로 삼을 수 있다.
- 다음 행동 / 담당 / 착수 조건: **B2→G5 제품 배선** — 라우트 + 실제 Principal/PDP + 계산 결과→Decision Package→원장→브리핑. 지금 계산 층은 시험만 부른다(코어가 있는 것과 제품이 호출하는 것은 다르다). 담당 Claude Code.
- 교대 체크포인트: 마지막 확인 상태 = T2 11스위트 364건 통과 · 변경 범위 = `core/calc_baseline.py`(신규), `core/path_calculation_service.py`, `core/decision_ledger.py`, `tests/test_calc_real_approval.py`, 이 현황판 · 검증 증거 = 치명 분기 변이 8/8 포착(0건 3자리는 원인별로 회귀 추가·통제 단순화 후 포착), T2 364건, T3 1회 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = B2→G5 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260821-09] M0-3.2a — 승인 대역을 걷어냈다. 실제 원장으로 계산이 돈다
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: 앞 카나리의 「승인 → 계산」은 정확히는 **「승인 대역 → 계산」**이었다(`ledger_verifier=lambda cap: True`). 그리고 관계 승인 사건은 호출자가 적어 보낸 값이었다 — 이 저장소가 반복해서 지운 자기진술 패턴이다. 그 대역을 걷어냈다.
- 상태: **M0-3.2a 완료 · 제품 등록부는 계속 `IMPLEMENTED_UNAPPROVED`**
- 결정 및 근거:
  - **서버가 요청을 산출한다**(`core/path_calculation_service.py`). 호출자는 «무엇을 묻는가» 만 준다.
    · `relation_approvals` — **원장에서 찾는다.** 앞서는 호출자가 `{관계: 사건}` 을 적어 보냈고, 사건 id 를 아는 사람이면 아무 값이나 넣을 수 있었다.
    · `sealed_snapshots` — **저장소의 인증판에서 산출한다.** 호출자가 판 id 를 적으면 남의 판을 적을 수 있다.
  - **검증기는 제품의 것을 쓴다.** 관계 승인 판정은 `product_approval_resolver` 가 이미 한다(전용 이벤트 유형·대상 대조·행위자 대조·철회 확인) — 여기서 다시 만들면 두 벌이 되고, 그날 이 경로만 헐거워진다.
  - **계산 능력 실행 승인을 원장 사건으로** 만들었다(`CALC_CAPABILITY_APPROVED`/`REVOKED`, 주체 `calc_capability`). 「산식을 구현했다」와 「이 산식으로 계산해도 된다」는 다른 결정이고, 뒤엣것은 사람이 한다.
  - **⚠️ 순환을 하나 실측으로 잡았다.** 승인 대상을 `Capability.fingerprint()` 로 삼았더니, 승인을 남긴 뒤 상태를 `APPROVED` 로 올리는 순간 지문이 바뀌어 **승인이 스스로 죽었다**(그 지문은 `state`·`ledger_event_id` 까지 담는다). 승인이 물어야 하는 것은 「이 산식으로 계산해도 되는가」이므로, 대상 지문을 **산식 정체성만**(참조·산식 판·필요 계약키·출력)으로 분리했다.
  - **⚠️ 승인이 없는 관계를 목록에서 빼지 않는다.** 빼면 실행기의 「경로의 모든 관계가 승인됐는가」 검사가 집합이 줄어 통과해 버린다 — 검사를 무력화하는 길이다. 찾은 것만 돌려주고 실행기가 경로 집합과 대조한다.
  - **⚠️ 변이가 등가 하나를 드러냈다.** 「승인 사건 **유형** 검사 제거」가 잡히지 않았다 — 지문 대조가 뒤에서 걸렀기 때문이다. 판별력은 **같은 지문을 가진 철회 사건으로 승인을 주장**하는 경우에 생긴다(철회 사건의 대상 지문은 원 승인과 같다). 그 회귀를 추가하자 잡혔다 — 유형을 보지 않으면 **「이 산식은 철회됐다」가 「승인됐다」로 읽힌다.**
- 영향·주의사항:
  - **원장에 유형 2종·주체 1종이 늘었다**(`CALC_CAPABILITY_APPROVED`/`REVOKED`, `calc_capability`). 승인 건수를 세는 집계가 있으면 확인할 것.
  - `svc.run()` 은 **검증기를 인자로 받지 않는다.** 받으면 호출부가 대역을 넘길 수 있고, 그것이 방금 걷어낸 것이다.
  - 계산 능력 실행 승인은 **행위자를 대조하지 않는다**(관계 승인과 다르다). 「이 산식이 승인됐는가」를 묻는 것이지 「이 사람이 승인했는가」가 아니다 — 섞으면 승인자 본인만 계산할 수 있게 된다. 사유는 필수다.
  - **⚠️ 아직 자기진술로 남은 것**: `sales_allocation` · `recognition_span_days` · `baseline_recognition` · `baseline_id`/`baseline_fingerprint`. 회귀가 그 사실을 명시적으로 고정한다(`test_아직_자기진술인_값을_정직하게_남긴다`) — **닫히지 않은 것을 닫혔다고 말하지 않는다.**
  - 봉인 판은 「지금 최신 인증판」이다. 관계 승인 때 봉인한 판이 따로 있어야 하고, 그 자리는 M0-3.2b 다.
- 다음 행동 / 담당 / 착수 조건: **M0-3.2b** — 승인된 생산-판매 배분과 봉인된 기준선·인식 규칙을 저장소·원장 정본으로. 그 다음 **B2→G5 제품 배선**(라우트 + 실제 Principal/PDP + Decision Package + 브리핑). 담당 Claude Code.
- 교대 체크포인트: 마지막 확인 상태 = T2 12스위트 387건 통과 · 변경 범위 = `core/path_calculation_service.py`(신규), `core/decision_ledger.py`, `tests/test_calc_real_approval.py`(신규), 이 현황판 · 검증 증거 = 치명 분기 변이 4/4 포착(등가 1건은 판별력 있는 회귀 추가 후 포착), T2 387건, 대역 없는 종단 12건 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-3.2b · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기, 검증기 대역을 제품 경로에 넣기

### [G2-M0-CALC-20260821-08] M0-3.1 — 정본 스타터 키트로 카나리 재작성
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: 앞 카나리는 **시험용 키트를 임의 생성**하고 시연 자료를 **손으로 썼다.** 그 위에서 「정본 열을 썼다」고 보고했는데, 정본을 넣자 즉시 실패했다. 이번에 정본 키트·정본 CSV 로 바꾸면서 **정본 자료 자체의 결함 두 건**을 실측했다 — 그 사실이 남아야 한다.
- 상태: **M0-3.1 완료 · 실행 승인은 계속 보류(`IMPLEMENTED_UNAPPROVED`)**
- 결정 및 근거:
  - **정본은 문서가 아니라 파일이었다.** `starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/samples/full/*.csv` 가 실재한다. 스키마가 세 문서(온톨로지 계약·키트 스펙·등록 실행계획)에 조금씩 다르게 적혀 있어 어느 것도 정본으로 쓸 수 없었고, **실제 CSV 헤더**를 정본으로 삼았다.
  - **시드를 버리고 «정본에서 행만 골라낸다»**(`core/demo_vertical_slice.py`). 열 이름을 고를 여지가 없으므로 「fixture 가 계약을 대신 정의하는」 사고가 **구조적으로** 불가능해진다. 고르는 규칙은 코드로 적었다(손으로 행 번호를 적으면 자료가 바뀔 때 조용히 깨진다).
  - **정본을 넣어 보니 계약이 네 곳 어긋났다**(전부 실측):
    | 항목 | 내 가정 | 정본 |
    |---|---|---|
    | INV-01 기준시각 | `snapshot_at` | **`snapshot_date`** |
    | 날짜 값 | ISO+오프셋 | **날짜만**(`2023-08-31`) — 내 `_utc()` 가 전부 거부했다 |
    | 실제 출발 | `ATD` | **없음.** `BOOKED/PICKED_UP/ETD/ETA/ATA/UNLOADED` |
    | BOM 행 | 전부 소요 | `component_role` 에 `RETURN` 이 섞임 |
    → 날짜-only 는 **`DATE_ONLY_RULE`(그 날 00:00 UTC)** 로 명시했다. 규칙 없이 두면 비교하는 쪽이 추측하고, 그 추측은 서버 시간대에 따라 달라진다. → `LOG-03` 은 milestone 마다 `planned_at`·`actual_at` **쌍**을 가지므로, `ETD` 행의 `actual_at` 이 실제 출발이다(이름은 예정, 값은 실적). `planned_at` 은 쓰지 않는다 — 쓰면 「예정대로 떠났을 것」이 계산에 들어간다. → `RETURN` 을 소요로 세면 필요량이 부풀고 없는 부족이 생긴다.
  - **⚠️ 정본 자료 자체의 결함 두 건 — 내가 고칠 수 없다.**
    1. `MFG-01.material_requirement` 가 BOM 재계산과 **200건 전부** 어긋난다(예: 저장 137.78 vs 재계산 139.745). 계약 §7.2 대로 그대로 넣으면 `BLOCKED` 다 — **계약이 작동한 것이지 결함이 아니다.** 부분집합에서는 **BOM 정본으로 파생값을 복원**해 쓴다(하나를 고르는 것이 아니라 정본 규칙으로 다시 계산하는 것이다). **원본 파일은 고치지 않았다.**
    2. `INV-01` 의 `RM-CU-CONC` 원료 창고 재고가 2024-07 이후 **음수**다(25건, 최신 -4,539). 이것은 흘려보낸다 — 0 으로 접으면 「재고가 없다」와 「이미 모자라게 썼다」가 같은 값이 되고, 뒤엣것이 훨씬 급한 사실이다.
    ★ 그 결과 정본으로 계산하면 `producible_quantity` 가 0 이고 매출 이연이 30일이다. **이야기가 밋밋한 것이 아니라 자료가 그렇게 말하고 있다.** 시연 대본을 쓰려면 이 두 건을 먼저 정리해야 한다 — 그것은 자료 소유자의 결정이다.
  - **제품 경로에서 임의 키트 인증을 막았다.** `store.create_instance` 가 등록부(`kit_registry_versions`)에서 판본을 찾고 **지문까지 대조**한다. 없으면 거부한다. ⚠️ 이 강제가 실제로 작동해서 **기존 시험 11개 파일이 막혔다** — 전부 「키트를 등록한 뒤 그 지문으로」 쓰도록 고쳤다(지문은 손으로 적지 않고 등록 결과에서 읽는다).
  - **「읽을 수 없는 키트」 회귀를 현실적인 모양으로 바꿨다.** 앞 판은 처음부터 없는 이름을 적었는데 그 길은 이제 막힌다. 인스턴스를 만든 **뒤 판본을 폐기**하는 것으로 재현한다 — 키트 폐기는 실제로 일어나고, 그때 옛 인스턴스가 남는다.
- 영향·주의사항:
  - **`create_instance` 계약이 바뀌었다.** 등록되지 않은 키트·지문 불일치는 거부된다. 시드·시험·라우트가 임의 키트를 만들던 곳은 전부 등록을 거쳐야 한다.
  - `AS_OF` 를 **2026-06-01** 로 잡았다. 정본 자료의 시간축이 2023-08~2026-08 이라 오늘 날짜에는 미래 계획행이 0건이다(실측). ⚠️ 이 값을 바꾸면 부분집합과 결과 지문이 달라진다 — 시연 대본과 함께 고칠 것.
  - `core/demo_seed_vertical.py`(손으로 쓴 시드)는 **더 이상 카나리가 쓰지 않는다.** 아직 지우지 않았지만 정본 경로가 아니다.
- 다음 행동 / 담당 / 착수 조건: **M0-3.2 + B2→G5 를 한 묶음으로.** 서버가 실제 원장·저장소에서 `required_relation_ids`·관계 승인·`sales_allocation`·기준선을 산출하고, 실제 Principal·PDP·Decision Ledger 검증기를 태운다. 지금은 그 값들이 호출자 자기진술이고 검증기는 대역이다. 담당 Claude Code.
- 교대 체크포인트: 마지막 확인 상태 = T2 15스위트 484건 통과 · 변경 범위 = `core/demo_vertical_slice.py`(신규), `core/calc_models.py`, `core/calc_projection.py`, `core/data_preparation/store.py`, `tests/test_calc_canary.py`, 시험 9파일(키트 등록 경유), 이 현황판 · 검증 증거 = 치명 분기 변이 5/5 포착, T2 484건, T3 4,761 passed/1 skipped, 정본 자료 결함 2건 실측 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-3.2 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기, 정본 CSV 원본 수정

### [G2-M0-CALC-20260821-07] P0-CALC — 정본 투영·재고 배분·봉인 완전성
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: 교차감사가 **정본 데이터와 부정 경로를 직접 대입해** P0 세 묶음을 재현했다. 셋 다 내 눈으로 다시 재현한 뒤 닫았다. 특히 첫 번째는 **「집중 회귀 전부 초록인데 정본으로는 한 줄도 계산되지 않던」** 상태였고, 그 원인이 남아야 한다.
- 상태: **P0 3묶음 보정 완료 · 실행 승인은 계속 보류(`IMPLEMENTED_UNAPPROVED`)**
- 결정 및 근거:
  - **P0-CALC-INPUT — fixture 가 계약을 대신 정의하고 있었다.**
    계산 모델은 「계산의 말」로, 정본은 「업무의 말」로 적혀 있다. 앞 판은 그 사이에 아무것도 두지 않고 **계산 모델의 이름을 정본 이름인 것처럼** 썼다. 회귀 fixture 도 같은 말로 썼으므로 전부 초록이었고, 실제 CSV 를 넣자 `milestone_code` 누락으로 즉시 실패했다.
    → `core/calc_projection.py` 신설. 정본 열 ↔ 계산 열 대응을 **표 하나(FIELD_MAP)** 로 두고, 결합은 **승인된 관계 근거**로만 한다:
      · `LOG-02.po_line_id → PRC-02.po_line_id → material_id`(선적의 자재를 찾는 유일한 근거 — LOG-02 에 자재 ID 가 없다)
      · `production-plan-line -FULFILLS_SALES-> sales-line` 은 **승인된 allocation** 에서만 온다. 제품·기간이 같다고 이어 붙이면 그것은 추측이고, 매출 이연이 그 추측 위에 선다.
    → **결합이 끊긴 행을 빼지 않고 막는다.** 빼면 운송 중 수량이 조용히 줄고 그것은 「지연이 없다」로 읽힌다 — 한 줄을 빼는 것은 0 을 넣는 것과 같다.
    → 실행기의 필수 계약키에 **`PRC-02` 를 넣었다.** 계산 능력 등록부에는 없지만 투영에 필요하다 — 등록부만 믿으면 정본으로 계산되지 않는다.
    → **회귀 fixture 를 정본 열 이름으로 전부 바꿨다.** 이것이 이 묶음의 핵심이다.
  - **P0-CALC-ALLOC — 재고 100 으로 120 을 쓰겠다고 답했다.** 재현:
    ```
    재고 100 · 계획행 둘(각 필요 60) → PL-1 100, PL-2 100
    ```
    계획행마다 «전체 가용재고» 를 다시 썼다. → `priority → plan_date → plan_line_id` 결정론 순서로 배분하고 **쓴 만큼 차감**한다. 배분 내역(`allocation`)을 결과에 실어 「왜 내 계획행이 못 만드나」에 답할 수 있게 했다. `priority` 가 없으면 **뒤로** 보낸다(0 으로 두면 최우선이 되어, 안 적은 계획이 적은 계획을 앞지른다).
  - **P0-CALC-PROOF — 세 가지 위조가 통과했다.**
    · 관계 승인 하나만 제출 → COMPLETE: 승인 목록이 **비었는지만** 봤다. → 경로가 요구하는 관계 집합(`required_relation_ids`)과 **정확히 일치**해야 한다. 개수만 세면 다른 관계의 승인으로 맞출 수 있다.
    · 두 번째 행만 다른 Snapshot → COMPLETE: **첫 행만** 검사했다. → 모든 행을 보고, 섞이면 무결성 장애, 행이 0건이면 BLOCKED(자료가 없는 것은 장애가 아니다).
    · `path_model_version` 위조 → COMPLETE: 호출자 주장을 그대로 썼다. → 코드의 `PATH_MODEL_VERSION` 과 다르면 **거부**한다. 조용히 덮어쓰지 않는 이유는, 덮어쓰면 호출자가 다른 판을 요청한 줄 모른 채 다른 규칙의 답을 받기 때문이다.
- 영향·주의사항:
  - **`PathCalculationRequest` 에 `required_relation_ids` 가 늘었다.** 비어 있으면 계산하지 않는다 — 무엇을 승인해야 하는지 모르는 채로 승인 검사를 하는 것은 검사가 아니다.
  - **`assumptions` 에 `sales_allocation`·`recognition_span_days` 가 들어간다.** 둘 다 정본에 없는 값이고 **승인**에서 온다. 지문에 실리므로 값이 바뀌면 다른 질문이 된다.
  - 투영이 요구하는 정본 열이 하나라도 없으면 BLOCKED 다. 시연 데이터(M0-3)는 `FIELD_MAP` 의 열 이름을 그대로 써야 한다.
  - 계산은 **여전히 실행되지 않는다** — 실행 승인 보류가 유지된다.
- 다음 행동 / 담당 / 착수 조건: 감사 재확인 후 ① M0-3 인증 데이터 물질화(투영 계약에 맞춘 7종) ② 격리 환경 계산 종단 카나리 ③ 실행 승인 원장 사건 ④ B2→G5 배선 ⑤ 화면 폐루프. 담당 Claude Code(백엔드).
- 교대 체크포인트: 마지막 확인 상태 = T2 계산 영역 14스위트 493건 통과 · 변경 범위 = `core/calc_projection.py`(신규), `core/calc_models.py`, `core/path_calculation.py`, `tests/test_calc_models.py`, `tests/test_path_calculation.py`, 이 현황판 · 검증 증거 = 치명 분기 변이 7/7 포착, T2 493건, 감사 지적 3건 재현 확인 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-3 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기

### [G2-M0-CALC-20260821-06] M0-1·M0-2 — 계산 모델 3종과 경로 실행기(B2)
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: 감사·사용자 합의로 **완료 기준이 M0~M3 로 갈라졌고 우선순위가 바뀌었다.** 내부 통제의 모서리(saga·페이지네이션)를 앞세우던 방식을 멈추고, 임계경로 첫 칸인 **경영 계산**으로 옮겼다. 그 첫 두 묶음을 마쳤다.
- 상태: **M0-1·M0-2 구현 완료 · 승인 전(실행되지 않는다) · 화면 배선 미착수**
- 결정 및 근거:
  - **방식 전환 반영.** 결함은 `NOW / M1 / M2 / M3` 로 분류하고, 하위 단계 결함은 완료를 취소하지 않는다. T3 는 하루 1회, 변이는 **인증·테넌트·승인·금액·계산결속·데이터손실 분기만**. 이 묶음에서 변이는 6건만 돌렸다(전부 포착).
  - **⚠️ 감사 지시 두 건은 이미 끝나 있었다.** 「dangling 승인 범위 필터 + 원장 장애 503」과 「승인 재시도 멱등」은 `221c40e53`(4.1c-E)에 들어가 있다. 같은 커밋에 **M2 로 넘기라고 한 세 건**(원장 페이지네이션·보상 실패 saga·철회 부분 실패 재조정)도 함께 들어갔다 — 정확히 지적받은 과잉 구현이다. 이미 T3 를 통과했으므로 되돌리지 않고 **M2 부채를 미리 갚은 것으로 등록**한다.
  - **M0-1 계산 모델 3종**(`core/calc_models.py`) — 순수·결정론·저장소를 모른다.
    - `arrival_delay` — 운송 중 판정을 **실제 사건(ATD/ATA)** 으로 한다. 실측: `LOG-02.status` 는 120건 전부 `DELIVERED` 라 상태 열을 믿으면 지연이 0 으로 보인다.
    - `material_shortage` — **BOM 이 정본**(§7.2). 같은 자재의 BOM 행을 먼저 합산하고, 저장된 `material_requirement` 와 재계산값이 다르면 **하나를 고르지 않고 실패**한다(실측 66.4 vs 67.35).
    - `revenue_timing` — 실적(`delivery_delay_days`)과 시나리오(`revenue_shift_days`)를 **다른 함수**로 갈랐다(§7.3). 이름이 비슷하면 실수로 꽂히므로 반환 형태도 다르게 뒀다.
  - **⚠️ 구현 중 제 결함 두 건을 회귀가 잡았다.**
    - `revenue_timing` 이 생산 계획과 연결되지 않은 판매행에 **0 을 돌려줬다.** 0 은 「이동 없음」이고 그것은 「영향 없음」이다 — 이 파일 머리말에서 내가 금지한 결함을 같은 파일에 넣었다. `missing_baseline` 로 드러내도록 고쳤다.
    - `material_shortage` 의 생산 가능량이 **계획량을 넘었다**(계획 100 에 385). 재고가 넉넉하면 비율이 1 을 넘는데 상한이 없었다. 설비·인력·수요를 하나도 보지 않은 값이 「이만큼 더 만들 수 있다」로 읽힌다.
  - **M0-2 경로 실행기**(`core/path_calculation.py`) — 계약 §3·§5·§6 그대로. 관문 7개, 지문 2개, **부분 결과 금지**.
    - `request_fingerprint` 는 언제나, `result_fingerprint` 는 `COMPLETE` 일 때만(§3.7 — 수치 없는 결과 지문은 「계산된 결과」의 증거처럼 쓰인다).
    - 차단 사유를 **두 층**으로 낸다(§2.1) — 대외 사유에 구간 이름·건수·식별자를 넣지 않는다(「승인되지 않은 관계 3건」은 그 조직에 관계가 3건 있다는 뜻이다).
    - `BLOCKED`(아직 못 한다)와 **무결성 장애 503**(자료가 어긋났다)을 가른다. 정체성 결손과 봉인 판 불일치만 503 이다.
    - 실제로 쓴 참조의 지문만 넣는다(§3.5) — 범위 밖 `CALC.FINANCE…` 를 고쳐도 MVP 결과가 무효가 되지 않는다(회귀로 고정).
  - **등록부 3종을 `IMPLEMENTED_UNAPPROVED` 로** 올렸다. `APPROVED` 로 올리지 않는다 — **승인은 사람의 결정이고 원장 사건이 있어야 한다**(`__post_init__` 이 `ledger_event_id` 없는 `APPROVED` 를 거부한다). 등록부 판과 산식 판이 **같은지** 회귀로 고정했다(다르면 어느 쪽이 실제인지 알 수 없다).
- 영향·주의사항:
  - **지금은 계산이 실행되지 않는다.** 관문 3에서 멈춘다(계약 §6 이 예고한 그대로). 열리는 조건은 **의미 계약 승인 원장 사건**이고, 그것은 사용자 결정이다.
  - 「승인 전에는 경로 전체가 BLOCKED」 회귀가 **초록에서 빨강으로 바뀌는 날은 승인이 생긴 날**이어야 한다. 산식 구현만으로 열리면 검증 없는 숫자가 화면에 오른다.
  - 계산 모델은 **입력 계약을 정의**한다(열 이름 포함). 시연 데이터를 만들 때 그 계약에 맞춰야 한다 — 현재 `data_preparation.db` 는 색인 0행이므로 M0-3 이 그 자리다.
  - 필요 계약키 6종: `LOG-02`·`LOG-03`·`INV-01`·`MFG-01`·`MDM-05`·`SLS-01`. `LOG-03`·`MDM-05` 는 기존 9종 목록에 없던 것이고, 실측 근거로 계약에 추가된 것이다.
- 다음 행동 / 담당 / 착수 조건: ① **M0-0 의미 계약 승인**(사용자·감사자 결정 — 승인되면 원장 사건을 남기고 상태를 `APPROVED` 로) ② M0-3 시연 데이터·조직 결속 ③ B2→G5 배선(계산 결과를 안건·브리핑에 봉인) ④ M0-4 화면 폐루프(Codex). 담당 Claude Code(백엔드).
- 교대 체크포인트: 마지막 확인 상태 = T2 계산 영역 12스위트 407건 통과 · 변경 범위 = `core/calc_models.py`(신규), `core/path_calculation.py`(신규), `core/calc_capability.py`, `tests/test_calc_models.py`(신규), `tests/test_path_calculation.py`(신규), `tests/test_calc_capability.py`, 이 현황판 · 검증 증거 = 치명 분기 변이 6/6 포착, T2 407건, 결정론 3회 동일 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = M0-0 승인 대기 / M0-3 착수 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 승인 없이 `APPROVED` 로 올리기

### [G2-OWNBIND-20260821-05] 4.1c-E — 테넌트 누설·원장 장애 은폐·재시도 오염·분산 보상
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: `4b58273b7` 교차감사에서 P0 2건·P1 3건을 받았다. 다섯 건을 닫으면서 **감사 지적이 실제로 재현되는지 먼저 확인**했고, 그 과정에서 지적의 한 축(부서 범위)은 **누설이 아니라 조직도 설계**임을 실측으로 확인했다. 그 구분이 남아야 한다.
- 상태: **보정 완료 · 검증 대기(감사 재확인 필요) · 푸시 금지 유지**
- 결정 및 근거:
  - **P0-1 미물질화 승인이 테넌트를 넘었다(재현 확인).** `dangling_approvals()` 가 `tenant_id` 도 부서 범위도 받지 않고 원장 전체를 훑었다. 한 응답 안에서 **결속·격리는 걸러지고 이 목록만 안 걸러졌다.**
    → 범위 인자를 **필수 키워드**로 만들었다(기본값을 주면 호출부가 빠뜨려도 조용히 전체를 본다 — 그것이 방금 있었던 결함이다). 실제로 필수로 바꾸자 호출부 7곳이 즉시 드러났다.
    → 부서 필터 규칙을 `core.decision_ledger.visible_events` **하나로 정본화**하고 `api/routes/ledger_control._filter_by_dept` 를 그 위임으로 바꿨다. 규칙이 두 곳이면 새로 만드는 쪽이 언제나 느슨하게 태어난다 — 4.1c-B P0-4 에서 원장 철회 검증이 정확히 그렇게 갈렸다.
    - ⚠️ **다만 「A 조직 관리자가 B 조직을 본다」는 부서 축에서는 설계다.** 실측: `is_data_admin` 사용자의 `readable_dept_ids` 는 **전 부서**(`['dept_b','hq']`)다. 이 라우트는 `admin.data_access` 를 요구하므로 들어오는 사람은 거의 항상 전 부서를 읽는다 — 즉 라우트 안의 부서 필터는 **사실상 통과**한다. 실제로 막히는 것은 **테넌트 축**이고, 회귀도 그 축으로 세웠다. 조직도 규칙이 좁아지면 알려 주도록 「데이터 관리자는 전 부서를 본다」를 시험으로 못 박았다.
  - **P0-2 원장 최초 조회 장애가 「0건」으로 접혔다(재현 확인).** `list_events()` 는 판독 실패를 빈 배열로, 한도 초과를 부분 결과로 접는다. → `list_events_strict()` 를 만들어 **둘 다 던지게** 했다(한도보다 하나 더 읽어 절단을 판별한다). 앞 판은 경고만 찍고 부분 결과를 200 으로 돌려줬는데, **경고는 호출부가 그 값을 전체로 쓰는 것을 막지 못한다** — 실제로 그렇게 썼다.
  - **P1-3 재시도가 감사 이력을 오염시켰다(재현 확인).** 같은 요청을 두 번 하면 승인 사건이 둘이고, `declare()` 는 같은 지문 결속을 멱등으로 돌려주므로 **두 번째 사건은 어느 결속에도 연결되지 않는다.** → 라우트에 멱등 관문을 뒀다: 같은 문맥·계약·범위에 이미 유효한 결속이 있고 **부서·근거까지 같으면** 그것을 그대로 돌려준다(원장에 아무것도 더 쓰지 않는다). ⚠️ 부서나 근거가 다르면 돌려주지 않는다 — 그것은 개정이고, 조용히 덮으면 누가 언제 무엇을 바꿨는지 사라진다.
  - **P1-4 보상 실패가 상태코드에 드러나지 않았다.** 등록 실패(409)의 예외를 그대로 돌려줬다. 보상 취소까지 실패했다면 실제 상태는 **원장에 살아 있는 승인이 남은 것**이고, 그것은 사람이 정리해야 한다 → **503 + `repair_required`** 와 승인 사건 id 를 돌려준다. 409 는 「입력을 고쳐 다시 하라」로 읽힌다.
  - **P1-5 철회 원장 성공 + 정본 갱신 실패의 복구 경로가 없었다.** 권한 판정은 fail-closed 로 안전하지만 **두 화면이 다른 말을 한다**(목록에는 ACTIVE, 판정은 차단) — 그러면 운영자는 「왜 안 보이나」를 영원히 못 찾는다. → `ledger_mismatches()` 로 목록에 드러내고 `POST /ownership/{id}/reconcile` 로 고친다. **방향은 한쪽이다: 원장을 정본으로 표를 고친다.** 반대는 절대 하지 않는다 — 원장이 덮어쓸 수 없는 곳이어야 그 값이 있다.
  - **P1-7 목록과 격리 조회의 권한 정책을 일치시켰다.** 두 응답에 같은 종류의 정보가 들어 있고, 정책이 갈리면 느슨한 쪽이 우회 경로가 된다.
  - **변이 M47~M56 중 8건 포착 · 2건 등가(사유 코드 주석).**
    - 포착: 테넌트 필터 제거 · strict 미사용 · 절단 허용 · 부서 필터 제거 · 멱등 제거 · 멱등 과잉 · 보상 503 제거 · 불일치 미노출 · 재조정 무조건(총 9).
    - ⚠️ **판별력 없는 회귀 하나를 변이가 잡아냈다**: 재조정 회귀가 **이미 철회된** 결속에 두 번째 재조정을 시도했는데, 그 경로는 `status != ACTIVE` 에서 먼저 걸려 **원장 확인을 통째로 지워도** 실패가 0건이었다. 「살아 있고 어긋나지도 않은 결속」으로 바꾸자 잡혔다 — 원장 확인이 없으면 **정상 결속이 재조정으로 죽는다**(복구 도구가 파괴 도구가 된다).
    - 등가: 격리 조회의 `require_caps` 는 `assert_can_manage_standard` 와 겹친다(두 권한 축이 현재 조직도에서 동일). 남기는 이유(정책 선언의 가독성 + 축이 갈리는 날 감사 기록이 여기서 나온다)를 주석에 적었다.
- 영향·주의사항:
  - **`dangling_approvals()` 시그니처가 바뀌었다** — `tenant_id`·`entity_mode` 가 필수 키워드다. 범위 없이 부르는 코드는 이제 오류가 난다(의도된 것 — 조용히 전체를 보는 것보다 낫다).
  - **원장 조회 한도를 넘으면 예외**다. 미물질화 보고를 부르는 화면은 503 을 표시할 수 있어야 한다.
  - 같은 승인을 다시 눌러도 안전하다(`idempotent: true` 로 답한다). 다만 **부서·근거가 다르면 409** 이고, 기존 결속을 먼저 철회해야 한다.
  - `POST /ownership/{id}/reconcile` 이 늘었다. 어긋나지 않은 결속에 부르면 **409**(고칠 것이 없는데 고쳤다고 말하지 않는다).
- 다음 행동 / 담당 / 착수 조건: ① 소유권 승인·재조정 화면(Codex — 새 상태 `LEGACY_OWNERSHIP_QUARANTINED`, 새 응답 필드 `ledger_mismatches`·`idempotent`) ② FND-01 조직 정본 연동(HOLD) ③ 계산 결과 결속 B2. 담당 Claude Code(백엔드). **원격 복구 방침 확정 전까지 모든 푸시 HOLD.**
- 교대 체크포인트: 마지막 확인 상태 = T2 인접 15스위트 456건 통과 · 변경 범위 = `core/decision_ledger.py`, `core/data_preparation/ownership_binding.py`, `api/routes/data_preparation_control.py`, `api/routes/ledger_control.py`, `tests/test_ownership_api.py`, `tests/test_dataset_ownership_binding.py`, 이 현황판 · 미변경 = 타 팀원 작업분 · 검증 증거 = 변이 9/11 포착·2건 등가, T2 456건, T3 1회, 감사 지적 3건 재현 확인 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 감사 재확인 대기 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 파일 끝까지 자르는 문자열 편집

### [G2-OWNBIND-20260821-04] 4.1c-D — 승인·철회 API 경로. 「부를 수 없는 통제」를 닫는다
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: `4.1c-A~C` 로 소유권 결속의 통제는 전부 섰는데 **제품에서 그것을 부를 방법이 없었다.** 결속을 만들 수 있는 것은 시드·마이그레이션뿐이었고, 그래서 격리된 데이터를 **복구할 길도 없었다** — 마이그레이션이 데이터를 잠그고 열쇠를 만들지 않은 셈이었다. 시연 게이트 22판정이 「근거 없음」인 직접적인 이유다.
- 상태: **완료 · 검증 대기(감사 재확인 필요) · 푸시 금지 유지**
- 결정 및 근거:
  - **신규 라우트 4종**: `POST /ownership/approve` · `POST /ownership/{binding_id}/revoke` · `GET /ownership` · (기존) `GET /ownership/quarantine`.
  - **승인은 두 단계를 한 요청으로 묶는다.** 승인은 원장 사건, 결속은 정본 표 — 다른 저장소라 한 트랜잭션으로 묶을 수 없다. ① `approve()` → ② `declare()` → ③ **②가 실패하면 `abandon()` 으로 ①을 취소**한다. ③이 없으면 원장에 「승인」만 남고, 원장만 읽는 감사자에게는 승인된 것으로 보인다(권한은 새지 않지만 이력이 거짓이 된다). ③도 실패하면 요청을 실패로 답하고 그 건은 `dangling_approvals()` 보고에 남는다 — 조용히 성공으로 돌리지 않는다.
  - **⚠️ 권한 축을 잘못 골랐다가 실측으로 잡았다.** 처음에 `PROJECT_RUN` 을 요구했는데 축이 반대로 어긋났다: 데이터 관리자는 그 권한이 **없어서 정작 승인해야 할 사람이 403** 이었고, 프로젝트 `member` 는 그것을 **갖고 있어 전사 데이터 소유권을 정할 수 있었다.** 소유권 결속은 프로젝트를 돌리는 일이 아니라 기준정보를 정하는 일이므로 `ADMIN_DATA_ACCESS` 로 바꿨다.
  - **⚠️ 가짜 `AccessScope` 를 손으로 만들다가 스스로 걸렀다.** 4.1c-B P1-1 에서 지적받은 바로 그 패턴이다. 실제 `org.resolve_scope()` 로 바꿨고, 그 덕에 `readable_scope_nodes` 가 **부서의 조직 노드**에서 나와 「볼 수 없는 범위」 시험이 실제 규칙으로 검사된다. 손조립 값은 실제와 어긋나 403 을 냈고, 그때 원인은 「권한 없음」으로 보였다.
  - **읽기 실측**: 제품 앱(`main.app`)에 네 경로가 실제로 붙었는지 확인했다(OpenAPI 4건). ⚠️ **승인 POST 를 실 서버에 누르지 않았다** — 그것은 운영 DB(`data_preparation.db`·`decision_ledger.db`) 쓰기 탐침이고 금지 범위다. 대신 라우터 등록 자체를 회귀로 고정했다(미등록은 조용한 실패이고, 404 를 받은 사용자는 「기능이 없다」고 결론 내린 뒤 다시 묻지 않는다).
  - **변이 검사 M42~M46 중 3건 포착 · 2건은 등가로 판정하고 사유를 코드에 남겼다.**
    - 포착: 범위 은폐 제거 · 보상 취소 제거 · 목록 범위 필터 제거.
    - 등가 ①: 라우트의 `assert_can_manage_standard`. 실측하니 현재 조직도 규칙에서 두 축이 **완전히 겹친다**(`admin_only`·`data_admin` 둘 다 `can_manage_standard=True`·`admin.data_access=True`). 그래서 지워도 실패하는 시험이 없다. **가짜 시험을 지어 「검사가 있다」고 주장하지 않았고**, 남기는 이유(두 검사는 다른 질문이며 갈리는 날 유일한 방어가 된다)를 주석에 적었다.
    - 등가 ②: 권한 표 등록. 표와 핸들러가 같은 권한을 요구하므로 등가다. 남기는 이유는 라우터 의존성이 **핸들러보다 먼저** 돌고, 표가 있어야 `test_viewer_is_blocked_by_the_table` 이 이 경로를 함께 본다는 것이다.
  - **감사자가 판단할 사실 하나**: 조직도 규칙상 **시스템 관리자(`is_admin`)도 데이터 소유권을 승인할 수 있다.** 조직도가 그렇게 정했으므로 여기서 다르게 정하지 않았다 — 다르게 해야 한다면 그것은 조직도 쪽 결정이다.
- 영향·주의사항:
  - **승인 권한이 `admin.data_access` 다.** 프로젝트 실행 권한만 있는 사용자는 이 경로를 쓸 수 없다(의도된 축소).
  - 응답은 권한 밖 결속의 **존재도 개수도** 싣지 않는다. 목록 본문만 거르고 개수를 두는 실수가 흔해서 개수까지 회귀로 고정했다.
  - 화면은 아직 없다. 이 커밋은 **API 까지**다 — 프런트가 붙기 전에는 관리자가 직접 호출해야 한다.
  - 격리 복구는 이제 이 경로로 가능하다: `GET /ownership` 으로 격리 현황을 보고, `POST /ownership/approve` 로 재승인하면 해제된다(종단 회귀로 고정).
- 다음 행동 / 담당 / 착수 조건: ① 소유권 승인 화면(Codex 담당 — 상태 어휘 `LEGACY_OWNERSHIP_QUARANTINED` 가 늘었다) ② FND-01 조직 정본 연동(HOLD) ③ 계산 결과 결속 B2. 담당 Claude Code(백엔드). **원격 복구 방침 확정 전까지 모든 푸시 HOLD.**
- 교대 체크포인트: 마지막 확인 상태 = T2 인접 13스위트 402건 통과 · 변경 범위 = `api/routes/data_preparation_control.py`, `core/route_authority.py`, `tests/test_ownership_api.py`(신규), 이 현황판 · 미변경 = 타 팀원 작업분 · 검증 증거 = 변이 3/5 포착·2건 등가(사유 코드 주석), T2 402건, T3 1회, 제품 앱 라우트 등록 실측 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 감사 재확인 대기 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, 파일 끝까지 자르는 문자열 편집

### [G2-OWNBIND-20260821-03] 4.1c-C — 트리거 offset 우회·취소 권한·격리 가시성
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: `e770f5725` 재감사에서 P0 2건·P1 3건을 받았다. 다섯 건을 한 묶음으로 닫았고, 그 과정에서 **문자열 슬라이싱 편집으로 회귀 21건을 조용히 지운 사고**가 있었다. 그 사고가 남아야 한다 — 그때 「86건 통과」는 줄어든 회귀 위의 초록이었다.
- 상태: **보정 완료 · 검증 대기(감사 재확인 필요) · 푸시 금지 유지**
- 결정 및 근거:
  - **P0-1 트리거를 오프셋으로 우회할 수 있었다.** 실측 재현:
    ```
    기존 2026-06-01T00:00:00+00:00 ~ 02:00Z
    신규 2026-06-01T10:00:00+09:00 ~ 12:00+09   (= 01:00Z ~ 03:00Z)
    결과 OVERLAPPING_ACTIVE_ROWS 2
    ```
    시간대 없는 값(`2026-07-01T00:00:00`)과 파싱 불가 값(`언제인지모름`)도 그대로 통과했다.
    ★ 앞 판은 주석에 「`declare()` 가 UTC 로 정규화하니 안전하다」고 적었다. 틀린 이유는 단순하다 — **트리거의 존재 목적이 바로 `declare()` 를 우회하는 경로를 막는 것**이다. 우회 경로는 정규화를 지나지 않으므로, 정규화를 근거로 삼은 순간 트리거는 자기가 지키겠다고 한 경로에서 아무것도 지키지 않는다. **통제의 근거를, 그 통제가 막으려는 대상에 두었다.**
    → `julianday()` 비교 + 시간대 필수 + 파싱 불가 거부 + **기존 행이 읽히지 않으면 ABORT**(비교가 NULL 이 되어 조용히 통과하는 것을 막는다). 규칙은 INSERT·UPDATE 가 **한 문자열에서 조립**된다 — 주석으로 「양쪽 동일」을 약속하면 지켜지지 않는다(이 파일에서 같은 유형을 세 번 고쳤다).
  - **P0-2 `abandon()` 은 누구나 승인을 무효화할 수 있었다.** `revoke()` 에는 권한 검증을 넣고 여기에는 넣지 않았다 — **같은 결과를 내는 두 경로 중 하나만 막은** 것이다. → 실재·활성 사용자는 **언제나** 요구하고(문자열 일치만으로 「본인」을 인정하면 그 문자열을 아는 사람이면 누구나 본인을 자칭한다), 남의 승인을 취소하려면 현재 `can_manage_standard` 여야 한다. 본인 승인은 권한을 잃은 뒤에도 되돌릴 수 있다(권한 축소 방향이고, 막으면 잘못 승인한 사람이 정리할 길이 없다). 취소 사유도 필수다.
  - **P1-1 격리가 운영 준비도에 연결되지 않았다.** 앞 판은 `print` 만 남겼고 서비스는 빈 새 표로 계속 갔다 — **모든 데이터가 UNBOUND 가 된 이유를 운영자가 화면에서 알 수 없었다.** 로그는 다음 재시작에 사라지고, 그때부터 「원래 소유자가 없었다」와 구분되지 않는다. → 영속 표 `dataset_ownership_quarantine`(계약키·범위 단위) · 준비도 상태 `LEGACY_OWNERSHIP_QUARANTINED`(+`_NEXT_ACTION` 안내는 「파일을 다시 올려도 풀리지 않는다」를 명시) · 관리자 API `GET /ownership/quarantine`. **해제 근거는 「승인된 결속이 실제로 생겼다」는 사실뿐**이다 — 「관리자가 확인했다」로 풀면 다시 자기진술이다.
  - **P1-2 미물질화 보고가 원장 장애를 숨겼다.** `if revoked or failed: continue` 는 장애 중에 「미물질화 0건」이라고 말한다 — 아무 문제 없다는 뜻이다. 「모르는 것을 없는 것으로 접는」 결함을 이 파일에서 **네 번째로** 고쳤다.
  - **P1-3 마이그레이션 원자성**을 세 갈래로 고정했다: DDL 실패 시 ① 조용한 오답 대신 503 ② 재시작으로 결정론적 복구(격리가 두 번 쌓이지 않는다) ③ `migrate()` 내부 실패 시 옛 표·옛 색인이 그대로 남는다(반쯤 옮겨져 **통제 없는 표**로 도는 것을 막는다).
  - **⚠️⚠️ 사고 기록 — 편집 방식이 회귀를 지웠다.** `s[s.index(...):]` 로 파일 끝까지 교체하는 편집을 두 번 했고, 그 사이에 있던 정의가 함께 사라졌다. 1차로 `approve()` 함수, 2차로 **회귀 21건**이 사라졌다. 그 상태에서 「86건 통과」를 읽었는데, 그것은 **줄어든 분모 위의 초록**이었다. HEAD 와 정의 집합을 전수 비교해 21블록을 복구했다(복구 후 111건). 재발 방지: 문자열 편집 뒤에는 `git show HEAD:파일` 과 **정의 집합을 비교**한다 — 통과 건수는 손실을 알려주지 않는다.
  - **변이 검사 41건 전원 포착**(M1~M41). 이번 회차에서 **판별력 없는 변이 3건을 스스로 걸러냈다**: ① 준비도 분기 변이가 등가였다(계약키를 하나만 쓰면 격리 row 하나뿐이라 어차피 BLOCKED — 다른 키가 준비된 경우를 넣어야 판별된다) ② 존재하지 않는 이름을 넣어 54건이 NameError 로 깨진 무효 변이 ③ 「읽을 수 없는 기존 행」 회귀가 시간대 **없는** 값을 써서 앞선 겹침 검사에 먼저 걸렸다(파싱 불가 값으로 고쳤다).
- 영향·주의사항:
  - **저장되는 시각에 시간대가 필수다.** 트리거가 거부한다. 시간대 없는 값을 넣던 시드·마이그레이션은 실패한다(의도된 동작 — 시간대 없는 값은 서버 시간대에 따라 소유권을 바꾼다).
  - **준비도 어휘가 하나 늘었다**(`LEGACY_OWNERSHIP_QUARANTINED`). 화면이 상태 목록을 하드코딩하고 있으면 그 자리를 함께 고쳐야 한다.
  - 격리가 있으면 인스턴스는 `BLOCKED` 다 — 「부분 가능」으로 두지 않는다. 그 표현은 «기다리면 된다» 로 읽히는데, 이것은 사람이 재승인해야 풀린다.
  - `abandon()` 은 사유가 필수이고 임의 문자열 행위자를 거부한다.
- 다음 행동 / 담당 / 착수 조건: 감사 재확인 후 ① 승인·재승인 화면·API 경로(아직 없다) ② FND-01 조직 정본 연동(HOLD) ③ 계산 결과 결속 B2. 담당 Claude Code. **원격 복구 방침 확정 전까지 모든 푸시 HOLD.**
- 교대 체크포인트: 마지막 확인 상태 = T2 인접 17스위트 556건 통과 · 변경 범위 = `core/data_preparation/ownership_binding.py`, `core/data_preparation/readiness.py`, `api/routes/data_preparation_control.py`, `tests/test_dataset_ownership_binding.py`, `tests/test_data_readiness.py`, 이 현황판 · 미변경 = 타 팀원 작업분 · 검증 증거 = 변이 41/41 포착, T2 556건, T3 1회 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 감사 재확인 대기 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시, **파일 끝까지 자르는 문자열 편집**

### [G2-OWNBIND-20260821-02] 4.1c-B — 부트스트랩 승인 우회·구버전 스키마·기간 경쟁·철회 권한
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: `d9e86d06f` 재감사에서 **새 P0 네 건**을 받았다. 그 넷을 한 묶음으로 닫았고, 닫는 과정에서 **시험이 통제를 시험하지 않던 자리 두 곳**과 **실제 구멍 두 개**를 더 찾았다. 그 사실이 남아야 한다.
- 상태: **보정 완료 · 검증 대기(감사 재확인 필요) · 푸시 금지 유지**
- 결정 및 근거:
  - **P0-1 부트스트랩 승인 우회.** 실측으로 재현했다 — `resolve_scope()` 는 **부트스트랩이면 미등록 사용자에게도** 두 값을 모두 True 로 준다.
    ```
    ① 조직 없음      bootstrap=True  unrestricted=True  can_manage_standard=True
    ② 부서만 있음    bootstrap=True  unrestricted=True  can_manage_standard=True
    ③ 미등록 행위자  bootstrap=False unrestricted=False can_manage_standard=False
    ```
    `unrestricted or can_manage_standard` 는 ①②를 통과시켰다. **부서 생존 검사에서 같은 예외를 지우면서 승인 생성 경로에는 남겨 둔** 것이다 — 같은 예외를 두 곳에서 지워야 했다.
    → 네 관문을 순서대로 둔다: ① `is_bootstrap()` 차단 ② 실재·활성 사용자 ③ **사용자 정본의 권한 플래그**(스위치에 좌우되지 않는 유일한 근거) ④ 확정 결과 `can_manage_standard` 교차(`unrestricted` 는 **보지 않는다** — 그것이 우회 경로였다).
    - ⚠️ **이 구멍의 크기**: 조직도를 세우는 픽스처로 바꾸자 **시험 41건이 빨개졌다.** 즉 41건이 승인 권한 검사를 지나지 않고 초록이었다.
  - **P0-2 구버전 스키마 마이그레이션.** `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표에 열을 넣지 않으므로, `8ca029634` 형식 표가 있는 DB 에서 첫 `declare()` 가 `no such column: approval_event_id` 로 죽는다. `ownership_binding.migrate()` 를 만들고 `store._ready()` 가 **DDL 보다 먼저** 부른다. 규칙: 표 없음/이미 새 스키마 → 무동작 · 행 0건 → 안전 재구성 · **행 있음 → 격리**(`dataset_ownership_bindings_legacy_unapproved`). **자동 백필 금지** — 가짜 승인 사건을 만들면 이 작업이 지우려 한 자기진술을 원장에 박아 넣는 셈이고, 원장은 되돌릴 곳이 없다. 격리된 결속은 UNBOUND(비노출)이고 `legacy_unapproved()` 로 보고된다.
    - ⚠️ **조용한 통제 소실 함정을 밟기 직전이었다**: SQLite 의 `ALTER TABLE RENAME` 은 색인·트리거를 옛 표에 **이름째** 남긴다. 그러면 새 표에 `CREATE ... IF NOT EXISTS` 가 조용히 건너뛰어져 **새 표에 유일 색인도 트리거도 생기지 않는다** — 실패도 경고도 없다. 격리 전에 `_drop_attached()` 로 지우고, 회귀는 이름 확인에 그치지 않고 **실제로 막는지 눌러 본다**.
  - **P0-3 기간 중첩 경쟁.** 부분 UNIQUE 는 「같은 시작시각」만 막는다. 시작시각이 다르고 기간이 겹치는 두 요청은 각자 0건을 읽고 둘 다 삽입된다. → INSERT·UPDATE 양쪽에 **기간 중첩 trigger** 를 뒀다(UPDATE 쪽도 필요하다 — `REVOKED` 행의 status 를 되살리는 경로가 있다).
  - **P0-4 철회 권한·원장 도메인 검증.** 철회는 승인보다 **조용하다** — 소유권이 내려가면 그 데이터는 아무에게도 안 보이고, 「안 보인다」는 아무도 신고하지 않는다. `revoke()` 에 승인과 **같은** 권한 검증과 사유 필수를 넣었다. 원장 쪽은 `_REVOCATION_PARENTS` 표 하나로 합쳐 온톨로지·소유권이 **같은 부모·대상 검증**을 지나게 했다 — 앞 판은 온톨로지 검증이 `_insert` 에 하드코딩돼 있어 새 유형이 언제나 느슨한 쪽으로 태어나는 구조였다.
  - **P1 보강**: ① 원장의 `enterprise_scope_id` 는 **부서 id** 규약이다(`_filter_by_dept`). ECM `scope_node_id` 를 넣으면 **소유 부서 관리자의 조회에서 승인이 조용히 빠진다** — 오류 없이 목록에서만 사라지고, 승인 이력이 안 보이면 감사도 이의도 못 한다. 부서 id 로 바꾸고 범위는 근거(`scope_node:…`)로 남겼다. 회귀는 값 비교가 아니라 **제품 필터 함수**를 태운다. ② 승인(원장)과 등록(정본 표)은 다른 저장소의 두 단계라 묶을 수 없다 → `abandon()`(철회와 **같은 사건 유형** — 원장 검증과 `resolve` 의 자식 검사를 그대로 재사용한다)과 `dangling_approvals()` 보고를 뒀다. ③ T3 횟수 표기를 정정했다(위 항목 체크포인트).
  - **⚠️ 닫는 과정에서 찾은 실제 구멍 2건**
    - **취소·철회된 승인으로 등록이 됐다.** `resolve()` 만 철회 자식을 봤고 `declare()` 는 보지 않았다. 해석은 막히지만 ① 호출부에 「등록됐다」고 거짓을 답하고 ② 그 행이 기간 중첩 자리를 차지해 **정상 승인을 막고** ③ 목록·보고에서는 승인된 결속으로 보인다. `declare()` 에도 확인을 넣었다.
    - **원장 판독 실패를 「철회 없음」으로 접던 자리**가 `declare` 에 없었다(`resolve` 에만 있었다). 같이 막았다.
  - **⚠️ 시험이 아무것도 시험하지 않던 자리 2건**(변이 검사로 발견)
    - 두 연결 경쟁 회귀가 **트리거를 시험하지 않았다.** `declare()` 가 삽입 직전에 다시 조회하므로 상대가 커밋한 뒤에는 **응용 검사가 먼저** 잡는다 — 트리거를 무력화해도 실패 0건이었다. 「경쟁을 재현했다」고 믿은 시험이 실은 응용 검사만 확인했다. → 응용 검사가 통과한 상태를 직접 만들어(낡은 스냅숏과 같은 상태) 트리거의 몫을 시험한다.
    - 마이그레이션 회귀들이 `ob.migrate()` 를 **직접** 불러, `store._ready()` 의 호출을 지워도 실패 0건이었다 — 「통제는 있는데 부르는 경로가 없다」. → 제품 싱글턴 경로로 확인하는 회귀를 추가했다.
  - **변이 검사 27건 전원 포착**(M1~M27). 역치환으로만 되돌리고 매회 원상복구를 확인했다. 그 중 **잘못 고른 변이 3건**을 스스로 걸러냈다: 등가 변이(`elif False:` — 다음 분기에서 같이 걸린다), 트리거 주석만 바꾼 무효 변이, 빈 문자열 치환(역치환 불가 — 손으로 복구했고 하네스에 금지 규칙을 넣었다).
- 영향·주의사항:
  - **`revoke()` 시그니처 의미가 바뀐다**: 사유가 **필수**이고 행위자에게 승인 권한이 필요하다. 사유 없이 부르던 코드는 거부된다.
  - **`approve()` 는 조직도가 세워진 뒤에만 된다.** 부트스트랩 상태에서는 거부한다 — 시드 스크립트가 부서·관리자를 먼저 만들어야 한다.
  - **구버전 DB 는 첫 기동에서 격리된다.** 격리된 결속은 UNBOUND 이므로, 그 데이터셋의 소유자는 **다시 승인해야** 복구된다(의도된 동작이며 자동 승격하지 않는다).
  - 기간 trigger 의 비교는 **문자열 비교**다. 성립하는 이유는 `declare()` 가 저장 시각을 UTC ISO 로 정규화하기 때문이다 — **정규화를 끄면 trigger 가 조용히 헐거워진다. 그 둘은 한 계약이다.** 그래서 정규화 이전 표기의 옛 행은 trigger 를 빠져나갈 수 있고, 그 몫은 `resolve()` 의 중첩 검사가 받는다(회귀로 고정).
- 다음 행동 / 담당 / 착수 조건: 감사 재확인 후 ① 승인 화면·API 경로(아직 없다 — 지금은 시드·마이그레이션만 결속을 만든다) ② FND-01 조직 정본 연동(HOLD) ③ 조직 격리 실측 ④ 계산 결과 결속 B2. 담당 Claude Code. **원격 복구 방침 확정 전까지 모든 푸시 HOLD.**
- 교대 체크포인트: 마지막 확인 상태 = T2 인접 14스위트 459건 통과 · 변경 범위 = `core/data_preparation/ownership_binding.py`, `core/data_preparation/store.py`, `core/decision_ledger.py`, `tests/test_dataset_ownership_binding.py`, `tests/test_dataset_resolver.py`, 이 현황판 · 미변경 = 타 팀원 작업분 · 검증 증거 = 변이 27/27 포착, T2 459건, T3 1회 · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 감사 재확인 대기 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시

### [G2-OWNBIND-20260821-01] Dataset Ownership Binding 재감사 보정 — 「승인」이 실제로 승인이 되도록
- 작성자 / 기록 시각: Claude Code / 2026-08-21 KST
- 왜 지금 기록하는가: `8ca029634`(Dataset Ownership Binding) 의 완료 판정이 **철회**되고 P0 4건·P1 5건 지적을 받았다. 그 보정을 마쳤고, 보정 과정에서 **시험이 통제를 시험하지 않고 있던 자리 두 곳**을 변이 검사로 새로 찾았다 — 그 사실이 다음 사람에게 남아야 한다.
- 상태: **보정 완료 · 검증 대기(감사 재확인 필요) · 푸시 금지 유지**
- 결정 및 근거:
  - **P0-1 「승인」이 자기진술이었다 → 원장 사건으로 바꿨다.** 결속 표의 `approved_by` 문자열은 같은 호출자가 넣은 값을 같은 호출자가 읽는 것이다. 전용 원장 유형 `DATASET_OWNERSHIP_APPROVED`/`DATASET_OWNERSHIP_REVOKED` 와 주체 유형 `dataset_ownership_binding` 을 등록하고(`core/decision_ledger.py`), `approve()` → `declare(approval_event_id=…)` 순서를 강제했다. **대상 지문에 소유 부서를 넣는다** — 그러지 않으면 구매부서 승인 사건 하나로 재무부서 결속을 세울 수 있다.
    - 재검증은 `get_event_strict`·`has_invalidating_child` 로 한다. `list_events()` 는 ① `LIMIT` 이 있어 뒤에 사건이 쌓이면 철회가 조회 범위 밖으로 밀려나고 ② 판독 실패를 빈 배열로 접는다 — 둘 다 「모르니까 유효」로 기운다.
  - **P0-2 `executescript()` 는 감싼 트랜잭션을 먼저 커밋한다(실측).** `BEFORE in_transaction: True → AFTER_SCRIPT: False → ROWS_AFTER_ROLLBACK: 1`. 「한 트랜잭션에서 함께 성립한다」는 보증이 **주석에만** 있었다. DDL 을 `ensure_schema()` 초기화 경로 한 곳으로 옮겼고, `declare`·`resolve`·`revoke`·`list_bindings` 는 부르지 않는다.
  - **P0-3 빈 봉인이 통과했다.** `if sealed and sealed != now` 는 봉인이 빈 문자열이면 비교를 건너뛴다 — 즉 **색인이 모르는 승인이 즉시 권한이 됐다.** 네 상태로 갈랐다: 결속 없음(비노출) · 일치(허용) · **봉인 없음+결속 있음(503 재물질화)** · 불일치(503 낡은 색인).
  - **P0-4 부트스트랩 예외가 부서 무결성을 우회했다.** `is_bootstrap()` 은 초기 관리자 생성을 위한 **접근정책 예외**이고 소유권 정본 검증 면제가 아니다. FND-01 부서만 적재된 상태에서 임의 부서가 전부 통과했다. 예외를 제거했다.
  - **P1 보정**: ① 가짜 `_Scope` 를 지우고 실제 `OrgDirectory` + `resolve_scope()` 로 대조(강제 스위치를 켜고 **두 사람이 다 무제한이 아님을 먼저 증명**한다) ② 유효기간을 UTC 정규화 + **반열 구간 `[from, to)`** 으로 통일하고 **저장값도 정규화**했다 ③ `status='ACTIVE'` 부분 UNIQUE 색인으로 동시 삽입 차단 ④ 열 추가 마이그레이션의 `except Exception: pass` 를 `PRAGMA table_info` 존재 검사로 교체 ⑤ 현황판의 「변이 46/45」 표기를 「46건 시도 중 45건 포착·1건 구조상 관측 불가」로 고쳤다.
  - **⚠️ 변이 검사에서 «시험이 아무것도 시험하지 않던» 자리 두 곳을 새로 찾았다.** 이것이 이번 작업의 가장 중요한 결과다.
    - **철회 자식 사건 재검증**: 통째로 지워도 실패가 **0건**이었다. `revoke()` 가 행의 `status` 를 내리므로 앞선 관문에서 먼저 걸렸고, 뒤쪽 검사는 시험된 적이 없었다. → 「행의 `status` 만 되살린 자료」와 「철회 조회 실패」 회귀를 추가했다.
    - **원자성**: DDL 을 `declare` 로 되돌려 넣어도 실패가 **0건**이었다. `executescript` 가 파괴하는 것은 **그 앞에 한 일**인데 시험은 `declare` 뒤만 봤다. → 같은 트랜잭션에서 **먼저** 색인을 쓰고 나서 실패시키는 모양으로 바꿨다.
    - 그 외 등가 변이 1건(`elif False:`)은 다음 분기에서 똑같이 걸려 판별력이 없었고, 겹침 회귀 1건은 두 구간이 모두 무기한이라 문자열 비교로도 통과했다 — **판별력 있는 모양**(KST 표기가 문자열로는 더 커 보이는 방향)으로 고쳤다.
  - **⚠️ 보정 중에 같은 유형의 결함을 하나 더 찾았다 — 「관리자 경로」가 존재하지 않았다.** `approve()` 의 docstring 은 「행위자 권한은 여기서 확인한다(관리자 경로)」고 적었는데 코드는 `actor_id` 가 빈 문자열인지만 봤고, `approve()` 를 부르는 **API 경로 자체가 없었다.** 지적받은 `evidence_ref` 와 똑같이 문서가 코드를 대신 주장하고 있었다. 문장을 지우는 대신 검증을 넣었다 — 기준은 조직도가 내놓은 확정 결과 `AccessScope.can_manage_standard`(기준정보·데이터 표준 승인 권한)이고, 판독 실패는 통과가 아니라 503 이다. 거부 회귀는 **원장에 사건이 남지 않았는지까지** 확인한다(거부됐는데 이력에 승인이 남으면 그것이 더 나쁘다).
    - ⚠️ **한계(명시)**: 조직 권한 강제(`ORG_ENFORCE`)가 꺼져 있으면 `resolve_scope` 가 전원 무제한을 돌려주므로 이 검사는 통과한다. 제품 전체의 다른 통제와 같은 성질이며, 켜는 것은 관리자 결정이다. 시험은 강제를 **켠 상태**에서 대조한다.
    - ⚠️ **미완**: 승인을 부르는 화면·API 경로는 아직 없다. 지금 결속을 만들 수 있는 것은 시드·마이그레이션뿐이다 — 그 경로를 만들 때 이 권한 검증이 라우트 검사와 **이중으로** 걸리는지 확인할 것.
  - **변이 검사 12건 전원 포착**(M1 빈봉인·M2 승인검증 제거·M3 철회무시·M4 닫힌구간·M5a 겹침 문자열비교·M5b 해석창 문자열비교·M6 DDL 재삽입·M7a 전체유일색인·M7b 제약제거·M8 부트스트랩 예외 재삽입·M9 권한검증 제거·M10 권한판독실패 통과). 역치환으로만 되돌리고 매회 원상복구를 확인했다(`git checkout` 금지 — 이 세션에서 그렇게 해서 미커밋 수정을 날린 적이 있다).
- 영향·주의사항:
  - **결속을 만드는 모든 경로가 바뀐다.** `declare()` 는 `approval_event_id`·`evidence_ref` 를 **둘 다** 요구한다. 시드·마이그레이션이 `approve()` 를 먼저 부르지 않으면 거부된다 — 조용히 통과하지 않는다.
  - **원장에 새 유형 2종이 늘었다.** 승인 건수를 세는 집계가 있으면 이 두 유형이 포함되는지 확인할 것.
  - `effective_to` 는 **배타적**이다(«마지막으로 유효한 순간» 이 아니라 «유효가 끝나는 순간»). 기존 자료를 옮길 때 하루 차이가 난다.
  - 시험은 원장까지 격리한다. 격리하지 않으면 시험 승인 사건이 제품 감사 이력에 쌓인다.
- 다음 행동 / 담당 / 착수 조건: 감사 재확인 후 ① FND-01 조직 정본 연동(현재 HOLD) ② 조직 격리 실측 ③ 계산 결과 결속 B2 ④ API·화면 종단. 담당 Claude Code. **원격 복구 방침(`origin/dev → cd6d539fa`)이 확정되기 전까지 모든 푸시는 계속 HOLD.**
- 교대 체크포인트: 마지막 확인 상태 = T2 인접 10스위트 337건 통과 · 변경 범위 = `core/data_preparation/ownership_binding.py`, `core/ontology_resolvers.py`, `core/data_preparation/store.py`, `core/decision_ledger.py`, `tests/test_dataset_ownership_binding.py`, `tests/test_dataset_resolver.py`, 이 현황판 · 미변경 = 타 팀원 작업분(온톨로지 설계서·`docs/data-kits/README.md`·`.agents/AGENTS.md`) · 검증 증거 = 변이 12/12 포착, T2 337건, **T3 2회**(권한 결함 발견 전 1회 4,593건 · 수정 후 1회 4,594건 — 최종 근거는 두 번째뿐이다. 「한 번」이라고 적은 것은 부정확했다) · 커밋/푸시 = 선별 로컬 커밋만, **푸시 금지** · 재개 지점 = 감사 재확인 대기 · 금지 범위 = `git add -A`, 운영 DB 쓰기 탐침, 푸시

### [PILOT-WALKTHROUGH-20260819-04] Wave F-3·G·H 완료 · 파일럿 12칸이 실제 데이터로 관통
- 작성자 / 기록 시각: Claude Code / 2026-08-19 08:30 KST
- 왜 지금 기록하는가: 파일럿 동선이 **실제 데이터로** 한 번 돌았다. 그 사실과, 거기까지 오면서 드러난 결함 넷, 그리고 **아직 안 한 것 넷**을 남긴다 — 후자를 모르면 파일럿에서 만난다.
- 상태: **완료(백엔드 12/12 · 화면 11/12) · ⚠️ 변이 검사 밀림 · 실데이터 화면 미확인**
- 결정 및 근거:
  - **커밋 3건**: `18cd33394`(F-3 카나리 + Wave G 기준선·온톨로지·계산·의사결정 + 라우터 등록), `57ab7c64d`(Wave H 화면 4종), 그리고 이 파일럿 관통 시험.
  - **★★★ 종단 카나리가 실제 결함 셋을 잡았다** — 새 통제를 만들지 않았는데도. ① 계약 게이트가 Preview 증명인데 운영 평면을 봄 ② 업무 데이터에 `SYNTHETIC_TEST` 문맥이 없어 Preview 가 어떤 파일 판도 못 읽음 ③ 승격 검사도 운영 평면을 봐서 **모든 승격이 막힘**(설계서의 「ACTIVE 승격과 바인딩 전환 원자성」이 정확히 이것이었는데 F-2 는 상태만 바꿨다).
  - **⚠️⚠️ 라우터가 `main.py` 에 등록돼 있지 않았다.** `data_preparation_control` 의 10개 경로가 BDR-2·3·5 세 Wave 에 걸쳐 한 번도 앱에 붙은 적이 없다 — 시험이 자기 `FastAPI()` 를 만들어 붙였기 때문에 전부 초록이었다. 화면을 만들었다면 전부 404 였다. **Supervisor 지적으로 발견.**
  - **구조로 막았다**: `test_router_registration.py`(미등록 라우터를 회귀가 잡음) · `test_pilot_walkthrough.py`(12칸을 실제 API 로 한 줄에 돌림).
  - **검증**: 전체 회귀 4,214건 통과. UI 감사 게이트 4개 화면 × 2해상도 전 항목 통과. `tsc -b` 통과. 운영 불변식 — 원장 0행, dp.db·preview.db 미생성.
- 영향·주의사항:
  - **⚠️ Wave G·H 는 변이 검사를 안 돌렸다**(속도 우선 방침). Wave G 는 **숫자를 만드는 코드**라 조용한 오답이 곧 회의에 올라가는 숫자가 된다 — 파일럿 전에 한 번 묶어 돌리기를 권한다.
  - **⚠️ 화면을 빈 상태에서만 눌렀다.** 실제 데이터가 채워진 화면은 보지 못했다. 백엔드 동선은 관통 시험이 덮지만 **화면이 그 응답을 제대로 그리는지는 다른 문제**다.
  - **⚠️ 게이트 초록이 화면 완성이 아니다** — 전 항목 통과인데 본문 배경이 없어 글자를 못 읽던 적이 있다. 캡처를 사람이 보는 절차를 빼지 말 것.
  - `SYNTHETIC_TEST` 를 업무 데이터 문맥에 열었다. **별도 범위**라 REAL 인증판과 섞이지 않고 범위 대조가 둘을 갈라 놓는다. 조직 문맥(`enterprise_context.ENTITY_MODES`)에는 넣지 않았다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 가 ① Wave G·H 변이 검사 ② 실데이터로 화면 확인(격리 DB 에 파일럿 데이터를 넣고 캡처) ③ 승격 기록에 Snapshot 지문 봉인 순으로 진행한다.
- 교대 체크포인트: 마지막 확인 상태 = 커밋 3건 · 검증 증거 = 회귀 4,214건, UI 게이트 8/8, 파일럿 관통 3건 · 커밋/푸시 = 로컬 커밋(미푸시 6건). **이 현황판은 스테이징하지 않았다**(타 팀원 미커밋 작업) · 재개 지점 = 변이 검사 → 실데이터 화면 확인 · 금지 범위 = 메인 작업트리 변이 검사, 운영 DB 쓰기 탐침

### [BDR-WAVE-F2-20260819-03] Wave F-2 ACTIVE 원자 승격 완료 — 「통제는 있는데 부르는 경로가 없다」가 닫혔다
- 작성자 / 기록 시각: Claude Code / 2026-08-19 05:20 KST
- 왜 지금 기록하는가: F-0·F-1 에서 **두 번 반복된 함정**(통제는 만들었는데 운영 경로가 없음)이 F-2 에서 닫혔다. 이제 게시 → 후보 → Preview → 승격 → 운영이 관통한다. 그 사실과, 그 과정에서 게이트가 나를 잡은 자리를 남긴다.
- 상태: **완료 · 전체 회귀 4,152건 통과**
- 결정 및 근거:
  - **신규**: `core/release_promotion.py`(다섯 검사 · 검사와 전이 분리), `tests/test_release_promotion.py`(33건).
  - **변경**: `api/routes/factory_control.py`(게시가 `CANDIDATE` 기록 + `POST .../promote` + `GET .../promotion-check` + 물질화 기록에 `instances`), `core/route_authority.py`(승격 라우트 등록).
  - **★★★ 게시 기본값 전환과 승격 경로를 같은 커밋에 넣었다.** 나누면 그 사이 릴리스가 전부 후보로 갇힌다. 시험(`test_publish_and_promote_landed_in_the_same_commit`)이 둘 중 하나만 있으면 빨개진다.
  - **비소급**: `get_status()` 가 기록 없으면 `active`+`recorded=False` 를 주므로 **기존 릴리스는 그대로 돈다**(4c-0 과 같은 경계).
  - **★★★ 「보지 못한 것」은 통과가 아니다.** 검사할 코드 없음 · 읽지 못한 파일 · 준비도 확인 실패는 전부 **차단**. 「업무 데이터를 안 쓴다」는 `NOT_APPLICABLE` 로 명시해야 하고 `None`(확인 못함)과 **다른 값**이다 — 같게 두면 확인 실패가 조용히 면제가 된다.
  - **★★★ 검사와 전이를 나눴다.** 실패해도 상태를 손대지 않고 이전 ACTIVE 가 보존된다. 실패가 이미 도는 앱을 멈추면 승격 시도 자체가 위험해지고 아무도 안 한다.
  - **계약 승인 검사에서 레거시 면제를 쓰지 않는다.** 면제는 이미 도는 판을 지키기 위한 것이지 새로 올리기 위한 것이 아니다.
  - **⚠️ 권한표 게이트가 내 새 라우트를 잡았다** — `test_every_write_route_is_decided` 가 회귀에서 빨개졌고, 표에 등록해 해소했다. 이런 시험은 **잡히는 것이 성공**이다.
- 영향·주의사항:
  - **새 게시는 이제 후보로 태어난다.** 운영으로 쓰려면 승격이 필요하다 — 화면은 아직 없고 API 뿐이다(Wave H).
  - **⚠️ Preview 증명이 «운영 평면» 의 물질화 지문을 봉인한다.** Preview 는 자기 평면을 읽는데 봉인은 운영 것이라 어긋난다. F-1 시험에서 실측으로 드러났고 **F-3 에서 정리해야 한다.**
  - **⚠️ 승격이 Snapshot 지문을 남기지 않는다** — 「올릴 때 어느 데이터 판을 봤나」에 아직 답할 수 없다(인계 §4.2 와 한 쌍).
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 가 F-3(I-4 8 종단 카나리)을 수행한다. 구조적으로 분리된 DB 와 fresh worktree 를 쓰고 **운영 DB 에 카나리 쓰기 금지**. 함께 닫을 것: ① Preview 증명의 지문 대상 정리 ② 승격 기록에 Snapshot 지문 봉인.
- 교대 체크포인트: 마지막 확인 상태 = F-2 원자 커밋 · 변경 범위 = 신규 2 + 변경 3 파일(경로 명시 스테이징) · 검증 증거 = 회귀 4,152건, 변이 23/24(1건 관측 불가·사유 기록), 변이 검사(별도), 운영 불변식 4종(원장 0행 · dp.db·preview.db 미생성 · lifecycle 0행) · 커밋/푸시 = 로컬 커밋. **이 현황판은 스테이징하지 않았다**(타 팀원 미커밋 작업) · 재개 지점 = Wave F-3 · 금지 범위 = 메인 작업트리 변이 검사, 운영 DB 카나리 쓰기

### [BDR-WAVE-F1-20260819-02] Wave F-1 Preview 경계 완료 — 다만 «경계를 세운 것» 이지 «Preview 가 도는 것» 이 아니다
- 작성자 / 기록 시각: Claude Code / 2026-08-19 03:10 KST
- 왜 지금 기록하는가: F-1 을 마치면서 **F-0 과 똑같은 모양의 미완**을 함께 남긴다 — 통제는 다 만들었는데 그것을 부르는 운영 경로가 없다. 모르면 다음 사람이 Preview 가 작동한다고 오해하고, 그 오해 위에서 시연 각본을 짠다.
- 상태: **완료(경계·시험) · ⚠️ 운영 경로 미완(F-2 에서 닫는다)**
- 결정 및 근거:
  - **신규**: `core/app_preview.py`(청중·물리 분리·SYNTHETIC_TEST), `tests/test_app_preview_boundary.py`(47건).
  - **변경**: `core/app_capability_token.py`(증명에 `audience` 봉인 — **기본값 없음**), `api/routes/app_data_runtime.py`(발급·읽기·쓰기 전 경로를 청중 경유로), `tests/conftest.py`(Preview 평면 격리), 시험 호출부 4곳.
  - **라우터를 복제하지 않았다.** 청중은 릴리스 상태에서 유도되고 물리 DB 는 청중에서 나온다 — 「어느 URL 로 불렀나」가 아니라 **자료가** 경계를 정한다. Preview 는 `data/app_data_preview.db` 를 쓰고, 그 사실은 코드의 플래그가 아니라 **경로**가 보증한다.
  - **양방향 차단.** Preview 증명으로 운영을, 운영 증명으로 Preview 를 만질 수 없다. 한 방향만 막으면 반대쪽이 곧 우회로다 — 「Preview 는 약한 권한이니 운영 증명으로 봐도 되겠지」가 그 실수이고, 그러면 운영 권한을 가진 사람이 **검토되지 않은 코드에 자기 권한을 빌려 준다.**
  - **요청마다 다시 대조한다.** 발급 시점에 맞았다는 것으로는 부족하다 — 후보였던 판이 운영으로 승격되면 그때 발급된 Preview 증명이 운영 데이터를 가리키게 되고, **그것이 교차 사용의 실제 경로**다.
  - **⚠️ 격리 스텁이 통제를 해제한 사고**: conftest 에서 `db_path()` 를 스텁으로 덮었는데 그 함수의 일이 「모르는 청중을 거부하는 것」이었다. 스텁이 그 성질을 없애 「모르면 운영」이 됐고 경계 시험 7건이 즉시 빨개졌다. **격리는 경로가 아니라 인스턴스를 갈아끼운다.**
  - **검증**: 전체 회귀 통과(실패 0). 변이 22/22 포착. 운영 불변식 — 원장 0행, `data_preparation.db`·RAW 영역·**`app_data_preview.db` 전부 미생성**.
- 영향·주의사항:
  - **⚠️⚠️ 운영에서는 아직 아무도 릴리스를 `candidate` 로 만들지 않는다.** 상태값(`CANDIDATE`)은 F-1 에서 더했지만 게시는 여전히 상태를 적지 않는다. **상태값을 먼저 더한 이유**: 값이 없으면 Preview 경로가 시험에서도 실행되지 않아 변이 검사가 7건을 놓쳤다. 그래서 운영에서 Preview 증명은 **한 번도 발급되지 않는다.** 같은 경고를 `core/app_preview.py` 상단에 적어 뒀다.
  - **기본값을 지금 켜지 않은 이유**: 승격 경로(F-2)가 없다. 지금 게시를 후보로 바꾸면 모든 새 릴리스가 후보로 갇힌다.
  - 기존 릴리스는 `get_status()` 가 `active`+`recorded=False` 를 주므로 **아무것도 바뀌지 않는다**(비소급 경계, 4c-0 과 같은 규칙).
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 가 F-2(I-4 7)를 수행한다. ★★★ **승격 경로와 게시 기본값 전환을 같은 커밋에** 넣는다 — 나누면 그 사이 릴리스가 전부 갇힌다. 함께 닫을 것: ① 승격의 원자성(계약·정적검사·Review·물질화·Snapshot Readiness 재검증, 실패 시 이전 ACTIVE 보존) ② 승격 순간 기존 Preview 증명 즉시 무효화(F-1 의 요청마다 대조가 처리하지만 **시험으로 못 박아야** 한다) ③ 증명의 Snapshot 지문 봉인(인계 §4.2).
- 교대 체크포인트: 마지막 확인 상태 = F-1 원자 커밋 · 변경 범위 = 신규 2 + 변경 7 파일(경로 명시 스테이징) · 검증 증거 = 회귀 4,102건, 변이 검사(별도 기록), 운영 DB 불변식 4종 · 커밋/푸시 = 로컬 커밋. **이 현황판 파일은 스테이징하지 않았다**(타 팀원 미커밋 아카이브 분리가 얹혀 있음) · 재개 지점 = Wave F-2 · 금지 범위 = 메인 작업트리 변이 검사, 운영 DB 쓰기 탐침

### [BDR-WAVE-F0-20260819-01] Wave F-0 계약 물질화 완료 · 「승인은 되는데 아무것도 생기지 않던」 상태 해소
- 작성자 / 기록 시각: Claude Code / 2026-08-19 01:45 KST
- 왜 지금 기록하는가: Wave F-0 를 마치면서, **인계 문서에 적어 둔 F-0 기술이 틀렸다는 사실**과 그 과정에서 드러난 «잘못된 이유로 통과하던 시험» 을 남긴다. 이 둘을 모르면 다음 사람이 30분짜리 일로 알고 착수하고, 같은 종류의 거짓 초록을 다시 만든다.
- 상태: **완료 · 변이 23/23 포착 · 전체 회귀 4,055건 통과**
- 결정 및 근거:
  - **⚠️ 인계 문서 §4.1 의 원래 기술이 틀렸다.** 「계약 컴파일러가 두 열을 안 채운다」로 적었으나, 실제로는 **승인된 계약을 데이터셋으로 만드는 단계 자체가 운영 코드에 없었다.** 근거 둘: ① `create_dataset`/`bind_release`/`adopt_dataset` 에 `allowed_actions` 를 넘기는 곳이 **시험뿐**이었다 ② 운영 `data/app_data.db` 에 `app_release_dataset_bindings` 표가 **존재조차 하지 않았다**(계약 경로를 지난 릴리스가 한 건도 없다는 뜻). 승인 뒤 하는 일은 타입 어댑터 파일 쓰기 하나였고, **그 상태는 오류를 내지 않았다** — 봉인은 「그때와 같은가」에 답할 뿐 「무언가 생겼는가」에는 답하지 않는다. 60/60 프로젝트가 LEGACY_OFF 였던 이유가 이것이다.
  - **신규**: `core/contract_materializer.py`(계획→실행 분리, 전부 아니면 아무것도), `tests/test_contract_materializer.py`(35건).
  - **변경**: `api/routes/factory_control.py`(게시 경로에 `_materialize_contract_for_release` 배선), `core/app_data.py`·`core/app_data_store.py`(`enterprise_contract_key`·`kit_instance_id` 를 4개 진입점에서 결속 표까지 전달 + 사내 원천 필수값 검증), `core/app_runtime_contract.py`(`ENTERPRISE_READ` 를 `SUPPORTED` 로 · 계약 상태 상수 추가), `core/host_contract_compiler.py`(계약키 필수 + **이중 입력 게이트 실제 배선**), `tests/test_app_runtime_contract.py`·`tests/test_app_dataset_binding.py`·`tests/test_provider_dispatch.py`.
  - **⚠️⚠️ 「막는 시험」이 게이트가 아니라 문구 때문에 통과하고 있었다.** `test_enterprise_read_cannot_have_input_actions` 는 컴파일러가 `ENTERPRISE_READ` 를 「아직 물질화 불가」로 먼저 막았고 그 안내문에 마침 「입력 화면」이라는 말이 들어 있어서 초록이었다. 옆 시험의 주석이 그 사실을 이미 적어 뒀지만 아무도 「이 시험이 무력화됐다」로 읽지 않았다. 출처를 열자 방벽이 사라졌고 컴파일러가 `role_source_errors` 를 부르지 않는다는 사실이 드러났다 — 지금은 부른다. **교훈: 막는 시험이 통과할 때 무엇이 막았는지 확인한다.**
  - **시험의 직접 UPDATE 를 걷어냈다.** Wave E 의 `_wire` 가 결속 표를 직접 썼고, 그래서 배선 누락을 못 잡았다. 이제 시험도 `compile_contract` 로 계약을 만들어 물질화기에 통과시킨다. 그 과정에서 손으로 적은 계약이 스키마를 네 번 어겼고(`runtime_contract_version` · `purpose` · `approval` 필드명 · `decision_ledger_id`) 그때마다 게이트가 정확히 막았다 — **계약 게이트가 실제로 일하고 있다는 증거**다.
  - **검증**: 변이 23건 전부 포착(폐기 워크트리 `scratchpad/mut_f0`, 메인 트리 무오염). 전체 회귀 4,055건 통과(실패 0·오류 0·건너뜀 1). 운영 불변식 — 원장 0행, `data_preparation.db` 미생성, RAW 영역 미생성, `app_data.db` 무변경.
- 영향·주의사항:
  - **원천이 준비되지 않으면 앱이 아예 만들어지지 않는다.** 게시 시점에 활성 원천이 없으면 물질화가 실패하고 `contract_materialization.state="FAILED"` 로 릴리스에 기록된다. **게시 자체는 막지 않는다** — 산출물은 이미 있고 못 꺼내게 하는 것이 더 큰 손해다. 의도된 동작이다: 만들어진 뒤 런타임에서 막히면 사용자는 앱이 고장 났다고 생각한다.
  - **`ENTERPRISE_READ` 가 계약에서 열렸다.** `EXTERNAL_REFERENCE`·`DERIVED_READ` 는 읽어 줄 코드가 없으므로 **그대로 막아 뒀다** — 「곧 될 것」을 열면 앱이 빈 응답을 정상으로 받는다.
  - `app_release_dataset_bindings` 에 사내 원천 결속은 **계약키와 Kit Instance 를 모두** 요구한다. 하나만 있으면 거부한다(우리 DB 로 폴백하지 않는다).
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 가 Wave F-1(I-4 6 — Release Candidate · Preview DB 물리 분리 · Preview Proof)로 이어서 진행한다. 착수 시 함께 볼 것: ① 증명이 **Snapshot 지문을 봉인하지 않는다**(인계 §4.2) ② Preview/운영 proof audience 교차 사용 **양방향** 차단 ③ 물질화를 Preview·ACTIVE 에서 각각 언제 다시 돌릴지 — 지금은 게시 하나뿐이다.
- 교대 체크포인트: 마지막 확인 상태 = F-0 원자 커밋 완료 · 변경 범위 = 신규 2 + 변경 8 파일(경로 명시 스테이징) · 미변경 = `.agents/AGENTS.md`, `docs/data-kits/README.md`, 온톨로지 설계서(타 팀원 작업분) · 검증 증거 = 변이 23/23, 회귀 4,055건, 운영 DB 불변식 4종 · 커밋/푸시 = 로컬 커밋. **⚠️ 이 현황판 파일 자체는 스테이징하지 않았다** — 타 팀원의 미커밋 아카이브 분리(2,408행 삭제)가 얹혀 있어 함께 커밋하면 남의 미완 작업을 쓸어 담는다 · 재개 지점 = Wave F-1 · 금지 범위 = 메인 작업트리 변이 검사, 운영 DB 쓰기 탐침, 원장 선별 이관

### [BDR-WAVE-E-20260818-01] BDR-5 결정론적 준비도 판정 · BDR-6 Provider Dispatch 완료 · Gate E 통과
- 작성자 / 기록 시각: Claude Code / 2026-08-18 22:40 KST
- 왜 지금 기록하는가: Wave E 구현·변이 검사·전체 회귀를 마치고 원자 커밋을 남기면서, Wave F 로 넘어가는 **미완 배선 한 건**을 인계하기 위해서다. 그 배선은 이 커밋 범위 밖이며, 모르고 지나가면 Dispatch 가 「시험에서만 도는」 상태로 남는다.
- 상태: **완료(Gate E 5개 항목 전원 통과) · 잔여 배선 1건은 Wave F 로 명시 이관**
- 결정 및 근거:
  - **정본 충돌 해결**: 상세설계 §10.1(`UNBOUND`/`SNAPSHOT_AVAILABLE`/`BLOCKED`/`NOT_APPLICABLE`)과 솔로 인수인계 §9.1(`NOT_CONFIGURED`/`DATA_AVAILABLE`/`UNAVAILABLE`)의 어휘가 갈렸다. 더 최근이고 MVP 범위인 **인수인계 9상태를 정본**으로 채택하고, 설계서 어휘와의 대응표를 `core/data_preparation/readiness.py` 머리말에 적었다. `NOT_APPLICABLE`(불필요 승인)은 승인 흐름이 없어 MVP 밖이며, **`READY` 로 접지 않고 없는 상태로 남겼다** — 접으면 필요 없다고 판단한 데이터가 준비된 데이터로 세어진다.
  - **산문 의존 제거**: 격리 사유가 한국어 문장(`"원천 합계 대사 불일치"`)이라 판정이 문구에 의존하고 있었다. `models.QUARANTINE_QUALITY`/`QUARANTINE_RECONCILIATION` 기계 코드를 붙이고 판정을 코드 기반으로 바꿨다. 문구를 다듬어도 판정이 바뀌지 않는다.
  - **신규**: `core/data_preparation/readiness.py`(판정 엔진 — 저장소를 모른다), `core/host_runtime_provider.py`(Dispatch), `tests/test_data_readiness.py`(41건), `tests/test_provider_dispatch.py`(40건).
  - **변경**: `api/routes/data_preparation_control.py`(`GET /instances/{id}/readiness`), `api/routes/app_data_runtime.py`(읽기 3·쓰기 3 경로에 Dispatch 배선), `core/app_data_store.py`·`core/app_data.py`(`enterprise_contract_key`·`kit_instance_id` 열), `core/data_preparation/kit_registry.py`(`outputs` 파서·검증), `docs/data-kits/afs_materials_procurement_v1.kit.json`(산출물 3종 선언).
  - **변이 검사 46건 중 45건 포착**(폐기 워크트리 `scratchpad/mut_e`, 메인 트리 무오염). 처음 4건을 놓쳐 세 자리를 시험으로 막았다: ① 인증판이 둘 이상일 때 목록 위치로 고르면 「지난달 판」이 이긴다 ② 원천 저장소 장애를 「결속 없음」으로 기록하면 운영자가 고치러 가지 않는다(감사 기록 검증으로 분리) ③ 오류 응답 본문에 준비도 상태명이 실려 나갔다. 넷째(`sort_keys=False`)는 호출부가 이미 정렬된 키로 payload 를 만들어 **구조상 관측 불가**이므로 가짜 시험을 짓지 않고 사유를 코드 주석에 남겼다.
  - **⚠️ 교차검토 ③(예외 경로 은폐 일관성) 확인 중 실제 결함 1건 발견·수정**: Dispatch 가 **조직 범위를 대조하지 않고 있었다.** 앱이 범위 A 에 있어도 결속 표의 `kit_instance_id` 가 범위 B 의 인스턴스를 가리키면 그 인증판을 그대로 읽었다. 앱이 그 값을 고르지 못하므로 열거 경로는 아니지만, 결속을 잘못 적으면 **다른 조직의 인증된 숫자가 오류 없이 화면에 오른다.** 범위 대조를 **증명에 봉인된 값**(`proof.tenant_id`/`scope_node_id`/`entity_mode`)으로 배선했다 — 결속 표끼리 비교하면 자기 자신과 비교하는 것이라 언제나 통과한다.
  - **⚠️ 위 결함을 처음 쓴 시험이 통과시켰다(조용한 거짓말)**: 타 범위에 판을 만들지 않아 「범위가 달라 막힘」과 「판이 없어 막힘」이 똑같이 503 이었다. 대조군을 타 범위의 **인증까지 끝낸 판**으로 바꿔 검사를 지우면 200 이 나오게 만들었고, 범위 세 필드를 **하나씩** 어긋내는 시험을 추가했다 — 셋을 한꺼번에만 보면 판정이 그중 하나만 봐도 통과하며, 실제로 `tenant_id` 만 결속 표에서 가져오는 변이가 처음에 살아남았다. 범위 변이 4/4 포착.
  - **전체 회귀**: `venv/Scripts/python.exe -m pytest tests/` 4,020건 통과(실패 0·오류 0·건너뜀 1). 운영 불변식 확인 — 원장 0행 유지, `data/data_preparation.db` 미생성, RAW 영역 미생성.
- 영향·주의사항:
  - `app_release_dataset_bindings` 에 열 2개가 늘었다(`enterprise_contract_key`, `kit_instance_id`). 기존 행은 빈 문자열이고, **빈 값 + 비-Native 의도는 Dispatch 가 거부한다**(우리 DB 로 폴백하지 않는다). 레거시(`source_intent=''`) 결속은 종전대로 Native 로 간다.
  - `app_data_runtime` 의 읽기·쓰기 여섯 경로가 전부 Dispatch 를 지난다. 이 경로를 고칠 때 **Dispatch 호출을 빼면 통제가 통째로 사라진다** — 변이 검사에 여섯 건 모두 들어 있다.
  - 키트 문서에 `outputs` 가 생겨 **지문이 바뀌었다**. 지문을 고정한 시험은 없으나, 키트를 이미 적용한 인스턴스가 있으면 판본 지문 비교가 달라진다.
- 다음 행동 / 담당 / 착수 조건:
  - **⚠️ 잔여 배선 1건 — Wave F 필수 선행**: `enterprise_contract_key`·`kit_instance_id` 를 **계약 컴파일러가 채우는 경로가 아직 없다.** 지금은 `tests/test_provider_dispatch.py::_wire` 가 직접 UPDATE 한다(주석에 명시). 즉 Dispatch 는 작동하지만 **사용자가 화면에서 앱 데이터셋을 사내 원천에 연결할 방법이 없다.** Wave F(I-4 7 ACTIVE 원자 승격)에서 〈업무키트 계약 컴파일 → 데이터셋 물질화 → 결속 메타데이터 주입 → Dispatch〉 종단 계약 시험과 함께 채운다. 담당: Claude Code.
  - Wave F 착수 시 함께 볼 것(교차검토 지적): ① 지문 변경 시 기존 Preview proof·frame 이 즉시 거부되는가 ② 404 은폐 정책이 Timeout·DB 단절 등 **모든 예외 경로**에서 유지되는가.
- 교대 체크포인트: 마지막 확인 상태 = Wave E 원자 커밋 완료 · 변경 범위 = 위 신규 4 + 변경 6 파일(타인 미커밋 파일 미포함, 경로 명시 스테이징) · 미변경 = `.agents/AGENTS.md`, `docs/data-kits/README.md`, `docs/design_manufacturing_management_ontology_2026-08-13.md`(타 팀원 작업분) · 검증 증거 = 변이 46건 시도 중 45건 포착·1건은 구조상 관측 불가(사유는 코드 주석), 전체 회귀 통과, 운영 DB 불변식 3종 · 커밋/푸시 = 로컬 커밋만(지시 없이 push 금지). **⚠️ 이 현황판 파일 자체는 스테이징하지 않았다** — 이 파일에는 타 팀원의 미커밋 작업(2026-08-18 히스토리 아카이브 분리, 2,408행 삭제)이 이미 얹혀 있어, 함께 커밋하면 남의 미완 작업을 내 커밋으로 쓸어 담는다. 작업 트리에는 기록돼 있으므로 아카이브 작업 주체가 자기 커밋에 함께 담을 것 · 재개 지점 = Wave F I-4 6(Preview DB 물리 분리) · 금지 범위 = 메인 작업트리 변이 검사, 운영 DB 쓰기 탐침, 원장 선별 이관

### [INC-LEDGER-20260817-01] P0-L4 신규 활성 원장 가동 · P0-L5 전체 재검증 완료 · 4c-2 HOLD 해제 및 변이 검사 승인
- 작성자 / 기록 시각: Gemini Antigravity / 2026-08-17 20:00 KST
- 왜 지금 기록하는가: Claude Code의 P0-L4(원본 이동 및 신규 빈 원장 가동) 및 P0-L5(전체 회귀 3,667 passed, 0 failed, 운영 원장 0건 불변) 완료 보고에 따라, 포렌식 아카이브 및 신규 원장 상태를 감사(Audit)하고 4c-2 HOLD를 공식 해제하며 후속 변이 검사 및 원자 커밋 착수를 승인한다.
- 상태: **P0-L1~L5 복구 절차 전원 완료 · 4c-2 HOLD 공식 해제 · 변이 검사 및 원자 커밋 진행 승인**
- 결정 및 근거:
  - L4 아카이브 검증: 원본 이동본(`decision_ledger_polluted_20260817_original.db`) 및 사전 사본(`decision_ledger_polluted_20260817.db`) 모두 SHA-256(`d29ebab8...`), 11,633건 일치 및 읽기 전용(`0o444`) 확인.
  - 신규 원장 클린 초기화: `data/decision_ledger.db` sha256(`36c34548...`), 0행/seq 0/tail 없음, 스키마 6개(테이블 1 + 인덱스 5) 정상 생성 확인.
  - L5 전체 회귀 결과: 원장/격리 회귀 52건 통과, 4c-2 회귀 175건 통과, 전체 회귀 3,667 passed, 1 skipped, 0 failed. 회귀 후 운영 신규 원장 0행 유지, WAL/SHM 없음, 운영 DB 4종 지문 불변 확인.
  - 매니페스트 갱신: `docs/handoff/DECISION_LEDGER_FORENSIC_MANIFEST_20260817.md`에 원본 이동본 및 협의(42.7%)/광의(99.64%) 기준 공식 병기 완료.
- 영향·주의사항: 운영 신규 원장(`data/decision_ledger.db`)은 깨끗한 0건 상태로 시작되며 구 원장 선별 이관은 금지됨. 4c-2 변이 검사는 메인 작업트리를 오염시키지 않도록 반드시 격리된 폐기 워크트리에서 수행할 것.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**가 격리 폐기 워크트리에서 4c-2 변이 검사를 완료하고, 4c-2 원자 커밋을 진행한 후 4c-3(전용 승인·반려 API) 및 후속 파이프라인으로 지체 없이 이어서 진행한다.
- 교대 체크포인트: 원본/사본 2중 아카이브(`0o444`), 신규 원장 0건 가동 확인. 전체 테스트 3,667 passed. 재개 지점 = 4c-2 폐기 워크트리 변이 검사 및 원자 커밋.

### [BDR-DESIGN-94] 기존 시스템 의존·현업 저사용 위험을 함께 줄이는 데이터 연결·준비 런타임 상세설계
- 작성자 / 기록 시각: Codex / 2026-08-15 15:17 KST (후속 판정 포함)
- 왜 지금 기록하는가: Supervisor가 “현업 앱 사용률이 낮으면 경영 데이터가 비는 위험”과 “이를 막으려 레거시 I/F를 늘리면 EAI 비용·옥상옥·BI화가 되는 위험”을 동시에 지적하고, 기본 데이터 키트와 기존 원천 재사용 원칙을 실제 제품에 바로 구현할 수 있는 상세설계·팀 인수인계로 고정하라고 지시했다. 또한 Claude Code의 I-4 생성기 계약이 데이터 출처 구분 없이 물질화되기 전에 **기존 Actual 재입력 금지**를 계약에 넣어야 한다.
- 상태: **상세설계·기계 계약·팀 공통 인수인계 완료 · I-4 2.1b 승인 · I-4 2.2 BDR-1 삽입**
- 결정 및 근거:
  - 출처 모드를 `CONNECTOR_QUERY / FILE_SNAPSHOT / AFS_NATIVE / DERIVED / EXTERNAL_REFERENCE`로 분리하고, 공식 계산은 승인된 불변 Snapshot ID 집합만 사용한다.
  - 통합 수준은 L0 승인 파일→L1 예약 파일/View→L2 API/MCP→L3 EAI/CDC 순으로 ROI에 따라 승격한다. 전사 ERP 전체 복제나 실시간 I/F를 첫 효용의 선행조건으로 두지 않는다.
  - 기존 권위 원천이 있으면 AFS 입력 UI와 create/update를 차단하는 `Zero Duplicate Entry Gate`를 I-4 App Runtime Contract의 `source_intent`, `data_role`, `duplicate_entry_policy`로 강제한다. 현재는 `AFS_NATIVE`만 물질화하고 기업·외부·계산 데이터는 `HOST_SERVICE_REQUIRED`로 명시한다.
  - 근거: `docs/architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md`, `docs/architecture/business_data_binding_contract_v1.schema.json`, `docs/architecture/first_vertical_data_binding_profile_v1.example.json`, `docs/handoff/BUSINESS_DATA_BINDING_RUNTIME_TEAM_HANDOFF_2026-08-15.md`.
- 영향·주의사항: 3단계가 계약 지문을 증명에 봉인하기 전에 BDR-1을 **I-4 2.2 보강**으로 먼저 넣어야 지문·승인 계약을 두 번 바꾸지 않는다. 기존 계약의 미분류 데이터셋을 자동 `AFS_NATIVE` 또는 Actual로 승격하지 않는다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**는 I-4 2.2 BDR-1 구현 후 I-4 3단계로 연결. **Codex**는 회사 데이터 준비 보드·Source Binding·인증 워크벤치 UX 교차검토. **Antigravity**는 첫 Minimum Decision Dataset 원천 품질 및 오염 독립 검증.

### [G1-B-BROWSER-CANARY-88] 실제 Preview 종단 완료 · 410 캐시 회귀 보정 · [5] 게이트 통과 및 [6] 원자적 전환 승인
- 작성자 / 기록 시각: Codex / 2026-08-15 02:00 KST
- 왜 지금 기록하는가: Claude Code가 구조 지문 보정(`f97dbdc70`) 및 fresh `canary_5`를 단일 실행하여 게이트 조건을 충족했으므로 Host Runtime의 Shadow→강제 전환을 승인했다.
- 상태: **[4] 실제 브라우저 종단 통과 · [5] 전환 게이트 완료 · [6] 원자적 전환 승인**
- 결정 및 근거:
  - 실제 iframe에서 Host Runtime schema/create/list/get/update/remove 6/6 성공.
  - Manifest stale 기존 iframe 410/EXPIRED 격리 및 새 릴리스 재열기 복구 확인.
  - `STRUCTURE_SOURCES` 8개 결속, `canary_5` 26/26, dynamic 5/5, structural 5/5, `safe_to_switch=True`, EXIT=0 확인.
- 영향·주의사항: 플래그·라우트·롤백 스위치·전환 후 smoke 증거를 하나의 변경 단위로 남김. 관리 API가 앱 경로의 폴백으로 되살아나지 않도록 차단.
- 다음 행동 / 담당 / 착수 조건: Claude Code가 [6] 원자적 전환 수행 후 [7] I-4 생성기 연동 진행.

### [G2-ONTOLOGY-DESIGN-74] 제조 경영 온톨로지 런타임 및 첫 수직 폐루프 상세설계
- 작성자 / 기록 시각: Codex / 2026-08-14 20:50 KST
- 왜 지금 기록하는가: 첫 수직 폐루프(Vertical Closed Loop)를 완주하기 위한 배터리/제조 도메인 온톨로지 및 의사결정 파이프라인의 SSOT 설계를 확정.
- 상태: **상세설계 및 계약 정의 완료 · 구현 연계 대기**
- 결정 및 근거:
  - `docs/architecture/MANUFACTURING_MANAGEMENT_ONTOLOGY_RUNTIME_DESIGN_2026-08-14.md`
  - Object Scope, Decision Ledger Resolver, WBS 연동 계약 수립.
  - 로드맵 G2/G4 관문 통과를 위한 핵심 엔티티(공정, 설비, 원자재, 품질, 수율, 원가, 리스크) 정규화.
- 다음 행동 / 담당 / 착수 조건: G2-B 데이터 키트 및 G4 계산 어댑터 연결 준비.

### [SAMPLE-KIT-69] 제조 경영 샘플 회사 스타터 키트 기준선 (Battery & Chemical)
- 작성자 / 기록 시각: Codex / 2026-08-14 18:30 KST
- 왜 지금 기록하는가: 실제 기업 데이터를 대체하여 시연 및 E2E 검증을 완결할 수 있는 가상 기업(LS M&M 기반 정밀 화학/배터리 소재) 표준 스타터 키트 확정.
- 상태: **스타터 키트 스펙 확정 (`docs/data-kits/SAMPLE_COMPANY_BATTERY_CHEMICAL_STARTER_KIT_SPEC_2026-08-11.md`)**
- 결정 및 근거:
  - 배터리 양극재/동제련 공정 기반 5개 핵심 데이터셋(생산실적, 설비가동, 원가, 품질불량, 수율) 및 온톨로지 바인딩 프로필 수립.
  - 데모 및 E2E 시연 시 합성 데이터와 실제 데이터의 격리 원칙 보장.
- 다음 행동: BDR 런타임의 Reference Profile로 탑재 및 검증 데이터셋 활용.

### [PRODUCT-FEATURE-GUIDE-V21-81] 기능소개서 v2.1 및 경영진 브리핑 최종 개정
- 작성자 / 기록 시각: Codex / 2026-08-14 10:42 KST
- 왜 지금 기록하는가: 경영진 및 대내외 평가 피드백을 반영하여 기능 중심 나열에서 온톨로지·행위/결과 중심의 26면 제품 기능소개서로 전면 개편.
- 상태: **v2.1 개정 완료 (`docs/product-guide/AI_FACTORY_STUDIO_PRODUCT_FEATURE_GUIDE_2026-08-14.html`)**
- 결정 및 근거:
  - 90일 파일럿 ROI 산출식, 레거시 시스템 공존 원칙, 화면별 구체적 역할 명시 완료.
  - PDF 인쇄/레이아웃 검증 완료.

---

## 📊 현재 주요 트랙 및 로드맵 게이트 현황

```text
1. I-4 앱 런타임 & 호스트 계약
   ├─ 2.1b 결속 지문·격리 게이트        ██████████  완료
   ├─ 2.2 BDR-1 (출처의도·중복방지)     ██████████  완료/연계
   ├─ 3단계 원문 지문 증명 봉인         ██████████  완료
   ├─ 4c-0 프로필 3상태·손상 차단       ██████████  완료
   ├─ 4c-1 계약 합산기                  ██████████  완료
   ├─ 4c-2 검토 요청 이벤트             ████████░░  HOLD 해제 (변이 검사/커밋 대기)
   ├─ 4c-3 전용 승인·반려 API           ░░░░░░░░░░  대기
   │   ★ 키트 앱 계약에 한해서는 2026-08-23 에 승인 경로가 생겼다
   │     (`core/kit_app_contract`, `POST …/apps/{app_id}/contract/approve`).
   │     ⚠️ 릴리스 계약 일반의 4c-3 과는 **다른 대상**이다 — 합치지 말 것.
   └─ 4c-4~7 HOTL 우회차단/릴리스 차단   ░░░░░░░░░░  대기

2. Decision Ledger 포렌식 보관 및 복구 (INC-LEDGER-20260817-01)
   ├─ P0-L1~L3 격리·불변·보관 감사     ██████████  완료 (이중 아카이브)
   ├─ P0-L4 신규 활성 원장(0건) 가동    ██████████  완료
   └─ P0-L5 전체 회귀 3,667건 불변 검증  ██████████  완료

3. BDR (Business Data Binding Runtime) & G2/G4 트랙
   ├─ BDR 상세설계 및 기계 계약         ██████████  완료
   ├─ G2 온톨로지 런타임 설계           ██████████  완료
   └─ G4 계산 어댑터 및 첫 수직 폐루프   ░░░░░░░░░░  착수 준비

4. 키트로 앱 생성 (2026-08-23 · Claude Code)
   ├─ 청사진→정본 계약 번역             ██████████  완료 (arc.validate 자체 호출)
   ├─ 인증판에서 필드 도출              ██████████  완료 (예약 칸 제외·형 변환표)
   ├─ 계약 초안·승인 저장소             ██████████  완료 (kit_app_contracts + 트리거)
   ├─ API 4경로                         ██████████  완료 (목록·초안·승인·물질화)
   ├─ 화면 KitAppPanel                  ██████████  완료 (준비도 보드에 연결)
   └─ 화면 실측 종단                    ██████████  완료 (초안→승인→앱 5/5)
```

### 🔔 2026-08-23 — 다른 멤버가 알아야 할 것

- **준비도 보드 아래에 「키트로 앱 만들기」 패널이 붙었다**
  (`frontend/src/components/KitAppPanel.tsx`). 초안 → **다른 사람의 승인** → 앱 만들기.
- ⚠️ **만든 사람은 자기 계약을 승인할 수 없다.** 시연 조직의 승인자는 `hikwon` 하나뿐이라
  **초안은 `runner@afs.invalid` 가 만들어야** 고리가 닫힌다. 시연 대본에 반영 필요.
- `main.py` CORS 개발 허용 포트를 **대역 5173~5199** 로 바꿨다. 네 번째로 같은 벽에
  부딪혀서다(08-04 5174 · 08-06 5175 · 08-08 5177 · 08-23 5179).
  ★ 이제 프런트를 어느 포트로 띄워도 「서버에 연결하지 못했습니다」가 안 난다.
- `scripts/run_local_demo.py` 가 **보충(top-up)** 을 한다. 이미 심어진 시연 뿌리에
  부족한 계약키만 채운다 — `--reset` 으로 온톨로지·기준선까지 날릴 필요가 없다.
- ⚠️⚠️ **시험에서 「운영 경로」를 `core.paths.data_path()` 로 계산하지 말 것.**
  conftest 가 `DATA_DIR` 을 tmp 로 돌리므로 감시자 판정이 **뒤집힌다**(실측 2건).
  `PROJECT_ROOT/data` 로 고정한다.
- 상세: `docs/handoff/KIT_APP_GENERATION_2026-08-23.md`

### 🔔 2026-09-19 (3) — Claude Code · 안내 수명 보완 · 미리보기 조사 종료

- **검토 요청: `docs/handoff/CLAUDE_REVIEW_REQUEST_PREVIEW_2026-09-19.md`** (Codex 앞).
  지시서 `CODEX_DOWNLOAD_REVIEW_NEXT_2026-09-19.md` 의 세 가지를 모두 끝냈다.
- **제품 변경은 프런트 2파일뿐이다** — `factory/RunControls.tsx` · `components/ControlPanel.tsx`.
  서버·권한 정책·CORS **무변경**. 커밋·푸시 없음.
- ⚠️⚠️ **`result.projectId !== pid` 는 «자기 자신과의 비교» 였다.** `pid` 는 요청을 시작한
  렌더의 클로저 값이라 결과와 언제나 같다. 화면을 바꿔도 통과했고, 구 통제실의 `alert` 는
  **전역**이라 남의 화면 위에 떴다. 이제 **완료 시점의 store** 와 화면 생존을 본다.
  → 같은 모양의 「대상 확인」이 다른 비동기 호출부에도 있는지 각자 한 번씩 봐 주기 바란다.
- **앱/보고서/문서 미리보기는 정상이라 아무것도 바꾸지 않았다.** 기존/신규가 같은
  `/state/latest` 스냅샷을 읽고, 새 Studio 는 기존 `PreviewPanel`·`ManualRenderer` 를
  그대로 재사용한다. 합성 산출물로 실제 클릭 이동해 앱 실행·판정칩·문서·빈 결과 두 종류를
  모두 확인했다.
- ⚠️ **계측 함정 둘(둘 다 제품 결함이 아니었다).**
  ① **fixture 가 에이전트 id 를 지어내면 화면이 「0단계 완료」로 보인다.** 정본은
     `core/agent_registry.py` 이고 id 는 `Frontend`(≠ `Frontend_Dev`)다. 필드 이름도
     `factoryViewModel.ts` 의 `STAGE_DOC_FIELDS` 를 보고 맞출 것.
  ② **브라우저 뷰포트를 강제로 바꾸면 그 뒤 클릭이 아무 데도 닿지 않는다.** 화면이 반응하지
     않으면 제품을 의심하기 전에 **다른 버튼도 안 눌리는지**부터 보라. 뷰포트를 되돌리면
     같은 클릭이 한 번에 된다.
- `<details>` 안에 든 버튼은 **접혀 있으면 접근성 트리에 없다.** 좌표 클릭이 빗나간 원인이
  이것이었다 — summary 를 먼저 누르면 정상적으로 클릭된다.
- §10.1 보존 대상 **17개** 중: 실화면 증거로 닫을 수 있음 **2**(내려받기·미리보기),
  새 Studio 입구 없음 **1**(공유·승격 진입), 서버 지표 부재 **1**(비용),
  코드 연결만 있고 실화면 증거 미기록 **13**. 전체 진척 **21/40=52.5% 유지**(가산 없음).

### 🔔 2026-09-19 (4) — Claude Code · 「검토용 버전 저장」 parity

- **검토 요청: `docs/handoff/CLAUDE_REVIEW_REQUEST_RELEASE_SAVE_2026-09-19.md`** (Codex 앞).
- ⚠️⚠️ **구 통제실이 «미확정» 을 «실패» 로 단정하고 있었다.** 이 명령의 `outcome` 은
  ACCEPTED·REJECTED·**UNKNOWN** 셋인데 `r.ok` 하나로 갈랐다. UNKNOWN 은 「안 됐다」가
  아니라 「됐는지 모른다」다 — 실패라고 들으면 사용자가 **다시 누르고 같은 결과물이 두 벌**
  저장된다. 공용 함수가 원키로 막으려던 사고를 화면이 되살리고 있었다.
  → **`ok` 불리언 하나로 세 결과를 가르는 곳이 더 있는지** 각자 한 번씩 봐 주기 바란다.
- 전역 `alert` 가 남의 화면 위에 뜨는 문제도 같은 자리에 있었다(완료 시점 비교로 고침).
  직전 라운드의 내려받기 보완과 **같은 모양**이다.
- **새 Studio 는 이미 맞았다** — 공용 `command` 가 미확정을 보존하고 새 요청을 **잠근다**.
  남는 비대칭은 구 화면에 그 잠금이 없다는 것 하나이고, C3 에서 지울 화면이라 보류했다.
- 프런트 **189 PASS**(project 64→66) · contracts 157 · tsc · build 통과. 변이 6종 각각 물림.
- 서버·권한 정책 무변경. 제품 변경은 `frontend/src/components/ControlPanel.tsx` 한 파일.
- **실화면 수용 완료** — 실제 클릭 → `POST execution-commands` 200 → 영수증 조회 →
  목록 0건→1건 · `lifecycle_status "candidate"`(**저장 ≠ 승격**이 서버 기록으로도 확인).
- ⚠️⚠️ **「다시 누르면 두 벌 저장된다」는 실측된 사실이다.** 한 번 더 눌러 2건을 만들고
  두 릴리스 본문을 비교했다 — `release_id`·시각을 빼면 **지문이 같다**(길이 2177 동일).
  그 사이 실행은 없었다. **원키는 「같은 요청의 재시도」만 막는다** — 손가락으로 다시 누른
  것은 새 요청이다. 안내 문구가 유일한 방어이므로 그 문구가 틀리면 바로 사고가 된다.
  진척 **21/40=52.5% 유지**(가산 없음). 격리 DB 합성 릴리스 2건은 원복 대상.

### 🔔 2026-09-19 (5) — Claude Code · 구 통제실 명령 결과 처리 8자리

- **검토 요청: `docs/handoff/CLAUDE_REVIEW_REQUEST_LEGACY_COMMANDS_2026-09-19.md`** (Codex 앞).
- 앞 글에서 부탁한 「`ok` 하나로 세 결과를 가르는 곳」을 **내가 먼저 훑었다.** 새 Studio 는
  전부 공용 `command` 를 지나 깨끗했고, **구 통제실 한 파일에 여덟 자리**가 모여 있었다.
- ⚠️⚠️ **「수정 요구」는 눌러도 아무 일도 일어나지 않는 상태였다.** 서버가 옛 접수를 닫아
  `POST /sprint/revision` 이 **항상 409**(`REVISION_REQUEST_REQUIRED`)인데, 화면은 `res.ok`
  가 아니면 **아무 말도 하지 않았다**. 사용자는 자기가 잘못 눌렀다고 읽는다.
- ⚠️⚠️ **「중단」은 결과를 버리고 무조건 「정지했습니다」라고 말했다.** 실행 중 작업이 없으면
  서버는 409 다(실측). **가동이 도는 동안 멈췄다고 믿는 것**이 가장 위험한 거짓이다.
  「일시정지」도 같은 모양이었고, 이 화면만 `/sprint/pause` 로 직접 POST 하고 있었다 →
  새 Studio 와 **같은 공용 명령**으로 옮겼다(서버 핸들러가 같다는 것을 확인하고).
- ★ 공용 판정 `tellCommandResult` 하나로 모았다. **`'ok'` 일 때만 후속 상태를 갱신한다** —
  미확정에 진행 손잡이·보류 지점·작업 기록을 지우면, 사용자는 진행을 보지도 멈추지도
  못한 채 다시 누르고 그것이 **유료 LLM 재실행**이 된다.
- 프런트 **195 PASS**(project 66→72) · contracts 157 · tsc · build. 변이 8종 각각 물림.
- ⚠️ **실클릭은 NOT_RUN** — 여덟 자리가 전부 유료 LLM 실행을 시작하거나 그 실행 중에만
  나타난다. 대신 서버 응답을 격리 서버에 직접 물어 확인했다(409×3, 상태 변경 없음).
- 서버·권한 정책 무변경. 진척 **21/40=52.5% 유지**(가산 없음).

### 📮 2026-09-19 — Claude Code → **Codex 검토 인계**

- **정본 인계: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-19.md`** ← 여기부터 읽어 주세요.
  세 라운드 요청서를 읽는 순서와, 판단이 필요한 항목을 한곳에 모았습니다.
- 대기 상태입니다. **지시 전에는 다음 항목에 착수하지 않습니다.**

**판단을 구하는 4건**

1. **미확정 잠금** — 구 통제실은 문구로 말릴 뿐 버튼을 잠그지 않습니다. 새 Studio 는
   공용 `command` 가 잠급니다. 「두 벌 저장」을 실측한 이상 문구만으로는 약합니다.
2. **「수정 요구」 방향** — 닫힌 옛 접수를 «안내로 막기» 로 끝냈습니다. 다시 배선하면
   새 Studio 흐름이 두 벌이 되고, §10 이 C3 에서 지울 화면입니다.
3. **`/sprint/pause` 직접 호출의 다른 소비자**가 있는지 — 저는 보지 못했습니다.
4. **한 번의 실제 제작 가동을 승인할지** — §10.1 의 다섯 항목(기획 시작·한도 대기·
   일시정지/중단/재개·재분할·수정 요구)은 **유료 LLM 실행이 돌아야만** 화면에 나타납니다.
   그 승인 없이는 이 다섯의 실클릭이 영구 NOT_RUN 입니다.

**실측값(제 실행값입니다)**: 프런트 **195 PASS / 0 FAIL**(project 72 · release 38 ·
draft-open 29 · draft-entry 17 · location 25 · kit-app 14) · contracts 157 · tsc · build 통과 ·
변이 17종 전부 단독으로 물림.

**진척 21/40=52.5% 유지**(가산 없음). 서버·권한 정책 무변경. 푸시 없음.

### 🔔 2026-09-19 (6) — Claude Code · 미확정 잠금 §1 · 수정 요구 안내 §2 완료

- 지시: `docs/handoff/CODEX_REPLY_TO_1521_HANDOFF_2026-09-19.md`. 제품 변경은
  `frontend/src/components/ControlPanel.tsx` 와 `factory/StudioExecutionRequests.tsx`(훅 수출 1줄).
- ⚠️⚠️ **제 주장 하나를 정정합니다.** 「다시 누르면 두 벌 저장된다」는 **미확정 중 중복
  전송의 증거가 아니었습니다.** 공용 `executeStudioCommand` 가 첫 POST 전에 UNKNOWN 을
  기록하고 PAUSE/STOP 외 새 명령을 **거절**합니다(소스 확인). 제가 만든 릴리스 2건은 각각
  확정된 **두 번의 명시적 저장**이었습니다. 멱등성 결함을 실증한 것이 아닙니다 —
  제품 문구·주석·시험 단언에서 과장을 걷어냈습니다.
- 그래서 §1 은 「잠그는 일」이 아니라 **「왜 막혔는지 보이게 하고 원요청 조회 입구를 주는
  일」** 이었습니다. 공용 훅 `useExecutionPending` 을 수출해 그대로 쓰고(세 번째 구독 사본
  없음), 기존 `StudioExecutionRequests` 를 미확정일 때만 띄웁니다.
  **일시정지·중단·내려받기는 잠그지 않습니다** — 미확정일수록 멈출 수 있어야 합니다.
- 「최종 결과물 저장 **(배포)**」 라벨을 **「검토용 버전 저장」**으로 맞췄습니다(배포·승격 별도).
- §2 **수정 요구는 이제 아무 데도 보내지 않습니다.** 안내를 보이려고 실패할 요청을 보내는
  것은 서버·감사 로그에 쓸데없는 자국을 남깁니다. 기존 입구를 이름으로 알리고 입력은
  보존합니다. 구 화면에 편집기·계약을 다시 만들지 않았고 App 도 고치지 않았습니다.
- 프런트 **197 PASS**(project 72→74) · contracts 157 · tsc · build. 변이 6종 각각 물림.
- ⚠️ 실클릭 NOT_RUN — 미확정 상태를 만들려면 유료 LLM 실행이 필요합니다.
  **유료 제작 1회는 여전히 사용자 승인 대기**입니다. 진척 21/40=52.5% 유지.

### 🔔 2026-09-20 — Claude Code · D01 「롤백 화면」 수용 1건 마감 (제품 변경 0)

- 기록: `docs/handoff/CLAUDE_D01_ROLLBACK_ACCEPTANCE_2026-09-20.md`.
- **진척 21/40=52.5% 는 마지막 인정치로 유지합니다.** 칸 판정은 제 몫이 아니며,
  이 문서는 수용 «증거»입니다. 이번에 마감한 사용자 흐름 1건과 남은 조건 수만 보고합니다.
- 제품 화면에서 실제 포인터·키보드로 끝까지 밟았습니다 — 워크스페이스 → 게이트 점검 →
  운영에서 내리기 → 사유 입력 → 사용 중단 → 릴리스 관리 → 사용 재개.
  **사유가 비면 확인 버튼이 `disabled`** 였습니다(경고만 하고 눌리는 구조가 아님).
  서버 `state: disabled` + 사유 보존, **옆 릴리스는 그대로**, 감사 이력 3건이 행위자·사유와
  함께 남습니다. 완료 고지가 **「이미 배포된 코드는 되돌리지 못한다」** 는 한계까지 말합니다.
- ⚠️ **판단 요청 2건(고치지 않음)**
  ① 「사용 재개」 뒤 상태가 원래 값 `candidate` 가 아니라 `active` 입니다 — 설계인지 결함인지.
  ② 릴리스 선택 목록에서 **같은 프로젝트의 두 판이 같은 이름**으로 보입니다
     (`display_name || project_name`). 되돌리기 어려운 화면에서 어느 판인지 구별이 안 됩니다.
     라벨 규칙은 여러 화면이 공유하므로 지시를 받고 고치겠습니다.
- ⚠️ **제 계측 실수 3건**(전부 보고 전에 자체 적발, 제품 결함 아님): 추천 질문 칩을 버튼으로
  셈 / **체크박스를 머리글로 읽음** / **상세 창을 목록으로 읽음**. 그리고 **`form_input` 으로
  넣은 select 값은 React 가 못 봅니다** — 실제 포커스+키보드로 해야 반영됩니다.
- 남은 D01 수용 조건: **즉시 검증 가능 4건**(진입·페이지 이동·오류·권한, 브라우저 재확인) ·
  **사용자·자료 필요 1건**(반복 업무). D07 은 실제 인증 사용자·실자료가 주 장애물이라
  비용 승인으로 풀리지 않습니다(앞서 정정).
- 격리 DB: 합성 릴리스 1건이 `candidate → disabled → active`. 원복 목록에 반영했습니다.

### 🔔 2026-09-20 (2) — Claude Code · D01 「즉시 검증 가능」 4건 실측 · **권한 구멍 1건**

- 기록: `docs/handoff/CLAUDE_D01_ACCEPTANCE_4CONDITIONS_2026-09-20.md`. **제품 코드 변경 0.**
  진척 21/40=52.5% 는 마지막 인정치로 유지합니다.
- **진입·페이지 이동·오류 = 통과.** 없는 대상은 열리지 않고 「현재 회사·권한에서 …」로 답하며
  `entry-metadata` 404 **한 건**만 나갑니다. 앱 안 뒤로 가기에서는 **미저장 입력 보호가
  정확히 뜹니다**(주소 안 움직임 · 입력 보존 · 선택지 5개).
- ⚠️⚠️ **권한 — 목록·진입은 막는데 릴리스 «단건 조회» 만 열려 있습니다.**
  ```
  proj_sent_synthetic/entry-metadata   → 404
  library/list                         → 그 릴리스 «없음»
  library/item/rel_sent_synthetic_01   → 200 + 산출물 전문(요구정의~추적성 전 탭)
  ```
  `library/list` 는 주석대로 「보이는 프로젝트 집합」 밖을 건수까지 빼는데, **같은 규칙이
  `library/item` 에 없습니다.** 한쪽 문만 막고 거울 쪽을 열어 둔 형태입니다.
  ★ 다만 404 로는 「없는 것」과 「안 보이는 것」이 구별되지 않아 **「다른 회사 것이 보인다」를
  실증한 것은 아닙니다.** 그래도 소유자 없는 릴리스가 모두에게 열리는 것도 같은 구멍입니다.
  **서버 권한·은닉 계약이라 제가 고치지 않았습니다 — 지시를 구합니다.**
- ★ 관찰(결함 아님): 입력 보호는 **앱 안 이동**만 막습니다. 주소창 직접 진입 뒤의 뒤로 가기는
  문서 이동이라 막히지 않고 입력이 사라집니다. 가드 주석이 그 경계를 이미 적어 두었고
  `beforeunload` 를 새로 넣지 않았습니다 — 수용 여부는 판단 사안입니다.
- ⚠️ 제 계측 실수 2건 추가(보고 전 자체 적발): **문서 이동으로 입력 보호를 시험**하고 결함으로
  적을 뻔함 / 타이핑이 들어갔는지 확인 없이 이동함. 이번 두 문서 합쳐 5건이고 전부 제품
  결함이 아니었습니다. 공통 원인은 **재는 방법을 먼저 정하지 않은 것**입니다.
- 남은 D01: 마감 4건(롤백·진입·이동·오류) / 결함 보고 1건(권한) / 미착수 1건(반복 업무).

### 📮 2026-09-20 — Claude Code → **Codex 검토 인계**

- **정본 인계: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-20.md`** ← 여기부터 읽어 주세요.
  대기 상태입니다. **지시 전에는 다음 항목에 착수하지 않습니다.**

**결정이 필요한 것 1건 (가장 급함)**

- **릴리스 «단건 조회» 에 가시성 규칙이 없습니다.** `library/list` 는 「보이는 프로젝트 집합」
  밖을 건수까지 빼는데 `library/item` 은 같은 규칙 없이 200 + 산출물 전문을 줍니다.
  ★ 다만 404 로는 「없는 것」과 「안 보이는 것」이 구별되지 않아 **「다른 회사 것이 보인다」를
  실증한 것은 아닙니다.** 서버 권한·은닉 계약이라 **고치지 않았습니다.**
  고친다면 `library/item` 에 같은 가시 집합을 적용하는 수준으로 보이나, **「소유자 없는
  릴리스」 처리 방침**이 함께 정해져야 합니다.

**판단 요청 3건** — ① 「사용 재개」 뒤 상태가 `candidate` 가 아니라 `active` ·
② 릴리스 목록에서 같은 프로젝트의 두 판이 **같은 이름**으로 보임 ·
③ 입력 보호가 **앱 안 이동만** 덮는 경계를 수용할지.

**마감한 사용자 흐름 4건**(비과금·실제 포인터/키보드): 롤백 · 진입 · 페이지 이동 · 오류 화면.
**남은 D01 수용 조건 2건**: 권한(위 결정 대기) · 반복 업무(사용자·자료 필요).

**실측값(제 실행값)**: 프런트 **197 PASS / 0 FAIL** · contracts 157 · tsc · build 통과 ·
변이 6종 각각 물림. **진척 21/40=52.5% 는 마지막 인정치로 유지합니다** — 제가 올리지 않습니다.

⚠️ 이번 구간 제 계측 실수 **5건**을 인계문 §5 에 전부 적었습니다(보고 전 자체 적발, 제품
결함 아님). 공통 원인은 재는 방법을 먼저 정하지 않은 것이고, 재발 방지 절차도 함께 적었습니다.

### 🔔 2026-09-20 (3) — Claude Code · **RELEASE-READ-VISIBILITY-01 (P1) 보완 완료**

- 기록: `docs/handoff/CLAUDE_RELEASE_READ_VISIBILITY_2026-09-20.md`. 지시대로 권한 한 건만.
- 수정: `api/routes/factory_control.py` 의 `get_release` — 목록과 **같은** 가시성 판정을
  fail-closed 로 적용(없는 릴리스와 **동일한 404**), 상태 확인 실패 시 **실행 payload 차단**,
  읽기 오류의 예외 원문·경로 비노출. 권한표·역할·CORS 무변경. 자료 무변경.
- 대조(수정 후): 비가시 릴리스 **404·코드 0** / 없는 릴리스와 **같은 문구** / 가시 릴리스 **200 정상** /
  목록 2건 회귀 없음. 화면 직접 링크도 같은 결과.
- 시험 신규 8 + 기존 2 통과(격리 러너). 극성 2건 — 가드 제거 시 **6 failed / 2 passed**
  (음성 실패·양성 통과), payload 차단 되돌리면 1 failed. 대역이 아닌 **실제 판정 경로** 1건 포함.
- ⚠️⚠️ **팀 전체가 걸릴 함정: 주트리를 고치고 격리 화면으로 재면 «옛 코드» 를 잽니다.**
  격리 서버는 워크트리 `C:\sentwt` 사본을 실행합니다. 서버를 재기동해도 200 이 그대로라
  처음엔 「수정이 안 먹었다」로 보였습니다. 그 한 파일만 동기화하니 404.
  → **원복 대상 추가: `C:/sentwt/api/routes/factory_control.py`**
- ⚠️ 시험 fixture 가 정본 계약과 달라 **양성 대조가 두 번 «제품 결함처럼» 빨강**이었습니다 —
  `scope` 대역에 `unrestricted` 없음 / `enterprise_scope_id` 를 비워 `RESOURCE_UNBOUND`.
  고치기 전에 정본 판정 함수를 직접 불러 사유를 찍어 확인했습니다.
- 주석 정정: `tellCommandResult` 의 「유료 LLM 재실행 … 둘 다 실측했다」 → **위험 가능성이며
  실측된 사건이 아님**(재전송은 공용 계층이 막고, 이 파일은 LLM 을 실행한 적 없음).
- ★ **「다른 회사 자료 유출」을 실증한 것은 아닙니다** — 없는 소유 프로젝트와 실재하는 타
  문맥은 다르며, 후자는 시험 안 격리 fixture 로만 만들었습니다.
- 다음: A 재개 상태 의미 10~15분 / B 라벨 10~15분 / C 문서 이탈 원인 확인.
  진척 **21/40=52.5% 마지막 인정치 유지**.

### 🔔 2026-09-20 (4) — Claude Code · A 재개 상태 «조사» · B 라벨 «구현»

- 기록: `docs/handoff/CLAUDE_REACTIVATE_AND_LABEL_2026-09-20.md`.

**A — 조사만 했고 서버는 고치지 않았습니다.**
- `reactivate` 는 `set_status(ACTIVE)` 무조건이고, `set_status` 에는 **전이 정책이 없습니다**.
- `CANDIDATE` 는 `USABLE` 에 없고 `audience_for_state` 가 candidate→PREVIEW,
  active/deprecated→OPERATIONAL 로 가릅니다. 따라서 **끄고 켜기만으로 Preview 전용 후보가
  운영 청중이 됩니다** — 승인·승격 절차 없이. `audience_for_state` 가 나눠 둔 의미가 이
  경로로 사라집니다.
- ★ 실증 범위: 상태값 전이는 실측. **그 판이 운영 데이터를 만졌다거나 권한을 우회했다는
  것은 실증하지 않았습니다**(운영 실행·승격 안 함).
- 최소안: `program_status_history.from_status` 에 **복원 재료가 이미 있습니다.** 마지막
  `to_status=DISABLED` 이벤트의 `from_status` 로 되돌리고, **이력이 없거나 값이 이상하면
  추정하지 말고 거절**(지금은 ACTIVE 로 떨어집니다). 함께 정할 것 — 화면 문구, 승격됐던
  판의 처리. **구현은 지시 대기입니다.**
- 보고 표기(지시대로): 사용 중단·이력 보존 확인 / 사용 재개 호출 확인 / **이전 상태 복원 미완료**.

**B — 라벨 구현 완료.**
- `WorkspacePanel.releaseLabel` = `이름 · 게시 시각 · release_id`, 선택 목록도 **같은
  formatter**. `App` 이 `createdAt` 을 실어 줍니다. 시각은 같을 수 있어 **id 를 항상** 붙이고,
  없으면 **「시각 미기록」**(만들어 채우지 않음). 선택값·제목·저장 데이터 무변경.
- 브라우저 실측: 종전 「prj_ddb…」 둘 → 이제 시각·id 로 구별됩니다.
- ⚠️ **확인창 렌더 문자열은 NOT_VERIFIED** — 같은 formatter 를 쓰도록 연결돼 있으나, 이번 턴에
  네이티브 `<select>` 키보드 선택이 재현되지 않아(앞 라운드엔 됐습니다) 화면에서 못 봤습니다.
  **의도된 미표시가 아니라 도구 한계**입니다.
- 프런트 197 PASS · contracts 157 · tsc · build 통과. 진척 21/40=52.5% 유지.
- 남은 것: C 문서 이탈 보호 «원인 확인» 미착수.

### 🔔 2026-09-20 (5) — Claude Code · C 문서 이탈 보호 «원인 확인» 완료

- 기록: `docs/handoff/CLAUDE_C_DOCUMENT_LEAVE_CAUSE_2026-09-20.md`. **제품 변경 0**,
  새 `beforeunload` 추가 0.
- **결론: 제품 보호는 등록·발화·`preventDefault()` 까지 정상입니다.** 이동이 진행된 것은
  **자동화가 확인창을 처리(무시)했기 때문**입니다. 제 앞선 「앱 안만 보호하는 설계」 해석을
  **철회합니다** — Codex 지적이 맞았습니다.
- 제한 재현(제품 핸들러 «뒤»에 붙인 측정 리스너로 `defaultPrevented` 만 읽음):
  ```
  미저장 입력 있음 → {"fired":true,"defaultPrevented":true}   ← 제품이 실제로 막았다
  입력 없음(음성)  → {"fired":true,"defaultPrevented":false}  ← 등록되지 않았다
  ```
  두 경우가 갈리므로 계측기가 늘 true 를 내는 것이 아닙니다.
- **NOT_VERIFIED(도구 한계)**: 브라우저가 사용자에게 확인창을 띄우는지, 취소/계속을 고르면
  각각 어떻게 되는지. `force` 를 주지 않았는데도 이동했습니다. **사람이 한 번 눌러 보면
  닫히는 항목**입니다.
- 「입력이 사라졌다」 관찰은 보존하되 원인은 자동화입니다. 문서 이동에서 입력이 사라지는 것
  자체는 예상 동작입니다(`studioInputMemory` 는 모듈 Map — 새로고침을 넘기지 못함).
- 등록 위치(소스): `BuildStartDialog`(`hasInput && !saved` 또는 PENDING/UNKNOWN) ·
  `AdaptiveProductionStudio`(`studioInputMemory.hasInputs`). 후자는 **소스 확인만** 했습니다.
- 진척 **21/40=52.5% 유지**. 남은 것: A 최소안 구현(지시 대기) · B 확인창 렌더 문자열.

### 🔔 2026-09-20 (6) — Claude Code · A 「사용 재개」 최소안 **구현 완료**

- 기록: `docs/handoff/CLAUDE_A_REACTIVATE_RESTORE_2026-09-20.md`.
  수정은 **`core/program_lifecycle.py` 한 파일**. API 라우트·권한표·역할·승격 경로 무변경.
- **`reactivate` 가 중단 «직전» 상태로 되돌립니다** — 무조건 `ACTIVE` 가 아닙니다.
  종전에는 끄고 켜는 것만으로 `candidate`(Preview 후보)가 **운영 청중**이 됐습니다.
  같은 자리에서 **`data_fingerprint` 도 지워지고** 있었습니다(`set_status` 가 덮어씀).
- 재료는 이미 있던 것만 씁니다 — `program_status_history.from_status`·`data_fingerprint`.
  새 열·새 권한 없음. 감사 이력은 지우지 않고 **한 줄 더** 쌓습니다.
  **이력을 모르면 추정하지 않고 거절**합니다(「모르면 활성」이 바로 그 사고였습니다).
  중단 상태가 아니면(deprecated 경고 해제 등) **종전 동작 그대로** — 전이 정책 일괄 변경 없음.
- 시험 신규 7 + 기존 회귀 26(lifecycle 22 · usable 4) 통과. 극성 3건 각각 물림
  (종전 동작 복원 시 **5 failed**). 상태값만 보지 않고 `audience_for_state` 로 **의미가
  갈리는지**까지 확인했습니다.
- 제품 HTTP 라우트 실측: `candidate → disable → reactivate → **candidate**`,
  사유에 「중단 직전 상태로 되돌림(candidate)」이 남습니다. 화면 클릭 증거와 섞지 않습니다.
- ⚠️ 한계: 이력 읽기와 `set_status` 쓰기가 **한 트랜잭션이 아닙니다**(이력은 append-only라
  읽은 값은 안 바뀝니다). 완전한 원자성은 `set_status` 구조 변경이 필요해 최소안 밖으로 뒀습니다.
- ⚠️ **원복 대상 추가: `C:/sentwt/core/program_lifecycle.py`.** 서버는 워크트리, **프런트는
  주트리**에서 뜹니다 — 서버 파일을 고쳤으면 동기화해야 격리 실측이 새 코드를 잽니다.
- 이미 `active` 가 된 fixture(`…150827`)는 **원복 완료로 쓰지 않습니다**(마지막 중단 직전이
  `active` 라 자가 복원되지 않음).
- 함께 정해야 할 것: ① 화면 문구(「사용 재개」인데 운영에서 안 도는 결과) ② 승격됐던 판의 처리.
- 진척 **21/40=52.5% 유지**.

### 📮 2026-09-20 (2차) — Claude Code → **Codex 검토 인계**

- **정본 인계: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-20_B.md`** ← 여기부터.
  `CODEX_D01_REVIEW_NEXT_2026-09-20.md` 의 **§2·§3-A·§3-B·§3-C 네 건 모두** 마쳤습니다.
  대기 상태이며 지시 전에는 다음 항목에 착수하지 않습니다.
- 지시 밖에서 **두 건을 더 고쳤습니다** — 과했다면 되돌리겠습니다.
  ① `reactivate` 가 `data_fingerprint` 를 지우고 있었음(A 최소안에 포함).
  ② **구 통제실 내려받기는 성공하면 아무 말도 하지 않았음** — 실제 클릭으로 확인
     (`export` 200 · alert 0건). 같은 파일에서 이미 고친 여덟 자리와 같은 유형이라 한 줄 더함.
- 실측: 서버 관련 시험 **67 passed**(격리 러너) · 프런트 **197 PASS** · contracts 157 ·
  tsc · build. **극성 6종 각각 물림.** 전부 제 실행값입니다.
- 브라우저: 비가시 릴리스 거절 / 가시 정상 / 라벨·확인창에 시각·id / 확인창 취소 시 상태 불변 /
  구 통제실 내려받기 실클릭 성공 안내 / 재개 `candidate→disable→reactivate→candidate`.
- **사람 또는 승인이 필요한 미검증 5건**을 인계문 §4 에 적었습니다. 그중 둘은
  **사람이 한 번 눌러 보면 닫힙니다**(문서 이탈 확인창, 구 화면 저장 `confirm()`).
- ⚠️ 트리에 **제 것이 아닌** 새 파일이 있습니다 —
  `docs/roadmap/NCP_OPERATIONAL_TRIAL_CICD_2026-09-20.md`. 건드리지 않았고 커밋에서 제외합니다.
- ⚠️ 원복 대상 갱신: 워크트리 동기화 2파일(`factory_control.py`·`program_lifecycle.py`),
  격리 fixture 에 `project_name` 추가, 격리 DB 릴리스 상태 변화.
- 진척 **21/40=52.5% 마지막 인정치 유지** — 제가 올리지 않습니다.

### 🔔 2026-09-21 — Claude Code · 재개 R1·R2·R3 마감 + DB-0 차이 지도(조사)

기록: `docs/handoff/CLAUDE_REACTIVATE_R1R2R3_2026-09-21.md` ·
`docs/handoff/CLAUDE_DB0_DELTA_AND_FIRST_SLICE_2026-09-20.md`.

- **재개 마감**: 지적 3건 모두 제 코드의 실제 결함이었고 고쳤습니다.
  **R1** 중단이 아니면 **불변 반환**(`restored: False`) — 앞선 「중단 아니면 ACTIVE」가 같은
  구멍을 다시 열었습니다. **R2** 지문·대체 대상을 **중단 직전 그 한 행**에서 통째로 읽습니다
  (빈 값도 값 — 과거 값으로 채우지 않음). **R3** `set_status` 가 `BEGIN IMMEDIATE` 로 잠그고
  직전 상태를 **트랜잭션 안에서** 읽으며 `expected_status` CAS 로 거절합니다(프로세스 간 유효).
  집중 시험 **13 passed**(7→13) · 회귀 48 · **극성 3종 각각 물림**.
- ⚠️ **배포 차단으로 표시**: `POST /programs/{id}/status` 는 여전히 `candidate → active` 를
  그대로 통과시킵니다. **제품 프런트 소비자는 없습니다**(관리 API 전용).
  최소 차단안만 제시했고 **승격 근거의 정의는 승인 경계 결정이라 제가 정하지 않았습니다.**
- **DB-0(조사)**: 기준선 **18파일/71표/DDL 9곳 → 현재 20/95/16**.
  새 파일 `app_data_preview.db`·`policy_shadow.db`. 원본 **읽기 전용**(`--write` 없이), 기동·seed 0.
- ⚠️ **DB 만 보면 절반을 놓칩니다** — 프로젝트 상태·릴리스 «본문» 은 파일이고 릴리스 «상태» 는
  DB 입니다. **둘을 묶는 트랜잭션이 없습니다.** 명령 영수증은 상담용 `advisor.db` 에 얹혀 있고,
  그 표는 운영본에 **아직 만들어지지도 않았습니다**(최초 사용 시 생성).
- 첫 수직 경로는 지시대로 **로그인→세션→SSE 티켓 1회 소비**. 티켓 소비는 이미
  `UPDATE … WHERE consumed_at='' ` + rowcount 로 **원자적**이고, 이관에서 그 조건절을 잃으면
  안 됩니다(코드의 `_lock` 은 다중 인스턴스에서 아무것도 보장하지 않습니다).
  **auth 표만 옮기면 안 되고** 조직 정본 4표가 함께 가야 합니다.
- ⚠️ **PostgreSQL 실행 환경이 없습니다.** DSN·도구 준비가 조건이며 클라우드 생성·실자료 이전은
  승인 대상으로 남깁니다. `scripts/data_migration.py` 는 실행하지 않았습니다.
- 미검증 보존: native dialog · 디스크 저장 · 실사용 반복 업무 · 유료 제작.
  격리 로그인이 다시 사라져 **재개 제품 HTTP 재확인(5분)** 만 대기 중입니다.
- 진척 **21/40=52.5% 마지막 인정치 유지**.

### 🔔 2026-09-21 (2) — Claude Code · **DB-1 첫 adapter 착수 완료**

기록: `docs/handoff/CLAUDE_DB1_FIRST_ADAPTER_2026-09-21.md`.
⚠️ **PostgreSQL 서버는 없습니다** — PG 경로는 한 번도 실행되지 않았습니다.

- 새 파일: `core/db/__init__.py`(방언 한 곳) · `core/db/schema/001_auth_and_context.sql`
  (첫 슬라이스 7표 **설치** DDL) · `tests/test_db_adapter_first_slice.py`(13건).
  `core/auth.py` 는 **주입점 한 곳만** 열었고 **SQL 은 한 글자도 안 바꿨습니다.**
- 방언 차이는 연결 wrapper 가 실행 직전에 흡수합니다 — 로그인 경로의 SQL 을 손으로 다시
  쓰는 것이 이관 첫 걸음에서 가장 위험합니다. **기본값은 지금 그대로 SQLite** 입니다.
- ⚠️ **조용한 실패를 두 곳에서 막았습니다**: `AFS_DB_BACKEND` 오타 → 거절,
  PG 인데 DSN 없음 → 멈춤. 조용히 SQLite 로 떨어지면 「PG 로 돌고 있다」고 믿는 채
  파일 DB 에 쓰게 되고 그 사고는 한참 뒤에 발견됩니다.
- ⚠️ **번역은 단순 치환이면 안 됩니다** — 리터럴 안의 `?`, `LIKE '%수%'` 의 `%` 가 깨집니다.
  리터럴을 추적하며 옮기고 `%`→`%%` escape 합니다(시험으로 잠금).
- ⚠️⚠️ **이관 대사 첫 항목**: SQLite 는 `consumed_at=''`(빈 문자열=미사용), PG 판은
  `TIMESTAMPTZ NULL` 입니다. **`'' → NULL` 이관과 조건절(`=''` → `IS NULL`) 이 함께 가야**
  합니다. 어긋나면 모든 티켓이 이미 쓴 것으로 보이거나 반대로 무한 재사용됩니다.
- 시험 13 passed · **극성 3종 각각 물림** · 회귀(auth 21 + SSE 14 = 35) 무변경.
- 남은 것: 빈 DB 설치·사본 대사·권한 거절·복구 검사는 **DSN 준비 후**. 큐/lease/fencing·
  durable SSE·파일 저장·기동 DDL 제거는 후속 필수 잔여.
- 진척 **21/40=52.5% 마지막 인정치 유지**. 클라우드 미배포.

### 🔔 2026-09-21 (3) — Claude Code · 주입점 확장 (DB-1 후속)

기록: `docs/handoff/CLAUDE_DB1_FIRST_ADAPTER_2026-09-21.md` §후속.

- `core/enterprise_context/repository.py` 와 `core/program_lifecycle.py` 에 **같은 모양의
  `connect=None` 주입점**을 넣었습니다. SQL·DDL 은 한 글자도 안 바꿨고 기본값은 그대로입니다.
  (주입점 모양이 저장소마다 다르면 이관 때 각자 다르게 고쳐집니다 — 시험으로 모양을 잠갔습니다.)
- ⚠️⚠️ **제가 어제 R3 에서 넣은 `BEGIN IMMEDIATE` 는 SQLite 전용 문장입니다** —
  PostgreSQL 에는 없습니다. 문자열로 박아 두면 이관 때 이 한 줄이 조용히 남아 터집니다.
  방언 상수로 바꾸고, PG 에서 같은 효과를 어떻게 낼지는 **부르는 쪽이 주도록** 했습니다.
- ⚠️ **주입이 DDL 부트스트랩을 건너뛰게 만들 뻔했습니다.** 첫 판이 주입 연결을 바로
  돌려줘 `no such table` 이 났고 시험이 그 자리에서 잡았습니다.
  **주입은 「연결을 어디서 얻는가」만 바꾸는 것이지 준비 절차를 건너뛰는 문이 아닙니다.**
- 시험 13 → **20 passed** · **극성 4종 각각 물림** · 회귀 **95건 무변경**
  (db_adapter 20 · program_lifecycle 22 · reactivate 13 · program_usable 4 ·
   auth_password 14 · sse_org 14 · release_item 8).
- 여전히 **PostgreSQL 서버 없음** — PG 경로 미실행. 클라우드 미배포.
  진척 **21/40=52.5% 마지막 인정치 유지**.

### 🔔 2026-09-21 (4) — Claude Code · 기동 DDL 분리 **조사** (코드 없음)

기록: `docs/handoff/CLAUDE_DB0_BOOT_DDL_SEPARATION_2026-09-21.md`.

- **설치 진입점이 없습니다** — 스키마를 만드는 주체가 「먼저 쓰는 요청」입니다.
  `run.py::_apply_installation_settings` 는 설치 «설정» 이지 스키마가 아닙니다.
  `ALTER TABLE ADD COLUMN` **16곳 / 13모듈**(기준선 9곳 → 16곳).
- **왜 무중단 배포의 직접 차단 조건인가**: ① 인스턴스가 둘이면 DDL 이 동시에 돌고 PG 의
  DDL 은 잠금을 잡습니다 ② **Blue/Green 에서 새 버전이 켜지는 순간 옛 버전이 모르는 열이
  생기고, 롤백해도 남습니다** — 스키마가 코드 롤백을 따라오지 않습니다
  ③ `executescript()` 조기 커밋 → 반쪽 적용 ④ 「언제 누가 스키마를 바꿨나」에 답할 수 없습니다.
- **최소 분리안(제안, 구현 안 함)**: `schema_is_managed()` 문 하나 + 각 store DDL 블록을
  **한 줄씩** 감싸기 + 설치 커맨드 하나. **SQL 은 옮기지 않습니다**(옮기면 두 벌이 되고
  한쪽만 고쳐집니다). 기본값은 오늘과 한 글자도 다르지 않습니다.
- ⚠️ **먼저 정해야 할 것 2건**
  ① **열 추가 규칙** — 지금 ALTER 는 `NOT NULL DEFAULT ''` 입니다. Blue/Green 에서 옛 버전이
     그 열을 모른 채 INSERT 하므로 기본값이 없으면 **옛 버전 쓰기가 죽습니다**.
     「새 열은 NULL 허용 또는 DEFAULT 필수」를 스키마 리뷰 규칙으로 둘지.
  ② **`julianday()` 트리거**(`data_preparation/ownership_binding.py`) — PG 에는 없어
     `tstzrange`+배제 제약으로 **재작성**해야 합니다. 이관이 아니라 제약의 재작성이라
     같은 것을 막는지 따로 증명해야 하고 **승인 없이 바꾸지 않습니다. 배포 차단 항목.**
- 다음: 규칙 결정 후 문+13곳+설치 커맨드 60~90분, 동등성 검사 20~30분.
  PG 실제 설치는 **DSN**, 트리거 재작성은 **승인**이 선행입니다.
- 진척 **21/40=52.5% 마지막 인정치 유지**.

### 📮 2026-09-21 — Claude Code → **Codex 검토 인계**

- **정본 인계: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-21.md`** ← 여기부터.
  `CODEX_REVIEW_B_AND_DB_START_2026-09-20.md` §2·§3 **전부 마쳤습니다.**
  `CODEX_DEPLOYMENT_PREP_PACKET_2026-09-21.md` **수신했고 경계를 합쳤습니다**(아래).
- **재개**: 지적 3건 모두 제 결함이었고 고쳤습니다(13 passed · 회귀 48 · 극성 3종).
- **DB**: 차이 지도(20파일/95표/DDL 16곳) · 첫 adapter + 주입점 3곳(20 passed · 극성 7종 ·
  회귀 95) · 기동 DDL 분리 조사. **PG 경로는 여전히 미실행.**
- **프렙 패킷과 합친 것**(지도 두 번 안 쓰기):
  · **DEP-03** — 릴리스 «본문» 이 그 `library/` 에 있고 «상태» 는 DB 입니다.
    **둘을 묶는 트랜잭션이 없어** 디렉터리 교체 시 상태 행이 고아가 됩니다.
  · **DEP-05** — 단순히 `run.py` 로 바꾸면 위험합니다. `_apply_installation_settings` 가
    `data/instance.json` 으로 **`organization_nodes` 를 다시 씁니다**(제가 격리에서 실측해
    트랩으로 기록한 그 동작). 「읽기 설정 검증 / 승인된 초기 설치」 분리가 맞습니다.
  · **DEP-07** — 같은 계열에 **DDL 16곳/13모듈**이 더 있습니다(자리·최소 분리안 문서화).
- ★ **결정 4건이 없으면 제가 더 밀 수 없습니다**: ① 새 열 추가 규칙(NULL 허용/DEFAULT 필수)
  ② `julianday()` 트리거 재작성 승인(배포 차단) ③ 일반 `status` 경로의 승격 근거 정의
  ④ PostgreSQL DSN.
- 다음은 프렙 패킷 §2 대로 **P1: CI/산출물 계약**으로 잡겠습니다. 대기합니다.
- 진척 **21/40=52.5% 마지막 인정치 유지**. 클라우드 미배포 · LLM 0 · 운영 DB 무접촉.

### 📮 2026-09-21 — Claude Code → **P1 배포 산출물 계약 · CI 초안 완료**

- **정본: `docs/handoff/CLAUDE_P1_ARTIFACT_CONTRACT_2026-09-21.md`**
- 만든 것: `scripts/release_artifact.py`(허용목록·내용·**완결성**·manifest · 표준
  라이브러리만) · `tests/test_release_artifact.py`(**24건**) ·
  `.github/workflows/artifact-contract.yml`(**미실행 초안**) · `deploy/README.md` §4 정정.
- ⚠️ **DEP-02 확인**: 「`update.sh` 가 `git archive` 로 추적 파일만 내보낸다」는 **사실이
  아니었습니다.** 그 스크립트에 `git archive` 가 없고 운영 위치에서 `git pull` 합니다 —
  **허용목록은 문서에만 있었습니다.** 문서를 고쳤고, 차단기는 새 검사기 쪽입니다.
- ★ **완결성 검사가 실제로 두 건을 잡았습니다.** 제 첫 초안이 `config.py`(19곳 import)와
  `nodes/` **22모듈**을 빠뜨렸는데 선별·필수·내용 검사는 **전부 초록**이었습니다.
  「조용히 깨진 산출물」이 나갈 뻔했습니다.
- 검사기가 처음 돌자마자 `core/connector_registry.py` 주석의 DSN 예시를 잡았고,
  **예외 목록으로 덮지 않고 그 «모양» 자체를 없앴습니다**(예외 한 줄 = 그 파일 영구 제외).
- `starter_kits/` CSV 71·XLSX 36 때문에 거부를 **DENY_ALWAYS / DENY_FORMAT** 으로 갈랐고,
  예외로 나간 건수(**107**)를 매 실행 결과에 숫자로 남깁니다. **XLSX 는 내용 검사 못 합니다.**
- 검증: 변이 **6종 각각 물림**(원복 해시 일치) · 회귀 63 passed ·
  격리 러너 `sources_unchanged true` · `blocked_file_writes []`.
- ⚠️ **CI 는 NOT_RUN**(Linux 러너·원격 없음). **`update.sh` 는 아직 허용목록을 쓰지
  않습니다** — 배포 동작 변경이라 승인 사항이고 P2 범위로 봅니다.
  [DEP-10] 원격 규칙·요금제·승인 기능은 제 손 밖이라 **「CI 구축됨」이라 보고하지 않습니다.**
- ★ **새 결정 2건**: ① `scripts/**` 를 산출물에서 뺀 것 확인(운영 DB 자료 심는 도구 8종
  포함 · 배포가 부르는 곳 0) ② `starter_kits/` 의 CSV·XLSX 를 내보내는 것 확인
  (**내용물 출처를 제가 확인할 수 없습니다**). 앞선 미결 4건은 그대로 대기.
- 다음: 결정 ①②가 오면 즉시 반영, 없으면 **P2(릴리스 슬롯·준비도)** 로 넘어갑니다.
- 진척 **21/40=52.5% 유지**(배포 기반이라 사용자 흐름 칸이 아닙니다). LLM 0 · 운영 DB 무접촉.

### 📮 2026-09-21 — Claude Code → **P2 서빙 준비도 · 배포 상태 원장**

- **정본: `docs/handoff/CLAUDE_P2_READINESS_AND_DEPLOY_LEDGER_2026-09-21.md`**
- 만든 것: `core/serving_readiness.py` · `core/deploy_ledger.py` ·
  `scripts/serving_readiness_probe.py` · `tests/test_deploy_readiness_and_ledger.py`(**56건**).
- **어휘를 먼저 봤습니다.** `core/release_readiness.py` 는 「이 **릴리스**를 운영에 둬도
  되는가」(§8.2)이고 P2 는 「이 **노드**가 트래픽을 받아도 되는가」로 **다른 것**입니다.
  한 낱말로 부르면 승격 판정이 어긋나므로 `serving_readiness` 로 나눴습니다.
- 판정은 `READY/FAIL/UNKNOWN` 셋이고 **UNKNOWN 도 승격을 막습니다.** 검사 0건이면
  READY 가 아니라 UNKNOWN 이고, **역할 선언이 비어도 UNKNOWN** 입니다(빈 집합끼리
  비교하면 공짜 초록이 나옵니다).
- ⚠️ 준비도는 **없는 DB 파일을 만들지 않습니다**(`mode=ro`). URI 를 문자열로 이어 붙인
  제 첫 판을 **격리 러너가 막아 냈고**, 파일 소유권 오류(`OSError`)에도 죽지 않고
  UNKNOWN 을 내도록 고쳤습니다.
- 원장: 환경 잠금 · 같은 `plan_id` 재요청은 **재실행 않고 현재 상태 반환** ·
  **승인은 digest·설정·이관계획에 결속**(뒤에 바뀌면 승인이 죽음) ·
  **[Z05] 준비 실패 시 승격 없음 + 돌던 계획의 행 무변경** ·
  **`ROLLED_BACK` 은 관측값 대조 뒤에만**.
- 검증: **56건 · 회귀 80 passed · 변이 18종 전부 물림**(원복 해시 일치).
  ★ 두 변이가 처음엔 «안 물렸고», 지우는 대신 원인을 갈랐습니다 — 둘 다
  **「통제 없음」이 아니라 「도달 못 함」**이어서 그 자리에 도달하는 시험을 더했습니다.
- ⚠️ **P1 과 실제로 부딪혔습니다**: 탐침이 `scripts/` 에 있는데 P1 에서 그 디렉터리를
  뺐습니다. 디렉터리째 열지 않고 **이름 한 건만** 되넣었습니다.
- ⚠️ **P2 가 다 끝난 게 아닙니다**: release별 **OS 서비스 슬롯**은 DEP-01(in-place 갱신
  교체)과 한 덩어리라 **승인 사항**이고, 기동 계약은 **읽기 검증 절반만** 했습니다.
- ★ **새 결정 3건**: ① 준비도 HTTP 노출 여부와 그 경계(인증 걸면 LB 가 못 쓰고, 안 걸면
  내부가 샙니다 — 그래서 노드 위 «명령» 으로 만들었습니다) ② 공유 저장소 표식
  `.afs-shared` 를 설치가 놓는 것으로 확정할지 ③ 환경 목록을
  `staging·trial·production` 으로 고정한 것 확인.
- 진척 **21/40=52.5% 유지**. 배포 0 · LB 무접촉 · LLM 0 · 운영 DB 무접촉.

### 📮 2026-09-21(B) — Claude Code → **Codex 검토 인계 (DEP-P1 + DEP-P2)**

- **정본 인계: `docs/handoff/CLAUDE_TO_CODEX_REVIEW_2026-09-21_B.md`** ← 여기부터.
- ★ **작업 도중 도착한 Codex 문서 2건**(`CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION` ·
  `..._INDEPENDENT_REVIEW`)을 **인계문 쓰기 전에 읽었고**, 어긋난 자리 셋을 적었습니다.
- **[INT-01] 수용** — 제 「P1·P2」는 준비 패킷 기준이므로 앞으로 **DEP-P1·DEP-P2** 로
  적겠습니다. OPS-P1(CI)·OPS-P2(관리 backend)와 겹치는 부분을 표로 넣었습니다.
- **[결정 #12] 이미 맞췄습니다** — `core/deploy_ledger.py` → **`ops_control/deploy_ledger.py`**.
  산출물 허용목록에도 안 넣었습니다(`--list | grep ^ops_control/` → **0건**). 회귀 80 passed.
- ⚠️ **[결정 #10] 제 `rollback()` 이 정본과 어긋납니다** — 이전 계획을 되돌리는 «상태
  되감기»입니다. 고칠 방향은 분명하지만 **지금 고치지 않았습니다**: 독립 검토가
  「충돌하는 실행권·완료 상태·승격 API 는 보완된 정본 전 확정 구현 금지」라 했고
  이건 상태 기계 재설계입니다. 정본 `PlanState` 15개 ↔ 제 7개 **대응표**를 넣었습니다.
  ★ 「문서에 적었으니 막았다」고 하지 않습니다 — 실제 봉쇄는
  **`deploy_ledger` 를 부르는 곳이 시험 말고 0곳**(실측)이라는 사실입니다.
- **[INT-02] 지적이 맞습니다** — 제 `build_manifest` 는 **파일 색인**이고 새 §3.1 release
  manifest 가 아닙니다. 빠진 것(archive digest·runtime lock·source/build/workflow 신원·
  SBOM·schema 호환·Linux 실행)을 표로 적었습니다. **제 증거로 `eligible=true` 를 줄 수
  없습니다.** starter kit 의 **경로 예외는 출처 승인이 아닙니다** — 동의합니다.
- 정본 결함 6건과의 접점: `SEC-01/02`·`EXE-01` 은 제 범위 밖, `EXE-03` 순환은 제 승격
  관문엔 **없고**, `EXE-02` 는 제게 lease 개념이 없어 충돌 자체가 없습니다.
- 검증: **DEP-P1 24건 · DEP-P2 56건 · 회귀 160 passed · 변이 24종 전부 물림**.
  ★ 그중 **4종이 처음엔 안 물렸고**, 전부 「통제 없음」이 아니라 **「도달 못 함」**이어서
  그 자리에 도달하는 시험을 더했습니다.
- ★ **결정 8건 대기**(정본 §6 표): ① 원장을 OPS-P2 출발점으로 쓸지/버릴지
  ② `serving_readiness` 위치 ③ 준비도 HTTP 노출 경계 ④ starter_kits 출처
  ⑤ `scripts/**` 제외 확인 ⑥ `.afs-shared` 표식 ⑦ `update.sh` 연결 ⑧ 기존 미결 4건.
- 진척 **21/40=52.5% 유지**. 커밋·푸시 없음 · 배포 0 · LLM 0 · 운영 DB 무접촉.

### 🔔 2026-09-21 (5) — Claude Code · **DEP-R1~R4 최소 보완 완료**

- **정본: `docs/handoff/CLAUDE_DEP_R1R4_REMEDIATION_2026-09-21.md`**
- 회신 `CODEX_REVIEW_DEP_P1_P2_2026-09-21_B.md` 의 **4건 전부 제 실제 결함입니다. 반박 없습니다.**

**해결한 반례**

| 반례 | 후 |
|---|---|
| `Report([Check("probe","TIMEOUT")])` → READY | `Check` 생성에서 거절 + 집계도 UNKNOWN |
| `check_shared_storage([])` → READY | **UNKNOWN** |
| 표식만 있는 디렉터리 → READY | **UNKNOWN**(결정 ⑥ 수용) |
| `DeployLedger()` → 업무 `data/` 에 생성 | **거절** · 모듈에서 `data_path` 제거 |

- **DEP-R2**: 집계를 「FAIL/UNKNOWN 이 없으면 READY」에서 **「전부 명시적 READY 일 때만
  READY」**로 뒤집었습니다. ★ 이건 제가 **역할 검사에서 고쳐 놓고 공유 경로 쪽 문을 안 본**
  것입니다.
- **DEP-R3**: 문구 정정. 인계 §4 의 「실제 증거 쪽」을 취소하고 **「읽기 전용 판정 초안 ·
  관측 공급자 미연결」**로 고쳤습니다. ★★ 그 결과 **지금 구성에서 종합 판정은 READY 가
  될 수 없습니다**(공유 저장소가 늘 UNKNOWN). 시험도 「READY 가 아니다」를 단언하게
  바꿨고, READY 양성 대조는 집계 수준에서 유지했습니다.
- **DEP-R1**: **고치지 않았습니다**(지시대로 이중 작업 회피). 두 반례를
  `ops_control/counterexamples_deploy_ledger.py` 로 **재현 가능하게 보존**했습니다 —
  `promoted_count: 2`, 복귀 실패인데 `ROLLED_BACK`. named in-memory 만 쓰고 파일 쓰기 0.
  pytest 로 두지 않은 이유: 「지금 동작」을 초록으로 단언하면 **시험이 결함을 지켜 줍니다.**
  원장 머리에 「미연결 프로토타입 — 배선 금지」를 명시했습니다.
- 검증: **167 passed**(160→+7) · 변이 5종 각각 물림 · 산출물 검사 ok · `ops_control/` 0건.
  ⚠️ 지적대로 **격리 러너 snapshot 은 `core/api/nodes/tests/scripts` 라 `ops_control/` 을
  포함하지 않습니다** — `sources_unchanged` 를 거기까지 확대하지 않습니다.
- **남은 운영 기능**: 정본 일치 관리 backend · 노드 관측 공급자 · 공유 저장소 결속 증명 ·
  PostgreSQL 준비도 · OS 슬롯/전환 · full manifest·출처 승인 · CI 실행. 전부 미완입니다.
- 다음: **이 묶음은 여기서 끝냅니다.** OPS-P2 는 보완된 정본 이후입니다.
- 진척 **21/40=52.5% 유지**(이번 보완으로 가산 없음). 커밋·푸시 없음 · 운영 DB 무접촉.

### 🔔 2026-09-21 — Claude Code · **지시 CLAUDE-P03-R3-01 수신 · P03.1 완료(READY_FOR_REVIEW)**

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md`** (단계별 누적 · 새 문서 안 늘립니다)
- 수신 기록은 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md` 에. 기준 HEAD `0d0789e97` 일치.
  **순차 소비 검증 추가 지시도 읽었습니다** — 단계마다 검증 묶음/검토 대기로 멈추지 않습니다.
- **다른 세션 변경 보존**: `.agents/DECISIONS.md`·`AI_HANDOFF.md`·`PROGRESS.md`·
  `DECISION_CREATION_CONTRACT_REPAIR_*.json`·`WEB_DEMO_*.md` 는 **열지 않았습니다.**

**P03.1 — 이번에 가능해진 것**: 스키마를 만드는 주체가 「먼저 쓰는 요청」이 아니라
**명시적 설치 명령**이 되었고, 관리 모드 저장소는 기동·첫 조회·재조회에 **DDL 0** 입니다.

- 신규 `core/db/managed_schema.py` · `scripts/install_first_db_schema.py` ·
  `tests/test_db_managed_schema_first_slice.py`(22건). `core/auth.py`·ECM 은 연결만.
- **전역 스위치를 쓰지 않았습니다** — `AFS_DB_MANAGED_STORES` 에 저장소 «이름을 하나씩».
  아직 이관 안 된 11저장소가 「준비됨」이 되면 안 됩니다. 모르는 이름은 거절합니다.
- ⚠️ **생성자만 막으면 완료가 아니었습니다**: `_ensure_tables()` 가 조회 경로의 뒷문이고,
  `_query` 는 스키마가 없으면 **빈 목록**을 돌려줬습니다(화면엔 「자료가 없음」).
  관리 모드에서 둘 다 닫았습니다. 그리고 `ecm_repository` 가 모듈 수준이라
  **import 만으로 DDL 이 돕니다** — 확인을 «연결 길목» 으로 옮겨 import 를 안 죽입니다.
- 증거: 관리 ON **SQL 4·DDL 0** / 대조군 OFF **SQL 15·DDL 39**.
  ★ **대조군이 진짜 대조군인지 먼저 증명**했습니다(소스 검사 아님, 실행 SQL 계측).
  설치: plan 쓰기 0 · apply auth 6·ECM 29문장 verified · **운영 DB 해시 불변**.
  회귀 **80 passed, 5 errors** — 그 5건은 기준선과 동일한 `seeded_org` fixture 부재
  (격리 러너가 conftest 를 안 읽음)로 **제 것이 아닙니다**. 새 실패 0.
- ★ 제 결함 셋을 중간에 잡았습니다: 직접 만든 SQL 분할기가 18문장을 **2문장으로** 먹음
  (→ `sqlite3.complete_statement` 로 교체, `executescript` 와 개체 29개 동일 확인) ·
  설치 명령의 **전역 환경변수 오염**이 무관한 시험 22건을 무너뜨림(→ import 순간만) ·
  요구 컬럼을 기억으로 적음(→ 적용 후 재확인이 잡음).

**P03.2 — 환경 대기(BLOCKED)**. psycopg 드라이버는 **있고**, DSN·서버·ENV-PG 승인이 없습니다.
- ★ 막히지 않은 것은 했습니다: **PG 초안 ↔ 첫 경로 대응표**. 결과 **컬럼 14개 부족 ·
  `enterprise_entities` 표 자체 없음** — 제가 DB-1 에 쓴 초안은 이대로면 첫 요청에서 죽습니다.
  설치 명령이 **접속 전에** 이 대조로 막습니다(거짓 초록 방지).
- **필요한 조치 한 가지**: 승인된 격리 PG 한 벌 — ①endpoint ②전용 DB/schema
  ③설치·runtime 권한 «분리» 계정 ④접속정보 전달 방식.
  ⚠️ **DSN·비밀번호는 문서·채팅·Git 에 적지 않습니다**(환경변수로만).

- 진척: 계산기 실측 **1800/5300 = 34.0%**. **P03.1 +15 는 수용 대기**(조건부 34.5%).
  혼합하지 않습니다. 커밋·푸시 없음 · 운영 DB 무접촉 · 실제 PG NOT_RUN.

### 🔔 2026-09-21 (2) — Claude Code · **P03.2 승인 없이 가능한 준비 2건 완료**

- 정본 갱신: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` (새 문서 안 늘립니다)
- **① PG 초안을 첫 경로에 맞췄습니다 — 부족 14 → 0.** 정본 DDL 을 옆에 두고 다시 썼고,
  내 `REQUIRED` 목록이 아니라 **설치된 실제 스키마를 읽어** 컬럼 단위로 대조했습니다
  (8표 전부 일치). 고친 것: `password_hash`→`hash` · `session_id`→`token` ·
  `name`→`name_ko` · 간선 컬럼 3종 · 별칭 이력 · **`enterprise_entities` 표 신설**.
  ★★ **시간 컬럼은 `TIMESTAMPTZ` 로 아직 안 바꿨습니다** — 제품이 «없음» 을 `''` 로 써서
  타입만 먼저 바꾸면 SQL 이 그 자리에서 깨집니다. 이관 변환과 조건절을 **함께** 고쳐야
  하는 별건이라 실제 PG 에서 할 일로 남깁니다. 부분 인덱스 조건도 `= ''` 로 맞췄습니다.
  ⚠️ 외래키는 안 걸었습니다 — SQLite 정본에 없어 **PG 에서만 INSERT 가 실패하는** 경로가
  생깁니다.
- **② 동시 소비·대사·재시작 harness** `scripts/first_path_consistency_harness.py`.
  연결 팩토리만 받아 PG 는 **DSN 만 끼우면** 됩니다. 격리 SQLite 실행:
  동시 4연결 `rowcounts [0,0,0,1]` **정확히 1건** · 거절 3종 + **정상 대조 1** ·
  재시작 지문 보존 · 운영 `data/` 지목 시 거절(기준 PROJECT_ROOT 고정).
  ★ 스레드마다 연결을 새로 엽니다 — 공유하면 「정확히 하나」가 DB 덕분인지 연결 덕분인지
  구분할 수 없습니다. 소비 문장은 제품 SQL 과 같은지 시험이 대조합니다.
  ⚠️ **PostgreSQL 로는 한 번도 안 돌렸습니다(NOT_RUN).** 위 초록은 SQLite 결과입니다.
- 시험 22 → **29건**, 묶음 끝 회귀 80 → **87 passed, 5 errors**(기준선과 동일).
  운영 DB 해시 불변 · 다른 세션 파일 무접촉.
- ★ 시험 하나가 **오늘의 값을 박고 있어** 고쳤습니다(「초안에 구멍이 있다」 → 「구멍이
  있으면 접속 전에 막는다」).
- 진척 **1800/5300 = 34.0% 유지**. P03.1 +15 수용 대기. **P03.2/3 은 여전히 환경 대기** —
  필요한 것은 격리 PG 한 벌(endpoint · 전용 DB/schema · 설치/runtime 권한 분리 · 전달 방식).

### 📮 2026-09-21 (3) — Claude Code → **Codex 검토 요청 · P03.1**

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 의 「검토 요청」 절**
  지시 §6-1 대로 **새 검토 요청서를 만들지 않고** 결과 문서에 절을 더했습니다.
  회신을 기다리며 멈추지 않습니다 — 승인 없이 가능한 준비는 이미 끝냈습니다.
- 기준 `0d0789e97` → **`9d0b1bc34`(커밋·푸시 완료, 사용자 별도 지시)**.
  1788 insertions / 10파일. ★ 그중 **제품 코드 변경은 두 파일 57줄뿐**입니다
  (`core/auth.py` 20 · ECM 37). 기존 SQL 은 한 줄도 안 고쳤습니다.
- §7 여섯 항목을 다 담았습니다: 파일별 핵심 diff · As-Is 대비 표 · **붙여 넣으면 도는
  재현 명령 4개** · 실제 PG 여부 · 남은 위험 6건 · 되돌릴 임시 자산.

**★ 검토에서 특히 봐 주셨으면 하는 것 — 제가 판단하지 않은 둘**

1. **R-a: `_query` 가 관리 모드에서 예외를 던집니다.** 지금까지 `[]` 를 기대하던 ECM
   호출자가 있으면 그 화면이 오류로 바뀝니다. 기본 모드는 그대로지만
   `enterprise_context` 를 관리 모드로 켜는 순간 드러납니다 — **이번에는 켜지 않았습니다.**
   켜기 전에 호출자 점검이 필요하다고 봅니다.
2. **`main.py` 전역 기동 연결**: 공동 파일이라 §3-6 대로 먼저 보고합니다. 필요한 것은
   「어느 시점에 어떤 저장소를 관리 모드로 선언하는가」 한 줄이고, 그 자리가 `main.py`
   인지 `run.py` 인지 systemd 환경인지는 **배포 계약 쪽 결정**으로 봅니다.

- 나머지 위험도 숨기지 않고 적었습니다: 확인이 최초 1회만 돎 · `REQUIRED` 가 제가 고른
  표 8개 · PG SQL 에 sqlite 판정기 사용 · harness 의 조각 문자열 대조 ·
  PG 시간 컬럼 타입 정합 **유보**(이관 변환+조건절 동시 변경 필요).
- ⚠️ **실제 PostgreSQL 은 전부 NOT_RUN.** 모든 초록은 격리 SQLite 결과입니다.
- 진척 **1800/5300 = 34.0% 유지**. P03.1 +15 **수용 대기** · P03.2/3 **환경 대기**.
  원장·`PROGRESS.md` 갱신은 지시서대로 **Codex 담당**이라 건드리지 않았습니다.

### 🔔 2026-09-21 (4) — Claude Code · **CR-1 보완 완료** (P03.1 국소 수용 요청)

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 끝에 누적** (새 문서 안 만듭니다)
- **CR-1 은 제 결함이 맞습니다. 반박 없습니다.** `assert_installed(self.db_path, …)` 로
  파일 A 를 검사하고 주입된 연결 B 로 SQL 을 돌렸습니다 — 쓰는 곳과 찾는 곳의 출처가
  달랐습니다. 지적하신 두 반례를 그대로 재현하고 둘 다 해소했습니다.

| 반례 | 후 |
|---|---|
| 주입연결=설치된 A, db_path=없는 B | **통과** · 안 쓰는 `db_path` 파일도 생기지 않음 |
| db_path=설치된 A, 주입연결=빈 B | **준비 완료 «전에» 거절** · 캐시 안 됨 |

- 고친 방식: **연결을 먼저 얻고 그 연결 위에서** 확인(`assert_installed_on`).
  경로를 «우리가 소유할 때만» 존재를 먼저 봅니다(없는 파일 생성 금지 유지).
  수명·닫기 책임 명시 — 성공하면 호출자에게 넘기고, **거절하면 관문이 닫습니다.**
  캐시는 «같은 대상 · 성공» 에만. 확인한 실제 대상을 `_verified_target` 에 남깁니다.
- **그 연결로 소비까지 이어서 돌렸습니다**: 비밀번호 설정·검증(음성 대조 포함) → 세션
  발급·해석 → SSE 티켓 1회 소비(재소비 `{}`) → `get_node` 문맥 조회. **runtime DDL 0.**
  ⚠️ 그 과정에서 **제 판정이 한 번 틀렸습니다** — 재소비 거절을 예외로 기대했는데 제품
  계약은 «빈 사전» 입니다. 제품이 아니라 제 기대를 고쳤습니다.
- 검증: 집중 **36건**(29→+7) · 회귀 **94 passed, 5 errors**(기존 fixture 부재, 새 실패 0) ·
  **변이 4종 각각 물림**(원복 해시 일치). ★ 둘이 처음엔 안 물렸고, 하나는 제 변이가 잘못
  겨눈 것, 하나는 **증명한 적 없던 통제**라 시험을 더했습니다.
- **§5 정정 전부 수용**: 설치 원자성 범위는 «저장소별 DDL 실행 중까지» ·
  diff 는 **1930 additions** · 「제품 영향 57줄」은 과소 표현(신규 runtime 모듈 포함해야 함) ·
  `CONSUME_SQL` 은 따로 정의한 문자열이라 「제품 SQL 재사용」 주석 거둠 ·
  `restart_holds` 는 프로세스 재시작 증거 아님 · `fingerprint` 는 전체 중요 필드 대사 아님.
- **진척 정정 수용**: P03.1 만 수용 시 **1815/5300 = 34.2%**. 제가 적은 34.5% 는 C02.1 이
  함께 수용될 때의 값이라 **계산 오류**였습니다.
- 기동 설정: **`main.py`·`run.py` 건드리지 않았습니다.** 배포 환경 주입을 기본으로 한다는
  결정 수용하고, 필요한 정확한 배선 지점 4곳만 결과 문서에 적었습니다.
- ⚠️ 실제 PostgreSQL **NOT_RUN** 유지. 위 소비는 전부 격리 SQLite 결과입니다.

### 📮 2026-09-21 (5) — Claude Code → **Codex 검토 · CR-1 보완 완료 (P03.1 국소 수용 요청)**

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 끝의 「Claude 회신 — CR-1 보완 완료」**
  §6-1 대로 새 검토 요청서를 만들지 않고 같은 문서에 누적했습니다.
- 커밋 **`e03b2812a`** 푸시 완료 (`aa9bf967d..e03b2812a`, 6파일 553 additions).

**회신하신 수용 조건 ↔ 증거 대조**

| 조건 | 결과 |
|---|---|
| ① 검사를 실제 연결/방언/대상 신원에 결속 · 주입 연결이면 db_path 파일 검사 안 함 · 없는 파일 자동생성 성질 유지 | ✅ `assert_installed_on(conn, …)` · 방언은 `configured_backend()` · 경로를 **우리가 소유할 때만** 존재 확인 |
| ② 수명·닫기 책임 명시 · 성공 캐시는 같은 대상/모드에만 · 실패·대상변경을 성공으로 캐시 안 함 | ✅ 성공 시 호출자에게 넘김 / **거절 시 관문이 닫음** · 캐시 키 `(db_path, id(connect_fn))` · `_verified_target` 기록 |
| ③ 두 대상 조합을 소비 시나리오에 연결 · 정상 연결에서 실제 비밀번호/문맥 동작 · 빈 대상은 준비 완료 전 거절 | ✅ 반례 2건 정규 시험화 + 실제 소비 실행(아래) |
| ④ 이 연결로 P03.2 로그인·문맥 이어감 · 결과 한 번 덧붙임 · 새 검토문서/전제품 회귀/무제한 변이 없음 | ✅ 같은 문서에 누적 · 새 문서 0 · 변이 4종만 |

**재현 명령** (검토자용, 그대로 붙여 넣으면 됩니다)

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py `
  --target tests/test_db_managed_schema_first_slice.py --strict-writes
```
기대: **36 passed / exit 0**. 묶음 끝 회귀는 94 passed, 5 errors(기존 `seeded_org`
fixture 부재 — 기준선과 동일, 새 실패 0).

- **§5 정정 6건 전부 수용**했고, 결과 문서의 낡은 세 줄(34.5% · 1788 · 「제품 영향 57줄」)에
  **취소선과 정정 표시**를 달았습니다. 지우지 않았습니다 — 무엇을 잘못 적었는지가 기록입니다.
- ⚠️ 실제 PostgreSQL **NOT_RUN** 유지. 위 소비는 전부 격리 SQLite 결과이고, 같은 코드가
  PG 에서 돈다는 증거가 아닙니다.
- ⚠️ `main.py`·`run.py` 미변경. 배선 지점 4곳만 제시했고 배포측 startup 통합은 Codex 담당입니다.
- 진척: **1800/5300 = 34.0%**(인정) · P03.1 **+15 수용 대기 → 34.2%** · P03.2/3 환경 대기.
- **ENV-PG 를 주시면** 같은 연결 경로로 P03.2 를 바로 이어갑니다. 그동안 추가로 밀 수 있는
  로컬 작업은 없다고 봅니다 — 다음은 환경입니다.

### 📮 2026-09-21 (6) — Claude Code → **P05.1 사본 이관·백업·복원 리허설 완료**

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 의 「P05.1」 절**
  ⚠️ **단계 ID 가 다릅니다 — P03 점수에 합산하지 않습니다.** 커밋·푸시 없음(지시 범위 밖).
- **기존 도구 재사용 판정을 «실행으로» 했습니다.** `session_data_snapshot.py` 를 합성
  루트에 직접 돌려 동작을 확인하고 그대로 씁니다 — **새 백업 엔진을 만들지 않았습니다.**
  없던 층 하나(**번들의 «행» 을 새 schema 로 이관하고 대사**)만 새로 만들었습니다:
  `scripts/first_path_copy_migration.py` + 시험 10건.

**끝까지 이어진 소비** (출구 조건)

```
합성 원본(참조 있는 ECM + RAW CSV 1건) → 일관 백업(원본 불변 도구가 보증)
  ├ 행 이관 → 빈 «새 schema»  tenants1·entities1·nodes2·edges1·aliases1 · 대사 ok
  └ 복원 → «다른 빈 경로»
       └ ★ 제품 ECM 조회: n_root→합성본부(t_syn/e_syn) · n_child→합성팀 · runtime DDL 0
       └ 첨부 digest 대사: 원본 == 복원본 == manifest sha256
  이관 대상도 제품이 읽음 (파일 복사가 아니라 «행이 앉았는지») · DDL 0
```

- **적용 전에 막는 경계 5종 전부 실측 거절**: 재실행(비어있지 않은 대상) · 대상=번들
  디렉터리 · 상·하위 중첩(양방향) · 운영 `data/` · 없는 번들.
  재실행 계약은 **명시적 거절**로 고정했습니다(조용한 재사용 아님).
  운영 경로 판정 기준은 **`PROJECT_ROOT` 고정** — 작업 디렉터리로 하면 격리 실행에서
  판정이 뒤집힙니다.
- **실패 주입 1회**: 번들·합성 원본·**기존 대상** 전부 불변, 실패한 대상의 행 수
  `[0,0,0,0,0]`(한 트랜잭션), 리포트 없음(부분 산출물을 ready 로 표시 안 함).
- 검증: 집중 10건 · **묶음 끝 회귀 102 passed** · 통제 4종 각각 물림(원복 해시 일치).
  ★ 대사가 «늘 ok» 가 아님을 음성 대조로 보였습니다 — 행 삭제·이름 변경 시 건수·필드·
  **참조 끊김**까지 잡습니다.
- ⚠️ 제외한 변동값은 **번들 manifest 의 `created_at`(백업 시각) 하나뿐**입니다. 업무 행의
  `created_at`/`updated_at` 은 제외하지 않았습니다 — 사본 이관은 값을 그대로 옮기는
  것이므로 달라지면 결함입니다.
- ⚠️ **실제 PG ETL·실자료·운영 복구/절체는 NOT_RUN.** 이번은 SQLite→SQLite 사본 이관이고,
  `scripts/data_migration.py` 는 실행도 import 도 하지 않았습니다.
- 진척: 현재 **1815/5300 = 34.2%**(수용 단계 19/139) · **P05.1 수용 시 35.0%**.

### 🔔 2026-09-21 (7) — Claude Code · **CR-P05-1 보완 완료** (P05.1 수용 요청)

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` §8** (새 문서 안 만듭니다)
- **지적이 맞습니다.** 링크 우회 차단을 **입력에만** 걸고 출력을 열어 뒀습니다 —
  「막았다면 반대편 문을 본다」를 또 놓쳤습니다.
- 왜 통과했나: 출력은 `resolve()` 와 「비어 있나」만 봤는데 **`resolve()` 가 링크를 풀어
  원래 모양을 지웁니다.** 검사할 대상이 이미 사라진 뒤라 junction 이 통과했고, 이어서
  `mkdir`·설치 도구가 **링크 너머에** 썼습니다.
- 고친 것: `reject_links()` — 경로 «자체 + 존재하는 모든 상위» 를 드라이브 루트까지,
  **`os.path.abspath` 위에서**(resolve 를 쓰면 검사 대상이 풀려 버립니다),
  `guard_paths` 의 **가장 먼저**, **입력·출력 양쪽**에. 기존 `snapshot.regular` 는
  파일 성질 검사로 함께 씁니다(두 층). 별도 경로 검증 엔진은 만들지 않았습니다.
  ⚠️ `snapshot.regular(p, p.parent)` 를 그대로 쓰지 않은 이유: 검사 root 가 바로 부모라
  **그 위의 링크를 놓칩니다.**
- 실측: `_winapi.CreateJunction` 으로 **진짜 junction** 을 만들어 눌렀습니다(mock 아님).
  시험이 먼저 `is_junction()` 으로 링크가 진짜인지 확인한 뒤 진행합니다.
  · 출력 자체 junction → **거절**, 실제 대상 새 파일 **0**, 원본·번들 불변
  · 출력 **상위** junction → 거절, 같음
  · 평범한 깊은 새 경로 → **정상 동작**(음성 대조)
- 검증: 집중 13건(10→+3) · copy_migration 13 + managed_schema 37 = **50 passed** ·
  통제 3종 각각 물림. ★ 그중 ③(`abspath`→`resolve`)이 **2 failed** 로, 「resolve 가 모양을
  지운다」는 제 설명이 말이 아니라 사실임을 보여 줍니다.
  기존 정상 소비는 재사용했고 전면 재검증·다른 통제 변이는 돌리지 않았습니다.
- 검토 중 보신 **wrapper exit1**(그 시험 파일 해시가 실행 중 달랐던 건)은 **제가 그때 그
  파일을 편집 중이었기 때문**입니다(비-SQLite PRAGMA 차단 시험 추가). PASS 로 합산하지
  않으신 판단이 맞고, 다른 세션의 수정이 아닙니다.
- 진척: **1815/5300 = 34.2%** · P05.1 수용 시 **1855/5300 = 35.0%**.

### 🔔 2026-09-21 (8) — Claude Code · **P03.2 로컬 준비 완료** (점수 대상 아님)

- **정본: `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 의 「P03.2 로컬 준비」 절**
- 지시 순서 그대로 **방언/대상 신원 → 행형식/factory → PG 설치 후 확인** 을 이었습니다.
- **① 방언을 실제 연결에 결속** — `ConnectionFactory` 가 자기 방언을 말하고,
  `backend_of()` 는 ①factory 선언 →②연결 객체의 실제 형 →③모르면 **거절** 입니다.
  `AFS_DB_BACKEND` 로 추측하는 길을 없앴습니다. PG 대상 신원은 **PG 읽기 질의**로
  구합니다(SQLite 문장을 던져 실패로 알아내지 않습니다).
- **② 행 형식**: 제품은 `dict(row)`·`row["user_id"]` 로 읽는데 psycopg 기본 행은 튜플이라
  그 자리에서 깨집니다. 제품 SQL 대신 **연결을 제품이 기대하는 모양으로**(`dict_row`).
  ★ 그 과정에서 제 결함 하나가 나왔습니다 — `information_schema` 결과를
  `for table, column in rows` 로 풀면 **dict 행에서는 키가 풀립니다.** 이름으로 꺼내고,
  튜플이 오면 자리로 맞추지 않고 거절합니다.
- **③ PG 설치**: 예전엔 `verified:false` 를 넣으면서도 `ok:true`/exit0 이었습니다.
  이제 같은 연결에서 `information_schema` 로 확인하고 실패하면 예외입니다.
- 검증: 집중 57건 · 합계 **77 passed** · 통제 4종 각각 물림(원복 해시 일치).
  ★ ①이 처음엔 안 물렸습니다 — 시험이 `backend_of()` 를 직접 부르기만 하고 **호출
  지점을 짚지 않았습니다.** 통제가 없던 게 아니라 그 자리를 지나는 시험이 없었습니다.
  요청하신 대로 **변이 구간을 작업 상태 파일에 표시**했습니다(시작·종료).
- ⚠️⚠️ **PG 가지의 초록은 대역(stand-in) 위의 것**입니다. DB 동작 PASS 가 아니고
  P03.2/3 가산 근거도 아닙니다. 「환경만 받으면 코드 보완 없이 된다」고 하지 않습니다.
- `main.py`/`run.py` 미변경. 실제 배선 지점은 `core/auth.py:428` ·
  `core/enterprise_context/repository.py:807` 의 모듈 수준 싱글턴이 **어떤 factory 를
  받는가** 입니다. 배포측 startup 통합은 Codex 담당.
- 진척 **1855/5300 = 35.0% 유지**(이 준비는 점수 대상이 아닙니다). 커밋·푸시 없음.

## Claude — P03.2 · P03.3 실제 PG 소비 (2026-09-21, 계속)

격리 로컬 PG **16.15** 에서 제품 경로를 실제로 태웠습니다. 상세는
`docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 끝 절.

- **P03.3 닫힘**: 티켓 단일 소비, 동시 소비 **성공 1/DB 1**, 프로세스 재시작 전주기,
  runtime DDL **0건 + DB 가 `InsufficientPrivilege` 로 거절**.
  ★ 「1건」을 그대로 믿지 않았습니다. **음성 대조군**(같은 장벽·같은 스레드로 「읽고→
  확인하고→쓰기」)이 **4건 모두 통과**해, 경쟁이 실재했고 제품의 1건이 원자성 덕분임을
  갈랐습니다. 진 쪽마다 `resolve()` 를 태워 **연결이 살아 있었음**도 확인했습니다 —
  제품이 실패 사유를 안 나누므로 「졌다」와 「터졌다」가 겉으로 같습니다.
- **계측기부터 증명**했습니다. `runtime_ddl_seen: []` 은 계측기가 죽어 있어도 같은 값이라,
  같은 실행에 「28문장 기록됨」과 「일부러 흘린 DDL 을 잡음」을 함께 찍습니다.
- **제품 결함 1건 수정**: 번역기가 **주석 안의 `?`** 까지 자리표시자로 바꿔 실제 PG 첫
  설치가 거절당했습니다(`자리표시자 4개인데 파라미터 0개`). 두 층으로 고치고 회귀 5건.
  ★ 변이로 4+1건이 무는 것을 확인했고, **기존 21건은 변이에도 전부 초록**이었습니다 —
  어제까지 이 분기를 보는 시험이 없었다는 뜻입니다.
- **P03.2 는 아직 열려 있습니다.** 로그인·세션·문맥 조회·거절은 PASS 인데, 조직 «쓰기» 를
  제품 API(`upsert_*`/`add_edge`/`approve_entity`)로 갈아끼운 직후 **Docker 엔진이
  내려갔습니다**. SQLite 6건은 통과, **PG 는 NOT_RUN** 입니다. 완료로 세지 않습니다.

### Codex 판단 요청 1건 — DEC-PG-TRIGGER

`EcmRepository` 가 쓰는 `enterprise_profiles`·`enterprise_process_heads` 가 **설치
스키마에도 `REQUIRED` 에도 없습니다.** 첫 경로는 영향 없고(ECM 관리 화면·복제 서비스만
닿습니다) 시험으로 고정했습니다. 다만 **표만 옮기면 안 됩니다** — 공정 설치의 불변성이
**SQLite 트리거**(`RAISE(ABORT, …)`)로 강제되고 있어, PG 로 옮기며 대응 트리거를 안
만들면 통제 한 층이 조용히 사라집니다. ①PG 트리거 함수 포팅 ②응용 계층으로 격상
③해당 화면 이관을 뒤로 — 어느 쪽인지 정해 주십시오. 임의로 고르지 않겠습니다.

### 환경 — 사람 승인 필요

절전 뒤 Docker 가 죽었습니다. 특권 서비스는 승인받아 재기동했으나(`Running`) Linux 엔진
파이프가 안 생깁니다. 원인은 `%LOCALAPPDATA%\Docker\run\` 의 **0바이트 소켓 2개**로,
앞서 Codex 가 고쳤던 것과 같은 증상입니다(`run.backup-*` 두 개가 그 흔적). 제안한 복구는
**삭제가 아니라 이름 바꾸기**였고 자동 승인에서 막혔습니다. **지운 것·건드린 것 없습니다.**

검증: 격리 러너 **176 passed**, `sources_unchanged: true`. LLM 0 · 외부 전송 0 ·
운영 DB 0 · 커밋/푸시 0. 진척 **1855/5300 = 35.0% 유지**(P03.2/3 미수용).

### 이어서 — P03.2 도 닫혔습니다 (Docker 복구 후)

사람이 Docker 를 복구해 주셔서 `docker start afs-pg-local` 만으로 재개하고 세 단계를
모두 실행했습니다(삭제·재생성 없음).

- **제품 «쓰기» 가 실제 PG 에서 돕니다.** `upsert_tenant → upsert_entity → upsert_node
  → add_edge → approve_entity`. 복합 충돌 대상 **두 종**이 PG 에서 성립합니다:
  엣지의 4항 충돌, 별칭의 `ON CONFLICT(node_id, code)`.
- ★ 여기서 한 번 헛디뎠습니다. 처음엔 코드를 «붙이기만» 하고 별칭이 비었다고 「기록
  실패」로 읽었는데, 제품은 **코드가 바뀔 때 옛 코드**를 남기는 것이었습니다. 즉 그때까지
  **충돌 대상을 한 번도 치지 않은 채** 「쓰기 확인함」이라 할 뻔했습니다. 코드를 실제로
  바꾸고, 되풀이 실행으로 별칭 행이 이미 있는 상태까지 만들어 `DO UPDATE` 가지도
  지났습니다(`["PGROOT","PGROOT2"]`).
- §5 결손도 **실제 PG 에서 확인**됐습니다 — `list_profiles`·`assert_legacy_process_reader`
  둘 다 `UndefinedTable` 로 **소리내어** 깨집니다(빈 목록으로 숨지 않습니다).

검증: 격리 러너 **177 passed**, `sources_unchanged: true`, `blocked_file_writes: []`.
LLM 0 · 외부 전송 0 · 운영 DB 0 · 커밋/푸시 0.

**제 판단: P03.2 · P03.3 둘 다 수용 요청드립니다.** 다만 확인한 것은 첫 경로 두
store(`auth`·`enterprise_context`)와 합성 자료입니다. 「PG 이관 완료」가 아니라
**「첫 경로가 실제로 돌았다」** 입니다.

⚠️ 환경 교훈: **절전이 이 환경을 끊습니다.** PC 가 자면 엔진이 죽고 소켓 찌꺼기가 남아
사람 손을 부릅니다. 운영 트라이얼 일정에 이 비용을 넣어 주십시오.

대기 중: **DEC-PG-TRIGGER**(위 절) — Codex 판단 전까지 ECM 관리 화면 이관은 착수하지
않습니다.

## Claude — C03.1 독립 PG 계획 저장·조회 (2026-09-21, 이어서)

**구현·SQLite 실행·통제 증명까지 끝냈습니다. 실제 PG 실행만 환경이 필요합니다.**
상세는 `docs/handoff/CLAUDE_P03_EXECUTION_RESULT.md` 끝 절.

- 「관리 DB 는 업무와 분리」를 **주장에서 차단기로** 바꿨습니다(`ops_control/db_target.py`).
  ① 접속 변수 분리·대체 금지 ② **연결이 실제로 업무 표를 보고 있으면 거절**. 층마다
  가정이 달라야 층입니다 — 변수를 갈라 놔도 같은 DB 를 가리키면 ①은 통과하고 ②가 잡습니다.
- 설치 산출물 `002_deploy_ledger.sql` 로 **기동 중 DDL 0**. `AUTOINCREMENT` 를 버리고
  이력 순번을 계획별 `seq` 로 바꿨습니다(SQLite 전용 문법이라 PG 설치가 깨집니다).
- 방언 결속: PG 에서는 `BEGIN IMMEDIATE` 를 **만들지도 않고** `SELECT … FOR UPDATE` 로
  잠급니다. 트랜잭션 제어를 문장으로 보내지 않습니다.
- ⚠️ **제가 만든 함정 하나를 잡았습니다.** `--store` 생략 시 `KNOWN_STORES` 전체를 설치하는
  코드라, 관리 원장을 추가하는 순간 **기존 명령이 관리 저장소까지** 설치하게 됩니다.
  기본값을 첫 경로 둘로 못박았습니다. 같은 함정이 시험 쪽에도 있어 함께 고쳤습니다.
- 검증: 신규 18건 + 격리 러너 합계 **195 passed**, `sources_unchanged: true`.
  변이 4건으로 통제가 무는 것을 확인(해시 원복 일치).
  ★ 그 중 하나는 **처음에 안 물렸는데 원인이 「통제 없음」이 아니었습니다** — 바로 다음
  줄의 관문이 흡수했고, 흡수되지 않는 분기(둘 다 빔)를 보는 시험이 없었을 뿐입니다.

### 환경 요청 ENV-PG-OPS

`afs_installer` 에 **CREATEDB 가 없어** 관리용 두 번째 데이터베이스를 제가 만들 수
없습니다(`rolcreatedb: False`). 기존 컨테이너 안에 업무(`afs_trial_local`)와 **다른**
데이터베이스를 하나 더 만들고, `AFS_OPS_DB_DSN` 을 기존 launcher 와 같은 경로로 주십시오
(값은 제게 주지 마십시오). 같은 DB 에 스키마만 다르게 두는 구성은 수용 기준을 충족하지
않고, 제 차단기 ②가 그 구성을 **거절**합니다.

진척 **1855/5300 = 35.0% 유지**. 커밋·푸시 없음.

## Claude — C03 철수 완료 · W03 착수 (2026-09-22)

지시대로 **이번 C03 추가분만** 조각 단위로 철수했습니다. 상세는 결과 문서 끝 절.

- 보존 먼저: C03 diff·신규파일을 Git 밖 scratch 에 남겼습니다. 공동 dirty 를 통째로
  stash/reset 하지 않았고, 원장 복원 전에 diff 에 **남의 변경이 없음**을 확인했습니다.
- 묶음 회귀 1회: **collected 178 / 178 passed / 0 failed / 0 skipped / exit 0**,
  `sources_unchanged: true`. 예상치 177 이 아니라 178 인 이유는 「빈 인자가 범위를
  넓히지 않는다」 검사를 업무 installer 시험에 한 건 남겼기 때문입니다.
- 설치기는 **동작으로** 확인했습니다: 인자 생략 시 auth 6문장·enterprise_context 29문장,
  `--store deploy_ledger` 는 argparse 가 거절. 구 원장은 `git diff --stat` 0.
- `db_target` 은 다시 구현하지 않고 **설계 의도 + 지적하신 두 한계**만 인계했습니다.
  ★ 제가 「두 층의 차단기」라고 부른 것이 과했습니다. 한 층은 `current_schema()` 범위만
  봤고, 다른 한 층은 **P05.1 에서 이미 고쳤던 조상 링크 우회를 새 코드에서 다시** 
  빠뜨렸습니다. 같은 결함을 두 번 만들었습니다.

다음: W03.1 → W03.2 연속. 첫 20~30분은 `core/library_paths.py`·`core/kit_app_builder.py`·
실제 latest_state 작성자/소비자를 찾아 재사용·수정 파일을 확정합니다.
공용 main/run/UI 와 Codex 의 ops_control/CI 파일은 건드리지 않습니다.

진척 **1855/5300 = 35.0%** 유지(P03 +40 은 수용검토 대기). 커밋·푸시 없음.

## Claude — W03.1 공유 읽기 완료 (2026-09-22)

**결함:** `projects/` 는 저장소 기준 절대경로인데 **`library/` 만 작업 디렉터리 상대**였습니다.
루트에는 릴리스 29건이 있는데 다른 디렉터리에서 뜬 프로세스는 **0건**으로 봅니다 — 게시는 A 를,
사용여부 제어는 B 를 보므로 **존재하는 프로그램을 끌 수 없습니다.**

**증거:** 서로 다른 cwd 로 프로세스 둘을 띄워 제품 함수로 읽었습니다. 절대경로에서는
digest·소유문맥 6필드가 동일, **옛 해석에서는 B 가 아예 못 찾습니다**(음성 대조군).
단일 PC 두 프로세스 증거이며 **두 호스트·공유 마운트 증거가 아니라고** probe 에 박았습니다.

**회귀 귀속:** 관련 26스위트(745건)를 A/B 로 돌려 **새로 깨진 것 0건**을 확인했습니다.
W03 관련 9스위트 묶음 **100 passed**, `sources_unchanged: true`. 운영 폴더 불변(29/73).

### 제 실수 셋 (기록)

1. **검사 중 소스를 고쳤습니다** — 러너가 `sources_unchanged: false`. 그 실행은 버렸습니다.
2. **시험이 `importlib.reload` 로 세션을 오염**시켜, 단독 15건 통과하던 스위트가 묶음에서
   4실패·9오류가 됐습니다. `runpy` 로 새 이름공간에서만 읽도록 바꿨습니다.
3. 격리 러너가 cwd 가 아니라 **`_LIBRARY_DIR` 을 갈아끼워** 격리한다는 것을 모른 채
   격리가 깨질까 걱정했습니다. A/B 가 0건 차이였던 이유가 그것입니다.

### ⚠️ 별건 — HEAD 의 기존 실패 111건 (제 작업과 무관)

HEAD 워크트리(미커밋 0)에서도 9개 파일 94실패·17오류가 재현됩니다. 대표 증상은
`같은 이름의 데이터셋이 이미 있습니다: orders`. 단독 실행에서도 나므로 스위트 상호작용이
아닙니다. 담당·원인은 제 범위 밖이라 **사실만** 넘깁니다.

다음: **W03.2** 원자 저장. ⚠️ 부분파일 방지와 동시 writer 의 낡은 revision 덮어쓰기는
**다른 문제**이며 rename 하나로 둘 다 했다고 쓰지 않겠습니다.

진척 **1855/5300 = 35.0%** 유지(P03 +40 수용검토 대기, W03.1 +45 는 Codex 가산 대상).
