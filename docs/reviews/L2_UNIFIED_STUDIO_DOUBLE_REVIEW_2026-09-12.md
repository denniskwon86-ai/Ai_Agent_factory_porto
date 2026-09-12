# L2·단일 SW 제작 화면 독립 이중검토 기록

- 요청자 / 기록자 / 시각: 사용자 요청 → Codex / Codex / 2026-09-12 20:28 KST
- 목적: 상세 설계·계획을 구현 전에 독립적으로 검토하고 지적별 반영·재확인을 추적한다.
- 기준: `codex/l2-unified-studio-20260912` / 코드·기존 문서 기준 `574c26fd8`.
- 대상: `docs/design_l2_unified_studio_execution_2026-09-12.md`.
- revision1 SHA-256: `05ee56f7878335b06c569b9a3ba9dc350cf700a93bc1ad384e164ce12c48c204`.
- revision2 SHA-256: `c45c19b53b9b2e7777c5e58395f9b3014c691472c01b40a553b6f997e6eab57b`.
- revision2.1 재확인 원문 SHA-256: `118365a75a3ba29a0a3ec16b22c21de6422a70632c009782fa77af0c2e4c3b52`.
- 최종 기록 시각: 2026-09-12 20:38 KST. 재확인 후 설계 문서의 표제 상태 한 줄만 PASS로 갱신했다.
- 실제 방법: 서로 다른 독립 에이전트가 문서와 현행 소스를 읽기 전용 검토.
  작성자 자체검토와 구별하며 실제 Claude/Gemini·현업·운영 보안 승인으로 표시하지 않는다.

## 1. 독립 검토자와 첫 판정

| 검토 | 검토자/ID | 범위 | 첫 판정 |
|---|---|---|---|
| A | Pauli / `01a0954c-072d-7d80-aa2d-aa499046859e` | 데이터·아키텍처·구현 가능성 | CHANGES_REQUIRED, P1 5건/P2 1건 |
| B | Faraday / `01a0954c-07d7-7be2-bea3-e16d7a9ada50` | 현업 UX·문맥/입력·기능 전환/검증 | CHANGES_REQUIRED, P1 5건/P2 1건 |

두 검토의 원래 판정을 PASS로 덮지 않는다. 아래 조치와 후속 재확인을 별도로 기록한다.
전체 P0 확인 없음, P1 10건, P2 2건. 새 결함 전체 수 또는 완전한 보안 감사 결과를 뜻하지 않는다.

## 2. 지적·반영·수용 시험 추적

| ID | 심각도 | 확인 근거/실패 시나리오 | revision2 문서 반영 | 추가 명세 |
|---|---|---|---|---|
| A-1 | P1 | store.transaction/get/list의 명시 read transaction 부재. 같은 연결의 snapshot/hold SELECT도 시점 혼합 가능 | §9 B0-A: projection 생산자 포함, 첫 SELECT 전 읽기 transaction·복수행·독립 연결 경쟁 | U19 |
| A-2 | P1 | 인증 GET/POST는 일반 관리권만 확인. snapshot 가시성/서명 종류별 적격성 부족 | §9 B0-B: 대상404·종류별 역할/위임·정책 미정 차단·동일인 예외 정책 | U20 |
| A-3 | P1 | 상이한 기간 요청을 무시하고 같은 snapshot의 서명으로 합칠 수 있음 | §9 B0-B: 불변 certification subject·기간/용도409·정책/소유권 변경·원자/멱등 | U21 |
| A-4 | P1 | project aggregator/compiler가 문맥을 잃거나 전역 schema 변경이 기존 해시를 깨뜨림 | §8.4: 실제 생산자→Host 대응,1.0 해시/승인 보존·별도2.0·서버 버전 선택 | U22 |
| A-5 | P1 | advisor upsert/승인 CAS 없음·bootstrap 재시도 새ID·meta 저장 예외 삼킴 | §8.5: immutable approved revision·승격 operation/고정ID·단계별 실패/복구·실행 차단 | U23 |
| A-6 | P2 | SealedDatasetError가 project API의 ProjectDataBindingError 경계에 연결되지 않아 보류가500으로 보일 가능성 | §9 B0-A: 구조화 예외→409/503/404·프로젝트 미생성 | U24 |
| B-1 | P1 | Timeline의 ContractReviewGate가 일반 HOTL만 있는 새 Studio에서 사라질 위험 | §6.1: 네 결정 종류/API/ID·반려 지원 상태·state_applied=false 재승인 없는 복구 | U25 |
| B-2 | P1 | 개별 task 실행/일반 재가동과 쿼터 재개 차이 누락, stop finally가 실패에도 상태 초기화 | §6.2/B5: 명령별 task/mode·접수/불명/확인 상태·스토어 결함 수정 범위 | U26 |
| B-3 | P1 | project만 있는 URL로 프로젝트 이전 초안·instance/app/release 키트 결과를 표현 못함 | §7.1: target union·space=build 호환·read/return/data-prep 왕복·가짜project 금지 | U27 |
| B-4 | P1 | 로컬 요구/답변/의견/피드백이 이동 시 유실되거나 다음 결정에 오복원 | §7.3: 입력 종류별 키·질문/결정 차수·소비 이력·미저장 이동 보호 | U28 |
| B-5 | P1 | report 결과 버튼·resimulate/cycle·mega start_all 및 무L2 legacy 쓰기 호환 불명 | §10.2: 유형×행동×기존/신규, 서버 이관 규칙·1.0 자산 보존 | U29 |
| B-6 | P2 | SSR/브라우저/현업 혼동 가능, J2/J4/J5 합격·도움/순서 기준 미정 | §12.1~2: 현존/예정 도구·한계, J1~J5 기준·순서 교차·참가자×과제 원표 | U30 |

