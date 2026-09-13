# B5 공통 제작 내용 — 핵심 구현·집중 검증 인계

## 추가: 일반 재개·오류 복구 명령 묶음 마감 — 2026-09-13 23:03 KST

Codex / 권고10 / G3-B·C. 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 22:08착수, 이번 묶음 구현·집중검증 완료이며 B5전체/B6/B7 완료는 아니다. 아래 과거 절의 해당 항목보다 이 절이 최신이다.

### 구현 계약

- POST `/api/v1/factory/{pid}/execution-commands`: UUID client_request_id, operation START/RESUME/RESUME_QUOTA/PAUSE/STOP/HEAL, task_id, 닫힌 input. START는 initial_idea/master_data/feedback, HEAL은 error_log, 나머지는 빈 input. 사용자·회사·승인문맥·스키마·전체state는 받지 않는다. 최대64KiB. GET 같은경로/{UUID}와 목록은 현재권한·개인·문맥을 재확인한다.
- CommandStore는 주입된 AdvisorStore의 전용 테이블. PROCESSING 선기록→실제처리→ACCEPTED/REJECTED/UNKNOWN 종결 CAS, command/receipt/record 지문검증, 동일key/body 재실행 금지. 프로젝트 PROCESSING/UNKNOWN은 다른key 신규실행을 막고 PAUSE/STOP 긴급요청만 예외다. HEAL은 서버 프로젝트당3회이며 HOTL대기 반환도 차감한다. 한도초기화/서버내부UNKNOWN 자동종결은 구현하지 않았다. 목록은 최신50개이며 별도원키 GET을 제공한다.
- 가시성→배타예약→전체PDP→기록→기존실행→종결→공개권한 재확인. HTTP취소도 shield worker 종료까지 예약 유지. 정확히 같은 asyncio task만 중첩 실행 소유권을 갖고 상속 자식task는 우회불가. 구START/QUOTA도 준비쓰기 전 예약·영속UNKNOWN 확인, 구HEAL 원키없는 직접호출409. 실행뒤 공개권한 변경은503으로 돌려 미접수4xx로 오해하지 않게 했다.
- pause는 실제worker 종료를 기다리고 객체별 callback으로 같은ID의 후속task를 지우지 않는다. checkpoint ID/상태지문/next/모드/템플릿/설정을 `.studio_pause_state.json`에 원자저장한다. 읽기는 파일생성없음, 새기획 아카이브에서도 증거 제외. 종료 확인과 재개 가능성은 별개다.
- resume_existing은 같은thread에 astream(None). 저장된 수동정지 증거 또는 현재노드의 실제오류, 현재checkpoint·프로젝트·템플릿 일치를 검증한다. 새기획/아카이빙/새task/WBS재분할/종결판정 초기화 없음. HOTL·동적interrupt·계약검토·쿼터·종결은 전용경로로 유지. state/latest는 실제running과 pause 투영을 반환하며 UI에 ‘멈춘 작업 이어하기’/‘일시정지’를 표시한다.
- HEAL은 기존check_hotl의 서버현재task/WBS실행중task와 요청원task를 확인한다. UNKNOWN보류, 다른현재task HOTL도 우선 반환. 새task는 TASK_REV_HEAL_{UUIDhex}, source_task_id/명령지문 보존. 엄격WBS/FileLock/CAS/fsync/원자replace/동일키멱등, 손상·누락원본 보존. task추가뒤 실행실패는UNKNOWN이며 task를 몰래 재생성/삭제하지 않는다.
- 프런트 실제SHA256/원명령·결과작업·상태검증, POST뒤 같은키GET. CONFIRMED는 명령접수 확인이지 가동·완료가 아니다. 검증한 개별record만공개, 원키목록/미확정잠금은숨긴본문과별도보존, 늦은사용자·문맥·응답무시. 원실패근거·입력 자동삭제없음. 원키없는 구명령UNKNOWN은 다른task캐시로 풀지 않는다.

### 검증·검토·보호

