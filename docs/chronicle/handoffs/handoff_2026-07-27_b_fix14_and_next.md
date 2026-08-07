# 인수인계 — 결함 14건 수정 완료, 남은 과제 1건 (2026-07-27 오후)

> **대상 브랜치: `dev`** · 최종 커밋 `83d64437c` · `pytest 289 passed`
> 앞선 문서: [handoff_2026-07-27_a1_completion.md](handoff_2026-07-27_a1_completion.md) (오전 조사 — 함정 6가지가 거기 있다. **반드시 먼저 읽을 것**)

---

## 0. 30초 요약

- **한 일**: A-1 완주를 막던 결함 **14건**을 근본 원인까지 추적해 수정·커밋. 테스트 4회 실행(v5~v8).
- **결과**: A-1 **아직 미완주.** 그러나 병목이 4번 이동했고 그때마다 원인을 제거했다.
- **남은 과제 1건**: **리뷰어 피드백이 개발자에게 전달되지 않는다.** 리뷰어가 정확한 결함과 해결책을 제시하는데 재작업 8회 동안 반영되지 않는다. 이것이 현재 유일한 차단 요인이다.
- **중요한 성격 변화**: 지금까지의 실패는 전부 **우리 인프라가 정상 코드를 거짓 반려**하는 것이었다(전부 수정 완료). 남은 하나는 **진짜 코드 결함을 못 고치는** 문제다 — 성격이 다르다.

---

## 1. 병목 이동 기록 (이게 이번 작업의 핵심 서사)

| 실행 | 막힌 지점 | 원인 | 조치 |
|---|---|---|---|
| v5 | 코드 생성이 전부 llama | Pro 체인에 살아있는 Gemini 없음 + 일시적 실패에 30분 배제 | A1, 쿨다운 분류 |
| v6 | `TECH_SPEC` 0.65 고정 | llama 역량 한계 (`api_contract=0.4`) | 유료 Gemini 전환 |
| v7 | 렌더 검증 9회 실패 | **하네스가 다중 디렉터리 구조를 거짓 반려** | 지연 모듈 해석 |
| v8 | 리뷰어 지적 미반영 | **← 남은 과제** | 미착수 |

v7에서 `TECH_SPEC`이 **1.0 만점 6회 연속**을 기록했다. 모델 문제는 해결됐다.
v8에서 **렌더 검증 7회 통과 / 실패 0회.** 하네스 문제도 해결됐다.

---

## 2. ★ 남은 과제 — 리뷰어 피드백 전달 경로

### 증상 (v8 실측)

리뷰어의 마지막 의견:
> `index.html` 파일에는 `src/js/main.js` 스크립트를 로드하는 태그가 누락되어 있습니다.
> `<body>` 태그 닫히기 직전에 `<script src="./src/js/main.js"></script>` 태그를 추가하십시오.

**정확하고 타당한 지적이며 해결책까지 구체적이다.** 그런데 재작업 8회 동안 이 한 줄이 반영되지 않고 `supervisor_hops` 상한에 도달해 `FAILED_REVIEW` 로 종결됐다.

### 조사 시작점 (우선순위 순)

1. **`_targeted_repair_instruction`([nodes/execution.py](../nodes/execution.py))이 `build_error_log` 만 본다.**
   리뷰어 의견은 `reviewer_feedback` 필드로 온다. 정밀 복구 지시가 리뷰 경로에는 적용되지 않는다. **가장 유력하다.**

2. **재작업 라우팅이 Tech Lead 를 경유한다.**
   `route_from_reviewer` 의 `REWORK_DEV` → `"Tech_Lead"`([core/agent_graph.py](../core/agent_graph.py)).
   Tech Lead 가 재설계를 거치면서 "스크립트 태그 한 줄 추가"라는 구체적 지시가 희석될 수 있다.
   개발자 프롬프트에 `reviewer_feedback` 원문이 **그대로** 도달하는지 확인할 것.

3. **`index.html` 이 개발자 소유 파일에 포함되는가.**
   `_FE_OWNED_EXTS` 에 `.html` 은 있다. 그러나 실제로 컨텍스트에 주입되고 재출력 대상이 되는지 확인 필요.

4. **v8 은 React 가 아니라 바닐라 JS 앱이었다**(`src/js/main.js`, `index.html`).
   렌더 하네스는 React 기준이라 이 구조를 제대로 검증하지 못했을 가능성이 있다
   (렌더 7회 통과가 **의미 있는 통과였는지** 확인할 것 — 통과 자체가 거짓양성일 수 있다).

### 재현 근거

실패 번들이 저장되어 있다:
```
projects/test_a1_v8/.failures/E2E-01_20260727T050156Z.json
```
생성 응답 원문·리뷰 의견·빌드 오류가 모두 들어 있다. **여기서 시작하는 것이 가장 빠르다.**

---

## 3. 이번에 고친 14건

