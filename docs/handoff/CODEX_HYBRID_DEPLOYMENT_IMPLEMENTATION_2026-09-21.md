# 하이브리드 배포관리 V1 구현 인계서

> **전체 계획 최신 정정 — 2026-09-21 / Codex:** 배포 R1 API/보안 규격은 유지한다. 제품·DB·배포 전체 작업/진척은 [TRIAL-GAP-R2](../roadmap/OPERATIONAL_TRIAL_GAP_PLAN.md)의 **18/53=34.0%**로 대체됐다. OPS-P1은 C02(Codex), 업무DB 첫 실경로는 P03(Claude)이며 상세 Gap과 출구를 함께 따른다. 과거52.5%는 현재 전체 지표가 아니다.

작성: Codex · 2026-09-21 KST
상태: R1 설계 보완 인계 / 지정6건 독립 재검토 범위 한정 PASS / 제품 구현·실배포 미실행.
수신·착수 여부: 공유 문서 준비만 완료. Claude가 이 문서를 읽거나 시작했다고 주장하지 않는다.

담당 정정(2026-09-21 12:50 KST): 최신 사용자 결정으로 OPS-P1은 **Codex 직접 구현**이다. Claude는 DB-1 실제 PG 첫 경로를 우선하고 DEP 완료 보완을 반복하지 않는다. 최신 통합 배치/진척/예상 시간은 [통합 현황](INTEGRATED_TRIAL_DELIVERY_STATUS_2026-09-21.md)을 따른다. 아래 계약 규격은 유지하며, 과거 팀보드의 Claude OPS-P1 배치는 대체한다. 새 구현 착수 자체를 이 정정으로 주장하지 않는다.

## 1. 첫 지시: 진행 중 DB 작업을 중단하지 않는다

이번 사용자 요청은 **독립 검토 지적을 반영해 배포시스템 설계를 보완**하는 것이다. 현재 Claude의 DB/보안 보완과 별개로 관리툴 구현 규격을 확정한다.
업무 PostgreSQL 이관을 관리 UI 완성까지 기다리게 하지 않는다. 반대로 DB 어댑터의 SQLite 시험을 실제 PG/무중단 수용으로 인정하지 않는다.

읽는 순서:

1. [상세 설계 정본](../design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md): 특히 §0, §2, §3, §6, §7, §8, §14.
2. [API 정본](../design/contracts/deployment-control-v1.openapi.json): 요청/응답·상태 enum.
3. [배포 준비 패킷](CODEX_DEPLOYMENT_PREP_PACKET_2026-09-21.md): DEP-01~10 및 Z-01~10.
4. [무중단 상위 계획](../roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md): 규모·인프라·비용·업무 런타임 선행.
5. 최신 CLAUDE_DB0_DELTA_AND_FIRST_SLICE 및 CLAUDE_DB1_FIRST_ADAPTER 인계: 실제 PG 검증 여부를 먼저 확인.

설계서가 확정한 사항을 다시 선택지 토론으로 돌리지 않는다. 다만 보안·API의 명백한 모순은 증거와 수정안을 제시해 정본을 먼저 고친다.
전체 인정 진척 **21/40=52.5%**는 유지한다. 이 설계의 완료와 제품/운영화 진척은 다른 지표다.

## 2. 결정 요약: 구현자가 바꾸면 안 되는 12가지

1. 사설 웹 Console + 별도 Control API + GitHub Actions + NCP 제한 agent.
2. 메뉴 3개: 운영 현황 / 버전·배포 / 배포 이력.
3. 플랫폼 artifact와 업무앱 library release를 분리.
4. GitHub App 사용자 로그인, 작성자만 자기 user token dispatch. plan.actor_id=token/run/OIDC numeric ID. 설치 token은 제한된 백그라운드 읽기와 claim 직전 현재 권한 조회.
5. trial 최종 승인은 GitHub에서만. 자체 approve/reject API 금지.
6. private 저장소에서 승인자 분리·bypass 차단 실측 전 trial 비활성.
7. workflow tag/SHA, artifact digest, config/migration/policy digest는 서로 구분해 불변 plan에 결속.
8. POST timeout은 UNKNOWN, 자동 재POST 금지. 환경 잠금+단일 claim이 중복 배포 차단.
9. observe 영수증 수락 시 실행권 RELEASED, 이후 GitHub success와 실제 serving/readiness 대조600초. lease와 대조 시간을 분리.
10. 취소는 실행권 획득 전만. rollback은 새 계획이고 DB 되감기가 아님.
11. Codex는 로컬 소스→PR 경로. 별도 Codex API·운영 서버 직접 수정 없음.
12. 구현 폴더는 ops_control/, ops_console/, deploy/agent/. 업무 App.tsx·core/db·core.paths에 관리툴이 의존하지 않으며 관리 DB fallback/startup DDL 금지. 업무 노드 readiness는 core/에 둘 수 있음.

