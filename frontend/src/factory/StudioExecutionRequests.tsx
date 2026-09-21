// B5: 실행 명령의 영수증 확인은 실제 가동·중지·완료 판정과 분리한다.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  getExecutionRecords, getExecutionRecoveryIds, hasExecutionPending, recoverExecutionRequest,
  refreshExecutionRecords, subscribeExecutionRecords,
  type ExecutionAttempt, type ExecutionOperation, type ExecutionReceipt,
} from '../lib/studioExecutionApi';
import { studioIdentityKey } from './studioInputMemory';

const EVENTS = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
const OPERATIONS: Record<ExecutionOperation, string> = {
  START: '작업 시작', RESUME: '같은 작업 재개', RESUME_QUOTA: '한도 회복 후 재개',
  PAUSE: '일시정지', STOP: '제작 중단', HEAL: '오류 복구',
  RELEASE: '릴리스 저장', REPLAN: '작업 목록 다시 나누기',
};
function subscribeIdentity(listener: () => void) {
  EVENTS.forEach(name => window.addEventListener(name, listener));
  return () => EVENTS.forEach(name => window.removeEventListener(name, listener));
}
function useExecutionIdentity() {
  return useSyncExternalStore(subscribeIdentity, studioIdentityKey, studioIdentityKey);
}
function subscribePending(listener: () => void) {
  const unsubscribe = subscribeExecutionRecords(listener);
  const unsubscribeIdentity = subscribeIdentity(listener);
  return () => { unsubscribe(); unsubscribeIdentity(); };
}
/** ★ 구 통제실도 이 훅을 쓴다 — «미확정이 있는가» 를 세 번째로 다시 구독하지 않는다.
 *  이미 기록 변경과 신원 변경을 함께 보고 있고, SSR 에서 개인 기록을 먼저 공개하지 않는다. */
export function useExecutionPending(projectId: string) {
  const snapshot = useCallback(() => !!projectId && hasExecutionPending(projectId), [projectId]);
  // boolean snapshot은 같은 값에 같은 참조다. SSR에서 개인 기록을 미리 공개하지 않는다.
  return useSyncExternalStore(subscribePending, snapshot, () => false);
}

