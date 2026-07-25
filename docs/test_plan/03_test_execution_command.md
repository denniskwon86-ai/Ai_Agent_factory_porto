# 🧪 테스트 실행 지시서 (Execution Directive)

> 이 문서는 **AI 에이전트(또는 개발자)에게 내리는 실행 명령서**다.
> 새 세션에서 아래 지시문을 그대로 복사해 붙여넣으면 테스트가 계획대로 자동 진행된다.

---

## 📌 복사용 지시 명령 (이걸 그대로 붙여넣으세요)

```
docs/test_plan/ 아래의 테스트 계획을 읽고 실효성 검증 테스트를 진행해줘.

1. 먼저 docs/test_plan/02_progress_tracker.md 를 읽고 현재 진행 상태를 파악할 것.
2. IN_PROGRESS 이거나 첫 번째 PENDING 인 Phase 부터 이어서 진행할 것.
3. 각 시나리오는 docs/test_plan/01_scenario_catalog.md 의 입력 데이터를 그대로 사용할 것.
4. 시나리오 1건을 끝낼 때마다 02_progress_tracker.md 의 해당 행을
   상태/점수/특이사항과 함께 즉시 갱신할 것 (끊겨도 이어갈 수 있도록).
5. 시나리오 전 태스크 완료 시, 반드시 POST /api/v1/factory/{project_id}/release API를 호출하여
   최종 결과물을 라이브러리에 게시(Release)하고 사용자 UI에서 확인 가능하도록 조치할 것.
6. 발견한 결함은 tracker 의 '발견된 결함 로그' 표에 기록할 것.
7. 한 번에 한 Phase 만 진행하고, Phase 가 끝나면 결과 요약을 보고할 것.
8. 토큰/컨텍스트가 소진될 것 같으면 진행 중이던 시나리오 상태를 tracker 에
   정확히 기록하고 멈출 것. 애매하게 중단하지 말 것.
```

---

## 🚦 실행 전 체크리스트 (Precondition & UI 검증)

| 항목 | 확인 | 조치 |
|---|---|---|
| `.env` 실 API 키 | `GOOGLE_API_KEY`, `groq_api_key` (선택: `CEREBRAS_API_KEY`) 가 실제 값인가 | 플레이스홀더면 P2 이후(LLM 필요) 진행 불가 |
| 백엔드 | `http://localhost:8080` 응답 | `.venv\Scripts\python.exe run.py` 로 기동 |
| 프론트 | `http://localhost:5173` 응답 | `cd frontend && npm run dev` |
| Cerebras 3차 폴백 | 로그에 `-> Cerebras(...)` 표시되는가 | `CEREBRAS_API_KEY` 설정 시 자동 활성 (미설정 시 Gemini→Groq 만) |
| 라이브러리 UI 노출 | 완주 후 UI의 **[결과물 라이브러리(Releases)]** 탭에서 산출물이 노출되는가 | 완주 직후 `/release` API 호환 및 정상 스냅샷 생성 여부 확인 |

## 🧭 Phase 진행 순서 (요약 — 상세는 00_master_plan.md)

```
P0 사전점검 → P1 구조테스트(LLM 불필요) → [P2 파일럿=관문]
   └ P2 실패 시: 원인 수정 우선, P3+ 중단
P2 성공 시 → P3 SW다양화 → P4 뷰타입 → P5 HOTL → P6 마케팅/분석
          → P7 제조 → P8 시뮬 → P9 메가 → P10 시스템 → P11 종합리포트
```

## 🎯 판정 기준 (요약)

- 시나리오당 30점 만점(6항목×5점). **24점↑ ✅ / 15~23 ⚠️ / 14↓ ❌**
- 루브릭 상세: `00_master_plan.md` 4절

## 🔁 중단·재개 규칙

- **중단 시**: 진행 중이던 시나리오를 `IN_PROGRESS` 로 두고, "세션 인수인계 메모"에 마지막 상태를 1줄 기록.
- **재개 시**: 위 "복사용 지시 명령"을 다시 붙여넣으면 tracker 기준으로 자동 이어짐.
- **쿼터 초과(429)**: 해당 시나리오를 `DEFERRED` 로 표시, Cerebras 폴백 동작 여부를 로그에서 확인 후 다음 무료 슬롯(다음날 등)에 재시도.

## 📂 관련 문서

- `00_master_plan.md` — 마스터플랜(Phase/루브릭/리스크)
- `01_scenario_catalog.md` — 39개 시나리오 입력 데이터 정의서
- `02_progress_tracker.md` — 진행 현황판(SSOT, 매 시나리오 갱신)
- `03_test_execution_command.md` — (이 문서) 실행 지시서

---
*생성: 2026-07-15 — LLM 3중 폴백(Gemini→Groq→Cerebras) 적용 후 테스트 준비 완료 상태.*
