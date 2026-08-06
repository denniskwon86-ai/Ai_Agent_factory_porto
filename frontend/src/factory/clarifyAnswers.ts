/**
 * [트랙 E · 4단계] 요구 확인 답변의 **직렬화 계약** — 한 곳에만 둔다.
 *
 * ## 왜 추출했는가
 *
 * 이 문자열 형식은 **백엔드가 파싱하는 계약**이다. `RFP_Analyst` 가
 * `[요구 확인 인터뷰 답변]` / `N. 질문` / `→ 선택: …` 형태를 읽어 RFP 초안을 만든다.
 * 종전에는 `components/HOTLInput.tsx` 안에만 있었고, 신규 Studio 의 Decision Dock 이 같은
 * 제출을 하려면 **복사**해야 했다. 이 저장소에서 «판정·형식이 두 벌이 되면 반드시 갈라진다» 는
 * 것을 여섯 번 확인했다 — 그래서 옮기지 않고 **한 곳으로 모으고 양쪽이 부른다.**
 *
 * ⚠️ 형식을 바꾸면 백엔드 파서도 함께 봐야 한다. 화면만 고치면 답변이 조용히 무시된다
 *   (오류가 나지 않고 «선택 없음» 으로 읽힌다 — 가장 찾기 어려운 종류의 결함이다).
 */

/** 화면이 다루는 질문 하나. `HOTLInput`(any 기반)과 Studio(ViewModel 기반)가 모두 만족한다. */
export interface ClarifyQuestionLike {
  id: string;
  question: string;
  multi?: boolean;
  options?: { label: string; description?: string; recommended?: boolean }[];
}

/** 질문 id → 고른 라벨들. */
export type ClarifySelections = Record<string, string[]>;

/**
 * 추천안을 기본 선택으로 채운다. **이미 고른 것이 있으면 지키되, 없는 라벨은 버린다.**
 *
 * ⚠️ 라벨까지 확인하는 이유: 같은 `id` 로 질문이 재생성되면 옛 라벨이 남고, 그 라벨은 어떤
 *   옵션과도 맞지 않아 직렬화에서 «선택 없음» 으로 나간다(종전 `HOTLInput` 주석이 기록한 결함).
 */
export function defaultSelections(
  questions: ClarifyQuestionLike[],
  prev: ClarifySelections = {},
): ClarifySelections {
  const next: ClarifySelections = {};
  for (const q of questions) {
    const labels = (q.options || []).map((o) => o.label);
    const kept = (prev[q.id] || []).filter((l) => labels.includes(l));
    if (kept.length) { next[q.id] = kept; continue; }
    const rec = (q.options || []).find((o) => o.recommended);
    next[q.id] = rec ? [rec.label] : [];
  }
  return next;
}

/** 한 옵션을 켜고 끈다. 단일 선택 질문이면 교체한다. */
export function toggleSelection(
  sel: ClarifySelections,
  q: ClarifyQuestionLike,
  label: string,
): ClarifySelections {
  const cur = sel[q.id] || [];
  if (q.multi) {
    return {
      ...sel,
      [q.id]: cur.includes(label) ? cur.filter((l) => l !== label) : [...cur, label],
    };
  }
  return { ...sel, [q.id]: [label] };
}

/**
 * 백엔드(`RFP_Analyst`)가 소비하는 텍스트로 만든다. **형식을 바꾸지 말 것** — 위 주석 참조.
 */
export function serializeClarifyAnswers(
  questions: ClarifyQuestionLike[],
  selections: ClarifySelections,
  extraNote = '',
): string {
  const lines = ['[요구 확인 인터뷰 답변]'];
  questions.forEach((q, i) => {
    const sel = selections[q.id] || [];
    const picked = (q.options || []).filter((o) => sel.includes(o.label));
    lines.push(`${i + 1}. ${q.question}`);
    if (picked.length) {
      picked.forEach((o) => lines.push(
        `→ 선택: ${o.label}${o.description ? ` (${o.description})` : ''}`));
    } else {
      // «선택 없음» 을 빈 줄로 두지 않는다 — 백엔드가 질문을 건너뛴 것으로 읽으면 안 된다.
      lines.push('→ 선택 없음 (전문가 추천안대로 진행)');
    }
  });
  if (extraNote.trim()) {
    lines.push('', '[추가 의견]', extraNote.trim());
  }
  return lines.join('\n');
}

/** 아직 아무것도 고르지 않은 질문 수. **0 이 아니면 사용자가 볼 것이 남았다.** */
export function unansweredCount(
  questions: ClarifyQuestionLike[],
  selections: ClarifySelections,
): number {
  return questions.filter((q) => !(selections[q.id] || []).length).length;
}
