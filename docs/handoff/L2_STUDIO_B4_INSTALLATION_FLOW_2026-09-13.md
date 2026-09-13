# B4 설치·탐색·재개·검토 승인 흐름

## 구조 편집과 제품 진입 연결 마감 — 2026-09-13 17:14 KST

작성 Codex. 사용자 승인으로 업무 추가·사용/미사용·상위 업무 이동·바로가기 추가/제거를 기존 표시 편집과 제안·타인 승인·GET 반영 흐름에 연결했다. **전체21/40=52.5%, 로컬18/28 유지.** 권고4·7·10/G2→G3의 업무 골격 사용자 변경 기능을 전진시켰으며, D02의 데이터/7앱 수용이나 B5~B7까지 완료한 것은 아니다.

### 사용자가 할 수 있는 기능

| 행동 | 처리와 보존 기준 |
|---|---|
| 상위/L1·하위/L2 업무 추가 | 업무 ID는 초안에서 고정, 정본 배치 ID는 서버 발급. 부모·중복·이름 검사 |
| 사용/미사용 | 삭제가 아닌 사용 상태 변경. ID·이력·앱/데이터 참조는 유지 |
| L2 상위 업무 이동 | 같은 원본과 canonical ID 유지, 대상의 같은 업무 바로가기는 먼저 제거 |
| 바로가기 추가/제거 | 원래 소속·업무를 복제하지 않음. 기존 바로가기만 REMOVE, 미제출 바로가기는 ADD 자체를 취소 |
| 표시 편집과 혼합 제안 | 표시 차이→구조 명령→후속 표시 차이 순서 보존. original base/version/digest는 별도 고정 |
| 검토·승인·반영 | 이동/사용 상태/바로가기 추가·제거를 요약하고, 실제 GET 기준판·제안판 트리에 바로가기까지 표시 |
| 실제 제품 진입 | 경영 홈·앱 운영의 `업무 구성 · L1/L2 수정` → 같은 CompanySetupPanel의 thread 탭. 중첩 대화상자 없이 전환, 닫으면 원래 화면/버튼 복귀 코드 |

새 노드/바로가기의 임시 placement ID는 전송하지 않는다. **새 배치가 포함된 형제 목록의 순서 이동은 승인 후 가능**하며 모델·UI가 함께 제한한다. 서버가 추가 배치를 발급하기 전 재정렬로 간주하지 않는다. 분리/통합·복잡한 상속·앱/데이터 참조 직접 편집은 이번 범위가 아니다.

### 입력·실패 보존

- workingBase는 로컬 표시 차이를 계산하는 용도이며 원래 승인 기준판을 바꾸지 않는다. 명령/기준/이유가 바뀌면 확인 체크가 무효화된다.
- 임시 바로가기 취소와 최신판 rebase는 복제본에 전체 명령 replay가 성공한 뒤에만 교체한다. 실패 시 이전 입력·명령·키를 유지한다.
- 해당 propose POST가 확정422로 거절됐을 때만 `수정 이어하기`를 제공한다. 선행 access/resolved GET 422·로컬 오류·unknown409/5xx로 미확정 키를 해제하지 않는다.
- 추가 양식도 flow의 순수 데이터에 보존하여 범위 왕복/재마운트로 지워지지 않는다. 아직 초안에 추가하지 않은 이름·설명이 있으면 POST0으로 막고 추가 또는 양식 비우기를 안내한다.
- 구조 명령을 누적하기 전에 미완성 표시 변경도 복제본에서 검증한다. 빈 이름/과도한 이름이 명령 앞부분에 고정되어 취소·최신판 비교를 막지 않으며 실패 시 입력을 그대로 둔다.
- 설정을 닫으면 경영 홈은 threadRevision, 앱 운영은 revision을 갱신하여 기존 GET 경로로 다시 조회한다. 이전 표시를 비우고, 선택 앱 ID는 새 목록에도 존재할 때만 유지한다. 이 연결의 STATIC 검사는 실제 브라우저 재조회 검증과 구별한다.

