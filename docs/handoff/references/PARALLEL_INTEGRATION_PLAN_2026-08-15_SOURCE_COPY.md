# AI Factory Studio 병렬개발 통합 수행계획

> 문서 상태: 실행 정본 초안
> 작성자: Codex
> 작성일: 2026-08-15
> 적용 목표: 3주 내 대내외 시연 가능한 MVP
> 적용 범위: Claude Code의 Host Runtime·I-4·BDR 트랙과 Codex의 G2 온톨로지·후속 G4·시연 UI 트랙 통합
> 중요 제한: 이 문서는 통합 절차를 확정하기 위한 문서이며, 작성 시점에는 실제 merge·cherry-pick·origin push를 수행하지 않는다.

---

## 1. 결론

병렬 개발 결과는 기존 `dev` 작업트리에서 바로 합치지 않는다. 다음 구조를 기본 통합 방식으로 확정한다.

```text
Claude Code 작업트리(dev)             Codex 병렬 작업트리
Host Runtime · I-4 · BDR              G2 Ontology · G4 · Demo UI
          │                                      │
          ├─ 각자 원자 커밋 + 자체 회귀 ─────────┤
          │                                      │
          └──────── 깨끗한 통합 전용 worktree ───┘
                         │
              ① 코드 통합: 선별 cherry-pick
              ② 계약 통합: 권한·Scope·지문·상태 정합
              ③ 제품 통합: API mount·내비게이션·E2E
                         │
                단계별 Gate 0~6 통과
                         │
               깨끗한 dev에 fast-forward
```

핵심 원칙은 다음과 같다.

1. **브랜치 전체 merge 금지**: 병렬 브랜치에 기준선 동기화 merge와 검토 문서가 섞여 있으므로 검증된 기능 커밋만 선별 적용한다.
2. **더러운 `dev`에서 통합 금지**: 다른 팀원의 미커밋 변경을 섞거나 잃을 위험이 있다.
3. **공통 진입점은 마지막에 한 번만 연결**: `main.py`, 전역 라우터, `frontend/src/App.tsx`, 전역 내비게이션은 통합 담당자가 별도 커밋으로 연결한다.
4. **통합 성공과 제품 연결 성공을 구분**: 파일이 합쳐지고 테스트가 통과해도 API mount·화면·수직 시나리오가 없으면 제품 통합 완료가 아니다.
5. **origin은 다루지 않는다**: 사용자의 별도 명시 전까지 fetch·pull·push 모두 통합 절차에 포함하지 않는다.

---

## 2. 착수 전 4문항

| 질문 | 답변 |
|---|---|
| 로드맵 권고 착수 항목 | G1-B Host Runtime, G2 의미 모델 런타임, G4 결정론적 계산, 첫 수직 폐루프 시연을 하나로 통합하기 위한 필수 작업 |
| 관문 | G1 안전 기반 → G2 데이터·의미 기반 → G4 계산 → G8 시연·파일럿으로 이어지는 관문 연결 작업 |
| 첫 수직 폐루프에 직접 필요한가 | 예. 병렬 산출물을 합치지 못하면 경영 질문→영향 경로→수치 계산→결정 흐름이 성립하지 않는다. |
| 왜 지금 하는가 | 사용자가 3주 내 시연 MVP를 요구했고 Claude Code와 Codex의 병렬 구현을 승인했다. |

---

## 3. 2026-08-15 실측 기준선

### 3.1 `dev` 상태

- 브랜치: `dev`
- 기준 커밋: `2ae0f8471`
- `origin/dev` 대비 로컬 4커밋 앞섬
- Claude Code가 I-4 3단계를 진행하며 다음 계열을 미커밋 변경 중이다.
  - `api/routes/app_data_runtime.py`
  - `core/app_capability_token.py`
  - `core/app_policy.py`
  - `core/app_runtime_contract.py`
  - `core/host_runtime_sdk.py`
  - `core/policy_shadow.py`
  - 관련 테스트와 신규 `core/app_contract_gate.py`

따라서 현재 `dev` 작업트리는 **통합 금지 상태**다. Claude Code가 자기 변경을 원자 커밋으로 정리하고 자체 회귀 결과를 남기기 전에는 통합하지 않는다.

