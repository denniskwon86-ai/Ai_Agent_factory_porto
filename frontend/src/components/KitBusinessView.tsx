import type { AppDatasetRow } from '../lib/kitAppViewApi';

type BusinessRow = Record<string, unknown>;

type DatasetView = {
  label: string;
  columns: string[];
};

type AppView = {
  title: string;
  description: string;
  defaultDataset: string;
  datasets: Record<string, DatasetView>;
};

const APP_VIEWS: Record<string, AppView> = {
  'APP-01': {
    title: '원료 도입 현황',
    description: '발주부터 선적·통관·입고까지 원료 도입의 진행 상태와 예외를 확인합니다.',
    defaultDataset: 'PRC-02',
    datasets: {
      'PRC-01': { label: '구매 계약', columns: ['contract_id', 'supplier_id', 'material_id', 'contract_quantity', 'ordered_quantity', 'benchmark_price', 'premium_rate', 'currency', 'valid_from', 'valid_to'] },
      'PRC-02': { label: '발주 현황', columns: ['po_line_id', 'supplier_id', 'material_id', 'order_date', 'due_date', 'order_quantity', 'quantity_uom', 'unit_price', 'currency', 'status'] },
      'LOG-01': { label: '공급사 제출', columns: ['submission_id', 'partner_id', 'business_ref', 'submission_status', 'submitted_at', 'revised_at'] },
      'LOG-02': { label: '선적 현황', columns: ['shipment_id', 'po_line_id', 'vessel_or_mode', 'origin_port', 'destination_port', 'shipment_quantity', 'quantity_uom', 'etd', 'eta', 'status'] },
      'LOG-03': { label: '운송 마일스톤', columns: ['shipment_id', 'event_type', 'planned_at', 'actual_at', 'location', 'status'] },
      'LOG-04': { label: '통관 현황', columns: ['shipment_id', 'declaration_date', 'inspection_status', 'duty_amount', 'currency', 'cleared_at', 'status'] },
      'LOG-05': { label: '입고 운송', columns: ['shipment_id', 'event_type', 'event_at', 'destination_location_id', 'delivered_quantity', 'quantity_uom', 'status'] },
      'EXT-01': { label: '환율 참고', columns: ['indicator_code', 'observed_at', 'value', 'unit', 'trust_grade'] },
      'EXT-02': { label: '원자재 가격', columns: ['commodity_code', 'observed_at', 'value', 'unit', 'currency', 'trust_grade'] },
      'EXT-03': { label: '운임 참고', columns: ['indicator_code', 'target_ref', 'observed_at', 'value', 'unit', 'trust_grade'] },
    },
  },
  'APP-03': {
    title: '재고·생산 영향',
    description: '가용재고와 안전재고, 생산계획·실적을 함께 보며 생산 차질 가능성을 확인합니다.',
    defaultDataset: 'INV-01',
    datasets: {
      'INV-01': { label: '재고 스냅숏', columns: ['snapshot_date', 'location_id', 'material_id', 'unrestricted_quantity', 'quality_quantity', 'blocked_quantity', 'safety_stock_quantity', 'quantity_uom'] },
      'INV-02': { label: '재고 이동', columns: ['movement_date', 'movement_type', 'material_id', 'from_location_id', 'to_location_id', 'quantity', 'quantity_uom', 'reference_type', 'reference_id'] },
      'MFG-01': { label: '생산 계획', columns: ['plan_line_id', 'plan_date', 'site_id', 'product_id', 'plan_quantity', 'quantity_uom', 'priority', 'material_requirement', 'capacity_requirement_hours', 'status'] },
      'MFG-02': { label: '생산 실적', columns: ['batch_id', 'plan_line_id', 'production_date', 'input_material_id', 'input_quantity', 'output_material_id', 'output_quantity', 'quantity_uom', 'actual_yield', 'downtime_hours', 'status'] },
      'MFG-03': { label: '설비 영향', columns: ['equipment_id', 'event_type', 'start_at', 'end_at', 'planned', 'root_cause', 'capacity_loss_hours'] },
      'QLT-01': { label: '품질 검사', columns: ['inspection_type', 'object_ref', 'inspection_date', 'characteristic', 'result_value', 'lower_spec', 'upper_spec', 'unit', 'verdict', 'action'] },
    },
  },
  'APP-04': {
    title: '구매원가·현금 전망',
    description: '구매 계약, 매입채무, 원가 차이와 현금흐름 근거를 같은 업무 맥락에서 확인합니다.',
    defaultDataset: 'FIN-02',
    datasets: {
      'PRC-01': { label: '구매 계약', columns: ['contract_id', 'supplier_id', 'material_id', 'ordered_quantity', 'benchmark_price', 'premium_rate', 'currency', 'payment_terms', 'valid_from', 'valid_to'] },
      'FIN-01': { label: '원가 차이', columns: ['fiscal_period', 'product_id', 'cost_component', 'standard_unit_cost', 'actual_unit_cost', 'variance_amount', 'currency', 'quantity_uom'] },
      'FIN-02': { label: '매입·지급', columns: ['finance_document_id', 'document_type', 'partner_id', 'reference_id', 'posting_date', 'due_date', 'amount', 'currency', 'paid_at', 'status'] },
      'FIN-03': { label: '현금흐름 근거', columns: ['document_id', 'posting_date', 'fiscal_period', 'account_id', 'cost_center_id', 'debit_amount', 'credit_amount', 'currency', 'cashflow_line', 'plan_actual'] },
      'EXT-01': { label: '환율 참고', columns: ['indicator_code', 'observed_at', 'value', 'unit', 'trust_grade'] },
      'EXT-02': { label: '원자재 가격', columns: ['commodity_code', 'observed_at', 'value', 'unit', 'currency', 'trust_grade'] },
    },
  },
};