### 검증·한계

- 서버 `output/usage-holds-0sx0_95d/isolation.json`: 6파일177PASS/77.84초, wrapper83.7469초/0. 수집=실행177, 소스775·보호자산259 전후불변/현재소스불일치0, SQLite471 모두 own RUN/금지0. 새 구조 시험27개이며 서버 제품 코드는 이번에 변경하지 않았다.
- 프런트 최종 `output/process-installation-check-4ffd0920-fd14-4bc9-900f-34a7b963db6b/report.json`: **105PASS/375.6702ms = UNIT/React SSR 104 + STATIC 소스 진입·복귀 계약1**. 소스16 전후불변/현재불일치0. SHA7e07e82d30a540212432b1373138de9704febe7e88b82d2a39870ab0aeece9a7. 이전102개 실행은 과거 기록이며 최종판 증거로 승계하지 않는다. **STATIC은 실제 DOM·포커스·재조회 검사가 아니다.**
- 최종 제품 tsc+Vite, 구조 전용6파일eslint, 합성fixture build PASS. 제품의 기존 동적 import/큰chunk 경고 유지. 기존 대형 Enterprise/KitOps 전체lint PASS를 주장하지 않는다.
- 브라우저 실클릭 NOT_RUN: computer-use 지침을 읽고 cua.getState 1회 시도했지만 helper_unknown_error/setup refresh 오류로 Node kernel 종료. 별도 우회/도구 개발을 하지 않았고 SSR·HTTP를 실제 화면 수용으로 합치지 않는다.
- 미리보기: http://127.0.0.1:8768/tests/process-installation.fixture.html?version=structure-20260913-1714 . `편집 화면 바로 체험`→`추가 설정`. 기존 모의 서버만 유지하고 실제 API/DB/승인을 호출하지 않는다. 앞선17:00 HTTP200/앱 열기 queued와 최종 fixture 재빌드는 확인했으며 실제 클릭은 미검증이다.
- 독립 마감 검토: Hilbert 최종 재대조 완료, 지정 범위 미해결 P1/P2 없음. 추가 양식 유실·잘못된 표시 명령 고정·설정 종료 후 원래 화면 재조회 누락의 P2 3건을 수정하고 정적으로 종결했다. 작성자 Codex(모델/연결), Dewey(구조 입력), Hooke(기존 합성검사/fixture), James(실제 API 구조 시험); 실행은 Codex. 모든 보조 에이전트 종료.

### 다음

**B4 지정 기본 편집 코드·집중 검증 출구는 마감했다. 실제 브라우저/현업 수용 출구는 OPEN이다.** 다음은 **B5 단일 제작 화면 내용 연결**이다. 기존 AdaptiveProductionStudio/RunControls/viewModel·B3 계약을 재사용하여 업무·요청 입력, 현재 필요한 행동, 검토·재개·저장을 한 흐름으로 연결한다. 초기 예상 **120~180분(집중 검증 포함)**, 실제 브라우저 복구 대기는 별도다. 두 생성기의 전역 mount/URL/SSE 전환은 B6의 App.tsx 단일 담당 단계에서 한다.

운영DB/RAW·실권한·실승인·원격·사용자로그 및 main.py/App.tsx 보존. 사용자로그 SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510. 미커밋·미푸시이며 과거 full 결과를 최신 전체 PASS로 승계하지 않는다.

## 이름·설명·순서 편집 연결 — 2026-09-13 15:43 KST

작성 Codex. 기존 설치 흐름에 사용자가 승인된 업무를 선택해 수정하고 변경안을 제안하는 기능을 추가했다. **전체21/40=52.5%, 로컬18/28 유지.** B4 전체를 완료 선언하거나 내부 작업 수를 전체 점수에 더하지 않는다.

