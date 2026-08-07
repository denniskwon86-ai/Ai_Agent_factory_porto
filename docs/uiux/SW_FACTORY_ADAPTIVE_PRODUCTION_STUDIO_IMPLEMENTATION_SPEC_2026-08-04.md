# SW Factory · Adaptive Production Studio 구현 명세

> 상태: **Supervisor 채택 확정**
> 확정일: 2026-08-04
> 시각 기준: `uiux-prototypes/sw-factory-concepts/adaptive-production-studio/`
> 대체 대상: Concept D의 영구 3열 통제 구조와 기존 `ControlPanel / TimelinePanel / PreviewPanel` 단순 병렬 배치
> 구현 시점: UI 이관 Wave 4 · 기존 데이터/권한 화면 이관과 충돌하지 않는 시점
> **실제 React 구현 담당: Claude Code**
> **UI/UX 감사 담당: Codex**
> **최종 제품 확인: Supervisor**

## 0. 구현 지시

이 문서는 아이디어·후보안·참고 시안이 아니라 **Supervisor가 확정한 실제 Factory React 구현 명세**다. Claude Code는 UI 이관 Wave 4에서 Concept E를 제품 코드로 구현한다.

- Concept A~D와 기존 3패널은 비교·회귀 기준일 뿐 최종 구현 선택지가 아니다.
- 구현 편의를 이유로 전체 제작 단계, WBS, 사용자 결정, Jarvis, 실행 앱 미리보기 중 하나를 제거하지 않는다.
- 기존 기능을 먼저 삭제한 뒤 다시 만드는 방식은 금지한다. 신규 Studio를 병행 카나리로 연결하고 기능 동등성을 확인한 후 전환한다.
- 실제 API·SSE·HOTL·artifact state를 연결한다. 프로토타입의 예시 데이터나 하드코딩된 단계로 완료 처리하지 않는다.
- 구현 완료 선언 전 Codex 시각 감사와 Supervisor 확인을 받아야 한다.

## 1. 제품 목적

Adaptive Production Studio는 현업 사용자가 필요한 SW를 직접 만들되, AI가 무엇을 했는지 숨기지 않는 제작 작업공간이다. 사용자는 한 화면에서 다음 질문에 답할 수 있어야 한다.

1. 무엇을 만들고 있는가?
2. 전체 제작 과정 중 어디까지 왔는가?
3. 현재 어떤 WBS와 Agent가 일하고 있는가?
4. 사용자가 지금 결정해야 할 것은 무엇인가?
5. 생성된 SW가 실제로 어떻게 동작하는가?
6. 다음 자동 전환과 차단 사유는 무엇인가?

코드와 로그는 중요하지만 기본 결과가 아니다. **기본 산출물은 실행 가능한 App-in-App SW**이며 코드·테스트·API 계약·설계 문서는 전문 검토용 보조 산출물이다.

## 2. 확정 공간 구조

### 2.1 상시 노출

- Global Product Shell: 회사·조직·프로젝트 문맥, 경영 홈 복귀, 현재 사용자.
- Project Header: 프로젝트명, 실행/중지 상태, WBS 완료, 사용자 결정, 누적 LLM 비용, 일시정지·현재 결과 검토.
- Production Stage Map: 실제 registry/graph 순서와 완료·진행·승인대기·재작업·실패·차단 상태.
- WBS Spine: 작업, 선후행 의존관계, Agent, 완료·진행·차단 이유.

### 2.2 단계별 Adaptive Canvas

| 단계 | 중앙 기본 화면 | 보조 검토 |
|---|---|---|
| 요구 확인 | 선택형 질문, 추천 이유, 답변 준비도, 권장 데이터 | 원문 요구와 답변 이력 |
| RFP | RFP 본문, 변경점, 사용자 승인 | 요구 추적성과 누락 조건 |
| 기획/PRD | 기능·업무 흐름·수용 기준 | RFP 대비 Diff |
| 아키텍처/UI | 구조도, 데이터 계약, UI 흐름, 주요 결정 | 영향 분석과 승인 이력 |
| WBS | 작업 분해, 의존관계, Agent 배정, 일정 | 재분할·잠금·차단 사유 |
| 구현 | **생성 SW 실행 미리보기** | 요구 충족 검토, 구현 상세 |
| 검증 | 테스트, 품질 게이트, 결함과 수정 전후 | 결정론적 근거·로그 |
| Release | 버전, 사용자 전달, 권한 Manifest, 릴리스 노트 | Export·회수·롤백 |

### 2.3 하단 Interaction Dock

