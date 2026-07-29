# AI Factory Studio 팀 현황판

> **🚨 [2026-07-29 사용자(Supervisor) 긴급 지침 전파]**
> **M2 구현은 보류하고, 모델·비용·컨텍스트 계측을 포함한 신규 A-1 카나리 1회를 먼저 수행하십시오.**
> 단, D-010은 현 범위에서 유지하고, D-014의 “범위 미지정=전사 공용”은 M2 신규 데이터에는 적용하지 않는 전제로 권한 설계를 진행하십시오. (M2 DB·API·권한 코드는 변경 금지)

### 📌 M1 $\rightarrow$ M2 진입 관문 교차검토 부채 판정 결과
- **D-010 (전수 주입)**: 5,300자 수준 조건부 승인. A-1 카나리에서 실증 요망.
- **D-011 (별칭 파생)**: 승인. 프롬프트 오탐률 관측.
- **D-012 (조직코드 SSOT)**: ECM 코드 체계 유지 승인.
- **D-013 / D-014**: "소유 범위와 공유 권한 분리" 원칙. "미지정=공용"은 M2 신규 데이터 적용 불가(반려).
- **ECM E1/E2 / MDM-SCOPE-01**: 조직 상속은 '문맥 적용 가능성'일 뿐 '데이터 접근 권한'과 철저히 분리. 독립 검토 후 닫기.

> 이 문서는 진행 중·검토 대기·차단 작업의 **현재 상태만** 관리한다.  
> 상세 경과는 중복 기록하지 않고 관련 커밋, 코드, 설계 문서, 테스트 증적으로 연결한다.

## 진행 중

### [PRODUCT-01] 사업모델·시장진입 전략 구체화
- 상태: 진행 중
- 책임 수행자 / 교차 검토자: Codex / 사용자 및 필요 시 전 팀원
- 목표·완료 기준: 첫 고객·첫 유스케이스·패키지·가격 원칙·도입 확장 경로를 제품 설계와 정합되게 정의한다.
- 영향 범위·결정/가정: 제품 포지셔닝, UI/UX 우선순위, LLM 비용 설계에 영향을 준다. 제품 방향의 최종 결정은 사용자에게 있다.
- 증거·다음 행동: `docs/business-model/index.html`에 내부 1호 고객 → 그룹 확산 → 제품회사·ITO 파트너 → 외부 확장 구조를 정리했다. 첫 파일럿 대상, 이전가격, IP·계약 구조, 외부 판매 조건을 사용자 결정 항목으로 남겼다.

### [IMPLEMENT-01] 현재 기능 구현·오류 보정
- 상태: 진행 중
- 책임 수행자 / 교차 검토자: Claude Code / 작업별 지정
- 목표·완료 기준: 외부 세션에서 진행 중인 기능 구현과 오류 보정을 코드·테스트 증거로 완료한다.
- 영향 범위·결정/가정: `DECISIONS.md` D-003(권한 상속은 OPERATING_PARENT 만)·D-004(부서 권한
  재사용)·D-005(부서 id/node_id 이중 해석)에 의존한다. 되돌림 비용이 D-003 은 높다.
- 증거·다음 행동: 커밋 `2e42968ec` · `core/enterprise_context/` · `tests/test_ecm_e1.py`(36건) ·
  실측(ORG_ENFORCE=True: admin 9 / bob 0 / exec 5+경로2, 집계 대상 상세는 403) ·
  설계서 §11 E1 완료 표. **검토 요청 관점**: ① 공유서비스·연결집계에서 권한이 새지 않는지
  ② 부서 매핑 없는 상위 노드의 `readable=false` 경로 노출이 정보 유출인지 ③ 순환·깊이 상한이
  실제 조직 규모에서 충분한지 ④ `enterprise_scope_id` 이중 형태 공존의 회귀 위험.

### [ECM-E2-XWALK-01] 크로스워크·MCP 조직 범위 격리 (ECM E2 잔여)
- 상태: **구현 완료, 교차검토 대기** (§3-1 **C등급** — 권한·격리. 통합 전 독립 검토 필요)
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(격리 실측)·Codex(제품 영향)**
- 목표·완료 기준: 설계서 §11 E2 잔여 중 "MDM/카탈로그/크로스워크/MCP 에 범위 키 도입과 권한
  강제"의 마지막 두 개. 카탈로그·용어사전·계약은 D-013 으로 완료돼 있었다.
