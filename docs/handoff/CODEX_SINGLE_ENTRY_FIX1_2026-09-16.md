# SINGLE-ENTRY-01 검토 — 보완 후 재검토

작성: Codex · 2026-09-16 KST. Claude 보고와 공유 소스를 읽기 검토했다. 제품 수정·시험 재실행 없음.
판정: 콜백 의존성 축소와 확인 중 URL 보존은 인정한다. 새로고침/뒤로·앞으로/중복 실행의 전체 완료는 아직 아니다.
이 문서는 CODEX_SINGLE_ENTRY_DECISION_2026-09-16.md의 수용 조건을 축소하지 않는다.

## 1. [P1] 늦은 초안 원문이 새 문맥 입력에 반영될 수 있음 — 먼저 재현·수정

근거: frontend/src/lib/studioRequirementDraft.ts의 openDraftRevision(398행)은 요청 전 identity를 보관하지 않고 signal/요청 세대도 받지 않는다. 응답 후 getStudioRequirementDraft(deliverable).adoptRevision을 실행한다(418행). getStudioRequirementDraft는 호출 시점의 processContextIdentity로 저장소를 선택한다.
따라서 A 문맥에서 보낸 원문 조회가 B 문맥 전환 후 완료되면, A 응답을 B의 입력 저장소에 반영할 경로가 있다. validateLoadedRevision은 옛 target.ownership과 응답을 대조할 뿐 현재 identity를 대조하지 않는다.
App DraftOpenCommit의 alive는 onOpened/setError만 막는다. openDraftRevision 내부의 adopt는 그보다 먼저 실행된다. 또한 버튼에서 open(true/false)가 반환한 cleanup은 React가 호출하지 않으므로 재시도 요청의 onOpened도 unmount 후 실행될 수 있다.

지시:

- 요청 시작의 identity와 대상/요청 세대를 고정하고 fetch/본문 파싱 이후 및 adopt 직전에 동일 요청/문맥인지 확인한다. 이전 응답은 입력·receipt·화면에 반영하지 않는다. abort만으로 해결했다고 가정하지 않는다.
- 자동 진입과 재시도/입력 교체 버튼 모두 동일한 취소·세대 수명을 사용한다. 닫기/다른 대상/문맥 전환에서 폐기한다.
- 격리 모의 HTTP로 지연시켜 검사: A 요청→B 문맥→A 응답, 초안1→초안2 역순 응답, 재시도→닫기→응답. 현재/다른 문맥 form·receipt가 모두 오염되지 않고 onOpened도 호출되지 않음을 확인한다.
- UI에서 막는 것만으로 통과시키지 말고 adopt 부작용 자체를 검사한다. 제품 데이터로 재현하지 않는다.

## 2. [P2] 대상 없는 주소 복원이 A안과 반대임

App.tsx onPopState(312행 이후)의 대상 없음 분기는 Gate만 닫고 currentProjectId/buildStart/현재 공간/릴리스·업무앱 화면을 정리하지 않는다. 목록이나 홈 URL로 돌아와도 기존 화면이 남을 수 있다.
check-project-entry.mjs는 plain.currentProject가 undefined여야 한다고 단언하여 이 잘못된 동작을 고정하고 있다(394행 부근).
또한 next.release와 next.isNew는 대상 없음 분기로 들어가며 해당 화면을 복원하지 않는다.

지시: URL의 목적지가 목록/홈이면 그 화면으로, release/new면 그 대상으로 전환한다. 떠나는 화면/요청은 안전하게 정리한다. 여섯 종류의 공통 적용 경로를 사용하고 해당 시험도 URL-화면 일치를 단언하도록 고친다. 단순히 대상 없음 시험을 삭제하지 않는다.

## 3. [P2] 열린 대상 URL 보존과 히스토리 생성 미구현

