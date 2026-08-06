/**
 * [트랙 E · 1단계] Adaptive Production Studio 의 상태 ViewModel.
 *
 * 근거: `docs/uiux/SW_FACTORY_ADAPTIVE_PRODUCTION_STUDIO_IMPLEMENTATION_SPEC_2026-08-04.md`
 *       §5 상태 ViewModel · §4 이식 매핑 · §7 구현 순서 1단계.
 *
 * ## 이 파일의 불변식
 *
 * 1. **기존 화면을 건드리지 않는다.** 신규 Studio 는 같은 API·SSE 상태를 읽는 **병행 카나리**로
 *    들어간다(§4 마지막 문단). 그래서 여기서는 store 를 **읽기만** 하고 어떤 액션도 부르지 않는다.
 * 2. **`selectedStageId` 와 `currentStageId` 는 다르다.** 과거 단계를 눌러 봐도 실제 실행 단계가
 *    바뀐 것처럼 보이면 안 된다(§5). 그래서 선택은 호출자가 넘기는 값이고, 현재 단계는 서버
 *    상태에서만 파생한다.
 * 3. **실패·권한없음·빈 상태·계산 전을 서로 다른 상태로 유지한다**(§5, §8 신뢰성).
 *    - `loading`   : 아직 안 왔다
 *    - `forbidden` : 권한이 없어 못 읽었다
 *    - `error`     : 읽으려 했는데 실패했다
 *    - `empty`     : 정상적으로 읽었고 내용이 없다
 *    - `ready`     : 내용이 있다
 *    ⚠️ 이 넷을 «0건» 하나로 합치면 §8 의 「조회 실패를 0건으로 표시하지 않는다」를 어긴다.
 * 4. **단계 목록을 하드코딩하지 않는다**(§4 `WorkflowStrip` → `ProductionStageMap` 행:
 *    «registry/실제 state 기반, 하드코딩 금지»). 그래서 레지스트리·템플릿이 없으면 단계를
 *    **비워 두고 그 이유를 `loadState` 로 말한다.** 기본 14단계를 그려 넣으면 커스텀 템플릿에서
 *    그 그림이 거짓이 되고, 사용자는 있지도 않은 단계를 기다린다.
 *
 * ## 왜 순수 함수인가
 *
 * `buildFactoryViewModel` 은 스냅샷을 받아 값을 만드는 순수 함수다. 프론트엔드에 테스트 러너가
 * 없으므로(package.json 에 vitest/jest 가 없다) 지금은 타입체크와 브라우저 확인으로만 검증한다.
 * 순수 함수로 두면 러너를 들이는 순간 그대로 테스트할 수 있고, 그때까지도 파생 규칙이 한곳에
 * 모여 있어 화면마다 다르게 계산되는 일이 없다.
 */
import { useMemo } from 'react';

// 용어 사전은 `design/terms.ts` 하나다 — 단계명을 여기서 다시 적으면 두 벌이 된다.
import { STAGE_KO } from '../design/terms';
import { useFactoryStore } from '../store/useFactoryStore';

import type { ProjectState } from '../store/useFactoryStore';

export type FactoryStageStatus =
  | 'waiting' | 'running' | 'decision_required' | 'completed'
  | 'reworking' | 'failed' | 'blocked' | 'stopped';

export type FactoryLoadState = 'loading' | 'ready' | 'empty' | 'forbidden' | 'error';

export type FactoryConnection = 'connected' | 'reconnecting' | 'offline';

export type FactoryArtifactType = 'app' | 'report' | 'document' | 'code' | 'test' | 'api';

export interface FactoryStageVm {
  id: string;
  label: string;
  status: FactoryStageStatus;
  summary: string;
  /** 이 단계를 맡은 에이전트의 표시 이름들. **여러 명일 수 있다** — `EXECUTION` 은 백엔드·
   *  프론트엔드가 함께 쓴다. 라벨을 한 명 이름으로 두면 나머지가 화면에서 사라진다. */
  agents: string[];
}

/** 작업 하나의 진행 종류. **판정은 ViewModel 에서만 한다** — 아래 `isTaskDone` 참조. */
export type FactoryWbsKind = 'done' | 'active' | 'blocked' | 'waiting';

