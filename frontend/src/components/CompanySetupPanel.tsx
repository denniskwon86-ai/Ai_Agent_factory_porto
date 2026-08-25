import { useCallback, useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { setEnterpriseContext } from '../lib/api';
import {
  approveEntity, approveProfile, createEntity, createNode, getTree, listEntities,
  listProfiles, listTenants, saveProfile, selectContext, upsertTenant,
  type EcmNode, type Entity, type Profile, type Tenant, type ThreadNode,
} from '../lib/companyApi';
import { useOperatingContext } from '../lib/operatingContext';

// [ECM §4·§9] **회사 구성** — 회사 이름 · 법인/가상회사 · 조직 노드 · Digital Thread 연결구성.
//
// ## ⚠️⚠️ [2026-08-25 사용자 지적] 왜 이 화면이 생겼는가
//
// > 회사 구성 정보를 등록하는 화면이 없는 것 같네요. 가상회사를 구성하고 선택할 수도
// > 있어야 합니다. ENTERPRISE DIGITAL THREAD 이 연결구성을 각 회사별로 설정할 수 있도록
//
// 백엔드는 **이미 다 있었다** — `enterprise_entities`(entity_mode · base_entity_id) ·
// `organization_nodes` · `enterprise_profiles`(process_profile) · `contexts/select`.
// 없는 것은 부르는 화면뿐이었다.
//
// ## ★ 이 화면이 지키는 것
//
// · **실제/가상/경쟁사를 항상 눈에 보이게 갈라 놓는다** — 시나리오 회사의 숫자가 실적으로
//   읽히는 것이 이 시스템에서 가장 위험한 실패다(비협상 3).
// · **승인 전에는 DRAFT 다.** 미승인 구성은 상속·판정에 참여하지 않는다(§4.1).
// · 문맥 전환은 **서버가 허가한 뒤에** 바꾼다 — 통과하지 않은 문맥으로 화면을 바꾸면
//   보이는 것과 권한이 갈린다.

const MODE_KO: Record<string, string> = {
  REAL: '실제', VIRTUAL: '가상', COMPETITOR: '경쟁사',
};
const MODE_TONE: Record<string, string> = {
  REAL: 'var(--state-success-fg)',
  VIRTUAL: '#7c3aed',
  COMPETITOR: 'var(--state-warn-fg)',
};

type Tab = 'company' | 'entity' | 'thread';

function Section({ title, desc, children }: {
  title: string; desc?: string; children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: 22 }}>
      <h3 style={{ fontSize: 15, margin: '0 0 2px' }}>{title}</h3>
      {desc && <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 8 }}>
        {desc}</div>}
      {children}
    </section>
  );
}

function Notice({ tone, children }: { tone: 'ok' | 'err'; children: React.ReactNode }) {
  return (
    <div style={{
      marginTop: 8, padding: '6px 10px', fontSize: 13, borderRadius: 6,
      background: tone === 'ok' ? 'var(--state-success-bg)' : 'var(--state-error-bg)',
      border: `1px solid ${tone === 'ok' ? 'var(--state-success-fg)' : 'var(--state-error-fg)'}`,
    }}>{children}</div>
  );
}

/** 트리를 평평하게 — 노드를 고를 수 있어야 연결구성을 어디에 붙일지 정한다. */
function flatten(rows: EcmNode[], depth = 0): (EcmNode & { _d: number })[] {
  const out: (EcmNode & { _d: number })[] = [];
  for (const n of rows || []) {
    out.push({ ...n, _d: depth });
    if (n.children?.length) out.push(...flatten(n.children, depth + 1));
  }
  return out;
}