- 최종 서버 `output/usage-holds-4w0j3fcs/isolation.json`: **260PASS/163.16초**, wrapper179.0485168초/0. B5 execution_resume/commands_api/command_store/healing_task, B3 execution_guard/hotl_api, B5 revision_requests, route_authority 등록·누락 두정합검사. source790/asset259 전후·현재일치, SQLite535 ownRUN/금지파일·SQLite0. 실제HTTP/PDP/격리SQLite/WBS와 명시적 그래프대역을 구분한다.
- 최종 프런트 `output/studio-contracts-4b7a3635-658e-4bae-b645-a38ecfaa32b2/report.json`: **127PASS/1005.8953ms**, source31 전후·현재일치. 이전105+실행22(UNIT/API대역/SSR21, STATIC1), 전체STATIC4. 멈춘일반task CTA 활성/재개불가 비활성 SSR 포함. 최종제품build(tsc+Vite)/fixturebuild PASS, 5eslint 오류0·cleanup generation ref 경고1. 기존chunk/dynamic import 경고 유지.
- Hilbert 독립P2두건(쿼터모드쓰기후조회실패False오판, HEAL다른현재task HOTL누락)을 main이503UNKNOWN/서버후보우선조회+회귀추가로 수정. 지적범위 정적재대조 종결. 시험은 main실행이며 독립실행·전체보안·실그래프·브라우저수용 인증이 아니다.
- 실패/비최종기록 보존: usage-holds-7ha7sxv9 89PASS이나source동시변경/wrapper1; dt4v3x75 71PASS35ERROR(모듈초기화전 테스트DB차단 순서수정); oxb4y60u 259PASS1FAIL(테스트UTF8누락)4ERROR(격리runner에없는fixture의테스트선택). 이후 qx0i4cnf24PASS, 11gt37te258PASS, P2추가후최종260PASS. studio-contracts-56e149f0-cd25-4e55-9a8c-ab1d52947844 126PASS1FAIL은 다른현재task HOTL허용 계약변경을 반영해127재통과. 실패를최종PASS로치환하지않는다.
- 사용자로그 SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`, main.py/App.tsx diff0. 운영DB/RAW/실역할/실승인/원격·기존dirty 보존. 미커밋·미푸시. source/asset/front 현재지문 불일치0.

### 체험·한계·다음

- `http://127.0.0.1:8768/tests/studio-transition.fixture.html?scene=execution&version=b5-execution-20260913-2303`, scene=paused는멈춘기획. 실제StudioContent+합성메모리API/응답유실→원키GET, bundle studio-transition.fixture-DhdxieL1.js. CSP connect-src none/no realfetch fallback/HTTP200, 앱열기queued. 이번 턴 새 컴퓨터사용 시도없음/실제클릭·포커스·브라우저수용 NOT_RUN.
- 단일서버프로세스 예약·SQLite 종결CAS·한WBS파일 원자교체까지만 보장한다. DB/FS/체크포인터 분산원자성이나 실제LLM/Host 실행은 입증하지 않았다. 서버PROCESSING/UNKNOWN 잔류는 자동재실행하지 않고 운영검토가 필요하다.
- 다음 **일반HOTL 초안 사용완료 결속과 B5 잔여판정45~75분**, 이후B6유형별 단일진입·URL/SSE/B7현업수용. 구release/replan 영수증없는UNKNOWN·상세접근성/실브라우저는별도. B6전역파일은이번에수정하지않았다.

## 추가: 수정 요청 접수·복구·초안 소비 마감 — 2026-09-13 22:04 KST

Codex / 권고10 / G3-B·C. 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 아래 수정 요청의 지정 기능 묶음 완료이며 B5 전체/B6/B7 완료가 아니다.

### 구현 계약

