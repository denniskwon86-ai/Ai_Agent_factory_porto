import { useEffect, useRef, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

interface PackDoc { filename: string; chunks: number; source: string; added_at: string; }
interface Pack { pack_id: string; name: string; description: string; created_at: string; documents: PackDoc[]; }

// 📚 지식 허브 — 도메인 참고자료(표준·논문·사내 데이터)를 지식팩으로 등록·관리하고
// 프로젝트에 연결해 모든 에이전트 산출물의 그라운딩 기준으로 쓴다.
export function KnowledgeHubPanel({ onClose }: { onClose: () => void }) {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<any[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchPacks = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/knowledge/packs`);
      if (res.ok) {
        const r = await res.json();
        setPacks(r.data || []);
      }
    } catch (e) { console.error('지식팩 목록 로드 실패:', e); }
  };

  useEffect(() => { fetchPacks(); }, []);

  const selectedPack = packs.find((p) => p.pack_id === selected) || null;

  const handleCreate = async () => {
    if (!newId.trim()) { alert('팩 ID(영문/숫자/_/-)를 입력하세요.'); return; }
    setBusy('create');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/knowledge/packs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack_id: newId.trim(), name: newName.trim() || newId.trim(), description: newDesc.trim() }),
      });
      if (!res.ok) { const r = await res.json().catch(() => ({})); alert(r?.detail || '생성 실패'); return; }
      setNewId(''); setNewName(''); setNewDesc('');
      await fetchPacks();
      setSelected(newId.trim());
    } finally { setBusy(null); }
  };

  const handleDelete = async (pid: string) => {
    if (!confirm(`지식팩 '${pid}' 와 등록된 모든 자료·인덱스를 삭제합니다. 계속할까요?`)) return;
    setBusy('delete');
    try {
      await fetch(`${API_BASE_URL}/api/v1/knowledge/packs/${pid}`, { method: 'DELETE' });
      if (selected === pid) setSelected(null);
      await fetchPacks();
    } finally { setBusy(null); }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || !selected) return;
    setBusy('upload');
    try {
      for (const f of Array.from(files)) {
        const form = new FormData();
        form.append('file', f);
        const res = await fetch(`${API_BASE_URL}/api/v1/knowledge/packs/${selected}/documents`, { method: 'POST', body: form });
        if (!res.ok) {
          const r = await res.json().catch(() => ({}));
          alert(`'${f.name}' 등록 실패: ${r?.detail || res.status}`);
        }
      }
      await fetchPacks();
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleRemoveDoc = async (filename: string) => {
    if (!selected || !confirm(`'${filename}' 문서와 인덱스를 삭제할까요?`)) return;
    await fetch(`${API_BASE_URL}/api/v1/knowledge/packs/${selected}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    await fetchPacks();
  };

  const handleSearch = async () => {
    if (!selected || !query.trim()) return;
    setBusy('search');
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/knowledge/packs/${selected}/search`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), n_results: 3 }),
      });
      if (res.ok) { const r = await res.json(); setHits(r.data || []); }
    } finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-5xl h-[85vh] bg-[#12141C] border border-[#2F3640] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2F3640] shrink-0">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            📚 지식 허브
            <span className="text-xs text-gray-500 font-normal">— 도메인 참고자료를 등록하면 프로젝트에 연결된 모든 에이전트가 그 지식 범위 안에서 산출물을 생성합니다</span>
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-2">✕</button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* 좌: 팩 목록 + 생성 */}
          <div className="w-72 border-r border-[#2F3640] flex flex-col overflow-hidden shrink-0">
            <div className="p-4 border-b border-[#2F3640]">
              <div className="text-xs font-bold text-gray-400 mb-2">새 지식팩</div>
              <input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="팩 ID (예: mfg_standard)"
                className="w-full mb-1.5 bg-[#0B0C10] border border-[#2F3640] rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500" />
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="이름 (예: 제조 표준 지식)"
                className="w-full mb-1.5 bg-[#0B0C10] border border-[#2F3640] rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500" />
              <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="설명 (선택)"
                className="w-full mb-2 bg-[#0B0C10] border border-[#2F3640] rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500" />
              <button onClick={handleCreate} disabled={busy !== null}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 text-white text-xs font-bold py-2 rounded-lg">
                {busy === 'create' ? '생성 중…(최초 1회 임베딩 로드)' : '+ 팩 생성'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {packs.length === 0 && <div className="text-xs text-gray-500 text-center py-6">등록된 지식팩이 없습니다.</div>}
              {packs.map((p) => (
                <button key={p.pack_id} onClick={() => { setSelected(p.pack_id); setHits([]); }}
                  className={`w-full text-left rounded-lg p-2.5 border transition-colors ${
                    selected === p.pack_id ? 'border-indigo-500 bg-indigo-900/30' : 'border-[#2F3640] bg-[#0B0C10] hover:border-gray-500'
                  }`}>
                  <div className="text-sm font-bold text-gray-100 truncate">{p.name}</div>
                  <div className="text-[10px] text-gray-500 font-mono">{p.pack_id} · 문서 {p.documents?.length || 0}건</div>
                </button>
              ))}
            </div>
          </div>

          {/* 우: 선택 팩 상세 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!selectedPack ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">좌측에서 지식팩을 선택하거나 새로 만드세요.</div>
            ) : (
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-base font-bold text-white">{selectedPack.name}</h3>
                    <p className="text-xs text-gray-400 mt-0.5">{selectedPack.description || '설명 없음'}</p>
                  </div>
                  <button onClick={() => handleDelete(selectedPack.pack_id)} disabled={busy !== null}
                    className="text-xs text-red-400 hover:text-red-300 bg-red-950/40 border border-red-900/50 rounded-lg px-3 py-1.5">🗑️ 팩 삭제</button>
                </div>

                {/* 업로드 */}
                <div className="rounded-xl border border-dashed border-[#2F3640] bg-[#0B0C10]/60 p-4">
                  <div className="text-xs font-bold text-gray-300 mb-2">참고자료 등록 (.pdf / .md / .txt / .csv / .json — 동일 파일명은 교체)</div>
                  <input ref={fileRef} type="file" multiple accept=".pdf,.md,.txt,.csv,.json"
                    onChange={(e) => handleUpload(e.target.files)} disabled={busy !== null}
                    className="text-xs text-gray-400 file:mr-3 file:bg-indigo-600 file:hover:bg-indigo-500 file:text-white file:border-0 file:rounded-lg file:px-3 file:py-1.5 file:text-xs file:font-bold file:cursor-pointer" />
                  {busy === 'upload' && <div className="text-xs text-indigo-300 mt-2 animate-pulse">텍스트 추출·임베딩 인덱싱 중…</div>}
                </div>

                {/* 문서 목록 */}
                <div>
                  <div className="text-xs font-bold text-gray-300 mb-2">등록된 문서 ({selectedPack.documents?.length || 0})</div>
                  <div className="space-y-1.5">
                    {(selectedPack.documents || []).map((d) => (
                      <div key={d.filename} className="flex items-center justify-between rounded-lg border border-[#2F3640] bg-[#0B0C10] px-3 py-2">
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-gray-200 truncate">📄 {d.filename}</div>
                          <div className="text-[10px] text-gray-500">{d.chunks} 청크 · {d.source} · {String(d.added_at).slice(0, 16)}</div>
                        </div>
                        <button onClick={() => handleRemoveDoc(d.filename)} className="text-xs text-red-400 hover:text-red-300 shrink-0 ml-2">삭제</button>
                      </div>
                    ))}
                    {(selectedPack.documents || []).length === 0 && (
                      <div className="text-xs text-gray-500 py-3 text-center">아직 등록된 문서가 없습니다. 위에서 파일을 올려주세요.</div>
                    )}
                  </div>
                </div>

                {/* 검색 테스트 */}
                <div className="rounded-xl border border-[#2F3640] bg-[#0B0C10]/60 p-4">
                  <div className="text-xs font-bold text-gray-300 mb-2">🔍 검색 품질 테스트 — 에이전트가 이 질의로 어떤 지식을 받게 되는지 확인</div>
                  <div className="flex gap-2">
                    <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      placeholder="예: 재고 회전율 표준 기준"
                      className="flex-1 bg-[#12141C] border border-[#2F3640] rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500" />
                    <button onClick={handleSearch} disabled={busy !== null || !query.trim()}
                      className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 text-white text-xs font-bold px-4 rounded-lg">검색</button>
                  </div>
                  <div className="mt-3 space-y-2">
                    {hits.map((h, i) => (
                      <div key={i} className="rounded-lg border border-[#2F3640] bg-[#12141C] p-2.5">
                        <div className="text-[10px] text-indigo-300 font-mono mb-1">
                          {h.metadata?.filename} · 유사도 거리 {Number(h.distance ?? 0).toFixed(3)}
                        </div>
                        <div className="text-xs text-gray-300 whitespace-pre-wrap line-clamp-4">{h.content}</div>
                      </div>
                    ))}
                    {busy === 'search' && <div className="text-xs text-indigo-300 animate-pulse">검색 중…</div>}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
