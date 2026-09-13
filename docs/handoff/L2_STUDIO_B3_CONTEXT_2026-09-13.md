# B3 생성 문맥·초안·승격·2.0 계약 인계

작성 Codex / 2026-09-13. **B3 지정 코드·격리 회귀 출구 완료.** 아래 최종 기록이 현재 상태이며 그 아래 시간별 기록은 당시 이력이다. 제품 전체·운영·UI 완료를 뜻하지 않는다.

## 최종 완료 — 2026-09-13 09:42 KST

- 실행: `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0 --b1 --b2 --b3`, session2975 정상 종료/wrapper exit0. `output/usage-holds-6m4qchly/tests.xml`의1929개 중 **1923PASS/6skip/실패·오류0**, pytest2183.28초·JUnit2183.250초. 기존 FastAPI on_event 폐기예정 경고2개는 별도이며 main.py를 이 작업에서 수정하지 않았다.
- 격리: `isolation.json` selection빈값, 소스369·보호자산259 hash전후동일, SQLite2492경로 모두 해당RUN아래, blocked_sqlite_paths/blocked_file_writes빈목록, repository_conftest_loaded=false. 종료 후 현재 소스369개 재대조도 불일치0. 이전 선택 회귀/실패 결과를 합산하지 않는다.
- 증적 SHA256: isolation.json `ddfd33260a6685e8948dc1d6b6f8b782738d9dbddd557816372b8eb0c095f0b8`; tests.xml `d1872bac559615cd0e9eb7fd569cf354eaaf20caf3bbd78376fa9abee5086b12`.
- 독립 확인: 요청Codex / 검토Hilbert. 기존4P2 정적종결과 관련핵심회귀16개, B3 시험27파일 포함, 최종JUnit/격리기록을 읽기 전용 대조하여 **B3 지정 출구PASS**. 실제시험 실행주체는 main이다.
- 6skip: B2팩 symlink1, Host reconcile 계약symlink1, decision round draft/meta symlink2, bootstrap 임시marker symlink/dangling-symlink2. 모두 실제Windows symlink 생성권 부재다. 통과로 계산하지 않으며 해당권한의 별도격리환경 검증으로 남긴다.
- 완료 범위: 서버고정문맥→초안revision/승인→같은ID승격/부분복구→일반·키트2.0 생산/소비→릴리스/Host의현재권한·고정판/보류, 1.0보존, 키트반려/기존Host승인복구/HOTL·결정차수 및 취소경합. 전체저장소T3/실제LLM·RAG/브라우저·현업수용/운영인증·배포/다중호스트직렬화는 미완료다.
- 진척: **전체21/40=52.5%, 로컬18/28≈64%**. 사용자지정B2·B3연속단계 완료, L2개편B0~B3완료/B4~B7남음. 70%의추가7제품조건을 코드·시험수로 대체하지 않는다.
- 다음: B4 서버연결 보강→L2 설치/탐색/수정/별도승인 UI, 예상**150~240분**. 하단09:37사전대조와 상세설계§11보완 참조. B4 구현은 미착수이며 전역App.tsx는B6담당영역이다.
- 보존: 사용자로그기존10줄/SHA7720cc45…f510, branch/HEAD 및 main.py/App.tsx 불변 재확인. B0~B3 로컬미커밋·미푸시. 원본Starter/운영DB·RAW/실역할·실승인/외부배포·원격변경 없음. 후속작업은 위RUN 증거를 보존하고 소스변경 후 필요회귀를 새RUN으로 수행한다.

## 09:02 실행 이력 — 전체 지정 회귀 session2975 (09:42 마감)

