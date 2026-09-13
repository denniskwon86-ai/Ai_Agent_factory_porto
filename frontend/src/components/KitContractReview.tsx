// B5: 서버가 확인한 v2 계약만 검토한다. 계약 승인과 데이터 준비/앱 제작은 다른 단계다.
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { createKitContractReviewApi, type KitContractReviewApi } from '../lib/kitContractReviewApi';
import { createKitContractReviewFlow, type KitReviewState, type ReviewRecord } from '../lib/kitContractReviewFlow';
import { studioIdentityKey } from '../factory/studioInputMemory';

export interface KitContractReviewProps {
  instanceId: string;
  appId: string;
  onChanged?: () => void;
  onVisibilityLost?: () => void;
  /** 합성/SSR 검사에서는 운영 API로 fallback하지 않는 전용 대역을 주입한다. */
  apiFactory?: (instanceId: string, appId: string, identity?: string) => KitContractReviewApi;
}

const CONTEXT_EVENTS = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
const STATUS_LABEL: Record<string, string> = {
  DRAFT: '검토 대기', APPROVED: '승인됨', REJECTED: '반려됨', SUPERSEDED: '이전 판 · 대체됨',
};
const OUTCOME_LABEL: Record<string, string> = {
  EDITING: '작성 중 · 미제출', UNKNOWN: '제출 결과 미확정', RECORDED: '사건 기록됨 · 반영 확인 필요',
  CONFIRMED: '서버 반영 확인', RESOLVED_OTHER: '다른 결정 또는 새 판 확인 · 내 제출 성공이 아님',
};

function subscribeContext(listener: () => void) {
  CONTEXT_EVENTS.forEach(name => window.addEventListener(name, listener));
  return () => CONTEXT_EVENTS.forEach(name => window.removeEventListener(name, listener));
}

export function KitContractReview(props: KitContractReviewProps) {
  const identity = useSyncExternalStore(subscribeContext, studioIdentityKey, studioIdentityKey);
  return <ReviewContent key={JSON.stringify([identity, props.instanceId, props.appId])}
    {...props} identity={identity} />;
}

