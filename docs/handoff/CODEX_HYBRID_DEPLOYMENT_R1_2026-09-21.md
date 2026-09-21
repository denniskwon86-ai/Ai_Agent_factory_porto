# 하이브리드 배포관리 R1 보완 인계 — 2026-09-21

작성: Codex. 사용자 지시: DEP-P1/P2 검토를 Claude에게 인계한 뒤 배포시스템 설계 보완 재개.
로드맵: 권고14개를 새로 재번호하지 않음. 사용자 명시 지시로 G7-B/C 운영화의 구현 전 계약을 보완한다. 첫 수직 폐루프의 실사용 수용을 대신하지 않는다.

## 1. 보완 범위

상세 설계, OpenAPI, 구현 인계서가 R1 정본이다. 기존 독립 검토는 당시 CHANGES_REQUESTED 기록으로 보존한다. 보완본 재검토 결과와 구조 검증은 아래에 따로 기록한다. 제품 코드/운영 DB/GitHub/NCP/실자료/커밋·푸시는 변경하지 않는다.

| 원 지적 | 보완 |
|---|---|
| SEC-01 | 작성자만 자기 user token으로 dispatch; session/plan/token/run/OIDC numeric ID 일치, UNKNOWN 재결속도 동일 |
| SEC-02 | 승인 대기 후 최초 claim 직전 실제 repo write 이상/환경 operator/명시 회수 재확인, 조회 불가 차단 |
| EXE-01 | AgentMtls execution-context 조회, plan/fence/환경/slot/다음 단계/5초 freshness, 종료 claim 거절 |
| EXE-02 | observe 수락 시 RELEASED; 실행 lease60초와 읽기 대조600초 분리, 환경 잠금 보존 |
| EXE-03 | artifact 적격과 환경별 실행 가능성 분리; 첫 staging 허용, trial만 같은 digest staging 증거 요구 |
| EXE-04 | CLEANUP_ONLY + cleanup_candidate, 해당 inactive slot만 정리·실측 후 FAILED 원자 기록 |
| INT-01/02 | DEP/OPS 작업 번호·의존성 분리, file index와 full manifest 구분 |
| DEP 검토 | 관리 DB 기본 fallback/startup DDL 금지, 실제 노드 관측, fail-closed, 원자 완료/새 복귀 계획 |

화면도 can_dispatch/execution_mode/finalization_deadline 및 환경별 preflight를 사용한다. “서버 변경 완료·결과 확인 중”과 “배포 완료”를 구분하고 메뉴3개/자체 승인 없음/Codex 로컬→PR 경계는 유지한다.

## 2. 검증 및 독립 재검토

**R1 보완 완료. 지정6건 독립 재검토는 범위 한정 PASS이며, 전체 시스템/보안 인증이나 운영 배포 승인이 아니다.**

| 검토자 | 범위 | 결과 |
|---|---|---|
| Kepler — 별도 Codex 실행 문맥 | SEC-01/02, EXE-01: 요청자·회수·mTLS 실행 문맥 | 추가 P1/P2 구체 반례0, 범위 한정 PASS |
| Laplace — 별도 Codex 실행 문맥 | EXE-02/03/04: 실행 종료/대조·환경 적격·제한 정리/원자성 | 추가 P1/P2 구체 반례0, 범위 한정 PASS |

두 검토자는 읽기 전용으로 실제 보완 파일을 읽었다. 다른 공급자/Claude/사람 검토로 표기하지 않는다. Laplace가 재대조한 기준본 SHA-256 앞12자리: 설계93F874386B2D, API77CD04D66FDF, 구현 인계FEB70380CFB0. 이후 변경은 상태/재검토 링크 표기와 인계의 축약 OPS 번호 확장뿐이며 인증·실행 계약은 동일하다. Claude의 구현자 관점 검토와 실제 수용은 후속이다.

직접 실행:

```powershell
venv/Scripts/python.exe -X utf8 -B docs/design/contracts/verify_deployment_control_contract.py
```

- 경로17 / 동작19 / schema31 / 내부 참조175: 구조 검사 PASS.
- JSON Schema 정상·거절 예제23건 PASS: 다른 mode·정리 전용 단계·종료 claim·추가 필드·빈 증거·잘못된 backend 등.
- 불변 plan의18필드 canonical JSON/SHA-256 재계산 일치. 신규 실행/표시 필드를 plan digest에 잘못 섞지 않음.
- 수용 정의52개 ID 중복 없음. **52개 모두 제품 NOT_RUN.** 23개 schema 예제를 실행권/권한/DB/실서버 시험 통과로 합산하지 않음.
- Markdown 링크·code fence·작업 번호 정렬 검사 PASS. 로컬 검증기는 문서만 읽으며 제품 import/DB/네트워크/파일 쓰기 없음.
- 전체 OpenAPI 표준 validator·생성 클라이언트 빌드·HTTP 실행은 미수행. jsonschema Draft202012 기반 schema 및 경량 OpenAPI 구조 검증임.

자체 확인에서 잡은 것: 원 API의 일부 inline JSON과 patch 문맥 불일치/파일 순서 오류로 초기 패치가 거절되어 실제 문맥으로 수정했다. 첫 문서 검사도 새 표의 OPS-P2/P4 축약과 심각도 P1 구분에서 실패했다. 축약은 완전한 namespace로 고치고 심각도 예외를 분리한 뒤 재실행했다. 실패를 제품 결함이나 통과로 숨기지 않는다.

## 2.1 구현 착수에 대한 판정

기존6개 명세 지적에 대한 설계 보완은 닫는다. INT-01/02와 DEP 통합 경계도 작성자가 정본/인계에 대조했다. OPS-P1의 로컬 file index→full manifest·합성 계약 준비, OPS-P2의 별도 관리 DB/domain/fake API 구현을 위한 명세 기준본으로 사용할 수 있다. 실제 외부 실행을 열어도 된다는 뜻은 아니다.

계정/요금제/권한 API의 실제 증거가 없으면 GitHub adapter는 NOT_READY, LB/PG/업무 선행 미충족이면 trial은 비활성이다. UI가 있어도 이를 우회하지 않는다.

## 3. 다음 구현 및 진척

구현자는 `CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md` §11부터 읽고 정본/API를 대조한다. 최초30분에는 작업자 소유·DEP/OPS 경계·현재 차단을 확인하고 OPS-P1 file index→full manifest 연결을 준비한다. 정식 OPS-P2는 별도 PG/domain/API 계약으로 구현하며 폐기 예정 프로토타입을 먼저 완성하지 않는다.

전체 인정치21/40=52.5% 유지. 설계 수용 정의52개는 제품 NOT_RUN이다. 실제 private GitHub 보호·현재 권한 조회·PG/NN-1·LB·파일/작업/SSE·복구 증거 및 비용/실자료 승인은 별도 운영 차단으로 남는다.

다음 권고: OPS-P1 full manifest 연결의 첫30분 checkpoint → 로컬 CI/manifest 초안0.5~1인일. OPS-P2 관리 backend1~2인일은 명세 기준 fake/격리 환경부터 진행한다. 전체6~11인일 잠정은 외부 대기/업무 런타임 선행을 제외한 추정이며 납기 약속이 아니다. 이번에 실제 구현은 시작하지 않았다.