- POST `/api/v1/factory/{pid}/sprint/revision-requests`: `client_request_id` UUID, full `target`(REVISION_REQUEST/원task/artifact_SHA), trim된 `feedback`, `input_draft:{draft_id,revision,digest}`. GET 동일 경로 `/{client_request_id}`는 현재 사용자·문맥의 고정 영수증을 조회한다. 성공은 `request_id,submission_id,project_id,actor_id,target,feedback,input_draft,task_id,status:ACCEPTED,execution_started:false,created_at,receipt_digest`를 반환한다.
- `core/studio_revision_requests.py`가 엄격 WBS 판독·기록/본문/원task 지문 검증·개인/문맥 은폐를 수행한다. `WBSManager.accept_revision_request`는 기존 파일 잠금→엄격 판독→동일키/동일초안 중복 확인→임시파일 fsync→최종권한/초안/산출물/파일CAS→원자 replace. 손상 WBS를 빈 목록으로 복구하지 않는다. 일반 WBS 상태 변화는 허용하지만 접수 당시 고정 task 필드가 바뀌면 원증거 확인에 실패한다.
- 예약은 AdvisorStore 진입 전부터 전체 요청을 덮는다. 그보다 먼저 fresh 조직 scope+프로젝트 가시성을 확인해 비가시 대상의 BUSY 존재 노출을 막는다. 기존 영수증 replay는 새 산출물/소비된 초안/실행 상태 검사보다 먼저이며 원키·원본문은 같아야 한다. 새 접수는 작업 실행 중 금지. 취소 shield가 실제 worker 종료까지 예약을 유지한다. 구 `/sprint/revision`은409이며 새 화면은 호출하지 않는다.
- `studio_input_draft_control`의 REVISION_REQUEST consume_supported=true. 소비는 같은 소유자/문맥/원target/본문/저장ref와 실제 접수증을 대조한 명시적 CAS다. 접수 자체로 소비하거나 작업을 시작하지 않는다.
- 프런트 새 API/flow, RevisionRequestEditor/RunControls/StudioInputDraftControls: 현재대상·저장초안 재조회 후POST→동일영수증GET; UNKNOWN/RECORDED는원키GET만. Target조회실패시과거기록본문숨김→별도recoverGET검증한행만공개. 다건은실패한A도다음B진입을막지않고순회하며A원본문/키/UNKNOWN유지. 새제출권한승격없음. 원초안소비증명은submission별보존, 같은기준새의견은원초안소비후명시시작.

### 검증 증거와 범위

- 최종 서버 `output/usage-holds-746l2d44/isolation.json`: 213수집/실행/PASS,127.33초,wrapper144.8575초/0. B5 revision_requests/input_drafts, B3 execution_guard, WBS artifact_kind, 권한표2개,격리guard49개만선택. 실제FastAPI/PDP/저장소/WBS를가벼운격리fixture로검증하며 LLM·Host·운영데이터실행은아니다. 서버782소스·259보호자산 전후 및22:03현재불일치0, SQLite303모두ownRUN/금지0/conftest미적재.
- 프런트 `output/studio-contracts-72241109-d165-42f4-8c8e-593649454e73/report.json`:105PASS/785.3151ms,27소스현재일치. 기존81+수정24(실제API/flow의대역HTTP·UNIT/SSR23, STATIC1); 전체STATIC3와브라우저미실행을분리. 최종제품build·fixturebuild PASS,지정6eslint오류0/generation ref cleanup경고1. 기존큰chunk/dynamic import경고도남는다.
- 최초 `usage-holds-005xoewm`:160PASS/2FAIL/145.55초. 취소중경쟁POST가AdvisorStore락에서대기하던순서결함과, FileLock의 `\\?\C:` 표기를ownRUN밖으로오인한격리실패. 운영외부쓰기아님/실패증거보존. 전자는예약시점+가시성선검사로보완,후자는현재RUN정규확장drive만정규화. UNC/device/ADS/예약명/상위경로/링크변환/protected거절유지, 링크경계회귀는resolve대역이지실제Windowsjunction생성시험이아니다. guard49PASS/0.67초 `usage-holds-e429ikqr` 후최종213재검증.
- Hilbert 독립읽기전용으로 API가시성/예약·단일/다건실패복구·guard변경 정적종결,추가확정P1/P2없음. 실행은main이며독립실행으로표현하지않는다.
- 합성체험 `http://127.0.0.1:8768/tests/studio-transition.fixture.html?scene=revision&version=b5-revision-20260913-2204`: 화면7번,초안저장→접수→소비 및응답유실체험. 최신JS `studio-transition.fixture-DM-c3EJJ.js`;CSPconnect-src none/운영fallback없음. HTTP200/빌드확인,앱표시요청queued. Computer Use초기화2회실패(kernel21364,helper_unknown_error)로실제클릭 NOT_RUN. 화면수용이나운영접수PASS로세지않는다.

### 다음 출구·보호

