# Claude Code 구현 작업서 · 앱 전달–의사결정–발간 폐쇄루프

> 작업 ID: `M6-UI-03C / PRODUCT-CLOSED-LOOP-20`  
> 작성: Codex / 2026-08-03 KST  
> 승인 상태: **Supervisor가 클릭형 프로토타입을 제품 UI 기준선으로 승인**  
> 구현 상태: 실제 React·API·DB 미착수  
> 승인 UI: `uiux-prototypes/closed-loop-product-samples/`  
> 상세 도메인 설계: `docs/design_app_delivery_decision_publication_loop.md`

## 1. 구현 목적

두 개의 제품 폐쇄루프를 실제 시스템에 만든다.

1. `SW 생성 → 릴리스 → 지정 사용자 전달 → 수신자 수락 → 내 앱 등록 → 공동 업무`
2. `시뮬레이션 → Decision Package → 관점별 검토 → 회의 → 결정 → 실행과제 → 효과측정 → 대내외 발간`

정적 프로토타입의 화면을 그대로 복사하는 작업이 아니다. 샘플 데이터와 가짜 상호작용을 실제 회사 문맥, 사용자 권한, 릴리스, 시뮬레이션, Decision Ledger, 구조화 보고서 계약으로 교체한다.

## 2. 구현 기준 우선순위

충돌할 경우 아래 순서로 판단한다.

1. 본 작업서의 구현 경계·완료 조건
2. `docs/design_app_delivery_decision_publication_loop.md`의 데이터·상태·API 설계
3. `docs/uiux/LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md`
4. `docs/uiux/LIVING_ENTERPRISE_UI_DESIGN_SPEC_2026-07-30.md`
5. 승인 클릭형 프로토타입의 정보 위계·동선
6. 현재 API의 권한·상태·오류 계약

시각적 세부값이 문서와 다르면 승인 프로토타입을 참고하되, 본문 12px 이상·키보드 접근·실제 상태 표현은 UI 설계서를 우선한다.

## 3. 변경 금지·분리 원칙

### 명칭 호환

승인 화면의 사용자 표시명은 `Jarvis`를 사용한다. 기존 문서·코드의 `Atlas`, `Supervisor Chat`, `atlasSessionStore`는 같은 전역 비서 기능의 레거시 내부 명칭으로 취급한다. 이 작업에서 별도 비서 세션이나 두 번째 채팅 API를 만들지 말고, 기존 계약 위에 호환 adapter를 둔다. 제품 명칭을 전역 변경하는 일은 별도 결정으로 분리한다.

1. 개인 앱 전달을 기존 `workspace_shares` 또는 Promotion 상태에 합치지 않는다.
2. `개인 전달`, `조직 공유`, `업무 배정`, `전사 승격`을 하나의 enum으로 만들지 않는다.
3. 앱 수락만으로 수신자의 데이터 접근 범위를 확대하지 않는다.
4. 생성 앱에 자체 로그인, 사용자 테이블, 비밀번호, JWT 발급기를 만들지 않는다.
5. 세 검토서를 서로 다른 원본 문서로 저장하지 않는다. 하나의 Decision Package에서 관점별로 렌더링한다.
6. 대외 발간은 책임 임원 승인과 법무·공시 검토가 모두 완료되기 전 실행하지 않는다.
7. 외부 캘린더·메시지·게시 시스템에 사용자 확인 없이 쓰지 않는다.
8. Jarvis가 Target Task ID를 요구하게 만들지 않는다. 회사·사용자·선택 객체 문맥을 사용한다.
9. 현재 Factory의 Workflow·WBS·HOTL·Preview·복구 기능을 이 작업에서 재설계하지 않는다.
10. 타 회사·부서·사용자의 자원은 403/409로 존재를 알리지 않고 권한 경계에서 404로 은폐한다. 인증 실패 401과 요청 형식 오류 422는 그대로 구분한다.

## 4. 목표 정보구조

```text
Global Shell
└─ 협업
   ├─ 사용자에게 전달       /collaboration/deliver/:releaseId
   ├─ 받은 앱               /collaboration/inbox
   ├─ 내 앱                 /collaboration/apps
   ├─ 의사결정 센터         /collaboration/decisions/:decisionId
   └─ 대내외 보고서 발간    /collaboration/publications/:publicationId
```

진입점은 세 곳이다.

- Release Studio: `지정 사용자에게 전달`
- Digital Twin Scenario Result: `의사결정 패키지 생성`
- Report Studio/Decision Package: `발간 준비`

