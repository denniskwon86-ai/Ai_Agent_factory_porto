// B5: 저장한 의견·산출물 기준으로 접수하고, 영수증 확인과 초안 사용 완료를 분리한다.
import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { createInputDraftApi, InputDraftApiError, sameInputDraftTarget } from '../lib/studioInputDraftApi';
import type { InputDraft, InputDraftSelector, InputDraftTarget } from '../lib/studioInputDraftApi';
import { createStudioRevisionFlow } from '../lib/studioRevisionFlow';
import { isRevisionTarget, type RevisionReceipt } from '../lib/studioRevisionApi';
import { StudioInputDraftControls } from './StudioInputDraftControls';
import { studioIdentityKey, studioInputKey, studioInputMemory } from './studioInputMemory';

export interface RevisionRequestEditorProps {
  projectId: string;
  taskId: string;
  disabled?: boolean;
  onSubmitted?: (receipt: RevisionReceipt) => void | Promise<void>;
  /** 부모는 현재 프로젝트 메모리를 다시 읽어 다른 쓰기만 잠근다. */
  onStateChange?: () => void;
}
type BoundInput = { target: InputDraftTarget; memoryKey: string; text: string };
const EVENTS = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
const OUTCOME_LABEL = {
  UNKNOWN: '접수 결과 미확정', RECORDED: '접수 응답 수신 · 저장된 영수증 확인 필요',
  CONFIRMED: '서버 접수 확인 · 실행 전', REJECTED: '접수 거절 · 기준 재확인 필요',
};

function subscribeIdentity(listener: () => void) {
  EVENTS.forEach(name => window.addEventListener(name, listener));
  return () => EVENTS.forEach(name => window.removeEventListener(name, listener));
}
// 메모리 키는 전체 대상 필드를 고정 순서로 직렬화한다. 옛 의견을 새 산출물에 복사하지 않는다.
function fullTarget(value: InputDraftTarget, taskId: string): InputDraftTarget {
  if (!isRevisionTarget(value) || value.task_id !== taskId)
    throw new InputDraftApiError('수정할 산출물의 전체 기준을 확인하지 못했습니다. 다시 조회해 주세요.', 409, 'TARGET_CHANGED');
  return { kind: value.kind, task_id: value.task_id, decision_kind: value.decision_kind,
    request_id: value.request_id, target_digest: value.target_digest, subject_id: value.subject_id };
}
const selectorFor = (target: InputDraftTarget): InputDraftSelector => ({ kind: 'REVISION_REQUEST', task_id: target.task_id });

export function RevisionRequestEditor(props: RevisionRequestEditorProps) {
  const identity = useSyncExternalStore(subscribeIdentity, studioIdentityKey, studioIdentityKey);
  return <RevisionEditor key={JSON.stringify([identity, props.projectId, props.taskId])} {...props} identity={identity} />;
}