- 최종 `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0 --b1 --b2 --b3` 실행 중. source/test전원동결,예상약25분. B3 OPEN/전체52.5%.
- 직전 zmv5h8sq 464PASS/2FAIL/3skip/307.34초/격리금지접근0. 두성공fixture의legacy작성방식을명시2.0생산자로수정. 마지막 c5qffnjy 6PASS/3.71초/SQLite17/소스자산불변/금지접근0. 두실패및API선행/후속조회503실측통과.
- Hilbert4P2모두정적종결. main _assert_resumable 및 _contract_review_context(strict=True)는엄격bound조회사용,2.0재개API가조회실패를빈상태409로숨기지않는다. 기존legacy분기유지.
- 첫재개=2975결과회수,전체증적확인전완료표시금지. main.py/App.tsx·사용자로그불변/운영·원격변경없음/미커밋·미푸시.

## 08:51 현재 체크포인트 — 동결/재실행 준비

- 선택 `usage-holds-py4q07im` 299PASS/3skip/930deselected/218초, 임시SQLite338/소스자산불변/금지DB0. 기존 tech_lead 종결 단위시험의 원본 failure bundle2쓰기와 Git subprocess1시도를 guard가 차단하여 wrapper exit1. 원본 변경 없음. main이 기존시험 tmp cwd+명시 GitManager 대역/실제 임시번들 확인으로 보정, 가드 면제 없음.
- Hilbert 추가P2 4건 보완: legacy1.0의 부분자동managed전환 금지(기본save_draft legacy보존, 명시 require_metadata=True만 신규), 신규2.0 LIBRARY 비계약 판정이 메타 요구보다 먼저, HOTL check의 bool사전조회 제거/UNKNOWN보존, 엄격 조회503/반영결과불명503 구별.
- **현재 생산자 계약 정정:** `nodes.execution._save_contract_draft`가 server state2.0일 때만 require_metadata=True를 전달한다. LLM 본문값은 사용하지 않는다. 기존 legacy `_resolutions` 소비는 유지하며 부분 파일 전환을 허용하지 않는다. 앞08:36의 매server save UUID 설명은 managed 신규에만 해당한다.
- main 실제 legacy두초안 HTTP/TechLead1·2 adapter/원장 readback 장애시험, Hooke31 HOTL서비스시험, Dewey2개호환성 부정시험 추가. 최신수정 AST통과, 재회귀전/독립4건마감전. B3 OPEN·전체52.5% 유지.

## 08:36 보완 — 새 차수 계약 / 아직 실행 전

- 최신 선택 결과는 `usage-holds-dcavqtay` 123PASS/4FAIL/1skip/198.25초다. 반려 READ회수2건은 data-admin 전사READ까지 제거하는 실제 회수 fixture로, API2건은 적격 DATA_ADMIN actor로 수정했다. 소스·자산불변/SQLite226/금지접근0. 새 소스 재검증 전이다.
- Hilbert 5건(취소 worker 예약, 비가시 BUSY, legacy 원장 자산문맥, DP ProcessError, stamp 후503) 정적종결. 후속 부모 get_event_strict 오류503도 수정했다. 신규 HOTL/결정 차수 최종 검토는 진행 중이다.
- `core/studio_hotl_context.py`: 영속 checkpoint_id/project/task/next 기반 request_id, 실제 질문집 digest, PENDING/NOT_PENDING/UNKNOWN. GET hotl/check의 `hotl_context`; POST hotl/resume의 `expected_request_id`, `expected_questions_digest`. 신규2.0/명시토큰 재개는 최종snapshot의 차수·고정5필드·workspace/template/config를 쓰기 전에 대조한다. 서버 조회 실패를 새 요청으로 만들지 않는다. 기존 무토큰1.0 재개는 유지한다.
- `core/contract_decision.py`/`nodes.contract`: 매 server save의 UUID 판, raw원문보존, 실제 compiler 읽기에만 현재 draftset/WBS 결속 overlay. pending 항목 `decision_request_id`, `expected_digest`, `draft_versions`, `round_status`. resolve도 같은 ID/digest를 받으며 실제 PDP/서버 owner/원장 callback→원자overlay→readback이다. 새 차수는 내용이 같아도 옛 결정을 상속하지 않는다. 메타 없는1.0은 LEGACY_UNPREPARED, 신규2.0 메타 유실은 차단한다.
- 결정의 RESERVED/RECORDED 부분 상태는 ID를 보존하고 재append를 금지한다. 자동복구 API라고 주장하지 않는다. 기존 Host 승인 reconcile은 별개의 복구 기능이다. 질문/의견의 사용자별 서버입력 draft 및 feedback artifact 기준선 저장·복원/소비는 B5 구현·시험 대상이며 B3에서 구현했다고 세지 않는다.
- `studio_execution_guard`: 복구·명령 분리 외에 결정은 exclusive/quiescent, 실행 명령은 같은프로젝트 명령 중 false. `finish_before_cancel`은 요청 취소/반복취소에도 전체 쓰기 worker 회수를 기다린 뒤 취소를 반환한다. 다중호스트 직렬화는 보장하지 않는다.
- James 반려/legacy오류시험, Hooke 실제 thread cancellation/HOTL순수helper/메모리서비스시험 동결. Dewey decision_round시험 마지막 작성, main API시험/runner 동결 준비. 시험 writer 완료 후 선택 회귀→전체 B0/B1/B2/B3. runner에 기존 contract_decision_api/capability_decision_normalization/tech_lead_contract_draft 추가로 영향 범위 검증.
- 사용자 interaction_log SHA7720cc45…f510 08:35 재확인. 전체52.5%/로컬18/28, B3 OPEN/미커밋·미푸시. 기존08:04 실행 중/잔여검토 상태는 이 기록으로 갱신한다.

