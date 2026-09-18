# Claude Code 최신 변경 동기화·검토·다음 작업 준비

> 후속 2026-09-15 22:16 KST: 사용자 진행 승인 후 R1/R2와 선택 조직 캐시 결함을 수정했다.
> 현재 시작점·162PASS 증거는 [진입 수정 인계](L2_STUDIO_KIT_ENTRY_REPAIR_2026-09-15.md).
> 아래 내용은 수정 전 검토 이력이다.
> 후속 22:30 KST: R3 release도 수정. 최신 재개는 [릴리스 수정 인계](L2_STUDIO_RELEASE_REPAIR_2026-09-15.md).

작성: Codex · 2026-09-15 21:14 KST.
사용자 요청: 다른 Claude Code 세션의 최신 변경을 pull하여 동기화·분석하고 다음 작업을 준비.
범위: Git 동기화, 읽기 전용 코드 검토, 격리 검사, 다음 실행계획. 제품 수정·DB 복원·서버 기동·커밋·푸시는 수행하지 않았다.
로드맵 권고10 / G3 Factory·AppShell 실제 UI 계약. 첫 수직 폐루프의 진입·문맥 일관성에 직접 필요한 준비다.

## 1. 동기화 결과

- 브랜치: codex/l2-unified-studio-20260912.
- 원격: https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git
- 이전: b13b73687e981a85170d13018a74b0df1a51b033.
- 최신: 2380143ea9552bbfbe1cf59678f54a5fb53666b5.
- fetch 뒤 pull --ff-only 성공. 19커밋, 13파일, +2,414 / -16. merge/rebase/cherry-pick 없음.
- 동기화 직후 로컬 HEAD와 origin 추적 HEAD 일치. 다른 원격 브랜치를 현재 브랜치로 임의 통합하지 않았다.
- 인계서의 17커밋·HEAD802c4c815, PROGRESS의 18커밋은 집계 시점이 다르다. 이번 비교 범위는 위 두 전체 SHA로 고정한다.
- 사용자 data/interaction_log.jsonl은 pull 전후 보존했다. SHA256 7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510.
- 데이터 ZIP SHA256 9c60dccd210974fecc7a65f3945d2617371d416cb12a01153fa80d411977ab34 유지.
- 원격 변경에 데이터 ZIP 갱신은 없다. 다른 PC의 DB·로그인·실행 중 상태가 이번 pull로 동기화된 것은 아니다.

## 2. 실제로 전진한 것

| 대상 | 최신 구현 | 아직 완료가 아닌 부분 |
|---|---|---|
| project | URL 직접 진입→서버 확인→Studio 연결, 회사·사용자 전환 시 열린 프로젝트 재확인 | 전체 히스토리·실제 사용자 수용 완료 아님 |
| new | URL에서 새 만들기 흐름을 열고 자동 생성 POST는 하지 않음 | 전체 생성 여정 완료 아님 |
| release | 직접 링크 연결, 조회 실패·권한 거절 표시와 나갈 길 추가 | 정상 산출물 브라우저 미검증, 비동기 경쟁 결함 잔존 |
| kit_app | 목록 수준 metadata API, reader/flow/Gate, 기존 경로 계산 패널 진입 연결 | v2 가시성 검사 누락 검토 결과, 선택 releaseId 미소비 |
| mega / draft | 문법·설계 존재 | App 연결 및 전용 서버 관계/문맥 확인 미완료 |

주요 코드: frontend/src/App.tsx, frontend/src/store/useFactoryStore.ts,
api/routes/data_preparation_control.py, frontend/src/factory/studioKitAppEntry.ts,
frontend/src/factory/StudioKitAppEntryGate.tsx.

사용자가 결정한 「목록 수준」은 유지한다. 조회 확인에 준비도·계약 승인·실행 권한을 새로 요구하라는 검토가 아니다.

## 3. 이번 PC에서 직접 재검증

| 검사 | 결과 | 근거 |
|---|---|---|
| 서버 동일7파일 | 148PASS / 0FAIL, pytest79.98초 | output/usage-holds-g6bhdvbw/isolation.json |
| 격리 wrapper | PASS, 89.33초 | sources_unchanged·protected_assets_unchanged=true, 차단쓰기/SQLite경로0, repository conftest 미적재 |
| B5+배선 | 157PASS | output/studio-contracts-e08ca0d1-216c-47d6-a64b-c714947e3a1d/report.json |
| kit-app-entry | 14PASS | 전용 검사 명령 exit0 |
| project-entry | 26PASS | 전용 검사 명령 exit0 |
| studio-location | 25PASS | 전용 검사 명령 exit0 |
| process-installation | 105PASS | output/process-installation-check-54148873-10f5-417e-8073-4552f0b8c89b/report.json |
| 제품 build | PASS, 타입 검사 포함 | 기존 청크 크기/동적 import 경고 유지 |