export interface FactoryWbsVm {
  id: string;
  title: string;
  status: string;
  /** ★★★ [2026-08-06 실측 결함] 종전에는 `WbsSpine` 이 `status` 를 보고 종류를 정하고
   *  ViewModel 이 `blockedBy` 를 따로 계산했다. **두 판정이 갈라졌다** — ViewModel 은
   *  `'COMPLETED'` 만 완료로 봤고 실제 데이터는 `'DONE'` 이었다. 그래서 완료된 작업과
   *  **진행 중인 작업까지 「차단」으로** 표시됐다(화면에 「진행 0 · 차단 3」이 떴는데 실제로는
   *  진행 1 · 차단 1 이었다). 그래서 종류를 여기서 한 번만 정한다. */
  kind: FactoryWbsKind;
  agent?: string;
  blockedBy?: string[];
}

/** 완료 판정 — **이 함수 하나만 쓴다.** 서버가 `DONE`·`COMPLETED` 를 섞어 쓴다(실측).
 *  ⚠️ 모르는 값을 «완료» 로 떨어뜨리지 않는다. 그쪽으로 틀리면 안 끝난 일이 끝난 것으로 보인다. */
export function isTaskDone(status: unknown): boolean {
  const s = String(status ?? '').trim().toUpperCase();
  return s === 'COMPLETED' || s === 'DONE';
}

/** 진행 중 판정 — 서버 표기 차이를 한곳에서 흡수한다. */
function isTaskActive(status: unknown): boolean {
  const s = String(status ?? '').trim().toUpperCase();
  return s === 'IN_PROGRESS' || s === 'RUNNING' || s === 'ACTIVE';
}

export interface FactoryDecisionVm {
  id: string;
  prompt: string;
  impact: string;
  options: unknown[];
}

export interface FactoryArtifactVm {
  id: string;
  type: FactoryArtifactType;
  status: string;
}

export interface FactoryEventVm {
  at: string;
  actor: string;
  event: string;
  reason?: string;
}

/** [3단계] 요구 확인 단계의 선택형 질문 하나. 서버 `state.clarification_questions` 에서 온다. */
export interface FactoryClarifyQuestionVm {
  id: string;
  question: string;
  /** 여러 개를 고를 수 있는 질문인가. */
  multi: boolean;
  options: { label: string; description: string; recommended: boolean }[];
}

/** [3단계] 요구 확인 Canvas 의 재료. */
export interface FactoryClarifyVm {
  /** 지금 사람이 답해야 하는 상태인가(단계가 CLARIFICATION 이고 질문이 있고 아직 요약이 없다). */
  awaiting: boolean;
  questions: FactoryClarifyQuestionVm[];
  /** 답변이 반영된 뒤 서버가 만든 요약. 있으면 이 단계는 지나간 것이다. */
  summary: string;
  /** 사용자가 처음 적어 넣은 한 줄. 질문의 «무엇을 기준으로 추천했는가» 근거다. */
  initialIdea: string;
}

/** [3단계] 구현 단계 Canvas — 생성 SW 실행 미리보기의 재료. */
export interface FactoryGeneratedAppVm {
  /** 생성된 프론트엔드 코드 원문. 비어 있으면 아직 만들어진 앱이 없다. */
  rawCode: string;
  /** 실행할 것이 있는가. `rawCode` 유무와 같지만 화면이 그 판정을 다시 하지 않게 여기서 정한다. */
  runnable: boolean;
  /** 지금 만들고 있는가(스프린트 진행 중). «없다» 와 «아직» 을 구분하는 데 쓴다. */
  building: boolean;
}

export interface FactoryStudioViewModel {
  project: { id: string; name: string; mode: string; cost: number | null };
  stages: FactoryStageVm[];
  /** 사용자가 보고 있는 단계. 비어 있으면 «현재 단계를 보고 있다». */
  selectedStageId: string;
  /** 서버 상태가 말하는 실제 실행 단계. **선택과 절대 섞지 않는다.** */
  currentStageId: string;
  wbs: FactoryWbsVm[];
  selectedWbsId?: string;
  decisions: FactoryDecisionVm[];
  artifacts: FactoryArtifactVm[];
  events: FactoryEventVm[];
  connection: FactoryConnection;
  loadState: FactoryLoadState;
  /** `loadState` 가 `ready`·`empty` 가 아닐 때 사람에게 보여줄 이유. 비면 이유를 모른다. */
  loadReason: string;
  /** 단계 목록을 만들 근거(레지스트리/템플릿)를 갖고 있는가. 없으면 `stages` 는 비어 있다. */
  stageSourceKnown: boolean;
  /** [3단계] 요구 확인 Canvas 재료. */
  clarify: FactoryClarifyVm;
  /** [3단계] 구현 Canvas 재료. */
  generated: FactoryGeneratedAppVm;
  /** [5단계] Inspector 재료 — 근거·상태. */
  inspect: FactoryInspectVm;
  /** [6단계] 단계별 산출물 문서. 키는 stage id. **없는 단계는 키가 없다** — 빈 문자열을 넣으면
   *  «만들어졌는데 비었다» 와 «아직 없다» 가 구분되지 않는다. */
  docs: Record<string, FactoryStageDocVm>;
  /** [6단계] 릴리스 목록(Release Canvas). */
  releases: { id: string; status: string; at: string }[];
}

