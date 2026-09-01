// PRDEditor — PRD Document tab extracted from the former Dashboard.tsx.
// Renders the compiled PRD as editable markdown sections with lock/unlock and
// inline section editing.
import { FileText, Pencil, Save, Lock, Unlock } from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';
import { getSafeSectionTitle, getSafeSectionContent } from '../utils/markdown';
import { parseAndRenderMarkdown } from './MarkdownRenderer';

export function PRDEditor({ state }: { state: ProjectState }) {
  const {
    prdMarkdown,
    sections,
    editingSectionId,
    setEditingSectionId,
    editBuffer,
    setEditBuffer,
    handleSaveSection,
    structuredRequirements,
    lockedRequirements,
    handleLockRequirement,
    handleUnlockRequirement,
  } = state;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Styled markdown content rendering */}
      <article className="bg-white p-6 md:p-10 rounded-3xl border border-outline shadow-sm prose prose-neutral max-w-none">
        
        {/* Header decorative accent */}
        <div className="h-1 w-24 bg-primary mb-6 rounded-full no-print"></div>
        
        {!prdMarkdown ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-on-surface-variant no-print">
            <FileText className="w-12 h-12 text-primary/40 mb-4 animate-pulse" />
            <p className="font-bold text-lg text-on-surface">PRD template not loaded yet</p>
            <p className="text-xs max-w-sm mt-1">The Krungsri Nimble template could not be fetched. Enter your raw requirements in the chat or click Generate PRD to build the document.</p>
          </div>
        ) : (
          <div className="space-y-10 divide-y divide-slate-100">
            {sections.map((section, sectionIdx) => {
              const isEditing = editingSectionId === section.id;
              const safeTitle = getSafeSectionTitle(section.title);
              const safeContent = getSafeSectionContent(section.content);
              
              return (
                <div 
                  key={section.id} 
                  className={`relative group pt-8 first:pt-0 transition-all duration-200 ${
                    isEditing 
                      ? 'bg-slate-50/50 p-6 rounded-2xl border border-primary/20 shadow-sm' 
                      : 'border-transparent hover:bg-slate-50/20 px-2 rounded-2xl'
                  }`}
                >
                  {/* Header Area with Title & Edit button */}
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 mb-5">
                    <h3 className="text-xs font-bold font-mono text-primary uppercase tracking-wider flex items-center gap-2">
                      <span className="opacity-40 font-semibold text-[10px]">#0{sectionIdx + 1}</span>
                      <span>{safeTitle}</span>
                    </h3>
                    
                    <div className="flex items-center gap-2">
                      {/* Lock/Unlock button for this section */}
                      {section.id === 'user_stories' && structuredRequirements.requirements && structuredRequirements.requirements.length > 0 && (
                        <button
                          onClick={() => {
                            const req = structuredRequirements.requirements![0];
                            const isLocked = req.is_locked || lockedRequirements[req.requirement_code]?.is_locked;
                            if (isLocked) {
                              handleUnlockRequirement(req.requirement_code);
                            } else {
                              handleLockRequirement(req.requirement_code);
                            }
                          }}
                          className={`opacity-60 hover:opacity-100 group-hover:opacity-100 transition-opacity text-[11px] px-2.5 py-1.5 rounded-xl flex items-center gap-1.5 border shadow-sm cursor-pointer z-10 font-semibold ${
                            (structuredRequirements.requirements![0].is_locked || lockedRequirements[structuredRequirements.requirements![0].requirement_code]?.is_locked)
                              ? 'bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200'
                              : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                          }`}
                        >
                          {(structuredRequirements.requirements![0].is_locked || lockedRequirements[structuredRequirements.requirements![0].requirement_code]?.is_locked) ? (
                            <>
                              <Unlock className="w-3.5 h-3.5 text-amber-700" />
                              <span>Unlock</span>
                            </>
                          ) : (
                            <>
                              <Lock className="w-3.5 h-3.5 text-primary" />
                              <span>Lock</span>
                            </>
                          )}
                        </button>
                      )}
                      
                      {!isEditing && (
                        <button
                          onClick={() => {
                            setEditingSectionId(section.id);
                            setEditBuffer(safeContent);
                          }}
                          disabled={section.id === 'user_stories' && structuredRequirements.requirements && structuredRequirements.requirements.length > 0 && (structuredRequirements.requirements[0].is_locked || lockedRequirements[structuredRequirements.requirements[0].requirement_code]?.is_locked)}
                          className={`opacity-60 hover:opacity-100 group-hover:opacity-100 transition-opacity bg-white hover:bg-slate-50 text-slate-700 text-[11px] px-2.5 py-1.5 rounded-xl flex items-center gap-1.5 border border-slate-200 shadow-sm cursor-pointer z-10 font-semibold disabled:opacity-30 disabled:cursor-not-allowed`}
                        >
                          <Pencil className="w-3.5 h-3.5 text-primary" />
                          <span>Edit</span>
                        </button>
                      )}
                    </div>
                  </div>
{isEditing ? (
                    <div className="space-y-4">
                      <textarea
                        ref={(el) => {
                          if (el) {
                            el.style.height = 'auto';
                            el.style.height = `${el.scrollHeight}px`;
                          }
                        }}
                        value={editBuffer}
                        onChange={(e) => {
                          setEditBuffer(e.target.value);
                          e.target.style.height = 'auto';
                          e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        className="w-full text-sm font-sans text-slate-800 bg-white border border-slate-200 rounded-2xl p-4.5 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all resize-y custom-scrollbar shadow-inner min-h-[120px]"
                        placeholder="Enter section content in markdown..."
                      />
                      <div className="flex items-center justify-between pt-3 border-t border-slate-100 mt-2">
                        <p className="text-[11px] text-slate-500 italic">
                          Changes save instantly to RequirementState.
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => {
                              setEditingSectionId(null);
                              setEditBuffer("");
                            }}
                            className="px-3.5 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-sm transition-all cursor-pointer"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveSection(section.id, editBuffer)}
                            className="px-4 py-1.5 rounded-xl bg-primary text-on-primary hover:brightness-110 text-xs font-semibold shadow-md transition-all flex items-center gap-1.5 cursor-pointer"
                          >
                            <Save className="w-3.5 h-3.5" />
                            <span>Save Changes</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="prose prose-slate max-w-none pb-4">
                      {parseAndRenderMarkdown(safeContent)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </article>
    </div>
  );
}