const FIELD_LABELS: Record<string, string> = {
  po_line_id: '발주행', supplier_id: '공급사', material_id: '자재', order_date: '발주일',
  due_date: '납기일', order_quantity: '발주량', quantity_uom: '단위', unit_price: '단가',
  currency: '통화', status: '상태', contract_id: '계약', contract_quantity: '계약량',
  ordered_quantity: '누적 발주량', benchmark_price: '기준가격', premium_rate: '프리미엄',
  payment_terms: '지급조건', valid_from: '유효 시작', valid_to: '유효 종료',
  submission_id: '제출 건', partner_id: '거래처', business_ref: '업무 참조',
  submission_status: '제출 상태', submitted_at: '제출 시각', revised_at: '수정 시각',
  shipment_id: '선적', vessel_or_mode: '운송 수단', origin_port: '출발지',
  destination_port: '도착지', shipment_quantity: '선적량', etd: '출발 예정', eta: '도착 예정',
  event_type: '이벤트', planned_at: '예정 시각', actual_at: '실제 시각', location: '위치',
  declaration_date: '신고일', inspection_status: '검사 상태', duty_amount: '관세',
  cleared_at: '통관 시각', event_at: '발생 시각', destination_location_id: '입고 위치',
  delivered_quantity: '입고량', indicator_code: '지표', commodity_code: '원자재',
  target_ref: '대상', observed_at: '관측일', value: '값', unit: '단위', trust_grade: '신뢰 등급',
  snapshot_date: '기준일', location_id: '재고 위치', unrestricted_quantity: '가용 수량',
  quality_quantity: '품질 보류', blocked_quantity: '사용 차단', safety_stock_quantity: '안전재고',
  movement_date: '이동일', movement_type: '이동 유형', from_location_id: '출발 위치',
  to_location_id: '도착 위치', quantity: '수량', reference_type: '참조 유형', reference_id: '참조',
  plan_line_id: '계획행', plan_date: '계획일', site_id: '사업장', product_id: '제품',
  plan_quantity: '계획량', priority: '우선순위', material_requirement: '원료 소요량',
  capacity_requirement_hours: '필요 설비시간', batch_id: '생산 배치', production_date: '생산일',
  input_material_id: '투입 자재', input_quantity: '투입량', output_material_id: '산출 제품',
  output_quantity: '산출량', actual_yield: '실제 수율', downtime_hours: '중단 시간',
  equipment_id: '설비', start_at: '시작', end_at: '종료', planned: '계획 여부',
  root_cause: '원인', capacity_loss_hours: '생산능력 손실', inspection_type: '검사 유형',
  object_ref: '검사 대상', inspection_date: '검사일', characteristic: '검사항목',
  result_value: '결과', lower_spec: '하한', upper_spec: '상한', verdict: '판정', action: '조치',
  fiscal_period: '회계기간', cost_component: '원가 요소', standard_unit_cost: '표준 원가',
  actual_unit_cost: '실제 원가', variance_amount: '원가 차이', finance_document_id: '재무 문서',
  document_type: '문서 유형', posting_date: '전기일', amount: '금액', paid_at: '지급일',
  document_id: '전표', account_id: '계정', cost_center_id: '코스트센터', debit_amount: '차변',
  credit_amount: '대변', cashflow_line: '현금흐름 항목', plan_actual: '계획/실적',
};

