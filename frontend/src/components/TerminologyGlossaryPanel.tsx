import { useEffect, useMemo, useState } from 'react';

import glossary from '../data/technologyTerminologyGlossary.json';
import { HubDialog } from '../design/HubDialog';
import './terminology-glossary.css';

type Entry = (typeof glossary.entries)[number];
type Conflict = (typeof glossary.p0_conflicts)[number];
type Tab = 'dictionary' | 'conflicts' | 'guide';

const STATUS_ORDER = ['권장안', '현행 유지', '표준 약어 유지', '기술 전용', '검토 필요', '과거 별칭'];

function includes(entry: Entry, query: string) {
  if (!query) return true;
  const haystack = [
    entry.id, entry.area, entry.current_term, entry.current_kind,
    entry.recommended_user_term, entry.recommended_english_term,
    entry.technical_canonical_name, entry.definition, entry.redefinition_issue,
    entry.migration_status, entry.usage_guidance, entry.legacy_alias,
  ].join(' ').toLocaleLowerCase('ko-KR');
  return haystack.includes(query.toLocaleLowerCase('ko-KR'));
}

function StatusChip({ status }: { status: string }) {
  const cls = status === '권장안' ? 'recommended'
    : status === '현행 유지' ? 'accepted'
      : status === '표준 약어 유지' ? 'standard'
      : status === '기술 전용' ? 'technical'
        : status === '과거 별칭' ? 'legacy' : 'review';
  return <span className={`term-status ${cls}`}>{status}</span>;
}

function DictionaryRow({ entry }: { entry: Entry }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="term-row">
      <div className="term-row-id">
        <code>{entry.id}</code>
        <span>{entry.current_kind}</span>
      </div>
      <div className="term-current">
        <small>현재 사용 용어</small>
        <b>{entry.current_term}</b>
        {entry.legacy_alias && <span>현재·검색 별칭으로 보존</span>}
      </div>
      <div className="term-arrow" aria-hidden="true">→</div>
      <div className="term-recommended">
        <small>권장 화면 표기</small>
        <b>{entry.recommended_user_term}</b>
        <span>{entry.recommended_english_term}</span>
      </div>
      <div className="term-technical">
        <small>기술 표준명</small>
        <code>{entry.technical_canonical_name}</code>
        <p>{entry.redefinition_issue}</p>
      </div>
      <StatusChip status={entry.migration_status} />
      {/* ★★★ [2026-08-23 실측] **접혀 있어도 DOM 에는 다 그려져 있었다.**
          `<details>` 는 «보이지 않게» 할 뿐 자식을 만들지 않는 것이 아니다. 항목 349개 ×
          한 줄 33요소 = **11,392개**가 한 화면에 올라갔고(다른 화면은 150~400개), 화면이
          눈에 띄게 느려졌다.
          ★ 펼친 줄만 안쪽을 그린다. 접힌 상태에서는 요약줄만 남는다. */}
      <details className="term-detail" onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>정의·사용 원칙 보기</summary>
        {open && (
          <div>
            <section>
              <small>정의</small>
              <p>{entry.definition}</p>
            </section>
            <section>
              <small>사용 원칙</small>
              <p>{entry.usage_guidance}</p>
            </section>
            <section>
              <small>재정의 쟁점</small>
              <p>{entry.redefinition_issue}</p>
            </section>
            <section>
              <small>정본 출처</small>
              <code>{entry.source}</code>
            </section>
          </div>
        )}
      </details>
    </article>
  );
}

function ConflictCard({ conflict }: { conflict: Conflict }) {
  return (
    <article className="conflict-card">
      <span className="conflict-priority">P0 · {conflict.priority}</span>
      <h3>{conflict.conflict_group}</h3>
      <dl>
        <div>
          <dt>결정해야 할 것</dt>
          <dd>{conflict.decision_required}</dd>
        </div>
        <div>
          <dt>팀 권장안</dt>
          <dd>{conflict.recommended_resolution}</dd>
        </div>
      </dl>
      <StatusChip status={conflict.status} />
    </article>
  );
}

