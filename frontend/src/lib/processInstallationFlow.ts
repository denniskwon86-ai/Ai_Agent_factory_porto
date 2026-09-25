import { ProcessApiError, type InstallationInput, type InstallationOperation, type InstallationPlan,
  type LegacySource, type ProcessAccess, type ProcessInstallationApi, type ProcessPack,
  type ProcessBoundary, type ResolvedProcesses, type ProcessChangeSummary,
  type ProcessChangeReview, type ProcessApprovalReceipt } from './processInstallationApi';

export type PreparedInstallation = { input: InstallationInput; plan: InstallationPlan; requestId: string; boundary: ProcessBoundary };
export type InstallationFlowState = {
  loaded: boolean; busy: string; error: ProcessApiError | null; access: ProcessAccess | null;
  resolved: ResolvedProcesses | null; packs: ProcessPack[]; legacy: LegacySource[];
  selectedDigest: string; registeredDigest: string; selectedKits: string[]; reason: string;
  legacyChoices: Record<string, 'KEEP_LEGACY' | 'MIGRATE'>;
  prepared: PreparedInstallation | null; startAttempted: boolean; startRejected: boolean;
  submittedOperationId: string; boundaryChanged: boolean; pendingAccess: ProcessAccess | null;
  preservedAttempts: PreparedInstallation[];
  operation: InstallationOperation | null; operations: InstallationOperation[]; nextOffset: number | null;
  changes: ProcessChangeSummary[]; nextChangeOffset: number | null; changesLoaded: boolean;
  review: ProcessChangeReview | null; approvalReason: string;
  mutationNeedsRefresh: boolean; approvalReceipt: ProcessApprovalReceipt | null; applicationVerified: boolean;
};

