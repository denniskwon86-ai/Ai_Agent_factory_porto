# 경영 홈 해상도 대응 — 2026-09-08

## 요청과 범위

사용자 첨부 화면(localhost:5173)에서 보조정보와 결정 카드가 겹치고, 왼쪽 하단 버튼·자비스 입력란이 화면 밖으로 밀리는 문제를 수정했다. 업무키트/데이터 작업은 이번 UI 변경과 별개이며 건드리지 않았다. 커밋·푸시하지 않았다.

## 변경

- `App.tsx`: 경영 홈에만 `enterprise-home`을 적용. 헤더의 실제 높이를 뺀 공간을 작업면으로 사용한다(100dvh, 100vh fallback).
- `EnterprisePage.tsx`: 업무 노드·보조정보·연결선을 한 지도 스크롤면으로 묶고 결정 카드를 그 다음에 배치한다. API/권한/수치/회사 문맥/질문 동작은 변경하지 않았다.
- `enterprise-responsive.css`: 기존 색상과 붉은 연결선 유지. 좌·우 레일 폭은 화면에 비례하되 상·하한을 둔다. 826px 최소 높이 및 결정 카드의 절대 위치는 경영 홈에서 해제한다.
- 데스크톱: 대기열·중앙 내용·자비스 본문이 각각 스크롤한다. 좌측 하단 작업 버튼과 비서 입력란은 화면 안에 유지한다. 긴 결정 설명은 본문 안에서 스크롤하고 행동 버튼은 별도 행에 둔다.
- 1279px 이하: 상단 주요 메뉴를 두 번째 행으로 배치. 1100px 이하: 자비스를 다음 행으로 이동. 900px 이하: 상단 행동을 별도 행으로 배치. 700px 이하: 세 영역을 세로 배치한다.
- 업무 지도는 노드당 최소 94px을 확보하고, 폭이 부족하면 노드·보조정보를 함께 가로 탐색한다. 빈 보조카드 칸, DATA/SW/TWIN 색상 및 켜기/끄기는 유지한다.

## 검증

1. `npx tsc -b --pretty false`: 종료 0.
2. `npm run build`: 종료 0. 기존 대형 번들/동적 import 경고는 남아 있다.
3. `tests/test_management_home_ui_contract.py` + `tests/test_ui_layer_order.py`: 103건 통과, 종료 0.
4. 실제 React 경영 홈·ProductShell·CanvasJarvisRail을 격리된 Chrome에서 렌더링: 10개 viewport × 기본/긴 본문·12단계 = 20조건 통과.
   - 1920×1080, 1536×864, 1440×770, 1366×768, 1280×720, 1280×600, 1152×648, 1024×768, 800×700, 390×844.
   - 문서 가로 넘침 없음, 보조카드와 결정 카드 간격 24px, 노드/카드 열 일치.
   - 데스크톱 작업 버튼·자비스 입력란 viewport 내부 유지, 대기열/본문과 비중첩.
   - 긴 안건에서도 행동 클릭, 노드 선택 후 초점 이동, DATA 레이어 전환, 질문 입력 확인.
5. 1440×770·1280×720 스크린샷 육안 검토. 5173의 새 반응형 CSS 응답 HTTP 200.

### 재현

```powershell
node frontend/scripts/build-enterprise-layout-fixture.mjs
venv/Scripts/python.exe scripts/check_enterprise_responsive.py
```

결과는 `tmp/home-responsive-layout/results.json` 및 `screenshots/`. fixture는 `frontend/tests/enterprise-layout.fixture.*`이며 제품 진입점에서 import하지 않는다. 모든 fetch는 시험 응답으로 종료하고 브라우저 외부 요청도 차단한다. 로그인·제품 API·LLM·운영 DB를 사용하지 않는다. 따라서 위 브라우저 검증은 **레이아웃 검증**이지 실제 계정/데이터 종단 검증은 아니다. 현재 사용자 세션에서는 5173 새로고침 후 확인하면 된다.

## 주의

기존 시안 CSS를 삭제하지 않고 경영 홈 전용 반응형 파일로 보완했다. `EnterprisePage.tsx`에서 `enterprise-canvas.css` 다음에 `enterprise-responsive.css`를 읽는 순서와 App의 `enterprise-home` 범위를 유지한다. 다른 화면이나 회사 구성 모달의 공통 높이에 이 규칙을 확대하지 않는다. 동시 작업 중인 데이터 수집·업무키트 파일은 이 변경 묶음에 포함하지 않는다.