- 사용자 화면: 상위/하위 업무 선택, 이름·설명 수정, 형제 배치 위/아래 이동, 원본 대비 변경 미리보기, 이유·확인 후 제안, 기존 타인 승인/GET 반영 확인 연결. 이미 설치된 범위는 편집을 앞에 두고 추가 설치를 접는다. 접수 후 검토 영역으로 초점을 이동한다.
- 서버: 기존 RENAME에 SET_NOTE/REORDER_PLACEMENTS 추가. 순서 명령은 같은 부모의 숨김·미사용·바로가기를 포함한 정확한 전체 집합만 받는다. 승인판·process/placement ID·앱 참조를 보존하며 표시 변경이 의미 지문을 바꾸지 않는다.
- 복구: 제출 직전 현재 권한 재검사. 원래 base/version/digest·명령·이유·요청 키를 고정하며 응답 유실 시 동일 키로 명시 재시도한다. 확정 head/digest 충돌만 명시 최신판 비교로 진행하며 입력을 다시 검토해야 한다. 미확정 제출은 버리기/새 기준판 변경을 막는다.
- 문맥: 범위별 편집 상태 유지. 실제 편집은 새 경계로 자동 이동하지 않고, 아직 수정하지 않은 초기 상태만 새 경계/승인판으로 옮긴다. 권한 오류는 부모의 기존 조회 결과도 숨기고 늦은 응답 복원을 차단한다.
- 교차검토: Hilbert 독립 검토 P2 2건(부모 읽기 결과 잔존/미수정 초기 기준판 전환 차단)을 Codex가 수정. 재대조에서 두 건 정적 종결, 추가 확정 P1/P2 없음. 실행 검증과는 구분한다.
- 백엔드 검증 완료: usage-holds-cqim8wod, B1 configuration/adversarial+B4 display/change/review 5파일 **150PASS**, pytest80.19초/wrapper87.13초. 수집/실행150, 소스774·보호자산259 전후불변/현재소스불일치0, SQLite390 own RUN·금지0, wrapper0. 이전107/281 기록과 새 전체 PASS로 합산하지 않는다.
- 프런트 최종 검사 완료(15:47): 기존60+편집20=80PASS/281.9072ms. `output/process-installation-check-e9445430-01fa-40b8-aced-a2f561613fbc/report.json`, SHA673c0d358e951091306b5c4d40a50959ee36541975e8f0b430702fc177e74cc6. 소스12 전후불변/현재불일치0. 실제 제품 controller·adapter·React SSR 합성이며 실제 API/브라우저가 아니다. 제품 tsc+Vite, 지정5파일eslint, 합성fixture build PASS. 기존 동적 import/큰chunk 경고 유지.
- 미리보기: `http://127.0.0.1:8768/tests/process-installation.fixture.html?version=edit-20260913-1546` HTTP200. `편집 화면 바로 체험 · 합성 승인판` 버튼은 빈 모의 범위만 초기화하며 기존 접수·승인·초안은 덮지 않는다. 메모리 합성 자료이며 운영 승인 경로를 검증하는 버튼이 아니다. 기존 localhost8768 서버 유지, open_in_codex는queued.
- 증거: 서버 isolation.json SHAb9ded3d466f8c78e40161d3bfca2c656a193f2e39b16901fd8230f68660ffeca, SQLite390 모두 own RUN 재대조. 시험 추가 외 새 검증 인프라 없음. 이번 기능 지정 검사 완료이며 과거 full 결과를 최신 전체 PASS로 승계하지 않는다.
- 실제 브라우저: computer-use 지침에 따라 초기화했으나 trusted Node process exited unexpectedly. 이번 1회 확인 후 복구 도구 개발·우회 없이 NOT_RUN 유지. HTTP/SSR/합성 화면을 실제 클릭/현업 수용 PASS로 표시하지 않는다.
- 남은 기능: L2 추가·사용/미사용·부모 이동·바로가기 편집 UI, B4 진입 연결 점검, B5 쉬운 단일 제작/B6 단일 진입/B7 전환·수용. 다음은 B4 남은 기본 구조 편집으로, 기존 서버 명령을 연결하는 초기 예상60~90분(검증 포함)이다.
- 보호/범위: 운영DB/RAW·실제 승인/정책/원격 및 main.py/App.tsx 변경 없음. 사용자 로그 SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 유지. D03 잔여는 REAL RECONCILED 검사→기간/Owner 서명·정책 UI→일반 사용자 연결이며 이번 B4에 무단 혼합하지 않았다.

