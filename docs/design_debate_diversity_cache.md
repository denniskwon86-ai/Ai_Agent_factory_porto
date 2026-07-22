# 설계 아이디어 — 토론(debate) 다양성 × Exact Hash Cache 상호작용

> 상태: **아이디어 정리(구현 대기)** | 작성: 2026-07-22
> 배경: 외부 세션이 도입한 v1 Exact Hash Cache(`f9e3dcfc5`, `core/cache_manager.py` +
> `core/llm_gateway.py` 훅)와, 다중 에이전트 토론 루프(`nodes/utils/debate.py`)의 상호작용을
> 검토한 결과. 캐시 자체는 M1·완주 대응과 호환(→ `session_log_2026-07-22.md`)이나, **생성·재작업
> 경로에서 다양성을 죽이는 특정 시나리오**가 있어 대응안을 정리한다.

---

## 1. 캐시 동작 요약 (사실관계)

- 캐시 키 = `SHA-256(system_content + final_prompt + output_mode)` (`llm_gateway.py:477`).
- `final_prompt` 는 `core_context(=ContextEngine, M1 포함) + skill_prompt + strict_json_rule` 로 조립.
- 이미 들어간 방어(그쪽 세션): 빈 코드 결과(`{"files":[]}`)·오류 센티넬(`is_llm_error_text`)은 캐시 금지
  (`llm_gateway.py:500-503, 549-552`). → "실패 산출물 영구 고정"은 이미 차단됨.

## 2. debate 의 3개 LLM 경로 (`nodes/utils/debate.py`)

| 경로 | 호출 | 프롬프트 구성 | 다양성 필요? |
|---|---|---|---|
| 초안 draft | `run_debate` L127 | `author_prompt`(skill+지시) | △ (재추첨 시) |
| 비평 critique | `run_debate` L143 | `critic_skill + persona + rubric + {draft}` | ✕ (결정론 바람직) |
| 개정 revise | `run_debate` L176 / `run_single_revision` L184 | `author_prompt + {prev} + {feedback}` | ✅ (개선=변화) |

## 3. 문제 시나리오 (코드 근거)

### 🔴 P1. 재작업 while 루프의 결정론적 무한 동일 (가장 실질적)
`run_supervised_stage` L231-239:
```
while result.verdict != PASS and used < MAX_STAGE_REWORKS:
    feedback = _build_feedback(result)              # result 고정 시 feedback 고정
    artifact = run_single_revision(prev, feedback)  # prompt 고정 → 캐시 HIT → 동일 산출물
    result = score_stage(...)                        # 산출물 동일 → score 동일 → feedback 동일 …
```
- `run_single_revision` 의 프롬프트는 `skill + {prev_text} + {feedback}` 뿐이다. 한 번 캐시에 올라가면
  **재작업을 아무리 돌려도 완전히 같은 산출물**이 나오고, 점수·피드백도 동일해져 **개선 없이 재작업
  예산(`MAX_STAGE_REWORKS`)만 소진**한 뒤 HOTL/실패로 빠진다. 캐시 도입 전에는 LLM 비결정성 덕에
  재시도가 다른 결과를 낼 여지가 있었으나, 캐시가 그 여지를 0으로 만든다.
- ⚠️ 주의: `score_stage`(judge)도 같은 산출물이면 캐시 히트로 동일 판정 — 이건 오히려 정상(결정론).
  문제는 **생성(revise) 쪽이 변하지 못하는 것**이다.

### 🟡 P2. 초안 재추첨 다양성 상실
동일 프로젝트 상태에서 스프린트를 재실행하면 `core_context` 가 동일 → draft 프롬프트 동일 →
캐시 히트로 **매번 같은 초안**. 쿼터 절감엔 이득이나, "다시 뽑아 더 나은 안을 기대"하는 용법은 막힌다.

### 🟢 P3. 비평 다양성 — 문제 아님
같은 초안에 같은 결함을 지적하는 것은 바람직(결정론). critique 는 캐시 유지가 옳다.

## 4. 설계 원칙

> **판정·비평(결정론이 바람직) = 캐시 유지. 생성·재작업(변화=개선) = 캐시 우회 또는 회차 주입.**

## 5. 대응안 (구체)

### 방안 A — `aexecute(cacheable: bool = True)` 경로별 플래그
- `llm_gateway.aexecute` 에 `cacheable` 인자 추가. `False` 면 캐시 조회·저장 모두 건너뜀.
- debate 호출부에서 지정: critique/judge = `True`(기본), **revise·single_revision = 조건부 `False`**.
- 장점: 명시적·안전. 단점: 재작업이 여전히 LLM 비결정성에만 의존(seed 고정 모델이면 여전히 유사 가능).

### 방안 B — 재작업 회차 nonce 를 프롬프트에 주입 (권장 기본)
- `run_single_revision`/`run_debate` revise 에 **재작업 회차 번호 + "이전 시도와 다른 접근을 취하라"**
  지시를 프롬프트에 명시적으로 추가:
  ```
  [재작업 회차: {n}/{max}] 직전 개정과 동일한 결과는 금지한다. 다른 구조·표현으로 개선하라.
  ```
- 효과: (1) 프롬프트가 회차마다 달라져 **캐시 자연 우회**, (2) LLM 에 실제 다양성 유도 신호.
- `used`(재작업 카운트)는 이미 `run_supervised_stage` 에 있으므로 `extra_instruction` 으로 전달만 하면 됨.

### 방안 C — (권장 조합) B 를 기본 + A 를 안전장치
- 생성·재작업 경로: **B(회차 주입)** 로 다양성+캐시우회를 동시에.
- 명시적으로 캐시가 무의미한 초안 재추첨 용법이 필요하면 그 진입점에서 **A(cacheable=False)**.
- 비평·판정·결정론 검사: 캐시 그대로 유지(쿼터 절감 최대화).

### 기각: 캐시 키에 attempt 자동 포함
- `gateway` 는 stage/attempt 문맥을 모른다. 호출부(debate)가 프롬프트에 넣는 B 가 결합도·명료성 모두 우수.

## 6. 검증 방법 (구현 시)
1. 단위: 같은 (prev, feedback)에 회차 1·2·3 으로 `run_single_revision` 호출 → 프롬프트 해시가 서로 달라야.
2. 통합: judge/critique 는 동일 입력 시 캐시 히트 유지(텔레메트리 `cache_hit`), revise 는 회차별 미스.
3. 회귀: `MAX_STAGE_REWORKS` 루프가 "동일 산출물 고정"에 빠지지 않는지(최소 1회는 변화) 확인.

## 7. v1.5 시맨틱 캐시(세션로그 §4)와의 관계
생성 전용 노드에 시맨틱 캐시(≥0.95)를 넣자는 논의가 열려 있으나, **생성 경로는 본 문서의 다양성
원칙상 시맨틱 캐시도 신중**해야 한다(유사 프롬프트를 같은 결과로 눌러 다양성을 더 강하게 죽임).
판정·검색 등 결정론 경로에 한정 적용을 권한다.

---

## 8. 홀딩 사유 / 다음 결정
사용자 판단으로 **추가 고민 후 착수**(2026-07-22). 착수 시 방안 C 기준으로 debate.py 만 수정하면 되고
캐시 모듈(외부 세션 소유)은 건드리지 않아도 된다(A 플래그 도입 시에만 gateway 시그니처 1줄 확장).