function ReviewContent({ instanceId, appId, onChanged, onVisibilityLost, apiFactory = createKitContractReviewApi, identity }:
  KitContractReviewProps & { identity: string }) {
  const api = useMemo(() => apiFactory(instanceId, appId, identity), [apiFactory, instanceId, appId, identity]);
  const flow = useMemo(() => createKitContractReviewFlow(instanceId, appId, api, identity), [instanceId, appId, api, identity]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const active = useRef(false);
  const [localError, setLocalError] = useState('');
  const currentContext = () => active.current && identity === studioIdentityKey();

  useEffect(() => {
    active.current = true;
    flow.activate();
    let disposed = false;
    const invalidate = () => {
      flow.invalidate();
      // 같은 값의 문맥 갱신 이벤트는 wrapper key가 바뀌지 않는다. 비활성 상태로 굳히지 않는다.
      if (identity === studioIdentityKey()) { flow.activate(); void flow.load(); }
    };
    CONTEXT_EVENTS.forEach(name => window.addEventListener(name, invalidate));
    queueMicrotask(() => { if (!disposed) void flow.load(); });
    return () => {
      disposed = true; active.current = false;
      CONTEXT_EVENTS.forEach(name => window.removeEventListener(name, invalidate));
      flow.invalidate();
    };
  }, [flow, identity]);

  useEffect(() => {
    if (active.current && identity === studioIdentityKey() && state.error
        && ([401, 403, 404].includes(state.error.status) || state.error.reasonCode === 'CONTEXT_CHANGED'))
      onVisibilityLost?.();
  }, [state.error, identity, onVisibilityLost]);

  const record = state.current;
  const records = record ? [record, ...state.history.filter(item => item.key !== record.key)] : state.history;
  const hasInput = records.some(item => !!item.rationale || item.outcome === 'UNKNOWN' || item.outcome === 'RECORDED');
  useEffect(() => {
    if (!hasInput) return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [hasInput]);

  const run = async (work: () => Promise<unknown>) => {
    if (!currentContext() || state.busy) return;
    setLocalError('');
    try { await work(); }
    catch (e) {
      if (currentContext()) setLocalError(e instanceof Error ? e.message : '처리 결과를 확인하지 못했습니다. 입력과 원래 요청을 보존합니다.');
    }
  };
  const submit = () => run(async () => {
    // true는 flow가 같은 계약·결정 사건의 반영까지 확인한 경우다. 불명 응답은 재전송하지 않는다.
    if (await flow.submit() && currentContext()) onChanged?.();
  });

  return <KitContractReviewView state={state} canSubmit={flow.canSubmit()} localError={localError}
    onLoad={() => void run(() => flow.load())} onSubmit={() => void submit()}
    onRecheck={key => void run(() => flow.recheck(key))}
    onRationale={flow.editRationale} onDecision={flow.editDecision} onConfirm={flow.confirm} />;
}

/** 실제 화면과 같은 마크업을 합성 상태로 SSR 검사한다. 권한/결정은 바깥 flow가 맡는다. */
export interface KitContractReviewViewProps {
  state: KitReviewState;
  canSubmit: boolean;
  localError?: string;
  onLoad: () => void;
  onSubmit: () => void;
  onRecheck: (key: string) => void;
  onRationale: (text: string) => void;
  onDecision: (decision: ReviewRecord['decision']) => void;
  onConfirm: (confirmed: boolean) => void;
}

export function KitContractReviewView({ state, canSubmit, localError = '', onLoad, onSubmit, onRecheck,
  onRationale, onDecision, onConfirm }: KitContractReviewViewProps) {
  const rationaleId = useId();
  const decisionId = useId();
  const confirmId = useId();
  const record = state.current;
  const records = record ? [record, ...state.history.filter(item => item.key !== record.key)] : state.history;
  const view = state.loaded ? state.view : null;
  const editable = !!view && view.status === 'DRAFT' && view.revision === view.latest_revision
    && record?.outcome === 'EDITING' && record.revision === view.revision
    && record.fingerprint === view.semantic_fingerprint && !state.busy;
  const approveAllowed = !!view?.permitted_actions.includes('approve');
  const rejectAllowed = !!view?.permitted_actions.includes('reject');
  const selectionAllowed = record?.decision === 'APPROVE' ? approveAllowed
    : record?.decision === 'REJECT' ? rejectAllowed : false;

  return <section className="process-review" aria-label="2.0 업무 앱 계약 검토" aria-busy={state.busy}
    style={{ border: '1px solid var(--surface-border)', borderRadius: 8, padding: 14, display: 'grid', gap: 10 }}>
    <div className="run-form-actions" style={{ justifyContent: 'space-between' }}>
      <strong>업무 앱 계약 검토 · 2.0</strong>
      <button type="button" disabled={state.busy} onClick={onLoad}>최신 계약 조회</button>
    </div>
    <p className="run-hint">계약 작성자와 다른 적격 사용자가 원문을 검토합니다. 데이터가 아직 준비되지 않아도 계약을 읽을 수 있으며,
      승인만으로 데이터 권한이나 앱 실행 권한이 생기지 않습니다.</p>
    {state.busy && <p role="status">계약과 처리 결과를 확인하는 중…</p>}
    {(state.error || localError) && <div role="alert" className="process-error">
      {state.error?.message || localError}
      <p className="run-hint">확인하지 못한 상태를 계약 없음이나 승인 완료로 표시하지 않습니다. 자동으로 다시 제출하지 않습니다.</p>
    </div>}
    {!view && <p role="status">{state.busy || !state.loaded
      ? '현재 문맥의 계약 원문을 확인한 뒤 검토할 수 있습니다.'
      : '현재 문맥에서 검토할 계약을 확인하지 못했습니다. 최신 계약을 조회해 주세요.'}</p>}

    {view && <>
      <div style={{ display: 'grid', gap: 4, overflowWrap: 'anywhere' }} aria-label="계약 요약">
        <strong>{STATUS_LABEL[view.status] || '상태 확인 필요'} · {view.revision}판</strong>
        <span>앱 {view.app_id} · 업무키트 적용본 {view.instance_id}</span>
        <span>현재 조회 {view.revision}판 / 서버 최신 {view.latest_revision}판</span>
        <span>작성자: {view.drafted_by || '확인 필요'}</span>
        <span>현재 사용자: {view.principal_user_id || '확인 필요'}</span>
        {view.approved_by && <span>승인자: {view.approved_by}</span>}
        <span>계약 지문: <code>{view.semantic_fingerprint}</code></span>
      </div>
      {view.revision !== view.latest_revision && <p role="alert">이 계약은 최신 판이 아닙니다. 이전 판의 의견을 새 판에 복사하거나 제출하지 않습니다.</p>}
      {view.drafted_by && view.drafted_by.trim().toLowerCase() === view.principal_user_id.trim().toLowerCase()
        && <p className="run-hint">현재 사용자가 계약 작성자입니다. 다른 적격 검토자가 승인·반려해야 합니다.</p>}
      <details open><summary>계약 원문 전체 보기</summary>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 420, overflow: 'auto', fontSize: 12 }}>
          {JSON.stringify(view.contract, null, 2)}
        </pre>
      </details>
      <section aria-label="서버 검토 제한 사항">
        <strong>검토 제한 사항</strong>
        {view.review_blockers.length ? <ul>{view.review_blockers.map((blocker, index) =>
          <li key={`${blocker.reason_code}-${index}`}>{blocker.message} <small>({blocker.reason_code})</small></li>)}</ul>
          : <p className="run-hint">서버가 전달한 검토 제한 사항이 없습니다. 실제 제출 시 현재 권한과 계약 판본을 다시 확인합니다.</p>}
        {!approveAllowed && !rejectAllowed && <p className="run-hint">현재 사용자·계약 상태에서 가능한 승인/반려 행동이 없습니다.</p>}
      </section>
      {view.decision_event && <section aria-label="서버에서 확인한 결정" className="process-safety">
        <strong>{view.decision_event.decision === 'APPROVED' ? '승인 사건 확인' : '반려 사건 확인'}</strong>
        <p>처리자: {view.decision_event.actor_id}</p>
        <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>사유: {view.decision_event.rationale}</p>
        <p style={{ overflowWrap: 'anywhere' }}>사건 ID: <code>{view.decision_event.event_id}</code></p>
        <p className="run-hint">계약 결정 확인입니다. 데이터 준비나 앱 제작 완료를 뜻하지 않습니다.</p>
      </section>}

      {record && <div style={{ display: 'grid', gap: 9 }}>
        <label htmlFor={decisionId}>검토 결과</label>
        <select id={decisionId} value={record.decision} disabled={!editable}
          onChange={event => {
            if (event.target.value === '' || event.target.value === 'APPROVE' || event.target.value === 'REJECT') onDecision(event.target.value);
          }}>
          <option value="">아직 선택하지 않음</option>
          <option value="APPROVE" disabled={!approveAllowed}>승인</option>
          <option value="REJECT" disabled={!rejectAllowed}>반려</option>
        </select>
        <label htmlFor={rationaleId}>검토 사유 (필수)</label>
        <textarea id={rationaleId} rows={3} maxLength={4000} value={record.rationale} disabled={!editable}
          placeholder="이 계약을 승인하거나 반려하는 이유를 적어 주세요."
          onChange={event => onRationale(event.target.value)} />
        <p className="run-hint">의견은 같은 사용자·문맥·적용본·앱·판본·지문별 메모리에만 보관합니다.
          서버 초안 저장은 아니며, 새로고침·로그아웃 시 사라질 수 있습니다. 새 판에는 자동 복사하지 않습니다.</p>
        <label htmlFor={confirmId} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <input id={confirmId} type="checkbox" checked={state.confirmed}
            disabled={!editable || !selectionAllowed || !record.rationale.trim()}
            onChange={event => onConfirm(event.target.checked)} />
          <span>{view.revision}판 원문·계약 지문·검토 제한과 위 사유를 확인했습니다.
            선택이나 사유가 바뀌면 다시 확인합니다.</span>
        </label>
        <div className="run-form-actions">
          <button type="button" className="primary-button" disabled={!canSubmit} onClick={onSubmit}>
            {record.decision === 'REJECT' ? '확인한 계약 반려' : record.decision === 'APPROVE' ? '확인한 계약 승인' : '검토 결과를 선택하세요'}
          </button>
        </div>
        <p role="status">{OUTCOME_LABEL[record.outcome] || '처리 상태 확인 필요'}{record.message ? ` · ${record.message}` : ''}</p>
      </div>}
    </>}

    {records.length > 0 && <details open={records.some(item => item.outcome === 'UNKNOWN' || item.outcome === 'RECORDED')}>
      <summary>검토 입력·처리 기록 ({records.length})</summary>
      <ul style={{ display: 'grid', gap: 12 }}>{records.map(item => <li key={item.key} style={{ overflowWrap: 'anywhere' }}>
        <strong>{item.revision}판 · {OUTCOME_LABEL[item.outcome] || '확인 필요'}</strong>
        <p>선택: {item.decision === 'APPROVE' ? '승인' : item.decision === 'REJECT' ? '반려' : '미정'}</p>
        <p>지문: <code>{item.fingerprint}</code></p>
        <p style={{ whiteSpace: 'pre-wrap' }}>사유: {item.rationale || '미작성'}</p>
        {item.eventId && <p>사건 ID: <code>{item.eventId}</code></p>}
        {item.message && <p>{item.message}</p>}
        {(item.outcome === 'UNKNOWN' || item.outcome === 'RECORDED') && <>
          <p className="run-hint">새 승인·반려를 보내지 않고 원래 요청의 처리 상태만 확인합니다.</p>
          <button type="button" disabled={state.busy} onClick={() => onRecheck(item.key)}>이 요청의 처리 결과 확인</button>
        </>}
      </li>)}</ul>
    </details>}
  </section>;
}
