# 일일 작업 로그: 2026년 7월 25일

> 이 세션은 **Claude Code 세션**이며, 같은 워킹 카피에서 **외부 세션(유료모델 E2E 테스트)이 병렬로 진행**됐다.
> 아래 A~D는 이 세션의 작업이고, 외부 세션 작업분은 §E에 관찰된 범위로만 기록한다.

## 📝 작업 개요

- **주요 목표**: (1) 계정·환경 변경 후 소스 전수 파악, (2) 이관 문서 현행화, (3) 런타임 데이터 재주입, (4) 조직·권한·전사 통합 기능 설계 확정.
- **기준 커밋**: 시작 `a18242fb7` → 종료 `bb15474fc`

---

## A. 환경 파악 및 검증

### A-1. 전수 확인 결과 (정상)

| 항목 | 결과 |
|---|---|
| pytest 전 스위트 | **258건 통과** |
| 백엔드 기동 | 정상 (`run.py` → :8080, 그래프 워밍업 OK) |
| 코드 ↔ 문서 정합 | `route_from_vision_qa` 자문 강등, RFP→PRD→UI→**Architect**→WBS 순서 모두 코드에 반영 확인 |
| 의존성 | langchain-core 1.4.9 · chromadb 1.5.9 · Python 3.14.3 |

### A-2. ⚠️ 이 환경의 운영 함정 — Bash 툴에서 네이티브 확장 로드 불가

Claude Code 의 **Bash 툴이 샌드박스 코드무결성 정책에 막혀 `.pyd`(네이티브 확장)를 못 읽는다.** `ormsgpack` DLL 로드 실패 → langgraph import 전멸로 **"테스트가 전부 깨진 것처럼" 보인다.** PowerShell 로 같은 명령을 돌리면 258건 정상 통과.
→ **이 환경에서 파이썬 실행은 반드시 PowerShell 툴로 할 것.**

### A-3. 다중 환경 동시 작업 사고

이 세션이 검증용으로 백엔드를 띄우자 **외부 클라이언트가 붙어 A-1 스프린트를 시작**했고(`POST /sprint/start`), 이후 그 백그라운드 프로세스가 종료되면서 **해당 스프린트가 같이 끊겼다.**
→ 8080 은 단일 포트다. 상대 환경의 가동 여부를 확인하고 기동/종료할 것. 대응은 `AI_HANDOFF.md` §3-1 에 신설.

---

## B. 문서 복구·현행화

### B-1. 진행 트래커(SSOT) 손상 복구 — `docs/test_plan/02_progress_tracker.md`

커밋 `c0b47a5f0`(07-22)에서 **인코딩 사고**로 유입된 손상을 복구했다.
- ENV-3 비고와 **S-1~S-7 행 7개가 소실**(S-8 행이 ENV-3 행에 병합)돼 있었다 → `ae3d245e8` 기준으로 복원. 시나리오 40행 정상, P1 "8/8" 표기와 정합.
- 결함로그 #6~#9 블록이 인수인계 메모 끝에 **중복 붙여넣기**되어 **#9 가 최신(MITIGATED)/구버전(OPEN) 두 벌로 공존**하고 있었다 → 중복 제거. 결함로그 #1~#12 각 1회.

### B-2. `AI_HANDOFF.md` 현행화 (07-18 → 07-25)

- **§0-1 신설** — PC 이동 시 런타임 데이터가 따라오지 않는다는 실측 사실 + 확인용 curl + 재주입 절차
- **§1-B 신설** — 07-19~07-24 커밋 62건 일자별 요약, 신규 코어 모듈/API/UI 패널 목록
- §2-1 재작성 — 07-24 방향 보정("무료 최적화 중단, 유료 모델로 완주") 반영
- §2-3 — G1·M1·M2·M3·리스크분석기 ✅ 표시
- §2-4 — pytest 부채 해소(258건), 신규 부채 추가
- **§3-1 신설** — 다중 환경 동시 작업 주의(포트 8080 단일, 워킹 카피 공유 시 `git add -A` 금지)

---

## C. 런타임 데이터 재주입 (실측)

