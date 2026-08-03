# 업무 협업·의사결정·발간 폐쇄루프 UI

Supervisor가 2026-08-03 프로토타입 상태를 승인한 제품 UI 기준선이다.

## 화면

- `#delivery`: 릴리스를 지정 사용자에게 최소 권한·만료·Capability Manifest와 함께 전달
- `#inbox`: 받은 요청 수락/거절, 보낸 요청 추적, 내 앱 주머니 등록
- `#decision`: 시뮬레이션 결과를 하나의 Decision Package로 전환하고 요청자·의사결정자·영향 부서 관점과 회의 요청 제공
- `#publication`: 대내 경영보고와 대외 보고를 분리하고 근거·민감정보·책임자 승인·법무/공시 검토 후 발간

모든 화면에서 Jarvis가 회사·사용자·선택 객체 문맥을 유지한다. 생성 앱은 App-in-App 원칙에 따라 별도 로그인·사용자·토큰을 만들지 않고 플랫폼 SSO, 조직 범위, 역할, 감사로그를 상속한다.

## 실제 제품 구현

- 상세 도메인 설계: `docs/design_app_delivery_decision_publication_loop.md`
- 화면·UI 기준: `docs/uiux/LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md`, `docs/uiux/LIVING_ENTERPRISE_UI_DESIGN_SPEC_2026-07-30.md`
- Claude Code 작업서: `docs/uiux/CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md`

이 폴더의 사용자·부서·수치·일정은 UI 검증용 샘플이다. 실제 React·API·DB 구현 완료 증거가 아니다.

