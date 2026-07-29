import { useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
const O = `${API_BASE_URL}/api/v1/org`;

interface Dept {
  dept_id: string; name_ko: string; parent_id: string; path: string; depth: number;
  master_domains: string[]; default_template_id: string; domain_agents: string[];
  legacy_domain: string; version: number; status: string; valid_from: string;
  children?: Dept[];
}
interface User {
  user_id: string; display_name: string; primary_dept_id: string;
  is_executive: boolean; is_admin: boolean; is_data_admin: boolean;
  status: string; roles: Record<string, string>;
}
interface Scope {
  user_id: string; unrestricted: boolean; can_edit_org: boolean;
  can_run_enterprise: boolean; can_manage_standard: boolean;
  readable_dept_ids: string[]; writable_dept_ids: string[];
}

const ROLES = ['viewer', 'member', 'manager'] as const;

// 🏢 조직도 — 부서는 '기준정보'다. 개편하면 새 버전이 생기고 구판은 이력으로 보존된다
// (과거 산출물의 소유 부서 해석이 깨지면 안 되기 때문). 폐지도 물리 삭제가 아니라 soft-retire.
export function OrgChartPanel({ onClose }: { onClose: () => void }) {
  const [tree, setTree] = useState<Dept[]>([]);
  const [flat, setFlat] = useState<Dept[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [scope, setScope] = useState<Scope | null>(null);
  const [tab, setTab] = useState<'dept' | 'user'>('dept');
  const [sel, setSel] = useState<string | null>(null);
  const [hist, setHist] = useState<Dept[]>([]);
  const [asUser, setAsUser] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // [Phase 2] 평상시 식별은 전역 인터셉터(lib/api)가 붙인다. 여기 asUser 는
  // **다른 사용자 시점을 즉석에서 확인**하기 위한 임시 오버라이드다(전역 상태를 바꾸지 않는다).
  const H = (): HeadersInit =>
    asUser ? { 'Content-Type': 'application/json', 'X-Factory-User': asUser }
           : { 'Content-Type': 'application/json' };

  const load = async () => {
    setBusy('조회 중...'); setErr(null);
    try {
      const [t, d, u, m] = await Promise.all([
        fetch(`${O}/tree`), fetch(`${O}/departments`), fetch(`${O}/users`),
        fetch(`${O}/me`, { headers: H() }),
      ]);
      setTree((await t.json())?.data || []);
      setFlat((await d.json())?.data || []);
      setUsers((await u.json())?.data || []);
      setScope((await m.json())?.data || null);
    } catch (e: any) { setErr(`조회 실패: ${e?.message || e}`); }
    finally { setBusy(null); }
  };

  useEffect(() => { load(); }, [asUser]);

  const call = async (method: string, path: string, body?: any) => {
    setBusy('처리 중...'); setErr(null);
    try {
      const r = await fetch(`${O}${path}`, { method, headers: H(), body: body ? JSON.stringify(body) : undefined });
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j?.detail || `HTTP ${r.status}`); }
      await load();
      return true;
    } catch (e: any) { setErr(`${e?.message || e}`); return false; }
    finally { setBusy(null); }
  };

  const seed = async () => {
    if (!confirm('코드에 하드코딩되어 있던 부서를 기준정보로 적재합니다(멱등). 기존 부서는 건드리지 않습니다.')) return;
    await call('POST', '/seed');
  };

  const addDept = async (parentId: string) => {
    const id = prompt(`새 부서 ID (영소문자·숫자·_-, 2~32자)${parentId ? `\n상위: ${parentId}` : '\n(최상위)'}`);
    if (!id) return;
    const name = prompt('부서명(한글)');
    if (!name) return;
    await call('POST', '/departments', { dept_id: id.trim(), name_ko: name.trim(), parent_id: parentId });
  };

  const renameDept = async (d: Dept) => {
    const name = prompt('부서명 변경 (개정 시 새 버전이 되고 구판은 이력으로 남습니다)', d.name_ko);
    if (!name || name === d.name_ko) return;
    await call('PUT', `/departments/${d.dept_id}`, { name_ko: name.trim() });
  };

  const moveDept = async (d: Dept) => {
    const p = prompt(`'${d.name_ko}' 를 어느 부서 밑으로 옮길까요? (비우면 최상위)\n※ 자기 하위 부서로는 옮길 수 없습니다`, d.parent_id);
    if (p === null) return;
    await call('PUT', `/departments/${d.dept_id}`, { parent_id: p.trim() });
  };

  const retireDept = async (d: Dept) => {
    if (!confirm(`'${d.name_ko}' 를 폐지합니다.\n물리 삭제가 아니라 soft-retire 이며, 과거 산출물의 소유 부서 해석은 유지됩니다.`)) return;
    await call('DELETE', `/departments/${d.dept_id}`);
  };

  const showHistory = async (deptId: string) => {
    setSel(deptId); setHist([]);
    try {
      const r = await fetch(`${O}/departments/${deptId}/history`);
      if (r.ok) setHist((await r.json())?.data || []);
    } catch { /* 이력 없음은 치명적이지 않다 */ }
  };

  const addUser = async () => {
    const id = prompt('사용자 ID (영문·숫자·. _ - @, 1~64자)');
    if (!id) return;
    const name = prompt('표시 이름');
    if (!name) return;
    await call('POST', '/users', { user_id: id.trim(), display_name: name.trim() });
  };

  const toggleFlag = async (u: User, flag: 'is_admin' | 'is_executive' | 'is_data_admin') => {
    await call('POST', '/users', { ...u, [flag]: !u[flag] });
  };

  const setRole = async (u: User, deptId: string, role: string) => {
    const roles = { ...(u.roles || {}) };
    if (role) roles[deptId] = role; else delete roles[deptId];
    await call('PUT', `/users/${u.user_id}/roles`, { roles });
  };

  const canEdit = !!scope?.can_edit_org || !!scope?.unrestricted;

  const renderNode = (d: Dept, depth = 0) => (
    <li key={d.dept_id}>
      <div className="flex items-center gap-2 py-1.5 group" style={{ paddingLeft: depth * 18 }}>
        <span className="text-gray-600 text-xs">{d.children?.length ? '▾' : '·'}</span>
        <button onClick={() => showHistory(d.dept_id)}
          className={`text-sm ${sel === d.dept_id ? 'text-white font-semibold' : 'text-gray-300'} hover:text-white`}>
          {d.name_ko}
        </button>
        <span className="text-[10px] text-gray-600 font-mono">{d.dept_id}</span>
        <span className="text-[10px] text-gray-700">v{d.version}</span>
        {d.default_template_id && (
          <span className="text-[10px] text-indigo-500/80" title="기본 템플릿">{d.default_template_id}</span>
        )}
        {canEdit && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 ml-1">
            <IconBtn onClick={() => addDept(d.dept_id)} title="하위 부서 추가">＋</IconBtn>
            <IconBtn onClick={() => renameDept(d)} title="개명(개정)">✎</IconBtn>
            <IconBtn onClick={() => moveDept(d)} title="상위 부서 이동">⇄</IconBtn>
            <IconBtn onClick={() => retireDept(d)} title="폐지(soft-retire)" danger>⊘</IconBtn>
          </span>
        )}
      </div>
      {d.children?.length ? <ul>{d.children.map((c) => renderNode(c, depth + 1))}</ul> : null}
    </li>
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-6xl h-[88vh] bg-[#0B0C10] border border-[#1F2833] rounded-xl flex flex-col overflow-hidden">
        <header className="h-14 px-5 border-b border-[#1F2833] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-white">🏢 조직·권한</h2>
            <span className="text-xs text-gray-500">부서는 기준정보 — 개편하면 새 버전이 되고 구판은 이력으로 보존됩니다</span>
          </div>
          <div className="flex items-center gap-2">
            <input value={asUser} onChange={(e) => setAsUser(e.target.value)} placeholder="사용자로 보기(ID)"
              className="px-2 py-1 text-xs bg-[#141a21] border border-[#1F2833] rounded text-gray-300 w-40"
              title="이 ID 로 권한을 해석해 화면을 그립니다(X-User-Id 헤더)" />
            <button onClick={seed} disabled={!canEdit}
              className="px-3 py-1.5 text-xs rounded bg-[#1F2833] hover:bg-[#2b3a49] text-gray-300 disabled:opacity-40"
              title="코드에 하드코딩되어 있던 부서를 기준정보로 적재(멱등)">부서 시드</button>
            <button onClick={onClose} className="px-3 py-1.5 text-xs rounded bg-[#1F2833] hover:bg-[#2b3a49] text-gray-300">닫기</button>
          </div>
        </header>

        {scope && (
          <div className="px-5 py-2 text-[11px] border-b border-[#1F2833] shrink-0 flex items-center gap-3 flex-wrap">
            <span className="text-gray-500">현재 권한:</span>
            <Badge on={scope.unrestricted} label="무제한" hint="조직 미도입/부트스트랩/강제해제 상태" />
            <Badge on={scope.can_edit_org} label="조직편집" />
            <Badge on={scope.can_run_enterprise} label="전사실행" />
            <Badge on={scope.can_manage_standard} label="표준관리" />
            {!scope.unrestricted && (
              <span className="text-gray-600">읽기 {scope.readable_dept_ids.length}개 · 쓰기 {scope.writable_dept_ids.length}개</span>
            )}
          </div>
        )}
        {(busy || err) && (
          <div className={`px-5 py-2 text-xs shrink-0 ${err ? 'text-red-400 bg-red-950/30' : 'text-indigo-300 bg-indigo-950/20'}`}>
            {err || busy}
          </div>
        )}

        <div className="flex border-b border-[#1F2833] shrink-0">
          {(['dept', 'user'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-5 py-2.5 text-xs font-semibold ${tab === t ? 'bg-[#1F2833] text-white' : 'text-gray-500 hover:text-gray-300'}`}>
              {t === 'dept' ? `조직도 (${flat.length})` : `사용자 (${users.length})`}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-5 min-h-0">
          {tab === 'dept' && (
            <div className="flex gap-6">
              <div className="flex-1 min-w-0">
                {canEdit && (
                  <button onClick={() => addDept('')} className="mb-2 text-xs text-indigo-400 hover:text-indigo-300">
                    ＋ 최상위 부서 추가
                  </button>
                )}
                {tree.length === 0 && !busy && (
                  <p className="text-sm text-gray-600">
                    등록된 부서가 없습니다. <b>부서 시드</b>로 기존 하드코딩 부서를 적재하거나 직접 추가하세요.
                    <br /><span className="text-xs">부서가 없으면 권한 필터가 전부 무효(기존과 동일 동작)입니다.</span>
                  </p>
                )}
                <ul>{tree.map((d) => renderNode(d))}</ul>
              </div>
              {hist.length > 0 && (
                <aside className="w-72 shrink-0 border-l border-[#1F2833] pl-4">
                  <h4 className="text-xs font-semibold text-gray-400 mb-2">{sel} 개편 이력</h4>
                  <table className="w-full text-[11px]">
                    <tbody>
                      {hist.map((h) => (
                        <tr key={h.version} className="border-b border-[#1F2833]/60 text-gray-500">
                          <td className="py-1 pr-2">v{h.version}</td>
                          <td className="pr-2">{h.name_ko}</td>
                          <td className={h.status === 'active' ? 'text-emerald-500' : ''}>{h.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-2 text-[10px] text-gray-600 leading-relaxed">
                    구판이 보존되므로 과거 산출물의 소유 부서를 계속 해석할 수 있습니다.
                  </p>
                </aside>
              )}
            </div>
          )}

          {tab === 'user' && (
            <div>
              {canEdit && (
                <button onClick={addUser} className="mb-3 text-xs text-indigo-400 hover:text-indigo-300">＋ 사용자 추가</button>
              )}
              {users.length === 0 && !busy && (
                <p className="text-sm text-gray-600">
                  등록된 사용자가 없습니다.
                  <br /><span className="text-xs">사용자가 0명이면 권한을 강제하지 않습니다 — 첫 관리자를 만들 수 있도록 하기 위함입니다.</span>
                </p>
              )}
              <div className="space-y-2">
                {users.map((u) => (
                  <div key={u.user_id} className="border border-[#1F2833] rounded p-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-gray-200">{u.display_name}</span>
                      <span className="text-[11px] text-gray-600 font-mono">{u.user_id}</span>
                      <span className="flex gap-1 ml-auto">
                        <Flag on={u.is_admin} label="관리자" hint="전권(조직·표준·전사실행)"
                          onClick={() => canEdit && toggleFlag(u, 'is_admin')} />
                        <Flag on={u.is_executive} label="경영진" hint="전 부서 열람 + 전사 실행. 조직 편집은 불가"
                          onClick={() => canEdit && toggleFlag(u, 'is_executive')} />
                        <Flag on={u.is_data_admin} label="DA" hint="표준·카탈로그 전권 + 메타 전사 열람. 전사 실행은 불가"
                          onClick={() => canEdit && toggleFlag(u, 'is_data_admin')} />
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {flat.map((d) => {
                        const cur = u.roles?.[d.dept_id] || '';
                        return (
                          <select key={d.dept_id} value={cur} disabled={!canEdit}
                            onChange={(e) => setRole(u, d.dept_id, e.target.value)}
                            className={`text-[10px] px-1.5 py-0.5 rounded border bg-[#141a21] disabled:opacity-40 ${
                              cur ? 'border-indigo-700 text-indigo-300' : 'border-[#1F2833] text-gray-600'}`}
                            title={`${d.name_ko} — 상위 부서 권한은 하위로 상속됩니다`}>
                            <option value="">{d.name_ko} —</option>
                            {ROLES.map((r) => <option key={r} value={r}>{d.name_ko} · {r}</option>)}
                          </select>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function IconBtn({ children, onClick, title, danger }: any) {
  return (
    <button onClick={onClick} title={title}
      className={`px-1.5 text-xs rounded hover:bg-[#1F2833] ${danger ? 'text-red-400' : 'text-gray-500'}`}>
      {children}
    </button>
  );
}

function Badge({ on, label, hint }: { on: boolean; label: string; hint?: string }) {
  return (
    <span title={hint}
      className={`px-1.5 py-0.5 rounded ${on ? 'bg-emerald-900/40 text-emerald-300' : 'bg-[#1F2833] text-gray-600'}`}>
      {label}
    </span>
  );
}

function Flag({ on, label, hint, onClick }: any) {
  return (
    <button onClick={onClick} title={hint}
      className={`px-1.5 py-0.5 text-[10px] rounded border ${
        on ? 'bg-amber-900/40 text-amber-300 border-amber-700/50' : 'bg-[#141a21] text-gray-600 border-[#1F2833]'}`}>
      {label}
    </button>
  );
}
