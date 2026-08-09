// [이관 2/10 · UIUX-AUDIT-33] 기준정보 마스터
//
// 자재·공정·설비·KPI 같은 느리게 변하는 기준값을 결정론적으로 관리한다. 지식 허브가
// «관련 문서를 찾아 주는 곳»이라면 이 화면은 «같은 코드에는 같은 값을 주는 곳»이다.
// 자체 fetch·alert·confirm·모달을 제거하고 데이터 기반 공용 계약을 그대로 사용한다.
import { useCallback, useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import {
  ConfirmInline, EvidenceStrip, FormField, FoundationList, FoundationToolbar,
  VersionHistory, foundationJarvis, useConfirm,
} from '../design/DataFoundationShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { useLatestOnly } from '../design/useLatestOnly';
import { errorTitle } from '../lib/closedLoopFetch';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import {
  masterDataApi, type CsvImportReport, type GroundingPreview, type MasterRecord,
  type MasterType,
} from '../lib/masterDataApi';

type View = 'catalog' | 'register' | 'import' | 'preview';

const MODULE = {
  catalog: { kicker: 'MASTER DATA', title: '기준정보', subtitle: '모델이 바뀌어도 동일하게 적용되는 골든 레코드입니다.' },
  register: { kicker: 'REVISE', title: '등록·개정', subtitle: '같은 코드를 다시 저장하면 구판을 보존하고 새 버전을 만듭니다.' },
  import: { kicker: 'BULK', title: 'CSV 일괄등록', subtitle: '행별 성공·실패를 분리해 결과를 남깁니다.' },
  preview: { kicker: 'INJECTION', title: '주입 미리보기', subtitle: '실제 에이전트 프롬프트에 들어갈 기준정보 블록을 확인합니다.' },
};

const EMPTY_RECORD = {
  code: '', name: '', domains: '', aliases: '', attrs: '', core: false,
};

function csvList(value: string): string[] {
  return value.split(',').map((v) => v.trim()).filter(Boolean);
}

function jsonObject(value: string, label: string): Record<string, unknown> | undefined {
  if (!value.trim()) return undefined;
  const parsed = JSON.parse(value);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`${label}은(는) JSON 객체여야 합니다.`);
  }
  return parsed as Record<string, unknown>;
}

