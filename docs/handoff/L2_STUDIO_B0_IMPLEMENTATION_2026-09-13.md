# L2·단일 Studio B0 구현 체크포인트

> **최신 갱신 2026-09-13 01:01 KST:** 아래 00:10 기록 이후 B0-B의 남은 종류별 권한·불변 대상·멱등·GET 일관성을 구현하고 최종382 회귀 및 독립 정적 지적 해소로 B0 지정 출구를 완료했다. 후속 정본은 `docs/handoff/L2_STUDIO_B0B_CERTIFICATION_2026-09-13.md`. 아래 부분 구현·미완료 목록은 당시 이력이며 삭제하지 않는다. 전체21/40=52.5% 유지, B1 착수 가능. 전체 T3/starter 자산 순서 문제·운영 인증은 별도다.

- 작성자 / 시각: Codex / 2026-09-13 00:10 KST
- 사용자 요청: 승인된 설계대로 순차 구현하고 단계 완료마다 전체 진척도를 보고한다.
- 기준: `codex/l2-unified-studio-20260912`, 시작 HEAD `58e666833`.
- 원격 선행 조건: 사용자 목적지 승인 후 기존 브랜치 `574c26fd8`, 새 브랜치 `58e666833` 정상 push 및 원격 일치 확인 완료. 과거 문서의 푸시 대기 기록은 당시 이력이다.
- 전체 **21/40 = 52.5%**, 로컬 **18/28 = 64.2857%** 유지. 하위 회귀 복구·시험 수를 제품 분자에 더하지 않는다.

## 1. 단계 판정

| 단계 | 판정 | 실제 전진 / 남은 출구 |
|---|---|---|
| R0 기록·분기·원격 | 완료 | 두 브랜치 push 및 원격 커밋 일치 |
| R1 설계·독립 이중검토 | 완료(설계 한정) | 기존 revision2.1 및 12개 설계 지적 조치 |
| B0-A 읽기·소비·프로젝트 HTTP | 완료 | 기존 7실패 해소, 동일 읽기 snapshot, 호출자 conn 보존, 404/409/422/503 |
| B0-B 실적 인증 안전성 | 부분 구현 | 단일 DP write transaction·기간·덮어쓰기·HTTP 가시성. 아래 미완료 조건 유지 |
| B1~B7 | 미착수 | B0 전체 출구 전 다음 배치로 이동 금지 |

로드맵 권고 착수 5·6, G2-D 기준선 및 G4 계산 입력 신뢰성 보강이다. 실제 회사 데이터 인증이나 사용자 폐루프 완료가 아니다.

## 2. B0-A 구현

- `DataPreparationStore.get_snapshot/list_snapshots`는 첫 SELECT 전에 BEGIN하여 snapshot과 source-binding 보류를 같은 읽기 시점으로 반환한다. 목록의 여러 행도 같은 시점이다.
- 호출자 transaction에서는 keyword-only `conn=conn`을 명시한다. 그 경우 새 lock/connection이나 BEGIN/commit/rollback/close를 만들지 않는다. conn을 생략한 임의 중첩 transaction을 자동 감지하는 계약은 아니다.
- `load_sealed/active_seals`는 DTO의 `usage_holds`를 검증한다. 누락/손상/unknown은 차단하며 최신 보류판을 빼고 옛 판으로 폴백하지 않는다. 인증 쓰기의 `require_usable_conn`은 유지한다.
- `UsageHoldError → SealedDatasetError → ProjectDataBindingError`의 reason_code/category를 보존한다. 프로젝트 생성 HTTP는 비가시404, 업무 보류409, 정책 판독불가503, 계약 입력불충족422를 구별하고 차단 시 프로젝트 폴더를 만들지 않는다.
- FakeStore는 `usage_holds=[]`를 명시한다. SQL 저장소 흉내나 누락 정책 허용으로 시험을 통과시키지 않았다.

## 3. B0-B 이번 최소 수정과 한계

- 잠금 밖의 마지막 서명 여부 계산과 서명 선커밋→별도 인증 fallback을 제거했다.
- BEGIN IMMEDIATE 이후 fresh snapshot, 보류, 소유 binding, 서명 집합, 용도·기간을 읽고 같은 DP 연결에서 서명과 최종 상태를 확정한다.
- 저장소 상태 전환 관문은 `_advance_snapshot_conn`으로 추출해 재사용한다. helper는 열린 transaction을 요구하며 연결 수명·commit을 관리하지 않는다. 공개 `advance_snapshot`은 모든 상태 전이에서 쓰기 예약을 먼저 잡는다.
- 마지막 상태까지 SQL로 쓴 후 의도적 실패를 주입하여 마지막 서명·기간/용도·상태가 함께 롤백됨을 검증한다.
- 날짜를 명시적으로 정규화/검증하고 누락·불가능·역전 기간을 거절한다. 이미 서명한 기간·용도와 다른 요청은409, 같은 종류의 다른 서명자/증거는 덮어쓰기 거절이다.
- 인증 GET/POST에 기존 `_snapshot_or_404`를 선행 적용했다. 이번 HTTP 시험은 비가시 scope와 미존재의 동일404를 검증한다. 전체 tenant/root/mode/PDP 인증 성공·실제 로그인 검증으로 확대하지 않는다.

**아직 구현하지 않은 B0-B 조건:**

