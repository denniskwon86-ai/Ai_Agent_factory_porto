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

/** [DRAFT-OPEN-01] 직접 링크로 «지정 판본» 을 열 때 쓰는 대상. */
export type DraftOpenTarget = {
  draftId: string; revision: number;
  /** ★★★ **서버가 돌려준** 소유 경계다. 선택 문맥으로 재구성하지 «않는다». */
  ownership: { tenant_id: string; context_root_id: string; entity_mode: string; scope_node_id: string };
};

/** 불러온 판본의 구조 검증.
 *
 *  ⚠️⚠️ `validateRevision` 을 그대로 쓸 수 «없다». 그 함수는 두 가지를 더 요구한다 —
 *    `author_actor === 현재 사용자` 와 `context_key === 현재 access.boundary`.
 *
 *    ① 직접 링크는 **남이 만든 초안**일 수 있다. 읽기 권한은 작성 여부와 무관하고,
 *       그 판정은 서버가 이미 했다(진입 확인 + 원문 조회 양쪽에서).
 *    ② 경계는 **서버가 돌려준 ownership** 과 맞춰야 한다. 현재 선택으로 맞추면
 *       「내 문맥으로 남의 초안을 읽는」 모양이 된다.
 *
 *  ★ 나머지 구조 검사(지문·상태·판본·blueprint 객체)는 **같은 규칙**을 쓴다 —
 *    두 벌로 만들면 한쪽만 느슨해진다. */
export function validateLoadedRevision(value: StudioRequirementRevision,
                                       target: DraftOpenTarget): StudioRequirementRevision {
  if (!value || value.draft_id !== target.draftId || value.revision !== target.revision
    || !value.revision_id || !/^[0-9a-f]{64}$/.test(value.digest)
    || !['DRAFT', 'APPROVED', 'REJECTED'].includes(value.status)
    || !value.author_actor || !value.context_key
    || boundaryKey(value.context_key) !== boundaryKey(target.ownership as never)
    || !value.blueprint || typeof value.blueprint !== 'object' || Array.isArray(value.blueprint)) {
    throw invalid('불러온 판본의 조직·판본·지문을 확인하지 못했습니다. 입력을 보존했습니다.');
  }
  return value;
}

const DELIVERABLES: readonly StudioDeliverable[] = ['software_app', 'hybrid_simulation', 'document_report'];

/** 초안 내용에서 **산출물 종류**를 되찾는다. 못 되찾으면 `null`.
 *
 *  ⚠️⚠️ 저장 경로가 `request_options.deliverable_type` 에 넣는 바로 그 값이다 —
 *    그래서 이것은 «추측» 이 아니다. 없거나 모르는 값이면 **`software_app` 으로 가정하지
 *    않는다.** 가정하면 다른 종류의 화면이 열리고, 그 화면에서 저장하면 초안의 종류가
 *    조용히 바뀐다(지시 ⑤). */
export function deliverableOf(row: StudioRequirementRevision): StudioDeliverable | null {
  const options = objectValue(objectValue(row.blueprint).request_options);
  const kind = options.deliverable_type;
  return typeof kind === 'string' && (DELIVERABLES as readonly string[]).includes(kind)
    ? kind as StudioDeliverable : null;
}