## 최신 보강/검증 — 2026-09-13 08:04 KST

- 선택 회귀 `usage-holds-_q7bmbx7`:176PASS/2skip/738deselected/411.23초, 임시SQLite246경로·소스자산불변·금지접근0. 2skip은 Windows 실제 symlink/dangling-symlink 생성권한 부재다.
- 그 뒤 설계 §6.1의 키트 `/contract/reject`, Host `/contract-review/reconcile` 누락을 발견해 추가했다. 위 결과는 이후 신규 변경의 통과 근거가 아니다. 반려는 현재 개정·지문·타인 적격성·원장·CAS·재접수/승인판 보존이며 기존 DB DDL은 바꾸지 않는다. 복구는 기존 승인 원장 검증→같은 원문/원승인자/시각의 atomic stamp→bound checkpoint 승인투영/read-back이다. 새 승인과 자동 실행 재개는 없다.
- `studio_execution_guard`는 같은 프로세스에서 start/resume 명령의 await 구간과 승인 복구를 분리한다. 다중 호스트 직렬화를 주장하지 않는다. 상태/stamp 각각 실패는 성공으로 감추지 않으며 같은 사건으로 복구한다. 새 검토 차수는 같은 지문이라도 과거 승인으로 복구하지 않는다.
- 04:45경 명령/독립 검토가 사용 한도로 중단됐고 08:00경 명령 재시도 성공으로 재개했다. 신규37파일 AST 확인. 선택 실행 `usage-holds-6wyns_sv`는 테스트 상수 MANAGER_B가 없어 수집1오류; 실제 MEMBER_B로 수정 후 재실행 중이다. 후속 독립 검토 및 §7.3 질문/결정 차수 식별자 추가 누락 감사가 아직 남아 있다.
- B3 OPEN, 전체52.5% 유지. 최종 `--b0 --b1 --b2 --b3`는 아직 미실행. 재개 시점 기준 잔여45~75분 추정. 사용자 로그 불변 재확인, 미커밋·미푸시.

## 범위와 제품 진척

