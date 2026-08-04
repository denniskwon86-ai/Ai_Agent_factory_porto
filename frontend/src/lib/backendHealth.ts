// [UIUX-AUDIT-29 §3] 백엔드 연결 상태 — **화면이 «연결»을 지어내지 않는다.**
//
// 감사 지적: 백엔드가 내려가 있는데도 Jarvis 가 `● 연결` 로 표시됐다. 상태 표시가 사실과 다르면
// 사용자는 «답이 안 오는 이유»를 자기 질문 탓으로 돌리고, 진짜 원인(서버가 없다)에 도달하지
// 못한다. 그래서 상태는 **실제 응답으로만** 바뀐다.
//
// 네 가지를 구분한다(감사 요구):
//   · `checking`  확인 중   — 아직 답을 받지 못했다. «연결»도 «오프라인»도 아니다.
//   · `online`    연결됨    — 최근 health 응답 성공.
//   · `degraded`  일시 중단 — health 는 살아 있는데 실제 요청이 실패했거나 응답이 느리다.
//   · `offline`   오프라인  — health 자체가 실패.
//
// ⚠️ `degraded` 를 `online` 에 합치지 않는다. "서버는 떠 있는데 이 기능만 안 된다"와 "서버가
//   없다"는 사용자가 할 일이 다르다(전자는 재시도, 후자는 담당자 호출).
import { useEffect, useState } from 'react';

import { API_BASE_URL } from './api';

export type HealthState = 'checking' | 'online' | 'degraded' | 'offline';

export const HEALTH_KO: Record<HealthState, { label: string; tone: string }> = {
  checking: { label: '확인 중', tone: 'muted' },
  online: { label: '연결됨', tone: 'success' },
  degraded: { label: '일시 중단', tone: 'warn' },
  offline: { label: '오프라인', tone: 'danger' },
};

/** 응답이 이보다 느리면 «일시 중단»으로 본다 — 살아 있어도 쓸 수 없는 상태다. */
const SLOW_MS = 2500;
const POLL_MS = 15000;

type Listener = (s: HealthState) => void;

let current: HealthState = 'checking';
let listeners: Listener[] = [];
let timer: ReturnType<typeof setInterval> | null = null;
/** 실제 업무 요청이 실패한 사실. health 가 성공해도 이 값이 있으면 «일시 중단»이다. */
let recentFailureAt = 0;

function set(next: HealthState) {
  if (next === current) return;
  current = next;
  listeners.forEach((l) => l(next));
}

async function probe() {
  const t0 = Date.now();
  try {
    const c = new AbortController();
    const to = setTimeout(() => c.abort(), 6000);
    const r = await fetch(`${API_BASE_URL}/api/v1/health`, { signal: c.signal });
    clearTimeout(to);
    if (!r.ok) { set('degraded'); return; }
    const slow = Date.now() - t0 > SLOW_MS;
    const recentlyFailed = Date.now() - recentFailureAt < 30000;
    set(slow || recentlyFailed ? 'degraded' : 'online');
  } catch {
    // ★ 실패를 «확인 중»으로 남겨 두지 않는다. 영원히 확인 중인 표시는 거짓말과 같다.
    set('offline');
  }
}

function start() {
  if (timer) return;
  probe();
  timer = setInterval(probe, POLL_MS);
}

/** 업무 요청이 실패했음을 알린다. 서버는 살아 있는데 기능이 안 되는 경우를 잡는다. */
export function reportRequestFailure() {
  recentFailureAt = Date.now();
  if (current === 'online') set('degraded');
  probe();
}

/** 업무 요청이 성공했음을 알린다 — 성공 하나가 «일시 중단»을 즉시 푼다. */
export function reportRequestSuccess() {
  recentFailureAt = 0;
  if (current !== 'online') probe();
}

export function useBackendHealth(): HealthState {
  const [s, setS] = useState<HealthState>(current);
  useEffect(() => {
    const l: Listener = (n) => setS(n);
    listeners.push(l);
    start();
    return () => { listeners = listeners.filter((x) => x !== l); };
  }, []);
  return s;
}
