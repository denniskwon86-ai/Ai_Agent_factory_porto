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
  /** [UI 설계서 §6.2] **재조회 중.** 값은 그대로 두고 «갱신 중» 만 덧붙인다. */
  refreshing?: boolean;
};

export function loading<T>(): Loaded<T> {
  return { status: 'loading', value: null };
}

/** [UI 설계서 §6.2] 「재조회 중 **기존 값은 유지하되** 「갱신 중」 표시.」
 *
 * ## 왜 값을 비우면 안 되는가
 *
 * 이 저장소의 화면은 행동 뒤에 목록을 다시 읽는다(승인 → 재조회, 저장 → 재조회). 그때마다
 * `loading()` 으로 값을 비우면 **읽고 있던 표가 사라졌다가 돌아온다.** 사용자는 방금 무엇이
 * 바뀌었는지 비교할 수 없고, 목록이 길면 스크롤 위치까지 잃는다. 심하면 «지워졌나?» 로 읽는다.
 *
 * ## ⚠️ 회사 문맥 변경에는 쓰지 않는다
 *
 * 같은 §6.2 가 「**회사 문맥 변경은 데이터 혼합 위험 때문에 이전 값을 즉시 비우고** 차단
 * skeleton 을 쓴다」고 못박았다. 조직을 바꿨는데 이전 조직의 숫자가 잠깐이라도 남아 있으면
 * 그것은 «느린 화면» 이 아니라 **다른 조직 자료를 보여 준 것**이다. 그 경우는 `loading()` 이
 * 맞다(이 저장소는 조직 전환에서 아예 `location.reload()` 한다).
 *
 * ⚠️ 첫 조회(값이 아직 없음)에는 자동으로 `loading()` 이 된다 — 보여 줄 «이전 값» 이 없는데
 *   «갱신 중» 이라고 적으면 사용자는 무엇이 갱신되는지 알 수 없다.
 */
export function refreshing<T>(prev: Loaded<T> | null | undefined): Loaded<T> {
  if (!prev || prev.value === null || prev.value === undefined) return loading<T>();
  return { ...prev, refreshing: true };
}

export function ok<T>(value: T): Loaded<T> {
  return { status: 'ok', value };
}

export function failed<T>(e: any): Loaded<T> {
  // 401/403 은 «없다»가 아니라 «내가 볼 수 없다»다 — 사용자가 할 일이 다르다.
  //
  // ★★★ [2026-08-08 역할별 감사] **404 도 여기 온다.** 이 저장소의 서버는 범위 밖 요청을
  //   «거부» 가 아니라 **404 로 은폐**한다(설계 §7.1 — 8개 라우터가 그렇게 한다. 403 은
  //   «그런 자원이 있다» 를 알려 주기 때문이다). 그런데 화면들은 404 를 «조회 실패» 로
  //   떨어뜨리고 있었다.
  //
  //   실측: viewer 로 「경영계획」을 열면 `/planning/scenarios?org_id=MNM_BATTERY` 가 404 이고
  //   (같은 요청이 관리자에게는 200), 화면은 **「조회 불가 — 목록을 가져오지 못했습니다」**
  //   를 그렸다. 사용자는 그것을 **서버 고장**으로 읽고 「다시 시도」를 누른다 — 영원히 같은
  //   결과다. 실제로 해야 할 일은 «다른 조직을 고르거나 권한을 요청하는» 것이다.
  //
  //   ⚠️ 문구는 **은폐를 깨지 않는다.** 「권한이 없습니다」라고 하면 그 조직에 자료가 있다는
  //     사실을 알려 주는 셈이 된다 — 그래서 「이 범위에서는 볼 수 없습니다」로 말한다.
  //     서버가 사유를 보내면 그것을 우선한다(화면이 지어내지 않는다).
  const s = e?.status;
  const hidden = s === 404;
  return {
    status: s === 401 || s === 403 || hidden ? 'forbidden' : 'error',
    value: null,
    error: e?.message
      || (hidden ? '이 범위에서는 볼 수 없습니다 — 다른 조직을 선택하거나 권한을 요청하십시오.'
        : s === 401 || s === 403 ? '볼 권한이 없습니다.'
          : String(e)),
    httpStatus: s,
  };
}