### 3.2 Codex 병렬 브랜치 상태

- 작업트리: `workspace/codex-three-week-mvp`
- 브랜치: `codex/three-week-mvp`
- 기준선: `dev@2ae0f8471`
- 작업트리: clean
- 제품 코드 커밋:

| 순서 | 커밋 | 역할 | 파일 |
|---:|---|---|---|
| 1 | `37ca74c0c` | G2 관계 거버넌스 런타임 | `core/ontology_runtime.py`, `tests/test_ontology_runtime.py` |
| 2 | `110e9bb4d` | G2 승인 모델 계약·REST 계약 | `api/routes/ontology_control.py`, 위 런타임·테스트 확장 |
| 3 | `a22388741` | 병렬 트랙 인수인계 갱신 | `docs/handoff/CODEX_THREE_WEEK_MVP_PARALLEL_TRACK_2026-08-15.md` |

다음 커밋은 통합 대상으로 사용하지 않는다.

- `9aebe87ee`, `d59dd679f`: `dev` 동기화를 위한 merge commit
- `d689b38cd`, `0c65d9ad7`: 교차검토 문서. 필요한 판정은 정본 설계·인수인계에 반영하되 제품 통합의 필수 코드가 아니다.

### 3.3 현재 파일 충돌 판정

`dev...codex/three-week-mvp` 실측 결과 Codex 고유 변경은 신규 6개 파일이며, 현재 Claude Code의 미커밋 I-4 파일과 직접 경로 충돌은 없다.

그러나 **논리 의존성은 존재한다.** G2의 `ResourceScope`·PDP 사용은 G1-B/I-4 계약 위에 있으므로, 파일 충돌이 없다고 먼저 합쳐도 된다는 뜻은 아니다. Claude Code의 3단계 계약 지문 봉인 완료본을 기준선으로 먼저 확정해야 한다.

---

## 4. 통합 단위와 순서

### 4.1 통합 단위

| 단위 | 내용 | 커밋 원칙 | 담당 |
|---|---|---|---|
| U0 | Claude Code I-4 3단계: 계약 원문·물질화 지문 봉인 | Claude Code가 자체 커밋·테스트 | Claude Code |
| U1 | G2 관계 런타임 | `37ca74c0c` 선별 적용 | Codex |
| U2 | G2 모델 계약·REST 팩토리 | `110e9bb4d` 선별 적용 | Codex |
| U3 | G2↔G1-B 계약 어댑터 | 신규 통합 커밋. 기존 판정 재구현 금지 | 공동, 구현자 1인 |
| U4 | Object Scope·Decision Ledger Resolver | Namespace별 어댑터와 승인 검증 | Claude 주도·Codex 검토 |
| U5 | 제품 API mount | `main.py` 단일 커밋 | 통합 담당자 |
| U6 | 시연 UI route·내비게이션 | 전역 진입점 단일 커밋 | Codex 주도 |
| U7 | 첫 수직 E2E Fixture·G4 연결 | DEMO_ONLY/CERTIFIED 분리 | Claude·Antigravity·Codex |
| U8 | 인수인계·보드·진척 정리 | 코드 완료와 분리된 문서 커밋 | 각 작성자 |

### 4.2 강제 순서

```text
U0 Claude I-4 3단계 완료
 └─ Gate 0: clean baseline
     └─ U1 G2 관계 런타임
         └─ Gate 1: 집중 회귀
             └─ U2 G2 계약·REST 팩토리
                 └─ Gate 2: 계약 정합
                     └─ U3~U4 Resolver·어댑터
                         └─ Gate 3: 권한·숨김·오류 계약
                             └─ U5 API mount
                                 └─ Gate 4: 실서버 카나리
                                     └─ U6 UI 연결
                                         └─ Gate 5: 브라우저 E2E
                                             └─ U7 첫 수직 폐루프
                                                 └─ Gate 6: 시연 승인
```

U1과 U2는 독립된 제품 커밋으로 유지한다. U1에서 문제가 나면 U2를 적용하지 않는다. U3~U6을 한 커밋에 섞지 않는다.

