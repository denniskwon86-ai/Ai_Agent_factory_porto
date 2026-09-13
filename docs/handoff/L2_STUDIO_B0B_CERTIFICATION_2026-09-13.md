# L2·단일 Studio B0-B 인증 경계 구현 인계

- 작성자: Codex / 2026-09-13 00:59 KST
- 사용자 지시: 다음 단계를 실제 구현하고 단계 완료마다 전체 진척을 보고한다.
- 승인 기준: `docs/design_l2_unified_studio_execution_2026-09-12.md` §9 B0-B, U03/U20/U21.
- 브랜치: `codex/l2-unified-studio-20260912`, 시작 HEAD `58e666833`.
- 전체 **21/40=52.5%**, 로컬 **18/28≈64%** 유지. 시험 개수나 안전성 하위 항목을 제품 영역의 완료 단계로 가산하지 않는다.
- 최종 판정 / 시각: **B0-B 지정 출구 완료 / 2026-09-13 01:01 KST**. B0-A와 합쳐 B0 기준선 복구를 종료한다. U03/U20/U21 구현·격리 회귀·독립 정적 검토 근거이며 전체 T3/운영 인증 완료가 아니다.
- 이전 `L2_STUDIO_B0_IMPLEMENTATION_2026-09-13.md`의 B0-A 완료 및 00:10의 B0-B 부분 기록은 당시 이력이다. 미완료 목록 1~6의 후속 구현은 본 문서다.

## 구현 결정

### 회사 서명권 정본

`core/data_preparation/certification_authority.py`가 정책 등록·해석·종류별 `can_sign`을 담당한다.

- DP DB의 불변 `certification_policies`와 CAS head, 기존 Decision Ledger의 승인 사건을 결속한다. 정상 등록 명령은 기존 데이터 표준 관리권과 명시 회사 승인 근거를 요구한다. 이 관리권이 서명 grant가 되지는 않는다.
- 문서는 용도별 필요 서명, 종류별 부서/정확한 역할/범위, 명시 위임, 동일인 예외 여부, 대사 증거 최소 길이를 모두 명시한다. 누락을 관리자의 권한이나 직함으로 보충하지 않는다.
- 운영 정책 자동 시드 없음. 승인 매핑 미등록은 `ROLE_MAPPING_REQUIRED`409, 정책/원장 판독·무결성 실패는503. 오래된 정책으로 폴백하지 않는다.
- 승인 지문에는 회사 문맥·정책 ID/revision·내용·승인자·근거가 들어간다. 매번 원장 사건 유형/주체/지문/회사 문맥과 철회를 확인한다.
- 실제 활성 사용자·부서 역할과 승인 범위가 일치해야 한다. DATA_OWNER는 현재 승인된 데이터 소유부서와도 일치해야 한다. EXECUTIVE는 회사 정책에 명시된 역할이며 `is_executive`만으로 허용하지 않는다.
- 위임은 회사 정책에 명시된 사용자/위임자/종류/범위/유효기간/근거로 제한한다. 위임자도 현재 적격해야 한다. 첫 부적격 위임 때문에 뒤의 유효한 위임을 숨기지 않는다. 판정 불가503은 계속 차단한다.
- `OrgDirectory.resolve_scope(fresh=True)`는 공유 권한 캐시를 재사용하지 않는다. 다른 저장소 인스턴스에서 완료한 권한 회수도 다음 명령에 반영한다. 사용자·범위·정책 지문과 확인 시각을 서명에 기록한다.

`core/actual_certification_policy.py`의 기존 JSON은 안내·제안 기본값이다. 실제 서명에 적용되는 필요 종류/증거 최소 길이는 승인된 회사 정책 판본에 있으며, JSON 편집으로 승인 정책이 자동 변경되지 않는다.

### 불변 대상·멱등·원자성

`core/data_preparation/certification_subject.py`가 인증 대상과 명령을 담당한다.

