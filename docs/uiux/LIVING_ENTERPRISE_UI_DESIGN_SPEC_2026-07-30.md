# AI Factory Studio · Living Enterprise Canvas
# UI 설계서

> 문서 버전: 1.0  
> 기준일: 2026-07-30  
> 적용 기준: Supervisor 승인 `master-concept`  
> 연계 문서: `LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md`  
> 구현 대상: `frontend/` M6 통합 UI

---

## 1. 디자인 방향

### 1.1 제품 인상

AI Factory Studio는 일반적인 카드형 AI 대시보드나 챗봇이 아니라, 실제 회사의 업무·데이터·현업 SW·Agent·시뮬레이션·의사결정을 한 화면에서 연결하는 **경영 운영 캔버스**로 보여야 한다.

핵심 인상은 다음 네 가지다.

- **기업용**: 신뢰 가능하고 과장되지 않으며, 수치의 근거와 범위를 분명히 한다.
- **업무 중심**: 기능명이 아니라 사용자가 처리해야 할 일과 업무 흐름을 중심에 둔다.
- **살아 있는 시스템**: 업무 노드·데이터·SW·Twin·Agent 상태가 연결되어 움직인다.
- **행동 가능**: 상태 확인에서 끝나지 않고 해결 행동·승인·실행으로 이어진다.

### 1.2 승인 시안에서 고정할 요소

1. 좌측 역할 기반 의사결정 대기열.
2. 중앙 Enterprise Digital Thread.
3. 업무 위의 DATA·SW·TWIN 레이어.
4. 하단 Trust Foundation.
5. 우측 회사 범위 Atlas.
6. 상단 회사·사업부·공장 Context.
7. LS Blue는 구조, LS Red는 결정·주의·핵심 행동에 제한 사용.

### 1.3 프로덕션에서 보정할 요소

프로토타입은 한 화면에 전체 개념을 담기 위해 8~11px 텍스트를 사용했다. 실제 제품에서는 가독성을 위해 아래 최소 크기를 적용한다.

- 본문 14px 이상.
- 폼 라벨·보조문 12px 이상.
- 버튼 13px 이상, 높이 36px 이상.
- 핵심 행동 버튼 높이 42~48px.
- KPI 22px 이상.
- 10~11px는 해시·ID·타임스탬프 같은 기술 메타데이터에만 사용.

---

## 2. 디자인 토큰

### 2.1 기본 컬러

| 토큰 | 기본값 | 의미 |
|---|---|---|
| `--brand-primary` | `#0A1E5A` | 회사 구조, 헤더, 선택 상태 |
| `--brand-accent` | `#FA002D` | 핵심 결정, 긴급, 주요 CTA |
| `--brand-data` | `#009BB4` | 데이터·지식·연계 |
| `--brand-link` | `#0569A0` | 탐색, 링크, 보조 선택 |
| `--surface-canvas` | `#F9F9F7` | 업무 캔버스 |
| `--surface-warm` | `#F2F0EA` | 의사결정 큐 |
| `--surface-panel` | `#FFFFFF` | 카드·패널 |
| `--ink-strong` | `#101A2D` | 제목·핵심 본문 |
| `--ink-muted` | `#667084` | 보조 설명 |
| `--line-default` | `#D8DBE1` | 경계선 |
| `--state-good` | `#0B8D82` | 검증된 정상·완료 |
| `--state-warn` | `#D97820` | 주의·부분 충족 |
| `--state-danger` | `#C71F3D` | 실패·차단·긴급 |
| `--state-unknown` | `#6B7280` | 미측정·미검증·기록 없음 |

색만으로 상태를 전달하지 않는다. 아이콘·라벨·설명 문구를 함께 사용한다.

### 2.2 회사별 브랜드 테마

최상위 회사 마스터에 아래 테마를 등록하고 Shell에 적용한다.

```ts
type EnterpriseBrandTheme = {
  entity_id: string;
  logo_url?: string;
  wordmark_url?: string;
  product_name?: string;
  primary: string;
  accent: string;
  data?: string;
  link?: string;
  surface?: string;
  favicon_url?: string;
  min_contrast: 4.5 | 7;
  inherited_from?: string;
  approved_by: string;
  approved_at: string;
};
```

하위 법인·가상회사는 상위 테마를 상속하되 승인된 프로필만 덮어쓴다. 회사 컬러가 상태 의미와 충돌하면 상태색을 우선한다. 예를 들어 회사 대표색이 초록이어도 “승인됨”을 의미하지 않는다.

### 2.3 타이포그래피

```css
--font-ui: Pretendard, "Noto Sans KR", "Segoe UI", Arial, sans-serif;
--font-mono: "Cascadia Mono", Consolas, monospace;
```

- 제목/본문/버튼: UI 폰트로 통일.
- 숫자 비교, 코드, 해시, 비용, 타임스탬프: mono.
- 장식용 영문 폰트는 사용하지 않는다.
- 다른 글꼴이 필요하면 경영 KPI 또는 특정 브랜드 워드마크 한정으로 사용한다.

