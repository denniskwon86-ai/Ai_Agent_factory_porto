// [UIUX-AUDIT-29 §2] **조회 실패와 «0건»을 같은 자리에 같은 모양으로 쓰지 않는다.**
//
// 감사 지적(경영 시스템에서 매우 위험한 표현):
//   백엔드가 죽은 상태에서 화면은 «Failed to fetch» 배너 두 건과 «발간물 0 / 대외 발간 0 /
//   내 결정 0» 을 **동시에** 보여줬다. 사용자는 그 0 을 «실제로 없다»로 읽는다.
//
// ★ 이 파일은 그 구분을 **타입으로 강제**한다. 숫자를 그냥 렌더링할 수 없고, 반드시 상태와 함께
//   넘겨야 한다. 규칙을 문서에 적어 두면 다음 화면에서 또 어긴다 — 컴파일러가 막게 한다.
//
//   · 정상 조회 후 0건 → `0`
//   · 조회 실패        → `—` + «조회 불가»
//   · 미측정           → `미측정`
//   · 계산 전          → `계산 전`
//   · 권한 없음        → `접근 불가`
//
// ⚠️ «모르는 것을 0 으로 두지 않는다»는 이 저장소의 설계 원칙이다(백엔드는 이미 그렇게 되어
//   있다 — 효과 미측정, 근거 미검증, 팩 결손). 화면만 0 으로 뭉개면 원칙이 화면에서 무너진다.
import type { ReactNode } from 'react';

import { Banner } from './HubShell';

export type LoadStatus = 'loading' | 'ok' | 'error' | 'forbidden';

export type Loaded<T> = {
  status: LoadStatus;
  value: T | null;
  /** 실패 사유. 화면이 지어내지 않고 서버 문구를 그대로 들고 있는다. */
  error?: string;
  httpStatus?: number;
};

export function loading<T>(): Loaded<T> {
  return { status: 'loading', value: null };
}

export function ok<T>(value: T): Loaded<T> {
  return { status: 'ok', value };
}

export function failed<T>(e: any): Loaded<T> {
  // 401/403 은 «없다»가 아니라 «내가 볼 수 없다»다 — 사용자가 할 일이 다르다.
  const s = e?.status;
  return {
    status: s === 401 || s === 403 ? 'forbidden' : 'error',
    value: null,
    error: e?.message || String(e),
    httpStatus: s,
  };
}

/** 지표 한 칸의 표시값. **숫자만 돌려주지 않는다** — 보조 문구가 항상 함께 나온다. */
export function metricText(state: LoadStatus, value: number | string | null | undefined,
                           unit = ''): { text: string; note: string; muted: boolean } {
  if (state === 'loading') return { text: '…', note: '확인 중', muted: true };
  if (state === 'forbidden') return { text: '—', note: '접근 불가', muted: true };
  if (state === 'error') return { text: '—', note: '조회 불가', muted: true };
  if (value === null || value === undefined || value === '') {
    // ★ 값이 없는 것과 0 은 다르다. 서버가 «아직 모른다»를 준 경우다.
    return { text: '—', note: '미측정', muted: true };
  }
  return { text: `${value}${unit}`, note: '', muted: false };
}

/** 지표 카드 한 칸. `metric-row` 안에서 쓴다. */
export function Metric({ label, state, value, unit = '', hint }: {
  label: string;
  state: LoadStatus;
  value: number | string | null | undefined;
  unit?: string;
  /** 정상일 때의 보조 설명. 실패 시에는 실패 문구가 우선한다. */
  hint?: string;
}) {
  const m = metricText(state, value, unit);
  return (
    <div>
      <span>{label}</span>
      <b style={m.muted ? { color: 'var(--muted)' } : undefined}>{m.text}</b>
      <small>{m.note || hint || ''}</small>
    </div>
  );
}

/** 목록 자리의 빈 상태. **조회 실패를 «없습니다»로 쓰지 않는다.** */
export function EmptyOrError({ state, error, emptyText, onRetry }: {
  state: LoadStatus;
  error?: string;
  emptyText: ReactNode;
  onRetry?: () => void;
}) {
  if (state === 'loading') return <div className="empty-note">불러오는 중입니다…</div>;
  if (state === 'forbidden') {
    return (
      <div className="empty-note">
        <b>접근 불가</b> — 이 목록을 볼 권한이 없습니다. 비어 있는 것이 아니라
        <b> 보이지 않는 것</b>입니다. {error}
      </div>
    );
  }
  if (state === 'error') {
    return (
      <div className="empty-note">
        <b>조회 불가</b> — 목록을 가져오지 못했습니다. <b>«0건»이 아닙니다.</b>
        <br />{error}
        {onRetry && (
          <div style={{ marginTop: 10 }}>
            <button className="secondary-button" onClick={onRetry}>다시 시도</button>
          </div>
        )}
      </div>
    );
  }
  return <div className="empty-note">{emptyText}</div>;
}

/** 여러 조회의 실패를 **하나의 상태 패널로 모은다**(감사 §2: 중복 배너 금지).
 *
 * ⚠️ 배너를 조회마다 하나씩 띄우면 화면이 오류로 뒤덮이고, 정작 «무엇을 해야 하는가»가 안 보인다. */
export function LoadStatusBanner({ items, onRetry }: {
  items: { label: string; state: Loaded<any> }[];
  onRetry?: () => void;
}) {
  const bad = items.filter((i) => i.state.status === 'error' || i.state.status === 'forbidden');
  if (bad.length === 0) return null;
  const forbidden = bad.filter((i) => i.state.status === 'forbidden');
  const errored = bad.filter((i) => i.state.status === 'error');
  return (
    <Banner tone="error"
      title={errored.length
        ? `${errored.length}개 항목을 조회하지 못했습니다 — 화면의 «0» 은 실제 0 이 아닙니다`
        : '권한 범위 밖의 항목이 있습니다'}>
      <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
        {bad.map((i) => (
          <li key={i.label}>
            <b>{i.label}</b> — {i.state.status === 'forbidden' ? '접근 불가' : '조회 불가'}
            {i.state.error ? `: ${i.state.error}` : ''}
          </li>
        ))}
      </ul>
      {forbidden.length > 0 && (
        <div style={{ marginTop: 6 }}>
          권한으로 가려진 항목은 다시 시도해도 보이지 않습니다 — 관리자에게 범위를 요청하십시오.
        </div>
      )}
      {onRetry && errored.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button className="secondary-button" onClick={onRetry}>다시 시도</button>
        </div>
      )}
    </Banner>
  );
}
