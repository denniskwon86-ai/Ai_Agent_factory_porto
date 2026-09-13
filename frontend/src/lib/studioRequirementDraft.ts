// B5 요구 입력/저장 수명. 실행·승인·bootstrap은 호출하지 않는다.
import { apiFetch } from './api';
import { createProcessInstallationApi, processContextIdentity, ProcessApiError,
  unwrapProcessResponse, type ProcessAccess, type ProcessBoundary,
  type ResolvedProcesses } from './processInstallationApi';

export type StudioDeliverable = 'software_app' | 'hybrid_simulation' | 'document_report';
export type StudioProcessSelection = { kind: 'APPROVED'; profile_id: string; process_ids: string[] } | null;
export type StudioRequirementForm = {
  initialIdea: string; projectName: string; isMega: boolean; templateId: string;
  packIds: string[]; masterDomains: string; mcpLiveGrounding: boolean; kitInstanceId: string;
  processSelection: StudioProcessSelection; kitStartInstanceId: string;
};
export type StudioRequirementRevision = {
  draft_id: string; revision_id: string; revision: number; digest: string;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED'; author_actor: string;
  context_key: Pick<ProcessBoundary, 'tenant_id' | 'context_root_id' | 'entity_mode' | 'scope_node_id'>;
  blueprint: Record<string, unknown>; process_ref: Record<string, unknown> | null;
};
type SaveBody = {
  context_root_id: string; scope_node_id: string; draft_id: string;
  expected_revision: number; expected_digest: string; client_request_id: string;
  patch: { op: 'SET'; path: string[]; value: unknown }[];
  process_selection: StudioProcessSelection;
};
type Attempt = { body: SaveBody; serialized: string; form: StudioRequirementForm };
export type StudioRequirementState = {
  form: StudioRequirementForm; access: ProcessAccess | null; resolved: ResolvedProcesses | null;
  busy: boolean; error: ProcessApiError | null; processError: string;
  receipt: StudioRequirementRevision | null; savedForm: string; attempt: Attempt | null;
  rejected: boolean; conflict: boolean; latest: StudioRequirementRevision | null;
  creationState: 'IDLE' | 'PENDING' | 'UNKNOWN' | 'CONFIRMED';
};
const blank = (): StudioRequirementForm => ({ initialIdea: '', projectName: '', isMega: false,
  templateId: '', packIds: [], masterDomains: '', mcpLiveGrounding: false,
  kitInstanceId: '', processSelection: null, kitStartInstanceId: '' });
const initial = (): StudioRequirementState => ({ form: blank(), access: null, resolved: null,
  busy: false, error: null, processError: '', receipt: null, savedForm: '', attempt: null,
  rejected: false, conflict: false, latest: null, creationState: 'IDLE' });
const boundaryKey = (b: StudioRequirementRevision['context_key']) => JSON.stringify([
  b.tenant_id, b.context_root_id, b.entity_mode, b.scope_node_id]);
const invalid = (message: string) => new ProcessApiError(503, message, 'STUDIO_RESPONSE_INVALID');

const objectValue = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => [key, canonical(item)]));
  return value;
}
const equal = (a: unknown, b: unknown) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

function validateRevision(value: StudioRequirementRevision, access: ProcessAccess): StudioRequirementRevision {
  if (!value || !value.draft_id || !value.revision_id || !Number.isInteger(value.revision)
    || value.revision < 1 || !/^[0-9a-f]{64}$/.test(value.digest)
    || !['DRAFT', 'APPROVED', 'REJECTED'].includes(value.status)
    || value.author_actor !== access.principal_user_id || !value.context_key
    || boundaryKey(value.context_key) !== boundaryKey(access.boundary)
    || !value.blueprint || typeof value.blueprint !== 'object' || Array.isArray(value.blueprint)) {
    throw invalid('저장 응답의 사용자·조직·판본을 확인하지 못했습니다. 입력과 요청 키를 보존했습니다.');
  }
  return value;
}