일반명령 접수확인/UNKNOWN·같은PLANNING비파괴재개·일반HOTL제출초안소비가남는다. 기존heal은예약검사전에WBS task/구성쓰기를수행해경쟁시실행만409가될수있다(기존일반명령P2). 새접수의동일WBS잠금원자성파손으로확정된것은아니며예약중모든프로젝트쓰기가막힌다고주장하지않는다. 다음일반재개·오류복구묶음60~90분초기예상,이후B6 App단일담당진입/B7수용.

main.py/App.tsx diff0·사용자로그SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510 유지. 운영DB/RAW/실역할·실승인/원격/기존dirty보존. 미커밋·미푸시. 소스동결및기존미리보기서버유지.

## 추가: 키트 v2 계약 검토 연결·집중 검증 마감 — 2026-09-13 20:44 KST

Codex / 권고10 / G3-B·C. 현재 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 지정 검토 기능 구현·집중 회귀를 마감했다. B5 전체·B6 단일 진입·실제 브라우저/현업 수용은 완료가 아니다.

### 사용자 기능과 근거

- 검토자도 현재 READ 가능한 v2 적용본→앱 목록에 진입한다. 기존v1 PROJECT_RUN 권한과 인스턴스 상세의 데이터 접근은 넓히지 않았다. 검토 전용 사용자의 runtime 상태/개수는 null이다.
- `GET .../instances/{instance}/apps/{app}/contract/v2?revision=N`은 저장 원문·행·지문·고정 업무판·승인/반려 사건을 검증한다. 현재 principal, 최신개정, blockers, permitted_actions와 검증된 decision_event를 반환한다. 반려판은 원문 DRAFT, 대체판은 원문 APPROVED를 그대로 보존한다.
- KitAppPanel에서 원문/판본/작성자/사용자/제한→사유·확인→기존 승인·반려 POST→원장 사건 재조회까지 연결했다. 생성권이 없는 적격 검토자도 가능하지만 자기검토·새판·다른문맥·권한회수는 재검증한다. 데이터보류 시 READ/반려와 승인/실행을 분리한다.
- 결과가 불명인 요청은 원래 판본·지문·사유·사용자를 메모리에 보존하고 GET만 제공한다. 영수증이 있으면 같은 사건 ID까지 비교한다. 구판 DRAFT가 최신개정보다 오래됐고 서버가 후속결정 불가를 검증한 경우에만 사건 영수증 없는 UNKNOWN을 내 성공이 아닌 상태로 닫고 새판을 독립 검토한다. RECORDED는 이 조건으로 잠금을 해제하지 않는다.
- 조회 가시성을 잃으면 계약뿐 아니라 앱/적용본 부모 캐시도 숨기고 재조회한다. 계약이 실제로 없는 v2는 reader를 마운트하지 않아 404 재조회 반복을 막는다. 기존v1을 유지하며 v2 초안작성/제작의 미연결 버튼은 명시 비활성이다.

### 검증 및 제한

- 실제 API: `output/usage-holds-mqfv5s1m/isolation.json` 156수집/실행/156PASS, 1422.62초(23분42초), wrapper1428.847초/0. 대상은 B5 kit_review_api + B3 kit_api/kit_rejection/kit_contract_v2 네 파일. 소스779·보호자산259 전후 및20:44 현재 지문 불일치0, SQLite896경로 모두ownRUN/금지접근0/외부conftest미적재. FastAPI·실제 principal/PDP/저장 계약/원장과 격리 합성 fixture를 사용하며, 기존 성공 build의 Preview/게시/물질화 대역을 실제 Host·운영 RAW 검증으로 세지 않는다. setup445.51초/call976.33초가 실측이며 다음 기능 ETA와 별도다.
- 프런트 최종: `output/studio-contracts-9f24a00a-3ab4-4f0d-9ffb-f99123075e04/report.json` 81PASS/388.8497ms, 25소스 전후·현재불일치0. 기존57 + 키트24(UNIT/API/SSR23, STATIC1), 전체 STATIC2는 동작 시험과 별도다. release-catalog7PASS/110.2757ms. 최종 제품build(tsc 포함), 지정6eslint, fixturebuild PASS. 기존 dynamic-import/큰chunk 경고 유지.
- 격리 보완: `usage-holds-ljrr0aal`32PASS/0.28초/wrapper0.7909초. 제품의 읽기 전용 원장 GET을 RW로 바꾸지 않고, 기존 guard가 모든 file: URI를 거부하던 부분에 현재RUN 기존 정규파일의 정확한 canonical URI+`?mode=ro`만 지원했다. 외부·형제RUN·누락·비정규·쓰기·vfs/추가옵션·resolve 우회 차단 및 실제 SQLite INSERT readonly 거절 포함. 원장파일 신규생성/복구 없음. 공통 B0/DP reader의 cold-start 스키마 준비까지 무쓰기라고 주장하지 않는다.
- 실패 기록: `usage-holds-b2t05mci` 최초4파일 실행은 초반 실패를 좁히려고 중단해 완료 증거로 사용하지 않는다. 선택2FAIL `usage-holds-v3lr6dvp`는 위 URI guard 차단(ownRUN만, 외부운영DB 접근 아님), 실패 증거 유지 후 현재4파일156PASS 재검증. 중간 빌드의 nullable 타입 전파 오류는 releaseCatalog의 타입 한 줄로 수정하고 기존7회귀/제품build 재통과. 실패를 처음부터 PASS였다고 보고하지 않는다.
- 독립 검토: Hilbert read-only. 구판 UNKNOWN 영구잠금·가시성 상실 부모캐시 P2 두 건을 수정·정적 재대조 종결(새 P1/P2 없음). 무계약 reader 미마운트 및 guard도 확인했다. 검사 실행은 main이며 독립 실행은 아니다.

