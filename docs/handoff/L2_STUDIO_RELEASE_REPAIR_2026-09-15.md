# R3 릴리스 요청 수명 수정 · 다음 기능 연결 인계

작성: Codex · 2026-09-15 22:30 KST. 사용자 다음 진행 승인. 권고10/G3.
기준 HEAD 2380143ea9552bbfbe1cf59678f54a5fb53666b5,
브랜치 codex/l2-unified-studio-20260912. 이번 작업은 미커밋·미푸시다.
앞선 R1/R2 및 선택 조직 캐시 보정은 L2_STUDIO_KIT_ENTRY_REPAIR_2026-09-15.md 참고.

## 완료 결과

- 닫기·취소 뒤 늦은 응답으로 결과물이 다시 열리지 않는다.
- A→B 역순 응답, 같은 ID 재조회, 이전 요청 실패가 최신 표시를 덮지 않는다.
- 새 조회 시작 즉시 이전 결과물을 제거한다. App에 로딩 안내와 조회 취소 버튼을 연결했다.
- 회사·사용자·세션 전환 시 열린 원문과 진행 중 요청을 즉시 무효화한다. 자동 재조회·쓰기는 하지 않는다.
- 이벤트 없이 신원 값만 변경된 경우도 응답 직전에 감지하여 현재 조회를 닫는다.
- 응답 release_id가 요청과 다르거나 없으면 표시하지 않는다. 기존 lifecycle/원문 payload를 임의로 승인·변환하지 않는다.
- 로그인 성공 직후에도 기존 check()에서 인증·회사 문맥을 확정한 다음 AppShell을 마운트한다.
  과거 tenant로 직접 링크가 소비된 뒤 회사 보정 이벤트가 그 조회를 취소하는 경로를 막았다.

## 변경 파일과 불변식

1. frontend/src/store/useFactoryStore.ts
   - _releaseGeneration / _releaseAbort를 독립 관리한다. 릴리스 조회를 currentProjectId에 묶지 않는다.
   - closeRelease, 새 viewRelease, 전환 이벤트가 요청 세대를 증가시키고 AbortController를 취소한다.
   - 세션/acting-user/enterprise-context 세 이벤트 모두 듣는다. 값이 A→B→A로 돌아와도 옛 요청은 폐기한다.
   - GET은 no-store와 signal을 사용한다. 기존 lib/api.ts 인터셉터가 init을 보존하므로 신호/인증 헤더가 함께 전달된다.
   - fetch, JSON 읽기, catch 이후 상태 갱신 전에 세대·신원을 확인한다.
   - 오래된 finally가 새 요청의 취소 참조를 지우지 못한다.
   - 단일 ASCII 경로 ID만 허용한다. 서버 _safe_id에는 길이 제한이 없으므로 목록 진입에 새160자 제한을 추가하지 않았다.
     Studio URL 문법의 기존 제한은 별개이며 변경하지 않았다.
   - 401/403/404의 기존 같은 안내와 나머지 실패 안내를 보존한다.
2. frontend/src/App.tsx
   - 기존 릴리스 오류 분기에 loading을 추가. role=status 안내와 실제 closeRelease 취소 버튼 제공.
   - LoginPage.onLoggedIn에서 setState(in)을 바로 호출하지 않고 void check()를 재사용.
     로그인/권한 정책을 새로 구현하지 않는다. check()의 기존 장애/거절 처리는 그대로다.
3. frontend/scripts/check-release-entry.mjs
   - 실제 Zustand store 전체 소스를 메모리에서 컴파일해 실행한다. store 동작을 다시 작성한 대역이 아니다.
   - fetch·신원 값·EventTarget은 격리 대역이다. 취소를 무시하는 응답을 일부러 전달하여 세대 검사도 검증한다.
   - App의 실제 상태 JSX·로그인 콜백·check 콜백을 AST로 추출해 실행한다.
     SSR·React 트리의 취소 onClick 호출로 배선을 확인하며 전체 App/브라우저 실행을 주장하지 않는다.
   - 각 검사는 새 store와 EventTarget을 사용한다. 제품/검사 소스 해시 전후 동일성을 확인한다.

## 검증 증거