/** [6단계] 한 단계가 내놓은 산출물. */
export interface FactoryStageDocVm {
  /** 문서 본문(마크다운). 비어 있으면 아직 만들어지지 않았다. */
  text: string;
  /** 판정이 있는 단계만 채운다(QA·수용검수의 PASS/FAIL). 없으면 빈 문자열. */
  verdict: string;
}

/** [5단계] 근거·상태 Inspector 의 재료(명세 §2.4). */
export interface FactoryInspectVm {
  /** 순서상 **다음 단계**. 「다음 자동 전환」의 사실 부분이다.
   *  ⚠️ «전환 조건» 은 서버 로직이고 화면이 알 수 없다 — 그래서 조건은 만들지 않는다. */
  nextStage: { id: string; label: string } | null;
  /** 지금 막혀 있는 작업과 그 이유. 「현재 작업 이유」를 사실로 말할 수 있는 유일한 근거다. */
  blocked: { id: string; title: string; blockedBy: string[] }[];
  /** 마지막 스프린트 실패. 없으면 `null` — «실패 0» 과 «실패 기록이 없다» 를 구분한다. */
  failure: { taskId: string; error: string; detail: string } | null;
  /** 자가복구 재시도 횟수. 0 이면 복구를 시도하지 않았다는 **사실**이다. */
  healingRetries: number;
  /** 쿼터로 동결된 작업. 사용자가 «왜 멈췄나» 를 여기서 안다. */
  suspendedTaskId: string;
}

/** `buildFactoryViewModel` 에 넘기는 store 스냅샷. store 타입에 의존하지 않게 **좁게** 받는다. */
export interface FactorySnapshot {
  state: ProjectState | null;
  currentProjectId: string | null;
  isConnected: boolean;
  completed_agents: string[];
  activeSprintId: string | null;
  hotlTaskId: string | null;
  currentTemplateData: any | null;
  agentRegistry: any | null;
  agentRegistryError: string;
  wbsData: any;
  isWbsError: boolean;
  logs: any[];
  supervisorFeed: any[];
  releases: any[];
  lastSprintFailure: { taskId: string; error: string; detail?: string } | null;
  isSuspendedQuota: boolean;
  suspendedTaskId: string | null;
  /** [5단계] 자가복구 재시도 횟수. Inspector 의 «실패·복구 이력» 에 쓴다. */
  healingRetryCount: number;
}

export interface FactoryViewModelOptions {
  /** 사용자가 고른 단계. 넘기지 않으면 «현재 단계를 본다». */
  selectedStageId?: string;
  selectedWbsId?: string;
}

/** 레지스트리·템플릿에서 뽑은 단계 정의(라벨과 담당 에이전트). */
interface StageDef {
  id: string;
  label: string;
  /** 상태 판정용 — 에이전트 **id** 소문자(서버의 `completed_agents` 와 맞춘다). */
  agents: string[];
  /** 표시용 — 에이전트의 사람 이름. 판정에 쓰지 않는다(이름은 바뀔 수 있다). */
  who: string[];
}

/**
 * 단계 정의를 **데이터에서** 만든다. 순서는 `order` 를 따르고, 없으면 배열 순서를 쓴다.
 *
 * ⚠️ 여기서 기본 흐름을 만들어 넣지 않는다. `null` 은 «모른다» 이고, 화면은 그 사실을 말해야 한다.
 *   `WorkflowStrip` 은 14단계를 파일에 적어 두었는데, 그것은 커스텀 템플릿에서 실제 흐름과
 *   달라진다(그 컴포넌트도 템플릿이 있으면 덮어쓴다 — 즉 하드코딩은 폴백일 뿐이었다).
 */
