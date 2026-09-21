# 배포 준비 패킷 — Claude DB 조사 이후 바로 사용할 작업서

작성: Codex · 2026-09-21 KST. 사용자 확인: Claude가 이전 지시서로 작업 중.
이 문서는 진행 중인 재개 보완/DB-0를 중단하거나 교체하지 않는다. Codex가 병행 가능한 배포 준비만 수행했다.
상위 정본: `docs/roadmap/NCP_ZERO_DOWNTIME_DELIVERY_AND_CODEX_2026-09-20.md`.
기존 30/10 → 100/30 → 200/50+ 규모, NCP, 별도 배포 관리, 무중단 원칙을 유지한다. 새 구매/정책 승인 문서가 아니다.

## 1. 이번에 확인한 실제 차이 — 재조사하지 말고 구현 때 해소

아래는 소스 정적 확인이다. Linux 설치/기동/복구/클라우드 기능은 실행 검증하지 않았다.

| ID | 근거 | 현행 상태 | 다음 구현에서 필요한 것 |
|---|---|---|---|
| DEP-01 | `deploy/update.sh` | 운영 위치에서 fetch/checkout 또는 pull, pip 설치, npm build, 단일 서비스 restart | 불변 산출물 설치와 Blue/Green 전환으로 교체. 구 스크립트를 trial CD에 연결하지 않음 |
| DEP-02 | `deploy/README.md` §4 vs update.sh | 문서는 git archive 사용이라고 하지만 해당 스크립트에는 없음 | 실제 패키저의 파일 허용목록·내용 검사를 구현. 추적 파일만이라는 조건도 비밀/데이터 배제의 충분조건 아님 |
| DEP-03 | `deploy/install.sh`, `core/library_paths.py` | 외부 링크는 data/projects/output뿐. library는 상대 경로 | library와 DB/첨부 manifest를 포함한 영속 경계 확정. 릴리스 디렉터리 교체로 업무 산출물이 사라지지 않게 함 |
| DEP-04 | `deploy/backup.sh` | DB별 온라인 백업 + projects tar. library 없음, tar 실패는 `|| true`, DB별 순차 백업 | 백업 누락/실패를 성공으로 표시하지 않음. DB 간·DB/파일 간 동일 업무 기준점 검증, 별도 환경 복원까지 확인 |
| DEP-05 | `deploy/afs.service:19`, `run.py` | systemd는 uvicorn main:app 직접 실행. 설치 문맥 적용은 run.py의 main 블록에 있음 | 운영 bootstrap 계약 통일. 단순히 run.py로 바꾸면 조직 쓰기도 동반하므로 읽기 설정 검증과 승인된 초기 설치를 분리 |
| DEP-06 | `main.py:56`, `deploy/check.sh` | health는 DB/인증 미확인. 점검은 health/401/로컬 dist/링크 위주 | liveness를 유지하고 별도 내부 readiness/업무 probe 추가. process 200만으로 트래픽 전환 금지 |
| DEP-07 | `main.py:114`, `scripts/derive_runtime_requirements.py` | startup에서 그래프/체크포인터 warmup·표준 seed. 의존성 도출도 main import | 운영 checkout에서 도출 도구 실행 금지. 합성 격리에서 import/기동의 쓰기·외부 호출을 감시하고 migration/seed 단일 실행 분리 |
| DEP-08 | `requirements.txt`, `requirements-dev.txt`, install.sh | 런타임 버전은 명시돼 있으나 dev는 pytest>=8, 설치 시 pip 및 torch를 별도 갱신, Python/Node 정확 판 미고정 | 깨끗한 Linux에서 런타임/도구/CPU wheel 포함 해시·버전 잠금. 기존 목록 삭제/무작정 재도출 금지 |
| DEP-09 | `frontend/package.json`, build-preview-vendor.mjs | prebuild가 preview-vendor 자산 생성 | 빌드 결과의 index/chunk뿐 아니라 preview-vendor 3종도 포함·내용 해시 검사 |
| DEP-10 | 현재 checkout | .github 디렉터리 없음 | CI 구현은 신규. 원격 규칙/요금제/승인 기능은 별도 확인, 이미 구축됐다고 보고하지 않음 |

DEP-05는 실제 tenant 오염을 입증한 것이 아니라 **기동 경로 차이**다. 환경변수로 전부 보완돼 있는지 아직 미확인. 운영 설정이 없거나 모호하면 준비 완료를 반환하지 않아야 한다.
DEP-04의 DB별 백업 성공은 전체 업무 스냅샷 일관성의 증거가 아니다. 기존 backup/restore를 PostgreSQL 복구 도구로 재명명하지 않는다.

