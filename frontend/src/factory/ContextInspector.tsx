/**
 * [트랙 E · 5단계] ContextInspector — 근거·상태 오버레이.
 *
 * 근거: 구현 명세 §2.4 · §4(`TimelinePanel.tsx` → `ContextInspector`, «최근 이벤트·원인·전환을
 *       요청 시 표시»).
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.inspector`.
 *
 * ## 명세가 못 박은 네 가지
 *
 * 1. **기존 영구 우측 상태 열을 없앤다.** 그래서 이것은 «항상 보이는 열» 이 아니라 **요청 시
 *    열리는 오버레이**다.
 * 2. **`근거·상태` 또는 `의존관계 보기` 를 눌렀을 때 우측 오버레이로 연다.**
 * 3. **Canvas 너비를 영구 축소하지 않는다.** `position: absolute` + `transform` 으로 덮는다 —
 *    grid 열을 하나 더 만들면 닫혀 있을 때도 폭을 먹는다.
 * 4. **열고 닫아도 선택 문맥과 스크롤 위치를 유지한다.** 그래서 **언마운트하지 않는다** —
 *    `hidden` 이나 조건부 렌더로 지우면 스크롤이 맨 위로 돌아가고, 사용자는 보던 자리를 잃는다.
 *    `transform: translateX(102%)` 로 화면 밖에 두고 `aria-hidden` 으로 보조기기에서만 감춘다.
 *
 * ⚠️ **없는 근거를 만들지 않는다.** 명세는 «다음 자동 전환» 을 요구하지만 전환 **조건**은 서버
 *   로직이고 화면이 알 수 없다. 그래서 순서상 다음 단계(사실)만 말하고, 조건은 «서버가 판단한다»
 *   고 적는다. 그럴듯한 조건을 지어 쓰면 사용자는 그것을 계약으로 읽는다.
 */
import { stageStatusKo } from '../design/terms';

import type { FactoryStudioViewModel } from './factoryViewModel';

export interface ContextInspectorProps {
  vm: FactoryStudioViewModel;
  open: boolean;
  onClose: () => void;
  /** 지금 보고 있는 단계 — «현재 작업 이유» 를 이 단계 기준으로 말한다. */
  shownStageId: string;
  shownStageLabel: string;
}

/** 최근 이벤트 몇 개만 보여 준다. 전체 이력은 Inspector 의 일이 아니다(§2.4: «최근»). */
const RECENT = 12;