function stageDefsFrom(templateData: any | null, registry: any | null): StageDef[] | null {
  const src = pickAgentSource(templateData, registry);
  if (!src) return null;
  const agents = [...src].sort((a: any, b: any) => (a?.order ?? 0) - (b?.order ?? 0));
  const defs: StageDef[] = [];
  for (const a of agents) {
    if (!a || typeof a !== 'object') continue;
    if (a.enabled === false) continue;          // 꺼진 에이전트는 흐름에 없다
    const rawId = String(a.id ?? '').trim();
    if (!rawId) continue;
    const stageId = String(a.stage ?? '').trim() || rawId.toUpperCase();
    const who = String(a.name_ko ?? a.name ?? rawId).trim();
    // ★ [2026-08-06 실측] 라벨을 에이전트 이름으로 두면 **한 단계에 여러 에이전트가 있을 때
    //   나머지가 사라진다.** `EXECUTION` 은 백엔드·프론트엔드가 함께 쓰는데 화면에는 「백엔드
    //   개발자」만 나왔다 — 프론트엔드가 그 단계에 없는 것처럼 보인다.
    //   → 단계명은 용어 사전(`STAGE_KO`)에서, 담당 에이전트는 부가 정보로 따로 준다.
    // ⚠️ `stageKo()` 를 쓰지 않는다. 그 함수는 사전에 없는 값에 `console.error` 를 내는데,
    //   커스텀 템플릿의 낯선 stage 는 «오류» 가 아니라 정상이다(그때는 에이전트 이름을 쓴다).
    const label = STAGE_KO[stageId] || who;
    const found = defs.find((d) => d.id === stageId);
    if (found) {
      // 한 단계를 여러 에이전트가 공유한다(예: backend·frontend 가 모두 EXECUTION).
      found.agents.push(rawId.toLowerCase());
      found.who.push(who);
    } else {
      defs.push({ id: stageId, label, agents: [rawId.toLowerCase()], who: [who] });
    }
  }
  return defs.length ? defs : null;
}

function pickAgentSource(templateData: any | null, registry: any | null): any[] | null {
  const t = templateData?.agents;
  if (Array.isArray(t) && t.length) return t;
  const r = registry?.agents;
  if (Array.isArray(r) && r.length) return r;
  return null;
}

/**
 * 한 단계의 상태를 정한다. **색이 아니라 사실에서** 나온다(§6: 색상만으로 표현하지 않는다 —
 * 그러려면 상태값 자체가 텍스트로 말할 수 있어야 한다).
 *
 * 우선순위가 중요하다. «결정 대기» 는 «실행 중» 보다 위다 — 사람이 손을 대야 멈춘 것이고,
 * 그것을 «돌고 있음» 으로 보이면 사용자는 기다리기만 한다.
 */
function stageStatus(
  def: StageDef,
  ctx: {
    completed: string[];
    scores: Record<string, number>;
    currentStage: string;
    hotlAgent: string;
    running: boolean;
    needsRevision: boolean;
    failedAgent: string;
    suspended: boolean;
  },
): FactoryStageStatus {
  const isCurrent = ctx.currentStage === def.id;
  const mine = (a: string) => def.agents.includes(a);

  if (ctx.hotlAgent && mine(ctx.hotlAgent)) return 'decision_required';
  if (ctx.failedAgent && mine(ctx.failedAgent)) return 'failed';
  if (ctx.suspended && isCurrent) return 'stopped';

  const done = def.agents.some((a) => ctx.completed.includes(a)) || ctx.scores[def.id] != null;
  // 재작업은 «완료» 를 덮는다 — 한 번 끝났어도 지금 다시 하고 있으면 끝난 것이 아니다.
  if (isCurrent && ctx.needsRevision) return 'reworking';
  if (done) return 'completed';
  if (isCurrent) return ctx.running ? 'running' : 'waiting';
  return 'waiting';
}

/** 단계 요약. 채점·현재 여부처럼 **가진 사실만** 적는다. 없으면 빈 문자열이다(추측하지 않는다). */
function stageSummary(def: StageDef, scores: Record<string, number>): string {
  const score = scores[def.id];
  if (typeof score === 'number') return `평가 ${score}점`;
  return '';
}

const ARTIFACT_KIND: Array<[RegExp, FactoryArtifactType]> = [
  [/(^|_)app(_|$)|preview|runtime/i, 'app'],
  [/report|qa|review|supervisor/i, 'report'],
  [/test|spec/i, 'test'],
  [/api|openapi|swagger/i, 'api'],
  [/code|frontend|backend|build/i, 'code'],
];

/** 산출물 종류 판정. 못 알아보면 `document` 다 — **버리지 않는다**(있는 것을 안 보여주면 그게 손실이다). */
function artifactType(key: string): FactoryArtifactType {
  for (const [rx, kind] of ARTIFACT_KIND) if (rx.test(key)) return kind;
  return 'document';
}

