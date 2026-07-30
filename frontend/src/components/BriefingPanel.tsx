import { useEffect, useState } from 'react';
import {
  BRIEFING_SECTIONS, SECTION_LABELS, fetchBriefing,
  type Briefing, type BriefingItem, type BriefingSection, type CostSection,
} from '../lib/briefingApi';

// [M5] 전사 브리핑 화면 (제품 성경 §5.5)
//
// ⚠️ 이 화면이 지켜야 할 것:
//   1. **`complete=false` 를 숨기지 않는다.** "위험 0건"과 "위험을 못 읽었다"는 다른 사실이고,
//      후자를 초록불로 그리면 그 순간 이 화면은 거짓 보고를 한다.
//   2. **항목마다 "무엇을 하면 풀리는가"를 함께 보여준다.** 상태만 나열하면 대시보드지 보좌가 아니다.
//   3. **비용 총액이 하한이면 `≥` 를 붙인다.** 단가 미등록 호출이 있는데 완전한 총액처럼
//      보이면 예산 판단이 틀린다(TelemetryPanel 과 같은 규칙).
//
// 디자인 시안 확정 시 교체 대상(§7 역할 규약) — 데이터는 lib/briefingApi.ts 에 분리했다.

const SEV_STYLE: Record<string, string> = {
  high: 'border-red-500/60 bg-red-500/10 text-red-200',
  medium: 'border-amber-500/50 bg-amber-500/10 text-amber-200',
  low: 'border-slate-600 bg-slate-800/50 text-slate-300',
  info: 'border-slate-700 bg-slate-800/30 text-slate-400',
};
const SEV_LABEL: Record<string, string> = {
  high: '높음', medium: '보통', low: '낮음', info: '참고',
};

