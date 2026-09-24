// ProjectsDashboard — projects overview page (the "Dashboard" view).
//
// Rendered next to the project sidebar when the user switches views from the
// sidebar nav (Workspace ⇄ Dashboard). Adapts the approved dashboard mock into
// the app's existing design system (Tailwind theme tokens, lucide icons,
// Tooltip) and reuses the shared project state so sidebar and dashboard never
// disagree:
//
//   - KPI cards   -> All projects / PRDs generated / Pending in review / Approved
//                    ("PRDs generated" probes each project's requirement state
//                    once per visit and counts non-empty generated_prd bodies)
//   - Tab pills   -> All / In review with HPO / In review with PO / Draft /
//                    Approved / Revised / ★ Flagged (dashboard-only marker —
//                    independent of the sidebar pin)
//   - Table rows  -> star = flag toggle (separate is_flagged field), user-editable
//                    workflow status badge (PUT /api/projects/{id}/status),
//                    relative "Updated" time, and an Open action that selects
//                    the project and returns to the workspace view.
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpDown,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  LayoutGrid,
  Search,
  Star,
  XCircle,
} from 'lucide-react';
import type { ProjectState } from '../hooks/useProjectState';
import type { ProjectStatus } from '../api/types';
import { api } from '../api/client';
import { Tooltip } from './Tooltip';
import { formatRelativeUpdated } from '../utils/time';

// ----------------------------------------------------------------------------
// Status metadata (kept in one place so tabs, dropdowns, and badges agree)
// ----------------------------------------------------------------------------

const STATUS_OPTIONS: ReadonlyArray<{ value: ProjectStatus; label: string }> = [
  { value: 'draft', label: 'Draft' },
  { value: 'in_review_hpo', label: 'In review · HPO' },
  { value: 'in_review_po', label: 'In review · PO' },
  { value: 'approved', label: 'Approved' },
  { value: 'revised', label: 'Revised' },
];

const STATUS_LABEL: Record<ProjectStatus, string> = Object.fromEntries(
  STATUS_OPTIONS.map((s) => [s.value, s.label]),
) as Record<ProjectStatus, string>;

/** Badge color classes per status (amber = in review, green = approved, navy = revised). */
const STATUS_BADGE: Record<ProjectStatus, string> = {
  draft: 'bg-black/5 text-on-surface-variant',
  in_review_hpo: 'bg-amber-100 text-amber-800',
  in_review_po: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  revised: 'bg-navy-100 text-navy-700',
};

/** Projects created before the status column default to 'draft' at the UI layer. */
const normalizeStatus = (status: string | undefined): ProjectStatus =>
  (STATUS_OPTIONS.some((s) => s.value === status) ? (status as ProjectStatus) : 'draft');

// Tab pills: filter shortcuts over the same dimensions as the dropdowns.
type TableTab = 'all' | ProjectStatus | 'flagged';

const TABLE_TABS: ReadonlyArray<{ key: TableTab; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'in_review_hpo', label: 'In review with HPO' },
  { key: 'in_review_po', label: 'In review with PO' },
  { key: 'draft', label: 'Draft' },
  { key: 'approved', label: 'Approved' },
  { key: 'revised', label: 'Revised' },
  { key: 'flagged', label: '★ Flagged' },
];

type SortKey = 'updated' | 'name';

// ----------------------------------------------------------------------------
// Dropdown — minimal styled select matching the mock's pill triggers.
// Closes on outside click / Escape; owns only its open flag.
// ----------------------------------------------------------------------------

interface DropdownProps<T extends string> {
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (value: T) => void;
  ariaLabel: string;
}

