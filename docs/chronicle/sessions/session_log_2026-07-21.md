# 세션 작업 기록 — 2026-07-21

> 이 세션의 목표: **무료 티어 한도 제약 하에서 스프린트가 "완주"하도록** LLM 라우팅·품질 게이트를
> 사전 분석·개선하고, 그 과정을 관측·검증 가능하게 만든다. (테스트는 별도 환경에서 진행)
> 브랜치 `dev`, 최종 커밋 `5f89ec974`. 전 pytest 스위트 **211건 통과**.

---

## 1. 핵심 문제 정의 (이 세션의 출발점)

A-1 관문 스프린트가 **무료 LLM 한도 소진으로 planning(TECH_SPEC) 단계에서 중단**되거나, 죽은
모델을 반복 재시도하며 **시간이 과도하게 소요**되어 끝까지 돌지 못했다. 원인을 코드로 사전 분석한 결과:

1. **티어 무기억 재시도**: `is_heavy`가 매 호출 결정 → Pro 소진 후에도 다음 단계에서 또 Pro부터 재시도.
2. **per-model 한도 미인지**: pro/flash '묶음'만 관리하고 묶음 내 개별 모델 한도를 안 봄 → "gemini 죽음,
   groq 생존" 상태에서 매 호출 죽은 gemini를 다시 두드리며 대기.
3. **Pro 콜 과다**: planning 대용량 드래프트(RFP·PRD·UI·아키텍처·기술명세) 5개 + 토론 리비전·재작업 +
   QA/Supervisor 판정이 모두 Pro → 무료 Pro 한도(분당 2~5회)를 완주 전 소진.
4. **체인 부풀림**: 동적 탐색이 tts/image/lyria 등 비-텍스트 Gemini 변종까지 폴백에 담아 죽은 체인 walk 증가.

> **원 설계 정체성 재확인**: 이 시스템은 "도메인 지식 기반 업무 산출물·시뮬레이션 팩토리"이며,
> 차별화 자산은 그라운딩(지식팩/기준정보)·시뮬레이션·요구 추적성·HOTL 거버넌스. **어떤 LLM으로
> 바꿔도 품질 게이트가 산출물 하한을 보장**하는 게 핵심 기조 — 이번 작업은 그 기조를 무료 한도
> 현실에서 실제로 작동하게 만드는 것.

---

## 2. 이번 세션 커밋 요약 (dev)

| 커밋 | 분류 | 내용 |
|---|---|---|
| `4a520f846` | 고도화(LLM 0콜) | **G1 추적성 엔진 완성** — REQ↔FR 링크 추출, PRD FR 커버리지 결정론 게이트(QA), 수용검수 근거 표 주입 |
| `974b9eee2` | 고도화(LLM 0콜) | **FinOps 리스크 분석기** — 변경분 정적 위험도(LOW/HIGH)로 리뷰 자동승인/정밀검토 |
| `8fcea5a46` | 고도화(LLM 0콜) | **G1-4 리비전 영향 분석** — 추적성 역인덱스로 변경 파급(파일·태스크·연관 FR) 산출 API |
| `afecc9270` | 문서 | **M1 기준정보 저장소 설계 개정** — 복합 PK(리니지 보존)·별칭 오탐 방지·결정론 선정 등 검토 6건 반영 |
| `0ad0f80e6` | 완주 대응 | **JUDGE_FORCE_HEAVY 되돌림**(채점 Pro→Flash, 유한 Pro 예산 보존) + **WBS 태스크 크기 결정론 게이트** |
| `ee5eb15f4` | 관측 | **Phase4 운영 계기판** — LLM 호출 텔레메트리 뷰어(실사용 모델 분포 중심), `data/llm_call_log.jsonl` |
| `c99925186` | 완주 대응 | **LOW_QUOTA_MODE** — 문서형 드래프트(RFP/PRD/UI) Flash, 구조 설계만 Pro, 리비전/재작업 Flash |
| `5f89ec974` | 완주 대응(속도) | **레버B** — per-model 쿨다운·폴백 체인 정제·재시도 슬립 단축 |

(앞선 세션 커밋 `b7dc409f9` fail-loud·심판앵커링·텔레메트리, `e1a4ca5f2` 스테일 테스트 현행화도 이 흐름의 일부)

---

## 3. 완주를 위한 4대 조치 (상호작용)

무료 공통 API 키 = **단일 유한 일일 Pro 풀**이라는 제약 위에서:

1. **Pro 예산 보존** (`0ad0f80e6`): 채점(judge)을 Pro→Flash(QA/Supervisor 최종 관문만 Pro 유지).
   Pro 콜 하나하나가 유한 예산 차감이므로 "채점에 Pro 낭비 금지".
2. **Pro 볼륨 감축** (`c99925186` LOW_QUOTA_MODE): 스프린트당 대용량 Pro 콜 **~7-13 → ~4**
   (아키텍처·기술명세 드래프트 + QA·Supervisor 판정). 문서형은 그라운딩이 도메인 정확성을 받쳐 Flash로.