function Item({ it }: { it: BriefingItem }) {
  return (
    <div className={`border rounded px-3 py-2 ${SEV_STYLE[it.severity] || SEV_STYLE.info}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold break-words">{it.title}</div>
          <div className="text-[11px] opacity-80 mt-0.5 break-words">{it.why}</div>
          {/* ★ 상태만 나열하면 대시보드다 — 다음 행동이 항목과 같은 자리에 있어야 한다 */}
          {it.suggested_action && (
            <div className="text-[11px] mt-1 break-words">
              <span className="opacity-60">→ </span>{it.suggested_action}
            </div>
          )}
        </div>
        <span className="text-[10px] shrink-0 opacity-70">{SEV_LABEL[it.severity]}</span>
      </div>
      {it.ref && (
        <div className="text-[10px] opacity-50 mt-1 font-mono">{it.ref_type}: {it.ref}</div>
      )}
    </div>
  );
}

function CostBlock({ c }: { c: CostSection }) {
  if (!c.available) {
    return (
      <div className="text-xs text-amber-300">
        비용을 읽지 못했습니다 — {c.reason || '원인 미상'}.
        <span className="text-amber-400/70"> (0 으로 표시하지 않습니다)</span>
      </div>
    );
  }
  // 단가 미등록이 있으면 총액은 **하한**이다.
  const prefix = c.cost_complete === false ? '≥ ' : '';
  return (
    <div className="flex gap-6 flex-wrap text-sm">
      <div>
        <span className="text-[11px] text-slate-400">LLM 비용</span>
        <div className="text-lg font-bold">{prefix}${(c.cost_usd ?? 0).toFixed(4)}</div>
        {c.cost_complete === false && (
          <div className="text-[10px] text-amber-400">
            단가 미등록 {c.unpriced_calls}건 — 총액은 하한입니다
          </div>
        )}
      </div>
      <div>
        <span className="text-[11px] text-slate-400">호출</span>
        <div className="text-lg">{(c.calls ?? 0).toLocaleString()}</div>
      </div>
    </div>
  );
}

export function BriefingPanel({ onClose }: { onClose: () => void }) {
  const [scope, setScope] = useState('');
  const [b, setB] = useState<Briefing | null>(null);
  const [perm, setPerm] = useState<any>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(true);

  const load = () => {
    setBusy(true);
    setErr('');
    fetchBriefing(scope || undefined)
      .then((r) => { setB(r.data); setPerm(r.permission); })
      .catch((e: Error) => { setB(null); setErr(e.message); })
      .finally(() => setBusy(false));
  };

  useEffect(load, []);

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 text-slate-200 overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">전사 브리핑</h2>
            <p className="text-[11px] text-slate-400">
              권한 범위 안의 상태를 결정론적으로 모았습니다(LLM 0콜).
              {b && <> · {b.generated_at?.slice(0, 16)} · {b.actor || '(식별 없음)'}</>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input value={scope} onChange={(e) => setScope(e.target.value)}
                   placeholder="조직 범위(비우면 전체)"
                   className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs w-48" />
            <button onClick={load} disabled={busy}
                    className="px-3 py-1 text-xs bg-blue-600 rounded disabled:opacity-50">
              {busy ? '집계 중…' : '새로고침'}
            </button>
            <button onClick={onClose} className="px-3 py-1 text-xs bg-slate-600 rounded">닫기</button>
          </div>
        </header>

        {err && (
          <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs
                          rounded px-3 py-2">{err}</div>
        )}

        {/* ★★ 불완전한 브리핑을 초록불로 그리지 않는다 — 숫자보다 **위**에 온다.
            "위험 0건"과 "위험을 못 읽었다"는 다른 사실이다. */}
        {b && !b.complete && (
          <section className="border border-red-500/60 bg-red-500/10 rounded p-4 space-y-2">
            <h3 className="text-sm font-bold text-red-200">
              ⚠️ 이 브리핑은 완전하지 않습니다
            </h3>
            <p className="text-xs text-red-200">{b.note}</p>
            {b.unavailable?.length > 0 && (
              <ul className="text-[11px] text-red-200/90 space-y-0.5">
                {b.unavailable.map((u, i) => (
                  <li key={i}>
                    · <b>{SECTION_LABELS[u.section as BriefingSection] || u.section}</b> —
                    {' '}{u.source}: {u.error}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {b && (
          <>
            {/* 주의가 필요한 것 */}
            <section className="border border-slate-700 rounded p-4">
              <div className="flex items-baseline gap-4 flex-wrap">
                <div>
                  <span className="text-[11px] text-slate-400">주의 필요</span>
                  <div className={`text-2xl font-bold ${
                    b.attention_count > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {b.attention_count}건
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {Object.entries(b.by_severity || {}).map(([sev, n]) => (
                    <span key={sev}
                          className={`text-[11px] border rounded px-2 py-0.5 ${
                            SEV_STYLE[sev] || SEV_STYLE.info}`}>
                      {SEV_LABEL[sev] || sev} {n}
                    </span>
                  ))}
                </div>
                {b.scope?.filtered && (
                  <span className="text-[10px] text-slate-500">
                    범위: {perm?.scope || b.scope.scope_node_id}
                  </span>
                )}
              </div>

              {b.top?.length > 0 && (
                <div className="mt-3 space-y-2">
                  <h4 className="text-xs font-bold text-slate-300">먼저 볼 것</h4>
                  {b.top.map((it, i) => <Item key={i} it={it} />)}
                </div>
              )}
            </section>

            {/* 섹션별 */}
            {BRIEFING_SECTIONS.map((name) => {
              if (name === 'cost') {
                return (
                  <section key={name} className="border border-slate-700 rounded p-4">
                    <h3 className="text-sm font-bold text-slate-200 mb-2">
                      {SECTION_LABELS[name]}
                    </h3>
                    <CostBlock c={b.sections.cost} />
                  </section>
                );
              }
              const sec = b.sections[name];
              if (!sec) return null;
              return (
                <section key={name} className="border border-slate-700 rounded p-4">
                  <h3 className="text-sm font-bold text-slate-200 mb-2">
                    {SECTION_LABELS[name]}
                    <span className="text-slate-500 font-normal"> ({sec.count}건)</span>
                  </h3>
                  {sec.items.length === 0 ? (
                    <p className="text-xs text-slate-500">해당 항목이 없습니다.</p>
                  ) : (
                    <div className="space-y-2">
                      {sec.items.map((it, i) => <Item key={i} it={it} />)}
                    </div>
                  )}
                </section>
              );
            })}
          </>
        )}

        {!b && !busy && !err && (
          <p className="text-xs text-slate-500">브리핑을 불러오지 못했습니다.</p>
        )}
      </div>
    </div>
  );
}