**배경**: `data/master/`·`data/knowledge_packs/`·`data/chroma_db/` 는 전부 gitignore 런타임 데이터라 PC 를 옮기면 **마스터데이터 0건 · 지식팩 0건**이 된다. API 로 직접 확인했고 실제로 비어 있었다. 이 상태로 시나리오를 돌리면 **그라운딩 없는 완주**가 되어 실측이 무의미해진다.

### C-1. 마스터데이터 — `scripts/api_data_loader.py`

신규 **36** · 개정 0 · 실패 0 · 타입 **10종** (07-24 문서 실측치와 정확히 일치)

```
material 11 · equipment 6 · finance_param 6 · simulation_node 3 · standard_field 3
bom 2 · quality_spec 2 · emission_factor 1 · kpi 1 · sensor_spec 1     (is_core 22개)
```

**별칭 확정조회 3건 전부 1순위 히트**: 자용로→`EQ-FLASH-01` · OEE→`ISO-KPI-01` · MHP→`RM-MHP-001`

### C-2. 지식팩 — `scripts/api_knowledge_loader.py`

`core-m3-standards` 문서 **11건 / 청크 641개**. 60MB CPPS PDF 만 30MB 제한(`api/routes/knowledge_control.py:83`)으로 거부(예상됨).
검색 거리 **0.36~0.52** 로 전부 컷오프 0.65 이내 = **실제 주입된다**.

### C-3. ⚠️ 그런데 어느 프로젝트도 이 데이터를 쓰지 않는다

전 프로젝트 `project_meta.json` 을 훑은 결과 **39개 전부 `knowledge_pack_ids=[]`, `master_domains=[]`**. `get_grounding_context`(`core/knowledge_base.py:285-287`)는 팩 목록이 비면 즉시 빈 문자열을 반환하므로 641청크가 한 번도 프롬프트에 들어가지 않는다. **A-1 은 `project_meta.json` 파일 자체가 없어** 전부 기본값 폴백이다.

**결정(사용자 승인)**: **A-1 은 의도적으로 미연결 유지.** 단위 변환기에 제조 표준 지식팩은 노이즈이고, A-1 은 "파이프라인이 끝까지 도는가"의 기준선이다. **그라운딩 효과 실측은 P7 제조 4종에서** 하며 그때 연결한다.

---

## D. [설계 확정·미착수] 조직·권한·부서게시·전사 표준/검색/시뮬

전체 설계: **`docs/design_org_permission_enterprise.md`** (Phase 0~13, 835줄). 방향 선언에 따라 **A-1 완주 이후 착수**.

### D-1. 설계의 출발점 — "한 판 DB"는 이미 현실이었다

`data/master/master.db`(M1+M2)·`data/chroma_db`·`data/mcp_cache.db` 는 **전부 전역이고 project_id 컬럼조차 없다.** 프로젝트별 차별화는 `master_domains` 태그 하나뿐(`core/master_data.py:501`). 즉 격리 계층을 만드는 게 아니라 **이미 통합된 데이터 위에 권한 뷰를 씌우는** 작업이다.

**데이터 카탈로그도 신규 테이블이 0개**다 — M2 스키마 레지스트리(`external_systems`/`external_schemas`/`key_crosswalk`/`crosswalk_proposals`)가 정확히 그 구조다. DA 콘솔은 기존 `CrosswalkPanel` 의 확장이 된다.

**전사 단일 시뮬 실행 엔진도 코드 변경 0**이다 — `core/agent_graph.py:409-421` 의 `domain_agents` 필터가 비어 있으면 전 도메인이 순차 실행되고, `mfg_sim` + `sim_*.md` 6종이 영업→구매→생산→품질→물류→재무 체인을 이미 강제한다.

### D-2. 확정된 결정

