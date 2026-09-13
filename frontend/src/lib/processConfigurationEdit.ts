import { ProcessApiError, type ProcessAccess, type ProcessBoundary, type ProcessChangeReceipt,
  type ProcessDisplayCommand, type ProcessDocument, type ProcessEditInput,
  type ProcessInstallationApi, type ResolvedProcesses, type ProcessCommand, type ProcessStructureCommand } from './processInstallationApi';
import { applyProcessStep, replayProcessSteps, type ProcessEditStep } from './processStructureEdit';

export const processBoundaryKey = (b: ProcessBoundary) => JSON.stringify([
  b.tenant_id, b.context_root_id, b.entity_mode, b.scope_node_id, b.configuration_kind]);
export function orderedPlacements(document: ProcessDocument, parent: string) {
  return document.placements.filter((p) => p.parent_process_id === parent)
    .sort((a, b) => a.position - b.position || a.placement_id.localeCompare(b.placement_id));
}
export function buildProcessEditCommands(base: ProcessDocument, document: ProcessDocument): ProcessDisplayCommand[] {
  const commands: ProcessDisplayCommand[] = [];
  for (const node of document.nodes) {
    const old = base.nodes.find((item) => item.process_id === node.process_id);
    if (!old) throw new ProcessApiError(409, '기준판에 없는 업무입니다. 입력을 보존했습니다.');
    if (old.label !== node.label) commands.push({ op: 'RENAME', process_id: node.process_id, label: node.label });
    if (old.note !== node.note) commands.push({ op: 'SET_NOTE', process_id: node.process_id, note: node.note });
  }
  for (const parent of new Set(document.placements.map((p) => p.parent_process_id))) {
    const ids = orderedPlacements(document, parent).map((p) => p.placement_id);
    const old = orderedPlacements(base, parent).map((p) => p.placement_id);
    if (JSON.stringify(ids) !== JSON.stringify(old)) {
      commands.push({ op: 'REORDER_PLACEMENTS', parent_process_id: parent, placement_ids: ids });
    }
  }
  return commands;
}

export type ProcessStructureInput = {
  level: 'L1' | 'L2'; label: string; note: string;
  addParent: { selectedId: string; parentId: string } | null;
  moveParent: { selectedId: string; parentId: string } | null;
  shortcutParent: { selectedId: string; parentId: string } | null;
  message: string; failed: boolean;
};
const emptyStructureInput = (): ProcessStructureInput => ({ level: 'L2', label: '', note: '',
  addParent: null, moveParent: null, shortcutParent: null, message: '', failed: false });
export type ProcessEditState = {
  base: ResolvedProcesses | null; access: ProcessAccess | null; document: ProcessDocument | null;
  selectedId: string; reason: string; busy: boolean; error: ProcessApiError | null;
  attempt: { body: ProcessEditInput } | null; receipt: ProcessChangeReceipt | null; conflict: boolean;
  workingBase: ProcessDocument | null; steps: ProcessEditStep[]; rejected: boolean;
  structureInput: ProcessStructureInput;
};