### 2.4 간격·라운드·그림자

- 기본 간격 단위: 4px.
- 화면 패딩: 24~32px.
- 카드 내부: 16~20px.
- 주요 패널 gap: 16px.
- 버튼 radius: 6px.
- 카드 radius: 8px. 지나치게 둥근 16~24px 카드 남발 금지.
- 기본 그림자: `0 6px 18px rgba(16,26,45,.08)`.
- 선택·중요도는 그림자보다 좌측 bar, border, 배경 대비로 표현.

---

## 3. 전역 레이아웃

### 3.1 데스크톱 기준

| 항목 | 값 |
|---|---:|
| 최소 지원 너비 | 1280px |
| 권장 너비 | 1440~1920px |
| Top Bar | 72px |
| 좌측 Decision Rail | 280px |
| 우측 Atlas Rail | 360px |
| 중앙 최소 너비 | 720px |
| 상세 Drawer | 440~560px |
| 전체화면 작업공간 본문 | `calc(100vh - 72px)` |

```text
┌────────────────────── Global Top Bar ──────────────────────┐
│ CI  Context          Primary Navigation        User/Action  │
├──────────────┬──────────────────────────────┬───────────────┤
│ Decision     │ Enterprise / Work Canvas     │ Atlas Global  │
│ Queue        │                              │ Rail          │
│              │                              │               │
│              ├──────────────────────────────┤               │
│              │ Trust Foundation / Status    │               │
└──────────────┴──────────────────────────────┴───────────────┘
```

### 3.2 화면 유형

| 유형 | 사용처 | Shell 유지 | Atlas |
|---|---|---|---|
| Decision Canvas | 경영 홈 | 승인된 3열 구성 전체 유지 | 고정 Decision Brief |
| Immersive Studio | Software Factory, Agent Studio, Digital Twin | 전역 Shell + Context Bar 유지 | 항상 접근 가능하되 Supervisor 통합·Context Pane·Drawer 중 화면 목적에 맞게 선택 |
| Workflow Hub | 협업 | 전역 Shell + Context Bar 유지 | 선택 앱·결정·발간 문맥의 고정 Rail |
| Registry | Knowledge, Admin | Top Bar 유지 | 문맥 도움 모드 |
| Focus Drawer | Decision/Asset/Release 상세 | 배경 화면 유지 | 선택 대상과 동기화 |
| Confirm Sheet | 승인·승격·중단 | 배경 유지 | 영향 설명 가능 |

기존처럼 모든 기능을 `fixed inset-0 z-50` 독립 화면으로 띄우지 않는다. URL과 선택 문맥을 보존하는 페이지/드로어 구조로 전환한다.

경영 홈의 `의사결정 큐 + Digital Thread + Atlas` 3열 골격을 전용 Studio에 그대로 반복하지 않는다. Atlas는 별도 기능 메뉴가 아니라 전역 Supervisor이므로 모든 Studio에서 한 번의 행동으로 접근 가능해야 하지만, 작업 화면을 압축하는 네 번째 고정 열을 기계적으로 추가하지 않는다. Factory에서는 기존 Supervisor Console에 통합하거나 Drawer로 열고, Guided Start에서는 단계 도움 패널로 제공할 수 있다.

### 3.4 전용 Studio 공간 모델

| Studio | 좌측 | 중앙 | 작업 Inspector | Atlas 제공 방식 |
|---|---|---|---|---|
| Software Factory | 신규 기획에서는 요구 입력, 실행 단계에서는 Control/WBS | Supervisor Timeline 또는 현재 집중 작업 | Preview/Artifact 또는 현재 단계 보조 정보 | Supervisor Console 통합이 기본, Context Drawer 병행. 별도 네 번째 고정 열 금지 |
| Agent Studio | Template·추천 구성 | Agent Workflow Canvas | 선택 Agent·Workflow Health·Model·Skill·HOTL·복구 | Agent 구성·비용·품질·연결 영향 질의 |
| Digital Twin | 기준선·시나리오 목록 | KPI + Value Flow + Scenario Result | 가정·외부동인·공식·신뢰도 | 결과 원인·불확실성·대안·보고서 생성 질의 |

경영 홈에서 Studio로 이동할 때 선택한 회사·업무·프로젝트를 전달한다. Studio의 공통 상단 바에는 `경영 홈으로 돌아가기`와 현재 회사 문맥을 항상 표시한다. Atlas는 Task ID를 필수로 요구하지 않으며 회사·프로젝트·선택 객체 문맥을 자동으로 인계받는다. Atlas의 존재를 보장하는 것과 고정 Rail을 강제하는 것은 구분한다.

### 3.3 목표 URL 구조

