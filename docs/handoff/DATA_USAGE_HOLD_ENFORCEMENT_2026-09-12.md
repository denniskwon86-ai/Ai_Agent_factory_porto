# 가격·과거 조직 시점 사용 보류 — 소비 경계 연결

- 작성자 / 기록 시각: Codex / 2026-09-12 17:26 KST
- 기준: claude/data-acquisition-orchestrator-20260905@e3a41768a + 아래 미커밋 구현. 직전 세 커밋은 9월 11일 푸시·원격 HEAD 일치를 확인했다. 이번 턴 커밋·푸시·병합·배포는 없다.
- 로드맵: 권고 5·6, G2-D. 첫 구매 폐루프에 직접 필요한 미검증 입력의 인증·소비 방지.
- 결과: 기존 보류 메모를 실제 인증·준비도·객체 조회·앱 스키마·계산 입력 차단으로 연결했다. 보류 해제·가격 정책 승인·소유권 승인·공식 실적 인증은 수행하지 않았다.
- 전체 **21/40=52.5%, 로컬 18/28=64% 유지**. D04는 2/4. 이 하위 묶음 완료를 영역 전체 연결 완료로 가산하지 않는다.

## 구현

| 경계 | 실제 동작 |
|---|---|
| 공통 정책 | usage_policy.py가 binding의 usage_holds, rehearsal_only, 과거 가격 보류 표식을 해석. 알 수 없는 보류 코드·잘못된 설정·없거나 문맥이 다른 결속은 차단 |
| Snapshot 조회 | get_snapshot/list_snapshots가 현재 결속의 보류를 읽기 전용으로 투영. ACTIVE 결속에 보류가 없어도 선택된 기존 판의 보류를 잃지 않음 |
| 인증·교체 | 서비스 사전 검사 + 저장소의 모든 CERTIFIED_STATES 인증 및 교체 트랜잭션 재검사. 정책 읽기 전에 BEGIN IMMEDIATE. 차단 시 인증일·인증자·기존판 철회·색인 변경 없음 |
| 준비도 | 기존 UNAVAILABLE 상태와 DATA_USAGE_HOLD 사유·데이터 오너·다음 행동 반환. 결과는 BLOCKED이며 READY/만료 경고로 통과하지 않음 |
| 객체 색인·근거 | 계획/기록/재생성·현재판/객체 조회·근거 결속·물질화 준비 상태에서 보류 반영. 독립 기록도 정책 읽기 전 쓰기 잠금 |
| 앱·계산 | 인증판의 앱 필드 추출, active_seals, load_sealed에 동일 판정. 보류된 최신판 대신 옛 판으로 조용히 폴백하거나 RAW 업무 행을 계산에 넘기지 않음 |

데이터셋 단위 보수적 차단이다. 가격을 새로 계산하거나 과거 조직 유효일을 추정하지 않는다. 스키마/인증 상태 이름은 새로 추가하지 않았으며 기존 RAW·DB 상태를 이행하지 않았다.

## 검증과 재현

1. `venv/Scripts/python.exe scripts/verify_data_usage_holds.py`: **234 passed, 실패/오류/SKIP 0**. 신규 보류 46건 + 기존 준비도·Snapshot·객체 색인·앱·계산 188건.
   - 최종 output/usage-holds-wg2g4k6f/tests.xml 및 isolation.json.
   - SQLite 168개 경로 모두 새 실행 폴더 안. 금지 경로 접근 0, 전역 conftest 미로드, 검사한 16개 소스·시험 파일 지문 전후 일치.
   - 시연·공표 원천·병행 추가된 회사 실적의 세 인증 종점 차단. 실제 인증 라우터 HTTP 409 확인. 인증 주체는 합성 테스트 사용자이며 운영 로그인/실사용 검증은 아니다.
