# B4 이후 검증 운영 개선 — 2026-09-13

## B4 첫 안정판 전체 회귀 — 2026-09-13 12:58 KST

후속 필수 출구였던 **동일 백엔드 소스판 full/jobs1 PASS를 확보했다.** `output/verification-axojhsot/summary.json`, parent exit0/FULL_REGISTERED/2194정확수집·실행,2187PASS7환경skip/186subtestsPASS/실패0/총1645.47초(27분25초). 이전2110누락0·신규84(B457포함),소스771·보호자산259전후현재불변,SQLite3051회모두RUN,금지접근0이다. 아래11:49제한마감과실패full은당시이력으로보존한다.

최신 집중 `usage-holds-r13oyl3d`203실행/202PASS1skip/34.87초,프런트별도37단위·SSR PASS/제품·fixture빌드·타입·지정lint PASS. 검증대상과소스가바뀌었으므로 과거실행과동일조건속도향상률을주장하지않는다. 기본jobs1유지. 실제브라우저는도구초기화환경오류로NOT_RUN,제품전체52.5%유지이며이회귀는저장소전체T3/실사용수용이아니다.

다음 B4 승인·변경안 연결에서는 exact/feature로 반복하고, 새로운 안정통합점에서 full을 실행한다. 구체 인계는 `docs/handoff/L2_STUDIO_B4_INSTALLATION_FLOW_2026-09-13.md`를 참조한다.

### 이전 1차 효율화 마감 이력

> 최종 판정: **1차 효율화의 제한 범위 검증 완료. 전체 통합 PASS는 아니다.**
> 최신 quick215사례는35.54초/집계PASS. 전체2110사례 시도는37분52초/11FAIL이며 기록을 보존한다.
> 실패 원인이었던 두 시험의 상대 출력 경로만 수정한 뒤 해당51사례+self171사례를 재검증했다.
> 다음 B4 안정 통합 시 동일 소스판 full/jobs=1을 필수 출구로 남긴다. 전체 제품52.5%는 그대로다.

## 승인 범위와 성공 기준

작성 Codex. 사용자가 테스트·기능 검사 효율화 제안을 모두 승인하여 B4보다 먼저 적용한다.
제품 진척은 전체21/40=52.5%, 로컬18/28이며 이 개선을 제품 완료 점수로 더하지 않는다.
권고4·7·10/G2-A/B/C→G3-B/C의 후속 구현 비용을 줄이는 지원 작업이지 새 제품 관문 완료가 아니다.

기존 비교 기준은 `output/usage-holds-6m4qchly`: B0~B3 1923PASS/6skip,
2183.28초(36분23초), SQLite2492, 소스369·자산259 불변이다. 전체 저장소 T3나 브라우저 완료가 아니다.
상위5파일166케이스가 시험시간 약81.5%를 차지했고, 단일 schema 표본은 시험 본문보다 설치·인증 준비와
무관한 모듈 초기화에 대부분의 시간을 썼다. 프로파일러 실행 시간과 비프로파일러 시간을 직접 비교하지 않는다.

목표는 빠른 확인 1분 이내, 기능 묶음3~5분, 안정된 통합 후보에 전체 등록 회귀1회다.
이는 목표이며 실제 시간·같은 범위·환경 조건을 측정한 후에만 달성으로 표시한다.
실패 후에는 관련 최소 회귀를 먼저 실행하고, 수정이 끝난 최종 소스 판본으로 전체 회귀한다.
시간을 맞추려고 필수 보안·권한·데이터 경계 시험을 제외하거나 skip 처리하지 않는다.

## 실행 계층

| 계층 | 언제 | 선택·판정 |
|---|---|---|
| quick | 편집 직후 | 명시한 순수 schema/HOTL/결정차수 및 도구 자체 시험. 부분 검사임을 표시 |
| feature | 사용자 흐름 한 묶음 완료 | 변경→계약→소비자 매핑. 공통·미지정·삭제·동적 의존성·fixture 소비자 불명은 full 승격 |
| full | 안정된 통합 후보·완료 인계 | 기존 B0~B3와 새 B3/verification 회귀. 사전수집 nodeid 전부를 정확히 한 번 실행 |

사용 명령(PowerShell, 저장소 루트):