App.tsx 336~352행은 확인 완료 후 여전히 대상 키를 전부 삭제하고 legacy project만 유지한다. draft onOpened가 closeEntryGate를 부르고, kit_app commit도 routeRestored=true로 전환한다. 따라서 확인 중 보존과 열린 화면 새로고침 보존은 다르다.
frontend/src의 검색에서 pushState 호출은 없고 popstate 리스너는 App의 이번 한 곳이다. 내부 이동은 replaceState로만 기록되어 앱 안 왕복에 필요한 항목이 쌓이지 않는다.

지시: 이전 결정서대로 열린 대상의 식별자/판본을 URL에 유지한다. 사용자 명시 이동은 한 칸 추가, 정규화는 교체, popstate 복원은 추가 금지. mega 부모/자식과 release도 빠뜨리지 않는다. 모든 replaceState를 무조건 pushState로 바꾸지 않는다.

## 4. [P2] 미저장 입력 이동 확인 우회

onPopState가 즉시 setBuildStart(false)를 호출한다. 기존 BuildStartDialog의 requestLeave/미저장 입력 확인은 거치지 않는다. beforeunload는 앱 안 popstate의 대체 수단이 아니다.
기존 메모리가 일부 입력을 보존할 수 있으므로 실제 데이터 유실이 재현됐다고 주장하지 않는다. 그러나 요구된 이동 취소/URL·화면 일치 보호는 구현되어 있지 않다.

지시: 이동 전 보호를 공통 적용한다. 취소 시 현재 URL·화면·입력이 일치하고 history 항목이 늘지 않아야 한다. 입력 유지/저장/폐기 정책은 기존 UI와 일치시킨다.

## 검사 해석과 탐침 주의

- 보고된 최종 프런트 합계는48+17+25+25+14+36=165 PASS. Codex 재실행값이 아니다.
- hookHarness는 useEffect의 의존성만 기록하며 효과 본문/cleanup/React commit을 실행하지 않는다. 콜백 신원 변경에 따른 의존성 안정화는 검사하지만 실제 중복 요청·StrictMode·버튼 재시도 수명까지 증명하지는 않는다.
- 콜백 ref 보완을 버리라는 지시가 아니다. 실제 효과/부작용 검사와 브라우저로 수용 범위를 보충한다.
- 최종 build/test 성공 보고를 존중하되, 원복 실패 이력이 있으므로 다음 시작 시 의도된 변경을 diff로 확인한다. 동시 빌드/서버가 읽는 공유 제품 파일을 계속 변이하지 않는다. 필요하면 격리 사본에서 수행하고 실패 시 반드시 해시 검증한다. 파일 잠금이 원인이었다는 주장은 미확인 추정으로 표시한다.

## 순차 실행 지시 / 보고

1. SINGLE-ENTRY-01-FIX1 ACK/RUNNING을 기록하고 첫20~30분에 1번 지연 응답 결함부터 재현·차단한다. 결과와 다음 ETA를 보고한다.
2. 이어서 2~4번 공통 라우팅 보완을 수행한다. 예상30~45분이며 구체 계획 후 갱신한다. 새 UI 전면 개편/새 라우팅 프레임워크는 범위 밖이다.
3. 변경 후 관련 프런트 회귀/build 한 번, 실제 제품 브라우저 수용15~25분 예상. 목록→초안→릴리스→뒤로→앞으로, 초안 새로고침, 미저장 이동 취소를 확인한다. NOT_RUN을 기능 완료로 바꾸지 않는다.
4. 환경 절차는 개인 기억이 아닌 저장소의 정확한 문서 경로로 남긴다. 미검증 브라우저와 route_authority 4 ERROR 부채를 계속 분리 보고한다.
5. 전체21/40=52.5%, 로컬18/28=64.3% 유지. 보드의 새로고침/히스토리 전체 완료 표기를 부분 구현·보완 중으로 정정한다. 이전 보고는 이력으로 보존한다.

구현 단독 담당 Claude. Codex는 검토·지시만 한다. 사용자 데이터/미커밋 변경/타 세션 작업 보존. 커밋·푸시·pull·환경 삭제 지시 없음. 수신 전 자동 전달/착수로 보고하지 않는다.
