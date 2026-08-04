// [UIUX] Jarvis 레일 (300px) — 전역 비서
//
// ★★ 작업서 §3-8: **Task ID 를 사용자에게 요구하지 않는다.** 회사·사용자·선택 객체 문맥을 쓴다.
// ★★ §3 명칭 호환: 표시명은 `Jarvis`, 엔진은 기존 Supervisor 다. 두 번째 채팅 API 를 만들지
//   않고 `lib/jarvisApi.ts` 어댑터로 붙인다.
//
// ⚠️ [교차검토 지적 3 반영] 이전 구현은 고정 질문 3개를 문자열로 판별해 **가짜 답**을 냈고,
//   그 답을 중앙 Banner 에 띄웠다. 두 가지가 문제였다:
//     ① 비서가 없는데 있는 것처럼 보인다 → 사용자는 그 내용을 근거로 판단한다.
//     ② 화면 5개에 같은 가짜 응답이 복제된다.
//   이제 실제 어댑터를 호출하고, **답변·대화는 이 레일 안에서 유지**한다.
//   연결이 안 된 상황은 숨기지 않고 그대로 보여준다(실패를 그럴듯한 답으로 대체하지 않는다).
import { useEffect, useRef, useState } from 'react';

import { jarvisApi, jarvisSession, type JarvisContext } from '../lib/jarvisApi';
import { HEALTH_KO, reportRequestFailure, reportRequestSuccess, useBackendHealth }
  from '../lib/backendHealth';

export type JarvisEvidence = { label: string; value: string };

export function JarvisRail({
  contextKicker = '현재 문맥',
  contextTitle,
  contextDescription,
  evidence = [],
  quickQuestions = [],
  context,
  projectId = '',
}: {
  contextKicker?: string;
  /** 지금 보고 있는 **객체**. id 를 사용자가 입력하게 하지 않는다. */
  contextTitle: string;
  contextDescription?: string;
  evidence?: JarvisEvidence[];
  quickQuestions?: string[];
  /** 서버로 보낼 문맥. `selected_object_id` 는 화면 강조 객체와 같아야 한다(지적 4). */
  context: JarvisContext;
  projectId?: string;
}) {
  const [turns, setTurns] = useState(jarvisSession.turns());
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>('');
  const logRef = useRef<HTMLDivElement>(null);
  // [UIUX-AUDIT-29 §3] 상태를 **실제 응답으로만** 바꾼다. 예전에는 서버가 죽어도 «연결»이었다.
  const health = useBackendHealth();

  useEffect(() => jarvisSession.subscribe(() => setTurns(jarvisSession.turns())), []);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [turns]);

  const send = async (message: string) => {
    const m = message.trim();
    if (!m || busy) return;
    setBusy(true); setErr('');
    jarvisSession.push({ role: 'user', text: m, at: new Date().toISOString(),
      objectId: context.selected_object_id });
    try {
      const r = await jarvisApi.ask(m, context, projectId);
      jarvisSession.push({ role: 'assistant', text: r.reply || '(빈 응답)',
        at: new Date().toISOString(), objectId: context.selected_object_id });
      reportRequestSuccess();
    } catch (e: any) {
      // 실패를 답으로 위장하지 않는다 — 무엇이 안 됐는지 그대로 말한다.
      //   ★ 그리고 그 실패를 상태 표시에 반영한다. 실패했는데 머리에 «연결»이 떠 있으면
      //     사용자는 원인을 자기 질문 탓으로 돌린다.
      reportRequestFailure();
      setErr(e?.status === 401
        ? '사용자를 지정해야 비서가 답할 수 있습니다.'
        : `비서 응답을 받지 못했습니다: ${e?.message || e}`);
    } finally { setBusy(false); setInput(''); }
  };

  return (
    <aside className="jarvis-rail" aria-label="Jarvis 비서">
      <header>
        <span className="jarvis-orb" aria-hidden="true">◈</span>
        <div>
          <small>AI FACTORY STUDIO</small>
          <b>Jarvis</b>
        </div>
        {/* ★★ [UIUX-AUDIT-29 §3] 상태를 **사실대로** 표시한다. 서버가 없는데 «연결»이라고
            쓰면, 답이 안 오는 이유를 사용자가 자기 질문 탓으로 돌린다. */}
        <span className={`online-dot ${health}`} title={HEALTH_KO[health].label}>
          ● {busy ? '생각 중' : HEALTH_KO[health].label}
        </span>
      </header>

      <div className="jarvis-context">
        <small>{contextKicker}</small>
        <h3>{contextTitle}</h3>
        {contextDescription && <p>{contextDescription}</p>}
      </div>

      {evidence.length > 0 && (
        <div className="jarvis-evidence">
          <b>참고 중인 근거</b>
          {evidence.map((e, i) => (
            // ⚠️ 라벨은 **데이터**다 — 같은 제목의 발간물 두 건처럼 얼마든지 겹친다.
            //   데이터를 key 로 쓰면 React 가 항목을 뒤섞거나 빠뜨린다(2026-08-04 실측).
            <div key={`${e.label}-${i}`}><span>{e.label}</span><em>{e.value}</em></div>
          ))}
        </div>
      )}

      {quickQuestions.length > 0 && (
        <div className="jarvis-quick">
          <b>바로 물어보기</b>
          {quickQuestions.map((q) => (
            <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>
          ))}
        </div>
      )}

      {/* 대화는 **이 레일 안에서** 유지된다(중앙 Banner 로 보내지 않는다). */}
      <div className="jarvis-log" ref={logRef} aria-live="polite">
        {turns.length === 0 && !err && (
          <div className="jarvis-answer">
            무엇이든 물어보십시오. 지금 선택한 객체와 회사·조직 권한 범위를 문맥으로 씁니다 —
            별도로 ID 를 입력할 필요는 없습니다.
          </div>
        )}
        {turns.map((t, i) => (
          <div key={`${t.at}-${i}`} className={`jarvis-turn ${t.role}`}>
            <span>{t.role === 'user' ? '나' : 'Jarvis'}</span>
            <p>{t.text}</p>
          </div>
        ))}
        {err && <div className="jarvis-turn error"><span>연결</span><p>{err}</p></div>}
      </div>

      {/* ⚠️ 오프라인이라고 입력을 막지 않는다(감사 §3). 막으면 사용자는 무엇을 물으려 했는지
          잊는다. 대신 «지금 보내면 실패한다»는 사실과 이유를 먼저 말한다. */}
      {health === 'offline' && (
        <div className="jarvis-offline">
          <b>서버에 연결되어 있지 않습니다</b>
          질문은 입력해 두실 수 있지만 지금 보내면 전송에 실패합니다. 임시 보관 기능은 아직
          없습니다 — 연결이 «연결됨»으로 바뀐 뒤 보내십시오.
        </div>
      )}
      {health === 'degraded' && (
        <div className="jarvis-offline warn">
          <b>응답이 지연되거나 일부 요청이 실패하고 있습니다</b>
          서버는 살아 있습니다. 실패하면 다시 시도해 보십시오.
        </div>
      )}

      <div className="jarvis-input">
        <textarea value={input} onChange={(e) => setInput(e.target.value)}
          placeholder="예: 이 앱은 어떤 자료를 요구합니까?"
          aria-label="Jarvis 에게 질문"
          onKeyDown={(e) => {
            // Enter 로 보내고 Shift+Enter 로 줄바꿈 — 키보드만으로 대화할 수 있어야 한다.
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); }
          }} />
        <button onClick={() => send(input)} disabled={busy || !input.trim()}>보내기</button>
      </div>
    </aside>
  );
}