export function CompanySetupPanel({ onClose }: { onClose: () => void }) {
  const ctx = useOperatingContext();
  const [tab, setTab] = useState<Tab>('company');
  const [tenants, setTenants] = useState<Tenant[] | null>(null);
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [nodes, setNodes] = useState<EcmNode[] | null>(null);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      //: ⚠️ 셋을 따로 받는다 — 하나가 실패해도 나머지는 보여야 한다.
      //:   전부 묶어 실패시키면 「회사가 없다」로 읽힌다.
      try { const r = await listTenants(); if (alive) setTenants(r); }
      catch (e: any) { if (alive) setErr(e?.message || '회사 목록을 읽지 못했습니다.'); }
      try { const r = await listEntities(); if (alive) setEntities(r); } catch { /* null 유지 */ }
      try { const r = await getTree(); if (alive) setNodes(r); } catch { /* null 유지 */ }
    })();
    return () => { alive = false; };
  }, [tick]);

  const run = useCallback(async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what); setErr(''); setOk('');
    try {
      await fn();
      setOk(`${what}을(를) 마쳤습니다.`);
      setTick((t) => t + 1);
    } catch (e: any) {
      //: ⚠️ 사유를 삼키지 않는다. 403 이면 권한이고, 그때 할 일은 관리자에게 요청하는 것이다.
      setErr(e?.status === 403
        ? '조직·사용자 편집 권한이 필요합니다(관리자 전용).'
        : (e?.message || `${what}에 실패했습니다.`));
    } finally { setBusy(''); }
  }, []);

  return (
    <HubDialog label="회사 구성" onClose={onClose}
      subtitle="회사 이름 · 법인과 가상회사 · 업무 연결구성(Digital Thread)">
      <div style={{ padding: 16, minWidth: 0 }}>
        {/* ★ 지금 어느 회사·어느 모드인지 **항상** 위에 둔다(채택 결정 6항). */}
        <div style={{
          display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap',
          padding: '8px 12px', borderRadius: 6, marginBottom: 14,
          background: 'var(--surface-raised)', border: '1px solid var(--surface-border)',
        }}>
          <strong style={{ fontSize: 14 }}>{ctx.companyName || ctx.company || '회사 미확인'}</strong>
          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>{ctx.company}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: MODE_TONE[ctx.entityMode] }}>
            {MODE_KO[ctx.entityMode] || ctx.entityMode} 실행 문맥
          </span>
          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
            · {ctx.scopeLabel}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {([['company', '회사 이름'], ['entity', '법인 · 가상회사'],
             ['thread', '업무 연결구성']] as [Tab, string][]).map(([id, label]) => (
            <button key={id} type="button" onClick={() => { setTab(id); setErr(''); setOk(''); }}
              style={{
                fontSize: 13, padding: '6px 12px', borderRadius: 6,
                border: '1px solid var(--surface-border-control)',
                background: tab === id ? 'var(--surface-selected)' : 'transparent',
                fontWeight: tab === id ? 700 : 400,
              }}>{label}</button>
          ))}
        </div>

        {err && <Notice tone="err">{err}</Notice>}
        {ok && <Notice tone="ok">{ok}</Notice>}

        {tab === 'company' && (
          <CompanyTab tenants={tenants} busy={busy} run={run} current={ctx.company} />
        )}
        {tab === 'entity' && (
          <EntityTab entities={entities} nodes={nodes} busy={busy} run={run}
            currentMode={ctx.entityMode} />
        )}
        {tab === 'thread' && (
          <ThreadTab nodes={nodes} busy={busy} run={run} />
        )}
      </div>
    </HubDialog>
  );
}

// ── ① 회사 이름 ──────────────────────────────────────────────────────────

