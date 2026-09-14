// 실행 접수증과 실제 실행 상태는 다르다. 미확정 명령은 GET으로만 복구한다.
import { apiFetch } from './api';
import { studioIdentityKey, studioInputKey, studioInputMemory } from '../factory/studioInputMemory';

export type ExecutionOperation = 'START' | 'RESUME' | 'RESUME_QUOTA' | 'PAUSE' | 'STOP' | 'HEAL' | 'RELEASE' | 'REPLAN';
/** 프로젝트 전체를 대상으로 하는 명령의 고정 task_id. 서버가 이 값만 받는다. */
export const PROJECT_TASK = 'PROJECT';
export type ExecutionRequest = { client_request_id: string; operation: ExecutionOperation; task_id: string;
  input: { initial_idea?: string; master_data?: string; feedback?: string; error_log?: string } };
export type ExecutionReceipt = { request_id: string; project_id: string; actor_id: string;
  operation: ExecutionOperation; task_id: string; input: ExecutionRequest['input']; command_digest: string;
  status: 'PROCESSING' | 'ACCEPTED' | 'REJECTED' | 'UNKNOWN';
  result: null | { http_status: number; response: Record<string, unknown> };
  created_at: string; updated_at: string; receipt_digest: string };
export type ExecutionAttempt = { request: ExecutionRequest; receipt: ExecutionReceipt | null;
  outcome: 'UNKNOWN' | 'CONFIRMED' | 'REJECTED'; message: string };

const KIND = 'execution-command';
const EMPTY: ExecutionAttempt[] = [];
const listeners = new Set<() => void>();
const cache = new Map<string, ExecutionAttempt[]>();
const visible = new Map<string, Set<string>>();
let lastIdentity = '';
const object = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {};
const operations: ExecutionOperation[] = ['START', 'RESUME', 'RESUME_QUOTA', 'PAUSE', 'STOP', 'HEAL', 'RELEASE', 'REPLAN'];
const shaPattern = /^[a-f0-9]{64}$/;
const uuidPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort()
    .map(key => JSON.stringify(key) + ':' + canonical((value as Record<string, unknown>)[key])).join(',') + '}';
  return JSON.stringify(value);
}
async function hash(value: unknown): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(value)))))
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
}
function identity() {
  const value = studioIdentityKey();
  if (lastIdentity !== value) { visible.clear(); cache.clear(); lastIdentity = value; }
  return value;
}
const projectKey = (projectId: string) => JSON.stringify([identity(), projectId]);
const path = (projectId: string) => '/api/v1/factory/' + encodeURIComponent(projectId) + '/execution-commands';
const changed = () => { for (const listener of listeners) listener(); };
function save(projectId: string, attempt: ExecutionAttempt) {
  const current = studioInputMemory.get<ExecutionAttempt | null>(
    studioInputKey(projectId, KIND, attempt.request.client_request_id), null);
  // 먼저 확정한 동일 영수증을 늦게 도착한 PROCESSING/통신 오류로 되돌리지 않는다.
  if (current?.receipt && current.outcome !== 'UNKNOWN' && attempt.outcome === 'UNKNOWN') return;
  studioInputMemory.set(studioInputKey(projectId, KIND, attempt.request.client_request_id), attempt);
  cache.delete(projectKey(projectId)); changed();
}
function privateRecords(projectId: string): ExecutionAttempt[] {
  identity();
  return studioInputMemory.projectValues<ExecutionAttempt>(projectId, KIND);
}
export function getExecutionRecords(projectId: string): ExecutionAttempt[] {
  const key = projectKey(projectId);
  if (!visible.has(key)) return EMPTY;
  if (!cache.has(key)) cache.set(key, privateRecords(projectId)
    .filter(row => visible.get(key)?.has(row.request.client_request_id)).sort((a, b) =>
    (b.receipt?.created_at || '').localeCompare(a.receipt?.created_at || '')));
  return cache.get(key)!;
}
export const hasExecutionPending = (projectId: string) => privateRecords(projectId).some(row => row.outcome === 'UNKNOWN');
export const getExecutionRecoveryIds = (projectId: string) => privateRecords(projectId).map(row => row.request.client_request_id);
export function subscribeExecutionRecords(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }

