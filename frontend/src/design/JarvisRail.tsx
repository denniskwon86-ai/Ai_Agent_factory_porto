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

/** [UI 설계서 §7.2 답변 패턴] 답변은 여섯 단으로 읽힌다.
 *
 *   핵심 답변 / 왜 그렇게 판단했는가 / 근거와 기준시각 /
 *   부족하거나 확인하지 못한 데이터 / 선택 가능한 다음 행동 / 실행 시 영향과 승인 필요 여부
 *
 * 서버가 프롬프트로 이 형식을 요구하고, 여기서 머리말을 찾아 **구조로** 그린다.
 *
 * ## ⚠️ 형식을 못 지킨 답을 버리지 않는다
 *
 * LLM 은 형식을 어길 수 있다. 그때 화면이 비거나 오류를 내면 **비서가 준 답을 사용자가 못 보게
 * 된다** — 형식은 읽기 편하자고 있는 것이지 답을 검열하자고 있는 것이 아니다. 머리말을 하나도
 * 못 찾으면 평문 그대로 보여 준다.
 *
 * ## ⚠️ 「부족한 데이터」 를 강조한다
 *
 * 여섯 중 **④** 가 이 화면의 핵심이다. 모르는 것을 아는 것처럼 말하는 답변은 그럴듯할수록
 * 위험하다 — 이 저장소가 화면 전체에서 «조회 실패 ≠ 0건» 으로 지켜 온 규칙과 같은 것이다.
 */
const ANSWER_SECTIONS = [
  '핵심 답변',
  '왜 그렇게 판단했는가',
  '근거와 기준시각',
  '부족하거나 확인하지 못한 데이터',
  '선택 가능한 다음 행동',
  '실행 시 영향과 승인 필요 여부',
] as const;

function parseAnswer(text: string): { label: string; body: string }[] | null {
  //: `at` = 이 절이 시작하는 자리(앞 절의 끝을 정한다)
  //: `bodyAt` = **머리말과 콜론을 지난** 자리 — 본문은 여기서 시작한다.
  const found: { label: string; at: number; bodyAt: number }[] = [];
  for (const label of ANSWER_SECTIONS) {
    //: 머리말은 줄 첫머리에 오고 뒤에 `:` 가 붙는다(서버가 그렇게 요구한다).
    //: ⚠️ [2026-08-20 실측] 모델이 `**핵심 답변:**` 처럼 **마크다운 굵게**로 감싸 보낸다.
    //:   그것을 못 읽으면 파서가 통째로 실패하고 답이 평문 덩어리로 떨어진다 — 그러면 ④ 「부족한 데이터」를
    //:   강조하는 이 화면의 목적이 사라진다.
    //: ★ 형식 위반을 **오류로 만들지 않는다**(평문 폴백은 그대로다). 다만 흔한 장식은 받아 준다.
    const DECOR = '[*_#\\s]*';
    const m = new RegExp(`(^|\\n)${DECOR}${label}${DECOR}[:：]`).exec(text);
    if (!m) continue;
    //: ★★★ [2026-08-20 실측] 종전에는 `at + label.length` 를 본문 시작으로 썼다.
    //:   그런데 `at` 은 **머리말 앞 공백**을 가리킨다(`\s*` 를 건너뛰지 않았다).
    //:   그래서 본문이 머리말의 **마지막 글자부터** 시작했다 — 화면에 「가:」「각:」
    //:   「터:」 같은 조각이 붙어 나왔다. 답은 멀쩡한데 화면만 깨져 보였다.
    //: ⚠️ 매치 전체 길이를 쓰면 공백·콜론·전각콜론을 한 번에 지난다.
    found.push({
      label,
      at: m.index + (m[1] ? m[1].length : 0),
      bodyAt: m.index + m[0].length,
    });
  }
  //: 한두 개만 걸리면 형식을 지킨 것이 아니라 **우연히 그 낱말이 나온 것**일 수 있다.
  if (found.length < 3) return null;
  found.sort((a, b) => a.at - b.at);
  return found.map((f, i) => {
    const end = i + 1 < found.length ? found[i + 1].at : text.length;
    return {
      label: f.label,
      //: 남은 콜론·공백은 한 번 더 털어 낸다(모델이 「:」 를 두 번 쓰는 경우).
      body: text.slice(f.bodyAt, end).replace(/^\s*[:：]\s*/, '').trim(),
    };
  }).filter((x) => x.body);
}