## 5. 데이터 저장·감사 구조

### 5.1 운영 상태 저장소

신규 `data/collaboration.db`를 협업 워크플로우의 변경 가능한 상태 SSOT로 사용한다. 기존 `workspace.db`는 조직 공유·승격, `decision_ledger.db`는 불변 감사 이벤트 책임을 유지한다.

최소 테이블:

| 테이블 | 핵심 컬럼 | 규칙 |
|---|---|---|
| `app_deliveries` | id, enterprise_scope_id, release_id, release_version, sender_user_id, recipient_user_id, purpose, status, expires_at, manifest_snapshot, permission_snapshot, created_at, responded_at | 동일 idempotency key 중복 생성 금지 |
| `user_app_pocket` | id, enterprise_scope_id, user_id, release_id, delivery_id, display_name, status, pinned, accepted_at, last_opened_at | `(user_id, release_id, delivery_id)` 유일 |
| `decision_cases` | id, scope_id, simulation_run_id, baseline_id, scenario_id, question, package_version, evidence_snapshot, status, created_by, created_at | Snapshot 이후 원천 변경 시 자동 덮어쓰기 금지 |
| `decision_participants` | decision_case_id, user_id, role, response_status, response, responded_at | 요청자/결정자/영향부서 역할 분리 |
| `decision_meetings` | id, decision_case_id, title, schedule, channel, agenda_snapshot, status, external_ref | 외부 생성 전 명시적 확인 |
| `decision_actions` | id, decision_case_id, owner_scope_id, owner_user_id, action, due_at, status, measured_effect | 결정 계보 유지 |
| `publications` | id, scope_id, source_type, source_id, publication_type, document_version, audience, security_class, status, rendered_asset_ref, created_by | INTERNAL/EXTERNAL 분리 |
| `publication_reviews` | publication_id, review_type, reviewer_id, status, comment, reviewed_at | EXTERNAL은 EXECUTIVE와 LEGAL_DISCLOSURE 필수 |
| `publication_distributions` | publication_id, target, channel, status, external_ref, published_at | 게시 실패를 성공으로 저장 금지 |

모든 테이블은 `created_at`, `updated_at`과 필요한 낙관적 잠금 버전 또는 fingerprint를 가진다. JSON snapshot은 정렬된 canonical JSON으로 hash를 계산한다.

### 5.2 불변 감사

상태 변경이 성공한 뒤 `core/decision_ledger.py`에 다음 이벤트를 append한다.

- `APP_DELIVERY_CREATED`, `APP_DELIVERY_ACCEPTED`, `APP_DELIVERY_REJECTED`, `APP_DELIVERY_REVOKED`
- `DECISION_CASE_CREATED`, `DECISION_REVIEW_REQUESTED`, `DECISION_MEETING_REQUESTED`, `DECISION_RECORDED`, `DECISION_ACTION_CREATED`, `DECISION_EFFECT_MEASURED`
- `PUBLICATION_REVIEW_REQUESTED`, `PUBLICATION_APPROVED`, `PUBLICATION_PUBLISHED`, `PUBLICATION_CORRECTED`, `PUBLICATION_WITHDRAWN`

Ledger 실패를 숨기고 성공 응답하지 않는다. DB 상태와 Ledger의 원자성 전략은 구현 전 독립 검토 대상으로 TEAM_BOARD에 기록한다.

## 6. App-in-App 플랫폼 계약

모든 생성 릴리스는 최소 Manifest를 가진다.

```json
{
  "auth_mode": "PLATFORM_INHERITED",
  "enterprise_scope_mode": "HOST_CONTEXT",
  "capabilities": ["material_plan.read", "arrival.update"],
  "required_data_scopes": ["procurement.raw_material", "logistics.arrival"],
  "forbidden_features": ["local_login", "local_user_store", "jwt_issuer"],
  "audit_mode": "PLATFORM_LEDGER",
  "version": "1.0"
}
```

구현:

- 신규 `core/app_manifest.py`: schema, canonicalization, validation.
- 신규 `nodes/utils/platform_auth_checker.py`: 생성 파일에서 로그인 폼, 비밀번호 저장, JWT 발급, 자체 사용자 테이블 패턴을 탐지.
- `api/routes/factory_control.py` 릴리스 생성 시 Manifest snapshot 저장.
- Backend/Frontend/Reviewer 스킬에 플랫폼 인증 상속 규칙을 주입하되, 일반 업무 화면의 사용자 입력 폼까지 오탐하지 않도록 인증 목적 패턴만 차단.
- Preview iframe은 `allow-same-origin`을 사용하지 않고 parent DOM·토큰 접근을 차단한다.

