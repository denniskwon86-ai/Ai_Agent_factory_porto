import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createProcessInstallationApi, processContextIdentity, type ProcessDocument,
  type ProcessInstallationApi, type ProcessChangeReview, type InstallationUpgrade } from '../lib/processInstallationApi';
import { createInstallationFlow, type InstallationFlow, type InstallationFlowState } from '../lib/processInstallationFlow';
import { createProcessEditFlow, processBoundaryKey, type ProcessEditFlow } from '../lib/processConfigurationEdit';
import { ProcessConfigurationEditor } from './ProcessConfigurationEditor';
import './process-installation.css';

const MODE: Record<string, string> = { REAL: '실제', VIRTUAL: '가상', COMPETITOR_REFERENCE: '경쟁사 참조' };
const STAGES: Record<string, string> = {
  PLANNED: '요청 접수 · 설치 담당자 진행 필요', AWAITING_INSTALLER: '설치 담당자 대기',
  PREPARING: '업무 골격 준비 중', AWAITING_APPROVAL: '별도 승인자 검토 대기',
  APPLIED: '업무 골격 적용됨', FAILED_RETRYABLE: '재개 확인 필요',
  FAILED_BLOCKED: '차단 사유 확인 필요', CANCELLED: '취소됨', REJECTED: '반려됨',
};
const REVIEW_BLOCKERS: Record<string, string> = {
  PROCESS_DISTINCT_REVIEWER_REQUIRED: '작성자는 자신의 변경안을 승인할 수 없습니다.',
  PROCESS_HEAD_CONFLICT: '다른 구성이 먼저 승인되었습니다. 기준판을 다시 검토해야 합니다.',
  PROCESS_CHANGE_NOT_DRAFT: '이미 처리된 변경안입니다.',
  PROCESS_PERMISSION_DENIED: '현재 범위의 승인 권한이 없습니다.',
  PROCESS_ACTION_FORBIDDEN: '현재 범위의 승인 권한이 없습니다.',
  PROCESS_LEGACY_CONFLICT: '기존 업무 구성이 변경되었습니다. 기준 내용을 다시 확인해야 합니다.',
};
function subscribeIdentity(listener: () => void) {
  const events = ['factory:enterprise-context-changed', 'factory:session-changed'];
  events.forEach((name) => window.addEventListener(name, listener));
  return () => events.forEach((name) => window.removeEventListener(name, listener));
}

export function ProcessTree({ document, title }: { document: ProcessDocument; title: string }) {
  const [selected, select] = useState('');
  const byId = new Map(document.nodes.map((node) => [node.process_id, node]));
  const placements = [...document.placements]
    .sort((a, b) => a.position - b.position || a.placement_id.localeCompare(b.placement_id));
  const roots = placements.filter((p) => !p.parent_process_id && byId.get(p.process_id)?.level === 'L1');
  const active = roots.some((p) => p.process_id === selected) ? selected : roots[0]?.process_id || '';
  const children = placements.filter((p) => p.parent_process_id === active);
  return <section className="process-tree" aria-label={title}>
    <h4>{title}</h4>
    {!roots.length ? <p>표시할 상위 업무가 없습니다.</p> : <div className="process-tree-columns">
      <div className="process-root-list" aria-label="상위 업무 선택">
        {roots.map((p) => <button type="button" key={p.placement_id} aria-pressed={active === p.process_id}
          onClick={() => select(p.process_id)}>{byId.get(p.process_id)?.label}
          {p.hidden ? ' · 숨김' : ''}{!byId.get(p.process_id)?.enabled ? ' · 미사용' : ''}</button>)}
      </div>
      <div><h5>{byId.get(active)?.label}의 하위 업무</h5>
        {!children.length ? <p>하위 업무가 아직 없습니다.</p> : <ol>
          {children.map((p) => { const node = byId.get(p.process_id); return <li key={p.placement_id}>
            <strong>{node?.label}</strong>{p.hidden ? ' · 숨김' : ''}{!node?.enabled ? ' · 미사용' : ''}
            {p.kind === 'SHORTCUT' && <small> · 바로가기 (원래 소속: {byId.get(node?.parent_process_id || '')?.label})</small>}
            {node?.note && <p>{node.note}</p>}
          </li>; })}
        </ol>}
      </div>
    </div>}
  </section>;
}