마감 확인 — 2026-09-13 15:08 KST: Codex 실행/Hilbert 독립 읽기 전용 대조 완료. B4 107개 수집·실행 정확 일치, 실패·skip·phase 중복0, wrapper0, 소스773·자산259 전후·현재 일치, SQLite306 ownRUN/금지0. 프런트60고유PASS·10현재지문 일치. 초기→최종 변경은 시험1파일이며 exact5는 초기 실패집합과 일치한다. 지정 코드 흐름 마감 가능 판정이며 실제 브라우저/현업·동일판281/full PASS는 아니다. 미리보기HTTP·빌드·lint는 main 실행 증거로 구분한다.

## 최신 연결·집중 검증 — 2026-09-13 15:05 KST

작성 Codex. 사용자 승인으로 14:41 착수 기록 이후 설치 요청을 담당자와 승인자가 이어 처리할 수 있도록 연결했다. **전체21/40=52.5%, 로컬18/28 유지. B4 전체와 실제 화면/현업 수용은 미완료다.** 아래 13:02 이전 기록은 첫 설치·탐색 slice의 이력이며 현재 판 전체회귀 PASS로 승계하지 않는다.

### 사용자가 끝낼 수 있도록 연결한 흐름

| 사용자 행동 | 이번 연결 | 확인 방법 |
|---|---|---|
| 담당자가 대기 요청을 찾고 진행 | 현재 요청별 resume/adopt, 명시 인수 확인, 검토 revision 고정 POST | 실제 API 설치→인수/재개→승인대기 및 프런트 중복/409/늦은 응답 검사 |
| 원작성자와 다른 승인자가 검토 | 범위별 변경 목록·상세, 고정 기준판/제안판·지문·작성자·서버검토자, 승인 이유와 확인 | 자기승인·권한회수·다른 경계·stale head·손상 부정 검사 |
| 승인 결과 확인 | 기존 원자 승인 재사용, operation/change/list/resolved GET, 승인응답과 적용확인 분리 | 실제 임시 저장소 APPLIED·profile/digest 일치, 후속 승인판 역사 기록 확인 |
| 오류 후 복구 | 결과 미확정 시 POST 잠금, 같은 대상 GET, 범위별 미확정 작업·변경안별 이유 메모리 보존 | 성공 후 조회503·409·응답유실·문맥왕복·unmount 검사 |

서버 contract: context.principal_user_id, operation.permitted_actions, `GET /process-changes`와 ID 상세. 상세는 payload/base_payload와 current_head_version/review_blockers를 제공한다. 쓰기는 기존 resume/approve API를 사용하고 검토한 base_head_version/draft_digest를 최신 값으로 자동 치환하지 않는다. 설치자와 승인자가 반드시 달라야 한다는 새 제한은 없으며, 승인자는 원작성자와 달라야 한다.

### 검증 기록 — 합산 또는 과장 금지

| 실행 | 결과 | 시간/범위 |
|---|---|---|
| 최초 관련 회귀 `usage-holds-15xmnk1v` | 281실행/276PASS5FAIL | pytest178.53초, wrapper187.05초. B1/B2/B3문맥+B4 선택 범위 |
| 실패 대상만 `usage-holds-v53wpcs5` | 5PASS | 3.34초, wrapper9.36초 |
| 최종 B4 `usage-holds-r0qqlsi1` | 107PASS/실패·skip0, wrapper0 | 48.26초, wrapper54.12초. 설치조회·변경조회·검토API3파일 |
| 프런트 `process-installation-check-426eb4ae-a505-428b-8690-14665427caa3/report.json` | 60PASS/10소스 전후·현재 일치 | 321.8211ms, SYNTHETIC_API_UNIT_AND_REACT_SSR |
| 정적/빌드 | 지정3파일eslint, 제품tsc+Vite, 합성fixture build PASS | 기존 dynamic import/큰chunk 경고 유지 |
| 실제 브라우저·현업 수용 | NOT_RUN | Cua 초기화helper_unknown_error, reset후trusted Node exit. 우회하거나 합성SSR로 대체하지 않음 |

