// 메모리는 미확정 원요청을 보존하고, 접수 완료는 같은 서버 영수증 GET으로만 확인한다.
import { studioIdentityKey, studioInputKey, studioInputMemory } from '../factory/studioInputMemory';
import { createInputDraftApi, sameInputDraftTarget } from './studioInputDraftApi';
import type { InputDraft, InputDraftTarget } from './studioInputDraftApi';
import { createStudioRevisionApi, isRevisionTarget, matchesRevisionDraft, RevisionApiError, revisionError, sameRevisionCommand, sameRevisionRef } from './studioRevisionApi';
import type { RevisionCommand, RevisionReceipt, StudioRevisionApi } from './studioRevisionApi';

export type RevisionAttempt = { command: RevisionCommand; receipt: RevisionReceipt | null;
  outcome: 'UNKNOWN' | 'RECORDED' | 'CONFIRMED' | 'REJECTED'; message: string };
export type RevisionState = { authorized: boolean; busy: boolean; records: RevisionAttempt[]; error: RevisionApiError | null };
const pending = (record: RevisionAttempt) => ['UNKNOWN', 'RECORDED'].includes(record.outcome);
export function createStudioRevisionFlow(projectId: string, taskId: string,
  api: StudioRevisionApi = createStudioRevisionApi(projectId), inputApi = createInputDraftApi(projectId), identity = studioIdentityKey()) {
  let state: RevisionState = { authorized: false, busy: false, records: [], error: null };
  let active = false, generation = 0;
  let target: InputDraftTarget | null = null;
  const recoveredKeys = new Set<string>();
  const listeners = new Set<() => void>();
  const live = (version = generation) => active && version === generation && identity === studioIdentityKey();
  const records = () => studioInputMemory.projectValues<RevisionAttempt>(projectId, 'revision-request');
  const emit = (patch: Partial<RevisionState>) => { state = { ...state, ...patch }; listeners.forEach(listener => listener()); };
  const save = (record: RevisionAttempt) => {
    if (!live()) return;
    studioInputMemory.set(studioInputKey(projectId, 'revision-request', record.command.client_request_id), structuredClone(record));
    emit({ records: state.authorized ? records() : [] });
  };
  const fail = (error: unknown) => {
    const value = revisionError(error);
    const hidden = [401, 403, 404].includes(value.status) || value.reasonCode === 'CONTEXT_CHANGED';
    emit({ error: value, ...(hidden ? { authorized: false, records: [] } : {}) });
  };
  const commandFor = (selected: InputDraftTarget, feedback: string, draft: InputDraft): RevisionCommand => ({
    client_request_id: '', target: structuredClone(selected), feedback: feedback.trim(),
    input_draft: { draft_id: draft.draft_id, revision: draft.revision, digest: draft.digest },
  });
  const model = {
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    hasRecovery: () => live() && records().some(record => record.outcome !== 'REJECTED'),
    activate() { active = true; },
    invalidate() { active = false; generation++; target = null; recoveredKeys.clear(); emit({ authorized: false, busy: false, records: [], error: null }); },
    authorize(selected: InputDraftTarget) {
      if (!live() || !isRevisionTarget(selected) || selected.task_id !== taskId) return;
      target = structuredClone(selected); emit({ authorized: true, records: records(), error: null });
    },
    canSubmit(selected: InputDraftTarget, feedback: string, draft: InputDraft | null) {
      if (!live() || !state.authorized || state.busy || !target || !isRevisionTarget(selected)
          || !sameInputDraftTarget(target, selected) || !feedback.trim() || feedback.trim().length > 32000
          || !matchesRevisionDraft(projectId, selected, feedback, draft)) return false;
      const command = commandFor(selected, feedback, draft);
      return !records().some(record => pending(record) || record.outcome === 'CONFIRMED' && sameRevisionCommand(record.command, command));
    },
    async submit(selected: InputDraftTarget, feedback: string, draft: InputDraft | null): Promise<RevisionReceipt | null> {
      if (!model.canSubmit(selected, feedback, draft) || !draft) return null;
      const version = generation;
      const command = commandFor(selected, feedback, draft);
      let attempt: RevisionAttempt | null = null;
      emit({ busy: true, error: null });
      try {
        const fresh = await inputApi.target({ kind: 'REVISION_REQUEST', task_id: taskId });
        if (!live(version)) return null;
        if (!sameInputDraftTarget(fresh.target, selected) || !matchesRevisionDraft(projectId, selected, feedback, fresh.draft)
            || !sameRevisionRef(fresh.draft, command.input_draft))
          throw new RevisionApiError('산출물 또는 저장한 초안이 바뀌었습니다. 의견을 보존했으니 기준과 초안을 다시 확인하세요.', 409, 'REVISION_BASIS_CHANGED');
        // 다른 패널의 첫 await 이후 예약도 다시 확인한다.
        if (records().some(record => pending(record) || record.outcome === 'CONFIRMED' && sameRevisionCommand(record.command, command)))
          throw new RevisionApiError('이미 접수됐거나 결과를 확인 중인 요청입니다.', 409, 'REVISION_ALREADY_PENDING');
        command.client_request_id = crypto.randomUUID();
        attempt = { command, receipt: null, outcome: 'UNKNOWN', message: '원래 요청을 보존했습니다. 접수 결과 확인 전 자동 재전송하지 않습니다.' };
        save(attempt);
        const receipt = await api.submit(command);
        if (!live(version)) return null;
        attempt = { ...attempt, receipt, outcome: 'RECORDED', message: '접수 응답을 받았습니다. 같은 요청의 저장 결과를 조회합니다.' }; save(attempt);
        const verified = await api.read(command, receipt);
        if (!live(version)) return null;
        save({ ...attempt, receipt: verified, outcome: 'CONFIRMED', message: '수정 작업 접수를 확인했습니다. 제작은 아직 시작하지 않았습니다.' });
        return verified;
      } catch (error) {
        if (!live(version)) return null;
        const parsed = revisionError(error);
        if (attempt?.outcome === 'UNKNOWN' && [400, 401, 403, 404, 409, 422].includes(parsed.status))
          save({ ...attempt, outcome: 'REJECTED', message: '서버가 접수를 거절했습니다. 기준과 초안을 다시 확인하세요.' });
        fail(parsed); return null;
      } finally { if (live(version)) emit({ busy: false }); }
    },
    async recheck(requestId: string): Promise<RevisionReceipt | null> {
      if (!live() || !state.authorized || state.busy) return null;
      const attempt = records().find(record => record.command.client_request_id === requestId);
      if (!attempt || !pending(attempt)) return null;
      const version = generation; emit({ busy: true, error: null });
      try {
        const receipt = await api.read(attempt.command, attempt.receipt || undefined);
        if (!live(version)) return null;
        save({ ...attempt, receipt, outcome: 'CONFIRMED', message: '원래 요청의 저장된 접수를 확인했습니다. 새 작업을 중복 생성하지 않았습니다.' });
        return receipt;
      } catch (error) { if (live(version)) fail(error); return null; }
      finally { if (live(version)) emit({ busy: false }); }
    },
    async recover(): Promise<RevisionReceipt | null> {
      if (!live() || state.busy) return null;
      const available = records().filter(record => record.outcome !== 'REJECTED');
      if (available.length && available.every(record => recoveredKeys.has(record.command.client_request_id))) recoveredKeys.clear();
      const unseen = available.filter(record => !recoveredKeys.has(record.command.client_request_id));
      const attempt = unseen.find(pending) || unseen.find(record => record.outcome === 'CONFIRMED');
      if (!attempt) return null;
      const version = generation;
      // 실패한 한 요청도 다음 기록의 조회를 막지 않는다. 이것은 성공 표시가 아니라 순회 위치다.
      recoveredKeys.add(attempt.command.client_request_id);
      // 현재 산출물 조회 실패는 과거 영수증 GET을 막지 않는다. 검증 전 과거 본문은 숨긴다.
      emit({ busy: true, records: [], error: null });
      try {
        const receipt = await api.read(attempt.command, attempt.receipt || undefined);
        if (!live(version)) return null;
        const verified: RevisionAttempt = { ...attempt, receipt, outcome: 'CONFIRMED',
          message: '원래 요청의 저장된 접수를 확인했습니다. 다른 기록은 이전 요청 접수 확인을 다시 누르면 순서대로 조회합니다. 새 요청 제출은 별도입니다.' };
        save(verified);
        // 이 GET으로 권한·고정 영수증이 확인된 한 건만 공개한다. 새 제출 권한은 올리지 않는다.
        emit({ records: [verified] });
        return receipt;
      } catch (error) { if (live(version)) fail(error); return null; }
      finally { if (live(version)) emit({ busy: false }); }
    },
  };
  return model;
}
export type StudioRevisionFlow = ReturnType<typeof createStudioRevisionFlow>;
