# 테스트 실행 지시서

> 기준일: 2026-07-26 | 대상: 개발자 및 AI 실행 에이전트
> 이 문서는 테스트를 빨리 끝내기 위한 지시가 아니라, **실패 원인을 잃지 않고 재현 가능한 품질 증거를 만드는 운영 절차**다.

## 복사용 실행 지시

```text
docs/test_plan/00_master_plan.md, 01_scenario_catalog.md,
02_progress_tracker.md, 04_evidence_and_failure_taxonomy.md를 읽고 테스트를 이어서 진행한다.

1. 트래커와 최신 프로젝트 상태를 먼저 대조해 현재 실행 소유자·프로젝트·단계를 확인한다.
2. 다른 실행자/서버/자동 드라이버가 동작 중이면 새 서버를 띄우거나 같은 프로젝트를 재시작하지 않는다.
3. IN_PROGRESS 시나리오는 /state/latest, /wbs, /hotl/check, /feed로 실제 상태를 확인한 뒤에만 재개한다.
4. 시나리오 입력과 HOTL 정책은 01_scenario_catalog.md를 따른다. A-10/A-11은 자동승인하지 않는다.
5. 종료·실패·보류마다 증거 묶음과 원인 태그를 남기고 02_progress_tracker.md를 갱신한다.
6. P2는 PASS가 아니면 P3+를 시작하지 않는다. 외부 LLM 장애는 시스템 FAIL과 구분하되 PASS로 간주하지 않는다.
7. Release 및 UI 확인까지 마친 뒤에만 파이프라인 완주를 PASS로 판정한다.
```

## ⚠️ [2026-07-29 추가] A-1 재카나리 전용 준비물 — 이것이 없으면 계측이 또 빈다

1차 카나리(`test_a1_unitconv_canary1`)는 **완주했지만 판정에 쓸 수 없었다.** 이유는 실행 방식이지
시스템 결함이 아니다 — 그래서 재카나리 전에 아래를 반드시 지정한다.

| 준비물 | 왜 | 지정하지 않으면 |
|---|---|---|
| **지식팩 연결**(`knowledge_pack_ids`) | 그라운딩 실측 | 1차처럼 `[]` — 지식 주입 0, 그라운딩 효과 판정 불가 |
| **`master_domains`** | 기준정보 주입 대상 결정 | 도메인 필터가 없어 D-010(전수 주입) 실증이 무의미해진다 |
| **`enterprise_scope_id`** | 조직 범위 격리 실측 | 범위 필터가 통과 모드로 돌아 격리 검증이 안 된다 |

> ★ **계측을 갖추는 것과 측정 대상이 있는 것은 다르다.** 1차 카나리는
> `knowledge_pack_ids: []` · `master_domains: []` 로 실행돼 **그라운딩 없이 완주**했다.
> 계측을 다 만들어도 주입할 것이 없으면 블록 길이는 여전히 0 이다.

**실행 후 판정은 판독기로 한다** (LLM 0콜, 수동 확인 불필요):

```
venv\Scripts\python.exe scripts\canary_report.py <프로젝트명>
venv\Scripts\python.exe scripts\canary_report.py --list      # 기록된 프로젝트 목록
```

계측 5종(모델·폴백사유 / 토큰·비용·지연 / 컨텍스트 길이·지식팩 / 재작업·실패원인 / 게이트·완주)을
읽어 **Close 가능 여부까지 판정**한다. 그 출력이 `QUALITY-TEL-01` 의 자동화 검증 증적이다
(UI 조회 증적은 별도).

## 실행 전 체크리스트