- 사용자 지정 B2→B3 연속 진행이다. 승인 설계 `docs/design_l2_unified_studio_execution_2026-09-12.md` §8/11/14의 B3 출구: 초안/승격 복구, 양쪽 생성 경로, 1.0 해시 보존, 2.0 유실·위조 차단.
- 권고4·7·10 / G2-A/B/C→G3-B/C, 원료구매 첫 수직 폐루프의 생성 문맥 기반이다. L2 탐색·수정(B4), 단일 Studio(B5), 제품 진입(B6), 브라우저·업데이트·현업 수용(B7)은 별도다.
- 전체 **21/40=52.5%, 로컬18/28≈64% 유지**. 70%=28/40에는 실제 제품 종료 기준7개가 더 필요하다. 구현 배치·파일·테스트 수를 가산하지 않는다. 새 후보팩은 여전히 NO_DATA/DOMAIN_REVIEW_REQUIRED/REFERENCE_ONLY다.

## 구현·연결

1. `core/enterprise_context/process_context.py`: 승인된 ECM 업무판과 B2 고정 원본에서 서버 ProcessContext를 만든다. 정확한 tenant/root/mode/scope, profile/process ID, 의미 지문, 데이터 요구·결속·인증판·정책·사용권 근거를 고정한다. 표시명/순서 변화와 의미 변화는 구분한다. READ/DRAFT/BOOTSTRAP/GENERATE/RUN/RELEASE마다 현재 권한·사용 가능성을 재검사한다. 데이터 미준비 상태는 조회/계획/준비까지만 허용한다.
2. `core/advisor_revision_store.py`, `studio_drafts.py`: 초안 revision/expected_digest CAS, 요청 멱등, 별도 승인/반려, 불변 승인 원문, 선택한 승인 revision 조회. 저장소의 고정 identity와 command digest를 클라이언트가 정할 수 없다. 누락된 선택값과 명시 해제를 구분한다.
3. `core/studio_bootstrap.py`, `studio_project_files.py`, `advisor_bootstrap_ledger.py`: 고정 project/operation/event ID로 준비 사가를 실행한다. 메타·state 원문 투영 read-back과 실제 원장의 동일 이벤트 접수 확인 후만 READY/COMPLETED다. 원장 손상은 재생성으로 감추지 않는다. 분산 원자성은 주장하지 않는다.
4. `api/routes/studio_draft_control.py`: 기존 advisor 하위에 문맥 생성, CAS 초안 저장/조회, 결정, bootstrap/operation 조회 계약. strict 요청과 명시 선택 문맥, 현재 권한 검사, 공통 route authority에 연결했다. `main.py`는 수정하지 않았다.
5. `core/app_runtime_contract.py`, `host_contract_compiler.py`, `project_contract_aggregator.py`, `nodes/contract.py`: 일반 생성 문서2.0은 서버의 고정 문맥을 포함한다. 기존1.0 producer/canonical/fingerprint를 별도 golden으로 보존한다. Host wire1 및 ProjectState5.3.0을 문서2.0과 혼동하지 않는다.
6. `core/kit_app_builder.py`, `kit_app_contract.py`, `api/routes/studio_kit_control.py`: B2 고정 원본·선택 업무로 키트2.0 초안→다른 승인자→실제 승인 원장→후보 게시→물질화. 초안/승인 revision과 지문 CAS, 동일 요청 재접수, 현재 생성/승인 권한을 검사한다. 기존1.0 API로 B2 적용본을 생성하는 우회는 차단한다.
7. `core/studio_release_cohort.py`, `studio_project_context.py`, `studio_release_context.py`: 신규 프로젝트 예약 및 키트 release cohort를 서버에서 찾는다. 복원 파일이 2.0 표식/문맥을 잃어도 legacy로 강등하지 않는다. 새 키트 후보 승인만으로 이미 승인된 운영 R1을 중단하지 않고 R1의 고정 원문·원장 및 현재 사용권을 검사한다.
8. `api/routes/factory_control.py`: 시작/재개/체크포인트/복구/계약 결정/게시에서 고정 문맥·현재 행위 권한을 재검사한다. 일반 게시 첫 쓰기 전 최종 소유 경계와 승인 원문을 대조한다. 검증한 계약을 후보·운영 물질화에 그대로 전달한다. 조회자의 선택 상위 조직과 실제 데이터 대상 조직을 분리한다. 복사/복원으로 신규 출처를 우회하지 못한다.
9. `core/studio_runtime_data.py`, `api/routes/app_data_runtime.py`, `core/app_contract_gate.py`: Host 실제 dispatch와 proof가 고정 인증판만 소비한다. 결속/원본/인증/현재 hold를 같은 DP 읽기 트랜잭션에서 재검사한다. 새 인증판을 최신판으로 대체하지 않는다. 제공할 release와 proof의 세 지문을 재대조하며, RAW를 실제 파싱한 바이트의 checksum도 검사한다.
10. `core/studio_release_readiness.py`, `core/release_promotion.py`: 양쪽 게시 경로의 준비도는 실제 사용하는 고정 데이터 집합만 평가한다. 기본30일/고정 profile 정책의 신선도는 Host 소비에도 적용한다. 준비도 지문과 Host 지문을 일치시키고, 운영 물질화 전후 게시판/현재 RELEASE 권한이 바뀌면 ACTIVE 전이를 차단한다. native-only의 명시 READY/빈 데이터 집합과 NO_DATA 지문을 구분한다.

