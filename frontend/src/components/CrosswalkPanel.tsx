import { useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
const X = `${API_BASE_URL}/api/v1/crosswalk`;

interface Sys { system_id: string; name: string; mcp_endpoint: string; scope: string; status: string; }
interface Field { system_id: string; entity: string; field: string; field_type: string; is_key: number; mapped_type: string; mapped_attr: string; }
interface Proposal { id: number; master_code: string; external_key: string; confidence: number; rationale: string; status: string; }
interface Mapping { master_code: string; external_key: string; }

// 🔗 연계/크로스워크 (M2) — 외부 시스템의 키·필드를 우리 기준정보(M1 골든 레코드)와 매핑한다.
// 매핑은 초안(제안) → 사람 승인(confirmed) 2단계. 승인된 매핑만 M3 온디맨드 조회의 주소록이 된다.
export function CrosswalkPanel({ onClose }: { onClose: () => void }) {
  const [systems, setSystems] = useState<Sys[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [schema, setSchema] = useState<Field[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [liveResults, setLiveResults] = useState<Record<string, any>>({});  // [M3] 실측 조회 결과
  const [busy, setBusy] = useState<string | null>(null);

  const [sysId, setSysId] = useState('');
  const [sysName, setSysName] = useState('');
  const [sysEndpoint, setSysEndpoint] = useState('');

  const [fEntity, setFEntity] = useState('');
  const [fField, setFField] = useState('');
  const [fType, setFType] = useState('');
  const [fIsKey, setFIsKey] = useState(false);
  const [fMappedAttr, setFMappedAttr] = useState('');

  const [useLlm, setUseLlm] = useState(false);

  const fetchSystems = async () => {
    try { const r = await fetch(`${X}/systems`); if (r.ok) setSystems((await r.json()).data || []); }
    catch (e) { console.error('시스템 로드 실패:', e); }
  };
  const refreshSel = async (sid: string) => {
    const [s, p, m] = await Promise.all([
      fetch(`${X}/systems/${sid}/schema`).then((r) => r.ok ? r.json() : { data: [] }),
      fetch(`${X}/systems/${sid}/proposals`).then((r) => r.ok ? r.json() : { data: [] }),
      fetch(`${X}/systems/${sid}/mappings`).then((r) => r.ok ? r.json() : { data: [] }),
    ]);
    setSchema(s.data || []); setProposals(p.data || []); setMappings(m.data || []);
  };

  useEffect(() => { fetchSystems(); }, []);
  useEffect(() => { if (sel) refreshSel(sel); }, [sel]); // eslint-disable-line

  const selSys = systems.find((s) => s.system_id === sel) || null;

  const handleCreateSystem = async () => {
    if (!sysId.trim()) { alert('system_id(영소문자/숫자/_/-, 2~32자)를 입력하세요.'); return; }
    setBusy('sys');
    try {
      const r = await fetch(`${X}/systems`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_id: sysId.trim(), name: sysName.trim() || sysId.trim(), mcp_endpoint: sysEndpoint.trim() }),
      });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || '시스템 등록 실패'); return; }
      setSysId(''); setSysName(''); setSysEndpoint('');
      await fetchSystems(); setSel(sysId.trim());
    } finally { setBusy(null); }
  };

  const handleAddField = async () => {
    if (!sel || !fEntity.trim() || !fField.trim()) { alert('엔티티와 필드명을 입력하세요.'); return; }
    setBusy('field');
    try {
      const r = await fetch(`${X}/systems/${sel}/schema/field`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity: fEntity.trim(), field: fField.trim(), field_type: fType.trim(), is_key: fIsKey, mapped_attr: fMappedAttr.trim() }),
      });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || '필드 추가 실패'); return; }
      setFEntity(''); setFField(''); setFType(''); setFIsKey(false); setFMappedAttr('');
      await refreshSel(sel);
    } finally { setBusy(null); }
  };

  const handleCsv = async (files: FileList | null) => {
    if (!files || !files[0] || !sel) return;
    setBusy('csv');
    try {
      const form = new FormData(); form.append('file', files[0]);
      const r = await fetch(`${X}/systems/${sel}/schema/import`, { method: 'POST', body: form });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { alert(j.detail || 'CSV 등록 실패'); return; }
      alert(`스키마 등록: 성공 ${j.data.imported}/${j.data.total}`);
      await refreshSel(sel);
    } finally { setBusy(null); }
  };

  const handlePropose = async () => {
    if (!sel) return;
    setBusy('propose');
    try {
      const r = await fetch(`${X}/systems/${sel}/propose?use_llm=${useLlm}`, { method: 'POST' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { alert(j.detail || '초안 생성 실패'); return; }
      alert(`매핑 초안: 신규 제안 ${j.data.proposed}건 (결정론 ${j.data.deterministic}${j.data.llm_used ? ' + Flash' : ''})`);
      await refreshSel(sel);
    } finally { setBusy(null); }
  };

  const handleApprove = async (p: Proposal) => {
    const ext = prompt('승인할 외부 키(인스턴스 값 지정 가능, 예: work_order:WO_TYPE=ASSY).\n비우면 제안된 포인터를 그대로 사용:', p.external_key);
    if (ext === null) return;
    await fetch(`${X}/proposals/${p.id}/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ external_key: ext.trim() || null }),
    });
    if (sel) await refreshSel(sel);
  };
  const handleReject = async (id: number) => {
    await fetch(`${X}/proposals/${id}/reject`, { method: 'POST' });
    if (sel) await refreshSel(sel);
  };

  const handleActivate = async () => {
    if (!sel) return;
    const next = selSys?.status === 'active' ? 'inactive' : 'active';
    const r = await fetch(`${X}/systems/${sel}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: next }),
    });
    if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || '상태 변경 실패'); return; }
    await fetchSystems();
  };

  // [M3] 승인 매핑의 외부 실측값을 온디맨드 조회(읽기전용). 시스템 비활성/미승인이면 409.
  const handleResolve = async (mc: string) => {
    if (!sel) return;
    setBusy('resolve');
    try {
      const r = await fetch(`${API_BASE_URL}/api/v1/mcp/resolve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ master_code: mc, system_id: sel }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({} as any));
        setLiveResults((p) => ({ ...p, [mc]: { ok: false, error: d.detail || `HTTP ${r.status}` } }));
        return;
      }
      const data = (await r.json()).data;
      setLiveResults((p) => ({ ...p, [mc]: data }));
    } catch (e) {
      setLiveResults((p) => ({ ...p, [mc]: { ok: false, error: '요청 오류' } }));
    } finally { setBusy(null); }
  };

  const inputCls = 'w-full bg-gray-950 border border-gray-700 rounded-lg p-2 text-xs text-gray-200 focus:outline-none focus:border-sky-500';
  const pending = proposals.filter((p) => p.status === 'pending');

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-6xl h-[88vh] bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 shrink-0">
          <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
            🔗 연계 / 크로스워크
            <span className="text-xs text-gray-500 font-normal">— 외부 시스템 키·필드를 기준정보와 매핑(초안→사람 승인). 승인된 매핑이 M3 온디맨드 조회의 주소록</span>
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-100 text-xl px-2">✕</button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* 좌: 시스템 목록 + 등록 */}
          <div className="w-72 border-r border-gray-700 flex flex-col overflow-hidden shrink-0">
            <div className="p-4 border-b border-gray-700">
              <div className="text-xs font-bold text-gray-400 mb-2">연계 시스템 등록</div>
              <input value={sysId} onChange={(e) => setSysId(e.target.value)} placeholder="system_id (예: sap, mes)" className={inputCls + ' mb-1.5'} />
              <input value={sysName} onChange={(e) => setSysName(e.target.value)} placeholder="이름 (예: SAP ERP)" className={inputCls + ' mb-1.5'} />
              <input value={sysEndpoint} onChange={(e) => setSysEndpoint(e.target.value)} placeholder="MCP endpoint (선택, M3용)" className={inputCls + ' mb-2'} />
              <button onClick={handleCreateSystem} disabled={busy !== null}
                className="w-full bg-sky-600 hover:bg-sky-500 disabled:bg-gray-700 text-white text-xs font-bold py-2 rounded-lg">
                {busy === 'sys' ? '등록 중…' : '+ 시스템 등록'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {systems.length === 0 && <div className="text-xs text-gray-500 text-center py-6">등록된 시스템이 없습니다.</div>}
              {systems.map((s) => (
                <button key={s.system_id} onClick={() => setSel(s.system_id)}
                  className={`w-full text-left rounded-lg p-2.5 border transition-colors ${
                    sel === s.system_id ? 'border-sky-500 bg-sky-900/30' : 'border-gray-700 bg-gray-950 hover:border-gray-500'}`}>
                  <div className="text-sm font-bold text-gray-100 truncate flex items-center gap-1.5">
                    {s.name}
                    <span className={`text-[9px] px-1.5 py-0.5 rounded ${s.status === 'active' ? 'bg-green-900/50 text-green-300' : 'bg-gray-700 text-gray-400'}`}>{s.status}</span>
                  </div>
                  <div className="text-[10px] text-gray-500 font-mono">{s.system_id}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 우: 스키마 + 제안 + 매핑 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!selSys ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">좌측에서 시스템을 선택하거나 새로 등록하세요.</div>
            ) : (
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-gray-100">{selSys.name} <span className="text-xs text-gray-500 font-mono">({selSys.system_id})</span></h3>
                  <button onClick={handleActivate}
                    className={`text-xs font-bold rounded-lg px-3 py-1.5 border ${selSys.status === 'active' ? 'text-gray-300 bg-gray-800 border-gray-600' : 'text-green-300 bg-green-950/40 border-green-900/50'}`}>
                    {selSys.status === 'active' ? '⏸ 비활성화' : '▶ 활성화(승인 매핑 필요)'}
                  </button>
                </div>

                {/* 외부 스키마 */}
                <div className="rounded-xl border border-dashed border-gray-700 bg-gray-950/60 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-bold text-gray-300">외부 스키마 (조인 컬럼 정의)</div>
                    <label className="text-[11px] text-sky-300 hover:text-sky-200 cursor-pointer">
                      📥 CSV(entity,field,field_type,is_key,mapped_attr)
                      <input type="file" accept=".csv" className="hidden" onChange={(e) => handleCsv(e.target.files)} disabled={busy !== null} />
                    </label>
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <input value={fEntity} onChange={(e) => setFEntity(e.target.value)} placeholder="entity (테이블)" className={inputCls} />
                    <input value={fField} onChange={(e) => setFField(e.target.value)} placeholder="field (필드)" className={inputCls} />
                    <input value={fType} onChange={(e) => setFType(e.target.value)} placeholder="type(선택)" className={inputCls} />
                    <input value={fMappedAttr} onChange={(e) => setFMappedAttr(e.target.value)} placeholder="→ 우리 속성명(선택)" className={inputCls} />
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                      <input type="checkbox" checked={fIsKey} onChange={(e) => setFIsKey(e.target.checked)} /> is_key(외부 기본키)
                    </label>
                    <button onClick={handleAddField} disabled={busy !== null} className="bg-sky-600 hover:bg-sky-500 disabled:bg-gray-700 text-white text-xs font-bold px-4 py-1.5 rounded-lg">+ 필드</button>
                  </div>
                  {schema.length > 0 && (
                    <div className="text-[11px] text-gray-400 pt-1 space-y-0.5 max-h-28 overflow-y-auto">
                      {schema.map((f) => (
                        <div key={`${f.entity}.${f.field}`} className="font-mono">
                          {f.is_key ? '🔑 ' : '· '}{f.entity}.{f.field}{f.field_type ? ` (${f.field_type})` : ''}{f.mapped_attr ? ` → ${f.mapped_attr}` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 매핑 초안 */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="text-xs font-bold text-gray-300">매핑 제안 (pending {pending.length})</div>
                    <label className="ml-auto flex items-center gap-1 text-[11px] text-gray-400 cursor-pointer" title="애매한 후보를 Flash 로 추가 제안(쿼터 소비)">
                      <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Flash 보강
                    </label>
                    <button onClick={handlePropose} disabled={busy !== null}
                      className="bg-sky-600 hover:bg-sky-500 disabled:bg-gray-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg">
                      {busy === 'propose' ? '생성 중…' : '🔎 매핑 초안 생성'}
                    </button>
                  </div>
                  <div className="space-y-1.5">
                    {pending.map((p) => (
                      <div key={p.id} className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-950 px-3 py-2">
                        <div className="min-w-0">
                          <div className="text-xs text-gray-100 truncate">
                            <span className="font-mono text-emerald-300">{p.master_code}</span> → <span className="font-mono text-sky-300">{p.external_key}</span>
                            <span className="ml-1.5 text-[9px] text-gray-500">신뢰도 {p.confidence}</span>
                          </div>
                          <div className="text-[10px] text-gray-500 truncate">{p.rationale}</div>
                        </div>
                        <div className="flex gap-1.5 shrink-0 ml-2">
                          <button onClick={() => handleApprove(p)} className="text-[11px] text-green-300 hover:text-green-200 bg-green-950/40 border border-green-900/50 rounded px-2 py-1">승인</button>
                          <button onClick={() => handleReject(p.id)} className="text-[11px] text-red-400 hover:text-red-300">기각</button>
                        </div>
                      </div>
                    ))}
                    {pending.length === 0 && <div className="text-xs text-gray-500 py-2 text-center">대기 중 제안이 없습니다. 스키마 등록 후 [매핑 초안 생성].</div>}
                  </div>
                </div>

                {/* 승인된 매핑 */}
                <div>
                  <div className="text-xs font-bold text-gray-300 mb-2">✅ 승인된 크로스워크 ({mappings.length}) <span className="text-gray-500 font-normal">— M3 가상 통합 주소록 · 🔄 로 외부 실측값 온디맨드 조회</span></div>
                  <div className="space-y-1">
                    {mappings.map((m) => {
                      const lr = liveResults[m.master_code];
                      return (
                        <div key={m.master_code} className="text-[11px] bg-gray-950 border border-gray-700 rounded px-2 py-1">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-mono text-gray-300 truncate">
                              <span className="text-emerald-300">{m.master_code}</span> ↔ <span className="text-sky-300">{m.external_key}</span>
                            </div>
                            <button onClick={() => handleResolve(m.master_code)} disabled={busy !== null}
                              className="shrink-0 text-[10px] text-sky-300 hover:text-sky-200 bg-sky-950/40 border border-sky-900/50 rounded px-2 py-0.5">
                              🔄 실측 조회
                            </button>
                          </div>
                          {lr && (
                            <div className="mt-1 text-[10px] pl-1">
                              {lr.ok ? (
                                <span className="text-gray-400">
                                  실측: <span className="text-sky-200">{Object.entries(lr.values || {}).map(([k, v]) => `${k}=${v}`).join(', ') || '(빈값)'}</span>
                                  <span className="opacity-60"> · as_of {String(lr.as_of || '').slice(0, 19)}{lr.cached ? ' · cache' : ''}</span>
                                </span>
                              ) : (
                                <span className="text-red-400">조회 실패: {lr.error}</span>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {mappings.length === 0 && <div className="text-xs text-gray-500 py-2 text-center">승인된 매핑이 없습니다.</div>}
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