## 7. 백엔드 구현 패키지

### CL-BE-01 · 저장소와 공통 모델

권장 파일:

```text
core/collaboration_store.py
core/app_delivery.py
core/decision_case.py
core/report_publication.py
api/routes/app_delivery_control.py
api/routes/decision_control.py
api/routes/publication_control.py
```

- Pydantic request/response 모델은 `extra='forbid'`.
- 공통 응답 형식은 현재 제품의 `{ "status": "success", "data": ... }`를 따른다.
- `main.py`에 세 Router를 mount한다.
- 연결은 요청 수명주기 또는 안전한 singleton 방식으로 관리하고 import 시 파괴적 migration을 실행하지 않는다.
- migration은 재실행 가능하고 기존 DB를 보존한다.

### CL-BE-02 · 앱 전달 API

```text
POST /api/v1/app-deliveries
GET  /api/v1/app-deliveries/inbox
GET  /api/v1/app-deliveries/outbox
GET  /api/v1/app-deliveries/{delivery_id}
POST /api/v1/app-deliveries/{delivery_id}/accept
POST /api/v1/app-deliveries/{delivery_id}/reject
POST /api/v1/app-deliveries/{delivery_id}/reassign-request
POST /api/v1/app-deliveries/{delivery_id}/revoke
GET  /api/v1/me/apps
PATCH /api/v1/me/apps/{pocket_id}
```

상태: `PENDING → ACCEPTED | REJECTED | EXPIRED | REVOKED`. 수락 재호출은 같은 결과를 반환하고 Pocket을 중복 생성하지 않는다. 발신자와 수신자는 같은 기업 범위에 대한 최소 read 권한이 있어야 하며, 수신자는 본인 요청만 조회한다.

### CL-BE-03 · Decision Package API

```text
POST /api/v1/simulations/{run_id}/decision-cases
GET  /api/v1/decisions/queue
GET  /api/v1/decisions/{decision_id}
POST /api/v1/decisions/{decision_id}/generate-views
POST /api/v1/decisions/{decision_id}/request-review
POST /api/v1/decisions/{decision_id}/request-meeting
POST /api/v1/decisions/{decision_id}/participant-response
POST /api/v1/decisions/{decision_id}/decide
POST /api/v1/decisions/{decision_id}/create-actions
POST /api/v1/decisions/{decision_id}/measure-effect
```

상태: `DRAFT → REVIEW_REQUESTED → MEETING_REQUESTED/IN_REVIEW → DECIDED → ACTIONED → EFFECT_MEASURED`, 중간 `CANCELLED`. `generate-views`는 데이터를 복제하지 않고 역할에 따른 projection을 반환한다. 기준선 불일치, 미검증 핵심 근거, 승인 후 snapshot 변경은 `decide`를 차단한다.

### CL-BE-04 · Publication API

```text
POST /api/v1/publications
GET  /api/v1/publications
GET  /api/v1/publications/{publication_id}
POST /api/v1/publications/{publication_id}/render
POST /api/v1/publications/{publication_id}/request-approval
POST /api/v1/publications/{publication_id}/approve
POST /api/v1/publications/{publication_id}/publish
POST /api/v1/publications/{publication_id}/correct
POST /api/v1/publications/{publication_id}/withdraw
```

상태: `DRAFT → RENDERED → REVIEW_REQUESTED → APPROVED → PUBLISHED → CORRECTED/WITHDRAWN`. EXTERNAL은 `EXECUTIVE=APPROVED`와 `LEGAL_DISCLOSURE=APPROVED`를 모두 요구한다. INTERNAL 승인만으로 EXTERNAL publish를 허용하지 않는다.

### CL-BE-05 · 알림·SSE

- 기존 Broadcaster를 사용할 경우 사용자별·회사 범위별 subscription filter를 서버에서 강제한다.
- 이벤트 payload에는 전체 문서·권한 snapshot을 싣지 않고 ID, 상태, 발생시각만 보낸다.
- 신규 이벤트: `APP_DELIVERY_RECEIVED`, `APP_DELIVERY_UPDATED`, `DECISION_REVIEW_REQUESTED`, `DECISION_UPDATED`, `PUBLICATION_REVIEW_REQUESTED`, `PUBLICATION_UPDATED`.
- 다른 사용자의 이벤트가 현재 클라이언트로 전송되는 구조라면 구현을 완료로 판정하지 않는다.