## 복구와 알려진 한계

- Bootstrap: RESERVED→PROVISIONING→CONTEXT_WRITTEN→LEDGER_PENDING→COMPLETED. 동일 operation은 고정 ID로 재개하고 부분 상태는 SETUP_INCOMPLETE로 잠근다. Windows 파일 잠금과 저장소 CAS를 함께 사용한다.
- marker 원자 기록 중 hard kill: 정확한 이름의 완성 임시파일 내용이 해당 operation과 일치하면 복구한다. 부분 JSON/다른 operation/외부 파일/심볼릭 링크가 있으면 BLOCKED409로 보존한다. 원본·다른 작업 파일을 삭제하지 않는다. 모든 강제 종료 상태의 자동 복구라고 주장하지 않는다.
- ECM/조직/DP/FS/원장 전체에 걸친 분산 직렬화·원자 커밋은 없다. 같은 저장소 transaction, 불변 참조, 전후 재검사, 재시도·차단을 제공한다. DB 전체가 외부에서 교체되는 공격에 대한 외부 공증은 별도다.
- 실제 임시 DP/PDP/ECM/승인/원장/키트 publisher/물질화는 시험 대상이다. 합성 인증 메타데이터와 RAW를 사용한다. 일반 생성 전체 LLM→RAG 게시, 실제 회사 인증/역할, 운영 로그인, 실제 사용자 브라우저 수용, 실데이터 실행/배포의 증거가 아니다.
- API/후보 계약은 준비했지만 두 SW생성기 화면을 하나로 바꾸는 B5/B6 UI 작업은 아직 하지 않았다. 일반 workflow의 RAW→LLM 반출은 별도 정책 경계이며 이 작업으로 자동 허용하지 않는다.

## 검증 이력 — 최종 실행과 합산 금지