export interface StudioExecutionRequestsProps {
  projectId: string;
  /** 명령을 재실행하지 않고 최신 상태/WBS reader만 갱신한다. */
  onConfirmed?: (receipt: ExecutionReceipt) => void | Promise<void>;
}
export function StudioExecutionRequests(props: StudioExecutionRequestsProps) {
  const identity = useExecutionIdentity();
  return <ExecutionRequests key={JSON.stringify([identity, props.projectId])} {...props} identity={identity} />;
}
function ExecutionRequests({ projectId, identity, onConfirmed }: StudioExecutionRequestsProps & { identity: string }) {
  const [records, setRecords] = useState<ExecutionAttempt[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('실행 요청 기록의 조회 권한을 확인하는 중입니다.');
  const pending = useExecutionPending(projectId);
  const active = useRef(false);
  const locked = useRef(false);
  const authorized = useRef(false);
  const generation = useRef(0);
  // API의 비공개 원요청에서 ID만 받는다. 목록 조회 실패·재마운트 후에도 본문 없이 GET 복구한다.
  // 이 ID 목록은 권한·접수 성공의 증명이 아니며 UI에 별도 인덱스를 저장하지 않는다.
  const [recoveryIds, setRecoveryIds] = useState<string[]>([]);
  const current = (version = generation.current) => active.current && version === generation.current && identity === studioIdentityKey();
  const sync = () => {
    if (!current()) return;
    const visible = getExecutionRecords(projectId);
    setRecoveryIds([...new Set(getExecutionRecoveryIds(projectId))]);
    setRecords(authorized.current ? visible : []);
  };
  const hide = (text: string) => {
    authorized.current = false; setReady(false); setRecords([]); setError(text);
  };
  const refresh = async () => {
    if (!projectId || locked.current || !current()) return;
    const version = ++generation.current;
    locked.current = true; setBusy('목록'); hide(''); setMessage('현재 문맥의 서버 기록을 조회합니다.');
    try {
      await refreshExecutionRecords(projectId);
      if (!current(version)) return;
      authorized.current = true; setReady(true); sync();
      setMessage('서버에서 공개 가능한 요청 기록을 조회했습니다. 접수 확인과 실제 실행 상태는 다릅니다.');
    } catch (e) {
      if (current(version)) { hide(e instanceof Error ? e.message : '실행 요청 기록을 조회하지 못했습니다.'); setMessage('이전 요청의 본문을 숨겼습니다. 원요청 ID별 GET 확인은 다시 시도할 수 있습니다.'); }
    } finally { locked.current = false; if (active.current) setBusy(''); }
  };
  const recover = async (requestId: string) => {
    if (locked.current || !current()) return;
    const version = ++generation.current;
    locked.current = true; setBusy(requestId); hide(''); setMessage('원래 요청 ID의 영수증만 GET으로 확인합니다.');
    try {
      const receipt = await recoverExecutionRequest(projectId, requestId);
      if (!current(version)) return;
      if (!receipt) { hide('원래 요청의 영수증을 확인하지 못했습니다. 원키를 보존하며 자동 재전송하지 않습니다.'); return; }
      authorized.current = true; setReady(true); sync();
      setMessage(receipt.status === 'ACCEPTED' || receipt.status === 'REJECTED'
        ? '원요청의 접수 결과를 확인했습니다. 실제 실행·중지·완료는 현재 상태를 별도로 확인하세요.'
        : '서버 기록은 조회했지만 처리 결과가 아직 미확정입니다. 같은 요청 ID로만 다시 조회하세요.');
      if (receipt.status === 'ACCEPTED' || receipt.status === 'REJECTED') {
        try { await onConfirmed?.(receipt); }
        catch (e) { if (current(version)) setError('영수증은 확인됐지만 현재 실행 상태 조회는 확인하지 못했습니다. 명령을 재전송하지 마세요. ' + (e instanceof Error ? e.message : '')); }
      }
    } catch (e) {
      if (current(version)) hide(e instanceof Error ? e.message : '접수 결과를 조회하지 못했습니다. 원키를 보존합니다.');
    } finally { locked.current = false; if (active.current) setBusy(''); }
  };
  useEffect(() => {
    active.current = true;
    let disposed = false;
    const unsubscribe = subscribeExecutionRecords(sync);
    const invalidate = () => {
      generation.current++; hide('사용자·문맥 또는 인증 상태가 바뀌었습니다. 요청 기록을 다시 조회하세요.');
      setRecoveryIds([]);
      queueMicrotask(() => { if (!disposed) sync(); });
    };
    EVENTS.forEach(name => window.addEventListener(name, invalidate));
    queueMicrotask(() => { if (!disposed) { sync(); void refresh(); } });
    return () => {
      disposed = true; active.current = false; generation.current++;
      unsubscribe(); EVENTS.forEach(name => window.removeEventListener(name, invalidate));
    };
    // 입력·부모 재렌더는 조회나 재전송을 일으키지 않는다. 문맥 변경은 wrapper key로 분리한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, identity]);

  return <section className="studio-execution-requests" aria-label="실행 요청 기록과 복구" aria-busy={!!busy}>
    <h4>실행 요청 기록</h4>
    <p className="run-hint">명령 접수 확인은 가동 중·중지 완료·제작 완료를 뜻하지 않습니다. 실제 진행은 위 실행 상태에서 확인하세요.</p>
    {pending && <p role="alert">미확정 실행 요청이 있어 다른 쓰기 명령은 잠겨 있습니다. 헤더의 일시정지·제작 중단은 서버 상태를 확인해 별도로 요청할 수 있습니다.</p>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <button type="button" disabled={!projectId || !!busy} onClick={() => void refresh()}>실행 요청 목록 조회</button>
    {ready && records.length === 0 && <p>현재 조회에서 공개 가능한 기록이 없습니다. 이 사실만으로 이전 미확정 명령이 해제되지는 않습니다.</p>}
    {records.map(record => <ExecutionRecord key={record.request.client_request_id} record={record}
      busy={!!busy} onRecover={() => void recover(record.request.client_request_id)} />)}
    {recoveryIds.filter(id => !records.some(record => record.request.client_request_id === id)).map(id => <div key={id} className="run-form-actions">
      <span>원요청 ID: <code>{id}</code> · 본문·결과는 조회 확인 전 숨김</span>
      <button type="button" disabled={!!busy} onClick={() => void recover(id)}>이 요청 접수 확인 · GET만</button>
    </div>)}
  </section>;
}

function ExecutionRecord({ record, busy, onRecover }: { record: ExecutionAttempt; busy: boolean; onRecover: () => void }) {
  const { request, receipt } = record;
  const response = receipt?.result?.response;
  const taskId = response && typeof response.task_id === 'string' ? response.task_id : '';
  const hotlTaskId = response && typeof response.hotl_task_id === 'string' ? response.hotl_task_id : '';
  const uncertain = record.outcome === 'UNKNOWN' || receipt?.status === 'PROCESSING' || receipt?.status === 'UNKNOWN';
  const title = uncertain ? '접수 결과 미확정' : record.outcome === 'REJECTED' ? '명령 접수 거절 확인' : '명령 접수 기록 확인';
  return <article className="process-safety" style={{ marginTop: 10, overflowWrap: 'anywhere' }}>
    <strong>{OPERATIONS[request.operation]} · {title}</strong>
    <p role="status">{record.message}</p>
    <p>원요청 ID: <code>{request.client_request_id}</code> · 원작업: {request.task_id || '원작업 ID 없음'}</p>
    {taskId && <p>{request.operation === 'HEAL' ? '접수된 복구 작업' : '서버 응답 작업'}: {taskId}</p>}
    {hotlTaskId && <p>먼저 확인할 사용자 결정(HOTL): {hotlTaskId} · 이 응답을 새 복구 작업의 실행 완료로 표시하지 않습니다.</p>}
    {receipt && <p>서버 접수 상태: {receipt.status} · 최종 기록 시각: {receipt.updated_at}</p>}
    <details><summary>원래 명령·입력·영수증 근거</summary>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify({ request, receipt }, null, 2)}</pre>
    </details>
    {uncertain && <button type="button" disabled={busy} onClick={onRecover}>원요청 접수 재확인 · GET만</button>}
  </article>;
}