## 3. 우선순위와 작업 패키지

예상 시간은 **1인 집중 구현 공수의 잠정 범위**다. PG 선행·외부 승인·클라우드 생성·유료 플랜 대기는 제외한다. 첫 30분 checkpoint에서 수정할 수 있다.
패키지 시간의 단순 합을 배포 확정일로 말하지 않는다. 병행 가능한 준비와 실제 외부 수용을 나눈다.

| ID | 순서·담당 | 산출물 / 완료 조건 | 예상 |
|---|---|---|---|
| OPS-P0 | 독립 설계 검토, Codex와 다른 검토자 | §4 질문 답변, P0/P1 차단 없음, 문서 모순 해소 | 30~60분 |
| OPS-P1 | CI 담당, DB 진행과 병행 | 배포 allowlist·Linux artifact/manifest·runtime lock·CI 초안. 로컬 dry-run, 비밀/DB 미포함 | 0.5~1일 |
| OPS-P2 | 관리 backend 담당 | 독립 package/DB migration·API형·상태 전이·fake GitHub/agent·멱등/잠금 시험 | 1~2일 |
| OPS-P3 | UI 담당, OPS-P2 계약 기반 | 3메뉴·배포 준비/상세·stale/UNKNOWN/권한/오류, fake API 브라우저 수용 | 1~1.5일 |
| OPS-P4 | GitHub/인프라 담당 | App auth·보호 검증·user dispatch·run 대조·OIDC claim·agent dry-run | 1~2일 |
| OPS-P5 | 인프라+backend, 업무 선행 후 | NCP LB adapter·Blue/Green·migration/파일/worker/SSE 경계 실측 | 1~2일 + 선행 작업 |
| OPS-P6 | 독립 수용·운영 담당 | 권한/중복/장애/복구·동시10·Z-01~10·운영 runbook | 1~2일 |
| OPS-P7 | 사용자/운영 책임자 승인 | 비용·자료·GitHub 보호·복구 증거 확인 후 trial 최초 배포 | 승인·이관 창에 따름 |

총 구현/수용 공수는 대략 **6~11 인일 + 업무 런타임 선행/외부 대기**로 본다. 기존 CI/배포 코드 재사용 실측에 따라 좁힌다. “설계가 끝났으니 하루 안에 무중단 운영”이라고 보고하지 않는다.
OPS-P1/OPS-P2에서 실제 GitHub 쓰기 없이 진행할 수 있다. OPS-P4의 App 등록·workflow push·실제 dispatch, OPS-P5 자원 생성/자료 이관은 해당 실행 승인 이후만 한다.
UI가 늦으면 엔진의 검증된 GitHub 수동 실행 경로로 staging 수용을 먼저 진행할 수 있다. trial의 동일 보호·불변 plan·claim 검증은 생략하지 않는다.

### 3.1 다음 30분의 정확한 행동 (R1 정본 재검토 후)

- 0~5분: git status와 작업자 소유 파일 확인, 진행 중 DB 코드와 분리 선언.
- 5~15분: §11 IR-01~10 및 R1 재검토 판정을 읽고 담당 파일/차단 조건을 고정. GitHub 보호 기능/미확정 값을 차단 목록에 표기.
- 15~25분: OPS-P1의 배포 파일 허용목록과 artifact manifest fixture를 설계에서 추출. 아직 원격 push/빌드/과금 없음.
- 25~30분: **읽은 파일·작성한 파일·완료 기준·막힌 것·다음 예상**으로 보고. 토큰/테스트 건수만 나열하지 않는다.
- 독립 검토가 끝나지 않으면 안전한 읽기·명세·fake 환경 준비까지만 하고 실제 쓰기 기능을 활성화하지 않는다.

