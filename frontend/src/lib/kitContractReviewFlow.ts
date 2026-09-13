// 검토 입력은 현재 로그인 메모리, 결정 정본은 서버 계약·원장이다.
import { studioIdentityKey, studioInputKey, studioInputMemory } from '../factory/studioInputMemory';
import { createKitContractReviewApi, KitReviewError, kitReviewError } from './kitContractReviewApi';
import type { KitContractReview, KitContractReviewApi, KitReviewCommand, KitReviewDecision } from './kitContractReviewApi';

export type ReviewRecord = {
  key: string; revision: number; fingerprint: string; rationale: string; decision: '' | KitReviewDecision;
  outcome: 'EDITING' | 'UNKNOWN' | 'RECORDED' | 'CONFIRMED' | 'RESOLVED_OTHER';
  command?: KitReviewCommand; eventId?: string; message?: string;
};
export type KitReviewState = { loaded: boolean; busy: boolean; view: KitContractReview | null;
  current: ReviewRecord | null; history: ReviewRecord[]; confirmed: boolean; error: KitReviewError | null };
const pending = (record: ReviewRecord) => record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED';
const target = (view: KitContractReview) => JSON.stringify([view.instance_id, view.app_id, view.revision, view.semantic_fingerprint, view.principal_user_id]);