프런트 합계327건. SSR·메모리 HTTP·정적 배선 검사이며 실제 브라우저는 이번 턴 NOT_RUN.
output 원기록은 Git 제외이므로 다른 PC에 있다고 가정하지 않는다.
원격 인계의 서버229초와 이번80초는 서로 다른 환경의 관측값이며 제품 성능 개선의 증거가 아니다.

## 4. 발견 사항 — 다음 구현 전 우선 처리

### R1 / P1: v2 kit_app 진입이 기존 목록의 추가 가시성 검사를 누락

- 신규 entry-metadata: api/routes/data_preparation_control.py:1169에서 연결 존재만 검사하고,
  연결이 있으면 legacy require_caps도 건너뛴 뒤 앱 metadata를 반환한다.
- 기존 목록: 같은 파일:1218 → _review_apps_v2(:1088) →
  _kit_review_context 및 core/kit_app_contract.py:496의 _visible_v2_instance.
- 기존 검사는 명시 선택 조직, 회사 루트, 선택 조직이 대상의 조상인지,
  fresh 조직 권한 및 PROCESS_CONFIG_READ까지 확인한다
  (core/enterprise_context/process_configuration.py:91).
- 신규 반환 직전:1182는 _instance_or_404만 반복한다.
  이 함수는 readable_scope_nodes 포함 여부를 보지만 v2 선택 조직의 조상 관계는 검사하지 않는다.
- 따라서 두 형제 조직을 읽을 수 있는 주체가 B를 선택한 채 A의 v2 인스턴스를 요청하는 등,
  목록이 거절하는 문맥을 신규 진입만 통과시킬 수 있다.
- 증거 수준: Confucius 독립 정적 검토 + Codex 호출 경로 대조. 해당 부정 HTTP 시나리오는 이번에 새로 실행하지 않았다.
- 기존17건은 설치된 v2의 주로 정상 방향을 검사하므로 148PASS가 이 누락의 반증은 아니다.
- 다음: 다른 선택 조직·권한 회수·현재 READ 부재를 먼저 격리 HTTP로 재현한 뒤,
  기존 v2 가시성 검사만 재사용한다. 준비도 계산이나 승인 계약 전체를 진입에 붙이지 않는다.

### R2 / P2: legacy 권한 부족의 은닉 응답이 일치하지 않음

- 신규 API:1172의 require_caps는403을 반환하고 은닉 변환이 없다(api/deps.py:100).
- 읽을 수 있는 조직이지만 PROJECT_RUN이 없는 주체에게 기존 인스턴스는403,
  없는 인스턴스는404가 되어 신규 API의 「없는 것과 못 보는 것 같은404」약속과 어긋난다.
- 기존 legacy 목록도 같은 경향이 있다. 기존 목록 전체의 새 회귀라고 주장하지 않는다.
  프런트 문구를 같게 만드는 것만으로 HTTP 응답 차이가 사라지지는 않는다.
- 증거 수준: 정적 대조. legacy allow/deny/absent 검사를 다음 묶음에 포함한다.

### R3 / P2: 릴리스의 늦은 응답이 닫기·최신 선택을 덮음

- frontend/src/store/useFactoryStore.ts:591~617.
- 실제 제품 AST의 viewRelease/closeRelease 함수 본문을 그대로 추출·트랜스파일하고
  set/fetch만 메모리 대역으로 주입했다. 파일 수정·실서버 호출 없이 다음을 재현했다.

| 조작 | 기대 | 실제 |
|---|---|---|
| A 조회 대기→closeRelease→A 응답 | 닫힌 상태(null) | A가 다시 viewingRelease에 설정됨 |
| A 조회→B 조회→B 응답→A 응답 | B 유지 | A로 덮임 |
| 기존 OLD 표시→NEW 조회 대기 | OLD 숨김·로딩 | OLD가 남고 releaseLoad만 loading |

- generation/abort/identity 검사 없이 매 응답이 set한다. 회사·사용자 전환에도 동일한 상태 수명 검토가 필요하다.
- 이 비동기 약점은 종전 viewRelease에도 있었다. 이번 직접 링크 확장에서 아직 해소되지 않은 잔여이며
  모두 Claude의 새 코드가 처음 만든 결함이라고 표현하지 않는다.
- 이번157건의 추가4건은 소스 배선 검사라 위 시간순 동작을 검증하지 않는다.
- 다음: release 전용 요청 세대·닫기 무효화·회사/사용자 변경 무효화·이전 표시 제거 및 응답 대상 일치 검증.

### R4 / 준비 문서: 기동 명령에서 검증 포트 설정 누락

- CLAUDE_TO_CODEX_2026-09-15.md §9.1은 run.py 실행에 --port8090이 없고
  프런트 VITE_API_BASE_URL도 없다. 기본 환경에서는8080으로 연결돼 다른 세션과 섞일 수 있다.
