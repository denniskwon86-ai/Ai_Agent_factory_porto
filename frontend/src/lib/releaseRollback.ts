import type { ApiError, RollbackResult } from './workspaceApi';

export type RollbackFeedback = {
  result: RollbackResult | null;
  message: string;
  error: string;
};

/** 처리 결과는 새로고침 뒤 게시한다. 조회 함수가 안내를 초기화해도 결과를 잃지 않는다. */
export function createRollbackRunner() {
  let running = false;
  return async ({ perform, refresh, onBusy }: {
    perform: () => Promise<RollbackResult>;
    refresh: () => Promise<unknown>;
    onBusy: (busy: boolean) => void;
  }): Promise<RollbackFeedback | null> => {
    if (running) return null;
    running = true;
    onBusy(true);
    const feedback: RollbackFeedback = { result: null, message: '', error: '' };
    try {
      try {
        feedback.result = await perform();
        if (feedback.result.outcome !== 'complete' || !feedback.result.program_disabled) {
          feedback.error = feedback.result.message || '사용 중단을 확인하지 못했습니다.';
        } else {
          feedback.message = feedback.result.message;
        }
      } catch (error) {
        const e = error as ApiError;
        feedback.result = e.rollback || null;
        feedback.error = e.message || '처리 결과를 확인하지 못했습니다. 상태를 확인한 뒤 다시 시도하십시오.';
      }
      // 응답 유실도 실제 변경이 없었다는 뜻은 아니다. 부분 실패일 때도 현재 상태를 갱신한다.
      try { await refresh(); }
      catch {
        feedback.error += `${feedback.error ? ' ' : ''}목록 갱신에 실패했습니다. 다시 조회하십시오.`;
      }
      return feedback;
    } finally {
      running = false;
      onBusy(false);
    }
  };
}