- 영향 범위·결정/가정: **`DECISIONS.md` D-016**. `external_systems` 에만 ECM-lite 3키를 두고
  자식은 부모 게이트를 지난다. MCP 는 캐시보다 먼저 판정하고, 범위 해석 실패 시 실측 병기를
  생략한다(fail-closed — 기준정보 주입과 의도적으로 다름).
- 증거·다음 행동: `core/crosswalk.py`(`is_system_visible`·`require_system_visible`·
  `systems_coverage`) · `core/mcp_broker.py` · `api/routes/{crosswalk,mcp}_control.py` ·
  `tests/test_crosswalk_mcp_scoping.py`(18건) · 거버넌스 콘솔 ①에 연계 시스템 커버리지 추가.
  **★ 실재한 누출을 닫았다**: `get_live_context()` 가 활성 시스템을 전부 순회해, 배터리소재
  프로젝트 프롬프트에 동제련 연계 시스템의 실측값이 섞여 들어갔다. 상태 모델에는 조직 문맥이
  이미 있었고 **이 경로만 그것을 안 보고 있었다**.
  **검토 요청 관점**: ① 자식 테이블에 키를 복제하지 않은 대가(경로마다 게이트 한 줄)를 감안할 때
  빠진 경로가 없는지 — 특히 CSV import·제안 승인/기각 ② MCP `resolve` 의 거부가 기존 관례상
  409(MCPError)로 나가는데 404 가 맞지 않은지(존재하지 않는 시스템도 현재 409라 일관은 유지)
  ③ fail-closed 판단이 ECM 도입 초기에 실측 병기를 과하게 죽이지 않는지(기본 off 기능이라
  손실이 작다고 봤다) ④ `entity_mode` 완전 일치 규칙이 VIRTUAL Sandbox(E3) 설계와 충돌하지 않는지.

### [QUALITY-TEL-01] 품질 결과 텔레메트리 + 실패 원인 분류 (§10.3 / §8.3)
- 상태: **구현 완료, 교차검토 대기** (§3-1 B등급 — 내부 계약 추가, 권한·마이그레이션 없음)
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(계측 정합성·실측)·Codex(화면 오독 위험)**
- 목표·완료 기준: `llm_calls` 만 있고 비어 있던 `quality_outcomes` 축을 채운다 — 게이트별
  통과/실패·재작업 횟수·실패 원인 분류·사람 수용 판정. LLM 0콜. UI 까지 완결(§7 역할 규약).
- 영향 범위·결정/가정: **`DECISIONS.md` D-015**(결정론적 근거 없으면 미분류 유지).
  훅 4곳 — `nodes/utils/scoring.py`(게이트 판정, 유일한 채점 지점) ·
  `nodes/execution.py`(빌드 실패 `_build_failed` 단일화, 생성 실패) ·
  `core/async_orchestrator.py`(HOTL 사람 판정). 저장은 append-only JSONL
  (`data/quality_outcomes.jsonl`), 부서 스코프는 텔레메트리와 **같은 `apply_scope`** 재사용.
- 증거·다음 행동: `core/quality_telemetry.py` · `api/routes/telemetry_control.py`(`/quality/*` 4개) ·
  `frontend/src/lib/qualityApi.ts` + `components/QualityOutcomesView.tsx`(운영 계기판 탭) ·
  `tests/test_quality_outcomes.py`(30건) · `tests/test_quality_outcomes_wiring.py`(6건).
  ⚠️ **브라우저 실측 미완** — Antigravity 테스트 중이라 8080 을 건드리지 않았다(§3-1).
  그쪽 종료 후 화면 실측 필요.
  **함께 고친 것**: 빌드 실패 경로에서 빌더가 남긴 `build_error_log` 가 **버려지고 있었다** —
  자가복구 재시도가 원인을 모른 채 같은 프롬프트를 다시 돌리는 상태였다(`_build_failed` 로 복구).
  **검토 요청 관점**: ① 점수 미달을 자동 분류하지 않는 판단(D-015)이 지표를 쓸모없게 만들지는
  않는지 — 대안은 "미달 기준 id → 원인" 매핑표를 두는 것인데 그 표의 근거를 만들 방법이 없다고
  봤다 ② `no_human_decision` 3칸 분리가 화면에서 실제로 구분되어 읽히는지(Codex)
  ③ HOTL 재개 기록이 게이트 기록과 짝이 없어 orphan 으로 남는 구조가 허용 가능한지 —
  현재는 "어느 게이트에 대한 판정인지"를 추정하지 않고 stage 만 남긴다
  ④ 빌드 로그 패턴 규칙(`_BUILD_RULES`)의 오탐 — 특히 `test_harness` 와 `model_quality` 경계.

