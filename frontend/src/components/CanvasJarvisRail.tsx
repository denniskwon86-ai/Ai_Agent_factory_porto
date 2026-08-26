import { useEffect, useRef, useState } from 'react';

import { ServerText } from '../design/ServerText';
import { ASSISTANT_NAME } from '../lib/brand';
import {
  HEALTH_KO, reportRequestFailure, reportRequestSuccess, useBackendHealth,
} from '../lib/backendHealth';
import { jarvisApi, jarvisSession, type JarvisContext, type JarvisTurn }
  from '../lib/jarvisApi';

// [승인 시안] 우측 비서 레일 — **시안 마크업 + 우리 비서 이름.**
//
// ## ⚠️⚠️ [2026-08-25 사용자 지적] **이름이 Atlas 가 아니다**
//
// > 우리 시스템의 AI비서 이름은 Atlas가 아니잖아요!
//
// 시안의 「Atlas」를 그대로 베꼈다. 이 시스템의 비서는 **Jarvis(자비스)** 다 —
// `api/v1/jarvis` 이고, `api/routes/jarvis_control.py` 머리말은 대놓고
// 「**두 번째 비서를 만들지 않는다**」라고 적어 두었다. 그 파일을 읽고도 이름을 베꼈다.
//
// ★ `.atlas-*` **CSS 클래스 이름은 그대로 둔다** — 그것은 시안의 «스타일 이름» 이지
//   비서 이름이 아니다. 화면에 보이는 이름만 우리 것으로 되돌린다.
//
// 원본: `uiux-prototypes/master-concept/index.html` 의 `<aside class="atlas-rail">`
// 스타일: `design/enterprise-canvas.css` 의 `.atlas-*` · `.brief` (이미 이식돼 있었다)
//
// ## ⚠️⚠️ [2026-08-25 사용자 지적] 왜 다시 만들었는가
//
// > 오른쪽 영역에 AI비서 부분의 디자인도 시안과 동일하게 수정해주세요
//
// `.atlas-rail` 안에 범용 `JarvisRail` 을 그대로 넣고 있었다. 그래서 **이식해 둔
// `.atlas-*` CSS 가 한 줄도 쓰이지 않았고**(선택자는 있는데 그 클래스를 쓰는 마크업이
// 없었다), 화면은 시안과 전혀 다른 모양이었다.
//
// ★ 마크업을 시안에서 옮기고 **기능은 그대로 잇는다** — 질문·답변은 같은 `jarvisApi` 다.
//
// ## ⚠️ 시안의 숫자는 표본이다
//
// 시안 `ATLAS DECISION BRIEF` 는 「납기 준수율 96% 이상」·「운전자본 약 ₩8.3억 감소」·
// 「근거 48건, 신뢰도 89%」를 적어 두었다. 그 화면에는 `PROTOTYPE · SAMPLE DATA` 배지가
// 붙어 있다. 채택 결정문이 「표시하는 수치·상태·추천은 **실제 API 근거가 있을 때만**」을
// 못박았으므로, 자리는 지키고 **우리가 실제로 아는 것**을 넣는다.
// ⚠️ 「권고」는 지어내지 않는다 — 우리 계산은 아직 권고를 내지 않는다. 대신 지금 답해야
//   할 것과 그 근거를 적고, 권고가 필요한 곳으로 **갈 수 있게** 한다.

export type JarvisFact = { label: string; value: string };

