import { useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080';
const S = `${API_BASE_URL}/api/v1/standards`;

interface StdRow {
  master_code: string; name: string; version: number; valid_from: string; status: string;
  type_id: string; kind: string; stage: string; agent_id: string; role_statement: string;
  pass_threshold: number | null; gate_count: number; advisory_count: number;
}
interface KindMeta { kind: string; type_id: string; label: string; desc: string; }
interface HistRow {
  version: number; name: string; valid_from: string; valid_to: string | null;
  status: string; source: string; updated_at: string;
}

// 📜 업무표준 — 에이전트의 '법규·사규'.
// 각 에이전트가 무엇을 어떤 기준으로 평가해 다음 단계로 넘기는지를 정의한 제도 문서다.
// 저장소는 M1 기준정보(master.db)이며 개정 시 새 버전이 생기고 구판은 리니지로 보존된다.
//   · 업무규정(regulation) — 판정 에이전트. 통과/반려 권한이 있고 기준값을 엄격히 따른다.
//   · 업무지침(guideline)  — 생성 에이전트. 작성 표준을 따르며 판정 권한이 없다.
export function WorkStandardPanel({ onClose }: { onClose: () => void }) {
  const [kinds, setKinds] = useState<KindMeta[]>([]);
  const [rows, setRows] = useState<StdRow[]>([]);
  const [tab, setTab] = useState<string>('regulation');
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [hist, setHist] = useState<HistRow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setBusy('목록 조회 중...');
    setErr(null);
    try {
      const [kr, lr] = await Promise.all([fetch(`${S}/kinds`), fetch(S)]);
      const kd = await kr.json();
      const ld = await lr.json();
      setKinds(kd?.data || []);
      setRows(ld?.data || []);
    } catch (e: any) {
      setErr(`조회 실패: ${e?.message || e}`);
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => { load(); }, []);

  const openDetail = async (stage: string) => {
    setSel(stage);
    setDetail(null);
    setHist([]);
    setBusy(`${stage} 표준 조회 중...`);
    try {
      const [dr, hr] = await Promise.all([fetch(`${S}/${stage}`), fetch(`${S}/${stage}/history`)]);
      const dd = await dr.json();
      setDetail(dd?.data || null);
      if (hr.ok) {
        const hd = await hr.json();
        setHist(hd?.data || []);
      }
    } catch (e: any) {
      setErr(`상세 조회 실패: ${e?.message || e}`);
    } finally {
      setBusy(null);
    }
  };

  const reseed = async () => {
    if (!confirm('코드 기본값에서 전 단계를 재등록합니다. 기존 개정본은 구판으로 보존되고 새 버전이 됩니다. 진행할까요?')) return;
    setBusy('재시드 중...');
    try {
      await fetch(`${S}/seed?force=true`, { method: 'POST' });
      await load();
      if (sel) await openDetail(sel);
    } catch (e: any) {
      setErr(`재시드 실패: ${e?.message || e}`);
    } finally {
      setBusy(null);
    }
  };

  const shown = rows.filter((r) => r.kind === tab);
  const std = detail?.standard;
  const checks: any[] = std?.checks || [];
  const gate = checks.filter((c) => !c.advisory);
  const adv = checks.filter((c) => c.advisory);
  const gateW = gate.reduce((s, c) => s + Number(c.weight ?? 1), 0);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-6xl h-[88vh] bg-gray-950 border border-gray-700 rounded-xl flex flex-col overflow-hidden">
        <header className="h-14 px-5 border-b border-gray-700 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-gray-100">📜 업무표준 (에이전트 법규)</h2>
            <span className="text-xs text-gray-500">
              각 에이전트가 어떤 기준으로 일하고 무엇을 확인해 넘기는지를 정의한 제도 문서
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={reseed}
              className="px-3 py-1.5 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-300"
              title="코드 기본값(criteria.py)에서 전 단계를 새 버전으로 재등록">기본값 재시드</button>
            <button onClick={onClose}
              className="px-3 py-1.5 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-300">닫기</button>
          </div>
        </header>

        {(busy || err) && (
          <div className={`px-5 py-2 text-xs shrink-0 ${err ? 'text-red-400 bg-red-950/30' : 'text-indigo-300 bg-indigo-950/20'}`}>
            {err || busy}
          </div>
        )}

        <div className="flex-1 flex min-h-0">
          {/* 좌: 분류 탭 + 목록 */}
          <aside className="w-80 border-r border-gray-700 flex flex-col shrink-0">
            <div className="flex border-b border-gray-700 shrink-0">
              {kinds.map((k) => (
                <button key={k.kind} onClick={() => setTab(k.kind)} title={k.desc}
                  className={`flex-1 px-3 py-2.5 text-xs font-semibold transition-colors ${
                    tab === k.kind ? 'bg-gray-800 text-gray-100' : 'text-gray-500 hover:text-gray-300'}`}>
                  {k.kind === 'regulation' ? '⚖️ 규정' : '📗 지침'}
                </button>
              ))}
            </div>
            <p className="px-4 py-2 text-[11px] leading-relaxed text-gray-500 border-b border-gray-700 shrink-0">
              {kinds.find((k) => k.kind === tab)?.desc}
            </p>
            <ul className="flex-1 overflow-y-auto">
              {shown.map((r) => (
                <li key={r.master_code}>
                  <button onClick={() => openDetail(r.stage)}
                    className={`w-full text-left px-4 py-3 border-b border-gray-700/60 hover:bg-gray-900 ${
                      sel === r.stage ? 'bg-gray-900' : ''}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-gray-200">{r.stage}</span>
                      <span className="text-[10px] text-gray-500">v{r.version}</span>
                    </div>
                    <div className="text-[11px] text-gray-500 mt-0.5">{r.agent_id || '—'}</div>
                    <div className="text-[10px] text-gray-600 mt-1">
                      관문 {r.gate_count}
                      {r.advisory_count > 0 && ` · 참고 ${r.advisory_count}`}
                      {r.gate_count === 0 && <span className="text-amber-500"> (반려 권한 없음)</span>}
                    </div>
                  </button>
                </li>
              ))}
              {shown.length === 0 && !busy && (
                <li className="px-4 py-6 text-xs text-gray-600">등록된 표준이 없습니다.</li>
              )}
            </ul>
          </aside>

          {/* 우: 상세 */}
          <section className="flex-1 overflow-y-auto p-5 min-w-0">
            {!std && <p className="text-sm text-gray-600">왼쪽에서 단계를 선택하세요.</p>}
            {std && (
              <div className="space-y-5">
                <div>
                  <div className="flex items-baseline gap-3 flex-wrap">
                    <h3 className="text-xl font-bold text-gray-100">{std._meta?.master_code}</h3>
                    <span className="text-xs text-gray-500">
                      v{std._meta?.version} · {std._meta?.source === 'registered' ? '등록 표준' : '코드 기본값(미등록)'}
                    </span>
                  </div>
                  {std.role_statement && (
                    <p className="mt-2 text-sm text-gray-300 leading-relaxed">{std.role_statement}</p>
                  )}
                </div>

                {std.standard_kind === 'guideline' ? (
                  <>
                    {std.inputs && <Field label="입력(근거)" value={std.inputs} />}
                    {std.deliverable && <Field label="산출물" value={std.deliverable} />}
                    <ListBlock title="반드시 포함할 것" items={std.must_include} />
                    <ListBlock title="작성 원칙" items={std.principles} />
                  </>
                ) : (
                  std.evaluates && <Field label="평가 대상" value={std.evaluates} />
                )}

                {gate.length > 0 ? (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-200 mb-2">
                      {std.standard_kind === 'guideline' ? '자가 점검 항목' : '통과/반려를 결정하는 항목'}
                      <span className="ml-2 text-xs font-normal text-indigo-400">
                        통과선 {(Number(std.pass_threshold) * gateW).toFixed(1)} / {gateW}
                        (임계 {std.pass_threshold})
                      </span>
                    </h4>
                    <table className="w-full text-xs">
                      <tbody>
                        {gate.map((c) => (
                          <tr key={c.id} className="border-b border-gray-700/60">
                            <td className="py-2 pr-3 align-top w-56">
                              <span className="text-gray-200 font-mono">{c.id}</span>
                              <span className="ml-1 text-gray-600">({c.weight})</span>
                              {(std.hard_fail_checks || []).includes(c.id) && (
                                <span className="ml-1 text-red-400" title="이 항목이 미달이면 즉시 차단">⛔</span>
                              )}
                            </td>
                            <td className="py-2 text-gray-400 leading-relaxed">{c.desc}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="px-3 py-2 rounded bg-amber-950/30 border border-amber-900/50 text-xs text-amber-300">
                    이 단계는 <b>관문이 아닙니다.</b> 반려 권한이 없으며 권고 의견만 남깁니다.
                  </div>
                )}

                {adv.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">
                      참고 항목 <span className="text-xs font-normal text-gray-600">— 반려 사유가 아님. 리포트로만 전달</span>
                    </h4>
                    <ul className="text-xs text-gray-500 space-y-1">
                      {adv.map((c) => (
                        <li key={c.id}><span className="font-mono text-gray-400">{c.id}</span> — {c.desc}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <ListBlock title="⚠️ 금지 사항" items={std.must_not} danger />

                {detail?.agent_brief && (
                  <details className="border border-gray-700 rounded">
                    <summary className="px-3 py-2 text-xs text-gray-400 cursor-pointer hover:text-gray-200">
                      에이전트가 실제로 받는 고지문 보기
                    </summary>
                    <pre className="px-3 py-2 text-[11px] text-gray-400 whitespace-pre-wrap leading-relaxed border-t border-gray-700">
                      {detail.agent_brief}
                    </pre>
                  </details>
                )}

                {hist.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">개정 연혁</h4>
                    <table className="w-full text-[11px]">
                      <thead className="text-gray-600">
                        <tr><th className="text-left py-1">버전</th><th className="text-left">시행일</th>
                          <th className="text-left">상태</th><th className="text-left">출처</th></tr>
                      </thead>
                      <tbody>
                        {hist.map((h) => (
                          <tr key={h.version} className="border-t border-gray-700/60 text-gray-500">
                            <td className="py-1">v{h.version}</td>
                            <td>{(h.valid_from || '').slice(0, 10)}</td>
                            <td className={h.status === 'active' ? 'text-emerald-500' : ''}>{h.status}</td>
                            <td>{h.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-gray-500">{label}</span>
      <p className="text-sm text-gray-300 mt-0.5 leading-relaxed">{value}</p>
    </div>
  );
}

function ListBlock({ title, items, danger }: { title: string; items?: string[]; danger?: boolean }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <h4 className={`text-sm font-semibold mb-1.5 ${danger ? 'text-red-400' : 'text-gray-200'}`}>{title}</h4>
      <ul className={`text-xs space-y-1 ${danger ? 'text-red-300/80' : 'text-gray-400'}`}>
        {items.map((m, i) => <li key={i} className="leading-relaxed">· {m}</li>)}
      </ul>
    </div>
  );
}
