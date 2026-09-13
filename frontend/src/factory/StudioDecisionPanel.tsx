// 일반 재개·Host 계약 승인·지원 능력 선택은 서로 다른 서버 결정이다.
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type { FactoryStudioViewModel } from './factoryViewModel';
import type { ClarifySelections } from './clarifyAnswers';
import { serializeClarifyAnswers, unansweredCount } from './clarifyAnswers';
import { studioIdentityKey, studioInputMemory } from './studioInputMemory';
import type { InputDraft } from '../lib/studioInputDraftApi';
import { canonicalQuestionJson, createStudioDecisionApi, isDecisionDigest, verifyHotlQuestions } from './studioDecisionApi';
import type { CapabilityDecision, StudioDecisionApi } from './studioDecisionApi';
import { useFactoryStore } from '../store/useFactoryStore';
import { StudioInputDraftControls } from './StudioInputDraftControls';
import {
  capabilityActionable, capabilitySubject, createStudioDecisionFlow, hostSubject, hotlSubject,
} from './studioDecisionFlow';
import type { DecisionRecord, StudioDecisionFlow } from './studioDecisionFlow';

export interface StudioDecisionPanelProps {
  vm: FactoryStudioViewModel;
  selections: ClarifySelections;
  onDecisionKeyChange?: (key: string) => void;
  onRestoreSelections?: (selections: ClarifySelections) => void;
  /** 합성 검증 전용 주입점. 기본값은 현재 인증·문맥의 실제 API다. */
  apiFactory?: (projectId: string, identity: string) => StudioDecisionApi;
}

function Note({ flow, kind, subject, record, disabled }: {
  flow: StudioDecisionFlow; kind: DecisionRecord['kind']; subject: string;
  record?: DecisionRecord; disabled: boolean;
}) {
  return <label className="decision-note"><span>{kind === 'HOTL' ? '추가 의견 (선택)' : '결정 이유 (반려할 때 필수)'}</span>
    <textarea value={record?.note || ''} disabled={disabled}
      style={{ width: '100%', minHeight: 64, padding: 8, font: 'inherit', boxSizing: 'border-box' }}
      onChange={event => flow.edit(kind, subject, 'note', event.target.value)} rows={2} />
  </label>;
}

const choiceLabels: Record<string, string> = {
  REDUCE: '요구 범위 줄이기', WAIT: '보류하기', REQUEST_HOST_FEATURE: 'Host 기능 지원 요청',
};

function DecisionDraftReceipt({ projectId, record }: { projectId: string; record: DecisionRecord }) {
  if (!record.eventId || record.kind === 'HOTL') return null;
  const drafts = studioInputMemory.projectValues<{ draft: InputDraft | null }>(projectId, 'server-input-draft')
    .map(row => row.draft).filter((draft): draft is InputDraft => !!draft && draft.target.kind === 'DECISION_COMMENT'
      && (record.kind === 'HOST'
        ? draft.target.decision_kind === 'HOST_CONTRACT' && draft.target.request_id === record.hostReceipt?.request_event_id
          && draft.target.target_digest === record.hostReceipt?.contract_fingerprint
        : draft.target.request_id === record.body?.decision_request_id && draft.target.target_digest === record.body?.expected_digest
          && draft.target.subject_id === (record.body?.dataset_key || record.body?.capability)));
  return <>{drafts.map(draft => <StudioInputDraftControls key={draft.draft_id} projectId={projectId}
    selector={{ kind: draft.target.kind, task_id: draft.target.task_id, decision_kind: draft.target.decision_kind,
      request_id: draft.target.request_id, subject_id: draft.target.subject_id }} expectedTarget={draft.target}
    content={{ text: record.note.trim(), decision: record.choice }} onRestore={() => undefined}
    disabled receiptOnly submissionId={record.eventId} />)}</>;
}

