# Living Enterprise Canvas 채택 결정

- 결정일: 2026-07-30
- 결정자: Supervisor
- 판정: **합격 · AI Factory Studio 메인 UI North Star로 채택**

## 고정할 핵심 요소

1. 좌측 역할 기반 의사결정 대기열
2. 중앙 Enterprise Digital Thread
3. 업무 위에 연결되는 Data·현업 SW·Digital Twin 레이어
4. 하단 MDM·운영데이터·지식·외부지표 Trust Foundation
5. 우측 Task ID 없는 회사 범위 Atlas
6. 회사·사업부·공장 Context와 권한 범위의 상시 노출
7. LS Blue 구조와 LS Red 핵심 행동의 제한적 사용

## 구현 원칙

- 기존 `ControlPanel`, `TimelinePanel`, `PreviewPanel` 기능을 폐기하지 않고 선택한 업무·프로젝트의 상세 작업 공간으로 연결한다.
- 메인 화면 전환 전에 기존 화면과 병행 가능한 Read-only 카나리로 이식한다.
- 화면에 표시하는 수치·상태·추천은 실제 API 근거가 있을 때만 노출한다.
- Atlas의 읽기 답변과 실행 명령을 분리하며 실행은 HOTL 승인을 거친다.
- 회사 Context·권한은 모든 집계·검색·대화·실행에서 Fail-closed로 적용한다.

## 다음 실행 순서

1. 디자인 토큰과 화면 기능 정의 확정
2. Enterprise Canvas Aggregate API 계약 확정
3. React Read-only 카나리 화면 이식
4. WBS·State·Feed·SSE·Release·MDM 데이터 연결
5. 회사 범위 Atlas API 연결
6. 사용자 과업·회귀·권한·성능 검증
7. 메인 화면 전환 여부 최종 승인