원 근거 주요 위치: store.py:383/694, data_preparation_control.py:1388,
ownership_binding.py:553, snapshot_service.py:504, test_actual_certification.py:256,
project_contract_aggregator.py:269, host_contract_compiler.py:344,
app_runtime_contract.py:275/403, advisor_store.py:361, advisor_control.py:448,
factory_control.py:558/936/1890, TimelinePanel.tsx:146, DecisionJarvisDock.tsx:86,
ControlPanel.tsx:329/808, useFactoryStore.ts:352, dataPrepApi.ts:302,
App.tsx:130, decisionDraft.ts:27, MegaBoardroomPanel.tsx:50.
줄 번호는 검토 시점 참고이며 구현 중 이동할 수 있다. 실제 판정은 해당 함수·계약을 따른다.

## 3. 제한적 재확인

- revision2 반영 후 원 검토자 A/B에게 각각 자기 지적 6건의 조건 해소만 요청했다.
- 최종 상태: **A PASS(설계 한정) / B PASS(설계 한정)**. 초안 반영 자체가 아니라 각각의 재확인 결과다.
- A는 revision2의 여섯 지적 모두 필요한 설계 조건이 해소됐고, 제한적 재확인 범위의 추가 요구가 없다고 판정했다. U19~U24와 배치 범위까지 대조했다. 실제 구현·시험·운영 승인은 아니다.
- B의 revision2 첫 재확인은 5건 해소/기존 B-2의 heal 분기 1건 잔여였다. 실제 API는 새 REVISION task_id 또는 기존 hotl_task_id를 반환하고,3회 제한은 현존 클라이언트 검사라는 점을 문서에서 구분하도록 요구했다. 이를 새 지적 한 건으로 중복 집계하지 않는다.
- revision2.1 §6.2/U26에서 새 작업 관찰·원실패 보존, 기존 HOTL 결정 재조회, 로컬 차단의 다음 행동, 서버 제한/멱등의 신규 제안 구분, 응답 유실 시 추가 REVISION 자동 생성 금지를 반영했다. B가 해당 한 건을 다시 읽어 PASS로 판정했고 기존6건 모두 해소됐다고 확인했다.
- A 재확인은 revision2의 A-1~A-6 범위다. 이후 revision2.1은 B-2 복구 설명/U26만 보완했으며 A 지적 관련 본문을 바꾸지 않았다. 두 검토를 전체 코드 안전 인증으로 확대하지 않는다.
- 코드·DB·브라우저/Host/현업 검증은 미실행이며 두 검토자는 코드를 수정하지 않았다.
- 최종 판정: **설계 검토 종료, 이 범위의 미해결 P0/P1/P2 0건.** 실제 구현 B0~B7은 미착수다.

## 4. 이번 턴의 실행 증거와 한계

- 코드 체크포인트 `41af3c06c`: Codex 사용 보류 소비 경계 + Claude M0 공동 작업 보존.
- 문서 체크포인트 `574c26fd8`: 기존 L2/인계 + 알려진 실패 기록. 정상 릴리스 기준선이 아니다.
- 이번 메인 재검증: 사용 보류234 passed, 실적 인증28 passed, project_data_context1 passed/7 failed.
  `output/usage-holds-7gwrk_3i` 및 체크포인트 인계의 임시 JUnit 참조.
- revision2 문서 정적 검산: U01~U30 순서/중복 없음,644줄, git diff --check 통과.
  **30건 시험 통과가 아니라30개 시험 명세**다.
- 분기점 이후 core/api/frontend/scripts/tests 변경 없음. 실제 새 변경은 문서/진척/팀 보드뿐.
- `data/interaction_log.jsonl`은 커밋 제외·원문 보존. 운영 DB·RAW·승인·권한·앱·배포 변경 없음.
- 전체 진척 **21/40=52.5%**, 로컬 **18/28≈64%** 유지.

## 5. 착수 조건과 인계

원격 푸시는 자동 보안 검토가 등록된 GitHub origin 목적지의 명시 확인을 요구해 차단했다.
사용자 확인을 요청했으며 외부 전송을 우회·재시도하지 않았다.
원격 체크포인트 확인 + 두 검토의 중요 지적 해소 후 B0부터 진행한다.
회사 역할·위임·동일인 서명 예외 정책은 실제 회사 승인 대상이며 문서가 대신 승인하지 않는다.
그 매핑이 미정이면 운영 서명은 차단하고 합성 격리 시험/구조 구현과 구분한다.

다음 담당 Codex: 최종 문서 커밋 → 목적지 승인 시 기존/새 브랜치 정상 push·원격 일치 확인 → B0 착수.
그 전 L2/생성기 구현, 운영 데이터 사용, 구 화면 삭제, dev 통합을 시작하지 않는다.