1. 인증 = **경량 사용자 전환**(비밀번호 없음), SSO 교체 가능하게 `api/deps.py` 단일 추출 지점
2. 권한은 **백엔드 API 레벨 강제** + LLM 프롬프트·검색 경로에도 동일 적용
3. 조직 = **계층 조직도**(materialized path, GLOB 접두 매칭)
4. **부서는 하드코딩 금지 — 기준정보로 관리**(`master_records` 와 동일 버전 계보). `factory_control.py:304-337` 의 맵 3개는 **삭제**
5. 데이터 표준은 **생성 시 권장 / 게시 시 정합화 / DA 정기 배치**. 표준화는 **코드를 고치지 않고 `key_crosswalk` 매핑으로** 해결(이미 동작하는 앱을 안 깨뜨림)
6. 권한 3축 분리 — `executive`(전사 업무) ⟂ `admin`(시스템 설정) ⟂ **`DA`(전체 DB·표준 관리)**
7. **카탈로그 메타는 전사 공개 / 산출물 본문은 부서 스코프** — 일반 사용자가 "무엇이 어디 있는지"는 찾되 열람은 권한을 따름
8. **재사용·포크로 사일로 방지**

### D-3. 🚨 권한 도입 전 반드시 막아야 할 유출 (Phase 5)

`get_relevant_context()`(`core/knowledge_base.py:401-423`)가 전역 `project_releases` 컬렉션을 **프로젝트 필터도 거리 임계값도 없이** 검색해 상위 3건을 **모든 프롬프트에 주입**한다(`core/context_engine.py:50`). 재무 산출물이 구매 부서 프롬프트에 섞이는 구조다.
같은 파일의 `get_grounding_context()`(`:282-327`)는 팩 화이트리스트 + `RELEVANCE_CUTOFF=0.65` 이중 방어가 **이미** 되어 있으므로 그 검증된 패턴을 이식하는 것이 해법.

### D-4. 관련성 판정 — 앱을 분류하지 말고 데이터 겹침을 측정 (Phase 6-7)

**질문**: 기준정보와 무관한 개인 편의 도구를 게시하면 표준화 대상인가? 관련성을 어떻게 판단하나?
**답**: "이 앱이 의미 있나"는 주관적이라 반드시 오판한다. 중요한 건 하나뿐 — **이 데이터를 회사의 다른 곳도 쓰는가.** 판단이 아니라 계산이다.

- **등록과 표준화 분리** — 카탈로그 등재는 예외 없이 전부(LLM 0콜), DA 큐는 신호 있는 것만. 전부 큐에 넣으면 DA 가 익사하고 마찰이 게시 회피(섀도 IT)를 부른다
- 5신호 → `enterprise` / `local` / `island`. **가장 강한 신호는 카탈로그 교차 히트** — 두 부서가 같은 `(entity, field)` 를 쓰면 정의상 전사 개념
- **A-1 단위 변환기**(`value`/`fromUnit`/`toUnit`)는 히트율 0%·교차히트 0·3필드 → **island**, 큐 제외
- **★ 핵심은 자동 승격** — 오늘 개인 도구가 내일 다른 부서가 비슷한 걸 만들면 그 순간 전사 개념이 된다. 분류를 **저장 상태가 아니라 `reconcile` 마다 재계산되는 값**으로 두어 최초 판정의 정확도에 의존하지 않는다
- 개인 산출물 프라이버시 — `visibility='personal'` 추가(카탈로그 등재는 하되 전사 검색에서 소유자·DA 만)

### D-5. 재사용·포크 (Phase 8) — 사일로 중복 생성 방지

**발견이 포크보다 먼저다.** 있는 줄 몰라서 또 만드는 게 사일로의 실제 원인. 생성 폼에서 아이디어 입력 시 유사 산출물 제시(Phase 7 검색 + 6-7 교차히트 재사용). **"무시하고 새로 만들기"는 막지 않고 지표로만 남긴다** — 차단은 우회를 낳는다.

**`copy_project`(`factory_control.py:550-568`) 결함 4건**(포크에 그대로 쓰면 안 됨):
| 문제 | 결과 |
|---|---|
| `.archive`/`.git`/`node_modules` 통짜 복사 | 저장소 비대 — **`_EXPORT_EXCLUDE_DIRS`(`:1016`)가 이미 있는데 여기선 안 씀** |
| `project_meta.json` verbatim | **포크가 원본 부서 소유권을 물려받음** |
| `latest_state.json` 의 `project_name` 원본 그대로 | 포크 후 이름·경로 불일치 |
| 계보 미기록 | 사일로 지표 산출 불가 |