## 4. 독립 검토 질문과 판정

| 질문 | PASS 기준 |
|---|---|
| 사람 A의 요청을 bot 요청으로 바꾸지 않는가? | user token과 numeric ID 일치, 최종 승인자는 GitHub 증거 |
| 승인된 버전을 다른 버전으로 바꿀 수 있는가? | artifact/workflow/config/migration/policy/generation 불변, 변경 시 새 승인 |
| GitHub POST 응답이 사라지면 두 번 배포되는가? | UNKNOWN 재송신 금지, 취소/claim 경쟁과 run 단일 결속 |
| workflow가 success인데 서버가 다르면? | 성공 판정 금지, 실제 관측과 FINALIZING/복구 상태 |
| DB/작업/SSE가 남은 상태에서 구 노드를 죽이는가? | NN-1/lease/fence/replay/drain 증거 없으면 차단 |
| 새로운 UI가 DB 완료를 늦추거나 기존 업무 인증을 깨는가? | 별도 package/DB/역할, 현업 App 수정 없음 |

검토 결과는 REVIEW_PASS/CHANGES_REQUESTED 및 근거로 기록한다. 자기 검토를 독립 검토로 부르지 않는다.
보호 설정이나 LB API를 확인할 수 없으면 해당 외부 기능 NOT_READY로 남기되 OPS-P1/OPS-P2를 계속한다. 시험을 통과시키려 보호/관문을 제거하지 않는다.

## 5. 수용 시험 행렬

모든 행은 초기 **NOT_RUN**이다. 아래는 실제 결과가 아니라 구현자가 수행할 수용 계약이다.
기록: test ID / source commit / config digest / 환경 / 조작 / 기대 / 실측 / 증거 파일 / RUN-PASS·RUN-FAIL·NOT_RUN.
시간·PASS 건수만으로 기능 수용을 대체하지 않는다. mock·실제 PG·실GitHub·실NCP·실사용자를 구분한다.