/**
 * [3단계] 요구 확인 재료. `state` 의 세 필드를 그대로 읽는다 — 판정은 `HOTLInput` 이 이미
 * 하고 있던 것과 **같은 조건**이다(단계가 CLARIFICATION · 질문 있음 · 요약 아직 없음).
 *
 * ⚠️ 명세 §2.2 는 «답변 준비도» 와 «권장 데이터» 도 요구하지만 **그 근거가 서버 상태에 없다.**
 *   그래서 만들지 않는다 — 없는 지표를 화면에 채우면 그것이 곧 거짓이 된다. 셀 수 있는 것은
 *   질문 수뿐이고, 그것만 준다.
 */
function toClarify(st: ProjectState | null, awaitingHuman: boolean): FactoryClarifyVm {
  const raw = Array.isArray((st as any)?.clarification_questions)
    ? ((st as any).clarification_questions as any[]) : [];
  const questions: FactoryClarifyQuestionVm[] = [];
  for (const q of raw) {
    if (!q || typeof q !== 'object') continue;
    const id = String(q.id ?? '').trim();
    const question = String(q.question ?? '').trim();
    if (!id || !question) continue;
    const opts = Array.isArray(q.options) ? q.options : [];
    questions.push({
      id,
      question,
      multi: !!q.multi,
      options: opts
        .filter((o: any) => o && String(o.label ?? '').trim())
        .map((o: any) => ({
          label: String(o.label).trim(),
          description: String(o.description ?? '').trim(),
          recommended: !!o.recommended,
        })),
    });
  }
  const summary = String((st as any)?.clarification_summary || '').trim();
  return {
    awaiting: awaitingHuman && String(st?.current_stage || '') === 'CLARIFICATION'
              && questions.length > 0 && !summary,
    questions,
    summary,
    initialIdea: String(st?.initial_idea || '').trim(),
  };
}

/** [3단계] 구현 Canvas 재료. `rawCode` 는 기존 `PreviewPanel` 이 받던 것과 **같은 값**이다 —
 *  다른 소스를 쓰면 두 화면이 다른 앱을 보여 준다. */
function toGenerated(st: ProjectState | null, running: boolean): FactoryGeneratedAppVm {
  const rawCode = String(st?.frontend_code_summary || '');
  return { rawCode, runnable: !!rawCode.trim(), building: running };
}

/**
 * [6단계] 단계 id → 산출물 필드 매핑. **명세 §2.2 표를 코드로 옮긴 것**이다.
 *
 * ⚠️ 여기 없는 단계(`UI_DESIGN`·`VISION_QA`)는 **서버가 요약 필드를 주지 않는다.** 그것을
 *   빈 문서로 만들어 넣지 않는다 — 화면은 «서버가 이 단계 요약을 제공하지 않는다» 고 말해야
 *   하고, 그것과 «아직 만들어지지 않았다» 는 다른 사실이다.
 */
const STAGE_DOC_FIELDS: Record<string, { text: keyof ProjectState; verdict?: keyof ProjectState }> = {
  RFP: { text: 'rfp_summary' },
  PLANNING: { text: 'prd_summary' },
  ARCHITECTURE: { text: 'architecture_summary' },
  TECH_SPEC: { text: 'tech_spec_summary' },
  CODE_REVIEW: { text: 'code_review_report_summary' },
  QA: { text: 'qa_report_summary', verdict: 'qa_verdict' },
  SUPERVISOR: { text: 'supervisor_report_summary', verdict: 'supervisor_verdict' },
  MANUAL: { text: 'user_manual_summary' },
};

/** 단계별 산출물을 모은다. **값이 있는 단계만** 키를 만든다(위 주석 참조). */
function toDocs(st: ProjectState | null): Record<string, FactoryStageDocVm> {
  const out: Record<string, FactoryStageDocVm> = {};
  if (!st) return out;
  for (const [stage, f] of Object.entries(STAGE_DOC_FIELDS)) {
    const text = String((st as any)[f.text] ?? '').trim();
    const verdict = f.verdict ? String((st as any)[f.verdict] ?? '').trim() : '';
    // 본문도 판정도 없으면 «아직 없다» 다 — 키를 만들지 않는다.
    if (!text && !verdict) continue;
    out[stage] = { text, verdict };
  }
  return out;
}