---

## 5. 통합 전용 worktree 운영

### 5.1 생성 조건

다음 조건을 모두 충족해야 통합 worktree를 만든다.

- Claude Code의 I-4 3단계가 원자 커밋으로 완료됨
- `dev`가 clean
- 전체 테스트 결과와 집중 테스트 결과가 인수인계에 기록됨
- `git status --short`가 비어 있음
- 깨끗한 checkout에서 `import main`이 정상
- 다른 팀원의 진행 중 파일이 스테이징되지 않음

### 5.2 브랜치 구조

```text
dev
└─ codex/integration-three-week-mvp   ← 매 통합 회차마다 dev 최신점에서 새로 생성
```

통합 브랜치를 오래 유지하며 계속 merge하지 않는다. `dev`가 통합 중 움직였다면 rebase로 억지 정리하지 않고, 최신 `dev`에서 통합 브랜치를 새로 만들어 검증된 원자 커밋을 다시 적용한다. 통합 재현성이 있다는 증거이기도 하다.

### 5.3 적용 명령 초안

아래는 절차를 명확히 하기 위한 명령 초안이며 이 문서 작성 시점에는 실행하지 않는다.

```powershell
git worktree add workspace/integration-three-week-mvp -b codex/integration-three-week-mvp dev
git -C workspace/integration-three-week-mvp cherry-pick 37ca74c0c
git -C workspace/integration-three-week-mvp cherry-pick 110e9bb4d
```

문서 커밋 `a22388741`은 코드 게이트 통과 후 적용한다. 코드 실패와 문서 충돌을 같은 순간에 다루지 않기 위해서다.

---

## 6. 충돌 분류와 처리 책임

| 등급 | 예시 | 처리 | 승인/검토 |
|---|---|---|---|
| C0 | 신규 파일끼리 겹치지 않음 | 자동 적용 후 테스트 | 구현자 자체 검증 |
| C1 | import·타입·함수 시그니처 변경 | 호출자와 생산자 계약 대조 | 원 파일 소유자 확인 |
| C2 | 권한·Scope·404/403/503 의미 충돌 | 자동 해결 금지, 계약표 작성 | 다른 팀원 교차검토 필수 |
| C3 | DB 스키마·마이그레이션·지문 변경 | 운영 DB 금지, 사본 이행 검증 | Claude+Antigravity 감사 |
| C4 | `main.py`·전역 UI·라우터 mount | 한 명만 수정, 별도 커밋 | Codex UX + Claude 구현 검토 |
| C5 | 경영 수치·Actual/CERTIFIED 승격 | 구현값과 공식값 분리 | Supervisor 최종 승인 |

충돌 해결자는 “두 코드를 모두 살리는 것”을 목표로 하지 않는다. 상위 문서와 계약에 맞는 하나의 판정을 남기고 중복 판정은 제거한다.

---

## 7. 통합 Gate 0~6

### Gate 0 — 기준선 무결성

통과 조건:

- 깨끗한 checkout에서 `import main` 성공
- 백엔드 `/health` 200
- 프론트 타입 검사·빌드 성공
- 통합 전후 `dev`의 미커밋 파일 0
- 기준 커밋, 적용 커밋, 실행 환경을 증적에 기록

실패 시: 통합하지 않고 원 작업자에게 기준선 결함을 반환한다. 선택적 import로 기능 부재를 숨기지 않는다.

### Gate 1 — 원자 커밋 집중 회귀

U1 적용 후:

- `tests/test_ontology_runtime.py`
- `tests/test_app_policy.py`
- G1-B PDP·ResourceScope 관련 테스트

U2 적용 후:

- `tests/test_ontology_control.py`
- 온톨로지 모델 설치·지문·무결성·승인 상태 회귀

실패 시: 실패한 단위까지만 되돌리고 다음 단위를 적용하지 않는다.

### Gate 2 — 계약 정합

다음 표의 생산자와 소비자가 같은 뜻을 갖는지 검사한다.

