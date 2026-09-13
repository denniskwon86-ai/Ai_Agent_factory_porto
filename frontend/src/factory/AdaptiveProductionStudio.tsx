/**
 * [B5] 공통 제작 내용 — 페이지와 오버레이가 같은 내용·store를 사용한다.
 *
 * 근거: 구현 명세 §2(확정 공간 구조) · §7-2(«기존 화면과 병행 렌더») · §6(시각·접근성).
 * 시각 SSOT: `uiux-prototypes/sw-factory-concepts/adaptive-production-studio/index.html`.
 *
 * ## 지금 무엇이 들어 있고 무엇이 비어 있는가
 *
 * · 단계·작업 목록·결과 캔버스·결정·근거 패널과 현재 대표 행동이 연결돼 있다.
 * · 전역 단일 진입·URL·SSE 연결은 B6이다. 브라우저 수용 전 기존 진입을 제거하지 않는다.
 *
 * ## 왜 기존 화면을 지우지 않는가
 *
 * §7-7 이 «기능 회귀·시각 게이트 통과 후 기존 3패널 제거» 로 못 박았다. 그래서 이것은 기존
 * 통제실의 오버레이 진입을 보존하고, B6에서 같은 StudioContent의 페이지 진입으로 통합한다.
 * 기존 유형별 기능과 진입·복귀의 동등 지원은 별도로 검증한다.
 *
 * ⚠️ **선택 상태는 여기서만 갖는다.** `selectedStageId` 를 store 에 넣지 않는 이유는 §5 다 —
 *   선택은 화면을 보는 사람의 것이고, 실행 중인 단계(`currentStageId`)는 서버의 것이다. 둘을
 *   한 곳에 두면 «과거 단계를 눌렀는데 진행 표시가 옮겨가는» 일이 생긴다.
 */
import { useEffect, useRef, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { AdaptivePhaseCanvas } from './AdaptivePhaseCanvas';
import { defaultSelections, toggleSelection } from './clarifyAnswers';
import { ContextInspector } from './ContextInspector';
import { DecisionJarvisDock } from './DecisionJarvisDock';
import { useFactoryViewModel } from './factoryViewModel';
import { ProductionStageMap } from './ProductionStageMap';
import { ProjectHeader } from './ProjectHeader';
// [7단계 전제] 실행 통제 — 시작·재개·복구·재분할·Release. §8 기능 게이트가 요구한다.
import { RunControls } from './RunControls';
import { WbsSpine } from './WbsSpine';
import { useFactoryStore } from '../store/useFactoryStore';
import { studioIdentityKey, studioInputKey, studioInputMemory } from './studioInputMemory';

import type { ClarifySelections } from './clarifyAnswers';

import './studio.css';

export interface AdaptiveProductionStudioProps {
  onClose: () => void;
}

/** 적재 상태 → 사람이 읽을 제목. `ready`·`empty` 는 본문이 스스로 말하므로 배너를 띄우지 않는다. */
const NOTE_TITLE: Record<string, string> = {
  loading: '아직 읽는 중입니다',
  forbidden: '권한이 없어 표시하지 않습니다',
  error: '읽지 못했습니다',
};

export function AdaptiveProductionStudio(props: AdaptiveProductionStudioProps) { return <StudioContainer {...props} dialog />; }

/** B6 페이지에서도 같은 내용을 마운트한다. 새 실행 store나 생성기를 만들지 않는다. */
export function StudioContent(props: AdaptiveProductionStudioProps) { return <StudioContainer {...props} />; }

function StudioContainer({ onClose, dialog = false }: AdaptiveProductionStudioProps & { dialog?: boolean }) {
  const projectId = useFactoryStore(s => s.currentProjectId);
  const [leaving, setLeaving] = useState(false);
  const leaveDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!leaving) return;
    const node = leaveDialog.current;
    node?.showModal();
    return () => node?.close();
  }, [leaving]);
  const requestClose = () => {
    if (projectId && studioInputMemory.hasInputs(projectId)) setLeaving(true);
    else onClose();
  };
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (projectId && studioInputMemory.hasInputs(projectId)) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [projectId]);
  const content = <>
    <StudioProjectContent key={projectId || 'empty'} onClose={requestClose} />
    {leaving && <dialog ref={leaveDialog} className="studio-leave-confirm" aria-labelledby="studio-leave-title"
      onKeyDown={event => event.stopPropagation()} onCancel={event => { event.preventDefault(); setLeaving(false); }}>
      <h2 id="studio-leave-title">작성 중인 입력을 어떻게 할까요?</h2>
      <p>목록으로 돌아가도 현재 로그인 세션의 입력은 유지됩니다. 새로고침 전에 서버에 보관하려면 편집 화면의 «입력 초안 저장»을 이용하세요.</p>
      {projectId && studioInputMemory.hasPending(projectId) && <p>결과 미확정 요청이 있어 입력 비우기는 잠겨 있습니다. 요청을 다시 보내지는 않습니다.</p>}
      <div className="run-form-actions">
        <button type="button" autoFocus onClick={() => setLeaving(false)}>계속 편집·저장하기</button>
        <button type="button" onClick={onClose}>입력 유지하고 돌아가기</button>
        <button type="button" disabled={!projectId || studioInputMemory.hasPending(projectId)} onClick={() => {
          if (projectId && studioInputMemory.clearProjectInputs(projectId)) onClose();
        }}>임시 입력 비우고 돌아가기</button>
      </div>
      <small>임시 입력 비우기는 서버 초안·승인 이력·결과물을 삭제하지 않습니다.</small>
    </dialog>}
  </>;
  return dialog ? <HubDialog label="업무 제작 작업공간" onClose={requestClose}>{content}</HubDialog> : content;
}

