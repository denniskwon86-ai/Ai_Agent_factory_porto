# 📜 작업 지시서: 품질 게이트 Fail-Loud 전환 + 심판 앵커링 + 모델 텔레메트리

> **이 문서는 AI 코딩 에이전트에게 내리는 실행 지시서입니다. 위에서부터 순서대로, 적힌 그대로 수행하세요.**
> - 전제 베이스라인: `dev` 브랜치, 커밋 `19357cc94` 이후.
> - 예상 변경 파일: `config.py`, `core/llm_gateway.py`, `nodes/utils/scoring.py`, `nodes/vision_qa.py`, `.gitignore` — **이 5개 외에는 어떤 파일도 수정 금지.**

---

## 0. 배경 (왜 이 작업을 하는가 — 반드시 읽고 시작)

이 시스템의 설계 기조는 **"어떤 LLM 모델을 쓰든 품질 게이트(비평/채점/QA)가 산출물 하한선을 보장한다"** 이다.
그런데 현재 코드에는 이 기조를 무너뜨리는 구멍 4개가 있다:

1. **심판(judge) 오류의 오귀속**: 채점 LLM 호출이 실패하면 에러 문자열이 채점 대상처럼 파싱되어
   전 항목 0점 → 멀쩡한 산출물이 REWORK 판정을 받고 재작업 루프가 쿼터만 태운다.
   (실패의 원인은 산출물이 아니라 인프라인데, 산출물 탓으로 기록됨)
2. **VisionQA 게이트 붕괴**: `gateway.aexecute()`를 `output_mode` 기본값("code")으로 호출해
   `{"decision": ...}` JSON을 받을 수 없는 구조 → **판정이 항상 PASS**. 또한 LLM 인프라 오류도
   조용히 PASS 처리(fail-open).
3. **심판이 고정되지 않음**: 생성 모델이 폴백으로 약해지면 채점 모델도 함께 약해져
   "약한 모델이 만든 것을 약한 심판이 후하게 통과"시키는 동반 표류가 가능.
4. **어떤 물리 모델이 각 호출을 처리했는지 기록이 없음**: "모델을 바꿔도 품질이 유지된다"를
   나중에 데이터로 증명할 수 없다.

이번 작업은 이 4개 구멍만 막는다. **기능 추가·리팩터링·성능 개선은 범위 밖이다.**

### 이미 구현되어 있는 것 (❌ 절대 다시 만들지 말 것 — 중복 구현 금지)
| 이미 있는 방어 | 위치 |
|---|---|
| 쿼터 소진 시 `QuotaExhaustedException` → `SUSPENDED_QUOTA` + `QUOTA_EXHAUSTED` 방송 | `core/llm_gateway.py`(raise), `core/async_orchestrator.py`(2곳 catch) |
| 문서 단계(RFP/PRD/UI/ARCH/TECH_SPEC)의 에러 sentinel 저장 차단 | `nodes/utils/debate.py` `_is_llm_error` + `run_supervised_stage` |
| 코드 산출물 빈 값 방어(재작업 루프 + 3회 후 HOTL) | `nodes/execution.py` `run_code_builder` 무결성 가드 |
| 일반 예외 → `SPRINT_FAILED` 방송 | `core/async_orchestrator.py` |

---

## 1. 절대 준수 규칙 (위반 시 작업 전체 무효)

1. **수정 허용 파일은 5개뿐**: `config.py`, `core/llm_gateway.py`, `nodes/utils/scoring.py`,
   `nodes/vision_qa.py`, `.gitignore`. 그 외(특히 `nodes/utils/debate.py`,
   `core/async_orchestrator.py`, `nodes/execution.py`, `state_models.py`, 프론트엔드, `.env`)는
   **읽기만 허용, 수정 금지**.
2. `state_models.py`의 `ProjectState`는 `extra='forbid'`다. **새 상태 필드를 추가하지 마라**
   (이번 작업은 상태 스키마를 건드리지 않고 완성된다).
3. 각 작업의 "찾을 코드(BEFORE)"는 파일에서 **정확히 일치하는 문자열**로 찾아라.
   **일치하는 코드가 없으면 그 작업을 중단하고 "앵커 불일치"라고 보고하라.**
   비슷해 보이는 다른 코드를 임의로 고치지 마라.
4. 기존 코드 스타일 유지: 한국어 주석, 이모지 프리픽스 로그, 4칸 들여쓰기.
   무관한 줄의 포맷팅/정렬/임포트 순서를 바꾸지 마라.
