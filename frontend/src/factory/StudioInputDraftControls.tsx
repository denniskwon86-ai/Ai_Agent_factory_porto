// 입력 보관은 실행/승인과 분리한다. GET은 입력을 자동 덮어쓰지 않는다.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { createInputDraftApi, InputDraftApiError, sameInputDraftTarget } from '../lib/studioInputDraftApi';
import type { InputDraft, InputDraftContent, InputDraftSave, InputDraftSelector, InputDraftTarget } from '../lib/studioInputDraftApi';
import { studioIdentityKey, studioInputKey, studioInputMemory } from './studioInputMemory';

type ConsumeAttempt = { draftId: string; expected_revision: number; expected_digest: string; client_request_id: string; submission_id: string };
type ConsumptionProof = { command: ConsumeAttempt; result: InputDraft };
type SavedInput = { draft: InputDraft | null; attempt: InputDraftSave | null; savedContent: string; consumeAttempt?: ConsumeAttempt | null };
const empty: SavedInput = { draft: null, attempt: null, savedContent: '' };
const canonical = (value: unknown): string => JSON.stringify(value, (_key, item) =>
  item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item);
export interface StudioInputDraftControlsProps {
  projectId: string; selector: InputDraftSelector; expectedTarget?: Partial<InputDraftTarget>;
  content: InputDraftContent; onRestore: (content: InputDraftContent) => void;
  disabled?: boolean;
  /** 현재 본문/대상과 같은 서버 저장 초안만 노출한다. 조회/변경/미확정 시 null이다. */
  onDraftChange?: (draft: InputDraft | null) => void;
  onAccessLost?: () => void;
  /** 영수증의 원초안 판본. 이후 같은 대상의 새 초안을 소비하지 않는다. */
  expectedDraft?: Pick<InputDraft, 'draft_id' | 'revision' | 'digest'>;
  onConsumed?: (submissionId: string) => void;
  /** 서버가 확인한 결정 사건 또는 수정 접수 영수증만 사용한다. 임의 ID는 전달하지 않는다. */
  submissionId?: string;
  /** 처리 기록의 원대상만 사용. 새 차수 GET/편집/복원은 제공하지 않는다. */
  receiptOnly?: boolean;
}
function subscribeIdentity(listener: () => void) {
  const events = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
  events.forEach(name => window.addEventListener(name, listener));
  return () => events.forEach(name => window.removeEventListener(name, listener));
}
export function StudioInputDraftControls(props: StudioInputDraftControlsProps) {
  const serialized = canonical(props.selector);
  const identity = useSyncExternalStore(subscribeIdentity, studioIdentityKey, studioIdentityKey);
  const key = studioInputKey(props.projectId, 'server-input-draft', canonical([props.selector, props.expectedTarget]));
  return <DraftControls key={JSON.stringify([key, props.submissionId])} {...props} identity={identity} memoryKey={key} selectorJson={serialized} />;
}
function DraftControls({ projectId, content, onRestore, onDraftChange, onAccessLost, expectedDraft, onConsumed, disabled, submissionId, receiptOnly, expectedTarget, identity, memoryKey, selectorJson }: StudioInputDraftControlsProps & {
  identity: string; memoryKey: string; selectorJson: string;
}) {
  const api = useMemo(() => createInputDraftApi(projectId, identity), [projectId, identity]);
  const [local, setLocal] = useState<SavedInput>(() => studioInputMemory.get(memoryKey, empty));
  const proofKey = studioInputKey(projectId, 'input-draft-consumption', submissionId || '');
  const [proof, setProof] = useState<ConsumptionProof | null>(() => submissionId ? studioInputMemory.get(proofKey, null) : null);
  const [target, setTarget] = useState<InputDraftTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const active = useRef(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const update = (next: SavedInput) => { studioInputMemory.set(memoryKey, next); setLocal(next); };
  const current = () => active.current && identity === studioIdentityKey();
  const matches = (value: InputDraftTarget) => Object.entries(expectedTarget || {}).every(([k, v]) => value[k as keyof InputDraftTarget] === v);
  const accessFailure = (error: unknown) => {
    if (error instanceof InputDraftApiError && ([401, 403, 404].includes(error.status) || error.reasonCode === 'CONTEXT_CHANGED')) onAccessLost?.();
  };
  const matchesRef = (id: string, revision: number, digest: string) => !expectedDraft
    || (expectedDraft.draft_id === id && expectedDraft.revision === revision && expectedDraft.digest === digest);
  const consumed = !!submissionId && !!proof && proof.command.submission_id === submissionId
    && matchesRef(proof.command.draftId, proof.command.expected_revision, proof.command.expected_digest)
    && proof.result.draft_id === proof.command.draftId && proof.result.project_id === projectId
    && proof.result.revision === proof.command.expected_revision + 1 && matches(proof.result.target)
    && proof.result.status === 'CONSUMED' && !proof.result.restorable && proof.result.content === null;
  const originalDraft = !!local.draft && local.draft.project_id === projectId && matches(local.draft.target)
    && matchesRef(local.draft.draft_id, local.draft.revision, local.draft.digest)
    && (!local.consumeAttempt || (local.consumeAttempt.submission_id === submissionId
      && matchesRef(local.consumeAttempt.draftId, local.consumeAttempt.expected_revision, local.consumeAttempt.expected_digest)));
  const load = async () => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(''); setTarget(null);
    try {
      const result = await api.target(JSON.parse(selectorJson));
      if (!current()) return;
      if (!matches(result.target)) throw new InputDraftApiError('화면에서 검토한 입력 차수가 바뀌었습니다. 현재 결정을 다시 조회하세요.', 409, 'TARGET_CHANGED');
      setTarget(result.target);
      // 미확정 쓰기가 있으면 GET으로 원키/원본문을 바꾸지 않는다.
      update({ ...local, draft: local.attempt || local.consumeAttempt ? local.draft : result.draft,
        savedContent: result.draft?.restorable && result.draft.content ? canonical(result.draft.content) : '' });
      setMessage(result.draft ? '같은 대상에 저장된 초안이 있습니다. 불러오기는 현재 입력을 바꿉니다.' : '아직 서버에 저장한 초안이 없습니다.');
    } catch (e) { if (current()) { setError(e instanceof Error ? e.message : '초안을 조회하지 못했습니다.'); accessFailure(e); } }
    finally { locked.current = false; if (current()) setBusy(false); }
  };
  useEffect(() => {
    active.current = true;
    let disposed = false;
    queueMicrotask(() => { if (!disposed && !receiptOnly) void load(); });
    return () => { disposed = true; active.current = false; };
    // 입력 변경은 재조회/자동 덮어쓰기를 일으키지 않는다. 대상 변경은 부모 key로 재마운트한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);
  useEffect(() => {
    if (consumed && submissionId && active.current && identity === studioIdentityKey()) onConsumed?.(submissionId);
  }, [consumed, submissionId, onConsumed, identity]);
  const verifiedDraft = !receiptOnly && !busy && target && local.draft?.status === 'DRAFT'
    && local.draft.restorable && local.draft.project_id === projectId && local.draft.content
    && !local.attempt && !local.consumeAttempt && matches(local.draft.target)
    && sameInputDraftTarget(local.draft.target, target)
    && local.savedContent === canonical(content) && canonical(local.draft.content) === canonical(content)
    ? local.draft : null;
  useEffect(() => {
    if (!onDraftChange) return;
    onDraftChange(active.current && identity === studioIdentityKey() && verifiedDraft
      ? structuredClone(verifiedDraft) : null);
  }, [onDraftChange, verifiedDraft, identity]);
  useEffect(() => () => { onDraftChange?.(null); }, [onDraftChange]);
  const save = async () => {
    if (disabled || local.consumeAttempt || !target || locked.current || !current()) return;
    const body: InputDraftSave = local.attempt || { target, content: structuredClone(content),
      draft_id: local.draft?.draft_id || '', expected_revision: local.draft?.revision || 0,
      expected_digest: local.draft?.digest || '', client_request_id: crypto.randomUUID() };
    locked.current = true; setBusy(true); setError(''); update({ ...local, attempt: body });
    try {
      const result = await api.save(body);
      if (!current()) return;
      if (canonical(result.target) !== canonical(body.target) || !result.restorable || !result.content
          || result.content.text !== body.content.text || result.content.decision !== body.content.decision
          || canonical(result.content.selections || {}) !== canonical(body.content.selections || {})) throw new InputDraftApiError('저장된 입력이 요청과 일치하지 않습니다. 원요청을 보존합니다.', 503);
      update({ draft: result, attempt: null, savedContent: canonical(body.content) });
      setMessage(`서버 초안 저장 확인 · 판본 ${result.revision}. 실행·승인은 요청하지 않았습니다.`);
    } catch (e) {
      if (!current()) return;
      // 이전 UNKNOWN의 원본문·키는 후속 4xx에서도 보존한다.
      if (!local.attempt && e instanceof InputDraftApiError && [400, 401, 403, 404, 409, 422].includes(e.status)) update({ ...local, attempt: null });
      setError(e instanceof Error ? e.message : '저장 결과를 확인하지 못했습니다. 같은 요청 키를 보존합니다.');
      accessFailure(e);
    } finally { locked.current = false; if (current()) setBusy(false); }
  };
  const discard = async () => {
    if (!confirmDiscard || !target || !local.draft || local.attempt || local.consumeAttempt || disabled || locked.current || !current()) return;
    locked.current = true; setBusy(true); setError('');
    const original = local.draft;
    try {
      const result = await api.discard(original.draft_id, { expected_revision: original.revision,
        expected_digest: original.digest, client_request_id: crypto.randomUUID() });
      if (!current()) return;
      if (result.status !== 'DISCARDED') throw new InputDraftApiError('초안 폐기 반영을 확인하지 못했습니다.', 503);
      update(empty); setMessage('저장된 초안을 폐기 표시했습니다. 현재 화면의 입력은 유지합니다.'); setConfirmDiscard(false);
    } catch (e) { if (current()) { setTarget(null); setError(`${e instanceof Error ? e.message : '폐기 결과 확인 필요'} 자동 반복하지 않고 상태를 다시 조회하세요.`); accessFailure(e); } }
    finally { locked.current = false; if (current()) setBusy(false); }
  };
  const consume = async () => {
    if (!submissionId || consumed || !originalDraft || !local.draft || !local.draft.restorable || local.attempt || locked.current || !current()) return;
    const attempt = local.consumeAttempt || { draftId: local.draft.draft_id,
      expected_revision: local.draft.revision, expected_digest: local.draft.digest,
      client_request_id: crypto.randomUUID(), submission_id: submissionId };
    locked.current = true; setBusy(true); setError(''); update({ ...local, consumeAttempt: attempt });
    try {
      const { draftId, ...body } = attempt;
      const result = await api.consume(draftId, body);
      if (!current()) return;
      if (result.draft_id !== draftId || result.project_id !== projectId || result.revision !== attempt.expected_revision + 1
          || !sameInputDraftTarget(result.target, local.draft.target)
          || result.status !== 'CONSUMED' || result.restorable || result.content !== null) throw new InputDraftApiError('초안 사용 완료 반영을 확인하지 못했습니다.', 503);
      const verified = { command: attempt, result };
      studioInputMemory.set(proofKey, verified); setProof(verified);
      update({ ...empty, draft: result });
      setMessage('서버가 같은 입력·대상·접수 또는 결정 사건을 확인했습니다. 이 초안은 다시 불러오지 않습니다.');
    } catch (e) { if (current()) { setError(`${e instanceof Error ? e.message : '초안 사용 완료 확인 실패'} 원래 사건·요청 키를 보존합니다. 승인·실행을 다시 요청하지 않습니다.`); accessFailure(e); } }
    finally { locked.current = false; if (current()) setBusy(false); }
  };
  return <section className="studio-input-draft" aria-label="입력 초안 보관">
    <p role="status">{consumed || (!expectedDraft && local.draft?.status === 'CONSUMED') ? '제출 초안 사용 완료 확인'
      : receiptOnly ? '이 접수·결정에 저장했던 초안 · 원래 사건으로 사용 완료만 확인합니다.'
      : local.savedContent && local.savedContent === canonical(content) ? '현재 입력 서버 저장 확인' : '현재 입력 미저장'} · {message}</p>
    {error && <p role="alert">{error}</p>}
    {receiptOnly && expectedDraft && !consumed && !originalDraft && <p role="alert">이 접수에 결속된 원초안 판본을 확인하지 못했습니다. 다른 초안을 사용 완료로 바꾸거나 새 기준으로 복원하지 않습니다.</p>}
    {local.attempt && <p>이전 저장 결과가 미확정입니다. 아래 버튼은 원래 입력과 같은 요청 키만 재확인합니다.</p>}
    <div className="run-form-actions">
      {!receiptOnly && <button type="button" disabled={busy} onClick={() => void load()}>저장 상태 조회</button>}
      {!receiptOnly && <button type="button" disabled={disabled || busy || !target || !!local.consumeAttempt} onClick={() => void save()}>{local.attempt ? '같은 저장 요청 재확인' : '입력 초안 저장'}</button>}
      {!receiptOnly && local.draft?.restorable && <button type="button" disabled={disabled || busy || !target || !!local.attempt || !!local.consumeAttempt} onClick={() => {
        if (!local.draft?.content || !matches(local.draft.target)) return;
        onRestore(structuredClone(local.draft.content)); update({ ...local, savedContent: canonical(local.draft.content) });
      }}>저장한 입력 불러오기</button>}
      {!receiptOnly && local.draft?.restorable && <button type="button" disabled={disabled || busy || !target || !!local.attempt || !!local.consumeAttempt} onClick={() => setConfirmDiscard(v => !v)}>저장 초안 폐기…</button>}
      {submissionId && !consumed && local.draft?.restorable && <button type="button" disabled={busy || !!local.attempt || !originalDraft} onClick={() => void consume()}>{local.consumeAttempt ? '같은 사건의 초안 사용 완료 재확인' : '제출 사건으로 초안 사용 완료 기록'}</button>}
    </div>
    {confirmDiscard && <p>서버 초안은 다시 불러오지 않도록 폐기 표시합니다. <button type="button" disabled={disabled || busy || !target || !!local.attempt || !!local.consumeAttempt} onClick={() => void discard()}>확인하고 폐기</button></p>}
  </section>;
}
