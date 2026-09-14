# Claude Code 시작 안내 — L2 Studio 인수인계

작성: Codex · 2026-09-15 KST. 사용자 요청: 상세 인계와 커밋·푸시, Claude Code의 정확한 작업 재개.
이 문서는 **현재 상태와 재개 순서의 입구**다. 제품 헌장·전략·실행계획을 대체하거나 미통과 Gate를 해제하지 않는다.

## 1. 처음 1분에 확인할 결론

- 작업 브랜치: `codex/l2-unified-studio-20260912`.
- 원격: `https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git`.
- 이전 Claude 기준: `dd0573383084fbcbd111b1e1443ac5b310f1beb6`.
- **인계 코드 커밋: `215253f22dd7be78555e83f60952f99aefe9e12e`**. 이 문서는 그 다음 문서 커밋에 포함된다. 문서 커밋의 실제 ID는 `git log -2 --oneline`으로 확인한다.
- 전체 **21/40 = 52.5%**, 로컬 **18/28 ≈ 64.3%**. 다른 분모다. 두 값을 합치거나 시험 수를 완료 칸에 가산하지 않는다.
- B5 결함 수정, B6 URL 문법·프로젝트 진입 확인 모듈, RevisionStore READ 초기화 제거는 구현·집중검증 완료.
- **App 전역 연결·단일 mount·실제 브라우저 수용은 미완료**다. 사용자가 보는 새 단일 Studio 진입 화면이 완성됐다고 말하지 않는다.
- 다음은 project 진입 연결의 선행 Gate 확인과 첫 연결 범위를 **20~30분**으로 끊는 작업이다. 아래 §6을 따른다. 통합계획 사본이 생긴 사실만으로 연결을 강행하지 않는다.
- 이 PC에 남긴 `data/interaction_log.jsonl` 변경은 사용자 소유이며 커밋에서 제외했다. 이를 삭제하거나 이관 코드의 일부로 커밋하지 않는다.

## 2. 자료 읽는 순서와 과거 문서 해석

먼저 저장소의 `.agents/AGENTS.md`를 읽는다. 이후 다음 순서로 확인한다.

1. `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md`
2. `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`
3. `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md`
4. `PROGRESS.md` 최상단과 이 안내
5. [병렬 통합계획 원문 사본](references/PARALLEL_INTEGRATION_PLAN_2026-08-15_SOURCE_COPY.md) 전문
6. [B5 결함 수정 상세](L2_STUDIO_B5_DEFECT_REPAIR_2026-09-14.md)
7. [B6 진입 및 READ 상세](L2_STUDIO_B6_PROJECT_ENTRY_2026-09-15.md) — 특히 마지막 「후속 묶음: 판본 READ 초기화 제거」
8. [기존 세션·데이터 인계](L2_STUDIO_CROSS_SESSION_HANDOFF_2026-09-13.md), [데이터 복원 절차](../../data_sync/README.md)

과거 문서는 당시 기록이다. 다음 충돌은 이렇게 해석한다.

| 과거 표현 | 현재 해석 |
|---|---|
| B5 저장 출구가 모두 닫혔다 | 이후 결함을 수정했지만 실제 화면/effect 수용은 여전히 미완료 |
| C0/parser 또는 project adapter를 다음에 구현한다 | 현재 코드에 이미 존재한다. 다시 만들지 않는다 |
| RevisionStore READ의 알려진 DDL만 예외 허용 | 후속 수정으로 이 예외를 제거했다. 새 시험은 READ DDL/DML0을 요구한다 |
| B6 미착수/설계만 존재 | 내부 모듈은 구현됐다. 전역 연결 완료는 아니다 |
| commit/push 미실행 | 각 과거 작업 종료 당시의 상태다. 이번 인계는 코드·문서 커밋으로 전달한다 |
| 432PASS, 251PASS, 312PASS | 서로 다른 시점/선택이다. 합산하지 않는다. 현재 코드의 인계 집중 재검증은312건 |
| 통합계획의 dev clean/HOLD·과거 커밋 | 2026-08-15 상태 기록이다. 현재 증거를 다시 확인하며 과거 명령을 그대로 실행하지 않는다 |