### 확인 화면 / 다음

`http://127.0.0.1:8768/tests/studio-transition.fixture.html?scene=kit&version=b5-kit-20260913-2035`

실제 KitAppPanel/검토 컴포넌트+메모리 합성 API. 타인검토·자기승인 차단·데이터보류·조회503 체험. 모든 fetch가 합성 내부 처리이며 미지원503, CSP connect-src none, 운영 인증/권한/승인 변경 없음. 기존8768 서버 HEAD200. 최신JS `studio-transition.fixture-DTHmkW8E.js`, CSS `studio-transition-D7vApZLv.css`. computer-use 초기화 kernel25276/helper_unknown_error로 실제조작 전에 실패했으며 **브라우저 NOT_RUN**이다. HTTP·SSR·빌드를 실제 클릭 수용으로 치환하지 않는다.

다음은 **수정 요청의 산출물 기준·제출ID 서버 결속/멱등 접수/초안 소비60~90분**. 기존 `/sprint/revision`은 feedback만 WBS에 넣으므로 UI 선행 GET만으로 원자성이 보장되지 않는다. 원 요청 기준과 제출 영수증을 서버에서 확인해야 한다. 일반 명령 UNKNOWN·같은PLANNING 비파괴 재개/B6 단일진입/B7 수용은 별도 잔여다.

소유: James core reader/GET/list, Codex DTO/flow/부모문맥/격리호환·최종검사·문서, Dewey KitAppPanel/KitContractReview, Godel 실제API36사례, Hooke 프런트21초기사례, Hilbert 독립검토. 최종수정은 Codex. 사용자로그 SHA7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510/main.py/App.tsx·운영DB/RAW/실역할·실승인·원격 보존, 기존dirty유지·미커밋·미푸시.

---

기록: Codex · 2026-09-13 18:57 KST. 권고10 / G3-B·G3-C / 첫 원료구매 앱의 요구→제작→검토 흐름.

## 판정

전체 **21/40=52.5%, 로컬18/28≈64.3% 유지**. 이번 기록은 B5 핵심 화면 기능 묶음의 구현·집중 검증 결과다. **B5 전체, B6 전역 단일 진입, 실제 브라우저·현업 수용 완료가 아니다.** 내부 함수·시험 수를 전체 점수에 가산하지 않는다.

## 이번에 연결한 기능