5실패는 같은 설치 기록의 조회자별 새 permitted_actions를 옛 시험이 동일하다고 가정한 경우다. 원작성자[]/관리자[adopt]를 명시 검증하고 기존 단일목록·next_offset·다른경계 ID 비노출을 유지했으며, 단건 동일성·GET 무쓰기를 추가했다. 초기 실행 이후 Python 지문 차이는 tests/test_b4_installation_queries.py 한 파일의 이 보강뿐이다. 신규50사례 및 비B4 기존174사례는 최초 실행에서 통과했다. **최종 판281PASS나 등록 전체2194+α PASS로 합산하지 않는다.**

최종 backend 소스773·보호자산259 전후불변/현재소스불일치0, SQLite306회 모두 RUN, 금지DB/파일 접근0, 전역conftest미로딩. 최종 isolation SHA256 `1a631dee83c70bcb3e97741f22dba1209dba769303a77863893b18990c2b1d35`. 프런트 report SHA256 `d3e7fcf6371e166471ed238096483240a37d087607f417d41149010ef77133d1`.

### 보이는 중간 결과·소유·다음 작업

- 합성 리허설: `http://127.0.0.1:8768/tests/process-installation.fixture.html`. 실제 제품 컴포넌트+메모리 API, 3역할 선택/요청 기록 제공. HTTP200 및 connect-src none 확인, Codex 오른쪽 열기 요청 queued. 사용자 직접 미리보기용이며 agent 브라우저 검증 완료가 아니다. localhost 서버 session82416은 이 산출물 폴더만 제공한다.
- 소유: James backend4파일+새시험2파일, Hooke 기존 frontend검사/fixture2파일, Codex frontendAPI/Flow/Panel/CSS·기존시험1함수·실행/기록. Hilbert 5경계 통합 정적검토 새 확정P1/P2 없음; 최종 증거 대조는 후속 마감란에 남긴다.
- 다음: B4 업무 선택→이름·설명·순서 변경 제안→이번 승인 흐름으로 반영. 초기 예상60~90분+집중5~10분. B5 쉬운 단일 Studio/B6 진입 통합/B7 업데이트·전환 수용 별도.
- 보존: 사용자로그SHA7720cc45…f510, 기존dirty/main.py/App.tsx·운영DB/RAW·실역할/실승인/배포/원격 불변. 미커밋·미푸시. 테스트 실행과 로컬 합성 미리보기 외 실제 승인을 하지 않았다.

마감 확인 — 2026-09-13 13:02 KST: Codex 실행·보존 확인/Hilbert 독립 read-only 대조 완료. backend FULL_REGISTERED2194정확1회·6582phase·186subtest·old2110누락0/new84·771source/259asset현재일치·추가삭제0·격리PASS,프런트37사례/10지문별도PASS. **첫 흐름의 지정 코드 출구만 마감하며 실제브라우저NOT_RUN/B4전체OPEN/전체52.5% 유지.**

## 최종 코드 검증 — 2026-09-13 12:58 KST

