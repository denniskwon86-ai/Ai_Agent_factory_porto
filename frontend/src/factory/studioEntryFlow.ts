/** [DRAFT-ENTRY-01] 진입 확인 flow 의 **공통부**. 2026-09-15.
 *
 *  ## 왜 지금 뽑는가
 *
 *  `project` 와 `kit_app` 의 flow 본체는 **글자까지 같았다.** 셋째(`draft`)를 붙이는
 *  순간이 뽑을 자리다 — Codex 검토 권고 4: 「mega/draft 추가 시 «확인된» flow
 *  공통부분만 추출하고 기존 대상별 시험·오류코드는 보존한다」.
 *
 *  ⚠️⚠️ **오류 코드와 메시지는 뽑지 않는다.** 대상마다 사용자에게 할 말이 다르고,
 *    합치면 「무엇을 못 열었는지」가 한 문장으로 뭉개진다. 여기서 공통인 것은
 *    «수명» 뿐이다 — 세대(generation)·중단(abort)·신원(identity)·구독.
 *
 *  ## 이 flow 가 지키는 것 셋
 *
 *    ① **늦은 응답은 반영하지 않는다** — 세대가 바뀌었으면 버린다
 *    ② **문맥이 바뀌면 즉시 내린다** — 회사·사용자 전환 이벤트에 무효화
 *    ③ **해제 뒤에는 아무것도 하지 않는다** — dispose 후 응답이 와도 IDLE 이다
 */
import { studioIdentityKey } from './studioInputMemory';

export type EntryPhase = 'IDLE' | 'LOADING' | 'AVAILABLE' | 'BLOCKED';
export type EntryState<T, E> = { phase: EntryPhase; data: T | null; error: E | null };

/** 회사·사용자 전환. 이 셋 중 하나라도 오면 «확인해 둔 것» 은 더 이상 유효하지 않다. */
export const ENTRY_EVENTS = ['factory:session-changed', 'factory:acting-user-changed',
  'factory:enterprise-context-changed'];

export function createEntryFlow<T, E>(options: {
  /** 대상별 실제 조회. 각자의 검증·오류를 그대로 쓴다. */
  read: (signal: AbortSignal) => Promise<T>;
  /** 문맥이 바뀌었을 때 쓸 **그 대상의** 오류. 공통으로 만들지 않는다. */
  contextChanged: () => E;
  /** 그 대상이 스스로 낸 오류인가. 아니면 문맥 오류로 접는다. */
  isOwnError: (error: unknown) => boolean;
}) {
  let state: EntryState<T, E> = { phase: 'IDLE', data: null, error: null };
  let active = false, generation = 0, identity = '', controller: AbortController | null = null;
  const listeners = new Set<() => void>();
  const emit = (next: EntryState<T, E>) => { state = next; for (const listener of listeners) listener(); };
  const invalidate = () => {
    generation++; controller?.abort(); controller = null;
    emit({ phase: 'BLOCKED', data: null, error: options.contextChanged() });
  };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    isCurrent: () => active && identity === studioIdentityKey(),
    activate() {
      if (active) return;
      active = true;
      if (typeof window !== 'undefined') for (const event of ENTRY_EVENTS) window.addEventListener(event, invalidate);
    },
    dispose() {
      active = false; generation++; controller?.abort(); controller = null;
      if (typeof window !== 'undefined') for (const event of ENTRY_EVENTS) window.removeEventListener(event, invalidate);
      emit({ phase: 'IDLE', data: null, error: null });
    },
    invalidate,
    async load() {
      if (!active) return;
      const version = ++generation;
      controller?.abort(); controller = new AbortController();
      identity = studioIdentityKey();
      const requestIdentity = identity;
      const live = () => active && version === generation && requestIdentity === studioIdentityKey();
      emit({ phase: 'LOADING', data: null, error: null });
      try {
        const data = await options.read(controller.signal);
        if (live()) emit({ phase: 'AVAILABLE', data, error: null });
        else if (active && version === generation) invalidate();
      } catch (error) {
        if (!active || version !== generation) return;
        emit({ phase: 'BLOCKED', data: null,
          error: live() && options.isOwnError(error) ? (error as E) : options.contextChanged() });
      }
    },
  };
}