type Props = { companyName: string; scopeLabel: string;
  apiFactory?: (identity: string) => ProcessInstallationApi };

export function ProcessInstallationPanel({ companyName, scopeLabel, apiFactory = createProcessInstallationApi }: Props) {
  const identity = useSyncExternalStore(subscribeIdentity, processContextIdentity, processContextIdentity);
  return <InstallationSession key={identity} identity={identity} companyName={companyName}
    scopeLabel={scopeLabel} apiFactory={apiFactory} />;
}

function InstallationSession({ identity, scopeLabel, apiFactory }: Props & {
  identity: string; apiFactory: (identity: string) => ProcessInstallationApi;
}) {
  const [companyWide, setCompanyWide] = useState(false);
  const [editFlows] = useState(() => [createProcessEditFlow(apiFactory(identity), false),
    createProcessEditFlow(apiFactory(identity), true)]);
  // 같은 세션의 적용 범위 왕복은 미확정 요청의 원입력·키를 유지한다. 다른 세션과 공유하지 않는다.
  const [flows] = useState(() => [createInstallationFlow(apiFactory(identity), false),
    createInstallationFlow(apiFactory(identity), true)]);
  return <section className="process-installation" aria-label="표준 업무 구성">
    <header><div><span className="process-kicker">업무 골격 · L1 / L2</span>
      <h3>우리 업무 구성</h3><p>표준 업무로 시작하고, 우리 조직에 맞게 수정하세요. 적용에는 별도 검토·승인이 필요합니다.</p></div>
    </header>
    <label className="process-scope">적용 범위
      <select value={companyWide ? 'company' : 'selected'} onChange={(e) => setCompanyWide(e.target.value === 'company')}>
        <option value="selected">현재 선택한 조직 · {scopeLabel || '상단에서 조직 선택 필요'}</option>
        <option value="company">운영 루트 전체 · 서버에서 권한 확인</option>
      </select>
    </label>
    <p className="process-muted">적용 범위별 입력·요청 번호는 이 화면을 연 동안 보존합니다. 사용자·회사 전환 시에는 새 문맥으로 조회합니다.</p>
    <InstallationScope key={String(companyWide)} flow={flows[companyWide ? 1 : 0]}
      editFlow={editFlows[companyWide ? 1 : 0]} companyWide={companyWide} />
  </section>;
}

