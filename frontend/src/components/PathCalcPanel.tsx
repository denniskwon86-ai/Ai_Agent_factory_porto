import { useCallback, useEffect, useRef, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { listInstances } from '../lib/dataPrepApi';
import {
  CalculationError, findImpactPaths, listOntologyObjects, runPathCalculation,
  runPathDecision,
  type CalcResult, type DecisionResult, type ImpactPath, type OntologyObject,
} from '../lib/calculationApi';
import { BaseValueFields } from './BaseValueFields';
import { BASE_FIELDS, DRIVER_FIELDS, num } from '../lib/calcFields';

// [G2 M0-4] 경로 계산 실행 — **질문을 고르고 답을 본다.**
//
// ## 이 화면이 메우는 자리
//
// 계산기·승인·준비도는 있었지만 **계산을 돌릴 화면이 없었다.** 프런트는 온톨로지를 한
// 번도 부르지 않았고, 시작점을 고를 방법이 없어 `dataset:shipment:SHP-001` 을 손으로
// 쳐야 했다 — 그것은 「개발자 도구 없이 완주」가 아니다.
//
// ## ⚠️ 이 화면이 지켜야 할 것
//
// ① **막힌 것을 «영향 없음» 으로 그리지 않는다.** `BLOCKED` 면 수치 칸을 아예 비우고
//    사유를 그 자리에 놓는다. 0 을 그리면 사용자는 그 위에서 보고서를 만든다.
// ② **사유를 두 층으로 보여 준다.** 대외 문구는 누설을 피해 뭉툭하고, 내부 사유가
//    「무엇이 없는가」를 말한다 — 둘 다 필요하다.
// ③ **판정하지 않는다.** 승인·범위·판은 서버가 정하고 화면은 질문만 보낸다.
// ④ **목록이 잘렸으면 잘렸다고 말한다.** 말하지 않으면 전부라고 믿는다.

/** 서버 계약과 같아야 한다 — 정량 관계만 계산이 붙는다(`ontology_path_adapter`). */
const RELATION_TYPES = ['AFFECTS'];

/** 정본 날짜 규칙 코드. ⚠️ 문자열을 화면에서 지어내지 않는다 — 서버 상수와 같아야 한다
 *  (`core.calc_models.DATE_ONLY_RULE`). */
const DATE_ONLY_RULE = 'date_only_is_midnight_utc';

function Err({ error }: { error: CalculationError }) {
  const hint =
    error.status === 403 ? '권한이 없습니다.'
    : error.status === 404 ? '그 경로를 찾을 수 없습니다 — 「경로 찾기」로 다시 고르십시오.'
    : error.status === 422 ? '요청이 성립하지 않습니다 — 아래 사유를 보십시오.'
    : error.status === 503 ? '데이터가 없는 것이 아니라 지금 확인하지 못한 상태입니다.'
    : '';
  return (
    <div style={{
      padding: 12, border: '1px solid var(--state-error-fg)', borderRadius: 6,
      background: 'var(--state-error-bg)', fontSize: 14, marginBottom: 12,
    }}>
      <strong style={{ color: 'var(--state-error-fg)' }}>계산하지 못했습니다 ({error.status})</strong>
      <div style={{ marginTop: 4 }}>{error.message}</div>
      {hint && <div style={{ marginTop: 4, fontSize: 13, color: 'var(--surface-text-muted)' }}>{hint}</div>}
    </div>
  );
}

function Metrics({ result }: { result: CalcResult }) {
  const names = Object.keys(result.metrics).sort();
  if (!names.length) {
    // ⚠️ 여기 오면 안 된다(COMPLETE 인데 지표가 없다). 0 으로 채우지 않고 그렇게 말한다.
    return (
      <Banner tone="warn">계산은 끝났는데 지표가 비어 있습니다 — 점검이 필요합니다.</Banner>
    );
  }
  return (
    <>
      {names.map((name) => {
        const series = result.metrics[name] || {};
        const keys = Object.keys(series).sort();
        if (!keys.length) {
          //: ⚠️⚠️ **빈 표를 그리지 않는다.** 머리말만 남으면 「0」으로 읽힌다 —
          //:   「해당하는 행이 없다」와 「값이 0이다」는 다른 답이다.
          return (
            <div key={name} style={{ marginBottom: 14 }}>
              <h4 style={{ margin: '0 0 4px', fontSize: 15 }}>{name}</h4>
              <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
                이 기준시점에 해당하는 행이 없습니다 — 값이 0인 것이 아닙니다.
              </div>
            </div>
          );
        }
        return (
          <div key={name} style={{ marginBottom: 14 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 15 }}>{name}</h4>
            <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
              <tbody>
                {keys.slice(0, 12).map((k) => {
                  const v = series[k];
                  // ★★★ **문자열 값은 「없음」의 표시다**(`missing_baseline` 등).
                  //   숫자 칸에 넣어 0 처럼 보이게 하지 않는다.
                  const missing = typeof v === 'string';
                  return (
                    <tr key={k} style={{ borderBottom: '1px solid var(--surface-border)' }}>
                      <td style={{ padding: '4px 12px 4px 0', color: 'var(--surface-text)' }}>{k}</td>
                      <td style={{
                        padding: '4px 0', textAlign: 'right',
                        color: missing ? 'var(--state-warn-fg)' : 'var(--surface-text)',
                        fontWeight: missing ? 400 : 600,
                      }}>
                        {missing ? `— ${v}` : String(v)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {keys.length > 12 && (
              <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 2 }}>
                {keys.length}건 중 12건만 표시했습니다.
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

export function PathCalcPanel({ onClose }: { onClose: () => void }) {
  const [instances, setInstances] = useState<any[] | null>(null);
  const [instanceId, setInstanceId] = useState('');
  // ★ 기준시점은 데모 날짜를 코드에 박지 않는다. 관계 승인은 벽시계 시각부터 유효한데
  // `type=date`의 00:00 UTC로 묻으면 오늘 오후에 승인한 관계도 «없음»으로 보인다.
  // 현지시각을 분 단위로 받아 실제 순간으로 바꿔 서버에 보낸다.
  const [asOf, setAsOf] = useState(() => {
    const now = new Date();
    const n = (v: number) => String(v).padStart(2, '0');
    return `${now.getFullYear()}-${n(now.getMonth() + 1)}-${n(now.getDate())}`
      + `T${n(now.getHours())}:${n(now.getMinutes())}`;
  });
  const [objects, setObjects] = useState<OntologyObject[] | null>(null);
  const [types, setTypes] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [rootKey, setRootKey] = useState('');
  const [targetType, setTargetType] = useState('');
  //: ★★★ 경로는 **여럿일 수 있다.** 서버는 하나를 고르라고 하는데 화면에 고를 자리가
  //:   없으면 404 로 끝난다 — 실측에서 그렇게 막혔다. 그래서 찾기와 계산을 나눈다.
  const [paths, setPaths] = useState<ImpactPath[] | null>(null);
  const [pathFp, setPathFp] = useState('');
  //: ★★★ **계산기는 기본값을 거부한다.** 「예약 수량이 없다」를 0 으로 보려면 사람이
  //:   그렇게 보겠다고 **말해야** 한다 — 조용히 0 으로 채우면 「예약 없음」과 「자료
  //:   없음」이 같아지고, 그 위에서 만든 숫자는 완성돼 보인다.
  const [reservedZero, setReservedZero] = useState(false);
  const [dateOnlyMidnight, setDateOnlyMidnight] = useState(false);
  const [result, setResult] = useState<CalcResult | null>(null);
  //: [G5] 안건 만들기 — 계산이 끝난 뒤에만 연다.
  const [baseValues, setBaseValues] = useState<Record<string, string>>({});
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [title, setTitle] = useState('');
  //: ★★★ **결정 문장은 제목이 아니다.** 「검토 요청」 같은 제목만 있으면 참석자는
  //:   무엇을 결정하는지 모르고, 회의록에는 「논의함」만 남는다.
  const [question, setQuestion] = useState('');
  const [owner, setOwner] = useState('');
  const [due, setDue] = useState('');
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [error, setError] = useState<CalculationError | null>(null);
  const [busy, setBusy] = useState('');
  const [activeSection, setActiveSection] = useState('question');
  const reqRef = useRef(0);
  const questionSectionRef = useRef<HTMLParagraphElement>(null);
  const pathsSectionRef = useRef<HTMLHeadingElement>(null);
  const resultSectionRef = useRef<HTMLDivElement>(null);
  const decisionSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listInstances()
      .then((r) => setInstances(r.instances || []))
      .catch((e) => setError(new CalculationError(
        e?.message || '키트 인스턴스 목록을 불러오지 못했습니다.', e?.status ?? 0)));
  }, []);

  const instant = asOf ? new Date(asOf).toISOString() : '';

  const loadObjects = useCallback(async () => {
    const seq = ++reqRef.current;
    setError(null);
    setBusy('objects');
    try {
      const got = await listOntologyObjects({ asOf: instant, relationTypes: RELATION_TYPES });
      if (reqRef.current !== seq) return;
      // A previous transient request can fail while this dialog is mounting and be followed by
      // a successful refresh.  Keeping that stale error beside a populated selector tells the
      // user both "loaded" and "failed".  The newest request sequence is authoritative.
      setError(null);
      setObjects(got.objects);
      setTypes(got.object_types);
      setTruncated(got.truncated);
    } catch (e: any) {
      if (reqRef.current !== seq) return;
      // ⚠️ 조회 실패를 빈 목록으로 그리지 않는다 — 「관계가 없다」로 읽힌다.
      setObjects(null);
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '객체 목록을 불러오지 못했습니다.', 0));
    } finally {
      if (reqRef.current === seq) setBusy('');
    }
  }, [instant]);

  useEffect(() => {
    let alive = true;
    void Promise.resolve().then(() => { if (alive) return loadObjects(); });
    return () => { alive = false; };
  }, [loadObjects]);

  const root = (objects || []).find(
    (o) => `${o.namespace}:${o.object_type}:${o.object_id}` === rootKey);

  async function onFind() {
    if (!root) return;
    setError(null);
    setPaths(null);
    setPathFp('');
    setResult(null);
    setBusy('find');
    try {
      const got = await findImpactPaths({
        roots: [root],
        target_types: targetType ? [targetType] : [],
        relation_types: RELATION_TYPES,
        as_of: instant,
      });
      setPaths(got.paths);
      //: 하나뿐이면 굳이 고르게 하지 않는다.
      if (got.paths.length === 1) setPathFp(got.paths[0].path_fingerprint);
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '경로를 찾지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }

  async function onRun() {
    if (!root || !instanceId.trim() || !pathFp) return;
    setError(null);
    setResult(null);
    setDecision(null);
    setBusy('run');
    try {
      setResult(await runPathCalculation({
        roots: [root],
        target_types: targetType ? [targetType] : [],
        relation_types: RELATION_TYPES,
        as_of: instant,
        instance_id: instanceId.trim(),
        path_fingerprint: pathFp,
        //: ★ 고른 것만 보낸다. 안 고르면 **보내지 않고**, 계산기가 「명시해야 한다」고
        //:   답한다 — 화면이 대신 정하지 않는다.
        assumptions: {
          ...(reservedZero ? { reserved_quantity_zero: true } : {}),
          ...(dateOnlyMidnight ? { date_only_rule: DATE_ONLY_RULE } : {}),
        },
      }));
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '계산하지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }


  //: ★★★ 안건의 기준선은 **계산이 읽은 그 판**이다. 다시 고르게 하지 않는다 —
  //:   다른 판을 고르면 「위쪽 숫자와 아래쪽 안건이 다른 자료를 본다」가 된다.
  const usedSnapshots = result ? Object.values(result.used_snapshots).sort() : [];

  async function onDecide() {
    if (!root || !result || result.status !== 'COMPLETE' || !pathFp) return;
    const missing = BASE_FIELDS.filter((f) => num(baseValues[f.key] || '') === null);
    if (missing.length) {
      //: ⚠️ 빈 칸을 0 으로 보내지 않는다 — 「모른다」와 「0이다」는 다르다.
      setError(new CalculationError(
        `기준값이 비어 있습니다: ${missing.map((f) => f.label).join(', ')} — `
        + '빈 칸을 0으로 채우지 않습니다.', 422));
      return;
    }
    setError(null);
    setBusy('decide');
    try {
      const base: Record<string, number> = {};
      for (const f of BASE_FIELDS) base[f.key] = num(baseValues[f.key] || '') as number;
      const scen: Record<string, number> = {};
      for (const f of DRIVER_FIELDS) {
        const v = num(drivers[f.key] || '');
        if (v !== null) scen[f.key] = v;
      }
      setDecision(await runPathDecision({
        roots: [root],
        target_types: targetType ? [targetType] : [],
        relation_types: RELATION_TYPES,
        as_of: instant,
        instance_id: instanceId.trim(),
        path_fingerprint: pathFp,
        assumptions: {
          ...(reservedZero ? { reserved_quantity_zero: true } : {}),
          ...(dateOnlyMidnight ? { date_only_rule: DATE_ONLY_RULE } : {}),
        },
        title, owner, due, question,
        snapshot_ids: usedSnapshots,
        base_values: base,
        scenario_assumptions: scen,
      }));
    } catch (e: any) {
      setError(e instanceof CalculationError ? e
        : new CalculationError(e?.message || '안건을 만들지 못했습니다.', 0));
    } finally {
      setBusy('');
    }
  }

  const canDecide = !!title.trim() && !!question.trim() && !!owner.trim()
    && !!due.trim() && busy !== 'decide';

  const canFind = !!rootKey && busy !== 'find';
  const canRun = !!pathFp && !!instanceId.trim() && busy !== 'run';

  useEffect(() => {
    if (paths === null) return;
    setActiveSection('paths');
    pathsSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [paths]);

  useEffect(() => {
    if (!result) return;
    setActiveSection('result');
    resultSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [result]);

  useEffect(() => {
    if (!decision) return;
    setActiveSection('decision');
    decisionSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [decision]);

  const railItems: RailItem[] = [
    { id: 'question', label: '질문·기준시점', hint: '자료·시점·시작점·가정을 정합니다', icon: 'search' },
    { id: 'paths', label: '영향 경로 선택',
      hint: paths === null ? '질문을 실행한 뒤 열립니다' : '승인된 관계 경로를 고릅니다',
      icon: 'flow', count: paths?.length || undefined },
    { id: 'result', label: '계산 결과·차단',
      hint: result ? '수치 또는 차단 사유를 확인합니다' : '경로 계산 후 열립니다', icon: 'cost' },
    { id: 'decision', label: '의사결정 안건 연결',
      hint: result?.status === 'COMPLETE' ? '봉인된 계산 결과로 안건을 만듭니다' : '계산 완료 후 열립니다',
      icon: 'decision' },
  ];

  const selectSection = (id: string) => {
    if (id === 'question') questionSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    if (id === 'paths' && paths !== null) pathsSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    if (id === 'result' && result) resultSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    if (id === 'decision' && result?.status === 'COMPLETE') {
      decisionSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
    const available = id === 'question' || (id === 'paths' && paths !== null)
      || (id === 'result' && !!result) || (id === 'decision' && result?.status === 'COMPLETE');
    if (available) setActiveSection(id);
    else setError(new CalculationError(id === 'paths'
      ? '시작점과 기준시점을 정해 경로를 먼저 찾으십시오.'
      : id === 'result'
        ? '승인된 영향 경로를 선택해 계산을 먼저 실행하십시오.'
        : '계산이 완료되어야 의사결정 안건으로 연결할 수 있습니다.', 409));
  };

  return (
    <HubDialog label="경로 계산" onClose={onClose}
      subtitle="승인된 관계를 따라가 부족량·생산가능량·매출 이연을 계산합니다 (LLM 0콜)">
      <div className="afs-dialog-body">
        <HubShell
          kicker="PATH CALCULATION"
          title="경로 계산"
          subtitle="승인된 업무 관계와 인증판 위에서만 영향을 계산합니다"
          items={railItems}
          activeId={activeSection}
          onSelect={selectSection}
          footer={
            <div className="inheritance-card">
              <span>NO SILENT ZERO</span>
              <b>막힌 계산은 숫자가 아닙니다</b>
              <p>승인·판·가정이 없으면 0을 표시하지 않고 차단 사유를 보여 줍니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextKicker="현재 영향 문맥"
            contextTitle={root
              ? `${root.object_type} · ${root.object_id}` : '영향 시작점을 선택하십시오'}
            contextDescription={result?.status === 'COMPLETE'
              ? '봉인된 경로·인증판·산식으로 계산을 완료했습니다.'
              : result?.status === 'BLOCKED'
                ? '계산이 막혔습니다. 차단 사유를 해결하기 전에는 숫자를 만들지 않습니다.'
                : '기준시점과 승인된 시작점을 고른 뒤 영향 경로를 찾습니다.'}
            context={{
              current_module: `path-calculation/${activeSection}`,
              selected_object_type: root?.object_type || 'ontology_object',
              selected_object_id: root?.object_id || '',
              object_snapshot: {
                as_of: instant,
                path_fingerprint: pathFp || null,
                calculation_status: result?.status || null,
                result_fingerprint: result?.status === 'COMPLETE' ? result.result_fingerprint : null,
              },
              available_actions: result?.status === 'COMPLETE'
                ? ['근거 확인', '의사결정 안건 만들기']
                : paths?.length ? ['경로 선택', '계산 실행'] : ['시작점 선택', '경로 찾기'],
              evidence_refs: result?.status === 'COMPLETE'
                ? Object.entries(result.used_snapshots).map(([key, snapshotId]) => ({
                    dataset_contract_key: key, snapshot_id: snapshotId,
                  })) : [],
            }}
            evidence={[
              { label: '기준시점', value: asOf || '미지정' },
              ...(paths !== null ? [{ label: '보이는 경로', value: `${paths.length}개` }] : []),
              ...(result ? [{ label: '계산 상태', value: result.status }] : []),
            ]}
            quickQuestions={[
              '이 경로가 막힌 이유는 무엇입니까?',
              '이 숫자는 어떤 인증판으로 만들었습니까?',
              '이 결과를 안건으로 만들 때 확인할 것은 무엇입니까?',
            ]} />}
        >
        <Panel className="path-calc-panel" kicker="영향 경로" title="경로 계산 — 질문을 고르고 답을 봅니다">
          <p ref={questionSectionRef} style={{
            fontSize: 13, color: 'var(--surface-text-muted)', margin: '0 0 12px', scrollMarginTop: 12,
          }}>
            승인된 관계를 따라가 <b>부족량·생산가능량·매출 이연</b>을 계산합니다.
            승인·판·기준선은 서버가 정합니다 — 여기서는 <b>질문만</b> 고릅니다.
          </p>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
                자료(키트 인스턴스)
              </label>
              {instances === null ? (
                <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>불러오는 중…</span>
              ) : instances.length === 0 ? (
                <span style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
                  내 범위에 인스턴스가 없습니다.
                </span>
              ) : (
                <select value={instanceId} onChange={(e) => setInstanceId(e.target.value)}
                  style={{ padding: 6, fontSize: 14, minWidth: 320 }}>
                  <option value="">— 고르십시오 —</option>
                  {instances.map((i) => (
                    <option key={i.instance_id} value={i.instance_id}>
                      {i.label || `${i.kit_id} ${i.version}`} · {i.scope_node_id}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
                기준시점(현지시각)
              </label>
              <input type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)}
                style={{ padding: 6, fontSize: 14 }} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap',
            alignItems: 'flex-end', marginTop: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
                시작점 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
              </label>
              {busy === 'objects' ? (
                <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>불러오는 중…</span>
              ) : objects === null ? (
                // ⚠️ 「없음」과 「못 읽음」을 가른다.
                <span style={{ fontSize: 13, color: 'var(--state-error-fg)' }}>
                  목록을 확인하지 못했습니다.
                </span>
              ) : objects.length === 0 ? (
                <span style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
                  이 기준시점에 보이는 승인된 관계가 없습니다.
                </span>
              ) : (
                <select value={rootKey} onChange={(e) => setRootKey(e.target.value)}
                  style={{ padding: 6, fontSize: 14, minWidth: 320 }}>
                  <option value="">— 고르십시오 —</option>
                  {objects.map((o) => {
                    const k = `${o.namespace}:${o.object_type}:${o.object_id}`;
                    return <option key={k} value={k}>{o.object_type} · {o.object_id}</option>;
                  })}
                </select>
              )}
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>
                도착 유형(비우면 전부)
              </label>
              <select value={targetType} onChange={(e) => setTargetType(e.target.value)}
                style={{ padding: 6, fontSize: 14, minWidth: 200 }}>
                <option value="">— 전부 —</option>
                {types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <button disabled={!canFind} onClick={onFind}
              style={{
                padding: '8px 18px', fontSize: 14, borderRadius: 6,
                border: '1px solid var(--action-primary-bg)', background: canFind ? 'var(--action-primary-bg)' : 'var(--surface-sunken)',
                color: canFind ? '#fff' : 'var(--surface-text-faint)',
                cursor: canFind ? 'pointer' : 'not-allowed',
              }}>
              {busy === 'find' ? '찾는 중…' : '경로 찾기'}
            </button>
            {/* ⚠️ 못 누르는 버튼에는 사유를 붙인다(§8.6). */}
            {!canFind && busy !== 'find' && (
              <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>시작점을 고르십시오.</span>
            )}
          </div>

          {truncated && (
            <div style={{ fontSize: 12, color: 'var(--state-warn-fg)', marginTop: 6 }}>
              시작점 목록이 잘렸습니다 — 전부가 아닙니다.
            </div>
          )}

          {/* ★★★ **사람이 해야 하는 판단.** 계산기가 기본값을 거부하는 자리이고,
              거부하는 이유를 그대로 옆에 적는다 — 체크박스만 있으면 그냥 켠다. */}
          <fieldset style={{
            marginTop: 14, border: '1px solid var(--surface-border)', borderRadius: 6, padding: 10,
          }}>
            <legend style={{ fontSize: 13, color: 'var(--surface-text)', padding: '0 6px' }}>
              계산 가정 — 사람이 정해야 합니다
            </legend>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 8 }}>
              <input type="checkbox" checked={reservedZero}
                onChange={(e) => setReservedZero(e.target.checked)}
                style={{ marginRight: 8 }} />
              예약 수량이 자료에 없는 것을 <b>0으로 본다</b>
              <div style={{ marginLeft: 24, fontSize: 12, color: 'var(--surface-text-muted)' }}>
                이 자료에는 예약 수량 칸이 없습니다. 켜지 않으면 계산기가 「명시해야
                한다」고 답합니다 — 조용히 0으로 채우면 「예약 없음」과 「자료 없음」이
                같아집니다.
              </div>
            </label>
            <label style={{ display: 'block', fontSize: 13 }}>
              <input type="checkbox" checked={dateOnlyMidnight}
                onChange={(e) => setDateOnlyMidnight(e.target.checked)}
                style={{ marginRight: 8 }} />
              날짜만 있는 값을 <b>그날 00:00 UTC</b> 로 본다
              <div style={{ marginLeft: 24, fontSize: 12, color: 'var(--surface-text-muted)' }}>
                시각이 없는 날짜를 어느 시점으로 읽을지 정합니다 — 규칙이 다르면 하루
                차이로 결과가 갈립니다.
              </div>
            </label>
          </fieldset>

          {paths !== null && (
            <div style={{ marginTop: 14 }}>
              <h4 ref={pathsSectionRef} style={{ margin: '0 0 6px', fontSize: 15, scrollMarginTop: 12 }}>
                찾은 경로 {paths.length}개
              </h4>
              {paths.length === 0 ? (
                /* ⚠️ 「없음」과 「못 읽음」을 가른다 — 여기는 정말 없는 것이다. */
                <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
                  이 시작점에서 보이는 승인된 경로가 없습니다 — 도착 유형이나 기준시점을
                  바꿔 보십시오.
                </div>
              ) : (
                <>
                  {paths.map((p) => (
                    <label key={p.path_fingerprint} style={{
                      display: 'block', padding: 8, marginBottom: 6, borderRadius: 6,
                      border: `1px solid ${pathFp === p.path_fingerprint
                        ? 'var(--action-primary-bg)' : 'var(--surface-border)'}`,
                      background: pathFp === p.path_fingerprint ? 'var(--state-info-bg)' : '#fff',
                      cursor: 'pointer',
                    }}>
                      <input type="radio" name="path"
                        checked={pathFp === p.path_fingerprint}
                        onChange={() => setPathFp(p.path_fingerprint)}
                        style={{ marginRight: 8 }} />
                      <span style={{ fontSize: 14 }}>
                        {p.nodes.map((n) => `${n.object_type} ${n.object_id}`).join(' → ')}
                      </span>
                      <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginLeft: 24 }}>
                        구간 {p.edges.length}개
                      </div>
                    </label>
                  ))}
                  <button disabled={!canRun} onClick={onRun}
                    style={{
                      padding: '8px 18px', fontSize: 14, borderRadius: 6,
                      border: '1px solid var(--action-primary-bg)',
                      /* ⚠️ 1차 행동은 구조색이다 — 초록은 «성공 상태» 전용(tokens.css). */
                      background: canRun ? 'var(--action-primary-bg)' : 'var(--surface-sunken)',
                      color: canRun ? '#fff' : 'var(--surface-text-faint)',
                      cursor: canRun ? 'pointer' : 'not-allowed',
                    }}>
                    {busy === 'run' ? '계산 중…' : '이 경로로 계산'}
                  </button>
                  {!canRun && busy !== 'run' && (
                    <span style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginLeft: 8 }}>
                      {!instanceId.trim() ? '자료를 고르십시오.' : '경로를 고르십시오.'}
                    </span>
                  )}
                </>
              )}
            </div>
          )}

          <div ref={resultSectionRef} style={{ marginTop: 16, scrollMarginTop: 12 }}>
            {error && <Err error={error} />}

            {result && result.status === 'BLOCKED' && (
              <>
                {/* ★★★ 수치 칸을 **아예 두지 않는다.** 빈 표를 두면 0 으로 읽힌다. */}
                <Banner tone="warn" title="아직 계산할 수 없습니다">
                  {result.blocked?.public_reason || '사유가 오지 않았습니다.'}
                </Banner>
                <div style={{
                  marginTop: 8, padding: 10, background: 'var(--surface-raised)', borderRadius: 6,
                }}>
                  <div style={{ fontSize: 13, color: 'var(--surface-text)', marginBottom: 4 }}>
                    무엇이 없는가
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {(result.blocked?.internal_reasons || []).map((r, i) => (
                      <li key={i} style={{ marginBottom: 2 }}>{r}</li>
                    ))}
                  </ul>
                  <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 6 }}>
                    「계산 실행 승인 · 시연 초기화」 화면의 <b>준비 상태</b>에서 남은 관문을
                    확인할 수 있습니다.
                  </div>
                </div>
              </>
            )}

            {result && result.status === 'COMPLETE' && (
              <>
                <Banner tone="info" title="계산했습니다">
                  이 숫자는 아래 <b>봉인된 판</b>과 <b>승인된 산식</b>으로 만들어졌습니다.
                </Banner>
                <div style={{ marginTop: 12 }}><Metrics result={result} /></div>
                <details style={{ marginTop: 10 }}>
                  <summary style={{ fontSize: 13, cursor: 'pointer', color: 'var(--action-primary-bg)' }}>
                    이 숫자는 무엇으로 만들었나
                  </summary>
                  <div style={{ fontSize: 12, color: 'var(--surface-text)', marginTop: 8 }}>
                    <div>결과 지문 {result.result_fingerprint}</div>
                    <div>요청 지문 {result.request_fingerprint}</div>
                    <div>경로 {result.query_id} / {result.path_fingerprint}</div>
                    <div style={{ marginTop: 6 }}>
                      기댄 관계 {result.required_relation_ids.join(', ') || '(없음)'}
                    </div>
                    <div style={{ marginTop: 6 }}>읽은 판</div>
                    <ul style={{ margin: '2px 0', paddingLeft: 18 }}>
                      {Object.entries(result.used_snapshots).sort().map(([k, v]) => (
                        <li key={k}>{k} — {v}</li>
                      ))}
                    </ul>
                    <div style={{ marginTop: 6 }}>산식 판</div>
                    <ul style={{ margin: '2px 0', paddingLeft: 18 }}>
                      {Object.entries(result.segment_model_versions).sort().map(([k, v]) => (
                        <li key={k}>{k} — {v}</li>
                      ))}
                    </ul>
                  </div>
                </details>

                {/* ── [G5] 이 결과로 안건 만들기 ─────────────────────────── */}
                <div ref={decisionSectionRef} style={{
                  marginTop: 18, borderTop: '1px solid var(--surface-border)',
                  paddingTop: 14, scrollMarginTop: 12,
                }}>
                  <h4 style={{ margin: '0 0 6px', fontSize: 15 }}>이 결과로 안건 만들기</h4>
                  <p style={{ fontSize: 13, color: 'var(--surface-text-muted)', margin: '0 0 10px' }}>
                    안건은 <b>계산이 읽은 그 판</b> 위에 섭니다({usedSnapshots.length}개) —
                    다시 고르지 않습니다. 아래 경영 수치는 <b>시뮬레이션</b>이 쓰는 값이고,
                    경로 계산의 지표와 <b>다른 집합</b>입니다.
                  </p>

                  <BaseValueFields
                    pick={{ instanceId: instanceId.trim(), snapshotIds: usedSnapshots }}
                    values={baseValues} onChange={setBaseValues} />

                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10 }}>
                    {DRIVER_FIELDS.map((f) => (
                      <div key={f.key}>
                        <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                          {f.label} ({f.unit})
                        </label>
                        <input value={drivers[f.key] || ''} inputMode="decimal"
                          onChange={(e) => setDrivers({ ...drivers, [f.key]: e.target.value })}
                          style={{ padding: 4, fontSize: 13, width: 110 }} />
                        {f.hint && (
                          <div style={{ fontSize: 11, color: 'var(--surface-text-faint)', maxWidth: 160 }}>
                            {f.hint}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap',
                    alignItems: 'flex-end', marginTop: 12 }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        안건 제목 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
                      </label>
                      <input value={title} onChange={(e) => setTitle(e.target.value)}
                        placeholder="예: 구매 지연 영향"
                        style={{ padding: 4, fontSize: 13, width: 240 }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        결정 문장 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
                      </label>
                      <input value={question} onChange={(e) => setQuestion(e.target.value)}
                        placeholder="무엇을 승인·기각하는가 (제목이 아닙니다)"
                        style={{ padding: 4, fontSize: 13, width: 340 }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        책임자 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
                      </label>
                      <input value={owner} onChange={(e) => setOwner(e.target.value)}
                        placeholder="user@company.com"
                        style={{ padding: 4, fontSize: 13, width: 220 }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
                        기한 <span style={{ color: 'var(--state-error-fg)' }}>*</span>
                      </label>
                      <input type="date" value={due}
                        // Embedded Chromium date controls may commit through `input` before
                        // `change` (the picker is native UI). Listen to both so a visibly filled
                        // deadline cannot leave the action disabled.
                        onInput={(e) => setDue((e.target as HTMLInputElement).value)}
                        onChange={(e) => setDue(e.target.value)}
                        style={{ padding: 4, fontSize: 13 }} />
                    </div>
                    <button disabled={!canDecide} onClick={onDecide}
                      style={{
                        padding: '8px 18px', fontSize: 14, borderRadius: 6,
                        border: '1px solid #7c3aed',
                        background: canDecide ? '#7c3aed' : 'var(--surface-sunken)',
                        color: canDecide ? '#fff' : 'var(--surface-text-faint)',
                        cursor: canDecide ? 'pointer' : 'not-allowed',
                      }}>
                      {busy === 'decide' ? '만드는 중…' : '안건 만들기'}
                    </button>
                    {!canDecide && busy !== 'decide' && (
                      <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
                        제목·결정 문장·책임자·기한이 필요합니다.
                      </span>
                    )}
                  </div>

                  {decision?.decision && (
                    <div style={{
                      marginTop: 12, padding: 12, border: '1px solid #ddd6fe',
                      background: '#faf5ff', borderRadius: 6,
                    }}>
                      <b style={{ color: '#6d28d9' }}>안건을 만들었습니다.</b>
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 13 }}>
                        {decision.decision.briefing.map((line, i) => (
                          <li key={i} style={{ marginBottom: 2 }}>{line}</li>
                        ))}
                      </ul>
                      <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginTop: 6 }}>
                        {/* ★★★ 계산 결속이 근거에 봉인됐음을 **보인다.** */}
                        계산 결속 결과 지문{' '}
                        {String(decision.decision.evidence?.calculation?.result_fingerprint
                          || '(없음)').slice(0, 16)}…
                      </div>
                      {/* ★ 저장된 안건이다 — 어디서 이어 가는지 말해 준다. */}
                      <div style={{ fontSize: 13, marginTop: 6 }}>
                        안건 <b>{decision.decision.decision_id}</b> 로 저장했습니다.
                        <div style={{ color: 'var(--surface-text-muted)', fontSize: 12 }}>
                          「협업·의사결정·발간」 화면에서 검토 요청·발간으로 이어 갑니다.
                        </div>
                      </div>
                    </div>
                  )}
                  {decision && !decision.decision && (
                    <Banner tone="warn" title="안건을 만들지 않았습니다">
                      계산이 완료되지 않았습니다 — 계산되지 않은 경로 옆에 숫자를 놓으면
                      그 숫자가 답으로 읽힙니다.
                    </Banner>
                  )}
                </div>
              </>
            )}
          </div>
        </Panel>
        </HubShell>
      </div>
    </HubDialog>
  );
}
