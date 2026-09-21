# GitHub 하이브리드 배포관리 V1 — 독립 검토 기록

작성·취합: Codex · 2026-09-21 KST
사용자 요청: “네 독립 검토 진행해주세요”
최초 기준본 판정: 독립 검토 완료 — CHANGES_REQUESTED. 아래는 해당 기준본의 역사 기록이다.
후속 R1: 지정6건 보완·범위별 재검토 결과는 [R1 인계](CODEX_HYBRID_DEPLOYMENT_R1_2026-09-21.md)를 따른다. 이 문서의 원 지적/기준본 hash를 소급 변경하지 않는다. 실제 운영 배포 승인은 별도다.

## 1. 검토 방식과 범위

- 검토 A: Mill — 인증·권한·GitHub 승인·OIDC·실행권의 신뢰 경계.
- 검토 B: Gibbs — OpenAPI/상태·경쟁·실행기·복구 계약의 구현 가능성.
- 두 검토자는 작성 대화 전체를 전달받지 않은 별도 Codex 실행 문맥에서 읽기 전용으로 검토한다. 다른 공급자의 Claude/Gemini 검토나 사람의 보안 인증을 대신했다고 주장하지 않는다.
- 주 작성자 Codex는 기준본·근거를 보존하고 지적 사항을 대조한다. 자신의 보완 의견은 독립 검토자 결과와 구분한다.
- 실제 제품 구현/HTTP 실행/PG/배포·GitHub 설정 변경은 범위 밖이다.
- 로드맵 위치: 사용자 명시 지시에 따른 G7 운영화 상세 설계 검토. 제품 수직 폐루프 및 실제 운영 수용을 대신하지 않는다.
- 전체 인정치: **21/40 = 52.5% 유지**.

### 검토 기준본 SHA-256

| 파일 | SHA-256 |
|---|---|
| docs/design/DEPLOYMENT_CONTROL_PLANE_V1_2026-09-21.md | 8198912052481d6a545241f860965c9ec5b1e48c0966049b871b56e3d638320c |
| docs/design/contracts/deployment-control-v1.openapi.json | fb4b04c086524025b64e3f4c2fa250c2dc8a724010b02e48c6a295a971acdb0b |
| docs/handoff/CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md | 4ef1d9523d636bc11462806b4ce060d7674ad85c146895889a64bd49e4535cf3 |

검토 중 위 정본은 수정하지 않는다. 현재 보고서와 공유 보드의 검토 기록만 작성한다.

## 2. 재확인한 기초 증거

- API JSON 파싱·내부 참조159개·plan 정답 hash 재계산: 일치.
- API 동작18개. 이 숫자는 실제 API가 구현됐거나 동작했다는 증거가 아니다.
- 42개 수용 사례는 여전히 **정의만 된 NOT_RUN**이다.
- 원격 GitHub 플랜/Environment 보호, actual runner/NCP LB, 실제 PG, 무중단 및 backup restore: 이번 검토에서 미실행.
- 현재 진행 중인 Claude 작업은 보존한다. 다른 세션의 파일은 변경하지 않는다.

## 3. 주 작성자 추가 확인 — 병행 작업 연결

이 절은 독립 검토자 findings가 아니라 취합 과정에서 확인한 인계 문제다.

### INT-01 [P2] 같은 P2/P3가 서로 다른 작업을 뜻한다

근거:

- [기존 준비 패킷](CODEX_DEPLOYMENT_PREP_PACKET_2026-09-21.md) 32~39행: P2=두 슬롯/readiness, P3=전환/복구.
- [신규 구현 인계](CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md) 47~49행: P2=관리 backend, P3=UI, P4=GitHub/agent 연결.
- [Claude P1 인계](CLAUDE_P1_ARTIFACT_CONTRACT_2026-09-21.md) 139~143행은 기존 P2=슬롯을 다음 작업으로 사용한다.

영향: “P2 계속”이라는 지시가 기존 서버 준비 대신 관리 backend 착수로 해석될 수 있다. DB/엔진 준비를 UI 완성 때문에 늦추지 않는 원칙과 충돌할 수 있다.
보완 권고: 기존은 DEP-P1~3, 신규는 OPS-P0~7처럼 구분하고 명시적 의존성 표를 넣는다. 기존 Claude 산출물을 폐기하거나 처음부터 재작성하지 않는다.
수용: 두 문서를 읽은 구현자가 “다음 작업”의 파일·완료 조건을 하나로 식별할 수 있어야 한다.

### INT-02 참고 — 기존 P1은 새 release 계약 전체를 충족한 것이 아니다

