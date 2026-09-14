# B5 결함 수정 및 B6 첫 연결 준비 인계

> 최신 재개 입구: [Claude Code 시작 안내](CLAUDE_CODE_START_HERE_2026-09-15.md). 아래는 각 시점의 작업 기록이다. 과거 「다음 C0/adapter 구현」「미커밋·미푸시」를 현재 지시로 사용하지 않는다. 현재 코드 커밋은215253f22, B6 후속 구현·검증 및 전달 조건은 시작 안내를 따른다.

작성: Codex · 2026-09-14 KST · 권고10 / G3. 사용자 승인 「결함 정리하고 계속 진도」에 따른 구현이다.

## 기준선과 보존 범위

- 기준선 `codex/l2-unified-studio-20260912` / `dd0573383`. 이전 pull 이후 미커밋 수정이며 이번 작업에서 push하지 않는다.
- 전체 **21/40=52.5%**, 로컬 **18/28≈64.3%**. 결함 수·시험 수를 제품 관문에 더하지 않는다.
- 기존 사용자 변경 `data/interaction_log.jsonl` 보존. SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`.
- 운영 DB·키·암호문·실제 프로젝트 산출물은 수정하지 않는다. 검사는 `output/usage-holds-*` 격리 자산만 사용한다.

## 구현한 사용자 동작

| 문제 | 수정 내용 | 검증 범위/한계 |
|---|---|---|
| RELEASE가 일반 실행 권한으로 접수됨 | 명령별 fresh 권한; RELEASE는 게시 권한도 필수, 예약·실행·응답 경계 재확인 | 실제 HTTP/PDP/접수 원장. 실행 엔진은 대역 |
| 게시/재분할 사전 거절도 UNKNOWN으로 잠김 | 효과 표시는 실제 첫 쓰기로 이동. 순수 사전 거절은 REJECTED, 쓰기 뒤 오류는 UNKNOWN | 실제 handler와 합성 파일. 실제 배포 아님 |
| 구 release/replan API가 영속 잠금을 우회 | 기존 경로에도 배타 예약·PROCESSING/UNKNOWN 확인; 게시 직전 fresh 게시 권한 | 기존 HTTP 경로도 별도 검사 |
| 명확화에 DTO 대신 bool 전달, legacy 분기 누락 | 실제 서버 문맥 DTO 전달, 현재 checkpoint가 명확화 종류를 결정 | legacy·managed·일반 HOTL 저장→제출→조회→소비 |
| 저장하지 않은 본문으로 초안 결속 가능 | 일반 의견은 원문, 명확화는 서버 조합 본문을 저장 초안과 대조 | 명확화 DTO 승인 승격 자체는 B3 범위 |
| 본문 검사 뒤 다른 탭의 저장/폐기 경쟁 | 접수 INSERT와 같은 BEGIN IMMEDIATE 연결에서 초안 상태·대상·revision·digest 재검사 | 권한·질문 조회는 락 밖. 접수 후 편집 전체를 잠그는 기능은 아님 |
| 원키 replay가 현재 질문 소멸 후 실패 | 원접수 조회·원본문 대조를 현재 차수 검사보다 먼저 수행 | 다른 본문 재전송은 409, 같은 본문은 재실행 없음 |
| PROCESSING/UNKNOWN/REJECTED를 재개 성공으로 표시 | API `submission_recorded`와 프런트 미확정/거절 상태 분리 | ACCEPTED만 사용완료 근거. 작업 완료를 뜻하지 않음 |
| GET 대기 중 권한 회수 후 원문 노출 | 조회 전후 fresh 문맥·권한 확인 | 역할 변경 후에도 주 소속 읽기 권한이 남는 정상 정책은 유지 |
| HTTP 취소가 PROCESSING 기록을 남김 | 접수부터 종결까지 worker 회수; 엔진 자체 취소는 UNKNOWN 기록 후 취소 재전파 | 프로세스 강제 종료·운영 복구는 미구현 |
| 결정 패널 effect 반복과 일반 의견 초안 불일치 | 안정적인 setter, 빈 selections 정규화, 현재 대상·본문과 같은 초안만 사용 | 실제 React effect는 NOT_RUN; STATIC/UNIT만 통과 |
| 접수 GET의 다른 초안/본문을 성공으로 받아들임 | 원요청·원대상·초안 참조 및 실제 SHA256 지문 검증 | POST 요약과 GET 전체 기록을 다른 계약으로 취급 |
| release/replan 문맥 왕복 후 재확인 잠김 | 영속 접수 기반 명령으로 분류해 기존 원키 조회 사용 | 실제 화면 왕복은 NOT_RUN |

추가로 기존 B3 실패 시험은 가짜 Principal과 권한 우회 대역을 제거하고 실제 격리 Principal·소유권·AdvisorStore로 수정했다. 제품 권한을 낮추어 시험을 통과시키지 않았다.

## 중요한 서버 계약

- `HOTLSubmissionStore.begin(..., require_current_draft=True)`는 HTTP 접수에서 필수다. 기본값 false는 기존 독립 원장 사용의 호환성용이며, HTTP 본문에서 선택할 수 없다.
- 저장된 같은 요청의 replay는 현재 초안이 소비/수정됐어도 원기록을 반환한다. 새 요청은 현재 초안 판본을 요구한다.
- `resumed`는 ACCEPTED 또는 기존 비결속 호출에만 쓴다. 나머지 기록은 `submission_recorded`; 미확정을 자동 재전송하거나 초안을 자동 폐기하지 않는다.
- 전체 GET 기록의 지문과 POST 요약을 혼동하지 않는다. 프런트는 GET을 원요청과 대조하며 늦은 회사/사용자 문맥 응답은 폐기한다.
- 접수·초안은 같은 Advisor DB에서 원자적으로 검사하지만 DB와 실행 엔진 전체의 분산 트랜잭션은 아니다. 서버 강제 종료로 남은 PROCESSING/UNKNOWN을 자동 확정하는 운영 기능은 이번 범위가 아니다.

## 검증 기록

- 첫 서버 집중 검사: **59 PASS / 2 FAIL**, 총61건, `output/usage-holds-kopd8ksc/isolation.json`. 실패는 숨기지 않는다.
  - 권한 회수 시험이 부서 역할만 변경해 주 소속의 정상 읽기 권한이 유지됐다. 실제 격리 계정 회수로 시험을 수정했다.
  - 릴리스 시험의 지연 import가 상위 RUN DB를 열어 더 좁은 시험별 SQLite guard에 걸렸다. 시험별 DB를 import 전에 주입했고 guard를 완화하지 않았다.
- 프런트 집중 **153 PASS / 0 FAIL**, `output/studio-contracts-c673a662-48f1-4e81-b66e-f78aa8e5b986/report.json`. 실제 SHA256, 모의 네트워크, UNIT/API/SSR/STATIC 혼합이다.
- 제품 `npm run build` PASS. 큰 청크·정적/동적 import 중복 경고는 남으며 이번 결함으로 오인하지 않는다.
- 설치 흐름105 PASS, `output/process-installation-check-da9a2b4a-f372-48a0-a937-0646a44c6398/report.json`. 키트15 render PASS + 독립 소스11 PASS.
- 최종 서버 확대 집중검사: **432 수집·실행 / 432 PASS / 0 FAIL**, pytest989.23초·전체995.17초. B5 전체와 B3 HOTL/실행문맥/릴리스 준비, 기존 릴리스 테넌트 시험. `output/usage-holds-bza0vdwu/isolation.json` 및 `tests.xml`에 기록됐다. `sources_unchanged=true`, `protected_assets_unchanged=true`, 금지 파일·SQLite 쓰기0, repository conftest 미적재, SQLite 경로1297개 모두 격리 RUN 내부다.
- 실제 화면: **NOT_RUN**. computer-use 스킬을 읽고 브라우저 도구 2회 및 지시된 런타임 초기화를 시도했으나 Windows helper/kernel 시작 오류. 화면을 보거나 조작했다는 증거가 없다.

## 다음 단계 경계

- 통합계획 원본은 현재 PC의 `workspace/codex-three-week-mvp/docs/roadmap/PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`에 있고 전문을 읽었다. 「원본 미확보」 장애는 이 PC에서는 해소됐다.
- 문서 확보가 과거 통합 HOLD의 해제 증거는 아니다. 브랜치 통합·전역 진입 연결은 원본의 clean 기준선/단계별 Gate를 별도 확인한다. `App.tsx`는 Codex 단독 담당이다.
- B6-C0 첫 작업은 순수 진입 대상 parser/serializer다. 새 제작·초안·프로젝트·키트 앱·릴리스·메가를 닫힌 union으로 구분하고 모호한 ID를 거절한다. 이 모듈 작성은 전역 mount 변경이 아니다.
- 다음 실제 연결에서는 기존 App의 project 자동복원/replaceState와 충돌하지 않도록 한 resolver로 옮기고, target별 서버 귀속을 확인한 다음 단일 Studio를 표시해야 한다. 조회만으로 프로젝트/초안을 생성하지 않는다.
- 필수 실제 화면 확인: ① 초안 저장 effect 안정성·ACCEPTED 소비 ② 직접 링크/뒤·앞/새로고침 단일 mount·POST 재실행 없음 ③ 회사/인증 전환의 늦은 응답·SSE·입력/초점 보호.
- B5 전체 수용, B6 전역 연결 완료, B7 표준 업데이트/복원·현업 수용은 완료로 가산하지 않는다.

## 후속 판정

### B6-C0 첫 모듈 — 22:42 KST

- `frontend/src/factory/studioLocation.ts`: 6종 target, MATCH/LIST/NOT_STUDIO/INVALID_TARGET 분리, target 없는 build는 목록. 구 project 링크만 project 대상으로 정규화한다.
- 정규 URL 키는 `space=build`, `target`, `project`, `draft_kind/draft/revision`, `instance/app/release`, `mega/child`다. `configuration/process`는 위치 힌트이며 권한 근거가 아니다.
- 내부 return target만 인코딩해 보존한다. 충돌 ID·중복 소유 키·빈 ID·잘못된 revision·외부 URL·중첩 return을 거절한다. 다른 공간의 query는 Studio가 가로채지 않는다.
- React/store/API/history를 연결하지 않은 순수 모듈이다. 서버 자산 존재/소속/권한·실제 ID 형식은 다음 reader adapter에서 확인한다. 지금 App에 import하지 않았으므로 사용자의 현재 진입 동작은 바뀌지 않는다.
- 메인 교차검토에서 복귀 목록의 문자열 강제변환, 다른 제품 공간의 오인식, 숨김 객체 속성 누락을 수정했다.
- `node frontend/scripts/check-studio-location.mjs`: **25 PASS / 0 FAIL**(UNIT23·STATIC1·해시보존1). 메인도 독립 재실행했다. tsc·lint PASS, 최종 제품 build PASS.
- 모듈 SHA256 `53e64f59bc0eae32f02e3a1bd1d21ab19ca831f49b3f4c581bea06611e3703fc`. 신규 검사 스크립트는 콘솔 결과만 출력하며 파일을 쓰지 않는다.

### 최종 판정 — 22:48 KST

- B5 이번 결함 수정 묶음은 구현·집중 회귀·독립 소스 대조를 완료했다. Hilbert는 main API 수정, main은 Hilbert의 권한/원장 수정과 Hooke의 프런트/C0 변경을 검토했다. 지적 수정 후 해당 범위의 추가 P1은 확인되지 않았다.
- **B5 전체 수용 미완료 / B6-C0 순수 모듈 완료 / B6 전역 연결 미구현 / B7 미완료**다. 브라우저 없이 effect·단일 mount·회사/SSE 왕복을 통과로 표시하지 않는다.
- 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 코드 결함 수정과 제품 관문 완료는 구분한다. 새로운 사용자 화면은 아직 열리지 않으며, 이번 사용자 동작 변화는 B5 오류 경계 수정이다.
- 검사시간의 주된 비용은 기존 `test_b5_kit_review_api.py` 36건586.80초와 `test_b3_release_readiness.py` 29건270.32초다. 합계857.12초로 pytest시간의 약87%다. 이후 프런트 연결 반복은 25건/153건/타입 검사를 먼저 쓰고, 이 무거운 묶음은 관련 서버 변경 또는 통합 출구에서 실행한다. 보호·권한 검증을 제거하지 않는다.
- 다음: target별 서버 귀속 확인 adapter와 단일 진입 연결 1차 **90~150분 예상**. 실제 화면 도구 정상화 대기 시간은 제외한다. 전역 연결 전에 통합 원본의 Gate 증거 및 변경 기준선을 확인한다.
- commit/push 미실행. 기존 로그는 별도 사용자 변경으로 남겨 둔다. 테스트 출력 폴더는 ignored 증거이며 커밋 대상으로 간주하지 않는다.

### 재실행

저장소 루트 PowerShell에서 다음처럼 같은 15개 파일을 선택한다. 소스 편집을 멈춘 상태로 실행한다.

```powershell
$b5Targets = @(rg --files tests | Where-Object { $_ -match '^tests[\\/]test_b5_.*\.py$' } | Sort-Object)
$b5Args = @('-B', 'scripts/verify_data_usage_holds.py', '--strict-writes')
foreach ($b5Target in $b5Targets) { $b5Args += @('--target', $b5Target.Replace('\', '/')) }
$b5Args += @('--target', 'tests/test_b3_hotl_api.py', '--target', 'tests/test_b3_execution_context.py',
             '--target', 'tests/test_b3_release_readiness.py', '--target', 'tests/test_release_carries_tenant.py')
& venv/Scripts/python.exe @b5Args
```

프런트: `frontend`에서 `node scripts/check-studio-contracts.mjs`, `node scripts/check-studio-location.mjs`, `npm.cmd run build`. 설치 회귀는 `node scripts/check-process-installation.mjs`, 키트 시작 화면은 `node scripts/check-kit-getting-started.mjs`.