```text
/enterprise
/enterprise/decisions/:decisionId
/build
/build/start
/build/projects/:projectId
/build/releases/:releaseId
/collaboration/deliver/:releaseId
/collaboration/inbox
/collaboration/apps
/collaboration/decisions/:decisionId
/collaboration/publications/:publicationId
/operate/workspace
/operate/promotions/:releaseId
/operate/shadow/:runId
/operate/programs/:releaseId
/simulate
/simulate/scenarios/:scenarioId
/knowledge
/knowledge/reference
/knowledge/master
/knowledge/catalog
/knowledge/glossary
/knowledge/integrations
/knowledge/lineage
/knowledge/external
/agent
/agent/workflows/:templateId
/agent/skills
/agent/benchmark
/admin/enterprise
/admin/profile
/admin/access
/admin/audit
```

React Router 도입 여부와 무관하게 URL은 새로고침·공유·뒤로가기가 가능한 상태 계약으로 관리한다.

---

## 4. 전역 컴포넌트 설계

### 4.1 `CompanyContextBar`

**구성**: CI, 회사명, 문맥 breadcrumb, REAL/VIRTUAL/COMPETITOR 배지, 회사 전환.  
**상태**: loading, verified, denied, stale.  
**동작**: 전환 전 서버 검증 → 성공 시 공통 헤더 갱신 → 모든 Read Model 무효화/재조회.  
**금지**: 문맥 ID를 사용자가 직접 텍스트 입력하게 하지 않는다.

드롭다운 마지막에는 `회사 구조·가상회사 관리` 진입을 고정한다. `Company Universe` 화면은 좌측 회사 트리, 중앙 선택 회사 프로필·산업 플레이북·추천 기능, 우측/하단 가상회사 생성기의 3단 구조를 사용한다. REAL은 네이비·브랜드색, VIRTUAL은 보라 계열 배지로 구분하되 색만으로 상태를 전달하지 않는다.

### 4.2 `DecisionQueue`

**행 높이**: 최소 84px.  
**필드**: 시각/도메인, 제목, 영향 요약, 상태, 담당 역할, 기한.  
**상태**: urgent, waiting-user, blocked, information, selected.  
**동작**: 클릭 시 중앙 노드·Decision Focus·Atlas를 같은 ref로 동기화.

### 4.3 `EnterpriseThreadCanvas`

- 공정/업무 노드는 process profile 기반 동적 렌더링.
- 노드 사이 관계는 운영 흐름·데이터 흐름·승인 흐름을 구분.
- 줌/팬보다 “업무 단계 선택 → 관련 레이어/결정 보기”를 우선.
- 노드 최대 12개 초과 시 상위 도메인 그룹과 drill-down 사용.

### 4.4 `DomainNode`

```ts
type DomainNodeVM = {
  id: string;
  label: string;
  sequence?: number;
  status: 'normal' | 'attention' | 'decision_required' | 'blocked' | 'unknown';
  primary_metric?: { label: string; value: string; status?: string };
  evidence_count: number;
  confidence?: number;
  updated_at?: string;
};
```

노드 선택 면적은 최소 64×64px. 원형 노드는 순차 업무 흐름에 사용하고, 상세 노드는 카드로 확장한다.

### 4.5 `LayerOverlay`

DATA, SW, TWIN은 토글 가능하며 모두 끄는 것도 허용한다.

- DATA: 자산, Master, 지식팩, 외부지표, 최신성.
- SW: 프로젝트, 릴리스, 운영 상태, 담당 Agent.
- TWIN: 시나리오, 기준선, 영향, Backtest.

레이어 아이템은 해당 업무 노드와 시각적으로 연결하고 클릭 시 상세 Drawer를 연다.

### 4.6 `TrustFoundationStrip`

| 카드 | 핵심 정보 | 경고 |
|---|---|---|
| MDM | 연결 도메인, 범위 커버리지, 중복 | 미바인딩·고신뢰 중복 |
| 운영 데이터 | 연결 시스템, 마지막 성공, 계약 | 연결 실패·계약 위반 |
| 지식 | 승인 팩, 문서/청크, 검토대기 | 미승인 자동사용 위험 |
| 외부지표 | 사용 가능 지표, vintage, 지연 | 기준선 사용 차단 |

숫자보다 상태의 완전성과 기준시각을 먼저 표시한다.

### 4.7 `AtlasGlobalRail`

**헤더**: Atlas, 현재 문맥, 온라인/부분 데이터/차단 상태.  
**본문**: 현재 화면 요약, 우선 제안, 근거, 부족 데이터, 관련 실행.  
**빠른 질문**: 왜 이 판단인가 / 데이터가 부족한가 / 관련 SW·Agent 상태 / 시나리오로 보기.  
**생성 상담**: 업무 SW / 시뮬레이터 / 보고서 3개 진입을 항상 노출하고, 선택 시 목적·필요 기능·데이터·Agent·검증 계획을 추천 선택지로 구체화한다.  
**입력창**: Task ID 없이 질문 가능.  
**제어**: 실행 초안 카드 → 영향 확인 → HOTL 승인.

Atlas가 긴 답변을 할 때 화면 전체를 덮지 않는다. 답변은 접을 수 있는 블록으로 나누고 근거·가정·실행을 별도 섹션으로 표시한다.