현재 scripts/release_artifact.py의 build_manifest(303~315행)는 file_count와 경로별 hash/bytes 목록을 만든다. 이는 재사용할 **file index**이며 새 설계 §3.1의 release manifest 전체와는 다르다.
추가로 필요한 항목: archive digest, 정확 runtime/lock, source/build/workflow 신원, SBOM/provenance, schema 호환, 동등 staging 증거, 실제 Linux 실행.
Claude도 CI 미실행·XLSX 36개 내용 미검사·자산 출처 미확인을 명시했다. 이를 거짓 완료 보고로 판정하지 않는다. 다만 해당 근거만으로 새 release eligible=true를 부여할 수 없다.
starter kit의 출처 확인/배포 허용은 기존 검사기의 경로 예외만으로 대체하지 않는다. 실제 자료 전송 승인과 제품 자산 분류가 필요하다.
기존 update.sh를 무중단 trial CD로 연결하지 않는 상위 제한도 유지한다.

## 4. 독립 검토 결과와 대조 판정

**최종 판정: CHANGES_REQUESTED — 현 문서 그대로 구현 승인하지 않음.**
독립 검토자 고유 지적6건을 수용했다. 중복인 agent 실행권 조회 누락은1건으로 합쳤다.
최종 분류는 **P1 4건 + P2 2건**, 취합자가 발견한 INT-01(P2)까지 포함하면 **P1 4건 + P2 3건**이다.
실제 보안 침해·운영 장애를 재현한 결과가 아니라, 설계 규칙대로 구현할 때 발생하는 계약 결함/반례다.

| ID | 등급 | 원 검토자 | 판정 요약 |
|---|---|---|---|
| SEC-01 | P2 | Mill A-01 | 작성자/최종 배포 요청자/GitHub 실행자의 결속 정책 누락 |
| SEC-02 | P1 | Mill A-02 | 승인 대기 후 권한 회수의 최초 실행권 발급 차단 규칙 누락 |
| EXE-01 | P1 | Gibbs B-01 + Mill A-03 | agent mTLS 실행권·불변 계획 조회 API 없음 |
| EXE-02 | P1 | Gibbs B-02 | 정상 실행 종료와 완료 대조 대기의 lease 수명 충돌 |
| EXE-03 | P1 | Gibbs B-03 | staging 배포가 자신의 이전 성공 증거를 요구하는 순환 |
| EXE-04 | P2 | Gibbs B-04 | 전환 전 candidate 실패의 정리 명령/책임 누락 |
| INT-01 | P2 | 주 작성자 Codex | 기존/신규 P2·P3 작업 번호 중복 (§3) |

### SEC-01 [P2] 실제 배포 요청자의 신원 기준을 하나로 고정해야 한다

근거: 상세 설계141~149행은 작성자를 actor_id로 고정한다. 104~112행·236행은 operator의 dispatch를 허용하며 작성자 한정 규칙이 없다. 99행은 사용자 token, 293~295행은 OIDC 대조지만 actor_id 대조는 없다. API2438~2440행에는 Plan.actor_id만 있고 dispatcher는 없다.

