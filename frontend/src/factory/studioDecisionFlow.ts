// 읽기 확인과 결정 제출을 분리한다. 미확정 쓰기는 메모리에 잠그고 자동 재전송하지 않는다.
import type { ContractDecisionResult, ContractReviewPending, ContractReconcileInput } from '../lib/contractReviewApi';
import type { CapabilityDecision, CapabilityPending, HotlDraftRef, HotlRound, HotlSubmissionReceipt, StudioDecisionApi } from './studioDecisionApi';
import { decisionError, isDecisionDigest, StudioDecisionError, verifyHotlQuestions } from './studioDecisionApi';
import type { HotlQuestionVerification } from './studioDecisionApi';
import { studioIdentityKey, studioInputKey, studioInputMemory } from './studioInputMemory';

export type DecisionRecord = {
  key: string; kind: 'HOTL' | 'HOST' | 'CAPABILITY'; subject: string;
  note: string; choice: string;
  outcome: 'EDITING' | 'UNKNOWN' | 'RECORDED' | 'CONFIRMED';
  body?: Record<string, unknown>; eventId?: string; message?: string;
  hostReceipt?: ContractDecisionResult; reconcileAttempted?: boolean;
  reconcileBody?: ContractReconcileInput;
};
export type StudioDecisionState = {
  loaded: boolean; busy: boolean; error: StudioDecisionError | null;
  hotl: HotlRound | null; host: ContractReviewPending | null; hostTaskId: string;
  capabilities: CapabilityPending | null; records: Record<string, DecisionRecord>;
  capabilityError: StudioDecisionError | null;
};
export const hotlSubject = (row: HotlRound) => JSON.stringify([row.taskId, row.request_id, row.questions_digest]);
export const hostSubject = (taskId: string, row: ContractReviewPending) => JSON.stringify([taskId, row.request_event_id, row.compiled_fingerprint]);
export const capabilitySubject = (row: CapabilityDecision) => JSON.stringify([
  row.decision_kind, row.task_id || '', row.capability || '', row.dataset_key || '', row.decision_request_id, row.expected_digest,
]);
export function capabilityActionable(row: CapabilityDecision): boolean {
  return row.round_status === 'PENDING' && !!row.decision_request_id && isDecisionDigest(row.expected_digest)
    && row.choices.length > 0 && (row.decision_kind === 'CAPABILITY' ? !!row.task_id && !!row.capability
      : row.decision_kind === 'DATASET' && !!row.dataset_key);
}
const stale = () => new StudioDecisionError('검토한 차수 또는 계약이 바뀌었습니다. 현재 결정 다시 조회 후 확인하세요.', 409, 'DECISION_ROUND_STALE');