1. `can_sign(subject, actor, review_kind)`와 승인된 회사 직무/범위/위임 매핑. 현재 남은 `_require_approval_authority`는 데이터 표준 관리권이며 종류별 서명권을 대신하지 못한다.
2. 매핑 부재 시 `ROLE_MAPPING_REQUIRED` 차단, 동일인 복수 종류 금지 및 명시 정책 예외. 현재 구현됐다고 보고하지 않는다.
3. 불변 certification_subject ID/revision/digest, 정책·소유권·checksum·tenant/root/mode/scope 고정과 expected_subject_digest.
4. 정책/소유권 변경 REVIEW_STALE, 기존 서명 감사 보존·새 revision 분리, 완성 직전 기존 서명자의 현재 적격성 재검증.
5. client_request_id 기반 요청 멱등, 완료 후 동일 요청 결과 재반환, 같은 키의 상이한 요청 충돌.
6. 인증 GET의 한 시점 일관 조회, 전체 문맥·권한 성공/실패 통합 회귀. 기존 helper의 전역 관리자/오류 처리 정책도 B0-B 전체 문맥 검토에 포함한다.

회사 매핑을 저장·검사하는 코드는 기존 설계로 구현할 수 있다. 실제 회사 서명권 표의 승인·활성화는 별도이며 직함 문자열이나 관리자 플래그를 실제 매핑으로 자동 변환하지 않는다. 이번 수정은 위 미완료 위험이 남으므로 **운영 실적 인증 안전성 완료/배포 가능**으로 판정하지 않는다.

## 4. 검증 증거

실행: `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0`

- `output/usage-holds-8gl4xefa`: 277 passed / 27 setup errors. 기존 인증 fixture가 경로에 `WorkSpace` 단어가 있다는 이유로 임시 DB도 운영 DB로 오인했다. 실제 tmp_path 하위 검증으로 교정했다. 정책 검사를 제거하지 않았다.
- `output/usage-holds-m7bked87`: 308 passed. B0-A 및 기존 인증 회귀.
- `output/usage-holds-gs2e9r7v`: 313 passed / 2 failed. 새 인증 HTTP fixture의 키트 등록 누락을 보완했다. 제품의 등록 관문은 유지했다.
- `output/usage-holds-p3gj6t5l`: 317 passed, 67.29초. 호출자 transaction과 최소 인증 원자성·HTTP 포함.
- `output/usage-holds-taqkbm0e`: `--focused --b0`, 134 passed, 37.07초. 명시적 날짜 검증 추가 후 집중 재검증.
- 최종 `output/usage-holds-1avm64wq`: **322 passed**, 71.57초, SQLite237경로 전부 새 임시 루트, source 불변, 금지 경로 접근0, 전역 conftest 미로딩. 기존234 + 프로젝트8 + 새 경계38 + 기존 인증28 + 새 원자성/기간12 + 호출자 transaction2다.

각 실행의 tests.xml/isolation.json에 코드 SHA, SQLite 경로, 전역 conftest 미로딩을 남겼다. 위 실행들은 source 불변·운영 SQLite 금지 경로 접근0이다. 모든 테스트 수를 더한 값을 고유 시험 수로 주장하지 않는다.

시험 분리:

- 새 원자성 서비스 시험은 기존 authority fixture(소유권/표준 권한 대역)를 사용한다. 회사별 실제 서명권을 입증하지 않는다.
- HTTP 시험은 실제 라우트·임시 조직/ECM·권한 계산을 사용하지만 합성 신원은 개발용 헤더로 주입한다. 실제 로그인/SSO 시험이 아니다.
- 전체 T3·starter asset 순서 회귀·프론트 build·브라우저·현업 사용성·실데이터 인증은 미실행이다.

## 5. 독립 코드 검토

| 검토자 | 범위 | 첫 판정·조치 | 재확인 |
|---|---|---|---|
| Boyle `01a0961e-e2e7-79e2-9561-eb1350dded30` | B0-A | CHANGES_REQUIRED, P2 1건: 기존 호출자 transaction 재사용 경로 없음 | 명시 conn 및 rollback 시험 추가 후 PASS, 범위 내 추가 지적 없음 |
| Lorentz `01a09618-0d9a-7241-a502-da93aa59e50a` | B0-B 최소 원자성/기존 설계 잔여 | 새 원자성 결함 발견 없음. 전체 인증 조건 미충족을 구분 | 단일 연결 helper/선커밋 제거 정적 확인. 회사 매핑/subject/멱등은 여전히 미완료 |

두 검토자는 파일 수정·DB/테스트 실행을 하지 않았다. 메인 담당자의 실행 결과와 독립 정적 검토를 구분하며 실제 Claude/Gemini·회사 승인을 주장하지 않는다.

## 6. 다음 실행 및 금지

다음은 B0-B 남은 서명권 매핑 정본·불변 subject·멱등을 구현하고 U03/U20/U21 전체를 완료하는 것이다. 그 전 B1 L2 저장·B4 UI에 착수하지 않는다. 상위 설계를 다시 작성하는 단계로 돌아가지 않는다.

운영 DB/RAW/승인/역할/앱/배포 변경 없음. 기존 `data/interaction_log.jsonl` 미커밋 변경은 제외·보존했고 SHA256은 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`이다. 이번 코드 변경의 원격 push는 수행하지 않는다.
