import { useMemo, useRef, useState, type ReactNode } from 'react';

type ReportBlock =
  | { kind: 'heading'; level: 3; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; headers: string[]; rows: string[][] };

interface ReportSection {
  id: string;
  title: string;
  blocks: ReportBlock[];
}

interface ParsedReport {
  title: string;
  prelude: ReportBlock[];
  sections: ReportSection[];
}

const SUMMARY_SECTION = /결론|요약|핵심|의사결정|판단|요청/i;
const CALLOUT_LABEL = /^(핵심 변동 요약|즉시 판단할 항목|권고안|기대효과|비용|위험|책임 부서|기한|의사결정 요청)\s*:/;

function cleanInline(value: string) {
  return value.trim().replace(/^\*{2}|\*{2}$/g, '').trim();
}

function inline(value: string): ReactNode[] {
  return value.split(/(\*\*.*?\*\*|`.*?`)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

function cells(line: string) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  const values = cells(line);
  return values.length > 0 && values.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function slug(value: string, index: number) {
  const safe = value.replace(/^\d+[.)]?\s*/, '').replace(/[^0-9A-Za-z가-힣]+/g, '-').replace(/^-|-$/g, '');
  return `report-section-${safe || index}`;
}

function parseBlocks(lines: string[]): ReportBlock[] {
  const blocks: ReportBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (line.startsWith('### ')) {
      blocks.push({ kind: 'heading', level: 3, text: line.slice(4).trim() });
      index += 1;
      continue;
    }

    if (line.startsWith('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = cells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push({ kind: 'table', headers, rows });
      continue;
    }

    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (ordered || unordered) {
      const isOrdered = Boolean(ordered);
      const items: string[] = [];
      while (index < lines.length) {
        const itemLine = lines[index].trim();
        const match = isOrdered ? itemLine.match(/^\d+[.)]\s+(.+)$/) : itemLine.match(/^[-*]\s+(.+)$/);
        if (!match) break;
        items.push(match[1].trim());
        index += 1;
      }
      blocks.push({ kind: 'list', ordered: isOrdered, items });
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (!next || next.startsWith('#') || next.startsWith('|') || /^\d+[.)]\s+/.test(next) || /^[-*]\s+/.test(next)) break;
      paragraph.push(next);
      index += 1;
    }
    blocks.push({ kind: 'paragraph', text: paragraph.join(' ') });
  }
  return blocks;
}