- **첫 설치·탐색 연결의 지정 코드 회귀 PASS. B4 전체와 실제 브라우저/현업 수용은 미완료.** 전체21/40=52.5%·로컬18/28유지.
- `output/verification-axojhsot/summary.json`:full/jobs1/FULL_REGISTERED/parent0/2194사례정확1회,2187PASS7symlink환경skip/실패0/186subtestsPASS/2기존FastAPI on_event폐기예고. 전체1645.47초=27분25초,pytest1623.98초. 이전2110누락0·추가84(B457포함).
- worker `worker-1-fbaddeb4-5047-427b-a0d2-d300cc1592d4.json`, RUN `usage-holds-do4kw4og`:소스771·보호자산259전후현재일치/SQLite3051회모두RUN/금지DB·파일접근0/전역conftest미로딩. 실제7skip사유는 tests.xml의Windows symlink권한/파일시스템제약이다. 이 제외를PASS로세지않는다.
- 최신 프런트는 `output/process-installation-check-ecc761e8-54a3-464e-824b-34ccb4ef4476/report.json`:37PASS/10파일전후현재hash일치. 이후소스동결. 지정5파일lint·tsc·제품build·fixturebuild모두exit0,기존dynamicimport/큰chunk경고. 실제브라우저NOT_RUN(도구환경)·페이지reload/로그인통합/현업과제NOT_RUN은별도유지.
- Codex실행/최종보존확인, Hilbert독립read-only 코드P1/P2정적종결·프런트37사례/지문대조PASS. backend최종증거대조결과는마감확인기록에남긴다. 설계검토나SSR를실제사용성PASS로치환하지않는다.
- 무결성: full summary SHA256 `20566719cf647f19c379fa6439dfcc2e7dda4f1d168426573bfcf91a6e0d161d`,프런트report SHA256 `ef7b9f83ee943531c0222600c96e3d24153ce5259dca2a70189d79fd4d667bed`.
- 다음: 담당자재개/명시인수·타인변경안검토/승인 API+UI 연결70~110분,집중검증5~10분. 이후설명·정확배치순서명령. 브라우저도구복구시화면크기·키보드·실API여정검증필수. 로컬미커밋·미푸시,운영·원격·전역진입점불변.

## 최신 검증 — 2026-09-13 12:38 KST

- 실제 API/선택기 동일 연속범위 `usage-holds-r13oyl3d`:203실행/202PASS1환경skip/34.87초/wrapper0,SQLite177모두RUN/소스·자산불변/금지0. 최초 두실패는 가상 원본 계보와 선행 시험의 bound-method 복원 오염이었다. 제품 권한 코드·404 기대값은 불변이며 회수 hook/역할제거/fresh차단을 보강 확인했다.
- 전체 회귀 `verification-axojhsot`, main session92140, jobs1/12:27 시작/진행 중. 정확2194수집, 이전2110누락0·추가84(B4 57포함). 실행중Python core/API/tests/scripts를동결했다. 프런트 JS 검증은 별도다.
- 최종 프런트 `output/process-installation-check-9d6e085d-934f-4209-bf62-b4c820342a4f/report.json`:37PASS/10소스지문불변/실제브라우저NOT_RUN. 변경5파일lint/tsc 및 제품·fixture build 재통과. 기존chunk경고만 남았다.
- 독립검토 보강: 최초boundary를access와분리해보존하고 load/refresh/replan에서 변경을 차단한다. 명시새경계확인에도 미확정원입력·키를 fullboundary와함께보존, A→B→A복귀시원키복원/새계획차단. 과거 상세와현재제출ID분리, 같은세션selected/company왕복 모델보존. 모두 메모리수명범위이며 페이지reload/로그인 통합 및 실브라우저 성공을뜻하지않는다.
- 앞선 실패·33/36검사 이력은 아래 작성시점 기록이다. 전체full은아직PASS가아니며 제품점수52.5%유지.

작성자: Codex / 2026-09-13 KST. 승인된 상세설계 §11을 작은 사용자 흐름으로 연결한다.
권고4·7·10, G2-A/B/C→G3-B/C와 원료구매 첫 수직 폐루프의 업무 골격 선택에 해당한다.
전체21/40=52.5%, 로컬18/28 유지. B4 전체·B5/B6 단일 Studio·B7 수용 완료가 아니다.

## 구현 범위