function toEvents(logs: any[], feed: any[]): FactoryEventVm[] {
  const out: FactoryEventVm[] = [];
  for (const l of [...(logs || []), ...(feed || [])]) {
    if (!l) continue;
    if (typeof l === 'string') {
      out.push({ at: '', actor: '', event: l });
      continue;
    }
    const at = String(l.at ?? l.timestamp ?? l.time ?? '');
    const actor = String(l.actor ?? l.agent ?? l.agent_id ?? l.node ?? '');
    const event = String(l.event ?? l.message ?? l.text ?? l.status ?? '');
    if (!at && !actor && !event) continue;
    const reason = l.reason ?? l.detail ?? l.error;
    out.push({ at, actor, event, ...(reason ? { reason: String(reason) } : {}) });
  }
  // 최신이 위로. 시간 문자열이 없는 항목은 순서를 지켜 뒤에 둔다(정렬로 사라지지 않게).
  return out.sort((a, b) => (a.at && b.at ? (a.at < b.at ? 1 : a.at > b.at ? -1 : 0) : 0));
}

/**
 * 스냅샷 → ViewModel. **부작용 없음.**
 *
 * ⚠️ 호출자가 «요청 시점의 프로젝트와 지금이 같은가» 를 재검증해야 한다(§5). 이 함수는 스냅샷을
 *   그대로 파생하므로, 스냅샷 자체가 이미 낡았다면 낡은 값을 정직하게 낸다. store 의 fetch 들은
 *   `currentProjectId` 를 다시 확인해 stale 응답을 버리고 있다(`fetchWBS` 등) — 그 계약에 기댄다.
 */
