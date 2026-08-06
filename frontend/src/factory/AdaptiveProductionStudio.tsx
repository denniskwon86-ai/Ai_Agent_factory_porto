/**
 * [트랙 E · 2단계] Adaptive Production Studio 컨테이너 — **병행 카나리**.
 *
 * 근거: 구현 명세 §2(확정 공간 구조) · §7-2(«기존 화면과 병행 렌더») · §6(시각·접근성).
 * 시각 SSOT: `uiux-prototypes/sw-factory-concepts/adaptive-production-studio/index.html`.
 *
 * ## 지금 무엇이 들어 있고 무엇이 비어 있는가
 *
 * · 2단계 = **Production Stage Map + WBS Spine 을 실제 데이터로** 렌더한다.
 * · Adaptive Canvas(3단계)·Decision/Jarvis Dock(4단계)·Context Inspector(5단계)는 **아직
 *   없다.** 그 자리를 빈 흰 화면으로 두지 않고 «다음 단계에서 채운다» 고 적는다 — 검토하는
 *   사람이 빈 화면을 «망가졌다» 로 읽지 않게 한다.
 *
 * ## 왜 기존 화면을 지우지 않는가
 *
 * §7-7 이 «기능 회귀·시각 게이트 통과 후 기존 3패널 제거» 로 못 박았다. 그래서 이것은 기존
 * 통제실 위에 열리는 **오버레이**이고, 닫으면 종전 화면이 그대로 있다. 지금 3패널을 지우면
 * Sprint 시작·정지·재개·HOTL 승인 같은 기능이 신규 화면에 아직 없는 동안 사라진다.
 *
 * ⚠️ **선택 상태는 여기서만 갖는다.** `selectedStageId` 를 store 에 넣지 않는 이유는 §5 다 —
 *   선택은 화면을 보는 사람의 것이고, 실행 중인 단계(`currentStageId`)는 서버의 것이다. 둘을
 *   한 곳에 두면 «과거 단계를 눌렀는데 진행 표시가 옮겨가는» 일이 생긴다.
 */
import { useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { AdaptivePhaseCanvas } from './AdaptivePhaseCanvas';
import { defaultSelections, toggleSelection } from './clarifyAnswers';
import { DecisionJarvisDock } from './DecisionJarvisDock';
import { useFactoryViewModel } from './factoryViewModel';
import { ProductionStageMap } from './ProductionStageMap';
import { WbsSpine } from './WbsSpine';

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

export function AdaptiveProductionStudio({ onClose }: AdaptiveProductionStudioProps) {
  const [selectedStageId, setSelectedStageId] = useState('');
  const [selectedWbsId, setSelectedWbsId] = useState<string | undefined>(undefined);
  const vm = useFactoryViewModel({ selectedStageId, selectedWbsId });

  // [4단계] 요구 확인 선택 상태를 **여기서** 갖는다. Canvas 가 고르고 Dock 이 제출하므로
  // 둘의 공통 부모가 보관해야 한다(§2.2/§2.3 분업).
  const [selections, setSelections] = useState<ClarifySelections>({});
  // 질문이 도착·변경되면 추천안을 기본값으로 채운다. **라벨까지 확인해** 옛 선택을 버린다 —
  // 같은 id 로 질문이 재생성되면 남은 라벨이 어떤 옵션과도 맞지 않아 «선택 없음» 으로 나간다.
  const fingerprint = JSON.stringify(
    vm.clarify.questions.map((q) => [q.id, q.options.map((o) => o.label)]));
  useEffect(() => {
    if (!vm.clarify.questions.length) return;
    setSelections((prev) => defaultSelections(vm.clarify.questions, prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint]);

  const noteTitle = NOTE_TITLE[vm.loadState];
  // 선택이 없으면 «현재 단계를 본다»(§5) — 선택을 현재로 덮어쓰지 않고 표시만 그렇게 한다.
  const shownStage = vm.stages.find(
    (s) => s.id === (selectedStageId || vm.currentStageId),
  );

  return (
    // `HubDialog` 를 쓴다 — 이관 작업이 자체 `fixed inset-0` 모달을 이것으로 통일했고, Escape
    // 닫기·포커스 트랩·배경 inert·전체화면(100dvh)을 이미 준다. 여기서 다시 만들면 그 계약이
    // 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
    <HubDialog label="SW 제작 작업공간 (Adaptive Production Studio · 병행 카나리)" onClose={onClose}>
      <div className="afs-studio">
      <ProductionStageMap
        vm={vm}
        onSelectStage={(id) => setSelectedStageId((prev) => (prev === id ? '' : id))}
      />

      <div className="studio-grid">
        <WbsSpine vm={vm} onSelectTask={(id) => setSelectedWbsId((prev) => (prev === id ? undefined : id))} />

        <section className="adaptive-canvas">
          <nav className="canvas-toolbar">
            <b>{shownStage ? shownStage.label : '제작 작업면'}</b>
            <span>
              {vm.project.name || '프로젝트 미선택'}
              {vm.connection !== 'connected'
                && ` · ${vm.connection === 'reconnecting' ? '재연결 중' : '연결 끊김'}`}
            </span>
            <div className="spacer" />
            <button type="button" className="secondary-button" onClick={onClose}>
              종전 통제실로 (Esc)
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
              onToggleChoice={(qid, label, multi) => setSelections(
                (prev) => toggleSelection(prev, { id: qid, question: '', multi }, label))}
            />
          </div>

          {/* [4단계] 하단 Interaction Dock. **결정이 0건이면 Decision Dock 이 아예 렌더되지
              않는다**(§2.3 완전 접힘) — 그 높이는 Canvas 가 가져간다. */}
          <DecisionJarvisDock
            vm={vm}
            selections={selections}
            shownStageId={selectedStageId || vm.currentStageId}
            shownStageLabel={shownStage?.label || ''}
          />
        </section>
      </div>
      </div>
    </HubDialog>
  );
}