- 대상에는 snapshot/checksum/source binding/instance/계약키, tenant/root/mode/scope, 자료 성격, 용도·명시 기간, 소유권 binding ID/digest, 서명 정책 ID/revision/digest, 필요 서명, 원천/대사 지문을 고정한다.
- 미리보기는 읽기 전용이다. 첫 서명이 subject revision을 기록한다. 클라이언트는 `subject_id`, `expected_subject_digest`, `client_request_id`를 보내야 한다.
- `BEGIN IMMEDIATE` 후 fresh snapshot/소유권/정책/대상/서명/보류를 검사한다. 서명 사건·용도/기간·최종 OWNER_CERTIFIED·멱등 응답이 같은 DP transaction에서 함께 확정된다. 선커밋 후 별도 인증 fallback 없음.
- 멱등 키는 subject/kind/actor/client request. 완료 후에도 동일 요청은 같은 사건과 당시 결과를 반환한다. 동일 키의 다른 본문은409. 기존 종류의 새 요청으로 서명을 덮어쓰지 않는다.
- 재시도도 현재 승인 소유부서의 PDP 읽기 권한을 확인한다. 해당 요청의 과거 subject 문맥도 검사한다. 현재 head만 보고 과거 결과를 반환하지 않는다.
- 동일인 복수 종류는 기본 거절. 명시 승인된 동일인 정책 예외와 양쪽 종류 적격성 검사가 있어야 허용한다. 마지막 서명 때 이전 서명자의 현재 적격성을 재평가한다.
- 정책/소유권/원천 변화는 미완료 대상을 REVIEW_STALE로 만든다. 명시 새 revision은 이전 서명을 보존하고 새 판에서 0건부터 모은다. 완료 판의 내용 변경은 새 snapshot이 필요하다.
- 기존 `snapshot_certifications`는 삭제/승격/자동 합산하지 않는다. 새 서명은 별도 `certification_signatures`에 기록한다. 정책·subject·서명·멱등 응답의 UPDATE/DELETE를 DB trigger로 차단한다.
- 저장소 일반 `advance_snapshot(... OWNER_CERTIFIED)`도 불변 대상과 필수 서명 집합을 확인하므로 인증 서비스 우회 경로가 아니다.

## HTTP 계약

모든 인증 요청은 서버가 검증하는 `X-Enterprise-Scope` 또는 기존 `enterprise_scope` query로 회사 범위를 명시한다. 서명용으로 사용자의 주부서나 루트를 추정하지 않는다.

| 메서드/경로 (`/api/v1/data-preparation` 아래) | 계약 |
|---|---|
| GET `/snapshots/{id}/certifications` | 같은 DP 읽기 시점의 snapshot/subject/signatures. stale/hold 상태와 감사 이력 |
| GET `/snapshots/{id}/certification-subject` | use_kind/period_from/period_to, 선택적 new_revision. subject 미리보기 |
| POST `/snapshots/{id}/certifications` | kind/use/evidence/period + subject_id/expected_subject_digest/client_request_id |
| POST `/snapshots/{id}/certification-subject-revisions` | 이전 subject ID와 새 미리보기 digest의 CAS, 현재 DATA_OWNER 적격성 |
| GET/POST `/certification-policies` | 데이터 표준 관리자. 현재 승인 정책 조회/명시 근거와 expected_policy_id로 새 판 승인 |

- tenant/root/mode/scope는 관리자도 면제하지 않는다. 현재 snapshot과 instance 문맥, 실제 승인 소유부서, 저장된 subject 문맥을 검사한다. 비가시/미존재는 같은404다.
- 노드 소속부서를 데이터 소유권 fallback으로 사용하지 않는다. 조직을 다른 루트로 재편한 뒤 새 루트에서 옛 서명 이력을 열 수 없다.
- 인가된 GET은 보류 중에도 이력을 반환한다. `ON_HOLD`, `usage_holds`, 집계 불가를 표시하며 신규 서명은409로 막는다. REVIEW_STALE도 새 검토 필요와 집계 제외를 명시한다.
- 정책 POST는 공통 권한표의 ADMIN_DATA_ACCESS. 서명/새 revision은 일반 PROJECT_RUN 대신 도메인 can_sign을 적용하는 이유를 공통 EXEMPT에 명시했다.
- 인증 접근 거부403/404는 대상·행위자와 함께 기존 감사 경로에 기록한다. 감사 저장소 장애의 처리 규칙은 기존 모듈 계약을 유지한다.

