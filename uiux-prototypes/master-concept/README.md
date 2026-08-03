# AI Factory Studio · Living Enterprise Canvas

여러 디자인 시안을 추가 생산하지 않고, AI Factory Studio의 제품 정체성을 한 화면에서 검증하기 위한 North Star 대표 화면이다.

> **채택 상태:** 2026-07-30 Supervisor 최종 합격. 이후 메인 UI 설계와 구현은 이 화면을 North Star로 사용한다. 이전 V1~V10 및 Revision 세트는 부분 요소 참고와 의사결정 이력으로만 보존한다.

## 대표 사용자 과업

1. 현재 회사·사업부·공장과 권한 범위를 확인한다.
2. 수주부터 손익까지 연결된 전사 업무 흐름에서 현재 문제를 찾는다.
3. 문제에 연결된 실제 데이터·현업 SW·Agent·Digital Twin을 확인한다.
4. 근거와 영향을 비교하고 Atlas의 설명을 받는다.
5. 시뮬레이션, 현업 SW 실행 또는 의사결정안 작성으로 이어진다.

## 제품 고유 문법

- 중앙의 `Enterprise Digital Thread`가 업무·데이터·AI·경영 결과를 하나로 묶는다.
- 좌측은 사용자 역할에 맞춘 실제 의사결정 대기열이다.
- 우측 Atlas는 Task ID 없이 현재 회사 전체를 이해하는 AI 동료다.
- 하단 Trust Foundation은 MDM·운영 데이터·지식·외부지표의 근거를 노출한다.
- 카드형 KPI 대시보드가 아니라 업무 흐름과 원인·결과 관계가 내비게이션이 된다.
- LS Blue는 기업 구조, LS Red는 현재 결정과 핵심 행동에만 제한적으로 사용한다.

## 현재 프로토타입 인터랙션

- 전사 업무 노드 또는 좌측 의사결정 항목 선택
- DATA·SW·TWIN 레이어 표시 전환
- 경영 시나리오 비교로 전환
- Atlas 판단 근거·데이터 부족·진행 상태 질문
- 자유 질문 및 의사결정안 초안 생성

## 실제 제품 적용 순서

1. 현재 `App.tsx`의 회사 컨텍스트와 메인 진입 화면을 이 정보구조로 매핑한다.
2. REST/SSE 상태를 Digital Thread 노드와 좌측 통제 대기열에 연결한다.
3. `ControlPanel`, `TimelinePanel`, `PreviewPanel`을 선택 노드의 세부 작업 공간으로 이동한다.
4. Atlas 전역 대화 API와 근거 추적·시뮬레이션 진입을 연결한다.
5. 사용자 과업 테스트 후 Build SW·Operate·Simulate 상세 화면으로 동일 문법을 확장한다.