- L2_STUDIO_BROWSER_BASELINE_2026-09-15.md §8은 해당 설정을 포함한다.
- 다음 기동은 가용 포트 확인 후 같은 checkout의 백엔드 --port8090,
  프런트 VITE_API_BASE_URL=http://127.0.0.1:8090 + --port5183을 명시한다.
  이번 턴에는 서버를 시작하거나 다른 세션 서버를 종료하지 않았다.

## 5. 진척도와 Gate 판정

- 기존 제품 정본: 전체21/40=52.5%, 로컬18/28≈64.3% 유지.
- 4/6 진입 경로가 연결된 것은 기능 연결의 부분 진척이지 제품 전체66.7%라는 뜻이 아니다.
- 통합 Gate4: Claude가 별도 환경 HTTP6항목 충족을 기록했다. 이번 PC에서 재실행/재승격하지 않았다.
- 통합 Gate5: 미충족. 인계에 12px 미만79건과 경영 질문 「부분」가 함께 기록되어 있으므로
  「글씨만 고치면 모든 브라우저 검증이 끝난다」고 해석하지 않는다.
- release 정상 화면, 전체 B6 전환/히스토리, 실제 LLM 응답·현업 수용의 미검증을 따로 남긴다.
- 이번은 동기화·검토·준비이므로 G3 관문 완료 칸을 추가하지 않는다.

## 6. 다음 작업 순서 — 구현은 다음 요청에서

| 순서 | 범위 | 예상 | 완료 기준 |
|---|---|---|---|
| 1 | R1/R2 kit_app 가시성·은닉 재현 및 최소 보정 | 첫20~30분 | 부정 HTTP 재현, 기존 목록과 동일 가시성, legacy allow/deny, 기존17건 회귀. 미완이면 정확한 잔여 보고 |
| 2 | R3 release 요청 수명 보정 | 20~30분 | 닫기·역순응답·회사/사용자 전환·로딩 중 이전 값 테스트 통과 |
| 3 | mega 부모/자식 확인 | 30~50분 | 기존 project 확인 경로 확장, 서버에서 관계와 각 대상 가시성 확인, 하나의 확인 응답 |
| 4 | draft 진입 | 40~60분 | 선택 문맥 기반 전용 metadata, 종류·판본·소유 검증, 합성 격리 초안으로 정상/거절 재현 |
| 5 | 단일 진입·히스토리·UI 수용 | 30~45분 | 실제 브라우저로 재조회/뒤로/앞으로/문맥 전환·미지원 링크·중복 mount 점검 |

추정은 준비된 환경 기준이며 사용자 로그인/실데이터 준비 대기는 별도다.20~30분마다 산출물·검증·전체 진척·다음 ETA를 보고한다.
각 작은 수정은 직접 관련 검사만 먼저 실행하고 안정된 합류 지점에148건+프런트327건+build를 실행한다.
전체 저장소 장시간 회귀를 매번 반복하지 않는다.

### Claude가 남긴5가지 결정에 대한 검토 권고

1. mega: 기존 project metadata를 호환 확장하고 서버가 부모-자식 관계를 검증한다.
   프런트의 두 응답으로 관계를 추측하지 않는다. 실제 변경 전에 응답 계약을 짧게 확정한다.
2. kit_app releaseId: 조용히 버리는 현재 상태를 완료로 보지 않는다.
   현재 목록 수준 진입을 유지하면서 명시 판본 링크는 결속을 검증하거나 지원 전임을 표시하는 선택지를 구분한다.
3. draft: 서버가 현재 문맥을 판정하는 전용 진입 API 권고. 운영 초안0행은 구현 불가 사유가 아니며 합성 사본으로 검사한다.
4. 공통화: 먼저 R1~R3의 동작을 잠근다. 전체 reader/오류코드 통일을 선행 대형 작업으로 만들지 않는다.
   mega/draft 추가 시 확인된 flow 공통부분만 추출하고 기존 대상별 시험·오류코드는 보존한다.
5. 담당: 다음 구현자 한 명이 App.tsx를 맡는다. 서버/프런트 계약을 먼저 맞추고 권한 변경은 별도 교차검토한다.
   이번 리뷰 종료 후 동시에 App을 수정하는 작업자는 없다.

## 7. 다음 세션 재개 요약

2380143ea까지 동기화 완료. 이번 검토 문서부터 읽고 Claude의09-15 인계·설계와 대조한다.
다음 첫20~30분은 공통 헬퍼나 글꼴 전면개편이 아니라 R1/R2 kit_app 가시성의 부정 HTTP 재현·최소 수정이다.
사용자의 목록 수준 결정을 바꾸지 않는다. 그 다음 R3 release 시간순 결함을 처리한다.
운영 DB/로그/키를 건드리지 말고 source/asset 불변 격리 검사를 사용한다.
이 보고서 작성 시 제품 변경·새 커밋·push는 없다.
