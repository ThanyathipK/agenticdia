import { useState, useMemo } from 'react';
import { Search, Copy } from 'lucide-react';

// One line of the displayed DDL, with an optional search-match highlight flag.
// Keeps the SQL rendering fully typed instead of casting to `any`.
interface SqlLine {
  text: string;
  highlighted: boolean;
}

interface DDLViewerProps {
  /**
   * Full PostgreSQL DDL text. Single source of truth imported from
   * backend/init.sql (`?raw`) by the owning container.
   */
  sqlText: string;
  /**
   * Copies the full DDL to the clipboard. Lifted to the parent so the
   * main "Copy DDL Code" header button and this viewer share the same
   * feedback (copied checkmark + toast).
   */
  onCopySql: () => void;
}

/**
 * TAB: POSTGRESQL DDL (init.sql)
 * Renders the live DDL script with a search-highlight viewer and a
 * full-script copy action.
 */
export default function DDLViewer({ sqlText, onCopySql }: DDLViewerProps) {
  // Search filter for SQL text
  const [sqlSearch, setSqlSearch] = useState<string>('');

  // Filtered rows of SQL based on user search
  const sqlLines = useMemo<SqlLine[]>(() => {
    const lines = sqlText.split('\n');
    if (!sqlSearch) {
      return lines.map(line => ({ text: line, highlighted: false }));
    }
    return lines.map(line => ({
      text: line,
      highlighted: line.toLowerCase().includes(sqlSearch.toLowerCase()),
    }));
  }, [sqlSearch, sqlText]);

  return (
    <div className="flex-1 flex flex-col bg-slate-950 rounded-2xl shadow-lg overflow-hidden border border-slate-800">
      <div className="bg-slate-900 px-5 py-3 border-b border-slate-800 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <span className="flex w-2.5 h-2.5 rounded-full bg-navy-500"></span>
          <span className="text-xs font-mono font-bold text-slate-200">init.sql - Postgres DDL</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 transform -translate-y-1/2" />
            <input 
              type="text" 
              placeholder="Search lines or constraints..."
              value={sqlSearch}
              onChange={(e) => setSqlSearch(e.target.value)}
              className="pl-8 pr-3 py-1 bg-slate-950 border border-slate-800 rounded text-xs text-slate-300 font-mono focus:outline-none focus:border-navy-500 w-52 transition-all"
            />
          </div>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/50 border border-emerald-900 px-2 py-0.5 rounded uppercase">{sqlText.split('\n').length} Lines</span>
        </div>
      </div>
      
      <div className="p-5 font-mono text-[12px] leading-relaxed overflow-y-auto flex-1 select-text scrollbar-thin scrollbar-thumb-slate-800">
        <pre className="text-slate-300 whitespace-pre-wrap">
          {sqlLines.map((line, i) => {
            const { text, highlighted } = line;
            
            return (
              <div 
                key={i} 
                className={`py-0.5 px-2 rounded -mx-2 flex ${
                  highlighted ? 'bg-orange-500/20 text-white font-bold border-l-2 border-orange-500' : 'hover:bg-slate-900/30'
                }`}
              >
                <span className="text-slate-600 select-none w-8 shrink-0 text-right pr-3 font-mono text-[10px]">{i + 1}</span>
                <span className="break-all">{text || ' '}</span>
              </div>
            );
          })}
        </pre>
      </div>
      <div className="bg-slate-900 px-5 py-3 border-t border-slate-800 flex justify-between items-center text-xs text-slate-400 font-mono">
        <span>Target: Supabase PostgreSQL (uuid-ossp enabled)</span>
        <button 
          onClick={onCopySql}
          className="text-navy-400 hover:text-navy-300 flex items-center gap-1 font-semibold"
        >
          <Copy className="w-3.5 h-3.5" />
          <span>Copy Full DDL Script</span>
        </button>
      </div>
    </div>
  );
}