export function createKitContractReviewFlow(instanceId: string, appId: string,
  api: KitContractReviewApi = createKitContractReviewApi(instanceId, appId), identity = studioIdentityKey()) {
  const memoryProject = JSON.stringify(['kit_app', instanceId, appId]);
  let state: KitReviewState = { loaded: false, busy: false, view: null, current: null, history: [], confirmed: false, error: null };
  let active = false;
  let generation = 0;
  let confirmation = '';
  const listeners = new Set<() => void>();
  const live = (version = generation) => active && version === generation && identity === studioIdentityKey();
  const emit = (patch: Partial<KitReviewState>) => { state = { ...state, ...patch }; listeners.forEach(listener => listener()); };
  const history = () => studioInputMemory.projectValues<ReviewRecord>(memoryProject, 'kit-review')
    .filter(row => row.outcome !== 'EDITING').sort((a, b) => b.revision - a.revision);
  const keyFor = (view: KitContractReview) => studioInputKey(memoryProject, 'kit-review', JSON.stringify([view.revision, view.semantic_fingerprint]));
  const recordFor = (view: KitContractReview) => {
    const key = keyFor(view);
    return studioInputMemory.get<ReviewRecord>(key, { key, revision: view.revision, fingerprint: view.semantic_fingerprint,
      rationale: '', decision: '', outcome: 'EDITING' });
  };
  const save = (record: ReviewRecord) => {
    if (!live()) return;
    studioInputMemory.set(record.key, record);
    emit({ history: history(), current: state.current?.key === record.key ? record : state.current });
  };
  const confirmKey = () => state.view && state.current ? JSON.stringify([target(state.view), state.current.rationale, state.current.decision]) : '';
  const allowed = (view: KitContractReview, decision: KitReviewDecision) => view.status === 'DRAFT'
    && view.revision === view.latest_revision && view.principal_user_id.trim().toLowerCase() !== view.drafted_by.trim().toLowerCase()
    && view.permitted_actions.includes(decision === 'APPROVE' ? 'approve' : 'reject');
  function observed(record: ReviewRecord, view: KitContractReview): ReviewRecord {
    const command = record.command;
    if (!command || !pending(record) || view.revision !== command.revision || view.semantic_fingerprint !== command.fingerprint) return record;
    // 서버가 같은 구판을 DRAFT로 읽고 더 최신 개정·후속 결정 불가를 확인했다.
    // 이미 받은 사건 영수증은 이 조건으로 해제하지 않는다.
    if (record.outcome === 'UNKNOWN' && !record.eventId && !view.decision_event && view.status === 'DRAFT'
        && view.latest_revision > command.revision && !view.permitted_actions.length
        && view.review_blockers.some(item => item.reason_code === 'PROCESS_CONTRACT_CONFLICT'))
      return { ...record, outcome: 'RESOLVED_OTHER', message: '서버가 이 구판의 후속 결정 불가를 확인했습니다. 내 요청 성공은 아니며 원기록을 보존하고 최신판을 독립 검토할 수 있습니다.' };
    if (!view.decision_event) return record;
    const event = view.decision_event;
    const same = (!record.eventId || record.eventId === event.event_id)
      && event.actor_id === command.actorId && event.rationale === command.rationale
      && event.decision === (command.decision === 'APPROVE' ? 'APPROVED' : 'REJECTED');
    return { ...record, outcome: same ? 'CONFIRMED' : 'RESOLVED_OTHER', eventId: event.event_id,
      message: same ? '서버의 같은 판본·지문·사용자·결정 이유로 반영을 확인했습니다. 앱 실행 승인은 별도입니다.'
        : '이 판본에는 다른 결정이 기록됐습니다. 내 요청 성공으로 표시하지 않으며 현재 계약을 다시 검토하세요.' };
  }
  function failure(error: unknown) {
    confirmation = '';
    const parsed = kitReviewError(error);
    emit({ loaded: false, confirmed: false, error: parsed,
      ...([401, 403, 404].includes(parsed.status) || parsed.reasonCode === 'CONTEXT_CHANGED'
        ? { view: null, current: null, history: [] } : {}) });
  }
  const model = {
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    activate() { active = true; },
    invalidate() { active = false; generation++; confirmation = ''; emit({ loaded: false, busy: false, view: null, current: null, history: [], confirmed: false, error: null }); },
    async load(revision?: number) {
      if (!live() || state.busy) return;
      const version = generation;
      confirmation = '';
      emit({ busy: true, loaded: false, confirmed: false, error: null, view: null, current: null, history: [] });
      try {
        const view = await api.read(revision);
        if (!live(version)) return;
        const current = observed(recordFor(view), view);
        save(current);
        emit({ view, current, history: history(), loaded: true });
      } catch (error) { if (live(version)) failure(error); }
      finally { if (live(version)) emit({ busy: false }); }
    },
    editRationale(rationale: string) {
      if (!live() || state.busy || !state.loaded || state.current?.outcome !== 'EDITING') return;
      confirmation = ''; save({ ...state.current, rationale }); emit({ confirmed: false });
    },
    editDecision(decision: '' | KitReviewDecision) {
      if (!['', 'APPROVE', 'REJECT'].includes(decision) || !live() || state.busy || !state.loaded || state.current?.outcome !== 'EDITING') return;
      confirmation = ''; save({ ...state.current, decision }); emit({ confirmed: false });
    },
    confirm(value: boolean) {
      if (!live() || state.busy || !state.loaded || state.current?.outcome !== 'EDITING') return;
      confirmation = value ? confirmKey() : ''; emit({ confirmed: !!confirmation });
    },
    canSubmit() {
      const row = state.current;
      return !!(live() && state.loaded && !state.busy && row?.outcome === 'EDITING' && row.decision
        && row.rationale.trim() && row.rationale.trim().length <= 4000 && state.view
        && state.confirmed && confirmation === confirmKey() && allowed(state.view, row.decision)
        && !state.history.some(pending));
    },
    async submit(): Promise<boolean> {
      if (!model.canSubmit() || !state.view || !state.current?.decision) return false;
      const original = state.current;
      const originalView = state.view;
      const version = generation;
      let sent: ReviewRecord | null = null;
      emit({ busy: true, error: null });
      try {
        const fresh = await api.read();
        if (!live(version)) return false;
        if (target(fresh) !== target(originalView) || !allowed(fresh, original.decision as KitReviewDecision))
          throw new KitReviewError('검토한 계약 판본이나 허용 행동이 바뀌었습니다. 입력을 보존했으니 다시 조회하세요.', 409, 'KIT_REVIEW_CHANGED');
        const command: KitReviewCommand = { revision: original.revision, fingerprint: original.fingerprint,
          actorId: fresh.principal_user_id, rationale: original.rationale.trim(), decision: original.decision as KitReviewDecision };
        sent = { ...original, command, outcome: 'UNKNOWN', message: '결정 요청 확인 중입니다. 같은 승인을 다시 보내지 않습니다.' };
        save(sent); confirmation = ''; emit({ confirmed: false });
        const receipt = await api.decide(command);
        if (!live(version)) return false;
        sent = { ...sent, outcome: 'RECORDED', eventId: receipt.event_id, message: '결정 기록 응답을 받았습니다. 같은 판본의 최신 증거를 확인합니다.' };
        save(sent);
        const view = await api.read(command.revision);
        if (!live(version)) return false;
        const checked = observed(sent, view); save(checked);
        emit({ view, current: checked, loaded: true });
        return checked.outcome === 'CONFIRMED';
      } catch (error) {
        if (!live(version)) return false;
        const parsed = kitReviewError(error);
        if (sent) {
          // 결정 POST의 명시 거절만 편집 상태로 돌린다. 기록 응답 후 GET 실패는 원 요청 보존.
          if (sent.outcome === 'UNKNOWN' && [400, 401, 403, 404, 409, 422].includes(parsed.status))
            save({ ...original, message: '서버가 결정을 거절했습니다. 최신 계약을 조회한 뒤 다시 검토하세요.' });
          else save({ ...sent, message: '결정 결과 확인이 필요합니다. 원래 판본·지문·이유를 보존했으며 조회만 제공합니다.' });
        }
        failure(parsed); return false;
      } finally { if (live(version)) emit({ busy: false }); }
    },
    async recheck(key: string) {
      if (!live() || state.busy) return;
      const record = history().find(row => row.key === key);
      if (!record || !pending(record)) return;
      const version = generation;
      emit({ busy: true, error: null, confirmed: false }); confirmation = '';
      try {
        const view = await api.read(record.revision);
        if (!live(version)) return;
        const checked = observed(record, view); save(checked);
        if (state.current?.key === key) emit({ current: checked, view, loaded: true });
      } catch (error) { if (live(version)) failure(error); }
      finally { if (live(version)) emit({ busy: false }); }
    },
  };
  return model;
}
export type KitContractReviewFlow = ReturnType<typeof createKitContractReviewFlow>;