| ID | 재현 | 기대 / 수용 단계 |
|---|---|---|
| A01 | state 누락/재사용·잘못된 PKCE/callback | 로그인 거절, 세션/토큰 미발급 / OPS-P2,OPS-P4 |
| A02 | viewer가 plan/dispatch/cancel POST | 서버403, 외부 호출0 / OPS-P2 |
| A03 | 미허용 환경 plan 조회, 존재/비존재 비교 | 같은404 계약 / OPS-P2 |
| A04 | user 권한 회수 후 idempotency 재시도 | 캐시 응답 전 권한 거절 / OPS-P2,OPS-P4 |
| A05 | CSRF/Origin 누락·위조 | 외부 쓰기0 / OPS-P2 |
| A06 | user token 대신 app bot으로 요청하는 변이 | 신원 시험 실패 / OPS-P4 |
| A07 | private 승인 기능 부재/self-review/bypass 가능 | trial 차단·사유 / OPS-P4 |
| A08 | 요청자 본인 승인·다른 사람이 승인 거절 | GitHub 보호, agent 변경0 / OPS-P4 |
| A09 | 틀린 issuer/aud/repo ID/env/workflow SHA/attempt | claim 거절 / OPS-P2,OPS-P4 |
| A10 | 승인 후 artifact/config/policy 바꾸기 | STALE_PLAN, 새 plan/승인 요구 / OPS-P2 |
| C01 | 동일 key·본문 2회/동시 요청 | 동일 plan/결과, dispatch1 / OPS-P2 |
| C02 | 같은 key 다른 본문 |409, 원요청 보존 / OPS-P2 |
| C03 | 두 탭·두 Control 인스턴스 다른 계획 동시 dispatch | 하나만 환경 잠금, 나머지409 / 실제 PG |
| C04 | POST 처리 후 응답 유실·worker crash | UNKNOWN, 자동 재POST0 / OPS-P2,OPS-P4 |
| C05 | 중복 run + 같은 plan, rerun attempt2 | agent 실행권1, 나머지 거절 / OPS-P4 |
| C06 | cancel과 claim 순서 각각 경쟁 | cancel승→실행0, claim승→취소409 / 실제 PG |
| C07 | 다른 계획이 실행 중인 READY/BLOCKED plan 취소 | 다른 계획 lock 유지 / OPS-P2 |
| C08 | lease 만료·old fence·다른 agent env | 신규 단계0, 잠금 유지 / OPS-P2,OPS-P5 |
| C09 | 역순 단계/변조 영수증/같은 단계 재전송 | 역순·변조 거절, 정상 중복은 동일 결과 / OPS-P2 |
| C10 | Control/DB 복구 뒤 과거 outbox | 자동 외부 재POST0, 실태 대조 / OPS-P6 |
| U01 | fresh→stale, GH green+서버 old | 정상/성공으로 표시 안 함 / OPS-P3 |
| U02 | 버튼 두 번·새로고침·중복 mount·POST timeout | 동일 key/요청 조회, 자동 새 POST 없음 / OPS-P3 |
| U03 | trial 배포 확인창·승인 링크·취소 한계 | 환경/DB영향/신원 명시, 자체 승인 없음 / OPS-P3 |
| U04 | 키보드/1280px/권한없음/빈목록/오류 | 초점 복원·행동/사유 명확 / OPS-P3 |
| U05 | 성공·요청 접수·복구 필요·자료 없음 | 문구·행동 구분 / OPS-P3 |
| U06 | “수정 요청 복사” 내용 | source/plan/증거만, token/실자료 없음 / OPS-P3 |
| E01 | package에서 DB/.env/library/user file 탐침 | 허용목록 검사 실패, publish 금지 / OPS-P1 |
| E02 | artifact/hash/provenance/서명 신뢰 변조 | release 부적격, agent 설치0 / OPS-P1,OPS-P4 |
| E03 | staging와 trial artifact 재빌드/불일치 | 승격 거절 / OPS-P4 |
| E04 | candidate readiness 실패, LB unchanged | 구 서비스 유지·증거 후 FAILED / OPS-P5 |
| E05 | migration expand 뒤 신버전 실패 | 구 앱 read/write 가능, DB down 없음 / OPS-P5 |
| E06 | LB API timeout/부분 전환·agent crash | RECOVERY_REQUIRED, 자동 잠금 해제0 / OPS-P5 |
| E07 | GitHub failure지만 새 버전이 서비스 중 | 단순 실패/재배포 금지, 복구 필요 / OPS-P5 |
| E08 | stale/역순/중복 agent 관측 | 최신값 보존·freshness 판정 / OPS-P2,OPS-P5 |
| E09 | runtime 인터넷 차단하고 배포 | 준비된 artifact로 실행, 현장 build/install download0 / OPS-P5 |
| E10 | 관리 서버를 중지 | 업무 서비스 계속, 신규 배포 중단 / OPS-P6 |
| O01 | 앱 세션/티켓·SSE·job·static N-1 | Z-01~10 개별 실측 연결 / OPS-P6 |
| O02 | 운영10명 혼합 입력/조회/SSE 중 배포 | 승인된 쓰기/작업 유실·중복0, 로그인 유지 / OPS-P6 |
| O03 | 복귀 계획 후 신규 업무 입력 대사 | 코드만 복귀, DB 입력 유지 / OPS-P6 |
| O04 | 관리 DB 및 업무 DB/파일 backup restore | 복구 격리, 결과 대사, RPO/RTO 실측 / OPS-P6 |
| O05 | audit 쓰기 실패·secret 탐침 | 외부 변경 시작0, 로그/응답 비밀0 / OPS-P2,OPS-P6 |
| O06 | 최초 trial 준비판정 | 미충족 gate0, 구매/자료/운영 승인 기록 / OPS-P7 |

핵심 변이는 A09·C04·C06·U01·E02 각각 1종을 우선한다. 모든 UI 문구에 변이 시험을 늘리지 않는다.
시험 효율: 순수 domain/contract → 필요한 실제 PG 경쟁 → fake UI 수직 흐름 → GitHub staging → NCP 무중단 순. 매 문구 변경마다 전체 서버 suite를 돌리지 않는다. 권한/DB/배포 경계 변경 시 관련 회귀와 단계 종료 통합 검사를 수행한다.

