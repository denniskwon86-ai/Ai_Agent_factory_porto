// B5: 현재 행동을 먼저 보여 주고 진단·재계획·내보내기는 접어 둔다.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
import type { FactoryStudioViewModel } from './factoryViewModel';
import { studioNextAction } from './studioNextAction';
import { studioIdentityKey, studioInputKey, studioInputMemory } from './studioInputMemory';
import { RevisionRequestEditor } from './RevisionRequestEditor';
import type { RevisionAttempt } from '../lib/studioRevisionFlow';
import { getExecutionRecords, hasExecutionPending, subscribeExecutionRecords, type ExecutionAttempt } from '../lib/studioExecutionApi';
import { StudioExecutionRequests } from './StudioExecutionRequests';
import {
  REPLAN_CONFIRM, REVISION_NOTE, SELF_HEAL_NOTE, exportArchiveUrl, newPlanningTaskId,
  replanWbs, resumeAfterQuota, resumeExistingTask, startPlanning, startExistingTask,
  type SprintResult,
} from './sprintActions';

type Form = { idea: string; reference: string; uncertain: string; observedTask: string; requestId?: string };
const EMPTY_FORM: Form = { idea: '', reference: '', uncertain: '', observedTask: '' };
const EMPTY_EXECUTION_RECORDS: ExecutionAttempt[] = [];
function pausedExecution(value: unknown, currentTaskId: unknown): { taskId: string; resumable: boolean; reason: string } | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const pause = row.pause && typeof row.pause === 'object' && !Array.isArray(row.pause)
    ? row.pause as Record<string, unknown> : null;
  if (typeof row.task_id !== 'string' || !row.task_id || row.task_id !== currentTaskId
      || row.running !== false || pause?.status !== 'PAUSED') return null;
  return { taskId: row.task_id, resumable: pause.resumable === true && typeof pause.reason_code === 'string',
    reason: typeof pause.reason_code === 'string' && pause.reason_code ? pause.reason_code : 'RESUME_STATE_UNAVAILABLE' };
}
function subscribeExecutionUI(listener: () => void) {
  const events = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
  const unsubscribe = subscribeExecutionRecords(listener);
  events.forEach(name => window.addEventListener(name, listener));
  return () => { unsubscribe(); events.forEach(name => window.removeEventListener(name, listener)); };
}
export interface RunControlsProps {
  vm: FactoryStudioViewModel;
  onReviewResult?: () => void;
  onReviewDecision?: () => void;
  onShowTasks?: () => void;
}

export function RunControls(props: RunControlsProps) {
  const identity = useSyncExternalStore(subscribeExecutionUI, studioIdentityKey, studioIdentityKey);
  return <ProjectRunControls key={JSON.stringify([identity, props.vm.project.id])} {...props} />;
}