export function buildFactoryViewModel(
  snap: FactorySnapshot,
  opts: FactoryViewModelOptions = {},
): FactoryStudioViewModel {
  const st = snap.state;
  const projectId = snap.currentProjectId || '';

  const defs = stageDefsFrom(snap.currentTemplateData, snap.agentRegistry);
  const completed = (snap.completed_agents || []).map((a) => String(a).toLowerCase());
  const scores = (st?.stage_scores || {}) as Record<string, number>;
  const currentStage = String(st?.current_stage || '');
  const hotlAgent = String(snap.hotlTaskId || '').toLowerCase();
  const running = !!snap.activeSprintId || !!snap.hotlTaskId;
  const failedAgent = String(snap.lastSprintFailure?.taskId || '').toLowerCase();

  const stages: FactoryStageVm[] = (defs || []).map((d) => ({
    id: d.id,
    label: d.label,
    status: stageStatus(d, {
      completed, scores, currentStage, hotlAgent, running,
      needsRevision: !!st?.needs_revision,
      failedAgent,
      suspended: !!snap.isSuspendedQuota,
    }),
    summary: stageSummary(d, scores),
    agents: d.who,
  }));

  // ── WBS ────────────────────────────────────────────────────────────────
  const rawTasks: any[] = Array.isArray(snap.wbsData?.tasks) ? snap.wbsData.tasks : [];
  const wbs: FactoryWbsVm[] = rawTasks.map((t) => {
    const deps: string[] = Array.isArray(t?.dependencies)
      ? (t.dependencies as unknown[]).map((d) => String(d))
      : [];
    // 차단 이유는 «끝나지 않은 선행 작업» 이다(§4: 의존관계·차단 이유 보강). 전부 끝났으면 차단이 아니다.
    // ⚠️ 완료 판정은 `isTaskDone` **하나만** 쓴다. 종전에는 여기서 `!== 'COMPLETED'` 로 직접
    //   비교했고 실제 데이터는 `'DONE'` 이라 **끝난 선행을 미완으로 셌다**.
    const unmet = deps.filter((d) => {
      const dep = rawTasks.find((x) => String(x?.task_id) === d);
      return !dep || !isTaskDone(dep?.status);
    });
    const agents = Array.isArray(t?.required_agents) ? t.required_agents.map(String) : [];
    // 종류를 **여기서** 정한다. 우선순위: 완료 → 진행 → 차단 → 대기.
    // «완료» 가 «차단» 보다 위인 이유: 끝난 작업에 남은 의존 표시는 이력일 뿐이고, 그것을
    // 차단으로 세면 «완료했는데 막혀 있다» 는 모순이 화면에 동시에 보인다(실측으로 그랬다).
    // «진행» 이 «차단» 보다 위인 이유: 이미 돌고 있으면 막힌 것이 아니다.
    const kind: FactoryWbsKind = isTaskDone(t?.status) ? 'done'
      : isTaskActive(t?.status) ? 'active'
      : unmet.length ? 'blocked'
      : 'waiting';
    return {
      id: String(t?.task_id ?? ''),
      title: String(t?.title ?? ''),
      status: String(t?.status ?? ''),
      kind,
      ...(agents.length ? { agent: agents.join(', ') } : {}),
      ...(unmet.length ? { blockedBy: unmet } : {}),
    };
  }).filter((t) => t.id);

  // ── 결정 대기 ──────────────────────────────────────────────────────────
  // HOTL 이 멈춰 세운 것이 곧 «사람이 답할 것» 이다. 큐(`human_feedback_queue`)는 **이미 답한
  // 것**이 쌓이는 곳이므로 결정 목록에 넣지 않는다 — 넣으면 답한 질문이 계속 남아 있다.
  const decisions: FactoryDecisionVm[] = snap.hotlTaskId
    ? [{
        id: String(snap.hotlTaskId),
        prompt: String(st?.supervisor_feedback || '').trim(),
        impact: currentStage,
        options: [],
      }]
    : [];

  // ── 산출물 ────────────────────────────────────────────────────────────
  const artMap = (st?.artifacts || {}) as Record<string, string>;
  const artifacts: FactoryArtifactVm[] = Object.keys(artMap).map((k) => ({
    id: k,
    type: artifactType(k),
    status: String(artMap[k] ?? ''),
  }));
  for (const r of snap.releases || []) {
    const id = String(r?.release_id ?? r?.id ?? '');
    if (id) artifacts.push({ id, type: 'report', status: String(r?.status ?? 'released') });
  }

  // ── 연결 ──────────────────────────────────────────────────────────────
  // «끊김» 과 «재연결 중» 을 나눈다. 스프린트가 돌고 있는데 SSE 가 끊긴 것은 곧 복구될 상태이고,
  // 아무것도 돌지 않을 때의 끊김은 그냥 끊김이다. 같은 색으로 보이면 사용자가 새로고침을 남발한다.
  const connection: FactoryConnection =
    snap.isConnected ? 'connected' : (running ? 'reconnecting' : 'offline');

  // ── 적재 상태 ─────────────────────────────────────────────────────────
  let loadState: FactoryLoadState = 'ready';
  let loadReason = '';
  if (!projectId) {
    loadState = 'empty';
    loadReason = '열어 둔 프로젝트가 없습니다.';
  } else if (isForbidden(snap.agentRegistryError)) {
    // 레지스트리를 못 읽으면 단계 지도를 그릴 근거가 없다. 그것을 «0단계» 로 그리지 않는다.
    loadState = 'forbidden';
    loadReason = snap.agentRegistryError;
  } else if (snap.agentRegistryError) {
    loadState = 'error';
    loadReason = snap.agentRegistryError;
  } else if (snap.isWbsError) {
    loadState = 'error';
    loadReason = 'WBS 를 세 번 연속 읽지 못했습니다.';
  } else if (!st && !defs) {
    loadState = 'loading';
    loadReason = '';
  } else if (!defs) {
    loadState = 'loading';
    loadReason = '단계 구성(에이전트 레지스트리)을 아직 읽지 못했습니다.';
  } else if (!stages.length && !wbs.length && !artifacts.length) {
    loadState = 'empty';
    loadReason = '아직 만들어진 것이 없습니다.';
  }

  return {
    project: {
      id: projectId,
      name: String(st?.project_name || projectId || ''),
      mode: String(st?.factory_mode || ''),
      // 비용은 이 store 에 없다. **0 으로 채우지 않는다** — «0원» 과 «모른다» 는 다르다.
      cost: null,
    },
    stages,
    selectedStageId: String(opts.selectedStageId || ''),
    currentStageId: currentStage,
    wbs,
    ...(opts.selectedWbsId ? { selectedWbsId: opts.selectedWbsId } : {}),
    decisions,
    artifacts,
    events: toEvents(snap.logs, snap.supervisorFeed),
    connection,
    loadState,
    loadReason,
    stageSourceKnown: !!defs,
    // 「사람이 답해야 하는 상태」 판정은 `HOTLInput` 과 같은 조건을 쓴다 — 두 화면이 다르게
    // 판정하면 한쪽은 질문을 보여 주고 다른 쪽은 안 보여 준다.
    clarify: toClarify(st, !!(st?.needs_revision || snap.hotlTaskId)),
    generated: toGenerated(st, running),
    inspect: {
      // 순서상 다음 단계 — «아직 끝나지 않은 것 중 현재 다음». 조건은 만들지 않는다.
      nextStage: (() => {
        const i = stages.findIndex((s) => s.id === currentStage);
        const next = i >= 0 ? stages[i + 1] : undefined;
        return next ? { id: next.id, label: next.label } : null;
      })(),
      // «무엇이 막고 있는가» 는 **시작할 수 없는 작업**만이다. 완료·진행 중인 작업을 여기 넣으면
      // 「완료했는데 차단」 같은 모순이 화면에 보인다(2026-08-06 실측으로 그랬다).
      blocked: wbs
        .filter((t) => t.kind === 'blocked')
        .map((t) => ({ id: t.id, title: t.title, blockedBy: t.blockedBy || [] })),
      failure: snap.lastSprintFailure
        ? {
            taskId: String(snap.lastSprintFailure.taskId || ''),
            error: String(snap.lastSprintFailure.error || ''),
            detail: String(snap.lastSprintFailure.detail || ''),
          }
        : null,
      healingRetries: Number(snap.healingRetryCount || 0),
      suspendedTaskId: snap.isSuspendedQuota ? String(snap.suspendedTaskId || '') : '',
    },
    docs: toDocs(st),
    releases: (snap.releases || [])
      .map((r: any) => ({
        id: String(r?.release_id ?? r?.id ?? ''),
        status: String(r?.status ?? ''),
        at: String(r?.created_at ?? r?.at ?? ''),
      }))
      .filter((r) => r.id),
  };
}