function InstallationScope({ flow, editFlow, companyWide }: {
  flow: InstallationFlow; editFlow: ProcessEditFlow; companyWide: boolean;
}) {
  const originalState = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const editing = useSyncExternalStore(editFlow.subscribe, editFlow.getSnapshot, editFlow.getSnapshot);
  const state = { ...originalState, busy: originalState.busy || (editing.busy ? '업무 변경안 처리 중' : '') };
  const reviewSection = useRef<HTMLElement>(null);
  const reviewId = originalState.review?.change_id;
  useEffect(() => { if (reviewId) reviewSection.current?.focus(); }, [reviewId]);
  useEffect(() => { void flow.load(); return flow.invalidate; }, [flow]);
  useEffect(() => () => editFlow.invalidate(), [editFlow]);
  useEffect(() => {
    if (editing.error && [401, 403, 404].includes(editing.error.status)) flow.suspendAccess(editing.error);
  }, [flow, editing.error]);
  const needsBase = !editing.base;
  useEffect(() => {
    if (originalState.loaded && originalState.access && originalState.resolved?.payload) {
      editFlow.begin(originalState.resolved, originalState.access);
    }
  }, [editFlow, originalState.loaded, originalState.resolved, originalState.access, needsBase]);
  const canPropose = state.access?.permitted_actions.includes('propose') === true;
  const canRegister = state.access?.permitted_actions.includes('edit') === true;
  const locked = !!state.busy || state.startAttempted;
  const pack = state.packs.find((p) => p.artifact_digest === state.selectedDigest);
  const operation = state.operation;
  return <>
    <div role="status" aria-live="polite" className="process-status">
      {state.busy || (!state.loaded ? '회사·조직과 업무 구성을 확인합니다.' : '선택 범위 확인됨')}
    </div>
    {state.error && <div role="alert" className="process-error">
      <strong>{state.error.message}</strong>
      {state.error.nextAction && <p>{state.error.nextAction}</p>}
      {state.error.reasonCode && <details><summary>오류 상세</summary>{state.error.reasonCode} · HTTP {state.error.status}</details>}
      {!state.loaded && !state.boundaryChanged && <button type="button" disabled={!!state.busy} onClick={() => void flow.load()}>다시 조회</button>}
    </div>}
    {state.boundaryChanged && state.pendingAccess && <div className="process-safety">
      <p>새 범위: {state.pendingAccess.context_root_label || state.pendingAccess.boundary.context_root_id}
        {' / '}{state.pendingAccess.target_label || state.pendingAccess.boundary.scope_node_id || '루트 전체'}</p>
      <p>이전 계획은 새 범위로 전송하지 않습니다. 미확정 제출은 원입력·요청 번호를 메모리에 보존합니다.</p>
      <button type="button" onClick={() => void flow.confirmBoundary()}>변경된 범위를 확인하고 새로 시작</button>
    </div>}
    {state.mutationNeedsRefresh && !state.boundaryChanged && <div className="process-safety" role="status">
      <strong>처리 결과 확인이 필요합니다.</strong>
      <p>재개·승인을 다시 보내지 않습니다. 같은 요청의 현재 상태를 먼저 조회하세요.</p>
      <button type="button" disabled={!!state.busy} onClick={() => void flow.refreshReview()}>처리 결과만 다시 조회</button>
    </div>}
    {state.loaded && state.access && <>
      <div className="process-context"><strong>{state.access.context_root_label || state.access.boundary.tenant_id}</strong>
        <span>{MODE[state.access.boundary.entity_mode] || state.access.boundary.entity_mode}</span>
        <span>{state.access.target_label || (companyWide ? '운영 루트 전체' : '선택 조직')}</span>
        <details><summary>서버 확인 범위</summary><div>루트: {state.access.boundary.context_root_id}</div>
          <div>조직: {state.access.boundary.scope_node_id || '루트 전체'}</div></details>
      </div>
      <div className="process-safety">업무 골격만 준비합니다. 데이터 미연결 · 현업 검토 필요 · 앱 사용 준비 미완료</div>
      {state.preservedAttempts.length > 0 && <p className="process-safety">이전 범위의 요청을 보존하고 있습니다. 새 범위에서 자동 재전송하지 않습니다. 이 화면을 닫으면 메모리 입력은 사라지며 서버 접수 내역은 원래 범위에서 조회해야 합니다.</p>}
      {state.resolved?.payload ? <ProcessTree document={state.resolved.payload} title="현재 승인된 업무 구성" />
        : <p>이 범위에 승인된 L1/L2 구성이 아직 없습니다. 아래에서 표준 업무를 선택해 시작하세요.</p>}
      {editing.base && processBoundaryKey(editing.base.boundary) === processBoundaryKey(state.access.boundary)
        ? <ProcessConfigurationEditor flow={editFlow} busy={!!originalState.busy || state.mutationNeedsRefresh}
          onReview={(id) => { void flow.reviewChange(id); }} />
        : editing.base && <div className="process-safety"><p>다른 범위에서 시작한 편집 입력을 보존하고 있습니다. 원래 범위로 돌아가 접수 결과를 확인하세요.</p>
          {(!editing.attempt || editing.receipt || editing.conflict || editing.rejected) && <button type="button" disabled={!!state.busy}
            onClick={() => editFlow.reset()}>이전 편집을 버리고 현재 범위에서 시작</button>}
        </div>}
      {!canPropose && <p className="process-safety">새 설치 제안은 할 수 없습니다. 기존 요청의 진행·승인은 아래에서 각 요청의 권한을 확인합니다.</p>}
      <details className="process-install-more" open={!state.resolved?.payload}>
      <summary>{state.resolved?.payload ? '표준 업무키트 추가 설치 · 설치 요청 관리' : '표준 업무로 처음 시작하기'}</summary>
      <section className="process-step"><h4>1. 필요한 표준 업무 선택</h4>
        {!state.packs.length && <p>현재 조회 가능한 표준 업무가 없습니다.</p>}
        {state.packs.map((p) => <label className="process-pack" key={p.artifact_digest}>
          <input type="radio" name="process-pack" checked={state.selectedDigest === p.artifact_digest}
            disabled={!canPropose || locked} onChange={() => flow.selectPack(p)} />
          <span><strong>{p.name}</strong><small>판본 {p.version} · {p.data_class} · {p.state}
            {p.setup_only ? ' · 골격 전용' : ''}</small></span>
        </label>)}
        {pack && <>
          <fieldset disabled={!canPropose || locked}><legend>포함할 업무키트</legend>
            {pack.business_kit_ids.map((id) => <label className="process-kit" key={id}>
              <input type="checkbox" checked={state.selectedKits.includes(id)}
                onChange={(e) => flow.selectKit(id, e.target.checked)} />
                {pack.business_kits?.find((kit) => kit.business_kit_id === id)?.label || id}</label>)}
          </fieldset>
          {canRegister ? <div className="process-register">
            <button type="button" disabled={locked} onClick={() => void flow.register()}>이 판본을 설치 후보로 등록</button>
            <span>{state.registeredDigest === pack.artifact_digest ? '등록 확인됨 · 다음으로 계획을 확인하세요.'
              : '처음 사용하는 판본은 등록이 필요합니다. 등록만으로 업무가 설치되지는 않습니다.'}</span>
          </div> : <p>등록된 판본은 계획 확인이 가능합니다. 미등록 오류가 나면 설치 담당자에게 등록을 요청하세요.</p>}
        </>}
      </section>
      <section className="process-step"><h4>2. 설치 계획 확인</h4>
        {state.legacy.map((source) => <label className="process-field" key={source.profile_id}>
          기존 구성: {source.payload.nodes?.map((n) => n.label || n.key).join(' → ') || source.profile_id}
          <select value={state.legacyChoices[source.profile_id] || ''} disabled={!canPropose || locked}
            onChange={(e) => flow.setLegacyChoice(source.profile_id, e.target.value as 'KEEP_LEGACY' | 'MIGRATE')}>
            <option value="" disabled>원본 처리 방법 선택</option>
            <option value="KEEP_LEGACY">기존 원본 유지 · 새 구성에 이관하지 않음</option>
            <option value="MIGRATE">기존 업무 ID를 보존하여 새 구성에 이관</option>
          </select>
        </label>)}
        <label className="process-field">설치 이유
          <textarea value={state.reason} maxLength={4000} rows={2} disabled={!canPropose || locked}
            placeholder="예: 원료구매의 구매계획부터 입고까지 표준 골격을 준비합니다."
            onChange={(e) => flow.setReason(e.target.value)} />
        </label>
        <button type="button" disabled={!canPropose || locked || !pack || !state.selectedKits.length || !state.reason.trim()}
          onClick={() => void flow.prepare()}>설치할 업무 미리보기</button>
        {state.prepared && <><ProcessTree document={state.prepared.plan.preview} title="설치 계획 미리보기 · 아직 적용 전" />
          <p>이 계획은 업무 구성 초안입니다. 데이터 연결과 별도 승인자의 검토가 남아 있습니다.</p>
        </>}
      </section>
      <section className="process-step"><h4>3. 설치 요청 및 진행 확인</h4>
        {state.error && <p className="process-safety">조회에 실패한 경우 아래 상태는 마지막 조회 결과입니다. 최신 상태로 확인하지 않았습니다.</p>}
        <div className="process-actions"><button type="button" disabled={!canPropose || !!state.busy || !state.prepared || !!state.submittedOperationId}
          onClick={() => void flow.start()}>{state.startAttempted ? '같은 요청으로 결과 확인·재시도' : '검토한 계획으로 설치 요청'}</button>
          <button type="button" disabled={!!state.busy} onClick={() => void flow.refresh()}>설치 상태 새로고침</button></div>
        {state.startAttempted && !state.submittedOperationId && <p>요청 결과가 확정될 때까지 입력·요청 번호를 보존합니다. 새로고침은 조회만 수행합니다.</p>}
        {state.submittedOperationId && <p>이번 설치 요청: {state.submittedOperationId}
          <button type="button" disabled={!!state.busy} onClick={() => void flow.refresh(state.submittedOperationId)}>이번 요청 상태 보기</button></p>}
        {state.startRejected && <button type="button" disabled={!!state.busy} onClick={() => void flow.replan()}>입력을 유지하고 최신 구성으로 다시 계획</button>}
        {operation && <div className="process-operation"><h5>{operation.operation_id === state.submittedOperationId ? '이번 요청 상세' : '선택한 요청 상세'}</h5>
          <strong>{STAGES[operation.stage] || `확인 필요 · ${operation.stage}`}</strong>
          <p>요청 번호: {operation.operation_id}</p>
          {operation.error_code && <p>확인할 사유: {operation.error_code}</p>}
          {operation.upgrade && <UpgradeActivation flow={flow} state={state} upgrade={operation.upgrade} />}
          <p>요청자: {operation.actor} · 설치 담당자: {operation.installer || '아직 지정되지 않음'}</p>
          <OperationActions key={`${operation.operation_id}:${operation.revision}`} flow={flow} state={state} />
          {operation.change_id && <button type="button" disabled={!!state.busy}
            onClick={() => void flow.reviewChange(operation.change_id)}>이 요청의 변경 전후 확인</button>}
          <p>새로고침은 조회만 수행합니다. 업무 골격의 적용과 데이터·앱 사용 준비는 별개입니다.</p>
        </div>}
        <h5>이 범위의 설치 요청</h5>
        {!state.operations.length ? <p>조회된 설치 요청이 없습니다.</p> : <ul className="process-operation-list">
          {state.operations.map((op) => <li key={op.operation_id}>
            <span>{STAGES[op.stage] || `확인 필요 · ${op.stage}`}
              {op.upgrade && ` · 판본 ${op.upgrade.from_version} → ${op.upgrade.to_version} ${ACTIVATION[op.upgrade.activation]?.short || op.upgrade.activation}`}
              <small>{op.operation_id}</small></span>
            <button type="button" disabled={!!state.busy} onClick={() => void flow.refresh(op.operation_id)}>상태 보기</button>
          </li>)}
        </ul>}
        {state.nextOffset !== null && <button type="button" disabled={!!state.busy} onClick={() => void flow.more()}>이전 요청 더 보기</button>}
      </section>
      </details>
      <section ref={reviewSection} tabIndex={-1} className="process-step" aria-label="업무 구성 검토 및 승인">
        <h4>4. 변경 내용 검토 및 승인</h4>
        <p>작성자와 다른 적격 승인자가 변경 전후 내용을 검토합니다. 설치 담당자와 승인자가 반드시 다른 사람이어야 하는 것은 아닙니다.</p>
        <button type="button" disabled={!!state.busy} onClick={() => void flow.loadChanges()}>검토 대기 목록 조회</button>
        {state.changesLoaded && (!state.changes.length ? <p>현재 범위에 검토 대기 중인 변경안이 없습니다.</p>
          : <ul className="process-operation-list">{state.changes.map((change) => <li key={change.change_id}>
            <span>{change.reason}<small>작성자 {change.actor} · 기준판 {change.base_head_version}
              {change.review_blockers.length > 0 ? ' · 승인 전 확인 필요' : ''}</small></span>
            <button type="button" disabled={!!state.busy} onClick={() => void flow.reviewChange(change.change_id)}>변경 전후 확인</button>
          </li>)}</ul>)}
        {state.nextChangeOffset !== null && <button type="button" disabled={!!state.busy}
          onClick={() => void flow.moreChanges()}>이전 변경안 더 보기</button>}
        {state.review && <ProcessReviewPanel key={`${state.review.change_id}:${state.review.draft_digest}:${state.review.status}`}
          flow={flow} state={state} review={state.review} />}
      </section>
    </>}
  </>;
}