### 모델·라우팅
| # | 내용 | 근거 |
|---|---|---|
| A1 | `gemini-2.5-flash` 를 Pro 체인 편입 + 코드 생성 적격성 정책(`CODE_GEN_MIN_OUTPUT_TOKENS`) | v3 100/100, v4 35/35 호출이 전부 llama, Gemini 0회 |
| — | **Pro 체인 제공사 매핑 파손 수정** | `LLM_PRO_FALLBACK_LIST` 는 **위치=제공사** 매핑이다. 항목을 끼워 넣었더니 `xAI(gemini-2.5-flash)` 체인이 생성됐다. → `PRO_TIER_EXTRA_GEMINI` 로 분리 |
| — | 일시적 실패에 30분 배제 → 90초(`TRANSIENT_MODEL_COOLDOWN_SEC`) | 체인이 뒤쪽 모델로 **성공**하면 앞선 모델들이 오류 정보 없이(`with_fallbacks` 가 개별 실패를 삼킴) 전부 쿼터사로 간주돼 배제됐다. 실측: attempts=10 → 이후 attempts=1 로 붕괴 |
| — | `GEMINI_MAX_RETRIES=2` + sticky winner | `max_retries=0` 이라 분당 제한 한 번에 즉시 폴백했다. sticky winner 는 마지막 성공 모델을 다음 호출 맨 앞으로 |
| — | OpenRouter 유료 백스톱을 llama → `google/gemini-2.5-flash` | 무료 Gemini 일일 쿼터 전소진 시 체인에 고출력 모델이 하나도 안 남는다. 실측: 구조화 출력 2.1초(llama 20초+), 출력 65,535(llama 8,192) |

### 실패 처리 (가짜 통과 제거)
| # | 내용 |
|---|---|
| B1 | **종료 상태 모델** — `END`≠`DONE`. `terminal_status` 도입, Reviewer 의 best-effort PASS 제거 |
| B2 | **생성 실패 분류** — 공급자 타임아웃이 개발자 재작업 예산을 먹지 않게(`GenerationFailure`) |
| B3 | **`TerminalHandler` 신설** — 롤백·실패 번들. 기존 롤백 분기는 **도달 불가능한 죽은 코드**였다 |

### 생성 구조
| # | 내용 |
|---|---|
| C1 | `CodeFilesOutput` — 아무도 안 읽는 `state_updates` 제거. **결함 #15(구조화 출력 폭주) 발생 0건 달성** |
| C2 | 죽은 스웜 분기(`_heavy=True` 하드코딩으로 항상 1개), 정밀 복구, 검증 대상을 디스크로 |
| C3 | `server_api_required=false` 연동 |
| C4 | CodeBuilder 전부-아니면-전무 트랜잭션(기존 `any(results)` → 부분 반영도 성공 처리) |

### 하네스 (거짓 반려 제거)
| # | 내용 |
|---|---|
| D1 | 백엔드 스모크 `cwd` — 상대 경로 DB 를 쓰는 정상 앱을 반려했다. **수정 후 FastAPI 라우트 8개 부팅 성공** |
| — | **렌더 하네스 지연 모듈 해석** — 파일을 배열 순서대로 로드해 `components/*` 가 `utils/*` 보다 먼저 로드되면 실제 존재하는 파일도 '미해결 모듈'이 됐다. **모델이 코드를 잘 분리할수록 더 확실히 반려되는 역설.** 또한 App 탐색 정규식이 정규화 키(확장자 제거)와 안 맞아 **절대 매치되지 않던** 상태였다 |
| E | 설계서 Phase 0 4건(P0-1~4) + `get_relevant_context` 무필터 주입 차단 |

---

## 4. 재개 절차

```powershell
# 1) 잔존 프로세스 정리 (포트 8080 은 단일 — 앞 문서 함정 2)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'run\.py|run_e2e_scenario' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) 회귀 확인 (반드시 venv 인터프리터 — 앞 문서 함정 1)
.\venv\Scripts\python.exe -m pytest -q -p no:warnings   # 289 passed 여야 함

# 3) 실패 번들부터 읽기
type projects\test_a1_v8\.failures\E2E-01_20260727T050156Z.json
```

**새 테스트는 반드시 새 프로젝트 이름으로** (`test_a1_v9`). v5~v8 은 전부 오염 상태이며 `--resume` 은 소진된 `supervisor_hops` 를 물려받는다(앞 문서 함정 3).

```powershell
.\venv\Scripts\python.exe run_e2e_scenario.py test_a1_v9
```

---

## 5. 이번 작업에서 배운 것 (반복 방지)

1. **`LLM_PRO_FALLBACK_LIST` 에 항목을 끼워 넣지 말 것.** 위치=제공사 매핑이다. Gemini 추가는 `PRO_TIER_EXTRA_GEMINI` 로.
2. **PowerShell `Get-Content -Raw` / `Set-Content` 왕복으로 소스를 일괄 치환하지 말 것.** UTF-8 한글이 깨진다(실제로 `llm_gateway.py` 를 한 번 깨뜨려 git 복원했다). 편집 도구를 쓸 것.
3. **하네스가 앱을 반려할 때는 하네스를 먼저 의심할 것.** 이번에 고친 14건 중 **3건이 하네스의 거짓 반려**였다(#20 브라우저 전역, D1 cwd, 지연 로딩). 공통 패턴: *요구한 대로 만든 것을 감점한다.*
4. **가짜 통과를 제거하면 진짜 병목이 드러난다.** B1 수정 전에는 모든 실패가 `DONE` 으로 위장돼 어디가 문제인지 알 수 없었다. 지금 보이는 실패는 **진단이 정확해졌다는 신호**다.

---

## 6. A-1 완주 판정 기준 (변경 없음)

1. WBS 전 태스크 `DONE` · 2. QA 통합검수 통과 · 3. 수용검수 통과 · 4. **라이브러리 게시 확인** · 5. 렌더 검증이 실제로 실행되어 통과

`terminal_status` 가 `COMPLETED` 가 아닌 종결은 **전부 실패로 기록된다**(B1). best-effort 수용은 더 이상 존재하지 않는다.
