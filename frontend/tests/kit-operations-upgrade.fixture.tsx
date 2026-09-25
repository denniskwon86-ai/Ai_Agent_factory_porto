// 실제 제품 패널(KitOperationsPanel → KitAppPanel)을 쓰고, API 는 이 페이지 안의 합성 응답이다.
// 서버·DB·로그인·운영 데이터를 쓰지 않는다. 판본 업그레이드의 목록 표시(Codex §19.3·§20)만 본다.
import { createRoot } from 'react-dom/client';
import { KitOperationsPanel } from '../src/components/KitOperationsPanel';
import '../src/index.css';
import '../src/design/afs.css';

type State = 'active' | 'awaiting' | 'stuck';
const state = (new URLSearchParams(location.search).get('state') || 'active') as State;
const digest = (c: string) => c.repeat(64);
const INSTANCE_ID = 'SYNTHETIC-ki-upgrade';
const base = { instance_id: INSTANCE_ID, label: '합성 비철 구매 적용본', kit_id: 'KIT-MFG-NONFERROUS-PROCUREMENT',
  kit_fingerprint: digest('a'), tenant_id: 'SYNTHETIC-TENANT', scope_node_id: 'SYNTHETIC-SCOPE',
  entity_mode: 'REAL', status: 'active', installed_version: '1.1.0' };
const instances: Record<State, Record<string, unknown>> = {
  active: { ...base, version: '1.2.0', active_artifact_digest: digest('b'), pending_upgrade: null },
  awaiting: { ...base, version: '1.1.0', active_artifact_digest: digest('a'), pending_upgrade: {
    state: 'AWAITING_APPROVAL', version: '1.2.0', artifact_digest: digest('b'), operation_id: 'SYNTHETIC-op' } },
  stuck: { ...base, version: '1.1.0', active_artifact_digest: digest('a'), pending_upgrade: {
    state: 'ACTIVATION_PENDING', version: '1.2.0', artifact_digest: digest('b'), operation_id: 'SYNTHETIC-op',
    activation_error: 'PROCESS_STORAGE_UNAVAILABLE' } },
};
const app = { app_id: 'APP-03', label: '재고 가용성(합성)', readiness_state: 'AVAILABLE', user_message: '',
  next_action: '', contract_schema_version: '2.0', contract_status: 'APPROVED', contract_revision: 2,
  drafted_by: 'synthetic-member', approved_by: 'synthetic-admin', permitted_actions: ['read'],
  release_id: `kitapp_${INSTANCE_ID}_APP-03_${'b'.repeat(16)}`, lifecycle_state: 'active', built_datasets: 2,
  release_history: [{ release_id: `kitapp_${INSTANCE_ID}_APP-03`, kit_version: '1.1.0', artifact_digest: digest('a'),
    current: false, lifecycle_state: 'active' }] };

const requests: string[] = [];
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' } });
// 제품 API 를 잘못 연결해도 네트워크로 나가지 않도록 fetch 를 닫는다(HTML 의 connect-src 'none' 도 함께).
window.fetch = async (input: RequestInfo | URL) => {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href);
  requests.push(url.pathname);
  (window as unknown as { __requests: string[] }).__requests = requests;
  if (url.pathname === '/api/v1/data-preparation/instances') {
    return json(200, { status: 'success', data: { instances: [instances[state]] } });
  }
  if (url.pathname === `/api/v1/data-preparation/instances/${INSTANCE_ID}/apps`) {
    return json(200, { status: 'success', data: { instance_id: INSTANCE_ID, apps: state === 'active' ? [app]
      : [{ ...app, release_id: `kitapp_${INSTANCE_ID}_APP-03`, release_history: [] }] } });
  }
  if (url.pathname === '/api/v1/auth/me') return json(200, { status: 'success', data: { user_id: 'synthetic-viewer' } });
  // ⚠️ 404 로 답하지 않는다: 계약 검토가 401·403·404 를 받으면 «보이지 않게 됨» 으로 목록을 다시 불러
  //   무한 반복한다(별도 작업으로 넘긴 기존 결함). 합성 응답이 없는 경로는 «지금 확인 못 함»(503)이다.
  return json(503, { detail: 'SYNTHETIC fixture: 합성 응답이 없는 경로' });
};

function Fixture() {
  return <main className="afs-scope" style={{ maxWidth: 1120, margin: '24px auto', padding: 20 }}>
    <section aria-label="합성 시험 안내" style={{ border: '2px solid #eab308', borderRadius: 12, padding: 16, marginBottom: 16 }}>
      <h1>SYNTHETIC / 합성 응답 — 앱 운영 판본 표시 시험</h1>
      <p>실제 제품 패널을 씁니다. 목록·앱 응답은 이 페이지의 합성 값이며 서버·DB·로그인은 호출하지 않습니다.</p>
      <p>상태: {state} · <a href="?state=active">활성(1.2.0)</a> · <a href="?state=awaiting">승인 대기</a> · <a href="?state=stuck">활성화 대기</a></p>
    </section>
    <KitOperationsPanel onOpenBuild={() => undefined} />
  </main>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
