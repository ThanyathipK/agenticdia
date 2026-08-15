// ArchitectureFlows — System Architecture Flows tab extracted from the former
// Dashboard.tsx. Renders the interactive animated SVG sequence diagram and the
// raw Mermaid source string.
import { Network, Info, FileCode } from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';

export function ArchitectureFlows({ state }: { state: ProjectState }) {
  const {
    mermaidDiagram,
    diagramZoom,
    setDiagramZoom,
    hoverNode,
    setHoverNode,
    activePacketFlow,
  } = state;

  return (
    <div className="space-y-6 animate-fadeIn">
      
      {/* Visual SVG diagram view with interactive controls */}
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm overflow-hidden relative">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-black/5">
          <div className="flex items-center gap-2">
            <Network className="text-primary w-5 h-5 animate-pulse" />
            <div>
              <h3 className="font-bold text-sm text-on-surface">Interactive System Sequence Flows</h3>
              <p className="text-[11px] text-on-surface-variant font-mono">Rendering: sequenceDiagram • Real-time Active Flows</p>
            </div>
          </div>
          <div className="flex bg-black/5 rounded-xl p-1">
            <button 
              onClick={() => setDiagramZoom(prev => Math.max(70, prev - 15))}
              className="p-1 px-2.5 text-xs font-semibold hover:bg-white rounded transition-all cursor-pointer"
            >
              -
            </button>
            <span className="px-3 text-xs font-mono font-bold flex items-center">{diagramZoom}%</span>
            <button 
              onClick={() => setDiagramZoom(prev => Math.min(150, prev + 15))}
              className="p-1 px-2.5 text-xs font-semibold hover:bg-white rounded transition-all cursor-pointer"
            >
              +
            </button>
          </div>
        </div>

        {/* Interactive Animated SVG Stage representing the compiled Mermaid output */}
        <div 
          className="w-full flex items-center justify-center p-6 bg-slate-950/95 rounded-2xl overflow-x-auto transition-transform duration-300"
          style={{ transform: `scale(${diagramZoom / 100})`, transformOrigin: 'top center' }}
        >
          <svg className="w-full max-w-2xl text-white font-mono" viewBox="0 0 650 360" fill="none">
            {/* Lifelines */}
            <g stroke="#ffffff" strokeWidth="1" strokeDasharray="5 5" opacity="0.15">
              <line x1="80" y1="50" x2="80" y2="310" />
              <line x1="220" y1="50" x2="220" y2="310" />
              <line x1="380" y1="50" x2="380" y2="310" />
              <line x1="560" y1="50" x2="560" y2="310" />
            </g>

            {/* Node Headers */}
            <g transform="translate(0, 10)">
              {/* Client Browser */}
              <rect 
                x="20" y="10" width="120" height="35" rx="5" 
                fill={hoverNode === "client" ? "#8a6a50" : "#1e293b"} 
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                onMouseEnter={() => setHoverNode("client")}
                onMouseLeave={() => setHoverNode(null)}
              />
              <text x="80" y="32" fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle">React Client</text>

              {/* FastAPI Backend */}
              <rect 
                x="160" y="10" width="120" height="35" rx="5" 
                fill={hoverNode === "backend" ? "#8a6a50" : "#1e293b"} 
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                onMouseEnter={() => setHoverNode("backend")}
                onMouseLeave={() => setHoverNode(null)}
              />
              <text x="220" y="32" fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle">FastAPI Backend</text>

              {/* National Switch */}
              <rect 
                x="320" y="10" width="120" height="35" rx="5" 
                fill={hoverNode === "switch" ? "#8a6a50" : "#1e293b"} 
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                onMouseEnter={() => setHoverNode("switch")}
                onMouseLeave={() => setHoverNode(null)}
              />
              <text x="380" y="32" fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle">PromptPay Switch</text>

              {/* Supabase DB */}
              <rect 
                x="500" y="10" width="120" height="35" rx="5" 
                fill={hoverNode === "db" ? "#8a6a50" : "#1e293b"} 
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                onMouseEnter={() => setHoverNode("db")}
                onMouseLeave={() => setHoverNode(null)}
              />
              <text x="560" y="32" fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle">Supabase DB</text>
            </g>

            {/* Transaction Packet Flow animations */}
            {activePacketFlow && (
              <g>
                {/* Inbound POST */}
                <path d="M 80,90 L 220,90" stroke="#8a6a50" strokeWidth="2" strokeDasharray="6 4" markerEnd="url(#arrow)">
                  <animate attributeName="stroke-dashoffset" values="50;0" dur="2s" repeatCount="indefinite" />
                </path>
                <text x="150" y="82" fill="#f59e0b" fontSize="9" textAnchor="middle">1. POST /api/transaction</text>

                {/* Verification call */}
                <path d="M 220,140 L 380,140" stroke="#8a6a50" strokeWidth="1.5" strokeDasharray="6 4" markerEnd="url(#arrow)">
                  <animate attributeName="stroke-dashoffset" values="50;0" dur="2s" repeatCount="indefinite" />
                </path>
                <text x="300" y="132" fill="#f59e0b" fontSize="9" textAnchor="middle">2. ISO 20022 message</text>

                {/* National Switch Callback */}
                <path d="M 380,190 L 220,190" stroke="#10b981" strokeWidth="1.5" strokeDasharray="6 4" markerEnd="url(#arrow)">
                  <animate attributeName="stroke-dashoffset" values="0;50" dur="2s" repeatCount="indefinite" />
                </path>
                <text x="300" y="182" fill="#34d399" fontSize="9" textAnchor="middle">3. 200 OK Settlement Confirmed</text>

                {/* Database write */}
                <path d="M 220,240 L 560,240" stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="6 4" markerEnd="url(#arrow)">
                  <animate attributeName="stroke-dashoffset" values="50;0" dur="2.5s" repeatCount="indefinite" />
                </path>
                <text x="390" y="232" fill="#93c5fd" fontSize="9" textAnchor="middle">4. Sync Ledger snapshot &amp; Idempotency</text>

                {/* Final return */}
                <path d="M 220,290 L 80,290" stroke="#10b981" strokeWidth="1.5" strokeDasharray="6 4" markerEnd="url(#arrow)">
                  <animate attributeName="stroke-dashoffset" values="0;50" dur="2s" repeatCount="indefinite" />
                </path>
                <text x="150" y="282" fill="#34d399" fontSize="9" textAnchor="middle">5. Return receipt</text>
              </g>
            )}

            {/* Baseline anchors */}
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#8a6a50" />
              </marker>
            </defs>
          </svg>
        </div>

        <div className="mt-4 p-4.5 bg-black/5 rounded-2xl border border-black/5 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-on-surface">
            <Info className="text-primary w-4 h-4 shrink-0" />
            <span>Visual Diagram Node Explanations:</span>
          </div>
          <p className="text-xs text-on-surface-variant leading-relaxed">
            Hover over headers to trace state changes. The network packets represent actual real-time ISO 20022 message envelopes parsed by the FastAPI route and compiled to Supabase in a single ACID transaction window.
          </p>
        </div>
      </div>

      {/* Raw Mermaid code collapse panel */}
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <FileCode className="text-primary w-4.5 h-4.5" />
          <span className="font-bold text-sm text-on-surface">Raw Mermaid.js Source String</span>
        </div>
        <pre className="p-4 bg-slate-900 text-slate-100 font-mono text-xs rounded-2xl overflow-x-auto border border-slate-800">
          <code>{mermaidDiagram}</code>
        </pre>
      </div>

    </div>
  );
}