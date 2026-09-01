// JSX-producing markdown renderer extracted from the former Dashboard.tsx.
// Renders markdown lines into high-fidelity styled React elements on-the-fly.
// Pure string helpers live in ../utils/markdown.ts.

export function renderInlineFormatting(text: string) {
  if (!text) return '';
  // Support bold formatting **text**
  const parts = text.split('**');
  return parts.map((part, index) => {
    if (index % 2 === 1) {
      return <strong key={index} className="font-semibold text-slate-900">{part}</strong>;
    }
    // Also support simple inline code format `code` inside the parts
    const subParts = part.split('`');
    return subParts.map((subPart, subIndex) => {
      if (subIndex % 2 === 1) {
        return <code key={subIndex} className="bg-slate-100 text-primary font-mono text-[11px] px-1.5 py-0.5 rounded border border-slate-200">{subPart}</code>;
      }
      return subPart;
    });
  });
}

// Splits a markdown table row "| a | b |" into its trimmed cells.
function splitMarkdownRow(row: string): string[] {
  return row
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
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
  const hasHeader = rows.length > 1 && isSeparatorRow(rows[1]);
  const headerCells = hasHeader ? splitMarkdownRow(rows[0]) : null;
  const bodyRows = hasHeader ? rows.slice(2) : rows;

  return (
    <table key={key} className="w-full border-collapse my-4 text-sm">
      {headerCells && (
        <thead>
          <tr>
            {headerCells.map((cell, i) => (
              <th
                key={i}
                className="border border-slate-200 bg-slate-50 px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-slate-700"
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
            {splitMarkdownRow(row).map((cell, c) => (
              <td key={c} className="border border-slate-200 px-3 py-2 align-top text-slate-600 leading-relaxed">
                {renderCellContent(cell)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
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
    <div className="space-y-3.5 text-on-surface-variant font-sans">
      {blocks.map((block, idx) => {
        if (block.kind === 'table') {
          return renderMarkdownTable(block.rows, `tbl-${idx}`);
        }

        const trimmed = block.line.trim();

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
            <blockquote key={idx} className="border-l-4 border-primary/40 bg-primary/5 pl-4 pr-2 py-2 rounded-r-md italic my-4 text-slate-700 text-sm">
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
            <li key={idx} className="ml-5 list-disc text-slate-700 my-1 leading-relaxed text-sm">
              {renderInlineFormatting(trimmed.slice(2))}
            </li>
          );
        }

        // Numbered Lists
        const numListMatch = trimmed.match(/^(\d+)\.\s(.*)/);
        if (numListMatch) {
          return (
            <li key={idx} className="ml-5 list-decimal text-slate-700 my-1 leading-relaxed text-sm">
              {renderInlineFormatting(numListMatch[2])}
            </li>
          );
        }

        // Empty line
        if (trimmed === '') {
          return <div key={idx} className="h-1"></div>;
        }

        // Standard Paragraph
        return (
          <p key={idx} className="text-slate-600 my-2 leading-relaxed text-sm">
            {renderInlineFormatting(trimmed)}
          </p>
        );
      })}
    </div>
  );
}