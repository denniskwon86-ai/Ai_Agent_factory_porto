/*
 * As-Is 역설계 Markdown을 검토용 Word 문서로 변환한다.
 * 실행: node scripts/generate_reverse_engineering_docx.js
 */
const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  PageNumber,
  Paragraph,
  Packer,
  ShadingType,
  Table,
  TableCell,
  TableOfContents,
  TableRow,
  TextRun,
  WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const DOCS = path.join(ROOT, "docs");
const BLUE = "17365D";
const SKY = "DCE6F1";
const PALE = "F5F8FC";
const GRAY = "5A6573";
const VERSIONED_OUTPUT = process.argv.includes("--versioned");
// SVG 미지원 뷰어를 위한 1px 투명 PNG 폴백. 최신 Word는 원본 SVG를 표시한다.
const SVG_FALLBACK_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9aQAAAABJRU5ErkJggg==",
  "base64",
);

const sources = [
  {
    source: "AS_IS_기능설계서_리버스엔지니어링_2026-07-28.md",
    output: "AI_Factory_Studio_AsIs_기능설계서_2026-07-28.docx",
    documentType: "기능설계서",
    subtitle: "현재 구현을 역추적한 기능·데이터·API·운영 설계",
  },
  {
    source: "AS_IS_화면기능정의서_리버스엔지니어링_2026-07-28.md",
    output: "AI_Factory_Studio_AsIs_화면기능정의서_2026-07-28.docx",
    documentType: "화면기능정의서",
    subtitle: "현재 구현을 역추적한 화면·행동·상태·연계 정의",
  },
];