## 8. 프론트엔드 구현 패키지

### CL-FE-01 · API와 Route

```text
frontend/src/lib/collaborationApi.ts
frontend/src/features/collaboration/CollaborationHub.tsx
frontend/src/features/collaboration/routes.tsx
```

`collaborationApi.ts`는 `lib/api.ts`의 `API_BASE_URL`, `apiFetch`, 인증·회사 문맥 interceptor를 재사용한다. `localhost:8080`을 다시 선언하지 않는다.

현재 AppShell/Router 전환이 아직 완료되지 않았다면 임시로 네 개의 overlay boolean을 추가하지 않는다. 하나의 `CollaborationHub`와 URL adapter를 만들고 내부 route/state를 관리한다. 정식 Router 병합 시 adapter만 제거할 수 있어야 한다.

### CL-FE-02 · 화면 컴포넌트

```text
CollaborationModuleRail.tsx
AppDeliveryWizard.tsx
CapabilityManifestCard.tsx
IncomingAppRequestCard.tsx
SentDeliveryList.tsx
MyAppPocket.tsx
DecisionPackageViewer.tsx
RoleViewTabs.tsx
ParticipantReviewPanel.tsx
MeetingRequestPanel.tsx
PublicationPreview.tsx
PublicationGatePanel.tsx
CollaborationJarvisContext.tsx
```

승인 UI의 `238px Rail / 가변 작업면 / 300px Jarvis` 구성을 데스크톱 기준으로 사용한다. Jarvis는 페이지 전환 시 대화를 초기화하지 않고 선택 객체만 갱신한다. 업무 텍스트는 12px 미만으로 축소하지 않는다.

### CL-FE-03 · 상태 관리

- 서버 상태는 query cache 또는 feature query 계층으로 관리한다.
- Draft store에는 Wizard 입력·회의 초안·발간 초안만 둔다.
- 회사 문맥 또는 로그인 사용자가 바뀌면 이전 수신함·Pocket·결정·발간 cache를 즉시 폐기한다.
- 비동기 응답 반영 전 요청 당시 `scope_id/user_id/object_id`와 현재 문맥을 재검증한다.
- SSE 이벤트 수신 후 전체 객체를 payload에서 merge하지 않고 해당 query를 무효화한다.

## 9. 화면별 완료 조건

### 사용자에게 전달

- 실제 릴리스와 Capability Manifest가 보인다.
- 수신자 검색은 현재 기업 범위에서 권한이 있는 사용자만 반환한다.
- 최소 기능 권한과 데이터 권한 부족을 분리해 표시한다.
- 전달 결과가 보낸 요청과 Ledger에 즉시 보인다.

### 받은 앱·내 앱

- 수락·거절·회수·만료가 정확히 구분된다.
- 중복 클릭/재시도에도 Pocket이 하나만 생성된다.
- 앱 실행 시 호스트 회사 문맥과 플랫폼 역할이 전달된다.
- 다른 사용자의 요청은 URL 직접 입력으로도 404다.

### 의사결정 센터

- 세 관점이 같은 package id, baseline, evidence hash를 표시한다.
- 회의 요청과 참여자 응답이 실제 상태로 갱신된다.
- 결정 후 실행과제의 담당·기한·영향 조직이 생성된다.
- 효과측정은 결정 당시 기준선과 비교하며 미측정을 0으로 표시하지 않는다.

### 대내외 발간

- 구조화 보고서와 Decision Package를 source로 선택할 수 있다.
- 렌더 실패를 발간 준비 완료로 표시하지 않는다.
- EXTERNAL은 두 필수 검토 전 발간 API와 버튼이 모두 차단된다.
- 발간·정정·회수가 원본 계보와 Ledger에 남는다.

## 10. 테스트 요구사항

### 백엔드 단위·통합

신규 테스트 파일 권장:

```text
tests/test_app_delivery.py
tests/test_app_manifest.py
tests/test_decision_case.py
tests/test_publication_control.py
tests/test_collaboration_scope_security.py
tests/test_collaboration_events.py
```

필수 케이스:

