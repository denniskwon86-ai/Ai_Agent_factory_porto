import { useRef, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { HubShell, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { DataPrepError, simulate } from '../lib/dataPrepApi';
import {
  BASE_FIELDS, DRIVER_FIELDS as DRIVERS, num,
} from '../lib/calcFields';
import { BaselinePicker, type BaselineChoice } from './BaselinePicker';
import { BaseValueFields } from './BaseValueFields';

// [G4 / Wave H] 시나리오 시뮬레이션 화면 — 파일럿 동선 10~11칸.
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **숫자를 화면이 만들지 않는다.** 서버가 준 값을 그대로 옮긴다 — 화면이 계산하면
//      두 곳이 갈라지고, 갈린 날 어느 쪽이 맞는지 아무도 모른다.
//   ② **기준선 없이 못 돌린다.** Snapshot 집합을 명시해야 한다. 「최신으로 알아서」는
//      재현할 수 없는 숫자를 낳는다.
//   ③ **비율만 크게 보여주지 않는다.** 작은 기준값에서 «+300%» 가 나오고, 그것이
//      회의에서 실제 규모보다 크게 읽힌다. 값과 비율을 함께 둔다.

type ScenarioStage = 'baseline' | 'base' | 'drivers' | 'results';

const SCENARIO_ITEMS: RailItem[] = [
  { id: 'baseline', label: '1. 기준선', hint: '인증된 업무키트와 데이터 판 선택', icon: 'catalog' },
  { id: 'base', label: '2. 기준값', hint: '계산에 사용할 현재 값 확인', icon: 'checklist' },
  { id: 'drivers', label: '3. 변화 가정', hint: '환율·지연·단가 변화 입력', icon: 'revise' },
  { id: 'results', label: '4. 비교 결과', hint: '기준 대비 영향과 재현 지문 확인', icon: 'decision' },
];

export function ScenarioPanel({ onClose, page = false }: { onClose: () => void; page?: boolean }) {
  //: ★ id 를 타이핑하게 하지 않는다 — 고르개가 목록에서 집어 준다.
  const [pick, setPick] = useState<BaselineChoice>({ instanceId: '', snapshotIds: [] });
  const [base, setBase] = useState<Record<string, string>>({});
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<ScenarioStage>('baseline');
  const baselineRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLDivElement>(null);
  const driversRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLElement>(null);

  const goStage = (id: string) => {
    const next = id as ScenarioStage;
    setStage(next);
    const refs = { baseline: baselineRef, base: baseRef, drivers: driversRef, results: resultsRef };
    refs[next].current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  async function run() {
    setError(null);
    setResult(null);

    const ids = pick.snapshotIds;
    if (!pick.instanceId || ids.length === 0) {
      // ★★★ 서버가 막을 자리를 **누르기 전에** 말한다.
      setError('키트 인스턴스와 Snapshot ID 를 지정해 주십시오 — 「최신으로 알아서」는 '
        + '재현할 수 없는 숫자를 만듭니다.');
      return;
    }
    const baseValues: Record<string, number> = {};
    const missing: string[] = [];
    for (const f of BASE_FIELDS) {
      const v = num(base[f.key] || '');
      // ⚠️ 빈 칸을 0으로 채우지 않는다 — 「데이터가 없다」가 「값이 0이다」가 되면
      //   결과가 완성돼 보인다.
      if (v === null) missing.push(f.label);
      else baseValues[f.key] = v;
    }
    if (missing.length) {
      setError(`기준값이 비었습니다: ${missing.join(', ')} — 빈 값을 0으로 채우지 않습니다.`);
      return;
    }
    const assumptions: Record<string, number> = {};
    for (const d of DRIVERS) {
      const v = num(drivers[d.key] || '');
      if (v !== null) assumptions[d.key] = v;
    }

    setBusy(true);
    try {
      setResult(await simulate(pick.instanceId, ids, baseValues, assumptions));
    } catch (e) {
      const err = e as DataPrepError;
      setError(err?.message || '시뮬레이션을 돌리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const workspace = (
    <div className={page ? 'product-page-content scenario-page' : 'afs-scope scenario-dialog-content'}>
      {page && (
        <header className="scenario-page-head">
          <div>
            <small>MANAGEMENT DIGITAL TWIN</small>
            <h1>시뮬레이션</h1>
            <p>승인된 데이터 판과 고정된 기준선에서 가정을 바꾸고 경영 영향을 비교합니다.</p>
          </div>
          <div className="scenario-principle">
            <strong>같은 기준선 · 같은 입력 · 같은 결과</strong>
            <span>화면이 숫자를 만들지 않고 서버 계산 결과를 그대로 표시합니다.</span>
          </div>
        </header>
      )}

      <div className="scenario-workspace">
        <section className="scenario-controls" aria-label="시나리오 조건 설정">
          <header>
            <small>SCENARIO CONTROL</small>
            <h2>기준선과 가정</h2>
            <p>인증된 판을 고정한 뒤 기준값과 변화 조건을 입력합니다.</p>
          </header>

          <div ref={baselineRef} data-scenario-stage="baseline">
            <BaselinePicker value={pick} onChange={setPick} />
          </div>
          <div ref={baseRef} data-scenario-stage="base">
            <BaseValueFields pick={pick} values={base} onChange={setBase} />
          </div>

          <div ref={driversRef} data-scenario-stage="drivers">
            <h4 style={{ margin: '4px 0 8px', fontSize: 15 }}>변화 가정</h4>
            <div className="scenario-driver-grid">
              {DRIVERS.map((driver) => (
                <label key={driver.key}>
                  <span>{driver.label} <em>({driver.unit})</em></span>
                  <input value={drivers[driver.key] || ''} inputMode="decimal" placeholder="0"
                    onChange={(event) => setDrivers({
                      ...drivers, [driver.key]: event.target.value,
                    })} />
                  <small>{driver.hint}</small>
                </label>
              ))}
            </div>
          </div>

          <button onClick={run} disabled={busy} className="primary-button scenario-run">
            {busy ? '계산 중…' : '시뮬레이션 실행'}
          </button>
        </section>

        <section ref={resultsRef} className="scenario-results" aria-label="시뮬레이션 비교 결과"
          data-scenario-stage="results">
          <header>
            <div>
              <small>SCENARIO RESULTS</small>
              <h2>기준 대비 영향</h2>
            </div>
            <span className={result ? 'scenario-result-state ready' : 'scenario-result-state'}>
              {result ? '계산 완료' : '실행 대기'}
            </span>
          </header>

          {error && (
            <div className="scenario-error" role="alert">{error}</div>
          )}

          {!result ? (
            <div className="scenario-empty">
              <span aria-hidden="true">↗</span>
              <strong>왼쪽에서 기준선과 가정을 확정하십시오.</strong>
              <p>실행 전에는 결과를 0이나 빈 차트로 그리지 않습니다. 계산하지 않은 값은 결과가 아닙니다.</p>
              <ol>
                <li>업무키트와 인증 데이터 판 선택</li>
                <li>기준값 확인·보완</li>
                <li>변화 가정 입력 후 실행</li>
              </ol>
            </div>
          ) : (
            <div className="scenario-result-body">
              {/* 성격 표시를 결과 바로 위에 둔다 — 빠지면 이 숫자가 실적으로 읽힌다. */}
              <div className="scenario-baseline-banner">
                <strong>{result.baseline?.display_label || '성격을 알 수 없는 기준선입니다'}</strong>
                <span>기준시점 {result.baseline?.as_of?.slice(0, 16).replace('T', ' ') || '없음'}</span>
              </div>

              <div className="scenario-kpis">
                {(result.compare || []).slice(0, 4).map((row: any) => (
                  <article key={row.key}>
                    <span>{row.label}</span>
                    <strong>{row.scenario.toLocaleString()} <small>{row.unit}</small></strong>
                    <em className={row.delta < 0 ? 'down' : row.delta > 0 ? 'up' : ''}>
                      기준 대비 {row.delta > 0 ? '+' : ''}{row.delta.toLocaleString()}
                    </em>
                  </article>
                ))}
              </div>

              <div className="scenario-table-wrap">
                <table>
                  <thead>
                    <tr><th>결과</th><th>기준</th><th>시나리오</th><th>변화</th></tr>
                  </thead>
                  <tbody>
                    {(result.compare || []).map((row: any) => (
                      <tr key={row.key}>
                        <td>{row.label} <small>{row.unit}</small></td>
                        <td>{row.base.toLocaleString()}</td>
                        <td>{row.scenario.toLocaleString()}</td>
                        <td className={row.delta < 0 ? 'down' : row.delta > 0 ? 'up' : ''}>
                          {row.delta > 0 ? '+' : ''}{row.delta.toLocaleString()}
                          <small>{row.delta_pct === null ? '비율 없음'
                            : `${row.delta_pct > 0 ? '+' : ''}${row.delta_pct}%`}</small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <footer className="scenario-trace">
                산식 {result.scenario?.calc_version} · 기준선 지문{' '}
                {String(result.baseline?.fingerprint || '').slice(0, 12)} · 결과 지문{' '}
                {String(result.scenario?.fingerprint || '').slice(0, 12)}
              </footer>
            </div>
          )}
        </section>
      </div>
    </div>
  );

  if (page) return (
    <HubShell layoutClassName="product-page-shell scenario-product-shell"
      kicker="MANAGEMENT DIGITAL TWIN" title="시뮬레이션"
      subtitle="승인된 판과 고정 기준선에서 변화 가정을 비교합니다."
      items={SCENARIO_ITEMS} activeId={stage} onSelect={goStage}
      footer={<div className="inheritance-card">
        <span>REPRODUCIBLE</span>
        <b>같은 기준선 · 같은 입력 · 같은 결과</b>
        <p>화면은 숫자를 만들지 않고 서버 계산 결과와 재현 지문을 그대로 보여 줍니다.</p>
      </div>}
      jarvis={<JarvisRail
        contextTitle={pick.instanceId ? `시나리오 · ${pick.instanceId}` : '새 시나리오'}
        contextDescription={pick.instanceId
          ? '현재 선택한 업무키트·데이터 판·변화 가정을 기준으로 답합니다.'
          : '기준선을 선택하면 해당 데이터 판을 기준으로 답합니다.'}
        context={{
          current_module: 'management_twin',
          selected_object_type: result ? 'scenario_result' : 'scenario_draft',
          selected_object_id: result?.scenario?.fingerprint || pick.instanceId,
          object_snapshot: {
            instance_id: pick.instanceId, snapshot_ids: pick.snapshotIds,
            assumptions: drivers, result_fingerprint: result?.scenario?.fingerprint,
          },
          available_actions: ['기준선 설명', '가정 영향 점검', '결과 근거 확인'],
        }}
        evidence={pick.instanceId ? [
          { label: '업무키트', value: pick.instanceId },
          { label: '봉인된 데이터 판', value: `${pick.snapshotIds.length}개` },
          { label: '계산 상태', value: result ? '완료' : busy ? '계산 중' : '실행 전' },
        ] : []}
        quickQuestions={[
          '이 시나리오의 기준선과 데이터 판을 설명해 주세요.',
          '입력한 가정이 어떤 경영 지표에 영향을 줍니까?',
          '결과를 의사결정에 쓰기 전에 무엇을 확인해야 합니까?',
        ]} />}
    >
      {workspace}
    </HubShell>
  );
  return (
    <HubDialog label="시나리오 시뮬레이션 — 환율·지연·전력단가" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>시나리오 시뮬레이션</b>
        <span>고정된 기준선 위에서만 계산합니다 — 같은 입력이면 같은 답입니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">계산 중…</span>}
          <button onClick={onClose} className="secondary-button">닫기 (Esc)</button>
        </div>
      </div>
      <div className="afs-dialog-body scenario-dialog-body">{workspace}</div>
    </HubDialog>
  );
}