### 통합계획 사본의 출처

- 원경로: `workspace/codex-three-week-mvp/docs/roadmap/PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`.
- 원경로는 이 브랜치의 Git 추적 파일이 아니었다. 다른 PC의 pull에는 없을 수 있어 위 참조 사본을 추가했다.
- 복사·비교 날짜: 2026-09-15 KST.
- 작성 PC 원본 및 사본 SHA256: `83199cf57721ec94c8ed3b704238eaa2a77ad7df5a9e147a5874af38bafd86c8`로 동일했다. 줄바꿈 정규화 텍스트 대조도 동일했다.
- Git의 줄바꿈 설정에 따라 checkout의 바이트 해시는 달라질 수 있다. 원문 의미를 수정한 사본이 아니다.
- **참조 자료 전달일 뿐, 정본 승격·브랜치 통합·HOLD 해제·Gate 통과의 증거가 아니다.** 원본 절차의 운영 DB 금지·단독 진입점 담당·단계별 검증 조건을 유지한다.

## 3. 안전한 코드 동기화·환경 준비

### 기존 checkout

먼저 읽기 전용 확인부터 한다.

```powershell
git status --short
git branch --show-current
git log -5 --oneline
git remote -v
```

- 다른 사람의 변경이 있으면 파일 소유를 확인한다. 자동 stash/reset/clean/checkout으로 제거하지 않는다.
- 지정 브랜치이며 작업트리가 안전하고 **새 세션에서 원격 동기화가 허용된 경우**에만 아래를 실행한다.

```powershell
git pull --ff-only origin codex/l2-unified-studio-20260912
git merge-base --is-ancestor 215253f22dd7be78555e83f60952f99aefe9e12e HEAD
git log -2 --oneline
```

두 번째 명령의 종료 코드0은 인계 코드 포함을 뜻한다. 불일치/분기/충돌이면 멈추고 보고한다. force push나 자동 rebase로 맞추지 않는다.
`dev`로 이동하거나 과거 통합 커밋을 cherry-pick하는 명령은 이 동기화 절차에 포함하지 않는다.

### 새 PC·새 폴더

- 사용자가 정한 빈 폴더에 **지정 브랜치**를 clone한다. 이미 사용 중인 경로에 덮어쓰지 않는다.
- 데이터까지 실제 실행하려면 §8의 동일 절대경로 조건을 먼저 확인한다.
- 검증 환경: Windows PowerShell, Python3.14.3, Node24.14.1. 이는 검증한 조합이지 모든 OS/버전의 통과 보장이 아니다.
- 저장소 Python requirements와 기존 환경 지침을 확인해 가상환경을 준비한다. 다른 버전이면 차이를 기록한다. 전역 Python 별칭으로 임의 실행하지 않는다.
- 프런트는 `frontend/package-lock.json` 기준으로 `npm ci`를 사용한다. 의존성이 이미 정상 설치된 현재 PC에서는 매번 재설치하지 않는다.
- Linux/macOS에서는 실행 파일 경로가 다르다. PowerShell 명령을 그대로 복사해 성공했다고 주장하지 않는다.
- 이 PC의 helper_unknown_error는 도구 시작 오류였다. 새 환경에서 같은 장애라고 가정하거나 보안 통제를 우회하지 않는다.

## 4. 구현 위치와 바꾸면 안 되는 계약