function clean(text) {
  return text
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\\([*_`|])/g, "$1")
    .trim();
}

function runsFromInline(text, defaultOptions = {}) {
  const result = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let pos = 0;
  for (const match of text.matchAll(re)) {
    if (match.index > pos) result.push(new TextRun({ text: clean(text.slice(pos, match.index)), ...defaultOptions }));
    const raw = match[0];
    const isBold = raw.startsWith("**");
    result.push(new TextRun({
      text: clean(raw),
      bold: isBold,
      font: isBold ? "맑은 고딕" : "Consolas",
      color: isBold ? undefined : "1F4E79",
      ...defaultOptions,
    }));
    pos = match.index + raw.length;
  }
  if (pos < text.length) result.push(new TextRun({ text: clean(text.slice(pos)), ...defaultOptions }));
  return result.length ? result : [new TextRun({ text: clean(text), ...defaultOptions })];
}

function splitTableRow(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((v) => clean(v));
}

function isSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function tableFromRows(rows) {
  const widths = [2600, 3300, 3300];
  const maxColumns = Math.max(...rows.map((r) => r.length));
  const columnWidths = Array.from({ length: maxColumns }, (_, i) => widths[i] || Math.floor(9200 / maxColumns));
  return new Table({
    width: { size: 9200, type: WidthType.DXA },
    columnWidths,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "B7C7D9" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "B7C7D9" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "B7C7D9" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "B7C7D9" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: "D9E2F3" },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: "D9E2F3" },
    },
    rows: rows.map((row, rowIndex) => new TableRow({
      children: Array.from({ length: maxColumns }, (_, colIndex) => new TableCell({
        width: { size: columnWidths[colIndex], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, color: rowIndex === 0 ? SKY : "FFFFFF" },
        margins: { top: 90, bottom: 90, left: 100, right: 100 },
        children: [new Paragraph({
          spacing: { after: 0 },
          children: runsFromInline(row[colIndex] || "", { size: 18, bold: rowIndex === 0 }),
        })],
      })),
    })),
  });
}

function diagramBlocks(fileName, caption) {
  const dimensions = fileName.includes("screen_structure")
    ? { width: 620, height: 419 }
    : { width: 620, height: 380 };
  const source = path.join(DOCS, "assets", fileName);
  const fallbackPath = source.replace(/\.svg$/i, ".png");
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 100, after: 90 },
      children: [new ImageRun({
        data: fs.readFileSync(source),
        type: "svg",
        fallback: { data: fs.existsSync(fallbackPath) ? fs.readFileSync(fallbackPath) : SVG_FALLBACK_PNG, type: "png" },
        transformation: dimensions,
        altText: { title: caption, description: caption, name: fileName },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 180 },
      children: [new TextRun({ text: caption, italics: true, color: GRAY, size: 18 })],
    }),
  ];
}

function metadataTable(item) {
  const rows = [
    ["문서 구분", item.documentType],
    ["기준 시점", "2026-07-28 / 저장소 현재 구현(As-Is)"],
    ["작성 방식", "소스코드·API·상태 모델·프론트엔드 화면을 역추적한 리버스 엔지니어링"],
    ["판독 원칙", "목표 설계(To-Be)가 아니라 실제 코드에 존재하는 기능과 현재 제약을 구분하여 기록"],
  ];
  return new Table({
    width: { size: 9200, type: WidthType.DXA },
    columnWidths: [2200, 7000],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: "9FBAD0" },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: "9FBAD0" },
      left: { style: BorderStyle.SINGLE, size: 6, color: "9FBAD0" },
      right: { style: BorderStyle.SINGLE, size: 6, color: "9FBAD0" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: "D9E2F3" },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: "D9E2F3" },
    },
    rows: rows.map(([label, value]) => new TableRow({ children: [
      new TableCell({
        width: { size: 2200, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, color: SKY },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: label, bold: true, size: 19 })] })],
      }),
      new TableCell({
        width: { size: 7000, type: WidthType.DXA },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: value, size: 19 })] })],
      }),
    ] })),
  });
}

function markdownToBlocks(markdown) {
  const lines = markdown.replace(/\r/g, "").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.startsWith("# ")) { index += 1; continue; } // cover title is used instead

    if (line.trim() === "```text") {
      const codeLines = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== "```") {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const code = codeLines.join("\n");
      if (code.includes("React/Vite UI")) {
        blocks.push(...diagramBlocks(
          "as_is_system_architecture.svg",
          "그림 1. 현재 코드 기준의 AI Factory Studio 논리 아키텍처",
        ));
      } else if (/^App\s*$/m.test(code)) {
        blocks.push(...diagramBlocks(
          "as_is_screen_structure.svg",
          "그림 1. 현재 코드 기준의 App 화면 구조와 전환 규칙",
        ));
      } else {
        blocks.push(new Paragraph({
          shading: { type: ShadingType.CLEAR, color: PALE },
          spacing: { after: 120 },
          children: [new TextRun({ text: code, font: "Consolas", size: 18, color: "1F4E79" })],
        }));
      }
      continue;
    }

    if (line.startsWith("|") && index + 1 < lines.length && isSeparator(lines[index + 1])) {
      const rows = [splitTableRow(line)];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push(tableFromRows(rows));
      continue;
    }

    const heading = /^(#{2,4})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const levelMap = { 2: HeadingLevel.HEADING_1, 3: HeadingLevel.HEADING_2, 4: HeadingLevel.HEADING_3 };
      blocks.push(new Paragraph({
        text: clean(heading[2]),
        heading: levelMap[level],
        spacing: { before: level === 2 ? 360 : 240, after: 120 },
      }));
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      blocks.push(new Paragraph({
        numbering: { reference: "bullet-list", level: 0 },
        spacing: { after: 60 },
        children: runsFromInline(line.replace(/^[-*]\s+/, ""), { size: 20 }),
      }));
      index += 1;
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      blocks.push(new Paragraph({
        numbering: { reference: "number-list", level: 0 },
        spacing: { after: 60 },
        children: runsFromInline(line.replace(/^\d+\.\s+/, ""), { size: 20 }),
      }));
      index += 1;
      continue;
    }
    if (/^>\s?/.test(line)) {
      blocks.push(new Paragraph({
        border: { left: { color: "9FBAD0", space: 8, style: BorderStyle.SINGLE, size: 16 } },
        shading: { type: ShadingType.CLEAR, color: PALE },
        indent: { left: 180 },
        spacing: { before: 60, after: 100 },
        children: runsFromInline(line.replace(/^>\s?/, ""), { size: 20, italics: true, color: GRAY }),
      }));
      index += 1;
      continue;
    }
    if (/^-{3,}$/.test(line.trim())) {
      blocks.push(new Paragraph({ border: { bottom: { color: "B7C7D9", style: BorderStyle.SINGLE, size: 6, space: 4 } }, spacing: { after: 120 } }));
      index += 1;
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4}\s+|[-*]\s+|\d+\.\s+|>\s?|\||---)/.test(lines[index])) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push(new Paragraph({
      spacing: { after: 120, line: 300 },
      children: runsFromInline(paragraphLines.join(" "), { size: 20 }),
    }));
  }
  return blocks;
}

