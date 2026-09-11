// Actual product form and request serializer. All network requests stop in memory.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CreateScreen } from '../src/features/collaboration/DecisionCenter';
import { decisionApi, evidenceBasisLabel, type DecisionCreateBody } from '../src/lib/decisionApi';
import '../src/index.css';
import '../src/design/afs.css';

const requests: { url: string; method: string; body: DecisionCreateBody }[] = [];
window.fetch = async (input, init) => {
  const url = String(input);
  if (init?.method !== 'POST' || !url.endsWith('/api/v1/simulations/sim_server_only/decision-cases')) {
    throw new Error('격리 시험: 예상하지 않은 요청 차단');
  }
  const body = JSON.parse(String(init.body)) as DecisionCreateBody;
  requests.push({ url, method: init.method, body });
  return new Response(JSON.stringify({ status: 'success', data: {
    decision_id: 'synthetic-only', evidence_basis: body.evidence_basis,
  } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
};

function Fixture() {
  const [receipt, setReceipt] = useState('아직 요청하지 않음');
  return <main className="afs-scope" style={{ maxWidth: 980, margin: '24px auto', padding: 20 }}>
    <h1>합성 자료 격리 시험 — 운영 저장 없음</h1>
    <CreateScreen sources={{ status: 'ok', value: [{ run_id: 'sim_server_only',
      label: '합성 시나리오 · 2027 · 계획 기준', scenario_label: '합성 시나리오',
      baseline_label: '2027 · 계획 기준', completed_at: '', engine_version: '1.0.0',
      bindable: true, blocked_reason: '' }] }}
      onRetrySources={() => {}} onCancel={() => {}}
      onSubmit={async (runId, body) => {
        const saved = await decisionApi.create(runId, body);
        setReceipt(JSON.stringify({ count: requests.length, label: evidenceBasisLabel(saved.evidence_basis),
          request: requests.at(-1) }, null, 2));
      }} />
    <h2>실제 요청 직렬화 결과 (응답은 합성)</h2>
    <pre id="request-receipt" aria-live="polite" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{receipt}</pre>
    <p id="legacy-basis">{evidenceBasisLabel('UNSTATED')}</p>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
