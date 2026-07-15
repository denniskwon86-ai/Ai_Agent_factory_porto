# 테스트 진행 트래커 (SSOT — 시나리오 완료 시마다 즉시 갱신)

> 재개 방법: 새 세션에서 **"docs/test_plan/02_progress_tracker.md 읽고 테스트 이어서 진행해줘"**
> 상태: `PENDING`(대기) / `IN_PROGRESS`(진행 중) / `PASS` / `COND`(조건부) / `FAIL` / `DEFERRED`(쿼터 등으로 연기) / `SKIP`

## 전체 현황

| Phase | 상태 | 완료/전체 | 비고 |
|---|---|---|---|
| P0 사전 점검 | PENDING | 0/3 | 실 API 키 확보가 선행 조건 |
| P1 구조 테스트 | PENDING | 0/8 | LLM 불필요 — 키 없이도 진행 가능 |
| P2 파일럿(관문) | PENDING | 0/1 | 실패 시 P3+ 중단하고 원인 수정 |
| P3 SW 다양화 | PENDING | 0/5 | |
| P4 view_type 변형 | PENDING | 0/3 | |
| P5 HOTL 리비전 | PENDING | 0/2 | |
| P6 마케팅+분석 | PENDING | 0/4 | |
| P7 제조 4종 | PENDING | 0/4 | |
| P8 시뮬레이터 | PENDING | 0/2 | |
| P9 메가 프로젝트 | PENDING | 0/2 | |
| P10 시스템 기능 | PENDING | 0/6 | |
| P11 종합 리포트 | PENDING | 0/1 | |

## 시나리오별 상세

| ID | 상태 | 점수(/30) | 실행일 | 특이사항 |
|---|---|---|---|---|
| ENV-1 | PENDING | — | | |
| ENV-2 | PENDING | — | | |
| ENV-3 | PENDING | — | | |
| S-1 | PENDING | — | | |
| S-2 | PENDING | — | | |
| S-3 | PENDING | — | | |
| S-4 | PENDING | — | | |
| S-5 | PENDING | — | | |
| S-6 | PENDING | — | | |
| S-7 | PENDING | — | | |
| S-8 | PENDING | — | | |
| A-1 | PENDING | — | | 🚧 관문 시나리오 |
| A-2 | PENDING | — | | |
| A-3 | PENDING | — | | |
| A-4 | PENDING | — | | |
| A-5 | PENDING | — | | |
| A-6 | PENDING | — | | |
| A-7 | PENDING | — | | |
| A-8 | PENDING | — | | |
| A-9 | PENDING | — | | |
| A-10 | PENDING | — | | |
| A-11 | PENDING | — | | |
| B-1 | PENDING | — | | |
| B-2 | PENDING | — | | |
| C-1 | PENDING | — | | |
| C-2 | PENDING | — | | |
| D-1 | PENDING | — | | |
| D-2 | PENDING | — | | |
| D-3 | PENDING | — | | |
| D-4 | PENDING | — | | |
| E-1 | PENDING | — | | |
| E-2 | PENDING | — | | |
| F-1 | PENDING | — | | |
| F-2 | PENDING | — | | |
| G-1 | PENDING | — | | |
| G-2 | PENDING | — | | |
| G-3 | PENDING | — | | |
| G-4 | PENDING | — | | |
| G-5 | PENDING | — | | |
| G-6 | PENDING | — | | |

## 발견된 결함 로그

| # | 발견 시나리오 | 심각도 | 내용 | 상태 |
|---|---|---|---|---|
| (없음) | | | | |

## 세션 인수인계 메모

- 2026-07-15: 계획 수립 완료. 백엔드(8080)/프론트(5173) 기동 중. `.env`는 플레이스홀더 — **P0 진입 전 실 키 필요**.
