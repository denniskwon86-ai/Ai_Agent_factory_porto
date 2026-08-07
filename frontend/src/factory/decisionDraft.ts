/**
 * [트랙 E · 7단계 전환 게이트] 사용자가 **작성 중이던 결정 초안**을 화면 밖에 보관한다.
 *
 * ## 왜 필요한가 — §8 전환 게이트가 「작업 보호 실패 0건」을 요구한다
 *
 * 2026-08-07 전환 게이트 실측에서 잡혔다:
 *   Decision Dock 의 「승인 조건이나 수정 요청」에 글을 쓰다가 «종전 통제실로» 를 눌렀다
 *   되돌아오면 **입력이 사라진다.** Studio 가 언마운트되면서 `useState('')` 가 초기화되기
 *   때문이다.
 *
 * ⚠️ **그리고 이것은 회귀다.** 기존 3패널의 같은 입력은 화면을 다녀와도 보존된다(그쪽은
 *   언마운트되지 않는다). 즉 신규 화면으로 옮기는 순간 사용자가 **하던 일을 잃는 경로**가
 *   새로 생긴다 — 승격 게이트가 막아야 하는 정확히 그 상황이다.
 *
 * ★ `jarvisApi.jarvisSession`(대화 이력을 모듈 스코프에 두는 것)과 **같은 방식**이다.
 *   그쪽에서 이미 「Dock 이 닫혀도 대화가 남아야 한다」를 이 방법으로 풀었다 — 두 벌을
 *   만들지 않고 같은 모양을 쓴다.
 *
 * ⚠️ 프로젝트별로 나눠 담는다. 한 칸에 담으면 A 프로젝트에 쓰던 승인 조건이 B 프로젝트의
 *   승인 칸에 나타난다 — 그것은 «보존» 이 아니라 **오입력 유도**다.
 * ⚠️ 제출에 성공하면 지운다. 남겨 두면 다음에 열었을 때 이미 보낸 문장이 다시 떠서
 *   «아직 안 보냈나» 로 읽힌다.
 * ⚠️ 저장소(localStorage)에 두지 않는다 — 세션을 넘겨 남길 만큼 확정된 입력이 아니고,
 *   승인 조건은 업무 내용이라 브라우저에 흘려 두지 않는 편이 낫다.
 */

/** projectId → 작성 중인 결정 초안. */
const drafts = new Map<string, string>();

export const decisionDraft = {
  get(projectId: string): string {
    return drafts.get(projectId) || '';
  },

  set(projectId: string, text: string): void {
    if (!projectId) return;
    if (text) drafts.set(projectId, text);
    else drafts.delete(projectId);
  },

  /** 제출에 **성공했을 때만** 부른다. */
  clear(projectId: string): void {
    drafts.delete(projectId);
  },
};
