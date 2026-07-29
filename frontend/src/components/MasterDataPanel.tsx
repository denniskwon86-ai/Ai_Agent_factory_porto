import { useEffect, useRef, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
const M = `${API_BASE_URL}/api/v1/master`;

interface MType { type_id: string; name_ko: string; description: string; attr_schema: any; }
interface MRecord {
  master_code: string; type_id: string; name: string; attributes: any;
  domains: string[]; is_core: boolean; version: number; aliases: string[];
}

// 🗂 기준정보 마스터 — 자재·공정·설비·KPI 같은 '느리게 변하는 참조 데이터'의 단일 진실원본.
// 여기 등록한 골든 레코드는 벡터검색이 아닌 '확정 조회'로 모든 에이전트 프롬프트에 주입된다
// (어떤 LLM 으로 폴백돼도 기준값이 동일하게 들어가는 모델 불변성의 축).
export function MasterDataPanel({ onClose }: { onClose: () => void }) {
  const [types, setTypes] = useState<MType[]>([]);
  const [selType, setSelType] = useState<string | null>(null);
  const [records, setRecords] = useState<MRecord[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // 타입 생성 폼
  const [tId, setTId] = useState('');
  const [tName, setTName] = useState('');
  const [tSchema, setTSchema] = useState('');

  // 레코드 생성/개정 폼
  const [rCode, setRCode] = useState('');
  const [rName, setRName] = useState('');
  const [rDomains, setRDomains] = useState('');
  const [rAliases, setRAliases] = useState('');
  const [rAttrs, setRAttrs] = useState('');
  const [rCore, setRCore] = useState(false);

  // 별칭 인라인 추가
  const [aliasDraft, setAliasDraft] = useState<Record<string, string>>({});

  // 주입 미리보기
  const [pvText, setPvText] = useState('');
  const [pvDomains, setPvDomains] = useState('');
  const [pv, setPv] = useState<{ block: string; matched: string[] } | null>(null);

  const fetchTypes = async () => {
    try {
      const r = await fetch(`${M}/types`);
      if (r.ok) setTypes((await r.json()).data || []);
    } catch (e) { console.error('타입 로드 실패:', e); }
  };
  const fetchRecords = async (typeId: string, q = '') => {
    try {
      const url = new URL(`${M}/records`);
      url.searchParams.set('type_id', typeId);
      if (q.trim()) url.searchParams.set('q', q.trim());
      const r = await fetch(url.toString());
      if (r.ok) setRecords((await r.json()).data || []);
    } catch (e) { console.error('레코드 로드 실패:', e); }
  };

  useEffect(() => { fetchTypes(); }, []);
  useEffect(() => { if (selType) fetchRecords(selType, search); }, [selType]); // eslint-disable-line

  const selTypeData = types.find((t) => t.type_id === selType) || null;

  const handleCreateType = async () => {
    if (!tId.trim() || !tName.trim()) { alert('type_id 와 한글명을 입력하세요 (type_id: 영소문자/숫자/_/-, 2~32자).'); return; }
    let schema: any = undefined;
    if (tSchema.trim()) {
      try { schema = JSON.parse(tSchema); } catch { alert('속성 스키마가 올바른 JSON 이 아닙니다.'); return; }
    }
    setBusy('type');
    try {
      const r = await fetch(`${M}/types`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type_id: tId.trim(), name_ko: tName.trim(), attr_schema: schema }),
      });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || '타입 생성 실패'); return; }
      setTId(''); setTName(''); setTSchema('');
      await fetchTypes();
      setSelType(tId.trim());
    } finally { setBusy(null); }
  };

  const handleCreateRecord = async () => {
    if (!selType) { alert('먼저 좌측에서 타입을 선택하세요.'); return; }
    if (!rCode.trim() || !rName.trim()) { alert('코드와 명칭을 입력하세요 (코드: 대문자/숫자로 시작, ^[A-Z0-9][A-Z0-9_-]{1,31}$).'); return; }
    let attrs: any = undefined;
    if (rAttrs.trim()) {
      try { attrs = JSON.parse(rAttrs); } catch { alert('속성값이 올바른 JSON 이 아닙니다.'); return; }
    }
    setBusy('rec');
    try {
      const r = await fetch(`${M}/records`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          master_code: rCode.trim(), type_id: selType, name: rName.trim(), attributes: attrs,
          domains: rDomains.split(',').map((s) => s.trim()).filter(Boolean),
          aliases: rAliases.split(',').map((s) => s.trim()).filter(Boolean),
          is_core: rCore,
        }),
      });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || '레코드 저장 실패'); return; }
      setRCode(''); setRName(''); setRDomains(''); setRAliases(''); setRAttrs(''); setRCore(false);
      await fetchRecords(selType, search);
    } finally { setBusy(null); }
  };

  const handleRetire = async (code: string) => {
    if (!selType || !confirm(`'${code}' 를 폐기(soft delete)합니다. 이력은 보존되지만 주입 대상에서 제외됩니다. 계속할까요?`)) return;
    await fetch(`${M}/records/${encodeURIComponent(code)}`, { method: 'DELETE' });
    await fetchRecords(selType, search);
  };

  const handleAddAlias = async (code: string) => {
    const a = (aliasDraft[code] || '').trim();
    if (!a || !selType) return;
    await fetch(`${M}/records/${encodeURIComponent(code)}/aliases`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aliases: [a] }),
    });
    setAliasDraft((d) => ({ ...d, [code]: '' }));
    await fetchRecords(selType, search);
  };
  const handleRemoveAlias = async (code: string, alias: string) => {
    if (!selType) return;
    await fetch(`${M}/records/${encodeURIComponent(code)}/aliases/${encodeURIComponent(alias)}`, { method: 'DELETE' });
    await fetchRecords(selType, search);
  };

  const handleCsv = async (files: FileList | null) => {
    if (!files || !files[0] || !selType) return;
    setBusy('csv');
    try {
      const form = new FormData();
      form.append('type_id', selType);
      form.append('file', files[0]);
      const r = await fetch(`${M}/import/csv`, { method: 'POST', body: form });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { alert(j.detail || 'CSV 등록 실패'); return; }
      const d = j.data;
      alert(`CSV 등록 완료: 성공 ${d.imported}/${d.total}${d.failed?.length ? `\n실패 ${d.failed.length}건: ` + d.failed.map((f: any) => `행${f.row}(${f.error})`).join(', ') : ''}`);
      await fetchRecords(selType, search);
    } finally { setBusy(null); if (fileRef.current) fileRef.current.value = ''; }
  };

  const handlePreview = async () => {
    if (!pvText.trim()) return;
    setBusy('preview');
    try {
      const r = await fetch(`${M}/grounding/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: pvText, domains: pvDomains.split(',').map((s) => s.trim()).filter(Boolean) }),
      });
      if (r.ok) setPv((await r.json()).data);
    } finally { setBusy(null); }
  };

  const inputCls = 'w-full bg-[#0B0C10] border border-[#2F3640] rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-emerald-500';

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-6xl h-[88vh] bg-[#12141C] border border-[#2F3640] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2F3640] shrink-0">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            🗂 기준정보 마스터
            <span className="text-xs text-gray-500 font-normal">— 골든 레코드는 확정 조회로 모든 에이전트 프롬프트에 주입됩니다(모델 불변). 지식팩(확률적 RAG)과 상호보완</span>
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-2">✕</button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* 좌: 타입 목록 + 생성 */}
          <div className="w-72 border-r border-[#2F3640] flex flex-col overflow-hidden shrink-0">
            <div className="p-4 border-b border-[#2F3640]">
              <div className="text-xs font-bold text-gray-400 mb-2">새 타입(온톨로지)</div>
              <input value={tId} onChange={(e) => setTId(e.target.value)} placeholder="type_id (예: process)" className={inputCls + ' mb-1.5'} />
              <input value={tName} onChange={(e) => setTName(e.target.value)} placeholder="한글명 (예: 공정)" className={inputCls + ' mb-1.5'} />
              <textarea value={tSchema} onChange={(e) => setTSchema(e.target.value)} rows={3}
                placeholder={'속성 스키마 JSON (선택)\n{"표준리드타임_h":{"type":"number"}}'} className={inputCls + ' mb-2 font-mono resize-none'} />
              <button onClick={handleCreateType} disabled={busy !== null}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white text-xs font-bold py-2 rounded-lg">
                {busy === 'type' ? '생성 중…' : '+ 타입 생성'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {types.length === 0 && <div className="text-xs text-gray-500 text-center py-6">등록된 타입이 없습니다.</div>}
              {types.map((t) => (
                <button key={t.type_id} onClick={() => { setSelType(t.type_id); setPv(null); }}
                  className={`w-full text-left rounded-lg p-2.5 border transition-colors ${
                    selType === t.type_id ? 'border-emerald-500 bg-emerald-900/30' : 'border-[#2F3640] bg-[#0B0C10] hover:border-gray-500'}`}>
                  <div className="text-sm font-bold text-gray-100 truncate">{t.name_ko}</div>
                  <div className="text-[10px] text-gray-500 font-mono">{t.type_id}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 우: 레코드 관리 + 미리보기 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!selTypeData ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">좌측에서 타입을 선택하거나 새로 만드세요.</div>
            ) : (
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-white">{selTypeData.name_ko} <span className="text-xs text-gray-500 font-mono">({selTypeData.type_id})</span></h3>
                  <label className="text-xs text-emerald-300 hover:text-emerald-200 cursor-pointer bg-emerald-950/40 border border-emerald-900/50 rounded-lg px-3 py-1.5">
                    📥 CSV 일괄등록
                    <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => handleCsv(e.target.files)} disabled={busy !== null} />
                  </label>
                </div>
                <div className="text-[10px] text-gray-500 -mt-3">CSV 헤더: <code>master_code,name,domains,aliases,attr:&lt;속성명&gt;…</code> (domains·aliases 는 <code>;</code> 구분)</div>

                {/* 레코드 생성/개정 폼 */}
                <div className="rounded-xl border border-dashed border-[#2F3640] bg-[#0B0C10]/60 p-4 space-y-2">
                  <div className="text-xs font-bold text-gray-300">레코드 생성 · 개정 <span className="text-gray-500 font-normal">(동일 코드 재저장 = 개정 version+1, 구판은 이력 보존)</span></div>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={rCode} onChange={(e) => setRCode(e.target.value)} placeholder="master_code (예: PROC-ASSY-01)" className={inputCls} />
                    <input value={rName} onChange={(e) => setRName(e.target.value)} placeholder="정식 명칭 (예: 조립 공정)" className={inputCls} />
                    <input value={rDomains} onChange={(e) => setRDomains(e.target.value)} placeholder="도메인 태그 (콤마구분, 예: manufacturing)" className={inputCls} />
                    <input value={rAliases} onChange={(e) => setRAliases(e.target.value)} placeholder="별칭 (콤마구분, 예: ASSY, 조립)" className={inputCls} />
                  </div>
                  <textarea value={rAttrs} onChange={(e) => setRAttrs(e.target.value)} rows={2}
                    placeholder={'속성값 JSON (선택, 타입 스키마 준수) {"표준리드타임_h":72}'} className={inputCls + ' font-mono resize-none'} />
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
                      <input type="checkbox" checked={rCore} onChange={(e) => setRCore(e.target.checked)} />
                      is_core (도메인 대표 레코드 — 별칭 미언급 시에도 우선 주입)
                    </label>
                    <button onClick={handleCreateRecord} disabled={busy !== null}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white text-xs font-bold px-4 py-1.5 rounded-lg">
                      {busy === 'rec' ? '저장 중…' : '저장'}
                    </button>
                  </div>
                </div>

                {/* 검색 + 레코드 목록 */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="text-xs font-bold text-gray-300">레코드 ({records.length})</div>
                    <input value={search} onChange={(e) => setSearch(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && selType && fetchRecords(selType, search)}
                      placeholder="이름·별칭 검색 (Enter)" className={inputCls + ' ml-auto max-w-[220px]'} />
                  </div>
                  <div className="space-y-1.5">
                    {records.map((r) => (
                      <div key={r.master_code} className="rounded-lg border border-[#2F3640] bg-[#0B0C10] px-3 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-gray-100 truncate">
                              <span className="font-mono text-emerald-300">{r.master_code}</span> · {r.name}
                              {r.is_core && <span className="ml-1.5 text-[9px] bg-amber-900/50 text-amber-300 px-1.5 py-0.5 rounded">CORE</span>}
                              <span className="ml-1 text-[9px] text-gray-500">v{r.version}</span>
                            </div>
                            <div className="text-[10px] text-gray-500 mt-0.5">
                              {r.domains?.length ? `도메인: ${r.domains.join(', ')}` : '도메인 없음'}
                              {Object.keys(r.attributes || {}).length ? ` · ${Object.entries(r.attributes).map(([k, v]) => `${k}=${v}`).join(', ')}` : ''}
                            </div>
                          </div>
                          <button onClick={() => handleRetire(r.master_code)} className="text-[10px] text-red-400 hover:text-red-300 shrink-0">폐기</button>
                        </div>
                        {/* 별칭 칩 */}
                        <div className="flex flex-wrap items-center gap-1 mt-1.5">
                          {(r.aliases || []).filter((a) => a !== r.name).map((a) => (
                            <span key={a} className="text-[10px] bg-[#12141C] border border-[#2F3640] text-gray-300 rounded-full pl-2 pr-1 py-0.5 flex items-center gap-1">
                              {a}<button onClick={() => handleRemoveAlias(r.master_code, a)} className="text-gray-500 hover:text-red-400">✕</button>
                            </span>
                          ))}
                          <input value={aliasDraft[r.master_code] || ''} onChange={(e) => setAliasDraft((d) => ({ ...d, [r.master_code]: e.target.value }))}
                            onKeyDown={(e) => e.key === 'Enter' && handleAddAlias(r.master_code)}
                            placeholder="+ 별칭" className="text-[10px] bg-transparent border-b border-[#2F3640] w-16 focus:outline-none focus:border-emerald-500 text-gray-300" />
                        </div>
                      </div>
                    ))}
                    {records.length === 0 && <div className="text-xs text-gray-500 py-3 text-center">레코드가 없습니다. 위에서 등록하세요.</div>}
                  </div>
                </div>

                {/* 주입 미리보기 */}
                <div className="rounded-xl border border-[#2F3640] bg-[#0B0C10]/60 p-4">
                  <div className="text-xs font-bold text-gray-300 mb-2">🔍 주입 미리보기 — 이 텍스트에 실제로 주입될 기준정보 블록 확인(별칭 감지 + is_core)</div>
                  <div className="flex gap-2 mb-2">
                    <input value={pvText} onChange={(e) => setPvText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handlePreview()}
                      placeholder="예: 조립 공정 리드타임을 단축한다" className={inputCls} />
                    <input value={pvDomains} onChange={(e) => setPvDomains(e.target.value)} placeholder="도메인(콤마)" className={inputCls + ' max-w-[160px]'} />
                    <button onClick={handlePreview} disabled={busy !== null || !pvText.trim()}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white text-xs font-bold px-4 rounded-lg shrink-0">확인</button>
                  </div>
                  {pv && (
                    <div className="rounded-lg border border-[#2F3640] bg-[#12141C] p-2.5">
                      <div className="text-[10px] text-emerald-300 font-mono mb-1">매칭: {pv.matched.length ? pv.matched.join(', ') : '(없음 — 주입 안 됨)'}</div>
                      {pv.block && <pre className="text-[11px] text-gray-300 whitespace-pre-wrap">{pv.block}</pre>}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
