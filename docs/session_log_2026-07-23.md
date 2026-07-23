# 세션 작업 기록 : 2026-07-23

> 💡 **세션 목표**: 어제(07-22) 발견된 A-1 E2E 시나리오 상의 **`UI_DESIGN` 단계 HOTL 자동 승인 무한 루프(Bug #10) 결함**을 분석하고, 수정 및 검증을 완료합니다.

---

## 1. 결함(Bug #10) 원인 분석 및 해결

어제 도입된 `v1 Exact Hash Cache`로 인해 기존에 간헐적으로 발생하던 로직 오류가 무한 루프라는 형태로 명확하게 터져나왔습니다.

- **원인**: 
  - `VisionQA` 에이전트가 UI 설계의 시각적 결함을 지적하며 반려(`reviewer_decision = "REWORK_DEV"`) 및 피드백을 전달했습니다.
  - 하지만, `UIDesigner` 노드는 오직 사용자의 피드백(`human_feedback_queue`)만 읽어오고 **AI 리뷰어의 반려 피드백을 완전히 무시**하도록 짜여 있었습니다.
  - 프롬프트에 아무런 피드백이 추가되지 않다 보니 이전과 100% 동일한 프롬프트가 LLM에 들어갔고, `Exact Hash Cache`가 이전의 잘못된 UI 결과를 0.01초 만에 뱉어냈습니다.
  - 이 결과가 다시 `VisionQA`로 가고 즉시 반려되며, 자동화 스크립트의 `resume`과 맞물려 무한 루프가 발생했습니다.

- **해결 방안 (수정 내역)**:
  - `nodes/ui_designer.py` 파일 수정
  - `UIDesigner`가 `reviewer_decision == "REWORK_DEV"`일 경우 `reviewer_feedback`을 읽어 LLM 프롬프트에 명시적으로 주입하도록 방어 로직을 추가했습니다. (캐시 Hit 방지 및 AI 재설계 유도)
  - 피드백을 수용하여 LLM에 넘긴 직후에는 `reviewer_decision`을 `"NONE"`으로 덮어써서 이후 단계 진행 시 이전 반려 이력으로 인해 롤백되는 부작용을 원천 차단했습니다.

---

## 2. E2E 테스트 검증 결과 (A-1 시나리오)

수정 사항을 적용한 후 백엔드 서버와 `run_e2e_scenario.py test_a1_unitconv` 스크립트를 가동하여 결함 해결을 검증했습니다.

- **무한 루프 탈출 성공**: 
  - `UI_DESIGN` 단계에서 `VisionQA`의 반려가 발생하자, 즉각 프롬프트가 변경되어 캐시가 우회(Bypass)되었습니다.
  - LLM이 새로운 UI 디자인을 반환했고, 두 번째 비평을 무사히 통과하여 **다음 단계인 `아키텍처(ARCHITECTURE)` 초안 작성 단계로 정상 진입**했습니다. (Bug #10 해결 확정)

- **할당량(Quota) 고갈 중단**:
  - `아키텍처` 단계로 무사히 넘어갔으나, 백엔드의 다중 라우터(`LLM Gateway`)에 배치된 모든 무료 API 제공사(Gemini, Groq, Cerebras, OpenRouter 등)의 일일 쿼터가 연이은 테스트로 인해 모두 429(할당량 초과) 에러를 반환했습니다.
  - 이로 인해 파이프라인이 다시 **`SUSPENDED_QUOTA` (할당량 소진 중단)** 모드로 동결되었습니다. (Bug #9)

---

## 3. 다음 작업자(다음 세션)를 위한 인수인계 사항 (Next Steps)

1. **테스트 완주 대기**:
   - 현재 코드나 로직상의 버그는 모두 잡혔습니다. 현재 테스트(A-1)는 `아키텍처(ARCHITECTURE)` 단계 초입에서 멈춰(Suspend) 있습니다.
   - 내일 무료 쿼터가 리셋되거나 새로운 유료 API 키가 발급되면, 터미널에서 `python run_e2e_scenario.py test_a1_unitconv --resume` 명령어를 실행하기만 하면 중단된 지점부터 코드 생성까지 이어서(Resume) 완주할 수 있습니다.
   
2. **저장소 상태**:
   - Bug #10에 대한 수정 사항(`nodes/ui_designer.py`)과 상황이 업데이트된 `docs/test_plan/02_progress_tracker.md` 파일은 모두 원격 저장소(`dev` 브랜치)에 안전하게 커밋 및 **Push** 완료되었습니다.