- 사용자 결정이 1건 이상이면 `Decision Dock`을 Jarvis 위에 표시한다.
- 결정 설명, 미결정 영향, 검토 행동을 같은 시야에 둔다.
- 결정이 0건이면 Decision Dock을 완전히 접고 확보된 높이를 Canvas에 반환한다.
- Jarvis는 하나만 제공한다. 별도 영구 우측 Jarvis Rail과 중복하지 않는다.
- 긴 대화는 Drawer로 확장할 수 있으나 Task ID를 요구하지 않고 회사·프로젝트·현재 단계·WBS·선택 산출물 문맥을 자동 인계한다.

### 2.4 근거·상태 Inspector

- 기존 영구 우측 상태 열은 제거한다.
- `근거·상태` 또는 `의존관계 보기`를 눌렀을 때 우측 오버레이 Inspector로 연다.
- 현재 작업 이유, 입력 근거, 다음 자동 전환, 최근 Agent 이벤트, 실패·복구 이력을 제공한다.
- Inspector는 Canvas 너비를 영구 축소하지 않고 열고 닫아도 선택 문맥과 스크롤 위치를 유지한다.

## 3. 생성 SW 결과 계약

### 3.1 기본 우선순위

1. 실행 앱
2. 사용자 검토
3. 보고서 결과물
4. 구현 상세: 코드·API·테스트·Diff

### 3.2 실행 앱

- `PreviewPanel`의 iframe/postMessage 격리 계약을 재사용한다.
- 플랫폼 SSO, 회사/조직 범위, 감사로그, App-in-App Capability Manifest를 상속한다.
- 생성 앱 내부에 로그인·회원가입·독자 권한관리 화면을 만들지 않는다.
- 실제 API 연결 전에는 샘플/Mock 상태와 실데이터 연결 대기를 명확히 표시한다.
- `새 창에서 실행`은 동일 격리 런타임을 확대하며 별도 인증 체계를 만들지 않는다.

### 3.3 사용자 검토

- RFP/PRD 요구별 충족·부분 충족·미구현 상태.
- 수치 표현, 업무 동선, 조직 권한, 데이터 출처를 사용자 언어로 검토.
- 검토 의견은 현재 WBS와 Reviewer 피드백으로 연결하되 자동 승인으로 취급하지 않는다.

### 3.4 보고서 산출물

- SW와 별도 결과 유형으로 취급한다.
- 실제 페이지 비율의 문서 Viewer, 목차, 근거, 버전, 검토 의견을 제공한다.
- Markdown/JSON 원문을 기본 화면에 그대로 노출하지 않는다.

### 3.5 구현 상세

- 생성 파일, 테스트, API 계약, 품질 게이트, Diff, 전체 로그.
- 일반 현업 사용자의 기본 탭으로 선택하지 않는다.
- 상태는 `생성됨`, `검증 중`, `검토 필요`, `검증됨`, `실패`로 구분하며 조회 실패를 0건으로 표시하지 않는다.

## 4. 현재 React 자산 이식 매핑

| 기존 자산 | 목표 컴포넌트 | 이식 원칙 |
|---|---|---|
| `WorkflowStrip.tsx` | `ProductionStageMap` | registry/실제 state 기반, 하드코딩 금지 |
| `ControlPanel.tsx` 요구·제어 | `AdaptivePhaseCanvas` + Project Header | 단계별로 기능 분해, API 계약 유지 |
| `ControlPanel.tsx` WBS | `WbsSpine` | 의존관계·Agent·차단 이유 보강 |
| `TimelinePanel.tsx` | `ContextInspector` | 최근 이벤트·원인·전환을 요청 시 표시 |
| `PreviewPanel.tsx` | `GeneratedAppRuntime` | 구현 단계 기본 Canvas로 승격 |
| `HOTLInput.tsx` | `DecisionDock` | 결정 0건이면 완전 접힘 |
| Supervisor Chat | `JarvisDock` + 확장 Drawer | Task ID 선택 요구 제거 |
| Store SSE 처리 | stage/WBS/Inspector selectors | 전체 store 구독과 중복 렌더 방지 |

권장 신규 경계:

- `frontend/src/factory/AdaptiveProductionStudio.tsx`
- `frontend/src/factory/ProductionStageMap.tsx`
- `frontend/src/factory/WbsSpine.tsx`
- `frontend/src/factory/AdaptivePhaseCanvas.tsx`
- `frontend/src/factory/GeneratedAppRuntime.tsx`
- `frontend/src/factory/DecisionJarvisDock.tsx`
- `frontend/src/factory/ContextInspector.tsx`
- `frontend/src/factory/factoryViewModel.ts`

기존 컴포넌트를 한 번에 삭제하지 않는다. 신규 Studio가 같은 API·SSE 상태를 읽는 병행 카나리로 들어간 뒤 기능 회귀가 없을 때 기존 3패널을 제거한다.

## 5. 상태 ViewModel