export function MasterDataPanel({ onClose }: { onClose: () => void }) {
  //: [설계 §6.1] 늦게 온 응답을 버리는 표 — 다른 것을 고른 뒤 옛 응답이 그려지지 않게.
  const claim = useLatestOnly();
  const [view, setView] = useState<View>('catalog');
  const [types, setTypes] = useState<Loaded<MasterType[]>>(loading<MasterType[]>());
  const [records, setRecords] = useState<Loaded<MasterRecord[]>>(ok<MasterRecord[]>([]));
  const [detail, setDetail] = useState<Loaded<MasterRecord | null>>(ok<MasterRecord | null>(null));
  const [selectedType, setSelectedType] = useState('');
  const [selectedCode, setSelectedCode] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  // ★★ [2026-08-04 실측 결함] 종전에는 숨김 건수를 숫자 두 개로만 들고 있었고, 배너가
  //   "유형 14개와 레코드 0건은 표시하지 않습니다" 처럼 **한 문장으로 합성**했다. 두 가지가 틀렸다:
  //     ① 레코드 건수는 «선택한 유형·검색 조건» 기준인데 문장은 전체처럼 읽힌다.
  //     ② 가린 것이 없는 쪽이 «0건»으로 함께 나가서 "숨겨진 자료 없음"으로 오해된다.
  //   → 있는 쪽만 각각 말한다. 건수는 서버가 DA·관리자에게만 주므로 `null` 이면 «있다»만 말한다.
  const EMPTY_VIS = { typesHidden: false, typesCount: null as number | null,
    recordsHidden: false, recordsCount: null as number | null };
  const [visibility, setVisibility] = useState(EMPTY_VIS);

  const [typeForm, setTypeForm] = useState({ id: '', name: '', desc: '', schema: '' });
  const [recordForm, setRecordForm] = useState(EMPTY_RECORD);
  const [aliasDraft, setAliasDraft] = useState('');
  const [previewText, setPreviewText] = useState('');
  const [previewDomains, setPreviewDomains] = useState('');
  const [previewScope, setPreviewScope] = useState('');
  const [preview, setPreview] = useState<Loaded<GroundingPreview | null>>(ok(null));
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvReport, setCsvReport] = useState<CsvImportReport | null>(null);
  const [csvKey, setCsvKey] = useState(0);

  const retire = useConfirm<string>();
  const removeAlias = useConfirm<string>();

  const run = useCallback(async <T,>(label: string, fn: () => Promise<T>, success?: string) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      const value = await fn();
      reportRequestSuccess();
      if (success) setFlash(success);
      return value;
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setErr({ msg: e?.message || String(e), status: e?.status });
      return null;
    } finally {
      setBusy(null);
    }
  }, []);

  const loadTypes = useCallback(async () => {
    setTypes(loading<MasterType[]>());
    try {
      const value = await masterDataApi.types();
      setVisibility((v) => ({ ...v, typesHidden: value.hiddenPresent,
        typesCount: value.hiddenCount }));
      setTypes(value.blockedReason
        ? { status: 'forbidden', value: null, error: value.blockedReason, httpStatus: 403 }
        : ok(value.rows));
      reportRequestSuccess();
      setSelectedType((current) => value.rows.some((t) => t.type_id === current)
        ? current : value.rows[0]?.type_id || '');
    } catch (e: any) {
      setTypes(failed<MasterType[]>(e)); reportRequestFailure(e?.status);
    }
  }, []);

  const loadRecords = useCallback(async (typeId: string, query = '') => {
    if (!typeId) { setRecords(ok<MasterRecord[]>([])); return; }
    const isCurrent = claim();   // §6.1 — 요청 직전에 표를 뽑는다
    setRecords(loading<MasterRecord[]>());
    try {
      const value = await masterDataApi.records(typeId, query);
      // ★ [§6.1] 유형을 연달아 고르거나 검색어를 빠르게 치면 앞의 결과가 뒤에 도착한다 —
      //   기준정보는 «이 유형에 이런 코드가 있다» 를 읽는 화면이라 섞이면 그대로 틀린다.
      if (!isCurrent()) return;
      setVisibility((v) => ({ ...v, recordsHidden: value.hiddenPresent,
        recordsCount: value.hiddenCount }));
      setRecords(value.blockedReason
        ? { status: 'forbidden', value: null, error: value.blockedReason, httpStatus: 403 }
        : ok(value.rows));
      reportRequestSuccess();
      setSelectedCode((current) => value.rows.some((r) => r.master_code === current) ? current : '');
    } catch (e: any) {
      setRecords(failed<MasterRecord[]>(e)); reportRequestFailure(e?.status);
    }
  }, []);

  const selectRecord = useCallback(async (code: string) => {
    setSelectedCode(code); setDetail(loading<MasterRecord | null>()); setAliasDraft('');
    try {
      const value = await masterDataApi.record(code);
      setDetail(ok(value)); reportRequestSuccess();
    } catch (e: any) {
      setDetail(failed<MasterRecord | null>(e)); reportRequestFailure(e?.status);
    }
  }, []);

  useEffect(() => { loadTypes(); }, [loadTypes]);
  useEffect(() => {
    setSearch(''); setSelectedCode(''); setDetail(ok(null)); setCsvReport(null);
    loadRecords(selectedType);
  }, [selectedType, loadRecords]);
  useEffect(() => {
    const onUser = () => {
      setSelectedType(''); setSelectedCode(''); setDetail(ok(null));
      setVisibility(EMPTY_VIS);
      setTypes(loading<MasterType[]>()); setRecords(ok([])); loadTypes();
    };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [loadTypes]);

  const typeRows = types.value || [];
  const recordRows = records.value || [];
  const selectedTypeData = typeRows.find((t) => t.type_id === selectedType) || null;
  const selectedRecord = detail.value;
  const railItems: RailItem[] = [
    { id: 'catalog', label: '유형·레코드', hint: '골든 레코드 조회', icon: 'catalog',
      count: types.status === 'ok' ? recordRows.length : undefined,
      countLabel: `현재 유형 레코드 ${recordRows.length}건` },
    { id: 'register', label: '등록·개정', hint: '구판을 보존해 개정', icon: 'revise' },
    { id: 'import', label: 'CSV 일괄등록', hint: '행별 결과 확인', icon: 'csv' },
    { id: 'preview', label: '주입 미리보기', hint: '에이전트가 받는 값', icon: 'inject' },
  ];

  const jarvisState = selectedType ? records : types;
  const jarvis = foundationJarvis({
    module: `master_data/${view}`,
    moduleTitle: MODULE[view].title,
    objectType: selectedRecord ? 'master_record' : 'master_type',
    selected: selectedRecord
      ? { id: selectedRecord.master_code, title: selectedRecord.name,
        meta: `${selectedRecord.master_code} · v${selectedRecord.version} · ${selectedRecord.domains.join(', ') || '도메인 미지정'}` }
      : selectedTypeData
        ? { id: selectedTypeData.type_id, title: selectedTypeData.name_ko,
          meta: `${selectedTypeData.type_id} · 레코드 ${recordRows.length}건` }
        : null,
    state: jarvisState,
    counts: {
      types: types.status === 'ok' ? typeRows.length : null,
      records: records.status === 'ok' ? recordRows.length : null,
    },
    actions: selectedRecord
      ? ['별칭 관리', '개정 등록', '주입 미리보기', '폐기']
      : ['유형 생성', '레코드 등록', 'CSV 일괄등록'],
    evidence: selectedRecord ? [
      { label: '코드', value: selectedRecord.master_code },
      { label: '버전', value: `v${selectedRecord.version}` },
      { label: '출처', value: selectedRecord.source || '미상' },
    ] : [],
  });

  const createType = async () => {
    if (!typeForm.id.trim() || !typeForm.name.trim()) {
      setErr({ msg: 'type_id와 한글명을 입력하십시오.' }); return;
    }
    let schema: Record<string, unknown> | undefined;
    try { schema = jsonObject(typeForm.schema, '속성 스키마'); }
    catch (e: any) { setErr({ msg: e.message || String(e) }); return; }
    const id = typeForm.id.trim();
    const result = await run('유형 생성 중', () => masterDataApi.createType({
      type_id: id, name_ko: typeForm.name.trim(), description: typeForm.desc.trim(), attr_schema: schema,
    }), '기준정보 유형을 만들었습니다. 이제 레코드를 등록하십시오.');
    if (result) {
      setTypeForm({ id: '', name: '', desc: '', schema: '' });
      await loadTypes(); setSelectedType(id);
    }
  };

  const saveRecord = async () => {
    if (!selectedType) { setErr({ msg: '기준정보 유형을 먼저 선택하십시오.' }); return; }
    if (!recordForm.code.trim() || !recordForm.name.trim()) {
      setErr({ msg: '코드와 정식 명칭을 입력하십시오.' }); return;
    }
    let attrs: Record<string, unknown> | undefined;
    try { attrs = jsonObject(recordForm.attrs, '속성값'); }
    catch (e: any) { setErr({ msg: e.message || String(e) }); return; }
    const code = recordForm.code.trim();
    const result = await run('레코드 저장 중', () => masterDataApi.saveRecord({
      master_code: code, type_id: selectedType, name: recordForm.name.trim(), attributes: attrs,
      domains: csvList(recordForm.domains), aliases: csvList(recordForm.aliases),
      is_core: recordForm.core,
    }), '기준정보를 저장했습니다. 같은 코드가 있었다면 새 버전으로 개정됐습니다.');
    if (result) {
      setRecordForm(EMPTY_RECORD); await loadRecords(selectedType, search); await selectRecord(code);
      setView('catalog');
    }
  };

  const doRetire = async (code: string) => {
    const done = await run('레코드 폐기 중', () => masterDataApi.retireRecord(code),
      '현행 주입 대상에서 제외했습니다. 개정 이력은 보존됩니다.');
    if (done !== null) {
      setSelectedCode(''); setDetail(ok(null)); await loadRecords(selectedType, search);
    }
  };

  const addAlias = async () => {
    if (!selectedRecord || !aliasDraft.trim()) return;
    const updated = await run('별칭 추가 중',
      () => masterDataApi.addAlias(selectedRecord.master_code, aliasDraft.trim()), '별칭을 추가했습니다.');
    if (updated) { setAliasDraft(''); setDetail(ok(updated)); await loadRecords(selectedType, search); }
  };

  const doRemoveAlias = async (alias: string) => {
    if (!selectedRecord) return;
    const updated = await run('별칭 제거 중',
      () => masterDataApi.removeAlias(selectedRecord.master_code, alias), '별칭을 제거했습니다.');
    if (updated) { setDetail(ok(updated)); await loadRecords(selectedType, search); }
  };

  const runPreview = async () => {
    if (!previewText.trim()) return;
    setPreview(loading<GroundingPreview | null>());
    const result = await run('주입 계산 중',
      () => masterDataApi.preview(previewText.trim(), csvList(previewDomains), previewScope.trim()));
    setPreview(result ? ok(result) : failed(new Error('주입 미리보기를 가져오지 못했습니다.')));
  };

  const importCsv = async () => {
    if (!selectedType || !csvFile) {
      setErr({ msg: '기준정보 유형과 CSV 파일을 선택하십시오.' }); return;
    }
    const result = await run('CSV 등록 중', () => masterDataApi.importCsv(selectedType, csvFile));
    if (result) {
      setCsvReport(result); setCsvFile(null); setCsvKey((v) => v + 1);
      setFlash(`CSV ${result.total}행 중 ${result.imported}행을 등록했습니다.`);
      await loadRecords(selectedType, search);
    }
  };

  return (
    <HubDialog label="기준정보 마스터 — 골든 레코드와 주입 기준" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>기준정보 마스터</b>
        <span>골든 레코드는 확정 조회로 모든 에이전트에 동일하게 주입됩니다</span>
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
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>DETERMINISTIC</span>
              <b>문서 검색이 아니라 확정값입니다</b>
              <p>같은 코드에는 같은 값이 적용됩니다. 개정은 구판을 지우지 않고 새 버전을 만듭니다.</p>
            </div>
          }
          jarvis={<JarvisRail contextTitle={jarvis.title} contextDescription={jarvis.desc}
            evidence={jarvis.ev} context={jarvis.ctx}
            quickQuestions={[
              '이 기준정보는 어떤 산출물에 영향을 줍니까?',
              '현재 별칭과 도메인 범위가 충분합니까?',
              '이 문장에는 어떤 기준정보가 주입됩니까?',
            ]} />}
        >
          {err && <Banner tone="error" title={errorTitle(err.status)}>{err.msg}</Banner>}
          {flash && <Banner tone="info">{flash}</Banner>}
          {/* ⚠️ 두 문장을 합치지 않는다. 가린 것이 있는 쪽만 말하고, 레코드는 **무엇을 기준으로 센
              것인지**(선택 유형·검색 조건)를 문장 안에 밝힌다. 종전 «유형 14개와 레코드 0건» 문장은
              전체 기준으로 읽혀서 "숨겨진 레코드 없음"으로 오해됐다. */}
          {visibility.typesHidden && (
            <Banner tone="warn">
              {visibility.typesCount === null
                ? '조직 범위 밖의 기준정보 유형은 표시하지 않았습니다 — 현재 조직 범위 자료만 표시 중입니다.'
                : `조직 범위 밖의 기준정보 유형 ${visibility.typesCount}개는 표시하지 않았습니다.`}
            </Banner>
          )}
          {visibility.recordsHidden && (
            <Banner tone="warn">
              {`현재 선택한 ‘${selectedTypeData?.name_ko || selectedType || '유형 미선택'}’ 유형과 `
                + `검색 조건에서 조직 범위 밖 레코드`
                + (visibility.recordsCount === null
                  ? '는 표시하지 않았습니다 — 현재 조직 범위 자료만 표시 중입니다.'
                  : ` ${visibility.recordsCount}건을 표시하지 않았습니다.`)}
            </Banner>
          )}

          {view === 'catalog' && (
            <CatalogView
              types={types} records={records} detail={detail}
              typeRows={typeRows} recordRows={recordRows}
              selectedType={selectedType} setSelectedType={setSelectedType}
              selectedCode={selectedCode} selectRecord={selectRecord}
              search={search} setSearch={setSearch}
              onSearch={() => loadRecords(selectedType, search)} onRetryTypes={loadTypes}
              onRetryRecords={() => loadRecords(selectedType, search)}
              typeForm={typeForm} setTypeForm={setTypeForm} onCreateType={createType}
              aliasDraft={aliasDraft} setAliasDraft={setAliasDraft} onAddAlias={addAlias}
              removeAlias={removeAlias} onRemoveAlias={doRemoveAlias}
              retire={retire} onRetire={doRetire}
            />
          )}
          {view === 'register' && (
            <RegisterView types={typeRows} selectedType={selectedType} setSelectedType={setSelectedType}
              form={recordForm} setForm={setRecordForm} onSave={saveRecord} />
          )}
          {view === 'import' && (
            <ImportView types={typeRows} selectedType={selectedType} setSelectedType={setSelectedType}
              file={csvFile} setFile={setCsvFile} fileKey={csvKey}
              report={csvReport} onImport={importCsv} />
          )}
          {view === 'preview' && (
            <PreviewView text={previewText} setText={setPreviewText}
              domains={previewDomains} setDomains={setPreviewDomains}
              scope={previewScope} setScope={setPreviewScope}
              state={preview} onRun={runPreview} />
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}

function CatalogView(props: any) {
  const {
    types, records, detail, typeRows, recordRows, selectedType, setSelectedType,
    selectedCode, selectRecord, search, setSearch, onSearch, onRetryTypes, onRetryRecords,
    typeForm, setTypeForm, onCreateType, aliasDraft, setAliasDraft, onAddAlias,
    removeAlias, onRemoveAlias, retire, onRetire,
  } = props;
  const selected: MasterRecord | null = detail.value;
  const core = recordRows.filter((r: MasterRecord) => r.is_core).length;
  return (
    <>
      <ScreenHead kicker="MASTER DATA" title="기준정보 카탈로그"
        description="유형을 고르고 골든 레코드의 코드·별칭·속성·개정 이력을 확인합니다."
        chip={types.status !== 'ok'
          ? types.status === 'loading'
            ? { label: '확인 중', tone: 'muted' }
            : { label: types.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
          : { label: `${typeRows.length}개 유형`, tone: typeRows.length ? 'data' : 'muted' }} />

      <div className="metric-row">
        <Metric label="유형" state={types.status} value={types.status === 'ok' ? typeRows.length : null} />
        <Metric label="현행 레코드" state={records.status} value={records.status === 'ok' ? recordRows.length : null} />
        <Metric label="핵심 레코드" state={records.status} value={records.status === 'ok' ? core : null}
          hint="별칭 미언급 시 우선 주입" />
        {/* ⚠️ 버전은 **재는 값이 아니다.** 종전에는 지표용 기본 문구가 그대로 붙어
            "선택 버전 — / 미측정" 이 됐다. «미측정» 은 수치·지표에만 쓴다.
            네 상태를 각각 구분해 말한다: 조회 중 · 조회 불가 · 미지정 · 적용된 버전. */}
        <Metric label="적용 버전" state={detail.status}
          value={selected ? `v${selected.version}` : null}
          notes={{ loading: '버전 정보 조회 중', error: '버전 정보 조회 불가',
            forbidden: '버전 정보 조회 불가', empty: '적용 버전 미지정' }} />
      </div>

      <FoundationToolbar search={search} onSearch={(v) => { setSearch(v); if (!v) onSearch(); }}
        placeholder="선택한 유형의 명칭·별칭 검색"
        actions={<>
          <div style={{ minWidth: 220 }}>
            <TypeSelect types={typeRows} value={selectedType} onChange={setSelectedType} />
          </div>
          <button className="primary-button" disabled={!selectedType} onClick={onSearch}>검색</button>
        </>}
        hint="코드가 아니라 정식 명칭과 별칭을 찾습니다. 유형을 바꾸면 해당 유형의 현행판만 조회합니다." />

      {types.status !== 'ok' && (
        <Panel kicker="TYPES" title="기준정보 유형을 가져오지 못했습니다">
          <EmptyOrError state={types.status} error={types.error} onRetry={onRetryTypes}
            emptyText="등록된 기준정보 유형이 없습니다." />
        </Panel>
      )}

      {selectedType && (
        <EvidenceStrip items={[
          { label: '선택 유형', value: typeRows.find((t: MasterType) => t.type_id === selectedType)?.name_ko },
          { label: 'type_id', value: selectedType },
          { label: '현행 레코드', value: records.status === 'ok' ? `${recordRows.length}건` : '조회 불가' },
        ]} note={typeRows.find((t: MasterType) => t.type_id === selectedType)?.description
          || '유형 설명이 없습니다 — 무엇을 등록해야 하는지 다른 사용자가 판단하기 어렵습니다.'} />
      )}

      <div className="delivery-grid">
        <FoundationList kicker="RECORDS" title="현행 골든 레코드" state={records}
          onRetry={onRetryRecords}
          rows={recordRows.map((r: MasterRecord) => ({
            id: r.master_code, title: r.name,
            meta: `${r.master_code} · v${r.version} · ${r.domains.join(', ') || '도메인 미지정'}`,
            chip: r.is_core
              ? { label: 'CORE', tone: 'warn' as const }
              : { label: '현행', tone: 'success' as const },
          }))}
          selectedId={selectedCode} onSelect={selectRecord}
          emptyText={selectedType
            ? (search ? `«${search}»와 일치하는 현행 레코드가 없습니다.` : '이 유형에 현행 레코드가 없습니다.')
            : '기준정보 유형을 먼저 선택하십시오.'} />

        <Panel kicker="DETAIL" title={selected?.name || selectedCode}>
          {!selectedCode ? (
            <div className="empty-note">좌측에서 레코드를 선택하면 속성·별칭·개정 이력을 표시합니다.</div>
          ) : detail.status !== 'ok' || !selected ? (
            <EmptyOrError state={detail.status} error={detail.error}
              onRetry={() => selectRecord(selectedCode)} emptyText="레코드를 선택하십시오." />
          ) : (
            <div style={{ padding: 15 }}>
              <EvidenceStrip items={[
                { label: '마스터 코드', value: selected.master_code },
                { label: '현행 버전', value: `v${selected.version}` },
                { label: '출처', value: selected.source },
              ]} note={`적용 도메인: ${selected.domains.join(', ') || '미지정 — 주입 범위를 확인하십시오.'}`} />

              <div className="section-grid">
                <section>
                  <h4>속성</h4>
                  {Object.keys(selected.attributes || {}).length ? (
                    <dl className="section-kv">
                      {Object.entries(selected.attributes).map(([key, value]) => (
                        <div key={key}><dt>{key}</dt><dd>
                          {value && typeof value === 'object'
                            ? <pre className="mdm-attribute-json">{JSON.stringify(value, null, 2)}</pre>
                            : String(value)}
                        </dd></div>
                      ))}
                    </dl>
                  ) : <p className="section-missing">등록된 속성이 없습니다.</p>}
                </section>

                <section>
                  <h4>동의어·유사어</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                    {(selected.aliases || []).map((alias) => (
                      <span key={alias} className="state-chip muted" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                        {alias}
                        {alias !== selected.name && (
                          <button className="text-button" aria-label={`${alias} 별칭 제거`}
                            onClick={() => removeAlias.ask(alias)}>×</button>
                        )}
                      </span>
                    ))}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 7 }}>
                    <input className="afs-input" value={aliasDraft} placeholder="새 별칭"
                      onChange={(e) => setAliasDraft(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') onAddAlias(); }} />
                    <button className="secondary-button" disabled={!aliasDraft.trim()} onClick={onAddAlias}>추가</button>
                  </div>
                  <ConfirmInline open={!!removeAlias.target}
                    title={`«${removeAlias.target || ''}» 별칭을 제거합니다`}
                    body="이 표현으로는 더 이상 해당 기준정보가 매칭되지 않습니다. 정식 명칭과 다른 별칭만 제거할 수 있습니다."
                    confirmLabel="별칭 제거" onCancel={removeAlias.cancel}
                    onConfirm={() => removeAlias.run(onRemoveAlias)} />
                </section>

                <section>
                  <h4>개정 이력</h4>
                  <VersionHistory rows={(selected.history || []).map((h) => ({
                    id: `${selected.master_code}-${h.version}`,
                    version: `v${h.version}`,
                    at: h.updated_at || h.valid_from,
                    actor: h.source || '출처 미상',
                    summary: h.status === 'active' ? '현행 버전' : '보존된 구판',
                  }))} />
                </section>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                <button className="danger-ghost" onClick={() => retire.ask(selected.master_code)}>현행 레코드 폐기</button>
              </div>
              <ConfirmInline open={retire.target === selected.master_code}
                title={`«${selected.name}» 현행판을 폐기합니다`}
                body={<>v{selected.version}은 에이전트 주입 대상에서 제외됩니다. 물리 삭제하지 않고 이력으로 보존합니다.</>}
                confirmLabel="현행판 폐기" onCancel={retire.cancel}
                onConfirm={() => retire.run(onRetire)} />
            </div>
          )}
        </Panel>
      </div>

      {types.status !== 'forbidden' && <Panel kicker="NEW TYPE" title="새 기준정보 유형">
        <div style={{ padding: 15 }}>
          <div className="delivery-grid">
            <FormField label="type_id" required hint="영소문자·숫자·_·- 조합, 2~32자">
              <input className="afs-input" value={typeForm.id} placeholder="예: process"
                onChange={(e) => setTypeForm({ ...typeForm, id: e.target.value })} />
            </FormField>
            <FormField label="한글명" required>
              <input className="afs-input" value={typeForm.name} placeholder="예: 공정"
                onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} />
            </FormField>
          </div>
          <FormField label="설명" hint="이 유형에 무엇을 등록해야 하는지 판단할 수 있게 적으십시오.">
            <input className="afs-input" value={typeForm.desc}
              onChange={(e) => setTypeForm({ ...typeForm, desc: e.target.value })} />
          </FormField>
          <FormField label="속성 스키마 JSON" hint={'예: {"표준리드타임_h":{"type":"number"}}'}>
            <textarea className="afs-textarea" value={typeForm.schema}
              onChange={(e) => setTypeForm({ ...typeForm, schema: e.target.value })} />
          </FormField>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!typeForm.id.trim() || !typeForm.name.trim()}
              onClick={onCreateType}>유형 만들기</button>
          </div>
        </div>
      </Panel>}
    </>
  );
}

function TypeSelect({ types, value, onChange }: {
  types: MasterType[]; value: string; onChange: (value: string) => void;
}) {
  return (
    <select className="afs-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">유형을 선택하십시오</option>
      {types.map((t) => <option key={t.type_id} value={t.type_id}>{t.name_ko} ({t.type_id})</option>)}
    </select>
  );
}

function RegisterView({ types, selectedType, setSelectedType, form, setForm, onSave }: any) {
  return (
    <>
      <ScreenHead kicker="REVISE" title="기준정보 등록·개정"
        description="같은 마스터 코드를 다시 저장하면 기존 현행판을 구판으로 보존하고 버전을 올립니다."
        chip={{ label: selectedType ? '유형 선택됨' : '유형 필요', tone: selectedType ? 'data' : 'warn' }} />
      <Panel kicker="RECORD" title="골든 레코드">
        <div style={{ padding: 15 }}>
          <FormField label="기준정보 유형" required>
            <TypeSelect types={types} value={selectedType} onChange={setSelectedType} />
          </FormField>
          <div className="delivery-grid">
            <FormField label="마스터 코드" required hint="대문자·숫자로 시작하고 _·- 사용 가능">
              <input className="afs-input" value={form.code} placeholder="예: PROC-ASSY-01"
                onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </FormField>
            <FormField label="정식 명칭" required>
              <input className="afs-input" value={form.name} placeholder="예: 조립 공정"
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </FormField>
          </div>
          <div className="delivery-grid">
            <FormField label="도메인" hint="콤마 구분. 예: manufacturing, logistics">
              <input className="afs-input" value={form.domains}
                onChange={(e) => setForm({ ...form, domains: e.target.value })} />
            </FormField>
            <FormField label="별칭" hint="콤마 구분. 정식 명칭은 자동 포함됩니다.">
              <input className="afs-input" value={form.aliases}
                onChange={(e) => setForm({ ...form, aliases: e.target.value })} />
            </FormField>
          </div>
          <FormField label="속성값 JSON" hint={'선택한 유형의 스키마를 따라야 합니다. 예: {"표준리드타임_h":72}'}>
            <textarea className="afs-textarea" value={form.attrs}
              onChange={(e) => setForm({ ...form, attrs: e.target.value })} />
          </FormField>
          <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={form.core}
              onChange={(e) => setForm({ ...form, core: e.target.checked })} />
            도메인 핵심 레코드 — 별칭이 직접 언급되지 않아도 우선 주입
          </label>
          <div className="request-alert warn" style={{ margin: '12px 0' }}>
            <i aria-hidden="true">!</i><div><b>같은 코드는 덮어쓰지 않습니다</b>
              <small>새 버전을 만들고 구판을 보존합니다. 코드가 같은지 저장 전에 확인하십시오.</small></div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!selectedType || !form.code.trim() || !form.name.trim()}
              onClick={onSave}>저장·개정</button>
          </div>
        </div>
      </Panel>
    </>
  );
}

