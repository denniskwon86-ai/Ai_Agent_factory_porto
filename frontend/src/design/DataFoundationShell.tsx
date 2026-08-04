// [DESIGN · UIUX-AUDIT-33] `DataFoundationShell` — 데이터 기반 화면군 공용 셸
//   대상: 지식 허브 → 기준정보 마스터 → 업무표준 (Supervisor 이관 순서)
//   공통 요소(감사 지정): 검색 · 필터 · 목록 · 상세 · 등록 · 출처 · 버전 · 데이터 상태 · Jarvis 문맥
//
// ## 왜 세 화면을 따로 꾸미기 전에 이것부터 만드는가 (Supervisor 이관 순서 지정)
//
// 세 화면은 겉모습만 다를 뿐 **같은 일을 한다**: 분류를 고르고 → 목록에서 하나를 고르고 →
// 상세를 보고 → 등록·수정하고 → 근거와 이력을 확인한다. 각각 꾸미면 같은 결정을 세 번 하고,
// 세 번 다르게 하게 된다. 그리고 그때부터는 «디자인»이 아니라 «세 화면을 서로 맞추는 일»이 된다.
//
// ## 이 셸이 강제하는 것 (감사 UIUX-AUDIT-29·30 에서 실측된 것들)
//
//   ① **조회 실패를 «0건»으로 보여줄 수 없다.** 목록·지표는 `Loaded<T>` 를 받는다.
//   ② **`alert()`/`confirm()` 을 쓰지 않는다.** 되돌릴 수 없는 행동은 `ConfirmInline` 으로
//      화면 안에서 확인한다 — 브라우저 대화상자는 키보드·스크린리더 대응이 되지 않고,
//      무엇보다 **무엇이 지워지는지**를 제대로 설명할 자리가 없다.
//   ③ **본문 12px 이상.** 여기서 만드는 요소에 9~11px 을 두지 않는다.
//   ④ **행동색과 상태색을 섞지 않는다.** 1차 행동은 구조색(Navy), 위험은 Red, 성공은 Green.
//      `action/*` 과 `state/*` 토큰(`tokens.css`)이 그 구분이다.
//
// ## 데이터 화면에만 있는 것
//
// 이 세 화면의 공통점은 «근거»다. 자료가 **어디서 왔고 언제 갱신됐는지**를 말하지 못하면
// 그 자료로 만든 산출물도 설명할 수 없다. 그래서 `EvidenceStrip` 을 셸이 제공하고,
// 값이 없으면 빈칸으로 두지 않고 «미상»이라고 쓴다(모르는 것을 0 으로 두지 않는다).
import { useState, type ReactNode } from 'react';

import { EmptyOrError, type Loaded } from './DataState';
import { Panel } from './HubShell';

// ── 검색·필터·1차 행동 한 줄 ────────────────────────────────────────────────
export function FoundationToolbar({ search, onSearch, placeholder, filters, actions, hint }: {
  search: string;
  onSearch: (v: string) => void;
  placeholder: string;
  /** 분류 전환. 2~5개까지만 — 넘어가면 목록이지 필터가 아니다. */
  filters?: { id: string; label: string; active: boolean; onSelect: () => void }[];
  actions?: ReactNode;
  hint?: string;
}) {
  return (
    <div className="foundation-toolbar">
      <div className="foundation-toolbar-row">
        <div className="search-field">
          <span aria-hidden="true">🔍</span>
          <input value={search} placeholder={placeholder} aria-label={placeholder}
            onChange={(e) => onSearch(e.target.value)} />
          {search && (
            <button type="button" className="text-button" onClick={() => onSearch('')}>지우기</button>
          )}
        </div>
        {filters && filters.length > 0 && (
          <div className="filter-pills">
            {filters.map((f) => (
              <button key={f.id} className={f.active ? 'active' : ''} onClick={f.onSelect}>
                {f.label}
              </button>
            ))}
          </div>
        )}
        {actions && <div className="foundation-actions">{actions}</div>}
      </div>
      {/* 검색이 **무엇을 뒤지는지** 적는다. 안 적으면 사용자는 결과가 없을 때
          «자료가 없다»와 «검색 대상이 아니다»를 구분할 수 없다. */}
      {hint && <p className="hint-line" style={{ margin: '8px 0 0' }}>{hint}</p>}
    </div>
  );
}