export function createStudioRequirementDraft(deliverable: StudioDeliverable,
  identity = processContextIdentity(), newId = () => crypto.randomUUID()) {
  const api = createProcessInstallationApi(identity);
  let state = initial();
  let generation = 0;
  let initialized = false;
  let disposed = false;
  let binding: ProcessAccess | null = null;
  let controller: AbortController | null = null;
  const listeners = new Set<() => void>();
  const set = (patch: Partial<StudioRequirementState>) => {
    state = { ...state, ...patch }; listeners.forEach((listener) => listener());
  };
  function assertCurrent(ticket = generation) {
    if (disposed || ticket !== generation || processContextIdentity() !== identity) {
      throw new ProcessApiError(409, '사용자·회사·조직이 바뀌었습니다. 원래 문맥에서 입력을 확인해 주세요.', 'CLIENT_CONTEXT_CHANGED');
    }
  }
  async function access() {
    assertCurrent();
    const current = await api.access(false);
    assertCurrent();
    if (!current.principal_user_id || !current.boundary?.context_root_id
      || !current.boundary.tenant_id || !current.boundary.entity_mode
      || !Array.isArray(current.permitted_actions)) throw invalid('현재 작업 문맥을 확인하지 못했습니다.');
    if (binding && (boundaryKey(binding.boundary) !== boundaryKey(current.boundary)
      || binding.principal_user_id !== current.principal_user_id)) {
      throw new ProcessApiError(409, '서버의 조직 범위가 바뀌었습니다. 이전 초안을 새 범위에 저장하지 않습니다.', 'STUDIO_BOUNDARY_CHANGED');
    }
    binding = current;
    set({ access: current });
    return current;
  }
  async function call<T>(path: string, serialized?: string) {
    assertCurrent();
    controller = new AbortController();
    const response = await apiFetch('/api/v1/advisor' + path, {
      signal: controller.signal, ...(serialized === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: serialized }),
    });
    assertCurrent();
    const result = await unwrapProcessResponse<T>(response);
    assertCurrent();
    return result;
  }
  function failure(error: unknown) {
    return error instanceof ProcessApiError ? error
      : new ProcessApiError(503, '응답을 확인하지 못했습니다. 입력을 보존했습니다. 자동으로 다시 보내지 않습니다.');
  }
  async function run(work: () => Promise<void>) {
    if (state.busy) return;
    const ticket = generation;
    set({ busy: true, error: null });
    try { assertCurrent(ticket); await work(); }
    catch (error) {
      if (ticket === generation && processContextIdentity() === identity) {
        const value = failure(error);
        set({ error: value, ...([401, 403, 404].includes(value.status) ? { access: null, resolved: null, latest: null } : {}) });
      }
    }
    finally { if (ticket === generation) { controller = null; set({ busy: false }); } }
  }
  const editable = () => !state.busy && state.creationState !== 'PENDING'
    && (!state.attempt || state.rejected) && !state.conflict;

  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    identity,
    initialize: (seed: Partial<StudioRequirementForm> = {}) => {
      if (initialized) return;
      initialized = true;
      // 기존 캐시/초안은 초기 props로 덮어쓰지 않는다. 원문은 전역 저장소에 기록하지 않는다.
      const allowed = Object.fromEntries(Object.keys(blank()).filter((key) => key in seed && seed[key as keyof StudioRequirementForm] !== undefined)
        .map((key) => [key, structuredClone(seed[key as keyof StudioRequirementForm])]));
      set({ form: { ...blank(), ...allowed } });
    },
    update: (patch: Partial<StudioRequirementForm>) => {
      assertCurrent();
      if (!editable()) return;
      const allowed = Object.fromEntries(Object.keys(blank()).filter((key) => key in patch && patch[key as keyof StudioRequirementForm] !== undefined)
        .map((key) => [key, structuredClone(patch[key as keyof StudioRequirementForm])]));
      set({ form: { ...state.form, ...allowed }, error: null, attempt: null, rejected: false });
    },
    refresh: () => run(async () => {
      const current = await access();
      try {
        const resolved = await api.resolved(current.boundary);
        assertCurrent();
        if (boundaryKey(resolved.boundary) !== boundaryKey(current.boundary)) throw invalid('업무 목록의 조직 범위가 다릅니다.');
        set({ resolved, processError: resolved.legacy_review_required ? '업무 구성 검토가 필요합니다. 업무 연결 미정으로 초안을 저장할 수 있습니다.' : '' });
      } catch (error) {
        assertCurrent();
        set({ resolved: null, processError: failure(error).message });
      }
    }),
    save: async (): Promise<StudioRequirementRevision | null> => {
      let saved: StudioRequirementRevision | null = null;
      await run(async () => {
        if (state.conflict) throw new ProcessApiError(409, '다른 판본이 있습니다. 최신 판본을 확인한 뒤 다시 저장해 주세요.');
        const current = await access();
        if (!current.permitted_actions.includes('propose')) throw new ProcessApiError(403, '현재 조직 범위에서 요구초안을 저장할 권한이 없습니다.');
        if (!state.form.initialIdea.trim()) throw new ProcessApiError(422, '어떤 일을 쉽게 만들고 싶은지 먼저 적어 주세요.');
        if (state.receipt && !state.attempt && state.savedForm === JSON.stringify(state.form)) {
          saved = state.receipt;
          return;
        }
        if (!state.attempt) {
          const form = structuredClone(state.form);
          const previous = state.receipt?.blueprint || {};
          const body: SaveBody = { context_root_id: current.boundary.context_root_id,
            scope_node_id: current.boundary.scope_node_id, draft_id: state.receipt?.draft_id || '',
            expected_revision: state.receipt?.revision || 0, expected_digest: state.receipt?.digest || '',
            client_request_id: newId(), process_selection: form.processSelection,
            patch: [
              { op: 'SET', path: ['title'], value: form.projectName.trim() || form.initialIdea.trim().slice(0, 80) },
              { op: 'SET', path: ['business'], value: { ...objectValue(previous.business), objective: form.initialIdea } },
              { op: 'SET', path: ['system'], value: { ...objectValue(previous.system), template_id: form.templateId } },
              { op: 'SET', path: ['request_options'], value: { ...objectValue(previous.request_options), deliverable_type: deliverable,
                is_mega: form.isMega, knowledge_pack_ids: form.packIds, master_domains: form.masterDomains.split(',').map((item) => item.trim()).filter(Boolean),
                mcp_live_grounding: form.mcpLiveGrounding, kit_instance_id: form.kitInstanceId,
                kit_start_instance_id: form.kitStartInstanceId } },
            ] };
          set({ attempt: { body, serialized: JSON.stringify(body), form }, rejected: false });
        }
        const attempt = state.attempt!;
        try {
          const row = validateRevision(await call<StudioRequirementRevision>('/drafts', attempt.serialized), current);
          if (row.revision !== attempt.body.expected_revision + 1 || row.status !== 'DRAFT'
            || (attempt.body.draft_id && row.draft_id !== attempt.body.draft_id)
            || attempt.body.patch.some((item) => !equal(row.blueprint[item.path[0]], item.value))) {
            throw invalid('응답이 저장하려던 입력/판본과 다릅니다. 같은 요청을 보존했습니다.');
          }
          const selection = attempt.body.process_selection;
          const ref = row.process_ref;
          if (selection ? (!ref || ref.profile_id !== selection.profile_id
            || !equal(ref.process_ids, [...selection.process_ids].sort())
            || !equal(ref.context_key, row.context_key)) : ref !== null) {
            throw invalid('저장한 업무 참조가 요청과 다릅니다. 원래 요청을 보존했습니다.');
          }
          assertCurrent();
          saved = row;
          set({ receipt: row, savedForm: JSON.stringify(attempt.form), attempt: null, error: null,
            rejected: false, latest: null });
        } catch (error) {
          const value = failure(error);
          assertCurrent();
          set({ rejected: value.status === 422, conflict: value.status === 409 });
          throw value;
        }
      });
      return saved;
    },
    readLatest: () => run(async () => {
      if (!state.receipt || !state.conflict) return;
      const current = await access();
      const query = new URLSearchParams({ context_root_id: current.boundary.context_root_id, scope_node_id: current.boundary.scope_node_id });
      const row = validateRevision(await call<StudioRequirementRevision>(`/drafts/${encodeURIComponent(state.receipt.draft_id)}?${query}`), current);
      if (row.draft_id !== state.receipt.draft_id) throw invalid('조회한 초안이 다릅니다.');
      set({ latest: row });
    }),
    useLatest: () => {
      assertCurrent();
      if (state.busy || !state.latest || !state.conflict) return;
      set({ receipt: state.latest, latest: null, conflict: false, attempt: null, rejected: false,
        savedForm: '', error: null });
    },
    beginCreate: () => {
      assertCurrent();
      if (!editable() || state.creationState !== 'IDLE') return false;
      set({ creationState: 'PENDING' });
      return true;
    },
    finishCreate: (creationState: 'IDLE' | 'UNKNOWN' | 'CONFIRMED') => {
      assertCurrent();
      if (state.creationState === 'PENDING') set({ creationState });
    },
    markCreationUnknown: () => {
      // 닫기/문맥 전환은 서버 실행 중단이 아니다. 재진입 시 생성 요청 재전송을 차단한다.
      if (!disposed && state.creationState === 'PENDING') set({ creationState: 'UNKNOWN' });
    },
    discard: () => {
      assertCurrent();
      if (!editable() || state.creationState === 'UNKNOWN') return false;
      set({ form: blank(), savedForm: '', attempt: null, receipt: null, latest: null, error: null, rejected: false, creationState: 'IDLE' });
      return true;
    },
    invalidate: () => { disposed = true; generation++; controller?.abort(); binding = null; state = initial(); listeners.forEach((listener) => listener()); },
  };
}
export type StudioRequirementDraft = ReturnType<typeof createStudioRequirementDraft>;

// 같은 로그인·회사·조직·모드·산출물에서 데이터 준비/패널을 왕복할 때만 메모리 입력 재사용.
// 세션 변경은 닫힌 화면의 입력도 지운다. 요청 원문/토큰/민감 요구를 localStorage에 쓰지 않는다.
const drafts = new Map<string, StudioRequirementDraft>();
let sessionListenerInstalled = false;
export function getStudioRequirementDraft(deliverable: StudioDeliverable) {
  if (!sessionListenerInstalled && typeof window !== 'undefined') {
    window.addEventListener('factory:session-changed', () => {
      drafts.forEach((draft) => draft.invalidate()); drafts.clear();
    });
    sessionListenerInstalled = true;
  }
  const key = JSON.stringify([processContextIdentity(), deliverable]);
  if (!drafts.has(key)) drafts.set(key, createStudioRequirementDraft(deliverable));
  return drafts.get(key)!;
}
export function subscribeStudioRequirementContext(listener: () => void) {
  window.addEventListener('factory:enterprise-context-changed', listener);
  window.addEventListener('factory:session-changed', listener);
  return () => {
    window.removeEventListener('factory:enterprise-context-changed', listener);
    window.removeEventListener('factory:session-changed', listener);
  };
}
