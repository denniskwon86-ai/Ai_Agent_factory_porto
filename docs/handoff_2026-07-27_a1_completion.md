# 인수인계 — A-1 관문 시나리오 완주 (2026-07-27 00:20 기준)

> **이 문서의 목적**: 다른 실행 환경(코덱스 등)이 **A-1 완주 작업을 그대로 이어받아 끝낼 수 있도록** 하는 것.
> 대화 맥락 없이 이 문서만 읽고 재개할 수 있게 작성했다.
> **작업 대상 브랜치: `dev`** (origin 계열은 보관용, `main`은 README 골격)
> 직전 커밋: `ccd629dd7`

---

## 0. 30초 요약

- **하는 일**: A-1(단위 변환기 웹앱) 시나리오를 **끝까지** 완주시켜, 이 플랫폼이 앱 하나를 실제로 만들어 게시할 수 있음을 처음으로 증명하는 것.
- **왜 중요한가**: `docs/business_value_assessment.md` 의 결론이 "설계는 시장의 빈 자리를 정확히 겨눴지만 **된다는 증거가 하나도 없다**". 완주 사례 1건이 어떤 기능 추가보다 가치가 크다.
- **지금 상태**: 프로젝트 `test_a1_v3` 에서 **E2E-01 DONE, E2E-02 진행 중, E2E-03~05 대기.** 서버·드라이버가 **실행 중이다**(§3).
- **이번 세션 성과**: 완주를 막고 있던 결함 3건(#19-b·#20·#21)을 근본 원인까지 추적해 수정. 특히 **#20 은 우리 검증 하네스가 정상 코드를 거짓 반려하던 결함**이었다.
- **남은 유일한 미해결 결함**: #15(구조화 출력 폭주). 간헐적(코드 생성 호출의 약 25%)이며 재시도로 회피된다. 완주를 막지는 않는다.

---

## 1. 이번 세션에서 고친 결함 (커밋 `6c5034d12`)

세 건 모두 **"재작업 루프가 겉으로는 도는데 실제로는 아무것도 개선되지 않는다"** 는 같은 증상의 서로 다른 원인이었다.

### #19-b — 감시 데몬의 판정 캐시 (Critical)

- **파일**: `core/supervisor_daemon.py:62,117`
- **무엇**: 결함 #19(판정 성격 LLM 호출의 캐시 우회)를 전수 점검했는데 `nodes/` 만 훑고 `core/` 의 감시 데몬을 빠뜨렸다.
- **왜 해로운가**: 이 데몬은 **파이프라인 일시정지(개입)를 시도**한다. 캐시된 옛 판정이 재생되면 **이미 해소된 결함으로 현재 스프린트를 멈춘다.**
- **증거**: #19 수정 후에도 해시 `3d744629` 히트가 계속 재발했고, 출처가 여기였다(`is_heavy=False, output_mode="json"` → `flash_router json` 경로).
- **조치**: `aexecute` 2곳에 `cacheable=False`.
- **교훈**: #19 자체가 "한 곳에서 배운 교훈이 형제 코드에 전파되지 않는 약점"을 지적했는데, **그 수정조차 같은 방식으로 한 디렉터리를 빠뜨렸다.** 앞으로 이런 전수 점검은 `grep -rn` 을 **리포 전체**에 걸 것.

### ★ #20 — 렌더 검증 하네스가 정상 코드를 거짓 반려 (Critical, 이번 세션 최대 발견)

- **파일**: `frontend/scripts/render_check.mjs`
- **무엇**: 이 하네스는 **맨 Node 에서 `renderToString`** 하는데 **브라우저 전역이 하나도 없었다.**
- **결과**: PRD 가 명시적으로 요구한 '변환 이력 저장'을 `localStorage` 로 **올바르게** 구현한 코드가
  `초기 렌더 런타임 에러: localStorage is not defined` 로 실패 처리됐다.
  실제 프리뷰(`PreviewPanel`)는 브라우저이므로 그 코드는 **정상 동작한다.**
  즉 **요구한 대로 만든 것을 감점**하고, 재작업 루프에 "고칠 수 없는 것을 고쳐라"를 8회 반복시켰다.
- **조치**: `localStorage`·`sessionStorage`·`window`·`document`·`navigator`·`matchMedia` **최소 스텁** 주입.
  - ⚠️ **스텁을 늘리지 말 것.** '브라우저라면 반드시 있는 것'으로만 제한했다. 과잉 스텁 시 진짜 깨진 코드가 통과해 검증 자체가 무의미해진다.
  - `document.getElementById` 는 의도적으로 `null` 반환 — 브라우저 초기 렌더와 동일하며, null 미확인 접근은 여기서 잡혀야 한다.
- **실측 검증**: 수정 전 실패 → 수정 후 현재 `test_a1_v3` 산출물로 **`ok=true, rendered=780`**.
- **왜 늦게 발견됐나**: #13·#19 를 고쳐 **재작업 루프가 실제로 돌기 시작한 뒤에야** 드러났다. 그 전에는 캐시가 루프를 무력화해 이 단계까지 오지 못했다.

### #21 — 전체 파일 재출력 강제의 부작용: 재작업 회귀 (Major)

- **파일**: `nodes/execution.py` (`_INCREMENTAL_GUARD`, 렌더 실패 메시지)
- **무엇**: 앞 회차에서 고친 결함(존재하지 않는 `./App.css` import)이 **다음 회차 전체 재출력에서 되살아났다.**
  실측: 렌더 검증 `srv6` 통과 2건 → `srv7` 실패 1건, **같은 결함 재출현.**
- **조치 (A) 예방**: `_INCREMENTAL_GUARD` 에 두 규칙 추가
  - **import 규칙**: 상대경로 import 는 같은 응답의 `files` 배열에 파일을 함께 생성하거나, import 를 삭제할 것
  - **회귀 금지**: 전체 재출력 시에도 앞 회차 수정 상태를 유지할 것
- **조치 (B) 교정**: 렌더 실패 메시지에서 누락 파일명을 정규식으로 추출해
  `(1) 그 파일도 함께 생성 (2) import 삭제` **두 선택지를 명시**하고, 이전 수정을 되돌리지 말라고 경고.
  - 기존 문구는 "외부 import / null 안전성" 일반론뿐이어서 **가장 흔한 실패인 '미해결 상대 모듈'의 해결책을 알려주지 못했다.**

### 검증

`pytest 258 passed (exit 0)` — **반드시 PowerShell 로 실행**(§5 함정 1).

---

## 2. A-1 완주 판정 기준 (이걸 만족해야 PASS)

`docs/test_plan/02_progress_tracker.md` 의 규칙에 따라:

1. WBS 5개 태스크(E2E-01~05) **전부 `DONE`**
2. QA 통합 검수 통과
3. 수용검수(Acceptance) 통과
4. **라이브러리 게시(Release)까지 확인** — 게시 검증 없이는 최종 PASS 로 기록하지 말 것
5. 프론트 렌더 검증이 **실제로 실행되어** 통과했을 것 (건너뛰기/best-effort 수용은 증거로 부족)

---

## 3. 지금 실행 중인 것 (그대로 이어받을 수 있음)

| 대상 | PID | 비고 |
|---|---|---|
| 백엔드 서버 | 부모 `32480` / 자식 `29388` | **8080 소유자는 자식 `29388`** |
| E2E 드라이버 | 부모 `26248` / 자식 `19344` | `run_e2e_scenario.py test_a1_v3 --resume` |

로그 경로(세션 스크래치패드 — 이 환경 종료 후에도 파일은 남음):

```
C:\Users\denni\AppData\Local\Temp\claude\C--WorkSpace-gemini-agent-team-verG\904b709c-9903-4d90-a354-e7dac9f9f6e0\scratchpad\srv8.log
...\scratchpad\srv8.log.err
...\scratchpad\drv8.log
...\scratchpad\drv8.log.err
```

런타임 증거: `data/llm_call_log.jsonl` (LLM 호출 이력), `data/interaction_log.jsonl`

**드라이버는 HOTL 게이트를 자동 승인하며 계속 진행한다.** 방치해도 E2E-05 까지 시도한다.

---

## 4. 이어받는 절차

### 4-A. 계속 돌고 있으면 (권장)

상태만 확인하고 완주를 기다린다.

```bash
curl -s http://127.0.0.1:8080/api/v1/factory/test_a1_v3/wbs
```

```powershell
Get-Content "$env:LOCALAPPDATA\Temp\claude\C--WorkSpace-gemini-agent-team-verG\904b709c-9903-4d90-a354-e7dac9f9f6e0\scratchpad\drv8.log" -Tail 20
```

전 태스크 `DONE` 이 되면 **게시(Release)까지 확인**한 뒤 트래커에 결과를 기록한다.

### 4-B. 죽었거나 새로 시작해야 하면

```powershell
# 1) 잔존 프로세스 정리 (8080 은 단일 — §5 함정 2)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'run\.py|run_e2e_scenario' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) 판정 캐시 오염 제거 (재개 전 권장)
Remove-Item data\llm_cache.db -Force -ErrorAction SilentlyContinue

# 3) 회귀 확인
.\venv\Scripts\python.exe -m pytest -q -p no:warnings

# 4) 서버 기동
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "run.py" -RedirectStandardOutput "srv9.log" -RedirectStandardError "srv9.log.err" -WindowStyle Hidden

# 5) 준비 대기 후 드라이버
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "run_e2e_scenario.py","test_a1_v3","--resume" -RedirectStandardOutput "drv9.log" -RedirectStandardError "drv9.log.err" -WindowStyle Hidden
```

서버 준비 확인: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/docs` → `200`

### 4-C. 깨끗한 증거가 필요하면 새 프로젝트로

`test_a1_v3` 의 **E2E-01 기록은 `best-effort 수용`으로 오염되어 있다**(§6). 대외 제출용 증거가 필요하면 새 프로젝트(`test_a1_v4`)로 처음부터 돌린다. 기획 파이프라인 재실행 비용은 약 7분 / 약 $1 수준.

```powershell
.\venv\Scripts\python.exe run_e2e_scenario.py test_a1_v4
```

---

## 5. 반드시 알아야 할 함정 (여기서 실제로 사고가 났던 것들)

### 함정 1 — ★ Python 은 반드시 PowerShell 로 실행할 것

Bash 툴 샌드박스가 **네이티브 `.pyd` 확장 로드를 차단**한다. `ormsgpack` DLL 로드가 실패해 langgraph import 가 죽고, **pytest 가 전부 깨진 것처럼 보인다.**
→ Python 실행은 전부 PowerShell. 인터프리터는 `.\venv\Scripts\python.exe` (맨 `python` 은 다른 3.14 를 잡아 pytest 가 없다).

### 함정 2 — ★ 포트 8080 은 단일이다

이 환경에서 **서버를 재시작해 외부 세션이 돌리던 스프린트를 죽인 사고가 있었다.**
서버를 만지기 전에 다른 환경이 테스트 중인지 확인할 것.

### 함정 3 — ★ `--resume` 는 재작업 예산을 복구하지 못한다

`supervisor_hops` 는 **태스크마다 `sprint/start` 에서 0으로 리셋**된다([api/routes/factory_control.py:592](../api/routes/factory_control.py#L592)).
그런데 `--resume` 는 **LangGraph 체크포인트를 복원**하므로 소진된 `hops=8` 을 그대로 물려받고, 리뷰어가 **즉시 `best-effort 수용`** 을 찍는다(렌더 검증조차 실행되지 않음).
→ **수정한 코드의 효과를 검증하려면 진행 중이던 태스크를 `--resume` 하지 말고, 새 태스크 또는 새 프로젝트에서 확인할 것.**

### 함정 4 — 같은 실수를 두 번 한 지점: 출력 상한을 올리지 말 것

`config.MODEL_OUTPUT_LIMITS` 의 `8192` 를 **올리지 마라.** 8192 실패 → 16384 로 올려도 16384 에서 동일 실패했다(#15). 상한 부족이 아니라 폭주다. config 에 주석으로 박아뒀다.

### 함정 5 — 타임아웃을 올리는 것은 벽을 옮기는 것일 뿐일 수 있다

56~59초 실패를 타임아웃으로 진단해 늘렸더니 178~191초 실패로 바뀌었다. 실패 시각이 상한에 붙어 있으면 **상한이 원인이 아닐 가능성**을 먼저 의심할 것.

### 함정 6 — 스냅샷이 아니라 시퀀스를 볼 것

"오염되지 않았다"고 잘못 판단한 적이 있다. 재시도 카운터·`build_status` 같은 **스냅샷 지표**는 정상으로 보였지만, 텔레메트리 **시퀀스**를 보니 9초에 같은 해시로 캐시 히트 38건이었다. 판단 근거는 시퀀스에서 찾을 것.

---

## 6. `test_a1_v3` 의 알려진 오염 (정직한 기록)

- **E2E-01 은 `재작업 상한(8) 도달 - best-effort 수용` 으로 종결됐다.** 재개 시 함정 3 때문에 소진된 예산을 물려받았고, 이는 되돌릴 수 없다.
- **실질적으로는 정상**이다: `reviewer_decision=PASS`, `build_status=success`, `CODE_REVIEW=1.0`, 그리고 산출물이 렌더 검증을 **독립적으로 통과**한다(`ok=true, rendered=780`, 별도 실측).
- 그러나 **"깨끗한 통과"라고 주장할 수는 없다.** E2E-02~05 는 각각 새 예산 8을 받으므로, **완주 증거는 그쪽에서 확보한다.**

### 현재 산출물 (`projects/test_a1_v3/`)

| 파일 | 크기 | 내용 |
|---|---|---|
| `src/App.tsx` | 3,691B | 변환기 3종 + 이력 UI |
| `src/conversion.ts` | 1,247B | 계수 정확(2.54 / 2.20462 / °F=°C×9/5+32) |
| `src/storage.ts` | 504B | localStorage 이력 저장 |
| `main.py` | 3,012B | FastAPI 백엔드 |

---

## 7. 미해결 결함 #15 — 구조화 출력 폭주 (OPEN)

- **증상**: `with_structured_output(CodeOutput)` 로 코드를 뽑을 때 모델이 종료하지 않고 `completion_tokens` 상한을 정확히 소진 → `Could not parse response content as the length limit was reached`.
- **성격**: 간헐적(코드 생성 호출의 약 25%), 1회당 약 3분 소모. **프롬프트 크기와 무관**(6,160 / 9,172 / 13,350 토큰에서 모두 발생).
- **현재 대응**: 재시도(새 표본)로 회피. #13 수정이 그 경로를 복구했다.
- **근본 대응 후보 (사용자 승인 필요)**:
  - **(A) 권고** — `CodeOutput` 스키마에서 **ADR·기술부채·파일인덱스를 files 와 분리**. 큰 코드 문자열과 메타데이터를 한 스키마에 섞는 것이 폭주 유인으로 의심된다.
  - (B) `with_structured_output` 대신 자유 JSON(`output_mode="json"`) + 자체 파싱.
- 완주를 **막지는 않는다.** A-1 이 끝난 뒤 다루는 것이 맞다.

---

## 8. 이 저장소의 구조적 약점 (반복 확인됨)

**한 곳에서 배운 교훈이 형제 코드에 전파되지 않는다.** 이 패턴으로만 결함 4건이 나왔다.

| 고쳐진 곳 | 빠져 있던 형제 |
|---|---|
| `debate.py:179,202` `cacheable=False` | 개발자 노드(#13), `debate.py:143` 비평가(#19) |
| `DebtItem` 동의어 흡수 | `ADR` (#17) |
| `nodes/` 판정 호출 캐시 우회(#19) | `core/supervisor_daemon.py` (#19-b) |

**이 결함군은 조용히 실패한다** — 에러가 없고, 오히려 "캐시 히트로 비용 절감"처럼 보이면서 실제로는 재작업 루프를 무력화하고 `best-effort 수용`으로 가짜 `DONE` 을 만든다.
→ **원칙: 생성물은 캐시해도 되지만, 판단(심사·채점·비평·검수)은 매번 새로 해야 한다.**
→ 유사 수정 시 반드시 리포 전체에 `grep -rn` 을 걸 것.

---

## 9. A-1 이후의 대기 작업 (모두 미착수)

- `docs/design_org_permission_enterprise.md` — 조직·권한·부서 게시·전사 데이터 표준·전사 검색·시뮬레이션 (Phase 0~13). **설계만 완료, 코드 미착수.**
- `docs/design_backbone_system_platform.md` — 기간계(ERP/MES급) 전환 로드맵 ①~⑤ + 게이트 G0~G4. **구상 단계.**
- `docs/business_value_assessment.md` — 사업 가치 평가. **우선순위 1번이 "실제 업무 1건 완주 + 게시"** 로 못박혀 있다. 그것이 지금 이 작업이다.

**A-1 완주 전에는 위 설계 구현을 시작하지 말 것** — 사업 평가의 결론이 그렇다.

---

## 10. 커밋 이력 (이번 세션)

| 커밋 | 내용 |
|---|---|
| `6c5034d12` | fix: 결함 #19 확장(감시데몬 캐시) + #20 렌더 하네스 거짓실패 + 재작업 회귀 방지 |
| `ccd629dd7` | docs: 트래커에 결함 #19-b·#20·#21 등재 |

그 이전 세션 커밋(#13~#18 수정 등)도 `dev` 에 누적되어 있다. 전부 push 완료.