## 2. 충돌 없는 작업 분담 / 착수 순서

- Claude 현재 작업: 재개 R1/R2/R3, 직접 status 경로 판정, DB 차이 지도/첫 저장소 경로. 이 문서 때문에 중단하지 않는다.
- Codex 이번 완료: 위 정적 차이 지도, 아래 CI 계약·배포 수용표·증거 기록 템플릿. 제품/시험/기존 배포 파일과 공용 TEAM_BOARD는 수정하지 않았다.
- Claude 인계 후 첫 후속은 **DEP-P1: CI/산출물 계약**, 다음은 **DEP-P2: 두 슬롯 배포 및 readiness**, DB/이벤트 외부화 수용 뒤 **DEP-P3: 전환·복구 리허설**이다. R1 번호 정정: 신규 관리툴 OPS-P0~7과 구분한다. 기존 원장은 미연결 프로토타입으로만 보존하며 정식 OPS-P2에 상태/승인/저장 모델을 그대로 이식하지 않는다. 연결 기준은 `CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md` §11과 `CODEX_REVIEW_DEP_P1_P2_2026-09-21_B.md`다.
- DB-0 결과와 DEP-03/05/07의 경계를 합친다. 같은 자산 지도를 두 번 작성하지 않는다. auth·조직·파일 경계 변경은 Claude DB 설계와 일치시킨다.

| 묶음 | 만들 것 | 확인할 것 | 예상 / 시작 조건 |
|---|---|---|---|
| DEP-P1 | CI workflow 초안, 산출물 허용목록/파일 색인/검사기 → OPS-P1 full manifest로 연결 | Linux 합성 검사·비밀/데이터 미포함·필수 자산 존재 | 60~90분 첫 초안, Linux 환경 없으면 실행은 미검증 |
| DEP-P2 | release별 서비스 슬롯, 기동 계약, 내부 readiness; 원장 프로토타입은 OPS-P2 통합 검토 자료 | Green 준비 실패 시 Blue 유지, 실제 노드 관측·설치 문맥 일치, 구 UI 자산 보존 | DB 지도 후 재산정. 첫 설계/실패 경로 체크포인트30분 |
| DEP-P3 | staging 전환/복귀·DB/파일 복구 리허설 → OPS-P5 실측 | §5 시나리오, 단일 노드 목표10명 부하 | 세션/작업/SSE/파일 공유 기반 완료 후. 지금 완료시간 약속 금지 |

DEP-P1 시작 전에 매 파일 승인을 반복할 필요는 없지만, 원격 workflow 활성화·runner 등록·Secrets 설정·자원 구매·자료 업로드는 별도 승인 범위다.

## 3. CI 구현 계약 — 계획과 실제 명령을 구별

### 실행 격리

깨끗한 Linux checkout과 합성 저장소에서만 실행한다. 이 PC의 실행 중인 환경, `.env`, instance.json, 사용자 DB/로그를 runner에 복사하지 않는다. 사설 시험 DB도 운영과 다른 자격증명/네트워크로 분리한다.
PR job은 읽기 권한, 비밀값0, 유료 LLM0. 릴리스 빌드/배포 승인은 보호된 ref와 별도 권한으로 분리한다. action SHA·실제 ref·승인 기능은 확인 후 지정하며 임의 값을 넣지 않는다.

### 확인된 기존 진입점

아래는 **향후 격리 CI에서 쓸 후보 명령**이며 이번에 실행한 결과가 아니다.

```text
# frontend/에서, 정확한 Node/npm 버전 고정 후
npm ci --no-audit --no-fund
npm run build
node scripts/check-studio-contracts.mjs
node scripts/check-project-entry.mjs
node scripts/check-draft-entry.mjs
node scripts/check-draft-open.mjs
node scripts/check-studio-location.mjs
node scripts/check-kit-app-entry.mjs
node scripts/check-release-entry.mjs

# 저장소 루트, 준비된 합성 격리에서; Python 실행 파일은 runner의 고정 런타임
python scripts/verify_data_usage_holds.py --strict-writes --target tests/test_release_item_visibility.py --target tests/test_program_reactivate_restores_prior_state.py
```

위 두 서버 파일만으로 전체 인증/승격/미확정 명령 계약을 대표하지 않는다. 추가 필수 nodeid는 Claude의 최신 통과 증거에서 수집하고 conftest 의존·격리 보호를 확인한다. 새 runner를 중복 작성하지 않는다. `verify_decision_creation_isolated.py`에는 임의 --target/--suite 기능이 없으므로 잘못된 옵션을 복사하지 않는다.