function StudioProjectContent({ onClose }: AdaptiveProductionStudioProps) {
  const [selectedStageId, setSelectedStageId] = useState('');
  const [selectedWbsId, setSelectedWbsId] = useState<string | undefined>(undefined);
  const vm = useFactoryViewModel({ selectedStageId, selectedWbsId });
  const [focusView, setFocusView] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [identity] = useState(studioIdentityKey);
  const [contextChanged, setContextChanged] = useState(false);
  const canvasRef = useRef<HTMLElement>(null);
  const decisionRef = useRef<HTMLDivElement>(null);
  const [decisionKey, setDecisionKey] = useState('');
  useEffect(() => {
    const changed = () => { if (identity !== studioIdentityKey()) setContextChanged(true); };
    window.addEventListener('factory:session-changed', changed);
    window.addEventListener('factory:acting-user-changed', changed);
    window.addEventListener('factory:enterprise-context-changed', changed);
    return () => {
      window.removeEventListener('factory:session-changed', changed);
      window.removeEventListener('factory:acting-user-changed', changed);
      window.removeEventListener('factory:enterprise-context-changed', changed);
    };
  }, [identity]);

  // [4단계] 요구 확인 선택 상태를 **여기서** 갖는다. Canvas 가 고르고 Dock 이 제출하므로
  // 둘의 공통 부모가 보관해야 한다(§2.2/§2.3 분업).
  const [selectionEdits, setSelectionEdits] = useState<{ key: string; value: ClarifySelections }>({ key: '', value: {} });
  // [5단계] Inspector 는 **오버레이**다. 열림 여부만 상태로 갖고, 컴포넌트는 언마운트하지
  // 않는다 — 지우면 스크롤 위치가 맨 위로 돌아간다(§2.4).
  const [inspectorOpen, setInspectorOpen] = useState(false);
  // 질문이 도착·변경되면 추천안을 기본값으로 채운다. **라벨까지 확인해** 옛 선택을 버린다 —
  // 같은 id 로 질문이 재생성되면 남은 라벨이 어떤 옵션과도 맞지 않아 «선택 없음» 으로 나간다.
  const fingerprint = JSON.stringify(
    vm.clarify.questions.map((q) => [q.id, q.options.map((o) => o.label)]));
  // 화면 선택은 사용자 입력에만 갱신한다. 새 차수는 같은 질문이어도 별도 기본값이다.
  const selectionKey = JSON.stringify([identity, vm.project.id, decisionKey, fingerprint]);
  const selections = defaultSelections(vm.clarify.questions, selectionEdits.key === selectionKey ? selectionEdits.value
    : decisionKey ? studioInputMemory.get<ClarifySelections>(studioInputKey(vm.project.id, 'clarification', decisionKey), {}) : {});
  const setSelections = (next: ClarifySelections | ((previous: ClarifySelections) => ClarifySelections)) =>
    setSelectionEdits({ key: selectionKey, value: typeof next === 'function' ? next(selections) : next });

  const noteTitle = NOTE_TITLE[vm.loadState];
  // 선택이 없으면 «현재 단계를 본다»(§5) — 선택을 현재로 덮어쓰지 않고 표시만 그렇게 한다.
  const shownStage = vm.stages.find(
    (s) => s.id === (selectedStageId || vm.currentStageId),
  );
  // 범용 보고서는 WBS를 만들지 않고 agent artifact를 직접 남긴다. 이때 빈 WBS 열을 고정하면
  // 읽을 본문만 좁아진다. 실제 문서가 있고 WBS가 없으면 넓은 읽기 모드를 기본으로 한다.
  const wideView = !showTasks || focusView;
  const reviewResult = () => {
    const result = vm.stages.find(s => ['EXECUTION', 'BUILD'].includes(s.id.toUpperCase()))
      || [...vm.stages].reverse().find(s => vm.docs[s.id.toUpperCase()]);
    if (result) setSelectedStageId(result.id);
    canvasRef.current?.focus();
  };

  if (contextChanged) return <section className="afs-studio studio-context-block">
    <h2>회사 또는 사용자가 바뀌었습니다</h2>
    <p>이전 문맥의 내용과 동작을 숨겼습니다. 목록에서 작업을 다시 열어 현재 권한을 확인하세요.</p>
    <button type="button" onClick={onClose}>작업 목록으로 돌아가기</button>
  </section>;

  return (
    // `HubDialog` 를 쓴다 — 이관 작업이 자체 `fixed inset-0` 모달을 이것으로 통일했고, Escape
    // 닫기·포커스 트랩·배경 inert·전체화면(100dvh)을 이미 준다. 여기서 다시 만들면 그 계약이
    // 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
      <div className={`afs-studio${focusView ? ' focus-canvas' : ''}`}>
      {/* [§2.1 상시 노출] Project Header — 7단계(3패널 제거)의 전제다. 이것 없이 3패널을
          지우면 사용자가 실행을 멈출 수 없다(§8 기능 게이트). */}
      <ProjectHeader
        vm={vm}
        onReviewResult={reviewResult}
      />
      {/* [§8 기능 게이트] 3패널을 지우려면 이 다섯 명령이 여기 있어야 한다 —
          없으면 사용자는 실행을 **시작할 수도, 멈춘 것을 재개할 수도** 없다. */}
      <RunControls vm={vm} onReviewResult={reviewResult}
        onReviewDecision={() => { decisionRef.current?.focus(); decisionRef.current?.scrollIntoView({ block: 'nearest' }); }}
        onShowTasks={() => setShowTasks(true)} />
      <ProductionStageMap
        vm={vm}
        onSelectStage={(id) => setSelectedStageId((prev) => (prev === id ? '' : id))}
        // [5단계] 「의존관계 보기」 — 명세 §2.4 가 지정한 두 입구 중 하나다.
        onOpenDependencies={() => setInspectorOpen(true)}
      />

      <div className={`studio-grid${wideView ? ' wide-canvas' : ''}`}>
        <WbsSpine vm={vm} onSelectTask={(id) => setSelectedWbsId((prev) => (prev === id ? undefined : id))} />

        <section className="adaptive-canvas" tabIndex={-1} ref={canvasRef} aria-label="제작 결과와 입력">
          <nav className="canvas-toolbar">
            <b>{shownStage ? shownStage.label : '제작 작업면'}</b>
            <span>
              {vm.project.name || '프로젝트 미선택'}
              {vm.connection !== 'connected'
                && ` · ${vm.connection === 'reconnecting' ? '재연결 중' : '연결 끊김'}`}
            </span>
            <div className="spacer" />
            <button type="button" className="inspector-btn"
              onClick={() => setFocusView((value) => !value)}
              aria-pressed={focusView}>
              {focusView ? '작업공간으로 돌아가기' : '결과물 전체 화면'}
            </button>
            <button type="button" className="inspector-btn"
              onClick={() => setShowTasks(value => !value)}
              disabled={focusView} aria-expanded={showTasks && !focusView}>
              {showTasks ? '작업 목록 접기' : `작업 목록${vm.wbs.length ? ` · ${vm.run.wbsDone}/${vm.wbs.length}` : ''}`}
            </button>
            {/* [5단계] 「근거·상태」 — §2.4 의 다른 입구. 영구 우측 열을 두지 않는 대신 이 버튼이
                오버레이를 연다. */}
            <button type="button" className="inspector-btn"
              onClick={() => setInspectorOpen((v) => !v)}
              aria-expanded={inspectorOpen}>
              근거·상태
            </button>
            <button type="button" className="secondary-button" onClick={onClose}>
              목록으로 돌아가기 · 닫기
            </button>
          </nav>

          <div className="canvas-body">
            {noteTitle && (
              <div className="studio-note" data-tone={vm.loadState}>
                <b>{noteTitle}</b>
                <p>{vm.loadReason || '사유가 기록되지 않았습니다.'}</p>
              </div>
            )}

            {/* [3단계] 선택과 현재가 다르면 **그 사실을 먼저 말한다.** 과거 단계의 작업면을
                보면서 «지금 이게 돌고 있나» 를 헷갈리면 안 된다(§5). */}
            {selectedStageId && selectedStageId !== vm.currentStageId && (
              <div className="studio-note" data-tone="empty">
                <b>지난 단계를 보고 있습니다</b>
                <p>
                  실행 중인 단계는 <b>{
                    vm.stages.find((s) => s.id === vm.currentStageId)?.label || '아직 없습니다'
                  }</b>입니다. 여기서 보는 것은 기록이며 진행이 옮겨간 것은 아닙니다.
                </p>
              </div>
            )}

            <AdaptivePhaseCanvas
              vm={vm}
              shownStageId={selectedStageId || vm.currentStageId}
              shownStageLabel={shownStage?.label || ''}
              selections={selections}
              onToggleChoice={(qid, label, multi) => setSelections(prev => {
                const next = toggleSelection(prev, { id: qid, question: '', multi }, label);
                if (decisionKey) studioInputMemory.set(studioInputKey(vm.project.id, 'clarification', decisionKey), next);
                return next;
              })}
            />
          </div>

          {/* [4단계] 하단 Interaction Dock. **결정이 0건이면 Decision Dock 이 아예 렌더되지
              않는다**(§2.3 완전 접힘) — 그 높이는 Canvas 가 가져간다. */}
          <div ref={decisionRef} tabIndex={-1} aria-label="검토할 내용">
          <DecisionJarvisDock
            vm={vm}
            selections={selections}
            shownStageId={selectedStageId || vm.currentStageId}
            shownStageLabel={shownStage?.label || ''}
            onDecisionKeyChange={setDecisionKey}
            onRestoreSelections={restored => {
              if (!decisionKey) return;
              setSelections(restored);
              studioInputMemory.set(studioInputKey(vm.project.id, 'clarification', decisionKey), restored);
            }}
          />
          </div>
        </section>

        {/* [5단계] Inspector 는 `studio-grid` 의 **자식이지만 grid 열이 아니다** —
            `position: absolute` 로 Canvas 를 덮는다. 열을 하나 더 만들면 닫혀 있을 때도
            폭을 먹고, 그것이 §2.4 가 없애라고 한 «영구 우측 상태 열» 이 된다. */}
        <ContextInspector
          vm={vm}
          open={inspectorOpen}
          onClose={() => setInspectorOpen(false)}
          shownStageId={selectedStageId || vm.currentStageId}
          shownStageLabel={shownStage?.label || ''}
        />
      </div>
      </div>
  );
}