시나리오: A 작성 → B가 자기 token으로 dispatch → A가 승인. GitHub의 자기승인 금지는 run을 시작한 사람 기준이므로 B가 시작한 run을 A가 승인하는 것은 GitHub 기준으로 정상일 수 있다. [공식 Environment 설정](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

정정: 검토 A의 첫 요약은 P1이었다. 상세 대조 후 검토자가 **P2로 정정**했다. “작성자가 승인했으니 자기승인 우회”라고 확정하지 않는다. 문제는 UI/감사/권한 회수의 요청자는 A인데 실행자·GitHub 승인 제외 기준은 B가 되는 **미정의된 신원 분리**다.

최소 보완 권고: V1에서는 작성자만 dispatch하도록 principal=plan.actor_id=run/OIDC.actor_id를 고정하는 단순안이 적합하다. 별도 operator 실행을 허용하려면 created_by와 requested_by를 분리하여 불변 실행 요청·사용 토큰·회수·승인 제외 대상을 명시해야 한다. 어느 안도 이번 검토에서 구현하거나 정책 확정하지 않았다.
공식 OIDC는 실행 시작자의 actor_id를 제공한다. [OIDC claim 정의](https://docs.github.com/en/actions/reference/security/oidc).

수용 IR-01: A작성/B실행을 선택한 정책대로 거절하거나 B 요청자로 일관되게 기록. 정상 run 응답과 DISPATCH_UNKNOWN 후 결속 모두 actor 불일치를 거절. 승인자 제외 기준도 같은 신원을 사용.

### SEC-02 [P1] 승인 대기 중 권한이 회수된 요청을 claim 단계에서 다시 차단해야 한다

근거: 상세 설계100행·260행은 dispatch/outbox 전의 권한 확인만 명시한다. 292~295행의 claim 검사에는 요청자 현재 권한이 없다. 153행의 재검사라는 일반 문구만으로는 무엇을 검사하는지 고정되지 않는다. 기존 수용 A04는 사용자의 idempotency 재시도만 시험한다.

시나리오: 정상 요청 → 승인 대기 → 요청자의 저장소 접근 또는 환경 operator 회수 → reviewer 승인 → 유효 OIDC/승인 증거를 가진 runner가 claim 요청. 열거된 검사만 구현하면 회수 후 새 실행권이 생길 수 있다.
GitHub가 실제로 회수 후 job을 반드시 실행한다는 주장이 아니다. Control이 그 입력을 받았을 때 독립적으로 차단할 계약을 요구한다.

최소 보완: SEC-01의 실제 요청자를 기준으로 최초 claim 직전에 현재 repository 접근·환경 operator·명시적 회수 상태를 조회. 조회 불가도 fail-closed. 로그인 세션 만료와 명시적 권한 회수는 구별한다. 이미 실행 중인 작업의 강제 종료로 범위를 확대하지 않는다.
수용 IR-02: 승인 대기 후 repository 회수/operator 제거/권한 조회 장애를 각각 주입. 나머지 OIDC/승인은 유효하게 유지하고 claim0·agent 변경0 확인. 사용자 재시도가 아닌 runner 경로로 시험.

### EXE-01 [P1] agent가 요구받는 live claim 확인을 수행할 API가 없다

근거: 상세 설계304행은 agent가 Control의 live claim을 확인한 뒤 실행하도록 한다. 444행의 agent 입력은 plan_id/claim_id/fence/step뿐이다. API1226~1237행 heartbeat는 runner OIDC 전용, 1452~1462행의 agent mTLS API는 관측 POST뿐이다. 불변 실행 계획은 runner의 Claim 응답에만 있다.

시나리오: 정상 runner가 claim 후 install을 보내도 agent는 현재 lease·fence·설치 대상을 자기 인증으로 얻을 계약이 없다. fail-closed면 첫 설치가 막히고, 우회하면 구현자마다 DB 직접 읽기/임의 토큰 전달 등 다른 보안 경계를 만든다.
분류: Mill은 P2, Gibbs는 P1. 필수 정상 실행이 계약상 불가능하다는 근거로 최종 **P1**로 수용했다. 이미 우회가 발생했다는 뜻은 아니다.

최소 보완: agent mTLS 전용 검증/실행 문맥 조회 API를 OpenAPI에 정의. 인증서 환경, claim/plan/fence, 현재 lease, 허용 다음 단계, 불변 plan과 결과 freshness를 명시한다. runner의 주장만 믿거나 agent에 사용자 세션/runner OIDC를 넘기지 않는다.
수용 IR-03: 정상 mTLS agent의 문맥 취득·실행. 다른 환경 인증서/old fence/만료 lease/선행 단계 누락/Control 장애는 변경 전에 거절.

### EXE-02 [P1] 실행권 종료와 GitHub 완료 확인 대기를 분리해야 한다

근거: 상세 설계301행 lease60초, 440행 observe 이후 FINALIZING에서 job 종료/GitHub success 대기. 251행은 PREPARING 이후 비종료 상태의 lease 유실을 RECOVERY_REQUIRED로 보내고, 253행은 이를 불변 종료 상태로 규정한다.

반례: 모든 실제 단계 성공 → runner 정상 종료로 heartbeat 종료 → GitHub 조회가90초 지연 →60초 lease 만료 → RECOVERY_REQUIRED → 정상 증거가 늦게 도착. 실제 운영이 정상이어도 일반 성공으로 닫지 못하고 수동 복구를 요구한다.

최소 보완: 최종 영수증 수락 시 실행 claim을 명시적으로 종료하여 추가 변경을 금지한다. 환경 잠금은 보존하고 GitHub/agent 실측의 **읽기 전용 완료 대조**는 계속한다. 실행권 상실과 최종 결과 조회 지연에 서로 다른 시간 제한/판정 규칙을 둔다. 살아 있는 실행 lease를 무한 연장하는 해법은 금지한다.
수용 IR-04: 가상 시계에서 정상 runner 종료+90초 결과 지연을 재현. SUCCEEDED 단1회, 종료 claim의 추가 명령0. 실제 증거 불일치나 중간 실행권 유실은 별도 RECOVERY_REQUIRED로 유지.

### EXE-03 [P1] staging 실행 적격과 trial 승격 적격을 분리해야 한다

근거: 상세 설계134행은 staging 후 같은 digest를 trial로 승격한다고 한다. 그런데 공통 실행 사전검사311행은 환경 구분 없이 “동일 digest staging 통과”를 요구한다. 324행의 첫 설치 예외도 구 slot 처리만 제외하고 나머지 검사는 유지한다.

반례: 새 digest D에 staging 성공 증거 없음 → 최초 staging 자체 BLOCKED → 실행할 수 없어 증거도 생성 불가. “원래 trial만 뜻했다”는 암묵적 해석으로 구현하게 해서는 안 된다.

최소 보완: staging은 trusted artifact/호환/안전 준비 증거로 실행 가능하게 하고, **동일 digest staging 성공은 trial 승격의 추가 조건**으로 고정한다. API Release.eligible의 의미도 환경별 판정인지 기본 artifact 적격인지 명시한다. 이를 원격 실행 승인 생략으로 해석하지 않는다.
수용 IR-05: D staging 실행 가능 → 증거 전 D trial 차단 → staging 성공 후 동일 D trial 가능 → 다른 digest D2에는 증거 재사용 불가. 최초 설치/일반 배포 모두 확인.

### EXE-04 [P2] candidate 정리의 책임·명령·영수증을 명시해야 한다

근거: 상세 설계250행은 candidate 종료와 기존 서비스 불변을 입증해야 FAILED로 닫는다. 303행·444행의 고정 명령에는 candidate 종료가 없고, verify 실패의 내부 보상 책임도 명시되지 않았다. 인계서 E04는 이 흐름을 수용 조건으로 요구한다.

반례: candidate 프로세스는 살아 있지만 readiness 실패, LB는 Blue 유지. 어느 컴포넌트가 어떤 권한으로 candidate만 종료하고 이를 증명하는지 구현자마다 달라진다.

최소 보완: 실패 단계 내부 보상 또는 고정된 제한 정리 단계 중 하나를 명문화한다. 대상은 해당 claim이 설치한 inactive slot로 한정하고 active slot/DB down migration은 제외한다.
수용 IR-06: candidate만 종료·Blue 지속, 정리 재전송 멱등, 정리 결과 불명은 RECOVERY_REQUIRED/잠금 유지. 증거 없는 FAILED 종결 금지.

## 5. 최종 판정·다음 작업

### 판정

- 하이브리드 방향을 폐기하거나 자체 UI/CS/API 방식을 다시 선정할 이유는 이번 검토에서 발견하지 않았다.
- **독립 검토는 완료했으나 설계는 조건 미충족이다.** 위6건의 계약 보완과 INT-01 번호 정리 후 재검토해야 한다.
- private GitHub 승인 기능·NCP LB API·실제 PG 등 이미 명시된 외부 미확인 사항은 결함 건수에 중복 합산하지 않는다.
- 제품 구현/실환경 우회 시험은 NOT_RUN. 설계 결함 발견을 실제 보안 사고로 보고하지 않는다.
- 기준본3개와 제품 코드는 수정하지 않았다. 이번 쓰기는 이 검토 기록과 TEAM_BOARD 인계 기록뿐이다.

### 보완 순서 권고

1. SEC-01의 최종 요청자 기준 고정 → SEC-02 회수 재검증.
2. EXE-01 agent 인증 API와 실행 문맥 schema 확정.
3. EXE-02 실행 claim 종료/읽기 전용 최종 대조 수명 분리.
4. EXE-03 환경별 preflight 표, EXE-04 제한 정리 단계.
5. INT-01 작업 번호 namespace, 기존 file index의 새 manifest 연결 지도.
6. OpenAPI·DB 필드·수용 IR-01~06과 기존42개 일관성 검사 → 독립 재검토.

예상: **설계/API 보완60~90분 + 독립 재검토20~30분**. 제품 구현·실제 GitHub/PG/NCP 검증 시간은 포함하지 않는다.
사용자 요청은 검토이므로 이번 턴에서 보완 설계나 제품 변경을 시작하지 않는다.
Claude의 DB 이관/읽기 전용 자산 조사/독립적인 CI 계약 준비는 계속 가능하다. 충돌하는 실행권·완료 상태·승격 API는 보완된 정본을 받기 전 확정 구현하지 않는 것이 안전하다.
전체21/40=52.5%는 유지하며, G7의 **구현 전 설계 결함 식별**을 전진시켰다. 실제 배포 준비 완료 칸을 추가하지 않는다.