/** 불러온 판본 → 입력 양식. 저장 경로의 patch 를 **거꾸로** 읽는다. */
export function formOfRevision(row: StudioRequirementRevision): StudioRequirementForm {
  const blueprint = objectValue(row.blueprint);
  const business = objectValue(blueprint.business), system = objectValue(blueprint.system);
  const options = objectValue(blueprint.request_options);
  const idea = typeof business.objective === 'string' ? business.objective : '';
  const title = typeof blueprint.title === 'string' ? blueprint.title : '';
  const list = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
  //: ★ 제목이 «아이디어 앞 80자» 대체값이면 이름 칸을 비워 둔다. 채우면 재저장 때
  //:   같은 제목이 나오긴 하지만, 사용자가 적지 않은 이름을 적은 것처럼 보인다.
  const projectName = title && title !== idea.trim().slice(0, 80) ? title : '';
  return { ...blank(), initialIdea: idea, projectName,
    isMega: options.is_mega === true,
    templateId: typeof system.template_id === 'string' ? system.template_id : '',
    packIds: list(options.knowledge_pack_ids),
    masterDomains: list(options.master_domains).join(', '),
    mcpLiveGrounding: options.mcp_live_grounding === true,
    kitInstanceId: typeof options.kit_instance_id === 'string' ? options.kit_instance_id : '',
    kitStartInstanceId: typeof options.kit_start_instance_id === 'string' ? options.kit_start_instance_id : '',
    processSelection: null };
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
    /** [DRAFT-OPEN-01] 불러온 판본을 이 인스턴스에 «앉힌다». **통신하지 않는다.**
     *
     *  ⚠️ 진입만으로 저장·승인·생성이 일어나지 않는다 — 여기서 하는 일은 상태 결합뿐이다.
     *  ⚠️ 권한을 건드리지 않는다. 저장 가능 여부는 기존 `permitted_actions` 가 판정한다
     *    — **조회 권한이 수정 권한이 되지 않는다.**
     *  ★ `receipt` 를 **그 판본**으로 둔다. 그래서 과거판을 불러와 저장하면
     *    `expected_revision/digest` 가 과거판이고 서버가 충돌로 막는다. 우회가 아니다. */
    adoptRevision: (row: StudioRequirementRevision,
                    options: { replaceUnsaved?: boolean; expectIdentity?: string } = {}) => {
      assertCurrent();
      //: ★★★ [FIX1 · P1] **요청을 시작한 문맥에서만 앉는다.**
      //:
      //: ⚠️⚠️ `assertCurrent()` 만으로는 부족하다 — 그것은 «이 인스턴스의 문맥 == 지금»
      //:   만 본다. 오염 경로는 다르다: A 문맥에서 보낸 응답이 도착했을 때
      //:   `getStudioRequirementDraft` 가 **B 문맥의 인스턴스**를 고르고, 그 인스턴스의
      //:   `assertCurrent()` 는 **통과한다**(B == 지금). 그래서 「요청이 시작된 문맥」을
      //:   여기서 함께 봐야 막힌다.
      //: ★ 호출부의 검사에 기대지 않는다 — 저장소에 쓰는 자리가 스스로 지킨다.
      if (options.expectIdentity !== undefined && options.expectIdentity !== identity) {
        throw new ProcessApiError(409,
          '다른 문맥에서 시작한 조회 결과입니다. 현재 입력에 반영하지 않았습니다.',
          'STUDIO_FOREIGN_CONTEXT_RESULT');
      }
      if (state.busy || state.creationState === 'PENDING') {
        throw new ProcessApiError(409, '진행 중인 작업이 있습니다. 끝난 뒤 다시 불러오세요.', 'STUDIO_BUSY');
      }
      //: ⚠️ 생성 결과를 모르는 상태에서 다른 초안을 앉히지 않는다 — 그 보호를 되돌리는 셈이다.
      if (state.creationState === 'UNKNOWN') {
        throw new ProcessApiError(409, '직전 생성 요청의 결과가 확인되지 않았습니다. 화면을 새로 연 뒤 다시 시도하세요.', 'STUDIO_CREATION_UNKNOWN');
      }
      const serialized = JSON.stringify(state.form);
      //: **미저장 입력을 말없이 덮지 않는다**(지시 ⑥). 확인을 받은 뒤에만 바꾼다.
      const dirty = serialized !== JSON.stringify(blank()) && serialized !== state.savedForm;
      if ((dirty || !!state.attempt) && !options.replaceUnsaved) {
        throw new ProcessApiError(409, '입력하던 내용이 있습니다. 불러오면 지금 입력이 바뀝니다.', 'STUDIO_UNSAVED_INPUT');
      }
      const form = formOfRevision(row);
      //: ★★★ **불러오기가 곧 초기화다.** 이걸 세우지 않으면 편집기가 mount 하면서
      //:   부르는 `initialize(seed)` 가 «빈 양식 + seed» 로 **방금 불러온 내용을 덮는다**
      //:   (`BuildStartDialog.tsx:104`). 지시 ⑥ 이 경고한 바로 그 덮어쓰기다.
      //: ⚠️ 실제로 그랬다 — 시험으로 잡았고, 이 한 줄이 그 순서를 고정한다.
      initialized = true;
      set({ form, receipt: row, savedForm: JSON.stringify(form), attempt: null, rejected: false,
        conflict: false, latest: null, error: null });
      return row;
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

/** [DRAFT-OPEN-01] 확인된 초안의 **지정 판본**을 불러와 알맞은 편집기에 앉힌다.
 *
 *  ## ⚠️⚠️ `readLatest` 를 재사용하지 «않는» 이유
 *
 *  그 함수는 **충돌 중인 receipt 가 있어야** 돌고 **최신판**을 본다. 직접 링크는 둘 다
 *  아니다 — receipt 가 없고, **요청한 그 판본**이어야 한다. 재사용하면 링크가 가리킨
 *  과거판 대신 최신판이 조용히 열린다(지시 ④·⑦).
 *
 *  ## 경계는 «서버가 돌려준 것» 을 쓴다
 *
 *  진입 확인이 알려 준 `ownership` 으로 원문을 부른다. 선택 문맥으로 재구성하면
 *  「내 문맥으로 남의 초안을 읽는」 모양이 된다(지시 ③).
 *
 *  ⚠️ 그렇다고 진입 확인이 **권한 토큰이 되지는 않는다** — 원문 조회도 서버의 자기
 *    권한 검사를 그대로 지난다. 여기서 하는 일은 «어느 경계로 물을지» 를 정하는 것뿐이다. */
//: [FIX1 · P1] 열기 요청의 **세대**. 늦게 도착한 옛 요청이 최신 결과를 덮지 못하게 한다.
//: ⚠️ 같은 문맥에서도 두 요청이 겹칠 수 있다(초안1 → 초안2). identity 만으로는 못 가른다.
let openGeneration = 0;

export async function openDraftRevision(target: DraftOpenTarget,
    options: { replaceUnsaved?: boolean; signal?: AbortSignal } = {},
  ): Promise<{ deliverable: StudioDeliverable; revision: StudioRequirementRevision }> {
  if (!target || !target.draftId || !Number.isSafeInteger(target.revision) || target.revision < 1
      || !target.ownership || !target.ownership.tenant_id || !target.ownership.context_root_id) {
    throw new ProcessApiError(422, '초안 링크를 확인하세요.', 'STUDIO_OPEN_TARGET_INVALID');
  }
  //: ★★★ 요청 «시작 시점» 의 문맥과 세대를 고정한다.
  //:
  //: ⚠️⚠️ 이것이 없으면 A 회사에서 보낸 조회가 B 회사로 바꾼 뒤 도착했을 때
  //:   `getStudioRequirementDraft` 가 **B 의 저장소**를 고르고 A 의 원문을 거기에 앉힌다.
  //:   화면의 `alive` 검사로는 못 막는다 — adopt 는 그 콜백보다 **먼저** 실행된다.
  //: ⚠️ abort 만으로 해결됐다고 보지 않는다. 취소가 늦거나 없는 경로가 늘 생긴다.
  const identity = processContextIdentity();
  const ticket = ++openGeneration;
  const live = () => {
    if (options.signal?.aborted || ticket !== openGeneration) {
      throw new ProcessApiError(409, '더 최근 요청이 있어 이 결과는 쓰지 않습니다.', 'STUDIO_OPEN_DISCARDED');
    }
    if (processContextIdentity() !== identity) {
      throw new ProcessApiError(409, '사용자·회사·조직이 바뀌었습니다. 원래 문맥에서 다시 확인해 주세요.', 'CLIENT_CONTEXT_CHANGED');
    }
  };
  live();
  const query = new URLSearchParams({ context_root_id: target.ownership.context_root_id,
    scope_node_id: target.ownership.scope_node_id || '', revision: String(target.revision) });
  const response = await apiFetch(
    `/api/v1/advisor/drafts/${encodeURIComponent(target.draftId)}?${query}`,
    { cache: 'no-store', signal: options.signal });
  live();
  const body = await unwrapProcessResponse<StudioRequirementRevision>(response);
  live();
  const row = validateLoadedRevision(body, target);
  const deliverable = deliverableOf(row);
  //: ⚠️⚠️ **추측해 덮지 않는다**(지시 ⑤). 종류를 모르면 다른 종류의 화면이 열리고,
  //:   거기서 저장하면 초안의 종류가 조용히 바뀐다.
  if (!deliverable) {
    throw new ProcessApiError(422,
      '이 초안의 산출물 종류를 확인하지 못해 편집 화면을 열 수 없습니다.', 'STUDIO_DELIVERABLE_UNKNOWN');
  }
  //: ★★★ **adopt «직전» 에 한 번 더 본다.** 여기까지 오는 사이에도 문맥은 바뀔 수 있고,
  //:   이 줄이 저장소에 쓰는 유일한 자리다.
  getStudioRequirementDraft(deliverable).adoptRevision(row, { ...options, expectIdentity: identity });
  return { deliverable, revision: row };
}