const TECHNICAL_KEYS = new Set([
  'record_id', 'tenant_id', 'scope_node_id', 'data_class', 'business_data_kind',
  'data_origin', 'quality_status', 'certification_status', 'as_of_date', 'lineage_id',
  'created_at', 'updated_at', 'deleted',
]);

const STATUS_LABELS: Record<string, string> = {
  OPEN: '진행 중', PENDING: '대기', COMPLETED: '완료', DELIVERED: '도착 완료',
  CLEARED: '통관 완료', PAID: '지급 완료', RELEASED: '확정', CONFIRMED: '실적 확정',
  PASS: '적합', FAIL: '부적합', ACTUAL: '실적', PLAN: '계획',
};

function number(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function sum(rows: BusinessRow[], key: string): number {
  return rows.reduce((total, row) => total + (number(row[key]) ?? 0), 0);
}

function commonValue(rows: BusinessRow[], key: string): string {
  const values = Array.from(new Set(rows.map((row) => String(row[key] || '').trim()).filter(Boolean)));
  return values.length === 1 ? values[0] : '';
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 }).format(value);
}

/** 물질화된 데이터셋 이름은 `prc_01`, 계약 정본은 `PRC-01`을 쓴다.
 *  표기 차이를 업무 의미 차이로 취급하면 사람용 이름·기본 탭이 전부 사라진다. */
function canonicalDatasetKey(value: string): string {
  return String(value || '').trim().toUpperCase().replace(/_/g, '-');
}

function formatDateTime(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(date);
}

function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  if (key === 'premium_rate' || key === 'actual_yield') {
    const n = number(value);
    return n === null ? String(value) : `${formatNumber(n * 100)}%`;
  }
  const n = number(value);
  if (n !== null && !key.endsWith('_id') && !key.endsWith('_at') && !key.endsWith('_date')) {
    return formatNumber(n);
  }
  return STATUS_LABELS[String(value)] || String(value);
}

type Metric = { label: string; value: string; hint: string };