class ExecutionError extends Error {
  readonly status: number;
  constructor(message: string, status = 0) { super(message); this.status = status; }
}
const invalid = () => new ExecutionError('명령 접수증의 대상·입력·무결성을 확인하지 못했습니다. 원래 요청을 보존합니다.', 503);
const same = (a: unknown, b: unknown) => canonical(a) === canonical(b);
function commandOf(row: ExecutionReceipt): ExecutionRequest {
  return { client_request_id: row.request_id, operation: row.operation, task_id: row.task_id, input: row.input };
}
async function validate(value: unknown, projectId: string, request?: ExecutionRequest, expected?: ExecutionReceipt | null) {
  const row = object(value) as ExecutionReceipt;
  if (!same(Object.keys(row).sort(), ['request_id', 'project_id', 'actor_id', 'operation', 'task_id', 'input',
    'command_digest', 'status', 'result', 'created_at', 'updated_at', 'receipt_digest'].sort())
      || !uuidPattern.test(row.request_id) || row.project_id !== projectId || typeof row.actor_id !== 'string' || !row.actor_id.trim()
      || !operations.includes(row.operation) || typeof row.task_id !== 'string' || !/^[A-Za-z0-9_-]{1,160}$/.test(row.task_id)
      || !row.input || Array.isArray(row.input) || typeof row.input !== 'object'
      || Object.entries(row.input).some(([key, v]) => !['initial_idea', 'master_data', 'feedback', 'error_log'].includes(key) || typeof v !== 'string')
      || !['PROCESSING', 'ACCEPTED', 'REJECTED', 'UNKNOWN'].includes(row.status)
      || !shaPattern.test(row.command_digest) || !shaPattern.test(row.receipt_digest)
      || !Number.isFinite(Date.parse(row.created_at)) || !Number.isFinite(Date.parse(row.updated_at))
      || Date.parse(row.updated_at) < Date.parse(row.created_at)) throw invalid();
  if (row.status === 'PROCESSING' ? row.result !== null : !row.result
      || !Number.isInteger(row.result.http_status) || row.result.http_status < 100 || row.result.http_status > 599
      || !same(Object.keys(row.result).sort(), ['http_status', 'response'])
      || !row.result.response || typeof row.result.response !== 'object' || Array.isArray(row.result.response)) throw invalid();
  if (row.status === 'ACCEPTED') {
    const result = row.result!;
    const reply = result.response;
    const wanted: Partial<Record<ExecutionOperation, string>> =
      { START: 'started', RESUME: 'resumed', RESUME_QUOTA: 'resumed', PAUSE: 'paused', STOP: 'stopped' };
    //: ★ [B5] 프로젝트 단위 명령은 응답 모양이 다르다. RELEASE 는 서버가 만든 release_id 를,
    //:   REPLAN 은 서버가 새로 정한 task_id 를 준다 — 둘 다 요청의 task_id('PROJECT')와 다르다.
    const valid = row.operation === 'HEAL'
      ? (reply.status === 'healing_started' && reply.task_id === 'TASK_REV_HEAL_' + row.request_id.replaceAll('-', '') && !reply.hotl_task_id)
        || (reply.status === 'success' && typeof reply.hotl_task_id === 'string'
          && /^[A-Za-z0-9_-]{1,160}$/.test(reply.hotl_task_id) && !reply.task_id)
      : row.operation === 'RELEASE'
      ? reply.status === 'success' && typeof reply.release_id === 'string' && !!reply.release_id
        && !reply.task_id && !reply.hotl_task_id
      : row.operation === 'REPLAN'
      ? reply.status === 'started' && typeof reply.task_id === 'string'
        && /^[A-Za-z0-9_-]{1,160}$/.test(reply.task_id) && !reply.hotl_task_id
      : reply.status === wanted[row.operation] && reply.task_id === row.task_id && !reply.hotl_task_id;
    if (result.http_status !== 200 || !valid) throw invalid();
  }
  if (row.status === 'REJECTED' && (row.result!.http_status < 400 || row.result!.http_status >= 500)) throw invalid();
  const command = commandOf(row);
  if ((request && !same(command, request)) || await hash(command) !== row.command_digest) throw invalid();
  const { receipt_digest: receiptDigest, ...unsigned } = row;
  if (await hash(unsigned) !== receiptDigest) throw invalid();
  if (expected && (row.actor_id !== expected.actor_id || row.command_digest !== expected.command_digest
      || row.created_at !== expected.created_at
      || (['ACCEPTED', 'REJECTED', 'UNKNOWN'].includes(expected.status) && row.receipt_digest !== expected.receipt_digest))) throw invalid();
  return structuredClone(row);
}
function attemptFrom(row: ExecutionReceipt): ExecutionAttempt {
  const detail = object(row.result?.response.detail);
  return { request: commandOf(row), receipt: row,
    outcome: row.status === 'ACCEPTED' ? 'CONFIRMED' : row.status === 'REJECTED' ? 'REJECTED' : 'UNKNOWN',
    message: row.status === 'ACCEPTED' ? '같은 요청의 접수를 확인했습니다. 실제 실행 상태는 별도로 확인하세요.'
      : row.status === 'REJECTED' ? typeof detail.message === 'string' ? detail.message : '요청이 거절되었습니다.'
        : '처리 결과가 미확정입니다. 새 요청을 보내지 말고 원래 요청을 조회하세요.' };
}
async function responseJson(response: Response) {
  const json = object(await response.json().catch(() => null));
  if (!response.ok) {
    const detail = object(json.detail);
    throw new ExecutionError(typeof detail.message === 'string' ? detail.message
      : typeof json.detail === 'string' ? json.detail : '명령 기록을 조회하지 못했습니다 (' + response.status + ').', response.status);
  }
  return json;
}
function current(expected: string) {
  if (identity() !== expected) throw new ExecutionError('사용자·회사 문맥이 바뀌었습니다. 현재 문맥에서 다시 조회하세요.', 409);
}
function hide(projectId: string) { visible.delete(projectKey(projectId)); cache.delete(projectKey(projectId)); changed(); }

