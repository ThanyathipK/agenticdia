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

export function parseAndRenderMarkdown(md: string) {
  if (!md) return null;
  const lines = md.split('\n');
  return (
    <div className="space-y-3.5 text-on-surface-variant font-sans">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        
        // Headers
        if (trimmed.startsWith('# ')) {
          return (
            <h1 key={idx} className="text-2xl font-extrabold text-slate-900 border-b border-slate-100 pb-3 mt-8 mb-4 tracking-tight">
              {trimmed.slice(2)}
            </h1>
          );
        }
        if (trimmed.startsWith('## ')) {
          return (
            <h2 key={idx} className="text-xl font-bold text-slate-800 border-b border-slate-100/50 pb-2 mt-6 mb-3 tracking-tight">
              {trimmed.slice(3)}
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