```powershell
venv/Scripts/python.exe -B scripts/run_verification.py --tier quick --jobs 1
venv/Scripts/python.exe -B scripts/run_verification.py --tier feature --changed core/enterprise_context/process_configuration.py --jobs 2 --plan-only
venv/Scripts/python.exe -B scripts/run_verification.py --tier full --jobs 1
```

`--changed`는 반복 가능하다. 미지정 feature는 full이다. quick에 변경 경로를 주어도 영향 검사를 생략하지 않는다.
기본은 jobs=1이다. jobs=2는 격리된 선택 옵션이며 일괄 활성화하지 않는다. quick 동범위 비교에서 이득이
없었고, 이번 full 병렬 실행에서도 큰 시간 절감을 확인하지 못했다. 병렬 가능성과 성능 개선은 별개다.
선택기는 정적이며 자동 영향 분석의 완전성을 주장하지 않는다. 범위가 불확실하면 full로 돌아간다.
기존 `verify_data_usage_holds.py --b0 --b1 --b2 --b3`도 유지한다.
단일 오류 재현은 `--target tests/test_*.py::test_name --strict-writes`를 쓰고 전체 성공으로 보고하지 않는다.

## 준비 데이터와 병렬 격리

- 순수 schema projection5사례는 실제 순수 함수를 최소 합성 입력으로 검사한다. 실제 설치·8인증을 수행하는 cold 동등성 시험은 별도 유지한다.
- 키트 seed는 이번 pytest 프로세스 안에서 실제 설치·인증으로 한 번 생성한다. 과거 실행 검색/재사용은 없다.
- 매 시험은 ECM·데이터 준비·조직·원장 네 SQLite의 독립 backup과 새 서비스를 받는다. 공유 연결·현재 권한 판정 캐시는 없다.
- seed 파일/논리 지문·소스·원장·고정 binding/snapshot/계약 동등성, 역할 회수·사용 보류·계약 revision의 복사본 간 비전파를 검사한다.
- 병렬은 최대2개 외부 worker로 시작한다. 각 worker가 독립 audit와 신규 RUN을 갖고 SQLite/파일 쓰기는 자기 RUN 내부만 허용한다.
- worker 내부 subprocess, SQLite URI/:memory:, 실제 원본 쓰기, xdist 감사 우회는 허용하지 않는다. 로그·temp도 RUN 내부다.
- 사전수집과 실행의 소스/자산 지문, 예상·실행 nodeid, setup/call/teardown 결과를 대조한다. 중복·누락·빈 실행·중도 종료·낡은 보고서는 FAIL이다.
- 무관한 무거운 모듈 초기화 생략은 검토한 경량 시험 파일에 한한다. 나머지는 pytest 시작 전에 실제 모듈을 RUN cwd에서 초기화한다. 실행 중 전역 cwd를 바꾸는 지연 초기화는 하지 않는다.

## B4 작업 단위와 조기 이중검토

먼저 API만 모두 끝내거나 UI를 마지막에 몰지 않는다. 다음 사용자 흐름마다 API·상태·UI·검증을 함께 완결한다.

1. 설치 시작: catalog → 명시 등록 → 고정 plan/digest → start → operation 확인.
   검수: 데이터가 없는 키트의 NO_DATA/DOMAIN_REVIEW_REQUIRED를 준비 완료로 보이지 않는다.
2. 업무 탐색: 실제 검증된 운영 root → L1/L2 선택 → 선택 범위에서 허용된 행동.
   검수: 화면 배치의 default_parent_id나 역할 capability 집합을 운영 root/행동 권한으로 오인하지 않는다.
3. 구성 변경: 이름/설명/순서/이동 제안 → 변경 상세 → 별도 승인자 대기목록·승인.
   검수: 제안자 자기승인 차단, stale revision 충돌, 현재 권한 재검사, 데이터 보류 유지.
4. 재접속·실패 복구: operation/변경안 GET → 최신 revision 채택 → 승인 상태와 재조회.
   검수: 응답 유실 뒤 자동 중복 설치하지 않음, 기존 plan 원문/digest/request 식별자 보존.

각 흐름은 구현 전 수용 기준·상태 전이·실패 경계·대응 시험을 1행씩 연결한다.
권한/데이터/API 계약은 첫 연결 시 독립검토하고 지적을 해당 작은 회귀로 잠근다.
브라우저에서는 최초 사용자가 무엇을 눌러야 하는지, 로딩/빈값/권한없음/오류/복구/새로고침까지 확인한다.
브라우저·현업 수용을 Python 회귀 통과로 대체하지 않는다. B4 전체 기존 예상150~240분은 실제 첫 흐름 측정 후 갱신한다.