/** 권한 문제인지 구분한다 — 사용자가 해야 할 다음 행동이 «로그인·권한 요청» 이라 다르다. */
function isForbidden(reason: string): boolean {
  const r = (reason || '').trim();
  if (!r) return false;
  return /403|401|권한|자격|식별|로그인/.test(r);
}

/**
 * 화면에서 쓰는 hook. **필요한 필드만 구독한다**(§4 마지막 행: 전체 store 구독과 중복 렌더 방지).
 *
 * ⚠️ `useFactoryStore((s) => s)` 로 통째로 받으면 store 의 어떤 값이 바뀌어도 Studio 전체가 다시
 *   그려진다 — 로그 한 줄이 들어올 때마다 단계 지도와 WBS 가 함께 리렌더된다. 그래서 필드 단위로
 *   고르고 `useMemo` 로 파생을 고정한다.
 */
export function useFactoryViewModel(opts: FactoryViewModelOptions = {}): FactoryStudioViewModel {
  const state = useFactoryStore((s) => s.state);
  const currentProjectId = useFactoryStore((s) => s.currentProjectId);
  const isConnected = useFactoryStore((s) => s.isConnected);
  const completed_agents = useFactoryStore((s) => s.completed_agents);
  const activeSprintId = useFactoryStore((s) => s.activeSprintId);
  const hotlTaskId = useFactoryStore((s) => s.hotlTaskId);
  const currentTemplateData = useFactoryStore((s) => s.currentTemplateData);
  const agentRegistry = useFactoryStore((s) => s.agentRegistry);
  const agentRegistryError = useFactoryStore((s) => s.agentRegistryError);
  const wbsData = useFactoryStore((s) => s.wbsData);
  const isWbsError = useFactoryStore((s) => s.isWbsError);
  const logs = useFactoryStore((s) => s.logs);
  const supervisorFeed = useFactoryStore((s) => s.supervisorFeed);
  const releases = useFactoryStore((s) => s.releases);
  const lastSprintFailure = useFactoryStore((s) => s.lastSprintFailure);
  const isSuspendedQuota = useFactoryStore((s) => s.isSuspendedQuota);
  const suspendedTaskId = useFactoryStore((s) => s.suspendedTaskId);
  const healingRetryCount = useFactoryStore((s) => s.healingRetryCount);

  const { selectedStageId, selectedWbsId } = opts;
  return useMemo(
    () => buildFactoryViewModel(
      {
        state, currentProjectId, isConnected, completed_agents, activeSprintId, hotlTaskId,
        currentTemplateData, agentRegistry, agentRegistryError, wbsData, isWbsError,
        logs, supervisorFeed, releases, lastSprintFailure, isSuspendedQuota, suspendedTaskId,
        healingRetryCount,
      },
      { selectedStageId, selectedWbsId },
    ),
    [state, currentProjectId, isConnected, completed_agents, activeSprintId, hotlTaskId,
     currentTemplateData, agentRegistry, agentRegistryError, wbsData, isWbsError,
     logs, supervisorFeed, releases, lastSprintFailure, isSuspendedQuota, suspendedTaskId,
     healingRetryCount, selectedStageId, selectedWbsId],
  );
}