function Dropdown<T extends string>({ value, options, onChange, ariaLabel }: DropdownProps<T>) {
  const [open, setOpen] = useState<boolean>(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointer = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const current = options.find((o) => o.value === value);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-expanded={open}
        className="h-11 flex items-center gap-2 px-4 bg-surface border border-outline rounded-[10px] text-[13px] font-semibold text-on-surface hover:border-primary/40 transition-colors whitespace-nowrap"
      >
        <span>{current?.label}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-on-surface-variant transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1.5 z-30 min-w-[190px] bg-surface border border-outline rounded-xl shadow-lg py-1">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={`w-full text-left px-3.5 py-2 text-[13px] transition-colors flex items-center justify-between gap-3 ${
                o.value === value ? 'text-primary font-semibold bg-primary/5' : 'text-on-surface hover:bg-black/5'
              }`}
            >
              <span>{o.label}</span>
              {o.value === value && <Check className="w-3.5 h-3.5 shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Pagination — flat "10 per page" over the current filtered/sorted rows. Prev /
// Next arrows frame a windowed number list (first, last, current ±1, ellipsis
// for gaps) so a large list never floods the footer with buttons.
// ----------------------------------------------------------------------------

const PAGE_SIZE = 10;

function paginationItems(
  current: number,
  total: number,
): Array<number | 'ellipsis'> {
  // Few pages: show every number. Otherwise collapse the middle into a window
  // of current ±1 framed by the first/last page, with ellipsis for the gap.
  if (total <= 7) return Array.from({ length: total }, (_, i) => i);
  if (current <= 2) return [0, 1, 2, 3, 'ellipsis', total - 1];
  if (current >= total - 3) return [0, 'ellipsis', total - 4, total - 3, total - 2, total - 1];
  return [0, 'ellipsis', current - 1, current, current + 1, 'ellipsis', total - 1];
}

function PaginationControls({
  totalRows,
  page,
  onPageChange,
}: {
  totalRows: number;
  page: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const from = safePage * PAGE_SIZE + 1;
  const to = Math.min(totalRows, (safePage + 1) * PAGE_SIZE);

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 border-t border-outline">
      <span className="text-[12.5px] text-on-surface-variant whitespace-nowrap">
        Showing {from}–{to} of {totalRows} {totalRows === 1 ? 'project' : 'projects'}
      </span>
      <nav className="flex items-center gap-1" aria-label="Pagination">
        <button
          type="button"
          onClick={() => onPageChange(safePage - 1)}
          disabled={safePage === 0}
          aria-label="Previous page"
          className={`w-8 h-8 inline-flex items-center justify-center rounded-md transition-colors ${
            safePage === 0 ? 'text-on-surface-variant opacity-40 cursor-not-allowed' : 'text-on-surface hover:bg-black/5'
          }`}
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        {paginationItems(safePage, totalPages).map((item, idx) =>
          item === 'ellipsis' ? (
            <span
              key={`ellipsis-${idx}`}
              className="w-8 h-8 inline-flex items-center justify-center text-[12.5px] text-on-surface-variant"
            >
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onPageChange(item)}
              aria-label={`Page ${item + 1}`}
              aria-current={safePage === item ? 'page' : undefined}
              className={`w-8 h-8 inline-flex items-center justify-center rounded-md text-[12.5px] font-semibold transition-colors ${
                safePage === item ? 'bg-primary text-on-primary' : 'text-on-surface hover:bg-black/5'
              }`}
            >
              {item + 1}
            </button>
          ),
        )}
        <button
          type="button"
          onClick={() => onPageChange(safePage + 1)}
          disabled={safePage >= totalPages - 1}
          aria-label="Next page"
          className={`w-8 h-8 inline-flex items-center justify-center rounded-md transition-colors ${
            safePage >= totalPages - 1 ? 'text-on-surface-variant opacity-40 cursor-not-allowed' : 'text-on-surface hover:bg-black/5'
          }`}
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </nav>
    </div>
  );
}

// ----------------------------------------------------------------------------
// ProjectsDashboard
// ----------------------------------------------------------------------------

export function ProjectsDashboard({ state }: { state: ProjectState }) {
  const {
    projects,
    projectId,
    setProjectId,
    handleToggleFlag,
    handleUpdateProjectStatus,
    setActiveView,
  } = state;

  // ---- Table filters (pure presentation state) -----------------------------
  const [query, setQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'all' | ProjectStatus>('all');
  const [sortKey, setSortKey] = useState<SortKey>('updated');
  const [activeTab, setActiveTab] = useState<TableTab>('all');

  // ---- "PRDs generated" KPI --------------------------------------------------
  // The generated PRD body lives in each project's requirement state, so the
  // dashboard probes every project once per visit (tiny JSON rows fetched in
  // parallel) and counts the non-empty ones. Failures (e.g. a project whose
  // state is not initialized yet) simply don't count — the KPI is informational.
  const [prdGeneratedCount, setPrdGeneratedCount] = useState<number>(0);
  const [prdCountLoaded, setPrdCountLoaded] = useState<boolean>(false);

  // Stable dependency key: re-probe when the *set* of projects changes, not on
  // every optimistic status/pin mutation that clones the projects array.
  const projectIdsKey = useMemo(() => projects.map((p) => p.id).join('|'), [projects]);

  useEffect(() => {
    const ids = projectIdsKey ? projectIdsKey.split('|') : [];
    if (ids.length === 0) {
      setPrdGeneratedCount(0);
      setPrdCountLoaded(true);
      return;
    }
    let cancelled = false;
    setPrdCountLoaded(false);
    (async () => {
      const states = await Promise.all(
        // PROJECT 2.6 — Fan-out read: the "PRD generated" KPI issues one
        // GET /api/project/{id} (PROJECT 2.2/2.3) per table row, tolerating
        // individual failures so a single unreadable project cannot blank the KPI.
        ids.map((id) => api.getProjectState(id).catch(() => null)),
      );
      if (cancelled) return;
      setPrdGeneratedCount(states.filter((s) => !!s && !!s.generated_prd?.trim()).length);
      setPrdCountLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [projectIdsKey]);

  // ---- KPI cards -------------------------------------------------------------
  const kpis = useMemo(() => {
    const inReview = projects.filter((p) => {
      const s = normalizeStatus(p.status);
      return s === 'in_review_hpo' || s === 'in_review_po';
    }).length;
    const approved = projects.filter((p) => normalizeStatus(p.status) === 'approved').length;
    return [
      { icon: LayoutGrid, value: String(projects.length), label: 'All projects' },
      { icon: FileText, value: prdCountLoaded ? String(prdGeneratedCount) : '…', label: 'PRDs generated' },
      { icon: AlertTriangle, value: String(inReview), label: 'Pending in review' },
      { icon: CheckCircle2, value: String(approved), label: 'Approved' },
    ];
  }, [projects, prdGeneratedCount, prdCountLoaded]);

  // ---- Filter + sort pipeline -------------------------------------------------
  const visibleRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = projects.filter((p) => {
      if (q && !p.name.toLowerCase().includes(q) && !(p.description ?? '').toLowerCase().includes(q)) return false;
      if (statusFilter !== 'all' && normalizeStatus(p.status) !== statusFilter) return false;
      if (activeTab === 'flagged' && !p.is_flagged) return false;
      if (activeTab !== 'all' && activeTab !== 'flagged' && normalizeStatus(p.status) !== activeTab) return false;
      return true;
    });
    return [...rows].sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      const ta = new Date(a.updated_at ?? 0).getTime();
      const tb = new Date(b.updated_at ?? 0).getTime();
      return tb - ta;
    });
  }, [projects, query, statusFilter, activeTab, sortKey]);

  // ---- Pagination (10 per page) ---------------------------------------------
  // `safePage` clamps the raw page state to the last valid page so the slice is
  // never out of range; the effects below reset to page 1 when the filter/sort
  // inputs change and re-clamp when the list shrinks (e.g. a project is deleted).
  const [page, setPage] = useState<number>(0);
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageRows = useMemo(
    () => visibleRows.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE),
    [visibleRows, safePage],
  );

  useEffect(() => {
    setPage(0);
  }, [query, statusFilter, activeTab, sortKey]);

  useEffect(() => {
    setPage((cur) => Math.min(cur, totalPages - 1));
  }, [totalPages]);

  // Open a project from the table: select it and jump back into the workspace.
  // PROJECT 2.1 — Dashboard row open: same selection trigger as the sidebar
  //              (setProjectId → useProjectSync effect → PROJECT 2.2).
  const handleOpenProject = (id: string) => {
    setProjectId(id);
    setActiveView('workspace');
  };

  // ---- Per-row status menu (user-editable workflow status) -------------------
  // PROJECT 7.5.1 / 7.4.1 — Per-row metadata menu (UI triggers): the status
  // dropdown calls handleUpdateProjectStatus (7.5.1 → api 7.5.2 → route 7.5.3)
  // and the ★ button calls handleToggleFlag (7.4.1 → api 7.4.2 → route 7.4.3).
  const [statusMenuFor, setStatusMenuFor] = useState<string | null>(null);

  useEffect(() => {
    if (!statusMenuFor) return;
    const handlePointer = (e: MouseEvent) => {
      const target = e.target;
      if (target instanceof Element && target.closest('[data-status-menu]')) return;
      setStatusMenuFor(null);
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setStatusMenuFor(null);
    };
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [statusMenuFor]);

  return (
    <section className="flex-1 min-w-0 min-h-0 flex flex-col bg-background overflow-hidden">
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div id="projects-dashboard-content" className="w-full max-w-5xl mx-auto px-4 sm:px-6 md:px-10 py-7">
          <h1 className="text-[24px] font-bold text-on-surface mb-6">Dashboard</h1>

          {/* TOP SEARCH AND FILTERS */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <div className="flex-1 min-w-[220px] flex items-center gap-2.5 bg-surface border border-outline rounded-[10px] px-4 h-11 focus-within:border-primary/50 transition-colors">
              <Search className="w-4 h-4 text-on-surface-variant shrink-0" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setQuery('');
                }}
                placeholder="Search projects or document hash..."
                className="flex-1 bg-transparent text-[14px] text-on-surface placeholder:text-on-surface-variant focus:outline-none min-w-0"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
                  aria-label="Clear search"
                >
                  <XCircle className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <Dropdown<'all' | ProjectStatus>
              ariaLabel="Filter by status"
              value={statusFilter}
              onChange={setStatusFilter}
              options={[{ value: 'all' as const, label: 'All statuses' }, ...STATUS_OPTIONS]}
            />
            <Dropdown<SortKey>
              ariaLabel="Sort projects"
              value={sortKey}
              onChange={setSortKey}
              options={[
                { value: 'updated' as const, label: 'Sort by: Updated' },
                { value: 'name' as const, label: 'Sort by: Name' },
              ]}
            />
          </div>

          {/* KPI METRICS GRID */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8">
            {kpis.map(({ icon: Icon, value, label }) => (
              <div
                key={label}
                className="bg-surface border border-outline rounded-xl p-4 sm:p-5 flex flex-col items-start min-w-0"
              >
                <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center mb-3 sm:mb-4">
                  <Icon className="w-4.5 h-4.5" />
                </div>
                <div className="text-[24px] sm:text-[28px] font-bold leading-tight text-on-surface">{value}</div>
                <div className="text-[13px] text-on-surface-variant mt-1 leading-snug">{label}</div>
              </div>
            ))}
          </div>

          {/* PROJECTS TABLE CONTAINER */}
          <div className="bg-surface border border-outline rounded-xl overflow-hidden">
            {/* HEADER TABS */}
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b border-outline">
              <span className="text-[15px] font-bold text-on-surface mr-2">Projects</span>
              <div className="flex flex-wrap items-center gap-0.5 bg-black/5 rounded-lg p-1">
                {TABLE_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setActiveTab(tab.key)}
                    className={`px-3 py-1.5 rounded-md text-[12.5px] font-semibold transition-all whitespace-nowrap ${
                      activeTab === tab.key
                        ? 'bg-surface text-on-surface shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* TABLE CONTENT — md and up: the table scrolls horizontally inside
                this container only, never the page. Below md the same rows are
                rendered as stacked cards (see below) so no control is clipped. */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr>
                    <th className="w-12 px-5 py-3 text-[12px] font-semibold text-on-surface-variant border-b border-outline">
                      <Star className="w-3.5 h-3.5" aria-label="Flagged" />
                    </th>
                    <th className="px-5 py-3 text-[12px] font-semibold text-on-surface-variant border-b border-outline">
                      <span className="inline-flex items-center gap-1">Project <ArrowUpDown className="w-3 h-3" /></span>
                    </th>
                    <th className="px-5 py-3 text-[12px] font-semibold text-on-surface-variant border-b border-outline">
                      <span className="inline-flex items-center gap-1">Status (User editable) <ArrowUpDown className="w-3 h-3" /></span>
                    </th>
                    <th className="px-5 py-3 text-[12px] font-semibold text-on-surface-variant border-b border-outline">
                      <span className="inline-flex items-center gap-1">Updated <ArrowUpDown className="w-3 h-3" /></span>
                    </th>
                    <th className="px-5 py-3 border-b border-outline" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((p) => {
                    const status = normalizeStatus(p.status);
                    return (
                      <tr
                        key={p.id}
                        className={`transition-colors hover:bg-black/[0.02] ${p.id === projectId ? 'bg-primary/[0.04]' : ''}`}
                      >
                        <td className="px-5 py-4 border-b border-outline">
                          <Tooltip label={p.is_flagged ? 'Unflag' : 'Flag'}>
                            <button
                              type="button"
                              onClick={() => handleToggleFlag(p.id)}
                              aria-label={p.is_flagged ? 'Unflag project' : 'Flag project'}
                              className={`transition-colors ${p.is_flagged ? 'text-amber-500' : 'text-slate-300 hover:text-amber-500'}`}
                            >
                              <Star className="w-4 h-4" fill={p.is_flagged ? 'currentColor' : 'none'} />
                            </button>
                          </Tooltip>
                        </td>
                        <td className="px-5 py-4 border-b border-outline max-w-[280px]">
                          <span className="font-bold text-[14px] text-on-surface block truncate" title={p.name}>
                            {p.name}
                          </span>
                        </td>
                        <td className="px-5 py-4 border-b border-outline">
                          <div className="relative" data-status-menu>
                            <button
                              type="button"
                              onClick={() => setStatusMenuFor((cur) => (cur === p.id ? null : p.id))}
                              aria-label={`Change status for ${p.name}`}
                              aria-expanded={statusMenuFor === p.id}
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] font-semibold transition-all hover:brightness-95 ${STATUS_BADGE[status]}`}
                            >
                              {STATUS_LABEL[status]}
                              <ChevronDown className="w-3 h-3" />
                            </button>
                            {statusMenuFor === p.id && (
                              <div className="absolute left-0 top-full mt-1.5 z-30 min-w-[180px] bg-surface border border-outline rounded-xl shadow-lg py-1">
                                {STATUS_OPTIONS.map((o) => (
                                  <button
                                    key={o.value}
                                    type="button"
                                    onClick={() => {
                                      setStatusMenuFor(null);
                                      if (o.value !== status) handleUpdateProjectStatus(p.id, o.value);
                                    }}
                                    className={`w-full text-left px-3.5 py-2 text-[13px] transition-colors flex items-center justify-between gap-3 ${
                                      o.value === status
                                        ? 'text-primary font-semibold bg-primary/5'
                                        : 'text-on-surface hover:bg-black/5'
                                    }`}
                                  >
                                    <span>{o.label}</span>
                                    {o.value === status && <Check className="w-3.5 h-3.5 shrink-0" />}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-5 py-4 border-b border-outline">
                          <span className="text-[13px] text-on-surface-variant whitespace-nowrap">
                            {formatRelativeUpdated(p.updated_at)}
                          </span>
                        </td>
                        <td className="px-5 py-4 border-b border-outline text-right">
                          <button
                            type="button"
                            onClick={() => handleOpenProject(p.id)}
                            className="inline-flex items-center gap-1 bg-surface border border-outline rounded-lg px-3.5 py-1.5 text-[13px] font-semibold text-on-surface hover:bg-black/5 transition-colors whitespace-nowrap"
                          >
                            Open
                            <ChevronRight className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* MOBILE PROJECT CARDS (< md): identical data to the table, stacked
                vertically so the flag, status, updated, and Open controls all
                remain reachable without horizontal scrolling. */}
            <div className="md:hidden divide-y divide-outline">
              {pageRows.map((p) => {
                const status = normalizeStatus(p.status);
                return (
                  <div key={p.id} className={`p-4 ${p.id === projectId ? 'bg-primary/[0.04]' : ''}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5 min-w-0">
                        <Tooltip label={p.is_flagged ? 'Unflag' : 'Flag'}>
                          <button
                            type="button"
                            onClick={() => handleToggleFlag(p.id)}
                            aria-label={p.is_flagged ? 'Unflag project' : 'Flag project'}
                            className={`mt-0.5 transition-colors ${p.is_flagged ? 'text-amber-500' : 'text-slate-300 hover:text-amber-500'}`}
                          >
                            <Star className="w-4 h-4" fill={p.is_flagged ? 'currentColor' : 'none'} />
                          </button>
                        </Tooltip>
                        <div className="min-w-0">
                          <span className="font-bold text-[14px] text-on-surface block break-words">{p.name}</span>
                          <span className="text-[12px] text-on-surface-variant">
                            {formatRelativeUpdated(p.updated_at)}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleOpenProject(p.id)}
                        className="shrink-0 inline-flex items-center gap-1 bg-surface border border-outline rounded-lg px-3 py-1.5 text-[12px] font-semibold text-on-surface hover:bg-black/5 transition-colors whitespace-nowrap"
                      >
                        Open
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                    <div className="relative mt-3 inline-block max-w-full" data-status-menu>
                      <button
                        type="button"
                        onClick={() => setStatusMenuFor((cur) => (cur === p.id ? null : p.id))}
                        aria-label={`Change status for ${p.name}`}
                        aria-expanded={statusMenuFor === p.id}
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] font-semibold transition-all hover:brightness-95 max-w-full ${STATUS_BADGE[status]}`}
                      >
                        <span className="truncate">{STATUS_LABEL[status]}</span>
                        <ChevronDown className="w-3 h-3 shrink-0" />
                      </button>
                      {statusMenuFor === p.id && (
                        <div className="absolute left-0 top-full mt-1.5 z-30 min-w-[180px] bg-surface border border-outline rounded-xl shadow-lg py-1">
                          {STATUS_OPTIONS.map((o) => (
                            <button
                              key={o.value}
                              type="button"
                              onClick={() => {
                                setStatusMenuFor(null);
                                if (o.value !== status) handleUpdateProjectStatus(p.id, o.value);
                              }}
                              className={`w-full text-left px-3.5 py-2 text-[13px] transition-colors flex items-center justify-between gap-3 ${
                                o.value === status
                                  ? 'text-primary font-semibold bg-primary/5'
                                  : 'text-on-surface hover:bg-black/5'
                              }`}
                            >
                              <span>{o.label}</span>
                              {o.value === status && <Check className="w-3.5 h-3.5 shrink-0" />}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {visibleRows.length === 0 && (
              <div className="px-5 py-12 text-center text-[13px] text-on-surface-variant">
                {projects.length === 0
                  ? 'No projects yet — create one from the sidebar to see it here.'
                  : 'No projects match the current filters.'}
              </div>
            )}

            {visibleRows.length > 0 && (
              <PaginationControls totalRows={visibleRows.length} page={safePage} onPageChange={setPage} />
            )}
          </div>

        </div>
      </div>
    </section>
  );
}



