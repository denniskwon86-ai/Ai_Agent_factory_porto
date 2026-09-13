// 실제 StudioContent + 메모리 상태/API. 운영 인증·DB·승인·SSE 시험이 아니다.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { StudioContent } from '../src/factory/AdaptiveProductionStudio';
import { KitAppPanel } from '../src/components/KitAppPanel';
import type { KitContractReview } from '../src/lib/kitContractReviewApi';
import type { InputDraft, InputDraftTarget } from '../src/lib/studioInputDraftApi';
import type { RevisionReceipt } from '../src/lib/studioRevisionApi';
import type { ExecutionReceipt, ExecutionRequest } from '../src/lib/studioExecutionApi';
import { sameRevisionCommand, sameRevisionRef } from '../src/lib/studioRevisionApi';
import { useFactoryStore } from '../src/store/useFactoryStore';
import type { ProjectState } from '../src/store/useFactoryStore';
import '../src/index.css';
import '../src/design/afs.css';

type Scene = 'request' | 'work' | 'review' | 'result' | 'offline' | 'kit' | 'revision' | 'execution' | 'paused';
let scene: Scene = 'request';
let sequence = 0;
const sha = 'a'.repeat(64);
const events: string[] = [];
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
let kitRun = 0;
let kitMode: 'reviewer' | 'author' | 'hold' | 'unavailable' = 'reviewer';
let kitView: KitContractReview;
function resetKit(mode = kitMode) {
  kitMode = mode;
  const instance = `synthetic_kit_${++kitRun}`;
  kitView = { instance_id: instance, app_id: 'APP-01', revision: 1, latest_revision: 1,
    status: 'DRAFT', semantic_fingerprint: sha, drafted_by: 'synthetic-author', approved_by: '',
    principal_user_id: mode === 'author' ? 'synthetic-author' : 'synthetic-reviewer',
    permitted_actions: mode === 'author' ? [] : mode === 'hold' ? ['reject'] : ['approve', 'reject'],
    review_blockers: mode === 'author' ? [{ reason_code: 'SELF_APPROVAL_FORBIDDEN', message: '초안 작성자는 자기 계약을 승인할 수 없습니다.' }]
      : mode === 'hold' ? [{ reason_code: 'SYNTHETIC_DATA_HOLD', message: '합성 데이터 보류: 원문 조회·반려는 가능하고 승인·실행은 차단된 예시입니다.' }] : [],
    decision_event: null, contract: { schema_version: '2.0', project_id: instance, task_id: 'APP-01',
      revision: 1, status: 'DRAFT', semantic_fingerprint: sha,
      description: 'SYNTHETIC: 구매 계획 조회용 계약. 실제 데이터·승인·실행과 무관합니다.',
      process: { l1: '원료 구매', l2: '구매 계획' }, outputs: ['원료별 구매 계획 목록'] } };
}
resetKit();
let revisionDraft: InputDraft | null = null;
const revisionDrafts = new Map<string, InputDraft>();
let loseRevisionResponse = false;
const revisionReceipts = new Map<string, RevisionReceipt>();
const executionReceipts = new Map<string, ExecutionReceipt>();
let loseExecutionResponse = false;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort()
    .map(key => JSON.stringify(key) + ':' + canonical((value as Record<string, unknown>)[key])).join(',') + '}';
  return JSON.stringify(value);
}
async function executionHash(value: unknown) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(value)))))
    .map(v => v.toString(16).padStart(2, '0')).join('');
}
const revisionTarget = (): InputDraftTarget => ({ kind: 'REVISION_REQUEST', task_id: 'TASK_1',
  decision_kind: '', subject_id: '', target_digest: sha, request_id: `artifact_${sha}` });