### 4.8 상태 컴포넌트

#### `CompletenessBanner`

- 화면 최상단 콘텐츠보다 먼저 배치.
- `complete=false` 원천과 오류를 표시.
- 닫기 가능하더라도 작은 지속 배지를 남김.

#### `GateRow`

- 상태 아이콘/라벨, 검사명, 왜, 해결 행동, 근거 링크.
- `unverifiable`은 회색이 아니라 경고 테두리와 차단 설명.

#### `EvidenceChip`

- 출처 유형, 식별자, 조직 범위, 기준시각, 검증 상태.
- hover만으로 중요 정보를 숨기지 않음.

#### `PrimaryDecisionAction`

- 문제·영향 패널 안쪽 우하단 또는 sticky footer에 배치.
- 화면 외곽 헤더에 단독 배치하지 않음.
- 버튼 문구는 “확인”, “적용” 대신 대상과 결과를 명시: `기준안으로 승인`, `전사 승격 신청`, `운영 사용 중단`.

---

## 5. 메뉴별 화면 레이아웃

### 5.1 Enterprise

#### `/enterprise`

- 좌 280: Decision Queue.
- 중앙 상단: 업무 노드와 DATA/SW/TWIN 토글.
- 중앙 하단: Decision Focus + Trust Foundation.
- 우 360: Atlas.
- 상단 KPI는 최대 4개. “업무 도메인 / Master Data / 연결 / 근거 충실도”를 기본으로 하되 회사 프로필에 따라 교체.

#### Decision Drawer

- 너비 520px.
- Summary → Impact → Evidence → Related objects → Approval → History.
- 주요 행동 sticky footer.

### 5.2 Build SW

#### `/build`

- 상단: `새 업무 만들기`와 진행 상태 필터.
- 본문: 진행 중 / 내 프로젝트 / Mega / Releases / Archive.
- 프로젝트 카드 최소 320px, 최대 3열.
- 카드 주 CTA는 `열기`, 보조 메뉴에 복제·삭제·관리.

#### `/build/start`

- 프로젝트 작업공간과 같은 전체 Workflow Map을 사용한다. 아직 생성되지 않은 WBS 영역에는 빈 태스크 대신 앞으로 생성될 단계·산출물·승인 계약을 표시한다.
- 중앙은 요구 질문·선택지·청사진을 넓게 제공하고, 우측은 준비율 숫자보다 확인된 조건·부족 데이터·다음 전환을 설명한다.
- 선택 옵션 높이 56px 이상, 추천안은 첫 번째이되 사용자가 쉽게 변경 가능.

#### `/build/projects/:id`

- Top: 실제 Graph 기반 Workflow Production Line 약 108px. 완료·진행·승인대기·재작업·실패·차단과 현재 위치를 항상 표시.
- Body: WBS·의존관계 Spine 260~280px / 현재 작업·산출물 Focus Surface 가변 / 수행 이유·다음 전환·실행 기록 300~340px.
- 중앙은 `현재 작업 툴바 → 현재 작업·산출물 → 사용자 상호작용 카드` 순서로 배치한다. 사용자 결정 대기와 Jarvis Console은 하단 상호작용 카드 안에서 상하로 배치하되 화면 바닥에 붙이지 않고 좌우·하단에 14px 이상의 여백을 둔다.
- 사용자 결정이 1건 이상이면 긴급 결정 행을 Jarvis 위에 표시한다. 0건이면 결정 행을 완전히 접고 Jarvis만 남기며, 확보된 높이는 현재 작업·산출물 영역에 돌려준다. 별도의 빈 결정 카드나 화면 끝 고정 바는 표시하지 않는다.
- 1280×720 기준 상호작용 카드는 결정 있음 170~180px, 결정 없음 110~120px를 권장한다. 결정 설명·영향·질문 입력·대표 질문이 서로 눌리지 않도록 각 행에 충분한 수직 여백을 둔다.
- 1280×720 기준 상호작용 카드는 결정 있음 170~180px, 결정 없음 110~120px를 권장한다. 결정 설명·영향·질문 입력·대표 질문이 서로 눌리지 않도록 각 행에 충분한 수직 여백을 둔다.
- 1280px 기준 주요 제목은 14px 이상, 상태·설명·선택 버튼은 12px 이상, 보조 메타데이터도 11px 이상을 원칙으로 한다. 전체 정보를 한 화면에 넣기 위해 8~10px 글자를 남발하지 않는다.
- 실시간 Agent 기록은 우측 상태 영역에 시간순으로 표시하고, 전체 로그는 중앙 집중 모드로 확대한다.
- 보고서·코드·Preview·Diff는 중앙 Focus Surface에서 전환한다. 전체 단계와 WBS를 숨기는 별도 페이지로 이동하지 않는다.
- HOTL/Quota/Failure는 본문보다 위에 sticky bar.

### 5.3 Collaboration

#### 공통 Workflow Hub

