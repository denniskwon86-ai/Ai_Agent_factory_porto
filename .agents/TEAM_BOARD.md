# AI Factory Studio 팀 현황판

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

## 검토 대기

### [CHRONICLE-01] 시스템 개발 & 비즈니스 완성 연대기 백서 작성 및 관리
- 상태: 검토 대기
- 책임 수행자 / 교차 검토자: Gemini Antigravity / 사용자(Supervisor) 및 전 팀원
- 목표·완료 기준: 창세기 사상부터 결함 잔혹사(#14~#21), A-1 완주, 4인 팀 체제, ECM E1/E2 통과까지의 시스템 역사를 상세 MD 백서와 인터랙티브 HTML/PPT 웹 백서(`docs/chronicle/index.html`)로 작성 및 수립.
- 증거·다음 행동: 상세 백서 [SYSTEM_DEVELOPMENT_CHRONICLE.md](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/SYSTEM_DEVELOPMENT_CHRONICLE.md) 및 인터랙티브 웹/PPT 백서 [index.html](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/index.html) 작성 완료.

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
  **검토 요청 관점**: ① 점진 도입 규칙("바인딩 없으면 통과")이 유출 창구가 되지 않는지
  ② 캐시 키 분리 대신 요청별 필터를 택한 판단(Codex 권고와 다름 — 근거는 커밋 메시지)
  ③ 상속(`inherit_descendants`)이 적용 가능성에 한정되고 열람 권한으로 비화하지 않는지
  ④ `master_version`·`effective_*` 미구현이 지금 단계에서 허용 가능한 한계인지.

## 차단

_현재 없음_

## 완료

완료 항목은 상세 이력을 이곳에 누적하지 않는다. 필요한 경우 `AI_HANDOFF.md`, 관련 커밋, 또는 `docs/` 산출물에서 확인한다.
