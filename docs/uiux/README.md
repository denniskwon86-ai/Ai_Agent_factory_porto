# AI Factory Studio UI/UX 기준 문서

실제 클릭형 제품 화면 샘플: [`../../uiux-prototypes/m6-product-samples/index.html`](../../uiux-prototypes/m6-product-samples/index.html)

## 확정 기준

- North Star: `uiux-prototypes/master-concept/index.html`
- 채택 결정: `uiux-prototypes/master-concept/ADOPTION_DECISION.md`
- Software Factory 투명 오케스트레이션: `uiux-prototypes/sw-factory-concepts/transparent-orchestration/`
- 앱 전달·의사결정·발간 폐쇄루프: `uiux-prototypes/closed-loop-product-samples/`

## M6 구현 설계 문서

1. [화면기능정의서](LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md)  
   목표 정보구조, 화면 목록, 역할·권한, 기능, 통합 사용자 여정, 상태 계약을 정의한다.
2. [UI 설계서](LIVING_ENTERPRISE_UI_DESIGN_SPEC_2026-07-30.md)  
   디자인 토큰, 레이아웃, 공통 컴포넌트, 화면별 배치, Atlas/Jarvis UX, 접근성·반응형·성능, 구현 단계를 정의한다.
3. [구현 추적 매트릭스](LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md)  
   현재 React·API와 목표 화면을 연결하고 재사용·재배치·신규 계약·회귀 조건을 추적한다.
4. [클로드코드 폐쇄루프 구현 작업서](CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md)  
   승인된 앱 전달·수락·Decision Package·회의·대내외 발간 UI를 실제 React·API·DB로 구현하기 위한 작업 패키지와 완료 조건이다.

## 구현 원칙

- 기존 기능을 삭제하지 않고 승인 Shell과 상세 작업공간으로 재배치한다.
- `unavailable`, `unverifiable`, `unmeasured`, `not recorded`를 정상·0·통과로 표현하지 않는다.
- 회사 문맥과 권한을 모든 조회·검색·생성·시뮬레이션·발간에 동일하게 적용한다.
- 개인 앱 전달과 조직 공유·업무 배정·전사 승격을 분리한다.
- 생성 앱은 플랫폼 인증을 상속하며 자체 로그인·사용자·JWT를 만들지 않는다.
- 대외 발간은 책임 임원과 법무·공시 검토를 모두 통과한 뒤 사용자가 명시적으로 실행한다.
- 정적 시안의 샘플 데이터는 제품 데이터로 간주하지 않는다.