function AnswerBody({ text }: { text: string }) {
  const parts = parseAnswer(text);
  if (!parts) return <p>{text}</p>;
  return (
    <div className="jarvis-answer">
      {parts.map((s) => (
        <section key={s.label}
          className={s.label === '부족하거나 확인하지 못한 데이터' ? 'gap' : undefined}>
          <h5>{s.label}</h5>
          <p>{s.body}</p>
        </section>
      ))}
    </div>
  );
}

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
  // 대화가 시작된 뒤의 «바로 물어보기» 한 줄 토글 상태.
  const [quickOpen, setQuickOpen] = useState(false);

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
      reportRequestFailure(e?.status);
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

      {/* ★★ [UIUX-AUDIT-33 §4] 대화가 시작되면 «바로 물어보기»를 한 줄로 접는다.
          감사 실측: 1280×720 오프라인 상태에서 로그 높이가 **24px** 밖에 남지 않았다.
          머리·문맥·근거·빠른 질문·오프라인 안내가 모두 고정 높이를 차지했기 때문이다.

          ★★ [2026-08-04 실측 결함] 대화가 **시작되기 전에는** 이 블록을 여기 두지 않는다.
          고정 블록으로 두면 그 아래 로그 영역이 250px 가까이 빈 채로 남았다 — 사용자에게는
          «비서가 아무것도 하지 않는 자리»로 보인다. 시작 전 추천 질문은 로그 안의 시작 상태로
          내려간다(아래 `jarvis-zero`). 그러면 빈 영역이 사라지고 질문도 그대로 보인다. */}
      {quickQuestions.length > 0 && turns.length > 0 && (
        <div className="jarvis-quick collapsed">
          <button type="button" className="jarvis-quick-toggle"
            aria-expanded={quickOpen}
            onClick={() => setQuickOpen((v) => !v)}>
            바로 물어보기 {quickQuestions.length}개 {quickOpen ? '접기' : '펼치기'}
          </button>
          {quickOpen && quickQuestions.map((q) => (
            <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>
          ))}
        </div>
      )}

      {/* 대화는 **이 레일 안에서** 유지된다(중앙 Banner 로 보내지 않는다). */}
      {/* `zero` 는 «아직 대화가 없다»는 뜻이다 — 그때만 시작 상태가 레일 높이를 채운다.
          대화가 시작되면 위에서부터 쌓여야 하므로(`align-content: start`) 클래스를 뗀다. */}
      <div className={`jarvis-log ${turns.length === 0 && !err ? 'zero' : ''}`}
        ref={logRef} aria-live="polite">
        {turns.length === 0 && !err && (
          /* 시작 상태 — 빈 채로 두지 않는다. 안내 · 지금 문맥 · 추천 질문을 함께 보여준다.
             ⚠️ 위 `jarvis-context` 가 «무엇을 보고 있는지»를 이미 말하므로 제목을 되풀이하지
               않는다. 여기서는 **비서가 실제로 무엇을 쓸 수 있는지**(객체·할 수 있는 일)를 말한다. */
          <div className="jarvis-zero">
            <p className="jarvis-zero-lead">
              무엇이든 물어보십시오. 지금 선택한 객체와 회사·조직 권한 범위를 문맥으로 씁니다 —
              별도로 ID 를 입력할 필요는 없습니다.
            </p>
            <dl className="jarvis-zero-ctx">
              {/* ⚠️ `current_module`(예: `collaboration/decisions`)은 **내부 식별자**다.
                  화면에 그대로 내보내면 사용자에게 뜻 없는 영문 슬러그가 보인다(실측에서 그랬다).
                  «무엇을 보고 있는가»는 위 `jarvis-context` 제목이 이미 한국어로 말한다. */}
              <div>
                <dt>선택한 객체</dt>
                {/* ⚠️ `selected_object_type`(`master_type` 등)도 내부 식별자다. 괄호로 붙여 놓으면
                    사용자에게 뜻 없는 영문이 하나 더 늘어난다. 식별자는 **id 하나**로 충분하다.
                    선택이 없다는 것은 숨기지 않는다 — 숨기면 사용자는 객체별 답을 기대한다. */}
                <dd>{context.selected_object_id
                  || '없음 — 목록에서 하나를 고르면 그 객체를 기준으로 답합니다'}</dd>
              </div>
              {!!context.available_actions?.length && (
                <div>
                  <dt>여기서 할 수 있는 일</dt>
                  <dd>{context.available_actions.join(' · ')}</dd>
                </div>
              )}
            </dl>
            {/* 낮은 화면에서도 감추지 않는다 — 이제 추천 질문은 **스크롤되는 로그 안**에 있어서
                다른 영역을 밀지 않는다. 종전에는 고정 블록이라 720px 에서 접어야 했다. */}
            {quickQuestions.length > 0 && (
              <div className="jarvis-zero-quick">
                <b>추천 질문</b>
                {quickQuestions.map((q) => (
                  <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>
                ))}
              </div>
            )}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={`${t.at}-${i}`} className={`jarvis-turn ${t.role}`}>
            <span>{t.role === 'user' ? '나' : 'Jarvis'}</span>
            {/* 사용자 발화는 그대로 — 형식은 **비서 답변**의 계약이다(§7.2). */}
            {t.role === 'user' ? <p>{t.text}</p> : <AnswerBody text={t.text} />}
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
        {/* ⚠️ [2026-08-23] 못 누르는 버튼에는 **사유**를 붙인다(설계 §8.6). 사유가 없으면
            사용자는 「고장」으로 읽는다 — 실제로 이 버튼은 조건이 명확한데 말하지 않았다. */}
        <button onClick={() => send(input)} disabled={busy || !input.trim()}
          title={busy ? '답변을 받는 중입니다 — 끝나면 다시 보낼 수 있습니다.'
            : !input.trim() ? '질문을 입력하면 보낼 수 있습니다.' : '질문을 보냅니다 (Enter)'}>
          보내기
        </button>
      </div>
    </aside>
  );
}
