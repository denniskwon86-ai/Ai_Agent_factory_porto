/** [SINGLE-ENTRY-01-FIX1 · 지시 4] 화면을 떠나기 «전» 에 물어야 하는 곳을 한 군데로 모은다.
 *
 *  ## 왜 필요한가
 *
 *  뒤로/앞으로가 `setBuildStart(false)` 로 편집기를 **즉시 닫았다.** 그러면
 *  `BuildStartDialog` 의 기존 미저장 입력 확인(`requestLeave`)을 **건너뛴다.**
 *  ⚠️ `beforeunload` 는 앱 «안» 이동의 대체 수단이 아니다 — 그것은 문서를 떠날 때만 뜬다.
 *
 *  ## 설계
 *
 *  입력을 들고 있는 화면이 **자기 상태로** 판단해 등록하고, 이동을 시작하는 쪽은
 *  「지금 떠나도 되는가」만 묻는다. 정책(유지·저장·폐기)은 **기존 UI 가 그대로** 가진다 —
 *  여기서 새 정책을 만들지 않는다.
 *
 *  ⚠️ 등록은 **하나**만 유효하다. 둘이 겹치면 어느 쪽 확인을 띄울지 알 수 없고, 실제로
 *    화면은 한 번에 하나만 입력을 들고 있다.
 */

/** 떠나도 되는지 답하고, 안 되면 «자기 확인 UI» 를 띄우는 쪽. */
export type LeaveGuard = {
  /** 지금 떠나도 안전한가(미저장 입력이 없는가). */
  safe: () => boolean;
  /** 안전하지 않을 때 확인을 띄운다. 사용자가 「떠난다」를 고르면 `proceed()` 를 부른다. */
  confirm: (proceed: () => void) => void;
  /** 확인을 띄우지 못했을 때. 화면이 «재시도 가능한» 오류를 보여 준다. */
  onConfirmError?: (error: unknown) => void;
};

/** `confirmLeave` 의 결과. **「보호 없음」과 「보호 실행 실패」는 다른 일이다.** */
export type LeaveOutcome = 'no-guard' | 'asked' | 'failed';

let current: LeaveGuard | null = null;

export function registerLeaveGuard(guard: LeaveGuard): () => void {
  current = guard;
  return () => { if (current === guard) current = null; };
}

/** 등록된 보호가 없거나 안전하면 `true`. 화면이 없으면 막을 이유도 없다. */
export function canLeaveNow(): boolean {
  if (!current) return true;
  try {
    return current.safe() === true;
  } catch {
    //: ⚠️ 판단이 실패하면 **막는 쪽** 으로 답한다. 잃는 것은 되돌릴 수 없다.
    return false;
  }
}

/** 확인을 띄운다. 사용자가 계속하겠다고 하면 `proceed` 가 불린다.
 *
 *  ⚠️ 보호가 **없으면** 묻지 않고 바로 진행한다 — 물을 사람이 없는데 멈추면 앱이 잠긴다.
 *  ⚠️⚠️ 그러나 보호가 **있는데 실행에 실패하면 떠나지 않는다.** 종전에는 예외에서
 *    `proceed()` 를 불렀다 — **보호 실패가 「이동 승인」으로 바뀌는** fail-open 이었고,
 *    그 순간 미저장 입력이 사라진다. 잃는 것은 되돌릴 수 없으므로 막는 쪽으로 답한다.
 *  ★ 화면은 그대로 남으므로 사용자는 **다시 시도할 수 있다.** */
export function confirmLeave(proceed: () => void): LeaveOutcome {
  if (!current) { proceed(); return 'no-guard'; }
  try {
    current.confirm(proceed);
    return 'asked';
  } catch (error) {
    try { current.onConfirmError?.(error); } catch { /* 알림 실패가 이동을 만들지 않는다 */ }
    return 'failed';
  }
}

/** 시험·화면 전환에서 남은 등록을 지운다. */
export function clearLeaveGuard(): void { current = null; }