| 항목 | 확인 | 조치 |
|---|---|---|
| 작업 소유권 | 다른 자동 드라이버, Claude/Codex, 개발자 실행이 있는가 | 동일 프로젝트·트래커를 동시에 수정하지 않음 |
| 백엔드 | `http://localhost:8080` 및 `/docs` 응답 | 미기동일 때만 `.venv\Scripts\python.exe run.py` |
| 프론트 | `http://localhost:5173` 응답 | 미기동일 때만 `frontend`에서 `npm run dev` |
| Python 환경 | `.venv\Scripts\python.exe -m pytest`가 프로젝트 의존성을 읽는가 | 시스템 Python과 혼용하지 않음 |
| LLM 공급자 | Gemini, xAI, Groq, Cerebras, OpenRouter 중 활성/비활성 사유가 로그에 드러나는가 | API 키·패키지 미설정은 숨기지 말고 기록 |
| 비밀값 | 로그·트래커에 API 키/토큰/원문 개인정보가 없는가 | 값 대신 공급자명·오류 코드만 기록 |
| UI 판정 | SSE 연결, HOTL 입력, 프리뷰, Releases 표시를 확인할 수 있는가 | UI 미확인 상태는 PASS 불가 |

현재 폴백 순서는 구성에 따라 Gemini → xAI → Groq → Cerebras → OpenRouter이며, 키/패키지 미설치 공급자는 의도적으로 비활성화된다. “설치됨”과 “실제 호출 가능”은 별도 검증 항목이다.

## 권장 실행 흐름

1. P0/P1은 API와 정식 테스트 스위트로 기본 회귀를 확인한다.
2. P2 A-1은 단독 서버·단독 프로젝트에서 실행한다.
3. 자동 완주 드라이버를 사용할 때:

```powershell
.venv\Scripts\python.exe run_e2e_scenario.py test_a1_unitconv
# 이미 생성된 프로젝트의 정상 체크포인트만 이어갈 때
.venv\Scripts\python.exe run_e2e_scenario.py test_a1_unitconv --resume
```

`--resume`은 새 기획을 만들지 않는다. 먼저 상태를 확인하지 않은 재개, 같은 task ID의 중복 start, 실행 중 서버 재기동은 금지한다. 드라이버의 A-1 HOTL 자동승인은 요구 확인 단계에서 추천안을 선택하고 나머지는 무피드백 승인하는 **무인 완주 시험 전용** 정책이다.

4. 각 WBS 태스크 종료 때 `DONE`/`FAILED`와 `build_error_log`를 확인한다. `FAILED`면 다음 태스크를 시작하지 않는다.
5. 전 태스크 `DONE` 뒤 `POST /api/v1/factory/{project_id}/release`와 UI Releases 노출을 확인한다.
6. 한 시나리오의 증거를 기록하고 트래커를 갱신한 후에만 다음 시나리오로 이동한다.

## 실패·중단 처리

| 상황 | 즉시 조치 | 트래커 상태 |
|---|---|---|
| 공급자 429/504/네트워크 | 제한 재시도 결과, 활성 공급자, 최종 상태를 보존 | `DEFERRED` 또는 `COND` 후보 + `EXTERNAL` 태그 |
| 파이프라인 예외/상태 불일치 | `feed`, 서버 로그, `latest_state`, WBS를 보존하고 실행 중지 | `FAIL` + `SYSTEM` 태그 |
| 빌드 3회 실패 | 실패한 파일/검사/롤백/HOTL·`SPRINT_FAILED` 이벤트 확인 | `FAIL` + `BUILD_RECOVERY` 태그 |
| 15분 무활동 | 드라이버 스톨 기록 후 서버 로그·checkpoint 확인 | `IN_PROGRESS` 또는 `DEFERRED`; 원인 확인 전 PASS 금지 |
| 사용자 피드백 시나리오 | A-10/A-11의 지정 피드백을 실제 입력 | 자동 승인 금지 |

`COND`는 필요한 산출물 증거는 있으나 외부 장애 또는 비핵심 검증이 남은 경우에만 쓴다. `FAIL`을 `COND`로 바꿔 통과시키지 않는다. 상세 정의와 최소 증거는 `04_evidence_and_failure_taxonomy.md`에 따른다.

## 관련 문서

- `00_master_plan.md` — 범위, 게이트, 루브릭, 재개 원칙
- `01_scenario_catalog.md` — 입력 데이터와 시나리오별 수용 조건
- `02_progress_tracker.md` — 실행 현황 SSOT (실행 소유자만 갱신)
- `04_evidence_and_failure_taxonomy.md` — 결과 기록 양식과 실패 분류
