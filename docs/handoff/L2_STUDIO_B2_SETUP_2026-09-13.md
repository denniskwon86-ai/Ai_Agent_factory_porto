# B2 표준 프로세스 팩·설치·명시 이관 인계

작성자 Codex / 2026-09-13 02:27 KST. **B2 코드 출구 완료.** 실제 운영 설치·Starter 출시·브라우저/현업 수용은 아니다.

최종 **662 passed /1 skipped /148.00초**, `output/usage-holds-2kfaqye_`, 임시SQLite807경로/소스·보호자산 hash불변/금지접근0/전역conftest없음. skip은 Windows 실제심볼릭링크 생성권부재이며 별도환경에서 남겨둔다. Hilbert1차4건 및 후속P2두건(작성자재인수명시·주입DP승인검증)을 해소, 정적범위내 추가P1/P2없음. 후속 두재현은 실제회귀에 포함했다. 이하 첫실패 기록은 당시 이력으로 보존한다.

## 범위와 기준

- 사용자 지시에 따라 B2 다음 B3까지 승인 대기 없이 순차 진행한다. 운영 설치·실데이터·실역할/승인·앱 실행/배포·Git push는 자동 진행에 포함하지 않는다.
- 권고 착수4·7·10, G2-A/B/C→G3-B/C. 원료구매 첫 폐루프에 필요한 표준 업무·설치 문맥 기반이다.
- 전체 **21/40=52.5%**, 로컬18/28≈64% 유지. B2의 L2 수·테스트·파일 수는 제품 분자에 더하지 않는다. 70%는28/40이며 현 상태 대비 실제 완료7칸이 더 필요하다.

## 구현 계약

1. `core/data_preparation/process_pack_artifacts.py`: 안전 상대경로/스키마/원문SHA/정확한 데이터·앱 후보 참조 검증. manifest/profile/pack/blueprints 원문을 base64와 고정 지문으로 동일 DP DB의 `kit_process_artifacts`에 저장한다. 동일kit/version 같은원문 멱등, 다른원문409. UPDATE/DELETE/REPLACE 차단. 현재 파일/레거시 registry로 조용히 fallback하지 않는다.
2. `process_packs/afs.manufacturing.materials-processes/1.1.0`: NO_DATA/DOMAIN_REVIEW_REQUIRED 독립 참조 후보. 8L1·29L2, BK-01 구매계획·공급사선정·계약·발주, 다른키트 업무3개는 UNINSTALLED 바로가기. 앱들은 REFERENCE_ONLY다. 실제1.1.0 Starter 출시나 도메인 인증이 아니다. 기존1.0.0/운영키트파일 변경 없음. `.gitattributes`에서 새 JSON만 개행 변환 금지.
3. `process_schema.py`의 신규 `enterprise_process_installations`: 전체문맥/요청멱등키/불변plan/작성자·설치자/revision·attempt/stage/인스턴스·변경·적용이력. 실제 업무지도는 여전히 ECM profile payload 한곳이다.
4. `process_installation.py`: dry-run 계획 → 작성자 제안 예약 → 적격 설치자 명시 인수 → DP 단계 → ECM 초안 → 독립 승인자. v1 모든 원본에 이관/원본유지 결정을 요구하며 원본 지문과 명시 targetcontext, key→동일process_id 대응을 확인한다. overlay의 null/누락과 원문 전체를 보존한다. 명칭 기반 자동 병합은 없다.
5. `process_kit_instances.py`: 기존 registry/instance 구조를 바꾸지 않고 신규 전용 `kit_process_instances`에 operation/instance/root/artifact/identity 결속. 같은 DP transaction에 인스턴스 신규행+결속을 넣는다. 기존registry와 같은버전은 양방향 충돌. 고정원본 소비자는 이 전용 결속을 읽는다.
6. `process_configuration.py`: 승인 직전에 DP instance/identity/artifact 재검증. 승인판/head/change/outbox/installation APPLIED 모두 같은 ECM transaction. DP와 분산 원자성 주장은 하지 않는다. 후속head변경은 과거APPLIED이력을 지우지 않는다.
7. API: 기존 ECM 하위 router의 process-packs 조회/허용후보등록, process-installations legacy-preview/plan/start/get/resume/cancel. 기존 공통권한표와 명시회사·조직문맥을 재사용한다. DP instance/스냅샷목록/준비도/앱초안의 프로필 조회는 고정원본 해석기를 사용한다.

## 상태·복구

- PLANNED 또는 AWAITING_INSTALLER → PREPARING → AWAITING_APPROVAL → APPLIED.
- 실패는 FAILED_RETRYABLE 또는 FAILED_BLOCKED. DP 인스턴스를 자동 삭제하거나 새ID로 다시 만들지 않는다.
- 재개에는 expected_revision 및 서버 attempt_id CAS를 적용한다. 이전 시도의 늦은 실패가 새 시도를 덮지 못한다. 현재 적격자가 adopt=True로 담당자를 바꿀 수 있고 outbox에 인수 이력이 남는다.
- 다른 head나 v1 원본 변경은 계획 재검토가 필요한409다. 이미 설치한 동일팩 확장은 기존 instance를 계획에서 명시 선택해야 한다.
- 업무 정의 승인은 데이터 인증/앱 생성/권한 부여가 아니다. `data_ready=false`, `apps_ready=false`를 유지한다.

## 안전 검토에 따른 범위 조정

첫 기존 DP store ALTER/영구트리거/전역 생성 변경안이 자동 안전 검토에서 차단되었다. **그 제안은 적용하지 않았다.** 신규 전용테이블과 좁은 같은버전 등록 가드로 대체했으며, 새 연결의 in_transaction 확인 후 BEGIN IMMEDIATE로 최초표생성·legacy등록 경쟁을 막는다. 현재 변경은 승인된 더 좁은 대안이다.

## 검증 기록 — 초기 결과 이력

- 첫 B2 단독: **110 passed / 1 skipped / 23.97초**, `output/usage-holds-it7kn6_2`. 임시SQLite133경로만, 원본/소스 불변, 금지접근0, 전역conftest 없음.
- 첫 통합: **654 passed / 6 failed / 1 skipped /150.29초**, `output/usage-holds-l5kjpboe`. 5실패는 준비도 응답의 잔여kit변수 NameError, 1실패는 B1의넓은routecount가 B2추가까지셈. 수정하고 새팩 준비도HTTP도 추가해 재실행 중이다. 실패한 결과를 PASS로 합산하지 않는다.
- skip은 이 Windows 호스트의 심볼릭 링크 생성권 부재. 실제symlink탈출 시험은 별도가능환경에서 확인해야 한다. 일반경로탈출/절대경로/URL/원문변조 시험과 구분한다.
- B2 runner: SQLite는 새 output/RUN안만, Starter/data-kits/process_packs의 open-write/rename/delete 등의 Python감사 차단, subprocess차단, 원본 전체 hash 전후비교. T3의 과거변조writer는 여전히 미확정이며 이번과거문제해결로 주장하지 않는다.
- 독립 Hooke팩검증/James설치부정시험 작성, 메인 실제시험. Hilbert 1차 P1 1건·P2 3건을 수정하고 재검토 중이다.

## 후속

최종 B0/B1/B2 회귀와 독립재검토를 마쳐 B3에 진입한다. B3는 server ProcessContext, advisor revision/승인·bootstrap사가, 일반/키트 runtime2.0 생산자·소비자, 기존1.0 고정golden 및 현재권한·데이터보류 재검증 연결이다. B4~B7 UI·단일Studio·업데이트·브라우저/현업수용은 별도 남아 있다.