2. `venv/Scripts/python.exe scripts/verify_kit_foundation_tests.py`: **186 passed**, 모든 SQLite 연결 금지. output/foundation-tests-bip19ymf/tests.xml 및 test-isolation.json.
3. `venv/Scripts/python.exe scripts/verify_kit_usage_holds.py`: 기존 foundation-raw-0yag5clt 사본의 정확한 RO URI만 허용. **61판 보존, 보류 25판 전부 차단**, 선행 5종의 6판 포함.
   - output/usage-holds-artifact-jmuyxcv8/verification.json.
   - DB SHA-256 전후 동일: 2048cfed491899496d6b4c9e3e5c810935960962e97be97cdb852eb8817e9184.
   - 사본의 인증·RAW 파일 수정 없음. 읽기 전용 검산이지 25판을 실제 인증 요청한 것이 아니다.

두 회귀 묶음은 서로 다른 시험 파일이며 합계 **420건 통과**다. 프로젝트 전체 T3/실사용/브라우저 검증을 의미하지 않는다.

## 실패에서 보완한 것·독립 검토

- 최초 fixture 누락·불완전 저장소 대역을 수정했다. API 회귀에는 tests/usage_hold_test_plugin.py의 임시 조직/정책만 주입했고 운영 조직은 읽지 않았다.
- 병행 OWNER_CERTIFIED 추가로 기존 고정 상태표 검사 2건이 실패했다. 새 종점을 제거하지 않고 tests/test_dataset_snapshot.py의 상태표·허용 성격·is_certified 기대 계약을 세 종점으로 명시했다. 이를 Codex의 실적 인증 구현으로 세지 않는다.
- 검토 요청자 Codex / 검토자 Galileo(별도 에이전트) / 판정: 제한적 코드검토 수용. 실제 운영·배포 승인 아님.
- P2: 같은 Python 저장소 락만으로 다른 SQLite 연결의 쓰기를 막지 못했다. 정책 확인 직후 별도 연결이 보류를 커밋하는 사례를 직접 인증·교체에서 재현했다(output/usage-holds-yew_gprk: 43 통과·2 실패).
- 인증·교체 첫 SELECT 전, 독립 색인 기록의 정책 조회 전에 BEGIN IMMEDIATE를 확보했다. 정책 검사 직후 경쟁 UPDATE 차단 및 커밋 후 추가된 보류의 소비 차단을 certify/replace/index 3경로에서 검증했다. Galileo가 좁은 수정에 대해 지적 해소를 확인했고 메인 Codex가 최종 234건을 실행했다.

## 변경 소유·다음 행동

Codex 변경: core/data_preparation/usage_policy.py, readiness.py, scope_index.py, store.py의 보류 투영·인증 잠금/검사, snapshot_service.py의 기존 시연/교체 검사, core/calc_dataset_loader.py, core/kit_app_builder.py, 보류 검사 도구 2개·회귀/격리 fixture·기존 계약 테스트 보완.

병행 작업자의 models.py OWNER_CERTIFIED, store.py의 실적 인증 열·서명 테이블, snapshot_service.py의 sign_actual_certification 및 관련 함수, api/routes/data_preparation_control.py의 실적 인증 API, tests/test_actual_certification.py, 실적 인증 제안/검증 계획 변경은 보존했다. 공통 파일 전체 diff를 Codex 단독 기여로 커밋하지 않는다.

다음 담당은 Codex와 실적 인증 구현 담당자다. 병행 변경을 확정한 뒤 다음을 확인한다.

1. 새 실적 서명 함수는 서명을 먼저 기록하고 최종 advance_snapshot에서 보류가 차단될 수 있다. **서명 전 보류 검사와 서명/인증 원자성**을 담당 구현에 연결·교차검토한다. 이번 검토 수용에서 해당 함수는 제외했다.
2. 가격 vintage·환산 및 과거 조직 유효성 근거, 정식 소유권/인증을 확보한다. 새로운 결속으로 자동 해제하거나 승인자를 대신 채우지 않는다.
3. 같은 사용자·회사·기간의 앱/계산/수용 검증으로 D04 연결 출구를 닫은 뒤 분자를 재평가한다.

운영 DB·원장·RAW·권한·회사 설정·실발송은 변경하지 않았다. data/interaction_log.jsonl 및 다른 팀원의 변경은 보존한다. 재개 시 선행 5종을 다시 적재하지 말고 위 인증 접점에서 시작한다.