/** 화면 입력의 수명만 관리한다. 업무 상태 판정은 서버를 재사용한다. */
export function createInstallationFlow(api: ProcessInstallationApi, companyWide: boolean,
  newId = () => crypto.randomUUID()) {
  let generation = 0;
  let confirmedBoundary: ProcessBoundary | null = null;
  const boundaryKey = (b: ProcessBoundary) => JSON.stringify([
    b.tenant_id, b.context_root_id, b.entity_mode, b.scope_node_id, b.configuration_kind]);
  // 범위 왕복·응답 유실에도 재개/승인을 자동 재전송하지 않는다.
  const pendingMutations = new Map<string, { operationId: string; changeId: string }>();
  const approvalReasons = new Map<string, string>();
  let state: InstallationFlowState = { loaded: false, busy: '', error: null, access: null,
    resolved: null, packs: [], legacy: [], selectedDigest: '', registeredDigest: '', selectedKits: [], reason: '',
    legacyChoices: {}, prepared: null, startAttempted: false, startRejected: false, operation: null,
    submittedOperationId: '', boundaryChanged: false, pendingAccess: null, preservedAttempts: [],
    operations: [], nextOffset: null, changes: [], nextChangeOffset: null, changesLoaded: false,
    review: null, approvalReason: '', mutationNeedsRefresh: false, approvalReceipt: null, applicationVerified: false };
  const listeners = new Set<() => void>();
  const set = (patch: Partial<InstallationFlowState>) => {
    state = { ...state, ...patch }; listeners.forEach((listener) => listener());
  };
  function checkAccess(access: ProcessAccess) {
    if (confirmedBoundary && (Object.keys(confirmedBoundary) as (keyof ProcessBoundary)[])
      .some((key) => confirmedBoundary![key] !== access.boundary[key])) {
      set({ boundaryChanged: true, pendingAccess: access, loaded: false, access: null,
        resolved: null, packs: [], operations: [], operation: null, changes: [], changesLoaded: false,
        review: null, approvalReceipt: null, applicationVerified: false });
      throw new ProcessApiError(409, '서버의 조직 경계가 변경되었습니다. 이전 계획의 표시와 제출을 중단했습니다.', 'CLIENT_BOUNDARY_CHANGED');
    }
    confirmedBoundary ||= { ...access.boundary };
  }
  async function run(label: string, work: (check: () => void) => Promise<Partial<InstallationFlowState>>) {
    if (state.busy || state.boundaryChanged) return;
    const ticket = generation;
    const check = () => { if (ticket !== generation) throw new Error('STALE_VIEW'); };
    set({ busy: label, error: null });
    try { const patch = await work(check); check(); set(patch); }
    catch (error) {
      if (ticket === generation) {
        const value = error instanceof ProcessApiError ? error
          : new ProcessApiError(0, error instanceof Error ? error.message : '연결을 확인해 주세요. 입력을 보존했습니다.');
        set({ error: value, ...([401, 403, 404].includes(value.status) ? {
          loaded: false, access: null, resolved: null, packs: [], operations: [], operation: null,
          changes: [], changesLoaded: false, review: null, approvalReceipt: null, applicationVerified: false,
        } : {}) });
      }
    } finally { if (ticket === generation) set({ busy: '' }); }
  }
  const editable = () => !state.busy && !state.startAttempted;
  async function freshAccess(check: () => void) {
    const access = await api.access(companyWide); check(); checkAccess(access); return access;
  }
  async function readMutationResult(check: () => void) {
    const access = await freshAccess(check);
    const key = boundaryKey(access.boundary);
    const pending = pendingMutations.get(key);
    const operationId = pending ? pending.operationId : state.review?.operation_id || state.operation?.operation_id || '';
    const [page, resolved, operation, changes] = await Promise.all([
      api.list(access.boundary), api.resolved(access.boundary),
      operationId ? api.get(operationId) : Promise.resolve(null),
      api.changes(access.boundary),
    ]); check();
    const changeId = pending ? pending.changeId || operation?.change_id || '' : state.review?.change_id || operation?.change_id || '';
    const review = changeId ? await api.change(access.boundary, changeId) : null; check();
    if ((operation && operation.operation_id !== operationId)
      || (review && (review.change_id !== changeId || boundaryKey(review.boundary) !== key
        || review.principal_user_id !== access.principal_user_id))) {
      throw new ProcessApiError(503, '조회된 요청·검토자·범위를 확인하지 못했습니다. 다시 조회해 주세요.');
    }
    // 승인 응답이 아닌 단건/설치/현재 구성 GET을 함께 대조한다.
    const applicationVerified = !!review && review.status === 'APPLIED'
      && resolved.configuration_id === review.configuration_id
      && (resolved.head_version > review.base_head_version + 1
        || (resolved.head_version === review.base_head_version + 1
          && resolved.profile_id === review.draft_profile_id && resolved.digest === review.draft_digest))
      && (!review.operation_id || (operation?.operation_id === review.operation_id
        && operation.change_id === review.change_id && operation.stage === 'APPLIED'
        && operation.applied_profile_id === review.draft_profile_id));
    pendingMutations.delete(key);
    return { access, loaded: true, operations: page.items, nextOffset: page.next_offset, resolved,
      operation, review, changes: changes.items, nextChangeOffset: changes.next_offset,
      changesLoaded: true, mutationNeedsRefresh: false, applicationVerified,
      approvalReason: review ? approvalReasons.get(`${key}:${review.change_id}`) || '' : '' };
  }
  const model = {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    invalidate: () => { generation++; state = { ...state, busy: '' }; },
    suspendAccess: (error: ProcessApiError) => {
      generation++;
      set({ busy: '', loaded: false, error, access: null, resolved: null, packs: [], legacy: [],
        operations: [], operation: null, changes: [], changesLoaded: false, review: null,
        approvalReceipt: null, applicationVerified: false });
    },
    load: () => run('현재 구성 조회', async (check) => {
      const access = await api.access(companyWide); check();
      checkAccess(access);
      const [resolved, packs, page, legacy] = await Promise.all([
        api.resolved(access.boundary), api.catalog(access.boundary), api.list(access.boundary),
        access.permitted_actions.includes('propose') ? api.legacy(access.boundary) : Promise.resolve({ sources: [] }),
      ]);
      return { access, resolved, packs, operations: page.items, nextOffset: page.next_offset,
        legacy: legacy.sources, loaded: true, mutationNeedsRefresh: pendingMutations.has(boundaryKey(access.boundary)) };
    }),
    selectPack: (pack: ProcessPack) => {
      if (editable()) set({ selectedDigest: pack.artifact_digest, selectedKits: [...pack.business_kit_ids], prepared: null });
    },
    selectKit: (kit: string, selected: boolean) => {
      if (editable()) set({ selectedKits: selected ? [...new Set([...state.selectedKits, kit])]
        : state.selectedKits.filter((id) => id !== kit), prepared: null });
    },
    setReason: (reason: string) => { if (editable()) set({ reason, prepared: null }); },
    setLegacyChoice: (id: string, choice: 'KEEP_LEGACY' | 'MIGRATE') => {
      if (editable()) set({ legacyChoices: { ...state.legacyChoices, [id]: choice }, prepared: null });
    },
    prepare: () => run('설치 계획 확인', async (check) => {
      const { access, resolved, selectedKits, reason, legacy, legacyChoices } = state;
      const pack = state.packs.find((item) => item.artifact_digest === state.selectedDigest);
      if (!access || !resolved || !pack || !selectedKits.length || !reason.trim() || state.startAttempted) {
        throw new ProcessApiError(422, '업무와 설치 이유를 먼저 선택해 주세요.');
      }
      if (!access.permitted_actions.includes('propose')) throw new ProcessApiError(403, '업무 구성 제안 권한이 필요합니다.');
      if (legacy.some((source) => !legacyChoices[source.profile_id])) {
        throw new ProcessApiError(422, '기존 구성마다 원본 유지 또는 이관을 명시적으로 선택해 주세요.');
      }
      const input: InstallationInput = {
        context_root_id: access.boundary.context_root_id, scope_node_id: access.boundary.scope_node_id,
        artifact_digest: pack.artifact_digest, business_kit_ids: [...selectedKits],
        expected_head_version: resolved.head_version, base_profile_id: resolved.profile_id,
        base_fingerprint: resolved.digest, reason: reason.trim(), template_mapping: {},
        instance_id: resolved.payload?.template_sources.find((s) => s.artifact_digest === pack.artifact_digest)?.kit_instance_ref || '',
        legacy_decisions: legacy.map((source) => ({ profile_id: source.profile_id, source_digest: source.source_digest,
          decision: legacyChoices[source.profile_id], confirmed_context: { ...access.boundary },
          key_mapping: legacyChoices[source.profile_id] === 'MIGRATE'
            ? Object.fromEntries((source.payload.nodes || []).map((node) => [node.key, node.key])) : {} })),
      };
      // 등록은 별도 사용자 행동이다. 조회·계획 버튼에서 묵시 등록하지 않는다.
      const plan = await api.plan(input); check();
      return { prepared: { input, plan, requestId: newId(), boundary: { ...access.boundary } } };
    }),
    register: () => run('표준 업무 등록', async (check) => {
      const pack = state.packs.find((item) => item.artifact_digest === state.selectedDigest);
      if (!state.access || !pack || !state.access.permitted_actions.includes('edit')) {
        throw new ProcessApiError(403, '표준 업무를 선택하고 등록 권한을 확인해 주세요.');
      }
      const result = await api.register(state.access.boundary, pack); check();
      if (result.artifact_digest !== pack.artifact_digest) throw new ProcessApiError(409, '표준 업무 판본이 변경되었습니다. 다시 조회해 주세요.');
      return { registeredDigest: result.artifact_digest };
    }),
    start: () => run('설치 요청', async (check) => {
      const prepared = state.prepared;
      if (!prepared) throw new ProcessApiError(422, '먼저 설치 계획을 확인해 주세요.');
      set({ startAttempted: true });
      let operation: InstallationOperation;
      try { operation = await api.start(prepared.input, prepared.plan.plan_digest, prepared.requestId); }
      catch (error) {
        check();
        // 서버가 생성 전에 거절한 확정 충돌만 재계획할 수 있다. 통신 오류는 동일 키를 유지한다.
        if (error instanceof ProcessApiError && error.status === 409 && [
          'PROCESS_PLAN_CONFLICT', 'PROCESS_HEAD_CONFLICT', 'PROCESS_DIGEST_CONFLICT', 'PROCESS_LEGACY_CONFLICT',
        ].includes(error.reasonCode)) set({ startRejected: true });
        throw error;
      }
      check();
      // 응답 유실 뒤에도 같은 요청을 유지한다. 재접속은 목록·상세 GET으로만 복구한다.
      set({ operation, submittedOperationId: operation.operation_id });
      const fresh = await api.get(operation.operation_id); check();
      return { operation: fresh };
    }),
    refresh: (operationId?: string) => run('설치 상태 새로고침', async (check) => {
      if (!state.access) throw new ProcessApiError(422, '먼저 회사·조직을 확인해 주세요.');
      const id = operationId || state.operation?.operation_id;
      const access = await api.access(companyWide); check();
      checkAccess(access);
      const [page, resolved, operation] = await Promise.all([
        api.list(access.boundary), api.resolved(access.boundary), id ? api.get(id) : Promise.resolve(null),
      ]); check();
      return { access, operations: page.items, nextOffset: page.next_offset, resolved, operation };
    }),
    replan: () => run('최신 구성으로 계획 다시 확인', async (check) => {
      if (!state.startRejected || state.submittedOperationId) throw new ProcessApiError(409, '요청 결과가 확정되지 않아 같은 요청 번호를 유지합니다.');
      const access = await api.access(companyWide); check();
      checkAccess(access);
      const [resolved, legacy] = await Promise.all([api.resolved(access.boundary), api.legacy(access.boundary)]);
      check();
      return { access, resolved, legacy: legacy.sources, legacyChoices: {}, prepared: null,
        startAttempted: false, startRejected: false };
    }),
    more: () => run('이전 설치 요청 조회', async (check) => {
      if (!state.access || state.nextOffset === null) return {};
      const page = await api.list(state.access.boundary, state.nextOffset); check();
      const unique = new Map([...state.operations, ...page.items].map((op) => [op.operation_id, op]));
      return { operations: [...unique.values()], nextOffset: page.next_offset };
    }),
    resume: (adopt: boolean) => run(adopt ? '설치 담당자로 인수·진행' : '설치 계속 진행', async (check) => {
      const operation = state.operation;
      if (!operation || state.mutationNeedsRefresh) throw new ProcessApiError(409, '먼저 요청 결과를 다시 조회해 주세요.');
      const action = adopt ? 'adopt' : 'resume';
      if (!operation.permitted_actions?.includes(action)) throw new ProcessApiError(403, '현재 요청을 진행할 권한이 없습니다.');
      const access = await freshAccess(check);
      pendingMutations.set(boundaryKey(access.boundary), { operationId: operation.operation_id, changeId: '' });
      set({ mutationNeedsRefresh: true, applicationVerified: false, review: null, approvalReceipt: null });
      const result = await api.resume(operation.operation_id, operation.revision, adopt); check();
      if (result.operation_id !== operation.operation_id) throw new ProcessApiError(503, '재개 응답의 요청 번호가 다릅니다. 처리 결과를 다시 조회해 주세요.');
      set({ operation: result });
      pendingMutations.set(boundaryKey(access.boundary), { operationId: operation.operation_id, changeId: result.change_id });
      return readMutationResult(check);
    }),
    loadChanges: () => run('검토 대기 목록 조회', async (check) => {
      const access = await freshAccess(check);
      const page = await api.changes(access.boundary); check();
      return { access, changes: page.items, nextChangeOffset: page.next_offset, changesLoaded: true };
    }),
    moreChanges: () => run('이전 변경안 조회', async (check) => {
      if (!state.access || state.nextChangeOffset === null) return {};
      const page = await api.changes(state.access.boundary, state.nextChangeOffset); check();
      const unique = new Map([...state.changes, ...page.items].map((item) => [item.change_id, item]));
      return { changes: [...unique.values()], nextChangeOffset: page.next_offset };
    }),
    reviewChange: (changeId: string) => run('변경 전후 확인', async (check) => {
      set({ review: null, applicationVerified: false });
      const access = await freshAccess(check);
      const review = await api.change(access.boundary, changeId); check();
      if (review.change_id !== changeId || boundaryKey(review.boundary) !== boundaryKey(access.boundary)
        || review.principal_user_id !== access.principal_user_id) {
        throw new ProcessApiError(503, '검토할 변경안의 범위·검토자를 확인하지 못했습니다.');
      }
      return { access, review, approvalReason: approvalReasons.get(`${boundaryKey(access.boundary)}:${changeId}`) || '',
        approvalReceipt: state.approvalReceipt?.change_id === changeId ? state.approvalReceipt : null,
        applicationVerified: false };
    }),
    setApprovalReason: (approvalReason: string) => {
      if (!state.busy && !state.mutationNeedsRefresh && state.review) {
        approvalReasons.set(`${boundaryKey(state.review.boundary)}:${state.review.change_id}`, approvalReason);
        set({ approvalReason });
      }
    },
    approveChange: () => run('검토한 변경안 승인', async (check) => {
      const review = state.review;
      if (!review || state.mutationNeedsRefresh) throw new ProcessApiError(409, '먼저 승인 결과와 변경안을 조회해 주세요.');
      if (review.status !== 'DRAFT' || !review.permitted_actions.includes('approve')
        || !review.principal_user_id || review.actor === review.principal_user_id || review.review_blockers.length) {
        throw new ProcessApiError(403, '작성자와 다른 적격 승인자의 검토가 필요합니다.');
      }
      const reason = state.approvalReason.trim();
      if (!reason) throw new ProcessApiError(422, '승인 이유를 입력해 주세요.');
      const access = await freshAccess(check);
      if (access.principal_user_id !== review.principal_user_id || boundaryKey(access.boundary) !== boundaryKey(review.boundary)) {
        throw new ProcessApiError(409, '검토자 또는 범위가 바뀌었습니다. 변경안을 다시 열어 확인해 주세요.');
      }
      const body = { expected_head_version: review.base_head_version, draft_digest: review.draft_digest, reason };
      pendingMutations.set(boundaryKey(access.boundary), { operationId: review.operation_id || '', changeId: review.change_id });
      set({ mutationNeedsRefresh: true, applicationVerified: false, approvalReceipt: null });
      const receipt = await api.approve(access.boundary, review.change_id, body); check();
      if (receipt.change_id !== review.change_id || receipt.configuration_id !== review.configuration_id
        || receipt.profile_id !== review.draft_profile_id || receipt.digest !== review.draft_digest
        || receipt.head_version !== review.base_head_version + 1 || receipt.status !== 'APPLIED') {
        throw new ProcessApiError(503, '승인 응답과 검토한 변경안이 일치하지 않습니다. 결과를 다시 조회해 주세요.');
      }
      set({ approvalReceipt: receipt });
      return readMutationResult(check);
    }),
    refreshReview: () => run('처리 결과 다시 조회', readMutationResult),
    /**
     * [2026-09-26 Codex §20] 승인은 기록됐지만 판본 활성화가 끊긴 업그레이드를 **같은 승인 재요청**으로 잇는다.
     * 서버가 그 승인자에게만 준 `retry` 값(원래 기준판·지문·이유)을 그대로 보낸다 — 새 승인을 만들지 않는다.
     * 아직도 활성화가 안 되면 서버가 503(`PROCESS_UPGRADE_ACTIVATION_PENDING`)으로 알리고, 상태는 다시 조회한다.
     */
    retryActivation: () => run('판본 활성화 다시 시도', async (check) => {
      const operation = state.operation;
      const retry = operation?.upgrade?.activation === 'ACTIVATION_PENDING' ? operation.upgrade.retry : undefined;
      if (!operation || !retry) throw new ProcessApiError(409, '다시 시도할 활성화가 없습니다. 요청 상태를 다시 조회해 주세요.');
      const access = await freshAccess(check);
      let failure: ProcessApiError | null = null;
      try {
        await api.approve(access.boundary, retry.change_id, {
          expected_head_version: retry.expected_head_version, draft_digest: retry.draft_digest, reason: retry.reason });
      } catch (error) {
        if (!(error instanceof ProcessApiError) || error.reasonCode !== 'PROCESS_UPGRADE_ACTIVATION_PENDING') throw error;
        failure = error;
      }
      check();
      const [page, current] = await Promise.all([api.list(access.boundary), api.get(operation.operation_id)]); check();
      return { access, operation: current, operations: page.items, nextOffset: page.next_offset, error: failure };
    }),
    confirmBoundary: async () => {
      if (state.busy || !state.boundaryChanged || !state.pendingAccess) return;
      const preservedAttempts = state.startAttempted && state.prepared
        ? [...state.preservedAttempts, structuredClone(state.prepared)] : state.preservedAttempts;
      confirmedBoundary = { ...state.pendingAccess.boundary };
      // 운영 계층 A→B→A에서도 미확정 A 요청을 새 키로 대체하지 않는다.
      const prior = preservedAttempts.findLast((attempt) =>
        (Object.keys(confirmedBoundary!) as (keyof ProcessBoundary)[])
          .every((key) => attempt.boundary[key] === confirmedBoundary![key]));
      set({ boundaryChanged: false, pendingAccess: null, prepared: prior || null, startAttempted: !!prior,
        startRejected: false, submittedOperationId: '', selectedDigest: prior?.input.artifact_digest || '',
        selectedKits: prior ? [...prior.input.business_kit_ids] : [], reason: prior?.input.reason || '',
        legacy: [], legacyChoices: {}, registeredDigest: '', preservedAttempts, error: null,
        review: null, approvalReason: '', approvalReceipt: null, applicationVerified: false,
        mutationNeedsRefresh: pendingMutations.has(boundaryKey(confirmedBoundary)) });
      await model.load();
    },
  };
  return model;
}
export type InstallationFlow = ReturnType<typeof createInstallationFlow>;