export function ContextInspector({
  vm, open, onClose, shownStageId, shownStageLabel,
}: ContextInspectorProps) {
  const { inspect } = vm;
  const shown = vm.stages.find((s) => s.id === shownStageId);
  const selectedTask = vm.selectedWbsId
    ? vm.wbs.find((t) => t.id === vm.selectedWbsId)
    : undefined;
  const events = vm.events.slice(0, RECENT);

  return (
    <aside
      className={`inspector${open ? ' open' : ''}`}
      aria-label="근거·상태 Inspector"
      // ⚠️ 언마운트하지 않으므로 닫힌 동안 보조기기에서 읽히지 않게 해야 한다. 그렇지 않으면
      //   스크린리더 사용자에게는 «닫아도 계속 읽히는 패널» 이 된다.
      aria-hidden={!open}
    >
      <header>
        <b>근거·상태</b>
        <button type="button" onClick={onClose} aria-label="Inspector 닫기">×</button>
      </header>

      <div className="inspector-body">
        {/* ① 현재 작업 이유 — 사실에서만 만든다. */}
        <article className="inspect-card">
          <h3>지금 무엇을 보고 있는가</h3>
          <p>
            <b>{shownStageLabel || '단계 미선택'}</b>
            {shown && ` — ${stageStatusKo(shown.status)}`}
            {shownStageId && shownStageId !== vm.currentStageId && (
              <> · 실행 중인 단계는 <b>{
                vm.stages.find((s) => s.id === vm.currentStageId)?.label || '없습니다'
              }</b>입니다</>
            )}
          </p>
          {selectedTask && (
            <p>
              선택한 작업 <b>{selectedTask.id}</b> {selectedTask.title}
              {selectedTask.agent && ` · 담당 ${selectedTask.agent}`}
            </p>
          )}
        </article>

        {/* ② 왜 막혀 있는가 — 「현재 작업 이유」를 사실로 말할 수 있는 유일한 근거다. */}
        <article className="inspect-card">
          <h3>무엇이 막고 있는가</h3>
          {inspect.blocked.length === 0 ? (
            <p>선행 조건으로 막힌 작업이 없습니다.</p>
          ) : (
            inspect.blocked.map((b) => (
              <div className="inspect-row" key={b.id}>
                <time>{b.id}</time>
                <span>
                  <b>{b.title}</b>
                  <small>{b.blockedBy.join(', ')} 완료 후 시작</small>
                </span>
              </div>
            ))
          )}
          {inspect.suspendedTaskId && (
            <p className="inspect-warn">
              <b>{inspect.suspendedTaskId}</b> 이(가) 쿼터 소진으로 동결됐습니다 — 쿼터가 회복되면
              마지막 체크포인트에서 재개합니다(처음부터 다시 하지 않습니다).
            </p>
          )}
        </article>

        {/* ③ 다음 자동 전환 — **순서만** 사실이다. 조건을 지어내지 않는다. */}
        <article className="inspect-card">
          <h3>다음 단계</h3>
          {inspect.nextStage ? (
            <p>
              순서상 다음은 <b>{inspect.nextStage.label}</b>입니다.
              <small>
                전환 조건(품질 게이트·승인 여부)은 서버가 판단합니다 — 이 화면은 순서만 알고
                있으므로 조건을 짐작해 적지 않습니다.
              </small>
            </p>
          ) : (
            <p>순서상 다음 단계가 없습니다(마지막 단계이거나 단계 구성을 읽지 못했습니다).</p>
          )}
        </article>

        {/* ④ 실패·복구 이력 — «없음» 과 «기록이 없음» 을 구분한다. */}
        <article className="inspect-card">
          <h3>실패·복구</h3>
          {inspect.failure ? (
            <>
              <p className="inspect-warn">
                <b>{inspect.failure.taskId}</b> 실패: {inspect.failure.error}
              </p>
              {inspect.failure.detail && <p><small>{inspect.failure.detail}</small></p>}
            </>
          ) : (
            <p>기록된 스프린트 실패가 없습니다.</p>
          )}
          <p>
            자가복구 재시도 <b>{inspect.healingRetries}회</b>
            <small>
              {inspect.healingRetries === 0
                ? '복구를 시도한 적이 없습니다 — 실패가 없었다는 뜻일 수도, 복구가 시작되지 않았다는 뜻일 수도 있습니다.'
                : '빌드 실패를 스스로 고쳐 본 횟수입니다.'}
            </small>
          </p>
        </article>

        {/* ⑤ 최근 Agent 이벤트. 비어 있으면 «아직 없다» 를 말한다(0으로 위장하지 않는다). */}
        <article className="inspect-card">
          <h3>최근 실행 기록</h3>
          {events.length === 0 ? (
            <p>
              아직 받은 이벤트가 없습니다.
              <small>
                {vm.connection === 'connected'
                  ? '연결은 되어 있습니다 — 실행이 시작되면 여기에 쌓입니다.'
                  : `실시간 연결이 ${vm.connection === 'reconnecting' ? '재연결 중' : '끊겼습니다'} — 그동안의 기록은 받지 못합니다.`}
              </small>
            </p>
          ) : (
            events.map((e, i) => (
              <div className="inspect-row" key={`${e.at}__${i}`}>
                <time>{e.at ? e.at.slice(11, 16) || e.at.slice(0, 5) : '—'}</time>
                <span>
                  <b>{e.actor || '시스템'}</b>
                  <small>{e.event}{e.reason ? ` · ${e.reason}` : ''}</small>
                </span>
              </div>
            ))
          )}
        </article>
      </div>
    </aside>
  );
}
