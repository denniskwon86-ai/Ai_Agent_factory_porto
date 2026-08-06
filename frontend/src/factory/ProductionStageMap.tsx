/**
 * [트랙 E · 2단계] Production Stage Map — 전체 제작 단계.
 *
 * 근거: 구현 명세 §2.1(상시 노출) · §4(`WorkflowStrip` → `ProductionStageMap`,
 *       «registry/실제 state 기반, 하드코딩 금지») · §8 신뢰성.
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.stage-map`.
 *
 * ## 이 컴포넌트가 지키는 것
 *
 * 1. **단계 목록을 스스로 만들지 않는다.** `factoryViewModel` 이 레지스트리·템플릿에서 파생한
 *    것을 그대로 그린다. 근거가 없으면(`stageSourceKnown === false`) **빈 지도를 그리지 않고
 *    그 사실을 문장으로 말한다** — 8칸이든 14칸이든 «우리가 믿는 흐름» 을 그려 놓으면 커스텀
 *    워크플로우에서 사용자가 있지도 않은 단계를 기다린다.
 * 2. **상태를 색으로만 말하지 않는다**(§6). 각 칸에 상태 낱말을 함께 넣고 `aria-label` 에도
 *    담는다. 색만 쓰면 색을 구분하지 못하는 사람에게는 «모두 같은 칸» 이다.
 * 3. **선택과 현재를 구분한다**(§5). 과거 단계를 눌러 봐도 실제 실행 단계 표시는 그대로다 —
 *    `aria-current="step"` 은 **선택**에, 진행 색은 **상태**에 붙는다.
 */
// 용어 사전은 `design/terms.ts` 하나다. Factory 전용 사전을 따로 두면 같은 상태가 두 문구로
// 나가고, 그때 어느 쪽이 정본인지 아무도 모른다.
import { stageStatusKo } from '../design/terms';

import type { FactoryStageVm, FactoryStudioViewModel } from './factoryViewModel';

export interface ProductionStageMapProps {
  vm: FactoryStudioViewModel;
  onSelectStage: (stageId: string) => void;
  /** 「의존관계 보기」 — 5단계에서 Inspector 로 연결한다. 없으면 버튼을 숨긴다. */
  onOpenDependencies?: () => void;
}

/** 사람이 읽을 요약 한 줄. **센 것만 말한다** — 모르는 것을 «0» 으로 채우지 않는다. */
function headline(vm: FactoryStudioViewModel): string {
  if (!vm.stageSourceKnown) return '단계 구성을 아직 읽지 못했습니다';
  const total = vm.stages.length;
  const done = vm.stages.filter((s) => s.status === 'completed').length;
  const cur = vm.stages.find((s) => s.id === vm.currentStageId);
  const tail = cur ? ` · 현재 ${cur.label}` : '';
  return `${total}단계 중 ${done}단계 완료${tail}`;
}

function stageLabel(s: FactoryStageVm, index: number): string {
  return `${String(index + 1).padStart(2, '0')} ${s.label}`;
}

/** 칸 안의 둘째 줄. 상태 낱말이 **항상** 들어가고, 요약이 있으면 뒤에 붙는다. */
function stageNote(s: FactoryStageVm): string {
  const ko = stageStatusKo(s.status);
  return s.summary ? `${ko} · ${s.summary}` : ko;
}

/** 담당 에이전트. **읽는 사람이 «누가 하는가» 를 알아야 한다** — 단계명만으로는 모른다.
 *  여러 명이면 모두 적는다(`EXECUTION` 은 백엔드·프론트엔드가 함께 쓴다). */
function stageWho(s: FactoryStageVm): string {
  return s.agents.filter(Boolean).join(' · ');
}

export function ProductionStageMap({ vm, onSelectStage, onOpenDependencies }: ProductionStageMapProps) {
  return (
    <section className="stage-map">
      <header className="stage-head">
        <b>전체 제작 단계</b>
        <span>{headline(vm)}</span>
        <div className="spacer" />
        {onOpenDependencies && (
          <button type="button" onClick={onOpenDependencies}>의존관계 보기</button>
        )}
      </header>

      {!vm.stageSourceKnown ? (
        // ⚠️ 여기서 기본 흐름을 그리면 «조회 실패» 가 «이런 단계들이 있다» 로 바뀐다(§8).
        <div className="studio-note" data-tone={vm.loadState === 'forbidden' ? 'forbidden' : 'loading'}>
          <b>단계 지도를 그릴 근거가 없습니다</b>
          <p>
            {vm.loadReason
              || '에이전트 레지스트리 또는 워크플로우 템플릿을 아직 읽지 못했습니다. '
                 + '읽히는 대로 실제 순서로 표시됩니다.'}
          </p>
        </div>
      ) : (
        <div className="stages" role="tablist" aria-label="전체 제작 단계">
          {vm.stages.map((s, i) => {
            const selected = vm.selectedStageId
              ? vm.selectedStageId === s.id
              : vm.currentStageId === s.id;
            return (
              <button
                key={`${s.id}__${i}`}
                type="button"
                role="tab"
                className="stage"
                data-status={s.status}
                aria-current={selected ? 'step' : undefined}
                aria-selected={selected}
                aria-label={
                  `${stageLabel(s, i)} — ${stageNote(s)}`
                  + (stageWho(s) ? ` · 담당 ${stageWho(s)}` : '')
                }
                title={stageWho(s) ? `담당: ${stageWho(s)}` : undefined}
                onClick={() => onSelectStage(s.id)}
              >
                <b>{stageLabel(s, i)}</b>
                <small>{stageNote(s)}</small>
                {/* 담당은 셋째 줄에 조용히 둔다 — 상태보다 덜 급하지만 «누가 하는가» 를
                    모르면 사용자가 물어볼 곳을 찾지 못한다. */}
                {stageWho(s) && <em>{stageWho(s)}</em>}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