- 1280px 이상: 좌측 협업 모듈 Rail 238px / 중앙 가변 작업면 / 우측 Jarvis Rail 300px.
- 1024~1279px: 모듈 Rail은 축약·Drawer 전환, Jarvis는 우측 Drawer로 열되 현재 문맥과 대화 상태를 보존.
- 상단 Context Bar에는 회사·업무 범위·선택 릴리스/시뮬레이션·REAL/VIRTUAL 상태를 표시.
- 본문 13~14px, 보조 정보 12px 이상을 기본으로 하며 기능을 한 화면에 넣기 위해 8~10px 텍스트를 사용하지 않는다.

#### `/collaboration/deliver/:releaseId`

- 중앙은 `릴리스 확인 → 수신자 선택 → 권한 Manifest → 전달 검토` 4단 Wizard.
- `CapabilityManifestCard`는 플랫폼 인증 상속, 기능 권한, 요구 데이터 범위, 금지 기능을 구분한다.
- 데이터 권한 부족은 자동 부여 체크박스가 아니라 별도 권한 요청 경로로 표시한다.
- 최종 CTA는 `이 조건으로 사용자에게 전달`이며 대상·버전·만료·영향 요약과 같은 시야에 둔다.

#### `/collaboration/inbox` · `/collaboration/apps`

- `받은 요청 / 보낸 요청 / 내 앱` 탭을 사용한다.
- `IncomingAppRequestCard`에는 발신자·부서, 앱·릴리스, 요청 사유, 최소 권한, 데이터 범위, 만료, 감사 대상 여부를 표시한다.
- 수락·거절은 카드 하단에 나란히 두되 수락을 무조건 기본값으로 강조하지 않는다.
- 수락 후 `MyAppPocket`에는 실행, 세부 권한, 버전 변경, 전달 출처, 회수 상태를 표시한다.

#### `/collaboration/decisions/:decisionId`

- 중앙 상단은 결정 질문, 기준선, 시나리오, KPI 영향, 불확실성, 근거 스냅샷.
- `RoleViewTabs`는 요청자·의사결정자·영향 부서 관점을 전환하되 같은 `decision_package_id`를 유지한다.
- 하단은 참여자 검토 상태, 회의 요청, 최종 결정, 실행과제, 효과측정의 시간 순서.
- 사용자가 아직 결정할 수 없는 경우 `결정` CTA 대신 부족 근거와 재계산·추가검토 행동을 표시한다.

#### `/collaboration/publications/:publicationId`

- 중앙은 실제 보고서 페이지 비율의 `PublicationPreview`, 우측은 `PublicationGatePanel`과 Jarvis 근거 점검.
- 대내/대외 유형 전환 시 필요한 게이트가 즉시 다시 계산되어야 한다.
- 대외 발간 버튼은 책임 임원 승인과 법무·공시 검토가 모두 완료되기 전 disabled 상태와 사유를 함께 표시한다.
- 정정·회수는 원문을 덮어쓰지 않고 발간 이력 타임라인에서 새 상태로 추가한다.

### 5.4 Operate

#### `/operate/workspace`

- 좌: 부서/상태/유형 필터.
- 중앙: 프로그램·릴리스 목록.
- 우: 선택 자산 상세와 공유/승격 흐름.

#### `/operate/promotions/:releaseId`

- 상단: 릴리스·소유 범위·목표 범위.
- 중앙: 5개 승격 게이트 세로 흐름.
- 우: 영향 범위·의존 대상·승인 이력.
- 하단: 신청/오너 승인/반려/승격 버튼. 현재 상태에 맞는 하나의 주 CTA만 강조.

#### `/operate/shadow/:runId`

- 좌 baseline, 우 candidate, 중앙 delta.
- 미측정 지표를 비교표 하단으로 숨기지 말고 별도 그룹으로 표시.
- 악화 항목 인지 체크는 지표와 같은 행.

### 5.5 Simulate

#### `/simulate`

- 상단 Context: 조직, 기간, 값 종류, 승인 상태.
- 경고 영역을 수치 영역보다 위에 배치.
- 중앙: 손익·현금·운영 KPI 연결 그래프.
- 하단: 계획대비실적, 시나리오, 외부동인, Backtest.

#### `/simulate/scenarios/:id`

- 좌 300: 기준선/가정.
- 중앙: 시나리오 결과 비교.
- 우 360: 영향 경로와 Atlas 설명.
- 같은 기준선이 아니면 전체 결과 위에 차단 overlay, 다시 계산 CTA 제공.

### 5.6 Knowledge

#### `/knowledge`

준비도 기반 6개 카드와 “지금 보정할 것” 목록을 제공한다. 데이터 자산 수보다 결손·오너·범위·최신성의 다음 행동을 우선한다.

#### Registry 화면 공통

