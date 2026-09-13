// ArchitectureFlows — System Architecture Flows tab. Renders a static, warm-themed
// SVG flowchart DERIVED FROM THE PRD (one node per functional requirement /
// user story in the validated dataset the PRD was generated from), plus the
// Mermaid flowchart source under it. With no PRD info the default "No info
// yet" empty state is shown.
import { Network, Info, FileCode } from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';
import { Tooltip } from './Tooltip';

/** One flowchart node derived from the PRD's requirements / user stories. */
interface FlowStep {
  code: string;
  title: string;
  storyCount: number;
}

// Flowchart layout constants (top-down spine, one node per PRD requirement).
const MAX_STEPS = 8;
const NODE_W = 300;
const NODE_H = 44;
const GAP = 26;
const START_H = 30;
const CENTER_X = 325;

const trunc = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

export function ArchitectureFlows({ state }: { state: ProjectState }) {
  const {
    mermaidDiagram,
    diagramZoom,
    setDiagramZoom,
    hoverNode,
    setHoverNode,
  } = state;

  // --- PRD-derived flowchart data -------------------------------------------
  // The PRD is generated from the validated requirement dataset, so the
  // flowchart nodes come straight from `structuredRequirements`: functional
  // requirements first, user stories as fallback, the epic as last resort.
  const { epic_name: epic, version, requirements, user_stories: stories } = state.structuredRequirements;
  let steps: FlowStep[] = (requirements ?? []).map((r, i) => ({
    code: r.requirement_code || `REQ-${String(i + 1).padStart(3, '0')}`,
    title: r.title || r.description || 'Requirement',
    storyCount: r.user_stories?.length ?? 0,
  }));
  if (steps.length === 0) {
    steps = (stories ?? []).map((s, i) => ({
      code: s.ticket_code || `US-${String(i + 1).padStart(3, '0')}`,
      title: s.story_title || 'User story',
      storyCount: s.acceptance_criteria?.length ?? 0,
    }));
  }
  if (steps.length === 0 && epic) {
    steps = [{ code: `V${version ?? 1}`, title: epic, storyCount: 0 }];
  }
  const hasPrdInfo = steps.length > 0;

  // Shared hover handlers/fills for the flowchart nodes (warm theme tones).
  const hoverProps = (key: string) => ({
    onMouseEnter: () => setHoverNode(key),
    onMouseLeave: () => setHoverNode(null),
  });
  // Requirement nodes: white card with a subtle warm highlight on hover.
  const nodeFill = (key: string) => (hoverNode === key ? '#ece7dc' : '#ffffff');
  // Start/End terminals: solid brand brown, brightened on hover.
  const terminalFill = (key: string) => (hoverNode === key ? '#a9835f' : '#8a6a50');

  // --- Layout (computed from the derived steps) ------------------------------
  const hasEpic = Boolean(epic);
  const yStart = hasEpic ? 40 : 16;
  const startBottom = yStart + START_H;
  const firstTop = startBottom + GAP;
  const shownSteps = steps.slice(0, MAX_STEPS);
  const hiddenCount = steps.length - shownSteps.length;
  const nodeTop = (i: number) => firstTop + i * (NODE_H + GAP);
  const lastBottom = nodeTop(shownSteps.length - 1) + NODE_H;
  const endTop = firstTop + shownSteps.length * (NODE_H + GAP);
  const viewH = endTop + START_H + 16;
  const edgePaths = hasPrdInfo
    ? [
        `M ${CENTER_X},${startBottom} L ${CENTER_X},${firstTop - 4}`,
        ...shownSteps.slice(0, -1).map((_, i) => `M ${CENTER_X},${nodeTop(i) + NODE_H} L ${CENTER_X},${nodeTop(i + 1) - 4}`),
        `M ${CENTER_X},${lastBottom} L ${CENTER_X},${endTop - 4}`,
      ]
    : [];

  // --- Mermaid source --------------------------------------------------------
  // The backend-generated diagram (itself PRD-derived) wins when it is a
  // flowchart; otherwise the flowchart markdown is generated from the PRD
  // dataset so the source always mirrors the visual above.
  const backendIsFlowchart = /^\s*(flowchart|graph)\s+(TD|TB|LR|RL)/i.test(mermaidDiagram || '');
  const derivedMermaid = hasPrdInfo
    ? [
        'flowchart TD',
        epic ? `    %% PRD Epic: ${epic} (v${version ?? 1})` : null,
        '    S([Start])',
        ...steps.flatMap((s, i) => ([
          `    N${i}["${s.code} · ${trunc(s.title, 60).replace(/"/g, "'")}"]`,
          `    ${i === 0 ? 'S' : `N${i - 1}`} --> N${i}`,
        ])),
        `    N${steps.length - 1} --> E([End])`,
      ].filter(Boolean).join('\n')
    : '';
  const displayedDiagram = backendIsFlowchart ? mermaidDiagram : derivedMermaid;

  return (
    <div className="space-y-6 animate-fadeIn">
      
      {/* Visual SVG diagram view with interactive controls */}
      <div className="bg-white rounded-3xl border border-outline p-4 sm:p-6 shadow-sm overflow-hidden relative">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-4 pb-3 border-b border-black/5">
          <div className="flex items-center gap-2 min-w-0">
            <Network className="text-primary w-5 h-5 shrink-0" />
            <div className="min-w-0">
              <h3 className="font-bold text-sm text-on-surface">Interactive System Flowchart</h3>
              <p className="text-[11px] text-on-surface-variant font-mono break-words">Rendering: flowchart TD • Derived from the PRD</p>
            </div>
          </div>
          <div className="flex bg-black/5 rounded-xl p-1 shrink-0">
            <Tooltip label="Zoom out" side="bottom">
              <button
                onClick={() => setDiagramZoom(prev => Math.max(70, prev - 15))}
                aria-label="Zoom out"
                className="p-1 px-2.5 text-xs font-semibold hover:bg-white rounded transition-all cursor-pointer"
              >
                -
              </button>
            </Tooltip>
            <span className="px-3 text-xs font-mono font-bold flex items-center">{diagramZoom}%</span>
            <Tooltip label="Zoom in" side="bottom">
              <button
                onClick={() => setDiagramZoom(prev => Math.min(150, prev + 15))}
                aria-label="Zoom in"
                className="p-1 px-2.5 text-xs font-semibold hover:bg-white rounded transition-all cursor-pointer"
              >
                +
              </button>
            </Tooltip>
          </div>
        </div>

        {/* Interactive Flowchart Stage — derived from the PRD dataset */}
        <div 
          className="w-full flex items-center justify-center p-4 sm:p-6 bg-background border border-outline rounded-2xl overflow-x-auto custom-scrollbar"
        >
          {/* Inner wrapper carries the zoom transform so the scroll container keeps full width */}
          <div
            className="min-w-0 transition-transform duration-300"
            style={{ transform: `scale(${diagramZoom / 100})`, transformOrigin: 'top center' }}
          >
          {hasPrdInfo ? (
          <svg className="w-full max-w-2xl font-mono" viewBox={`0 0 650 ${viewH}`} fill="none">
            {/* Arrowhead marker */}
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#8a6a50" />
              </marker>
            </defs>

            {/* Flowchart edges (always visible) */}
            <g stroke="#8a6a50" strokeWidth="1.5" fill="none" opacity="0.7" markerEnd="url(#arrow)">
              {edgePaths.map((d, i) => (
                <path key={i} d={d} />
              ))}
            </g>

            {/* Flowchart nodes — one per PRD requirement / user story */}
            <g>
              {/* Epic name from the PRD */}
              {hasEpic && (
                <text x={CENTER_X} y={24} fill="#8c8676" fontSize="11" fontWeight="bold" textAnchor="middle" className="pointer-events-none">{trunc(epic, 52)}</text>
              )}

              {/* Start terminal */}
              <rect
                x={CENTER_X - 60} y={yStart} width="120" height={START_H} rx="16"
                fill={terminalFill('start')}
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                {...hoverProps('start')}
              />
              <text x={CENTER_X} y={yStart + 20} fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle" className="pointer-events-none">Start</text>

              {/* PRD requirement nodes */}
              {shownSteps.map((step, i) => {
                const top = nodeTop(i);
                return (
                  <g key={`${step.code}-${i}`}>
                    <rect
                      x={CENTER_X - NODE_W / 2} y={top} width={NODE_W} height={NODE_H} rx="10"
                      fill={nodeFill(`step-${i}`)}
                      stroke="#8a6a50" strokeWidth="1.5"
                      className="cursor-pointer transition-colors"
                      {...hoverProps(`step-${i}`)}
                    />
                    <text x={CENTER_X} y={top + 17} fill="#8a6a50" fontSize="10" fontWeight="bold" textAnchor="middle" className="pointer-events-none">{step.code}</text>
                    <text x={CENTER_X} y={top + 33} fill="#171717" fontSize="10" textAnchor="middle" className="pointer-events-none">{trunc(step.title, 40)}</text>
                    {step.storyCount > 0 && (
                      <text x={CENTER_X + NODE_W / 2 - 10} y={top + 17} fill="#8c8676" fontSize="8" textAnchor="end" className="pointer-events-none">{step.storyCount} {step.storyCount === 1 ? 'story' : 'stories'}</text>
                    )}
                  </g>
                );
              })}

              {/* End terminal */}
              <rect
                x={CENTER_X - 60} y={endTop} width="120" height={START_H} rx="16"
                fill={terminalFill('end')}
                stroke="#8a6a50" strokeWidth="1.5"
                className="cursor-pointer transition-colors"
                {...hoverProps('end')}
              />
              <text x={CENTER_X} y={endTop + 20} fill="#ffffff" fontSize="10" fontWeight="bold" textAnchor="middle" className="pointer-events-none">End</text>

              {hiddenCount > 0 && (
                <text x={CENTER_X} y={endTop + START_H + 13} fill="#8c8676" fontSize="9" textAnchor="middle" className="pointer-events-none">+{hiddenCount} more requirements in the PRD</text>
              )}
            </g>

          </svg>
          ) : (
          <div className="p-6 sm:p-10 m-2 border border-dashed border-outline rounded-2xl flex flex-col items-center justify-center gap-1.5 text-center">
            <FileCode className="w-7 h-7 text-primary/40" />
            <span className="text-sm font-bold text-on-surface">No info yet</span>
            <p className="text-xs text-on-surface-variant italic max-w-sm">
              The flowchart is derived from the PRD — validate requirements and generate the PRD first.
            </p>
          </div>
          )}
          </div>
        </div>

        <div className="mt-4 p-4.5 bg-black/5 rounded-2xl border border-black/5 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-on-surface">
            <Info className="text-primary w-4 h-4 shrink-0" />
            <span>Visual Diagram Node Explanations:</span>
          </div>
          <p className="text-xs text-on-surface-variant leading-relaxed">
            Every node is derived from the PRD — one per functional requirement (or user story) in the validated dataset, in document order. Hover over a node to highlight it; the arrows show the processing order from Start to End.
          </p>
        </div>
      </div>

      {/* Raw Mermaid flowchart source panel — the source mirrors the PRD:
          the backend-generated flowchart when present, otherwise the
          flowchart generated from the PRD dataset; "No info yet" until the
          PRD data exists. */}
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <FileCode className="text-primary w-4.5 h-4.5" />
          <span className="font-bold text-sm text-on-surface">Raw Mermaid.js Flowchart Source</span>
          <span className="text-[10px] font-mono font-bold bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded uppercase">flowchart TD</span>
        </div>
        {hasPrdInfo ? (
          <pre className="p-4 bg-slate-900 text-slate-100 font-mono text-xs rounded-2xl overflow-x-auto border border-slate-800">
            <code>{displayedDiagram}</code>
          </pre>
        ) : (
          <div className="p-10 bg-black/5 border border-dashed border-outline rounded-2xl flex flex-col items-center justify-center gap-1.5 text-center">
            <FileCode className="w-6 h-6 text-on-surface-variant/50" />
            <span className="text-sm font-bold text-on-surface">No info yet</span>
            <p className="text-xs text-on-surface-variant italic max-w-sm">
              The flowchart is derived from the PRD — validate requirements and generate the PRD first.
            </p>
          </div>
        )}
      </div>

    </div>
  );
}