## 6. 업무 DB 담당과 주고받을 계약

DB 담당에게 관리 UI 구현을 요청하지 않는다. 다음만 증거 링크로 받는다.

| 받아야 할 것 | 배포 쪽 사용 |
|---|---|
| 실제 PostgreSQL auth/context/SSE ticket 원자성 | 다른 노드로 전환해도 로그인/소모 계약 유지 |
| migration ledger·startup DDL/seed 분리 | 배포 중 단일 migration owner |
| 업무 read/write schema epoch 범위 | NN-1 사전검사·rollback 적격 |
| durable job ownership/fence/recovery | drain120초 뒤에도 작업 유실 방지 |
| event outbox/cursor/replay/context 경계 | SSE 재연결·늦은 이벤트 차단 |
| library/projects/output/DB 경로 외부화 | artifact 교체와 업무 자료 분리 |
| 백업/복구 실제 결과 | 초기 이관·일상 배포·재해복구 구분 |

현재 읽은 Claude 문서는 첫 adapter와 SQLite 시험, PG 미실행을 보고한다. 그 이후 변경이 있으면 최신 인계와 시험으로 갱신한다. 이전 보고만으로 “PG 완료” 또는 “아직 안 됨”을 고정하지 않는다.

## 7. 실제 운영 전 runbook 목록

OPS-P6 완료 시 아래를 각각 실행 가능한 문서로 제출한다. 이번 상세 설계 단계에서 실행했다고 표시하지 않는다.

- 최초 설치: private network/VPN, DB 역할/키, App 등록, 권한·보호 proof, exact runtime.
- 일상 배포: source→trusted artifact→동일 digest staging→trial plan→GitHub 승인→실태 확인.
- DISPATCH_UNKNOWN: 재POST 금지, run 식별, 안전 취소/새 plan, 단일 claim 증명.
- RECOVERY_REQUIRED: 운영 lock 보존, LB/slot/schema/job 대조, 이중 확인, 제한 CLI 복구 감사.
- 코드 복귀: 현재 schema 호환 확인, 이전 성공 release 새 plan, 신규 DB 입력 대사.
- DB 재해복구: 별도 승인·쓰기 통제·DB와 object 기준점·복원·대사·재개.
- 자격증명 회전/퇴사자 회수: App key/user session/agent cert/CI bucket key, 미완료 plan 처리.
- 관리 DB 복구: 과거 outbox 재실행 차단, 실제 운영과의 재동기화.
- 비상 접근: GitHub/Control 장애 중 담당자·권한·명령 allowlist·실행 후 감사. 앱 개발자의 임의 SSH 금지.

## 8. 보고 형식

매 패키지 종료 시 아래만 간결하게 보고한다.

```text
전체 제품 인정치: 21/40=52.5% (변동 근거 없으면 유지)
이번 패키지: DEP-Pn 또는 OPS-Pn — 목표 / 실제 완료 / 미완료
화면·기능 변화: 사용자가 할 수 있게 된 행동 1~3개
증거: mock / 실제 PG / GitHub / NCP / 실사용 구분
운영 배포 차단: 이름과 개수, 다음 해제 대상
다음 작업: 구체 산출물 + 예상 시간 범위
변경 파일/타 세션 충돌: 있음/없음
외부 변경/비용/자료 이동: 수행 여부와 승인 근거
```

목표는 많은 검사를 만드는 것이 아니라 안전하게 실제 배포 가능한 수직 흐름을 닫는 것이다. 이미 삭제 예정인 구 통제실의 일반 UI 보완으로 다시 돌아가지 않는다.

## 9. 최초 작성 시 확인 범위 (역사 기록)

