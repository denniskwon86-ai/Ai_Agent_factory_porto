# GitHub 기반 배포관리 시스템 V1 상세 설계

작성: Codex · 2026-09-21 KST
상태: R1 보완 완료 / 지정6건 독립 재검토 범위 한정 PASS / 제품 구현·외부 설정·실배포 미실행.
사용자 승인 범위: GitHub를 실행 엔진으로 사용하고 자체 접근·관리 UI를 연결하는 하이브리드 방식의 상세 설계.
이 문서의 MUST/금지는 구현 수용 기준이다. 미정 구성값은 비워 둔 채 실행을 차단하며 추정값으로 운영하지 않는다.

## 0. 정본·범위·충돌 해결

- 제품 방향: Product Bible → 제품 전략 → 최종 완성 실행계획 G7. 사용자 명시 배포 요청으로 G7 운영화 준비를 수행한다.
- 규모·예산·무중단 정의: [09-20 상위 계획](../roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md) 유지.
- **관리 UI·GitHub·Codex 연결의 구현 정본은 본 문서**다. 상위 계획의 초기 Codex API 자동 실행 구상은 V1에서 제외한다. CS 설치형과 별도 AI API 연결도 V1 범위가 아니다.
- [배포 준비 패킷](../handoff/CODEX_DEPLOYMENT_PREP_PACKET_2026-09-21.md)의 DEP-01~10·Z-01~10은 계속 유효하다. 기존 단일 서버 update.sh를 무중단 CD로 재사용하지 않는다.
- API 필드 정본: [OpenAPI](contracts/deployment-control-v1.openapi.json). 동작·권한·상태 정본: 본 문서. 모순 발견 시 구현자가 임의 선택하지 않고 명세 PR로 해소한다.
- 구현 순서·수용 시험: [구현 인계서](../handoff/CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md).
- 새 플랫폼 배포 시스템이지, 업무용 생성 앱이나 기존 Studio 릴리스 관리 화면의 개편이 아니다. 플랫폼 배포 artifact와 업무앱 library release를 혼용하지 않는다.
- 문서 작성은 전체 완료 인정치를 변경하지 않는다: **21/40 = 52.5%**. 구현 담당 Claude의 진행 중 DB·제품 작업은 보존한다.

R1(2026-09-21): SEC-01/02·EXE-01~04·INT-01/02와 DEP-P1/P2 검토 경계를 반영한다. 최초 독립 검토는 당시 판정으로 보존한다. 수정 후 별도 Codex 검토자2명의 지정 범위 재검토 PASS와 구조 검증은 [R1 인계](../handoff/CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md)에 기록하며 전체 보안 인증·운영 승인이 아니다. 기존 서버 준비 패키지는 DEP-P1~3, 본 관리 시스템 패키지는 OPS-P0~7이다.

### 0.1 확정 경계

| 구분 | V1 포함 | V1 제외 |
|---|---|---|
| UI | 사설 웹 관리 콘솔, 3개 주 메뉴, 요청·조회·이력 | CS 설치 패키지, 자체 코드 편집기, GitHub 복제품 |
| 실행 | GitHub Actions + NCP 제한 실행기, Blue/Green | 임의 셸 실행, UI가 운영 서버에 직접 SSH |
| 승인 | GitHub Environment의 사람 승인 | 자체 승인 API, 공용 봇 대리 승인 |
| Codex | 개발 PC의 기존 Codex → 변경 브랜치 → PR | 별도 모델 API/토큰 저장, 운영 소스 직접 수정 |
| 데이터 | 배포 메타데이터·요약 증거 | 업무 DB 내용, 실제 업무 첨부, 비밀키를 Git/CI로 복사 |
| 서비스 | afs-platform 하나, staging/trial 둘 | 고객별 다중 제품 배포, 멀티클라우드, 관리툴 자체 자동 배포 |

### 0.2 규모와 비용

1단계 30명/동시10, 2단계 100명/동시30, 3단계 200명/동시50 이상을 유지한다. 관리 콘솔 동시 운영자 목표는 5명이며 업무 동시사용 목표와 다르다.
월 상한 150/300/600만원은 기존 **권고값**이지 구매 승인·확정 견적이 아니다. GitHub private 저장소 승인 기능 요금제, 관리 서버·배포 runner·백업·관측 비용을 품목 견적에 포함한다. LLM/Codex 사용료는 별도다.

## 1. 구조와 배치

```text
개발 PC Codex/Claude → PR → GitHub hosted CI → 불변 artifact / 검증 증거
                                         │
운영자 → VPN → 자체 Console → Control API ├→ GitHub dispatch (사용자 신원)
                          │              └→ GitHub Environment (사람 승인)
                          │                         │
                          ├→ Ops PostgreSQL         ▼
                          └← 실행 claim/관측 ← NCP 전용 deploy runner
                                               │ 제한된 고정 명령
                                               ▼
                                         환경별 deploy agent
                                               │
                                 NCP LB → App Blue / App Green
                                               │
                                 업무 PG / 외부 파일 / 내구성 작업·이벤트
```

| 구성요소 | 책임 / 금지 |
|---|---|
| ops_console | 화면·확인·상태 조회. GitHub/클라우드 토큰과 배포 로직 없음 |
| ops_control | 인증·역할, 계획 불변성, 요청/중복 방지, GitHub 대조, 감사. 업무 main.py/core.auth import 금지 |
| GitHub Actions | CI, 검증된 빌드, 승인 대기, 검토 가능한 고정 배포 workflow |
| deploy runner | 보호된 workflow만 실행. PR/외부 fork/사용자 소스 빌드 실행 금지 |
| deploy agent | 환경 allowlist 내 고정 단계 실행, 로컬 journal, 실측/복구. 임의 경로·명령·URL 입력 없음 |
| Ops PostgreSQL | 관리 상태 전용 DB afs_ops. 업무 DB와 사용자/스키마/접속권한 분리 |
| 업무 런타임 | 정상 서비스·공유 세션·작업 lease·outbox·재연결·외부 파일. 콘솔 장애와 독립 |

네트워크: UI/API 동일 origin HTTPS, VPN/접근 프록시 뒤. 인터넷 inbound webhook은 V1에 만들지 않는다. Control API는 GitHub를 outbound polling한다.
NCP deploy runner는 보호된 전용 runner group/저장소만 사용한다. 운영 앱과 관리 API의 OS 계정·자격증명을 공유하지 않는다. 가능하면 별도 VM에 놓고 해당 비용을 견적에 포함한다. PR CI는 GitHub hosted runner로 분리한다.
agent는 mTLS 내부 통신만 허용한다. GitHub OIDC는 Control API와의 인증에 사용하며 **NCP가 GitHub OIDC를 직접 지원한다고 가정하지 않는다**.
Control 서버 장애로 이미 운영 중인 앱을 중지하지 않는다. agent/runner의 불확실 상태에서는 새 트래픽 변경을 중지한다.

### 1.1 구현 폴더·기술 선택

```text
ops_control/                 # 독립 FastAPI 서비스, Pydantic 요청/응답
  api/                      # public_ops, auth, internal_execution
  domain/                   # plan, transitions, permissions, preflight
  integrations/github/      # OAuth, dispatch, reconcile, protections
  persistence/              # psycopg3, 명시적 SQL, 트랜잭션
  migrations/               # 번호 기반 forward SQL + checksum ledger
  tests/
ops_console/                # React + TypeScript + Vite, 독립 entry
  src/{pages,components,api}
  tests/
deploy/agent/               # Python, 고정 단계 adapter + durable journal
deploy/manifests/           # schema·허용목록, 비밀정보 없는 정책
.github/workflows/          # CI/build/deploy, 도입 시 보호 검토
```

업무 frontend/src/App.tsx와 core/db 어댑터를 관리툴 기반으로 수정/재사용하지 않는다. 스타일 토큰·아이콘은 복사 출처를 기록하여 재사용할 수 있으나 업무 store/인증에 의존하지 않는다.
의존성은 독립 lock을 둔다. 런타임 정확한 patch 버전·Linux ABI·Node/Python 버전은 첫 CI 패키지에서 검증 후 manifest에 고정한다. 기존 업무 런타임을 임의 업그레이드하지 않는다. 프런트 생성 클라이언트는 OpenAPI에서 생성하고 수작업 타입 사본을 만들지 않는다.