| 파일/영역 | 현재 역할 | 지켜야 할 경계 |
|---|---|---|
| `frontend/src/factory/studioLocation.ts` | new/draft/project/kit_app/release/mega URL parser/serializer | 순수 문법, 권한 근거 아님. 빈 build는 목록이며 자동 생성 안 함 |
| `studioProjectEntry.ts` | project GET 응답 검증·상태 흐름 | ID/회사 결속, abort+세대번호, 늦은 응답 폐기, 전환 후 기존 데이터 숨김 |
| `StudioProjectEntryGate.tsx` | 확인 중/거절/재조회/확인된 자식 표시 | App에 아직 연결되지 않음. 조회 가능을 실행·게시 승인으로 바꾸지 않음 |
| `api/routes/factory_control.py` | entry-metadata GET 및 B5 HOTL/구 실행 경로 | 신규 GET은 이름·ID·문서판·소유/조회 문맥만 반환. 상세 state/초안 원문 반환 안 함 |
| `core/advisor_revision_store.py` | 판본·승격 저장 및 read_only 연결 | READ는 mode=ro, DB/스키마 복구 안 함. 기본 쓰기 모드 유지 |
| `core/studio_project_context.py` | 현재 권한·승인·고정 프로젝트 문맥 확인 | 기본 READ에 읽기 모드 연결. 명시 주입 revisions 객체까지 자동 변환한 것은 아님 |
| `core/studio_hotl_submissions.py` | 원키 접수·초안 판본 원자 확인 | 원본문 일치·초안 CAS·현재 권한 검증을 제거하지 않음 |
| `api/routes/studio_execution_control.py` | 실행 명령 접수/권한/효과 경계 | RELEASE 게시 권한, 실제 효과 전후 REJECTED/UNKNOWN 구분 |
| `StudioDecisionPanel/Api/Flow`, `RunControls` | B5 입력·제출·원키 조회 연결 | 접수 확인과 실행 성공/작업 완료를 혼동하지 않음 |

앞의 프런트 짧은 파일명은 모두 `frontend/src/factory/` 아래다.

특히 다음을 보존한다.

- PROCESSING/UNKNOWN 접수는 자동 재실행하지 않는다. 원래 요청 ID로 조회한다. 같은 ID에 다른 본문을 보내지 않는다.
- 회사·사용자 변경 뒤 이전 정보/SSE/입력이 남지 않아야 한다. `setActingUser()` 자체는 전환 이벤트를 발생시키지 않으므로 새 호출 경로의 이벤트 배선을 확인한다.
- URL 문법은 최대200자의 불투명 ID를 받아도 project reader는 ASCII 영숫자/밑줄/하이픈 최대160자다. 문법 통과가 실제 대상 조회 성공은 아니다.
- 소유 조직과 조회 조직이 상위/하위 관계일 수 있다. 단순 ID 일치로 서버 권한 판정을 재구현하지 않는다.
- project GET의 fresh 선택권한 추가 검사는 해당 경로의 캐시 지연을 막는다. 다른 API의 동일 문제가 모두 수정된 것은 아니다.
- 조회 실패를 빈 결과·0건·legacy 성공으로 바꾸지 않는다. v2 마커/서버 승인 원장이 불일치하면 차단한다.

## 5. 검증된 것과 아직 검증하지 않은 것

인계 직전 검증(2026-09-15, 코드215253f22에 포함된 소스):

- 서버 **312PASS/0FAIL**, pytest70.97초, 격리 wrapper77.13초.
- 소스·보호 자산 지문 불변, 차단 파일 쓰기0, 차단 SQLite 경로0, repository conftest 미적재.
- 프런트 project entry26 + location25 + B5 contracts153 = **204PASS**.
- 제품 `npm run build` PASS(타입 검사 포함). 기존 큰 청크/정적·동적 import 혼용 경고는 남아 있다.
- **실제 브라우저·React effect·현업 수용 NOT_RUN**. SSR/모의 HTTP 검사로 대체 통과하지 않는다.
- 서버 전체 저장소 회귀가 아니다. 이전432건/전체2175건 등의 결과를 현재 코드 전체 PASS로 승계하지 않는다.

로컬 원기록은 `output/usage-holds-3fczpwg6/isolation.json` 및 `tests.xml`,
프런트 B5는 `output/studio-contracts-08dba497-230f-41c7-a076-3bc383964119/report.json`이다.
**output은 Git 제외**라 다른 PC에는 없다. 없는 파일을 확인했다고 주장하지 말고 아래 명령으로 자신의 실행 증거를 만든다.