- B2 최종(선행 증거): `output/usage-holds-2kfaqye_`, 662PASS/1skip/148.00초. B3 통과를 뜻하지 않는다.
- B3 첫 수집: `output/usage-holds-zvb9nz0c`, seed 이전 NODES 참조의 동일 원인3 collection errors. 실행 전 fixture 초기화를 수정했다. 원본/소스 불변, 금지 DB 접근0.
- B3 첫 실행: `output/usage-holds-8mhv496g`, **861PASS/3FAIL/1282.58초**. OwnershipError가 corruption503으로 변환된 문제, 실제 primary부서 READ 정책과 다른 시험 기대값, dispatch 시험 monkeypatch 재귀를 각각 수정했다. 테스트를 삭제하거나 느슨하게 우회하지 않았다.
- 첫 실행의 격리 guard는 무관한 legacy skill import의 상대경로 mkdir3회를 차단했다. 실제 원본 쓰기는 발생하지 않았다. runner가 실제 해당 모듈만 새 RUN cwd에서 먼저 초기화하도록 고쳤으며 guard 면제·앱 대역으로 숨기지 않는다.
- 수정 확인 `--select` 결과는 최종 전체 회귀와 구분한다. 최종 명령은 `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0 --b1 --b2 --b3`이다.
- runner는 새로운 output/RUN 내부 SQLite만 허용하고 원래 data/projects/library/workspace 및 Starter/데이터키트/팩 쓰기를 차단한다. source/자산 SHA 전후 일치, 금지 접근0, 전역 conftest 미로딩을 별도로 확인한다. 모든 source writer를 freeze한 뒤 실행한다.
- 전체 저장소 T3와 동일한 시험 집합이 아니다. Windows 실제 심볼릭 링크 생성권 부재의 skip은 별도 권한 환경에 남긴다.

## 독립 검토와 소유권

- 요청 Codex / Hilbert read-only 독립 검토. 출처 유실, 원장 오류·멱등, 승인판 추적, proof 재결속, parsed RAW, hard-kill marker, 게시 고정 대상 조직/준비도 연결을 검토했다. 최신 정적 범위에서 추가 확정 P1/P2 없음. 실제 회귀 완료와 구분한다.
- James: ProcessContext·키트 producer/승인·실제 임시 publisher 시험. Hooke: 1.0/2.0 문서·물질화·cohort 및 고정판 준비도 시험. Dewey: advisor 저장/원장 및 초안·bootstrap/API 시험. Codex: API·사가·Factory/Host·승격 경계·격리 실행/통합. 공유 파일은 한 명만 편집했다.

## 재개·보존