- BuildStartDialog: 자연어 요구·선택 업무·데이터 없는 요구초안 저장을 기본으로 노출하고 기존 옵션·키트 진입은 추가 설정에 보존. 실제 advisor 초안 API, 사용자/문맥·revision/CAS·본문·멱등 키 검증을 연결했다. 저장은 승인·프로젝트 생성이 아니다.
- StudioContent: 기존 결과/단계/작업/근거 패널을 재사용하는 공통 내용. 대표 행동 하나, 추가 작업 접기, 결과 전체화면, 작업 목록 접기, 명시 닫기와 입력 유지/비우기·새로고침 보호. 사용자·회사 전환 후 이전 내용 숨김. 전역 App은 아직 이관하지 않았다.
- 실행: 새 기획/기존 작업/쿼터 재개/복구/검토용 버전/수정/재분할/내려받기 연결. pause와 stop 분리. 허용 입력만 전송하며 store state/schema를 복사하지 않는다. REJECTED/ACCEPTED/UNKNOWN을 구분하고 접수를 실행 확인으로 바꾸지 않는다. stop 실패 시 active/HOTL 참조를 지우지 않는다.
- 결정: 일반 HOTL, Host 계약, 지원 능력/데이터 선언을 분리. 실제 요청 차수·질문 원문 SHA-256·화면 질문을 교차 확인하고 의견/선택 변경 시 확인 체크를 무효화한다. Host 원장 기록 후 미반영은 새 승인 없이 동일 사건 복구를 명시적으로 요청한다.
- 입력 초안: 요구, 명확화 답변/선택, 결정 의견, 수정 의견의 서버 저장·조회·명시 복원·폐기. 사용자/문맥/프로젝트/전체 대상/판본을 검사하고 다른 회사의 옛 메모리 키 읽기·쓰기·삭제를 차단한다. UNKNOWN 원키는 후속4xx에서도 보존한다.
- 결정 초안 사용 완료: Host/지원 능력/데이터 결정 사건과 실제 저장 입력을 서버가 대조한 뒤 명시 기록. 대기 카드가 없어져도 처리 기록에서 원 target·draft·event·consumeAttempt로 재확인한다. 승인/실행을 반복하지 않는다. 저장/제출 의견은 앞뒤 공백 정규화를 공유한다.
- RevisionRequestEditor: 작성 기준 전체 target을 고정하고 target별로 의견을 분리한다. 제출 전 GET에서 기준이 바뀌면 전송0·본문 보존. 명시 기준 재조회 시 옛 의견을 새 산출물에 복사하지 않는다. 이 선행 GET은 서버 원자적 CAS가 아니다.

## 검증 근거

1. 실제 FastAPI 집중: `output/usage-holds-rc74v0pf/isolation.json` — 64 collected/executed, 64PASS/30.46초, wrapper37.738초/exit0. B5 input drafts + B3 HOTL/decision-round/reconcile API. SQLite231회 모두 own RUN, 소스778·보호자산259 전후 불변, 금지 파일/SQLite 접근0, repository conftest 미적재. 18:54 현재 서버 소스 불일치0.
2. 프런트: `output/studio-contracts-794056d3-4754-4198-a651-b0aafa664b0f/report.json` — 57PASS/237.8847ms, 검사 대상20소스 전후 불변. 실제 action/store/decision flow/API/요구초안 모델 단위·React SSR·정적 검사이며 HTTP는 대역이다. 요구초안5건은 단위 검사이며 실제 요구초안 API의 이번 재실행을 뜻하지 않는다.
3. 제품 `npm run build`(tsc 포함), 지정13파일 eslint, 최신 합성 fixture build PASS. 기존 동적 import·대형 chunk 경고는 남으며 기능 실패로 바꾸어 보고하지 않는다.
4. 최초 서버63PASS1FAIL(`usage-holds-hg1_afw1`)은 데이터셋 winner 검증이 변경 task evidence만 찾던 오류. 실제 차수의 draft_versions와 변경 증거를 별도 확인하도록 수정, 위64 재검증. 최초 프런트49PASS1FAIL(`studio-contracts-1b26a014-7f6a-4992-b941-26d03478a12c`)은 old-key 삭제 경계로 수정했다. 실패 증거는 보존했다.

computer-use 스킬에 따라 실제 브라우저 확인을 시도했으나 초기화 `helper_unknown_error`로 조작 전에 실패했다. **브라우저/포커스/클릭/뒤로가기/현업 수용 NOT_RUN**. SSR·빌드·HTTP200을 브라우저 PASS로 바꾸지 않는다. 자동 승인 경로의 일시 사용량 오류는 최신 계정 조회와 동일 경로 읽기 재확인 성공 후 정상 경로로 재개했으며 우회·reset credit 사용은 없다.

## 확인 화면