Git으로 전달하는 [검증 요약 JSON](evidence/L2_STUDIO_2026-09-15_VERIFICATION.json)에는 선택 파일·건수·격리 판정과 참조 사본 지문을 기록했다. 로컬 실행 관측의 요약이며, 독립 서명된 증명이나 새 PC에서의 재실행을 대체하지 않는다.

### 무쓰기의 정확한 의미

- 완료: 기본 프로젝트 READ가 사용하는 RevisionStore에서 schema DDL·업무 DML 제거.
- 확인: 손상/부분/필수 열 누락/유실 DB는503, 읽기 호출로 복구·생성하지 않음.
- 확인: SQLite mode=ro 자체의 쓰기 거절, DB 본체 보존, live WAL의 서로 다른 두 커밋을 새 읽기 transaction이 모두 조회.
- 제한: SQLite는 WAL/SHM 보조파일을 만들 수 있다. `immutable=1`로 숨기면 최신 WAL을 놓칠 수 있어 금지한다.
- 잔여: 관리형 표준 팩·인증 데이터 경로의 DP Store 초기화/마이그레이션, OWNER_CERTIFIED 정책의 DecisionLedger 초기화, ECM RW 연결. 시작 singleton 초기화·거절 감사도 별도.
- 실제 managed 시험은 승인판·승격·ECM/PDP를 연결했지만 인증 데이터·표준 팩은 없는 fixture다. 모든 관리형 READ가 무쓰기라는 증거가 아니다.

## 6. 다음 20~30분: 수행 순서·완료 기준

### A. 먼저 5~10분: 재개 판정

1. 동기화·기준 커밋·소유자 불명 변경·필수 파일을 확인한다.
2. 아래 빠른 기준선 검사를 실행한다. 실패하면 기능을 붙이기 전에 원인을 분리한다.
3. 전역 연결에 필요한 원본 통합계획 Gate 증거를 찾는다. 과거 HOLD 문구만으로 영구 차단하거나 사본 확보만으로 PASS로 바꾸지 않는다.
4. `frontend/src/App.tsx`, `components/BuildPage.tsx`, 기존 프로젝트 복원/URL 갱신/Studio 렌더 경로를 읽고 **현재 화면→목표 화면→수정 파일→확인 시나리오**를 먼저 한국어로 보고한다.
5. 사용자의 Claude Code 이관 요청에 따라 다음 세션의 단독 구현 담당을 Claude Code로 인계한다. 전역 진입점을 동시에 수정하는 다른 담당이 없는지 확인한다. 단독 담당 조건과 통합 Gate 조건은 그대로다.

### B. 조건이 충족되면: project 경로 한 개만 첫 연결

- 기존 project 직접 링크를 순수 location 해석→서버 entry 확인→확인된 Studio 하나의 흐름에 연결하는 최소 변경을 설계한다.
- 실제 기존 진입 경로를 먼저 확인하고 연결 위치를 결정한다. 이 문서의 추측으로 두 번째 Studio를 더 렌더하지 않는다.
- new/draft/kit/release/mega 전체 연결, 전역 디자인 재구성, 신규 데이터 이관을 같은 묶음에 포함하지 않는다.
- 확인 전/권한 거절/회사 전환 후에는 이전 Studio를 표시하지 않는다.
- 직접 링크/뒤로·앞으로/새로고침으로 프로젝트 생성·실행 POST가 재전송되지 않도록 한다.
- 이전 URL 자동복원과 새 resolver가 서로 덮어쓰지 않아야 한다. SSE 구독 해제와 선택 프로젝트 저장 위치도 함께 확인한다.
- 전역 mount 변경은 기능·계약 변경과 별도 커밋 단위로 유지한다.

### C. 증거가 부족하거나 환경이 막히면

