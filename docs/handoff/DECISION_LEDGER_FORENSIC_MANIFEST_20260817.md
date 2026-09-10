# Decision Ledger 포렌식 보관 매니페스트

- **사고 ID**: `INC-LEDGER-20260817-01`
- **보관 파일 경로**: `data/archive/decision_ledger_polluted_20260817.db`
- **보관 일시**: 2026-08-17 (Asia/Seoul)
- **작성 주체**: Gemini Antigravity (교차검증 및 포렌식 감사) / Claude Code
- **참조 문서**: [DECISION_LEDGER_TEST_POLLUTION_INCIDENT_AND_RECOVERY_2026-08-17.md](file:///c:/WorkSpace/gemini_agent_team_verG/docs/handoff/DECISION_LEDGER_TEST_POLLUTION_INCIDENT_AND_RECOVERY_2026-08-17.md)

---

## 1. 포렌식 원장 무결성 지표

| 항목 | 원본 이동본 (`data/archive/decision_ledger_polluted_20260817_original.db`) | 보관 사본 (`data/archive/decision_ledger_polluted_20260817.db`) | 신규 활성 원장 (`data/decision_ledger.db`) |
|---|---|---|---|
| **SHA-256** | `d29ebab865a7bd4f0271d5f043782f20244790b71a571f7a7c15358ff7a7001f` | `d29ebab865a7bd4f0271d5f043782f20244790b71a571f7a7c15358ff7a7001f` | `36c34548eeaf385f9334e05b59145e51f1c924e6de03a3945ee6ffffd7fce04e` |
| **행 수 (Rows)** | 11,633 | 11,633 | **0 (클린 초기화)** |
| **최대 시퀀스 (Max Seq)** | 11,633 | 11,633 | **0** |
| **Tail Event Hash** | `5c72c7e814f6d44905c97792ac718ffe3309190ee1dc75468133ded96ac1f408` | `5c72c7e814f6d44905c97792ac718ffe3309190ee1dc75468133ded96ac1f408` | `"" (없음)` |
| **체인 검증 (`verify_chain`)** | `ok: True, checked: 11633, broken: 0` | `ok: True, checked: 11633, broken: 0` | `ok: True, checked: 0, broken: 0` |
| **파일 속성** | 읽기 전용 (Read-Only, `0o444`) | 읽기 전용 (Read-Only, `0o444`) | 읽기/쓰기 활성 (Read/Write) |

---

## 2. 오염 분류 쿼리 및 이중 기준(Dual Standard) 분석

### ① 협의 기준 vs 광의 기준 대조 요약
- **협의 기준 (Claude Code)**: **4,968건 / 11,633건 (42.7%)**
  - 명시적 시험 식별자 기반 필터: `actor_id IN ('t_admin@test.invalid', 'admin', 'bob', 'tester')` OR `project_id LIKE 'p_%'` / `project_id IN ('p1', 'PA', ...)`
- **광의 기준 (Codex / Antigravity 감사)**: **11,585건 / 11,633건 (99.64%)**
  - 누적 자동화 시험 계정 및 테스트 파이프라인 패턴 포함: `actor_id IN ('u@x', 'bob', 'kim', 't_admin@test.invalid')`
  - 주요 원인: `u@x` 계정의 자동화 대량 생성 이벤트(`APP_DATASET_CREATED` 5,764건), `kim` 계정(870건) 등이 협의 필터에서는 제외되었으나 실제로는 자동화 시험 반복 산물임.
- **불변 원칙**: 42.7%든 99.64%든 **선별 이관(Selective Migration)은 전면 기각**되며, 구 원장은 포렌식으로 전량 동결 보존하고 신규 빈 원장(0건)으로 시작합니다.

### ② Actor별 분포 (전체 11,633건)
```sql
SELECT actor_id, COUNT(*) AS count 
FROM decision_ledger_events 
GROUP BY actor_id 
ORDER BY count DESC;
```
- `u@x`: 5,764건 (자동화 시험 생성)
- `bob`: 4,925건 (시험 계정)
- `kim`: 870건 (시험 계정)
- `hikwon@lsmnm.com`: 27건
- `t_admin@test.invalid`: 26건
- 빈 값: 15건
- 기타/시험 표식: 6건 (`project_id='p_isolated'`)

### ③ 주요 이벤트 유형 분포
```sql
SELECT event_type, COUNT(*) AS count 
FROM decision_ledger_events 
GROUP BY event_type 
ORDER BY count DESC;
```
- `APP_DATASET_CREATED`: 5,764건
- `BLUEPRINT_APPROVED`: 3,503건
- `PROJECT_BOOTSTRAPPED`: 1,326건
- `BLUEPRINT_REJECTED`: 775건
- `DATA_REQUIREMENT_ACCEPTED`: 195건
- `APP_CONTRACT_APPROVED`: 23건
- `APP_CONTRACT_REVIEW_REQUESTED`: 9건
- `WBS_APPROVED`: 7건
- `APP_CONTRACT_REJECTED`: 3건

### ④ 2차 사고 추가 6건 (seq 11,628 ~ 11,633)
- `project_id='p_isolated'`
- `APP_CONTRACT_REVIEW_REQUESTED`: 1건
- `WBS_APPROVED`: 5건

---

## 3. 격리 및 보관 정책

1. **읽기 전용 동결**: `data/archive/decision_ledger_polluted_20260817.db`는 불변 증거로 영구 보존하며, 활성 런타임 및 테스트 조회 대상에서 제외한다.
2. **신규 활성 원장(P0-L4)**: 신규 `data/decision_ledger.db`는 깨끗한 상태(0건)로 초기화하며 구 원장 데이터를 임의로 이관하지 않는다.
3. **추적성 유지**: 본 매니페스트 및 인계서(`DECISION_LEDGER_TEST_POLLUTION_INCIDENT_AND_RECOVERY_2026-08-17.md`)가 구 원장과 신규 원장의 연결 고리 역할을 수행한다.