- 회사 구성 → 업무 연결구성의 기본 본문에 `ProcessInstallationPanel` 연결. 이전 평면 편집은 접힌 별도 항목으로 보존하고 v2 읽기 전용 판을 덮어쓰지 않는다. App.tsx/main.py는 변경하지 않았다.
- 서버 `GET /process-configurations/context?company_wide=false`가 명시 선택 조직의 활성·유효 OPERATING_PARENT 경로로 root를 확인한다. 범위별 read/propose/edit/approve는 B1 판정으로 제공하며 role capability 목록을 UI 권한으로 대체하지 않는다.
- `GET /process-installations`는 정확한 경계의 목록과 제한 페이지를 반환한다. 단건 GET과 같은 원문·변경안·승인 증거 확인을 적용하며 조회가 설치·재개·승인을 실행하지 않는다. offset 방식이므로 동시 신규 접수 중에는 처음부터 새로고침해야 한다.
- 후보 조회 → 사용자 명시 등록 → 원래 Plan 입력·계획 미리보기 → 같은 입력+digest+요청 키로 start → 단건 GET·목록 새로고침을 연결했다. L1 선택으로 하위 L2 이름·설명을 확인한다. 기존 판은 원본 유지/ID 보존 이관을 명시 선택한다.
- 새 adapter는 구조화 오류의 HTTP 상태/사유/다음 행동을 보존한다. 문맥·사용자·세션 전환 및 unmount 뒤 이전 응답/후속 호출을 폐기한다. 409 입력 유지, 확정 충돌의 명시 재계획, 결과 유실의 동일 요청 키 재시도, 권한 회수 시 기존 표시 숨김을 구분한다.
- NO_DATA/DOMAIN_REVIEW_REQUIRED/setup_only는 골격 준비만 의미한다. 설치 요청·APPLIED를 데이터 인증이나 앱 사용 READY로 표시하지 않는다.

## 검증과 현재 한계

| 층 | 증거 | 판정 |
|---|---|---|
| 변경 프런트 5파일 lint/TypeScript | eslint 지정 파일, tsc -b | PASS |
| 제품 프런트 build | npm run build | PASS; 기존 동적 import/큰 chunk 경고 별도 |
| 단위·React SSR | node scripts/check-process-installation.mjs | 33 PASS; 모의 API, 실제 브라우저 아님 |
| 화면 fixture 빌드 | node scripts/build-process-installation-fixture.mjs | PASS; output/process-installation-browser |
| 최초 실제 API/선택기 격리 검사 | output/usage-holds-fkrgwuvi | 200 PASS/2 FAIL/1환경skip,32.77초. 실패 수정·재실행 필요 |
| 동일판 full/jobs1 | 안정 소스 동결 후 실행 | 아직 미실행 |
| 실제 브라우저 | Cua 초기화→reset→재초기화, sky 대체 초기화 | NOT_RUN; Windows sandbox helper/node 커널 오류로 입력 이전 실패 |
| 현업 수용 | 미참가 | NOT_RUN/B7 |

최초 격리 실행은203개 정확 수집·실행, SQLite177 모두 RUN, 보호자산·소스 불변, 금지 접근0이다.
실패는 가상회사 fixture의 원본 entity 누락과 조회 중 다른 연결 권한 회수의 재판정이다.
후속 결과를 이 문서 상단에 추가하되 이전 실패를 삭제하거나 부분 PASS와 합산하지 않는다.

## 독립 검토·소유

- Codex: 프런트 adapter/controller/Panel·CompanySetup 연결·실행·문서.
- James: core/API 두 쌍과 실제 B4 HTTP 부정시험. 기존 권한 정책 의미 완화 금지.
- Hooke: 프런트 계약시험33개·명시 SYNTHETIC/메모리 API fixture. fixture는 fetch/CSP로 실제 API 전송을 차단한다. 재접속 제어는 패널 remount이며 전체 문서 reload/제품 로그인 통합 검증이 아니다.
- Dewey: verification_plan의 B4 full/feature 포함과 누락 방지시험. quick 기본 선택·불명확 full fallback 유지, guard/runner 예외 없음.
- Hilbert: 독립 read-only 권한/오류/입력수명/최종 코드 검토. 실제 시험을 독립 실행한 것으로 표현하지 않는다.