3. **대기 제거** (`5f89ec974` 레버B): per-model 쿨다운으로 죽은 모델을 체인에서 제외 → 재시도·타임아웃
   낭비 0. 티어 브레이커를 per-model `_all_cooled`로 일반화(일부만 죽으면 티어 내 생존 모델 사용).
4. **실측 관측** (`ee5eb15f4` 계기판): `used`(실제 모델)·`downgraded`(Pro→Flash 강등)·폴백률·단계별
   소요를 집계 → "이 산출물이 실제로 어느 모델로 만들어졌나 = 모델 불변성"을 데이터로 확인.

**되돌리기 안전장치**: LOW_QUOTA_MODE·JUDGE_FORCE_HEAVY·MODEL_COOLDOWN_SEC 등은 전부 `config.py`
플래그 → 완주 증거 확보 후 골든 벤치마크로 단계별 Pro 복귀를 판정하면 됨.

---

## 4. 관련 신규/변경 파일

- `config.py` — LOW_QUOTA_MODE, PRO_DRAFT_STAGES, JUDGE_FORCE_HEAVY(False), WBS_MAX_TASK_TOKENS,
  MAX_GEMINI_VARIANTS, MODEL_COOLDOWN_SEC, QUOTA_RETRY_SLEEP_SEC
- `core/llm_gateway.py` — per-model 쿨다운(`_model_cooldown`/`_compose_chain`/`_update_cooldowns`/
  `_all_cooled`), 체인 정제(`_is_text_gen_model`), 텔레메트리(`_log_llm_call` + requested_tier/downgraded)
- `core/risk_analyzer.py` (신규) — 변경분 정적 위험도
- `nodes/utils/traceability_manager.py` — G1 추출/커버리지/역인덱스/영향분석
- `nodes/utils/debate.py` — LOW_QUOTA_MODE 티어 배정(드래프트/리비전/재작업)
- `nodes/execution.py` — G1 커버리지·수용검수 근거·리스크 분석기 배선
- `criteria.py` — fr_coverage / wbs_task_sizes 결정론 게이트
- `api/routes/telemetry_control.py` (신규) — 계기판 API 3종
- `frontend/src/components/TelemetryPanel.tsx` (신규) + `App.tsx` 헤더 버튼
- `docs/design_master_data_m1.md` — M1 설계 개정
- `tests/` — test_traceability, test_risk_analyzer, test_traceability_impact, test_telemetry,
  test_wbs_size_gate, test_low_quota_mode, test_model_cooldown (LLM 0콜 단위 테스트)

---

## 5. 추가 조치 및 기능 고도화 (2026-07-21 후반 세션)

1. **쿼터 고갈 상태(SUSPENDED_QUOTA) 무한루프 및 HOTL 오탐지 핫픽스**
   - 백엔드의 `is_hotl_pending()`이 쿼터 고갈 상태를 HOTL 대기로 착각하여 발생하는 무한 대기를 수정.
   - `run_e2e_scenario.py` 스크립트가 쿼터 고갈 감지 시 즉각적으로 Abort(실패 종료)되도록 Fail-fast 대응 완료.
2. **텔레메트리 v2 (실측 토큰 수집)**
   - `core/llm_gateway.py` 내 `_ModelRecorder`를 통해 `usage_metadata` (입력/출력 토큰)를 추출.
   - `api/routes/telemetry_control.py`에서 누적 토큰을 집계하여 `/summary` 응답에 포함시킴. 비용 최적화 분석 기반 마련.
3. **실행 단계(Execution) 선택적 컨텍스트 다이어트**
   - `core/context_engine.py`에서 실행 단계 진입 시 아키텍처 요약본을 강제로 절반으로 압축(`_clip`).
   - WBS 태스크의 `required_agents`를 분석하여 프론트엔드 작업 시 백엔드 명세를, 백엔드 작업 시 프론트엔드 명세를 과감하게 클리핑하는 휴리스틱 적용. 컨텍스트 낭비 차단.

---

## 6. 다음 할 일 (Next Steps)

1. **A-1 관문 재실행 (별도 환경)** — API 일일 쿼터 회복 후, 컨텍스트 다이어트와 핫픽스가 적용된 `dev` 브랜치로 완주 가능 여부 실측.
2. **M1 기준정보(Master Data) 저장소 및 G2 RAG 구현** — `docs/design_master_data_m1.md`에 명시된 DB DDL, API, UI 연동, 그리고 텍스트 내 별칭 감지를 통한 결정론적 컨텍스트 주입 1순위 구현. (환각 차단의 핵심)
3. **골든 벤치마크 테스트 파이프라인 구축** — 품질 회귀를 방지하기 위해 LLM Judge와 사람의 교차 채점 체계 도입.

## 7. 미해결/주의

- 루트에 방치된 일부 임시 스크립트(test_cb.py, test_gemini.py 등)는 아직 존재함. 사용 종료 시 정리 권장.
- 폴더가 클라우드 동기화 중일 가능성이 있으므로 항상 작업 직후 Commit/Push를 습관화해야 함.
