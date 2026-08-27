import { useEffect, useRef, useState, type ReactNode } from 'react';

import { HubShell, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';

type Kind = 'promotion' | 'workspace';

const PROMOTION_ITEMS: RailItem[] = [
  { id: 'candidate', label: '1. 후보 판', hint: '운영으로 올릴 결과 선택', icon: 'catalog' },
  { id: 'gate', label: '2. 사전 점검', hint: '계약·승인·데이터 준비도 확인', icon: 'checklist' },
  { id: 'decision', label: '3. 승격 결정', hint: '사유와 데이터 사용 여부 확정', icon: 'decision' },
];

const WORKSPACE_ITEMS: RailItem[] = [
  { id: 'inspect', label: '1. 릴리스 점검', hint: '대상 판과 소유 범위 선택', icon: 'search' },
  { id: 'gate', label: '2. 전사 승격 게이트', hint: '차단·확인 불가·통과 구분', icon: 'shield' },
  { id: 'operations', label: '3. 운영 준비', hint: '7단계 체크리스트와 롤백', icon: 'checklist' },
  { id: 'share', label: '4. 공유·복제', hint: '부서 공유와 계보 확인', icon: 'deliver' },
];

const TARGETS: Record<Kind, Record<string, string[]>> = {
  promotion: {
    candidate: ['올릴 후보 판'], gate: ['올리기 전 점검'], decision: ['올리기 전 점검'],
  },
  workspace: {
    inspect: ['INSPECT'], gate: ['GATE'], operations: ['OPERATIONS'], share: ['SHARE', 'FORKS'],
  },
};

/** 운영 전환·공유 화면의 공통 제품 문법. 실제 판정은 기존 서버/본문에만 둔다. */
export function OperationsGovernanceShell({ kind, children }: { kind: Kind; children: ReactNode }) {
  const items = kind === 'promotion' ? PROMOTION_ITEMS : WORKSPACE_ITEMS;
  const [active, setActive] = useState(items[0].id);
  const bodyRef = useRef<HTMLDivElement>(null);

  // 같은 셸 인스턴스가 promotion → workspace 전환에서 재사용된다. 초기화하지 않으면
  // 좌측 항목은 워크스페이스인데 자비스 문맥은 이전 화면의 candidate 로 남는다.
  useEffect(() => setActive(items[0].id), [kind]);

  const select = (id: string) => {
    setActive(id);
    const wanted = TARGETS[kind][id] || [];
    const candidates = [...(bodyRef.current?.querySelectorAll<HTMLElement>('.panel, h4') || [])];
    const target = candidates.find((node) => {
      const marker = node.matches('h4')
        ? node.textContent?.trim()
        : node.querySelector<HTMLElement>('.panel-head small')?.textContent?.trim()
          || node.querySelector<HTMLElement>('h4')?.textContent?.trim();
      return wanted.includes(marker || '');
    });
    (target || bodyRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const promotion = kind === 'promotion';
  const description = promotion
    ? '후보 판을 운영으로 올리기 전에 제품 게이트와 사람 결정을 확인합니다.'
    : '부서 공유·복제·전사 승격과 롤백을 하나의 계보에서 관리합니다.';

  return (
    <HubShell layoutClassName={`product-page-shell ${kind}-product-shell`}
      kicker={promotion ? 'RELEASE CONTROL' : 'OPERATING WORKSPACE'}
      title={promotion ? '운영 승격' : '워크스페이스'} subtitle={description}
      items={items} activeId={active} onSelect={select}
      footer={<div className="inheritance-card">
        <span>{promotion ? 'GATED' : 'TRACEABLE'}</span>
        <b>{promotion ? '검사를 통과해도 사람의 결정이 필요합니다' : '공유와 승격은 같은 행위가 아닙니다'}</b>
        <p>{promotion
          ? '화면은 서버 판정을 바꾸지 않고 차단 사유와 봉인 지문을 그대로 보여 줍니다.'
          : '확인 불가는 통과가 아니며 회수·롤백·반려는 사유와 확인을 남깁니다.'}</p>
      </div>}
      jarvis={<JarvisRail
        contextTitle={promotion ? '후보 판 운영 전환' : '공유 · 복제 · 전사 승격'}
        contextDescription={`${description} 현재 단계와 회사·조직 권한 범위를 문맥으로 씁니다.`}
        context={{
          current_module: promotion ? 'release_promotion' : 'department_workspace',
          selected_object_type: promotion ? 'release_candidate' : 'workspace_release',
          selected_object_id: active,
          object_snapshot: { stage: active },
          available_actions: promotion
            ? ['차단 사유 설명', '데이터 결속 확인', '승격 전 점검']
            : ['게이트 설명', '운영 준비 확인', '공유·복제 계보 점검'],
        }}
        evidence={[{ label: '현재 단계', value: items.find((item) => item.id === active)?.label || active }]}
        quickQuestions={promotion ? [
          '이 후보를 운영으로 올리지 못하게 막는 항목은 무엇입니까?',
          '승격 시 어떤 계약과 데이터 지문이 봉인됩니까?',
          '업무 데이터를 사용하지 않는다는 확인은 무엇을 뜻합니까?',
        ] : [
          '현재 릴리스의 전사 승격 게이트를 설명해 주세요.',
          '공유와 전사 승격의 차이는 무엇입니까?',
          '운영에서 내리기 전에 어떤 영향을 확인해야 합니까?',
        ]} />}
    >
      <div ref={bodyRef} className="operations-governance-workspace">{children}</div>
    </HubShell>
  );
}