| 검사 | 결과 | 근거 |
|---|---|---|
| 최초 릴리스30건, 수정 전 | 6PASS / 24FAIL | output/release-entry-91388302-1316-4324-befb-ba3f5f15f863/report.json |
| 최종 릴리스36건 | 36PASS / 0FAIL | output/release-entry-559a56a2-1bf8-49fc-aa17-05a0fe70d3a1/report.json |
| 기존 Studio/배선 | 157PASS | output/studio-contracts-dc743c60-1411-48db-b9f0-7d55a252e965/report.json |
| 업무 앱/프로젝트/주소 | 14+26+25PASS | 각 전용 검사 exit0 |
| 업무 설치 | 105PASS | output/process-installation-check-10ca82ed-2f29-43b7-b4eb-6a6893563aa9/report.json |
| 타입/제품 빌드 | PASS | npm run build, tsc -b 포함, exit0 |

합계363건. 24FAIL은 24개 별도 제품 결함이라는 뜻이 아니라 새 요구/회귀 시나리오의 실패 수다.
기존 동적 import·500KB 초과 번들 경고는 남아 있다. 브라우저·실서버·실제 사용자 수용 NOT_RUN.
서버 제품 소스가 이번에 바뀌지 않아 이전162PASS를 재실행해 시간을 쓰지 않았다.
이전 서버 결과를 이번 신규 실행 실적으로 합산하지 않는다.
output 원문은 Git ignored. 재실행 명령과 요약은 이 문서로 전달한다.

저장소 루트:

    node frontend/scripts/check-release-entry.mjs
    node frontend/scripts/check-studio-contracts.mjs
    node frontend/scripts/check-kit-app-entry.mjs
    node frontend/scripts/check-project-entry.mjs
    node frontend/scripts/check-studio-location.mjs
    node frontend/scripts/check-process-installation.mjs
    npm --prefix frontend run build

## 이중 검토

Codex 요청 → Raman 독립 읽기 전용.
기존 프로젝트 재확인만으로 release 단독/세션 전환이 처리되지 않는 점과 로그인 초기 회사 보정 순서 P2를 지적했다.
Codex가 이벤트3종 무효화·check 재사용으로 수정하고 원본 콜백/취소/역순응답 검사를 실행했다.
Raman 최종 diff 판정: 범위 내 P1/P2 없음, 기존 지적 정적 종결.
검사는 메인이 실행했고 독립 검토자가 재실행한 것은 아니다.

## 진척과 다음 단계

- 우선 결함 R1~R3 코드 수정 완료. G3 진입 기능의 안정성 전진이다.
- 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 새 관문 완료 칸을 추가하지 않았다.
- 다음 신규 기능: mega 부모-자식 진입, 예상30~50분.
  첫20~30분에 서버 관계/가시성 계약과 핵심 구현 상태를 보고한다.
- 기존 project 확인 경로를 재사용하되 서버가 부모-자식 관계와 양쪽 가시성을 확인해야 한다.
  프런트가 두 응답을 조합해 관계를 추측하거나 미확인 프로젝트를 먼저 열지 않는다.
- 이어서 draft 선택 문맥 기반 진입, 그 뒤 단일 진입/히스토리/문맥 전환의 실제 브라우저 수용.
- kit_app releaseId 미소비, Gate5 글자 크기·실제 LLM 응답·전체 사용자 수용은 잔여다.
  이번 문서로 해당 Gate를 해제하거나 B6 전체 완료로 보고하지 않는다.

## 데이터·전달 상태

운영DB·RAW·키·공유ZIP·사용자로그 변경 없음. 서버를 기동하거나 데이터를 복원하지 않았다.
로그 SHA256: 7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510.
ZIP SHA256: 9c60dccd210974fecc7a65f3945d2617371d416cb12a01153fa80d411977ab34.
이전 턴의 서버 코드/문서 수정도 작업트리에 그대로 보존했다.
다른 PC에서는 아직 이번 수정이 pull되지 않는다. 커밋·push 요청 시 관련 파일만 명시적으로 포함하고
data/interaction_log.jsonl은 사용자 기존 변경이므로 제외한다. 전역 UI/코드/문서 커밋 분리 규칙 유지.