window.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href);
  const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
  events.unshift(`${++sequence}. ${init.method || 'GET'} ${url.pathname}`);
  window.dispatchEvent(new Event('synthetic:request'));
  const commandMatch = /^\/api\/v1\/factory\/(synthetic_[a-z]+)\/execution-commands(?:\/([a-f0-9-]+))?$/.exec(url.pathname);
  if (commandMatch) {
    const [, projectId, requestId] = commandMatch;
    if (init.method !== 'POST') {
      if (!requestId) return response({ requests: [...executionReceipts.values()].filter(row => row.project_id === projectId) });
      const row = executionReceipts.get(requestId);
      return row?.project_id === projectId ? response({ request: row }) : response({ detail: { message: '합성 원요청 기록이 없습니다.' } }, 404);
    }
    const command = body as ExecutionRequest;
    const previous = executionReceipts.get(command.client_request_id);
    if (previous) return previous.command_digest === await executionHash(command)
      ? response({ request: previous }) : response({ detail: { message: '같은 합성 요청 ID의 본문이 다릅니다.' } }, 409);
    const reply = command.operation === 'HEAL'
      ? { status: 'healing_started', task_id: 'TASK_REV_HEAL_' + command.client_request_id.replaceAll('-', '') }
      : { status: command.operation === 'START' ? 'started' : command.operation === 'PAUSE' ? 'paused'
        : command.operation === 'STOP' ? 'stopped' : 'resumed', task_id: command.task_id };
    const now = new Date().toISOString();
    const unsigned = { request_id: command.client_request_id, project_id: projectId, actor_id: 'synthetic-user',
      operation: command.operation, task_id: command.task_id, input: command.input, command_digest: await executionHash(command),
      status: 'ACCEPTED' as const, result: { http_status: 200, response: reply }, created_at: now, updated_at: now };
    const row = { ...unsigned, receipt_digest: await executionHash(unsigned) };
    executionReceipts.set(command.client_request_id, row);
    if (loseExecutionResponse) { loseExecutionResponse = false; throw new Error('합성: 접수 후 응답 유실'); }
    return response({ request: row });
  }
  const revisionBase = '/api/v1/factory/synthetic_revision';
  if (scene === 'revision' && url.pathname.startsWith(revisionBase)) {
    if (url.pathname.endsWith('/input-drafts/target')) return response({ status: 'success', data: {
      target: revisionTarget(), draft: revisionDraft?.status === 'DRAFT' ? revisionDraft : null, consume_supported: true } });
    if (url.pathname === `${revisionBase}/input-drafts` && init.method === 'POST') {
      const current = revisionDraft?.status === 'DRAFT' ? revisionDraft : null;
      if (body.target?.target_digest !== sha || body.expected_revision !== (current?.revision || 0)
          || body.expected_digest !== (current?.digest || '')) return response({ detail: { message: '합성 초안의 기준·판본이 바뀌었습니다.' } }, 409);
      const revision = (current?.revision || 0) + 1;
      revisionDraft = { draft_id: current?.draft_id || `synthetic_revision_draft_${revisionDrafts.size + 1}`, project_id: 'synthetic_revision', target: revisionTarget(),
        content: { text: body.content.text, decision: '', selections: {} }, revision,
        digest: revision.toString(16).padStart(64, '0'), status: 'DRAFT', restorable: true };
      revisionDrafts.set(revisionDraft.draft_id, revisionDraft);
      return response({ status: 'success', data: revisionDraft });
    }
    if (url.pathname.startsWith(`${revisionBase}/input-drafts/synthetic_revision_draft_`) && url.pathname.endsWith('/consume') && init.method === 'POST') {
      const receipt = [...revisionReceipts.values()].find(value => value.submission_id === body.submission_id);
      const id = url.pathname.split('/').at(-2)!;
      const saved = revisionDrafts.get(id);
      if (!saved || !receipt || receipt.input_draft.draft_id !== id || receipt.input_draft.digest !== body.expected_digest
          || receipt.input_draft.revision !== body.expected_revision) return response({ detail: { message: '합성 접수증과 저장초안이 일치하지 않습니다.' } }, 409);
      if (saved.status === 'CONSUMED') return response({ status: 'success', data: saved });
      if (saved.digest !== body.expected_digest || saved.revision !== body.expected_revision)
        return response({ detail: { message: '접수 후 수정된 합성 초안은 사용 완료할 수 없습니다.' } }, 409);
      const consumed: InputDraft = { ...saved, content: null, status: 'CONSUMED', restorable: false,
        revision: saved.revision + 1, digest: 'f'.repeat(64) };
      revisionDrafts.set(id, consumed);
      if (revisionDraft?.draft_id === id) revisionDraft = consumed;
      return response({ status: 'success', data: consumed });
    }
    const endpoint = `${revisionBase}/sprint/revision-requests`;
    if (url.pathname === endpoint && init.method === 'POST') {
      const previous = revisionReceipts.get(body.client_request_id);
      if (previous) return sameRevisionCommand({ ...previous, client_request_id: previous.request_id }, body)
        ? response({ status: 'success', data: previous }) : response({ detail: { message: '같은 합성 요청 번호의 내용이 다릅니다.' } }, 409);
      if ([...revisionReceipts.values()].some(receipt => sameRevisionRef(receipt.input_draft, body.input_draft)))
        return response({ detail: { message: '같은 합성 초안 판은 이미 접수됐습니다.' } }, 409);
      if (!revisionDraft || revisionDraft.status !== 'DRAFT' || revisionDraft.content?.text.trim() !== body.feedback
          || body.input_draft?.draft_id !== revisionDraft.draft_id || body.input_draft?.digest !== revisionDraft.digest || body.input_draft?.revision !== revisionDraft.revision)
        return response({ detail: { message: '같은 의견의 합성 초안을 먼저 저장하세요.' } }, 409);
      const receipt: RevisionReceipt = { request_id: body.client_request_id, submission_id: `synthetic_submission_${sequence}`,
        project_id: 'synthetic_revision', actor_id: 'synthetic-user', target: revisionTarget(), feedback: body.feedback,
        input_draft: body.input_draft, task_id: `TASK_REV_${revisionReceipts.size + 1}`, status: 'ACCEPTED',
        execution_started: false, created_at: new Date().toISOString() };
      revisionReceipts.set(body.client_request_id, receipt);
      useFactoryStore.setState(state => ({ wbsData: { ...state.wbsData, tasks: [...(state.wbsData?.tasks || []),
        { task_id: receipt.task_id, title: '합성 수정 요청 · 접수됨', status: 'TODO', dependencies: [] }] } }));
      if (loseRevisionResponse) { loseRevisionResponse = false; throw new Error('합성 응답 유실: 서버 접수는 저장했습니다. 원 요청 결과 확인을 눌러 주세요.'); }
      return response({ status: 'success', data: receipt });
    }
    if (url.pathname.startsWith(endpoint + '/') && (!init.method || init.method === 'GET')) {
      const receipt = revisionReceipts.get(decodeURIComponent(url.pathname.slice(endpoint.length + 1)));
      return receipt ? response({ status: 'success', data: receipt }) : response({ detail: { message: '합성 접수증을 아직 확인하지 못했습니다.' } }, 404);
    }
  }
  if (url.pathname === '/api/v1/auth/me') return response({ status: 'success', data: { user_id: kitView.principal_user_id } });
  const kitBase = `/api/v1/data-preparation/instances/${kitView.instance_id}/apps`;
  if (url.pathname === kitBase) return response({ status: 'success', data: { instance_id: kitView.instance_id, apps: [{
    app_id: 'APP-01', label: '구매 계획 확인 · 합성 예시', contract_schema_version: '2.0',
    readiness_state: kitMode === 'hold' ? 'BLOCKED' : 'AVAILABLE', user_message: '실제 자료를 읽지 않는 검토 화면 체험입니다.',
    next_action: '계약 확인', contract_status: kitView.status, contract_revision: 1, drafted_by: kitView.drafted_by,
    approved_by: kitView.approved_by, permitted_actions: kitView.permitted_actions,
    release_id: '', built_datasets: 0, lifecycle_state: '',
  }] } });
  const contractBase = `${kitBase}/APP-01/contract`;
  if (url.pathname.startsWith(contractBase)) {
    if (kitMode === 'unavailable') return response({ detail: { reason_code: 'SYNTHETIC_UNAVAILABLE', message: '합성 조회 실패입니다. 성공이나 빈 계약으로 표시하지 않습니다.' } }, 503);
    if (url.pathname === `${contractBase}/v2` && (!init.method || init.method === 'GET')) return response({ status: 'success', data: kitView });
    const approve = url.pathname === `${contractBase}/v2/approve`;
    if (init.method === 'POST' && (approve || url.pathname === `${contractBase}/reject`)) {
      if (!kitView.permitted_actions.includes(approve ? 'approve' : 'reject')) return response({ detail: { message: '합성 상태에서 허용되지 않은 결정입니다.' } }, 403);
      if (body.revision !== 1 || (approve ? body.expected_fingerprint : body.expected_digest) !== sha) return response({ detail: { message: '합성 대상 판본이 다릅니다.' } }, 409);
      const eventId = `synthetic-event-${sequence}`;
      kitView = { ...kitView, status: approve ? 'APPROVED' : 'REJECTED', permitted_actions: [],
        approved_by: approve ? kitView.principal_user_id : '',
        contract: { ...kitView.contract, status: approve ? 'APPROVED' : 'DRAFT',
          ...(approve ? { approval: { decision_ledger_id: eventId } } : {}) },
        decision_event: { event_id: eventId, actor_id: kitView.principal_user_id,
          decision: approve ? 'APPROVED' : 'REJECTED', rationale: body.rationale } };
      return response({ status: 'success', data: { ...kitView, ledger_event_id: approve ? eventId : '',
        ...(approve ? {} : { rejection: { decision_ledger_id: eventId, rejected_by: kitView.principal_user_id, rationale: body.rationale } }) } });
    }
  }
  if (url.pathname.endsWith('/hotl/check')) return response({ status: 'success', hotl_task_id: scene === 'review' ? 'TASK_1' : null,
    ...(scene === 'review' ? { hotl_context: { status: 'PENDING', pending: true, available: true, request_id: sha,
      questions_digest: sha, decision_kind: 'GENERAL_HOTL', reason_code: 'HOTL_PENDING' } } : {}) });
  if (url.pathname.endsWith('/contract-decisions/pending')) return response({ status: 'success', data: {
    pending: false, capability_decisions: [], dataset_conflicts: [], other_errors: [], round_metadata_status: 'READY' } });
  if (url.pathname.endsWith('/contract-review/pending')) return response({ status: 'success', data: {
    pending: scene === 'review', actionable: scene === 'review', request_event_id: 'synthetic-request', compiled_fingerprint: sha,
    reason: '합성 예시: 원료 입고 내역 조회와 담당자 입력 권한을 확인하세요.', verdict: scene === 'review' ? 'REVIEW_REQUIRED' : 'APPROVED' } });
  if (url.pathname.endsWith('/contract-review/decision')) return response({ status: 'success', data: {
    decision: body.decision, event_id: 'synthetic-event', request_event_id: body.request_event_id,
    contract_fingerprint: sha, state_applied: false } });
  if (url.pathname.endsWith('/contract-review/reconcile')) return response({ status: 'success', data: {
    event_id: body.event_id, request_event_id: body.request_event_id, contract_fingerprint: body.compiled_fingerprint,
    state_applied: true, execution_started: false } });
  if (url.pathname.endsWith('/sprint/start')) return response({ status: 'started', task_id: body.task_id });
  if (url.pathname.endsWith('/sprint/pause') || url.pathname.endsWith('/sprint/stop')) return response({ status: url.pathname.endsWith('/stop') ? 'stopped' : 'paused', task_id: body.task_id });
  if (url.pathname.endsWith('/input-drafts/target')) return response({ status: 'success', data: { target: {
    kind: url.searchParams.get('kind'), task_id: url.searchParams.get('task_id'),
    decision_kind: url.searchParams.get('decision_kind') || '', request_id: url.searchParams.get('request_id') || 'synthetic-artifact',
    target_digest: sha, subject_id: url.searchParams.get('subject_id') || '' }, draft: null, consume_supported: true } });
  // 모의 저장 미구현은 성공으로 꾸미지 않는다. 실제 서버 요청으로 폴백하지 않는다.
  return response({ detail: { message: '이 체험에서 지원하지 않는 모의 동작입니다. 실제 서버는 호출하지 않았습니다.' } }, 503);
};
function select(value: Scene) {
  scene = value;
  if (value === 'kit') resetKit();
  const finished = value === 'result' || value === 'revision';
  const state = { project_name: '원료 구매 업무 앱 · 합성 예시', factory_mode: value === 'paused' ? 'PLANNING' : 'EXECUTION',
    current_sprint_task_id: value === 'paused' ? 'PLANNING_1700000000' : 'TASK_1', current_stage: finished || value === 'paused' ? 'PLANNING' : 'EXECUTION',
    needs_revision: value === 'review', build_status: '', human_feedback_queue: [], developer_retry_count: 0,
    architecture_summary: '', tech_spec_summary: '', frontend_code_summary: '', backend_code_summary: '',
    code_review_report_summary: '', qa_report_summary: '', user_manual_summary: '',
    initial_idea: '', artifacts: finished ? { planner: '# 구매 계획 확인\n\n원료별 구매 계획과 입고 예정일을 확인하는 합성 기획 결과입니다.\n\n실제 가격·수량·거래처 자료는 포함하지 않았습니다.' } : {},
    terminal_status: finished ? 'COMPLETED' : '',
    ...(value === 'paused' ? { studio_execution_state: { task_id: 'PLANNING_1700000000', running: false,
      pause: { status: 'PAUSED', resumable: true, reason_code: '' } } } : {}),
  } as ProjectState;
  useFactoryStore.setState({ currentProjectId: `synthetic_${value}`, state, isConnected: value !== 'offline',
    activeSprintId: null, hotlTaskId: value === 'review' ? 'TASK_1' : null,
    lastSprintFailure: value === 'execution' ? { taskId: 'TASK_1', error: 'SYNTHETIC: 구매 계획 결과 화면의 오류 예시' } : null,
    isSuspendedQuota: false, suspendedTaskId: null, releases: [], completed_agents: finished ? ['planner'] : [],
    agentRegistryError: '', isWbsError: false, logs: [], supervisorFeed: [],
    currentTemplateData: { agents: [
      { id: 'requirements', stage: 'CLARIFICATION', name_ko: '요구 확인', order: 1 },
      { id: 'planner', stage: 'PLANNING', name_ko: '설계 확인', order: 2 },
      { id: 'developer', stage: 'EXECUTION', name_ko: '제작', order: 3 },
      { id: 'qa', stage: 'QA', name_ko: '결과 검토', order: 4 },
    ] }, wbsData: { tasks: value === 'request' || value === 'paused' ? [] : [
      { task_id: 'TASK_1', title: '원료별 구매 계획 조회', status: finished ? 'DONE' : 'PENDING', dependencies: [] },
      ...(value === 'revision' ? [...revisionReceipts.values()].map(receipt => ({ task_id: receipt.task_id,
        title: '합성 수정 요청 · 접수됨', status: 'TODO', dependencies: [] }))
        : [{ task_id: 'TASK_2', title: '입고 예정일 입력', status: 'PENDING', dependencies: ['TASK_1'] }]),
    ] }, fetchLatestState: async () => {}, fetchWBS: async () => {}, checkHotl: async () => {}, fetchReleases: async () => {},
  });
}
const initialScene = new URLSearchParams(location.search).get('scene');
select(initialScene === 'kit' || initialScene === 'revision' || initialScene === 'execution' || initialScene === 'paused' ? initialScene : 'request');
export function Fixture() {
  const [version, setVersion] = useState(0);
  const [showEvents, setShowEvents] = useState(false);
  return <main style={{ height: '100dvh', display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr)', background: 'var(--surface-page)' }}>
    <header style={{ padding: '10px 16px', background: '#fff7dc', color: '#44350a', fontSize: 13 }}>
      <b>SYNTHETIC · 제작 화면 체험</b> — 실제 제품 화면 + 합성 상태. 운영 데이터·승인·실행 없음.
      <nav style={{ display: 'flex', gap: 8, paddingTop: 8, flexWrap: 'wrap' }}>
        {Object.entries({ request: '1. 요구 입력', work: '2. 작업 시작', review: '3. 계약 검토·복구', result: '4. 결과 확인', offline: '5. 연결 오류', kit: '6. 키트 계약 검토', revision: '7. 수정 요청 접수', execution: '8. 오류 복구·요청 확인', paused: '9. 멈춘 기획 이어하기' }).map(([id, label]) =>
          <button type="button" key={id} onClick={() => { select(id as Scene); setVersion(v => v + 1); }}>{label}</button>)}
        <button type="button" onClick={() => setShowEvents(v => !v)}>모의 요청 기록 {showEvents ? '접기' : '보기'}</button>
      </nav>
      {(scene === 'execution' || scene === 'paused') && <p>합성 접수증의 원키 조회를 체험합니다. 접수 확인 후에도 실제 제작 실행 상태로 바꾸지 않습니다.
        <button type="button" onClick={() => { loseExecutionResponse = true; setShowEvents(true); }}>다음 실행 요청 응답 유실 체험</button>
      </p>}
      {scene === 'revision' && <p>아래 ‘추가 작업’ → ‘수정 요청’에서 의견 작성 → 초안 저장 → 접수 → 사용 완료를 체험하세요.
        <button type="button" onClick={() => { loseRevisionResponse = true; setShowEvents(true); }}>다음 접수 응답 유실 체험</button>
        {loseRevisionResponse && <span> · 다음 접수 후 응답만 유실합니다. 실제 서버는 호출하지 않습니다.</span>}
      </p>}
      {scene === 'kit' && <nav style={{ display: 'flex', gap: 8, paddingTop: 8, flexWrap: 'wrap' }}>
        <span>합성 상태 선택(운영 권한 변경 없음):</span>
        {Object.entries({ reviewer: '타인 검토 · 초기화', author: '자기승인 차단', hold: '데이터 보류', unavailable: '조회 실패' }).map(([id, label]) =>
          <button type="button" key={id} onClick={() => { resetKit(id as typeof kitMode); setVersion(v => v + 1); }}>{label}</button>)}
      </nav>}
      {showEvents && <pre style={{ maxHeight: 100, overflow: 'auto' }}>{events.slice(0, 10).join('\n') || '아직 없음'}</pre>}
    </header>
    {scene === 'kit' ? <section style={{ overflow: 'auto', padding: 20 }}>
      <KitAppPanel key={version} instanceId={kitView.instance_id} />
    </section> : <StudioContent key={version} onClose={() => { select('request'); setVersion(v => v + 1); }} />}
  </main>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