PR: 변경 영향 시험 + 항상 필요한 보안 계약. release 후보: 전체 지정 수용 묶음 + 실제 PostgreSQL 동등성/권한/원자성. Windows 모의 검사 통과를 Linux/실제 PostgreSQL 검증으로 합산하지 않는다.
전체 검사를 매 작은 수정마다 반복하지 않는다. 검사가 실패하면 정확한 실패 계약을 고치며 skip 추가로 초록을 만들지 않는다.

### 불변 산출물

- 깨끗한 검토 완료 SHA에서 한 번 빌드, staging/trial은 **동일 artifact digest** 사용. 서버 git pull/pip 해석/npm build 금지.
- 실행 소스의 import 결속·템플릿/기준 팩·프런트 산출물을 기준으로 실제 파일 허용목록을 만든다. 전체 repo zip이나 확장자만으로 허용하지 않는다. starter kit도 승인된 제품 자산과 실자료를 분리한다.
- 금지: data/projects/library/output/data_sync, .env/키/토큰, 사용자 로그/덤프, 격리 fixture, .git/에이전트 이력. 금지 경로 파일을 가리키는 symlink·경로탈출·압축 해제 경로도 검사한다.
- 빌드 입력: 잠긴 의존성·정확한 Linux/Python/Node판·빌드 설정 지문. 결과: 소스 SHA, artifact digest, 파일별 hash, dependency/SBOM, schema 호환 범위, worker/event 계약판, 검사 증거 참조.
- 설정은 별도 버전 지문으로 결속하고 비밀 원문은 manifest에 넣지 않는다. 승인도 환경·digest·설정 지문·migration 계획에 결속한다. 승인 뒤 하나라도 바뀌면 재승인한다.
- 프런트 same-origin API 설정과 preview-vendor 포함을 실측한다. 설치 문서의 「셸 빈 환경값은 불가」 설명은 현행 api.ts가 `??`로 빈 값을 허용하는 점과 대조가 필요하다. 예전 관찰을 그대로 새 CI 제약으로 고정하지 않는다.

## 4. 트래픽 전환 계약

**생존 / 준비 / 업무 수용은 별개**다.

| 층 | 필요한 확인 | 실패 시 |
|---|---|---|
| 생존 | 프로세스가 응답함; 기존 health 의미 유지 | 노드 이상, 신규 트래픽 제외 |
| 내부 readiness(구현 예정) | release/config 식별, schema 지원 범위, DB 제한 조회, 공유 저장소, 올바른 설치 문맥, 해당 역할 기동 완료 | Green 승격 금지. 세부 경로/비밀은 공개 응답에 넣지 않음 |
| 업무 probe | 정상 로그인·권한 거절, 세션 교차노드, 티켓 일회소비, SSE 재생, 접수 영수증/작업 추적 | 승격 금지, 원인 기록 |

readiness는 외부 LLM 호출/자료 seed/DDL을 실행하지 않는다. DB 장애로 모든 앱을 끊임없이 재시작하는 판단도 하지 않는다. 실패/무응답은 초록이 아니라 FAIL/UNKNOWN이다.

배포 관리 시스템은 환경별 잠금과 plan ID를 가진다. 네트워크 응답 유실 때 현재 digest/트래픽/작업 상태를 다시 조회하고 무조건 재실행하지 않는다. 이미 진행 중인 안전한 단계는 완료/관측할 수 있게 하되 관리 서버를 잃으면 새 승격은 중지한다.
승격 전 Blue가 단독으로 목표 부하를 처리할 수 있어야 한다. Green 실패만으로 Blue를 재기동하지 않는다. 오래된 UI chunk와 worker를 보존하며 열린 입력을 강제로 새로고침하지 않는다.
NCP LB의 cohort/가중치/연결 드레인 실제 지원은 미확인이다. 해당 기능이 있다고 가정한 스크립트를 작성하지 않는다. 지원 경로 확정 전에는 합성 상태 머신 검사까지만 한다.

## 5. 무중단 리허설 — 관측 대상을 먼저 고정

모든 쓰기 probe는 staging 합성 계정/자료로 한다. trial의 실제 업무에 시험 쓰기를 숨겨 넣지 않는다.