### [MDM-SEED-01] M1~M4 기준정보 시드 · 주입 경로 정상화 (2026-07-29)
- 상태: **구현 완료, 교차검토 대기**
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(데이터 정합성)·Codex(제품 영향)**
- 목표·완료 기준: 문서로만 있던 M1~M4 기준정보를 저장소에 적재하고 조직 범위에 바인딩한다
  (감사 `ENTERPRISE-01` Action 1 종결). 값의 정확도는 판정 대상이 아니고 보정 목록으로 넘긴다.
- 영향 범위·결정/가정: **`DECISIONS.md` D-010(주입 상한 폐기 = 전수 주입)·D-011(별칭 파생)**.
  D-010 은 **모든 에이전트 프롬프트의 기준정보 블록 길이를 바꾼다**(≈2,200자 → ≈5,300자) —
  되돌림은 환경변수로 즉시 가능하나 제품 영향(토큰 비용) 검토가 필요하다.
- 증거·다음 행동: 커밋 `34a3e8a37` · `core/master_data_seed.py` ·
  `tests/test_master_document_seed.py`(30건) · **전체 709 통과** ·
  상세 인계 [`docs/handoff_2026-07-29_master_seed_and_injection.md`](../docs/handoff_2026-07-29_master_seed_and_injection.md).
  실측: 적재 44건·바인딩 44건 / 격리(배터리·동제련 상호 0건, **LS전선 0건**) /
  주입 30건 중 절단 0 / 품질 보정 목록 5건(high 4).
  **검토 요청 관점**: ① 전수 주입이 토큰 비용·프롬프트 품질에 미치는 영향이 감당 가능한지
  (실측 필요 — 지금은 길이만 확인했고 산출물 품질 비교는 못 했다)
  ② 품질 보정 목록 5건(황산 UOM 500배·Cpk 3건·NiSO4 적자)이 **문서 수정으로 처리될지 실데이터
  대기로 남을지** — 데이터 담당 판단 필요
  ③ ~~외부 세션 시드 스크립트와 영역 중복~~ → **정리 완료(D-012)**. 조직 코드 SSOT 를
  `core/enterprise_context/seed.py` 로 확정했다. 외부 산출물이 같은 조직에 다른 코드 체계
  (`BU_SMELTING`·`PLANT_ONSAN_1/2`)를 쓰는데, **조직 코드 불일치는 곧 권한 유출**이다 —
  바인딩이 조용히 건너뛰어지고 미바인딩 레코드는 전사 공통으로 통과한다.
  현재 그 JSON 을 읽는 코드는 0곳이라 잠재 상태에서 잠갔다.
  **Antigravity 앞 요청**: `scripts/generate_realistic_mfg_data.py` 의 `organization_tree` 를
  ECM 코드 체계에 맞추거나, 조직 정의를 빼고 데이터만 생성하도록 조정해 주십시오.
  어느 쪽 조직 구조도 M1~M4 문서에 근거가 없어(문서에 공장 정보 0건) 사실성으로는 우열을
  가릴 수 없었고, 이미 44건이 붙어 있는 쪽을 택했습니다.
  ④ 별칭 파생 규칙이 오탐을 만들지 않는지(단어경계 + 최소 2자 + 수치 토큰 배제로 억제했다).

## 검토 대기

