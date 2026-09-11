# 결정 생성 근거 계약 복구 — 2026-09-11

- 작성자: Codex / 검증 기준 2026-09-11 16:44 KST
- 범위: 로드맵 항목 13·G5의 기존 결정 생성 경로. 전역 라우트·내비게이션·운영 권한·인증 정책은 변경하지 않았다.
- 결과: **전체 21/40 = 52.5%, 로컬 18/28 = 64%**. 16:16 재산정의 D07 연결 단계만 2/4→3/4로 복구했다. 나머지 9영역은 승계했으며 전수 재감사로 표현하지 않는다.
- 집계: 완료 21 · 진행/부분 7 · 검증 미완료 6 · 미착수/대기 6. 10영역 모두 실사용 완료를 뜻하지 않는다.
- 정본: [기계 검산용 40칸·해시](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/DECISION_CREATION_CONTRACT_REPAIR_2026-09-11.json). 직전 [16:16 재산정](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/PRODUCT_PROGRESS_REASSESSMENT_2026-09-11.json)은 수정하지 않았다.

## 실제 변경

1. DecisionCenter에 근거 종류 4종을 필수 선택으로 추가했다. 빈 값에서 시작하며 실행 선택만으로 종류를 추정하지 않는다. 종류가 없으면 제출 버튼과 제출 처리에서 모두 차단한다.
2. 공용 요청 타입에 evidence_basis를 필수로 넣고 실제 API 요청에 전달한다. 상세 화면에도 저장된 종류를 표시한다. 이전 미기재 기록을 전문가 판단으로 바꾸지 않는다.
3. 서버가 실행을 다시 읽어 결속하는 기존 경계를 유지하면서, 도메인 검증기가 읽는 baseline_id·scenario_id·engine_version도 같은 서버 스냅샷에서 파생한다. simulation_binding과 세 정본 키의 사용자 덮어쓰기는 422다.
4. 계산 버전·입력 지문이 없는 실행은 목록에서 사용 불가로 표시하고 생성 재검사에서도 409로 차단한다. 범위 밖 실행은 존재하지 않는 실행과 동일한 404다.

## 검증 결과

| 검증 | 결과 | 범위 |
|---|---|---|
| 실제 작성 화면 | 1440×900·390×844 통과 | 네 근거 종류 8회 제출, 미선택 차단, 기존 미기재 표시, 가로 넘침 없음 |
| 캡처 요청→실제 API | 8/8 저장 확인 | 실제 CreateScreen→decisionApi→closedLoopFetch의 직렬화 결과를 FastAPI 라우터에 그대로 재대입 |
| 집중 회귀검사 | **115 passed, 실패 0, SKIP 0** | 기존 결정·원천·발간 회귀 + 새 계약/범위/변조 차단 및 캡처 재대입 |
| 결정→발간 연결 | 통과 | 생성→동일 문서 3관점→검토→결정→실행과제→효과→발간 원천 지문·승인 |
| 발간 실패/성공 | 통과 | 실제 HTTP 경로의 어댑터 미연결은 FAILED, 합성 어댑터에서만 PUBLISHED |
| 원장·DB 격리 | 통과 | 실제 임시 원장 이벤트 확인, SQLite 경로 151개 모두 새 격리 폴더 내부, 운영 DB 연결 0 |
| 타입 검사·제품 빌드 | 통과 | tsc -b, Vite 3503모듈. 큰 청크와 정적/동적 import 중복 경고는 남음 |
| 패치 검사 | 통과 | 제품 4파일 git diff --check |

- 최종 회귀: [JUnit](C:/WorkSpace/gemini_agent_team_verG/output/decision-create-g1kphf05/tests.xml), [격리 증명](C:/WorkSpace/gemini_agent_team_verG/output/decision-create-g1kphf05/isolation.json).
- 브라우저: [요청 8건](C:/WorkSpace/gemini_agent_team_verG/output/decision-ui-r5soclz6/browser-report.json), [데스크톱](C:/WorkSpace/gemini_agent_team_verG/output/decision-ui-r5soclz6/basis-1440.png), [모바일](C:/WorkSpace/gemini_agent_team_verG/output/decision-ui-r5soclz6/basis-390.png).
- 타입 검사 및 빌드는 Codex 실행 출력에서 확인했다. 제품 빌드는 output/decision-create-product-build에만 출력했고 배포하지 않았다.
- 앞선 74건 검사 및 시험용 CSS 경로/셸 범위 수정 전 실패 산출물도 보존했다. 완료 근거는 위 최종 실행만 사용한다.

## 검증 한계와 안전 경계

- 제품 브라우저 제어 도구는 Windows sandbox setup 오류로 두 번 종료됐다. 저장소에 이미 설치된 Playwright와 별도 headless Chrome 프로필로 합성 fixture를 시험했다. 사용자 브라우저·계정은 열지 않았다.
- 브라우저 응답은 메모리 합성이며 실제 요청 본문을 별도 FastAPI TestClient에 재대입한 **경계별 연결 검증**이다. 로그인된 실제 앱→실서버의 연속 E2E로 주장하지 않는다.
- API의 인증 주체는 합성 Principal로 대체하고 실제 범위 필터·도메인·원천 저장소·임시 원장을 사용했다. 실제 SSO·운영 인증 경로는 이번 검증 밖이다.
- 발간 HTTP 경로에는 실제 외부 게시 어댑터가 연결되지 않는다. 이번에도 미연결 실패를 확인했다. 합성 어댑터의 성공은 외부 전송 실적이 아니다.
- pytest 전역 conftest와 자동 플러그인을 끄고 제품 모듈 import 전에 DATA_DIR을 격리했다. SQLite audit hook은 격리 폴더 밖 연결을 거절한다. 운영 DB·RAW·실적 인증 상태는 변경하지 않았다.
- 전체 T3/Gate5·6 완료나 운영 승인으로 간주하지 않는다. 기존 전체 회귀 미통과·원장 과거 오염 조사도 별개로 남는다.
- 시험용 18764 정적 서버는 검증 후 종료했다. 커밋·푸시·병합·배포는 하지 않았다.

## 재현

1. frontend에서 node scripts/build-decision-create-fixture.mjs 실행.
2. 저장소 루트에서 venv/Scripts/python.exe -m http.server 18764 --bind 127.0.0.1 --directory output/decision-create-browser 실행.
3. 다른 터미널에서 venv/Scripts/python.exe scripts/verify_decision_create_browser.py 실행. 출력된 새 browser-report.json 경로를 사용한다.
4. venv/Scripts/python.exe scripts/verify_decision_creation_isolated.py --browser-report output/<새 decision-ui 폴더>/browser-report.json 실행.
5. 시험 서버를 종료한다. 매 회귀 실행은 새 decision-create 임시 폴더를 만들며 이전 증거를 지우지 않는다.

## 다음 작업

- 다음 로컬 구현 묶음: 초기 데이터 준비 FND-01/03·MDM-04/08·EXT-02를 기존 판/원문 보존 조건으로 정렬하고 같은 40단계 기준으로 종료 증거를 쌓는다.
- D07 실사용은 실제 사용자·실자료·반복 업무 수용 검증이 필요하다. 외부 게시 어댑터 연결·전송과 운영 권한 변경은 별도 범위·승인 사항이다.