export function CanvasJarvisRail({
  contextLabel, title, why, facts, actions, context, onRecommend, recommendLabel,
}: {
  /** 시안의 `CURRENT CONTEXT · 생산계획` 자리. */
  contextLabel: string;
  title: string;
  /** 서버가 준 설명. ⚠️ 화면이 다시 쓰지 않는다. */
  why?: string;
  /** 시안 `brief` 의 목록 자리 — **우리가 아는 사실**만. */
  facts: JarvisFact[];
  /** 시안 `atlas-actions` 의 보조 버튼들 — 누르면 비서에게 그대로 묻는다. */
  actions: string[];
  context: JarvisContext;
  /** 시안의 빨간 1차 행동. ⚠️ 없으면 그리지 않는다 — 누를 수 없는 버튼은 고장으로 읽힌다. */
  onRecommend?: () => void;
  recommendLabel?: string;
}) {
  const [turns, setTurns] = useState<JarvisTurn[]>(jarvisSession.turns());
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const primaryLabel = recommendLabel || '의사결정 안건으로 만들기';
  const [selectedAction, setSelectedAction] = useState(primaryLabel);
  //: ★ 스크롤하는 것은 **본문**이다(로그가 아니다). 로그를 스크롤 상자로 두면 상자 둘이
  //:   생기고, 그중 하나가 화면 밖으로 밀려나 새 답이 보이지 않는다(2026-08-26 실측).
  const bodyRef = useRef<HTMLDivElement>(null);
  // ★★ 상태를 **사실대로** 표시한다. 서버가 없는데 «연결» 이라고 쓰면, 답이 안 오는
  //   이유를 사용자가 자기 질문 탓으로 돌린다(UIUX-AUDIT-29 §3).
  const health = useBackendHealth();

  useEffect(() => jarvisSession.subscribe(() => setTurns(jarvisSession.turns())), []);
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    //: ⚠️ 답이 도착했는데 사용자가 스크롤을 내려야 보인다면 「안 왔다」와 구별되지 않는다.
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [turns, busy, err]);

  const send = async (message: string) => {
    const m = message.trim();
    if (!m || busy) return;
    setBusy(true); setErr('');
    jarvisSession.push({ role: 'user', text: m, at: new Date().toISOString(),
      objectId: context.selected_object_id });
    try {
      const r = await jarvisApi.ask(m, context, '');
      jarvisSession.push({ role: 'assistant', text: r.reply || '(빈 응답)',
        at: new Date().toISOString(), objectId: context.selected_object_id });
      reportRequestSuccess();
    } catch (e: any) {
      // ⚠️ 실패를 답으로 위장하지 않는다 — 무엇이 안 됐는지 그대로 말한다.
      reportRequestFailure(e?.status);
      setErr(e?.status === 401
        ? '사용자를 지정해야 비서가 답할 수 있습니다.'
        : `비서 응답을 받지 못했습니다: ${e?.message || e}`);
    } finally { setBusy(false); setInput(''); }
  };

  //: ★★★ 상태 이름을 **지어내지 않는다.** 처음에 `ok`·`down` 이라고 썼는데 이 저장소의
  //:   어휘는 `checking · online · degraded · offline` 이고 한글 이름도 `HEALTH_KO` 에
  //:   이미 있다(타입 검사가 잡아 줬다 — 「겹치는 값이 없다」).
  //: ⚠️ 같은 질문에 두 어휘가 생기면 한쪽만 고쳐지는 날이 온다.
  const DOT: Record<typeof health, string> = {
    checking: '#d39a58', online: '#53c8b8', degraded: '#d39a58', offline: 'var(--ls-red)',
  };
  const dot = DOT[health];
  const dotKo = HEALTH_KO[health].label;

  return (
    <>
      <header className="atlas-head">
        <span className="atlas-orb" aria-hidden>✦</span>
        <div>
          <b>{ASSISTANT_NAME}</b>
          <span>회사 전체를 이해하는 AI 경영비서</span>
        </div>
        {/* 시안의 오른쪽 점. ★ 색만으로 말하지 않는다 — `title` 로 이름을 남긴다. */}
        <i title={`서버 ${dotKo}`} aria-label={`서버 ${dotKo}`}
           style={{ background: dot, boxShadow: `0 0 0 4px ${dot}1a` }} />
      </header>

      <div className="atlas-body" ref={bodyRef}>
        <span className="atlas-context">{contextLabel}</span>
        <h2>{title}</h2>
        {why && <p><ServerText text={why} /></p>}

        <section className="brief">
          <small>지금 판단의 근거</small>
          {/* ⚠️ 시안은 여기에 «권고» 를 적었다(`발주량 -4% …`). 우리 계산은 아직 권고를
              내지 않으므로 **지어내지 않는다.** 무엇을 근거로 보고 있는지를 적는다. */}
          <strong>
            {facts.length
              ? '지금 이 판단이 서 있는 근거입니다.'
              : '아직 근거로 삼을 것을 읽지 못했습니다.'}
          </strong>
          <ul>
            {facts.length ? facts.map((f) => (
              <li key={f.label}>{f.label} — {f.value}</li>
            )) : (
              // ⚠️ 「없다」와 「못 읽었다」를 섞지 않는다.
              <li>서버에서 근거를 받지 못했습니다 — 없다는 뜻은 아닙니다.</li>
            )}
          </ul>
        </section>

        <div className="atlas-actions">
          {onRecommend && (
            <button type="button" className={selectedAction === primaryLabel ? 'selected' : ''}
              aria-pressed={selectedAction === primaryLabel}
              onClick={() => { setSelectedAction(primaryLabel); onRecommend(); }}>
              {primaryLabel}
            </button>
          )}
          {actions.map((q) => (
            <button key={q} type="button" disabled={busy}
              className={selectedAction === q ? 'selected' : ''}
              aria-pressed={selectedAction === q}
              onClick={() => { setSelectedAction(q); void send(q); }}>
              {q}
            </button>
          ))}
        </div>

        {/* 주고받은 말. ★ 시안에는 이 자리가 없다 — 시안은 «한 번 답한 상태» 를 그린
            정지 화면이기 때문이다. 실제 비서는 대화가 쌓이고, 그것을 볼 곳이 없으면
            답을 받고도 어디로 갔는지 알 수 없다. */}
        {(turns.length > 0 || err) && (
          <div className="atlas-log">
            {turns.map((t, i) => (
              <div key={i} className={t.role === 'user' ? 'me' : 'it'}>
                {t.role === 'assistant' ? <ServerText text={t.text} /> : t.text}
              </div>
            ))}
            {busy && <div className="it">생각 중…</div>}
            {err && <div className="err">{err}</div>}
          </div>
        )}
      </div>

      <div className="atlas-input">
        {/* ⚠️⚠️ [2026-08-25 사용자 지적] 「Task ID 없이」 같은 **시스템 용어를 노출하지
            않는다.** 시안 문구를 그대로 옮긴 것인데, 사용자는 Task ID 가 무엇인지 알 필요가
            없다. 말하려던 사실(「특정 작업을 고르지 않아도 회사 전체를 물을 수 있다」)만
            사용자 말로 적는다. */}
        <label htmlFor="atlas-q">회사 전체에 대해 무엇이든 물어보십시오.</label>
        <div>
          <input id="atlas-q" value={input} disabled={busy}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') void send(input); }}
                 placeholder="예: 전력비가 15% 오르면 내년 손익은?" />
          <button type="button" aria-label="보내기" disabled={busy}
                  onClick={() => void send(input)}>↑</button>
        </div>
      </div>
    </>
  );
}
