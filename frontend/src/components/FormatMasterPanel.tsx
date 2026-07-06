import { useEffect, useState } from "react";
import { useFactoryStore, type OutputFormat } from "../store/useFactoryStore";

export default function FormatMasterPanel() {
  const formats = useFactoryStore((s) => s.formats);
  const closeFormatPanel = useFactoryStore((s) => s.closeFormatPanel);
  const saveFormat = useFactoryStore((s) => s.saveFormat);
  const deleteFormat = useFactoryStore((s) => s.deleteFormat);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<OutputFormat | null>(null);
  const [saving, setSaving] = useState(false);

  // 선택된 포맷이 변경되면 draft 초기화
  useEffect(() => {
    if (editingId) {
      const f = formats.find(x => x.id === editingId);
      if (f) {
        setDraft(JSON.parse(JSON.stringify(f)));
      } else {
        setDraft({ id: editingId, name: "", description: "", prompt_injection: "" });
      }
    } else {
      setDraft(null);
    }
  }, [editingId, formats]);

  const handleCreateNew = () => {
    const newId = prompt("새로운 포맷 ID (영문, 숫자, _ 만 사용):", "");
    if (!newId || !newId.trim()) return;
    if (formats.find(f => f.id === newId)) {
      alert("이미 존재하는 ID입니다.");
      return;
    }
    setEditingId(newId.trim());
  };

  const handleSave = async () => {
    if (!draft) return;
    if (!draft.name.trim() || !draft.prompt_injection.trim()) {
      alert("포맷 이름과 시스템 프롬프트(주입) 내용은 필수입니다.");
      return;
    }
    setSaving(true);
    const ok = await saveFormat(draft);
    setSaving(false);
    if (ok) {
      alert(`✅ '${draft.name}' 양식을 저장했습니다.`);
      setEditingId(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (id === "default") {
      alert("기본(default) 포맷은 삭제할 수 없습니다.");
      return;
    }
    if (!confirm(`정말 '${id}' 포맷을 삭제하시겠습니까?`)) return;
    await deleteFormat(id);
    if (editingId === id) setEditingId(null);
  };

  return (
    <div className="absolute inset-0 z-50 bg-gray-900/90 backdrop-blur flex items-center justify-center p-4">
      <div className="bg-gray-800 border border-gray-700 rounded-lg shadow-2xl w-full max-w-6xl h-full max-h-[90vh] flex flex-col overflow-hidden">
        
        {/* 헤더 */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 bg-gray-900">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <span className="text-xl">📄</span> 출력 양식 (Format) 마스터
            </h2>
            <span className="text-xs text-gray-400">결과물 형태를 강제하는 템플릿(Harness) 중앙 제어판</span>
          </div>
          <button onClick={closeFormatPanel} className="text-gray-400 hover:text-white px-3 py-1 rounded border border-gray-700 hover:bg-gray-800 transition-colors">
            ✕ 닫기
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* 좌측: 포맷 목록 */}
          <div className="w-1/3 border-r border-gray-700 bg-gray-800 flex flex-col">
            <div className="p-3 border-b border-gray-700 flex justify-between items-center">
              <span className="text-sm font-semibold text-gray-300">저장된 양식 ({formats.length})</span>
              <button 
                onClick={handleCreateNew}
                className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-2 py-1 rounded"
              >
                + 새 양식
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {formats.map((f) => (
                <div 
                  key={f.id}
                  onClick={() => setEditingId(f.id)}
                  className={`p-3 rounded cursor-pointer border transition-colors flex justify-between items-center ${
                    editingId === f.id 
                      ? "bg-blue-900/30 border-blue-500/50" 
                      : "bg-gray-900 border-gray-800 hover:border-gray-600"
                  }`}
                >
                  <div>
                    <div className="text-sm font-bold text-gray-200">{f.name}</div>
                    <div className="text-xs text-gray-500 mt-1 truncate max-w-[200px]">{f.id}</div>
                  </div>
                  {f.id !== "default" && (
                    <button 
                      onClick={(e) => { e.stopPropagation(); handleDelete(f.id); }}
                      className="text-gray-500 hover:text-red-400 p-1"
                      title="삭제"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 우측: 포맷 상세 편집 */}
          <div className="w-2/3 bg-gray-900 p-6 flex flex-col overflow-y-auto">
            {!editingId ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 flex-col gap-2">
                <span className="text-4xl">📝</span>
                <span>좌측에서 편집할 양식을 선택하거나 새 양식을 만드세요.</span>
              </div>
            ) : draft ? (
              <div className="max-w-3xl w-full mx-auto flex flex-col gap-5">
                
                <div className="flex justify-between items-end mb-2">
                  <div>
                    <h3 className="text-xl font-bold text-gray-100">양식 편집</h3>
                    <div className="text-sm text-gray-400 mt-1">ID: <span className="text-gray-300 font-mono">{draft.id}</span></div>
                  </div>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => setEditingId(null)}
                      className="px-4 py-2 rounded text-sm bg-gray-800 text-gray-300 hover:bg-gray-700 transition border border-gray-700"
                    >
                      취소
                    </button>
                    <button 
                      onClick={handleSave} disabled={saving}
                      className="px-4 py-2 rounded text-sm font-bold bg-blue-600 hover:bg-blue-500 text-white shadow-lg transition flex items-center gap-2"
                    >
                      {saving ? "저장 중..." : "💾 저장"}
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 mb-1">양식 표시 이름</label>
                    <input 
                      type="text" 
                      value={draft.name} 
                      onChange={e => setDraft({ ...draft, name: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-600 rounded p-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500" 
                      placeholder="예: 반응형 대시보드 UI"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-gray-400 mb-1">양식 설명 (선택)</label>
                    <input 
                      type="text" 
                      value={draft.description} 
                      onChange={e => setDraft({ ...draft, description: e.target.value })}
                      className="w-full bg-gray-800 border border-gray-600 rounded p-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500" 
                      placeholder="이 양식에 대한 간단한 설명을 작성합니다."
                    />
                  </div>

                  <div>
                    <div className="flex justify-between mb-1">
                      <label className="text-xs font-bold text-gray-400">시스템 프롬프트 주입 내용 (Harness Rules)</label>
                    </div>
                    <div className="text-[11px] text-gray-500 mb-2 leading-relaxed bg-gray-800/50 p-2 rounded border border-gray-700/50">
                      💡 에이전트의 시스템 프롬프트 맨 마지막에 강제로 주입될 규칙입니다. <br/>
                      반드시 <b>&lt;artifact&gt;</b> 태그 안에 최종 결과물을 넣으라고 지시해야 하며, 
                      다음 작업자를 위한 요약을 <b>&lt;summary&gt;</b>에 작성하도록 지시해야 시스템이 꼬이지 않습니다.
                    </div>
                    <textarea 
                      value={draft.prompt_injection} 
                      onChange={e => setDraft({ ...draft, prompt_injection: e.target.value })}
                      className="w-full h-80 bg-gray-800 border border-gray-600 rounded p-3 text-sm font-mono text-gray-100 focus:outline-none focus:border-blue-500 resize-none" 
                      placeholder="당신의 최종 결과물은 반드시 <artifact> ... </artifact> 태그 안에..."
                    />
                  </div>
                </div>

              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