function CompanyTab({ tenants, busy, run, current }: {
  tenants: Tenant[] | null; busy: string; current: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [legal, setLegal] = useState('');

  return (
    <>
      <Section title="등록된 회사"
        desc="상단 문맥에 보이는 이름입니다. 등록하지 않으면 화면이 식별자를 그대로 씁니다.">
        {tenants === null ? (
          // ⚠️ 「못 읽음」과 「0건」을 섞지 않는다.
          <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
            지금 확인하지 못했습니다 — 없다는 뜻은 아닙니다.
          </div>
        ) : tenants.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
            아직 등록된 회사가 없습니다.
          </div>
        ) : (
          <ul style={{ padding: 0, margin: 0, listStyle: 'none', display: 'grid', gap: 6 }}>
            {tenants.map((t) => (
              <li key={t.tenant_id} style={{
                display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap',
                padding: '8px 10px', borderRadius: 6,
                border: '1px solid var(--surface-border)',
                background: t.tenant_id === current ? 'var(--surface-selected)' : 'transparent',
              }}>
                <strong style={{ fontSize: 14 }}>{t.name_ko}</strong>
                {t.legal_name && <span style={{ fontSize: 12 }}>{t.legal_name}</span>}
                <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                  {t.tenant_id}</span>
                {t.tenant_id === current && (
                  <span style={{ fontSize: 12, fontWeight: 700 }}>· 지금 보는 회사</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="회사 이름 등록 · 변경"
        desc="같은 식별자로 다시 저장하면 이름이 바뀝니다. 이름은 비울 수 없습니다.">
        <div style={{ display: 'grid', gap: 6, maxWidth: 560 }}>
          <input value={id} onChange={(e) => setId(e.target.value)}
            placeholder="회사 식별자 — 예: tenant-afs-demo-materials"
            style={{ fontSize: 13, padding: '6px 9px' }} />
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="회사 이름 — 예: LS MnM"
            style={{ fontSize: 13, padding: '6px 9px' }} />
          <input value={legal} onChange={(e) => setLegal(e.target.value)}
            placeholder="법인명(선택) — 예: LS엠엔엠 주식회사"
            style={{ fontSize: 13, padding: '6px 9px' }} />
          <div>
            <button type="button" disabled={!id.trim() || !name.trim() || !!busy}
              onClick={() => void run('회사 이름 저장',
                () => upsertTenant({ tenant_id: id.trim(), name_ko: name.trim(),
                  legal_name: legal.trim() }))}
              style={{ fontSize: 13, padding: '6px 14px', fontWeight: 600 }}>
              {busy === '회사 이름 저장' ? '저장 중…' : '저장'}
            </button>
          </div>
        </div>
      </Section>
    </>
  );
}

// ── ② 법인 · 가상회사 ────────────────────────────────────────────────────

function EntityTab({ entities, nodes, busy, run, currentMode }: {
  entities: Entity[] | null; nodes: EcmNode[] | null; busy: string; currentMode: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [mode, setMode] = useState('');
  const [base, setBase] = useState('');
  const flat = flatten(nodes || []);

  return (
    <>
      <Section title="등록된 법인 · 가상회사"
        desc="실제·가상·경쟁사는 한 트리에 섞이지 않습니다 — 지금 문맥의 모드에 해당하는 것만 보입니다.">
        {entities === null ? (
          <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
            지금 확인하지 못했습니다 — 없다는 뜻은 아닙니다.
          </div>
        ) : entities.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
            현재 문맥({MODE_KO[currentMode] || currentMode})에 등록된 것이 없습니다.
          </div>
        ) : (
          <ul style={{ padding: 0, margin: 0, listStyle: 'none', display: 'grid', gap: 6 }}>
            {entities.map((e) => (
              <li key={e.entity_id} style={{
                display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap',
                padding: '8px 10px', borderRadius: 6,
                border: '1px solid var(--surface-border)',
              }}>
                <strong style={{ fontSize: 14 }}>{e.name_ko}</strong>
                {/* ★ 색만으로 말하지 않는다 — 모드 이름을 함께 적는다. */}
                <span style={{ fontSize: 12, fontWeight: 700, color: MODE_TONE[e.entity_mode] }}>
                  {MODE_KO[e.entity_mode] || e.entity_mode}
                </span>
                <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                  {e.entity_type}</span>
                {e.base_entity_id && (
                  <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    · 원본 {e.base_entity_id}</span>
                )}
                <span style={{
                  fontSize: 12, fontWeight: 700,
                  color: e.status === 'ACTIVE' ? 'var(--state-success-fg)'
                    : 'var(--state-warn-fg)',
                }}>
                  {e.status === 'ACTIVE' ? '승인됨' : '승인 대기'}
                </span>
                {e.status !== 'ACTIVE' && (
                  <button type="button" disabled={!!busy}
                    onClick={() => void run('회사 승인', () => approveEntity(e.entity_id))}
                    style={{ fontSize: 12, padding: '3px 10px', marginLeft: 'auto' }}>
                    승인
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="새로 등록"
        desc="가상회사는 시나리오·복제용이며 반드시 원본이 있어야 합니다 — 「이 가상 조직이 어느 실제 조직에서 나왔는가」를 잃지 않기 위해서입니다(§7.1 계보).">
        <div style={{ display: 'grid', gap: 6, maxWidth: 560 }}>
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="이름 — 예: LS MnM 가상(2027 시나리오)"
            style={{ fontSize: 13, padding: '6px 9px' }} />
          <label style={{ fontSize: 13 }}>
            성격{' '}
            <select value={mode} onChange={(e) => setMode(e.target.value)}
              style={{ fontSize: 13, padding: '4px 6px' }}>
              {/* ⚠️ 미리 고르지 않는다 — 실제/가상을 사람이 **의식해서** 골라야 한다.
                  기본값으로 REAL 이 박혀 있으면 시나리오 회사가 실제로 등록된다. */}
              <option value="">— 고르십시오 —</option>
              <option value="REAL">실제 (운영 중인 법인)</option>
              <option value="VIRTUAL">가상 (시나리오·복제)</option>
              <option value="COMPETITOR">경쟁사 (참고)</option>
            </select>
          </label>
          {mode === 'VIRTUAL' && (
            <>
              {/* ★★★ [2026-08-25 실측] 처음에 「비우면 새로 만듭니다」라고 적었다가
                  서버에 400 으로 막혔다 — **화면이 서버가 안 하는 일을 약속했다.**
                  서버 규칙: 「가상 조직은 복제 원본이 있어야 합니다」(§7.1 계보 —
                  이 가상 조직이 어느 실제 조직에서 나왔는가를 잃지 않는다).
                  ⚠️ id 를 손으로 적게 하지 않는다. 오타 하나가 **거짓 계보**를 만든다. */}
              <label style={{ fontSize: 13 }}>
                원본 회사(필수){' '}
                <select value={base} onChange={(e) => setBase(e.target.value)}
                  style={{ fontSize: 13, padding: '4px 6px', maxWidth: 300 }}>
                  <option value="">— 고르십시오 —</option>
                  {(entities || []).map((e) => (
                    <option key={e.entity_id} value={e.entity_id}>
                      {e.name_ko} ({MODE_KO[e.entity_mode] || e.entity_mode})
                    </option>
                  ))}
                </select>
              </label>
              {(entities || []).length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--state-warn-fg)' }}>
                  본뜰 회사가 없습니다 — 먼저 <b>실제</b> 법인을 등록하십시오.
                </div>
              )}
            </>
          )}
          <div>
            {/* ⚠️ 서버가 막을 것을 **누르기 전에** 막는다 — 400 을 받고 나서 알게 하지 않는다. */}
            <button type="button"
              disabled={!name.trim() || !mode || !!busy
                || (mode === 'VIRTUAL' && !base)}
              onClick={() => void run('회사 등록', () => createEntity({
                name_ko: name.trim(), entity_mode: mode,
                base_entity_id: mode === 'VIRTUAL' ? base.trim() : '',
              }))}
              style={{ fontSize: 13, padding: '6px 14px', fontWeight: 600 }}>
              {busy === '회사 등록' ? '등록 중…' : '등록 (승인 대기로)'}
            </button>
          </div>
          <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
            {/* ★ 승인이 왜 필요한지 화면이 말한다 — 누르고 나서 알게 하지 않는다. */}
            등록하면 <b>승인 대기(DRAFT)</b> 입니다. 승인해야 조직 트리와 판정에 참여합니다.
          </div>
        </div>
      </Section>

      <Section title="조직 노드"
        desc="연결구성(Digital Thread)은 조직 노드에 붙습니다. 노드가 없으면 붙일 곳이 없습니다.">
        <NodeAdd entities={entities} busy={busy} run={run} flat={flat} />
      </Section>

      <Section title="지금 보는 성격 — 실제 · 가상 · 경쟁사"
        desc="가상회사는 성격을 바꿔야 보입니다. 한 트리에 섞지 않는 것이 이 시스템의 비협상 규칙입니다.">
        <ModeSwitch current={currentMode} busy={busy} run={run} />
      </Section>

      <Section title="문맥 전환 — 이 조직 범위로 보기"
        desc="서버가 「그 범위를 그 모드로 볼 수 있는가」를 먼저 판정합니다. 통과해야 화면이 바뀝니다.">
        <ContextSwitch flat={flat} busy={busy} run={run} />
      </Section>
    </>
  );
}

/** 성격만 바꾼다. ★ 조직 노드가 하나도 없어도 가상회사를 볼 수 있어야 한다.
 *
 * ⚠️⚠️ [2026-08-25 실측] 처음에는 «범위 + 성격» 을 한꺼번에만 바꿀 수 있게 두었다.
 *   그런데 새로 만든 가상회사는 **성격이 VIRTUAL 이라 목록에 안 보이고**, 목록에 안
 *   보이니 노드를 못 만들고, 노드가 없으니 범위를 못 골라 성격도 못 바꿨다 — 잠겼다.
 * ★ 서버는 빈 범위 + 성격만으로도 허가한다(실측 `resolved:false`, 200). */
function ModeSwitch({ current, busy, run }: {
  current: string; busy: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      {['REAL', 'VIRTUAL', 'COMPETITOR'].map((m) => (
        <button key={m} type="button" disabled={!!busy || m === current}
          onClick={() => void run('성격 전환', async () => {
            //: ★ 여기서도 서버 허가를 먼저 받는다.
            await selectContext('', m);
            setEnterpriseContext({ entityMode: m });
          })}
          style={{
            fontSize: 13, padding: '6px 12px', borderRadius: 6,
            border: `1px solid ${m === current ? MODE_TONE[m] : 'var(--surface-border-control)'}`,
            background: m === current ? 'var(--surface-selected)' : 'transparent',
            fontWeight: m === current ? 700 : 400,
            color: m === current ? MODE_TONE[m] : undefined,
          }}>
          {MODE_KO[m]}{m === current ? ' · 지금' : ''}
        </button>
      ))}
    </div>
  );
}

/** 조직 노드 만들기. ⚠️ 노드가 없으면 연결구성을 붙일 곳도, 문맥을 고를 곳도 없다. */
function NodeAdd({ entities, flat, busy, run }: {
  entities: Entity[] | null; flat: (EcmNode & { _d: number })[]; busy: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [entity, setEntity] = useState('');
  const [name, setName] = useState('');
  const [type, setType] = useState('business_division');
  const [parent, setParent] = useState('');
  //: ★ 승인된 회사에만 붙인다 — 미승인 회사에 노드를 달면 승인 절차가 이름만 남는다.
  const usable = (entities || []).filter((e) => e.status === 'ACTIVE');

  return (
    <div style={{ display: 'grid', gap: 6, maxWidth: 620 }}>
      {flat.length > 0 && (
        <div style={{ fontSize: 13 }}>
          지금 {flat.length}개: {flat.map((n) => n.name_ko).join(' · ')}
        </div>
      )}
      <label style={{ fontSize: 13 }}>
        소속 회사{' '}
        <select value={entity} onChange={(e) => setEntity(e.target.value)}
          style={{ fontSize: 13, padding: '4px 6px', maxWidth: 260 }}>
          <option value="">— 고르십시오 —</option>
          {usable.map((e) => (
            <option key={e.entity_id} value={e.entity_id}>{e.name_ko}</option>
          ))}
        </select>
      </label>
      {usable.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--state-warn-fg)' }}>
          승인된 회사가 없습니다 — 위에서 등록하고 <b>승인</b>하십시오.
        </div>
      )}
      <label style={{ fontSize: 13 }}>
        종류{' '}
        <select value={type} onChange={(e) => setType(e.target.value)}
          style={{ fontSize: 13, padding: '4px 6px' }}>
          <option value="business_division">사업부</option>
          <option value="site_plant">공장·사업장</option>
          <option value="functional_department">기능 부서</option>
          <option value="shared_service">공유 서비스</option>
        </select>
      </label>
      <label style={{ fontSize: 13 }}>
        상위(선택){' '}
        <select value={parent} onChange={(e) => setParent(e.target.value)}
          style={{ fontSize: 13, padding: '4px 6px', maxWidth: 260 }}>
          <option value="">— 없음(최상위) —</option>
          {flat.map((n) => (
            <option key={n.node_id} value={n.node_id}>
              {' '.repeat(n._d * 2)}{n._d ? '└ ' : ''}{n.name_ko}
            </option>
          ))}
        </select>
      </label>
      <input value={name} onChange={(e) => setName(e.target.value)}
        placeholder="이름 — 예: 제련공장"
        style={{ fontSize: 13, padding: '6px 9px' }} />
      <div>
        <button type="button" disabled={!entity || !name.trim() || !!busy}
          onClick={() => void run('조직 노드 추가', () => createNode({
            entity_id: entity, node_type: type, name_ko: name.trim(),
            default_parent_id: parent,
          }))}
          style={{ fontSize: 13, padding: '6px 14px', fontWeight: 600 }}>
          {busy === '조직 노드 추가' ? '만드는 중…' : '노드 추가'}
        </button>
      </div>
    </div>
  );
}

function ContextSwitch({ flat, busy, run }: {
  flat: (EcmNode & { _d: number })[]; busy: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [node, setNode] = useState('');
  const [mode, setMode] = useState('REAL');

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <select value={node} onChange={(e) => setNode(e.target.value)}
        style={{ fontSize: 13, padding: '4px 6px', maxWidth: 320 }}>
        <option value="">— 조직 범위 —</option>
        {flat.map((n) => (
          // ★ 깊이를 **글자**로 표시한다 — 색·여백만으로 계층을 말하면 좁은 화면에서 사라진다.
          <option key={n.node_id} value={n.node_id}>
            {' '.repeat(n._d * 2)}{n._d ? '└ ' : ''}{n.name_ko}
          </option>
        ))}
      </select>
      <select value={mode} onChange={(e) => setMode(e.target.value)}
        style={{ fontSize: 13, padding: '4px 6px' }}>
        <option value="REAL">실제</option>
        <option value="VIRTUAL">가상</option>
        <option value="COMPETITOR">경쟁사</option>
      </select>
      <button type="button" disabled={!node || !!busy}
        onClick={() => void run('문맥 전환', async () => {
          //: ★★★ 서버 허가를 **먼저** 받는다. 통과하지 않은 문맥으로 화면을 바꾸면
          //:   보이는 것과 권한이 갈린다.
          await selectContext(node, mode);
          setEnterpriseContext({ scopeNodeId: node, entityMode: mode });
        })}
        style={{ fontSize: 13, padding: '6px 14px' }}>
        {busy === '문맥 전환' ? '확인 중…' : '이 문맥으로 보기'}
      </button>
      {flat.length === 0 && (
        <span style={{ fontSize: 12, color: 'var(--state-warn-fg)' }}>
          고를 조직 범위가 없습니다 — 먼저 법인을 등록·승인하고 조직 노드를 만드십시오.
        </span>
      )}
    </div>
  );
}

// ── ③ 업무 연결구성 (Digital Thread) ─────────────────────────────────────

function ThreadTab({ nodes, busy, run }: {
  nodes: EcmNode[] | null; busy: string;
  run: (what: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const flat = flatten(nodes || []);
  const [scope, setScope] = useState('');
  const [rows, setRows] = useState<ThreadNode[]>([]);
  const [found, setFound] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState('');

  const load = useCallback(async (nodeId: string) => {
    setScope(nodeId); setRows([]); setFound(null); setNote('');
    if (!nodeId) return;
    setLoading(true);
    try {
      const list = await listProfiles(nodeId, 'process_profile');
      //: ★ 승인된 것이 있으면 그것을, 없으면 초안을 연다. 둘 다 없으면 빈 상태다.
      const pick = list.find((x) => x.is_effective) || list[0] || null;
      setFound(pick);
      setRows(pick?.payload?.nodes || []);
      if (!pick) setNote('이 범위에 아직 연결구성이 없습니다 — 새로 만드십시오.');
      else if (!pick.is_effective) setNote('승인 대기 중인 초안입니다 — 승인해야 화면에 반영됩니다.');
    } catch (e: any) {
      setNote(e?.message || '연결구성을 읽지 못했습니다.');
    } finally { setLoading(false); }
  }, []);

  const set = (i: number, patch: Partial<ThreadNode>) =>
    setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  return (
    <>
      <Section title="어느 조직의 연결구성인가"
        desc="회사·사업부·공장마다 다를 수 있습니다. 하위가 없으면 상위 것을 물려받습니다.">
        <select value={scope} onChange={(e) => void load(e.target.value)}
          style={{ fontSize: 13, padding: '4px 6px', maxWidth: 360 }}>
          <option value="">— 조직 범위 —</option>
          {flat.map((n) => (
            <option key={n.node_id} value={n.node_id}>
              {' '.repeat(n._d * 2)}{n._d ? '└ ' : ''}{n.name_ko}
            </option>
          ))}
        </select>
        {flat.length === 0 && (
          <div style={{ fontSize: 12, color: 'var(--state-warn-fg)', marginTop: 6 }}>
            고를 조직 범위가 없습니다 — 「법인 · 가상회사」에서 먼저 등록·승인하십시오.
          </div>
        )}
      </Section>

      {scope && (
        <Section title="업무 흐름 단계"
          desc="경영 홈 가운데의 ENTERPRISE DIGITAL THREAD 가 이 순서대로 그려집니다.">
          {loading ? <div style={{ fontSize: 13 }}>읽는 중…</div> : (
            <>
              {/* ★ [2026-08-25 실측] 저장·승인 뒤에도 「아직 연결구성이 없습니다」가
                  남아 있었다 — 안내문을 **한 번 적어 두고 갱신하지 않았기** 때문이다.
                  ⚠️ 지금 상태에서 **파생**시킨다. 두 곳이 다른 말을 하면 사용자는 무엇이
                    참인지 화면에서 판단할 수 없다. */}
              {(() => {
                const msg = !found ? (note || '이 범위에 아직 연결구성이 없습니다 — 새로 만드십시오.')
                  : !found.is_effective ? '승인 대기 중인 초안입니다 — 승인해야 화면에 반영됩니다.'
                    : '';
                return msg ? (
                  <div style={{ fontSize: 13, color: 'var(--state-warn-fg)', marginBottom: 8 }}>
                    {msg}
                  </div>
                ) : null;
              })()}
              <ul style={{ padding: 0, margin: 0, listStyle: 'none', display: 'grid', gap: 6 }}>
                {rows.map((r, i) => (
                  <li key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, width: 26, textAlign: 'right',
                      color: 'var(--surface-text-muted)' }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <input value={r.key} onChange={(e) => set(i, { key: e.target.value })}
                      placeholder="기계 이름 — 예: order"
                      style={{ fontSize: 13, padding: '5px 8px', width: 150 }} />
                    <input value={r.label} onChange={(e) => set(i, { label: e.target.value })}
                      placeholder="사람이 읽는 이름 — 예: 수주·판매"
                      style={{ fontSize: 13, padding: '5px 8px', flex: 1, minWidth: 120 }} />
                    <button type="button" aria-label={`${i + 1}번 단계 삭제`}
                      onClick={() => setRows((x) => x.filter((_, j) => j !== i))}
                      style={{ fontSize: 12, padding: '4px 9px' }}>✕</button>
                  </li>
                ))}
              </ul>
              <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <button type="button"
                  onClick={() => setRows((r) => [...r, { key: '', label: '' }])}
                  style={{ fontSize: 13, padding: '6px 12px' }}>＋ 단계 추가</button>
                <button type="button"
                  disabled={!!busy || rows.length === 0
                    || rows.some((r) => !r.key.trim() || !r.label.trim())}
                  onClick={() => void run('연결구성 저장', async () => {
                    const saved = await saveProfile({
                      scope_node_id: scope,
                      payload: { nodes: rows.map((r) => ({
                        key: r.key.trim(), label: r.label.trim(), note: r.note || '' })) },
                    });
                    setFound(saved);
                  })}
                  style={{ fontSize: 13, padding: '6px 12px', fontWeight: 600 }}>
                  {busy === '연결구성 저장' ? '저장 중…' : '저장 (승인 대기로)'}
                </button>
                {found && !found.is_effective && (
                  <button type="button" disabled={!!busy}
                    onClick={() => void run('연결구성 승인', async () => {
                      const a = await approveProfile(found.profile_id);
                      setFound(a);
                    })}
                    style={{ fontSize: 13, padding: '6px 12px', fontWeight: 600 }}>
                    승인
                  </button>
                )}
                {found?.is_effective && (
                  <span style={{ fontSize: 13, color: 'var(--state-success-fg)',
                    alignSelf: 'center' }}>
                    ● 승인됨 — 경영 홈에 반영됩니다
                    {found.approved_by ? ` (${found.approved_by})` : ''}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 8 }}>
                {/* ⚠️ 저장만 하면 반영되지 않는다는 사실을 **누르기 전에** 말한다. */}
                저장하면 초안입니다. <b>승인해야</b> 경영 홈의 업무 흐름에 반영됩니다.
              </div>
            </>
          )}
        </Section>
      )}
    </>
  );
}