// ── 좌측 목록 (분류/레코드) ─────────────────────────────────────────────────
export type FoundationRow = {
  id: string;
  title: string;
  /** 한 줄 메타. **비어 있으면 «정보 없음»이라고 쓴다** — 빈칸은 «확인 안 함»으로 읽힌다. */
  meta?: string;
  chip?: { label: string; tone: 'success' | 'warn' | 'data' | 'danger' | 'muted' };
};

export function FoundationList({ state, rows, selectedId, onSelect, emptyText, onRetry, title,
  kicker, action }: {
  state: Loaded<any>;
  rows: FoundationRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  emptyText: ReactNode;
  onRetry: () => void;
  title: string;
  kicker: string;
  action?: ReactNode;
}) {
  return (
    <Panel kicker={kicker} title={title} action={action}>
      {rows.length === 0 ? (
        <EmptyOrError state={state.status} error={state.error} onRetry={onRetry}
          emptyText={emptyText} />
      ) : (
        <div className="people-list" style={{ padding: 15 }}>
          {rows.map((r) => (
            <button key={r.id} type="button"
              className={`person ${r.id === selectedId ? 'selected' : ''}`}
              aria-pressed={r.id === selectedId}
              onClick={() => onSelect(r.id)}>
              <i aria-hidden="true">{r.title.slice(0, 2)}</i>
              <div style={{ minWidth: 0 }}>
                <b style={{ whiteSpace: 'normal' }}>{r.title}</b>
                <small>{r.meta || '정보 없음'}</small>
              </div>
              {r.chip && <span className={`state-chip ${r.chip.tone}`}>{r.chip.label}</span>}
            </button>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── 근거 띠 — 이 자료가 어디서 왔는가 ───────────────────────────────────────
export function EvidenceStrip({ items, note }: {
  items: { label: string; value: string | number | null | undefined }[];
  note?: string;
}) {
  return (
    <div className="identity-bar">
      {items.map((it) => (
        <div key={it.label}>
          <span>{it.label}</span>
          {/* ★ 값이 없으면 빈칸이 아니라 «미상»이다. 빈칸은 «확인했는데 없다»로 읽힌다. */}
          <b>{it.value === null || it.value === undefined || it.value === '' ? '미상' : String(it.value)}</b>
        </div>
      ))}
      {note && <p>{note}</p>}
    </div>
  );
}

// ── 되돌릴 수 없는 행동의 확인 ──────────────────────────────────────────────
export function ConfirmInline({ open, title, body, confirmLabel, onConfirm, onCancel, danger = true }: {
  open: boolean;
  title: string;
  /** **무엇이 사라지는지** 구체적으로 쓴다. "계속할까요?" 만으로는 판단할 수 없다. */
  body: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}) {
  if (!open) return null;
  return (
    <div className={`request-alert ${danger ? 'warn' : ''}`} style={{ marginTop: 10 }}>
      <i aria-hidden="true">{danger ? '!' : 'i'}</i>
      <div style={{ flex: 1 }}>
        <b>{title}</b>
        <small>{body}</small>
        <div style={{ display: 'flex', gap: 7, marginTop: 10, justifyContent: 'flex-end' }}>
          <button className="secondary-button" onClick={onCancel}>취소</button>
          <button className={danger ? 'danger-solid' : 'primary-button'} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 확인이 필요한 행동 하나를 다루는 상태 훅. 화면마다 boolean 을 새로 만들지 않게 한다. */
export function useConfirm<T = string>() {
  const [target, setTarget] = useState<T | null>(null);
  return {
    target,
    ask: (t: T) => setTarget(t),
    cancel: () => setTarget(null),
    /** 실행 후 자동으로 닫는다 — 닫는 것을 잊으면 확인 문구가 화면에 남는다. */
    run: (fn: (t: T) => void) => { if (target !== null) { fn(target); setTarget(null); } },
  };
}

// ── 등록·편집 폼 ────────────────────────────────────────────────────────────
export function FormField({ label, hint, required, children }: {
  label: string; hint?: string; required?: boolean; children: ReactNode;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label className="field-label">
        {label}{required && <span style={{ color: 'var(--action-danger-quiet-fg)' }}> *</span>}
      </label>
      {children}
      {hint && <p className="hint-line" style={{ margin: '5px 0 0' }}>{hint}</p>}
    </div>
  );
}

// ── 이력 (업무표준·MDM 공용) ────────────────────────────────────────────────
export function VersionHistory({ rows, emptyText = '이력이 없습니다.' }: {
  rows: { id: string; version: string; at: string; actor: string; summary: string }[];
  emptyText?: string;
}) {
  if (rows.length === 0) return <div className="empty-note">{emptyText}</div>;
  return (
    <div className="people-list">
      {rows.map((r) => (
        <div key={r.id} className="person">
          <i aria-hidden="true">{r.version.slice(0, 3)}</i>
          <div style={{ minWidth: 0 }}>
            <b>{r.summary}</b>
            <small>{r.actor || '작성자 미상'} · {r.at ? r.at.slice(0, 16) : '시각 미상'}</small>
          </div>
          <span className="state-chip muted">{r.version}</span>
        </div>
      ))}
    </div>
  );
}

// ── Jarvis 문맥 (감사 지정 공통 요소) ───────────────────────────────────────
/** 데이터 기반 화면의 Jarvis 문맥을 **한 규칙으로** 만든다.
 *
 * ★ 세 화면이 각자 만들면 «선택한 객체»의 표현이 달라지고, 비서는 화면마다 다른 것을 참조한다.
 * ⚠️ `snapshot` 에 본문을 통째로 넣지 않는다 — 비서 문맥이 권한 검사를 우회하는 두 번째
 *   조회 경로가 되면 안 된다(CL-4 에서 같은 이유로 알림 페이로드를 화이트리스트로 막았다).
 */
export function foundationJarvis(opts: {
  module: string;
  /** 화면의 **한국어 제목**. 선택한 객체가 없을 때 문맥 제목으로 쓴다.
   *  ⚠️ 없으면 `module` 슬러그(`knowledge/packs`)가 그대로 화면에 나갔다 — 사용자에게 뜻이 없다. */
  moduleTitle?: string;
  objectType: string;
  selected: { id: string; title: string; meta?: string } | null;
  state: Loaded<any>;
  counts: Record<string, number | null>;
  actions: string[];
  evidence?: { label: string; value: string }[];
}) {
  const { module, moduleTitle, objectType, selected, state, counts, actions, evidence } = opts;
  const failed = state.status === 'error' || state.status === 'forbidden';
  return {
    ctx: {
      current_module: module,
      selected_object_type: objectType,
      selected_object_id: selected?.id || '',
      object_snapshot: selected
        ? { id: selected.id, title: selected.title, meta: selected.meta || '' }
        : { load_status: state.status, ...counts },
      // ★★ [2026-08-04 실측 결함] 목록을 못 읽은 상태에서도 «할 수 있는 일: 유형 생성 · 레코드
      //   등록»이 그대로 떴다. 익명 사용자에게 그렇게 보였고, 누르면 403 이다.
      //   비서가 «할 수 있다»고 말한 것이 안 되면 사용자는 자기 조작을 의심한다 —
      //   권한 문제를 조작 실수로 오해하게 만드는 것이 가장 나쁜 안내다.
      //   ⚠️ 여기서 «권한»을 새로 판정하지 않는다. 판정은 서버가 이미 했고(403/차단 사유),
      //     그 결과가 `state.status` 로 와 있다. 그것을 따르기만 한다.
      available_actions: failed ? [] : actions,
      evidence_refs: [],
    },
    // 조회에 실패했으면 비서 문맥도 «없다»가 아니라 «못 읽었다»라고 말해야 한다.
    // 슬러그를 제목으로 쓰지 않는다 — 한국어 화면 제목이 없으면 «선택 없음»이 더 정확하다.
    title: selected?.title
      || (failed ? '조회 불가'
        : Object.values(counts).some((v) => v) ? (moduleTitle || '선택 없음') : '선택 없음'),
    desc: failed
      ? '목록을 가져오지 못했습니다 — «0건»이 아닙니다.'
      : selected?.meta || '좌측에서 항목을 선택하면 그 자료를 문맥으로 씁니다.',
    ev: evidence || [],
  };
}
