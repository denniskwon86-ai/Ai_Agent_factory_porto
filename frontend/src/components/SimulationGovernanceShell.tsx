import { useRef, useState, type ReactNode } from 'react';

import { HubShell, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';

type Kind = 'planning' | 'shadow';

const PLANNING_ITEMS: RailItem[] = [
  { id: 'scope', label: '1. 조직·기간', hint: '계획을 비교할 범위 선택', icon: 'orgtree' },
  { id: 'scenarios', label: '2. 시나리오', hint: '같은 기준선의 대안 선택', icon: 'revise' },
  { id: 'results', label: '3. 계획·실적 비교', hint: '차이·현금흐름·오차 확인', icon: 'decision' },
  { id: 'assurance', label: '4. 신뢰성 확인', hint: '승인·대사·결손 확인', icon: 'shield' },
];

const SHADOW_ITEMS: RailItem[] = [
  { id: 'summary', label: '1. 검증 현황', hint: '검토·채택·비교 불가 구분', icon: 'catalog' },
  { id: 'runs', label: '2. 비교 목록', hint: '병렬 실행 결과 선택', icon: 'apps' },
  { id: 'detail', label: '3. 차이 검토', hint: '개선·악화·미측정 확인', icon: 'checklist' },
  { id: 'promotion', label: '4. 제한 적용', hint: '범위와 악화를 확인한 뒤 승격', icon: 'deliver' },
];

const TARGET_KICKERS: Record<Kind, Record<string, string[]>> = {
  planning: {
    scope: ['SCOPE'], scenarios: ['SCENARIOS'],
    results: ['COMPARE', 'VARIANCE', 'CASH FLOW', 'BACKTEST'],
    assurance: ['APPROVAL', 'SCOPE'],
  },
  shadow: {
    summary: ['SUMMARY'], runs: ['RUNS'], detail: ['DETAIL'], promotion: ['DETAIL'],
  },
};

/**
 * 시뮬레이션 하위 업무도 제품의 공통 3열 문법을 쓴다.
 *
 * 기존 Planning/Shadow 본문은 대화상자와 독립 화면 양쪽에서 재사용하므로 여기서 바꾸지
 * 않는다. 전체 메뉴의 독립 화면만 역할 레일과 자비스를 더하고, 레일은 실제 본문의
 * kicker를 찾아 이동한다. 존재하지 않는 결과 구획을 지어내지 않고 현재 화면 맨 위에 남는다.
 */
export function SimulationGovernanceShell({ kind, children }: { kind: Kind; children: ReactNode }) {
  const items = kind === 'planning' ? PLANNING_ITEMS : SHADOW_ITEMS;
  const [active, setActive] = useState(items[0].id);
  const bodyRef = useRef<HTMLDivElement>(null);

  const select = (id: string) => {
    setActive(id);
    const wanted = TARGET_KICKERS[kind][id] || [];
    const panels = [...(bodyRef.current?.querySelectorAll<HTMLElement>('.panel') || [])];
    const target = panels.find((panel) => wanted.includes(
      panel.querySelector<HTMLElement>('.panel-head small')?.textContent?.trim() || '',
    ));
    (target || bodyRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const planning = kind === 'planning';
  const title = planning ? '경영계획' : 'Shadow Mode';
  const description = planning
    ? '같은 기준선에서 계획·실적·시나리오를 비교합니다.'
    : '새 규칙과 모델을 운영과 분리해 검증하고 승인된 범위에서만 적용합니다.';

  return (
    <HubShell layoutClassName={`product-page-shell ${kind}-product-shell`}
      kicker={planning ? 'PLANNING CONTROL' : 'CONTROLLED EXPERIMENT'}
      title={title} subtitle={description}
      items={items} activeId={active} onSelect={select}
      footer={<div className="inheritance-card">
        <span>{planning ? 'COMPARABLE' : 'FAIL-CLOSED'}</span>
        <b>{planning ? '같은 기준선만 비교합니다' : '승격 전 결과는 운영값이 아닙니다'}</b>
        <p>{planning
          ? '미입력·대사 실패·기준선 차이를 0이나 정상으로 표시하지 않습니다.'
          : '미측정과 비교 불가는 개선·악화와 분리하고 적용 범위를 다시 확인합니다.'}</p>
      </div>}
      jarvis={<JarvisRail
        contextTitle={planning ? '계획 · 실적 · 시나리오' : '병렬 검증 · 제한 적용'}
        contextDescription={`${description} 현재 선택한 단계와 회사·조직 권한 범위를 문맥으로 씁니다.`}
        context={{
          current_module: planning ? 'planning_control' : 'shadow_mode',
          selected_object_type: planning ? 'planning_workspace' : 'shadow_workspace',
          selected_object_id: active,
          object_snapshot: { stage: active },
          available_actions: planning
            ? ['비교 기준 설명', '결손 확인', '계획 대비 차이 점검']
            : ['비교 결과 설명', '악화 항목 점검', '승격 조건 확인'],
        }}
        evidence={[{ label: '현재 단계', value: items.find((item) => item.id === active)?.label || active }]}
        quickQuestions={planning ? [
          '지금 비교하는 기준선과 기간을 설명해 주세요.',
          '결손 또는 대사 실패가 있는 항목을 알려 주세요.',
          '계획 대비 실적 차이에서 먼저 볼 항목은 무엇입니까?',
        ] : [
          '현재 비교에서 개선·악화·미측정을 구분해 주세요.',
          '이 결과를 운영에 적용하기 전에 무엇을 확인해야 합니까?',
          '비교 불가인 항목은 왜 판정에서 제외됐습니까?',
        ]} />}
    >
      <div ref={bodyRef} className="simulation-governance-workspace">{children}</div>
    </HubShell>
  );
}