프런트 변경은 별도 관문이다. `frontend/package.json`의 기존 `npm run lint`, `npm run build`
(타입 검사+Vite 및 기존 prebuild 포함)을 흐름 단위 완료 시 실행하고 실제 화면 검사를 더한다.
이 Python 실행기는 프런트 빌드/브라우저를 자동 수행하지 않는다. 현재 등록 full은 B0~B3 한정이다.
B4 새 시험을 작성할 때 선택기의 full 등록·변경 계약 매핑·수용 기준을 함께 갱신해야 한다.
등록되지 않은 미래 B4 시험까지 자동 검증됐다고 해석하지 않는다. 기능 묶음3~5분 목표가 미달이면
작은 흐름의 정확한 nodeid 확인을 빠른 피드백으로 쓰되, 필수 통합 관문은 그대로 남긴다.

첫 흐름 구현 인계(11:09 Hooke 읽기 전용 대조, 구현 미착수):

- 서버 `api/routes/process_installation_control.py`의 catalog/register/plan/start/get을 사용한다.
  `frontend/src/lib/companyApi.ts`에는 아직 설치 adapter가 없으므로 v2 DTO/구조화 오류와 함께 추가한다.
- 기존 진입점은 `CompanySetupPanel.tsx`의 profile `load()`와 `KitOperationsPanel.tsx`의
  `listInstances()`다. instance 목록을 설치 operation 목록으로 오인하지 않는다.
- 먼저 검증된 boundary/permitted_actions와 범위별 operation 목록의 누락을 메운다.
  start 응답 ID로 GET·새로고침하며 재접속 시 POST를 다시 호출하지 않는다.
- 수용 기준→시험: catalog 조회만으로 register 호출0/NO_DATA·검토필요 표시,
  Plan 원문·digest·client_request_id 보존/중복 클릭/409 후 입력 유지,
  재접속 GET-only/문맥 변경 후 늦은 응답 폐기/503을 빈 목록과 구분.
  실제 서버 근거는 `test_b2_installation_api.py`·`test_b2_installation.py`이며 UI 검사는 새로 연결한다.

## 기록·소유권

Codex=격리 runner/guard·시간측정·실제 실행·문서, James=순수 선택기·자체시험,
Hooke=키트 fixture/seed·격리시험, Dewey=외부 dispatcher·증거 집계·자체시험,
Hilbert=독립 읽기 전용 보안/증거 검토. 공유 파일 한 편집자. 최종 측정 전 전원 소스 동결.

보고에는 전체 제품 진척, 이번 완료 조건, 대상 수/실행 수/실패·skip, 실제 wall time,
보호 판정, 이전 동일 범위와의 차이, 남은 위험 및 다음 예상 시간을 함께 적는다.
setup/call/teardown 합은 병렬 전체 wall time과 구별한다. 테스트 수나 배치 수를 제품 점수로 세지 않는다.

## 실측 결과와 남은 출구

중간 실측(최종 full 증거와 구분):

- `usage-holds-b5wg66m6`: schema projection5PASS/pytest0.29초/실행기0.81초, 소스·자산불변/금지접근0.
  이전 동일5사례의 setup+call+teardown 합계는26.06초였다. 측정 층위 차이를 숨기지 않는다.
- `usage-holds-x0o43m1q`: kit/seed59PASS/573.09초. 동일기존49사례751.102→481.27초(약36% 감소).
  도구5파일의 동시 개발로 sources_unchanged=false/wrapper1: 최종 통합 PASS로 사용하지 않는다.
- `verification-2ncdi0tv`/`verification-cvkam3mv`: 동일 quick188nodeid 순차11.57초/병렬11.53초, 둘 다 집계PASS.
  작은 묶음의 병렬 이득은 확인되지 않아 기본 jobs=1을 유지한다. 이후 보강 시험이 추가됐다.
- `verification-7pgatt2q`: 환경 PYTEST_ADDOPTS/PYTEST_PLUGINS 주입 조건에서도 quick215nodeid/12.35초/집계PASS.
- 실제 audit probe: 다른 RUN 파일쓰기·SQLite·mkdir·os.system을 실행 전에 차단했고 목적 파일이 생기지 않았다.
  Windows os.startfile 실제 호출도 실행 전에 차단했다. 보호 예외를 추가하지 않았다.