/** [2026-09-26] 판본 업그레이드의 활성화 상태. 새 판본은 **승인 뒤에만** 활성화된다(Codex §19.1). */
const ACTIVATION: Record<string, { short: string; text: string }> = {
  NOT_REQUESTED: { short: '· 적용 전', text: '설치 담당자의 명시 적용 전입니다. 현재 판본이 그대로 활성입니다.' },
  AWAITING_APPROVAL: { short: '· 승인 대기', text: '승인 전까지 현재 판본이 그대로 활성입니다. 계약·인증·프로필은 바뀌지 않았습니다.' },
  NOT_ACTIVATED: { short: '· 활성화 안 됨', text: '반려·취소되어 판본이 바뀌지 않았습니다.' },
  ACTIVE: { short: '· 활성', text: '새 판본이 활성화되었습니다. 기존 인증분은 새 판본 계약으로 재인증한 뒤 운영에 쓸 수 있습니다.' },
  ACTIVATION_PENDING: { short: '· 활성화 대기', text: '업무 구성은 승인됐지만 판본 활성화가 끝나지 않았습니다. 그동안 새 판본의 운영 사용은 막혀 있습니다.' },
};

export function UpgradeActivation({ flow, state, upgrade }: {
  flow: InstallationFlow; state: InstallationFlowState; upgrade: InstallationUpgrade;
}) {
  const view = ACTIVATION[upgrade.activation];
  const pending = upgrade.activation === 'ACTIVATION_PENDING';
  return <div className={pending ? 'process-safety' : undefined} role={pending ? 'status' : undefined}>
    <p><strong>판본 업그레이드 {upgrade.from_version} → {upgrade.to_version}</strong> · {view?.text || `확인 필요 · ${upgrade.activation}`}</p>
    {pending && upgrade.activation_error && <p>마지막 활성화 실패 사유: {upgrade.activation_error}</p>}
    {pending && (upgrade.retry
      ? <button type="button" disabled={!!state.busy} onClick={() => void flow.retryActivation()}>
        같은 승인으로 활성화 다시 시도</button>
      : <p>이 승인을 한 승인자만 같은 승인을 다시 요청해 활성화를 이을 수 있습니다.</p>)}
  </div>;
}

