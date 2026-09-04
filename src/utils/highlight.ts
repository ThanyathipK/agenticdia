// Shared search-term highlight helper.
//
// Used by the sidebar (project names + match snippets) and the chat panel
// (message bubbles) so the active sidebar search query lights up everywhere
// the matched text appears. Pure function: no state, no hooks.
import { createElement } from 'react';
import type { ReactNode } from 'react';

const DEFAULT_HIGHLIGHT_CLASS =
  'bg-primary/15 text-primary font-semibold rounded-[2px] px-0.5 -mx-0.5';

/**
 * Case-insensitively wrap every occurrence of `query` inside `text` in a
 * themed `<mark>`, returning ReactNode parts. When the query is empty or
 * nothing matches, the original text is returned unchanged.
 */
export function highlightMatch(
  text: string,
  query: string,
  highlightClass: string = DEFAULT_HIGHLIGHT_CLASS,
): ReactNode {
  const needle = query.trim().toLowerCase();
  if (!needle || !text) return text;
  const lower = text.toLowerCase();

  const parts: ReactNode[] = [];
  let index = 0;
  let hit = lower.indexOf(needle);
  while (hit !== -1) {
    if (hit > index) parts.push(text.slice(index, hit));
    parts.push(
      createElement(
        'mark',
        { key: parts.length, className: highlightClass },
        text.slice(hit, hit + needle.length),
      ),
    );
    index = hit + needle.length;
    hit = lower.indexOf(needle, index);
  }
  parts.push(text.slice(index));
  return parts.length === 1 ? parts[0] : parts;
}