function ImportView({ types, selectedType, setSelectedType, file, setFile, fileKey, report, onImport }: any) {
  return (
    <>
      <ScreenHead kicker="BULK" title="CSV 일괄등록"
        description="부분 성공을 허용하되 실패 행과 사유를 숨기지 않습니다."
        chip={report ? { label: `${report.imported}/${report.total} 성공`, tone: report.failed.length ? 'warn' : 'success' } : undefined} />
      <Panel kicker="UPLOAD" title="CSV 파일">
        <div style={{ padding: 15 }}>
          <FormField label="기준정보 유형" required>
            <TypeSelect types={types} value={selectedType} onChange={setSelectedType} />
          </FormField>
          <FormField label="CSV 파일" required
            hint="헤더: master_code,name,domains,aliases,attr:<속성명>… / domains·aliases는 ; 구분">
            <input key={fileKey} type="file" accept=".csv" className="afs-input"
              onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </FormField>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!selectedType || !file} onClick={onImport}>CSV 등록</button>
          </div>
        </div>
      </Panel>
      {report && (
        <Panel kicker="RESULT" title="등록 결과">
          <div style={{ padding: 15 }}>
            <EvidenceStrip items={[
              { label: '전체 행', value: report.total },
              { label: '성공', value: report.imported },
              { label: '실패', value: report.failed.length },
            ]} note="실패 행을 고쳐 다시 올리면 같은 코드는 새 버전으로 개정됩니다." />
            {report.failed.length > 0 && (
              <ul className="section-list">
                {report.failed.map((f: any) => <li key={`${f.row}-${f.master_code || ''}`}>
                  <b>행 {f.row}{f.master_code ? ` · ${f.master_code}` : ''}</b> {f.error}
                </li>)}
              </ul>
            )}
          </div>
        </Panel>
      )}
    </>
  );
}

