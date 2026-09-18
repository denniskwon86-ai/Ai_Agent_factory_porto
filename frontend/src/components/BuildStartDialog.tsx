// B5: 업무와 요구를 먼저 묻는다. 요구초안 저장은 실행/계약 승인과 별개다.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { HubDialog } from '../design/HubDialog';
import { DataPrepError, listInstances } from '../lib/dataPrepApi';
import { processContextIdentity } from '../lib/processInstallationApi';
import { registerLeaveGuard } from '../factory/studioLeaveGuard';
import { getStudioRequirementDraft, subscribeStudioRequirementContext,
  type StudioDeliverable, type StudioRequirementForm, type StudioRequirementRevision,
} from '../lib/studioRequirementDraft';
import { KitAppPanel } from './KitAppPanel';

export type BuildDeliverableType = StudioDeliverable;
export type BuildStartResult = {
  projectName: string; isMega: boolean; templateId: string; packIds: string[];
  masterDomains: string; mcpLiveGrounding: boolean; kitInstanceId: string;
  initialIdea?: string; processSelection?: StudioRequirementForm['processSelection'];
  requirementDraft?: Pick<StudioRequirementRevision, 'draft_id' | 'revision_id' | 'revision' | 'digest'>;
};
type CreateResult = void | boolean | string | null;
type KnowledgePackChoice = { pack_id: string; name?: string };
type KitInstanceChoice = {
  instance_id: string; label?: string; kit_id?: string; entity_mode?: string; status?: string;
};
export type BuildStartDialogProps = {
  templates: { template_id?: string; id?: string; name?: string; pipeline_name?: string; deliverable_type?: string }[];
  knowledgePacks: KnowledgePackChoice[]; packsBlocked: string; deliverableType?: BuildDeliverableType;
  onClose: () => void; onOpenDataPrep: () => void;
  onCreate: (result: BuildStartResult) => CreateResult | Promise<CreateResult>;
  /** B6 부모가 요구/업무/초안 참조를 실제 생성 흐름에 보존할 때만 true. 기존 부모는 미지원. */
  supportsInitialIdea?: boolean;
  /** 최초 빈 입력의 seed. 재마운트/서버 저장/실패 입력을 덮어쓰지 않는다. */
  initialIdea?: string; form?: Partial<StudioRequirementForm>;
  onFormChange?: (form: StudioRequirementForm) => void;
  /** 직접 B3 저장을 검증한 뒤에만 알린다. 이 콜백이 저장/승인 API를 다시 호출하면 안 된다. */
  onSaveDraft?: (revision: StudioRequirementRevision, form: StudioRequirementForm) => void;
  /** 현재 문맥에서 서버가 확인한 후보만 공급. 없으면 코드 직접 입력 대신 준비 필요를 표시. */
  masterDomainOptions?: { value: string; label: string }[];
  /** [B6-CONTEXT] 회사 문맥 칩. **대화상자 안**에 그려야 초점 가둠에서 닿는다.
   *  ⚠️ 여기서 칩을 «만들지» 않는다 — 모양·상태 출처가 갈라진다. 부모가 넣어 준다. */
  contextChip?: React.ReactNode;
};

export function BuildStartDialog(props: BuildStartDialogProps) {
  const identity = useSyncExternalStore(subscribeStudioRequirementContext, processContextIdentity, processContextIdentity);
  return <BuildStartContent key={identity + (props.deliverableType || 'software_app')} {...props} identity={identity} />;
}

