// 미저장 입력만 보존한다. 서버 저장·승인·권한 증명이 아니다.
import { getActingUser, getEnterpriseContext, getSessionToken } from '../lib/api';

const inputs = new Map<string, unknown>();
let owner = '';

export function studioIdentityKey(): string {
  const auth = JSON.stringify([getSessionToken(), getActingUser()]);
  if (owner !== auth) { inputs.clear(); owner = auth; }
  const c = getEnterpriseContext();
  return JSON.stringify([auth, c.tenantId, c.scopeNodeId, c.entityMode]);
}

export function studioInputKey(projectId: string, kind: string, subject: string): string {
  return JSON.stringify([studioIdentityKey(), projectId, kind, subject]);
}

function currentKey(key: string): boolean {
  try { return JSON.parse(key)[0] === studioIdentityKey(); } catch { return false; }
}
function projectEntries(projectId: string) {
  studioIdentityKey();
  return [...inputs.entries()].filter(([key]) => currentKey(key) && JSON.parse(key)[1] === projectId);
}
function pending(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return !!record.uncertain || !!record.attempt || !!record.discardAttempt || !!record.consumeAttempt
    || record.outcome === 'UNKNOWN' || record.outcome === 'RECORDED';
}

export const studioInputMemory = {
  projectValues<T>(projectId: string, kind: string): T[] {
    return projectEntries(projectId).filter(([key]) => JSON.parse(key)[2] === kind).map(([, value]) => structuredClone(value as T));
  },
  get<T>(key: string, fallback: T): T {
    if (!currentKey(key)) return structuredClone(fallback);
    return structuredClone((inputs.has(key) ? inputs.get(key) : fallback) as T);
  },
  set<T>(key: string, value: T): void {
    if (!currentKey(key)) return;
    inputs.set(key, structuredClone(value));
  },
  hasPending(projectId: string): boolean { return projectEntries(projectId).some(([, value]) => pending(value)); },
  hasInputs(projectId: string): boolean {
    return projectEntries(projectId).some(([key, value]) => {
      if (pending(value)) return true;
      const kind = JSON.parse(key)[2] as string;
      if (kind === 'decision-index' || kind === 'server-input-draft') return false;
      if (typeof value === 'string') return !!value.trim();
      if (!value || typeof value !== 'object') return false;
      const row = value as Record<string, unknown>;
      if (kind === 'clarification') return Object.keys(row).length > 0;
      if (kind.startsWith('decision-') && row.outcome !== 'EDITING') return false;
      return ['idea', 'reference', 'feedback', 'note', 'choice', 'text'].some(field => !!row[field]);
    });
  },
  clearProjectInputs(projectId: string): boolean {
    // 미확정 명령/결정의 중복 전송 방지 영수증은 사용자가 입력을 비워도 지우지 않는다.
    if (projectEntries(projectId).some(([, value]) => pending(value))) return false;
    for (const [key, value] of projectEntries(projectId)) {
      const kind = JSON.parse(key)[2] as string;
      if (kind === 'run-input' || kind === 'run-feedback' || kind === 'revision-input' || kind === 'clarification'
          || (kind.startsWith('decision-') && (value as { outcome?: string })?.outcome === 'EDITING')) inputs.delete(key);
    }
    return true;
  },
  clear(key: string): void { if (currentKey(key)) inputs.delete(key); },
  clearAll(): void { inputs.clear(); },
};

if (typeof window !== 'undefined') {
  window.addEventListener('factory:session-changed', () => {
    inputs.clear(); owner = '';
  });
}
