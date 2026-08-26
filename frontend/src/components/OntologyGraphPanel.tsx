import { useMemo } from 'react';
import {
  Background, Controls, MarkerType, MiniMap, ReactFlow,
  type Edge, type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { OntologyObject, OntologyRelation } from '../lib/ontologyApi';

const objectKey = (ref: OntologyObject) => `${ref.namespace}:${ref.object_type}:${ref.object_id}`;

const NAMESPACE_COLOR: Record<string, string> = {
  dataset: '#bf1e2e',
  ecm: '#245789',
  mdm: '#866118',
  external: '#30756a',
  g4: '#7b4f96',
  decision: '#aa4f1f',
  knowledge: '#4f6478',
};

type Props = {
  relations: OntologyRelation[];
  selectedRelationId: string;
  selectedRoot: OntologyObject | null;
  onSelectRelation: (relationId: string) => void;
  onSelectRoot: (ref: OntologyObject) => void;
};

/** 현재 사용자가 실제로 조회한 관계만 그리는 읽기 전용 상관 그래프.
 *
 * 숨겨진 관계의 개수나 가상의 연결을 채우지 않는다. 노드 선택은 아래 영향 경로 조회의
 * 시작점 선택과 같은 상태를 사용하고, 간선 선택은 관계 상세 패널과 같은 상태를 사용한다.
 */
export function OntologyGraphPanel({ relations, selectedRelationId, selectedRoot,
  onSelectRelation, onSelectRoot }: Props) {
  const graph = useMemo(() => {
    const refs = new Map<string, OntologyObject>();
    const outgoing = new Map<string, string[]>();
    const indegree = new Map<string, number>();

    for (const relation of relations) {
      const source = objectKey(relation.subject);
      const target = objectKey(relation.object);
      refs.set(source, relation.subject); refs.set(target, relation.object);
      outgoing.set(source, [...(outgoing.get(source) || []), target]);
      indegree.set(source, indegree.get(source) || 0);
      indegree.set(target, (indegree.get(target) || 0) + 1);
    }

    // 승인 관계는 순환할 수 있으므로 Kahn 정렬 뒤 남은 노드는 마지막 층에 둔다.
    // 입력 순서가 달라도 같은 배치가 나오도록 모든 순서를 글자로 고정한다.
    const level = new Map<string, number>();
    const queue = [...refs.keys()].filter((key) => (indegree.get(key) || 0) === 0).sort();
    if (!queue.length && refs.size) queue.push([...refs.keys()].sort()[0]);
    while (queue.length) {
      const key = queue.shift()!;
      const current = level.get(key) || 0;
      for (const target of [...(outgoing.get(key) || [])].sort()) {
        level.set(target, Math.max(level.get(target) || 0, current + 1));
        const left = (indegree.get(target) || 0) - 1;
        indegree.set(target, left);
        if (left === 0) queue.push(target);
      }
      queue.sort();
    }
    const fallbackLevel = Math.max(0, ...level.values()) + 1;
    for (const key of refs.keys()) if (!level.has(key)) level.set(key, fallbackLevel);

    const byLevel = new Map<number, string[]>();
    for (const key of [...refs.keys()].sort()) {
      const l = level.get(key) || 0;
      byLevel.set(l, [...(byLevel.get(l) || []), key]);
    }

    const selectedRootKey = selectedRoot ? objectKey(selectedRoot) : '';
    const nodes: Node[] = [];
    for (const [l, keys] of [...byLevel.entries()].sort(([a], [b]) => a - b)) {
      keys.forEach((key, row) => {
        const ref = refs.get(key)!;
        const color = NAMESPACE_COLOR[ref.namespace] || '#526477';
        const selected = key === selectedRootKey;
        nodes.push({
          id: key,
          position: { x: l * 285, y: row * 116 },
          data: { ref, label: <div style={{ display: 'grid', gap: 2, textAlign: 'left' }}>
            <small style={{ color, fontWeight: 800 }}>{ref.namespace} · {ref.object_type}</small>
            <b style={{ color: '#172033', fontSize: 13 }}>{ref.object_id}</b>
          </div> },
          style: {
            width: 230, borderRadius: 9, padding: '10px 12px', background: '#fff',
            border: `${selected ? 3 : 1}px solid ${selected ? '#bf1e2e' : '#cfd7e2'}`,
            boxShadow: selected ? '0 0 0 3px rgba(191,30,46,.12)' : '0 4px 14px rgba(15,35,55,.08)',
          },
        });
      });
    }

    const edges: Edge[] = relations.map((relation) => {
      const selected = relation.relation_id === selectedRelationId;
      const approved = relation.approval_status === 'APPROVED';
      const color = selected ? '#bf1e2e' : approved ? '#2b607f' : '#8a96a6';
      return {
        id: relation.relation_id,
        source: objectKey(relation.subject), target: objectKey(relation.object),
        label: relation.relation_type_id,
        type: 'smoothstep',
        animated: relation.approval_status === 'IN_REVIEW',
        markerEnd: { type: MarkerType.ArrowClosed, color },
        style: { stroke: color, strokeWidth: selected ? 3 : 2,
          strokeDasharray: approved ? undefined : '7 5' },
        labelStyle: { fill: color, fontWeight: 800, fontSize: 11 },
        labelBgStyle: { fill: '#f7f9fc', fillOpacity: .94 },
        labelBgPadding: [5, 3] as [number, number],
        data: { relationId: relation.relation_id },
      };
    });
    return { nodes, edges };
  }, [relations, selectedRelationId, selectedRoot]);

  if (!relations.length) {
    return <div className="empty-note">현재 조회 조건에서 시각화할 관계가 없습니다. 관계를 지어내지 않고 빈 그래프로 둡니다.</div>;
  }

  return <div style={{ display: 'grid', gap: 9 }}>
    <div aria-label="업무 온톨로지 상관 그래프" style={{ height: 460, borderRadius: 10,
      border: '1px solid var(--surface-border)', overflow: 'hidden', background: '#f7f9fc' }}>
      <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView fitViewOptions={{ padding: .22 }}
        minZoom={.2} maxZoom={1.7} nodesDraggable={false} nodesConnectable={false}
        elementsSelectable onNodeClick={(_, node) => onSelectRoot(node.data.ref as OntologyObject)}
        onEdgeClick={(_, edge) => onSelectRelation(String(edge.data?.relationId || edge.id))}>
        <Background color="#d6dde7" gap={18} />
        <MiniMap pannable zoomable nodeColor={(node) => NAMESPACE_COLOR[
          (node.data.ref as OntologyObject).namespace] || '#526477'} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
    <div className="hint-line">노드를 선택하면 영향 경로 시작점이 되고, 간선을 선택하면 승인·근거 상세로 이동합니다.
      실선은 승인 관계, 점선은 승인 전·종료 관계입니다.</div>
  </div>;
}
