// JSX-producing markdown renderer extracted from the former Dashboard.tsx.
// Renders markdown lines into high-fidelity styled React elements on-the-fly.
// Pure string helpers live in ../utils/markdown.ts.
import type { ReactNode } from 'react';
import { highlightMatch } from '../utils/highlight';

// Renders inline markdown formatting (`**bold**` → real <strong>, `` `code` `` →
// styled <code>) as React nodes, on-the-fly from a plain string.
//
// For the chat panel the optional `highlightQuery`/`highlightClass` args are
// forwarded so the sidebar search highlight keeps lighting up matches — the
// formatting and highlight compose on the same message body. Bold/code nodes
// inherit the surrounding text color so they stay readable on brand-tinted
// chat bubbles (white-on-brown) as well as the white PRD preview surface.
export function renderInlineFormatting(
  text: string,
  highlightQuery?: string,
  highlightClass?: string,
): ReactNode {
  if (!text) return '';
  const nodes: ReactNode[] = [];

  // Renders one non-bold chunk: `` `code` `` spans become <code> chips and
  // everything else goes through the shared search-highlighter.
  const renderCodeAndText = (chunk: string): void => {
    const codePattern = /`([^`]+?)`/g;
    let codeMatch: RegExpExecArray | null;
    let last = 0;
    while ((codeMatch = codePattern.exec(chunk)) !== null) {
      const plain = chunk.slice(last, codeMatch.index);
      if (plain) nodes.push(highlightMatch(plain, highlightQuery ?? '', highlightClass));
      nodes.push(
        <code
          key={nodes.length}
          className="bg-slate-100 text-primary font-mono text-[11px] px-1.5 py-0.5 rounded border border-slate-200"
        >
          {codeMatch[1]}
        </code>,
      );
      last = codeMatch.index + codeMatch[0].length;
    }
    if (last < chunk.length) {
      nodes.push(highlightMatch(chunk.slice(last), highlightQuery ?? '', highlightClass));
    }
  };

  // Paired **bold** segments only — an unmatched opening `**` (e.g. `5 ** 3`)
  // stays literal text instead of bolding the rest of the line.
  const boldPattern = /\*\*([^*]+?)\*\*/g;
  let boldMatch: RegExpExecArray | null;
  let cursor = 0;
  while ((boldMatch = boldPattern.exec(text)) !== null) {
    renderCodeAndText(text.slice(cursor, boldMatch.index));
    nodes.push(
      <strong key={nodes.length} className="font-bold">
        {highlightMatch(boldMatch[1], highlightQuery ?? '', highlightClass)}
      </strong>,
    );
    cursor = boldMatch.index + boldMatch[0].length;
  }
  renderCodeAndText(text.slice(cursor));

  return nodes;
}

// Splits a markdown table row "| a | b |" into its trimmed cells.
function splitMarkdownRow(row: string): string[] {
  const source = row.replace(/^\|/, '').replace(/\|$/, '');
  const cells: string[] = [];
  let cell = '';
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    // A GFM escaped pipe belongs to the cell; it is not a column boundary.
    if (char === '\\' && source[i + 1] === '|') {
      cell += '|';
      i += 1;
    } else if (char === '|') {
      cells.push(cell.trim());
      cell = '';
    } else {
      cell += char;
    }
  }
  cells.push(cell.trim());
  return cells;
}

// True for GFM separator rows like "|---|---|".
function isSeparatorRow(row: string): boolean {
  const cells = splitMarkdownRow(row);
  return cells.length > 0 && cells.every((cell) => /^:?-{1,}:?$/.test(cell) || cell === '');
}

// Renders a template/PRD table cell. Cells may contain inline markdown and
// GFM-style <br> line breaks (the Krungsri template uses them heavily), which
// are converted into real line breaks instead of literal text.
function renderCellContent(cell: string) {
  const segments = cell.split(/<br\s*\/?>/i);
  return segments.map((segment, i) => (
    <span key={i}>
      {i > 0 && <br />}
      {renderInlineFormatting(segment)}
    </span>
  ));
}

// Renders grouped markdown-table lines as a styled React table.
function renderMarkdownTable(rows: string[], key: string) {
  const separatorIndex = rows.findIndex(isSeparatorRow);
  const declaredHeader = separatorIndex > 0 ? splitMarkdownRow(rows[separatorIndex - 1]) : null;
  // Separator rows are Markdown syntax, never document content. Filter every
  // occurrence so repeated separators from generated/edited tables cannot
  // leak strings such as `:-----------------` into the visible preview.
  let bodyRows = rows.filter((row, index) => (
    !isSeparatorRow(row) && (separatorIndex < 0 || index !== separatorIndex - 1)
  ));

  // Pandoc sometimes emits an empty first row for LaTeX tables whose real
  // headings are in the next bold row. Do not render that empty band as the
  // table header; promote the next all-bold row when one is available.
  let headerCells = declaredHeader?.some(Boolean) ? declaredHeader : null;
  if (!headerCells && bodyRows.length > 0) {
    const firstBodyCells = splitMarkdownRow(bodyRows[0]);
    if (firstBodyCells.some(Boolean) && firstBodyCells.every(cell => !cell || /^\*\*.+\*\*$/.test(cell))) {
      headerCells = firstBodyCells;
      bodyRows = bodyRows.slice(1);
    }
  }

  const allRows = [headerCells, ...bodyRows.map(splitMarkdownRow)].filter(Boolean) as string[][];
  const columnCount = Math.max(1, ...allRows.map(row => row.length));
  const normalizeCells = (cells: string[]) => [
    ...cells.slice(0, columnCount),
    ...Array(Math.max(0, columnCount - cells.length)).fill(''),
  ];
  if (headerCells) headerCells = normalizeCells(headerCells);

  return (
    <div key={key} className="w-full max-w-full overflow-hidden my-4 rounded-xl border border-slate-200">
    <table className="w-full max-w-full border-collapse text-sm table-fixed">
      {headerCells && (
        <thead>
          <tr>
            {headerCells.map((cell, i) => (
              <th
                key={i}
                className="border border-slate-200 bg-slate-50 px-2 sm:px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-slate-700 break-words [overflow-wrap:anywhere]"
              >
                {renderCellContent(cell)}
              </th>
            ))}
          </tr>
        </thead>
      )}
      <tbody>
        {bodyRows.map((row, r) => (
          <tr key={r} className={r % 2 === 1 ? 'bg-slate-50/50' : ''}>
            {normalizeCells(splitMarkdownRow(row)).map((cell, c) => (
              <td key={c} className="border border-slate-200 px-2 sm:px-3 py-2 align-top text-slate-600 leading-relaxed break-words [overflow-wrap:anywhere] whitespace-normal">
                {renderCellContent(cell)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

type MarkdownBlock = { kind: 'line'; line: string } | { kind: 'table'; rows: string[] };

export function parseAndRenderMarkdown(md: string) {
  if (!md) return null;
  const lines = md.split('\n');

  // First pass: group consecutive pipe-table lines into single table blocks so
  // they render as real <table> elements (the Krungsri PRD template is almost
  // entirely tables) instead of raw "|" characters.
  const blocks: MarkdownBlock[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('|')) {
      const last = blocks[blocks.length - 1];
      if (last && last.kind === 'table') last.rows.push(trimmed);
      else blocks.push({ kind: 'table', rows: [trimmed] });
    } else {
      blocks.push({ kind: 'line', line });
    }
  }

  return (
    <div className="space-y-3.5 text-on-surface-variant font-sans min-w-0">
      {blocks.map((block, idx) => {
        if (block.kind === 'table') {
          return renderMarkdownTable(block.rows, `tbl-${idx}`);
        }

        const trimmed = block.line.trim();

        // Pandoc wraps the cover brand in a flushright HTML container. The
        // preview does not render raw HTML; hide the wrapper and style its
        // retained text directly.
        if (/^<\/?div(?:\s[^>]*)?>$/i.test(trimmed)) return null;
        if (trimmed.toLowerCase() === 'nimble by krungsri') {
          return (
            <h2 key={idx} className="text-xl font-bold text-right text-slate-800 mt-2 mb-8 tracking-tight">
              {trimmed}
            </h2>
          );
        }

        // Manual page break marker — shown as a subtle divider in the preview.
        if (trimmed === '\\newpage') {
          return (
            <div key={idx} className="my-6 flex items-center gap-3" aria-label="Page break">
              <span className="h-px flex-1 bg-slate-200" />
              <span className="text-[10px] uppercase tracking-widest text-slate-400">Page Break</span>
              <span className="h-px flex-1 bg-slate-200" />
            </div>
          );
        }

        // Headers
        if (trimmed.startsWith('# ')) {
          return (
            <h1 key={idx} className="text-2xl font-extrabold text-slate-900 border-b border-slate-100 pb-3 mt-8 mb-4 tracking-tight">
              {trimmed.slice(2)}
            </h1>
          );
        }
        if (trimmed.startsWith('## ')) {
          const headingText = trimmed.slice(3);
          const isCoverTitle = headingText.trim().toLowerCase() === 'nimble by krungsri';
          return (
            <h2 key={idx} className={`text-xl font-bold text-slate-800 border-b border-slate-100/50 pb-2 mt-6 mb-3 tracking-tight${isCoverTitle ? ' text-right' : ''}`}>
              {headingText}
            </h2>
          );
        }
        if (trimmed.startsWith('### ')) {
          return (
            <h3 key={idx} className="text-lg font-bold text-slate-800 mt-5 mb-2 tracking-tight">
              {trimmed.slice(4)}
            </h3>
          );
        }
        if (trimmed.startsWith('#### ')) {
          return (
            <h4 key={idx} className="text-base font-semibold text-slate-700 mt-4 mb-2">
              {trimmed.slice(5)}
            </h4>
          );
        }

        // Blockquotes
        if (trimmed.startsWith('> ')) {
          return (
            <blockquote key={idx} className="border-l-4 border-primary/40 bg-primary/5 pl-4 pr-2 py-2 rounded-r-md italic my-4 text-slate-700 text-sm break-words min-w-0">
              {renderInlineFormatting(trimmed.slice(2))}
            </blockquote>
          );
        }

        // Horizontal Rules
        if (trimmed === '---' || trimmed === '***') {
          return <hr key={idx} className="border-t border-slate-100 my-6" />;
        }

        // Bullet Lists
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          return (
            <li key={idx} className="ml-5 list-disc text-slate-700 my-1 leading-relaxed text-sm break-words">
              {renderInlineFormatting(trimmed.slice(2))}
            </li>
          );
        }

        // Numbered Lists
        const numListMatch = trimmed.match(/^(\d+)\.\s(.*)/);
        if (numListMatch) {
          return (
            <li key={idx} className="ml-5 list-decimal text-slate-700 my-1 leading-relaxed text-sm break-words">
              {renderInlineFormatting(numListMatch[2])}
            </li>
          );
        }

        // Empty line
        if (trimmed === '') {
          return <div key={idx} className="h-1"></div>;
        }

        // Standard Paragraph
        const paragraphText = trimmed.endsWith('\\') ? trimmed.slice(0, -1).trimEnd() : trimmed;
        return (
          <p key={idx} className="text-slate-600 my-2 leading-relaxed text-sm break-words">
            {renderInlineFormatting(paragraphText)}
          </p>
        );
      })}
    </div>
  );
}