function parseReport(markdown: string): ParsedReport {
  const lines = markdown.replace(/^\```(?:markdown)?\s*/i, '').replace(/\s*\```$/, '').split(/\r?\n/);
  let title = '재무 분석 보고서';
  const prelude: string[] = [];
  const rawSections: Array<{ title: string; lines: string[] }> = [];
  let current: { title: string; lines: string[] } | null = null;

  for (const source of lines) {
    const line = source.trimEnd();
    if (line.startsWith('# ') && title === '재무 분석 보고서') {
      title = cleanInline(line.slice(2));
    } else if (line.startsWith('## ')) {
      current = { title: cleanInline(line.slice(3)), lines: [] };
      rawSections.push(current);
    } else if (current) {
      current.lines.push(line);
    } else {
      prelude.push(line);
    }
  }

  return {
    title,
    prelude: parseBlocks(prelude),
    sections: rawSections.map((section, index) => ({
      id: slug(section.title, index + 1),
      title: section.title,
      blocks: parseBlocks(section.lines),
    })),
  };
}

function cellTone(value: string) {
  if (/유리|개선|절감|감소|완료|정상/i.test(value)) return 'positive';
  if (/불리|증가|위험|초과|지연|미산출/i.test(value)) return 'negative';
  return undefined;
}

function ReportBlockView({ block }: { block: ReportBlock }) {
  if (block.kind === 'heading') return <h3>{inline(block.text)}</h3>;
  if (block.kind === 'paragraph') {
    const callout = CALLOUT_LABEL.test(block.text.replace(/\*\*/g, ''));
    return <p className={callout ? 'report-callout-line' : undefined}>{inline(block.text)}</p>;
  }
  if (block.kind === 'list') {
    const Tag = block.ordered ? 'ol' : 'ul';
    return <Tag>{block.items.map((item, index) => <li key={index}>{inline(item)}</li>)}</Tag>;
  }
  return (
    <div className="report-table-wrap" role="region" aria-label="보고서 데이터 표" tabIndex={0}>
      <table className="report-data-table">
        <thead><tr>{block.headers.map((header, index) => <th key={index}>{inline(header)}</th>)}</tr></thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((value, cellIndex) => (
                <td key={cellIndex} data-tone={cellTone(value)}>{inline(value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 인쇄 시 소제목과 그 설명이 서로 다른 페이지로 갈라지지 않도록 논리 문단 묶음을 만든다. */
function blockGroups(blocks: ReportBlock[]) {
  const groups: ReportBlock[][] = [];
  let current: ReportBlock[] = [];
  for (const block of blocks) {
    if (block.kind === 'heading' && current.length) {
      groups.push(current);
      current = [];
    }
    current.push(block);
  }
  if (current.length) groups.push(current);
  return groups;
}

export function ExecutiveReportView({ markdown }: { markdown: string }) {
  const report = useMemo(() => parseReport(markdown), [markdown]);
  const [view, setView] = useState<'summary' | 'full'>('full');
  const [fontSize, setFontSize] = useState(1);
  const reportRef = useRef<HTMLDivElement>(null);
  const summarySections = report.sections.filter((section) => SUMMARY_SECTION.test(section.title));
  const visibleSections = view === 'full'
    ? report.sections
    : (summarySections.length ? summarySections : report.sections.slice(0, 2));

  const printReport = () => {
    const source = reportRef.current;
    if (!source) return;

    // 화면 Canvas 는 고정 높이·스크롤 컨테이너다. 그 DOM 을 그대로 인쇄하면 첫 페이지만
    // 잘릴 수 있으므로, 현재 보고서만 독립 문서로 복제해 자연스러운 다중 페이지 흐름으로 출력한다.
    const frame = document.createElement('iframe');
    frame.title = '재무 보고서 인쇄';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.position = 'fixed';
    frame.style.width = '1px';
    frame.style.height = '1px';
    frame.style.right = '0';
    frame.style.bottom = '0';
    frame.style.border = '0';

    const styles = Array.from(document.head.querySelectorAll('link[rel="stylesheet"], style'))
      .map((node) => node.outerHTML)
      .join('');
    const copy = source.cloneNode(true) as HTMLElement;
    copy.querySelector('.report-view-controls')?.remove();
    copy.querySelector('.report-section-nav')?.remove();
    copy.querySelector('.report-expand')?.remove();

    frame.onload = () => {
      const printWindow = frame.contentWindow;
      if (!printWindow) {
        frame.remove();
        return;
      }
      const cleanup = () => frame.remove();
      printWindow.addEventListener('afterprint', cleanup, { once: true });
      window.setTimeout(() => {
        printWindow.focus();
        printWindow.print();
      }, 150);
      window.setTimeout(cleanup, 60_000);
    };
    frame.srcdoc = (
      `<!doctype html><html lang="ko"><head><meta charset="UTF-8"><base href="${document.baseURI}">${styles}</head>` +
      `<body class="printing-executive-report"><main class="afs-studio print-report-root">${copy.outerHTML}</main></body></html>`
    );
    document.body.appendChild(frame);
  };

  return (
    <div ref={reportRef} className={`executive-report report-font-${fontSize}`}>
      <div className="report-view-controls" aria-label="보고서 표시 설정">
        <div className="report-view-switch" role="group" aria-label="보고서 범위">
          <button type="button" aria-pressed={view === 'summary'} onClick={() => setView('summary')}>핵심 요약</button>
          <button type="button" aria-pressed={view === 'full'} onClick={() => setView('full')}>전체 보고서</button>
        </div>
        <div className="report-font-controls" role="group" aria-label="보고서 글자 크기">
          <span>글자 크기</span>
          <button type="button" aria-label="글자 작게" disabled={fontSize === 0} onClick={() => setFontSize((size) => Math.max(0, size - 1))}>가−</button>
          <button type="button" aria-label="글자 크게" disabled={fontSize === 2} onClick={() => setFontSize((size) => Math.min(2, size + 1))}>가＋</button>
          <button className="report-print-button" type="button" onClick={printReport}>인쇄·PDF</button>
        </div>
      </div>

      <header className="report-title-band">
        <small>EXECUTIVE FINANCIAL REPORT</small>
        <h1>{report.title}</h1>
        <p>핵심 판단과 산출 근거를 같은 보고서에서 확인합니다.</p>
      </header>

      {view === 'full' && report.sections.length > 1 && (
        <nav className="report-section-nav" aria-label="보고서 목차">
          {report.sections.map((section, index) => (
            <a key={section.id} href={`#${section.id}`}><span>{String(index + 1).padStart(2, '0')}</span>{section.title.replace(/^\d+[.)]?\s*/, '')}</a>
          ))}
        </nav>
      )}

      {report.prelude.length > 0 && (
        <section className="report-section report-prelude">
          {report.prelude.map((block, index) => <ReportBlockView key={index} block={block} />)}
        </section>
      )}

      <div className="report-sections">
        {visibleSections.map((section) => (
          <section
            className={`report-section ${SUMMARY_SECTION.test(section.title) ? 'report-section-emphasis' : ''}`}
            id={section.id}
            key={section.id}
          >
            <header><span>{String(report.sections.indexOf(section) + 1).padStart(2, '0')}</span><h2>{section.title.replace(/^\d+[.)]?\s*/, '')}</h2></header>
            <div className="report-section-body">
              {blockGroups(section.blocks).map((blocks, groupIndex) => (
                <div className="report-content-group" key={groupIndex}>
                  {blocks.map((block, blockIndex) => <ReportBlockView key={blockIndex} block={block} />)}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      {view === 'summary' && report.sections.length > visibleSections.length && (
        <button className="report-expand" type="button" onClick={() => setView('full')}>전체 근거와 상세 분석 보기</button>
      )}
    </div>
  );
}