/** 편집 입력·명령 순서를 보관하며 제출 후 고정 요청 키로 접수 결과를 확인한다. */
export function createProcessEditFlow(api: ProcessInstallationApi, companyWide: boolean,
  newId: () => string = () => crypto.randomUUID()) {
  const initial = (): ProcessEditState => ({ base: null, access: null, document: null,
    selectedId: '', reason: '', busy: false, error: null, attempt: null, receipt: null, conflict: false,
    workingBase: null, steps: [], rejected: false, structureInput: emptyStructureInput() });
  let state = initial();
  let generation = 0;
  let principal = '';
  const listeners = new Set<() => void>();
  const set = (patch: Partial<ProcessEditState>) => {
    state = { ...state, ...patch }; listeners.forEach((listener) => listener());
  };
  const editable = () => !!state.access?.permitted_actions.includes('propose') && !state.busy && !state.attempt && !state.receipt;
  const pendingDisplay = () => state.workingBase && state.document ? buildProcessEditCommands(state.workingBase, state.document) : [];
  const getCommands = (): ProcessCommand[] => [...state.steps.map((step) => structuredClone(step.command)), ...pendingDisplay()];
  const allSteps = (): ProcessEditStep[] => [...state.steps, ...pendingDisplay().map((command) => ({ command }))];
  const canReorder = (parent: string) => !!state.document && !state.document.placements.some((p) =>
    p.parent_process_id === parent && state.steps.some((step) => step.placementId === p.placement_id));
  function appendStructure(command: ProcessStructureCommand, placementId?: string) {
    if (!editable() || !state.document) return false;
    try {
      const step = { command, ...(placementId ? { placementId } : {}) };
      const pending = pendingDisplay().map((change) => ({ command: change }));
      // 빈 이름 등 미완성 표시 입력을 취소·재적용 불가능한 prefix로 고정하지 않는다.
      const checked = replayProcessSteps(state.workingBase!, pending);
      const steps = [...state.steps, ...pending, step];
      const document = applyProcessStep(checked, step);
      set({ steps, workingBase: structuredClone(document), document, error: null });
      return true;
    } catch (error) { set({ error: error as ProcessApiError }); return false; }
  }
  function validBase(base: ResolvedProcesses, access: ProcessAccess) {
    if (!base.payload || !base.profile_id || !base.digest || base.head_version < 1
      || processBoundaryKey(base.boundary) !== processBoundaryKey(access.boundary)) {
      throw new ProcessApiError(409, '승인된 기준판과 적용 범위를 먼저 확인해 주세요.', 'CLIENT_BASE_REQUIRED');
    }
  }
  async function run(work: (check: () => void) => Promise<void>) {
    if (state.busy) return;
    const ticket = generation;
    const check = () => { if (generation !== ticket) throw new Error('STALE_VIEW'); };
    set({ busy: true, error: null });
    try { await work(check); }
    catch (error) {
      if (ticket === generation) {
        const value = error instanceof ProcessApiError ? error : new ProcessApiError(0, '응답을 확인하지 못했습니다. 입력과 요청 번호를 보존했습니다.');
        set({ error: value, conflict: state.conflict || (value.status === 409 && ['PROCESS_HEAD_CONFLICT', 'PROCESS_DIGEST_CONFLICT'].includes(value.reasonCode)),
          ...([401, 403, 404].includes(value.status) ? { access: null } : {}) });
      }
    } finally { if (ticket === generation) set({ busy: false }); }
  }
  async function freshAccess(check: () => void) {
    const access = await api.access(companyWide); check();
    if (!state.base || processBoundaryKey(access.boundary) !== processBoundaryKey(state.base.boundary)
      || access.principal_user_id !== principal) {
      throw new ProcessApiError(409, '편집을 시작한 회사·조직·사용자가 달라졌습니다. 원래 범위의 입력을 보존했습니다.', 'CLIENT_CONTEXT_CHANGED');
    }
    if (!access.permitted_actions.includes('propose')) throw new ProcessApiError(403, '현재 이 범위에 변경안을 제안할 권한이 없습니다.');
    set({ access }); return access;
  }
  function updateNode(field: 'label' | 'note', value: string) {
    if (!editable() || !state.document) return;
    set({ document: { ...state.document, nodes: state.document.nodes.map((node) =>
      node.process_id === state.selectedId ? { ...node, [field]: value } : node) }, error: null });
  }
  const model = {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    invalidate: () => { generation++; state = { ...state, busy: false }; },
    begin: (base: ResolvedProcesses, access: ProcessAccess) => {
      if (state.busy) return;
      if (state.base) {
        const same = processBoundaryKey(state.base.boundary) === processBoundaryKey(access.boundary)
          && principal === access.principal_user_id;
        const pristine = !state.attempt && !state.receipt && !state.reason
          && !!state.document && !getCommands().length && !state.structureInput.label && !state.structureInput.note
          && state.structureInput.level === 'L2' && !state.structureInput.addParent
          && !state.structureInput.moveParent && !state.structureInput.shortcutParent;
        if (!pristine || (same && state.base.profile_id === base.profile_id && state.base.digest === base.digest)) {
          if (same) set({ access, error: null });
          return;
        }
        // 편집하지 않은 자동 초기화 상태만 새 범위/승인판으로 옮긴다. 실제 입력·미확정 제출은 보존한다.
        set(initial());
      }
      try {
        validBase(base, access);
        principal = access.principal_user_id;
        set({ base: structuredClone(base), access: structuredClone(access), document: structuredClone(base.payload!),
          workingBase: structuredClone(base.payload!), steps: [], rejected: false,
          selectedId: orderedPlacements(base.payload!, '')[0]?.process_id || base.payload!.nodes[0]?.process_id || '', error: null });
      } catch (error) { set({ error: error as ProcessApiError }); }
    },
    select: (id: string) => { if (state.document?.nodes.some((node) => node.process_id === id)) set({ selectedId: id }); },
    setLabel: (value: string) => updateNode('label', value),
    setNote: (value: string) => updateNode('note', value),
    setReason: (reason: string) => { if (editable()) set({ reason }); },
    setStructureInput: (patch: Partial<ProcessStructureInput>) => {
      if (editable()) set({ structureInput: { ...state.structureInput, ...patch } });
    },
    getCommands,
    canReorder,
    addNode: (level: 'L1' | 'L2', parent: string, label: string, note = ''): string | null => {
      if (!editable()) return null;
      const id = `custom-${newId()}`, placementId = `local-placement-${newId()}`;
      if (!appendStructure({ op: 'ADD_NODE', node: { process_id: id, level, parent_process_id: parent, label, note } }, placementId)) return null;
      set({ selectedId: id }); return id;
    },
    setUsage: (enabled: boolean) => {
      if (state.document?.nodes.find((node) => node.process_id === state.selectedId)?.enabled === enabled) return;
      appendStructure({ op: 'SET_USAGE', process_id: state.selectedId, enabled });
    },
    moveNode: (parent: string) => {
      if (state.document?.nodes.find((node) => node.process_id === state.selectedId)?.parent_process_id === parent) return;
      appendStructure({ op: 'MOVE_NODE', process_id: state.selectedId, parent_process_id: parent });
    },
    addShortcut: (processId: string, parent: string) => {
      if (editable()) appendStructure({ op: 'ADD_SHORTCUT', process_id: processId, parent_process_id: parent }, `local-placement-${newId()}`);
    },
    removeShortcut: (placementId: string) => {
      if (!editable() || !state.base || !state.document) return;
      const added = state.steps.find((step) => step.placementId === placementId && step.command.op === 'ADD_SHORTCUT');
      if (!added) { appendStructure({ op: 'REMOVE_SHORTCUT', placement_id: placementId }); return; }
      try {
        const steps = allSteps().filter((step) => step !== added);
        const document = replayProcessSteps(state.base.payload!, steps);
        set({ steps, document, workingBase: structuredClone(document), error: null });
      } catch (error) { set({ error: error as ProcessApiError }); }
    },
    move: (id: string, direction: -1 | 1) => {
      if (!editable() || !state.document) return;
      const placement = state.document.placements.find((p) => p.placement_id === id);
      if (!placement) return;
      if (!canReorder(placement.parent_process_id)) {
        set({ error: new ProcessApiError(422, '새 업무·바로가기가 포함된 목록의 순서는 승인 후 변경할 수 있습니다. 다른 수정 입력은 보존됩니다.') }); return;
      }
      const siblings = orderedPlacements(state.document, placement.parent_process_id);
      const index = siblings.findIndex((p) => p.placement_id === id), next = index + direction;
      if (next < 0 || next >= siblings.length) return;
      [siblings[index], siblings[next]] = [siblings[next], siblings[index]];
      const positions = new Map(siblings.map((p, position) => [p.placement_id, position]));
      set({ document: { ...state.document, placements: state.document.placements.map((p) =>
        positions.has(p.placement_id) ? { ...p, position: positions.get(p.placement_id)! } : p) }, error: null });
    },
    submit: async (): Promise<ProcessChangeReceipt | null> => {
      if (!state.base || !state.document || state.receipt || state.conflict || state.rejected || state.busy) return state.receipt;
      let result: ProcessChangeReceipt | null = null;
      await run(async (check) => {
        const access = await freshAccess(check);
        if (!state.attempt) {
          if (state.structureInput.label || state.structureInput.note) {
            throw new ProcessApiError(422, '작성 중인 새 업무를 초안에 추가하거나 추가 양식을 비운 뒤 제안해 주세요. 입력은 보존했습니다.');
          }
          const commands = getCommands();
          if (!commands.length || commands.length > 200 || !state.reason.trim()
            || state.document!.nodes.some((node) => !node.label.trim() || node.label.length > 200)) {
            throw new ProcessApiError(422, '변경할 내용, 200자 이내 업무 이름, 제안 이유를 확인해 주세요. 한 번에 최대 200개 변경을 제안할 수 있습니다.');
          }
          set({ attempt: { body: { context_root_id: access.boundary.context_root_id,
            scope_node_id: access.boundary.scope_node_id, commands, expected_head_version: state.base!.head_version,
            base_profile_id: state.base!.profile_id, base_fingerprint: state.base!.digest,
            client_request_id: newId(), reason: state.reason.trim() } } });
        }
        let receipt: ProcessChangeReceipt;
        try { receipt = await api.propose(state.base!.boundary, structuredClone(state.attempt!.body)); check(); }
        catch (error) {
          check();
          if (error instanceof ProcessApiError && error.status === 422) set({ rejected: true });
          throw error;
        }
        if (!receipt.change_id || receipt.configuration_id !== state.base!.configuration_id
          || receipt.base_head_version !== state.attempt!.body.expected_head_version || !receipt.draft_digest
          || !receipt.draft_profile_id || receipt.actor !== access.principal_user_id) {
          throw new ProcessApiError(503, '접수 응답의 기준판을 확인하지 못했습니다. 같은 요청 번호를 유지합니다.');
        }
        set({ receipt }); result = receipt;
      });
      return result;
    },
    reloadBase: () => run(async (check) => {
      if (state.attempt && !state.conflict && !state.receipt && !state.rejected) throw new ProcessApiError(409, '먼저 같은 요청의 접수 결과를 확인해 주세요.');
      const access = await freshAccess(check);
      const base = await api.resolved(access.boundary); check(); validBase(base, access);
      const steps = state.receipt ? [] : allSteps();
      let document: ProcessDocument;
      try { document = replayProcessSteps(base.payload!, steps); }
      catch { throw new ProcessApiError(409, '최신 구성에 기존 수정을 그대로 옮길 수 없습니다. 업무·부모·배치를 확인해 주세요. 입력은 보존했습니다.', 'CLIENT_REBASE_CONFLICT'); }
      set({ base: structuredClone(base), document, access, attempt: null, receipt: null, conflict: false,
        workingBase: structuredClone(document), steps, rejected: false,
        selectedId: document.nodes.some((node) => node.process_id === state.selectedId) ? state.selectedId : document.nodes[0]?.process_id || '' });
    }),
    reset: () => {
      if (!state.busy && (!state.attempt || state.receipt || state.conflict || state.rejected)) { generation++; principal = ''; set(initial()); }
    },
    revise: () => { if (!state.busy && state.rejected) set({ attempt: null, rejected: false, error: null }); },
  };
  return model;
}
export type ProcessEditFlow = ReturnType<typeof createProcessEditFlow>;