5. 패키지 설치/업그레이드 금지. 이번 작업은 기존 의존성만으로 완성된다.
6. 커밋 전 반드시 6장(검증)의 모든 항목을 통과시켜라. 하나라도 실패하면 커밋 금지.

---

## 2. 작업 1 — `config.py`: 심판 앵커링 스위치 추가

### 2-1. 찾을 코드 (BEFORE)
```python
# Supervisor 게이트 / 무한루프 안전장치
MAX_STAGE_REWORKS = 1            # 단계별 in-node 재작업 한도(할당량 절감). 초과 시 인간 개입(HOTL)
```

### 2-2. 바꿀 코드 (AFTER) — BEFORE 를 아래로 교체
```python
# [심판 앵커링] llm_judge 채점을 항상 Pro(가용 최강) 체인으로 고정할지 여부.
# 생성 모델이 폴백으로 약해져도 채점 '잣대'까지 함께 약해지는 동반 표류(약한 모델이 만든 산출물을
# 약한 심판이 후하게 통과)를 차단한다 — 모델 불가지 품질 보장의 전제 조건.
# 단점: 단계당 judge 1콜이 Pro 쿼터를 소모한다. 쿼터가 극도로 부족한 날은 False 로 완화 가능.
JUDGE_FORCE_HEAVY = True

# Supervisor 게이트 / 무한루프 안전장치
MAX_STAGE_REWORKS = 1            # 단계별 in-node 재작업 한도(할당량 절감). 초과 시 인간 개입(HOTL)
```
(= 기존 두 줄은 그대로 두고, 그 **위에** `JUDGE_FORCE_HEAVY` 블록을 삽입하는 것이다)

---

## 3. 작업 2 — `core/llm_gateway.py`: 공용 sentinel 감지 함수 + 모델 텔레메트리

### 3-1. 임포트 추가
파일 상단의 아래 코드(BEFORE)를 찾아라:
```python
import os
import json
import re
import asyncio
from typing import Any
```
아래(AFTER)로 교체하라:
```python
import os
import json
import re
import time
import asyncio
from datetime import datetime
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
```

### 3-2. 공용 sentinel 감지 함수 + 텔레메트리 헬퍼 추가
아래 코드(BEFORE, 이미 존재)를 찾아라:
```python
def _is_truncated(response: Any) -> bool:
```
그 **바로 위에** 아래 블록을 삽입하라(기존 `_is_truncated`는 그대로 둠):
```python
def is_llm_error_text(text) -> bool:
    """게이트웨이가 최종 실패 시 반환하는 에러 sentinel 문자열 감지(모든 소비자 공용).
    이 문자열이 산출물/채점 입력으로 흘러들면 '조용한 오판'이 생기므로, 소비자는
    반드시 이 함수로 걸러 fail-loud(예외 표면화) 처리해야 한다.
    (nodes/utils/debate.py 의 _is_llm_error 와 동일 규약 — 그쪽은 수정하지 말 것)"""
    return isinstance(text, str) and ("LLM API LIMIT ERROR" in text or "LLM UNKNOWN ERROR" in text)


class _ModelRecorder(BaseCallbackHandler):
    """[모델 텔레메트리] 폴백 체인에서 '실제로 어떤 물리 모델이 시도/성공했는지'를 포착한다.
    with_fallbacks 는 성공 모델을 노출하지 않으므로, 콜백으로 각 시도의 모델명을 수집한다.
    성공 시 attempts[-1] = 실제 응답을 만든 모델."""
    def __init__(self):
        self.attempts = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        try:
            kw = (serialized or {}).get("kwargs", {}) or {}
            name = kw.get("model") or kw.get("model_name") or ((serialized or {}).get("id") or ["?"])[-1]
            self.attempts.append(str(name))
        except Exception:
            self.attempts.append("?")


_LLM_CALL_LOG_PATH = os.path.join("data", "llm_call_log.jsonl")


def _log_llm_call(state_obj, tier: str, output_mode: str, retry_count: int, attempts: list, ok: bool, duration_s: float):
    """LLM 호출 1건당 텔레메트리 JSONL 1줄 기록 — '모델을 바꿔도 품질 유지' 주장을
    사후에 데이터(단계별 사용 모델 x stage_scores)로 증명하기 위한 기초 계측.
    기록 실패가 파이프라인을 막으면 안 되므로 모든 예외를 삼킨다(부가 기능)."""
    try:
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "project": getattr(state_obj, "project_name", "") or "",
            "stage": getattr(state_obj, "current_stage", "") or "",
            "tier": tier,
            "output_mode": output_mode,
            "retry_count": retry_count,
            "attempts": attempts,
            "used": (attempts[-1] if attempts else ""),
            "ok": ok,
            "duration_s": round(duration_s, 2),
        }
        os.makedirs("data", exist_ok=True)
        with open(_LLM_CALL_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if ok:
            print(f"[Telemetry] stage={rec['stage'] or '-'} tier={tier} used={rec['used']} attempts={len(attempts)} {rec['duration_s']}s")
    except Exception:
        pass


```

