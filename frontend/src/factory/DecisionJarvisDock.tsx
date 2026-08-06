/**
 * [트랙 E · 4단계] Decision Dock + Jarvis Dock — 하단 Interaction Dock.
 *
 * 근거: 구현 명세 §2.3 · §4(`HOTLInput` → `DecisionDock`, Supervisor Chat → `JarvisDock`).
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.interaction-dock`.
 *
 * ## 명세가 못 박은 네 가지
 *
 * 1. **결정이 0건이면 Decision Dock 을 완전히 접고 높이를 Canvas 에 반환한다.** 빈 상자를
 *    남겨 두면 좁은 화면에서 실행 미리보기가 그만큼 줄어든다 — «결정 없음» 을 표시하는 데
 *    62px 를 쓸 이유가 없다.
 * 2. **Jarvis 는 하나만.** 그래서 기존 `lib/jarvisApi.ts` 의 `jarvisSession`(모듈 스코프 이력)을
 *    그대로 쓴다. 별도 이력을 만들면 화면을 옮길 때 대화가 끊기고, 사용자는 같은 질문을 다시 한다.
 * 3. **Task ID 를 요구하지 않는다.** 서버 계약이 `task_id_required: false` 이고, 문맥은 화면이
 *    자동으로 싣는다(회사·프로젝트·현재 단계·선택 작업).
 * 4. **결정 설명·미결정 영향·검토 행동을 같은 시야에 둔다.** «무엇을 결정하는가» 만 있으면
 *    사용자는 미루고, «안 하면 무엇이 멈추는가» 를 알아야 결정한다.
 *
 * ⚠️ 제출은 **실제 파이프라인을 재개한다**(`POST /{pid}/hotl/resume`). 기존 `HOTLInput` 과
 *   동일한 엔드포인트·동일한 직렬화(`factory/clarifyAnswers.ts`)를 쓴다 — 두 화면이 다르게
 *   보내면 백엔드가 한쪽 답변만 이해한다.
 */
import { useEffect, useRef, useState } from 'react';

import { jarvisApi, jarvisSession } from '../lib/jarvisApi';
import { useFactoryStore } from '../store/useFactoryStore';
import { serializeClarifyAnswers, unansweredCount } from './clarifyAnswers';

import type { JarvisTurn } from '../lib/jarvisApi';
import type { ClarifySelections } from './clarifyAnswers';
import type { FactoryStudioViewModel } from './factoryViewModel';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';

export interface DecisionJarvisDockProps {
  vm: FactoryStudioViewModel;
  /** 요구 확인 Canvas 에서 고른 답. 제출은 여기서 하고 선택은 Canvas 에서 한다(§2.2/§2.3 분업). */
  selections: ClarifySelections;
  /** 지금 보고 있는 단계 — Jarvis 문맥에 싣는다. */
  shownStageId: string;
  shownStageLabel: string;
}