| 계약 | 생산자 | 소비자 | 필수 검증 |
|---|---|---|---|
| ResourceScope | G1-B/I-4 | G2 관계 런타임 | tenant·entity mode·scope·상태 |
| 계약 지문 | I-4 Compiler/물질화 | Host Proof·G2 참조 | 원문·물질화 지문 각각 봉인 |
| 객체 범위 | ECM/MDM/Snapshot | G2 path/evidence | 누락·장애는 0건이 아니라 503 |
| 승인 | Decision Ledger | G2 approve | 문자열 ID만으로 승인 금지 |
| 데이터 역할 | BDR | G4/경영 집계 | Actual·Scenario·Derived·Synthetic 혼합 금지 |

### Gate 3 — 보안·오류 계약

필수 부정 시나리오:

1. 다른 tenant 관계·객체 접근
2. 다른 scope 중간 노드가 있는 경로
3. 미승인·만료·폐기 관계
4. Resolver 누락·장애
5. Decision Ledger 승인 사건 불일치
6. 계약 지문·물질화 지문 변경 후 오래된 proof
7. 미바인딩 데이터와 `UNMODELED` 유형

판정 원칙:

- 존재를 볼 수 없음: 404 또는 응답에서 완전 제외
- 사용자가 자기 문맥을 선택하지 않음: 조치 가능한 409
- 서버가 판정할 수 없음: 503
- 미측정·조회 실패: 0건으로 표시 금지
- 숨긴 자원의 개수·사유: 권한 없는 응답에 노출 금지

### Gate 4 — 실서버 카나리

- 운영 DB가 아닌 별도 worktree·별도 DB·별도 포트
- `create_router(runtime)`에 제품 Resolver를 실제 주입
- 정상 인증·권한 부족·다른 조직·Resolver 장애를 HTTP로 확인
- 카나리 절차와 코드 지문을 함께 보관
- 운영 DB 파일 지문 불변 확인

### Gate 5 — 브라우저 E2E

- 실제 로그인 세션
- 회사·사업부·공장 문맥 선택
- 경영 질문 입력
- 온톨로지 경로와 근거 표시
- 계산 요청과 결과 표시
- 조회 실패·계산 전·승인 대기 상태를 서로 다르게 표시
- 가로 넘침·잘림·12px 미만·키보드 접근 검사
- DOM 측정뿐 아니라 1280×720, 1440×900 이미지 확인

### Gate 6 — 첫 수직 폐루프 시연

최소 시연 흐름:

```text
원료 도입계획 또는 레거시 Snapshot
→ 환율·운임·도착 지연 시나리오
→ 원료·생산·재고·판매·현금·손익 영향 경로
→ 결정론적 수치 계산
→ 세 관점 검토서
→ 의사결정 회의 요청
→ 실행과제·책임자·기한
→ 전사 브리핑 또는 대내외 보고서
```

모든 숫자는 `DEMO_ONLY`, `SYNTHETIC`, `REFERENCE`, `CERTIFIED` 중 하나의 상태를 보여야 한다. 합성값을 Actual처럼 표시하면 시연 불합격이다.

---

## 8. 중단 조건

다음 중 하나라도 발생하면 통합을 즉시 멈춘다.

1. `dev` 또는 통합 worktree에 소유자 불명의 미커밋 변경이 생김
2. Claude Code의 I-4 3단계가 커밋·테스트 없이 진행 중임
3. 깨끗한 checkout에서 백엔드 import 또는 프론트 build 실패
4. DB 마이그레이션이 원본 운영 DB를 요구함
5. 권한 불일치를 “테스트를 고쳐서” 통과시키려 함
6. 404·403·409·410·503의 의미가 기존 계약과 달라짐
7. Resolver 장애가 0건 또는 빈 경로로 보임
8. 계약·물질화·모델 지문 중 하나가 봉인되지 않음
9. merge commit을 cherry-pick해야만 통합된다고 판단됨
10. 전체 테스트는 통과하지만 API가 mount되지 않거나 UI가 호출하지 않음

중단은 실패가 아니라 회귀 원인을 좁히기 위한 정상 통제다.

---

## 9. 롤백 계획

### 9.1 통합 브랜치 안에서