function BuildStartContent({ templates, knowledgePacks, packsBlocked, deliverableType = 'software_app',
  onClose, onOpenDataPrep, onCreate, supportsInitialIdea = false, initialIdea, form: seed,
  onFormChange, onSaveDraft, masterDomainOptions, identity, contextChip,
}: BuildStartDialogProps & { identity: string }) {
  // 바깥 key가 사용자/문맥 변경 시 본문을 새로 마운트한다.
  const flow = useMemo(() => getStudioRequirementDraft(deliverableType), [deliverableType]);
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const form = state.form;
  const [message, setMessage] = useState('');
  const creating = state.creationState === 'PENDING';
  //: ★ [FIX1 · 지시 4] `'history'` 는 앱 «안» 이동(뒤로/앞으로)이다. 기존 확인 UI 를
  //:   그대로 쓰되, 「이동」이 곧 그 이동을 이어 가는 것이 되게 한다.
  const [navigation, setNavigation] = useState<'close' | 'data' | 'history' | null>(null);
  const pendingLeave = useRef<(() => void) | null>(null);
  const [domainQuery, setDomainQuery] = useState('');
  const [dataInstances, setDataInstances] = useState<KitInstanceChoice[] | null>(null);
  const [dataError, setDataError] = useState('');
  const active = useRef(true);
  const createLock = useRef(false);
  const appTemplates = useMemo(() => templates.filter((item) =>
    String(item.deliverable_type || 'software_app') === deliverableType), [templates, deliverableType]);
  const firstTemplate = appTemplates[0]?.template_id || appTemplates[0]?.id || '';
  const pending = Boolean(state.attempt && !state.rejected);
  const locked = state.busy || creating || pending || state.conflict;
  const saved = !!state.receipt && state.savedForm === JSON.stringify(form) && !state.attempt;
  const hasInput = !!(form.initialIdea || form.projectName || form.packIds.length || form.masterDomains
    || form.processSelection || form.kitInstanceId || form.kitStartInstanceId || form.isMega || form.mcpLiveGrounding);
  const needsData = deliverableType !== 'software_app';
  const template = appTemplates.find((item) => (item.template_id || item.id) === form.templateId);
  const dataSelected = !!form.kitInstanceId && !!dataInstances?.some((row) => row.instance_id === form.kitInstanceId);
  const requiresParent = !!form.initialIdea.trim() || !!form.processSelection;
  const createReason = state.creationState === 'UNKNOWN' ? '프로젝트 생성 결과가 불명입니다. 기존 작업 목록에서 먼저 확인해 주세요.'
    : state.creationState === 'CONFIRMED' ? '생성 응답을 받은 요청입니다. 기존 작업 화면에서 계속해 주세요.'
    : requiresParent && !supportsInitialIdea ? '현재 생성 연결은 요구문·업무 참조를 전달하지 못합니다. 먼저 요구초안으로 저장해 주세요.'
    : form.projectName.trim().length < 2 ? '추가 설정에서 업무 이름을 2자 이상 입력해 주세요.'
    : !template ? '사용할 업무 진행 절차를 확인해 주세요.'
    : needsData && !dataSelected ? '프로젝트 생성에는 현재 확인된 데이터 적용본이 필요합니다. 요구초안은 데이터 없이 저장할 수 있습니다.'
    : '';
  const canCreate = !locked && !createReason;
  const canSave = !creating && !state.busy && !state.conflict && !saved && !!form.initialIdea.trim()
    && !!state.access?.permitted_actions.includes('propose');
  const processDocument = state.resolved?.payload;
  const processOptions = state.resolved?.state === 'APPROVED' && !state.resolved.legacy_review_required
    ? (processDocument?.nodes || []).filter((node) => node.level === 'L2' && node.enabled
      && processDocument?.nodes.some((parent) => parent.process_id === node.parent_process_id && parent.level === 'L1' && parent.enabled))
    : [];
  const selectedProcess = form.processSelection?.process_ids.length === 1
    ? processOptions.find((node) => node.process_id === form.processSelection?.process_ids[0]
      && state.resolved?.profile_id === form.processSelection.profile_id) : undefined;
  const processValue = form.processSelection ? selectedProcess?.process_id || '__unavailable__' : '';
  const selectedDomains = form.masterDomains.split(',').map((value) => value.trim()).filter(Boolean);
  const domainOptions = (masterDomainOptions || []).filter((item) => item.value && !item.value.includes(','));
  const visibleDomains = domainOptions.filter((item) => item.label.toLocaleLowerCase().includes(domainQuery.toLocaleLowerCase()));
  const copy = deliverableType === 'hybrid_simulation' ? '새 시뮬레이터 요청'
    : deliverableType === 'document_report' ? '새 보고서 자동화 요청' : '새 업무 앱 요청';
  const labelStyle: React.CSSProperties = { display: 'grid', gap: 7, fontSize: 14, fontWeight: 600 };
  const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', minHeight: 42,
    padding: '9px 12px', font: 'inherit', borderRadius: 6, border: '1px solid var(--surface-border)',
    background: 'var(--surface-card)', color: 'var(--surface-text)' };
  const noteStyle: React.CSSProperties = { fontSize: 13, color: 'var(--surface-text-muted)', margin: '6px 0', lineHeight: 1.6 };

  useEffect(() => {
    active.current = true;
    flow.initialize({ templateId: firstTemplate, ...(initialIdea === undefined ? {} : { initialIdea }), ...seed });
    void flow.refresh();
    return () => { active.current = false; flow.markCreationUnknown(); };
    // seed는 처음 빈 양식에만 적용한다. 부모 재렌더로 편집 중 원문을 덮지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow]);
  useEffect(() => {
    if (!needsData) return;
    let alive = true;
    listInstances().then((data) => {
      if (alive && processContextIdentity() === identity) setDataInstances(data.instances || []);
    }).catch((error: unknown) => {
      if (alive && processContextIdentity() === identity) setDataError((error as DataPrepError)?.message || '데이터 적용본을 조회하지 못했습니다.');
    });
    return () => { alive = false; };
  }, [needsData, identity]);
  useEffect(() => {
    if ((!hasInput || saved) && state.creationState !== 'PENDING' && state.creationState !== 'UNKNOWN') return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [hasInput, saved, state.creationState]);

  //: ★★★ [FIX1 · 지시 4] **앱 «안» 이동도 같은 확인을 거친다.**
  //:
  //: ⚠️ 위의 `beforeunload` 는 문서를 떠날 때만 뜬다 — 뒤로/앞으로의 대체 수단이 아니다.
  //:   종전에는 그 이동이 편집기를 즉시 닫아 이 확인을 통째로 건너뛰었다.
  //: ★ 정책(저장/유지/폐기)은 **아래 기존 UI 가 그대로** 가진다. 여기서 새로 만들지 않는다.
  useEffect(() => registerLeaveGuard({
    //: ⚠️ [FIX2 · 지시 4] 기존 `requestLeave` 와 **같은 제한**을 쓴다 — 생성 중·요청 중·
    //:   결과 미확인이면 떠나지 않는다. 한쪽만 느슨하면 그 문으로 입력이 빠져나간다.
    safe: () => !(hasInput && !saved) && !creating && !state.busy
      && state.creationState !== 'UNKNOWN',
    confirm: (proceed) => { pendingLeave.current = proceed; setNavigation('history'); },
    onConfirmError: () => setMessage('이동 확인을 띄우지 못했습니다. 입력은 그대로 있습니다. 다시 시도해 주세요.'),
  }), [hasInput, saved, creating, state.busy, state.creationState]);

  const update = (patch: Partial<StudioRequirementForm>) => {
    if (locked) return;
    flow.update(patch); setMessage('');
    onFormChange?.(flow.getSnapshot().form);
  };
  const save = async () => {
    if (!canSave) return null;
    const row = await flow.save();
    if (row && active.current && processContextIdentity() === identity) {
      try { onSaveDraft?.(row, flow.getSnapshot().form); }
      catch { setMessage('초안은 서버에 저장됐지만 부모 화면 연결에 실패했습니다. 아래 보관 번호를 유지해 주세요.'); }
    }
    return row;
  };
  const leave = (target: 'close' | 'data' | 'history') => {
    setNavigation(null);
    if (target === 'history') { const go = pendingLeave.current; pendingLeave.current = null; go?.(); return; }
    if (target === 'close') onClose(); else onOpenDataPrep();
  };
  const requestLeave = (target: 'close' | 'data') => {
    if (creating || state.busy) return;
    if (hasInput && !saved) setNavigation(target); else leave(target);
  };
  const copyRequirement = async () => {
    try {
      await navigator.clipboard.writeText(form.initialIdea);
      if (active.current) setMessage('요구 내용을 복사했습니다. 복사는 서버 저장이 아닙니다.');
    } catch { if (active.current) setMessage('복사하지 못했습니다. 요구 입력에서 내용을 직접 선택해 복사해 주세요.'); }
  };
  const create = async () => {
    if (!canCreate || createLock.current || processContextIdentity() !== identity || !flow.beginCreate()) return;
    createLock.current = true; setMessage('');
    try {
      const result = await onCreate({ projectName: form.projectName.trim(), isMega: form.isMega,
        templateId: form.templateId, packIds: [...form.packIds], masterDomains: form.masterDomains,
        mcpLiveGrounding: form.mcpLiveGrounding, kitInstanceId: form.kitInstanceId,
        ...(supportsInitialIdea ? { initialIdea: form.initialIdea, processSelection: form.processSelection,
          ...(saved && state.receipt ? { requirementDraft: { draft_id: state.receipt.draft_id,
            revision_id: state.receipt.revision_id, revision: state.receipt.revision, digest: state.receipt.digest } } : {}) } : {}) });
      if (!active.current || processContextIdentity() !== identity) return;
      if (result === false || result === null) {
        flow.finishCreate('IDLE'); setMessage('프로젝트를 만들지 못했습니다. 입력은 유지했습니다.');
      }
      else if (result === undefined) {
        flow.finishCreate('UNKNOWN'); setMessage('생성 완료 응답이 없습니다. 작업 목록에서 결과를 확인하기 전에는 다시 생성하지 마세요.');
      } else {
        flow.finishCreate('CONFIRMED'); setMessage('프로젝트 생성 응답을 받았습니다. 연결된 작업 화면에서 확인해 주세요.');
      }
    } catch (error) {
      if (!active.current || processContextIdentity() !== identity) return;
      const status = Number((error as { status?: number })?.status);
      flow.finishCreate(status >= 400 && status < 500 ? 'IDLE' : 'UNKNOWN');
      setMessage(error instanceof Error ? error.message : '생성 결과를 확인하지 못했습니다. 입력을 보존했습니다.');
    } finally {
      createLock.current = false;
    }
  };

  return <HubDialog label={copy} onClose={() => requestLeave('close')}>
    <div className="afs-dialog-bar"><b>{copy}</b>
      <span>업무와 요구부터 정리하세요. 데이터와 업무 연결은 나중에 준비할 수 있습니다.</span>
      {/*: ★★★ [B6-CONTEXT · 결정 1] 회사 문맥을 **이 화면 안에** 둔다.
           ⚠️ 대화상자는 초점을 가둔다(focus trap). 바깥 셸의 칩을 쓰라고 하면 키보드
             사용자는 그 버튼에 **닿지 못한다.** 그래서 대화상자 «자기 머리 바» 에 둔다.
           ★ 모양·접근 이름·상태 출처는 셸과 같은 컴포넌트가 책임진다(부모가 넣어 준다). */}
      <div className="bar-actions">
        {contextChip}
        <button type="button" className="secondary-button" disabled={creating || state.busy}
          onClick={() => requestLeave('close')}>닫기</button></div>
    </div>
    <div className="afs-dialog-body" style={{ padding: 24, display: 'grid', gap: 18 }}>
      <label style={labelStyle}>어떤 업무인가요? (미정 가능)
        <select style={inputStyle} value={processValue} disabled={locked}
          onChange={(event) => update({ processSelection: event.target.value && state.resolved
            ? { kind: 'APPROVED', profile_id: state.resolved.profile_id, process_ids: [event.target.value] } : null })}>
          <option value="">업무 연결 미정 — 요구부터 정리하기</option>
          {processValue === '__unavailable__' && <option value="__unavailable__" disabled>이전 업무 선택 재확인 필요</option>}
          {processOptions.map((node) => <option value={node.process_id} key={node.process_id}>
            {processDocument?.nodes.find((parent) => parent.process_id === node.parent_process_id)?.label} · {node.label}
          </option>)}
        </select>
      </label>
      <p style={noteStyle}>{state.processError || (!state.access ? '현재 회사·조직의 저장 문맥 확인이 필요합니다.'
        : !processOptions.length ? '현재 선택할 수 있는 승인 업무가 없습니다. 업무 연결 미정으로 저장할 수 있습니다.'
        : '업무 선택은 데이터 사용권이나 실행 승인을 부여하지 않습니다.')}</p>
      <label style={labelStyle}>어떤 일을 쉽게 만들고 싶으세요?
        <textarea style={{ ...inputStyle, minHeight: 145, resize: 'vertical', fontWeight: 400 }} autoFocus
          value={form.initialIdea} disabled={locked}
          placeholder="예: 매일 엑셀에서 확인하는 원료 재고와 입고 예정량을 한눈에 보고 싶어요."
          onChange={(event) => update({ initialIdea: event.target.value })} />
      </label>
      <p style={noteStyle}>누가 쓰는지, 지금 불편한 일, 받고 싶은 결과를 편하게 적어 주세요. 실제 데이터가 없어도 요구초안을 저장할 수 있습니다.</p>
      <div className="process-actions">
        <button type="button" className="secondary-button" disabled={!form.initialIdea} onClick={copyRequirement}>요구 내용 복사</button>
        <span role="status" style={noteStyle}>{state.busy ? '문맥·저장 결과 확인 중…'
          : saved ? `요구초안 저장 확인 · ${state.receipt?.revision}판`
          : pending ? '저장 결과 확인 필요 · 원래 요청과 입력 보존 중' : '미저장 입력'}</span>
      </div>
      {state.error && <div role="alert" className="process-error">
        {state.error.message}
        <p style={noteStyle}>{state.error.status === 401 ? '다시 로그인한 뒤 같은 초안을 확인해 주세요.'
          : state.error.status === 403 ? '현재 범위의 초안 작성 권한을 확인해 주세요.'
          : state.error.status === 404 ? '현재 문맥에서 이 대상을 확인할 수 없습니다.'
          : state.error.status === 409 ? '다른 판본 또는 문맥 변경입니다. 자동으로 덮어쓰지 않습니다.'
          : '입력과 저장 요청은 보존했습니다.'}</p>
      </div>}
      {state.conflict && state.receipt && <div className="process-safety">
        <button type="button" disabled={state.busy} onClick={() => void flow.readLatest()}>최신 판본 확인</button>
        {state.latest && <><p>서버 최신 {state.latest.revision}판 · {String(state.latest.blueprint.title || '제목 없음')}</p>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(state.latest.blueprint, null, 2)}</pre>
          <button type="button" disabled={state.busy} onClick={() => flow.useLatest()}>차이를 확인했습니다 · 내 입력을 유지하고 이 판본 기준으로 편집</button></>}
      </div>}
      {message && <p role="status" style={noteStyle}>{message}</p>}
      {state.receipt && state.access && <details><summary>저장 정보</summary>
        <p style={noteStyle}>저장된 업무 이름: {String(state.receipt.blueprint.title || '제목 없음')}</p>
        <p style={noteStyle}>초안 보관 번호: {state.receipt.draft_id} · {state.receipt.revision}판</p>
        <p style={noteStyle}>요구초안만 저장했습니다. 실행 계약·데이터 인증·프로젝트 생성·승인은 수행하지 않았습니다.
          새로고침 뒤 자동 복원은 아직 연결되지 않았습니다. 보관 번호를 유지해 주세요.</p>
      </details>}
      <div className="process-actions">
        <button type="button" className="primary-button" disabled={!canSave} onClick={() => void save()}>
          {pending ? '같은 저장 요청 다시 확인' : '요구초안 저장'}</button>
        <button type="button" className="secondary-button" disabled={creating || state.busy} onClick={() => void flow.refresh()}>문맥·업무 목록 다시 확인</button>
      </div>
      {!form.initialIdea.trim() && <p style={noteStyle}>하고 싶은 일을 적으면 요구초안을 저장할 수 있습니다.</p>}
      {!!state.access && !state.access.permitted_actions.includes('propose') && <p style={noteStyle}>현재 조직에서는 요구초안 저장 권한이 없습니다. 입력을 복사해 보관하거나 작성 권한을 확인해 주세요.</p>}

      <details><summary style={{ cursor: 'pointer', fontWeight: 700, padding: '12px 0' }}>추가 설정 · 이름, 제작 조건, 업무키트</summary>
        <div style={{ display: 'grid', gap: 18, padding: '12px 0' }}>
          <label style={labelStyle}>업무 이름 (변경 가능)
            <input style={inputStyle} value={form.projectName} disabled={locked} maxLength={200}
              placeholder="비우면 요구 내용의 첫 부분을 초안 제목으로 사용합니다"
              onChange={(event) => update({ projectName: event.target.value })} />
          </label>
          <fieldset disabled={locked}><legend>프로젝트 유형</legend>
            <label><input type="radio" name="build-project-kind" checked={!form.isMega} onChange={() => update({ isMega: false })} /> 독립 프로젝트</label>{' '}
            <label><input type="radio" name="build-project-kind" checked={form.isMega} onChange={() => update({ isMega: true })} /> 여러 프로젝트를 묶는 통합 프로젝트</label>
          </fieldset>
          <label style={labelStyle}>업무 진행 절차
            <select style={inputStyle} value={template ? form.templateId : ''} disabled={locked}
              onChange={(event) => update({ templateId: event.target.value })}>
              <option value="">추천 가능한 절차 없음 / 미정</option>
              {appTemplates.map((item) => <option key={item.template_id || item.id} value={item.template_id || item.id}>
                {item.pipeline_name || item.name || '이름 없는 절차'}</option>)}
            </select>
          </label>
          <fieldset disabled={locked || !!packsBlocked}><legend>연결할 지식팩 (선택)</legend>
            {packsBlocked ? <p>{packsBlocked}</p> : !knowledgePacks.length ? <p style={noteStyle}>등록된 지식팩이 없습니다.</p>
              : knowledgePacks.map((pack) => <label key={pack.pack_id} style={{ display: 'block', padding: 6 }}>
                <input type="checkbox" checked={form.packIds.includes(pack.pack_id)} onChange={(event) => update({
                  packIds: event.target.checked ? [...form.packIds, pack.pack_id] : form.packIds.filter((id) => id !== pack.pack_id),
                })} /> {pack.name || '이름 없는 지식팩'}</label>)}
          </fieldset>
          {domainOptions.length ? <fieldset disabled={locked}><legend>연결할 기준정보 분야 (선택)</legend>
            <label style={labelStyle}>분야 검색<input style={inputStyle} value={domainQuery} onChange={(event) => setDomainQuery(event.target.value)} /></label>
            {visibleDomains.map((item) => <label key={item.value} style={{ display: 'block', padding: 6 }}>
              <input type="checkbox" checked={selectedDomains.includes(item.value)} onChange={(event) => update({
                masterDomains: (event.target.checked ? [...selectedDomains, item.value] : selectedDomains.filter((value) => value !== item.value)).join(','),
              })} /> {item.label}</label>)}
            {!visibleDomains.length && <p style={noteStyle}>검색 결과가 없습니다.</p>}
          </fieldset> : <p style={noteStyle}>기준정보 선택은 준비 필요 — 현재 문맥의 허용목록이 연결되지 않았습니다. 내부 코드를 직접 입력하지 않습니다.</p>}
          <label style={{ display: 'flex', gap: 10 }}><input type="checkbox" checked={form.mcpLiveGrounding} disabled={locked}
            onChange={(event) => update({ mcpLiveGrounding: event.target.checked })} />
            외부 연계 실측값 함께 보기 (별도 연계 권한이 필요하며 처리 시간·호출량이 늘어납니다)</label>
          {needsData && <label style={labelStyle}>기존 프로젝트 생성에 사용할 업무 데이터
            {dataError ? <span role="alert">{dataError}</span> : dataInstances === null ? <span>적용본 확인 중…</span>
              : <select style={inputStyle} value={form.kitInstanceId} disabled={locked} onChange={(event) => update({ kitInstanceId: event.target.value })}>
                <option value="">아직 선택하지 않음 — 요구초안 저장 가능</option>
                {form.kitInstanceId && !dataSelected && <option value={form.kitInstanceId} disabled>이전 적용본 재확인 필요</option>}
                {dataInstances.map((row) => <option key={row.instance_id} value={row.instance_id}>
                  {row.label || '이름 없는 적용본'} · {row.entity_mode || '문맥 확인 필요'}</option>)}
              </select>}
          </label>}
          <button type="button" className="secondary-button" disabled={state.busy || creating} onClick={() => requestLeave('data')}>업무 데이터 준비 열기</button>
          <div className="process-safety"><p style={noteStyle}>{createReason || '아래 버튼은 요구초안 저장이 아니라 기존 프로젝트 생성입니다.'}</p>
            <button type="button" disabled={!canCreate} onClick={() => void create()}>{creating ? '생성 결과 확인 중…' : '기존 프로젝트 생성'}</button>
          </div>
          {deliverableType !== 'document_report' && <details><summary>적용된 업무키트에서 계속하기</summary>
            <p style={noteStyle}>아래는 기존 키트의 데이터·앱 계약 흐름입니다. 위 요구 입력은 유지되며 키트 계약에 자동 반영되지 않습니다.</p>
            <fieldset disabled={locked}><KitStartFlow onOpenDataPrep={() => requestLeave('data')}
              selected={form.kitStartInstanceId} onSelect={(kitStartInstanceId) => update({ kitStartInstanceId })}
              appKind={deliverableType === 'hybrid_simulation' ? 'simulation' : 'software'} /></fieldset>
          </details>}
        </div>
      </details>

      {navigation && <div className="process-safety" role="group" aria-label="미저장 요구 입력 확인">
        <p>아직 저장하지 않은 입력이 있습니다. 어떻게 이동할까요?</p>
        <p style={noteStyle}>입력 유지는 같은 로그인·문맥의 메모리에만 보관합니다. 새로고침·로그아웃 시 사라집니다.</p>
        <div className="process-actions">
          <button type="button" disabled={!canSave} onClick={async () => { const row = await save(); if (row && active.current) leave(navigation); }}>저장 후 이동</button>
          <button type="button" disabled={state.busy || creating} onClick={() => leave(navigation)}>입력 유지하고 이동</button>
          <button type="button" disabled={locked || state.creationState === 'UNKNOWN'} onClick={() => { if (flow.discard()) leave(navigation); }}>입력 폐기하고 이동</button>
          <button type="button" onClick={() => setNavigation(null)}>계속 작성</button>
        </div>
      </div>}
    </div>
  </HubDialog>;
}

/** 현재 사용자가 **볼 수 있는 조직 적용본**에서만 앱 생성 흐름을 시작한다.
 *
 * 임의 `kit_instance_id` 입력을 받지 않는다. 적용본을 골라도 서버가 내려 준 준비도와
 * 계약 상태를 `KitAppPanel`이 다시 확인하며, 승인된 계약 전에는 앱 만들기 행동이 열리지 않는다.
 */
function KitStartFlow({ onOpenDataPrep, appKind, selected, onSelect }: {
  onOpenDataPrep: () => void;
  appKind: 'software' | 'simulation';
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [instances, setInstances] = useState<KitInstanceChoice[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let alive = true;
    listInstances()
      .then((d) => {
        if (!alive) return;
        const rows = d.instances || [];
        setInstances(rows);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        const err = e as DataPrepError;
        setError({ message: err?.message || '적용된 업무키트를 확인하지 못했습니다.',
          status: err?.status || 0 });
      });
    return () => { alive = false; };
  }, [revision]);

  if (error) {
    return (
      <div style={{ padding: 14, borderRadius: 8, border: '1px solid var(--state-error-fg)',
        background: 'var(--state-error-bg)' }}>
        <strong style={{ color: 'var(--state-error-fg)' }}>업무키트를 확인하지 못했습니다</strong>
        <div style={{ fontSize: 13, marginTop: 5 }}>{error.message}</div>
        <div style={{ fontSize: 12, marginTop: 5, color: 'var(--surface-text-muted)' }}>
          {error.status === 404 ? '현재 회사·조직 범위를 다시 확인하십시오.'
            : '적용본이 없는 것이 아니라 지금 조회하지 못한 상태입니다.'}
        </div>
        <button type="button" className="secondary-button" style={{ marginTop: 10 }}
          onClick={() => {
            // 최초 로딩은 초기값, 재조회 로딩은 명시적 사용자 행동에서 시작한다.
            setInstances(null); setError(null); setRevision((value) => value + 1);
          }}>
          다시 확인
        </button>
      </div>
    );
  }

  if (instances === null) {
    return <div style={{ color: 'var(--surface-text-muted)', fontSize: 14 }}>
      이 조직에 적용된 업무키트를 확인하는 중…
    </div>;
  }

  if (instances.length === 0) {
    return (
      <div style={{ padding: 16, borderRadius: 8, border: '1px solid var(--surface-border)',
        background: 'var(--surface-raised)' }}>
        <strong>이 회사·조직에 적용된 업무키트가 없습니다.</strong>
        <p style={{ margin: '7px 0 12px', fontSize: 13, color: 'var(--surface-text-muted)' }}>
          먼저 업무 데이터 준비에서 샘플 패키지를 조직에 적용하고 필요한 데이터 판을 인증하십시오.
        </p>
        <button className="secondary-button" onClick={onOpenDataPrep}>업무 데이터 준비 열기</button>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 7 }}>조직 적용본</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {instances.map((row) => {
            const on = selected === row.instance_id;
            return (
              <button key={row.instance_id} type="button" onClick={() => onSelect(row.instance_id)}
                aria-pressed={on} style={{
                  minHeight: 58, padding: '10px 13px', textAlign: 'left', borderRadius: 8,
                  border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
                  borderLeft: `4px solid ${on ? 'var(--ls-navy)' : 'transparent'}`,
                  background: on ? 'var(--surface-raised)' : 'var(--surface-card)',
                  color: 'var(--surface-text)', cursor: 'pointer',
                }}>
                <strong style={{ display: 'block', fontSize: 14 }}>
                  {row.label || row.kit_id || '이름 없는 적용본'}
                </strong>
                <span style={{ display: 'block', marginTop: 3, fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  {row.entity_mode || '문맥 확인 필요'} · {row.status || '상태 확인 필요'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {selected && instances.some((row) => row.instance_id === selected) ? (
        <div style={{ border: '1px solid var(--surface-border)', borderRadius: 8,
          background: 'var(--surface-card)' }}>
          <KitAppPanel instanceId={selected} appKind={appKind} />
        </div>
      ) : (
        <div style={{ padding: 13, borderRadius: 8, background: 'var(--surface-raised)',
          color: 'var(--surface-text-muted)', fontSize: 13 }}>
          적용본을 고르면 만들 수 있는 업무 앱, 데이터 준비 상태, 계약 승인 여부가 표시됩니다.
        </div>
      )}
    </div>
  );
}
