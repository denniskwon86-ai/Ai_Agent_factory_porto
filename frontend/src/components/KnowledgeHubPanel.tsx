// [이관 1/10 · UIUX-AUDIT-33] 지식 허브 — `DataFoundationShell` 위로 옮긴 첫 화면
//
// 도메인 참고자료(표준·논문·사내 데이터)를 지식팩으로 등록·관리하고, 프로젝트에 연결해 모든
// 에이전트 산출물의 그라운딩 기준으로 쓴다.
//
// ## 이관하면서 함께 고친 것 (색만 바꾼 것이 아니다)
//
//   ① **자체 `API_BASE_URL` 선언 제거** — 공용 `lib/knowledgeApi.ts` 를 쓴다.
//   ② **조회 실패를 «0건»으로 표시하던 것** — 실패를 `console.error` 로 삼키고 `packs` 를 빈
//      배열로 두어, 화면이 «등록된 지식팩이 없습니다» 라고 말했다. 이제 `DataState` 계약이다.
//   ③ **`alert()`/`confirm()` 3곳 제거** — 키보드·스크린리더 대응이 되지 않고, 무엇보다
//      «무엇이 지워지는지»를 설명할 자리가 없다. 화면 안 확인(`ConfirmInline`)으로 바꿨다.
//   ④ **자체 모달 제거** — `fixed inset-0` 손수 모달에는 dialog semantics·배경 inert·포커스
//      트랩·Escape 가 없었다. 셸의 `HubDialog` 로 옮겼다.
//   ⑤ **9~11px 글자 제거** — 감사 기준(본문 14 / 압축 13 / 라벨·버튼 13 / 메타·시간 12).
//
// ## 이 화면이 반드시 말해야 하는 것
//
// ★ 자료가 **어디서 왔고 언제 들어왔는지**. 근거를 말하지 못하는 자료로 만든 산출물은 나중에
//   설명할 수 없다. 그래서 문서마다 출처·청크 수·등록 시각을 함께 싣고, 값이 없으면 빈칸이
//   아니라 «미상»이라고 쓴다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import {
  ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar,
  foundationJarvis, useConfirm,
} from '../design/DataFoundationShell';
import { EmptyOrError, Refreshing, Metric, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';
import { errorTitle } from '../lib/closedLoopFetch';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import {
  knowledgeApi, type Pack, type ReferenceAsset, type ReferenceSummary, type SearchHit,
} from '../lib/knowledgeApi';

type View = 'packs' | 'register' | 'search' | 'sources';

const MODULE = {
  packs: { kicker: 'KNOWLEDGE', title: '지식팩', subtitle: '프로젝트에 연결하면 이 범위 안에서 산출물이 만들어집니다.' },
  register: { kicker: 'REGISTER', title: '자료 등록', subtitle: '등록한 파일은 텍스트를 추출해 검색 색인에 들어갑니다.' },
  search: { kicker: 'GROUNDING', title: '검색 품질 확인', subtitle: '에이전트가 이 질의로 어떤 지식을 받게 되는지 그대로 봅니다.' },
  sources: { kicker: 'SOURCES', title: '원본 자료 등록부', subtitle: '출처·범위·분류를 관리합니다. 검토 전에는 자동으로 연결하지 않습니다.' },
};

export function KnowledgeHubPanel({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<View>('packs');
  const [packs, setPacks] = useState<Loaded<Pack[]>>(loading<Pack[]>());
  // 건수는 DA·관리자에게만 온다(`api.deps.hidden_envelope`) — `null` 은 «모른다»다.
  const EMPTY_PACK_VIS = { blockedReason: '', hiddenPresent: false,
    hiddenCount: null as number | null };
  const [packVisibility, setPackVisibility] = useState(EMPTY_PACK_VIS);
  const [refSummary, setRefSummary] = useState<Loaded<ReferenceSummary>>(loading<ReferenceSummary>());
  const [selected, setSelected] = useState<string>('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<Loaded<SearchHit[]>>(ok<SearchHit[]>([]));
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [form, setForm] = useState({ id: '', name: '', desc: '' });

  const delPack = useConfirm<string>();
  const delDoc = useConfirm<string>();

  const load = useCallback(async () => {
    setBusy('불러오는 중'); setErr(null);
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다** — 자료를 올리거나 지운 뒤 목록이 사라졌다
    //   돌아오면 방금 무엇이 바뀌었는지 비교할 수 없고 스크롤 위치도 잃는다.
    setPacks(refreshing); setRefSummary(refreshing);
    // ⚠️ 두 조회를 **따로** 담는다. 하나가 실패했다고 다른 하나까지 «없음»으로 만들지 않는다.
    const [p, r] = await Promise.allSettled([knowledgeApi.packs(), knowledgeApi.referenceSummary()]);
    if (p.status === 'fulfilled') {
      setPackVisibility({ blockedReason: p.value.blockedReason,
        hiddenPresent: p.value.hiddenPresent, hiddenCount: p.value.hiddenCount });
      setPacks(p.value.blockedReason
        ? { status: 'forbidden', value: null, error: p.value.blockedReason, httpStatus: 403 }
        : ok(p.value.packs));
      reportRequestSuccess();
    }
    else { setPacks(failed<Pack[]>(p.reason)); reportRequestFailure((p.reason as any)?.status); }
    setRefSummary(r.status === 'fulfilled' ? ok(r.value) : failed<ReferenceSummary>(r.reason));
    setBusy(null);
  }, []);

  useEffect(() => { load(); }, [load]);

  // 사용자가 바뀌면 이전 사용자의 목록을 즉시 폐기한다 — 권한 범위가 다르다.
  useEffect(() => {
    const h = () => {
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다** — 행동 뒤 목록이 사라졌다
    //   돌아오면 방금 무엇이 바뀌었는지 비교할 수 없고 스크롤 위치도 잃는다.
      // ⚠️⚠️ 여기는 **`refreshing` 을 쓰면 안 되는 자리**다. 설계 §6.2 는 「재조회 중 기존
      //   값은 유지」하라면서도 「**문맥 변경은 데이터 혼합 위험 때문에 이전 값을 즉시 비운다**」
      //   고 따로 못박았다. 사용자 전환은 곧 **권한 범위 전환**이라, 이전 사용자의 지식팩이 한
      //   순간이라도 남으면 «느린 화면» 이 아니라 **남의 자료를 보여 준 것**이다.
      //   (이 줄을 §6.2 적용 대상으로 오인해 바꿨다가 되돌렸다 — 2026-08-09.)
      setPacks(loading<Pack[]>()); setRefSummary(loading<ReferenceSummary>());
      setPackVisibility(EMPTY_PACK_VIS);
      setSelected(''); setHits(ok<SearchHit[]>([])); load();
    };
    window.addEventListener('factory:acting-user-changed', h);
    return () => window.removeEventListener('factory:acting-user-changed', h);
  }, [load]);

  const act = async (label: string, fn: () => Promise<unknown>, note?: string) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      await fn();
      setFlash(note || null);
      await load();
      return true;
    } catch (e: any) {
      setErr({ msg: e?.message || String(e), status: e?.status });
      return false;
    } finally { setBusy(null); }
  };

  const rows = packs.value || [];
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((p) =>
      p.pack_id.toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q));
  }, [rows, search]);

  const pack = rows.find((p) => p.pack_id === selected) || null;
  const docCount = pack?.documents?.length ?? 0;

  const items: RailItem[] = [
    { id: 'packs', label: '지식팩', hint: '등록된 자료 묶음', icon: 'packs',
      count: packs.status === 'ok' ? rows.length : undefined,
      countLabel: `지식팩 ${rows.length}개` },
    { id: 'register', label: '자료 등록', hint: '파일 올리기·삭제', icon: 'upload' },
    { id: 'search', label: '검색 품질 확인', hint: '에이전트가 받는 지식', icon: 'search' },
    { id: 'sources', label: '원본 등록부', hint: '출처·변환 필요', icon: 'sources' },
  ];

  const jarvis = foundationJarvis({
    module: `knowledge/${view}`,
    moduleTitle: MODULE[view].title,
    objectType: 'knowledge_pack',
    selected: pack ? { id: pack.pack_id, title: pack.name || pack.pack_id,
      meta: `문서 ${docCount}건 · ${pack.description || '설명 없음'}` } : null,
    state: packs,
    counts: { packs: packs.status === 'ok' ? rows.length : null },
    actions: pack ? ['자료 등록', '검색 품질 확인', '팩 삭제'] : ['팩 만들기'],
    evidence: pack ? [
      { label: '팩 ID', value: pack.pack_id },
      { label: '문서', value: `${docCount}건` },
      { label: '등록', value: (pack.created_at || '').slice(0, 10) || '미상' },
    ] : [],
  });

  const runSearch = async () => {
    if (!pack || !query.trim()) return;
    setBusy('검색 중'); setHits(loading<SearchHit[]>());
    try { setHits(ok(await knowledgeApi.search(pack.pack_id, query.trim()))); }
    catch (e: any) { setHits(failed<SearchHit[]>(e)); }
    finally { setBusy(null); }
  };

  return (
    <HubDialog label="지식 허브 — 도메인 참고자료와 근거" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>지식 허브</b>
        <span>등록한 자료의 범위 안에서 모든 에이전트가 산출물을 만듭니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">{busy}…</span>}
          <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker={MODULE[view].kicker} title={MODULE[view].title} subtitle={MODULE[view].subtitle}
          items={items} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>GROUNDING</span>
              <b>등록하지 않은 자료는 참고되지 않습니다</b>
              <p>
                에이전트는 여기에 등록되고 프로젝트에 연결된 지식팩만 봅니다. 사내 어딘가에
                파일이 있다는 사실만으로는 산출물에 반영되지 않습니다.
              </p>
            </div>
          }
          jarvis={
            <JarvisRail
              contextTitle={jarvis.title} contextDescription={jarvis.desc}
              evidence={jarvis.ev} context={jarvis.ctx}
              quickQuestions={[
                '이 지식팩에는 어떤 자료가 들어 있습니까?',
                '이 질의에 어떤 문서가 걸립니까?',
                '변환이 필요한 원본이 있습니까?',
              ]} />
          }
        >
          {err && (
            <Banner tone="error" title={errorTitle(err.status)}>
              {err.msg}
              <div style={{ marginTop: 10 }}>
                <button className="secondary-button" onClick={load}>다시 시도</button>
              </div>
            </Banner>
          )}
          {flash && <Banner tone="info">{flash}</Banner>}
          {packVisibility.hiddenPresent && (
            <Banner tone="warn">
              {packVisibility.hiddenCount === null
                ? '조직 권한 범위 밖의 지식팩은 표시하지 않았습니다 — 현재 조직 범위 자료만 표시 중입니다.'
                : `조직 권한 범위 밖의 지식팩 ${packVisibility.hiddenCount}개는 표시하지 않았습니다.`}
            </Banner>
          )}

          {view === 'packs' && (
            <PacksView
              state={packs} rows={filtered} selected={selected} onSelect={setSelected}
              search={search} onSearch={setSearch} onRetry={load}
              form={form} setForm={setForm}
              onCreate={async () => {
                const id = form.id.trim();
                if (!id) return;
                const okd = await act('팩 생성 중',
                  () => knowledgeApi.createPack({
                    pack_id: id, name: form.name.trim() || id, description: form.desc.trim() }),
                  '지식팩을 만들었습니다. «자료 등록»에서 파일을 올리십시오.');
                if (okd) { setForm({ id: '', name: '', desc: '' }); setSelected(id); setView('register'); }
              }}
              confirmDel={delPack}
              onDelete={(pid: string) => act('팩 삭제 중', () => knowledgeApi.deletePack(pid),
                '지식팩과 색인을 삭제했습니다.').then(() => setSelected(''))}
            />
          )}

          {view === 'register' && (
            <RegisterView
              pack={pack} state={packs}
              onUpload={async (files: FileList | null) => {
                if (!pack || !files) return;
                for (const f of Array.from(files)) {
                  const okd = await act(`«${f.name}» 등록 중`,
                    () => knowledgeApi.uploadDoc(pack.pack_id, f));
                  if (!okd) break;   // 첫 실패에서 멈춘다 — 나머지도 같은 이유로 실패한다
                }
              }}
              confirmDoc={delDoc}
              onRemove={(fn: string) => pack && act('문서 삭제 중',
                () => knowledgeApi.removeDoc(pack.pack_id, fn), '문서와 색인을 삭제했습니다.')}
              onGoPacks={() => setView('packs')}
            />
          )}

          {view === 'search' && (
            <SearchView pack={pack} query={query} onQuery={setQuery} onRun={runSearch}
              hits={hits} onGoPacks={() => setView('packs')} />
          )}

          {view === 'sources' && (
            <SourcesView state={refSummary} onRetry={load}
              onScan={() => act('원본 폴더 재스캔 중', knowledgeApi.referenceScan,
                '재스캔했습니다. 등록부 수치를 확인하십시오.')} />
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}

// ── 지식팩 ───────────────────────────────────────────────────────────────────
function PacksView({ state, rows, selected, onSelect, search, onSearch, onRetry, form, setForm,
  onCreate, confirmDel, onDelete }: any) {
  const pack = rows.find((p: Pack) => p.pack_id === selected) || null;
  return (
    <>
      <ScreenHead kicker="KNOWLEDGE" title="지식팩"
        description="도메인 참고자료를 묶어 둡니다. 프로젝트에 연결하면 그 범위 안에서 산출물이 만들어집니다."
        chip={state.status !== 'ok'
          ? state.status === 'loading'
            ? { label: '확인 중', tone: 'muted' }
            : { label: state.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
          : { label: `${rows.length}개`, tone: rows.length ? 'success' : 'muted' }} />

      <div className="metric-row" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
        <Metric label="지식팩" state={state.status}
          value={state.status === 'ok' ? rows.length : null} hint="검색어 적용 결과" />
        <Metric label="등록 문서" state={state.status}
          value={state.status === 'ok'
            ? rows.reduce((n: number, p: Pack) => n + (p.documents?.length || 0), 0) : null}
          hint="모든 팩 합계" />
      </div>

      <FoundationToolbar search={search} onSearch={onSearch}
        placeholder="팩 ID 또는 이름으로 찾기"
        hint="팩 ID·이름만 찾습니다. 문서 내용 검색은 «검색 품질 확인» 에서 합니다." />

      <FoundationList kicker="PACKS" title="등록된 지식팩" state={state} onRetry={onRetry}
        rows={rows.map((p: Pack) => ({
          id: p.pack_id,
          title: p.name || p.pack_id,
          meta: `${p.pack_id} · 문서 ${p.documents?.length || 0}건`,
          chip: (p.documents?.length || 0) > 0
            ? { label: '자료 있음', tone: 'success' as const }
            : { label: '비어 있음', tone: 'warn' as const },
        }))}
        selectedId={selected} onSelect={onSelect}
        emptyText={search
          ? `«${search}» 와 일치하는 지식팩이 없습니다.`
          : '등록된 지식팩이 없습니다. 아래에서 새로 만드십시오.'} />

      {pack && (
        <Panel kicker="SELECTED" title={pack.name || pack.pack_id}>
          <div style={{ padding: 15 }}>
            <EvidenceStrip
              items={[
                { label: '팩 ID', value: pack.pack_id },
                { label: '문서', value: `${pack.documents?.length || 0}건` },
                { label: '만든 날', value: (pack.created_at || '').slice(0, 10) },
              ]}
              note={pack.description || '설명이 없습니다 — 다른 사람이 이 팩의 범위를 알 수 없습니다.'} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
              <button className="danger-ghost" onClick={() => confirmDel.ask(pack.pack_id)}>
                팩 삭제
              </button>
            </div>
            <ConfirmInline
              open={confirmDel.target === pack.pack_id}
              title={`«${pack.name || pack.pack_id}» 을(를) 삭제합니다`}
              body={<>
                등록된 문서 <b>{pack.documents?.length || 0}건</b>과 검색 색인이 함께 지워집니다.
                이 팩을 연결한 프로젝트는 해당 지식 없이 산출물을 만들게 됩니다. 되돌릴 수 없습니다.
              </>}
              confirmLabel="삭제합니다"
              onCancel={confirmDel.cancel}
              onConfirm={() => confirmDel.run(onDelete)} />
          </div>
        </Panel>
      )}

      {state.status !== 'forbidden' && <Panel kicker="NEW" title="새 지식팩">
        <div style={{ padding: 15 }}>
          <FormField label="팩 ID" required
            hint="영문·숫자·_·- 만 씁니다. 나중에 프로젝트 설정에서 이 값으로 연결합니다.">
            <input className="afs-input" value={form.id} placeholder="예: mfg_standard"
              onChange={(e: any) => setForm({ ...form, id: e.target.value })} />
          </FormField>
          <FormField label="이름" hint="비우면 팩 ID 를 그대로 씁니다.">
            <input className="afs-input" value={form.name} placeholder="예: 제조 표준 지식"
              onChange={(e: any) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="설명"
            hint="이 팩에 무엇이 들어가는지 적습니다 — 다른 사람이 어떤 자료를 여기 올릴지 판단하는 기준입니다.">
            <textarea className="afs-textarea" rows={2} value={form.desc}
              onChange={(e: any) => setForm({ ...form, desc: e.target.value })} />
          </FormField>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!form.id.trim()} onClick={onCreate}>
              지식팩 만들기
            </button>
          </div>
          <p className="hint-line">최초 생성 시 임베딩 모델을 한 번 불러오므로 몇 초 걸릴 수 있습니다.</p>
        </div>
      </Panel>}
    </>
  );
}

// ── 자료 등록 ────────────────────────────────────────────────────────────────
function RegisterView({ pack, state, onUpload, confirmDoc, onRemove, onGoPacks }: any) {
  if (!pack) {
    return (
      <>
        <ScreenHead kicker="REGISTER" title="자료 등록"
          description="파일을 올리면 텍스트를 추출해 검색 색인에 넣습니다." />
        <Panel kicker="SELECT" title="지식팩을 먼저 고르십시오">
          <EmptyOrError state={state.status} error={state.error} onRetry={onGoPacks}
            emptyText={<>
              «지식팩» 에서 자료를 넣을 팩을 선택하십시오. 팩이 없으면 거기서 새로 만들 수 있습니다.
            </>} />
        </Panel>
      </>
    );
  }
  const docs: any[] = pack.documents || [];
  return (
    <>
      <ScreenHead kicker="REGISTER" title={`자료 등록 — ${pack.name || pack.pack_id}`}
        description="같은 파일명을 다시 올리면 교체됩니다. 등록 즉시 색인에 반영됩니다."
        chip={{ label: `${docs.length}건`, tone: docs.length ? 'success' : 'warn' }} />

      <Panel kicker="UPLOAD" title="파일 올리기">
        <div style={{ padding: 15 }}>
          <input type="file" multiple accept=".pdf,.docx,.pptx,.ppt,.md,.txt,.csv,.json"
            onChange={(e: any) => onUpload(e.target.files)}
            style={{ fontSize: 13, color: 'var(--surface-text-muted)' }} />
          {/* ★ «왜 안 되는지»를 미리 말한다. 올리고 나서 실패를 보는 것보다 낫다. */}
          <div className="request-alert warn" style={{ marginTop: 12 }}>
            <i aria-hidden="true">!</i>
            <div>
              <b>구형 .ppt 는 본문 추출을 보장할 수 없습니다</b>
              <small>
                .pptx 또는 PDF 로 변환한 뒤 등록하십시오. 변환 없이 올리면 색인에 들어가도
                내용이 비어 있을 수 있고, 그러면 에이전트는 그 자료를 «참고했다»고 말하면서
                실제로는 아무것도 읽지 못합니다.
              </small>
            </div>
          </div>
        </div>
      </Panel>

      <Panel kicker="DOCUMENTS" title={`등록된 문서 (${docs.length})`}>
        {docs.length === 0 ? (
          <div className="empty-note">
            아직 등록된 문서가 없습니다. 이 팩을 프로젝트에 연결해도 참고할 자료가 없습니다.
          </div>
        ) : (
          <div className="people-list" style={{ padding: 15 }}>
            {docs.map((d) => (
              <div key={d.filename} className="person" style={{ alignItems: 'flex-start' }}>
                <i aria-hidden="true">문</i>
                <div style={{ minWidth: 0 }}>
                  <b style={{ whiteSpace: 'normal' }}>{d.filename}</b>
                  {/* 출처·청크·시각 — 값이 없으면 «미상». 빈칸은 «확인했는데 없다»로 읽힌다. */}
                  <small>
                    {d.chunks ? `${d.chunks} 청크` : '청크 미상'}
                    {' · '}{d.source || '출처 미상'}
                    {' · '}{d.added_at ? String(d.added_at).slice(0, 16) : '등록 시각 미상'}
                  </small>
                  <ConfirmInline
                    open={confirmDoc.target === d.filename}
                    title={`«${d.filename}» 을(를) 삭제합니다`}
                    body={<>이 문서에서 만든 <b>{d.chunks || 0}개 청크</b>가 색인에서 함께 지워집니다. 되돌릴 수 없습니다.</>}
                    confirmLabel="삭제합니다"
                    onCancel={confirmDoc.cancel}
                    onConfirm={() => confirmDoc.run(onRemove)} />
                </div>
                {confirmDoc.target !== d.filename && (
                  <button className="text-button" onClick={() => confirmDoc.ask(d.filename)}>삭제</button>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 검색 품질 확인 ───────────────────────────────────────────────────────────
function SearchView({ pack, query, onQuery, onRun, hits, onGoPacks }: any) {
  if (!pack) {
    return (
      <>
        <ScreenHead kicker="GROUNDING" title="검색 품질 확인"
          description="에이전트가 이 질의로 어떤 지식을 받게 되는지 그대로 봅니다." />
        <Panel kicker="SELECT" title="지식팩을 먼저 고르십시오">
          <div className="empty-note">
            «지식팩» 에서 확인할 팩을 선택하십시오.
            <div style={{ marginTop: 10 }}>
              <button className="secondary-button" onClick={onGoPacks}>지식팩으로 가기</button>
            </div>
          </div>
        </Panel>
      </>
    );
  }
  const rows: SearchHit[] = hits.value || [];
  return (
    <>
      <ScreenHead kicker="GROUNDING" title={`검색 품질 확인 — ${pack.name || pack.pack_id}`}
        description="여기서 걸리지 않는 내용은 에이전트도 참고하지 못합니다. 산출물이 이상하면 먼저 여기를 확인하십시오."
        chip={{ label: `문서 ${pack.documents?.length || 0}건`, tone: 'data' }} />

      <FoundationToolbar search={query} onSearch={onQuery}
        placeholder="예: 재고 회전율 표준 기준"
        actions={<button className="primary-button" disabled={!query.trim()} onClick={onRun}>검색</button>}
        hint="실제 에이전트와 같은 방식으로 검색합니다 — 결과가 비면 그 질문에는 근거가 없다는 뜻입니다." />

      <Panel kicker="HITS" title="에이전트가 받게 될 지식">
        {rows.length === 0 ? (
          <EmptyOrError state={hits.status} error={hits.error} onRetry={onRun}
            emptyText={query
              ? '이 질의로 걸리는 내용이 없습니다. 자료가 없거나, 표현이 문서와 다릅니다.'
              : '질의를 입력하고 «검색» 을 누르십시오.'} />
        ) : (
          <div style={{ padding: 15, display: 'grid', gap: 10 }}>
            {rows.map((h, i) => (
              <section key={i} className="panel" style={{ padding: 13 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <b style={{ fontSize: 13 }}>{h.metadata?.filename || '파일명 미상'}</b>
                  {/* ★ 거리는 «가까울수록 관련»이다. 숫자만 두면 크면 좋은 줄 안다. */}
                  <span className="state-chip muted">
                    거리 {Number(h.distance ?? 0).toFixed(3)} · 작을수록 가까움
                  </span>
                </div>
                <p className="section-text" style={{ marginTop: 8 }}>{h.content}</p>
              </section>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

// ── 원본 등록부 ──────────────────────────────────────────────────────────────
function SourcesView({ state, onScan, onRetry }: any) {
  const s: ReferenceSummary | null = state.value;
  return (
    <>
      <ScreenHead kicker="SOURCES" title="원본 자료 등록부"
        description="출처·범위·분류를 관리합니다. 검토 전에는 사업부 자료를 자동으로 모든 프로젝트에 연결하지 않습니다."
        chip={state.status !== 'ok'
          ? state.status === 'loading'
            ? { label: '확인 중', tone: 'muted' }
            : { label: state.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
          : { label: `${s?.total ?? 0}건`, tone: 'data' }} />

      <div className="metric-row">
        <Metric label="원본" state={state.status} value={s?.total} hint="등록부 전체" />
        <Metric label="추출 가능" state={state.status} value={s?.supported} hint="그대로 색인 가능" />
        <Metric label="변환 필요" state={state.status} value={s?.conversion_required}
          hint={s?.conversion_required ? '.pptx·PDF 로 변환 후 등록' : '없음'} />
        <Metric label="검토 대기" state={state.status} value={s?.pending_review}
          hint="연결 전 사용자 확인 필요" />
      </div>

      <Panel kicker="SCAN" title="원본 폴더 재스캔"
        action={<button className="secondary-button" style={{ minHeight: 32 }} onClick={onScan}>재스캔</button>}>
        <div style={{ padding: 15 }}>
          {state.status !== 'ok' ? (
            <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
              emptyText="등록부가 비어 있습니다." />
          ) : (
            <p className="hint-line" style={{ margin: 0 }}>
              재스캔은 원본 폴더를 다시 훑어 <b>등록부 수치만</b> 갱신합니다. 자료를 프로젝트에
              연결하지도, 색인에 넣지도 않습니다 — 연결은 «지식팩» 에서 사용자가 결정합니다.
            </p>
          )}
        </div>
      </Panel>

      <ReferenceTable onChanged={onRetry} />
    </>
  );
}

/** [설계 §5.6 Registry 화면 공통 · Reference Registry 특화]
 *
 * 필수 열 — **이름 · 범위 · 상태 · 오너 · 최신성 · 위험**.
 * 필터 — 지식팩 · 범위 · 분류 · 확장자 · 승인 · 색인.
 * 행 CTA 는 «상세 검토» 하나이고, **승인·색인은 Drawer 에서** 한다.
 *
 * ⚠️ 이 표는 서버에 이미 있던 `/reference/assets` 를 그대로 읽는다. 그동안 화면은 요약 4수치만
 *   보여 줬고, 「검토 대기 N건」이라고 말하면서 **그 N건이 무엇인지는 어디에서도 볼 수 없었다.**
 *   숫자를 세는 화면과 일을 할 수 있는 화면은 다르다.
 */
function ReferenceTable({ onChanged }: { onChanged: () => void }) {
  const [rows, setRows] = useState<Loaded<ReferenceAsset[]>>(loading<ReferenceAsset[]>());
  const [f, setF] = useState({ pack: '', scope: '', cls: '', ext: '', approval: '', index: '' });
  const [openId, setOpenId] = useState('');
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    // §6.2 — 승인·색인 뒤 목록을 다시 읽어도 표가 사라지지 않게 한다.
    setRows(refreshing);
    try {
      setRows(ok(await knowledgeApi.referenceAssets() || []));
    } catch (e) {
      setRows(failed<ReferenceAsset[]>(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const all = rows.value || [];
  const opts = (pick: (a: ReferenceAsset) => string) =>
    Array.from(new Set(all.map(pick).filter(Boolean))).sort();

  const shown = all.filter((a) =>
    (!f.pack || a.pack_id === f.pack)
    && (!f.scope || a.scope_code === f.scope)
    && (!f.cls || a.classification === f.cls)
    && (!f.ext || a.extension === f.ext)
    && (!f.approval || a.approval_status === f.approval)
    && (!f.index || a.ingestion_status === f.index));

  const open = all.find((a) => a.asset_id === openId) || null;

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setBusy(label); setErr('');
    try { await fn(); await load(); onChanged(); } catch (e: any) {
      // 서버 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(e?.message || '요청이 거절됐습니다.');
    } finally { setBusy(''); }
  };

  const sel = (label: string, key: keyof typeof f, values: string[]) => (
    <label className="reg-filter">
      <span>{label}</span>
      <select className="afs-select" value={f[key]}
        onChange={(e) => setF({ ...f, [key]: e.target.value })}>
        <option value="">전체</option>
        {values.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    </label>
  );

  /** 위험 열 — **분류와 승인 드리프트를 합친 한 낱말.** 색만으로 전달하지 않는다(§2.1). */
  const risk = (a: ReferenceAsset) => {
    if (a.approval_drift === 'changed') {
      return { label: '승인 후 변경', cls: 'afs-danger-fg' };
    }
    if (a.approval_drift === 'unknown') {
      return { label: '승인 시점 내용 미상', cls: 'afs-warn-fg' };
    }
    if (a.classification && a.classification !== 'INTERNAL') {
      return { label: a.classification, cls: 'afs-warn-fg' };
    }
    if (a.extraction_status !== 'SUPPORTED') {
      return { label: '추출 불가', cls: 'afs-warn-fg' };
    }
    return { label: '—', cls: 'afs-muted' };
  };

  return (
    <Panel kicker="REGISTRY" title="원본 자산 목록"
      action={rows.status === 'ok' && (
        <span className="afs-muted" style={{ fontSize: 12 }}>
          {shown.length === all.length ? `${all.length}건`
            : `${shown.length} / ${all.length}건`}
        </span>)}>
      <div style={{ padding: 15 }}>
        {/* 설계 §5.6 필터 6종 */}
        <div className="reg-filters">
          {sel('지식팩', 'pack', opts((a) => a.pack_id))}
          {sel('범위', 'scope', opts((a) => a.scope_code))}
          {sel('분류', 'cls', opts((a) => a.classification))}
          {sel('확장자', 'ext', opts((a) => a.extension))}
          {sel('승인', 'approval', opts((a) => a.approval_status))}
          {sel('색인', 'index', opts((a) => a.ingestion_status))}
        </div>

        {err && <Banner tone="error" title="진행하지 못했습니다">{err}</Banner>}

        {rows.status !== 'ok' ? (
          <EmptyOrError state={rows.status} error={rows.error} onRetry={load}
            emptyText="등록된 원본 자산이 없습니다." />
        ) : shown.length === 0 ? (
          <p className="afs-muted" style={{ fontSize: 13 }}>
            {/* ⚠️ 필터 때문에 빈 것과 원래 없는 것을 구분한다. */}
            {all.length > 0
              ? '이 필터에 맞는 자산이 없습니다 — 필터를 «전체» 로 되돌리십시오.'
              : '등록된 원본 자산이 없습니다.'}
          </p>
        ) : (
          <div className="afs-table-wrap">
            <table className="afs-table">
              <thead>
                <tr>
                  <th>이름</th><th>범위</th><th>상태</th><th>오너</th><th>최신성</th>
                  <th>위험</th><th />
                </tr>
              </thead>
              <tbody>
                {shown.map((a) => {
                  const r = risk(a);
                  return (
                    <tr key={a.asset_id} className={openId === a.asset_id ? 'on' : ''}>
                      <td title={a.relative_path}>{a.filename}</td>
                      <td>{a.scope_code || '미지정'}</td>
                      <td>
                        {a.approval_status}
                        <span className="afs-muted"> · {a.ingestion_status}</span>
                      </td>
                      <td>{a.owner_org_id || '미지정'}</td>
                      {/* ⚠️ 「최신성」의 원천이 승인 시각뿐이다 — 파일 수정 시각을 서버가 주지
                          않는다. 그래서 «최종 수정» 이라 쓰지 않고 무엇의 시각인지 밝힌다. */}
                      <td>{a.approved_at
                        ? `${a.approved_at.slice(0, 10)} 승인` : '승인 이력 없음'}</td>
                      <td className={r.cls}>{r.label}</td>
                      <td>
                        {/* 설계: 행 CTA 는 «상세 검토» 하나. 승인·색인은 Drawer 에서. */}
                        <button className="text-button"
                          onClick={() => { setOpenId(a.asset_id); setNote(''); setErr(''); }}>
                          상세 검토
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 우 440 상세 Drawer */}
        {open && (
          <aside className="registry-drawer" role="dialog" aria-modal="false"
            aria-label={`자산 상세: ${open.filename}`}>
            <header>
              <div>
                <span>{open.pack_id || '지식팩 미지정'}</span>
                <b>{open.filename}</b>
              </div>
              <button className="secondary-button" onClick={() => setOpenId('')}>닫기</button>
            </header>

            {open.approval_drift === 'changed' && (
              <Banner tone="error" title="승인한 내용과 파일이 다릅니다">
                이 자산은 승인 뒤 내용이 바뀌었습니다 — 지금 색인하면 <b>검토받지 않은 문서</b>가
                사내 지식으로 들어갑니다. 다시 검토한 뒤 승인하십시오.
              </Banner>
            )}
            {open.approval_drift === 'unknown' && (
              <Banner tone="warn" title="승인 당시 내용을 확인할 수 없습니다">
                승인 시점의 내용 해시가 기록되기 전에 승인된 자산입니다 — 바뀌었는지 «아닌지»를
                판단할 근거가 없습니다. 필요하면 다시 승인해 기준을 남기십시오.
              </Banner>
            )}

            <dl className="drawer-facts">
              <div><dt>범위</dt><dd>{open.scope_code || '미지정'}</dd></div>
              <div><dt>소유 조직</dt><dd>{open.owner_org_id || '미지정'}</dd></div>
              <div><dt>분류</dt><dd>{open.classification}</dd></div>
              <div><dt>추출</dt><dd>{open.extraction_status}</dd></div>
              <div><dt>색인</dt><dd>{open.ingestion_status}</dd></div>
              <div><dt>승인</dt>
                <dd>{open.approval_status}
                  {open.approved_by ? ` · ${open.approved_by}` : ''}</dd></div>
              <div><dt>크기</dt>
                <dd>{(open.size_bytes / 1024).toFixed(0)} KB · {open.extension}</dd></div>
              <div><dt>내용 지문</dt>
                <dd style={{ fontFamily: 'monospace', fontSize: 11 }}>
                  {open.sha256.slice(0, 16)}</dd></div>
            </dl>

            <label className="field-label" htmlFor="ref-note">
              사유 / 메모 (반려에는 <b>필수</b> — 없으면 같은 문서가 계속 다시 올라옵니다)
            </label>
            <textarea id="ref-note" className="afs-textarea" value={note}
              onChange={(e) => setNote(e.target.value)} />

            <div className="drawer-actions">
              <button className="secondary-button" disabled={!!busy}
                onClick={() => act(() => knowledgeApi.referenceApprove(open.asset_id, note),
                  'approve')}>
                {busy === 'approve' ? '승인 중…' : '승인'}
              </button>
              <button className="danger-ghost" disabled={!!busy || !note.trim()}
                onClick={() => act(() => knowledgeApi.referenceReject(open.asset_id, note.trim()),
                  'reject')}>
                반려
              </button>
              {/* ⚠️ 색인은 되돌릴 수 없다 — **예행이 기본**이고, 실제 색인은 따로 누른다. */}
              <button className="secondary-button" disabled={!!busy}
                onClick={() => act(() => knowledgeApi.referenceIndex([open.asset_id], true),
                  'dry')}>
                {busy === 'dry' ? '확인 중…' : '색인 예행 (넣지 않음)'}
              </button>
              <button className="primary-button"
                disabled={!!busy || open.approval_status !== 'APPROVED'
                  || open.approval_drift === 'changed'}
                onClick={() => act(() => knowledgeApi.referenceIndex([open.asset_id], false),
                  'index')}>
                {busy === 'index' ? '색인 중…' : '색인'}
              </button>
            </div>
            {open.approval_status !== 'APPROVED' && (
              <p className="afs-muted" style={{ fontSize: 12, margin: '8px 0 0' }}>
                승인되지 않은 자산은 색인할 수 없습니다 — 먼저 승인하십시오.
              </p>
            )}
          </aside>
        )}
      </div>
    </Panel>
  );
}
