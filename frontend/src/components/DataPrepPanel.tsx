import { useEffect, useRef, useState } from 'react';

// ★★★ 손수 모달을 만들지 않는다 — 승인된 제품 셸을 쓴다(설계 §12 UI 규칙).
//   `HubDialog` 가 dialog semantics · 배경 inert · 포커스 트랩 · Escape 를 준다.
import { HubDialog } from '../design/HubDialog';
import { HubShell, Panel, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { DataReadinessBoard } from './DataReadinessBoard';
import {
  certifySnapshot, DataPrepError, getInstance, listInstances, listKits,
  listSnapshots, uploadSnapshot,
} from '../lib/dataPrepApi';

// [BDR-2·3·5 / Wave H] 업무 데이터 준비 패널.
//
// 파일럿 동선의 2~4칸을 한 화면에서 끝낸다:
//   Starter Package 확인 → 조직 적용본 선택 → 원천 결속 상태 → 파일 등록 → 준비 상태 확인
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **조회 실패와 0건을 구분한다.** 실패를 빈 목록으로 그리면 사용자는 「데이터가
//      없다」로 읽고 원인을 데이터에서 찾는다.
//   ② **기술 ID 를 앞세우지 않는다**(설계 §12 UI 규칙). 사람이 읽는 이름이 먼저다.
//   ③ **파일 등록 실패의 사유를 그대로 보여 준다.** 「올라가지 않는다」만 남으면
//      사용자는 파일이 아니라 시스템을 의심한다.

function Err({ error }: { error: { message: string; status: number } }) {
  return (
    <div style={{
      padding: 12, border: '1px solid var(--state-error-fg)', borderRadius: 6,
      background: 'var(--state-error-bg)', fontSize: 14,
    }}>
      <strong style={{ color: 'var(--state-error-fg)' }}>불러오지 못했습니다</strong>
      <div style={{ marginTop: 4 }}>{error.message}</div>
      <div style={{ marginTop: 4, fontSize: 13, color: 'var(--surface-text-muted)' }}>
        {/* ⚠️ 「없음」과 「지금 못 읽음」은 사용자가 할 일이 다르다. */}
        {error.status === 404
          ? '찾을 수 없습니다 — 조직 범위를 확인해 주십시오.'
          : '데이터가 없는 것이 아니라 지금 확인하지 못한 상태입니다.'}
      </div>
    </div>
  );
}

export function DataPrepPanel({ onClose, initialView = 'overview', page = false }: {
  onClose: () => void;
  initialView?: 'overview' | 'readiness';
  page?: boolean;
}) {
  const [packages, setPackages] = useState<any[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [instanceId, setInstanceId] = useState('');
  //: `null` = 아직 못 읽음, `[]` = 정말 0건. ⚠️ 둘을 같은 화면으로 그리면 사용자가
  //:   원인을 데이터에서 찾는다.
  const [instances, setInstances] = useState<any[] | null>(null);
  const [instance, setInstance] = useState<any | null>(null);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [busy, setBusy] = useState('');
  //: 계약 이름 → 사람이 읽는 이름. ⚠️ 화면이 제 나름의 번역표를 만들지 않는다 —
  //:   서버가 계약과 함께 준 것만 쓴다(없으면 계약 이름 그대로).
  const labelOf = (key: string) =>
    (instance?.required_datasets || []).find(
      (d: any) => d.dataset_contract_key === key)?.label || key;
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [activeSection, setActiveSection] = useState(
    initialView === 'readiness' ? 'instances' : 'packages');
  const packagesSectionRef = useRef<HTMLHeadingElement>(null);
  const instancesSectionRef = useRef<HTMLHeadingElement>(null);
  const instanceSectionRef = useRef<HTMLDivElement>(null);
  const sourceSectionRef = useRef<HTMLDetailsElement>(null);

  // ★ «열기» 뒤에는 사용자의 질문(어느 업무기능이 준비됐나)에 먼저 답한다.
  // 원천 파일 관리 표가 앞에 오면 35행을 지나야 준비도를 볼 수 있어, 업무키트가 평면
  // 데이터 목록처럼 보인다. 선택된 적용본이 그려진 다음 준비도 시작점으로 이동한다.
  useEffect(() => {
    if (instance) {
      setActiveSection('readiness');
      instanceSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }, [instance]);

  useEffect(() => {
    // 준비도 확인은 패키지 카탈로그와 독립적이다. 카탈로그 조회 장애 때문에 이미 적용된
    // 업무기능의 준비도까지 못 보는 것은 잘못된 결합이므로, 준비도 입구에서는 조회하지 않는다.
    if (initialView === 'overview') {
      listKits()
        .then((d) => setPackages(d.starter_packages || []))
        .catch((e: unknown) => {
          const err = e as DataPrepError;
          setError({ message: err?.message || '', status: err?.status || 0 });
        });
    } else {
      setPackages([]);
    }
    //: ⚠️ 목록 실패가 키트 화면까지 막지 않는다 — 실패는 목록 자리에만 남긴다.
    listInstances()
      .then((d) => {
        const visible = d.instances || [];
        setInstances(visible);
        // 홈의 「데이터 준비 상태」는 패키지 카탈로그가 아니라 현재 적용본의 준비도를
        // 묻는 입구다. 하나뿐이면 곧바로 연다. 여러 개면 임의 선택하지 않고 사용자가
        // 고르게 한다 — 다른 조직·업무기능을 대신 고르는 것은 편의가 아니라 오판이다.
        if (initialView === 'readiness' && visible.length === 1) {
          openInstance(visible[0].instance_id);
        }
      })
      .catch(() => setInstances(null));
  }, [initialView]);

  async function openInstance(id: string) {
    setInstanceId(id);
    setInstance(null);
    setSnapshots([]);
    setNotice(null);
    if (!id.trim()) return;
    try {
      setInstance(await getInstance(id.trim()));
      setSnapshots((await listSnapshots(id.trim())).snapshots || []);
    } catch (e) {
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '인스턴스를 열지 못했습니다.' });
    }
  }

  async function onCertify(snapshotId: string, rowCount: number) {
    setBusy(snapshotId);
    setNotice(null);
    try {
      // ⚠️ 원천 합계를 모르면 **행 수만이라도** 대사한다. 아무것도 안 주면 대사가
      //   «건너뛴 것» 이 되고, 잘린 파일이 그대로 인증된다.
      const out = await certifySnapshot(snapshotId, { row_count: rowCount });
      setNotice(out.state === 'DEMO_CERTIFIED'
        ? { ok: true, text: `인증됨 — ${out.display_label}` }
        // ★ 격리도 «실패» 가 아니라 **결과**다. 사유를 그대로 옮긴다.
        : { ok: false, text: `${out.state}: ${out.quarantine?.reason || '검사에서 멈췄습니다'}` });
      setSnapshots((await listSnapshots(instanceId)).snapshots || []);
    } catch (e) {
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '인증하지 못했습니다.' });
    } finally {
      setBusy('');
    }
  }

  async function onUpload(bindingId: string, file: File | null) {
    if (!file) return;
    setBusy(bindingId);
    setNotice(null);
    try {
      const snap = await uploadSnapshot(bindingId, file);
      setNotice({ ok: true, text: `${file.name} — ${snap.row_count}행 등록됨` });
      setSnapshots((await listSnapshots(instanceId)).snapshots || []);
    } catch (e) {
      // ★★★ 사유를 **그대로** 보여 준다. 「올라가지 않는다」만 남으면 사용자는
      //   파일이 아니라 시스템을 의심한다.
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '등록하지 못했습니다.' });
    } finally {
      setBusy('');
    }
  }

  const railItems: RailItem[] = [
    ...(initialView === 'overview' ? [{
      id: 'packages', label: '샘플 기업 패키지', hint: '사용 가능한 업무·데이터 구성을 봅니다',
      icon: 'packs' as const, count: packages?.length || undefined,
    }] : []),
    { id: 'instances', label: '조직 적용본', hint: '현재 조직에 적용된 패키지를 고릅니다',
      icon: 'apps', count: instances?.length || undefined },
    { id: 'readiness', label: '업무기능 준비도',
      hint: instance ? '계약·결속·인증판의 준비 상태' : '적용본 선택 후 열립니다', icon: 'checklist' },
    { id: 'sources', label: '원천·데이터 판',
      hint: instance ? '관리자용 결속·등록·인증 작업' : '적용본 선택 후 열립니다', icon: 'upload',
      count: snapshots.length || undefined },
  ];

  const selectSection = (id: string) => {
    setActiveSection(id);
    if (id === 'packages') packagesSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    if (id === 'instances') instancesSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    if (id === 'readiness') {
      if (!instance) {
        setNotice({ ok: false, text: '조직 적용본을 먼저 선택해야 준비도를 확인할 수 있습니다.' });
        setActiveSection('instances');
        return;
      }
      instanceSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
    if (id === 'sources') {
      if (!instance) {
        setNotice({ ok: false, text: '조직 적용본을 먼저 선택해야 원천과 데이터 판을 관리할 수 있습니다.' });
        setActiveSection('instances');
        return;
      }
      if (sourceSectionRef.current) sourceSectionRef.current.open = true;
      sourceSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  };

  return (
    <HubDialog page={page}
      label={initialView === 'readiness'
        ? '데이터 준비 상태 — 현재 적용본의 계약·결속·인증판'
        : '업무 데이터 준비 — 샘플 패키지·업무기능·데이터 판'}
      onClose={onClose}>
      {!page && <div className="afs-dialog-bar">
        <b>{initialView === 'readiness' ? '데이터 준비 상태' : '업무 데이터 준비'}</b>
        <span>{initialView === 'readiness'
          ? '현재 조직에 적용된 업무기능의 계약·원천 결속·인증판을 확인합니다'
          : '샘플 기업 패키지를 고르고 · 필요한 업무기능의 데이터를 준비합니다'}</span>
        <div className="bar-actions">
          <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      {/* ★★★ `.afs-dialog-body` 가 셸의 배경·여백 규약이다. 이걸 빼고 손수
          `padding` 만 주면 **배경이 없어 뒤 화면이 그대로 비친다** — 감사 게이트는
          그것을 잡지 못하고 통과시킨다(실측). */}
      <div className={`afs-dialog-body${page ? ' journey-product-body' : ''}`}>
        <HubShell layoutClassName={page ? 'product-page-shell' : ''}
          kicker="DATA READINESS"
          title={initialView === 'readiness' ? '데이터 준비 상태' : '업무 데이터 준비'}
          subtitle="업무기능별 계약·원천 결속·인증판을 한 흐름으로 준비합니다"
          items={railItems}
          activeId={activeSection}
          onSelect={selectSection}
          footer={
            <div className="inheritance-card">
              <span>NOT ZERO</span>
              <b>못 읽은 것은 0건이 아닙니다</b>
              <p>적용본·원천·인증판의 조회 실패와 실제 미등록 상태를 구분합니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextKicker="현재 데이터 문맥"
            contextTitle={instance?.label || '조직 적용본을 선택하십시오'}
            contextDescription={instance
              ? `${instance.entity_mode === 'VIRTUAL' ? '가상 시나리오 기준' : '실제 운영 기준'} · 현재 조직 문맥`
              : '현재 회사·조직에 적용된 업무기능을 고르면 계약과 인증판을 함께 봅니다.'}
            context={{
              current_module: `data-preparation/${activeSection}`,
              selected_object_type: instance ? 'kit_instance' : 'starter_package',
              selected_object_id: instanceId,
              object_snapshot: {
                active_section: activeSection,
                binding_count: instance?.bindings?.length ?? null,
                snapshot_count: instance ? snapshots.length : null,
              },
              available_actions: instance
                ? ['준비도 확인', '원천 결속 확인', '파일 등록', '데이터 판 인증']
                : ['조직 적용본 선택'],
              evidence_refs: snapshots.map((snapshot) => ({
                snapshot_id: snapshot.snapshot_id,
                dataset_contract_key: snapshot.dataset_contract_key,
                state: snapshot.state,
              })),
            }}
            evidence={instance ? [
              { label: '조직 범위', value: '현재 운영 문맥' },
              { label: '원천 결속', value: `${instance.bindings?.length || 0}건` },
              { label: '데이터 판', value: `${snapshots.length}건` },
            ] : []}
            quickQuestions={[
              '지금 준비가 막힌 업무기능은 무엇입니까?',
              '인증되지 않은 데이터 판은 무엇입니까?',
              '다음으로 연결해야 할 원천은 무엇입니까?',
            ]} />}
        >
        <Panel className="afs-fill data-prep-panel">
          {error ? <Err error={error} /> : (
            <>
              {initialView === 'overview' && (<>
              <h4 ref={packagesSectionRef} style={{ margin: '0 0 8px', fontSize: 15, scrollMarginTop: 12 }}>
                사용 가능한 샘플 기업 패키지
              </h4>
              {packages === null ? (
                <div style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>불러오는 중…</div>
              ) : packages.length === 0 ? (
                // ⚠️ 「0건」은 실패가 아니다 — 그 사실을 **그대로** 말한다.
                <div style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
                  등록된 샘플 패키지가 없습니다. 관리자에게 패키지 등록을 요청해 주십시오.
                </div>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 16px', display: 'grid', gap: 8 }}>
                  {packages.map((k) => {
                    const ready = k.catalog_status === 'AVAILABLE_FOR_DEMO';
                    return (
                      <li key={`${k.kit_id}@${k.version}`} style={{
                        padding: '10px 12px', border: '1px solid var(--surface-border)', borderRadius: 7,
                        background: ready ? 'var(--surface-card)' : 'var(--surface-sunken)',
                        fontSize: 14,
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <strong>{k.name || '이름 미등록 패키지'}</strong>
                          <span className={`state-chip ${ready ? 'success' : 'warn'}`}>
                            {ready ? '시연 가능' : '준비 중'}
                          </span>
                          <span style={{ color: 'var(--surface-text-muted)', fontSize: 12 }}>
                            데이터 {k.dataset_count} · 업무영역 {k.business_kit_count}
                            {' · '}실행 앱 {k.app_count} · 보고서 {k.report_count}
                          </span>
                        </div>
                        <div style={{ color: 'var(--surface-text-muted)', marginTop: 4, fontSize: 12 }}>
                          {k.description || '패키지 설명 준비 중'} · {k.data_kind}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
              </>)}

              <h4 ref={instancesSectionRef} style={{
                margin: initialView === 'overview' ? '16px 0 8px' : '0 0 8px',
                fontSize: 15, scrollMarginTop: 12,
              }}>
                {initialView === 'readiness'
                  ? '준비 상태를 확인할 적용본'
                  : '이 조직에 적용된 패키지'}
              </h4>

              {/* ★★★ 먼저 «이미 있는 것» 을 보여 준다. id 를 외워 오라고 하지 않는다. */}
              {instances === null ? (
                <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 8 }}>
                  적용된 패키지 목록을 지금 확인하지 못했습니다. 잠시 뒤 다시 시도하거나
                  관리자에게 데이터 준비 상태 점검을 요청하십시오.
                </div>
              ) : instances.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 8 }}>
                  이 조직 범위에 적용된 샘플 패키지가 아직 없습니다.
                </div>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 12px' }}>
                  {instances.map((it: any) => (
                    <li key={it.instance_id} style={{ marginBottom: 6 }}>
                      {/* ★ 줄 전체가 하나의 누를 곳이다 — 이름 옆에 작은 «열기» 를
                          따로 두면 누를 곳이 이름과 어긋난다. */}
                      <button
                        onClick={() => { setInstanceId(it.instance_id);
                                         openInstance(it.instance_id); }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                          textAlign: 'left', padding: '10px 12px',
                          border: '1px solid var(--surface-border)', borderRadius: 6,
                          background: '#fff', cursor: 'pointer', fontSize: 14,
                          fontFamily: 'inherit', color: 'inherit',
                        }}>
                        <span style={{ flex: 1 }}>
                          {/* 사람이 읽는 이름이 먼저다(설계 §12). */}
                          <strong>{it.label || '이름 미등록 적용본'}</strong>
                          <span style={{ color: 'var(--surface-text-muted)', marginLeft: 8, fontSize: 12 }}>
                            {it.entity_mode === 'VIRTUAL' ? '가상 기준' : '실제 운영 기준'}
                          </span>
                        </span>
                        <span style={{ color: 'var(--action-primary-bg)', fontSize: 13 }}>열기</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {/* 목록 장애를 ID 암기로 우회하게 하지 않는다. 기술 진단은 사용자 제품 화면이
                  아니라 관리자 관측 도구에서 다룬다. */}

              {notice && (
                <div style={{
                  padding: '8px 12px', borderRadius: 6, fontSize: 14, marginBottom: 12,
                  background: notice.ok ? 'var(--state-success-bg)' : 'var(--state-error-bg)',
                  border: `1px solid ${notice.ok ? 'var(--state-success-fg)' : 'var(--state-error-fg)'}`,
                  color: notice.ok ? '#065f46' : 'var(--state-error-fg)',
                }}>{notice.text}</div>
              )}

              {instance && (
                <div ref={instanceSectionRef} style={{ scrollMarginTop: 12 }}>
                  <DataReadinessBoard instanceId={instanceId.trim()} />

                  {/* 일반 사용자의 첫 질문은 준비도다. 원천·파일·판 관리는 필요할 때만
                      펼치는 관리자 작업으로 둔다. 기능을 숨기지 않고 위계만 바로잡는다. */}
                  <details ref={sourceSectionRef} style={{
                    margin: '4px 16px 16px', border: '1px solid var(--surface-border)',
                    borderRadius: 7, background: 'var(--surface-sunken)',
                  }}>
                    <summary style={{ cursor: 'pointer', padding: '10px 12px', fontSize: 14 }}>
                      관리자 작업 — 원천 결속·파일 등록·데이터 판
                    </summary>
                    <div style={{ padding: '0 12px 12px' }}>
                  <h4 style={{ margin: '8px 0', fontSize: 15 }}>원천 결속과 파일 등록</h4>
                  {(instance.bindings || []).length === 0 ? (
                    <div style={{ fontSize: 14, color: 'var(--surface-text-muted)' }}>
                      아직 원천이 연결되지 않았습니다.
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16 }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid var(--surface-border)', textAlign: 'left' }}>
                          <th style={{ padding: 8, fontSize: 13 }}>업무 데이터</th>
                          <th style={{ padding: 8, fontSize: 13 }}>결속 상태</th>
                          <th style={{ padding: 8, fontSize: 13 }}>파일 등록</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(instance.bindings || []).map((b: any) => (
                          <tr key={b.binding_id} style={{ borderBottom: '1px solid var(--surface-border)' }}>
                            <td style={{ padding: 8, fontSize: 14 }}>
                              {labelOf(b.dataset_contract_key)}
                              <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                                {b.dataset_contract_key}
                              </div>
                            </td>
                            <td style={{ padding: 8, fontSize: 14 }}>
                              {b.state}
                              {b.blocked_reason && (
                                <div style={{ color: 'var(--state-error-fg)', fontSize: 12 }}>
                                  {b.blocked_reason}
                                </div>
                              )}
                            </td>
                            <td style={{ padding: 8, fontSize: 13 }}>
                              {/* ⚠️ 활성 결속에만 올릴 수 있다 — 서버가 막기 전에 말한다. */}
                              {b.state === 'ACTIVE' ? (
                                <input type="file" accept=".csv"
                                  disabled={busy === b.binding_id}
                                  onChange={(e) => onUpload(b.binding_id,
                                    e.target.files?.[0] || null)} />
                              ) : (
                                <span style={{ color: 'var(--surface-text-muted)' }}>
                                  결속을 활성화한 뒤 올릴 수 있습니다.
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {/* ★★★ 계약이 요구하는데 **아직 연결되지 않은** 것도 한 줄로
                            남긴다. 연결된 것만 보이면 화면은 「다 됐다」처럼 보인다. */}
                        {(instance.required_datasets || [])
                          .filter((d: any) => !d.bound)
                          .map((d: any) => (
                            <tr key={d.dataset_contract_key}
                                style={{ borderBottom: '1px solid var(--surface-border)' }}>
                              <td style={{ padding: 8, fontSize: 14 }}>
                                {d.label || d.dataset_contract_key}
                                <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                                  {d.dataset_contract_key}
                                </div>
                              </td>
                              <td style={{ padding: 8, fontSize: 14, color: 'var(--state-warn-fg)' }}>
                                원천 미지정
                                <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                                  이 데이터를 어디서 가져올지 아직 고르지 않았습니다.
                                </div>
                              </td>
                              <td style={{ padding: 8, fontSize: 13, color: 'var(--surface-text-muted)' }}>
                                원천을 고른 뒤 올릴 수 있습니다.
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}

                  {snapshots.length > 0 && (
                    <>
                      <h4 style={{ margin: '16px 0 8px', fontSize: 15 }}>등록된 데이터 판</h4>
                      <ul style={{ paddingLeft: 18, margin: '0 0 16px' }}>
                        {snapshots.map((s) => (
                          <li key={s.snapshot_id} style={{ fontSize: 14, marginBottom: 8 }}>
                            {labelOf(s.dataset_contract_key)} · {s.state} · {s.row_count}행
                            {/* ★ 성격 표시는 서버가 준 문구를 그대로 쓴다 — 화면마다
                                각자 붙이면 한 화면에서 빠진다. */}
                            <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                              {s.display_label}
                            </div>
                            {/* ★★★ 인증은 «이 판을 공식으로 쓴다» 는 선언이다.
                                ⚠️ 이미 인증된 판·격리된 판에는 버튼을 두지 않는다 —
                                  누를 수 없는 버튼은 「고장」으로 읽힌다. */}
                            {s.state === 'RAW' ? (
                              <button disabled={busy === s.snapshot_id}
                                onClick={() => onCertify(s.snapshot_id, s.row_count)}
                                style={{
                                  marginTop: 4, padding: '4px 12px', fontSize: 13,
                                  border: '1px solid var(--action-primary-bg)', background: '#fff',
                                  color: 'var(--action-primary-bg)', borderRadius: 6, cursor: 'pointer',
                                }}>
                                {busy === s.snapshot_id ? '검사 중…' : '품질·대사 검사 후 시연 인증'}
                              </button>
                            ) : s.state === 'QUARANTINED' ? (
                              <div style={{ fontSize: 12, color: 'var(--state-error-fg)', marginTop: 2 }}>
                                격리됨 — {s.quarantine?.reason || '사유 미기재'}. 고친 파일을 다시 올리십시오.
                              </div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                    </div>
                  </details>
                </div>
              )}
            </>
        )}
        </Panel>
        </HubShell>
      </div>
    </HubDialog>
  );
}