### 3-3. `aexecute` 안에서 콜백 연결 + 로그 기록
`aexecute` 메서드 안의 아래 코드(BEFORE)를 찾아라:
```python
        try:
            # 1. 일차적으로 LangChain의 with_fallbacks 체인 호출
            response = await llm.ainvoke(messages)
```
아래(AFTER)로 교체하라:
```python
        _rec = _ModelRecorder()
        _t0 = time.time()
        try:
            # 1. 일차적으로 LangChain의 with_fallbacks 체인 호출 (+텔레메트리 콜백)
            response = await llm.ainvoke(messages, config={"callbacks": [_rec]})
            _log_llm_call(state_obj, logical_model_name, output_mode, retry_count, _rec.attempts, True, time.time() - _t0)
```
이어서, 같은 메서드의 아래 코드(BEFORE)를 찾아라:
```python
        except Exception as e:
            error_str = str(e)
```
아래(AFTER)로 교체하라:
```python
        except Exception as e:
            _log_llm_call(state_obj, logical_model_name, output_mode, retry_count, _rec.attempts, False, time.time() - _t0)
            error_str = str(e)
```
> ⚠️ 주의: 크로스 티어/재시도 재귀 호출은 각 호출 레벨이 자기 시도를 각각 1줄씩 기록한다.
> 이는 의도된 동작이다(레벨별 시도 이력이 남음). 재귀 쪽 코드는 건드리지 마라.
> ⚠️ `aexecute_vision` 등 다른 메서드는 이번 작업 범위 밖이다 — 수정 금지.

---

## 4. 작업 3 — `nodes/utils/scoring.py`: 심판 오류 fail-loud + 앵커링 적용

### 4-1. 임포트 및 예외 클래스 추가
파일 상단의 아래 코드(BEFORE)를 찾아라:
```python
import os
import re
import json
from criteria import STAGE_RUBRICS, DETERMINISTIC_CHECKS
```
아래(AFTER)로 교체하라:
```python
import os
import re
import json
import config
from criteria import STAGE_RUBRICS, DETERMINISTIC_CHECKS


class JudgeUnavailableError(Exception):
    """심판(judge) LLM 자체가 응답 불능인 상태 — '산출물 결함'과 반드시 구분해야 한다.
    이 예외는 노드 → LangGraph → 오케스트레이터의 일반 예외 핸들러까지 전파되어
    SPRINT_FAILED 로 방송된다(fail-loud). 0점 처리로 삼키면 멀쩡한 산출물이
    REWORK 루프를 돌며 쿼터만 태우는 오귀속이 생긴다."""
    pass
```