**반대로 "수정보완"은 신규 구현이 필요 없다** — 포크 후 `sprint/revision`(`:731-744`) → `TASK_REV_*` → `start_sprint:597-598` 이 REVISION 을 강제해 **Architect 를 건너뛰고 Tech_Lead 직행**(기획 산출물 재사용). `_INCREMENTAL_GUARD`(`nodes/execution.py:161-167`)가 포크 자산 유실을 막는다.

---

## E. 외부 세션(유료모델 테스트) 관련 — 관찰·검토

### E-1. 유료 경로 정상 작동 확인 (텔레메트리 실측)

`data/llm_call_log.jsonl` 11:19~12:49 총 96콜 기준:
- **`meta-llama/llama-3.3-70b-instruct`(OpenRouter 유료) 8콜 정상 응답** — 크레딧·키·라우팅 전부 정상
- A-1 이 이전 UI_DESIGN 에서 막히던 것이 **TECH_SPEC 까지 진행**(현재 `SUSPENDED_QUOTA`)
- 다만 **성공 35 / 실패 61** — 유료 전환만으로는 완주가 안 되고 있다

### E-2. 🚨 미해결 가설 — 쿨다운이 유료 제공사까지 배제한다

실패 61건 중 다수가 **`depth=1` · `in=0 out=0` · 0.14초**로 폴백을 한 번도 안 타고 죽는다. 원인 가설:
`_update_cooldowns`(`core/llm_gateway.py:399-412`)가 실패 모델을 **무조건 `MODEL_COOLDOWN_SEC`(기본 1800초)** 배제하는데 **유료 제공사도 똑같이 배제**된다. 전 모델이 쿨다운되면 `_compose_chain`(`:387-397`)이 `if not live: live = [ordered[0][1]]` 로 **첫 모델(무료 Gemini) 하나만**으로 재프로브 → 즉시 429 → 폴백 없음. 크레딧이 남은 유료 모델을 30분간 손도 안 댄다.
`_all_cooled(pro_chain)` 이면 Pro→Flash 강등(`:458-461`)까지 겹쳐 유료 Pro 가 더 멀어진다.

**미검증 가설이며 수정하지 않았다.** 유료로 완주가 안 되면 여기부터 확인할 것.

### E-3. 외부 세션 수정안 검토 (구현은 외부에서 진행)

외부 세션이 제시한 2건을 코드로 검증했다.
1. **`QuotaExhaustedException` 삼킴** — `nodes/execution.py:179-182` 의 `except Exception: return None` 이 쿼터 예외를 삼켜 빈 산출물로 둔갑시키는 것 **사실 확인**. 트래커 결함 #9 의 정확한 원인. ⚠️ **누락 1곳**: `nodes/clarification.py:25-56` 에도 동일 패턴이 있다. 나머지(`planning`/`vision_qa`/`universal`/`scoring`/`debate`)는 try 가 파싱만 감싸고 있어 안전.
2. **resume race condition** — 현상은 맞으나 **원인 규명이 부정확**했다. `resume-quota` 도 비동기인 게 문제가 아니라, **`/state/latest` 는 디스크 파일**(`factory_control.py:870`)을 읽는데 **`resume_from_suspend`(`core/async_orchestrator.py:306-345`)가 체크포인트만 갱신하고 `_save_latest_state` 를 호출하지 않는다.** API 를 바꿔도 폴링은 여전히 낡은 디스크 값을 읽는다.
   → 진짜 수정은 `aupdate_state` 뒤에 `aget_state` + `_save_latest_state` 3줄(`_suspend_for_quota:299-301` 의 대칭). **UI 도 같은 엔드포인트를 보므로 통제실 표시도 함께 고쳐진다.**

---

## 🚀 다음 과제

1. **A-1 실제 완주** — 유료 경로로 재개. 막히면 E-2 쿨다운 가설부터 확인.
2. 완주 후 트래커의 A-1 벤치마크 표(리드타임/자가복구/토큰/HOTL 피로도) 실측 기입 → 골든 벤치마크 채점 → **그 다음에야** 최적화 도구 취사선택.
3. P7 제조 4종 진입 시 `core-m3-standards` 지식팩 연결 → **그라운딩 효과 실측**(C-3).
4. (완주 이후) `docs/design_org_permission_enterprise.md` Phase 0 착수.
