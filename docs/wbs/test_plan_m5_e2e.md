# M5 통합 E2E 테스트(Quality Gate) 시나리오 기획서

## 1. 개요 및 검증 목표 (Definition of Done)
현재 M5(E2E 통합 검증 및 텔레메트리 점검) 단계는 단순히 서버가 켜지는지 확인하는 것을 넘어, **권한 격리, 승격 모델, 경영계획(디지털트윈)**이라는 핵심 비즈니스 로직이 100% 정상 작동하는지 확인하는 관문입니다.
이 문서는 M5를 최종 완료(DONE)로 승인하기 위해 통과해야 하는 **3단계 통합 시나리오(Quality Gate)**를 명세합니다.

---

## 2. 통합 E2E 시나리오 명세

### 🧪 Scenario A: Core Factory Flow (기본 파이프라인 무결성)
가장 기본이 되는 A-1 생성 워크플로우로, LangGraph 오케스트레이션과 LLM 에이전트 루프가 멈춤 없이 완주하는지 확인합니다.
- **주요 실행 드라이버**: `run_e2e_scenario.py`
- **검증 항목**:
  - `PLANNING` -> `EXECUTION` -> `RELEASE` 로 이어지는 상태 전이가 중단(스톨)이나 타임아웃 없이 이뤄지는가?
  - `build_error_log` 발생 시 에이전트가 자체 복구(Self-healing)를 통해 에러를 픽스하는가?
- **통과 기준**: `run_e2e_scenario.py` 실행 시 "전 태스크 완주 성공" 로딩 후 종료 코드 `0` 반환.

### 🔐 Scenario B: 권한 격리 및 운영 통제 (Security & Audit)
M2 단계에서 구축한 부서별 권한 상속 및 비인가 자원 404 은폐 로직을 집중 검증합니다.
- **주요 테스트 스위트**: `test_m2_entry_gates.py`, `test_access_audit.py`
- **검증 항목**:
  - 클라이언트가 허위 `enterprise_scope_id`를 헤더나 파라미터로 주입하여 상위 조직의 자원을 조회하려 할 때, 401/403이 아닌 **404(Not Found)로 은폐**하는가?
  - 해당 권한 우회 시도가 `data/access_audit.jsonl` (감사로그)에 고스란히 저장(Append)되는가?
- **통과 기준**: 해당 pytest 묶음에서 xfail/error 없이 모두 PASS.

### 💼 Scenario C: Business Value (Shadow Mode & Planning Twin)
우리 시스템의 꽃인 M3/M4 단계의 비즈니스 핵심 모듈(섀도우 검증 및 경영계획 엔진)의 정합성을 검증합니다.
- **주요 테스트 스위트**: `test_shadow_mode.py`, `test_planning_engine.py`
- **검증 항목**:
  - LLM 0콜 원칙(결정론적 함수)이 지켜진 상태에서 섀도우 모드의 입력값 불일치가 정상적으로 판정 거부(Reject)되는가?
  - 경영계획 디지털트윈 구동 시 결손된 입력(미입력)에 대해 0이 아닌 '미입력(Comparable=False)' 상태로 정직하게 출력하는가?
  - 승격 게이트(Promotion Gate) 통과 전 4가지 선행 조건이 충족되었는지 확인하는지?
- **통과 기준**: Planning Engine 연동 테스트 케이스 100% 통과 (가짜 통과 방지).

---

## 3. 테스트 구동 및 감사(Audit) 가이드
위 시나리오들은 M5 담당자인 **Antigravity(Gemini)** 주도 하에 독립적으로 검증(Audit)되어야 합니다. 
만약 에러가 발생하거나 배선이 누락된 경우, `claude_code_tasks.md`로 Fix Task를 이관하여 코드 보정을 요구합니다. 3개 시나리오가 모두 PASS될 때 비로소 M5 완료를 선언할 수 있습니다.
