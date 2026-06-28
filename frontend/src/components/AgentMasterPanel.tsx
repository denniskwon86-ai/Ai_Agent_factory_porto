import { useEffect, useState } from "react";
import { useFactoryStore } from "../store/useFactoryStore";

// 에이전트 마스터 제어판 (범용 멀티에이전트 플랫폼 Phase 1)
// 각 에이전트의 역할·스킬·모델티어·순서·HOTL·활성화를 외부 레지스트리(SSOT)에서 보고 편집/저장한다.

const CATEGORY_META: Record<string, { label: string; color: string }> = {
  planning: { label: "기획", color: "text-sky-400 border-sky-500/40 bg-sky-500/10" },
  execution: { label: "실행", color: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10" },
  review: { label: "검수", color: "text-amber-400 border-amber-500/40 bg-amber-500/10" },
  system: { label: "시스템", color: "text-gray-400 border-gray-500/40 bg-gray-500/10" },
};

function Toggle({ on, onClick, label, title }: { on: boolean; onClick: () => void; label: string; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`px-2.5 py-1 rounded text-xs font-bold border transition-colors ${
        on ? "bg-blue-600 border-blue-400 text-white" : "bg-gray-900 border-gray-700 text-gray-500 hover:text-gray-300"
      }`}
    >
      {on ? "● " : "○ "}{label}
    </button>
  );
}