Codex가 수행: 기존 전략/배포 계획/Claude DB 인계 읽기, GitHub 공식 API·인증·승인·OIDC 문서 확인, 상세 설계 및 OpenAPI 작성, 문서 내부 계약 점검.
미수행: 제품 구현, 실제 PostgreSQL 시험, GitHub App/Environment 생성, workflow 원격 실행, NCP 자원 생성, 실제 자료 이관, 커밋/푸시, 독립 검토.
설계 파일만 검증한 것을 “API 작동 확인”이나 “무중단 배포 완료”라고 보고하지 않는다.

## 10. 최초 설계 문서 검증 기록 — 2026-09-21 (R1 이전)

- JSON 문법·로컬 참조·operationId 중복·경로 파라미터·required/property 일치: PASS.
- 경로16개 / 동작18개 / schema28개 / 로컬 참조159개 / 상태15개.
- 수용 시험42개 ID 중복 없음. **42개 모두 정의 단계이며 제품 실행은 NOT_RUN**.
- Markdown 내부 파일 링크·코드 블록·한국어 문서 언어 점검: PASS.
- OpenAPI의 x-plan-digest-fixture: 18필드 canonical JSON과 SHA-256 재계산 일치.
- git diff --check(변경 문서 한정): 오류0. 기존 TEAM_BOARD의 LF→CRLF 경고는 줄끝 정책 안내이며 전체 보드를 정규화하지 않았음.
- 검증은 경량 구조/상호 일관성 검사다. 완전한 OpenAPI 표준 validator·생성 클라이언트 빌드·HTTP 런타임 시험을 수행한 것은 아니다. OPS-P2에서 수행한다.
- 두 번째 관점 점검 보완: 불변 계획에서 변동 preflight 제외, detached manifest로 hash 자기참조 방지, 최초 설치 예외 제한, 승인 전 job summary가 존재한다는 가정 제거.
- 당시 독립 검토 판정: 대기 → 이후 CHANGES_REQUESTED. R1 보완·재검토는 §11 및 별도 보완 인계에서 기록한다. 아래 원래 수치를 R1 실측으로 재사용하지 않는다.


## 11. R1 변경 지도와 추가 수용 계약

읽기 추가: [최초 독립 검토](CODEX_HYBRID_DEPLOYMENT_INDEPENDENT_REVIEW_2026-09-21.md), [DEP-P1/DEP-P2 회신](CODEX_REVIEW_DEP_P1_P2_2026-09-21_B.md), [R1 보완·검증 인계](CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md).

### 11.1 작업 번호와 의존성 — INT-01/02

| 기존 준비 작업 | 신규 작업과 연결 | 완료로 넘겨짚지 않을 것 |
|---|---|---|
| DEP-P1 파일 선별·색인·CI 초안 | OPS-P1이 선별기를 재사용하고 archive/runtime lock/provenance/출처/정식 manifest를 완성 | 파일 색인=release 적격 아님, CI 원격 미실행을 PASS로 적지 않음 |
| DEP-P2 두 슬롯·노드 기동/readiness | OPS-P4 agent 문맥 API 소비 → OPS-P5 OS 슬롯/실제 관측으로 연결 | 7상태 원장=OPS-P2 backend 아님, 표식/역할 문자열=서빙 실측 아님 |
| DEP-P3 전환·복귀 준비 | OPS-P5 LB/cleanup/drain/reconcile 구현에 연결 | update.sh in-place 갱신=무중단 아님, rollback=과거 계획 상태 복원 아님 |
| 업무 DB 이관 트랙 | OPS-P2의 관리 DB와 별개; DEP-P2/OPS-P5는 실제 backend/NN-1 증거 수신 | 업무 DB 시험을 관리 DB 동시성 또는 실제 PG 수용으로 합산 금지 |

Claude에게 전달한 DEP 보완은 해당 회신 범위에서 진행한다. 본 설계가 기존 제품/DB 파일의 소유권을 가져오지 않는다. OPS-P2는 별도 관리 package/PG migration/domain/API를 담당하며, 구 원장 정교화 뒤 폐기하는 작업을 하지 않는다.

### 11.2 추가 수용 사례 — 모두 정의만, 제품 NOT_RUN