function metrics(appId: string, dataset: string, rows: BusinessRow[], total: number): Metric[] {
  const first = rows[0] || {};
  const uom = commonValue(rows, 'quantity_uom');
  const currency = commonValue(rows, 'currency');
  if (appId === 'APP-01' && dataset === 'PRC-02') {
    const open = rows.filter((row) => String(row.status || '').toUpperCase() === 'OPEN').length;
    const due = rows.map((row) => String(row.due_date || '')).filter(Boolean).sort()[0] || '—';
    return [
      { label: '발주행', value: `${total}건`, hint: `${rows.length}건을 현재 화면에서 확인` },
      { label: '진행 중', value: `${open}건`, hint: '현재 표시된 발주행 기준' },
      { label: '표시 발주량', value: uom ? `${formatNumber(sum(rows, 'order_quantity'))} ${uom}` : '단위 혼합', hint: uom ? '현재 표시 범위 합계' : '단위별로 나눠 확인 필요' },
      { label: '가장 이른 납기', value: due, hint: '현재 표시 범위 기준' },
    ];
  }
  if (appId === 'APP-03' && dataset === 'INV-01') {
    const below = rows.filter((row) => (number(row.unrestricted_quantity) ?? 0) < (number(row.safety_stock_quantity) ?? 0)).length;
    return [
      { label: '재고 항목', value: `${total}건`, hint: `${rows.length}건을 현재 화면에서 확인` },
      { label: '표시 가용재고', value: uom ? `${formatNumber(sum(rows, 'unrestricted_quantity'))} ${uom}` : '단위 혼합', hint: uom ? '현재 표시 범위 합계' : '단위별로 나눠 확인 필요' },
      { label: '표시 안전재고', value: uom ? `${formatNumber(sum(rows, 'safety_stock_quantity'))} ${uom}` : '단위 혼합', hint: uom ? '정책 기준량 합계' : '단위별로 나눠 확인 필요' },
      { label: '안전재고 미달', value: `${below}건`, hint: '현재 표시 범위 기준' },
    ];
  }
  if (appId === 'APP-04' && dataset === 'FIN-02') {
    const unpaid = rows.filter((row) => String(row.status || '').toUpperCase() !== 'PAID').length;
    return [
      { label: '재무 문서', value: `${total}건`, hint: `${rows.length}건을 현재 화면에서 확인` },
      { label: '미지급', value: `${unpaid}건`, hint: '현재 표시 범위 기준' },
      { label: '표시 금액', value: currency ? `${formatNumber(sum(rows, 'amount'))} ${currency}` : '통화 혼합', hint: currency ? '현재 표시 범위 합계' : '통화별로 나눠 확인 필요' },
      { label: '지급 완료', value: `${rows.length - unpaid}건`, hint: '현재 표시 범위 기준' },
    ];
  }
  const statusKey = rows.some((row) => 'status' in row) ? 'status' : '';
  const exceptionCount = statusKey
    ? rows.filter((row) => !['COMPLETED', 'DELIVERED', 'CLEARED', 'PAID', 'CONFIRMED', 'PASS'].includes(String(row.status || '').toUpperCase())).length
    : 0;
  return [
    { label: '전체 건수', value: `${total}건`, hint: `${rows.length}건을 현재 화면에서 확인` },
    { label: '현재 표시', value: `${rows.length}건`, hint: '화면 합계는 이 범위만 사용' },
    { label: statusKey ? '확인 필요 상태' : '데이터 기준일', value: statusKey ? `${exceptionCount}건` : String(first.as_of_date || '—'), hint: statusKey ? '완료 상태가 아닌 표시 건' : '인증판 기준' },
  ];
}

export function preferredDatasetName(appId: string, datasets: AppDatasetRow[]): string {
  const preferred = APP_VIEWS[appId]?.defaultDataset;
  return datasets.find((row) => canonicalDatasetKey(row.name) === preferred)?.name
    || datasets[0]?.name || '';
}

export function datasetDisplayName(appId: string, dataset: AppDatasetRow): string {
  return APP_VIEWS[appId]?.datasets[canonicalDatasetKey(dataset.name)]?.label
    || dataset.label || dataset.name;
}