```ts
type FactoryStageStatus =
  | 'waiting' | 'running' | 'decision_required' | 'completed'
  | 'reworking' | 'failed' | 'blocked' | 'stopped'

interface FactoryStudioViewModel {
  project: { id: string; name: string; mode: string; cost: number | null }
  stages: Array<{ id: string; label: string; status: FactoryStageStatus; summary: string }>
  selectedStageId: string
  currentStageId: string
  wbs: Array<{ id: string; title: string; status: string; agent?: string; blockedBy?: string[] }>
  selectedWbsId?: string
  decisions: Array<{ id: string; prompt: string; impact: string; options: unknown[] }>
  artifacts: Array<{ id: string; type: 'app'|'report'|'document'|'code'|'test'|'api'; status: string }>
  events: Array<{ at: string; actor: string; event: string; reason?: string }>
  connection: 'connected'|'reconnecting'|'offline'
  loadState: 'loading'|'ready'|'empty'|'forbidden'|'error'
}
```

- `selectedStageId`와 `currentStageId`를 분리한다. 과거 단계를 탐색해도 실제 현재 실행 단계가 바뀐 것처럼 보이면 안 된다.
- 비동기 결과를 적용하기 전에 요청 시점의 project/company/organization과 현재 문맥이 같은지 재검증한다.
- 실패·권한없음·빈 상태·계산 전을 서로 다른 상태로 유지한다.

## 6. 시각·접근성 계약

- 제품 업무 표면은 라이트, Global Header와 생성 앱 내부 역할 레일만 LS Navy를 사용한다.
- 전체 단계와 WBS를 넓은 다크 블록으로 만들지 않는다.
- Red는 현재 진행·사용자 결정·위험 행동 등 핵심 신호에 제한한다.
- 1280px 이상: WBS 238px, Canvas 가변. 영구 우측 열 없음.
- 1280×720에서 Decision+Jarvis Dock은 약 126~180px, 앱 프레임은 Dock과 겹치지 않는다.
- 가시 텍스트 최소 12px, 주요 제목 14px 이상.
- 키보드로 단계, WBS, 실행/검토/구현 상세, 결정, Jarvis, Inspector에 도달한다.
- 상태를 색상만으로 표현하지 않고 텍스트와 아이콘을 함께 사용한다.

## 7. 구현 순서

1. 현재 Factory API/SSE를 읽는 `factoryViewModel` 작성.
2. Production Stage Map과 WBS Spine을 기존 화면과 병행 렌더.
3. Adaptive Canvas에 요구 확인과 구현/실행 두 극단 상태를 먼저 연결.
4. Decision/Jarvis Dock 연결.
5. Context Inspector로 Timeline과 근거 이식.
6. RFP·기획·아키텍처·WBS·검증·Release Canvas 순차 이식.
7. 기능 회귀·시각 게이트 통과 후 기존 3패널 제거.

## 8. 완료 게이트

### 기능

- Sprint 시작·일시정지·정지·재개·복구·재분할·Release·Export가 보존된다.
- HOTL 질문·승인·수정 요구가 보존된다.
- SSE 재연결과 REST 최신 상태 복구가 보존된다.
- 앱·보고서·코드·테스트·추적성 산출물을 모두 열 수 있다.

### 신뢰성

- 실패를 실행 중으로, 조회 실패를 0건으로 표시하지 않는다.
- Jarvis가 권한 없는 행동을 가능하다고 안내하지 않는다.
- 타 조직 자원은 서버 404 은폐 계약을 유지한다.
- App-in-App은 Host 권한을 상속하고 독자 로그인 기능을 만들지 않는다.

### 시각

- 1280×720·1440×900 가로 넘침 0.
- Canvas와 Decision/Jarvis Dock 겹침 0.
- 12px 미만 가시 텍스트 0.
- 요구 확인·구현·결정 있음/없음·오류·오프라인·복구 실패 화면을 실제 캡처로 검토한다.

### 전환

- 신규 Studio 병행 카나리에서 기존 화면과 동일 프로젝트 상태를 비교한다.
- 기능 누락, 상태 불일치, 작업 보호 실패가 0건일 때만 기본 route로 승격한다.
- 승격 전 기존 3패널은 즉시 되돌릴 수 있게 유지한다.

## 9. 프로토타입 검증 증거

- 1280×720: 가로 넘침 0, 생성 앱과 Decision/Jarvis Dock 겹침 0.
- 1440×900: 가로 넘침 0, 겹침 0.
- 요구 확인 ↔ 구현 단계 문맥 전환 확인.
- 실행 ↔ 검토 ↔ 구현 상세 전환 확인.
- 근거·상태 Inspector 열기/닫기 확인.
- 브라우저 콘솔 오류 0.

프로토타입의 회사명·프로젝트명·수치·파일명은 디자인 검토용 예시 데이터다. 실제 구현은 현재 프로젝트 state, artifact index, WBS, 권한, 텔레메트리를 사용한다.