| ID | 시나리오 | 통과 증거 |
|---|---|---|
| Z01 | Blue 로그인 후 Green에서 동일 세션 사용 | 재로그인 없음, 권한 동일, 만료/회수된 세션 거절 |
| Z02 | 같은 SSE 티켓을 두 노드에서 동시 소비 | 하나만 성공, 다른 하나 거절; raw ticket 로그0 |
| Z03 | 전환 중 이벤트/회사 전환 | cursor 기준 누락/중복 표시0, 이전 문맥/회수 권한 이벤트 미반영 |
| Z04 | 진행 중 작업을 둔 배포 | 접수ID/상태 보존, 구 worker 완료 또는 검증된 인계, 중복 외부효과0 |
| Z05 | Green 준비 실패·DB schema 불일치 | Blue 계속 서비스, 승격 없음, 원장에 실패 이유 |
| Z06 | 배포 관리 서버/응답 단절 | 업무 계속, 새 승격 정지, 복구 후 실제 상태 재조회·중복 실행 없음 |
| Z07 | 구 UI를 열어둔 채 신 API 전환 | 구 chunk 로드 가능, 입력 유지, 명령 계약/거절 표시 정상 |
| Z08 | 전환 후 합성 쓰기를 만든 뒤 코드 복귀 | 새 쓰기 보존, 호환 코드로 복귀; DB snapshot 자동 덮어쓰기 없음 |
| Z09 | DB+library/첨부 복구 | 별도 복원 환경에서 참조/내용 지문/권한 대사; 누락 파일/실패 백업을 초록으로 표시하지 않음 |
| Z10 | 동시10명, 한 App 제외한 전환 부하 | 요청수/관찰시간/지연/오류·작업/이벤트 실측. 단순 오류0만으로 통과 금지 |

장기작업 합성 시험과 실제 LLM 생산자 수용은 구별한다. 합성으로 유료 제작 검증 완료라고 하지 않는다. Z04에서 비용/외부 호출이 필요해지면 그 부분만 별도 승인 대기한다.
기존 계획의 일반API p95 1.5초/SSE 재연결 5초는 검증 목표이지 측정 완료나 SLA가 아니다. 관찰시간/요청수·실제값을 증거에 반드시 남긴다.

## 6. 전환 실패 / 복귀 분기

1. Green 준비 전 실패: Blue 유지, Green 전환 금지. 로그/실패 증거 보존.
2. 일부 전환 뒤 오류: 승인된 환경 정책에 따라 Green 유입 중단. Blue/schema/현재 자료 호환 확인 후 코드 트래픽 복귀. 진행 작업 임의 kill 금지.
3. 호환성 불명/자료 손상: 자동 rollback/downgrade 금지. 영향 쓰기만 격리하고 현재 자료/원장 보존, 별도 복원 환경 대사 후 운영자 판단.
4. 복귀 완료: 실제 serving digest·DB판·접수된 작업·새 쓰기 보존 확인. 명령 exit0만으로 ROLLED_BACK 표시 금지.

## 7. 운영 개시 전에만 필요한 사용자 결정

지금 Claude를 멈추고 모두 질문하지 않는다. 아래는 구매/자료 반입/운영 개시 직전 한 번에 확정할 카드다.

- 예산: 1단계 월150만원 권고 상한 승인 여부(LLM/자동 코드수정 사용료 별도). 실제 품목 견적이 먼저다.
- 운영자/승인자/장애 연락 담당, 실제 도메인·관리 접속 경로. 비밀값은 채팅/문서에 쓰지 않는다.
- 반입 자료: 소유자·조직·보관기간·허용 사용자·외부 LLM 전송 허용 여부. 클라우드 이전 승인과 LLM 전송 승인 분리.
- 복구 목표: 제안 RPO 15분 이내, RTO 2시간 이내를 복구 실측/업무 허용치와 대조해 확정. 아직 합의/SLA가 아니며 HA가 이 목표를 보장하지 않는다.
- 초기 이관: trial 개시 전 이관 기본. 기존 로컬 업무를 계속 사용하는 경우 최종 전환창/동기화 방안 별도 승인.

## 8. 증거 기록·다음 인계

같이 만든 `CODEX_DEPLOYMENT_EVIDENCE_TEMPLATE_2026-09-21.json`은 검증 결과를 적을 **빈 양식**이다. 배포 실행기/검증기 설정이 아니며 비어 있는 값은 PASS가 아니다. 최종 결과에는 실행 commit/dirty 여부·환경·artifact/config digest·시험시간·실제값·관련 보고 경로를 결속한다.
Claude 현재 보고가 오면 Codex는 R1~R3/DB-0 결과와 이 패킷을 합쳐 P1 착수 범위만 확정한다. 새 아키텍처 문서를 다시 쓰거나 닫은 UI를 재검증하지 않는다.

전체 제품 진척은 마지막 인정치 **21/40=52.5% 유지**. 이번 완료는 배포 준비 자료이며 DB 이관/CI 구현/무중단 실증 완료가 아니다. 커밋·푸시·원격 조회/변경·클라우드/DB 실행·환경 철수 없음.
