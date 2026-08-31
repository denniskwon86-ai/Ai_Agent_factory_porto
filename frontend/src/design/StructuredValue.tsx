/**
 * API의 구조화 값을 사람이 읽는 카드·목록으로 그린다.
 *
 * 결정·발간 화면이 객체 안의 배열을 `JSON.stringify()` 한 줄로 노출하면, 지표명이
 * 길거나 항목이 여러 개인 순간 본문 폭을 사실상 잃는다. 원본 값은 그대로 두고 표현만
 * 나눠서, 검토자가 값의 구조와 빠진 항목을 눈으로 확인할 수 있게 한다.
 */

const LABELS: Record<string, string> = {
  as_of: '기준 시각', baseline_fingerprint: '기준선 지문', baseline_id: '기준선 연결',
  data_kind: '데이터 구분', snapshot_ids: '인증 데이터 판', assumptions: '가정',
  compared: '지표 비교', base: '기준', scenario: '시나리오', delta: '변화',
  delta_pct: '변화율', key: '지표 코드', label: '지표', unit: '단위',
  fx_rate_pct: '환율 변동률', lead_time_days: '리드타임', power_price_pct: '전력비 변동률',
};

const label = (key: string) => LABELS[key] || key.replaceAll('_', ' ');

/** 내부 식별자는 원장·API 결속에는 필요하지만 사람이 읽는 문서 값은 아니다.
 * 값 자체를 가리는 대신 결속 여부와 개수만 보여 주어, «근거 없음»으로 오해하지 않게 한다. */
const internalReference = (key: string) => key === 'id' || key.endsWith('_id')
  || key.endsWith('_ids') || key.endsWith('_code');

function referenceSummary(value: unknown) {
  if (Array.isArray(value)) return value.length ? `${value.length}개 결속됨` : '연결 안 됨';
  return value === null || value === undefined || value === '' ? '연결 안 됨' : '연결됨';
}

function scalar(value: unknown, key = '') {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  if (typeof value === 'number') {
    const text = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 4 }).format(value);
    return key.endsWith('_pct') ? `${text}%` : text;
  }
  return String(value);
}

export function StructuredValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (!value.length) return <p className="section-missing">등록된 항목이 없습니다.</p>;
    const objects = value.every((item) => item !== null && typeof item === 'object' && !Array.isArray(item));
    if (objects) {
      return <div className="structured-value-list">{value.map((item, i) => (
        <section className="structured-value-card" key={i}>
          <span className="structured-value-index">{i + 1}</span>
          <StructuredValue value={item} depth={depth + 1} />
        </section>
      ))}</div>;
    }
    return <ul className="section-list">{value.map((item, i) => (
      <li key={i}><StructuredValue value={item} depth={depth + 1} /></li>
    ))}</ul>;
  }

  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return <dl className={`structured-value-kv${depth ? ' nested' : ''}`}>
      {Object.entries(record)
        // 지표의 사람용 label 이 있으면 병렬 key 는 내부 코드이므로 문서에 반복하지 않는다.
        .filter(([key]) => !(key === 'key' && typeof record.label === 'string'))
        .map(([key, child]) => (
        <div key={key}>
          <dt>{label(key)}</dt>
          <dd>{internalReference(key)
            ? <span className="structured-value-scalar">{referenceSummary(child)}</span>
            : child !== null && typeof child === 'object'
            ? <StructuredValue value={child} depth={depth + 1} />
            : <span className="structured-value-scalar">{scalar(child, key)}</span>}</dd>
        </div>
      ))}
    </dl>;
  }

  return depth
    ? <span className="structured-value-scalar">{scalar(value)}</span>
    : <p className="section-text">{scalar(value)}</p>;
}