### [CHRONICLE-01] 시스템 개발 & 비즈니스 완성 연대기 백서 작성 및 관리 (v2.0 쇄신 완료)
- 상태: 검토 대기
- 책임 수행자 / 교차 검토자: Gemini Antigravity / 사용자(Supervisor) 및 전 팀원
- 목표·완료 기준: C-Level 경영 시뮬레이터 사상 통합, 어색한 어휘 쇄신, 실제급 제조 시드 데이터 성과를 반영한 연대기 백서 v2.0 작성 완료.
- 증거·다음 행동: 상세 백서 [SYSTEM_DEVELOPMENT_CHRONICLE.md](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/SYSTEM_DEVELOPMENT_CHRONICLE.md) 및 인터랙티브 웹/PPT 백서 v2.0 [index.html](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/index.html) 갱신 완료.

### [ENTERPRISE-01] 엔터프라이즈 제조·시뮬레이션 트랙 선행 점검 (M1~M4 감사 완료)
- 상태: 검토 대기 → **Claude Code 교차검토 완료, 반영 착수**
- 책임 수행자 / 교차 검토자: Gemini Antigravity / Claude Code(완료), Codex, 사용자
- 목표·완료 기준: M1~M4 기준정보와 ECM(2026-07-28) 설계 및 시나리오(D-1~D-4, E-1~E-2) 정합성 선행 감사 완료.
- 증거·다음 행동: 감사 보고서 [audit_report_m1_m4_enterprise_context.md](file:///C:/Users/denni/.gemini/antigravity-ide/brain/674cfd24-4b90-4e2e-8295-258d25bd5b89/audit_report_m1_m4_enterprise_context.md) 작성 완료. Claude Code R-001/R-002 반영 진행 중.

### [MDM-SCOPE-01] R-001 기준정보 조직 범위 바인딩 (C등급 — 통합 전 검토 필요)
- 상태: 검토 대기
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(정합성·데이터)·Codex(제품 영향)**
- 목표·완료 기준: 감사 Finding 1(기준정보에 조직 문맥 없음) 해결. 본문은 MDM 에 두고
  `master_scope_bindings` 로 **원본 1 : 적용범위 N**, 주입 경로에 범위 필터.
- 영향 범위·결정/가정: `TEAM_PROTOCOL` §3-1 **C등급**(권한·보안 + 데이터 구조). `DECISIONS.md`
  D-009 에 의존. 점진 도입(바인딩 없으면 전사 공통 통과)으로 회귀 위험을 낮췄다.
- 증거·다음 행동: 커밋 `1fe965902` · `tests/test_master_scope_binding.py`(18건) · 전체 680 통과 ·
  실측(제1공장 3 / 제2공장·동제련 2 / **LS전선 1** / 범위 미지정 3).
  **★ ① 에 대한 자체 답(2026-07-29, 커밋 `34a3e8a37`)**: **유출 창구가 됐다.** 재시드가 기존
  레코드를 건너뛸 때 바인딩 확인까지 건너뛰어, ECM 조직 없이 먼저 적재된 레코드가 미바인딩으로
  남고 통과 규칙을 타고 **모든 조직에 노출**됐다(실측 DB: 바인딩 26 < 레코드 45). 수정 후 44/44,
  LS전선 노출 0건. `test_reseed_binds_preexisting_records` 로 잠금. 규칙 자체는 유지하되
  **미바인딩 레코드 수를 상시 관측**해야 한다는 것이 교훈 — 검토 시 이 관점을 함께 봐 주십시오.
  **검토 요청 관점**: ① 점진 도입 규칙("바인딩 없으면 통과")이 유출 창구가 되지 않는지
  ② 캐시 키 분리 대신 요청별 필터를 택한 판단(Codex 권고와 다름 — 근거는 커밋 메시지)
  ③ 상속(`inherit_descendants`)이 적용 가능성에 한정되고 열람 권한으로 비화하지 않는지
  ④ `master_version`·`effective_*` 미구현이 지금 단계에서 허용 가능한 한계인지.

## 차단

_현재 없음_

## 완료

완료 항목은 상세 이력을 이곳에 누적하지 않는다. 필요한 경우 `AI_HANDOFF.md`, 관련 커밋, 또는 `docs/` 산출물에서 확인한다.