function CapabilityCard({ row, flow, disabled, projectId, serverDrafts }: {
  row: CapabilityDecision; flow: StudioDecisionFlow; disabled: boolean; projectId: string; serverDrafts: boolean;
}) {
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const subject = capabilitySubject(row);
  const record = state.records[flow.keyFor('CAPABILITY', subject)];
  const [confirmed, setConfirmed] = useState('');
  const confirmation = JSON.stringify([subject, record?.choice || '', record?.note || '']);
  // 데이터셋 초안은 선택 결과가 아닌 현재 충돌에 실제 참여한 첫 task에 고정한다.
  const draftTaskId = row.decision_kind === 'DATASET' ? row.choices[0] : row.task_id;
  const draftSelector = { kind: 'DECISION_COMMENT' as const, task_id: draftTaskId || '',
    decision_kind: row.decision_kind === 'DATASET' ? 'DATASET' as const : 'CAPABILITY' as const,
    request_id: row.decision_request_id || '', subject_id: row.capability || row.dataset_key || '' };
  const locked = disabled || !capabilityActionable(row) || state.capabilities?.round_metadata_status !== 'READY'
    || (!!record && record.outcome !== 'EDITING');
  return <section aria-label={row.decision_kind === 'DATASET' ? '데이터 선언 충돌 결정' : '지원 능력 결정'}>
    <h4>{row.dataset_key ? '데이터 선언 선택' : '지원 능력 선택'} · {row.capability || row.dataset_key}</h4>
    <p>{row.reason || row.status_label || '서버가 제공한 선택지에서 처리 방법을 정하세요.'}</p>
    {!!row.differences?.length && <details open><summary>충돌하는 선언의 차이</summary>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(row.differences, null, 2)}</pre>
    </details>}
    {!capabilityActionable(row) && <p role="status">서버 결정 차수가 준비되지 않았거나 이미 처리 중입니다. 다시 제출하지 않고 조회하세요.</p>}
    <label>처리 방법 <select value={record?.choice || ''} disabled={locked}
      onChange={event => flow.edit('CAPABILITY', subject, 'choice', event.target.value)}>
      <option value="">선택하세요</option>
      {row.choices.map(choice => <option key={choice} value={choice}>{choiceLabels[choice] || `기준 선언: ${choice}`}</option>)}
    </select></label>
    <Note flow={flow} kind="CAPABILITY" subject={subject} record={record} disabled={locked} />
    {serverDrafts && capabilityActionable(row) && <StudioInputDraftControls projectId={projectId}
      selector={draftSelector} expectedTarget={{ ...draftSelector, target_digest: row.expected_digest }}
      content={{ text: record?.note.trim() || '', decision: record?.choice || '' }} disabled={locked}
      submissionId={record?.eventId}
      onRestore={content => {
        if (locked || (content.decision && !row.choices.includes(content.decision))) return;
        flow.edit('CAPABILITY', subject, 'note', content.text);
        flow.edit('CAPABILITY', subject, 'choice', content.decision); setConfirmed('');
      }} />}
    <label><input type="checkbox" checked={confirmed === confirmation} disabled={locked || !record?.choice}
      onChange={event => setConfirmed(event.target.checked ? confirmation : '')} />현재 선택과 이유를 확인했습니다.</label>
    <button type="button" disabled={locked || confirmed !== confirmation || !row.choices.includes(record?.choice || '')}
      onClick={() => { void flow.resolve(row); }}>선택을 초안에 반영</button>
    <small>초안 반영은 계약 승인이나 실행 재개가 아닙니다.</small>
  </section>;
}