- 좌 260: 유형/팩/시스템 트리.
- 중앙 상단: 자연어 질문창과 예시 질문. `의미 검색 + Graph 관계 + 계보` 사용 여부를 표시.
- 중앙 본문: 검색 의도 해석, 관계 경로, 검색·필터·표.
- 우 440: 상세 Drawer.
- Bulk 작업은 승인 가능한 사용자에게만 노출.
- 표의 필수 열: 이름, 범위, 상태, 오너, 최신성, 위험.
- 자연어 검색 결과는 `검색된 이유`, `원문 근거`, `조직 범위`, `승인 상태`, `의미 유사도`를 숨기지 않는다.
- 질문에 답할 근거가 부족하면 유사 결과를 정답처럼 제시하지 않고 “답변 불충분”과 필요한 데이터 등록 행동을 제안한다.

#### Reference Registry 특화

- 상단 4 KPI: 원본/추출가능/변환필요/검토대기.
- 필터: 지식팩, 범위, 분류, 확장자, 승인, 색인.
- 행 CTA: 상세 검토. 승인/색인은 Drawer에서 수행.
- 해시 변경 자산은 기존 승인과 다른 경고 상태로 표시.

### 5.7 Agent

#### `/agent`

- 중앙에 Agent graph.
- 좌 템플릿 목록.
- 우 선택 Agent 설정(역할, 스킬, 모델, HOTL, 비용 정책).
- 하단 Simulation/Validation panel: 그래프 유효성, 예상 호출, 모델 가용성.

#### Skill Evolution

- 제안 카드마다 실패 근거, 현재 규칙, 추가 규칙, 영향 Agent, 예상 회귀를 나란히 표시.
- 승인/반려는 카드 하단의 명확한 두 행동.

### 5.8 Administration

#### Enterprise Structure

- 기본 트리와 의미 그래프를 탭으로 구분.
- 트리는 탐색, 그래프는 소유/운영/공유/연결 관계 편집에 사용.
- 권한 상속 관계는 OPERATING_PARENT만 별도 강조.

#### Profile & Brand

- 상속 원천, 현재 해석값, 하위 override를 3열 diff로 표시.
- CI 미리보기: Top Bar, 주요 버튼, 상태색 충돌 검사.

#### Settings & Administration Console

- 상단 사용자 영역의 `환경설정·관리자`에서 진입하며 일반 업무 내비게이션과 혼합하지 않는다.
- 좌측은 `개인 / 회사·브랜드 / 사용자·권한 / AI 모델·비용 / 데이터·연계 / 보안·감사·운영` 도메인, 중앙은 설정 폼, 우측은 `Change Impact`로 고정한다.
- 개인 설정에는 `나에게만 적용`, 전사 설정에는 대상 회사·하위 상속 범위와 필요한 관리자 역할을 명시한다.
- 설정 저장 버튼은 화면 외곽이 아니라 페이지 헤더와 영향 패널 하단에 반복 배치한다. 전사 설정에서는 문구를 `저장`이 아닌 `검토 요청`으로 바꾼다.
- 브랜드 색상은 실제 Shell Preview로 즉시 확인하되 승인 전 전역 사용자에게 배포하지 않는다. CI 색과 위험·성공 상태색이 충돌하면 저장을 차단한다.
- API Key·토큰은 마스킹된 값도 재표시하지 않는다. Vault 참조, 연결 상태, 마지막 교체일만 표시하고 `교체` 행동만 제공한다.
- 권한 변경은 타 범위 자원 존재를 노출하지 않는 404 은폐, 미바인딩 거부, OPERATING_PARENT 상속 규칙을 설명하는 정책 배너를 상시 표시한다.
- AI 설정은 공급자 연결 여부뿐 아니라 모델 역할, 예상 품질, 비용 하한, 월 예산, 쿼터, Golden Benchmark를 함께 보여준다. 진행 중 Sprint에는 정책을 소급하지 않는다.
- 운영 변경은 사전검토·승인·예약 적용·감사 기록·되돌림의 5단계 상태로 표시한다.

---

## 6. 상호작용 규칙

### 6.1 선택과 문맥 동기화

화면 선택은 아래 단일 문맥으로 관리한다.

```ts
type ScreenContext = {
  enterpriseScopeId: string;
  entityMode: 'REAL' | 'VIRTUAL' | 'COMPETITOR_REFERENCE';
  domainCode?: string;
  projectId?: string;
  taskId?: string;
  releaseId?: string;
  deliveryId?: string;
  decisionCaseId?: string;
  publicationId?: string;
  scenarioId?: string;
  decisionId?: string;
  asOf?: string;
};
```

Decision Queue, Canvas, Atlas, Drawer는 이 문맥을 공유한다. 비동기 응답 적용 전 요청 시점의 scope/project와 현재 문맥이 같은지 재검증한다.

### 6.2 Loading

- 전체 화면 스피너 대신 영역별 skeleton.
- 재조회 중 기존 값은 유지하되 “갱신 중” 표시.
- 회사 문맥 변경은 데이터 혼합 위험 때문에 이전 값을 즉시 비우고 차단 skeleton 사용.

### 6.3 Empty

