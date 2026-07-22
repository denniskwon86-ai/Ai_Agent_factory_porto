# 세션 작업 기록 — 2026-07-22

> 이 세션의 목표: **반복적인 A-1 시나리오 실행 시 발생하는 LLM 쿼터 낭비를 방어하기 위해 v1 정확 일치 캐시(Exact Hash Cache) 시스템을 도입한다.**
> M1 기준정보(Master Data) 저장소 및 RAG 시스템 구축은 현재 다른 환경에서 병렬 진행하기로 하여 일시 홀딩됨.

---

## 1. 핵심 설계 의사결정 (Architecture Decision)

초기에는 시맨틱 기반 캐싱(유사도 검색)을 고려했으나, 설계 리뷰 과정에서 **게이트 노드(judge/QA/Critic)에 시맨틱 캐시를 적용할 경우 치명적인 리스크**가 발견되어 방향을 선회함.

- **위험**: 수정된 문서(v2)가 이전 문서(v1)와 프롬프트 유사도가 높다는 이유로 과거의 판정(FAIL)을 그대로 가져오게 되면, 재작업 루프(Feedback Loop)가 파괴되고 게이트가 영구 오작동함.
- **해결책 (v1 Exact Match Cache)**: 
  - `system_content + final_prompt + output_mode`를 결합하여 `SHA-256` 해싱을 수행.
  - 정확히 내용이 일치할 때만 Cache Hit으로 인정함으로써 오판 확률을 0%로 차단.
  - 외부 인프라(Redis) 없이 자체 SQLite 기반으로 동작하도록 가볍게 구축.

---

## 2. 주요 변경 사항 및 구현체

| 변경 파일 | 분류 | 내용 |
|---|---|---|
| `core/cache_manager.py` (신규) | 인프라 | `sqlite3` 및 `asyncio.to_thread`를 사용하여 `data/llm_cache.db` 파일에 해시-응답 키밸류 저장 로직(CRUD) 구현 |
| `core/llm_gateway.py` | 훅 주입 | `aexecute` 및 `aexecute_vision` 메서드의 프롬프트 조립 직후에 SHA-256 해시 생성 및 캐시 히트(Bypass) 로직 주입. 캐시 저장 로직 적용. |
| `core/llm_gateway.py` | 관측 | 캐시 히트 시 텔레메트리 `_log_llm_call`에 `attempts=["cache_hit"]` 기록 (운영 계기판에 "cache_hit" 모델로 자동 집계됨) |
| `tests/test_cache_manager.py` (신규) | 테스트 | 캐시 모듈에 대한 단일 해시 검증 테스트 추가 (통과 완료) |

---

## 3. 타 환경/모델을 위한 인수인계 사항 (Next Steps)

1. **DB 경로 유의**: 캐시 DB는 `data/llm_cache.db` 에 자동 생성되며, `data/` 디렉토리는 `.gitignore` 정책상 형상 관리에 포함되지 않는 런타임 저장소입니다.
2. **Telemetry 자동 집계**: `cache_hit` 레코드는 기존 `api/routes/telemetry_control.py`에서 `used="cache_hit"`으로 자동 인식되므로, 프론트엔드의 파이 차트나 통계 패널에서도 별도 수정 없이 쿼터 방어율을 확인할 수 있습니다.
3. **M1 기능 홀딩 상태**: M1 기준정보(Master Data) 저장소 작업은 설계(docs/design_master_data_m1.md)까지만 진행 및 논의되었으며, 현재 본 캐시 시스템 도입을 위해 구현이 멈춘 상태입니다. 이어서 작업할 모델은 M1 설계를 참고하여 `data/master/master.db` 관련 구현을 진행하면 됩니다.
4. **v1.5 고도화**: 추후 인프라가 확보되고 안전이 검증된 생성(Generation) 전용 노드에 한하여 Chromadb 기반의 높은 임계값(>=0.95) 시맨틱 매칭 캐시를 적용하는 논의가 열려 있습니다.

---

## 4. E2E 테스트 (A-1 시나리오) 실행 결과 및 후속 과제

Exact Hash Cache 도입 후 `run_e2e_scenario.py`를 통해 A-1 관문 시나리오를 다시 실행했습니다. 

- **캐시 동작 확인**: 이전 테스트에서 LLM 할당량 초과(429)로 멈췄던 **기획(PLANNING) 단계**를 성공적으로 돌파했습니다.
- **신규 결함 발견 (UI_DESIGN 무한루프)**: 하지만 `UI_DESIGN` 단계에 진입한 후, 승인 게이트(HOTL)에서 **무한 반복 승인(resume) 루프**에 빠져 파이프라인이 다음 단계(ARCHITECTURE)로 넘어가지 못하는 현상이 발생했습니다. (총 18분 대기 후 강제 종료)
- **후속 작업 지시**:
  - 내일 세션에서 가장 먼저 이 **`UI_DESIGN` 무한왕복 잠재결함**을 추적하고 해결해야 합니다.
  - 이전에 `progress_tracker.md`에 FIXED 처리되었던 결함(#1 연관 - `reviewer_decision` 미초기화)이 재발한 것인지, 혹은 자동화 스크립트의 루프 탈출 조건에 문제가 있는 것인지 점검이 필요합니다.