### 4-2. judge 호출부 교체
`score_stage` 함수 안의 아래 코드(BEFORE)를 찾아라:
```python
        # QA·Supervisor 같은 고위험 수용검수는 Pro judge로 엄격 채점(rubric의 judge_heavy), 그 외는 Flash 경량.
        judge_heavy = bool(rubric.get("judge_heavy", False))
        raw = await gateway.aexecute(state, prompt, is_heavy=judge_heavy, output_mode="json", light=True)
        jdata = _parse_json(raw)
        scores = jdata.get("scores", {}) or {}
        rationale = str(jdata.get("rationale", "") or "")
```
아래(AFTER)로 교체하라:
```python
        # [심판 앵커링] 채점 잣대는 생성 모델과 함께 흔들리면 안 된다 — JUDGE_FORCE_HEAVY 가 켜져
        # 있으면 모든 단계의 judge 를 Pro(가용 최강) 체인으로 고정한다. (끄면 기존 동작:
        # QA/Supervisor 등 rubric 의 judge_heavy 단계만 Pro)
        judge_heavy = bool(rubric.get("judge_heavy", False)) or bool(getattr(config, "JUDGE_FORCE_HEAVY", False))
        raw = await gateway.aexecute(state, prompt, is_heavy=judge_heavy, output_mode="json", light=True)

        # [fail-loud] 심판 호출 실패(인프라 오류)는 산출물 결함이 아니다 — 예외로 표면화한다.
        from core.llm_gateway import is_llm_error_text
        if is_llm_error_text(raw):
            raise JudgeUnavailableError(f"[{stage_key}] 심판 LLM 호출 실패(인프라 오류) — 채점 불가: {str(raw)[:200]}")

        jdata = _parse_json(raw) or {}
        scores = jdata.get("scores", {}) or {}
        rationale = str(jdata.get("rationale", "") or "")

        # 비정형 응답 방어: scores 가 비면 Pro 승격 1회 재시도, 그래도 비면 판정 불가(fail-loud).
        # (조용히 전 항목 0점 처리하면 '심판 오류'가 '산출물 불합격'으로 둔갑한다)
        if not scores:
            print(f"⚠️ [Judge] {stage_key} 채점 JSON 비정형 — Pro 승격 1회 재시도")
            raw = await gateway.aexecute(state, prompt, is_heavy=True, output_mode="json", light=True)
            if is_llm_error_text(raw):
                raise JudgeUnavailableError(f"[{stage_key}] 심판 재시도 실패(인프라 오류): {str(raw)[:200]}")
            jdata = _parse_json(raw) or {}
            scores = jdata.get("scores", {}) or {}
            rationale = str(jdata.get("rationale", "") or "")
            if not scores:
                raise JudgeUnavailableError(f"[{stage_key}] 심판 채점 JSON 2회 연속 파싱 실패 — 판정 불가.")
```

---

## 5. 작업 4 — `nodes/vision_qa.py`: 판정 붕괴 수정 + fail-open 제거

### 5-1. 임포트 확장
아래 코드(BEFORE)를 찾아라:
```python
from core.llm_gateway import gateway
```
아래(AFTER)로 교체하라:
```python
from core.llm_gateway import gateway, is_llm_error_text
```

### 5-2. 판정 호출부 교체
아래 코드(BEFORE)를 찾아라:
```python
    print("⏳ [Vision QA] 정적 HTML 구조 분석 요청 중...")
    try:
        # aexecute_vision 대신 텍스트 기반 aexecute 사용
        output_str = await gateway.aexecute(state_obj, prompt)
        data = json.loads(output_str)
        decision = data.get("decision", "PASS")
        feedback = data.get("feedback", "")
    except Exception as e:
        print(f"⚠️ [Vision QA] 정적 분석 LLM 연동 실패: {e}")
        decision = "PASS"
        feedback = str(e)
```
아래(AFTER)로 교체하라:
```python
    print("⏳ [Vision QA] 정적 HTML 구조 분석 요청 중...")
    # ⚠️ [판정 붕괴 수정] output_mode 기본값은 "code"(파일 스키마 강제 구조화 출력)라서
    #    {"decision","feedback"} JSON 을 절대 받을 수 없다 → 판정이 항상 PASS 로 붕괴하던 결함.
    #    반드시 "json" 모드로 호출한다. (UI 구조 자문 판정이므로 Flash + 경량 컨텍스트면 충분)
    output_str = await gateway.aexecute(state_obj, prompt, is_heavy=False, output_mode="json", light=True)

    # [fail-loud] 게이트웨이 최종 실패 sentinel 은 '판정 불가'다 — 조용한 PASS 로 삼키지 않고
    # 예외로 표면화한다(오케스트레이터가 SPRINT_FAILED 방송 → UI 에 실패 노출 → 사람이 재시도 결정).
    if is_llm_error_text(output_str):
        raise RuntimeError(f"[Vision QA] 판정 LLM 호출 실패(인프라 오류) — 검증 불가로 중단: {str(output_str)[:200]}")

    try:
        data = json.loads(output_str)
        decision = data.get("decision", "PASS")
        feedback = data.get("feedback", "")
    except Exception as e:
        # 모델이 '응답은 했으나' 형식이 비정형인 경우에 한해 보수적 PASS 유지(자문 게이트 성격).
        # 인프라 실패(위 sentinel)와 달리, 이 경로는 게이트웨이가 정상 응답을 준 상태다.
        print(f"⚠️ [Vision QA] 판정 JSON 파싱 실패(비정형 응답) — 보수적 PASS 처리: {e}")
        decision = "PASS"
        feedback = str(e)
```