export default function AgentMasterPanel() {
  const agentRegistry = useFactoryStore((s) => s.agentRegistry);
  const saveAgentRegistry = useFactoryStore((s) => s.saveAgentRegistry);
  const resetAgentRegistry = useFactoryStore((s) => s.resetAgentRegistry);
  const closeAgentPanel = useFactoryStore((s) => s.closeAgentPanel);

  const [draft, setDraft] = useState<any | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  // 레지스트리 로드 시 편집 사본 초기화
  useEffect(() => {
    if (agentRegistry) {
      setDraft(JSON.parse(JSON.stringify(agentRegistry)));
      setDirty(false);
    }
  }, [agentRegistry]);

  if (!draft) {
    return (
      <div className="h-screen w-screen bg-gray-900 text-gray-300 flex items-center justify-center">
        <span className="animate-pulse">에이전트 레지스트리 로딩 중…</span>
      </div>
    );
  }

  const agents: any[] = [...(draft.agents || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

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
    const ok = await saveAgentRegistry(draft);
    setSaving(false);
    if (ok) { setDirty(false); alert("✅ 레지스트리를 저장했습니다.\n(HOTL 중단점 변경은 서버 재시작 후 파이프라인에 반영됩니다.)"); }
  };
  const handleReset = async () => {
    if (!confirm("레지스트리를 기본값(현재 SW 파이프라인)으로 초기화하시겠습니까? 저장된 커스텀 설정이 사라집니다.")) return;
    await resetAgentRegistry();
  };

  const hotlCount = agents.filter((a) => a.enabled && a.hotl_after).length;

  return (
    <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
      {/* 헤더 */}
      <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-4 min-w-0">
          <button onClick={closeAgentPanel} className="text-sm font-bold text-gray-400 hover:text-white bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 런처</button>
          <h1 className="text-lg font-bold text-white truncate">⚙️ 에이전트 마스터 제어판</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {dirty && <span className="text-xs text-amber-400 mr-1">● 저장 안 됨</span>}
          <button onClick={handleReset} className="text-xs font-bold text-gray-300 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded transition-colors">기본값 초기화</button>
          <button onClick={handleSave} disabled={!dirty || saving} className="text-sm font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 px-4 py-1.5 rounded transition-colors">
            {saving ? "저장 중…" : "💾 저장"}
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-6">
          {/* 안내 */}
          <div className="bg-blue-950/40 border border-blue-800/50 rounded-lg p-4 text-sm text-blue-200 mb-6">
            각 에이전트의 <b>역할·스킬·모델·순서·HOTL(인간 검토)·활성화</b>를 이 화면에서 관리합니다.
            <span className="text-blue-300/80"> 현재(Phase 1)는 <b>HOTL 중단점</b>이 저장 후 <b>서버 재시작 시</b> 파이프라인에 실제 반영됩니다.
            노드 활성/순서·동적 그래프 생성의 실행 반영은 Phase 2(동적 빌더)에서 적용됩니다.</span>
          </div>

          {/* 파이프라인 메타 */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-5 mb-6">
            <label className="block text-xs font-bold text-gray-400 mb-1">파이프라인 이름</label>
            <input
              value={draft.pipeline_name || ""}
              onChange={(e) => updateMeta("pipeline_name", e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white mb-3 focus:border-blue-500 outline-none"
            />
            <label className="block text-xs font-bold text-gray-400 mb-1">설명</label>
            <textarea
              value={draft.description || ""}
              onChange={(e) => updateMeta("description", e.target.value)}
              rows={2}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 resize-y focus:border-blue-500 outline-none"
            />
            <div className="text-xs text-gray-500 mt-3">
              총 {agents.length}개 에이전트 · 활성 {agents.filter((a) => a.enabled).length}개 · HOTL 중단점 {hotlCount}개
            </div>
          </div>

          {/* 에이전트 카드 목록 */}
          <div className="space-y-3">
            {agents.map((a, idx) => {
              const cat = CATEGORY_META[a.category] || CATEGORY_META.system;
              return (
                <div key={a.id} className={`bg-gray-800 border rounded-lg p-4 ${a.enabled ? "border-gray-700" : "border-gray-800 opacity-60"}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-xs font-mono text-gray-500 w-6 text-right">{idx + 1}</span>
                    <span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${cat.color}`}>{cat.label}</span>
                    <input
                      value={a.name_ko || ""}
                      onChange={(e) => updateAgent(a.id, "name_ko", e.target.value)}
                      className="bg-transparent text-base font-bold text-white border-b border-transparent hover:border-gray-600 focus:border-blue-500 outline-none px-1 flex-1 min-w-0"
                    />
                    <span className="text-xs font-mono text-gray-600 shrink-0">{a.id}</span>
                  </div>

                  <textarea
                    value={a.role || ""}
                    onChange={(e) => updateAgent(a.id, "role", e.target.value)}
                    rows={2}
                    className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 resize-y focus:border-blue-500 outline-none mb-3"
                    placeholder="역할 설명"
                  />

                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
                    <label className="flex items-center gap-1.5 text-gray-400">
                      스킬
                      <input
                        value={a.skill || ""}
                        onChange={(e) => updateAgent(a.id, "skill", e.target.value)}
                        placeholder="(없음)"
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200 font-mono w-36 focus:border-blue-500 outline-none"
                      />
                    </label>
                    <label className="flex items-center gap-1.5 text-gray-400">
                      단계
                      <input
                        value={a.stage || ""}
                        onChange={(e) => updateAgent(a.id, "stage", e.target.value)}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200 font-mono w-28 focus:border-blue-500 outline-none"
                      />
                    </label>
                    <label className="flex items-center gap-1.5 text-gray-400">
                      모델
                      <select
                        value={a.model_tier || "pro"}
                        onChange={(e) => updateAgent(a.id, "model_tier", e.target.value)}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200 focus:border-blue-500 outline-none"
                      >
                        <option value="pro">pro (고성능)</option>
                        <option value="flash">flash (고속)</option>
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5 text-gray-400">
                      순서
                      <input
                        type="number"
                        value={a.order ?? 0}
                        onChange={(e) => updateAgent(a.id, "order", parseInt(e.target.value || "0", 10))}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200 w-16 focus:border-blue-500 outline-none"
                      />
                    </label>

                    <div className="flex items-center gap-2 ml-auto">
                      <Toggle on={!!a.enabled} onClick={() => updateAgent(a.id, "enabled", !a.enabled)} label="활성" title="비활성 시 파이프라인에서 제외(Phase 2 반영)" />
                      <Toggle on={!!a.hotl_after} onClick={() => updateAgent(a.id, "hotl_after", !a.hotl_after)} label="HOTL" title="이 단계 직후 인간 검토 중단점(재시작 시 반영)" />
                      <Toggle on={!!a.debate} onClick={() => updateAgent(a.id, "debate", !a.debate)} label="토론" title="다중 에이전트 토론·합의 루프" />
                      {!a.llm && <span className="text-[11px] text-gray-500 border border-gray-700 rounded px-2 py-1">비-LLM</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