`http://127.0.0.1:8768/tests/studio-transition.fixture.html?version=b5-20260913-1857`

기존8768 로컬 서버, 실제 StudioContent + 합성 상태/메모리 fetch. 요구 입력·작업 시작·Host 검토/복구·결과·연결 오류5상태. HTML connect-src none, 모의 API 외 실제 서버 fallback 없음. 초안 POST 전체를 구현한 E2E fixture가 아니며 미지원 모의 요청은503이다. 운영 데이터·승인·실행 없음.

## 남은 출구와 다음 순서

| 남은 기능 | 상태·필요 작업 | 초기 예상 |
|---|---|---|
| Kit v2 계약 검토 | 저장 계약 본문/차수/지문 GET, 적격 타인의 목록 진입, 기존 KitAppPanel v2 승인/반려 연결. 데이터 준비 차단과 검토 읽기 분리. 기존 v1 유지 | 60~90분 |
| 수정 요청의 서버 결속 | backlog 생성에 기준 artifact와 제출 ID를 원자적으로 고정하고 제출 후 초안 소비 검증. 현재 UI 선행GET만으로 보장하지 않음 | 상세 계약 확인 후 확정 |
| 일반 명령 UNKNOWN 해소 | 명령별 서버 영수증·반영 증거 부족. 기존 캐시 task ID만으로 잠금을 풀지 않음. 미확정 실행/버전 저장 자동 재전송 금지 | 다음 서버 계약 작업에서 산정 |
| 같은 PLANNING 비파괴 재개 | 현 서버가 같은ID도 아카이빙·payload 재시작하므로 안전 차단. 일반/쿼터 재개와 구분. checkpoint/중단 표식·취소 경합 수정 필요 | 별도75~120분 |
| B6 단일 진입 | App 단일 담당, new/draft/project/kit/release/mega URL·복귀·SSE 단일 mount. 요구초안 검토→적격 타인 승인→bootstrap operation COMPLETED→같은 project 진입 | B5 잔여 후 재산정 |
| B7 전환·수용 | 기존 앱/override 보존·브라우저·현업 수용 | B6 후 |

**중요:** `supportsInitialIdea=true`만 켜거나 advisor 초안을 기존 `/factory/projects`로 우회하지 않는다. 현재 부모는 새 요구/업무 참조를 보존하지 못하므로 저장까지만 지원한다. B3 승인·bootstrap 경로가 정본이며, 기존 메가/지식팩/기준정보/MCP/데이터 적용본의 동등 지원도 검증해야 한다. 신규 기획으로 기존 중단 기획을 몰래 대체하지 않는다.

## 소유·교차검토·보호

- Codex: 공통 내용/실행 UI/서버 초안 UI/미리보기/집중 실행·통합. James: action/store 반환 계약·읽기 검토. Dewey: 요구 입력·요구초안·RevisionEditor. Hooke: 결정 API/Flow/UI·집중57 검사. Godel: 별도 입력 초안 저장/API·실제 API 회귀. Hilbert: 읽기 전용 독립 권한/입력/결정/UX 검토. 시험 실행은 main이며 독립 실행으로 표현하지 않는다.
- 독립 지적: 캐시로 UNKNOWN 잠금 해제, 후속4xx 원키 폐기, 최신GET과 저장 확인 표시 불일치, 수정 의견 기준 자동 재결속, 소비 재확인 UI 소실, 의견 공백 불일치를 수정했다. 최종 판정은 TEAM_BOARD 마감란에 남긴다. 브라우저 및 위 미구현 출구는 종결하지 않는다.
- `data/interaction_log.jsonl` SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510` 유지. `main.py`, `frontend/src/App.tsx` 변경 없음. 운영 DB·RAW·실역할·실승인·원격 변경 없음. 기존 dirty tree 보존, 커밋·푸시 없음.

마감 재대조(19:00): Hilbert 지정 정적 리뷰 종결, 마지막 RECORDED 카드 분기의 consume 재확인까지 확인. 마지막 소스 기준 프런트57·제품build·fixturebuild 재실행 PASS. 18:59 프런트20소스 현재 지문 불일치0, 사용자 로그 일치, main.py/App.tsx diff0. 브라우저 NOT_RUN 및 위 미구현 서버·진입 출구는 그대로 OPEN이다.