- Gate/브라우저/데이터/담당 조건 중 **무엇이 없고 어떤 증거가 필요한지** 보고한다.
- 없는 DB를 만들어 성공시키거나 인증 권한을 낮추지 않는다. 다른 저장소 전면 리팩터링으로 범위를 넓히지도 않는다.
- 안전한 독립 모듈 작업이 남아 있으면 수정 범위를 먼저 밝힌다. 허용 범위 안에서 할 일이 없으면 중단하고 사용자에게 필요한 결정 한 가지를 요청한다.
- 20~30분을 넘겨 자동 확장하지 않는다. 완료·진행·미착수를 구분해 전체 진척도와 다음 예상 시간을 보고한다.

완료 기준: 연결한 경로의 코드/시험 통과와 실제 브라우저 증거를 별도로 기록한다.
브라우저를 못 돌렸으면 「구현 및 계약검사 완료, 화면 수용 미완료」라고 보고한다. B6 전체 완료로 가산하지 않는다.

## 7. 복사 가능한 검증 명령

모든 Python 소스 편집과 병렬 작성자를 먼저 동결한다. 운영 데이터를 사용하는 일반 pytest를 먼저 실행하지 않는다.

빠른 기준선(저장소 루트):

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_revision_reads.py --target tests/test_b6_project_entry.py
node frontend/scripts/check-project-entry.mjs
node frontend/scripts/check-studio-location.mjs
```

현재 소스 기준 서버46건·프런트26/25건이 기대치다. 실행 환경/소스가 달라지면 수집 수부터 대조한다.

인계312건 재현(저장소 루트):

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_revision_reads.py --target tests/test_b6_project_entry.py --target tests/test_b3_advisor_revisions.py --target tests/test_b3_execution_context.py --target tests/test_b3_studio_drafts.py --target tests/test_b5_hotl_submission_api.py --target tests/test_b5_project_commands.py --target tests/test_b5_hotl_submissions.py
```

프런트 추가 확인(`frontend` 폴더):

```powershell
node scripts/check-studio-contracts.mjs
npx.cmd tsc --noEmit --incremental false
npm.cmd run build
```

각 명령의 종료 코드와 보고서를 **각각** 확인한다. 여러 명령을 연속 실행한 마지막 exit0만으로 앞 검사의 통과를 판단하지 않는다.
wrapper가 소스/자산 변경 또는 격리 위반을 보고하면 pytest PASS 수와 관계없이 실패다.
기존 키트검토/릴리스준비 확대 회귀는 합계 약14분이 걸렸으므로 관련 변경/통합 출구에서 선택한다. 단순 문서/프런트 반복마다 전체를 다시 돌리지 않는다.
전체 검증 방법론은 `docs/testing_efficiency_2026-09-13.md`를 따른다.

## 8. 다른 PC의 데이터: 코드 pull과 복원을 분리한다

이번에는 운영 데이터를 수정하거나 새 스냅샷을 생성하지 않았다. 기존 2026-09-13 스냅샷이 Git에 남아 있다.

- 파일: `data_sync/session-data-20260913.aesgcm`
- 암호문 SHA256: `c0dded58abf4eb0b8e30ba0c8f2504b70024651b38c32f657cd6bac718809790` — 이번 인계에서도 일치 확인.
- 13,672,011bytes /164파일 /15DB /143RAW. 공개 manifest는 `data_sync/snapshot-public.json`.
- 복호화 키는 Git에 없다. 사용자에게 비공개 경로로 별도 전달받는다. 키 값이나 평문 DB를 문서/커밋/로그에 기록하지 않는다.
- 이 스냅샷은 **09-13 시점**이다. 이후 운영 데이터까지 자동 동기화됐다고 말하지 않는다.
- auth.db/비밀번호/세션/커넥터/Advisor 개인 대화/생성 프로젝트/체크포인트/library는 제외돼 있다.
- 따라서 복원해도 기존 생성 작업·로그인·모든 실행 상태가 자동 재현되지는 않는다. 프로젝트/판본 누락을 임의 생성이나 downgrade로 우회하지 않는다.