빈 화면은 `없음`의 이유와 다음 행동을 제공한다.

- 지식팩 없음 → `지식팩 만들기`.
- 시나리오 없음 → `상담 또는 시나리오 생성`.
- 승격 없음 → `릴리스 선택`.
- 데이터 없음 → 필요한 템플릿·오너·입력 경로 제안.

### 6.4 Error

- 사용자가 해결 가능한 오류: 원인 + 행동.
- 권한 오류: 존재 상세를 노출하지 않고 문맥/권한 요청 경로.
- 조회 실패: 0으로 대체하지 않음.
- 서버 장애: correlation ID와 재시도, 로그 전체 노출 금지.

### 6.5 Destructive/High-impact action

삭제·승격·운영 중단·계획 승인·Shadow 승격은 확인 Sheet를 사용한다.

1. 무엇이 바뀌는가.
2. 영향 받는 조직·SW·데이터.
3. 되돌릴 수 있는가.
4. 필요한 승인/근거.
5. 사유 입력.

---

## 7. Atlas UX 계약

### 7.1 시각적 계층

- Atlas는 어두운 브랜드색 rail로 본문과 구분.
- 긴급 경고에만 accent red.
- 일반 추천은 흰색/청록 outline.
- 답변 본문 14px, 근거 12px, 질문 입력 14px.

### 7.2 답변 패턴

```text
핵심 답변
왜 그렇게 판단했는가
근거와 기준시각
부족하거나 확인하지 못한 데이터
선택 가능한 다음 행동
실행 시 영향과 승인 필요 여부
```

### 7.3 실행 패턴

`추천안으로 의사결정안 작성` → 실행 초안 → 영향 분석 → 사용자 수정 → 승인 → 기존 도메인 API 호출 → 결과/실패 Ledger 기록.

Atlas가 직접 DB를 수정하거나 권한 검증을 우회하지 않는다.

---

## 8. 프론트엔드 구조 제안

### 8.1 유지할 데이터 계층

아래 파일은 표현과 분리되어 있으므로 우선 재사용한다.

- `lib/advisorApi.ts`
- `lib/briefingApi.ts`
- `lib/planningApi.ts`
- `lib/workspaceApi.ts`
- `lib/shadowApi.ts`
- `lib/programApi.ts`
- `lib/governanceApi.ts`
- `lib/qualityApi.ts`
- `store/useFactoryStore.ts`의 Factory/SSE 상태

### 8.2 목표 컴포넌트 구조

```text
frontend/src/
  app/
    AppShell.tsx
    routes.tsx
    context/EnterpriseContextProvider.tsx
    context/ScreenContextProvider.tsx
  features/
    enterprise/
    build/
    collaboration/
    operate/
    simulate/
    knowledge/
    agent/
    admin/
    atlas/
  components/
    foundation/
    feedback/
    data-display/
    decision/
  lib/
    기존 API 클라이언트
```

한 번에 전체 파일을 이동하지 않는다. 새 Shell에서 기존 패널을 adapter route로 연결한 뒤 화면별로 교체한다.

### 8.3 신규 상태

- `enterpriseContextStore`: tenant/scope/entityMode/theme/profile.
- `screenContextStore`: 선택 domain/project/release/scenario/decision.
- `enterpriseCanvasQuery`: Aggregate read model.
- `atlasSessionStore`: 질문/근거/실행 초안.
- `collaborationQuery`: 수신함·보낸 요청·내 앱·결정 큐·발간 목록의 서버 상태.
- `collaborationDraftStore`: 전달 Wizard, 회의 요청, 발간 검토의 미저장 입력만 보관.

기존 Factory store와 분리해 프로젝트 SSE 이벤트가 회사 전역 화면 전체를 불필요하게 재렌더링하지 않게 한다.

---

## 9. 접근성·반응형·성능

### 9.1 접근성

- WCAG AA, 텍스트 대비 4.5:1 이상.
- 모든 버튼과 노드 키보드 탐색 가능.
- focus ring 제거 금지.
- 상태 아이콘에 텍스트 라벨 제공.
- Canvas 관계를 표/목록 대체보기로 제공.
- motion reduce 환경에서 노드·SSE 애니메이션 최소화.

### 9.2 반응형

| 너비 | 동작 |
|---|---|
| 1600+ | 3열 전체 표시 |
| 1280~1599 | 좌 260/우 320, 중앙 유동 |
| 1024~1279 | Decision Queue 또는 Atlas를 drawer로 전환 |
| 768~1023 | 읽기·승인 중심 태블릿, Canvas를 세로 단계 목록으로 전환 |
| <768 | 브리핑·알림·간단 승인만 지원, 설계/그래프 편집 비권장 |

### 9.3 성능

- 전사 Canvas는 대형 원본 state/code를 받지 않고 요약 Read Model만 사용.
- SSE payload는 식별자·상태 위주, 상세는 필요 시 조회.
- Timeline 로그 500건 제한과 virtualization.
- Markdown/그래프/Preview는 선택 탭만 렌더.
- Mega 하위 상태는 `Promise.all`과 변경 비교 후 store 반영.
- 회사 문맥별 query cache key를 분리.