/** 상태별 보조 문구를 화면이 바꿔 쓸 수 있게 하는 자리.
 *
 * ★★ 기본 문구는 **수치 지표**용이다(«미측정» = 아직 재지 않았다). 그런데 같은 칸을 버전처럼
 *   수치가 아닌 값에도 쓰다 보니 "선택 버전 — / 미측정" 이 나왔다 — 버전은 재는 것이 아니다.
 *   ⚠️ 그렇다고 기본 문구를 바꾸지 않는다. «미측정과 0 은 다르다»는 판정은 지표 화면들이
 *     공유하는 단일 지점이고(DecisionCenter §⑤), 여기서 바꾸면 그 화면들이 함께 틀어진다.
 *   → 기본은 그대로 두고, 수치가 아닌 칸만 자기 언어를 넘긴다. */
export type MetricNotes = {
  loading?: string;
  forbidden?: string;
  error?: string;
  /** 정상 조회인데 값이 없을 때. 지표에서는 «미측정», 상태값에서는 «미지정» 계열이 맞다. */
  empty?: string;
};

/** 지표 한 칸의 표시값. **숫자만 돌려주지 않는다** — 보조 문구가 항상 함께 나온다. */
export function metricText(state: LoadStatus, value: number | string | null | undefined,
                           unit = '', notes: MetricNotes = {},
): { text: string; note: string; muted: boolean } {
  if (state === 'loading') return { text: '…', note: notes.loading || '확인 중', muted: true };
  if (state === 'forbidden') return { text: '—', note: notes.forbidden || '접근 불가', muted: true };
  if (state === 'error') return { text: '—', note: notes.error || '조회 불가', muted: true };
  if (value === null || value === undefined || value === '') {
    // ★ 값이 없는 것과 0 은 다르다. 서버가 «아직 모른다»를 준 경우다.
    return { text: '—', note: notes.empty || '미측정', muted: true };
  }
  return { text: `${value}${unit}`, note: '', muted: false };
}

/** 지표 카드 한 칸. `metric-row` 안에서 쓴다. */
export function Metric({ label, state, value, unit = '', hint, notes }: {
  label: string;
  state: LoadStatus;
  value: number | string | null | undefined;
  unit?: string;
  /** 정상일 때의 보조 설명. 실패 시에는 실패 문구가 우선한다. */
  hint?: string;
  /** 수치가 아닌 칸(버전·상태 등)의 상태 문구. 지정하지 않으면 지표용 기본 문구를 쓴다. */
  notes?: MetricNotes;
}) {
  const m = metricText(state, value, unit, notes);
  return (
    <div>
      <span>{label}</span>
      <b style={m.muted ? { color: 'var(--muted)' } : undefined}>{m.text}</b>
      <small>{m.note || hint || ''}</small>
    </div>
  );
}

/** 목록 자리의 빈 상태. **조회 실패를 «없습니다»로 쓰지 않는다.** */
/** [UI 설계서 §6.2] 「재조회 중 기존 값은 유지하되 **「갱신 중」 표시**.」
 *
 * 값을 그대로 두는 것만으로는 부족하다 — 사용자는 «지금 보는 것이 최신인가» 를 알 수 없다.
 * 화면마다 다른 말로 적지 않도록 한 곳에 둔다.
 *
 * ⚠️ 로딩 스피너로 화면을 덮지 않는다. 덮으면 값을 유지한 의미가 없다.
 */
export function Refreshing({ on }: { on?: boolean }) {
  if (!on) return null;
  return (
    <span className="refreshing-badge" role="status" aria-live="polite">
      <i aria-hidden="true" />갱신 중
    </span>
  );
}

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
