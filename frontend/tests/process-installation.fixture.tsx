// 실제 제품 패널·컨트롤러를 사용하되 API는 메모리 대역이다. 서버 권한·DB·승인을 검증하지 않는다.
import { useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { ProcessInstallationPanel } from '../src/components/ProcessInstallationPanel';
import { ProcessApiError, type InstallationInput, type InstallationOperation, type InstallationPlan,
  type ProcessBoundary, type ProcessDocument, type ProcessInstallationApi, type ProcessPack,
  type ResolvedProcesses, type ProcessChangeReview, type ProcessChangeSummary,
  type ProcessApprovalReceipt, type ProcessApprovalInput, type ProcessEditInput,
  type ProcessChangeReceipt } from '../src/lib/processInstallationApi';
import '../src/index.css';
import '../src/design/afs.css';

type Scope = 'A' | 'B';
type Role = 'requester' | 'installer' | 'approver';
type Scenario = 'normal' | 'read503' | 'read403' | 'conflict409' | 'lost503' | 'postRead503' | 'propose422';
type Receipt = { sequence: number; scope: string; principal: string; method: 'GET' | 'POST'; action: string;
  body: unknown; outcome: string };
type World = { boundary: ProcessBoundary; registered: boolean; plans: Map<string, InstallationInput>;
  operations: InstallationOperation[]; requests: Map<string, { body: string; operation: InstallationOperation }>;
  changes: ProcessChangeReview[]; approved: ResolvedProcesses | null;
  edits: Map<string, { input: string; receipt: ProcessChangeReceipt }>;
  approvals: Map<string, { input: ProcessApprovalInput; receipt: ProcessApprovalReceipt }>;
  /** [2026-09-26] 승인됐지만 판본 활성화가 끊긴 업그레이드(합성). 재시도 실패 횟수를 정해 둔다. */
  upgrade?: { changeId: string; operationId: string; failuresLeft: number } };
const principals: Record<Role, string> = { requester: 'synthetic-requester', installer: 'synthetic-installer', approver: 'synthetic-approver' };
const roleLabels: Record<Role, string> = { requester: '모의 요청자', installer: '모의 설치 담당자', approver: '모의 별도 승인자' };
const clone = <T,>(value: T): T => structuredClone(value);
const artifact = 'a'.repeat(64);
const pack: ProcessPack = { kit_id: 'KIT-MFG-NONFERROUS-PROCUREMENT', version: '1.1.0',
  artifact_digest: artifact, name: '비철 제조 · 합성 표준 업무', state: 'DOMAIN_REVIEW_REQUIRED',
  data_class: 'NO_DATA', setup_only: true, business_kit_ids: ['BK-01', 'BK-02'],
  business_kits: [{ business_kit_id: 'BK-01', label: '원료 구매' }, { business_kit_id: 'BK-02', label: '원료 입고' }] };
const preview: ProcessDocument = {
  nodes: [
    { process_id: 'synthetic-buy', level: 'L1', parent_process_id: '', label: '원료 구매',
      note: '현업 검토 전 합성 표준입니다.', enabled: true },
    { process_id: 'synthetic-plan', level: 'L2', parent_process_id: 'synthetic-buy', label: '구매 계획',
      note: '필요 원료와 구매 시기를 검토합니다. 자료는 연결하지 않았습니다.', enabled: true },
    { process_id: 'synthetic-order', level: 'L2', parent_process_id: 'synthetic-buy', label: '주문 발주',
      note: '계약 내용을 확인하는 합성 업무입니다.', enabled: true },
    { process_id: 'synthetic-receive', level: 'L1', parent_process_id: '', label: '원료 입고', note: '', enabled: true },
    { process_id: 'synthetic-check', level: 'L2', parent_process_id: 'synthetic-receive', label: '입고 확인',
      note: '수량 대조를 위한 합성 업무입니다.', enabled: true },
  ],
  placements: [
    { placement_id: 'p-buy', process_id: 'synthetic-buy', parent_process_id: '', position: 0, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'p-plan', process_id: 'synthetic-plan', parent_process_id: 'synthetic-buy', position: 0, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'p-order', process_id: 'synthetic-order', parent_process_id: 'synthetic-buy', position: 1, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'p-receive', process_id: 'synthetic-receive', parent_process_id: '', position: 1, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'p-check', process_id: 'synthetic-check', parent_process_id: 'synthetic-receive', position: 0, hidden: false, kind: 'CANONICAL' },
  ], template_sources: [],
};

function createSyntheticServer() {
  let scenario: Scenario = 'normal';
  let pauseStarts = false;
  let postReadBlocked = false;
  let revision = 0;
  let planCount = 0;
  const receipts: Receipt[] = [];
  const worlds = new Map<string, World>();
  const waiting = new Set<() => void>();
  const listeners = new Set<() => void>();
  const notify = () => { revision++; listeners.forEach((listener) => listener()); };
  const fail = (status: number, code: string, message: string): never => {
    throw new ProcessApiError(status, `모의 API: ${message}`, code,
      '시험 제어에서 정상으로 바꾼 뒤 입력과 요청 기록을 확인하세요.');
  };
  function world(scope: Scope, companyWide: boolean) {
    const key = `${scope}:${companyWide ? 'root' : 'selected'}`;
    if (!worlds.has(key)) worlds.set(key, { registered: false, plans: new Map(), operations: [], requests: new Map(),
      changes: [], approved: null, approvals: new Map(), edits: new Map(),
      boundary: { tenant_id: `SYNTHETIC-TENANT-${scope}`, context_root_id: `SYNTHETIC-ROOT-${scope}`,
        entity_mode: 'REAL', scope_node_id: companyWide ? '' : `SYNTHETIC-SCOPE-${scope}`,
        configuration_kind: 'business_process' } });
    return worlds.get(key)!;
  }
  function checkBoundary(current: World, boundary: ProcessBoundary) {
    if (JSON.stringify(current.boundary) !== JSON.stringify(boundary)) {
      fail(409, 'SYNTHETIC_CONTEXT_CHANGED', '합성 문맥이 다릅니다.');
    }
  }
  async function call<T>(scope: string, principal: string, method: Receipt['method'], action: string,
    body: unknown, work: () => T | Promise<T>): Promise<T> {
    const receipt: Receipt = { sequence: receipts.length + 1, scope, principal, method, action, body: clone(body), outcome: '대기' };
    receipts.push(receipt); notify();
    try {
      if (method === 'GET' && (scenario === 'read503' || postReadBlocked)) fail(503, 'SYNTHETIC_READ_UNAVAILABLE', '조회 장애입니다. 빈 결과가 아닙니다.');
      if (method === 'GET' && scenario === 'read403') fail(403, 'SYNTHETIC_PERMISSION_DENIED', '권한이 회수되었습니다. 이전 결과를 숨깁니다.');
      if (['start', 'resume', 'approve', 'propose'].includes(action) && pauseStarts) {
        await new Promise<void>((resolve) => { waiting.add(resolve); notify(); });
      }
      const result = await work();
      if (['resume', 'approve', 'propose'].includes(action) && scenario === 'lost503') {
        fail(503, 'SYNTHETIC_RESPONSE_LOST', action === 'propose'
          ? '모의 제안 접수 뒤 응답을 유실했습니다. 정상으로 바꾼 뒤 같은 요청 번호로 접수를 확인하세요.'
          : '모의 쓰기 완료 뒤 응답을 유실했습니다. GET으로만 먼저 확인하세요.');
      }
      if (['start', 'resume', 'approve', 'propose'].includes(action) && scenario === 'postRead503') postReadBlocked = true;
      receipt.outcome = '모의 성공'; return clone(result);
    } catch (error) {
      receipt.outcome = error instanceof ProcessApiError ? `모의 오류 ${error.status} · ${error.reasonCode}` : '모의 오류';
      throw error;
    } finally { notify(); }
  }
  function apiFactory(scope: Scope, role: Role): (identity: string) => ProcessInstallationApi {
    // 제품의 identity는 받기만 한다. 실세션 값은 비교·기록·저장하지 않고 대역 문맥은 별도로 둔다.
    return (_identity: string) => {
      let companyWide = false;
      const principal = principals[role];
      const current = () => world(scope, companyWide);
      const label = () => `${scope}:${companyWide ? 'root' : 'selected'}`;
      const query = <T,>(action: string, body: unknown, work: () => T) => call(label(), principal, 'GET', action, body, work);
      const write = <T,>(action: string, body: unknown, work: () => T) => call(label(), principal, 'POST', action, body, work);
      const accessActions = () => role === 'approver' ? ['read', 'approve']
        : role === 'installer' ? ['read', 'propose', 'edit'] : ['read', 'propose'];
      const projectOperation = (operation: InstallationOperation): InstallationOperation => {
        const projected: InstallationOperation = { ...operation,
          permitted_actions: !operation.change_id && ['AWAITING_INSTALLER', 'FAILED_RETRYABLE', 'PLANNED', 'PREPARING'].includes(operation.stage)
            && role === 'installer' ? [operation.installer === principal ? 'resume' : 'adopt'] : [] };
        // 서버와 같게: 같은 승인 재요청 값(retry)은 활성화 대기일 때 그 승인자에게만 준다.
        if (operation.upgrade) {
          const { retry, ...upgrade } = operation.upgrade;
          projected.upgrade = upgrade.activation === 'ACTIVATION_PENDING' && role === 'approver' && retry
            ? { ...upgrade, retry } : upgrade;
        }
        return projected;
      };
      const projectChange = (change: ProcessChangeReview): ProcessChangeReview => {
        const blockers = [
          ...(change.actor === principal ? ['PROCESS_DISTINCT_REVIEWER_REQUIRED'] : []),
          ...(change.status !== 'DRAFT' ? ['PROCESS_CHANGE_NOT_DRAFT'] : []),
          ...(role !== 'approver' ? ['PROCESS_ACTION_FORBIDDEN'] : []),
          ...(change.status === 'DRAFT' && change.base_head_version !== (current().approved?.head_version || 0)
            ? ['PROCESS_HEAD_CONFLICT'] : []),
        ];
        return { ...change, principal_user_id: principal,
          current_head_version: current().approved?.head_version || 0,
          permitted_actions: blockers.length ? ['read'] : ['read', 'approve'], review_blockers: blockers };
      };
      const summary = (change: ProcessChangeReview): ProcessChangeSummary => {
        const { payload: _payload, base_payload: _basePayload, ...result } = projectChange(change);
        return result;
      };
      return {
        access: (wide) => { companyWide = wide; return query('access', { company_wide: wide },
          () => ({ boundary: current().boundary, principal_user_id: principal, context_root_label: `합성 회사 ${scope}`,
            target_label: companyWide ? `합성 회사 ${scope} 전체` : `합성 구매팀 ${scope}`,
            permitted_actions: accessActions() })); },
        resolved: (boundary) => query('resolved', boundary, (): ResolvedProcesses => {
          checkBoundary(current(), boundary);
          if (current().approved) return current().approved!;
          return { boundary, configuration_id: `synthetic-config-${label()}`, head_version: 0,
            profile_id: '', digest: '', state: 'EMPTY', payload: null, legacy_review_required: false };
        }),
        catalog: (boundary) => query('catalog', boundary, () => { checkBoundary(current(), boundary); return [pack]; }),
        legacy: (boundary) => query('legacy', boundary, () => { checkBoundary(current(), boundary); return { sources: [] }; }),
        register: (boundary, selected) => write('register', { boundary, kit_id: selected.kit_id, version: selected.version }, () => {
          checkBoundary(current(), boundary);
          if (role !== 'installer') fail(403, 'SYNTHETIC_PERMISSION_DENIED', '등록은 모의 설치 담당자만 가능합니다.');
          if (selected.artifact_digest !== artifact) fail(409, 'SYNTHETIC_PACK_CHANGED', '판본이 다릅니다.');
          current().registered = true; return { artifact_digest: artifact };
        }),
        plan: (body) => write('plan', body, (): InstallationPlan => {
          const target = current();
          if (role === 'approver') fail(403, 'SYNTHETIC_PERMISSION_DENIED', '모의 승인자는 설치 요청 역할이 아닙니다.');
          if (!target.registered) fail(404, 'SYNTHETIC_NOT_REGISTERED', '먼저 명시적으로 이 판본을 등록하세요.');
          if (body.context_root_id !== target.boundary.context_root_id || body.scope_node_id !== target.boundary.scope_node_id) {
            fail(409, 'SYNTHETIC_CONTEXT_CHANGED', '설치 입력의 문맥이 다릅니다.');
          }
          const digest = (++planCount).toString(16).padStart(64, '0');
          target.plans.set(digest, clone(body));
          return { plan_digest: digest, preview, state: 'READY', warnings: ['DOMAIN_REVIEW_REQUIRED'],
            data_ready: false, apps_ready: false };
        }),
        start: (body, digest, requestId) => write('start', { ...body, plan_digest: digest, client_request_id: requestId }, () => {
          // 실제 컨트롤러의 확정 충돌 분기를 시험하므로 알려진 코드만 이 시나리오에 사용한다.
          if (scenario === 'conflict409') fail(409, 'PROCESS_PLAN_CONFLICT', '계획 충돌입니다. 입력을 보존한 채 다시 계획할 수 있습니다.');
          const target = current();
          const planned = target.plans.get(digest);
          if (!planned || JSON.stringify(planned) !== JSON.stringify(body)) {
            fail(409, 'SYNTHETIC_PLAN_CHANGED', '원래 계획 입력과 시작 입력이 다릅니다.');
          }
          const signature = JSON.stringify({ body, digest });
          const existing = target.requests.get(requestId);
          if (existing) {
            if (existing.body !== signature) fail(409, 'SYNTHETIC_REQUEST_CONFLICT', '같은 요청 키의 본문이 다릅니다.');
            return projectOperation(existing.operation);
          }
          const operation: InstallationOperation = {
            operation_id: `SYNTHETIC-${label()}-${target.operations.length + 1}`, configuration_id: `synthetic-config-${label()}`,
            plan_digest: digest, stage: 'AWAITING_INSTALLER', error_code: '', kit_instance_ref: `synthetic-instance-${label()}`,
            change_id: '', actor: principal, installer: principal, revision: 1,
            applied_profile_id: '', data_ready: false, apps_ready: false,
          };
          target.operations.unshift(operation); target.requests.set(requestId, { body: signature, operation });
          if (scenario === 'lost503') fail(503, 'SYNTHETIC_RESPONSE_LOST', '모의 접수 후 응답을 유실했습니다. 자동 재전송하지 않습니다.');
          return projectOperation(operation);
        }),
        list: (boundary, offset = 0) => query('list', { boundary, offset }, () => {
          const target = current(); checkBoundary(target, boundary);
          return { items: target.operations.slice(offset, offset + 20).map(projectOperation),
            next_offset: target.operations.length > offset + 20 ? offset + 20 : null };
        }),
        get: (id) => query('get', { operation_id: id }, () => {
          const operation = current().operations.find((item) => item.operation_id === id);
          return operation ? projectOperation(operation) : fail(404, 'SYNTHETIC_OPERATION_NOT_FOUND', '이 합성 문맥에 요청이 없습니다.');
        }),
        resume: (operationId, expectedRevision, adopt) => write('resume',
          { operation_id: operationId, expected_revision: expectedRevision, adopt }, () => {
            const target = current(); const operation = target.operations.find((item) => item.operation_id === operationId);
            if (!operation) return fail(404, 'SYNTHETIC_OPERATION_NOT_FOUND', '설치 요청이 없습니다.');
            if (role !== 'installer') fail(403, 'SYNTHETIC_PERMISSION_DENIED', '모의 설치 담당자만 재개할 수 있습니다.');
            if (scenario === 'conflict409' || expectedRevision !== operation.revision) {
              fail(409, 'PROCESS_INSTALLATION_CONFLICT', '검토한 설치 revision과 현재 값이 다릅니다.');
            }
            if (!['AWAITING_INSTALLER', 'FAILED_RETRYABLE', 'PLANNED'].includes(operation.stage)) {
              fail(409, 'SYNTHETIC_STAGE_CONFLICT', '이미 진행된 요청은 재개할 수 없습니다.');
            }
            if (operation.installer !== principal && !adopt) fail(409, 'SYNTHETIC_ADOPT_REQUIRED', '명시적으로 인수해야 합니다.');
            operation.installer = principal; operation.revision++; operation.stage = 'AWAITING_APPROVAL';
            operation.change_id = `SYNTHETIC-change-${operation.operation_id}`;
            const payload = clone(preview);
            payload.template_sources = [{ artifact_digest: artifact, kit_instance_ref: operation.kit_instance_ref }];
            target.changes.unshift({ change_id: operation.change_id, configuration_id: operation.configuration_id,
              base_head_version: target.approved?.head_version || 0, draft_profile_id: `SYNTHETIC-draft-${operation.operation_id}`,
              draft_digest: (++planCount).toString(16).padStart(64, '0'), actor: operation.actor,
              reason: target.plans.get(operation.plan_digest)?.reason || '합성 설치', status: 'DRAFT',
              boundary: clone(target.boundary), current_head_version: target.approved?.head_version || 0,
              principal_user_id: principal, permitted_actions: [], review_blockers: [], operation_id: operation.operation_id,
              payload, base_payload: clone(target.approved?.payload || null) });
            return projectOperation(operation);
          }),
        propose: (boundary, body: ProcessEditInput) => write('propose', body, (): ProcessChangeReceipt => {
          const target = current(); checkBoundary(target, boundary);
          if (!accessActions().includes('propose')) fail(403, 'PROCESS_ACTION_FORBIDDEN', '모의 제안 권한이 없습니다.');
          if (body.context_root_id !== target.boundary.context_root_id || body.scope_node_id !== target.boundary.scope_node_id) {
            fail(409, 'SYNTHETIC_CONTEXT_CHANGED', '편집 입력의 범위가 다릅니다.');
          }
          const key = JSON.stringify([principal, body.client_request_id]);
          const signature = JSON.stringify(body); const prior = target.edits.get(key);
          if (prior) {
            if (prior.input !== signature) fail(409, 'PROCESS_IDEMPOTENCY_CONFLICT', '같은 요청 키의 편집 내용이 다릅니다.');
            return prior.receipt;
          }
          if (scenario === 'propose422') fail(422, 'PROCESS_COMMAND_INVALID', '모의 서버가 제안을 거절했습니다. 정상으로 바꾼 뒤 입력을 보존하고 수정 이어하기를 선택하세요.');
          const base = target.approved;
          if (!base?.payload) return fail(409, 'PROCESS_HEAD_CONFLICT', '먼저 합성 골격 설치·승인을 완료하세요.');
          if (scenario === 'conflict409' || base.head_version !== body.expected_head_version || base.profile_id !== body.base_profile_id) {
            fail(409, 'PROCESS_HEAD_CONFLICT', '모의 기준판 충돌입니다. 정상으로 바꾼 뒤 최신판을 명시 조회하세요.');
          }
          if (base.digest !== body.base_fingerprint) fail(409, 'PROCESS_DIGEST_CONFLICT', '편집 기준판의 지문이 다릅니다.');
          if (!body.client_request_id || !body.reason.trim() || !body.commands.length || body.commands.length > 200) {
            fail(422, 'PROCESS_CHANGE_INVALID', '변경 명령·이유·요청 번호가 필요합니다.');
          }
          // 모의 서버의 적용 함수이다. 제품 편집기 계산을 재사용하지 않아 미리보기와 독립적으로 대조한다.
          const payload = clone(base.payload);
          let placementSequence = 0;
          const requireParent = (id: string) => {
            if (!payload.nodes.some((node) => node.process_id === id && node.level === 'L1')) {
              fail(422, 'PROCESS_COMMAND_INVALID', '존재하는 상위 업무를 선택하세요.');
            }
          };
          const addPlacement = (processId: string, parent: string, kind: 'CANONICAL' | 'SHORTCUT') => {
            // 실제 서버 ID가 아니다. 모의 서버가 독립 발급하며 클라이언트 local-placement ID를 사용하지 않는다.
            payload.placements.push({ placement_id: `SYNTHETIC-server-placement-${label()}-${planCount + 1}-${++placementSequence}`,
              process_id: processId, parent_process_id: parent, kind, hidden: false, position: payload.placements.length });
          };
          const commandFields: Record<string, string[]> = {
            ADD_NODE: ['op', 'node'], RENAME: ['op', 'process_id', 'label'], SET_NOTE: ['op', 'process_id', 'note'],
            REORDER_PLACEMENTS: ['op', 'parent_process_id', 'placement_ids'], SET_USAGE: ['op', 'process_id', 'enabled'],
            MOVE_NODE: ['op', 'process_id', 'parent_process_id'], ADD_SHORTCUT: ['op', 'process_id', 'parent_process_id'],
            REMOVE_SHORTCUT: ['op', 'placement_id'],
          };
          for (const command of body.commands) {
            const fields = commandFields[command.op];
            if (!fields || JSON.stringify(Object.keys(command).sort()) !== JSON.stringify([...fields].sort())) {
              fail(422, 'PROCESS_COMMAND_UNSUPPORTED', '명령에 미리보기 메타데이터나 지원하지 않는 필드가 포함되었습니다.');
            }
            if (command.op === 'ADD_NODE') {
              const node = command.node;
              if (!node.process_id || payload.nodes.some((item) => item.process_id === node.process_id)
                || !node.label.trim() || node.label.length > 200 || typeof node.note !== 'string'
                || Object.keys(node).some((field) => !['process_id', 'level', 'parent_process_id', 'label', 'note'].includes(field))) {
                fail(422, 'PROCESS_COMMAND_INVALID', '새 업무의 ID·이름·설명과 필드를 확인하세요.');
              }
              if (node.level === 'L2') requireParent(node.parent_process_id);
              else if (node.level !== 'L1' || node.parent_process_id) fail(422, 'PROCESS_COMMAND_INVALID', '상위 업무는 최상위에만 추가하세요.');
              payload.nodes.push({ ...clone(node), enabled: true });
              addPlacement(node.process_id, node.parent_process_id, 'CANONICAL');
            } else if (command.op === 'REMOVE_SHORTCUT') {
              const found = payload.placements.find((placement) => placement.placement_id === command.placement_id && placement.kind === 'SHORTCUT');
              if (!found || command.placement_id.startsWith('local-placement-')) fail(422, 'PROCESS_COMMAND_INVALID', '모의 서버에 존재하는 바로가기만 제거할 수 있습니다.');
              payload.placements = payload.placements.filter((placement) => placement !== found);
            } else if (command.op === 'REORDER_PLACEMENTS') {
              if (command.parent_process_id) requireParent(command.parent_process_id);
              const siblings = payload.placements.filter((placement) => placement.parent_process_id === command.parent_process_id);
              if (new Set(command.placement_ids).size !== command.placement_ids.length
                || siblings.length !== command.placement_ids.length
                || command.placement_ids.some((id) => id.startsWith('local-placement-'))
                || siblings.some((placement) => !command.placement_ids.includes(placement.placement_id))) {
                fail(422, 'PROCESS_COMMAND_INVALID', '형제의 모든 배치 ID를 정확히 한 번씩 지정하세요.');
              }
              siblings.forEach((placement) => { placement.position = command.placement_ids.indexOf(placement.placement_id); });
            } else {
              const node = payload.nodes.find((item) => item.process_id === command.process_id);
              if (!node) return fail(422, 'PROCESS_COMMAND_INVALID', '수정할 업무 ID가 없습니다.');
              if (command.op === 'RENAME') {
                if (!command.label.trim() || command.label.length > 200) fail(422, 'PROCESS_COMMAND_INVALID', '업무 이름을 확인하세요.');
                node.label = command.label;
              } else if (command.op === 'SET_NOTE') {
                if (typeof command.note !== 'string') fail(422, 'PROCESS_COMMAND_INVALID', '설명은 문자열이어야 합니다.');
                node.note = command.note;
              } else if (command.op === 'SET_USAGE') {
                if (typeof command.enabled !== 'boolean') fail(422, 'PROCESS_COMMAND_INVALID', '사용 여부는 참·거짓이어야 합니다.');
                node.enabled = command.enabled;
              } else if (command.op === 'MOVE_NODE') {
                if (node.level !== 'L2') fail(422, 'PROCESS_COMMAND_INVALID', '하위 업무만 다른 상위 업무로 옮길 수 있습니다.');
                requireParent(command.parent_process_id);
                if (payload.placements.some((placement) => placement.kind === 'SHORTCUT'
                  && placement.process_id === node.process_id && placement.parent_process_id === command.parent_process_id)) {
                  fail(422, 'PROCESS_COMMAND_INVALID', '목적지의 같은 업무 바로가기를 먼저 제거하세요.');
                }
                node.parent_process_id = command.parent_process_id;
                payload.placements.filter((placement) => placement.process_id === node.process_id && placement.kind === 'CANONICAL')
                  .forEach((placement) => { placement.parent_process_id = command.parent_process_id; });
              } else if (command.op === 'ADD_SHORTCUT') {
                if (node.level !== 'L2') fail(422, 'PROCESS_COMMAND_INVALID', '하위 업무만 바로가기를 만들 수 있습니다.');
                requireParent(command.parent_process_id);
                if (node.parent_process_id === command.parent_process_id || payload.placements.some((placement) =>
                  placement.process_id === node.process_id && placement.parent_process_id === command.parent_process_id)) {
                  fail(422, 'PROCESS_COMMAND_INVALID', '원래 소속이나 기존 배치 위치에 중복 바로가기를 만들 수 없습니다.');
                }
                addPlacement(node.process_id, command.parent_process_id, 'SHORTCUT');
              } else fail(422, 'PROCESS_COMMAND_UNSUPPORTED', '지원하지 않는 합성 편집 명령입니다.');
            }
          }
          const serial = ++planCount;
          const receipt: ProcessChangeReceipt = { change_id: `SYNTHETIC-edit-${label()}-${serial}`,
            configuration_id: base.configuration_id, base_head_version: base.head_version,
            draft_profile_id: `SYNTHETIC-edit-profile-${label()}-${serial}`, draft_digest: serial.toString(16).padStart(64, '0'),
            actor: principal, reason: body.reason, status: 'DRAFT' };
          target.changes.unshift({ ...receipt, boundary: clone(target.boundary), current_head_version: base.head_version,
            principal_user_id: principal, permitted_actions: [], review_blockers: [], operation_id: null,
            payload, base_payload: clone(base.payload) });
          target.edits.set(key, { input: signature, receipt: clone(receipt) });
          return receipt;
        }),
        changes: (boundary, offset = 0) => query('changes', { boundary, offset }, () => {
          checkBoundary(current(), boundary);
          const changes = current().changes.filter((item) => item.status === 'DRAFT');
          return { items: changes.slice(offset, offset + 20).map(summary), next_offset: changes.length > offset + 20 ? offset + 20 : null };
        }),
        change: (boundary, changeId) => query('change', { boundary, change_id: changeId }, () => {
          checkBoundary(current(), boundary);
          const change = current().changes.find((item) => item.change_id === changeId);
          return change ? projectChange(change) : fail(404, 'SYNTHETIC_CHANGE_NOT_FOUND', '검토할 초안이 없습니다.');
        }),
        approve: (_boundary, changeId, body) => write('approve', { change_id: changeId, ...body }, () => {
          const target = current(); const change = target.changes.find((item) => item.change_id === changeId);
          if (!change) return fail(404, 'SYNTHETIC_CHANGE_NOT_FOUND', '검토할 초안이 없습니다.');
          if (change.actor === principal) fail(403, 'PROCESS_DISTINCT_REVIEWER_REQUIRED', '자기가 작성한 초안은 승인할 수 없습니다.');
          if (role !== 'approver') fail(403, 'SYNTHETIC_PERMISSION_DENIED', '모의 별도 승인자만 승인할 수 있습니다.');
          if (!body.reason.trim()) fail(422, 'SYNTHETIC_REASON_REQUIRED', '승인 이유가 필요합니다.');
          if (target.upgrade?.changeId === changeId) {
            // 같은 승인 재요청만 멱등 경로다. 다른 값이면 서버처럼 멱등 충돌로 거절한다.
            const approval = target.approvals.get(changeId)!;
            if (JSON.stringify(approval.input) !== JSON.stringify(body)) {
              fail(409, 'PROCESS_IDEMPOTENCY_CONFLICT', '이미 승인된 요청의 검토 내용이 다릅니다.');
            }
            const operation = target.operations.find((item) => item.operation_id === target.upgrade!.operationId)!;
            if (target.upgrade.failuresLeft > 0) {
              target.upgrade.failuresLeft--;
              fail(503, 'PROCESS_UPGRADE_ACTIVATION_PENDING',
                '업무판 승인은 기록됐고 새 판본 활성화는 끝나지 않았습니다. 같은 승인을 다시 요청하면 활성화를 다시 시도합니다.');
            }
            const activated = { ...operation.upgrade!, activation: 'ACTIVE' };
            delete activated.retry; delete activated.activation_error;
            operation.upgrade = activated;
            return approval.receipt;
          }
          const previous = target.approvals.get(changeId);
          if (previous && JSON.stringify(previous.input) === JSON.stringify(body)) return previous.receipt;
          if (scenario === 'conflict409' || change.status !== 'DRAFT'
            || change.base_head_version !== body.expected_head_version
            || (target.approved?.head_version || 0) !== body.expected_head_version
            || change.draft_digest !== body.draft_digest) {
            fail(409, 'PROCESS_HEAD_CONFLICT', '검토한 초안 지문 또는 기준 버전이 다릅니다.');
          }
          const receipt: ProcessApprovalReceipt = { change_id: changeId, configuration_id: change.configuration_id,
            status: 'APPLIED', profile_id: change.draft_profile_id, head_version: body.expected_head_version + 1,
            digest: body.draft_digest, event_id: `SYNTHETIC-event-${changeId}`, audit_delivery: 'PENDING' };
          change.status = 'APPLIED';
          target.approved = { boundary: clone(target.boundary), configuration_id: change.configuration_id,
            head_version: receipt.head_version, profile_id: receipt.profile_id, digest: receipt.digest, state: 'APPROVED',
            payload: clone(change.payload), legacy_review_required: false };
          // 기본 편집 변경안은 설치 operation이 없다. 기존 설치 기록을 새 편집 결과로 덮지 않는다.
          if (change.operation_id) {
            const operation = target.operations.find((item) => item.operation_id === change.operation_id)!;
            operation.stage = 'APPLIED'; operation.applied_profile_id = receipt.profile_id; operation.revision++;
          }
          target.approvals.set(changeId, { input: clone(body), receipt });
          return receipt;
        }),
      };
    };
  }
  // 화면 체험 전용 합성 기준판이다. 기존 쓰기·승인·초안·접수 기록은 절대로 덮지 않는다.
  function canSeedPreview(scope: Scope, companyWide: boolean) {
    const target = world(scope, companyWide);
    const label = `${scope}:${companyWide ? 'root' : 'selected'}`;
    return !waiting.size && !target.registered && !target.approved && !target.plans.size
      && !target.operations.length && !target.requests.size && !target.changes.length
      && !target.edits.size && !target.approvals.size
      && !receipts.some((receipt) => receipt.scope === label && receipt.method === 'POST');
  }
  return {
    apiFactory, receipts,
    canSeedPreview: (scope: Scope) => [false, true].some((wide) => canSeedPreview(scope, wide)),
    seedPreview: (scope: Scope) => {
      let count = 0;
      for (const wide of [false, true]) {
        if (!canSeedPreview(scope, wide)) continue;
        const target = world(scope, wide), label = `${scope}:${wide ? 'root' : 'selected'}`;
        target.approved = { boundary: clone(target.boundary), configuration_id: `synthetic-config-${label}`,
          head_version: 1, profile_id: `SYNTHETIC-PREVIEW-ONLY-${label}`, digest: 'e'.repeat(64),
          state: 'APPROVED', payload: clone(preview), legacy_review_required: false };
        count++;
      }
      if (count) notify();
      return count;
    },
    // [2026-09-26] 승인됐지만 판본 활성화가 끊긴 업그레이드 한 건(합성). 빈 선택 범위에만 넣는다.
    seedUpgrade: (scope: Scope) => {
      if (!canSeedPreview(scope, false)) return false;
      const target = world(scope, false), label = `${scope}:selected`;
      const changeId = `SYNTHETIC-upgrade-change-${label}`, operationId = `SYNTHETIC-upgrade-operation-${label}`;
      const input: ProcessApprovalInput = { expected_head_version: 1, draft_digest: 'd'.repeat(64),
        reason: '합성 · 데이터셋 계약을 싣는 1.2.0 업그레이드 승인' };
      const receipt: ProcessApprovalReceipt = { change_id: changeId, configuration_id: `synthetic-config-${label}`,
        status: 'APPLIED', profile_id: `SYNTHETIC-upgrade-profile-${label}`, head_version: 2,
        digest: input.draft_digest, event_id: `SYNTHETIC-event-${changeId}`, audit_delivery: 'PENDING' };
      target.approved = { boundary: clone(target.boundary), configuration_id: receipt.configuration_id,
        head_version: 2, profile_id: receipt.profile_id, digest: receipt.digest, state: 'APPROVED',
        payload: clone(preview), legacy_review_required: false };
      target.changes.unshift({ change_id: changeId, configuration_id: receipt.configuration_id, base_head_version: 1,
        draft_profile_id: receipt.profile_id, draft_digest: input.draft_digest, actor: principals.requester,
        reason: '합성 · 1.1.0 → 1.2.0 업그레이드', status: 'APPLIED', boundary: clone(target.boundary),
        current_head_version: 2, principal_user_id: '', permitted_actions: [], review_blockers: [],
        operation_id: operationId, payload: clone(preview), base_payload: clone(preview) });
      target.approvals.set(changeId, { input, receipt });
      target.operations.unshift({ operation_id: operationId, configuration_id: receipt.configuration_id,
        plan_digest: 'c'.repeat(64), stage: 'APPLIED', error_code: '', kit_instance_ref: 'SYNTHETIC-instance',
        change_id: changeId, actor: principals.requester, installer: principals.installer, revision: 3,
        applied_profile_id: receipt.profile_id, data_ready: false, apps_ready: false,
        upgrade: { instance_id: 'SYNTHETIC-instance', from_artifact_digest: 'a'.repeat(64), to_artifact_digest: 'b'.repeat(64),
          from_version: '1.1.0', to_version: '1.2.0', activation: 'ACTIVATION_PENDING',
          activation_error: 'PROCESS_STORAGE_UNAVAILABLE',
          retry: { change_id: changeId, ...input } } });
      target.upgrade = { changeId, operationId, failuresLeft: 1 };
      notify();
      return true;
    },
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => revision,
    setScenario: (value: Scenario) => { scenario = value; postReadBlocked = false; notify(); },
    setPause: (value: boolean) => { pauseStarts = value; notify(); },
    pendingCount: () => waiting.size,
    releasePending: () => { const pending = [...waiting]; waiting.clear(); pending.forEach((resolve) => resolve()); notify(); },
  };
}

// 제품 API를 잘못 연결해도 HTTP로 빠져나가지 않도록 이 fixture의 fetch를 닫는다.
// HTML의 connect-src 'none'도 함께 적용한다. 앱 셸·운영 데이터는 불러오지 않는다.
window.fetch = async () => { throw new Error('SYNTHETIC fixture: 실제 네트워크 요청 금지'); };

function Fixture() {
  const [server] = useState(createSyntheticServer);
  useSyncExternalStore(server.subscribe, server.getSnapshot, server.getSnapshot);
  const [scope, setScope] = useState<Scope>('A');
  const [role, setRole] = useState<Role>('installer');
  const [mount, setMount] = useState(0);
  const [visible, setVisible] = useState(true);
  const [scenario, setScenario] = useState<Scenario>('normal');
  const [pause, setPause] = useState(false);
  const [previewNotice, setPreviewNotice] = useState('');
  const posts = server.receipts.filter((item) => item.method === 'POST');
  return <main className="afs-scope" style={{ maxWidth: 1120, margin: '24px auto', padding: 20 }}>
    <section aria-label="합성 시험 안내" style={{ border: '2px solid #eab308', borderRadius: 12, padding: 16, marginBottom: 16 }}>
      <h1>SYNTHETIC / 모의 API — 표준 업무 설치 시험</h1>
      <p>실제 제품 컴포넌트와 컨트롤러를 사용합니다. 응답·권한·ID는 모두 메모리 합성 값이며 실제 서버·DB·승인은 호출하지 않습니다.</p>
      <p>운영 데이터 없음 · DOMAIN_REVIEW_REQUIRED · NO_DATA · 앱 사용 준비 미완료</p>
      <p>담당자 등록 → 요청자로 전환해 설치 요청 → 담당자의 명시 인수·재개 → 별도 승인자의 초안 검토·승인 → 적용 조회 순서입니다.</p>
      <p>기본 편집: 골격 승인 후 모의 요청자로 전환 → 업무 이름·설명·형제순서 수정 → 변경안 제안 → 모의 승인자로 기존 검토·승인 → 적용 조회.</p>
      <p>추가 설정에서 상위·하위 업무 추가, 사용 여부, 소속 이동, 바로가기를 체험할 수 있습니다. 새 배치는 모의 서버가 별도 ID를 발급하므로 형제순서 변경은 승인판을 조회한 뒤 진행하세요.</p>
      <p><strong>합성 3역할 리허설입니다. 실제 계정 선택·로그인 전환이 아니며 운영 사용자·세션은 변경하지 않습니다.</strong></p>
    </section>
    <section aria-label="모의 API 시험 제어" style={{ display: 'grid', gap: 12, padding: 16, border: '1px solid #64748b', borderRadius: 12, marginBottom: 16 }}>
      <h2>시험 제어 · 제품 기능 아님</h2>
      <button type="button" disabled={!server.canSeedPreview(scope)} onClick={() => {
        const count = server.seedPreview(scope);
        if (!count) return;
        setPreviewNotice(`합성 문맥 ${scope}의 빈 범위 ${count}곳에 화면 체험용 기준판을 넣었습니다. 운영 승인·설치 실행이 아니며 기존 기록은 변경하지 않았습니다.`);
        setRole('requester'); setVisible(true); setMount((value) => value + 1);
        setScenario('normal'); server.setScenario('normal');
      }}>편집 화면 바로 체험 · 합성 승인판</button>
      <p>빈 모의 범위에서만 사용합니다. 설치·승인 절차를 검증하지 않는 화면 미리보기이며 기존 승인판·요청·기록은 덮어쓰지 않습니다.</p>
      <button type="button" disabled={!server.canSeedPreview(scope)} onClick={() => {
        if (!server.seedUpgrade(scope)) return;
        setPreviewNotice(`합성 문맥 ${scope}에 «승인됐지만 판본 활성화가 끊긴 업그레이드» 한 건을 넣었습니다. 첫 재시도는 모의 503, 두 번째 재시도에서 활성화됩니다.`);
        setRole('approver'); setVisible(true); setMount((value) => value + 1);
        setScenario('normal'); server.setScenario('normal');
      }}>판본 업그레이드 활성화 대기 체험 · 합성</button>
      {previewNotice && <p role="status">{previewNotice}</p>}
      <label>합성 역할 선택 · 실계정 아님 <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
        <option value="requester">모의 요청자</option><option value="installer">모의 설치 담당자</option>
        <option value="approver">모의 별도 승인자</option>
      </select></label>
      <p>현재: {roleLabels[role]} ({principals[role]}). 역할 전환은 패널을 새로 열지만 같은 합성 회사의 모의 접수 내역은 유지합니다.</p>
      <label>모의 응답 시나리오 <select value={scenario} onChange={(event) => {
        const value = event.target.value as Scenario; setScenario(value); server.setScenario(value);
      }}>
        <option value="normal">정상</option>
        <option value="read503">조회 503 · 빈 데이터 아님</option>
        <option value="read403">조회 403 · 이전 결과 숨김</option>
        <option value="conflict409">쓰기 409 · GET 재확인 후 명시 재시도</option>
        <option value="propose422">편집 제안 422 · 명시 수정 이어하기 후 새 키</option>
        <option value="lost503">쓰기 후 응답 유실 503 · 결과 조회 필요</option>
        <option value="postRead503">쓰기 응답 성공 후 조회만 503 · 재POST 금지</option>
      </select></label>
      <label><input type="checkbox" checked={pause} onChange={(event) => {
        setPause(event.target.checked); server.setPause(event.target.checked);
      }} />설치·재개·승인·편집 제안 응답 보류 · 중복 클릭/늦은 응답 시험</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" disabled={!server.pendingCount()} onClick={server.releasePending}>보류 응답 완료 ({server.pendingCount()})</button>
        <button type="button" onClick={() => setMount((value) => value + 1)}>패널 재접속 · 모의 서버 유지</button>
        <button type="button" onClick={() => setScope((value) => value === 'A' ? 'B' : 'A')}>합성 문맥 A/B 전환 · 현재 {scope}</button>
        <button type="button" onClick={() => setVisible((value) => !value)}>{visible ? '패널 unmount' : '패널 다시 표시'}</button>
      </div>
      <p>재접속은 React 패널 remount 시험입니다. 문서 전체 새로고침 시 메모리 모의 서버도 초기화됩니다. 제품 로그인·문맥 전환 이벤트의 통합 검증은 아닙니다.</p>
      <p>409/503 이후 정상으로 전환해도 자동 요청하지 않습니다. 제품 버튼을 명시적으로 누르세요. 지연 응답은 완료 버튼으로만 풀립니다.</p>
    </section>
    {visible && <ProcessInstallationPanel key={`${scope}:${role}:${mount}`} companyName={`합성 회사 ${scope}`}
      scopeLabel={`합성 구매팀 ${scope}`} apiFactory={server.apiFactory(scope, role)} />}
    <section aria-label="모의 API 요청 기록" style={{ marginTop: 24 }}>
      <h2>모의 API 요청 기록 · 실제 전송 없음</h2>
      <p id="request-counts" aria-live="polite">총 {server.receipts.length}회 · 조회 GET {server.receipts.length - posts.length}회 · 쓰기 역할 POST {posts.length}회 · 설치 start {posts.filter((item) => item.action === 'start').length}회 · 재개 resume {posts.filter((item) => item.action === 'resume').length}회 · 승인 approve {posts.filter((item) => item.action === 'approve').length}회 · 편집 제안 propose {posts.filter((item) => item.action === 'propose').length}회</p>
      <p>plan의 원래 입력과 start의 추가 plan_digest/client_request_id를 대조하세요. 새로고침·재접속 뒤에는 조회 기록만 늘어야 합니다.</p>
      <p>재개는 expected_revision/adopt, 승인은 검토한 draft_digest/expected_head_version/reason을 대조하세요. 적용 후에도 NO_DATA·앱 준비 미완료입니다.</p>
      <p>편집 제안은 commands·고정 base/version/fingerprint·client_request_id를 기록합니다. 제안 접수만으로 승인판이 바뀌지 않습니다.</p>
      <pre id="request-receipt" style={{ maxHeight: 520, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', border: '1px solid #64748b', borderRadius: 8, padding: 12 }}>
        {JSON.stringify(server.receipts, null, 2)}
      </pre>
    </section>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