---

## 10. 구현 단계와 UI 검증

### 단계 1 · 디자인 토큰과 Shell

- 토큰, typography, buttons, badges, banners, drawers.
- CompanyContextBar와 8개 전역 메뉴.
- 기존 화면 adapter route.

### 단계 2 · Enterprise Read-only Canary

- Briefing 기반 Decision Queue.
- 정적/집계 Domain Node.
- Trust Foundation 요약.
- Atlas 자리와 기존 프로젝트 Supervisor Chat adapter.

### 단계 3 · Build SW 전환

- Advisor, Portfolio, Production Workspace, HOTL, Release.
- 기존 기능 회귀 비교.

### 단계 3A · Collaboration 폐쇄루프

- App-in-App 생성 계약·Capability Manifest·정적 금지 규칙을 Release Studio에 연결.
- 개인 전달·수신 승인·내 앱과 조직 공유·승격을 분리 구현.
- Decision Package 한 건에서 세 관점 검토·회의·결정·실행과제를 렌더.
- 대내외 발간 게이트·배포·정정·회수와 Jarvis 문맥 연결.

### 단계 4 · Operate/Simulate 전환

- 승격/운영준비/Program/Shadow.
- 경영계획 4개 화면.

### 단계 5 · Knowledge/Agent/Admin 전환

- Registry shell 공통화.
- Reference approval/indexing UI는 백엔드 계약 구현 후 활성화.
- 회사 브랜드 설정.

### 단계 6 · Atlas/Canvas 정식 전환

- 전역 API와 근거 계약.
- 기존 Launcher를 fallback route로 1개 릴리스 유지.
- 사용자 과업 테스트 통과 후 기본 route 변경.

---

## 11. 시각·기능 검수 체크리스트

### 공통

- [ ] 화면 제목과 현재 회사 문맥이 항상 보이는가.
- [ ] 12px 미만의 업무 텍스트가 없는가.
- [ ] 가장 중요한 행동이 문제·영향과 같은 시야에 있는가.
- [ ] 상태를 색만으로 표현하지 않는가.
- [ ] 빈 값과 0, 미측정과 정상, 미기록과 승인을 구분하는가.
- [ ] 회사 문맥 전환 후 이전 데이터가 남지 않는가.

### Enterprise

- [ ] 의사결정 큐와 중앙 노드·Atlas가 동기화되는가.
- [ ] DATA/SW/TWIN의 연결 대상이 실제 API 근거를 가지는가.
- [ ] Aggregate 일부 실패가 상단에 노출되는가.

### Build SW

- [ ] 인터뷰 질문·추천·사용자 선택이 명확한가.
- [ ] Workflow 단계가 실제 graph와 일치하는가.
- [ ] HOTL·Quota·빌드 실패·SSE 끊김이 종료 없는 대기로 보이지 않는가.
- [ ] 기존 Preview·Traceability·품질 탭이 보존되는가.

### Collaboration

- [ ] 지정 사용자 전달과 조직 공유·전사 승격을 다른 상태·화면으로 구분하는가.
- [ ] 생성 앱이 별도 로그인·사용자·토큰을 만들지 않고 플랫폼 권한을 상속하는가.
- [ ] 앱 수락이 데이터 권한을 자동 확대하지 않는가.
- [ ] 수락·거절·회수·중복 수락이 멱등적이고 감사 가능한가.
- [ ] 세 관점 검토가 동일 Decision Package와 근거 스냅샷을 가리키는가.
- [ ] 회의·결정·실행과제·효과측정이 한 타임라인으로 이어지는가.
- [ ] 대외 발간이 책임 임원 승인과 법무·공시 검토 전 차단되는가.
- [ ] Jarvis가 선택 앱·결정·발간 문맥을 Task ID 없이 인계받는가.

### Operate

- [ ] `unverifiable` 승격이 차단되는가.
- [ ] 데이터 오너 승인과 일반 사용자 승인이 구분되는가.
- [ ] 프로그램 삭제 대신 상태·대체·영향을 관리하는가.

### Simulate

- [ ] PLAN/ACTUAL/FORECAST/SCENARIO가 섞이지 않는가.
- [ ] 기준선 불일치와 승인 후 변경을 숫자보다 먼저 경고하는가.
- [ ] 현금흐름 계산 불가와 0을 구분하는가.

### Knowledge

- [ ] 원본자료가 승인 전에 자동 색인되지 않는가.
- [ ] 조직 범위·오너·분류·최신성이 목록에서 보이는가.
- [ ] Connector→Contract→Crosswalk→MCP 순서가 드러나는가.

### Atlas

- [ ] Task ID 없이 현재 회사 범위 질문이 가능한가.
- [ ] 근거·가정·부족 데이터를 분리해서 보여주는가.
- [ ] 쓰기 행동이 HOTL 없이 실행되지 않는가.
