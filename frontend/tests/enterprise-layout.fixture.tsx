// Layout-only fixture: real UI components, no App/authentication, no backend/LLM/DB.
// Never import this entry from the product. All fetches terminate in this file.
import React from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import '../src/design/afs.css';
import { ProductShell } from '../src/components/ProductShell';
import { EnterprisePage } from '../src/components/EnterprisePage';

const params = new URLSearchParams(location.search);
const long = params.has('long');
const count = params.has('many') ? 12 : 7;
const labels = ['원료조달', '수주·판매', '생산계획', '제련·생산', '품질', '물류·출하', '손익·경영'];
const nodes = Array.from({ length: count }, (_, i) => ({
  key: `layout-${i}`, label: labels[i % labels.length], note: '업무 자료와 시나리오 연결',
  overlay: i === 2 ? null : {
    layer: ['DATA', 'SW', 'TWIN'][i % 3],
    kicker: '레이아웃 시험용 합성 자료',
    body: `${labels[i % labels.length]} 입력 자료 120건 · 검토 결과 6건`,
  },
}));
const canvas = {
  domain_nodes: nodes.map((n, i) => ({ ...n, id: n.key, sequence: i + 1, systems: '', status: 'normal' })),
  decision_queue: Array.from({ length: 16 }, (_, i) => ({
    ref: `layout-${i}`, ref_type: 'decision', kind: 'decision', section: 'my_decisions',
    title: `${i + 1}. 원료 도입 일정과 생산계획을 함께 검토합니다${long ? ' — 원료별 입고 지연과 대체 조달 및 고객별 납기 조정 방안 비교'.repeat(4) : ''}`,
    why: '배치 검증용 합성 자료입니다. 원료 수급과 납기를 같은 기준으로 검토합니다. '.repeat(long ? 15 : 1),
    severity: 'high', data_kind: 'SYNTHETIC', impact_rows: [],
  })),
  unavailable: [], cost_summary: {},
};
window.fetch = async (input) => {
  const url = String(input instanceof Request ? input.url : input);
  let data: unknown;
  if (url.includes('/briefing/canvas')) data = canvas;
  else if (url.includes('/profiles')) data = [{ is_effective: true, payload: { nodes } }];
  else if (url.includes('/briefing')) data = { sections: {}, generated_at: '2026-09-08T09:00:00Z' };
  else if (url.includes('/org/me')) data = { capabilities: [], unrestricted: false };
  else if (url.includes('/master/types') || url.includes('/knowledge/packs')) data = [{}, {}, {}];
  else if (url.includes('/readiness')) data = { status: 'READY', gates: [], datasets: [] };
  else if (url.includes('/instances')) data = { instances: [] };
  else if (url.includes('/health')) return Response.json({ status: 'ok' });
  else data = [];
  return Response.json({ status: 'ok', data });
};
const noop = () => {};
createRoot(document.getElementById('root')!).render(
  <div className="afs-scope enterprise-home">
    <ProductShell module="enterprise" company="LS MnM" scope="레이아웃 검증 · 합성 자료" entityMode="VIRTUAL"
      onNav={noop} onContext={noop} onAbout={noop} onSettings={noop} onNewWork={noop}
      right={<><span style={{ color: '#fff', fontSize: 12 }}>검증 사용자</span><button className="afs-icon-action" style={{ width: 90 }}>초기 비밀번호</button><button className="afs-icon-action">⏻</button><button className="afs-icon-action" style={{ width: 54 }}>☰ 26</button></>} />
    <EnterprisePage onOpenBuild={noop} onOpenDataReadiness={noop} onOpenMenu={noop} />
  </div>,
);