export function StudioDecisionPanel({ vm, selections, onDecisionKeyChange, onRestoreSelections,
  apiFactory = createStudioDecisionApi }: StudioDecisionPanelProps) {
  const identity = studioIdentityKey();
  // 합성 결정 API를 주입한 검증 화면이 실제 서버 초안 API에 접근하지 않도록 한다.
  const serverDrafts = apiFactory === createStudioDecisionApi;
  const taskHint = vm.decisions[0]?.id || vm.run.sprintId || 'sprint_init';
  const flow = useMemo(() => createStudioDecisionFlow(vm.project.id,
    apiFactory(vm.project.id, identity), taskHint), [vm.project.id, identity, taskHint, apiFactory]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const [confirmedKey, setConfirmedKey] = useState('');
  const [hostConfirmedKey, setHostConfirmedKey] = useState('');
  const currentProjectId = useFactoryStore(store => store.currentProjectId);
  const rawState = useFactoryStore(store => store.state);
  const rawQuestions = currentProjectId === vm.project.id
    ? (rawState as unknown as Record<string, unknown> | null)?.clarification_questions : undefined;
  let questionMaterial = '';
  try { questionMaterial = canonicalQuestionJson(rawQuestions); } catch { /* 질문 원문 미확인은 제출 차단 상태다. */ }
  const shownQuestionMaterial = canonicalQuestionJson(vm.clarify.questions);
  const verificationKey = JSON.stringify([identity, vm.project.id, state.hotl?.questions_digest || '', questionMaterial, shownQuestionMaterial]);
  const [verifiedQuestionKey, setVerifiedQuestionKey] = useState('');
  useEffect(() => {
    let active = true;
    const digest = state.hotl?.questions_digest || '';
    if (questionMaterial && digest) {
      void verifyHotlQuestions({ rawQuestions: JSON.parse(questionMaterial), displayedQuestions: JSON.parse(shownQuestionMaterial) }, digest)
        .then(valid => { if (active && identity === studioIdentityKey()) setVerifiedQuestionKey(valid ? verificationKey : ''); });
    }
    return () => { active = false; };
  }, [identity, verificationKey, questionMaterial, shownQuestionMaterial, state.hotl?.questions_digest]);
  useEffect(() => {
    flow.activate(); void flow.load();
    const refresh = () => { void flow.load(); };
    const invalidate = () => { flow.invalidate(); };
    window.addEventListener('factory:contract-review-pending', refresh);
    window.addEventListener('factory:session-changed', invalidate);
    window.addEventListener('factory:acting-user-changed', invalidate);
    window.addEventListener('factory:enterprise-context-changed', invalidate);
    return () => {
      flow.invalidate();
      window.removeEventListener('factory:contract-review-pending', refresh);
      window.removeEventListener('factory:session-changed', invalidate);
      window.removeEventListener('factory:acting-user-changed', invalidate);
      window.removeEventListener('factory:enterprise-context-changed', invalidate);
    };
  }, [flow]);
  const hotl = state.hotl;
  const hotlKey = hotl?.available ? flow.keyFor('HOTL', hotlSubject(hotl)) : '';
  useEffect(() => {
    if (state.loaded) onDecisionKeyChange?.(hotlKey);
  }, [hotlKey, state.loaded, onDecisionKeyChange]);

  if (!vm.project.id) return null;
  const host = state.host;
  const hostRound = host ? hostSubject(state.hostTaskId, host) : '';
  const hostKey = flow.keyFor('HOST', hostRound);
  const hostDraft = state.records[hostKey];
  const hotlDraft = state.records[hotlKey];
  const hotlConfirmation = JSON.stringify([hotlKey, questionMaterial, shownQuestionMaterial, hotlDraft?.note || '', selections]);
  const hostConfirmation = JSON.stringify([hostKey, hostDraft?.note || '', hostDraft?.choice || '']);
  const hotlLocked = state.busy || !flow.canResume() || (!!hotlDraft && hotlDraft.outcome !== 'EDITING');
  const hostLocked = state.busy || !flow.canDecide() || !host?.pending || host.actionable !== true || !host.request_event_id
    || !isDecisionDigest(host.compiled_fingerprint) || (!!hostDraft && hostDraft.outcome !== 'EDITING');
  const isClarify = hotl?.decision_kind === 'CLARIFICATION';
  const clarifyReady = !isClarify || (vm.clarify.awaiting && !!onDecisionKeyChange && !!questionMaterial
    && verifiedQuestionKey === verificationKey);
  const items = state.capabilities ? [...state.capabilities.capability_decisions, ...state.capabilities.dataset_conflicts] : [];
  const receipts = Object.values(state.records).filter(record => record.outcome !== 'EDITING');
  const unavailable = state.error && [401, 403, 404].includes(state.error.status);
  return <article className="decision-dock" aria-label="현재 결정" data-testid="studio-decision-panel"
    style={{ gridTemplateColumns: 'minmax(0, 1fr)', alignItems: 'start', overflowWrap: 'anywhere' }}>
    <header><b>현재 결정</b><button type="button" className="quiet" disabled={state.busy}
      onClick={() => { void flow.load(); }}>{state.busy ? '확인 중…' : '현재 결정 다시 조회'}</button></header>
    <p><small>작성 중 입력은 로그인 세션의 메모리에 보존됩니다. 서버 보관은 별도 «입력 초안 저장» 후 확인되며, 저장 자체는 결정·실행이 아닙니다.</small></p>
    {!serverDrafts && <p>합성 결정 API 화면입니다. 실제 서버 초안 보관에는 연결하지 않습니다.</p>}
    {state.error && <p className="dock-error" role="alert">
      {unavailable ? '현재 사용자로 이 작업을 확인할 수 없습니다. 이전 결정 내용과 동작을 숨겼습니다.' : state.error.message}
      {state.error.status ? ` (${state.error.status})` : ''}
      {state.error.reasonCode ? ` · ${state.error.reasonCode}` : ''}
      {!unavailable && ' 실패를 결정 없음으로 처리하지 않습니다. 현재 상태를 조회하세요.'}
    </p>}
    {!state.loaded && !state.error && <p role="status">서버의 현재 결정 차수를 확인하고 있습니다.</p>}
    {state.loaded && <div className="decision-body" style={{ display: 'grid', gap: 18 }}>
      {state.capabilityError && <p role="status">지원 능력 결정은 아직 계약 초안 판을 확인할 수 없습니다.
        현재는 서버가 확인한 명확화 답변만 제출할 수 있습니다. ({state.capabilityError.reasonCode})</p>}
      {hotl?.status === 'UNKNOWN' && <p role="alert">현재 재개 차수를 확인할 수 없습니다. 재개하지 말고 다시 조회하세요. {hotl.reason_code}</p>}
      {host?.pending && <section aria-label="Host 계약 검토">
        <h4>Host 계약 승인</h4><p>{host.reason || '이 앱이 사용할 데이터와 권한의 계약을 검토하세요.'}</p>
        <details><summary>검토 대상 확인</summary><p>요청 사건: {host.request_event_id || '준비되지 않음'}</p>
          <p>계약 지문: {host.compiled_fingerprint || '확인되지 않음'}</p></details>
        {host.actionable !== true && <p role="status">{host.not_actionable_reason || '현재 승인할 수 있는 요청 사건이 없습니다.'}</p>}
        <label>검토 결정 <select value={hostDraft?.choice || ''} disabled={hostLocked}
          onChange={event => flow.edit('HOST', hostRound, 'choice', event.target.value)}>
          <option value="">선택하세요</option><option value="APPROVE">승인</option><option value="REJECT">반려</option>
        </select></label>
        <Note flow={flow} kind="HOST" subject={hostRound} record={hostDraft} disabled={hostLocked} />
        {serverDrafts && host.request_event_id && isDecisionDigest(host.compiled_fingerprint) && <StudioInputDraftControls
          projectId={vm.project.id} selector={{ kind: 'DECISION_COMMENT', decision_kind: 'HOST_CONTRACT', task_id: state.hostTaskId,
            request_id: host.request_event_id, subject_id: '' }}
          expectedTarget={{ kind: 'DECISION_COMMENT', decision_kind: 'HOST_CONTRACT', task_id: state.hostTaskId,
            request_id: host.request_event_id, target_digest: host.compiled_fingerprint, subject_id: '' }}
          content={{ text: hostDraft?.note.trim() || '', decision: hostDraft?.choice || '' }} disabled={hostLocked}
          submissionId={hostDraft?.eventId}
          onRestore={content => {
            if (hostLocked || !['', 'APPROVE', 'REJECT'].includes(content.decision)) return;
            flow.edit('HOST', hostRound, 'note', content.text); flow.edit('HOST', hostRound, 'choice', content.decision);
            setHostConfirmedKey('');
          }} />}
        <label><input type="checkbox" checked={hostConfirmedKey === hostConfirmation} disabled={hostLocked}
          onChange={event => setHostConfirmedKey(event.target.checked ? hostConfirmation : '')} />현재 요청·계약 지문·결정 이유를 확인했습니다.</label>
        <div className="decision-actions"><button type="button" disabled={hostLocked || hostDraft?.choice !== 'APPROVE' || hostConfirmedKey !== hostConfirmation}
          onClick={() => { void flow.decide('APPROVE'); }}>계약 승인 기록</button>
          <button type="button" className="quiet" disabled={hostLocked || hostDraft?.choice !== 'REJECT' || hostConfirmedKey !== hostConfirmation || !hostDraft?.note.trim()}
            onClick={() => { void flow.decide('REJECT'); }}>이유를 남기고 반려</button></div>
        <small>승인 기록·상태 반영·실행 재개는 서로 다른 단계입니다. 의견은 앞뒤 공백을 제외하고 저장·제출합니다.</small>
      </section>}
      {items.map((row, index) => <CapabilityCard key={`${capabilitySubject(row)}:${index}`}
        row={row} flow={flow} disabled={state.busy} projectId={vm.project.id} serverDrafts={serverDrafts} />)}
      {!!state.capabilities?.other_errors.length && <p role="alert">결정 선택으로 해결할 수 없는 계약 오류 {state.capabilities.other_errors.length}건이 있습니다. 계약 내용을 먼저 확인하세요.</p>}
      {hotl?.available && <section aria-label={isClarify ? '요구 확인 답변' : '일반 산출물 검토'}>
        <h4>{isClarify ? '요구 확인 답변' : '일반 산출물 검토 후 재개'}</h4>
        <p>{isClarify ? '현재 차수의 질문과 선택한 답변을 확인하세요.' : '현재 산출물을 확인한 뒤 의견을 남기고 재개합니다. Host 계약 승인을 대신하지 않습니다.'}</p>
        {isClarify && <p>{unansweredCount(vm.clarify.questions, selections)}개 미선택 — 빈 답변은 추천안대로 진행하는 것으로 전달됩니다.</p>}
        {!clarifyReady && <p role="alert">현재 질문 화면과 서버 차수 연결을 확인하지 못했습니다. 작업을 다시 조회하세요.</p>}
        {isClarify && <button type="button" className="quiet" disabled={state.busy}
          onClick={() => {
            const store = useFactoryStore.getState();
            if (identity !== studioIdentityKey() || store.currentProjectId !== vm.project.id) return;
            void store.fetchLatestState().then(() => {
              if (identity === studioIdentityKey() && useFactoryStore.getState().currentProjectId === vm.project.id) void flow.load();
            });
          }}>질문·결정 다시 조회</button>}
        {!flow.canResume() && <p role="status">계약 승인·지원 능력 결정 또는 오류 확인이 먼저 필요합니다.</p>}
        <Note flow={flow} kind="HOTL" subject={hotlSubject(hotl)} record={hotlDraft} disabled={hotlLocked} />
        {serverDrafts && <StudioInputDraftControls projectId={vm.project.id}
          selector={{ kind: isClarify ? 'CLARIFICATION' : 'DECISION_COMMENT', task_id: hotl.taskId,
            decision_kind: isClarify ? '' : 'GENERAL_HOTL', request_id: hotl.request_id, subject_id: '' }}
          expectedTarget={{ kind: isClarify ? 'CLARIFICATION' : 'DECISION_COMMENT', task_id: hotl.taskId,
            decision_kind: isClarify ? '' : 'GENERAL_HOTL', request_id: hotl.request_id,
            target_digest: hotl.questions_digest, subject_id: '' }}
          content={{ text: hotlDraft?.note || '', decision: '', ...(isClarify ? { selections } : {}) }}
          disabled={hotlLocked || !clarifyReady || (isClarify && !onRestoreSelections)}
          onRestore={content => {
            if (hotlLocked || !clarifyReady || (isClarify && !onRestoreSelections)) return;
            flow.edit('HOTL', hotlSubject(hotl), 'note', content.text);
            if (isClarify) onRestoreSelections?.(content.selections || {});
            setConfirmedKey('');
          }} />}
        <label><input type="checkbox" checked={confirmedKey === hotlConfirmation} disabled={hotlLocked || !clarifyReady}
          onChange={event => setConfirmedKey(event.target.checked ? hotlConfirmation : '')} />현재 차수의 {isClarify ? '질문과 답변' : '산출물'} 및 의견을 확인했습니다.</label>
        <button type="button" disabled={hotlLocked || !clarifyReady || confirmedKey !== hotlConfirmation}
          onClick={() => { void flow.resume(isClarify
            ? serializeClarifyAnswers(vm.clarify.questions, selections, hotlDraft?.note || '') : (hotlDraft?.note || '').trim(),
            isClarify ? { rawQuestions: structuredClone(rawQuestions), displayedQuestions: structuredClone(vm.clarify.questions) } : undefined); }}>
          {isClarify ? '현재 답변 제출하고 재개' : '검토 의견 제출하고 재개'}</button>
      </section>}
      {!hotl?.available && hotl?.status !== 'UNKNOWN' && !host?.pending && !state.capabilities?.pending
        && !state.capabilities?.other_errors.length && <p>현재 조회에서 대기 중인 결정이 없습니다. 실행 완료를 뜻하지는 않습니다.</p>}
      {receipts.map(record => <section key={record.key} aria-label="결정 제출 결과" className="studio-note"
        style={{ color: 'var(--surface-text, #222)' }}>
        <h4>{record.kind === 'HOST' ? 'Host 계약' : record.kind === 'HOTL' ? '재개 요청' : '지원 능력·데이터 결정'} 처리 기록</h4>
        <p role="status">{record.message}</p>
        {record.eventId && <p>원장 사건: {record.eventId}</p>}
        <details><summary>고정 요청과 보존 입력 확인</summary>
          <p>대상: {record.subject}</p><p>입력: {record.note || '(추가 의견 없음)'}</p>
          {record.hostReceipt && <p>계약 지문: {record.hostReceipt.contract_fingerprint}</p>}
        </details>
        {record.hostReceipt?.decision === 'APPROVE' && !record.hostReceipt.state_applied && <>
          <button type="button" disabled={state.busy}
            onClick={() => { void flow.reconcile(record.key); }}>{record.reconcileAttempted ? '동일 사건 다시 복구 확인' : '기존 승인 사건 반영 복구'}</button>
          <small>원래 사건·요청·지문으로만 멱등 복구합니다. 자동 재전송·새 승인·실행 시작은 하지 않습니다.</small>
        </>}
        {record.outcome === 'UNKNOWN' && <strong>결과 미확정 · 재전송 금지 · 조회로 상태 확인</strong>}
        {serverDrafts && (record.kind === 'HOST'
          ? !host?.pending || record.subject !== hostRound
          : !items.some(row => capabilitySubject(row) === record.subject && capabilityActionable(row)))
          && <DecisionDraftReceipt projectId={vm.project.id} record={record} />}
      </section>)}
    </div>}
  </article>;
}