export async function refreshExecutionRecords(projectId: string): Promise<void> {
  const owner = identity();
  try {
    const response = await apiFetch(path(projectId)); current(owner);
    const json = await responseJson(response); current(owner);
    if (!Array.isArray(json.requests)) throw invalid();
    const rows = await Promise.all(json.requests.map(row => validate(row, projectId))); current(owner);
    if (new Set(rows.map(row => row.request_id)).size !== rows.length || new Set(rows.map(row => row.actor_id)).size > 1) throw invalid();
    for (const row of rows) {
      const prior = privateRecords(projectId).find(item => item.request.client_request_id === row.request_id);
      await validate(row, projectId, prior?.request, prior?.receipt); current(owner);
    }
    for (const row of rows) save(projectId, attemptFrom(row));
    visible.set(projectKey(projectId), new Set(rows.map(row => row.request_id))); cache.delete(projectKey(projectId)); changed();
  } catch (error) {
    if (identity() === owner) hide(projectId);
    throw error;
  }
}
export async function recoverExecutionRequest(projectId: string, requestId: string): Promise<ExecutionReceipt | null> {
  const owner = identity();
  const prior = privateRecords(projectId).find(row => row.request.client_request_id === requestId);
  if (!prior) return null;
  try {
    const response = await apiFetch(path(projectId) + '/' + encodeURIComponent(requestId)); current(owner);
    const json = await responseJson(response); current(owner);
    const receipt = await validate(json.request, projectId, prior.request, prior.receipt); current(owner);
    save(projectId, attemptFrom(receipt));
    visible.set(projectKey(projectId), new Set([requestId])); cache.delete(projectKey(projectId)); changed();
    return receipt;
  } catch (error) {
    if (identity() !== owner) return null;
    if (error instanceof ExecutionError && [401, 403, 404].includes(error.status)) hide(projectId);
    // 404도 미접수 증거가 아니다. 원래 키/본문과 UNKNOWN 잠금을 유지한다.
    save(projectId, { ...prior, message: error instanceof Error ? error.message : '원래 요청 조회에 실패했습니다.' });
    return null;
  }
}

export async function executeStudioCommand(projectId: string, operation: ExecutionOperation, taskId: string,
  input: ExecutionRequest['input'] = {}): Promise<ExecutionAttempt> {
  const owner = identity();
  const request: ExecutionRequest = { client_request_id: crypto.randomUUID(), operation, task_id: taskId, input: structuredClone(input) };
  let attempt: ExecutionAttempt = { request, receipt: null, outcome: 'UNKNOWN', message: '서버의 명령 접수 결과를 확인하고 있습니다.' };
  if (hasExecutionPending(projectId) && !['PAUSE', 'STOP'].includes(operation)) return {
    ...attempt, outcome: 'REJECTED', message: '결과가 미확정인 요청이 있습니다. 원래 요청을 먼저 조회하세요.' };
  save(projectId, attempt);
  visible.set(projectKey(projectId), new Set([request.client_request_id])); cache.delete(projectKey(projectId)); changed();
  try {
    const response = await apiFetch(path(projectId), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    current(owner);
    const json = await responseJson(response); current(owner);
    const receipt = await validate(json.request, projectId, request); current(owner);
    // POST 응답만으로 확인 완료 표시하지 않는다. 동일 접수증 GET을 수행한다.
    attempt = { ...attempt, receipt };
    save(projectId, attempt);
    await recoverExecutionRequest(projectId, request.client_request_id); current(owner);
    return privateRecords(projectId).find(row => row.request.client_request_id === request.client_request_id) || attempt;
  } catch (error) {
    if (identity() !== owner) return { ...attempt, outcome: 'UNKNOWN', message: '문맥 변경 전 요청의 결과는 해당 문맥에서 확인하세요.' };
    attempt = { ...attempt, outcome: error instanceof ExecutionError && error.status >= 400 && error.status < 500 ? 'REJECTED' : 'UNKNOWN',
      message: error instanceof Error ? error.message : '응답이 없어 결과가 미확정입니다. 원래 요청을 조회하세요.' };
    save(projectId, attempt);
    if (error instanceof ExecutionError && [401, 403, 404].includes(error.status)) hide(projectId);
    return attempt;
  }
}