## 다음 출구

1. 최초2실패 수정 및 동일 범위 재검증, 독립 P1/P2 종결.
2. B0~B3+B4 등록 시험의 동일 소스판 full/jobs1. 소스 writer 동결, 운영 DB/RAW 접근 금지.
3. 브라우저 도구 복구 후 1280×720/1440×900·좁은 화면, 키보드, scope전환/409/503/재접속 확인. 실제 제품 API와 브라우저를 함께 쓰는 여정도 별도 필요하다.
4. 다음 B4 slice: 설치 담당자의 최신 revision 재개/명시 인수, 별도 승인자 대기목록·상세/검토·승인, 기본 변경 제안 및 설명·배치순서 명령. B4 전체 기존 예상150~240분 중 후속범위다.

## 다음 slice 사전 대조 — 구현 아님

James read-only 사전 대조를 main이 채택했다. 구현 예상은 변경안 조회·서버 신원/행동 보강을 포함해 **70~110분**, 집중 검증5~10분으로 구체화한다. full·실제브라우저는별도다.

1. context에 서버 `Principal.user_id`를 제공하고 operation에 현재 작업별 resume/adopt 행동을 투영한다. 개발용 `getActingUser()`로 자기승인 여부를 판단하지 않는다. 원작성자(change.actor)와 인수담당자(installer)를 바꾸거나 혼동하지 않는다.
2. `GET /process-changes?context_root_id=…&scope_node_id=…&status=DRAFT&limit=20&offset=0` → `{items,next_offset}`. `GET /process-changes/{change_id}`도 명시root/scope를받아 boundary/payload/current_head_version/principal_user_id/permitted_actions/review_blockers를 반환한다. 범위별freshread·페이지제한·고정원문/지문·operation결속을검증하며GET무쓰기. 오래된DRAFT도읽되head충돌이면승인행동을제외한다. 기존 POST validate는이GET의대체가아니다.
3. 기존 `POST /process-installations/{id}/resume {expected_revision,adopt}`를 연결한다. 본인재개와 타인작업 명시인수를 구분,409/유실은먼저GET하며revision을자동갱신해POST반복하지않는다.
4. 별도검토자 목록→고정base_profile_id기준비교→기존approve `{expected_head_version:base_head_version,draft_digest,reason}`→operation/detail/list/resolved각각GET. 원작성자와서버검토자가다르고서버행동허용인경우만승인버튼. 승인접수후조회실패를재승인으로복구하지않는다.
5. 설명·순서는그다음별도slice. `SET_NOTE {process_id,note}`, `REORDER_PLACEMENTS {parent_process_id,placement_ids}`(같은부모전체ID,중복/누락금지), 부모이동은MOVE_NODE. ID/불변승인판/앱참조·semantic지문보존을검증한다.

신규예정시험은 test_b4_change_queries.py(타인발견/교차문맥/손상503/오래된초안/fresh회수/GET무쓰기), test_b4_review_api.py(명시인수/현재revision/실principal자가승인차단/타인검토승인/409입력보존), 이후 test_b4_display_commands.py(설명semantic보존/정확sibling순서/ID·이력보존)다. 기존B1자가승인부정시험/B2실제plan-adopt-approve/B4조회패턴과프런트37검사를재사용한다. 아직이파일들을작성하거나통과한것이아니다.

## 보존

브랜치 codex/l2-unified-studio-20260912, HEAD58e666833. 로컬 미커밋·미푸시.
사용자 interaction_log 기존10줄 SHA256 7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 유지.
기존 B0~B3 변경, 원본 Starter, 운영 DB/RAW/실역할/실승인·앱·배포 및 원격은 변경하지 않는다.
