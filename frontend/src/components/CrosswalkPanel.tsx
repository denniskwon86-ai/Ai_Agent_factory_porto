// [이관 F 4/8] 연계 / 크로스워크 (M2) — 외부 시스템의 키·필드를 우리 기준정보(M1 골든 레코드)와
// 매핑한다. 매핑은 초안(제안) → 사용자 승인(confirmed) 2단계이며, **승인된 매핑만** M3 온디맨드
// 조회의 주소록이 된다.
//
// ## ★★★ 이관에서 드러난 것 — 조회 실패를 «빈 목록» 으로 바꿔치기하고 있었다
//
//   `fetch(...).then(r => r.ok ? r.json() : { data: [] })`
//
// 403 도 500 도 **빈 목록**이 됐다. 이 화면에서 빈 목록은 「매핑할 것이 없다」·「승인 대기가
// 없다」로 읽힌다. 그런데 승인 대기 제안은 **«외부 필드 = 우리 표준의 무엇» 을 확정하는**
// 관문이다 — 못 본 것을 «없다» 로 보여주면 그 관문이 조용히 비어 보인다.
// → 각 목록을 `Loaded<T>` 로 담고, 실패는 실패로 말한다.
//
// ## 자체 `API_BASE_URL` 선언을 제거했다
//
// `lib/api.ts` 머리말이 경고한 «8곳 중복 선언» 중 하나였다. 예전에 같은 방식으로
// `KnowledgeHubPanel` 의 모든 호출이 **조용히 익명으로** 나갔다. 지금은 인터셉터가 origin 으로
// 판정해 덮이지만, 남겨 두면 포트가 갈릴 때 같은 사고가 재현된다.
//
// ## `alert()` 7곳 · `prompt()` 1곳을 없앴다
//
// 디자인 시스템 규칙 ②(브라우저 대화상자 금지). 특히 승인은 `prompt()` 로 외부 키를 받고
// 있었는데, 그 한 줄이 **무엇을 확정하는지** 설명할 자리가 없었다. 화면 안 입력으로 바꾸고
// 확정되는 내용을 그대로 보여준다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 모달(모달 semantics·포커스 트랩·Escape 없음) → `HubDialog`
//   · 승인·기각이 **응답을 확인하지 않던 것**(fire-and-forget — 실패해도 화면은 성공처럼 굴었다)
//   · **9~11px 글자 12곳** → 본문 12px 이상
import { useCallback, useEffect, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import {
  crosswalkApi, type Field, type LiveValue, type Mapping, type Proposal, type Sys,
} from '../lib/crosswalkApi';


export function CrosswalkPanel({ onClose }: { onClose: () => void }) {
  const [systems, setSystems] = useState<Loaded<Sys[]>>(loading<Sys[]>());
  //: ★★★ 「지금 이 사람이 바꿀 수 있는가」는 **서버가 답한다**(§10 UI). 빈 문자열이면 가능.
  //:   ⚠️ 화면이 이 판정을 다시 만들지 않는다 — 만들면 서버와 갈라져 「버튼은 보이는데 서버는
  //:   거부」가 다시 생긴다. 2026-08-08 대조에서 실제로 그 상태를 발견했다: viewer 에게
  //:   「+ 시스템 등록」이 **항상 활성**이었고 누르면 403 이었다.
  const [writeBlocked, setWriteBlocked] = useState('');
  const [sel, setSel] = useState<string | null>(null);
  const [schema, setSchema] = useState<Loaded<Field[]>>(loading<Field[]>());
  const [proposals, setProposals] = useState<Loaded<Proposal[]>>(loading<Proposal[]>());
  const [mappings, setMappings] = useState<Loaded<Mapping[]>>(loading<Mapping[]>());
  const [liveResults, setLiveResults] = useState<Record<string, LiveValue>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  const [sysId, setSysId] = useState('');
  const [sysName, setSysName] = useState('');
  const [sysEndpoint, setSysEndpoint] = useState('');

  const [fEntity, setFEntity] = useState('');
  const [fField, setFField] = useState('');
  const [fType, setFType] = useState('');
  const [fIsKey, setFIsKey] = useState(false);
  const [fMappedAttr, setFMappedAttr] = useState('');

  const [useLlm, setUseLlm] = useState(false);
  /** 승인 시 확정할 외부 키. `prompt()` 를 대신한다. */
  const [approveKey, setApproveKey] = useState('');

  const confirmApprove = useConfirm<Proposal>();
  const confirmPropose = useConfirm<true>();

  const fetchSystems = useCallback(async () => {
    setSystems(loading<Sys[]>());
    try {
      const { rows, writeBlocked: wb } = await crosswalkApi.systemsWithRights();
      setWriteBlocked(wb);
      reportRequestSuccess();
      setSystems(ok(rows || []));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setSystems(failed<Sys[]>(e));
    }
  }, []);

  const refreshSel = useCallback(async (sid: string) => {
    setSchema(loading<Field[]>());
    setProposals(loading<Proposal[]>());
    setMappings(loading<Mapping[]>());
    // ★ 셋을 **따로** 담는다. 하나가 실패해도 나머지를 «없다» 로 만들지 않는다.
    const [s, p, m] = await Promise.allSettled([
      crosswalkApi.schema(sid), crosswalkApi.proposals(sid), crosswalkApi.mappings(sid),
    ]);
    setSchema(s.status === 'fulfilled' ? ok(s.value || []) : failed<Field[]>(s.reason));
    setProposals(p.status === 'fulfilled' ? ok(p.value || []) : failed<Proposal[]>(p.reason));
    setMappings(m.status === 'fulfilled' ? ok(m.value || []) : failed<Mapping[]>(m.reason));
  }, []);

  useEffect(() => { fetchSystems(); }, [fetchSystems]);
  useEffect(() => { if (sel) refreshSel(sel); }, [sel, refreshSel]);

  const selSys = (systems.value || []).find((s) => s.system_id === sel) || null;
  const pending = (proposals.value || []).filter((p) => p.status === 'pending');

  /** 쓰기 한 번. **응답을 반드시 확인한다** — 종전 승인·기각은 확인하지 않았다. */
  const act = async (tag: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(tag); setErr(''); setMsg('');
    try {
      await fn();
      setMsg(okMsg);
      return true;
    } catch (e: any) {
      setErr(e?.message || '요청이 거절됐습니다.');
      return false;
    } finally {
      setBusy(null);
    }
  };

  const handleCreateSystem = async () => {
    if (!sysId.trim()) { setErr('system_id 를 입력하십시오 (영소문자/숫자/_/-, 2~32자).'); return; }
    const id = sysId.trim();
    if (await act('sys', () => crosswalkApi.createSystem({
      system_id: id, name: sysName.trim() || id, mcp_endpoint: sysEndpoint.trim(),
    }), `시스템 «${id}» 를 등록했습니다.`)) {
      setSysId(''); setSysName(''); setSysEndpoint('');
      await fetchSystems();
      setSel(id);
    }
  };

  const handleAddField = async () => {
    if (!sel || !fEntity.trim() || !fField.trim()) {
      setErr('엔티티와 필드명을 입력하십시오.'); return;
    }
    if (await act('field', () => crosswalkApi.addField(sel, {
      entity: fEntity.trim(), field: fField.trim(), field_type: fType.trim(),
      is_key: fIsKey, mapped_attr: fMappedAttr.trim(),
    }), '필드를 추가했습니다.')) {
      setFEntity(''); setFField(''); setFType(''); setFIsKey(false); setFMappedAttr('');
      await refreshSel(sel);
    }
  };

  const handleCsv = async (files: FileList | null) => {
    if (!files || !files[0] || !sel) return;
    setBusy('csv'); setErr(''); setMsg('');
    try {
      const d = await crosswalkApi.importCsv(sel, files[0]);
      // ⚠️ «성공 N/M» 을 그대로 말한다 — 일부만 들어간 것을 «등록 완료» 로 뭉치지 않는다.
      setMsg(d.imported === d.total
        ? `스키마 ${d.total}건을 모두 등록했습니다.`
        : `스키마 ${d.total}건 중 ${d.imported}건만 등록됐습니다 — 나머지는 형식을 확인하십시오.`);
      await refreshSel(sel);
    } catch (e: any) {
      setErr(e?.message || 'CSV 등록에 실패했습니다.');
    } finally {
      setBusy(null);
    }
  };

  const doPropose = async () => {
    if (!sel) return;
    if (await act('propose', () => crosswalkApi.propose(sel, useLlm).then((d) => {
      setMsg(`매핑 초안: 신규 제안 ${d.proposed}건 (결정론 ${d.deterministic}`
        + `${d.llm_used ? ' + Flash' : ''})`);
    }), '')) await refreshSel(sel);
  };

  const doApprove = async (p: Proposal) => {
    if (await act('approve', () => crosswalkApi.approve(p.id, approveKey.trim() || null),
      `«${p.master_code}» 매핑을 확정했습니다.`)) {
      setApproveKey('');
      if (sel) await refreshSel(sel);
    }
  };

  const handleReject = async (p: Proposal) => {
    if (await act('reject', () => crosswalkApi.reject(p.id), `«${p.master_code}» 제안을 기각했습니다.`)) {
      if (sel) await refreshSel(sel);
    }
  };

  const handleActivate = async () => {
    if (!sel || !selSys) return;
    const next = selSys.status === 'active' ? 'inactive' : 'active';
    if (await act('status', () => crosswalkApi.setStatus(sel, next),
      next === 'active' ? '활성화했습니다.' : '비활성화했습니다.')) await fetchSystems();
  };

  const handleResolve = async (mc: string) => {
    if (!sel) return;
    setBusy('resolve');
    try {
      const data = await crosswalkApi.resolve(mc, sel);
      setLiveResults((p) => ({ ...p, [mc]: data }));
    } catch (e: any) {
      // ⚠️ 실측 조회 실패는 **그 매핑 칸에서** 말한다 — 전역 배너로 올리면 어느 것인지 사라진다.
      setLiveResults((p) => ({ ...p, [mc]: { ok: false, error: e?.message || '조회 실패' } }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <HubDialog label="연계 / 크로스워크 — 외부 시스템 키를 기준정보와 매핑" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>연계 / 크로스워크</b>
        <span>초안 → 사용자 승인 2단계 · 승인된 매핑만 M3 온디맨드 조회의 주소록이 됩니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">처리 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="CROSSWALK" title="연계 / 크로스워크"
            description="외부 시스템의 키·필드를 우리 기준정보와 잇습니다. 승인은 «외부 필드 = 우리 표준의 무엇»을 확정하는 행위입니다 — 확정된 매핑이 이후 모든 실측 조회의 주소록이 됩니다."
            chip={systems.status === 'loading' ? { label: '확인 중', tone: 'muted' }
              : systems.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' }
                : systems.status === 'error' ? { label: '조회 불가', tone: 'danger' }
                  : { label: `시스템 ${(systems.value || []).length}개`, tone: 'data' }} />

          {err && (
            <div style={{ marginBottom: 12 }}>
              <Banner tone="error" title="진행하지 못했습니다">
                <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
              </Banner>
            </div>
          )}
          {msg && <div style={{ marginBottom: 12 }}><Banner tone="info">{msg}</Banner></div>}

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 300px) 1fr',
            gap: 14, alignItems: 'start' }}>
            {/* ── 좌: 시스템 목록 + 등록 ─────────────────────────────── */}
            <div>
              <Panel kicker="REGISTER" title="연계 시스템 등록">
                <div className="panel-body">
                  <input className="afs-input" style={{ width: '100%' }} value={sysId}
                    onChange={(e) => setSysId(e.target.value)}
                    placeholder="system_id (예: sap, mes)" />
                  <input className="afs-input" style={{ width: '100%' }} value={sysName}
                    onChange={(e) => setSysName(e.target.value)} placeholder="이름 (예: SAP ERP)" />
                  <input className="afs-input" style={{ width: '100%' }} value={sysEndpoint}
                    onChange={(e) => setSysEndpoint(e.target.value)}
                    placeholder="MCP endpoint (선택, M3용)" />
                  <button className="primary-button" style={{ width: '100%' }}
                    onClick={handleCreateSystem}
                    disabled={busy !== null || Boolean(writeBlocked)}
                    aria-disabled={Boolean(writeBlocked) || undefined}>
                    {busy === 'sys' ? '등록 중…' : '+ 시스템 등록'}
                  </button>
                  {/* §8.6 — 못 누르는 이유를 **항상** 들고 다닌다. 회색 버튼만 두면 사용자는
                      화면 고장으로 읽고 진짜 이유는 아무에게도 도달하지 않는다. */}
                  {writeBlocked && (
                    <small className="afs-warn-fg" style={{ fontSize: 12, display: 'block',
                      marginTop: 6 }}>🔒 {writeBlocked}</small>
                  )}
                </div>
              </Panel>

              <div style={{ marginTop: 14 }}>
                <Panel kicker="SYSTEMS" title="등록된 시스템">
                  <div className="panel-body">
                    {systems.status !== 'ok' ? (
                      // ★★★ 종전에는 여기가 «등록된 시스템이 없습니다» 였다.
                      <EmptyOrError state={systems.status} error={systems.error}
                        emptyText="등록된 시스템이 없습니다." onRetry={fetchSystems} />
                    ) : (systems.value || []).length === 0 ? (
                      <p className="afs-muted" style={{ fontSize: 13 }}>등록된 시스템이 없습니다.</p>
                    ) : (
                      (systems.value || []).map((s) => (
                        <button key={s.system_id} onClick={() => setSel(s.system_id)}
                          className={`afs-border ${sel === s.system_id ? 'afs-action-border' : ''}`}
                          style={{ display: 'block', width: '100%', textAlign: 'left',
                            borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                            padding: '8px 10px',
                            background: sel === s.system_id ? 'var(--surface-raised)' : '#fff' }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <b style={{ fontSize: 13, overflow: 'hidden',
                              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</b>
                            <span className={`state-chip ${s.status === 'active' ? 'success' : 'muted'}`}>
                              {s.status}
                            </span>
                          </span>
                          <span className="afs-muted" style={{ display: 'block', fontSize: 12,
                            fontFamily: 'monospace' }}>{s.system_id}</span>
                        </button>
                      ))
                    )}
                  </div>
                </Panel>
              </div>
            </div>

            {/* ── 우: 스키마 + 제안 + 매핑 ───────────────────────────── */}
            <div>
              {!selSys ? (
                <Panel>
                  <div className="panel-body">
                    <p className="afs-muted" style={{ fontSize: 13 }}>
                      왼쪽에서 시스템을 선택하거나 새로 등록하십시오.
                    </p>
                  </div>
                </Panel>
              ) : (
                <>
                  <Panel kicker="SYSTEM" title={selSys.name}
                    action={
                      <button className={selSys.status === 'active'
                        ? 'secondary-button' : 'primary-button'}
                        onClick={handleActivate} disabled={busy !== null}>
                        {selSys.status === 'active' ? '⏸ 비활성화' : '▶ 활성화(승인 매핑 필요)'}
                      </button>}>
                    <div className="panel-body">
                      <p className="afs-muted" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                        {selSys.system_id}
                      </p>
                    </div>
                  </Panel>

                  {/* 외부 스키마 */}
                  <div style={{ marginTop: 14 }}>
                    <Panel kicker="SCHEMA" title="외부 스키마 (조인 컬럼 정의)"
                      action={
                        <label className="secondary-button" style={{ display: 'inline-flex',
                          alignItems: 'center', cursor: 'pointer' }}>
                          📥 CSV 등록
                          <input type="file" accept=".csv" style={{ display: 'none' }}
                            disabled={busy !== null}
                            onChange={(e) => handleCsv(e.target.files)} />
                        </label>}>
                      <div className="panel-body">
                        <p className="afs-muted" style={{ fontSize: 12 }}>
                          CSV 열: entity, field, field_type, is_key, mapped_attr
                        </p>
                        <div style={{ display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                          <input className="afs-input" value={fEntity}
                            onChange={(e) => setFEntity(e.target.value)} placeholder="entity (테이블)" />
                          <input className="afs-input" value={fField}
                            onChange={(e) => setFField(e.target.value)} placeholder="field (필드)" />
                          <input className="afs-input" value={fType}
                            onChange={(e) => setFType(e.target.value)} placeholder="type (선택)" />
                          <input className="afs-input" value={fMappedAttr}
                            onChange={(e) => setFMappedAttr(e.target.value)}
                            placeholder="→ 우리 속성명 (선택)" />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center',
                          justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                          <label className="afs-ink" style={{ display: 'flex', alignItems: 'center',
                            gap: 6, fontSize: 13, cursor: 'pointer' }}>
                            <input type="checkbox" checked={fIsKey}
                              onChange={(e) => setFIsKey(e.target.checked)} />
                            is_key (외부 기본키)
                          </label>
                          <button className="secondary-button" onClick={handleAddField}
                            disabled={busy !== null}>+ 필드</button>
                        </div>

                        {schema.status !== 'ok' ? (
                          <EmptyOrError state={schema.status} error={schema.error}
                            emptyText="등록된 스키마가 없습니다."
                            onRetry={() => sel && refreshSel(sel)} />
                        ) : (schema.value || []).length > 0 && (
                          <div style={{ maxHeight: 140, overflowY: 'auto' }}>
                            {(schema.value || []).map((f) => (
                              <div key={`${f.entity}.${f.field}`} className="afs-muted"
                                style={{ fontFamily: 'monospace', fontSize: 12 }}>
                                {f.is_key ? '🔑 ' : '· '}{f.entity}.{f.field}
                                {f.field_type ? ` (${f.field_type})` : ''}
                                {f.mapped_attr ? ` → ${f.mapped_attr}` : ''}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </Panel>
                  </div>

                  {/* 매핑 초안 */}
                  <div style={{ marginTop: 14 }}>
                    <Panel kicker="PROPOSALS" title={`매핑 제안 (대기 ${pending.length})`}
                      action={
                        <button className="secondary-button" disabled={busy !== null}
                          onClick={() => (useLlm ? confirmPropose.ask(true) : doPropose())}>
                          {busy === 'propose' ? '생성 중…' : '🔎 매핑 초안 생성'}
                        </button>}>
                      <div className="panel-body">
                        <label className="afs-ink" style={{ display: 'flex', alignItems: 'center',
                          gap: 6, fontSize: 13, cursor: 'pointer' }}>
                          <input type="checkbox" checked={useLlm}
                            onChange={(e) => setUseLlm(e.target.checked)} />
                          {/* ⚠️ 쿼터를 쓰는 선택지는 그 사실을 화면에 적는다 — 체크박스 title 로만
                              두면 아무도 읽지 않는다. */}
                          Flash 보강 — 애매한 후보를 LLM 으로 추가 제안합니다
                          <b className="afs-warn-fg">(LLM 쿼터를 소비합니다)</b>
                        </label>

                        <ConfirmInline open={confirmPropose.open}
                          title="LLM 을 호출해 초안을 보강합니다"
                          body={<>결정론 규칙으로 못 찾은 후보를 Flash 모델에 물어봅니다 —
                            <b> LLM 쿼터를 소비합니다.</b> 결과는 제안일 뿐이며 승인 전에는
                            아무것도 확정되지 않습니다.</>}
                          confirmLabel="보강 실행" danger={false}
                          onCancel={confirmPropose.cancel}
                          onConfirm={() => confirmPropose.run(() => doPropose())} />

                        {proposals.status !== 'ok' ? (
                          // ★★★ 승인 대기는 관문이다 — 못 본 것을 «없다» 로 보여주면 관문이 비어 보인다.
                          <EmptyOrError state={proposals.status} error={proposals.error}
                            emptyText="대기 중 제안이 없습니다."
                            onRetry={() => sel && refreshSel(sel)} />
                        ) : pending.length === 0 ? (
                          <p className="afs-muted" style={{ fontSize: 13 }}>
                            대기 중 제안이 없습니다. 스키마 등록 후 [매핑 초안 생성] 을 누르십시오.
                          </p>
                        ) : (
                          pending.map((p) => (
                            <div key={p.id} className="afs-bg-sunken afs-border"
                              style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                                padding: '8px 12px' }}>
                              <div style={{ display: 'flex', alignItems: 'center',
                                justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontSize: 13 }}>
                                    <span className="afs-success-fg" style={{ fontFamily: 'monospace' }}>
                                      {p.master_code}
                                    </span>
                                    {' → '}
                                    <span className="afs-info-fg" style={{ fontFamily: 'monospace' }}>
                                      {p.external_key}
                                    </span>
                                    <span className="afs-muted"> · 신뢰도 {p.confidence}</span>
                                  </div>
                                  <div className="afs-muted" style={{ fontSize: 12 }}>{p.rationale}</div>
                                </div>
                                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                  <button className="primary-button" disabled={busy !== null}
                                    onClick={() => { setApproveKey(p.external_key); confirmApprove.ask(p); }}>
                                    승인
                                  </button>
                                  <button className="secondary-button" disabled={busy !== null}
                                    onClick={() => handleReject(p)}>기각</button>
                                </div>
                              </div>

                              {/* ★ `prompt()` 를 대신한다 — 무엇이 확정되는지 화면 안에서 보여준다. */}
                              {confirmApprove.open && confirmApprove.target?.id === p.id && (
                                <>
                                  <div style={{ marginTop: 8 }}>
                                    <label htmlFor={`cw-key-${p.id}`} className="afs-muted"
                                      style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                                      확정할 외부 키 (인스턴스 값 지정 가능 — 예:
                                      work_order:WO_TYPE=ASSY)
                                    </label>
                                    <input id={`cw-key-${p.id}`} className="afs-input"
                                      style={{ width: '100%' }} value={approveKey}
                                      onChange={(e) => setApproveKey(e.target.value)} />
                                  </div>
                                  <ConfirmInline open
                                    title="이 매핑을 확정합니다"
                                    body={<>
                                      <b>{p.master_code}</b> 를 외부 키{' '}
                                      <b>{approveKey.trim() || p.external_key}</b> 로 확정합니다.
                                      확정된 매핑은 이후 <b>모든 실측 조회의 주소록</b>이 됩니다 —
                                      틀리면 다른 시스템의 값을 우리 표준으로 읽게 됩니다.
                                    </>}
                                    confirmLabel="매핑 확정" danger={false}
                                    onCancel={() => { confirmApprove.cancel(); setApproveKey(''); }}
                                    onConfirm={() => confirmApprove.run((t) => doApprove(t))} />
                                </>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </Panel>
                  </div>

                  {/* 승인된 매핑 */}
                  <div style={{ marginTop: 14 }}>
                    <Panel kicker="CONFIRMED"
                      title={`승인된 크로스워크 (${(mappings.value || []).length})`}
                      action={<span className="afs-muted" style={{ fontSize: 12 }}>
                        M3 가상 통합 주소록 — 🔄 로 외부 실측값을 온디맨드 조회합니다
                      </span>}>
                      <div className="panel-body">
                        {mappings.status !== 'ok' ? (
                          <EmptyOrError state={mappings.status} error={mappings.error}
                            emptyText="승인된 매핑이 없습니다."
                            onRetry={() => sel && refreshSel(sel)} />
                        ) : (mappings.value || []).length === 0 ? (
                          <p className="afs-muted" style={{ fontSize: 13 }}>승인된 매핑이 없습니다.</p>
                        ) : (
                          (mappings.value || []).map((m) => {
                            const lr = liveResults[m.master_code];
                            return (
                              <div key={m.master_code} className="afs-bg-sunken afs-border"
                                style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                                  padding: '6px 10px', fontSize: 13 }}>
                                <div style={{ display: 'flex', alignItems: 'center',
                                  justifyContent: 'space-between', gap: 8 }}>
                                  <span style={{ fontFamily: 'monospace', overflow: 'hidden',
                                    textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    <span className="afs-success-fg">{m.master_code}</span>
                                    {' ↔ '}
                                    <span className="afs-info-fg">{m.external_key}</span>
                                  </span>
                                  <button className="secondary-button" style={{ flexShrink: 0 }}
                                    onClick={() => handleResolve(m.master_code)}
                                    disabled={busy !== null}>🔄 실측 조회</button>
                                </div>
                                {lr && (
                                  <div style={{ marginTop: 4, fontSize: 12 }}>
                                    {lr.ok === false ? (
                                      <span className="afs-danger-fg">조회 실패: {lr.error}</span>
                                    ) : (
                                      <span className="afs-muted">
                                        실측:{' '}
                                        <span className="afs-ink">
                                          {Object.entries(lr.values || {})
                                            .map(([k, v]) => `${k}=${v}`).join(', ') || '(빈값)'}
                                        </span>
                                        {' · as_of '}{String(lr.as_of || '').slice(0, 19)}
                                        {lr.cached ? ' · cache' : ''}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    </Panel>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </HubDialog>
  );
}