- 적용 직전 로컬 기준 커밋 ID를 증적에 기록한다.
- 실패한 cherry-pick은 통합 worktree에서만 중단·폐기한다.
- 이미 커밋된 통합 단위는 해당 단위만 `revert`하거나 통합 브랜치를 최신 `dev`에서 다시 만든다.
- 메인 `dev`에는 `reset --hard`, 강제 checkout, 재작성 rebase를 사용하지 않는다.

### 9.2 `dev` 승격 후

- 승격은 fast-forward만 허용한다.
- 승격 직전 `dev`가 움직였다면 fast-forward를 강행하지 않고 통합 브랜치를 새 기준선에서 재검증한다.
- 운영 데이터 마이그레이션은 별도 승인 전 수행하지 않는다.
- 제품 mount 커밋과 기능 커밋을 분리해 mount만 되돌릴 수 있게 한다.

---

## 10. 팀별 역할과 인계

| 단계 | 주 책임 | 교차검토 | 산출물 |
|---|---|---|---|
| I-4 3단계 완료·기준선 | Claude Code | Codex | 원자 커밋·테스트·잔여사항 |
| G2 기능 커밋 | Codex | Claude Code | 커밋 2개·집중 회귀 |
| 계약·Scope·Approval 연결 | Claude Code | Codex·Antigravity | 어댑터·부정 시나리오 |
| DB·데이터·카나리 감사 | Antigravity | Claude Code | 사본 이행·오염·텔레메트리 |
| 제품 API·UI 연결 | Codex | Claude Code | mount·route·화면 E2E |
| 시연 데이터 상태·사업 판단 | Supervisor | 전원 | DEMO/CERTIFIED 경계·최종 승인 |

한 사람이 자기 작업을 스스로 고치고 검토하는 것은 허용한다. 교차검토는 진행을 막는 사전 대기가 아니라 C2~C5 위험 단위의 승격 Gate로 사용한다.

---

## 11. 커밋 규칙

### 허용 예시

```text
feat(G2): integrate governed ontology runtime
feat(G2): wire product scope and approval resolvers
feat(G2): mount ontology API after fail-closed canary
feat(UI): add management impact demo workspace
test(E2E): prove purchase-to-profit closed loop
docs(handoff): record integration evidence and residual work
```

### 금지

- 코드·DB·UI·문서를 한 커밋에 혼합
- 다른 팀원의 미커밋 파일 포함
- “conflict fix”처럼 무엇을 선택했는지 알 수 없는 메시지
- merge commit 자체를 기능 단위로 사용
- 테스트 실패 상태 커밋을 다음 작업의 기준선으로 사용

---

## 12. 통합 증적 파일

각 통합 회차는 다음 정보를 `docs/handoff/`의 회차별 기록에 남긴다.

```yaml
integration_id: MVP-INT-YYYYMMDD-NN
author: 이름
reason: 왜 지금 통합하는가
base_commit: dev 기준선
applied_commits:
  - 커밋 ID와 목적
excluded_commits:
  - 제외한 커밋과 이유
conflicts:
  - 파일·계약·판정·해결자
gates:
  gate_0: PASS|FAIL|NOT_RUN
  gate_1: PASS|FAIL|NOT_RUN
  gate_2: PASS|FAIL|NOT_RUN
  gate_3: PASS|FAIL|NOT_RUN
  gate_4: PASS|FAIL|NOT_RUN
  gate_5: PASS|FAIL|NOT_RUN
  gate_6: PASS|FAIL|NOT_RUN
tests:
  focused: 결과
  full: 결과
  frontend: 결과
  browser: 결과
data_safety:
  production_db_touched: false
  fixture_classification: DEMO_ONLY
residual:
  - 남은 작업·담당·착수 조건
promotion_decision: HOLD|APPROVED
```

TEAM_BOARD에는 위 전문을 복사하지 않고 작성자·시각·근거·Gate 결과·다음 행동·인계 문서 경로를 기록한다.

---

## 13. 3주 운영 타임테이블

### 1주차 — 안전한 통합 기반과 G2 제품 연결