- 브랜치 `codex/l2-unified-studio-20260912`, HEAD `58e666833b6d346297231a6e8da5c1aef8ac5cc2`. B0~B3 변경은 로컬 미커밋·미푸시다. 이번 요청에 커밋/푸시를 추가하지 않았다.
- 사용자 `data/interaction_log.jsonl` 기존10줄 변경 보존. 기준 SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`; 일괄 stage 대상이 아니다.
- 운영 DB/RAW/실역할/실제 승인·앱·배포·기존 Starter1.0.0은 변경하지 않았다. `main.py`, `frontend/src/App.tsx`는 후속 단일 담당자 영역으로 보존했다.
- 최종 B3 지정 출구 통과 후 B4: 설치→L2 조회→기본 수정 제안→별도 승인→새로고침의 프런트 연결. 상세 예상 시간은 코드 대조 후 최신 PROGRESS에 기록한다. B5/B6 단일 화면 통합과 혼합 완료하지 않는다.

### B4 사전 코드 대조 — 구현 아님

- `frontend/src/components/CompanySetupPanel.tsx`의 ThreadTab은 기존 평면 프로필 저장/승인과 canEditOrg를 사용한다. 새 L2 편집에는 resolved 응답의 `process_config.*` capabilities를 사용하며, 조직 편집권과 업무 제안/승인권을 혼동하지 않는다.
- `frontend/src/lib/companyApi.ts`에 B1/B2 별도 DTO/요청 adapter를 추가할 대상이다. 기존 Profile/ThreadNode는 L1 legacy projection 소비자를 위해 유지한다. `context_root_id`는 tenant/company 표시 ID와 같다고 추정하지 않고 서버 조직 트리의 실제 루트·명시 선택 scope로 구성한다.
- 검증된 회사/조직/실제·가상 문맥을 화면 상단에 고정하고, L1 선택→L2 목록/상세→기본 수정 제안→별도 승인자 검토/적용→새 조회 흐름을 연결한다. NO_DATA/DOMAIN_REVIEW_REQUIRED 팩을 운영 인증 완료나 앱 생성 가능으로 표시하지 않는다.
- 초기 범위는 이름·설명·순서·사용 여부 등 설계의 기본 명령이다. 불변 승인판/expected head·digest CAS,409입력보존,늦은다른문맥응답무효화,자기승인차단,조회실패와빈구성구별을 UI에서 시험한다. B7의업데이트/복원전체와B5의제작입력draft는별도다.
- B4 예상90~150분. TypeScript/build·상태/adapter 단위회귀와 실제브라우저검증을 구분해 기록한다. 전역 App.tsx 단일진입 교체는 B6까지 하지 않는다. 현재 이 사전 대조로 frontend 파일을 변경하지 않았다.

### B4 사전 대조 보정 — 2026-09-13 09:37 KST

- 요청 Codex / 검토 James, 메인 소스 재확인. 읽기만 수행했으며 B3 소스 동결과 B4 미착수는 유지한다. 위 사전 가정 중 조직 루트와 capabilities 해석을 아래처럼 정정한다.
- 표시 트리의 `default_parent_id` 최상단은 업무 구성의 운영 루트가 아니다. B1의 활성·유효기간·단일 `OPERATING_PARENT` 경로 검증을 재사용해, 명시 선택 scope에서 정확한 root와 경계를 반환하는 조회가 B4에 필요하다. tenant/company 이름이나 화면 트리로 root를 추정하지 않는다.
- `resolved.capabilities`는 역할 capability 집합이다. 선택 범위의 편집·승인 가능성을 보장하지 않는다. B4에서 같은 `_authorize`를 사용하는 범위별 행동 projection을 제공하고, 실제 변경 endpoint의 fresh 판정은 그대로 유지한다. 권한 조회 장애를 빈 권한/승인 가능으로 바꾸지 않는다.
- 현재 설치는 `/process-installations`이다. 알려진 operation ID의 GET/재개는 있으나, 별도 담당자의 대기 건 발견·재접속을 위한 operation/변경안 목록과 change 상세 GET은 없다. 경계별 읽기 권한·제한된 페이지 크기·초안 무결성 확인을 갖춘 조회를 먼저 보강한다. 목록 조회가 설치/승인/재개를 수행해서는 안 된다.
- 현재 기본 변경은 ADD_NODE/RENAME/SET_USAGE/MOVE_NODE/ADD_SHORTCUT/REMOVE_SHORTCUT만 있다. 설명(note)과 placement 순서 변경을 추가해야 한다. MOVE_NODE는 순서 변경의 대용이 아니다. 기존 process/placement/앱 ID, 승인판, 의미 지문과 표시 지문의 구분을 보존한다. 데이터·앱 참조를 클라이언트 입력으로 새 인증/실행 계약으로 승격하지 않는다.
- 설치 흐름은 후보 조회 → 적격자의 명시 register → 원래 Plan 입력과 plan_digest로 start → 최신 revision으로 별도 resume/인수 → 적격 타인 approve → operation GET과 resolved를 각각 재조회한다. plan 반환 전체를 start body에 펼치지 않는다. NO_DATA/DOMAIN_REVIEW_REQUIRED/setup_only를 앱 준비 완료로 표시하지 않는다.
- B4 순서: 서버 조회·기본 명령 보강 및 실제 격리 HTTP 부정 시험 → companyApi의 별도 v2 DTO/오류 adapter → CompanySetupPanel의 L1/L2 탐색·제안/검토 → EnterprisePage/KitOperationsPanel 연결 → 타입/빌드·단위/SSR·브라우저 증거 분리. App.tsx 단일 진입은 B6, 표준 업데이트/복원과 현업 수용은 B7이다.
- 예상 시간은 위 서버 보강을 포함해 **150~240분**으로 갱신한다(종전90~150분 대체). 구현 시 core/API·UI·시험 파일 소유자를 분리하고 독립 권한/최종 UX 검토를 거친다. 전체21/40=52.5%에는 가산하지 않는다.