## 2. 신원·권한·승인

### 2.1 로그인

- GitHub App web application flow + 일회용 state + PKCE S256. callback URI 완전 일치, 외부 return URL 금지.
- 서버가 code를 교환하고 /user 및 대상 installation/repository 접근을 확인한다. 변경 가능한 login 문자열이 아니라 GitHub numeric user ID로 역할을 결속한다.
- 세션은 랜덤 opaque ID의 해시를 DB에 저장한다. cookie Secure/HttpOnly/SameSite=Lax, idle30분/absolute8시간. 프런트 localStorage에 토큰 금지.
- state 유효5분/일회용. API 쓰기는 CSRF token + Origin 검증. 로그아웃 시 서버 세션/보관 user token 폐기.
- user token은 서버 암호화 저장, 키는 DB 밖 secret 저장소. V1은 자동 장기 갱신하지 않고 만료 시 재로그인. private key/client secret도 서버 전용.
- 사용자 대신 요청하는 dispatch는 **사용자 access token**을 쓴다. 백그라운드 읽기는 repository 한정 installation token을 필요한 read 권한만으로 발급한다. GitHub 공식 권고와 사용자 권한 교집합에 따른 선택이다. [사용자 토큰](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app), [App 권고](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app).
- UI 조회 시 repository 접근 재검증 캐시는 최대5분. dispatch/cancel은 매번 권한을 재검증하며 확인 불가 시 외부 쓰기하지 않는다.

**V1 요청자 정책:** 계획 작성자만 dispatch할 수 있다. `session.user_id = plan.actor_id = 사용 user token의 /user.id = GitHub run.actor.id = OIDC.actor_id`를 동일 numeric ID로 결속한다. 다른 operator의 대신 실행은403 ACCESS_DENIED이며 자기 명의 새 계획을 생성해야 한다. 정상 dispatch 응답과 DISPATCH_UNKNOWN 재대조 모두 run actor를 확인한다. 환경 operator의 실행 전 취소는 허용하되 취소자의 ID를 별도 감사에 기록하고 계획 작성자를 바꾸지 않는다. GitHub 승인 제외 대상도 이 실제 요청자다.

최초 claim 및 기존 ACTIVE claim의 획득 재시도는 승인 대기 전 세션 캐시를 사용하지 않는다. 서버는 installation의 read-only 권한으로 요청자의 **현재 repository write 이상 접근**, 현재 환경 operator, 명시적 배포 권한 회수 여부를 확인한다. GitHub 권한 응답의 user.id도 plan.actor_id와 일치해야 한다. numeric ID에 결속된 login을 사용하고 이름 변경/조회 실패 시 추정하지 않는다. claim commit 기준 외부 권한 확인은10초 이내이며, 로컬 grant/revocation version을 environment→plan 잠금 안에서 재확인한다. 회수는403 ACCESS_DENIED, 조회 장애는503 DEPENDENCY_UNAVAILABLE, claim/agent 변경0이다.
로그인 idle/absolute 만료 및 일반 로그아웃 자체를 명시적 배포 권한 회수로 취급하지 않는다. 이미 GitHub에 접수된 요청은 위 독립 권한 조회로 판정한다. 운영자의 명시 회수는 ops_principal_revocations에 기록한다. 이미 실행 중인 배포를 권한 조회 장애 때문에 임의 kill하는 정책은 V1 범위 밖이며, lease/fence와 비상 runbook으로 통제한다. [공식 사용자 권한 조회](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user).

### 2.2 역할

| 행위 | viewer | operator | GitHub reviewer | 정책 관리자 |
|---|---:|---:|---:|---:|
| 허용 환경 조회/이력 | O | O | 콘솔 역할 별도 | 콘솔 역할 별도 |
| 계획 생성/사전 확인 | - | O | 별도 operator 필요 | 별도 operator 필요 |
| staging/trial 요청·실행 전 취소 | - | O | 별도 operator 필요 | 별도 operator 필요 |
| trial 최종 승인 | - | - | GitHub에서만 O | 자동 권한 없음 |
| 역할/환경/보호 정책 변경 | - | - | - | 검토된 설정 PR/운영 절차 |

역할은 서버의 승인된 설정에서 user ID별 환경 목록과 함께 로드한다. UI에서 역할 편집 기능을 만들지 않는다.
업무 시스템 manager/admin과 콘솔 operator를 자동 매핑하지 않는다.
GitHub App 등록 권한: Metadata read, Contents read, Actions write(사용자 dispatch), Deployments read, Administration read(환경 보호 조회). Organization 관리, Secrets write, Contents write, Deployments write 금지. installation background token은 Actions read로 축소한다.
Administration read를 제공할 수 없으면 보호 설정 자동 확인 불가로 trial을 차단한다. 고권한 토큰을 몰래 대체하지 않는다.

### 2.3 승인 강제와 요금제