export function createStudioDecisionFlow(projectId: string, api: StudioDecisionApi, taskHint = 'sprint_init') {
  const identity = studioIdentityKey();
  const indexKey = studioInputKey(projectId, 'decision-index', 'rounds');
  const listeners = new Set<() => void>();
  let generation = 0;
  let active = false;
  let state: StudioDecisionState = {
    loaded: false, busy: false, error: null, hotl: null, host: null, hostTaskId: '', capabilities: null, records: {}, capabilityError: null,
  };
  const live = (version = generation) => active && version === generation && identity === studioIdentityKey();
  const emit = (patch: Partial<StudioDecisionState>) => {
    state = { ...state, ...patch }; listeners.forEach(listener => listener());
  };
  const keyFor = (kind: DecisionRecord['kind'], subject: string) => studioInputKey(projectId, `decision-${kind}`, subject);
  const readRecords = (): Record<string, DecisionRecord> => {
    const records: Record<string, DecisionRecord> = {};
    for (const key of studioInputMemory.get<string[]>(indexKey, [])) {
      const value = studioInputMemory.get<DecisionRecord | null>(key, null);
      if (value) records[key] = value;
    }
    return records;
  };
  const record = (kind: DecisionRecord['kind'], subject: string): DecisionRecord => {
    const key = keyFor(kind, subject);
    return studioInputMemory.get<DecisionRecord>(key, { key, kind, subject, note: '', choice: '', outcome: 'EDITING' });
  };
  const save = (value: DecisionRecord) => {
    if (!live()) return;
    studioInputMemory.set(value.key, value);
    const keys = studioInputMemory.get<string[]>(indexKey, []);
    if (!keys.includes(value.key)) studioInputMemory.set(indexKey, [...keys, value.key]);
    emit({ records: { ...state.records, [value.key]: value } });
  };
  const fail = (error: unknown) => {
    const parsed = decisionError(error);
    emit({ error: parsed, ...([401, 403, 404].includes(parsed.status) ? {
      loaded: false, hotl: null, host: null, capabilities: null, records: {}, hostTaskId: '', capabilityError: null,
    } : {}) });
  };
  async function readAll() {
    const [hotlResult, capabilityResult] = await Promise.allSettled([api.hotl(), api.capabilities()]);
    if (hotlResult.status === 'rejected') throw hotlResult.reason;
    const hotl = hotlResult.value;
    let capabilities: CapabilityPending | null = null;
    let capabilityError: StudioDecisionError | null = null;
    if (capabilityResult.status === 'fulfilled') capabilities = capabilityResult.value;
    else {
      capabilityError = decisionError(capabilityResult.reason);
      // 계약 작성 전 명확화 단계에서만 아직 없는 계약 판을 별도 안내한다. 빈 목록으로 위장하지 않는다.
      if (!hotl.available || hotl.decision_kind !== 'CLARIFICATION'
          || capabilityError.status !== 503 || capabilityError.reasonCode !== 'DECISION_ROUND_METADATA_MISSING') throw capabilityError;
    }
    const hostTaskId = hotl.taskId || taskHint || 'sprint_init';
    const host = await api.host(hostTaskId);
    return { hotl, capabilities, capabilityError, hostTaskId, host };
  }
  const sameHotl = (a: HotlRound, b: HotlRound) => a.available && b.available
    && hotlSubject(a) === hotlSubject(b) && a.decision_kind === b.decision_kind;
  const unresolvedHost = (taskId: string, fingerprint: string) => Object.values(readRecords()).some(row => {
    if (row.kind !== 'HOST' || !['UNKNOWN', 'RECORDED'].includes(row.outcome) || row.body?.task_id !== taskId) return false;
    try { return JSON.parse(row.subject)[2] === fingerprint; }
    catch { return true; }
  });
  const permitHotl = (view: Pick<StudioDecisionState, 'host' | 'capabilities' | 'hotl' | 'capabilityError'>) => view.host?.pending === false
    && ((view.capabilities?.pending === false && view.capabilities.other_errors.length === 0)
      || (view.hotl?.decision_kind === 'CLARIFICATION' && view.capabilityError?.status === 503
        && view.capabilityError.reasonCode === 'DECISION_ROUND_METADATA_MISSING'))
    && !Object.values(readRecords()).some(row => row.kind === 'HOST' && row.body?.task_id === view.hotl?.taskId
      && (row.outcome === 'RECORDED' || row.outcome === 'UNKNOWN'));
  const model = {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    activate() { active = true; emit({ busy: false }); },
    invalidate() {
      active = false; generation += 1;
      emit({ loaded: false, busy: false, hotl: null, host: null, capabilities: null, records: {}, hostTaskId: '', capabilityError: null,
        error: new StudioDecisionError('문맥이 바뀌었거나 작업을 닫았습니다. 현재 작업을 다시 여세요.', 409, 'DECISION_CONTEXT_CHANGED') });
    },
    keyFor,
    canResume: () => state.loaded && !!state.hotl?.available && permitHotl(state),
    canDecide: () => state.loaded && !!state.host?.pending && state.host.actionable === true
      && !!state.host.request_event_id && isDecisionDigest(state.host.compiled_fingerprint)
      && !unresolvedHost(state.hostTaskId, state.host.compiled_fingerprint),
    async load() {
      if (!live() || state.busy) return;
      const version = ++generation;
      emit({ busy: true, loaded: false, error: null, hotl: null, host: null, capabilities: null, records: {}, capabilityError: null });
      try {
        const view = await readAll();
        if (live(version)) {
          const records = readRecords();
          emit({ ...view, loaded: true, records });
        }
      } catch (error) { if (live(version)) fail(error); }
      finally { if (live(version)) emit({ busy: false }); }
    },
    edit(kind: DecisionRecord['kind'], subject: string, field: 'note' | 'choice', value: string) {
      if (!live() || state.busy || !state.loaded) return;
      const current = record(kind, subject);
      if (current.outcome === 'EDITING') save({ ...current, [field]: value });
    },
    async resume(feedback: string, questionProof?: HotlQuestionVerification, draft?: HotlDraftRef | null) {
      const row = state.hotl;
      if (!row || !model.canResume()) return;
      //: ★ [B5] 일반 HOTL 과 명확화 모두 저장 초안을 닫는다. 명확화는 서버가 같은 질문으로
      //:   본문을 재현해 접수 시점에 대조한다(설계안 갈래 A).
      const bound = draft ? { ...draft } : null;
      await mutate('HOTL', hotlSubject(row), async () => {
        if (row.decision_kind === 'CLARIFICATION'
            && (!questionProof || !await verifyHotlQuestions(questionProof, row.questions_digest))) {
          throw new StudioDecisionError('화면 질문과 서버 질문 지문이 일치하지 않습니다. 질문을 다시 조회하세요.', 409, 'HOTL_QUESTIONS_UNVERIFIED');
        }
        const fresh = await readAll();
        if (!sameHotl(row, fresh.hotl) || !permitHotl(fresh)) throw stale();
        return { task_id: row.taskId, expected_request_id: row.request_id, expected_questions_digest: row.questions_digest, feedback,
          ...(bound ? { client_request_id: crypto.randomUUID(), input_draft: bound } : {}) };
      }, body => api.resume(body as Parameters<StudioDecisionApi['resume']>[0]), result => {
        //: 접수 기록이 확인된 제출만 초안을 닫을 근거(eventId)로 남긴다. 접수는 가동·완료가 아니다.
        const receipt = (result as { submission?: HotlSubmissionReceipt } | null)?.submission;
        return { outcome: 'CONFIRMED', ...(receipt ? { eventId: receipt.request_id } : {}),
          message: '재개 요청이 접수됐습니다. 실제 실행 상태는 현재 결정 조회와 진행 화면에서 확인하세요.' };
      });
    },
    /** 응답 유실 뒤 원키 확인. 재전송하지 않고 접수 여부만 다시 읽는다. */
    async recheckSubmission(subject: string, requestId: string) {
      if (!live() || state.busy || !requestId) return null;
      const current = record('HOTL', subject);
      const version = generation;
      emit({ busy: true, error: null });
      try {
        const receipt = await api.readSubmission(requestId);
        if (!live(version)) return null;
        save({ ...current, eventId: receipt.request_id, outcome: 'CONFIRMED',
          message: receipt.status === 'ACCEPTED'
            ? '원래 요청의 저장된 접수를 확인했습니다. 새로 제출하지 않았습니다.'
            : `원래 요청의 서버 상태는 ${receipt.status} 입니다. 자동으로 다시 보내지 않습니다.` });
        return receipt;
      } catch (error) { if (live(version)) fail(error); return null; }
      finally { if (live(version)) emit({ busy: false }); }
    },
    async decide(decision: 'APPROVE' | 'REJECT') {
      const row = state.host;
      if (!model.canDecide() || !row?.pending || row.actionable !== true || !row.request_event_id
          || !isDecisionDigest(row.compiled_fingerprint)) return;
      const taskId = state.hostTaskId;
      const subject = hostSubject(taskId, row);
      const draft = record('HOST', subject);
      if (decision === 'REJECT' && !draft.note.trim()) {
        fail(new StudioDecisionError('반려 이유를 입력하세요.', 422, 'RATIONALE_REQUIRED')); return;
      }
      await mutate('HOST', subject, async () => {
        const fresh = await api.host(taskId);
        if (!fresh.pending || fresh.actionable !== true || hostSubject(taskId, fresh) !== subject) throw stale();
        // 지문은 제출에 덧붙이지 않는다. 서버가 고정 요청 사건의 지문을 검증한다.
        return { task_id: taskId, request_event_id: row.request_event_id!, decision, rationale: draft.note.trim() };
      }, body => api.decide(body as Parameters<StudioDecisionApi['decide']>[0]), result => {
        const receipt = result as ContractDecisionResult;
        if (receipt.contract_fingerprint !== row.compiled_fingerprint) throw stale();
        return { outcome: receipt.state_applied ? 'CONFIRMED' : 'RECORDED', hostReceipt: receipt, eventId: receipt.event_id,
          message: receipt.state_applied ? '계약 결정 반영을 확인했습니다. 실행 재개는 별도입니다.'
            : '결정은 원장에 기록됐으나 상태 반영이 확인되지 않았습니다. 재승인하지 마세요.' };
      });
    },
    async resolve(row: CapabilityDecision) {
      if (!state.loaded || state.capabilities?.round_metadata_status !== 'READY' || !capabilityActionable(row)) return;
      const subject = capabilitySubject(row);
      const draft = record('CAPABILITY', subject);
      if (!row.choices.includes(draft.choice)) {
        fail(new StudioDecisionError('서버가 제공한 선택지 중 하나를 선택하세요.', 422, 'CHOICE_REQUIRED')); return;
      }
      await mutate('CAPABILITY', subject, async () => {
        const pending = await api.capabilities();
        const fresh = [...pending.capability_decisions, ...pending.dataset_conflicts].find(item => capabilitySubject(item) === subject);
        if (pending.round_metadata_status !== 'READY' || !fresh || !capabilityActionable(fresh)
            || JSON.stringify(fresh.choices) !== JSON.stringify(row.choices)) throw stale();
        return { decision_request_id: row.decision_request_id!, expected_digest: row.expected_digest!, rationale: draft.note.trim(),
          ...(row.decision_kind === 'DATASET' ? { dataset_key: row.dataset_key, winner_task_id: draft.choice }
            : { task_id: row.task_id, capability: row.capability, decision: draft.choice }) };
      }, body => api.resolve(body as Parameters<StudioDecisionApi['resolve']>[0]), result => {
        const receipt = result as Awaited<ReturnType<StudioDecisionApi['resolve']>>;
        return { outcome: receipt.draft_applied ? 'CONFIRMED' : 'RECORDED', eventId: receipt.event_id,
          message: receipt.draft_applied ? '선택의 초안 반영을 확인했습니다. 실행 재개는 별도입니다.'
            : '원장 기록 이후 초안 반영을 확인하지 못했습니다. 재결정하지 말고 조회하세요.' };
      });
    },
    async reconcile(key: string) {
      if (!live() || !state.loaded || state.busy) return;
      const draft = state.records[key];
      const receipt = draft?.hostReceipt;
      if (!receipt || receipt.decision !== 'APPROVE' || receipt.state_applied) return;
      const version = generation;
      const body = structuredClone(draft.reconcileBody || {
        task_id: String(draft.body?.task_id || ''), request_event_id: receipt.request_event_id,
        event_id: receipt.event_id, compiled_fingerprint: receipt.contract_fingerprint });
      // 별도 복구도 미확정 결과를 자동 재전송하지 않는다. 승인 본문은 끝까지 그대로 보존한다.
      save({ ...draft, reconcileAttempted: true, reconcileBody: body });
      emit({ busy: true, error: null });
      try {
        const result = await api.reconcile(body);
        if (!live(version)) return;
        save({ ...draft, reconcileAttempted: true, reconcileBody: body, outcome: result.state_applied ? 'CONFIRMED' : 'RECORDED',
          hostReceipt: { ...receipt, state_applied: result.state_applied },
          message: result.state_applied ? '동일 승인 사건의 반영을 확인했습니다. 실행은 시작하지 않았습니다.'
            : '반영이 아직 확인되지 않았습니다. 기존 사건을 보존했습니다. 상태를 조회하세요.' });
      } catch (error) {
        if (live(version)) {
          save({ ...draft, reconcileAttempted: true, reconcileBody: body,
            message: '복구 결과가 미확정입니다. 현재 상태를 조회하거나 아래에서 동일 사건 복구만 명시적으로 다시 확인하세요. 새 승인은 금지합니다.' });
          fail(error);
        }
      } finally { if (live(version)) emit({ busy: false }); }
    },
  };
  async function mutate(kind: DecisionRecord['kind'], subject: string,
    prepare: () => Promise<Record<string, unknown>>, post: (body: Record<string, unknown>) => Promise<unknown>,
    summarize: (result: unknown) => Partial<DecisionRecord>) {
    if (!live() || state.busy || !state.loaded) return;
    const original = record(kind, subject);
    if (original.outcome !== 'EDITING') return;
    const version = generation;
    let attempted: DecisionRecord | null = null;
    emit({ busy: true, error: null });
    try {
      const body = await prepare();
      if (!live(version)) return;
      attempted = { ...original, body: structuredClone(body), outcome: 'UNKNOWN',
        message: '전송 결과 확인 중입니다. 같은 결정을 다시 보내지 않습니다.' };
      save(attempted);
      const result = await post(body);
      if (!live(version)) return;
      save({ ...attempted, ...summarize(result) });
    } catch (error) {
      if (!live(version)) return;
      if (attempted) {
        const parsed = decisionError(error);
        save({ ...attempted, eventId: typeof parsed.detail.event_id === 'string' ? parsed.detail.event_id : attempted.eventId,
          message: '제출 결과를 확인하지 못했습니다. 입력·대상·사건을 보존했습니다. 재전송 대신 현재 결정 다시 조회를 사용하세요.' });
      }
      fail(error);
    } finally { if (live(version)) emit({ busy: false }); }
  }
  return model;
}
export type StudioDecisionFlow = ReturnType<typeof createStudioDecisionFlow>;
