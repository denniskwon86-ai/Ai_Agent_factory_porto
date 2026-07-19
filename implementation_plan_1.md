# [Enterprise Readiness] Antigravity AI Factory 실무 적용 고도화 계획 (비용 최적화 반영)

현 시스템은 훌륭한 비전을 갖추고 있으나 현업 도입 시 신뢰성, 품질, 거버넌스 피로도라는 3가지 치명적 리스크를 안고 있습니다. 
최근 발생한 **API 429 할당량 초과(Quota Exhausted) 이슈** 및 사용자님의 지적에 따라, **추가적인 LLM 자원 소모를 '0'에 가깝게 통제하면서도 효용성을 극대화하는 비용 최적화(FinOps) 관점**으로 계획을 전면 수정했습니다.

## User Review Required

LLM 호출 비용을 아끼면서도 엔터프라이즈급 신뢰성(추적성)과 품질(QA)을 확보하기 위한 '정적 분석 중심의 우회 전략'이 추가되었습니다. 이 갱신된 계획을 검토하시고 승인(Proceed)해 주십시오.

---

## 🛠 Proposed Changes (LLM 자원 절감형 구현 계획)

### 1단계: LLM 추가 호출 0(Zero) - 기계적 추적성 확보 (Traceability)
AI에게 "왜 이 코드를 짰는지 설명해봐"라고 묻는 것은 막대한 토큰(비용) 낭비입니다. 

#### [NEW] `core/traceability_engine.py` (비용: 0 LLM Call)
- 에이전트가 코드를 생성할 때 이미 출력하고 있는 JSON의 `reason` 필드와, 주입되었던 마스터 데이터(M1), 요구사항 ID를 **백엔드(Python)에서 기계적으로(AST 파싱) 맵핑**하여 DB에 저장합니다. 추가 LLM 호출이 전혀 발생하지 않습니다.
#### [MODIFY] `frontend/src/components/PreviewPanel.tsx`
- 통제실의 코드 뷰어에서 라인을 클릭하면, 이미 저장되어 있는 메타데이터(프롬프트 해시, 주입된 M1 데이터, 에이전트의 최초 추론 로그)를 꺼내어 시각적으로만 보여줍니다.

### 2단계: 정적 분석(Static Analysis) 기반의 지능형 HOTL
에이전트의 산출물을 평가할 때 LLM을 사용하지 않고 기존 파이썬 도구를 활용합니다.

#### [NEW] `core/risk_analyzer.py` (비용: 0 LLM Call)
- 코드의 변경점(Git Diff 형태)을 LLM에게 묻지 않고, **Python AST 및 정규식 분석기**를 통해 위험도(Risk Score)를 자동 산출합니다.
  - *Low Risk:* CSS 파일 변경, 단순 텍스트 수정 (→ 즉시 자동 승인)
  - *High Risk:* DB 스키마(`models.py`) 변경, API 엔드포인트 변경, 의존성 패키지 추가 (→ 인간 개입 강제)
#### [MODIFY] `frontend/src/components/HOTLInput.tsx`
- 인간 개입이 강제된(High Risk) 항목에 대해서만 시각적 Diff를 띄우고 **부분 승인(Partial Approval)**을 받습니다. 인간의 피로도를 낮추고 쓸데없는 LLM 검수 루프를 원천 차단합니다.

### 3단계: Flash 모델 위임 및 샌드박스 TDD (Shift-Left QA)
QA와 테스트 코드를 Pro 모델에게 맡기면 예산이 파탄 납니다. 철저한 티어(Tier) 분리가 필요합니다.

#### [NEW] `nodes/test_engineer.py` (비용: 극소형 Flash 모델 전담)
- TDD 기반의 단위 테스트(Unit Test) 코드 작성은 가장 저렴하고 빠른 **Flash 모델(또는 Llama 8b 등 소형 모델)**에게 전담시킵니다.
#### [MODIFY] `nodes/execution.py` (CodeBuilder 샌드박스)
- 생성된 코드를 격리된 샌드박스에서 실행해보고 에러 스택트레이스(Stacktrace)가 발생하면, 역시 Flash 모델이 에러 로그를 읽고 1~2회만 퀵 픽스(Quick Fix)를 시도합니다. 
- **[서킷 브레이커 강경화]** 2회 내에 Flash 모델이 해결하지 못하면, 비싼 Pro 모델로 승격하여 무한루프를 돌리는 대신 **즉시 인간(HOTL)에게 "복잡한 논리 오류 발생"으로 에스컬레이션**하여 LLM 쿼터를 사수합니다.

---

## 🧪 Verification Plan (검증 및 비용 기대 효과)

1. **LLM 쿼터 절감율 (FinOps Metric):** 기존처럼 빌드 실패 시 Pro 모델이 3번 연속 재시도하던 방식 대비, Flash 모델 위임 및 서킷 브레이커 강경화(3단계)를 통해 전체 프로젝트 완주 시의 **API 토큰 소모량이 최소 40% 이상 감소**하는지 측정합니다.
2. **리드타임 감소:** 정적 분석(2단계)을 통한 자동 승인(Low Risk)으로 인간 대기 시간이 줄어드는지 확인합니다.
3. **코드 신뢰성:** 추가 비용 없이 코드 뷰어(1단계)에서 산출물의 근거(M1 주입 데이터)를 100% 추적할 수 있는지 통제실 UI에서 시연합니다.