---

## 6. 작업 5 — `.gitignore`: 텔레메트리 로그 제외

아래 코드(BEFORE)를 찾아라:
```python
# 지식 허브 런타임 데이터 (벡터 인덱스/등록 자료 원본)
data/chroma_db/
data/knowledge_packs/
```
아래(AFTER)로 교체하라:
```python
# 지식 허브 런타임 데이터 (벡터 인덱스/등록 자료 원본)
data/chroma_db/
data/knowledge_packs/

# LLM 호출 텔레메트리(런타임 계측 데이터 — 커밋 금지)
data/llm_call_log.jsonl
```

---

## 7. 검증 (전부 통과해야 커밋 가능 — 순서대로)

작업 디렉토리: `C:\AI Workspace\Ai_Agent_factory_porto-dev`, 파이썬: `.venv\Scripts\python.exe`

### 7-1. 임포트 무결성
```powershell
.venv\Scripts\python.exe -c "import main; print('IMPORT OK')"
```
기대: `IMPORT OK` (예외 없음)

### 7-2. pytest 전체 (베이스라인 155건)
```powershell
.venv\Scripts\python.exe -m pytest -q
```
기대: **155 passed, 실패 0**. 실패가 있으면 원인 파악 전 커밋 금지.

### 7-3. sentinel 감지 단위 확인
```powershell
.venv\Scripts\python.exe -c "from core.llm_gateway import is_llm_error_text as f; assert f('{\"files\": [], \"error\": \"LLM UNKNOWN ERROR: x\"}'); assert f('LLM API LIMIT ERROR'); assert not f('PASS'); assert not f(None); print('SENTINEL OK')"
```
기대: `SENTINEL OK`

### 7-4. 심판 fail-loud 시뮬레이션 (LLM 무호출·모킹)
먼저 llm_judge 항목이 있는 단계를 확인:
```powershell
.venv\Scripts\python.exe -c "from criteria import STAGE_RUBRICS; [print(k, sum(1 for c in v.get('checks',[]) if c.get('type')!='deterministic')) for k,v in STAGE_RUBRICS.items()]"
```
출력에서 **두 번째 숫자가 1 이상인 단계 키 하나**(예: `PLANNING`)를 골라 아래 `STAGE` 에 넣고 실행:
```powershell
.venv\Scripts\python.exe -c "
import asyncio
from unittest.mock import patch, AsyncMock
from nodes.utils import scoring
from state_models import ProjectState

STAGE = 'PLANNING'  # <- 위에서 고른 단계 키
async def main():
    st = ProjectState()
    sentinel = '{\"files\": [], \"error\": \"LLM UNKNOWN ERROR: simulated\"}'
    with patch('core.llm_gateway._LazyGateway.aexecute', new=AsyncMock(return_value=sentinel)):
        try:
            await scoring.score_stage(st, STAGE)
            print('FAIL: JudgeUnavailableError 가 발생하지 않음')
        except scoring.JudgeUnavailableError as e:
            print('JUDGE FAIL-LOUD OK:', str(e)[:80])
asyncio.run(main())
"
```
기대: `JUDGE FAIL-LOUD OK: ...`

### 7-5. VisionQA fail-loud 시뮬레이션
```powershell
.venv\Scripts\python.exe -c "
import asyncio
from unittest.mock import patch, AsyncMock
from state_models import ProjectState
from nodes import vision_qa

async def main():
    st = ProjectState(ui_mockup_summary='<!DOCTYPE html><html><body><main>x</main></body></html>')
    sentinel = '{\"files\": [], \"error\": \"LLM UNKNOWN ERROR: simulated\"}'
    with patch('core.llm_gateway._LazyGateway.aexecute', new=AsyncMock(return_value=sentinel)):
        try:
            await vision_qa.run_vision_qa(st)
            print('FAIL: RuntimeError 가 발생하지 않음')
        except RuntimeError as e:
            print('VISIONQA FAIL-LOUD OK:', str(e)[:80])
asyncio.run(main())
"
```
기대: `VISIONQA FAIL-LOUD OK: ...`
(만약 `ProjectState(ui_mockup_summary=...)` 가 필드 오류를 내면 — 필드명이 다른 것이니
`state_models.py` 에서 `ui_mockup` 으로 시작하는 실제 필드명을 찾아 바꿔 실행하라. 파일 수정은 금지.)