## 검증 및 독립 검토

실행: `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0`.

- `usage-holds-nstz55zp`: 집중158 통과/1 실패. HTTP 요청의 명시 조직 선택 누락을 보완했다.
- `usage-holds-mcvjdjvj`: 전체365 통과/111.54초. 기존322 + 실제 조직·원장 신규43.
- `usage-holds-8qgw9a75`: 전체378 통과/133.32초. 조회 일관성/불변성/독립 검토 회귀 추가.
- `usage-holds-8uj3i39h`: 전체380 통과/136.34초. 보류 중 이력·정책 관리 API 추가. SQLite469경로 임시 루트, 소스 불변·금지 접근0·전역 conftest 미로딩.
- 최종 `usage-holds-3tnn8abh`: **382 통과 / 135.97초**, 제3자 폐기예정 경고2. 기존322 + 후속60. SQLite473경로 전부 신규 임시 루트, 검사 소스 불변, 금지 접근0, 전역 conftest 미로딩. `tests.xml`과 `isolation.json`에 근거를 남겼다. 단계별 시험 수를 합산해 고유 건수로 주장하지 않는다.

독립 검토: 요청자 Codex / 검토자 Lorentz(`01a09618-0d9a-7241-a502-da93aa59e50a`). 파일 수정·테스트·DB 접근 없이 정적 교차검토했다.

1. 1차 P1 3/P2 2: ECM 상태값, 원장 사건 등록, 현재 권한 캐시, 위임 후보 처리, 중첩 정책 입력 검증 → 수정 및 재확인.
2. 2차 P1 2/P2 2: 실제 owner PDP, 저장된 루트 문맥, GET stale 상태, restart 용도 정규화 → 수정 및 실제 조직 회귀.
3. 3차 P2 1: 보류가 감사 조회도 차단 → 수정, GET200 이력/신규 POST409 회귀. 재확인 범위 내 추가 P1/P2 없음.
4. 마지막 공통 권한표/접근 거부 감사 보완은 메인 최종 점검에서 추가했다. Lorentz 최종 재확인에서도 새 P1/P2 없음, 기존 지적의 정적 닫힘 유지. 독립 검토는 정적이며 최종382 실행은 메인 담당자의 별도 증거다.

## 한계·다음 실행

- DP 내부 원자성이다. Org/ECM/Decision Ledger까지 분산 직렬화·전역 즉시 회수를 보장한 것이 아니다. 후속 명령/사용은 현재 정책을 재검사한다.
- 실제 권한 시험은 합성 `.invalid` 사용자와 신규 임시 조직/원장이다. HTTP는 개발용 신원 헤더를 사용했다. 실제 로그인/SSO·운영 회사 인증·브라우저 사용성 완료가 아니다.
- 신규 서비스 경계 시험과 기존 권한 대역 단위 시험을 구분한다. 시험 건수를 전체 제품 기능 수로 보고하지 않는다.
- 전체 T3 및 기존 starter asset 실행순서 변형 원인은 별도 미종결이다(`docs/test_plan/T3_2026-09-12.md`). 이번에 전체 T3를 통과했다고 주장하지 않는다. 후속 패키지/전역 시험에서는 자산 쓰기 격리를 먼저 고정한다.
- 다음 순차 배치는 B1: L2 저장 v2/권한/CAS/구버전 writer 차단. B0 지정 출구 확인으로 착수 가능하다. B4/B5 UI로 건너뛰지 않는다.
- 실제 회사 매핑 등록·활성화는 회사 승인 역할/위임표가 있을 때 별도 수행한다. 이번 코드 작업을 이유로 운영 역할을 생성하거나 승인하지 않았다.
- 운영 DB/RAW/역할/승인/앱/배포 변경 없음. 사용자 `data/interaction_log.jsonl` 변경은 보존·제외했고 SHA256은 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`이다.
- 이번 후속 구현은 로컬 미커밋·미푸시. 앞서 완료한 R0 push를 새 코드 push로 보고하지 않는다.