1. 같은 idempotency key 전달·수락 재시도.
2. 타 사용자 inbox/detail/accept 404.
3. 타 기업 범위 릴리스 전달 차단.
4. 수락 후 데이터 Scope 불변.
5. 생성 앱 자체 로그인/JWT 검출.
6. 세 관점 projection의 package/evidence hash 동일.
7. 기준선 불일치·핵심 근거 미검증 결정 차단.
8. EXTERNAL 단일 승인 publish 차단, 이중 승인 성공.
9. publish adapter 실패 시 PUBLISHED 미기록.
10. Ledger·운영 DB 상태 정합성.
11. 사용자 A SSE 이벤트가 사용자 B에게 전달되지 않음.

### 프론트엔드·브라우저

1. 1280×720과 1440×900에서 가로 overflow 0.
2. keyboard만으로 Wizard, 수락/거절, 역할 탭, 승인 게이트 수행.
3. 회사/사용자 전환 후 이전 데이터 잔류 0.
4. inbox 수락 후 Pocket 갱신 및 새로고침 유지.
5. Decision 역할 탭 전환 시 package id 불변.
6. 대외 발간 버튼의 서버·화면 이중 차단.
7. 모든 화면에서 Jarvis 문맥이 현재 객체로 갱신되고 Task ID를 요구하지 않음.
8. 기존 Factory Release, Workspace Share/Promotion, Twin, Reports 회귀 없음.

## 11. 구현 순서와 커밋 경계

| 순서 | 작업 | 독립 완료 조건 |
|---:|---|---|
| 1 | CL-0 App-in-App Manifest·정적 게이트 | 릴리스에 Manifest 저장, 자체 인증 생성 차단 테스트 |
| 2 | CL-1 개인 전달·수락·Pocket BE/FE | inbox/outbox/pocket E2E와 권한 회귀 통과 |
| 3 | CL-2 Decision Package·회의·실행 | 단일 Package 3관점과 상태 전이 통과 |
| 4 | CL-3 Publication Control | 대내외 게이트·발간 실패·정정/회수 통과 |
| 5 | CL-4 Jarvis·알림·Lineage 통합 | 사용자별 이벤트 격리와 객체 문맥 통과 |
| 6 | CL-5 카나리 | 기존 기능 회귀 + 실제 회사 문맥 과업 1회 |

각 단계는 별도 커밋이 가능해야 한다. 2단계 완료 전 3~4단계의 화면만 가짜 데이터로 먼저 병합하지 않는다.

## 12. 검토 필요 지점

작업은 자체검토 후 계속 진행하되 다음은 통합 전 다른 팀원 1명의 독립 검토를 TEAM_BOARD에 요청한다.

- `collaboration.db` schema/migration과 Ledger 원자성.
- 앱 전달의 사용자·기업 범위 권한 판정과 404 은폐.
- Decision Package snapshot/fingerprint와 결정 차단 규칙.
- 대외 발간 redaction, 책임자·법무/공시 승인, 외부 adapter.
- 사용자별 SSE 격리.

검토 대기 때문에 무관한 다음 패키지의 로컬 구현을 멈추지는 않지만, 해당 위험 변경은 검토 전 기본 브랜치에 통합하지 않는다.

## 13. Claude Code 착수 보고 형식

착수 시 `.agents/TEAM_BOARD.md`에 다음을 남긴다.

- 작업 ID와 담당 패키지.
- 확인한 기준 문서·프로토타입.
- 실제 수정 예정 파일.
- 기존 기능 재사용 범위와 신규 구현 범위.
- 권한·DB·외부 쓰기 영향.
- 첫 완료 조건과 테스트 명령.

구현 중 발견한 문서 불일치는 임의로 UX를 바꾸지 말고, 코드 증거·대안·영향과 함께 보드에 기록한다. 프로토타입 승인 여부를 다시 묻지 않는다.

## 14. 최종 Definition of Done

- 정적 샘플이 아니라 실제 릴리스·사용자·회사·시뮬레이션·보고서 데이터로 동작한다.
- 두 폐쇄루프의 상태와 계보가 API·DB·Ledger·UI에서 일치한다.
- 개인 전달/조직 공유/업무 배정/전사 승격이 분리된다.
- 앱 인증 상속과 데이터 권한 비확대가 테스트로 고정된다.
- Decision Package 세 관점이 동일 근거 snapshot을 사용한다.
- 대외 발간 이중 게이트와 명시적 사용자 실행이 서버에서 강제된다.
- Jarvis가 Task ID 없이 객체·회사 문맥으로 지원한다.
- 신규 테스트, 기존 관련 회귀, `frontend npm run build`, 1280/1440 브라우저 과업이 통과한다.
- TEAM_BOARD에 구현 증거·미해결 위험·커밋·푸시 상태가 기록된다.
