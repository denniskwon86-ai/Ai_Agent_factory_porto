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
import { useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { useFactoryViewModel } from './factoryViewModel';
import { ProductionStageMap } from './ProductionStageMap';
import { WbsSpine } from './WbsSpine';

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

            <div className="canvas-pending">
              <h3>단계별 작업면은 다음 단계에서 연결합니다</h3>
              <p>
                지금 이 화면은 <b>전체 제작 단계</b>와 <b>WBS 실행 구조</b>를 실제 서버 상태로
                보여주는 병행 카나리입니다(구현 순서 2단계). 요구 확인·구현 실행 미리보기 등
                단계별 작업면은 3단계에서, 결정·Jarvis Dock 은 4단계, 근거·상태 Inspector 는
                5단계에서 붙습니다.
              </p>
              <p>
                기존 통제실은 그대로 있습니다 — Sprint 시작·정지·재개, HOTL 승인 같은 기능은
                아직 종전 화면에서만 할 수 있고, <b>기능 회귀가 없다고 확인된 뒤에</b> 옮깁니다.
              </p>
              {shownStage && (
                <p>
                  선택한 단계: <b>{shownStage.label}</b>
                  {selectedStageId && selectedStageId !== vm.currentStageId
                    && ' (실행 중인 단계와 다릅니다 — 보고 있을 뿐 진행이 옮겨간 것은 아닙니다)'}
                </p>
              )}
              {selectedWbsId && <p>선택한 작업: <b>{selectedWbsId}</b></p>}
            </div>
          </div>
        </section>
      </div>
      </div>
    </HubDialog>
  );
}
