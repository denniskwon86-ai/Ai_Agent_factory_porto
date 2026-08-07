# 📊 Telemetry & Audit Collector 명세서
> **문서 버전**: v1.0  
> **작성일자**: 2026-08-04  
> **작성자**: Gemini Antigravity (전략·감사 전담)  
> **목적**: 소스 코드 수정을 배제하고, 클로드 코드 및 코덱스가 구현 중인 에이전트 시스템에 비침습적(Non-invasive) 방식으로 연동하여 8대 공통 증거 및 실증 ROI 지표를 모니터링·수집하기 위한 감사 로그 스펙을 정의함.

---

## 1. 수집 목적 및 8대 공통 증거 연계

| 수집 지표 영역 | 세부 수집 항목 | 8대 공통 증거 연계 | 비침습 수집 방식 |
| :--- | :--- | :--- | :--- |
| **A. 폐루프 Latency** | 단계별 처리 시간, 의사결정 수립 총 소요시간 | 1. 단일 폐루프 완주 증거<br>2. 정량적 개선 지표 | 에이전트 오케스트레이터 Event Hook / Middleware 로그 |
| **B. LLM 비용·품질** | 프롬프트/완성 토큰 수, Latency, hallucination 탐지 | 6. LLM 비용 대비 품질 지표 | API Gateway / LLM Proxy 감사 인터셉터 |
| **C. 데이터 계보 & 보안** | 에이전트간 데이터 이동, 접근 권한 검증 | 5. 보안·권한·데이터 계보 증적 | Event Bus Audit Stream |
| **D. 데이터 무결성** | 실데이터 ↔ 합성 데이터 스키마 일치 여부 | 3. 독립 데모용 합성 데이터 | Data Schema Validator 감사 체크 |
| **E. 권리 및 IP 이력** | 모듈 기여 주체, 코드/문서 이력 기록 | 7. IP 출처 및 기여 기록 | Git Context & `TEAM_BOARD.md` 증적 로그 |

---

## 2. Telemetry 감사 로그 이벤트 스키마 (Draft Spec)

### 2.1 에이전트 실행 감사 이벤드 (`agent_execution_audit`)
```json
{
  "event_id": "evt_20260804_001",
  "timestamp": "2026-08-04T21:07:00Z",
  "vertical_loop_id": "loop_raw_material_purchase_01",
  "agent_id": "agent_cost_simulator",
  "step_name": "material_cost_prediction",
  "metrics": {
    "execution_time_ms": 1420,
    "input_tokens": 1280,
    "output_tokens": 350,
    "estimated_cost_usd": 0.0024,
    "hallucination_score": 0.01
  },
  "context": {
    "data_mode": "SYNTHETIC", // REAL vs SYNTHETIC
    "provenance_author": "Claude Code",
    "security_level": "RESTRICTED"
  }
}
```

### 2.2 수직 폐루프 ROI 종합 리포트 스키마 (`closed_loop_roi_summary`)
```json
{
  "summary_id": "roi_sum_2026_w32",
  "loop_name": "원료 구매계획 ~ 손익/추적 수직 폐루프",
  "baseline_manual_hours": 24.0,       // 기존 수작업 소요시간 (시간)
  "system_execution_minutes": 15.2,   // AI 시스템 실행 소요시간 (분)
  "time_saving_percentage": 98.9,     // 시간 절감률 (%)
  "decision_accuracy_score": 96.5,    // 의사결정 정확도 (%)
  "total_llm_cost_usd": 0.42,         // 1회 완주 총 토큰 비용
  "roi_ratio": 57.1                   // 소요 비용 대비 가치 절감비
}
```

---

## 3. 구현팀(Claude Code / Codex)과의 협업 가이드

1. **비침습성 보장**: 본 명세서는 백엔드 및 UI 구현에 직접적인 코드 변경이나 과도한 종속성을 강제하지 않으며, 기존 로깅 및 이벤트 스트림에 감사 인터셉터를 결합하는 방식으로 작동합니다.
2. **독립적 수집 및 리포팅**: Antigravity는 본 스펙에 따라 생성된 로그를 파싱하여 **자동 ROI 리포트 및 Whitepaper 증적자료**를 독립적으로 생성합니다.

---
*본 명세서는 소스 코드 수정 없이 프로젝트 문서 자산으로 관리됩니다.*