- 정확한 HOTL `[hotl/resume-1]` 선택 과정에서 수집 순서 의존을 찾아, 경량 이외 실행의 실제 빈 조직
  singleton을 RUN에서 pytest 전에 초기화하도록 했다. 원본/정책 대역 없음. `usage-holds-qkj0ij88`1PASS/0.70초/wrapper0.
- 독립 Hilbert: 외부 실행·환경 선택 주입·파라미터 선택·상대 dir_fd 4건 수정 후 정적종결, 추가P1/P2없음.
  pytest subtest는 기본 phase와 분리하되 실패를 보존하며, UTF-8 로그 설정은 판정/가드와 무관하다.
- full 시도 `verification-5xyfosvs`: 실제2110사례 실행, 기존1929누락0/신규181,
  **2092PASS/11FAIL/7skip/subtest186PASS**, 부모 집계FAIL. 전체벽시계2272.45초(37분52초).
  기존36분23초 대비 큰 단축은 확인되지 않았고, 시험 수·가드·병렬 조건도 달라 순수 병렬 효과로 해석하지 않는다.
  각 worker 소스770·자산259 불변, SQLite2252+651개 모두각자RUN, 금지SQLite0.
  상대 write-open11회는 가드가 차단했으며 실제 외부 파일 쓰기는 없었다.
- 11실패는 `test_contract_decision_api.py`10건과 `test_tech_lead_contract_draft.py`1건의
  상대 출력 경로였다. 전자는 기존 tmp_path 하위 절대 경로로, 후자는 해당 시험의 `Path("data")`만
  tmp/data로 연결했다. 실제 번들 작성과 status/reason readback을 확인하며 생산 코드·가드는 바꾸지 않았다.
- 수정 후 `usage-holds-6q1sonnm`: 해당 두 파일51사례 + selftest171사례,
  **221PASS/1환경skip/subtest186PASS**, pytest31.51초/실행기52.34초/wrapper0,
  SQLite31 모두RUN/금지접근0/소스770·자산259 불변. full 이후 소스 해시 차이는 정확히 이 두 시험 파일뿐이다.
- 최신 `verification-imhhufyo`: **quick215사례(214PASS/1환경skip), subtest186PASS,
  전체벽시계35.54초/부모SELECTED PASS**. collector·worker 소스/자산 지문 일치, SQLite·파일 금지접근0,
  감사·환경 정리 적용, conftest미로딩. 1분 목표를 충족했으나 이전12.35초와의 차이를 숨기지 않는다.
  단회 실측이므로 평균 성능·모든 환경의 시간을 보증하지 않는다. 기능 묶음3~5분 목표는 아직 미확인이다.
- 취소 probe `verification-hka1q8yz`: 실제 worker 시작30초 뒤 같은 취소 처리기의 flag를 켜
  CANCELLED/종료130/PASS미발행/관리자식 종료를 확인했다. main의 Windows CIM 조회에서도
  해당 launcher PID와 직접 자식 잔존0이었다. OS hard-kill/모든 플랫폼 종료를 보증하는 시험은 아니다.
  Windows venv가 실제 인터프리터를 따로 시작하는 점은 [CPython 3.14 원본](https://github.com/python/cpython/blob/3.14/PC/venvlauncher.c)도 대조했다.

독립 최종 판단(Codex 요청/Hilbert 검토): 두 fixture 수정만의 영향 범위 검증은 종결 가능하며 지금
전체를 다시 실행하는 것은 필수로 보지 않는다. 제품·runner·guard 불변, 해당두파일전체51+self171 통과를
확인한 제한적 판단이다. **기존 full FAIL을 PASS로 바꾸거나 서로 다른 소스판 결과를 합쳐 전체 통과라고
표시하지 않는다.** 다음 B4 안정 통합의 동일판 full/jobs=1은 반드시 남긴다.

실제 symlink 생성권이 필요한7사례는 환경 제약으로 전체 시도에서 skip되었다. POSIX dir_fd 실제 실행도
이번 Windows 실측 범위가 아니다. 브라우저·실제 LLM·현업 수용·운영 배포 검증을 대체하지 않는다.

보존: 사용자 interaction_log 기존10줄 SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510,
main.py/App.tsx·생산 코드·원본자산·운영 DB/RAW/실권한/원격 불변. 변경은 로컬 미커밋·미푸시다.