| ID | 변경/재현 | 기대 | 담당 |
|---|---|---|---|
| IR-01 | A 작성/B dispatch, user token/run/OIDC actor 각각 불일치, 정상 응답·UNKNOWN 재결속 | 작성자만 실행, 불일치403/증거 거절, agent0. 자기 명의 새 계획 정상 대조 | OPS-P2/OPS-P4 |
| IR-02 | 승인 대기 후 repo write 회수·operator 제거·명시 회수·권한 조회 장애; 다른 OIDC/승인은 정상 | 최초 claim0,403/503. 세션 만료만으로는 자동 회수하지 않는 양성 대조 | OPS-P2/OPS-P4 |
| IR-03 | mTLS execution-context 정상·다른 환경·old fence·만료·종료·선행누락·Control 장애 | 정상 다음 단계1개, no-store/최대5초·lease 이내. 거절 시 신규 부작용0 | OPS-P2/OPS-P4 |
| IR-04 | observe 수락/runner 종료 뒤 GH 결과90초 지연,600초 초과, 응답 유실 재시도 | RELEASED로 추가 변경0,90초 뒤 SUCCEEDED1회. 기한 초과/실제 불일치는 recovery와 lock 유지 | OPS-P2/OPS-P5 |
| IR-05 | 새 digest 첫 staging/증거 전 trial/성공 후 같은 digest trial/다른 digest/증거 만료·정책 불일치 | staging 순환 없음, trial 증거 강제. bootstrap·rollback에도 같은 환경별 규칙 | OPS-P1/OPS-P2/OPS-P4 |
| IR-06 | candidate 실패→CLEANUP_ONLY→cleanup 재전송, 소유권 불명·active slot·lease 만료 | 후보만 정리, old/DB 보존 후 FAILED. 불명은 recovery, active/LB/down 변경0 | OPS-P2/OPS-P5 |
| IR-07 | 환경 현재 포인터·결과·audit 갱신 중 둘째 SQL 실패, 동시 완료, 잘못된 복귀 대상 | 실제 PG transaction 원자성, 부분 commit0, 종료 이력 불변·성공1회 | OPS-P2 |
| IR-08 | 알 수 없는 check·필수 검사 누락·빈 필요 공유 경로·로컬 표식만·가짜 started·잘못된 backend | 준비도/승격 차단, 실제 관측 양성 대조만 통과 | DEP-P2/OPS-P5 |
| IR-09 | 관리 DB 설정 없음/업무 data 기본 fallback/startup 생성자, OPS 산출물 혼입 | 기동/설치 차단, 업무 data 접근0·DDL0, 업무 package에 ops_control0 | OPS-P1/OPS-P2 |
| IR-10 | 미분류 starter asset·file index만으로 eligible·수동 PASS 주입 | publish/적격 차단. 출처/완전 manifest 검증 후에만 artifact 적격 | DEP-P1/OPS-P1 |

기존42개에 추가10개, 총52개 수용 정의다. 스키마 검증/정적 검토 통과는 이52개 제품 시험의 RUN-PASS가 아니다. 기존 C08은 EXECUTING/CLEANUP_ONLY lease 유실과 RELEASED의 대조 대기를 구분하도록 수정해서 실행한다. E04는 cleanup_candidate 영수증과 NN-1/기존 서비스 증거를 요구한다.

### 11.3 실제 구현 순서

1. 독립 재검토의 미해소 P1 확인. 외부 미확정 값은 그대로 비활성.
2. OPS-P1: 기존 file index를 full release 계약으로 연결. 업무 DB 작업과 병행.
3. OPS-P2: 먼저 불변 plan/실제 요청자/관리 PG migration → env lock/claim/context → RELEASED/cleanup/reconcile 계약과 IR-01~07,09.
4. OPS-P3: can_dispatch·execution_mode·finalization_deadline 및 환경별 preflight를 그대로 표시. 자체 승인·강제 취소 기능은 만들지 않는다.
5. DEP-P2/OPS-P4~5: 실제 노드 관측/PG/공유 저장소 → GitHub staging → 승인 보호/실LB 검증. 기존 fixture 통과만으로 연결을 활성화하지 않는다.

첫 착수 단위는30분 checkpoint이며 전체 공수6~11인일 잠정은 유지한다. 위 위험 보완 자체가 실제 운영 자원·외부 실행 승인으로 바뀌지 않는다.