function PreviewView({ text, setText, domains, setDomains, scope, setScope, state, onRun }: any) {
  const value: GroundingPreview | null = state.value;
  return (
    <>
      <ScreenHead kicker="INJECTION" title="주입 미리보기"
        description="벡터 검색 결과가 아니라 실제 에이전트 프롬프트에 들어갈 확정 기준정보를 보여줍니다."
        chip={value ? { label: `${value.matched.length}건 매칭`, tone: value.matched.length ? 'success' : 'muted' } : undefined} />
      <Panel kicker="QUERY" title="업무 문장과 도메인">
        <div style={{ padding: 15 }}>
          <FormField label="업무 문장" required hint="별칭과 정식 명칭이 이 문장 안에서 감지됩니다.">
            <textarea className="afs-textarea" value={text} placeholder="예: 조립 공정의 표준 리드타임을 단축한다"
              onChange={(e) => setText(e.target.value)} />
          </FormField>
          <FormField label="도메인" hint="콤마 구분. 비우면 문장 매칭과 핵심 레코드를 기준으로 계산합니다.">
            <input className="afs-input" value={domains} placeholder="예: manufacturing"
              onChange={(e) => setDomains(e.target.value)} />
          </FormField>
          <FormField label="조직 범위" hint="일반 사용자는 소속 범위 안의 ECM 노드 ID를 지정해야 합니다. 관리자는 비워도 됩니다.">
            <input className="afs-input" value={scope} placeholder="예: MNM_BATTERY"
              onChange={(e) => setScope(e.target.value)} />
          </FormField>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!text.trim()} onClick={onRun}>주입값 확인</button>
          </div>
        </div>
      </Panel>
      <Panel kicker="OUTPUT" title="에이전트가 받게 될 기준정보">
        {state.status !== 'ok' || !value ? (
          <EmptyOrError state={state.status} error={state.error} onRetry={onRun}
            emptyText="업무 문장을 입력하고 «주입값 확인»을 누르십시오." />
        ) : (
          <div style={{ padding: 15 }}>
            <EvidenceStrip items={[
              { label: '매칭 수', value: value.matched.length },
              { label: '매칭 코드', value: value.matched.join(', ') || '없음' },
              { label: '주입 여부', value: value.block ? '주입됨' : '주입 안 됨' },
            ]} note="매칭이 없으면 기준정보가 없는지, 별칭이 등록되지 않았는지 확인하십시오." />
            {value.block ? <pre className="mdm-preview-block">{value.block}</pre>
              : <div className="empty-note">이 문장에 주입되는 기준정보가 없습니다.</div>}
          </div>
        )}
      </Panel>
    </>
  );
}