async function build(item) {
  const markdown = fs.readFileSync(path.join(DOCS, item.source), "utf8");
  const title = markdown.match(/^#\s+(.+)$/m)?.[1] || item.documentType;
  const doc = new Document({
    creator: "AI Factory Studio",
    title,
    description: item.subtitle,
    numbering: {
      config: [
        { reference: "bullet-list", levels: [{ level: 0, format: "bullet", text: "•", alignment: AlignmentType.LEFT }] },
        { reference: "number-list", levels: [{ level: 0, format: "decimal", text: "%1.", alignment: AlignmentType.LEFT }] },
      ],
    },
    styles: {
      default: { document: { run: { font: "맑은 고딕", size: 20, color: "1F2937" }, paragraph: { spacing: { line: 300 } } } },
      paragraphStyles: [
        { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", run: { font: "맑은 고딕", size: 44, bold: true, color: BLUE }, paragraph: { alignment: AlignmentType.CENTER, spacing: { after: 260 } } },
        { id: "Subtitle", name: "Subtitle", basedOn: "Normal", next: "Normal", run: { font: "맑은 고딕", size: 24, color: GRAY }, paragraph: { alignment: AlignmentType.CENTER, spacing: { after: 460 } } },
      ],
    },
    sections: [{
      properties: { page: { margin: { top: 1200, bottom: 1100, left: 1200, right: 1200 } } },
      headers: { default: new (require("docx").Header)({ children: [new Paragraph({
        border: { bottom: { color: "9FBAD0", style: BorderStyle.SINGLE, size: 6, space: 4 } },
        children: [new TextRun({ text: "AI FACTORY STUDIO  |  AS-IS REVERSE ENGINEERING", bold: true, color: BLUE, size: 16 })],
      })] }) },
      footers: { default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "내부 검토용  |  ", color: GRAY, size: 16 }), new TextRun({ children: [PageNumber.CURRENT], color: GRAY, size: 16 })],
      })] }) },
      children: [
        new Paragraph({ text: title, style: "Title" }),
        new Paragraph({ text: item.subtitle, style: "Subtitle" }),
        metadataTable(item),
        new Paragraph({ text: "", pageBreakBefore: true }),
        new Paragraph({ text: "문서 읽는 법", heading: HeadingLevel.HEADING_1 }),
        new Paragraph({
          spacing: { after: 180 },
          children: [new TextRun({ text: "이 문서는 AI Factory Studio 저장소의 현재 코드와 화면 구현을 기준으로 작성한 As-Is 역설계 문서입니다. 계획·아이디어·향후 로드맵은 구현 사실로 취급하지 않았으며, 실제로 동작하는 기능·부분 구현·명시된 제약을 구분해 기록했습니다.", size: 20 })],
        }),
        new Paragraph({ text: "목차", heading: HeadingLevel.HEADING_1 }),
        new TableOfContents("", { hyperlink: true, headingStyleRange: "1-3" }),
        ...markdownToBlocks(markdown),
      ],
    }],
  });
  const buffer = await Packer.toBuffer(doc);
  const baseTarget = path.join(DOCS, item.output);
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
  const parsed = path.parse(baseTarget);
  const versionedTarget = path.join(parsed.dir, `${parsed.name}_${stamp}${parsed.ext}`);
  let target = VERSIONED_OUTPUT ? versionedTarget : baseTarget;

  try {
    fs.writeFileSync(target, buffer);
  } catch (error) {
    // Word/Explorer가 기존 파일을 잡고 있으면 기존 검토본을 훼손하지 않고 새 버전으로 남긴다.
    if (!VERSIONED_OUTPUT && ["EPERM", "EACCES"].includes(error.code)) {
      target = versionedTarget;
      fs.writeFileSync(target, buffer);
    } else {
      throw error;
    }
  }
  console.log(`${path.basename(target)} (${fs.statSync(target).size} bytes)`);
}

(async () => {
  for (const item of sources) await build(item);
})().catch((error) => { console.error(error); process.exitCode = 1; });