function ProjectRunControls({ vm, onReviewResult, onReviewDecision, onShowTasks }: RunControlsProps) {
  const pid = vm.project.id;
  const key = studioInputKey(pid, 'run-input', 'requirements');
  const [form, setForm] = useState<Form>(() => studioInputMemory.get(key, EMPTY_FORM));
  const update = (patch: Partial<Form>) => setForm(previous => {
    const next = { ...previous, ...patch }; studioInputMemory.set(key, next); return next;
  });
  const [panel, setPanel] = useState<'planning' | 'resume-task' | 'task' | 'heal' | 'revision' | 'replan' | null>(null);
  const [resumeTaskId, setResumeTaskId] = useState('');
  const [revisionSelection, setRevisionSelection] = useState({ key: '', taskId: '' });
  const [, renderRevisionState] = useState(0);
  const revisionStateChanged = useCallback(() => renderRevisionState(value => value + 1), []);
  const [busy, setBusy] = useState('');
  const busyRef = useRef(false);
  const alive = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const [note, setNote] = useState<{ ok: boolean; text: string; requestId?: string } | null>(null);
  const readExecutionPending = useCallback(() => hasExecutionPending(pid), [pid]);
  const readExecutionRecords = useCallback(() => getExecutionRecords(pid), [pid]);
  const executionPending = useSyncExternalStore(subscribeExecutionUI, readExecutionPending, () => false);
  const executionRecords = useSyncExternalStore(subscribeExecutionUI, readExecutionRecords, () => EMPTY_EXECUTION_RECORDS);
  const stateTaskId = useFactoryStore(store => store.state?.current_sprint_task_id);
  const executionSnapshot = useFactoryStore(store => store.state?.studio_execution_state);
  const stateProjectId = useFactoryStore(store => store.currentProjectId);
  const paused = stateProjectId === pid ? pausedExecution(executionSnapshot, stateTaskId) : null;
  const planningTaskId = typeof stateTaskId === 'string' && /^PLANNING_[A-Za-z0-9_-]+$/.test(stateTaskId) ? stateTaskId : '';
  useEffect(() => {
    let disposed = false;
    const sync = () => {
      if (disposed || key !== studioInputKey(pid, 'run-input', 'requirements')) return;
      const previous = studioInputMemory.get<Form>(key, EMPTY_FORM);
      if (!previous.uncertain || !previous.requestId) return;
      const confirmed = getExecutionRecords(pid).find(record => record.request.client_request_id === previous.requestId
        && (record.outcome === 'CONFIRMED' || record.outcome === 'REJECTED'));
      if (!confirmed) return;
      // 같은 태스크 ID나 active/pending 상태는 증거가 아니다. 공개 검증된 원요청 ID만 해제한다.
      const next = { ...previous, uncertain: '', observedTask: '', requestId: '' };
      studioInputMemory.set(key, next); setForm(next);
    };
    const unsubscribe = subscribeExecutionRecords(sync);
    queueMicrotask(sync);
    return () => { disposed = true; unsubscribe(); };
  }, [pid, key]);
  const action = studioNextAction(vm);
  const resumePrimary = !!paused && !['refresh', 'decision', 'quota', 'running'].includes(action.kind);
  const selected = vm.wbs.find(t => t.id === vm.selectedWbsId)
    || vm.wbs.find(t => t.id === action.taskId)
    || vm.wbs.find(t => t.id === vm.inspect.failure?.taskId);
  const revisionRecords = studioInputMemory.projectValues<RevisionAttempt>(pid, 'revision-request');
  const pendingRevision = revisionRecords.find(record => record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED');
  const hasRevisionPending = () => studioInputMemory.projectValues<RevisionAttempt>(pid, 'revision-request')
    .some(record => record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED');
  const preferredRevisionTask = pendingRevision?.command.target.task_id || selected?.id
    || useFactoryStore.getState().state?.current_sprint_task_id || revisionRecords[0]?.command.target.task_id || '';
  const revisionTask = revisionSelection.key === key ? revisionSelection.taskId : preferredRevisionTask;
  const openRevision = () => {
    setRevisionSelection({ key, taskId: preferredRevisionTask }); setPanel('revision');
  };
  const feedbackKey = studioInputKey(pid, 'run-feedback', selected?.id || '');
  const [feedbackEdits, setFeedbackEdits] = useState<Record<string, string>>({});
  const feedback = feedbackEdits[feedbackKey] ?? studioInputMemory.get<string>(feedbackKey, '');
  const updateFeedback = (value: string) => {
    studioInputMemory.set(feedbackKey, value);
    setFeedbackEdits(previous => ({ ...previous, [feedbackKey]: value }));
  };
  const readReason = !pid ? '프로젝트를 먼저 선택하세요.'
    : ['forbidden', 'loading', 'error'].includes(vm.loadState) ? vm.loadReason || '상태 확인이 필요합니다.'
    : vm.connection !== 'connected' ? '연결을 확인한 뒤 요청하세요.' : '';
  const disabledReason = readReason || (form.uncertain ? '이전 요청 결과를 확인하기 전에는 새 요청을 보내지 않습니다.'
    : executionPending ? '실행 명령의 접수 결과가 미확정입니다. 아래에서 원래 요청을 조회하세요.'
    : pendingRevision ? '수정 접수 결과를 확인하기 전에는 다른 쓰기 명령을 보내지 않습니다.' : '');
  const activeReason = disabledReason || (vm.run.active ? `현재 ${vm.run.label} 상태입니다.` : '');
  const resumeReason = activeReason || (vm.inspect.suspendedTaskId ? '한도 회복 후 재개를 사용하세요.'
    : !paused ? '현재 작업과 일치하는 일시정지 상태를 다시 조회하세요.'
      : !paused.resumable ? `서버가 재개를 허용하지 않았습니다 (${paused.reason}).` : '');
  const openResume = () => {
    if (!paused || resumeReason) return;
    setResumeTaskId(paused.taskId); setPanel('resume-task');
  };
  const hasResult = !!Object.keys(vm.docs).length || vm.generated.runnable || vm.run.wbsDone > 0;

  const command = async (label: string, work: () => Promise<SprintResult>, observedTask = '', receiptBacked = false) => {
    if (busyRef.current || disabledReason || hasExecutionPending(pid) || hasRevisionPending() || studioInputKey(pid, 'run-input', 'requirements') !== key) return;
    busyRef.current = true; setBusy(label); setNote(null);
    const identity = studioIdentityKey();
    // 새 bridge는 POST 전 원키를 예약한다. 별도의 원키 없는 UNKNOWN을 중복 생성하지 않는다.
    // 영수증 없는 기존 명령은 이전 방식의 보수적인 잠금을 유지한다.
    if (!receiptBacked) update({ uncertain: label, observedTask, requestId: '' });
    try {
      const result = await work();
      if (identity !== studioIdentityKey()) return;
      const settled = result.requestId && getExecutionRecords(pid).some(record => record.request.client_request_id === result.requestId
        && (record.outcome === 'CONFIRMED' || record.outcome === 'REJECTED'));
      const uncertain = result.outcome === 'UNKNOWN' && !settled;
      const next = { ...studioInputMemory.get<Form>(key, EMPTY_FORM), uncertain: uncertain ? label : '',
        observedTask: uncertain ? result.taskId || observedTask : '', requestId: uncertain ? result.requestId || '' : '' };
      studioInputMemory.set(key, next);
      if (!alive.current || useFactoryStore.getState().currentProjectId !== pid) return;
      setForm(next);
      setNote({ ok: result.ok, requestId: result.requestId,
        text: result.message || (result.ok ? '명령 접수 결과를 확인했습니다. 실제 진행 상태는 별도로 확인하세요.' : '요청 결과를 확인해야 합니다.') });
      if (result.ok) {
        setPanel(null);
        // 입력은 자동 삭제하지 않는다. 조회·접수와 서버 초안 저장은 다른 상태다.
        // 접수는 실행 확인이 아니다. 최신 reader/SSE가 실제 active task를 갱신한다.
        try {
          await Promise.all([useFactoryStore.getState().fetchLatestState(), useFactoryStore.getState().fetchWBS(true), useFactoryStore.getState().checkHotl()]);
        } catch {
          if (alive.current && identity === studioIdentityKey() && useFactoryStore.getState().currentProjectId === pid)
            setNote({ ok: false, requestId: result.requestId, text: '명령 접수 결과와 별도로 현재 상태 조회를 확인하지 못했습니다. 명령을 다시 보내지 말고 상태를 조회하세요.' });
        }
      }
    } catch (error) {
      if (!alive.current || identity !== studioIdentityKey() || useFactoryStore.getState().currentProjectId !== pid) return;
      update({ uncertain: label, observedTask, requestId: '' });
      setNote({ ok: false, text: `요청 결과를 확인하지 못했습니다. 자동 재전송하지 않습니다. ${error instanceof Error ? error.message : ''}` });
    } finally { busyRef.current = false; if (alive.current) setBusy(''); }
  };

  const refresh = async () => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy('상태 확인');
    const identity = studioIdentityKey();
    try {
      const store = useFactoryStore.getState();
      await Promise.all([store.fetchLatestState(), store.fetchWBS(true), store.checkHotl(), store.fetchReleases()]);
      if (!alive.current || identity !== studioIdentityKey() || useFactoryStore.getState().currentProjectId !== pid) return;
      // 기존 캐시의 같은 task ID는 이번 명령의 접수 증거가 아니다.
      // 상태 조회는 명령별 영수증 조회를 대신하지 않는다. 원키가 없는 UNKNOWN도 풀지 않는다.
      setNote({ ok: !form.uncertain, text: form.uncertain
        ? '상태 조회를 요청했습니다. 이전 요청의 반영 여부는 아직 확인되지 않아 중복 요청을 막고 있습니다.'
        : '현재 상태 조회를 요청했습니다. 아래 연결·오류 안내를 함께 확인하세요.' });
    } finally { busyRef.current = false; if (alive.current) setBusy(''); }
  };

  const revisionSubmitted = useCallback(async () => {
    if (!alive.current || studioInputKey(pid, 'run-input', 'requirements') !== key
        || useFactoryStore.getState().currentProjectId !== pid) return;
    // 수정 접수는 부모 command의 UNKNOWN·자동 닫기·실행 경로를 사용하지 않는다.
    // 원래 작업 선택과 처리 카드를 유지하며 WBS 조회만 요청한다.
    await useFactoryStore.getState().fetchWBS(true);
  }, [pid, key]);
  const executionConfirmed = useCallback(async () => {
    if (!alive.current || studioInputKey(pid, 'run-input', 'requirements') !== key
        || useFactoryStore.getState().currentProjectId !== pid) return;
    const store = useFactoryStore.getState();
    // 영수증은 명령 접수 결과다. 실제 가동·중지·완료는 상태 reader로 따로 확인한다.
    await Promise.all([store.fetchLatestState(), store.fetchWBS(true), store.checkHotl()]);
  }, [pid, key]);

  const doPlanning = () => {
    if (activeReason || planningTaskId || vm.wbs.length || !form.idea.trim()) return;
    const task = newPlanningTaskId();
    void command('요구사항 정리 요청', () => startPlanning(pid, form.idea, form.reference, task), task, true);
  };
  const doResumeTask = () => {
    if (resumeReason || !paused || paused.taskId !== resumeTaskId) return;
    const store = useFactoryStore.getState();
    const latest = pausedExecution(store.state?.studio_execution_state, store.state?.current_sprint_task_id);
    if (store.currentProjectId !== pid || !latest?.resumable || latest.taskId !== resumeTaskId) return;
    void command('멈춘 작업 이어하기', () => resumeExistingTask(pid, resumeTaskId), resumeTaskId, true);
  };
  const doTask = () => {
    if (activeReason || !selected || selected.kind === 'blocked' || selected.kind === 'done') return;
    const raw = useFactoryStore.getState().wbsData?.tasks?.find((t: { task_id: string }) => t.task_id === selected.id);
    if (!raw) { setNote({ ok: false, text: '현재 작업 목록에서 대상을 다시 확인하세요.' }); return; }
    void command('선택 작업 시작 요청', () => startExistingTask(pid, selected.id, {}, feedback), selected.id, true);
  };
  const doHeal = () => {
    if (activeReason || !vm.inspect.failure) return;
    void command('오류 복구 요청', async () => {
      const result = await useFactoryStore.getState().triggerSelfHealing(vm.inspect.failure!.error);
      return { ...result, outcome: result.outcome === 'HEAL_STARTED' || result.outcome === 'HOTL_PENDING'
        ? 'ACCEPTED' : result.outcome === 'LOCAL_BLOCKED' ? 'REJECTED' : result.outcome };
    }, vm.inspect.failure.taskId || '', true);
  };
  const doRelease = () => {
    if (activeReason || !hasResult) return;
    void command('검토용 버전 저장', async () => {
      const result = await useFactoryStore.getState().saveRelease(pid);
      return { ...result, message: result.ok
        ? `검토용 버전 ${result.releaseId}을 저장했습니다. 배포·운영 승인은 별도입니다.` : result.message };
    });
  };
  const primary = () => {
    if (resumePrimary) { openResume(); return; }
    switch (action.kind) {
      case 'refresh': void refresh(); break;
      case 'decision': onReviewDecision?.(); break;
      case 'quota': void command('한도 재개 요청', () => resumeAfterQuota(pid, vm.inspect.suspendedTaskId), vm.inspect.suspendedTaskId, true); break;
      case 'planning': if (planningTaskId) void refresh(); else setPanel('planning'); break;
      case 'task': setPanel('task'); break;
      case 'heal': setPanel('heal'); break;
      case 'result': case 'running': onReviewResult?.(); break;
      default: onShowTasks?.();
    }
  };
  return <section className="run-controls" aria-label="지금 할 일">
    <div className="studio-next-action">
      <div><strong>{resumePrimary ? '멈춘 작업을 이어갈 수 있는지 확인하세요' : action.title}</strong>
        <p>{resumePrimary ? '현재 작업의 저장된 지점에서 재개합니다. 새 작업 시작과는 다릅니다.' : action.description}</p></div>
      <button type="button" className="primary" disabled={!!busy || (action.kind === 'blocked' && !pid)
        || (resumePrimary && !!resumeReason)
        || ((executionPending || !!pendingRevision || !!form.uncertain) && ['planning', 'task', 'heal', 'quota'].includes(action.kind))} onClick={primary}>{resumePrimary ? '멈춘 작업 이어하기' : action.kind === 'planning' && planningTaskId ? '기존 기획 상태 확인' : action.label}</button>
      <button type="button" disabled={!!busy} onClick={() => void refresh()}>상태 새로고침</button>
    </div>
    {paused && !paused.resumable && <p className="run-note bad" role="status">재개 불가 사유: {paused.reason}. 상태를 다시 조회하거나 필요한 조건을 먼저 확인하세요.</p>}
    {note && (!note.requestId || executionRecords.some(record => record.request.client_request_id === note.requestId))
      && <p className={`run-note ${note.ok ? 'ok' : 'bad'}`} role={note.ok ? 'status' : 'alert'}>{note.text}</p>}
    {form.uncertain && <p className="run-note bad" role="alert">{form.uncertain}: 결과 확인 필요. 입력은 보존되어 있으며 요청을 자동 반복하지 않습니다.</p>}
    {form.uncertain && !form.requestId && <p className="run-hint">이전 명령에는 복구할 원요청 ID가 없습니다. 현재 상태나 다른 요청의 성공만으로 잠금을 해제하지 않습니다.</p>}
    <StudioExecutionRequests projectId={pid} onConfirmed={executionConfirmed} />
    {pendingRevision && <div className="run-note bad" role="alert">
      수정 요청의 접수 결과가 미확정입니다. 다른 쓰기는 잠그고 원래 요청의 GET 확인만 제공합니다.
      <button type="button" disabled={!!readReason} onClick={openRevision}>수정 접수 확인 열기</button>
    </div>}
    <details className="studio-more-actions">
      <summary>추가 작업 · 수정 요청, 버전 저장, 내려받기</summary>
      <div className="run-buttons">
        <Action label="요구사항 정리" why={activeReason || (planningTaskId ? '현재 기획의 일시정지·재개 가능 상태를 먼저 조회하세요.' : vm.wbs.length ? '이미 작업 목록이 있습니다.' : '')} busy={busy} onClick={() => setPanel('planning')} />
        {paused && <Action label="멈춘 작업 이어하기" why={resumeReason} busy={busy} onClick={openResume} />}
        <Action label="선택 작업 시작·재가동" why={activeReason || (!selected ? '작업 목록에서 대상을 선택하세요.' : selected.kind === 'blocked' || selected.kind === 'done' ? '완료·선행 조건을 확인하세요.' : '')} busy={busy} onClick={() => setPanel('task')} />
        <Action label="한도 회복 후 재개" why={disabledReason || (!vm.inspect.suspendedTaskId ? '사용 한도로 멈춘 작업이 없습니다.' : '')} busy={busy} onClick={() => void command('한도 재개 요청', () => resumeAfterQuota(pid, vm.inspect.suspendedTaskId), vm.inspect.suspendedTaskId, true)} />
        <Action label="오류 복구" why={activeReason || (!vm.inspect.failure ? '복구할 오류 기록이 없습니다.' : '')} busy={busy} onClick={() => setPanel('heal')} />
        <Action label="수정 요청" why={readReason || (!hasResult && !revisionRecords.length ? '먼저 결과를 확인하세요.' : '')}
          busy="" onClick={openRevision} />
        <Action label="검토용 버전 저장" why={activeReason || (!hasResult ? '저장할 결과가 없습니다.' : '')} busy={busy} onClick={doRelease} />
        <Action label="작업 계획 다시 나누기" why={activeReason || (!vm.docs.PLANNING ? '기획 결과가 필요합니다.' : '')} busy={busy} onClick={() => setPanel('replan')} />
        <Action label="코드·문서 내려받기" why={disabledReason || (!hasResult ? '내려받을 결과가 없습니다.' : '')} busy={busy} onClick={() => {
          const a = document.createElement('a'); a.href = exportArchiveUrl(pid); a.download = `${pid}.zip`; a.click();
        }} />
      </div>
    </details>
    {panel && <div className="run-form">
      {panel === 'planning' && <>
        <label className="field-label" htmlFor="studio-idea">어떤 일을 쉽게 만들고 싶으세요?</label>
        <textarea id="studio-idea" rows={3} value={form.idea} disabled={!!busy || !!form.uncertain} onChange={e => update({ idea: e.target.value })} placeholder="예: 원료별 구매계획과 입고 예정일을 한눈에 확인하고 싶어요." />
        <details><summary>추가 설명</summary><label htmlFor="studio-reference">참고할 업무 설명 — 인증된 기준정보로 자동 등록되지 않습니다.</label>
          <textarea id="studio-reference" rows={2} value={form.reference} disabled={!!busy || !!form.uncertain} onChange={e => update({ reference: e.target.value })} /></details>
      </>}
      {panel === 'task' && <p><b>{selected?.title || '작업을 선택하세요'}</b> — 기존 작업 ID와 서버의 실행 모드로 제작을 요청합니다. 한도 재개와는 다릅니다.</p>}
      {panel === 'resume-task' && <>
        <p><b>{resumeTaskId}</b> — 서버가 같은 작업의 재개 가능 상태를 확인합니다.
          기존 산출물을 새 작업으로 대체하지 않으며, 현재 폼의 요구·참고 설명·피드백을 재전송하지 않습니다.</p>
        {(resumeReason || paused?.taskId !== resumeTaskId) && <p role="alert">{resumeReason || '일시정지 대상이 바뀌었습니다. 현재 상태를 조회한 뒤 재개 화면을 다시 여세요.'}</p>}
      </>}
      {panel === 'task' && <>
        <label htmlFor="studio-feedback">이번 작업에 전달할 추가 설명 (선택)</label>
        <textarea id="studio-feedback" rows={3} value={feedback} disabled={!!busy || !!form.uncertain} onChange={e => updateFeedback(e.target.value)} />
        <p className="run-hint">{REVISION_NOTE}</p>
      </>}
      {panel === 'revision' && (readReason ? <p role="alert">{readReason} · 현재 권한을 확인할 때까지 이전 수정 본문·기록을 숨깁니다.</p>
        : revisionTask ? <RevisionRequestEditor projectId={pid} taskId={revisionTask}
          disabled={!!busy || !!activeReason} onSubmitted={revisionSubmitted} onStateChange={revisionStateChanged} />
          : <p role="alert">수정할 작업을 목록에서 선택하세요. 기준 없는 수정 요청은 보내지 않습니다.</p>)}
      {panel === 'heal' && <><p role="alert">{vm.inspect.failure?.error}</p><p>{SELF_HEAL_NOTE}</p><p>새 복구 작업 또는 먼저 확인할 기존 검토 건을 서버 응답에 따라 안내합니다.</p></>}
      {panel === 'replan' && <p role="alert">{REPLAN_CONFIRM}</p>}
      <p className="run-hint">입력은 현재 로그인 세션에 보관됩니다. 서버 초안 저장과는 다르며 새로고침하면 잃을 수 있습니다.</p>
      {disabledReason && <p role="alert">{disabledReason}</p>}
      <div className="run-form-actions">
        <button type="button" onClick={() => setPanel(null)}>입력 유지하고 접기</button>
        {panel !== 'revision' && <button type="button" className="primary" disabled={!!busy || !!activeReason || (panel === 'planning' && (!form.idea.trim() || !!planningTaskId))
          || (panel === 'resume-task' && (!!resumeReason || paused?.taskId !== resumeTaskId))} onClick={() => {
          if (panel === 'planning') doPlanning();
          if (panel === 'resume-task') doResumeTask();
          if (panel === 'task') doTask();
          if (panel === 'heal') doHeal();
          if (panel === 'replan') void command('작업 계획 재분할 요청', () => replanWbs(pid));
        }}>{busy || (panel === 'planning' ? '요구사항 정리 시작' : panel === 'resume-task' ? '같은 작업 재개 요청' : panel === 'replan' ? '영향을 확인하고 다시 나누기' : '확인하고 요청')}</button>}
      </div>
    </div>}
  </section>;
}

function Action({ label, why, busy, onClick }: { label: string; why: string; busy: string; onClick: () => void }) {
  return <button type="button" disabled={!!why || !!busy} onClick={onClick}><span>{label}</span>{why && <em>{why}</em>}</button>;
}