[공식 복원 가이드](../../data_sync/README.md)를 전문으로 읽은 뒤:

1. **현재 원본 PC:** 기존 데이터가 있으므로 다시 복원하지 않는다.
2. **다른 PC의 동일 절대 루트** `C:/WorkSpace/gemini_agent_team_verG`: 앱을 띄우기 전에 새 checkout에 복원한다. 키 경로를 실제 비공개 파일로 지정하고 먼저 verify한다.
3. **다른 폴더/OS:** `--copy-only`는 검사 사본만 만든다. 제품 실행용 데이터로 간주하지 않는다.
4. 복원이 기존 DB/설정 때문에 거절되면 삭제로 해결하지 않는다. 다른 복원 위치 또는 별도 이관 결정을 요청한다.
5. 새 로그인 사용자/역할·참조 RAW·Starter·프로젝트의 적격성과 가시성을 확인해야 실제 재개가 된다.

원본 PC와 같은 비공개 키 경로를 준비한 경우의 verify 예시:

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py verify --bundle data_sync/session-data-20260913.aesgcm --key-file output/session-handoff/session-data-20260913.key
```

키가 없으면 이 명령을 성공시킬 수 없다. 키를 찾기 위해 다른 자격증명 저장소를 탐색하지 않는다.
암호화 스냅샷이 없어도 §7의 합성 격리 검사는 수행할 수 있다. 화면용 운영 데이터와 시험 데이터를 섞지 않는다.

## 9. 재발 방지·중단 조건

다음은 작업을 쉽게 끝내기 위한 허용 옵션이 아니다.

- 테스트가 실패한다고 권한/지문/원키/초안 CAS 검사 삭제.
- 회사 변경 이벤트 없이 이전 응답을 표시하거나, 모의 응답 PASS를 실제 DOM PASS로 표시.
- 비어 있는 DB를 정상 legacy로 간주하거나 손상 테이블을 GET에서 복구.
- readonly 검사를 예열 또는 immutable DB로 통과시키기.
- 과거 통합 커밋의 전체 merge/cherry-pick을 새 branch에 무조건 적용.
- 소유자 모르는 변경을 커밋하거나 `git add .`/`git add -A`로 로그·데이터까지 포함.
- 데이터 경로를 문자열 치환해 서명·지문을 깨뜨리거나 운영 DB에서 마이그레이션 시험.
- 과거 소요시간만 보고 검사 범위를 무한 확대하거나 상태보고만 하고 구현 범위를 설명하지 않기.

중단 시 실제 실패 명령/종료코드/대상/보존 상태/필요한 결정만 보고한다. 오류가 없는 것처럼 인계를 덮어쓰지 않는다.

## 10. Claude Code에 전달할 재개 프롬프트

> 이 브랜치의 docs/handoff/CLAUDE_CODE_START_HERE_2026-09-15.md부터 읽고, 문서가 지정한 상위 문서와 최신 인계를 확인하세요. 전체21/40=52.5%, 로컬18/28≈64.3%가 기준입니다. 이미 구현된 B5 결함 수정·B6 URL/entry 모듈·RevisionStore READ 초기화 제거를 다시 만들지 마세요. 먼저 기준 커밋과 변경 소유를 확인하고 빠른 격리 검사를 실행한 뒤, 다음 project 진입 연결을20~30분 한 묶음으로 설계·검토·진행하세요. 전역 연결 Gate 증거가 없으면 무엇이 부족한지 밝히고 강행하지 마세요. 수정 전에 현재 화면/목표 화면/대상 파일/검증 범위를 한국어로 설명하고, 중간 진행과 단계 종료 시 전체 진척도·다음 예상 시간을 보고하세요. 운영 데이터·기존 로그·비밀키를 수정/커밋하지 말고, 실제 브라우저 미실행을 통과로 표시하지 마세요.