trial job에는 GitHub Environment required reviewers, prevent self-review, 보호 ref 제한, 허용되는 경우 관리자 bypass 금지를 적용한다. V1 정책상 요청자 본인 승인과 bypass를 허용하지 않으므로 해당 강제가 불가능하면 trial 기능을 활성화하지 않는다.
private repository의 승인 기능 가용성은 GitHub 요금제에 따라 다르다. 실제 계정의 설정·API·시험으로 확인한다. 지원되지 않으면 요금제/승인 구조를 별도 승인받고 설계를 개정한다. dispatch 버튼을 승인으로 대신하지 않는다. [공식 환경 제약](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
UI의 버튼은 **“GitHub에서 승인 검토”** 링크이며 자체 승인/거절 endpoint가 없다. GitHub run-name은 입력에 존재하는 환경·plan ID·digest 앞12자리로 고정한다. 승인자는 사설 Console의 해당 불변 plan에서 전체 digest·변경·DB 영향·복구 조건을 확인한 뒤 GitHub에서 승인한다. 검토 권한이 없으면 승인하지 않는다.
승인 대기 job은 아직 실행되지 않으므로 그 job의 summary가 승인 전에 존재한다고 가정하지 않는다. 실행 후 summary에 전체 plan 정보와 결과를 남긴다. 승인 전 별도 고권한 prep job을 편의상 추가하지 않는다.
승인 대기 중 artifact/config/workflow/schema 계획을 변경하지 않는다. 변경은 새 plan + 새 run + 새 승인이다.
staging은 합성 데이터만 사용하며 operator 요청으로 실행 가능하다. trial은 승인 대기 중 운영 권한/agent 실행권을 받지 않는다.

## 3. 릴리스·불변 계획·증거의 신원

### 3.1 release

release는 업무앱 릴리스가 아니라 afs-platform 배포 artifact다.
필수 manifest: format_version=1, release_id(UUID), source_commit(40자리 SHA), source_repo_id, build_run_id, build_run_attempt, build_workflow_sha, target_os/arch, python/node 정확 버전, artifact_sha256, file_index_sha256, dependency_lock_sha256, sbom_sha256, provenance_ref, schema_read_min/max, schema_write_min/max, config_schema_version, created_at.
schema 범위는 정수 증가 epoch다. 마이그레이션 파일 checksum 집합은 별도 migration_plan_digest에 결속한다. 대응 안 되는 앱은 READY가 될 수 없다.
CI는 Linux용 tar.zst와 검증된 wheelhouse·frontend/dist·vendor asset을 빌드한다. 실행 서버에서 git pull/npm build/인터넷 pip install 하지 않는다. allowlist 포함 파일만 패키징하고 DB·.env·library·사용자 파일·로그를 제외한다.
동일 artifact digest를 staging에서 시험한 뒤 trial에 승격한다. trial용으로 다시 빌드하지 않는다.
저장 위치는 비공개 Object Storage의 digest 키이며 CI 증명(허용된 workflow/source/run)과 내용 hash를 검증한다. locator는 서버 정책에서 유도하고 클라이언트 입력 URL을 fetch하지 않는다.
manifest/provenance는 archive 밖의 detached sidecar다. archive가 자신의 hash를 포함하는 자기 참조 구조를 만들지 않는다.
signed provenance 검증기·신뢰 workflow/key 정책이 설정되지 않으면 release eligible=false다. 사람이 체크박스로 “검증 완료”를 만드는 API는 없다.

`Release.eligible`은 **환경 공통 artifact 적격성만** 뜻한다. staging 성공/환경 권한/현재 schema/backup/LB 준비를 포함하지 않는다. 환경별 실행 가능 여부의 정본은 `Plan.preflight`다. UI는 eligible=true를 곧바로 “trial 배포 가능”으로 표시하지 않는다. 카탈로그 수집 시 provenance/파일 출처가 미확인인 자산은 artifact 적격성도 차단한다.

| 조건 | staging DEPLOY/ROLLBACK | trial DEPLOY/ROLLBACK |
|---|---|---|
| trusted artifact·출처·lock·hash | 필수 | 필수 |
| 현재 환경/DB/파일/역할·호환·복구 정책 | 필수 | 필수 |
| 같은 digest의 이전 staging 성공 | **불필요** — 최초 staging 실행 가능 | 필수: SUCCEEDED 계획과 실제 관측 증거에 결속 |
| 같은 config 호환 정책·migration digest·schema 범위의 staging 증거 | 실행 후 생성 | 정책이 허용한 호환 범위에서 검증, 불일치/오래됨 차단 |
| GitHub 승인 | operator 요청, 보호 workflow | 요청자 외 사람 승인·보호 증거 필수 |

staging 증거 최대 유효기간은 환경 정책의 필수 구성값이며 policy_digest에 결속한다. 미설정은 trial 차단이다. 다른 artifact digest에는 재사용 불가하다. bootstrap도 이 환경별 조건을 그대로 따른다.

### 3.2 plan

계획 생성 입력은 environment, release_id, operation(DEPLOY/ROLLBACK), reason뿐이다. 서버가 아래를 스냅샷한다.

- plan_id, environment, release_id/artifact_sha256/source_commit
- workflow_ref + 정확 workflow_sha, config_digest, migration_plan_digest
- expected_environment_generation, 현재 serving digest, observed_schema_epoch
- 승인 정책 version/digest, 사전검사 결과/시각, 작성자 numeric ID
- rollback인 경우 복구 대상이 실제 이전 성공 release인지, 현재 DB/설정과의 호환 판정

plan_digest는 다음 **18개 필드만** 담은 불변 payload의 UTF-8 JSON SHA-256이다: plan_id, environment, release_id, operation, artifact_sha256, source_commit, workflow_ref, workflow_sha, config_digest, migration_plan_digest, policy_digest, policy_version, expected_environment_generation, current_serving_digest, observed_schema_epoch, actor_id, format_version(1), service(afs-platform).
규칙: 키 ASCII 사전순, 공백/마지막 줄바꿈 없음, 문자열 Unicode 그대로(escape는 JSON 필수 escape만), 숫자는 정수만, null 명시. plan_id는 API의 id에서 매핑한다. reason·표시 문구·state·revision·preflight 결과/시각은 제외한다. 초기 검사와 재검사는 ops_preflights에 추가하며 불변 payload를 덮어쓰지 않는다.
관측 schema가 없으면 null인 BLOCKED 계획만 가능하다. 필수 환경 설정 자체가 없으면 계획 생성은503이다. 재검증에서 schema 차이가 사전 승인된 migration 경로를 벗어나면 STALE_PLAN이다.
계획은 생성 뒤 수정 API가 없다. READY 이후 설정/환경이 바뀌면 STALE_PLAN이고 새 계획을 만든다.
사전검사 유효10분. dispatch 직전, claim 직전 다시 검사한다. 승인 때문에 유효 시간이 지났다면 같은 불변 입력을 재검증할 수 있으나 digest/환경 generation이 바뀌면 재승인이 필요한 새 계획이다.

### 3.3 진실의 원천

| 데이터 | 권위 원천 | UI 표시 |
|---|---|---|
| 의도·요청자·중복·계획 | Ops DB | 요청한 버전 |
| run·승인·job 결과 | GitHub 조회 | GitHub 실행 상태/확인 시각 |
| serving digest·LB·schema·readiness | 인증된 agent 실측 | 실제 서비스 버전/관측 시각 |
| 업무 정상 여부 | 배포 smoke + 서비스 지표 | 업무 검사 결과, 검증 범위 |
| 성공 이력 | 당시 3종 증거를 결속한 완료 기록 | 당시 완료 사실 |

이후 장애가 생겨도 과거 SUCCEEDED를 FAILED로 덮어쓰지 않는다. 현재 환경 HEALTHY/DEGRADED/UNKNOWN과 drift를 따로 표시한다.
GitHub success만으로 SUCCEEDED를 기록할 수 없다. 양쪽 보고가 다르면 FINALIZING 또는 RECOVERY_REQUIRED다.

## 4. 화면 상세

### 4.1 공통

좌측 메뉴는 **운영 현황 / 버전·배포 / 배포 이력** 3개. 상단 환경(staging/trial), 로그인 사용자, 마지막 동기화 시각.
데스크톱 1280px 이상 2열, 이하 1열. 색상에만 의존하지 않는 상태명·아이콘, 키보드 접근/초점 복귀, 최소14px 본문.
기본 화면에는 업무 용어, SHA/epoch/원본 JSON은 “기술 정보” 접힘 영역. 퍼센트 진행바 대신 현재 단계·완료 단계·막힌 사유를 표시한다.
프런트 polling은5초(활성 상세)/30초(현황); 숨은 탭60초. API 캐시를 읽을 뿐 화면마다 GitHub를 호출하지 않는다. 중복 mount로 POST하지 않는다.
인증 없음→로그인, 권한 없음→접근 불가, 자료 없음→아직 배포 없음, 오래된 정보→마지막 확인 시각과 재시도, 외부 장애→UNKNOWN. UNKNOWN을 정상이나 0건으로 표현하지 않는다.

### 4.2 화면·경로·수용

| 화면 | 경로 | 필수 내용 | 주 행동 |
|---|---|---|---|
| 운영 현황 | /ops | 환경별 실제 버전·건강·schema·최근 요청·미완료 복구 | 환경 상세, 배포 준비 |
| 환경 상세 | /ops/environments/:environment | 요청/실제 버전 비교, Blue/Green, 관측 freshness, 차단 사유 | 버전 선택, 복구 후보 보기 |
| 버전 목록/상세 | /ops/releases 및 /:id | commit·변경 요약·CI·staging 증거·DB호환·eligible | 이 버전으로 배포 준비 |
| 배포 준비 | /ops/deployments/new | 환경/버전 선택 → 서버 preflight → 영향 확인 | staging 배포 요청 / trial 승인 요청 |
| 배포 상세 | /ops/deployments/:id | 요청자·단계·GitHub 승인 링크·실제 관측·감사·결과 | 실행 전 요청 취소, GitHub 상세 |
| 이력 | /ops/history | 환경/기간/결과 필터·시간·신원·release·복구 관계 | 상세 열기 |

현황 배치:
```text
[운영 현황]                          [trial ▾] [사용자]
[실제 서비스 버전 / 건강 / 14초 전 확인] [다음 후보 / 검사 결과]
[진행 중 요청: 승인 대기 → GitHub에서 승인 검토]
[최근 배포 5건: 요청자 / 버전 / 결과 / 시각]
```

배포 확인창은 환경 이름, 현재→목표 버전, 실제자료 여부, DB 변경, 복구 가능/불가 사유, 승인 방식, 요청 사유를 표시한다. trial은 환경명 trial을 직접 입력해야 요청 버튼 활성화. 이는 오조작 방지일 뿐 승인 대체가 아니다.
제출 중 버튼 비활성, 동일 Idempotency-Key 유지. timeout이면 “접수 여부 확인 중”과 조회 버튼을 표시하고 새 요청을 자동 생성하지 않는다.
결과 문구: “요청을 접수했습니다” ≠ “배포가 완료됐습니다”. 성공은 serving/readiness/업무 검사까지 닫힌 후 표시.
다른 사람이 작성한 계획에는 “작성자만 요청할 수 있습니다 / 내 명의로 새 계획 만들기”를 표시한다. RELEASED claim으로 FINALIZING 중이면 “서버 변경 완료 · GitHub 결과 확인 중”과 대조 기한을 표시하며 실행 취소/재실행 버튼을 만들지 않는다. CLEANUP_ONLY는 “후보 정리 중 · 기존 서비스 확인”으로 표시하고 성공으로 표시하지 않는다.
ROLLBACK은 “이전 버전으로 복귀 요청”. **DB가 이전 데이터로 돌아가는 것이 아님**을 확인창에 고정한다.
배포 시작 후 강제 취소 버튼 없음. RECOVERY_REQUIRED는 일반 재배포/복귀 비활성 + 운영 절차 링크. read-only 상세/이력은 유지한다.

## 5. API 계약과 공통 오류

구체 schema와 HTTP 코드는 동반 OpenAPI 정본을 따른다. /ops/api/v1은 세션 API, /internal/ops/v1은 OIDC runner 및 mTLS agent API. public CORS 허용 없음.

| API | 의미 |
|---|---|
| GET /session | 사용자/환경 권한/CSRF, 토큰 원문 없음 |
| GET /environments, /environments/{environment} | cache 기반 실제 관측/차단 |
| GET /releases, /releases/{release_id} | trusted CI 카탈로그 |
| POST /plans | 불변 계획 생성 + preflight, 실행 안 함 |
| GET /plans/{plan_id}, GET /plans | 상태/이력 |
| POST /plans/{plan_id}/dispatch | 환경 잠금+outbox를 원자 기록 후202 |
| POST /plans/{plan_id}/cancel | claim 이전만 취소, 외부 실행 강제 중단 아님 |
| GET /plans/{plan_id}/events | 정제된 audit/단계, cursor pagination |
| POST internal /claims | 승인된 run의 단일 실행권 획득 |
| POST internal /claims/{claim_id}/heartbeat | 현재 lease 연장 |
| GET internal /claims/{claim_id}/execution-context | 환경 결속 mTLS agent만 불변 계획·현재 실행권·허용 단계 조회; 쓰기 권한 발급/연장 아님 |
| POST internal /claims/{claim_id}/steps/{step}/complete | 검증된 단계 영수증 |
| POST internal /environments/{environment}/observations | agent 현재 실측 |

Console 계획 쓰기 공통: Idempotency-Key UUID, X-CSRF-Token, Origin, Content-Type. 로그아웃은 CSRF/Origin만 요구하며 반복 호출은 추가 효과가 없다. 내부 API는 CSRF 대신 OIDC 또는 mTLS, 별도 principal 정책과 OpenAPI의 개별 헤더를 적용한다.
If-Match는 plan revision의 strong ETag(따옴표 있는 정수)로 dispatch/cancel에 필수. 재시도 시 동일 key/동일 body에는 최초 결과를 반환하되 **현재 인증·환경 접근 검사를 먼저** 한다. 같은 key 다른 body는409.
인증401, 역할403, 보이지 않는/없는 객체404 동일, 입력422, 중복/상태충돌409, revision412, 선행조건428, 의존 시스템 장애503. 에러는 code/message/request_id/retryable/details(비밀정보 제외).
오류 code: AUTH_REQUIRED, ACCESS_DENIED, NOT_FOUND, VALIDATION_ERROR, ENV_BUSY, STALE_PLAN, IDEMPOTENCY_CONFLICT, UNSAFE_CANCEL, PRECONDITION_FAILED, REQUIRED_PRECONDITION, DEPENDENCY_UNAVAILABLE, APPROVAL_UNAVAILABLE, DISPATCH_UNKNOWN, LEASE_LOST, INVALID_EVIDENCE.
에러가 나도 audit 실패를 숨기지 않는다. 로컬 감사 기록을 보장하지 못하면 외부 쓰기를 시작하지 않는다.
리스트 limit 기본20/최대100, 불투명 cursor, 정렬 created_at DESC + id DESC. reason은1~500자 plain text, 렌더 시 escape. 임의 HTML/URL 링크 금지.

## 6. 상태 기계·중복·취소

### 6.1 상태 전이

| 현재 → 다음 | 조건/수행 주체 |
|---|---|
| 생성 → READY 또는 BLOCKED | 서버 preflight. BLOCKED 계획은 고치지 않고 새 계획 |
| READY → DISPATCHING | 작성자인 operator, CAS revision, 잠금·outbox·audit 한 DB transaction |
| DISPATCHING → QUEUED | GitHub 응답 run_id 확인 |
| DISPATCHING → DISPATCH_UNKNOWN | timeout/응답 유실/성공인지 불확실 |
| DISPATCHING → FAILED | 명백한 dispatch 거절, run 없음이 확인됨 |
| DISPATCH_UNKNOWN → QUEUED | 식별된 정확 run을 GET 또는 검증된 claim으로 결속 |
| QUEUED → APPROVAL_PENDING | trial GitHub 승인 대기 확인 |
| QUEUED/APPROVAL_PENDING → PREPARING | 승인 후 claim 검증 + environment fence 획득 |
| PREPARING → VERIFYING | inactive slot 설치·비파괴 migration·기동 영수증 |
| VERIFYING → PROMOTING | readiness·합성 smoke·N/N-1 검사 통과 |
| PROMOTING → DRAINING | LB 실제 전환 확인 |
| DRAINING → FINALIZING | 이전 slot 유입 차단/진행 중 요청·작업 handoff 확인 |
| FINALIZING → SUCCEEDED | GitHub success + 신선한 target 실측 + 완료 증거 |
| READY/BLOCKED/DISPATCHING/DISPATCH_UNKNOWN/QUEUED/APPROVAL_PENDING → CANCELLED | claim 미획득을 DB lock으로 확인, 이후 claim 거절 |
| QUEUED/APPROVAL_PENDING → FAILED | 거절/실행 전 GitHub 실패·취소 확인 |
| PREPARING/VERIFYING → FAILED | CLEANUP_ONLY에서 cleanup_candidate 성공·기존 서비스 불변·DB NN-1 안전을 실측 입증; claim 종료와 잠금 해제 원자 기록 |
| PREPARING 이후 비종료 상태 → RECOVERY_REQUIRED | 외부 변경 불명/전환·드레인 실패, 또는 아직 EXECUTING/CLEANUP_ONLY인 claim lease 유실 |
| FINALIZING(RELEASED) → FINALIZING | GitHub 조회 지연: 변경권 없이 읽기 대조 계속, lease 만료를 장애로 처리하지 않음 |
| FINALIZING(RELEASED) → RECOVERY_REQUIRED | 증거 불일치/GitHub failure 또는 별도 대조 기한600초 경과 |

모든 종료 상태는 역사적으로 불변이다. RECOVERY_REQUIRED는 **운영 잠금이 남는 종료 판정**이다. 자동으로 READY로 돌리거나 새 계획을 통과시키지 않는다.
rollback은 이전 성공 release를 지정한 **새 ROLLBACK 계획**이며 같은 승인·검증·상태 흐름을 탄다. DB down migration/backup restore는 실행하지 않는다.
RECOVERY_REQUIRED 해소는 V1 별도 runbook/이중 확인: 실제 LB/두 slot/schema/job 소유·감사 확인 → 승인된 복구 조치 → 새 recovery observation → 관리 CLI의 reconcile-close(명시 env/plan/fence/증거, 권한 제한). 일반 UI API로 우회하지 않는다. 기존 plan 결과는 유지하고 recovery audit를 추가한다.

### 6.2 중복 방지와 불확실한 dispatch

- DB 환경 row SELECT FOR UPDATE 후 active_plan_id가 비어 있는지 확인한다. outbox unique(plan_id, action=dispatch). 여러 서버/탭도 한 건만 접수한다.
- 워커는 사용자 토큰/현재 권한을 확인하고 outbox를 claim한다. 외부 POST를 보냈을 수 있는 crash 지점은 DISPATCH_UNKNOWN이다. 외부 API가 멱등성을 보장한다고 가정하지 않는다.
- GitHub REST API version=2026-03-10 고정. 현재 문서의 dispatch200은 workflow_run_id/URL을 돌려준다. ref는 branch/tag이며 source commit SHA와 동일 개념이 아니다. [공식 dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).
- workflow는 보호된 tag 이름을 사용하고 정확 SHA를 plan에 저장/claim에서 대조한다. tag 이동·삭제는 보호하고 이동이 관측되면 차단한다.
- inputs는 plan_id, plan_digest, environment 3개뿐. workflow는 이를 셸 문자열로 보간하지 않고 엄격 schema 확인 후 API로 조회한다.
- run-name의 plan_id는 탐색 단서일 뿐 신뢰 증거가 아니다. repository/workflow/ref/run_attempt/actor_id/OIDC/plan digest가 모두 맞아야 결속한다.
- timeout/알 수 없는204/5xx를 받은 dispatch는 자동 재POST 금지. read-only reconciliation만 수행한다. 15분 지나도 미확인이면 경고+잠금 유지. 취소 후 새 계획은 가능하지만 구 plan의 모든 claim은 거절된다.
- 중복 run이 생겨도 DB CAS로 한 run만 claim 가능. 다른 run은 no-op 오류로 끝내고 agent에 접근하지 못한다. GitHub rerun(run_attempt>1)은 V1 거절; 새 plan으로 재요청한다.
- GitHub concurrency는 보조 방어, cancel-in-progress=false. 큐 보존·단일 실행 보장은 Ops DB가 맡는다.
- idempotency 기록 보관7일, audit365일 기본 제안. 보안/운영 승인 전 자동 삭제 작업 활성화 금지.

### 6.3 취소 경쟁

cancel과 claim은 같은 plan/environment row lock 순서를 사용한다. cancel 선승→plan취소/잠금해제/뒤늦은 claim차단. claim 선승→409 UNSAFE_CANCEL.
취소 뒤 GitHub job이 대기/실행 중으로 보일 수 있으므로 UI는 “요청 취소됨 / GitHub 종료 확인 중”을 구분한다. agent 실행권이 없는 job은 실제 변경을 할 수 없다.
이미 실행 중인 run을 API로 강제 취소하여 실패를 rollback으로 오인하지 않는다.

## 7. GitHub workflow와 실행권

### 7.1 세 workflow

| workflow | 입력/출력 | 권한/경계 |
|---|---|---|
| ci.yml | PR → lint/type/target tests/secret 검사 | hosted runner, production secret 없음, fork 읽기 |
| release.yml | 보호된 source commit → artifact+manifest+SBOM+provenance | build-only, 운영 DB/agent 접근 없음 |
| deploy.yml | plan_id/digest/environment → 승인 → claim → 고정 단계 | 전용 runner, id-token:write, contents:read, trial Environment |

Actions 및 reusable workflow는 full commit SHA pin. 코드/배포 policy 변경은 CODEOWNERS+branch/ruleset 검토 대상으로 설정한다. 관리자 설정 변경도 감사/재검증 대상이다.
수동 dispatch를 위한 workflow 정의는 repository default branch에도 존재해야 한다. 실제 실행 ref는 승인된 보호 tag이며 두 설정을 혼동하지 않는다. default branch/tag 이름은 실제 저장소에서 확인한 구성값을 사용한다.
처음 릴리스·워크플로·App 등록·환경 생성은 실제 외부 변경 승인을 받은 구현 단계에서 수행한다. 본 설계가 이를 실행한 것은 아니다.

### 7.2 OIDC claim 검증

Control API가 GitHub JWKS 서명, issuer=https://token.actions.githubusercontent.com, 정확 aud(구성값), exp/nbf(시계오차 최대30초)를 검증한다.
repository_id/repository_owner_id, environment, 보호 ref, workflow_ref, workflow_sha, run_id, run_attempt=1, actor_id=plan.actor_id, event_name=workflow_dispatch를 allowlist/plan과 대조한다. 이름만 맞는 다른 저장소는 거절한다. OIDC sha는 workflow 실행 commit이므로 배포 artifact source_commit으로 오인하지 않는다.
OIDC jti는 최초 claim에 단일 사용으로 기록한다. 후속 heartbeat/step은 갱신된 OIDC와 결속된 claim_id/run/fence로 검증한다. claim token을 외부 영구 자격증명으로 만들지 않는다.
GitHub Environment 보호가 실제로 적용된 job인지 승인/설정 evidence를 조회하고 claim 직전 보호 설정 freshness≤60초를 요구한다. 누락·불일치·조회 장애는 실패. 지원 claim의 세부는 [공식 OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)를 따른다.
공격자가 저장소 최고 관리자와 클라우드 root를 모두 장악한 상황까지 이 UI로 방어한다고 주장하지 않는다. 권한 분리·MFA·관리자 변경 감사를 별도 적용한다.

### 7.3 fence·agent

environment generation은 환경 변경을 나타내는 단조 정수, execution fence는 claim마다 증가하는 정수다. 별개로 관리한다.
claim mode는 EXECUTING/CLEANUP_ONLY/RELEASED/EXPIRED다. EXECUTING/CLEANUP_ONLY의 lease60초, heartbeat10초. lease 만료 시 EXPIRED로 바꾸어 추가 변경을 금지하지만 **논리적 환경 잠금은 자동 해제하지 않는다**. RELEASED/EXPIRED는 되살리지 않는다.
agent는 plan/fence/step별 durable journal과 단일 OS lock을 갖는다. 같은 단계 재전송은 기록된 결과를 반환한다.
명령은 install, migrate_expand, start_candidate, verify, switch_traffic, drain, observe와 제한 보상 cleanup_candidate 고정 enum. plan 외 임의 command/path/target/SQL을 받지 않는다.
mTLS runner identity와 env allowlist, Control의 live claim 확인 후 수행한다. 한 환경 한 agent coordinator가 LB 변경을 직렬화한다. 재기동/이중 agent 시 불명 상태를 인계받아 즉시 재실행하지 않고 LB 실제 상태를 먼저 대조한다.
NCP LB API의 원자성/지연·target group 조작은 OPS-P4에서 조사하고 OPS-P5에서 실제 SKU/API adapter contract test로 고정한다. 확인 전 dry-run만 가능하며 자동 전환을 활성화하지 않는다. API timeout은 재호출 성공으로 가정하지 않는다.

### 7.4 agent 실행 문맥 조회 — EXE-01

`GET /internal/ops/v1/claims/{claim_id}/execution-context?plan_id=UUID&fence=N`는 AgentMtls 전용이다. 인증서의 사전 등록 agent_id/환경을 서버가 유도하며 caller가 보낸 agent_id를 신뢰하지 않는다. 다른 환경은 같은404, old fence/종료·만료 claim/해제된 환경 lock은409, 의존 시스템 장애는503이다. runner OIDC/사용자 cookie만으로는401이다.

응답은 plan/claim/fence/agent/environment, immutable plan, target_slot/previous_active_slot, 현재 mode, 현재 allowed_steps(정확히 다음1개), checked_at, valid_until, lease_expires_at다. slot은 claim 시 인증 관측에서 결정하여 claim에 고정하고 runner가 지정하지 않는다. `valid_until=min(checked_at+5초, lease_expires_at)`; 서버 시각 기준이다. 응답은 `Cache-Control: no-store`. 조회는 claim을 연장하거나 새 실행권을 발급하지 않는다.

agent는 요청한 step이 allowed_steps에 없으면409, 응답/신원/관측 불명은 변경 전 거절한다. 각 단계의 최초 부작용 직전 및 긴 단계의 후속 부작용 전 다시 조회한다. 일단 발행된 네트워크/DB 작업을 강제로 취소할 수 있다는 뜻은 아니다. 만료 직전에 시작한 외부 작업 결과는 journal에 남겨 재대조하고, 새 변경·맹목 재실행을 금지한다. 중복 step은 이미 기록된 receipt를 읽을 수 있지만 새 실행은 안 한다. OS lock·단계 journal을 함께 사용하고 agent에 Ops DB 직접 접속·runner OIDC 전달·사용자 token 공유를 금지한다.

### 7.5 실행 종료와 완료 대조 — EXE-02

drain 뒤 FINALIZING으로 들어가도 observe60초 측정 중에는 EXECUTING/heartbeat를 유지한다. **observe 성공 영수증을 Control이 독립 검증하여 수락할 때**, step 기록·claim RELEASED/finished_at·allowed_steps=[]·finalization_started_at/deadline(+600초)·audit를 같은 transaction으로 기록한다. StepResult에 claim_mode와 finalization_deadline을 반환한다. runner는 해당 수락 확인 후 heartbeat를 멈추고 정상 종료한다. 응답 유실 시 동일 영수증 재전송은 기록된 결과만 반환하며 종료 claim을 연장하지 않는다.

RELEASED 이후 신규 step/heartbeat/context 취득은409. 이미 수락한 동일 complete 재시도만 유효한 동일 run/fence 인증 후 읽기 멱등 응답을 허용한다. read-only agent 관측 업로드는 실행 claim과 독립적으로 계속한다. Control은 원래 run/attempt의 GitHub success와 freshness45초 이내 실제 target/LB/schema/smoke 증거를 대조한다. 90초 GitHub 지연은 FINALIZING 유지 후 정상 SUCCEEDED가 가능하다. deadline600초까지 대조 불가 또는 실측 불일치는 RECOVERY_REQUIRED이며 자동 잠금 해제하지 않는다. 기한 이후 늦은 성공도 종료 이력을 바꾸지 않고 복구 audit로 남긴다.

SUCCEEDED 기록은 environment→plan→claim 잠금, generation/active_plan/target 재대조 후 결과·generation+1·현재 serving 포인터·잠금 해제·audit를 한 transaction으로 기록한다. crash/retry로 두 성공·두 serving 포인터를 만들지 않는다. DB transaction은 외부 LB를 되감지 않는다. commit 결과 불명은 읽기 대조하고 외부 전환을 다시 실행하지 않는다.

## 8. 무중단 실행·DB 경계

### 8.1 고정 순서

1. dispatch 사전검사: 환경 fresh, active plan 없음, 백업/복구 시험 정책 유효, §3.1의 환경별 조건 충족. 동일 digest staging 통과는 trial에만 필수. claim에서는 active_plan이 자기 plan인지 확인한다.
2. claim 후 재검사: 승인된 불변 대상/현재 schema/generation/현재 두 slot의 호환.
3. inactive slot에 digest 검증 후 설치. runtime secret/DB/파일은 release 폴더 외부.
4. migration owner 단일 실행: additive expand만, migration ledger checksum·DB advisory lock·idempotent restart. 앱 startup DDL/seed 금지.
5. candidate 기동. liveness와 readiness 분리. readiness는 실제 설정된 DB backend/필수 저장소·queue·schema호환·필수 설정을 확인한다. LB용은 사설 접근 제한+최소200/503 응답, 관리용 상세 진단은 인증된 내부 계약으로 분리한다. 상세 신원·경로·비밀을 무인증 본문에 넣지 않는다.
6. candidate에 합성 사용자/자료로 인증·문맥·쓰기 영수증·SSE·파일·job smoke. 실제 업무 데이터로 테스트 쓰기 금지.
7. V1은 **canary가 아닌 Blue/Green**. candidate 3회 연속 readiness(5초 간격), 고정 smoke 통과 후 LB를 candidate로 전환.
8. LB 실측/요청 응답 release digest 확인. old slot은 새 유입을 끊고 기존 요청을 drain.
9. 최대 drain120초 기본. SSE는 종료 후 cursor 기반 새 노드 재연결. 장기 제작 job은 durable lease/fencing으로 이관하며 웹 요청 타임아웃으로 kill하지 않는다.
10. 새로운 요청30건 이상/60초 관측, 5xx0 및 핵심 업무 smoke 통과, old slot 새 유입0 확인. 저트래픽은 합성 probe로 채운다. 이는 V1 수용 기준이지 가용성 SLA 약속이 아니다.
11. observe 영수증 수락으로 실행 claim 종료, 이후 읽기 전용 GitHub 완료·실측 대조 후 SUCCEEDED/generation+1/active_plan 해제를 원자 기록(§7.5).
12. old code/static asset은 이전 웹 클라이언트가 참조할 수 있도록 최소24시간 및 N-1 보존. DB destructive contract는 별도 후속 릴리스에서 호환 종료 후 승인.

첫 설치 예외는 정책의 bootstrap_allowed=true, environment generation=0, active slot 없음, 실제 사용자 유입 전임이 확인된 경우뿐이다. 계획 policy_digest에 이 결정을 결속하고 trial 승인도 동일하게 요구한다. 구 slot drain/구 코드 복귀만 해당 없음으로 기록하며 나머지 검사·DB 이관·새 slot 검증은 생략하지 않는다. 첫 성공 후 bootstrap_allowed를 제거한다. 기존 서비스가 있었던 환경에는 이 예외를 적용하지 않는다.

### 8.2 필수 선행·차단

- 공유 세션/atomic SSE 티켓, durable event cursor/replay, 내구성 제작 queue/lease/fencing, DB·파일 외부화, NN-1 schema/event/config 호환을 모두 충족해야 trial 무중단을 활성화한다.
- 현재 Claude 어댑터 인계는 실제 PG 검증 미실행으로 기록되어 있다. SQLite 집중 시험 성공을 PostgreSQL 이관 완료로 간주하지 않는다.
- 업무 DB 초기 이관은 trial 개시 전 별도 작업. 운영 중 원본 쓰기가 있다면 승인된 cutover 절차 없이는 실행하지 않는다.
- migrate→코드 실패 시 expand schema를 남겨도 N-1이 동작해야 한다. down migration/DB restore를 “롤백” 버튼에 넣지 않는다.
- destructive/장시간 migration, 이전 앱 write 호환 없음, durable job 미완료, backup restore 미검증이면 BLOCKED. 승인 체크만으로 기술 차단을 무시하는 override API 없음.
- DB 복구는 별도 재해복구 절차/쓰기 통제/RPO·RTO 승인이다. 본 콘솔 정상 배포 흐름과 혼용하지 않는다.

### 8.3 장애 동작

| 장애 | 조치 |
|---|---|
| GitHub 불통, 실행 전 | 조회는 stale 표시, 새 dispatch/claim 금지 |
| Control/DB 불통 | agent 신규 단계 금지, 기존 서비스 유지, 상태 불확실 기록 |
| candidate 실패, LB 미변경 입증 | 기존 버전 유지, FAILED, 증거 후 잠금 해제 |
| LB timeout/일부 target 불명 | RECOVERY_REQUIRED, 실제 라우팅 대조, 맹목 재전환 금지 |
| 새 버전 업무 실패 | 자동 DB 복구 없음. 호환 확인된 이전 버전 복귀 계획/승인 |
| GitHub failure지만 target 운영 중 | RECOVERY_REQUIRED, 단순 FAILED로 잠금 해제 금지 |
| old SSE/worker가 늦게 응답 | current context/epoch·job fence로 차단, 시험 필요 |
| 관리 콘솔 배포 장애 | 업무 운영 지속. 관리툴 V1 자체 배포는 별도 검토된 수동 절차 |

### 8.4 전환 전 candidate 정리 — EXE-04

install/migrate_expand/start_candidate/verify 실패 중, agent journal과 실측으로 **switch_traffic 미착수·LB 기존 상태 유지**를 확인한 경우에만 Control이 claim을 CLEANUP_ONLY로 좁힌다. 다음 허용 단계는 cleanup_candidate 하나다. 모든 정상 단계로의 복귀는 금지한다. 기존 lease/heartbeat만 사용하며 만료된 실행권을 정리 목적으로 되살리지 않는다.

cleanup_candidate는 해당 claim이 소유한 inactive target_slot의 프로세스만 중지하고 slot을 비활성/격리한다. active slot 중지·LB 변경·공유 파일 삭제·DB down migration은 금지한다. 설치가 시작되지 않은 경우에도 journal의 미소유/미기동 및 기존 서비스 유지 증거를 남겨 멱등 완료한다. journal 소유권 또는 현재 inactive 여부가 불명이면 작업하지 않는다.

영수증에는 target slot/process 종료, old serving/LB 유지(bootstrap은 기존 서비스 부재), migration NN-1 안전, started/finished_at, plan/claim/fence를 포함한다. Control이 독립 조회하여 확인한 뒤 FAILED + claim RELEASED + 환경 lock 해제를 원자 기록한다. cleanup 실패/UNKNOWN/lease 유실·Control 불통은 RECOVERY_REQUIRED/lock 유지다. workflow는 정리 수락 뒤 원래 배포 실패로 종료한다. candidate 종료를 배포 성공으로 표시하지 않는다. switch_traffic 시도 이후 실패에는 이 경로를 사용하지 않는다.

## 9. 관리 DB 논리 스키마

UUID는 UUID형, GitHub ID는 BIGINT(HTTP에서는 decimal string), 시각 TIMESTAMPTZ UTC, hash는 소문자64자리 CHECK. 임의 JSON에 정본 식별자를 숨기지 않는다.

| 테이블 | 필수 컬럼/제약 |
|---|---|
| ops_schema_migrations | version PK, checksum UNIQUE, applied_at; 앱 startup 적용 금지 |
| ops_sessions | session_hash PK, user_id, login_display, roles_snapshot, envs, token_ciphertext, key_id, csrf_hash, idle/absolute expiry, revoked_at |
| ops_oauth_states | state_hash PK, verifier_ciphertext, expires_at, consumed_at; 1회 CAS |
| ops_environments | name PK CHECK staging/trial, generation, next_fence, active_plan_id nullable UNIQUE, serving_release_id nullable, serving_plan_id nullable, config_digest, policy_digest |
| ops_releases | id PK, artifact_sha256 UNIQUE, source_commit, manifest JSONB, verified_at, eligible, evidence_refs; 불변 |
| ops_plans | id PK, env FK, release FK, operation, reason, actor_id, immutable_payload JSONB, digest, state, revision, run_id nullable UNIQUE, run_actor_id nullable CHECK(actor_id와 일치), run_attempt, finalization_started_at/deadline nullable, created/updated_at |
| ops_preflights | id PK, plan FK, checked_at, expires_at, inputs_digest, checks JSONB; 추가 전용 |
| ops_outbox | id PK, plan FK, action, state, attempt_started_at, last_error_code; UNIQUE(plan,action) |
| ops_idempotency | actor_id, route, key 복합 PK, request_hash, result_status, result_body, created_at; 토큰 없음 |
| ops_claims | id PK, plan UNIQUE, env FK, run_id UNIQUE, fence, mode, target_slot, previous_active_slot nullable, lease_expires_at, oidc_jti UNIQUE, authorization_checked_at, grant_version, finished_at; UNIQUE(env,fence), mode/finished CHECK |
| ops_principal_revocations | user_id+env PK, revoked_at nullable, version; 명시 배포 권한 회수/해제는 승인 운영 절차와 audit, UI 편집 없음 |
| ops_steps | claim FK + step 복합 PK, receipt_digest, result JSONB, started/finished_at; 완료 기록 불변 |
| ops_observations | id PK, env FK, agent_id, agent_sequence, observed_at, received_at, payload JSONB; UNIQUE(agent_id,agent_sequence) |
| ops_audit_events | id PK, plan nullable FK, env, actor_type/id, action, outcome, request_id, redacted_detail, created_at; 추가 전용 |

JSONB 형식도 API/내부 타입으로 검증한다. FK는 원칙적으로 RESTRICT, 이력 CASCADE DELETE는 금지한다.
plan(state,updated_at), audit(env,created_at,id), observation(env,observed_at DESC), outbox(state,attempt_started_at)에 index를 둔다.
state 갱신·audit·환경 잠금/outbox는 같은 transaction이다. 잠금 순서는 environment→plan→claim으로 통일한다.
운영자 권한 설정에는 단조 grant_version을 두고 claim 직전 snapshot/version을 검사한다. 최초 claim은 EXECUTING, 종료 mode는 finished_at 필수다. environment의 serving 포인터는 단일 FK 쌍으로 release/plan/env를 검증하며 과거 SUCCEEDED 상태를 되살려 표현하지 않는다. 동시 완료·둘째 SQL 실패·잘못된 복귀 대상에서도 부분 성공을 commit하지 않는다. 실제 PG로 시험한다.
관리 저장소는 명시 OPS DB 설정 필수, 업무 core.paths/data_path import 및 업무 data/SQLite fallback 금지. 생성자/startup DDL을 하지 않고 전용 migration 역할로만 schema를 준비한다.
API DB 역할에는 audit UPDATE/DELETE가 없다. migration 역할은 별도 secret이며 API에 주지 않는다. 암호화 키와 DB 백업을 같은 위치에만 저장하지 않는다.
관리 DB 자체도 backup/restore 시험이 필요하다. 복구 시 새 dispatch를 비활성화하고 GitHub/agent 실제 상태와 대조한다. 과거 outbox를 자동 재POST하지 않는다.
agent 관측의 시계 오차>30초, 역순, 다른 환경 인증서는 거절/격리하고 감사한다. 같은 sequence·같은 본문은 기존 관측 영수증을 반환하며, 다른 본문은409다. 재기동 후에도 agent_sequence를 journal에서 이어 간다. 오래된 관측으로 최근 관측을 덮어쓰지 않는다.
ObservationPayload.readiness_evidence는 slot별 node_id/시각/실제 artifact·config digest/실제 PostgreSQL·공유 저장소의 비밀 없는 결속 digest/필수 check를 담는다. node/slot/agent/environment 매핑은 사전 등록과 일치해야 하며 check code 집합은 해당 역할 정책에서 유도한다. 관측이 없으면 []와 health=UNKNOWN으로 보고한다. HEALTHY는 현재 serving slot의 모든 필수 PASS와 freshness를 요구하며, candidate 전환은 candidate 증거를 별도로 요구한다. 빈 증거/알 수 없는 check/자기 신고 값으로 HEALTHY를 만들지 않는다.

## 10. 관측·안전한 로그

- Control→GitHub polling: active10초/idle60초, ETag, rate-limit/Retry-After 준수, 지수 backoff 최대5분. 공개 webhook은 후속 판단이다.
- agent 관측15초, freshness45초. 초과 시 UNKNOWN이고 새 dispatch/claim은 불가하다. UI에 관측/수신/마지막 GitHub 확인을 구분한다.
- GitHub HTTP timeout10초. POST timeout은 UNKNOWN, GET은 backoff 재시도. 처리 중 lease를 무기한 연장하지 않는다.
- audit는 누가/어느 환경/무슨 digest/어느 run/어떤 결과를 기록한다. 승인자는 GitHub 확인으로 표시하며, 못 얻었으면 “미확인”으로 둔다. 요청자를 승인자로 복사하지 않는다.
- raw runner log/업무 자료/token/header/body 전체를 저장하지 않는다. UI에는 정제된 단계 결과와 allowlist를 통과한 GitHub 링크만 표시한다.
- 지표: dispatch_unknown 수, 승인 대기 시간, claim 경쟁, 관측 stale, 배포 소요 시간, FAILED/RECOVERY_REQUIRED, drift, audit 쓰기 실패. 요청 ID로 연결한다.
- 알림 대상은 구성값이다. V1은 화면 경고와 기존 모니터링용 구조화 이벤트까지이며 임의 Slack/메일 연동은 추가하지 않는다.
- secret 검사·의존성 취약점·artifact 허용목록·로그 redaction 시험을 CI에 포함한다.

## 11. Codex와의 접점

V1에서 Codex에 필요한 것은 **관리 대상 소스의 로컬 checkout과 작업 규약**이다. Console에서 Codex API를 호출하는 구조가 아니다.
Console 상세에 “수정 요청 복사”를 둔다. 출력은 plan ID, source SHA, 정제된 실패 code, 증거 링크, 재현 절차이며 token/실자료/SQL 내용을 포함하지 않는다.
사용자가 기존 Codex/Claude 작업에 요청하고, 분리 브랜치/PR→검토→기존 CI→동일 배포 경로를 통과한다. 작업 시작이나 PR 생성을 자동 실행하는 버튼은 V1에 만들지 않는다.
PC 폴더 지정은 소스 작업 장소를 정하는 것이지 클라우드 운영 권한을 부여하는 것이 아니다. 운영 서버 checkout을 에이전트가 직접 수정하지 않는다.
따라서 **GitHub 연동 API는 쓰지만 Codex 모델 API의 별도 인증·비용은 V1 필수 요건이 아니다**. 기존 Codex 이용료가 무료라는 의미는 아니다.

## 12. 구현 전에 채울 구성값·해제 조건

| 구성/증거 | 담당 | 미확정 시 |
|---|---|---|
| repository/owner numeric ID, App/install ID, 보호 workflow tag/SHA | GitHub 관리자 | fake adapter만 |
| private 환경 required reviewers/self-review/bypass 보호 실측 | GitHub 관리자+독립 검토자 | trial 비활성 |
| operator/reviewer numeric ID, VPN/domain/callback/audience | 운영 책임자 | 외부 로그인/dispatch 비활성 |
| NCP LB SKU/target IDs/agent mTLS/secret 보관/네트워크 | 인프라 담당 | dry-run만 |
| 업무 PG/schema 호환, session/job/SSE/외부 파일/복구 증거 | Claude 구현+Codex 검토 | trial 무중단 비활성 |
| CI 정확 runtime/lock/allowlist/provenance/보관 위치 | CI 담당 | release eligible=false |
| 비용 견적/구매 승인, 실자료 범위 | 사용자/운영 책임자 | 자원 생성·자료 이관 불가 |

사용자 수는 다시 묻지 않는다. 예산·GitHub 요금제 구매 승인을 설계 동의에서 추정하지 않는다.

## 13. 자체 이중 검토와 승인 상태

아래 표는 최초 작성 시 Codex 자체 점검의 기록이다. 이후 독립 검토 CHANGES_REQUESTED와 R1 보완은 별도 기록으로 구분한다.

| 관점 | 초안에서 차단한 모호함 | 본 설계 결론 |
|---|---|---|
| 승인자 신원 | bot dispatch가 요청자를 숨김 | user token dispatch, GitHub 최종 승인 |
| private 요금제 | 버튼이 있으면 승인 가능하다는 가정 | 보호 기능 실측 전 fail-closed |
| 외부 POST 재시도 | timeout을 실패로 보고 재송신 | UNKNOWN·대조·단일 claim |
| 버전 바꿔치기 | branch와 artifact SHA 혼동 | workflow ref/SHA와 artifact digest 별도 고정 |
| 성공 표시 | GitHub green만으로 완료 | 실제 상태의 신선한 관측까지 AND |
| 취소 경쟁 | 실행 후 강제 종료 | claim과 동일 잠금, 실행 전 한정 |
| DB 복귀 | 코드 복귀를 DB 되감기로 처리 | expand/NN-1, DB 복구 별도 |
| UI 과대화 | Apollo/GitHub 전체 재구현 | 3메뉴·기존 검토/로그 링크 |
| Claude와 충돌 | 업무 App/auth를 고쳐 관리툴 구현 | 독립 package/DB, 현재 작업 계속 |
| 진척 부풀리기 | 설계 완료를 실제 배포 가능으로 표기 | 설계/구현/실측을 별도 관리 |

독립 검토는 구현 전 API/상태/인증/실행 경계를 대상으로 한다. P0/P1이 남으면 외부 쓰기 기능을 켜지 않는다.
출시 전 API 계약 시험, 실제 GitHub staging dispatch/승인 거절, NCP Blue/Green, 업무 Z-01~10, 백업 복구를 나누어 RUN/NOT_RUN을 기록한다. 구체 목록은 구현 인계서에 고정했다.

## 14. 실행 프로토콜 보충 계약

### 14.1 단계와 상태 결속

| 단계 영수증 | 상태·완료 조건 |
|---|---|
| install | PREPARING 유지; manifest/provenance/hash/허용 경로 검증 |
| migrate_expand | PREPARING 유지; migration ledger checksum 및 NN-1 증거 |
| start_candidate | VERIFYING 전이; boot/readiness probe 가능 |
| verify | PROMOTING 전이; 연속 readiness·핵심 smoke 증거 |
| switch_traffic | DRAINING 전이; LB read-back + target digest 확인 |
| drain | FINALIZING 전이; 요청 drain·job handoff·SSE 재연결 검사 |
| observe | FINALIZING 유지; 60초 관측 영수증 수락 시 claim RELEASED. 이후 GitHub success와 fresh 실측 대조로 SUCCEEDED |
| cleanup_candidate | CLEANUP_ONLY에서만; 전환 전 실패 후보 정리·기존 서비스/DB 안전 증명 후 FAILED와 claim 종료 |

선행 단계 누락·다른 fence·다른 plan·역순 완료는409다. 단 cleanup_candidate는 §8.4의 확인된 실패에서만 분기하는 보상 단계로 정상 순서의 나머지를 요구하지 않는다. 같은 단계 같은 receipt는 기존 결과, 다른 receipt는409다.
runner가 보낸 result 문자열만 신뢰하지 않는다. Control API는 mTLS로 사전 등록 agent의 영수증을 읽어 receipt hash/plan/fence/step을 검증한다.
agent 내부 API는 POST /agent/v1/steps(고정 enum, plan_id/claim_id/fence/step), GET /agent/v1/receipts/{id}, GET /agent/v1/observation뿐이다. 입력은 모두 필수이며 추가 필드는 거절한다. 명령 POST는 Idempotency-Key=claim_id+step 문자열을 사용한다. 응답은 receipt_id/result/receipt_digest/observed_at와 정제된 proof다. 이 인터페이스는 인터넷·Console에 노출하지 않는다.
장기 단계를 POST 응답에 매달지 않는다. POST는202+receipt_id를 반환하고 GET은 PENDING/RUNNING/SUCCEEDED/FAILED/UNKNOWN 상태를 반환한다. 중복 POST는 같은 receipt_id다. complete API는 완료 영수증만 받는다.
proof는 artifact hash, schema epoch, LB read-back digest, smoke 결과, slot 관측, 시작/종료 시각 중 단계에 필요한 필드를 담는다. 민감한 실제 업무 데이터는 넣지 않는다. CLI 임의 명령/동적 플러그인은 V1 금지.

### 14.2 불확실 상태의 세부

DISPATCH_UNKNOWN 상태의 합법적 claim은 먼저 run identity를 검증해 QUEUED로 결속한 뒤 승인 여부를 대조한다. UNKNOWN에서 검증 없이 PREPARING으로 뛰지 않는다.
claim 재시도는 같은 run/Idempotency-Key/body이면 같은 claim 반환이다. OIDC token의 재사용으로 두 번째 claim을 만들지 않는다. 새 heartbeat token의 유효성 검증은 별도로 계속한다.
취소할 때 active_plan_id가 해당 plan과 같을 때만 환경 잠금을 해제한다. READY/BLOCKED 계획 취소가 다른 실행 계획의 잠금을 풀면 안 된다.
GitHub state가 낯선 값이면 unknown으로 매핑하고 원값은 정제 감사에 남긴다. 완료와 정상으로 추정하지 않는다.

### 14.3 CI 카탈로그 수집

release workflow의 게시 자격증명은 artifact bucket의 정해진 prefix에 쓰기만 허용한다. 업무 DB/agent/배포 서버 접근 권한은 없다. 장기 키가 필요한 NCP 연동이면 별도 secret 보관·회전·회수 계획과 비용 승인 후 연결한다.
Control 카탈로그 수집기는 허용된 GitHub release workflow 성공 run을 polling하여 manifest/provenance/object digest를 검증한 뒤 ops_releases를 추가한다. UI나 임의 클라이언트가 release/검사 PASS를 등록하는 endpoint는 없다.
Object Store 업로드 완료 전 release를 eligible로 만들지 않는다. staging 증거는 동일 digest·config 정책·schema 호환 범위에 결속하며 시험 결과를 이유 없이 다른 artifact에 재사용하지 않는다.

### 14.4 DEP-P1/P2 산출물 통합 규칙

`scripts/release_artifact.py`는 file index/허용목록 도구로 재사용한다. archive/runtime lock/source/build/workflow/SBOM/provenance/schema/출처 승인은 OPS-P1의 별도 완성 조건이다. starter_kits의 경로 예외는 실자료 배포 승인이 아니다. 미분류 자산은 외부 publish 차단, 원본 삭제/공개 금지. scripts 기본 제외와 명시 탐침 허용은 유지하고 migration/bootstrap은 별도 작업용 산출물로 검토한다.

`core/serving_readiness.py`는 업무 노드 진단 위치로 유지 가능하나 실제 backend/프로세스/스토리지 관측 공급자를 연결해야 한다. 알 수 없는 판정·누락 필수 검사·필요 공유 경로 빈 목록은 READY 불가. `.afs-shared` 단순 존재, `--started` 자기 신고, 탐침 환경변수 digest를 실제 관측으로 승격하지 않는다. 공유 저장소는 승인 설치 시 양 노드가 동일 backend/mount·검증 자료를 보는지 확인하며 readiness는 read-only다.

`ops_control/deploy_ledger.py`의 미연결 7상태 프로토타입은 시험 의도만 선별 재사용한다. 상태명15개로 개명만 하거나 임의 approver를 GitHub 승인으로 쓰지 않는다. 이전 결과를 되살리는 rollback·업무 DB 기본 경로·분리 commit은 정식 관리 backend에 이식하지 않는다. 새 계획/환경 현재 포인터/명시 PG migration/원자 commit이 기준이다. 구 원장 완성→폐기의 이중 작업을 피한다. 기존 update.sh의 in-place 갱신은 trial CD 경로에 연결하지 않는다.
