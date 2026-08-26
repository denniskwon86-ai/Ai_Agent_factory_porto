// [이관 6/10] 에이전트 통제소 — «누가 무엇을 어떤 순서로 하는가»
//
// 이 화면이 정하는 것: 에이전트의 역할·모델 등급·스킬·실행 순서, 그리고 **HOTL 중단점**
// (전문가가 반드시 확인하는 지점). 중단점을 지우면 사람 확인 없이 파이프라인이 끝까지 흐른다.
//
// ★★★ [2026-08-04 실측] 이 구성을 바꾸는 API 에 권한 검사가 **없었다.** 익명이
//   `PUT /factory/agents` 와 `POST /factory/agents/reset` 을 호출할 수 있었고, 초기화는
//   파일을 지워 **되돌릴 수 없었다.** 백엔드에 자격 검사와 백업을 넣었다(같은 커밋).
//
// ⚠️ 종전 구현에서 제거한 것:
//   · `alert()` 4곳 · `confirm()` 4곳 · `prompt()` 2곳 → 화면 안 안내·확인·입력
//     특히 새 템플릿 식별자를 `prompt()` 로 받고 있었다 — 형식 오류를 잡아 줄 자리가 없었다.
//   · 런처를 덮는 자체 전체화면 → `HubDialog`(모달 semantics·포커스 트랩·Escape·스크롤 잠금)
//   · 실패를 삼키던 store 액션 — 403 이어도 «템플릿 없음»으로 보였다.
//
// ★ 범위: **상세 편집 패널(`AgentFlow/AgentDetailSidebar`)은 그대로 재사용한다.** 12개 필드를
//   편집하는 231줄짜리이고, 다시 만들면 필드 누락 위험이 크다. 아직 다크 스타일이며 별도 단계로
//   옮긴다 — 여기서 «되던 것이 안 되는» 위험을 만들지 않는 편이 낫다.
import { useCallback, useEffect, useState } from 'react';
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, addEdge, applyEdgeChanges } from '@xyflow/react';
import type { Edge, Node, Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import AgentDetailSidebar from './AgentFlow/AgentDetailSidebar';
import AgentNode from './AgentFlow/AgentNode';
import {
  ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar, useConfirm,
  type FoundationRow,
} from '../design/DataFoundationShell';
import { Metric, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { deliverableTypeKo, modelTierKo, stageKo, DELIVERABLE_TYPE_KO } from '../design/terms';
import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';
import { useFactoryStore, API_BASE_URL } from '../store/useFactoryStore';

const nodeTypes = { agentNode: AgentNode };

/** [UI 설계서 §5.7] 하단 Simulation/Validation panel —
 *  **그래프 유효성 · 예상 호출 · 모델 가용성.**
 *
 * ## 왜 저장 전에 보여야 하는가
 *
 * 순환이 있는 그래프는 저장은 되지만 실행되지 않는다. 시작점이 없어도 마찬가지다. 실행하다
 * 실패하면 사용자는 「어느 에이전트가 문제인가」를 로그에서 찾아야 하는데, 이 화면은 그것을
 * **저장 전에** 알 수 있는 유일한 자리다.
 *
 * ## ⚠️ 모델 가용성은 지어내지 않는다
 *
 * 설계는 「모델 가용성」을 요구하지만 이 저장소에는 **공급자 연결 상태를 묻는 경로가 없다.**
 * 그래서 「티어별로 몇 개가 걸려 있는가」까지만 사실대로 적고, 실제 연결 여부는 **확인할 수
 * 없다고 말한다.** 초록 불을 켜 두면 사용자는 확인된 것으로 읽는다. */
function FlowValidationPanel({ agents, edges, hotlCount }: {
  agents: any[]; edges: any[]; hotlCount: number;
}) {
  const ids = new Set(agents.map((a) => a.id));
  //: 켜진 에이전트끼리의 연결만 센다 — 꺼진 노드로 가는 연결은 실행되지 않는다.
  const live = edges.filter((e) => ids.has(e.source) && ids.has(e.target));

  //: 순환 검출 — 위상 정렬로 다 빠지지 않으면 남은 것이 순환에 속한다.
  const indeg: Record<string, number> = {};
  const next: Record<string, string[]> = {};
  agents.forEach((a) => { indeg[a.id] = 0; next[a.id] = []; });
  live.forEach((e) => { next[e.source].push(e.target); indeg[e.target] += 1; });
  const queue = agents.filter((a) => indeg[a.id] === 0).map((a) => a.id);
  const order: string[] = [];
  while (queue.length) {
    const n = queue.shift()!;
    order.push(n);
    next[n].forEach((m) => { if (--indeg[m] === 0) queue.push(m); });
  }
  const cyclic = agents.length - order.length;

  const linked = new Set(live.flatMap((e) => [e.source, e.target]));
  //: 고립 노드 — 에이전트가 둘 이상일 때만 문제다. 하나뿐이면 이을 상대가 없다.
  const isolated = agents.length > 1 ? agents.filter((a) => !linked.has(a.id)) : [];
  const starts = agents.filter((a) => !live.some((e) => e.target === a.id));

  const tiers: Record<string, number> = {};
  agents.forEach((a) => {
    const t = a.model_tier || 'pro';
    tiers[t] = (tiers[t] || 0) + 1;
  });

  const problems: { title: string; detail: string }[] = [];
  if (agents.length === 0) {
    problems.push({ title: '켜진 에이전트가 없습니다',
      detail: '이 구성으로는 아무 것도 실행되지 않습니다.' });
  }
  if (cyclic > 0) {
    problems.push({ title: `연결이 순환합니다 (${cyclic}개 노드)`,
      detail: '순환이 있으면 실행 순서를 정할 수 없어 파이프라인이 시작되지 않습니다. '
        + '되돌아오는 연결을 끊으십시오.' });
  }
  if (agents.length > 0 && starts.length === 0) {
    problems.push({ title: '시작점이 없습니다',
      detail: '들어오는 연결이 없는 에이전트가 하나도 없습니다 — 어디서 시작할지 정할 수 없습니다.' });
  }
  if (isolated.length > 0) {
    problems.push({ title: `연결되지 않은 에이전트 ${isolated.length}개`,
      detail: `${isolated.map((a) => a.name_ko || a.id).join(', ')} — 켜져 있지만 흐름에 없어 `
        + '실행되지 않습니다.' });
  }

  return (
    <Panel kicker="VALIDATION" title="구성 점검 — 저장 전에 확인합니다"
      action={<span className={`state-chip ${problems.length ? 'danger' : 'success'}`}>
        {problems.length ? `문제 ${problems.length}건` : '실행 가능'}
      </span>}>
      <div style={{ padding: 15 }}>
        <div className="validation-facts">
          <div>
            <span>그래프 유효성</span>
            <b className={problems.length ? 'afs-danger-fg' : 'afs-success-fg'}>
              {problems.length ? '실행할 수 없습니다' : '이상 없음'}
            </b>
            <small>에이전트 {agents.length} · 연결 {live.length} · 시작점 {starts.length}</small>
          </div>
          <div>
            <span>예상 호출</span>
            <b>{agents.length}회</b>
            {/* ⚠️ 재시도·분기까지 세지 않는다 — 「최소」임을 밝힌다. 정확한 수처럼 적으면
                비용 예측이 어긋난다. */}
            <small>
              켜진 에이전트당 1회 기준의 <b>최소</b>값입니다. 재시도·분기는 포함하지 않았습니다.
              사람 확인 {hotlCount}곳에서 멈춥니다.
            </small>
          </div>
          <div>
            <span>모델 가용성</span>
            <b>{Object.entries(tiers).map(([t, n]) => `${t} ${n}`).join(' · ') || '없음'}</b>
            {/* ⚠️ 연결 여부를 묻는 경로가 없다 — 초록 불을 켜지 않는다. */}
            <small>
              티어별 배정 현황입니다. 공급자 연결이 실제로 살아 있는지 확인하는 경로가 아직
              없어, 이 화면은 <b>가용 여부를 보증하지 않습니다.</b>
            </small>
          </div>
        </div>

        {problems.length > 0 && (
          <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
            {problems.map((p) => (
              <Banner key={p.title} tone="error" title={p.title}>{p.detail}</Banner>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

type View = 'agents' | 'flow' | 'templates';

const MODULE: Record<View, { kicker: string; title: string; subtitle: string; desc: string }> = {
  agents: {
    kicker: 'AGENTS', title: '에이전트',
    subtitle: '각 단계를 누가 맡고 무엇을 근거로 일하는지.',
    desc: '모델 등급·스킬·역할을 정합니다. 끈 에이전트는 파이프라인에서 아예 빠집니다.',
  },
  flow: {
    kicker: 'FLOW', title: '실행 흐름',
    subtitle: '연결이 순서를 정합니다.',
    desc: '노드를 이으면 실행 순서가 다시 계산됩니다. 사람 확인 지점에서는 확인 없이 넘어가지 않습니다.',
  },
  templates: {
    kicker: 'TEMPLATES', title: '워크플로우 템플릿',
    subtitle: '여러 벌을 두고 프로젝트마다 고릅니다.',
    desc: '기존 템플릿은 바꾸지 않고 복사해서 새로 만듭니다 — 이미 생성된 프로젝트는 계속 동작합니다.',
  },
};

export default function AgentMasterPanel({ page = false, onClose }: {
  page?: boolean;
  onClose?: () => void;
} = {}) {
  const agentRegistry = useFactoryStore((s) => s.agentRegistry);
  const registryError = useFactoryStore((s) => s.agentRegistryError);
  const actionError = useFactoryStore((s) => s.agentActionError);
  const clearActionError = useFactoryStore((s) => s.clearAgentActionError);
  const fetchAgentRegistry = useFactoryStore((s) => s.fetchAgentRegistry);
  const resetAgentRegistry = useFactoryStore((s) => s.resetAgentRegistry);
  const restoreAgentRegistry = useFactoryStore((s) => s.restoreAgentRegistry);
  const closeAgentPanel = useFactoryStore((s) => s.closeAgentPanel);
  const close = onClose || closeAgentPanel;
  const templates = useFactoryStore((s) => s.templates);
  const editingTemplateId = useFactoryStore((s) => s.editingTemplateId);
  const selectEditingTemplate = useFactoryStore((s) => s.selectEditingTemplate);
  const saveTemplateRegistry = useFactoryStore((s) => s.saveTemplateRegistry);
  const copyTemplate = useFactoryStore((s) => s.copyTemplate);
  const deleteTemplate = useFactoryStore((s) => s.deleteTemplate);

  const [view, setView] = useState<View>('agents');
  const [draft, setDraft] = useState<any | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<ActingScope | null>(actingScope.peek());

  // 화면 안 입력 — `prompt()` 를 쓰지 않는다.
  const [copyForm, setCopyForm] = useState({ id: '', name: '' });
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [askAi, setAskAi] = useState(false);

  const delTpl = useConfirm<string>();
  const doReset = useConfirm<string>();
  const switchTpl = useConfirm<string>();
  const aiOverwrite = useConfirm<string>();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges] = useEdgesState<Edge>([]);

  const isDefault = editingTemplateId === 'default';
  const canEdit = Boolean(scope?.canManageStandard || scope?.unrestricted);

  useEffect(() => { actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE)); }, []);
  useEffect(() => actingScope.subscribe(setScope), []);

  // 레지스트리 로드 시 편집 사본 초기화
  // ⚠️ `null` 이면 편집 사본도 버린다. 남겨 두면 «못 읽었다» 는 배너와 **이전 사용자의 구성**이
  //   같은 화면에 함께 뜬다(실측). 권한 잔상은 통제를 무력해 보이게 만든다.
  useEffect(() => {
    if (agentRegistry) {
      setDraft(JSON.parse(JSON.stringify(agentRegistry)));
      setDirty(false);
      setSelectedAgentId(null);
    } else {
      setDraft(null);
      setDirty(false);
      setSelectedAgentId(null);
    }
  }, [agentRegistry]);

  // 사용자가 바뀌면 즉시 다시 읽는다 — 권한 범위가 다르다.
  useEffect(() => {
    const onUser = () => { fetchAgentRegistry(); };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [fetchAgentRegistry]);

  // draft가 변경될 때마다 React Flow 노드/엣지 초기화 동기화
  useEffect(() => {
    if (!draft || !draft.agents) return;
    const sortedAgents = [...draft.agents].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

    setNodes((nds) => {
      const itemsPerRow = Math.max(3, Math.floor(window.innerWidth / 300));
      return sortedAgents.map((agent, index) => {
        const existingNode = nds.find((n) => n.id === agent.id);
        const position = agent.position || (existingNode ? existingNode.position : {
          x: (index % itemsPerRow) * 280,
          y: 100 + Math.floor(index / itemsPerRow) * 160,
        });
        return {
          id: agent.id,
          type: 'agentNode',
          position,
          data: agent,
          selected: agent.id === selectedAgentId,
        };
      });
    });

    // 만약 draft.edges가 있으면 그걸 사용하고, 없으면 기존 order 기반으로 생성
    const currentEdges: Edge[] = draft.edges || [];
    if (currentEdges.length === 0 && sortedAgents.length > 1) {
      for (let i = 0; i < sortedAgents.length - 1; i++) {
        currentEdges.push({
          id: `e-${sortedAgents[i].id}-${sortedAgents[i + 1].id}`,
          source: sortedAgents[i].id,
          target: sortedAgents[i + 1].id,
          animated: true,
          style: { stroke: '#4b5563', strokeWidth: 2 },
        });
      }
    }
    setEdges(currentEdges);
  }, [draft?.agents?.length, draft?.edges, selectedAgentId, editingTemplateId]);

  const updateOrderFromEdges = (currentEdges: Edge[], agentList: any[]) => {
    const inDegree: Record<string, number> = {};
    const graph: Record<string, string[]> = {};
    agentList.forEach((a) => { inDegree[a.id] = 0; graph[a.id] = []; });

    currentEdges.forEach((e) => {
      if (graph[e.source] && inDegree[e.target] !== undefined) {
        graph[e.source].push(e.target);
        inDegree[e.target] += 1;
      }
    });

    const queue = agentList.filter((a) => inDegree[a.id] === 0).map((a) => a.id);
    let currentOrder = 1;
    const newOrderMap: Record<string, number> = {};

    while (queue.length > 0) {
      const node = queue.shift()!;
      newOrderMap[node] = currentOrder++;
      (graph[node] || []).forEach((neighbor) => {
        inDegree[neighbor] -= 1;
        if (inDegree[neighbor] === 0) queue.push(neighbor);
      });
    }

    agentList.forEach((a) => {
      if (!newOrderMap[a.id]) newOrderMap[a.id] = currentOrder++;
    });

    return newOrderMap;
  };

  const handleEdgesChange = useCallback(
    (changes: any) => {
      setEdges((eds) => {
        const nextEdges = applyEdgeChanges(changes, eds) as Edge[];
        setDraft((d: any) => {
          if (!d) return d;
          const newOrderMap = updateOrderFromEdges(nextEdges, d.agents);
          return {
            ...d,
            edges: nextEdges,
            agents: d.agents.map((a: any) => ({ ...a, order: newOrderMap[a.id] })),
          };
        });
        setDirty(true);
        return nextEdges;
      });
    },
    [setEdges],
  );

  const onConnect = useCallback(
    (params: Connection) => {
      const newEdge = { ...params, animated: true, style: { stroke: '#4b5563', strokeWidth: 2 } };
      setEdges((eds) => {
        const nextEdges = addEdge(newEdge, eds) as Edge[];
        setDraft((d: any) => {
          if (!d) return d;
          const newOrderMap = updateOrderFromEdges(nextEdges, d.agents);
          return {
            ...d,
            edges: nextEdges,
            agents: d.agents.map((a: any) => ({ ...a, order: newOrderMap[a.id] })),
          };
        });
        setDirty(true);
        return nextEdges;
      });
    },
    [setEdges],
  );

  // 노드 드래그 종료 시 위치만 저장 (순서는 엣지가 결정)
  const onNodeDragStop = useCallback((_event: any, node: any) => {
    setDraft((d: any) => {
      if (!d || !d.agents) return d;
      return {
        ...d,
        agents: d.agents.map((a: any) => (a.id === node.id ? { ...a, position: node.position } : a)),
      };
    });
    setDirty(true);
  }, []);

  const onNodeClick = useCallback((_event: any, node: any) => {
    setSelectedAgentId(node.id);
  }, []);

  const onPaneClick = useCallback(() => { setSelectedAgentId(null); }, []);

  // ── 파생 ────────────────────────────────────────────────────────────────
  const agents: any[] = draft?.agents || [];
  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || null;
  const enabledAgents = agents.filter((a) => a.enabled);
  const hotlCount = enabledAgents.filter((a) => a.hotl_after).length;
  const filteredAgents = (() => {
    const q = search.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter((a) => `${a.name_ko || ''} ${a.id} ${a.role || ''} ${a.stage || ''}`
      .toLowerCase().includes(q));
  })();

  /** 조회 상태 — «아직 안 왔다»·«못 가져왔다»·«정상»을 구분한다. */
  const listState: Loaded<any[]> = registryError
    ? { status: 'error', value: null, error: registryError }
    : draft ? { status: 'ok', value: agents } : { status: 'loading', value: null };
  const metricState = registryError ? 'error' : draft ? 'ok' : 'loading';

  const updateAgent = (id: string, key: string, value: any) => {
    setDraft((d: any) => ({
      ...d,
      agents: d.agents.map((a: any) => (a.id === id ? { ...a, [key]: value } : a)),
    }));
    setDirty(true);
  };

  const updateMeta = (key: string, value: any) => {
    setDraft((d: any) => ({ ...d, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true); setFlash(null); clearActionError();
    const ok = await saveTemplateRegistry(editingTemplateId, draft);
    setSaving(false);
    if (ok) {
      setDirty(false);
      setFlash(`템플릿 «${editingTemplateId}» 을 저장했습니다. `
        + '이 템플릿으로 새로 만드는 프로젝트부터 반영되고, 진행 중인 작업에는 영향이 없습니다.');
    }
  };

  const runGeneratePipeline = async () => {
    if (!aiPrompt.trim()) return;
    setAiBusy(true); setFlash(null); clearActionError();
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/ai-recommend/pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_request: aiPrompt }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.status === 'success') {
        setDraft(data.data);
        setDirty(true);
        setSelectedAgentId(null);
        setAiPrompt('');
        setAskAi(false);
        setFlash('구상안을 편집판에 올렸습니다 — 아직 저장되지 않았습니다. 확인 후 저장하십시오.');
      } else {
        // ⚠️ 실패를 `alert` 로 띄우지 않는다. 화면 안 배너로 남겨야 다시 읽을 수 있다.
        useFactoryStore.setState({
          agentActionError: res.status === 403
            ? '구상 기능을 쓸 권한이 없습니다 — 우측 상단에서 사용자를 지정하십시오.'
            : String(data?.detail || `구상에 실패했습니다(서버 ${res.status}).`),
        });
      }
    } catch (e: any) {
      useFactoryStore.setState({ agentActionError: `구상 중 오류: ${e?.message || e}` });
    } finally { setAiBusy(false); }
  };

  const railItems: RailItem[] = [
    { id: 'agents', label: '에이전트', hint: '역할·모델·스킬', icon: 'people' },
    { id: 'flow', label: '실행 흐름', hint: '연결이 순서다', icon: 'flow',
      // 사람 확인 지점은 통제다 — 몇 곳인지 항상 보여야 한다.
      count: hotlCount || undefined, countLabel: `사람 확인 지점 ${hotlCount}곳` },
    { id: 'templates', label: '워크플로우 템플릿', hint: '복사해서 만든다', icon: 'apps' },
  ];

  const jarvisContext = {
    current_module: `agent_master/${view}`,
    selected_object_type: 'agent',
    selected_object_id: selectedAgent?.id || '',
    object_snapshot: selectedAgent
      ? { id: selectedAgent.id, stage: selectedAgent.stage, enabled: selectedAgent.enabled,
        hotl_after: selectedAgent.hotl_after, model_tier: selectedAgent.model_tier }
      : { template: editingTemplateId, agents: agents.length, hotl: hotlCount },
    available_actions: canEdit
      ? ['역할 수정', '모델 등급 변경', '사람 확인 지점 설정', '템플릿 복사']
      : [],
    evidence_refs: [],
  };

  const agentRows: FoundationRow[] = filteredAgents.map((a) => ({
    id: a.id,
    title: a.name_ko || a.id,
    // ⚠️ `stage` 와 `model_tier` 는 내부 코드다(`CLARIFICATION` · `pro`). 사전을 거친다 —
    //   6/10 실측에서 그대로 노출됐다. `a.id` 는 로그·리포트의 실제 식별자이므로 그대로 둔다.
    meta: `${a.id}${a.stage ? ` · ${stageKo(a.stage)}` : ''}`
      + `${a.model_tier ? ` · ${modelTierKo(a.model_tier)}` : ''}`
      + ` · 순서 ${a.order ?? '미지정'}`,
    // ⚠️ 꺼진 에이전트를 조용히 두지 않는다 — 파이프라인에서 아예 빠진다.
    chip: !a.enabled
      ? { label: '꺼짐', tone: 'muted' }
      : a.hotl_after
        ? { label: '사람 확인', tone: 'warn' }
        : { label: '자동', tone: 'data' },
  }));

  const templateRows: FoundationRow[] = templates.map((t: any) => ({
    id: t.id,
    title: t.name || t.id,
    meta: `${t.id}${t.builtin ? ' · 기본 템플릿' : ' · 사용자 템플릿'}`,
    chip: t.id === editingTemplateId
      ? { label: '편집 중', tone: 'success' }
      : t.builtin ? { label: '기본', tone: 'data' } : { label: '사용자', tone: 'muted' },
  }));

  const askSwitch = (tid: string) => {
    if (tid === editingTemplateId) return;
    // 저장하지 않은 변경이 있으면 화면 안에서 확인한다(`confirm()` 을 쓰지 않는다).
    if (dirty) { switchTpl.ask(tid); return; }
    selectEditingTemplate(tid);
  };

  const hub = (
        <HubShell layoutClassName={page ? 'product-page-shell' : ''}
          kicker={MODULE[view].kicker} title={MODULE[view].title} subtitle={MODULE[view].subtitle}
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>HOTL</span>
              <b>사람 확인 지점은 통제입니다</b>
              <p>지우면 전문가 확인 없이 파이프라인이 끝까지 흐릅니다. 변경은 서버 재시작 후 반영됩니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextTitle={selectedAgent ? (selectedAgent.name_ko || selectedAgent.id)
              : registryError ? '조회 불가' : MODULE[view].title}
            contextDescription={selectedAgent
              ? `${selectedAgent.id} · ${selectedAgent.stage ? stageKo(selectedAgent.stage) + ' · ' : ''}순서 ${selectedAgent.order ?? '미지정'}`
                + `${selectedAgent.hotl_after ? ' · 사람 확인 지점' : ''}`
              : registryError
                ? '에이전트 구성을 가져오지 못했습니다 — «구성 없음»이 아닙니다.'
                : `템플릿 «${editingTemplateId}» · 에이전트 ${agents.length}개 · 사람 확인 ${hotlCount}곳`}
            context={jarvisContext}
            evidence={selectedAgent ? [
              { label: '에이전트', value: selectedAgent.id },
              { label: '모델 등급', value: selectedAgent.model_tier ? modelTierKo(selectedAgent.model_tier) : '미지정' },
              { label: '사람 확인', value: selectedAgent.hotl_after ? '있음' : '없음' },
            ] : []}
            quickQuestions={[
              '이 에이전트는 무엇을 근거로 판단합니까?',
              '사람 확인 지점을 지우면 무엇이 달라집니까?',
              '이 순서를 바꾸면 어디에 영향이 갑니까?',
            ]} />}
        >
          <div className={page ? 'product-page-content product-hub-page agent-master-page' : undefined}>
          {/* ★★ 조회 실패와 «구성 없음»을 구분한다. 없다고 믿으면 사용자는 처음부터 다시 만든다. */}
          {registryError && (
            <Banner tone="error" title="에이전트 구성을 가져오지 못했습니다">
              {registryError} — 구성이 <b>없는 것이 아니라</b> 읽지 못한 것입니다.{' '}
              <button className="text-button" onClick={() => fetchAgentRegistry()}>다시 시도</button>
            </Banner>
          )}
          {actionError && (
            <Banner tone="error" title="요청을 처리하지 못했습니다">
              {actionError}{' '}
              <button className="text-button" onClick={clearActionError}>지우기</button>
            </Banner>
          )}
          {flash && <Banner tone="info">{flash}</Banner>}
          {!canEdit && !registryError && (
            <Banner tone="warn" title="조회만 가능합니다">
              에이전트 구성을 바꿀 권한이 없습니다. 이 구성은 모든 산출물이 만들어지는 방식을
              정하므로 데이터 관리자·관리자만 편집할 수 있습니다.
            </Banner>
          )}

          <ScreenHead kicker={MODULE[view].kicker} title={MODULE[view].title}
            description={MODULE[view].desc}
            chip={registryError ? { label: '조회 불가', tone: 'danger' }
              : !draft ? { label: '확인 중', tone: 'muted' }
                : { label: `에이전트 ${agents.length}개`, tone: 'data' }} />

          {page && (
            <div className="agent-page-actions" aria-label="에이전트 구성 저장 상태">
              <div>
                <small>CONFIGURATION</small>
                <b>{dirty ? '저장하지 않은 변경이 있습니다' : '현재 구성이 저장되어 있습니다'}</b>
              </div>
              <div>
                {saving && <span className="busy">저장 중…</span>}
                {canEdit && (
                  <button className="primary-button" disabled={!dirty || saving} onClick={handleSave}>
                    변경사항 저장
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="metric-row">
            <Metric label="에이전트" state={metricState} value={draft ? agents.length : null}
              notes={{ error: '조회 불가', loading: '확인 중' }} hint="이 템플릿의 구성" />
            <Metric label="켜진 에이전트" state={metricState}
              value={draft ? enabledAgents.length : null}
              notes={{ error: '조회 불가', loading: '확인 중' }}
              hint={draft && enabledAgents.length < agents.length
                ? `${agents.length - enabledAgents.length}개는 빠집니다` : '전부 참여'} />
            {/* ⚠️ 0 을 숨기지 않는다. 사람 확인 지점 0곳은 «통제 없음»이라는 중요한 사실이다. */}
            <Metric label="사람 확인 지점" state={metricState} value={draft ? hotlCount : null}
              notes={{ error: '조회 불가', loading: '확인 중' }}
              hint={draft && hotlCount === 0 ? '확인 없이 끝까지 흐릅니다' : '전문가 개입'} />
            <Metric label="최종 산출물" state={metricState}
              value={draft ? deliverableTypeKo(draft.deliverable_type || 'software_app') : null}
              notes={{ error: '조회 불가', loading: '확인 중', empty: '미지정' }} />
          </div>

          {view === 'agents' && (
            <>
              <FoundationToolbar search={search} onSearch={setSearch}
                placeholder="이름·식별자·역할로 찾기"
                hint={canEdit
                  ? '고른 에이전트의 역할·모델·스킬을 오른쪽에서 편집합니다. 저장 전까지 반영되지 않습니다.'
                  : undefined} />
              <div className="inbox-layout agent-master-detail-layout">
                <FoundationList state={listState} rows={agentRows}
                  selectedId={selectedAgentId || ''} onSelect={setSelectedAgentId}
                  onRetry={() => fetchAgentRegistry()}
                  kicker="AGENTS" title="에이전트"
                  emptyText={search
                    ? <>«{search}» 와 일치하는 에이전트가 없습니다.</>
                    : <>이 템플릿에 에이전트가 없습니다.</>} />

                <Panel kicker="AGENT"
                  title={selectedAgent ? (selectedAgent.name_ko || selectedAgent.id) : '에이전트 상세'}>
                  {!selectedAgent ? (
                    <div className="empty-note">왼쪽에서 에이전트를 선택하십시오.</div>
                  ) : (
                    <>
                      <div style={{ padding: '0 14px' }}>
                        <EvidenceStrip items={[
                          { label: '식별자', value: selectedAgent.id },
                          { label: '모델 등급', value: selectedAgent.model_tier ? modelTierKo(selectedAgent.model_tier) : '미지정' },
                          { label: '사람 확인', value: selectedAgent.hotl_after ? '있음' : '없음' },
                        ]} note="식별자는 로그·리포트에 같은 문자열로 남습니다 — 바꾸지 않습니다." />
                      </div>
                      {/* ★ 상세 편집은 기존 패널을 그대로 재사용한다(12개 필드). 아직 다크
                          스타일이며 별도 단계로 옮긴다 — 다시 만들면 필드 누락 위험이 크다. */}
                      <div style={{ marginTop: 12 }}>
                        <AgentDetailSidebar
                          agent={selectedAgent}
                          updateAgent={canEdit ? updateAgent : () => { /* 조회 전용 */ }}
                          onClose={() => setSelectedAgentId(null)} />
                      </div>
                    </>
                  )}
                </Panel>
              </div>
            </>
          )}

          {view === 'flow' && (
            <>
              <FoundationToolbar
                actions={canEdit ? (
                  <>
                    <button className="secondary-button" disabled={aiBusy}
                      onClick={() => (dirty ? aiOverwrite.ask('ai') : setAskAi(true))}>
                      구상안 만들기
                    </button>
                    {isDefault && (
                      <button className="danger-ghost" onClick={() => doReset.ask('default')}>
                        기본값으로 초기화
                      </button>
                    )}
                  </>
                ) : undefined}
                hint={canEdit
                  ? '노드를 이으면 순서가 다시 계산됩니다. 저장 전까지 반영되지 않습니다.'
                  : undefined} />

              <ConfirmInline open={doReset.open}
                title="기본값으로 초기화합니다"
                body={<>편집해 둔 구성(역할·모델·순서·<b>사람 확인 지점</b>)이 사라집니다.
                  직전 구성은 서버에 보존되므로 한 번은 되돌릴 수 있습니다.</>}
                confirmLabel="초기화"
                onConfirm={() => doReset.run(() => { resetAgentRegistry(); setDirty(false); })}
                onCancel={doReset.cancel} />

              <ConfirmInline open={aiOverwrite.open}
                title="저장하지 않은 변경이 사라집니다"
                body="구상안을 만들면 지금 편집판이 덮어써집니다. 먼저 저장하려면 취소하십시오."
                confirmLabel="계속" danger={false}
                onConfirm={() => aiOverwrite.run(() => setAskAi(true))}
                onCancel={aiOverwrite.cancel} />

              {askAi && (
                <Panel kicker="DRAFT" title="어떤 구성을 만들까요">
                  <div style={{ padding: 14 }}>
                    <FormField label="원하는 구성"
                      hint="구상안은 편집판에만 올라갑니다 — 저장하기 전까지 아무것도 바뀌지 않습니다.">
                      <textarea className="afs-textarea" rows={3} value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        placeholder="예: 제조 원가 분석을 위한 에이전트 구성을 만들어 주십시오" />
                    </FormField>
                    <div style={{ display: 'flex', gap: 7, justifyContent: 'flex-end' }}>
                      <button className="secondary-button" onClick={() => setAskAi(false)}>취소</button>
                      <button className="primary-button" disabled={aiBusy || !aiPrompt.trim()}
                        onClick={runGeneratePipeline}>
                        {aiBusy ? '구상 중…' : '구상안 만들기'}
                      </button>
                    </div>
                  </div>
                </Panel>
              )}

              <Panel kicker="FLOW" title="실행 흐름">
                {registryError ? (
                  <div className="empty-note">
                    흐름을 그릴 구성을 가져오지 못했습니다 — «구성 없음»이 아닙니다.
                  </div>
                ) : !draft ? (
                  <div className="empty-note">구성을 확인하고 있습니다…</div>
                ) : (
                  <div style={{ padding: 12 }}>
                    <div style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
                      <FormField label="파이프라인 이름">
                        <input className="afs-input" value={draft.pipeline_name || ''}
                          disabled={!canEdit}
                          onChange={(e) => updateMeta('pipeline_name', e.target.value)}
                          placeholder="예: 소프트웨어 개발 팩토리" />
                      </FormField>
                      <FormField label="설명">
                        <textarea className="afs-textarea" rows={2} value={draft.description || ''}
                          disabled={!canEdit}
                          onChange={(e) => updateMeta('description', e.target.value)} />
                      </FormField>
                      <FormField label="최종 산출물 유형"
                        hint="파이프라인이 마지막에 무엇을 내놓는지에 따라 검수 방식이 달라집니다.">
                        <select className="afs-select" disabled={!canEdit}
                          value={draft.deliverable_type || 'software_app'}
                          onChange={(e) => updateMeta('deliverable_type', e.target.value)}>
                          {Object.entries(DELIVERABLE_TYPE_KO).map(([k, v]) => (
                            <option key={k} value={k}>{v}</option>
                          ))}
                        </select>
                      </FormField>
                    </div>
                    {/* ReactFlow 캔버스는 종전 그대로다 — 그래프 편집 동작을 바꾸지 않는다. */}
                    <div style={{ height: 420, border: '1px solid var(--surface-border)',
                      borderRadius: 8, overflow: 'hidden', background: '#0f172a' }}>
                      <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={handleEdgesChange}
                        onConnect={onConnect}
                        onNodeDragStop={onNodeDragStop}
                        onNodeClick={onNodeClick}
                        onPaneClick={onPaneClick}
                        nodeTypes={nodeTypes}
                        nodesDraggable={canEdit}
                        nodesConnectable={canEdit}
                        fitView
                        fitViewOptions={{ padding: 0.2 }}
                        minZoom={0.2}
                      >
                        <Background color="#374151" gap={16} />
                        <Controls className="bg-gray-800 border-gray-700 fill-white" />
                      </ReactFlow>
                    </div>
                    <p className="hint-line">
                      노드를 끌어 배치하고 이으면 실행 순서가 다시 계산됩니다.
                      {hotlCount === 0
                        ? ' 지금 사람 확인 지점이 없어 확인 없이 끝까지 흐릅니다.'
                        : ` 사람 확인 지점 ${hotlCount}곳에서 멈춥니다.`}
                    </p>
                  </div>
                )}
              </Panel>

              {/* ★ [설계 §5.7] 「하단 Simulation/Validation panel: **그래프 유효성, 예상 호출,
                  모델 가용성**」 — 저장하기 전에 이 구성이 실제로 돌아가는지 본다. */}
              <FlowValidationPanel agents={enabledAgents} edges={edges} hotlCount={hotlCount} />
            </>
          )}

          {view === 'templates' && (
            <>
              <FoundationToolbar
                hint={canEdit
                  ? '기존 템플릿은 바꾸지 않습니다 — 복사해서 새로 만듭니다.'
                  : '조회만 가능합니다 — 템플릿 변경은 데이터 관리자에게 요청하십시오.'} />

              <ConfirmInline open={switchTpl.open}
                title="저장하지 않은 변경이 사라집니다"
                body="템플릿을 전환하면 지금 편집판의 변경이 사라집니다. 먼저 저장하려면 취소하십시오."
                confirmLabel="전환" danger={false}
                onConfirm={() => switchTpl.run((tid) => selectEditingTemplate(tid))}
                onCancel={switchTpl.cancel} />

              <ConfirmInline open={delTpl.open}
                title={`템플릿 «${delTpl.target || ''}» 을 삭제합니다`}
                body={<>되돌릴 수 없습니다. <b>이미 이 템플릿으로 생성된 프로젝트는 계속
                  동작합니다</b> — 앞으로 이 템플릿을 고를 수 없게 되는 것입니다.</>}
                confirmLabel="삭제"
                onConfirm={() => delTpl.run((tid) => deleteTemplate(tid))}
                onCancel={delTpl.cancel} />

              <div className="inbox-layout">
                <FoundationList
                  state={registryError
                    ? { status: 'error', value: null, error: registryError }
                    : { status: 'ok', value: templates }}
                  rows={templateRows} selectedId={editingTemplateId}
                  onSelect={askSwitch} onRetry={() => fetchAgentRegistry()}
                  kicker="TEMPLATES" title="워크플로우 템플릿"
                  emptyText={<>템플릿을 가져오지 못했거나 등록된 것이 없습니다 — 기본 템플릿으로
                    동작합니다.</>} />

                <Panel kicker="TEMPLATE" title="지금 편집 중">
                  <div style={{ padding: 14 }}>
                    <EvidenceStrip items={[
                      { label: '식별자', value: editingTemplateId },
                      { label: '구분', value: isDefault ? '기본 템플릿' : '사용자 템플릿' },
                      { label: '에이전트', value: `${agents.length}개` },
                    ]} note={isDefault
                      ? '기본 템플릿은 모든 신규 프로젝트의 출발점입니다.'
                      : '이 템플릿을 고른 프로젝트에만 적용됩니다.'} />

                    {canEdit ? (
                      <>
                        <div style={{ marginTop: 14 }}>
                          <FormField label="새 템플릿 식별자" required
                            hint="영문·숫자·_- 만. 프로젝트 기록에 남으므로 나중에 바꾸기 어렵습니다.">
                            <input className="afs-input" value={copyForm.id}
                              onChange={(e) => setCopyForm({ ...copyForm, id: e.target.value })}
                              placeholder="예: cost_analysis" />
                          </FormField>
                          <FormField label="표시 이름">
                            <input className="afs-input" value={copyForm.name}
                              onChange={(e) => setCopyForm({ ...copyForm, name: e.target.value })}
                              placeholder="예: 원가 분석 파이프라인" />
                          </FormField>
                          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                            <button className="primary-button" disabled={!copyForm.id.trim()}
                              onClick={async () => {
                                const okDone = await copyTemplate(editingTemplateId,
                                  copyForm.id.trim(), copyForm.name.trim());
                                if (okDone) {
                                  setFlash(`템플릿 «${copyForm.id.trim()}» 을 만들었습니다 — `
                                    + '지금부터 이 템플릿을 편집합니다.');
                                  setCopyForm({ id: '', name: '' });
                                }
                              }}>복사해서 새로 만들기</button>
                            {!isDefault && (
                              <button className="danger-ghost"
                                onClick={() => delTpl.ask(editingTemplateId)}>
                                이 템플릿 삭제
                              </button>
                            )}
                          </div>
                        </div>
                        {isDefault && (
                          <p className="hint-line">
                            기본 템플릿은 삭제할 수 없습니다 — 모든 신규 프로젝트가 여기서 시작합니다.
                          </p>
                        )}
                        <div style={{ marginTop: 14, borderTop: '1px solid var(--surface-border)',
                          paddingTop: 12 }}>
                          <p className="hint-line" style={{ marginTop: 0 }}>
                            기본값으로 초기화한 적이 있으면 <b>직전 구성</b>으로 되돌릴 수 있습니다.
                          </p>
                          <button className="secondary-button" onClick={async () => {
                            const okDone = await restoreAgentRegistry();
                            if (okDone) { setDirty(false); setFlash('초기화 직전 구성으로 되돌렸습니다.'); }
                          }}>직전 구성으로 되돌리기</button>
                        </div>
                      </>
                    ) : (
                      <p className="hint-line">템플릿을 만들거나 삭제할 권한이 없습니다.</p>
                    )}
                  </div>
                </Panel>
              </div>
            </>
          )}
          </div>
        </HubShell>
  );

  if (page) return hub;
  return (
    <HubDialog label="에이전트 통제소 — 누가 무엇을 어떤 순서로 하는가" onClose={close}>
      <div className="afs-dialog-bar">
        <b>에이전트 통제소</b>
        <span>사람 확인 지점을 지우면 확인 없이 끝까지 흐릅니다</span>
        <div className="bar-actions">
          {dirty && <span className="busy">저장 안 됨</span>}
          {saving && <span className="busy">저장 중…</span>}
          {canEdit && (
            <button className="primary-button" disabled={!dirty || saving} onClick={handleSave}>
              저장
            </button>
          )}
          <button className="secondary-button" onClick={close}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>
      <div className="afs-dialog-body">{hub}</div>
    </HubDialog>
  );
}
