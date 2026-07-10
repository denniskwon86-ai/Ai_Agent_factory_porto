import { useEffect, useState, useCallback } from "react";
import { useFactoryStore, API_BASE_URL } from "../store/useFactoryStore";
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, addEdge, applyEdgeChanges } from "@xyflow/react";
import type { Edge, Node, Connection } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import AgentNode from "./AgentFlow/AgentNode";
import AgentDetailSidebar from "./AgentFlow/AgentDetailSidebar";

const nodeTypes = { agentNode: AgentNode };

export default function AgentMasterPanel() {
  const agentRegistry = useFactoryStore((s) => s.agentRegistry);
  const resetAgentRegistry = useFactoryStore((s) => s.resetAgentRegistry);
  const closeAgentPanel = useFactoryStore((s) => s.closeAgentPanel);
  const templates = useFactoryStore((s) => s.templates);
  const editingTemplateId = useFactoryStore((s) => s.editingTemplateId);
  const selectEditingTemplate = useFactoryStore((s) => s.selectEditingTemplate);
  const saveTemplateRegistry = useFactoryStore((s) => s.saveTemplateRegistry);
  const copyTemplate = useFactoryStore((s) => s.copyTemplate);
  const deleteTemplate = useFactoryStore((s) => s.deleteTemplate);

  const [draft, setDraft] = useState<any | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [isGeneratingPipeline, setIsGeneratingPipeline] = useState(false);
  const [showAiModal, setShowAiModal] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const isDefault = editingTemplateId === "default";

  // 레지스트리 로드 시 편집 사본 초기화
  useEffect(() => {
    if (agentRegistry) {
      setDraft(JSON.parse(JSON.stringify(agentRegistry)));
      setDirty(false);
      setSelectedAgentId(null);
    }
  }, [agentRegistry]);

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
          y: 100 + Math.floor(index / itemsPerRow) * 160 
        });
        return {
          id: agent.id,
          type: "agentNode",
          position,
          data: agent,
          selected: agent.id === selectedAgentId,
        };
      });
    });

    // 만약 draft.edges가 있으면 그걸 사용하고, 없으면 기존 order 기반으로 생성
    let currentEdges: Edge[] = draft.edges || [];
    if (currentEdges.length === 0 && sortedAgents.length > 1) {
      for (let i = 0; i < sortedAgents.length - 1; i++) {
        currentEdges.push({
          id: `e-${sortedAgents[i].id}-${sortedAgents[i+1].id}`,
          source: sortedAgents[i].id,
          target: sortedAgents[i+1].id,
          animated: true,
          style: { stroke: '#4b5563', strokeWidth: 2 },
        });
      }
    }
    setEdges(currentEdges);
  }, [draft?.agents?.length, draft?.edges, selectedAgentId, editingTemplateId]); 

  const updateOrderFromEdges = (currentEdges: Edge[], agents: any[]) => {
    const inDegree: Record<string, number> = {};
    const graph: Record<string, string[]> = {};
    agents.forEach(a => { inDegree[a.id] = 0; graph[a.id] = []; });
    
    currentEdges.forEach(e => {
      if (graph[e.source] && inDegree[e.target] !== undefined) {
        graph[e.source].push(e.target);
        inDegree[e.target] += 1;
      }
    });

    const queue = agents.filter(a => inDegree[a.id] === 0).map(a => a.id);
    let currentOrder = 1;
    const newOrderMap: Record<string, number> = {};

    while (queue.length > 0) {
      const node = queue.shift()!;
      newOrderMap[node] = currentOrder++;
      (graph[node] || []).forEach(neighbor => {
        inDegree[neighbor] -= 1;
        if (inDegree[neighbor] === 0) queue.push(neighbor);
      });
    }

    agents.forEach(a => {
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
    [setEdges]
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
    [setEdges]
  );

  // 노드 드래그 종료 시 위치만 저장 (순서는 엣지가 결정)
  const onNodeDragStop = useCallback((event: any, node: any) => {
    setDraft((d: any) => {
      if (!d || !d.agents) return d;
      return {
        ...d,
        agents: d.agents.map((a: any) => a.id === node.id ? { ...a, position: node.position } : a)
      };
    });
    setDirty(true);
  }, []);

  const onNodeClick = useCallback((event: any, node: any) => {
    setSelectedAgentId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedAgentId(null);
  }, []);

  if (!draft) {
    return (
      <div className="h-screen w-screen bg-gray-900 text-gray-300 flex items-center justify-center">
        <span className="animate-pulse">에이전트 레지스트리 로딩 중…</span>
      </div>
    );
  }

  const agents: any[] = draft.agents || [];
  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || null;
  const hotlCount = agents.filter((a) => a.enabled && a.hotl_after).length;

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
    setSaving(true);
    const ok = await saveTemplateRegistry(editingTemplateId, draft);
    setSaving(false);
    if (ok) {
      setDirty(false);
      alert(`✅ 템플릿 '${editingTemplateId}' 을(를) 저장했습니다.\n(이 템플릿으로 새로 생성하는 프로젝트부터 반영됩니다. 진행 중인 작업에는 영향 없음.)`);
    }
  };

  const handleGeneratePipeline = async () => {
    if (!aiPrompt.trim()) return;
    if (dirty && !confirm("저장하지 않은 변경사항이 사라집니다. 계속하시겠습니까?")) return;
    
    setIsGeneratingPipeline(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/ai-recommend/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_request: aiPrompt })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        setDraft(data.data);
        setDirty(true);
        setSelectedAgentId(null);
        setAiPrompt("");
        setShowAiModal(false);
      } else {
        alert(`생성 실패: ${data.detail || "알 수 없는 오류"}`);
      }
    } catch (e: any) {
      alert(`생성 중 오류 발생: ${e.message}`);
    } finally {
      setIsGeneratingPipeline(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("기본(default) 템플릿을 출고 상태(현재 SW 파이프라인)로 초기화하시겠습니까? 저장된 커스텀 설정이 사라집니다.")) return;
    await resetAgentRegistry();
  };

  const handleSwitchTemplate = async (tid: string) => {
    if (tid === editingTemplateId) return;
    if (dirty && !confirm("저장하지 않은 변경이 있습니다. 템플릿을 전환하면 변경이 사라집니다. 계속할까요?")) return;
    await selectEditingTemplate(tid);
  };

  const handleCopy = async () => {
    const newId = prompt("새 템플릿 ID (영문/숫자/_/- 만):", "");
    if (!newId || !newId.trim()) return;
    const newName = prompt("새 템플릿 표시 이름:", "") || "";
    const ok = await copyTemplate(editingTemplateId, newId.trim(), newName.trim());
    if (ok) alert(`✅ 템플릿 '${newId.trim()}' 을(를) 만들었습니다. 지금부터 이 템플릿을 편집합니다.`);
  };

  const handleDelete = async () => {
    if (isDefault) return;
    if (!confirm(`템플릿 '${editingTemplateId}' 을(를) 삭제하시겠습니까? 복구할 수 없습니다.\n(이미 이 템플릿으로 생성된 프로젝트는 계속 동작합니다.)`)) return;
    const ok = await deleteTemplate(editingTemplateId);
    if (ok) alert("템플릿을 삭제했습니다. 기본(default) 템플릿으로 돌아갑니다.");
  };

  return (
    <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
      {/* 헤더 */}
      <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0 z-10 shadow-sm">
        <div className="flex items-center gap-4 min-w-0">
          <button onClick={closeAgentPanel} className="text-sm font-bold text-gray-400 hover:text-white bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 런처</button>
          <h1 className="text-lg font-bold text-white truncate">⚙️ 에이전트 마스터 제어판</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {dirty && <span className="text-xs text-amber-400 mr-1">● 저장 안 됨</span>}
          {isDefault && <button onClick={handleReset} className="text-xs font-bold text-gray-300 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded transition-colors">기본값 초기화</button>}
          <button onClick={handleSave} disabled={!dirty || saving} className="text-sm font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 px-4 py-1.5 rounded transition-colors">
            {saving ? "저장 중…" : "💾 저장"}
          </button>
        </div>
      </header>

      {/* 템플릿 툴바 */}
      <div className="bg-gray-850 bg-gray-800/60 border-b border-gray-700 px-6 py-2.5 flex items-center gap-3 shrink-0 flex-wrap z-10">
        <span className="text-xs font-bold text-gray-400 shrink-0">🧩 편집 중인 템플릿</span>
        <select
          value={editingTemplateId}
          onChange={(e) => handleSwitchTemplate(e.target.value)}
          className="bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-blue-500 outline-none min-w-[16rem]"
        >
          {templates.length === 0 && <option value="default">기본 워크플로우</option>}
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name || t.id}{t.builtin ? " (기본)" : ""}</option>
          ))}
        </select>
        <button onClick={handleCopy} className="text-xs font-bold text-emerald-300 bg-emerald-900/40 border border-emerald-700/50 hover:bg-emerald-800/50 px-3 py-1.5 rounded transition-colors">
          ＋ 복사해서 새 템플릿
        </button>
        <button onClick={() => setShowAiModal(true)} className="text-xs font-bold text-blue-300 bg-blue-900/40 border border-blue-700/50 hover:bg-blue-800/50 px-3 py-1.5 rounded transition-colors ml-2">
          ✨ AI로 템플릿 신규 구상
        </button>
        <button
          onClick={handleDelete}
          disabled={isDefault}
          title={isDefault ? "기본 템플릿은 삭제할 수 없습니다" : "이 템플릿 삭제"}
          className="text-xs font-bold text-rose-300 bg-rose-900/30 border border-rose-800/50 hover:bg-rose-800/40 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1.5 rounded transition-colors"
        >
          🗑 삭제
        </button>
        <span className="text-xs text-gray-500 ml-auto">
          {isDefault ? "기본 템플릿(default) — 모든 신규 프로젝트의 기본값" : `커스텀 템플릿 — id: ${editingTemplateId}`}
        </span>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* React Flow 캔버스 */}
        <div className="flex-1 relative bg-gray-900">
          {/* 상단 파이프라인 메타 정보 */}
          <div className="absolute top-4 left-4 z-10 bg-gray-800/90 backdrop-blur-md border border-gray-700 p-4 rounded-xl shadow-lg w-96">
            <input
              value={draft.pipeline_name || ""}
              onChange={(e) => updateMeta("pipeline_name", e.target.value)}
              placeholder="파이프라인 이름"
              className="w-full bg-transparent text-white font-bold text-lg outline-none border-b border-transparent hover:border-gray-600 focus:border-blue-500 mb-2 px-1"
            />
            <textarea
              value={draft.description || ""}
              onChange={(e) => updateMeta("description", e.target.value)}
              placeholder="파이프라인 설명"
              rows={2}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 resize-none outline-none focus:border-blue-500 mb-2"
            />
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-gray-400 whitespace-nowrap">최종 산출물 유형:</span>
              <select
                value={draft.deliverable_type || "software_app"}
                onChange={(e) => updateMeta("deliverable_type", e.target.value)}
                className="bg-gray-800 text-xs text-gray-200 border border-gray-600 rounded px-2 py-1 outline-none focus:border-blue-500 w-full"
              >
                <option value="software_app">소프트웨어 애플리케이션 (실행 가능)</option>
                <option value="document_report">분석/보고서 문서 (열람 및 다운로드)</option>
                <option value="hybrid_simulation">복합 시뮬레이터 (UI 렌더링 및 최종 보고서)</option>
              </select>
            </div>
            <div className="text-[10px] text-gray-400 px-1 flex gap-2">
              <span>드래그앤드랍으로 실행 순서 동적 변경</span>
              <span>•</span>
              <span className="text-blue-400 font-bold">{agents.length} Nodes</span>
              <span>•</span>
              <span className="text-rose-400 font-bold">{hotlCount} HOTL</span>
            </div>
          </div>

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
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
          >
            <Background color="#374151" gap={16} />
            <Controls className="bg-gray-800 border-gray-700 fill-white" />
          </ReactFlow>
        </div>

        {/* 우측 상세 패널 */}
        <div
          className={`transition-all duration-300 ease-in-out border-l border-gray-700 bg-gray-800 flex-shrink-0 overflow-hidden ${
            selectedAgentId ? "w-80 opacity-100" : "w-0 opacity-0 border-none"
          }`}
        >
          {selectedAgent && (
            <AgentDetailSidebar
              agent={selectedAgent}
              updateAgent={updateAgent}
              onClose={() => setSelectedAgentId(null)}
            />
          )}
        </div>
      </div>

      {/* AI 파이프라인 생성 모달 */}
      {showAiModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-800 border border-gray-600 rounded-xl p-6 shadow-2xl w-[500px]">
            <h2 className="text-lg font-bold text-white mb-2">✨ AI 파이프라인 자동 구상</h2>
            <p className="text-xs text-gray-400 mb-4">어떤 에이전트 파이프라인을 만들고 싶으신가요? AI가 최적의 구조를 제안합니다.<br/>(기존 편집 내용이 덮어쓰기 됩니다.)</p>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="예: 제조업 원가 분석을 위한 에이전트 구성을 만들어 줘"
              rows={4}
              className="w-full bg-gray-900 border border-gray-600 rounded p-3 text-sm text-white resize-none outline-none focus:border-blue-500 mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowAiModal(false)}
                className="px-4 py-2 text-sm font-bold text-gray-300 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleGeneratePipeline}
                disabled={isGeneratingPipeline || !aiPrompt.trim()}
                className="px-4 py-2 text-sm font-bold text-white bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded transition-colors"
              >
                {isGeneratingPipeline ? "⏳ 생성 중..." : "파이프라인 생성"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