export function TerminologyGlossaryPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('dictionary');
  const [query, setQuery] = useState('');
  const [area, setArea] = useState('전체');
  const [status, setStatus] = useState('전체');
  const [pathCopied, setPathCopied] = useState(false);

  //: 한 번에 그리는 줄 수. ⚠️ 검색·필터를 바꾸면 처음으로 되돌린다 — 안 되돌리면
  //:   좁힌 결과가 이미 다 보이는데도 「더 보기」가 남아 사용자를 헷갈리게 한다.
  const PAGE = 80;
  const [shown, setShown] = useState(PAGE);
  const areas = useMemo(() => ['전체', ...new Set(glossary.entries.map((e) => e.area))], []);
  const filtered = useMemo(() => glossary.entries.filter((entry) => (
    (area === '전체' || entry.area === area)
    && (status === '전체' || entry.migration_status === status)
    && includes(entry, query.trim())
  )), [area, query, status]);
  //: ★ 조건이 바뀌면 표시 개수를 처음으로 되돌린다. 안 되돌리면 좁힌 결과가 이미 다
  //:   보이는데도 「더 보기」가 남거나, 반대로 넓혔는데 앞부분만 보인다.
  //:   ⚠️ 렌더 중에 `setState` 를 부르지 않는다 — `useEffect` 로 조건 변화에 반응한다.
  useEffect(() => { setShown(PAGE); }, [area, query, status]);
  const stats = useMemo(() => STATUS_ORDER.map((key) => ({
    key,
    count: glossary.entries.filter((entry) => entry.migration_status === key).length,
  })), []);
  const excelPath = 'docs/architecture/AI_FACTORY_STUDIO_TECHNOLOGY_TERMINOLOGY_DICTIONARY_2026-08-12.xlsx';

  const copyExcelPath = async () => {
    try {
      await navigator.clipboard.writeText(excelPath);
      setPathCopied(true);
      window.setTimeout(() => setPathCopied(false), 1800);
    } catch {
      setPathCopied(false);
    }
  };

  return (
    <HubDialog label="기술·제품 용어집 — 현재 용어와 권장 용어 전환 사전" onClose={onClose}>
      <div className="afs-dialog-bar terminology-bar">
        <div>
          <b>기술·제품 용어집</b>
          <span>표준 용어는 유지하고, 쉬운 설명과 기술 표준명을 함께 관리합니다.</span>
        </div>
        <div className="bar-actions">
          <button className="secondary-button" onClick={copyExcelPath}>
            {pathCopied ? '경로 복사됨' : 'Excel 경로 복사'}
          </button>
          <button className="secondary-button" onClick={onClose}>닫기 <b>(Esc)</b></button>
        </div>
      </div>

      <div className="afs-dialog-body terminology-page">
        <section className="terminology-intro">
          <div>
            <small>TRANSITION DICTIONARY · v{glossary.metadata.version}</small>
            <h1>쉬운 표현과 정확한 표준 용어를 함께 사용합니다.</h1>
            <p>
              사용자 화면에는 이해하기 쉬운 표현을 우선하되 WBS·RFP·PRD처럼 널리 통용되는
              표준 약어는 유지합니다. 최초 노출에서 뜻을 병기하고 반복 화면에서는 약어를 사용합니다.
            </p>
          </div>
          <aside>
            <b>{glossary.metadata.decision_label} · 최종 승인 전</b>
            <p>신규 화면과 문서의 기본 표현입니다. API·DB·코드 식별자는 별도 마이그레이션 승인 없이 변경하지 않습니다.</p>
          </aside>
        </section>

        <section className="terminology-summary" aria-label="용어집 요약">
          <div><strong>{glossary.metadata.entry_count}</strong><span>전체 용어</span></div>
          <div><strong>{areas.length - 1}</strong><span>업무·기술 영역</span></div>
          <div><strong>{glossary.metadata.conflict_count}</strong><span>P0 충돌 묶음</span></div>
          {stats.map((item) => (
            <div key={item.key}><strong>{item.count}</strong><span>{item.key}</span></div>
          ))}
        </section>

        <nav className="terminology-tabs" aria-label="용어집 보기">
          <button className={tab === 'dictionary' ? 'active' : ''} onClick={() => setTab('dictionary')}>
            전체 용어 사전
          </button>
          <button className={tab === 'conflicts' ? 'active' : ''} onClick={() => setTab('conflicts')}>
            P0 충돌과 권장안
          </button>
          <button className={tab === 'guide' ? 'active' : ''} onClick={() => setTab('guide')}>
            사용 원칙
          </button>
        </nav>

        {tab === 'dictionary' && (
          <section className="terminology-dictionary">
            <div className="term-controls">
              <label>
                <span>자연어 검색</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)}
                  placeholder="예: 권한 범위, 시뮬레이션, Jarvis, HOTL" />
              </label>
              <label>
                <span>영역</span>
                <select value={area} onChange={(event) => setArea(event.target.value)}>
                  {areas.map((value) => <option key={value}>{value}</option>)}
                </select>
              </label>
              <label>
                <span>전환 상태</span>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option>전체</option>
                  {STATUS_ORDER.map((value) => <option key={value}>{value}</option>)}
                </select>
              </label>
              <strong>{filtered.length}개 표시</strong>
            </div>
            <div className="term-list">
              {filtered.slice(0, shown).map((entry) => (
                <DictionaryRow key={entry.id} entry={entry} />
              ))}
              {/* ★★★ 한 번에 다 그리지 않는다 — 349개를 모두 올리면 요소가 만 개를 넘는다.
                  ⚠️ **감춘 건수를 반드시 적는다.** 「80개 표시」만 적으면 사용자는 그것이
                    전부인 줄 알고 없는 용어를 찾았다고 판단한다(이 저장소가 반복해서 잡아 온
                    «0은 없다로 읽힌다» 와 같은 결함이다). 남은 수와 전체를 함께 말한다. */}
              {filtered.length > shown && (
                <button className="secondary-button" style={{ margin: '10px auto', display: 'block' }}
                  onClick={() => setShown((n) => n + PAGE)}>
                  {filtered.length - shown}개 더 보기 (전체 {filtered.length}개 중 {shown}개 표시 중)
                </button>
              )}
              {filtered.length === 0 && (
                <div className="term-empty">
                  <b>조건에 맞는 용어가 없습니다.</b>
                  <span>검색어나 영역·상태 필터를 바꿔 보십시오.</span>
                </div>
              )}
            </div>
          </section>
        )}

        {tab === 'conflicts' && (
          <section className="conflict-grid">
            {glossary.p0_conflicts.map((conflict) => (
              <ConflictCard key={conflict.priority} conflict={conflict} />
            ))}
          </section>
        )}

        {tab === 'guide' && (
          <section className="terminology-guide">
            {glossary.metadata.policy.map((policy, index) => (
              <article key={policy}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <p>{policy}</p>
              </article>
            ))}
            <div className="terminology-source">
              <small>정본과 산출물</small>
              <b>{glossary.metadata.canonical_source}</b>
              <code>{glossary.metadata.policy_source}</code>
              <code>{excelPath}</code>
              <p>인벤토리와 전환 정책을 수정한 뒤 생성기를 실행합니다. Excel과 화면용 JSON을 서로 따로 수정하지 않습니다.</p>
            </div>
          </section>
        )}
      </div>
    </HubDialog>
  );
}