export function KitBusinessView({
  appId, datasetName, datasetLabel, records, total, asOf, stale,
}: {
  appId: string;
  datasetName: string;
  datasetLabel: string;
  records: BusinessRow[];
  total: number;
  asOf: string;
  stale: boolean;
}) {
  const app = APP_VIEWS[appId];
  const datasetKey = canonicalDatasetKey(datasetName);
  const view = app?.datasets[datasetKey];
  const available = records.length ? new Set(Object.keys(records[0])) : new Set<string>();
  const columns = (view?.columns || Array.from(available).filter((key) => !TECHNICAL_KEYS.has(key)))
    .filter((key) => available.has(key));
  const allColumns = records.length ? Object.keys(records[0]) : [];
  const cards = metrics(appId, datasetKey, records, total);
  const first = records[0] || {};
  const synthetic = String(first.data_class || '').toUpperCase() === 'SYNTHETIC'
    || String(first.data_origin || '').toUpperCase() === 'SYNTHETIC';

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{app?.title || datasetLabel}</div>
          <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginTop: 2 }}>
            {app?.description || `${datasetLabel}의 인증된 업무 데이터를 확인합니다.`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {synthetic && (
            <span style={{
              fontSize: 12, padding: '3px 8px', borderRadius: 999,
              color: 'var(--state-warn-fg)', background: 'var(--state-warn-bg, #fff7ed)',
              border: '1px solid var(--state-warn-fg)',
            }}>시연용 합성 데이터</span>
          )}
          {asOf && (
            <span style={{
              fontSize: 12, padding: '3px 8px', borderRadius: 999,
              color: stale ? 'var(--state-warn-fg)' : 'var(--surface-text-muted)',
              border: `1px solid ${stale ? 'var(--state-warn-fg)' : 'var(--surface-border)'}`,
            }}>{stale ? '오래된 인증판' : '인증 기준'} · {formatDateTime(asOf)}</span>
          )}
          <span style={{
            fontSize: 12, padding: '3px 8px', borderRadius: 999,
            color: 'var(--surface-text-muted)', border: '1px solid var(--surface-border)',
          }} title={`데이터셋 식별자: ${datasetName}`}>{view?.label || datasetLabel}</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: 8 }}>
        {cards.map((card) => (
          <div key={card.label} style={{
            padding: '10px 12px', border: '1px solid var(--surface-border)', borderRadius: 8,
            background: 'var(--surface-base, var(--surface-raised))', minWidth: 0,
          }}>
            <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>{card.label}</div>
            <div style={{ fontSize: 19, fontWeight: 700, marginTop: 3, overflowWrap: 'anywhere' }}>{card.value}</div>
            <div style={{ fontSize: 11, color: 'var(--surface-text-muted)', marginTop: 3 }}>{card.hint}</div>
          </div>
        ))}
      </div>

      {records.length ? (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%', minWidth: 680 }}>
            <thead>
              <tr>{columns.map((column) => (
                <th key={column} style={{
                  textAlign: 'left', padding: '7px 9px', whiteSpace: 'nowrap',
                  borderBottom: '1px solid var(--surface-border)', color: 'var(--surface-text-muted)',
                  fontWeight: 600, background: 'var(--surface-base, var(--surface-raised))',
                }}>{FIELD_LABELS[column] || column}</th>
              ))}</tr>
            </thead>
            <tbody>
              {records.map((row, index) => (
                <tr key={String(row.record_id || index)}>{columns.map((column) => (
                  <td key={column} style={{
                    padding: '7px 9px', whiteSpace: 'nowrap',
                    borderBottom: '1px solid var(--surface-border)',
                  }}>{formatCell(column, row[column])}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
          이 데이터셋에는 표시할 업무 행이 없습니다.
        </div>
      )}

      {!!records.length && (
        <details style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
          <summary style={{ cursor: 'pointer' }}>관리자 진단 — 원본 칸 보기</summary>
          <div style={{ overflowX: 'auto', marginTop: 8 }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 11, minWidth: 720 }}>
              <thead><tr>{allColumns.map((column) => (
                <th key={column} style={{ textAlign: 'left', padding: '4px 7px', whiteSpace: 'nowrap', borderBottom: '1px solid var(--surface-border)' }}>{column}</th>
              ))}</tr></thead>
              <tbody>{records.map((row, index) => (
                <tr key={String(row.record_id || index)}>{allColumns.map((column) => (
                  <td key={column} style={{ padding: '4px 7px', whiteSpace: 'nowrap', borderBottom: '1px solid var(--surface-border)' }}>{formatCell(column, row[column])}</td>
                ))}</tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