| 일자 | 작업 | 출구 조건 |
|---|---|---|
| D1 | Claude I-4 3단계 원자 커밋·기준선 정리 | Gate 0 |
| D2 | U1·U2 선별 적용 | Gate 1 |
| D3 | Scope·Approval Resolver | Gate 2·3 |
| D4 | API mount·실서버 카나리 | Gate 4 |
| D5 | G2 경로 화면과 브라우저 E2E | Gate 5 일부 |

### 2주차 — G4 계산과 시연 데이터

- 원료 도입 지연 대표 관계 Fixture
- 외부 지표·Master·Legacy Snapshot·AFS Native 데이터 분류
- 기존 Planning Engine·Calc Bridge 재사용
- 환율·운임·도착 지연 → 생산·재고·현금·손익 계산
- 계산 근거·버전·Snapshot·온톨로지 경로 함께 표시

### 3주차 — 폐루프 완주와 리허설

- 경영 질문 → 영향 경로 → 수치 → 검토서 → 회의 요청
- 실행 책임·기한·영향 부서
- 전사 브리핑·보고서 출력
- 실패 상태·권한·조회 불가 UX
- 1280/1440 시각 감사
- 시연 스크립트·백업 영상·FAQ·중단 기준

---

## 14. 진척 시각화 기준

모든 완료 보고는 기능 목록만 나열하지 않고 아래 두 축을 함께 표시한다.

### 14.1 통합 진척

```text
기준선 정리           ░░░░░░░░░░  0/1  Claude I-4 3단계 진행 중
G2 원자 커밋 적용     ░░░░░░░░░░  0/2  통합 미실행
계약·Resolver 통합    ░░░░░░░░░░  0/2
제품 API·UI 연결      ░░░░░░░░░░  0/2
첫 수직 E2E           ░░░░░░░░░░  0/1
Gate 통과             ░░░░░░░░░░  0/7
```

### 14.2 병렬 구현 진척

```text
Host Runtime / I-4      ████████░░  3단계 진행 중
BDR 출처·중복입력       ████░░░░░░  BDR-1 완료 · BDR-2~7 잔여
G2 관계 거버넌스        ██████████  핵심 런타임 완료
G2 모델 계약·REST       █████████░  제품 Resolver·mount 잔여
G4 원료구매 계산        ░░░░░░░░░░  미착수
시연 UI·폐루프          ░░░░░░░░░░  미착수
```

진척률은 제품 완성도를 뜻하지 않는다. “코드가 존재함”, “제품에 연결됨”, “실제 시나리오가 완주함”을 서로 다른 상태로 유지한다.

---

## 15. 즉시 다음 행동

1. Claude Code가 I-4 3단계 작업을 자체 커밋하고 `dev`를 clean 상태로 만든다.
2. Claude Code 인수인계에 기준 커밋·변이 검사·전체 테스트·잔여사항을 기록한다.
3. Codex가 최신 `dev`에서 통합 전용 worktree를 생성한다.
4. `37ca74c0c` → 집중 회귀 → `110e9bb4d` → 집중 회귀 순으로 적용한다.
5. Claude Code가 G1-B/I-4와 G2의 계약 정합을 검토한다.
6. Antigravity가 DB 사본·Scope·숨김·오염 관점의 독립 감사를 수행한다.
7. Gate 0~4가 통과한 뒤에만 `main.py`와 제품 UI를 연결한다.
8. Gate 5~6까지 통과한 통합 브랜치만 깨끗한 `dev`에 fast-forward한다.

---

## 16. 현재 판정

```text
병렬 구현 가능성       PASS   파일 소유 경계가 분리되어 있음
즉시 통합 가능성       HOLD   dev에 Claude Code 미커밋 3단계 변경 존재
통합 방식              확정   clean worktree + 선별 cherry-pick + 단계별 Gate
origin 작업            금지   사용자 별도 명시 없음
제품 시연 준비도       진행   G2 코어 존재, G4·제품 연결·E2E 잔여
```

현재 가장 중요한 다음 조건은 **Claude Code의 I-4 3단계 원자 커밋과 깨끗한 기준선 확보**다. 그 조건이 충족되는 즉시 본 계획의 Gate 0부터 통합을 실행한다.