function OperationActions({ flow, state }: { flow: InstallationFlow; state: InstallationFlowState }) {
  const [adoptConfirmed, confirmAdopt] = useState(false);
  const actions = state.operation?.permitted_actions || [];
  const disabled = !!state.busy || state.mutationNeedsRefresh;
  return <div className="process-actions">
    {actions.includes('resume') && <button type="button" disabled={disabled} onClick={() => void flow.resume(false)}>설치 계속 진행</button>}
    {actions.includes('adopt') && <>
      <label className="process-kit"><input type="checkbox" checked={adoptConfirmed} disabled={disabled}
        onChange={(event) => confirmAdopt(event.target.checked)} />이 요청의 설치 담당자로 인수하겠습니다.</label>
      <button type="button" disabled={disabled || !adoptConfirmed} onClick={() => void flow.resume(true)}>담당자로 인수하고 진행</button>
    </>}
    {!actions.length && state.operation?.stage !== 'APPLIED' && <p>현재 이 요청에서 실행할 수 있는 재개·인수 행동이 없습니다. 상태와 담당자를 확인하세요.</p>}
  </div>;
}

export function ProcessReviewPanel({ flow, state, review }: {
  flow: InstallationFlow; state: InstallationFlowState; review: ProcessChangeReview;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const before = review.base_payload;
  const previous = new Map((before?.nodes || []).map((node) => [node.process_id, node]));
  const after = new Map(review.payload.nodes.map((node) => [node.process_id, node]));
  const changes = review.payload.nodes.flatMap((node) => {
    const old = previous.get(node.process_id);
    if (!old) return [`추가: ${node.label}`];
    const edits: string[] = [];
    if (old.label !== node.label) edits.push(`이름 ${old.label} → ${node.label}`);
    if (old.note !== node.note) edits.push('설명 변경');
    if (old.enabled !== node.enabled) edits.push(node.enabled ? '사용으로 변경' : '미사용으로 변경');
    if (old.parent_process_id !== node.parent_process_id) edits.push(`상위 업무 ${previous.get(old.parent_process_id)?.label || old.parent_process_id} → ${after.get(node.parent_process_id)?.label || node.parent_process_id}`);
    return edits.length ? [`${node.label}: ${edits.join(', ')}`] : [];
  });
  previous.forEach((node, id) => { if (!after.has(id)) changes.push(`제거: ${node.label}`); });
  for (const placement of review.payload.placements.filter((p) => p.kind === 'SHORTCUT')) {
    if (!before?.placements.some((p) => p.placement_id === placement.placement_id)) changes.push(
      `바로가기 추가: ${after.get(placement.process_id)?.label} → ${after.get(placement.parent_process_id)?.label} (원래 소속 유지)`);
  }
  for (const placement of (before?.placements || []).filter((p) => p.kind === 'SHORTCUT')) {
    if (!review.payload.placements.some((p) => p.placement_id === placement.placement_id)) changes.push(
      `바로가기 제거: ${previous.get(placement.process_id)?.label} · ${previous.get(placement.parent_process_id)?.label}에서만 제거`);
  }
  const placementsChanged = JSON.stringify(before?.placements || []) !== JSON.stringify(review.payload.placements);
  const canApprove = review.status === 'DRAFT' && review.permitted_actions.includes('approve')
    && !!review.principal_user_id && review.actor !== review.principal_user_id && review.review_blockers.length === 0;
  return <div className="process-review">
    <h5>검토할 변경안</h5>
    <p><strong>{review.reason}</strong></p>
    <p>작성자: {review.actor} · 현재 검토자: {review.principal_user_id}</p>
    <p>검토 기준판: {review.base_head_version} · 현재 승인판: {review.current_head_version}</p>
    <ul>{changes.map((text, index) => <li key={index}>{text}</li>)}
      {placementsChanged && <li>업무의 배치·순서·바로가기 구성이 변경됩니다. 아래 기준판과 제안판을 비교하세요.</li>}
      {!changes.length && !placementsChanged && <li>업무 이름·설명·배치는 동일합니다. 전체 변경안의 참조 정보도 확인하세요.</li>}
    </ul>
    <details><summary>기준판과 제안판 전체 업무 보기</summary><div className="process-review-columns">
      <div>{before ? <ProcessTree document={before} title="변경 전 · 고정 기준판" /> : <p>변경 전: 승인된 업무 구성이 없습니다.</p>}</div>
      <ProcessTree document={review.payload} title="변경 후 · 검토 대상" />
    </div></details>
    <details><summary>변경안 식별자·원문 확인</summary><p>변경안: {review.change_id}</p>
      <p>검토 지문: {review.draft_digest}</p><pre>{JSON.stringify(review.payload, null, 2)}</pre></details>
    {review.actor === review.principal_user_id && <p className="process-safety">내가 작성한 변경안입니다. 다른 적격 승인자에게 검토를 요청하세요.</p>}
    {review.review_blockers.length > 0 && <ul className="process-safety">
      {review.review_blockers.map((reason) => <li key={reason}>{REVIEW_BLOCKERS[reason] || reason}</li>)}
    </ul>}
    {state.approvalReceipt?.change_id === review.change_id && !state.applicationVerified && <p role="status">승인 처리 응답을 받았습니다. 적용 결과 조회 확인이 남아 있습니다.</p>}
    {state.applicationVerified && <div className="process-success" role="status">
      <strong>업무 골격 적용 기록을 확인했습니다.</strong>
      <p>{state.resolved?.profile_id === review.draft_profile_id ? '현재 승인된 업무 구성에도 반영되어 있습니다.'
        : '이 변경 이후 다른 승인판이 적용되었습니다. 위 현재 구성을 별도로 확인하세요.'}</p>
      <p>데이터 연결·인증과 앱 사용 준비는 별도입니다.</p>
    </div>}
    {review.status !== 'DRAFT' && !state.applicationVerified && <p>변경안 상태: {review.status}. 적용 여부는 아래에서 다시 조회할 수 있습니다.</p>}
    {canApprove && <>
      <label className="process-field">승인 이유<textarea rows={2} maxLength={4000} value={state.approvalReason}
        disabled={!!state.busy || state.mutationNeedsRefresh} placeholder="변경 목적과 적용 범위를 검토한 이유를 적어 주세요."
        onChange={(event) => flow.setApprovalReason(event.target.value)} /></label>
      <label className="process-kit"><input type="checkbox" checked={confirmed}
        disabled={!!state.busy || state.mutationNeedsRefresh} onChange={(event) => setConfirmed(event.target.checked)} />위 변경 전후와 적용 범위를 확인했습니다.</label>
      <button type="button" disabled={!!state.busy || state.mutationNeedsRefresh || !confirmed || !state.approvalReason.trim()}
        onClick={() => void flow.approveChange()}>검토한 변경안 승인</button>
    </>}
    {!canApprove && review.status === 'DRAFT' && !review.review_blockers.length && <p>이 변경안을 승인할 권한이 없습니다.</p>}
    <button type="button" disabled={!!state.busy} onClick={() => void flow.refreshReview()}>변경안·반영 결과 다시 조회</button>
  </div>;
}
