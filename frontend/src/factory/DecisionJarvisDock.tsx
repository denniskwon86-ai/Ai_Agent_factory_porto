// 결정별 고정 차수 패널과 기존 Jarvis를 같은 작업면에 둔다.
import { useEffect, useRef, useState } from 'react';

import { jarvisApi, jarvisSession } from '../lib/jarvisApi';
import { StudioDecisionPanel } from './StudioDecisionPanel';
import { studioIdentityKey } from './studioInputMemory';
import { decisionError } from './studioDecisionApi';

import type { JarvisTurn } from '../lib/jarvisApi';
import { ASSISTANT_NAME } from '../lib/brand';
import type { ClarifySelections } from './clarifyAnswers';
import type { FactoryStudioViewModel } from './factoryViewModel';


export interface DecisionJarvisDockProps {
  vm: FactoryStudioViewModel;
  /** 요구 확인 Canvas 에서 고른 답. 제출은 여기서 하고 선택은 Canvas 에서 한다(§2.2/§2.3 분업). */
  selections: ClarifySelections;
  /** 지금 보고 있는 단계 — Jarvis 문맥에 싣는다. */
  shownStageId: string;
  shownStageLabel: string;
  /** 서버 GET으로 확인한 실제 HOTL 차수. 상위 질문 선택을 이 키로 분리한다. */
  onDecisionKeyChange?: (key: string) => void;
  onRestoreSelections?: (selections: ClarifySelections) => void;
}

export function DecisionJarvisDock({
  vm, selections, shownStageId, shownStageLabel, onDecisionKeyChange, onRestoreSelections,
}: DecisionJarvisDockProps) {
  const [turns, setTurns] = useState<JarvisTurn[]>(jarvisSession.turns());
  const [ask, setAsk] = useState('');
  const [askBusy, setAskBusy] = useState(false);
  const [askErr, setAskErr] = useState('');
  const [drawer, setDrawer] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const requestGeneration = useRef(0);
  const identity = studioIdentityKey();
  useEffect(() => {
    const invalidate = () => { requestGeneration.current += 1; };
    window.addEventListener('factory:session-changed', invalidate);
    window.addEventListener('factory:acting-user-changed', invalidate);
    window.addEventListener('factory:enterprise-context-changed', invalidate);
    return () => {
      invalidate();
      window.removeEventListener('factory:session-changed', invalidate);
      window.removeEventListener('factory:acting-user-changed', invalidate);
      window.removeEventListener('factory:enterprise-context-changed', invalidate);
    };
  }, [vm.project.id, identity]);

  useEffect(() => jarvisSession.subscribe(() => setTurns(jarvisSession.turns())), []);
  useEffect(() => {
    if (drawer) logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, drawer]);

  const decision = vm.decisions[0];
  /** Jarvis 질문 — 문맥을 **화면이** 싣는다. 사용자가 id 를 입력하지 않는다(§2.3). */
  const sendAsk = async (message: string) => {
    const m = message.trim();
    if (!m || askBusy) return;
    const version = requestGeneration.current;
    const stillCurrent = () => version === requestGeneration.current && identity === studioIdentityKey();
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
      if (!stillCurrent()) return;
      jarvisSession.push({
        role: 'assistant', text: r.reply || '(빈 응답)',
        at: new Date().toISOString(), objectId,
      });
    } catch (error) {
      if (!stillCurrent()) return;
      const e = decisionError(error);
      setAskErr(e.status === 401
        ? '사용자를 지정해야 비서가 답할 수 있습니다.'
        : `비서 응답을 받지 못했습니다: ${e?.message || e}`);
    } finally {
      if (stillCurrent()) { setAskBusy(false); setAsk(''); }
    }
  };

  return (
    <section className="interaction-dock">
      <StudioDecisionPanel key={`${vm.project.id}:${identity}`} vm={vm} selections={selections}
        onDecisionKeyChange={onDecisionKeyChange} onRestoreSelections={onRestoreSelections} />

      <article className="jarvis-dock">
        <div className="jarvis-head">
          <h3>✦ {ASSISTANT_NAME}</h3>
          <p>
            {shownStageLabel
              ? `«${shownStageLabel}» 문맥으로 답합니다`
              : '전체 제작 단계와 현재 작업을 함께 이해합니다'}
            {vm.selectedWbsId && ` · 선택 작업 ${vm.selectedWbsId}`}
          </p>
        </div>
        <input
          aria-label={`${ASSISTANT_NAME} 질문`}
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
                <b>{t.role === 'user' ? '나' : ASSISTANT_NAME}</b>
                <p>{t.text}</p>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}