export function DecisionJarvisDock({
  vm, selections, shownStageId, shownStageLabel,
}: DecisionJarvisDockProps) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');

  const [turns, setTurns] = useState<JarvisTurn[]>(jarvisSession.turns());
  const [ask, setAsk] = useState('');
  const [askBusy, setAskBusy] = useState(false);
  const [askErr, setAskErr] = useState('');
  const [drawer, setDrawer] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => jarvisSession.subscribe(() => setTurns(jarvisSession.turns())), []);
  useEffect(() => {
    if (drawer) logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, drawer]);

  const decision = vm.decisions[0];
  const isClarify = vm.clarify.awaiting;
  const left = isClarify ? unansweredCount(vm.clarify.questions, selections) : 0;

  /** 제출 — 기존 `HOTLInput` 과 **같은 경로·같은 형식**이다. */
  const submit = async () => {
    if (!decision || !vm.project.id || busy) return;
    setBusy(true); setErr(''); setOk('');
    try {
      const feedback = isClarify
        ? serializeClarifyAnswers(vm.clarify.questions, selections, note)
        : note.trim();
      const r = await fetch(
        `${API_BASE_URL}/api/v1/factory/${encodeURIComponent(vm.project.id)}/hotl/resume`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: decision.id, feedback }),
        });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail || `서버 응답 오류 (${r.status})`);
      }
      setNote('');
      setOk('제출했습니다 — 파이프라인이 이어서 진행합니다.');
      // 종전 화면과 **같은 방식**으로 store 를 맞춘다. 여기서 다르게 두면 두 화면의 상태 표시가
      // 갈라진다(한쪽은 «대기», 다른 쪽은 «가동 중»).
      useFactoryStore.setState((prev) => ({
        state: prev.state ? { ...prev.state, needs_revision: false } : null,
        hotlTaskId: null,
        activeSprintId: decision.id,
      }));
    } catch (e: any) {
      // 실패를 성공처럼 보이게 두지 않는다 — 무엇이 안 됐는지 그대로 적는다.
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  /** Jarvis 질문 — 문맥을 **화면이** 싣는다. 사용자가 id 를 입력하지 않는다(§2.3). */
  const sendAsk = async (message: string) => {
    const m = message.trim();
    if (!m || askBusy) return;
    setAskBusy(true); setAskErr('');
    const objectId = vm.selectedWbsId || shownStageId || vm.project.id;
    jarvisSession.push({ role: 'user', text: m, at: new Date().toISOString(), objectId });
    try {
      const r = await jarvisApi.ask(m, {
        current_module: 'factory/studio',
        selected_object_type: vm.selectedWbsId ? 'wbs_task' : 'production_stage',
        selected_object_id: objectId,
        // 화면이 **지금 보여 주고 있는 값**을 그대로 싣는다. 다른 값을 보내면 사용자는 A 를
        // 보면서 B 에 대한 답을 읽는다(서버 주석이 경고하는 그 상태).
        object_snapshot: {
          stage: shownStageLabel || shownStageId,
          stage_status: vm.stages.find((s) => s.id === shownStageId)?.status || '',
          current_stage: vm.currentStageId,
          wbs_total: vm.wbs.length,
          wbs_blocked: vm.wbs.filter((t) => t.blockedBy?.length).length,
          decisions_waiting: vm.decisions.length,
          app_runnable: vm.generated.runnable,
        },
        available_actions: [
          ...(decision ? ['결정 제출'] : []),
          ...(vm.generated.runnable ? ['생성 앱 실행 확인'] : []),
        ],
      }, vm.project.id);
      jarvisSession.push({
        role: 'assistant', text: r.reply || '(빈 응답)',
        at: new Date().toISOString(), objectId,
      });
    } catch (e: any) {
      setAskErr(e?.status === 401
        ? '사용자를 지정해야 비서가 답할 수 있습니다.'
        : `비서 응답을 받지 못했습니다: ${e?.message || e}`);
    } finally {
      setAskBusy(false); setAsk('');
    }
  };

  return (
    <section className="interaction-dock">
      {/* ① 결정이 있을 때만 렌더한다 — 0건이면 이 요소가 **아예 없다**(§2.3: 완전 접힘). */}
      {decision && (
        <article className="decision-dock">
          <header>
            <b>사용자 결정 대기</b>
            <span>{vm.decisions.length}건</span>
          </header>
          <div className="decision-body">
            <p>
              {isClarify
                ? '요구 확인 질문에 답해야 합니다.'
                : (decision.prompt || `«${shownStageLabel || decision.impact}» 단계의 산출물을 검토하고 승인해야 합니다.`)}
              {/* 미결정 영향 — «안 하면 무엇이 멈추는가». 이것이 없으면 사용자는 미룬다. */}
              <small>
                {isClarify
                  ? (left
                      ? `아직 고르지 않은 질문 ${left}개 — 비워 두면 추천안대로 진행합니다.`
                      : '모두 골랐습니다. 제출하면 RFP 초안 작성이 시작됩니다.')
                  : '제출하기 전까지 다음 단계가 시작되지 않습니다.'}
              </small>
            </p>
            <label className="decision-note">
              <span>추가 의견 (선택)</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={isClarify ? '고른 것 외에 덧붙일 내용' : '승인 조건이나 수정 요청'}
                disabled={busy}
              />
            </label>
          </div>
          <div className="decision-actions">
            <button type="button" onClick={submit} disabled={busy}>
              {busy ? '제출 중…' : isClarify ? '답변 제출하고 재개' : '승인하고 재개'}
            </button>
          </div>
          {/* 결과를 같은 자리에서 말한다. 사라지는 알림으로 두면 실패를 놓친다. */}
          {err && <p className="dock-error" role="alert">제출하지 못했습니다: {err}</p>}
          {ok && <p className="dock-ok">{ok}</p>}
        </article>
      )}

      <article className="jarvis-dock">
        <div className="jarvis-head">
          <h3>✦ Jarvis</h3>
          <p>
            {shownStageLabel
              ? `«${shownStageLabel}» 문맥으로 답합니다`
              : '전체 제작 단계와 현재 작업을 함께 이해합니다'}
            {vm.selectedWbsId && ` · 선택 작업 ${vm.selectedWbsId}`}
          </p>
        </div>
        <input
          aria-label="Jarvis 질문"
          value={ask}
          onChange={(e) => setAsk(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') sendAsk(ask); }}
          placeholder="지금 만드는 SW, 진행상황, 다음 결정에 대해 질문하세요"
          disabled={askBusy}
        />
        <div className="jarvis-actions">
          <button type="button" onClick={() => sendAsk(ask)} disabled={askBusy || !ask.trim()}>
            {askBusy ? '묻는 중…' : '질문하기'}
          </button>
          {/* 긴 대화는 Drawer 로 넓힌다(§2.3). Canvas 를 영구히 좁히지 않는다. */}
          <button type="button" className="quiet" onClick={() => setDrawer((v) => !v)}>
            {drawer ? '대화 접기' : `대화 보기${turns.length ? ` (${turns.length})` : ''}`}
          </button>
        </div>
        {askErr && <p className="dock-error" role="alert">{askErr}</p>}
      </article>

      {drawer && (
        <div className="jarvis-drawer" ref={logRef}>
          {turns.length === 0 ? (
            <p className="dock-empty">아직 주고받은 대화가 없습니다.</p>
          ) : (
            turns.map((t, i) => (
              <div className={`turn ${t.role}`} key={`${t.at}__${i}`}>
                <b>{t.role === 'user' ? '나' : 'Jarvis'}</b>
                <p>{t.text}</p>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}