### 7-6. VisionQA 정상 판정 확인 (json 모드 수정 검증)
```powershell
.venv\Scripts\python.exe -c "
import asyncio
from unittest.mock import patch, AsyncMock
from state_models import ProjectState
from nodes import vision_qa

async def main():
    st = ProjectState(ui_mockup_summary='<!DOCTYPE html><html><body><main>x</main></body></html>')
    ok = '{\"decision\": \"REWORK_DEV\", \"feedback\": \"레이아웃 결함\"}'
    with patch('core.llm_gateway._LazyGateway.aexecute', new=AsyncMock(return_value=ok)):
        r = await vision_qa.run_vision_qa(st)
        assert r.get('reviewer_decision') == 'REWORK_DEV', r
        print('VISIONQA REWORK ROUTING OK')
asyncio.run(main())
"
```
기대: `VISIONQA REWORK ROUTING OK` — 판정이 더 이상 무조건 PASS 가 아님을 증명.

### 7-7. 텔레메트리 기록 확인 (파일 생성)
```powershell
.venv\Scripts\python.exe -c "
from core.llm_gateway import _log_llm_call
from state_models import ProjectState
_log_llm_call(ProjectState(), 'pro_router', 'json', 0, ['gemini-2.5-pro'], True, 1.23)
import json, io
line = open('data/llm_call_log.jsonl', encoding='utf-8').readlines()[-1]
rec = json.loads(line)
assert rec['used'] == 'gemini-2.5-pro' and rec['ok'] is True
print('TELEMETRY OK:', rec)
"
```
기대: `TELEMETRY OK: {...}`

### 7-8. 변경 범위 확인
```powershell
git status --short
```
기대: 수정 파일이 `config.py`, `core/llm_gateway.py`, `nodes/utils/scoring.py`,
`nodes/vision_qa.py`, `.gitignore` **5개뿐**이어야 한다(+ 검증으로 생긴 `data/llm_call_log.jsonl` 은
untracked 로 보이면 안 됨 — gitignore 가 정상이면 목록에 안 나타난다).
다른 파일이 섞여 있으면 `git checkout -- <파일>` 로 되돌려라.

---

## 8. 커밋 및 푸시

7장 전 항목 통과 후에만:
```powershell
git add config.py core/llm_gateway.py nodes/utils/scoring.py nodes/vision_qa.py .gitignore
git commit -m "fix: 품질 게이트 fail-loud 전환 + 심판 앵커링 + LLM 모델 텔레메트리

- scoring: 심판 LLM 실패를 0점(REWORK 오귀속) 대신 JudgeUnavailableError 로 표면화,
  비정형 채점 JSON 은 Pro 승격 1회 재시도 후 판정 불가 처리
- scoring/config: JUDGE_FORCE_HEAVY 로 심판을 Pro 체인에 고정(잣대 동반 표류 차단)
- vision_qa: output_mode 미지정('code' 기본값)으로 판정이 항상 PASS 로 붕괴하던 결함 수정
  (json 모드 호출), 인프라 오류는 RuntimeError 로 fail-loud(비정형 응답만 보수적 PASS)
- llm_gateway: is_llm_error_text 공용 sentinel 감지 + 호출별 사용 모델 텔레메트리
  (data/llm_call_log.jsonl — '모델 교체에도 품질 유지' 검증용 계측 기반)"
git push origin dev
```

## 9. 막혔을 때 행동 규칙

- BEFORE 앵커가 파일에 없으면 → **그 작업만 중단**하고 "작업 N 앵커 불일치: <파일명>" 보고. 나머지 작업은 계속.
- 검증 7-2(pytest)에서 기존 테스트가 깨지면 → 내 변경이 원인인지 `git stash` 로 확인.
  내 변경이 원인이면 수정 재검토, 아니면(HEAD 에서도 실패) 그 사실을 보고에 명시.
- 이 지시서에 없는 개선점을 발견해도 **이번 커밋에 포함하지 마라**. 보고서에 "발견 사항"으로만 적어라.
- 작업 완료 보고에는 반드시 포함: ① 커밋 해시 ② 7장 각 항목의 실제 출력 ③ 앵커 불일치/특이사항 목록.
