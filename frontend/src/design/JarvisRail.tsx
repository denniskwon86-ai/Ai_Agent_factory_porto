// [UIUX] Jarvis 레일 (300px) — 전역 비서의 **문맥 표시**
//
// ★★ 작업서 §3-8: **Jarvis 가 Target Task ID 를 요구하게 만들지 않는다.** 회사·사용자·선택
//   객체 문맥을 쓴다. 사용자가 id 를 찾아 붙여야 하는 비서는 아무도 쓰지 않는다.
//
// ★★ §3 명칭 호환: 화면 표시명은 `Jarvis` 다. 기존 `Atlas`·`Supervisor Chat`·
//   `atlasSessionStore` 는 **같은 기능의 레거시 내부 명칭**으로 취급한다. 여기서 두 번째 채팅
//   API 를 만들지 않는다 — 지금은 문맥 표시와 빠른 질문까지만 두고, 대화 전송은 기존 계약에
//   adapter 로 붙인다(별도 단계). 이 파일이 세션을 소유하지 않는 이유가 그것이다.
//
// ⚠️ 페이지를 옮겨도 대화가 초기화되지 않아야 한다(§CL-FE-02). 그래서 이 컴포넌트는 **상태를
//   갖지 않는다** — 선택 객체만 props 로 받는다. 상태를 여기 두면 화면 전환마다 사라진다.
export type JarvisEvidence = { label: string; value: string };

export function JarvisRail({
  contextKicker = '현재 문맥',
  contextTitle,
  contextDescription,
  evidence = [],
  quickQuestions = [],
  onAsk,
  answer,
}: {
  contextKicker?: string;
  /** 지금 보고 있는 **객체**(릴리스·전달·결정). id 를 사용자가 입력하게 하지 않는다. */
  contextTitle: string;
  contextDescription?: string;
  /** 근거 — 무엇을 보고 답하는지. 비면 표시하지 않는다(빈 칸은 신뢰를 깎는다). */
  evidence?: JarvisEvidence[];
  quickQuestions?: string[];
  onAsk?: (q: string) => void;
  answer?: string;
}) {
  return (
    <aside className="jarvis-rail" aria-label="Jarvis 문맥">
      <header>
        <span className="jarvis-orb" aria-hidden="true">◈</span>
        <div>
          <small>AI FACTORY STUDIO</small>
          <b>Jarvis</b>
        </div>
        <span className="online-dot">● 연결됨</span>
      </header>

      <div className="jarvis-context">
        <small>{contextKicker}</small>
        <h3>{contextTitle}</h3>
        {contextDescription && <p>{contextDescription}</p>}
      </div>

      {evidence.length > 0 && (
        <div className="jarvis-evidence">
          <b>참고 중인 근거</b>
          {evidence.map((e) => (
            <div key={e.label}>
              <span>{e.label}</span>
              <em>{e.value}</em>
            </div>
          ))}
        </div>
      )}

      {quickQuestions.length > 0 && (
        <div className="jarvis-quick">
          <b>바로 물어보기</b>
          {quickQuestions.map((q) => (
            <button key={q} onClick={() => onAsk?.(q)}>{q}</button>
          ))}
        </div>
      )}

      {answer && <div className="jarvis-answer">{answer}</div>}
    </aside>
  );
}