function RevisionEditor({ projectId, taskId, disabled = false, onSubmitted, onStateChange, identity }:
  RevisionRequestEditorProps & { identity: string }) {
  const api = useMemo(() => createInputDraftApi(projectId, identity), [projectId, identity]);
  const flow = useMemo(() => createStudioRevisionFlow(projectId, taskId, undefined, api, identity), [projectId, taskId, api, identity]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const [input, setInput] = useState<BoundInput | null>(null);
  const [savedDraft, setSavedDraft] = useState<InputDraft | null>(null);
  const [composition, setComposition] = useState<Record<string, string[]>>({});
  const [consumedIds, setConsumedIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('수정할 산출물 기준을 확인하는 중입니다.');
  const active = useRef(false);
  const locked = useRef(false);
  const generation = useRef(0);
  const disabledRef = useRef(disabled);
  const textId = useId();
  const hintId = useId();
  useEffect(() => { disabledRef.current = disabled; }, [disabled]);
  const current = (version = generation.current) =>
    active.current && version === generation.current && identity === studioIdentityKey();
  const accessLost = useCallback(() => {
    if (!active.current || identity !== studioIdentityKey()) return;
    generation.current++; flow.invalidate(); flow.activate(); setSavedDraft(null);
    setError('입력 초안에 접근할 권한을 확인하지 못했습니다. 본문과 기록을 숨겼습니다. 현재 기준 또는 원래 접수증을 다시 조회하세요.');
  }, [flow, identity]);
  const recordConsumed = useCallback((submissionId: string) => {
    if (!active.current || identity !== studioIdentityKey()) return;
    setConsumedIds(previous => previous.includes(submissionId) ? previous : [...previous, submissionId]);
  }, [identity]);

  const refresh = async () => {
    if (locked.current || state.busy || !current()) return;
    const version = ++generation.current;
    locked.current = true; setBusy(true); setError(''); setSavedDraft(null);
    if (input) studioInputMemory.set(input.memoryKey, input.text);
    flow.invalidate(); flow.activate();
    try {
      if (!projectId || !taskId) throw new InputDraftApiError('프로젝트와 작업을 먼저 선택해 주세요.', 422);
      const result = await api.target({ kind: 'REVISION_REQUEST', task_id: taskId });
      if (!current(version)) return;
      const target = fullTarget(result.target, taskId);
      const memoryKey = studioInputKey(projectId, 'revision-input', JSON.stringify(target));
      const restored = studioInputMemory.get<string>(memoryKey, '');
      const changed = input && !sameInputDraftTarget(input.target, target);
      setInput({ target, memoryKey, text: typeof restored === 'string' ? restored : '' });
      // 현재 GET의 권한·대상 검증이 끝난 뒤에만 과거 접수 기록을 표시한다.
      flow.authorize(target);
      setMessage(changed
        ? '현재 기준으로 전환했습니다. 이전 의견은 이전 기준에 보관하며 새 기준에 복사하지 않습니다.'
        : '산출물 기준을 확인했습니다. 같은 기준에서 작성하던 의견만 복원합니다.');
    } catch (e) {
      if (current(version)) {
        flow.invalidate(); flow.activate();
        setError(e instanceof Error ? e.message : '기준을 조회하지 못했습니다. 기존 의견은 보존하고 화면에서 숨깁니다.');
      }
    } finally {
      locked.current = false;
      if (active.current) setBusy(false);
    }
  };

  useEffect(() => {
    active.current = true; flow.activate();
    let disposed = false;
    const unsubscribe = flow.subscribe(() => { if (identity === studioIdentityKey()) onStateChange?.(); });
    const invalidate = () => {
      generation.current++; flow.invalidate(); flow.activate(); setSavedDraft(null);
      setMessage('사용자·문맥이 갱신되었습니다. 현재 기준을 다시 조회해 주세요.');
    };
    EVENTS.forEach(name => window.addEventListener(name, invalidate));
    queueMicrotask(() => { if (!disposed) void refresh(); });
    return () => {
      disposed = true; active.current = false; generation.current++;
      unsubscribe(); EVENTS.forEach(name => window.removeEventListener(name, invalidate)); flow.invalidate();
    };
    // 부모 재렌더·입력 변경은 기준을 재조회하거나 의견을 덮어쓰지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow, identity, onStateChange]);

  const visible = state.authorized && input;
  const pending = state.records.some(record => record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED');
  const composeKey = input ? studioInputKey(projectId, 'revision-compose', JSON.stringify(input.target)) : '';
  const startedAfter = composition[composeKey] ?? studioInputMemory.get<string[]>(composeKey, []);
  const acceptedRecords = visible ? state.records.filter(record => record.outcome === 'CONFIRMED'
    && record.receipt && sameInputDraftTarget(record.command.target, visible.target)) : [];
  const acceptedTarget = acceptedRecords.some(record => !startedAfter.includes(record.command.client_request_id));
  const canStartOpinion = acceptedTarget && acceptedRecords.every(record => record.receipt && consumedIds.includes(record.receipt.submission_id));
  const writingLocked = disabled || busy || state.busy || pending || acceptedTarget || !visible;
  const startOpinion = () => {
    if (!input || !canStartOpinion || disabledRef.current || busy || state.busy || pending || locked.current || !current()) return;
    const previous = acceptedRecords.map(record => record.command.client_request_id);
    studioInputMemory.set(composeKey, previous);
    setComposition(value => ({ ...value, [composeKey]: previous }));
    studioInputMemory.set(input.memoryKey, ''); setInput({ ...input, text: '' }); setSavedDraft(null); setError('');
    setMessage('같은 산출물 기준에 새 의견을 시작합니다. 이전 의견·영수증은 처리 기록에 보존하고 본문을 복사하지 않습니다. 새 초안을 저장한 뒤 접수하세요.');
  };
  const updateText = (text: string) => {
    if (!input || writingLocked || disabledRef.current || locked.current || !current()) return;
    studioInputMemory.set(input.memoryKey, text); setSavedDraft(null); setInput({ ...input, text });
  };
  const notifyReceipt = async (receipt: RevisionReceipt, version: number) => {
    if (!current(version)) return;
    setMessage('수정 요청의 서버 접수를 확인했습니다. 제작은 시작하지 않았습니다. 아래에서 초안 사용 완료를 별도로 기록하세요.');
    try { await onSubmitted?.(receipt); }
    catch (e) {
      if (current(version)) setError('접수는 확인됐지만 작업 목록 새로고침을 확인하지 못했습니다. 접수 요청은 다시 보내지 마세요. '
        + (e instanceof Error ? e.message : ''));
    }
  };
  const submit = async () => {
    if (!input || writingLocked || disabledRef.current || locked.current || !current()
        || !flow.canSubmit(input.target, input.text, savedDraft)) return;
    const version = generation.current;
    locked.current = true; setBusy(true); setError('');
    studioInputMemory.set(input.memoryKey, input.text);
    try {
      const receipt = await flow.submit(input.target, input.text, savedDraft);
      if (receipt) await notifyReceipt(receipt, version);
    } catch (e) {
      if (current(version)) setError(e instanceof Error ? e.message : '접수 결과 확인이 필요합니다. 자동 재전송하지 않습니다.');
    } finally { locked.current = false; if (active.current) setBusy(false); }
  };
  const recheck = async (requestId: string) => {
    if (!state.authorized || locked.current || state.busy || !current()) return;
    const version = generation.current;
    locked.current = true; setBusy(true); setError('');
    try {
      const receipt = await flow.recheck(requestId);
      if (receipt) await notifyReceipt(receipt, version);
    } catch (e) {
      if (current(version)) setError(e instanceof Error ? e.message : '접수 조회에 실패했습니다. 원래 요청을 보존합니다.');
    } finally { locked.current = false; if (active.current) setBusy(false); }
  };
  const recover = async () => {
    if (locked.current || state.busy || !current() || !flow.hasRecovery()) return;
    const version = generation.current;
    locked.current = true; setBusy(true); setError('');
    try {
      const receipt = await flow.recover();
      if (receipt) await notifyReceipt(receipt, version);
    } catch (e) {
      if (current(version)) setError(e instanceof Error ? e.message : '이전 접수증을 확인하지 못했습니다. 원래 요청을 보존합니다.');
    } finally { locked.current = false; if (active.current) setBusy(false); }
  };

  return <section className="run-form" aria-label="수정 요청 작성" aria-busy={busy || state.busy}>
    <label htmlFor={textId}>어떤 부분을 고칠까요?</label>
    <textarea id={textId} rows={4} maxLength={32000} value={visible ? visible.text : ''} aria-describedby={hintId}
      placeholder={visible ? '바꾸고 싶은 부분과 기대하는 결과를 적어 주세요.' : '산출물 기준과 권한 확인 후 입력할 수 있습니다.'}
      disabled={writingLocked} onChange={event => updateText(event.target.value)} />
    <p id={hintId} className="run-hint">① 입력 초안 저장 → ② 수정 요청 접수 → ③ 저장된 접수증 확인 → ④ 초안 사용 완료.
      접수는 실행이나 수정 완료가 아니며 자동으로 제작을 시작하지 않습니다.</p>
    <p className="run-hint">저장·제출에는 앞뒤 공백을 뺀 같은 의견을 사용합니다. 미저장 입력은 같은 로그인·문맥의 메모리에만 남습니다.</p>
    {(error || state.error) && <p role="alert">{error || state.error?.message}</p>}
    {message && <p role="status">{message}</p>}
    <div className="run-form-actions">
      <button type="button" disabled={busy || state.busy} onClick={() => void refresh()}>현재 기준 다시조회</button>
      {!state.authorized && flow.hasRecovery() && <button type="button" disabled={busy || state.busy}
        onClick={() => void recover()}>이전 요청 접수 확인 · GET 조회만</button>}
    </div>
    {visible && <>
      <details><summary>현재 의견의 전체 기준 보기</summary>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(visible.target, null, 2)}</pre>
      </details>
      {!acceptedTarget && <StudioInputDraftControls key={visible.memoryKey} projectId={projectId}
        selector={selectorFor(visible.target)} expectedTarget={visible.target}
        content={{ text: visible.text.trim(), decision: '', selections: {} }} onDraftChange={setSavedDraft} onAccessLost={accessLost}
        onRestore={content => updateText(content.text)} disabled={writingLocked} />}
      {acceptedTarget ? <p role="status">이 산출물 기준으로 접수가 확인됐습니다. 원초안을 덮어쓰지 않고 아래 처리 기록에서 사용 완료를 기록하세요.</p>
        : !savedDraft && <p className="run-hint">현재 의견과 기준이 일치하는 서버 저장 초안이 있어야 접수할 수 있습니다.</p>}
      {acceptedTarget && <button type="button" disabled={!canStartOpinion || disabled || busy || state.busy || pending}
        onClick={startOpinion}>같은 기준에 새 의견 작성</button>}
      {acceptedTarget && !canStartOpinion && <p className="run-hint">확인된 원초안의 사용 완료를 먼저 기록하면 새 의견을 작성할 수 있습니다.</p>}
    </>}
    <div className="run-form-actions">
      <button type="button" className="primary-button"
        disabled={writingLocked || !input || !flow.canSubmit(input.target, input.text, savedDraft)}
        onClick={() => void submit()}>저장한 초안으로 수정 요청 접수</button>
    </div>
    {state.records.length > 0 && <section aria-label="수정 요청 처리 기록">
      <h4>수정 요청 처리 기록</h4>
      <p className="run-hint">미확정 요청은 원래 본문·키로 조회만 합니다. 이전 기준의 기록을 새 산출물에 복사하지 않습니다.</p>
      {state.records.map(record => <article key={record.command.client_request_id} className="process-safety"
        style={{ marginTop: 10, overflowWrap: 'anywhere' }}>
        <strong>{OUTCOME_LABEL[record.outcome]}</strong>
        <p role="status">{record.message}</p>
        <p>요청 ID: <code>{record.command.client_request_id}</code></p>
        <p>기준 작업: {record.command.target.task_id} · 초안 {record.command.input_draft.revision}판</p>
        <details><summary>원래 의견·산출물 기준</summary>
          <p style={{ whiteSpace: 'pre-wrap' }}>{record.command.feedback}</p>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(record.command.target, null, 2)}</pre>
        </details>
        {(record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED') && <button type="button"
          disabled={busy || state.busy} onClick={() => void recheck(record.command.client_request_id)}>이 요청의 접수 상태 확인 · GET 조회만</button>}
        {record.outcome === 'CONFIRMED' && record.receipt && <>
          <p>접수증: <code>{record.receipt.submission_id}</code> · 생성된 수정 작업: {record.receipt.task_id}</p>
          <p>접수 시각: {record.receipt.created_at} · 서버 접수 확인, 실행은 시작하지 않음</p>
          {/* 작성 때와 동일한 selector + expectedTarget 키로 원래 저장 초안을 재사용한다. */}
          <StudioInputDraftControls projectId={projectId} selector={selectorFor(record.command.target)}
            expectedTarget={record.command.target} expectedDraft={record.receipt.input_draft}
            content={{ text: record.command.feedback, decision: '', selections: {} }}
            onRestore={() => undefined} onAccessLost={accessLost} onConsumed={recordConsumed}
            disabled receiptOnly submissionId={record.receipt.submission_id} />
        </>}
      </article>)}
    </section>}
  </section>;
}
