import { useState } from 'react';
import { ShieldCheck, Activity, Check, HelpCircle, Send } from 'lucide-react';
import { ClarificationQuestionRow } from '../../data';

interface AuditChecklistProps {
  questions: ClarificationQuestionRow[];
  setQuestions: React.Dispatch<React.SetStateAction<ClarificationQuestionRow[]>>;
  showToast: (message: string, type?: 'success' | 'info') => void;
}

/**
 * TAB: AUDIT INTEGRITY & COMPLIANCE
 * Renders the DDL rigor / index coverage compliance cards plus the interactive
 * stakeholder clarification resolver backed by the clarification_questions table.
 */
export default function AuditChecklist({ questions, setQuestions, showToast }: AuditChecklistProps) {
  // Inline Question answer helper
  const [resolvingQuestionId, setResolvingQuestionId] = useState<string | null>(null);
  const [answerInput, setAnswerInput] = useState<string>('');

  // Answer inline checklist clarification question
  const submitQuestionAnswer = (e: React.FormEvent, questionId: string) => {
    e.preventDefault();
    if (!answerInput.trim()) return;

    setQuestions(prev => prev.map(q => q.id === questionId ? { ...q, user_answer: answerInput.trim(), is_resolved: true } : q));
    setResolvingQuestionId(null);
    setAnswerInput('');
    showToast("Audit Clarification answer logged! Metric state updated.", "success");
  };

  return (
    <div className="space-y-6">
      
      {/* Compliance overview blocks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">PostgreSQL Structural Rigor</h4>
              <h3 className="text-sm font-bold text-slate-900 mt-0.5">Automated DDL Rule Checks</h3>
            </div>
          </div>
          
          <ul className="space-y-3.5 text-xs pt-2">
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">UUID v4 Primary Keys (gen_random_uuid())</span>
                <p className="text-slate-500 text-[11px] mt-0.5">Verified on all 9 tables. Eliminates centralized ID bottleneck sequence leaks.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">High-Precision Audit TIMESTAMPTZ Trails</span>
                <p className="text-slate-500 text-[11px] mt-0.5">Enforces localized time integrity on modified records across the financial network.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">Cascading Deletion Rules (CASCADE / RESTRICT)</span>
                <p className="text-slate-500 text-[11px] mt-0.5">RESTRICT prevents users or projects from deletion if they have active transaction logs.</p>
              </div>
            </li>
          </ul>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-navy-100 text-navy-600 flex items-center justify-center">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Index Coverage Performance</h4>
              <h3 className="text-sm font-bold text-slate-900 mt-0.5">Foreign Key Query Optimizers</h3>
            </div>
          </div>

          <ul className="space-y-3.5 text-xs pt-2">
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">Foreign Key Constraint Coverage</span>
                <p className="text-slate-500 text-[11px] mt-0.5">11 indexes explicitly generated on foreign keys to prevent full table scans during JOIN queries.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">Dashboard Metrics Optimization</span>
                <p className="text-slate-500 text-[11px] mt-0.5">Indices on columns `is_locked`, `role`, and `is_resolved` maximize throughput under heavy analytical query loads.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Check className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold text-slate-800">Double-Entry Ledger Architecture Check</span>
                <p className="text-slate-500 text-[11px] mt-0.5">Immutable snapshots logged as standard JSONB blocks ensure absolute audit compliance.</p>
              </div>
            </li>
          </ul>
        </div>
      </div>
      {/* Stakeholder Clarification Questions (interactive resolver) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-4.5 h-4.5 text-navy-600" />
            <h3 className="text-sm font-bold text-slate-900">Stakeholder Clarification & Compliance Dialogues</h3>
          </div>
          <span className="text-xs bg-slate-100 px-2 py-0.5 rounded font-mono font-bold text-slate-600">
            clarification_questions table
          </span>
        </div>
        <p className="text-xs text-slate-500 mb-6">
          Pending queries must be answered and resolved by Product Owners or compliance analysts before core systems are unlocked for production deployment.
        </p>

        <div className="space-y-4">
          {questions.map((q) => (
            <div key={q.id} className={`p-4 rounded-2xl border transition-all ${
              q.is_resolved 
                ? 'bg-slate-50/50 border-slate-200' 
                : 'bg-orange-50/30 border-orange-200'
            }`}>
              <div className="flex justify-between items-start gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${q.is_resolved ? 'bg-slate-400' : 'bg-orange-500 animate-pulse'}`}></span>
                    <span className="text-[10px] font-mono text-slate-400 font-bold uppercase">{q.checklist_category}</span>
                    <span className="text-slate-300">|</span>
                    <span className="text-[10px] font-mono text-slate-500">Story Target: {q.target_user_story_id ? 'US-PAY-002' : 'General'}</span>
                  </div>
                  <p className="text-xs font-semibold text-slate-800 leading-relaxed">
                    {q.question_text}
                  </p>
                </div>

                <span className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 uppercase tracking-wider ${
                  q.is_resolved 
                    ? 'bg-slate-200 text-slate-600' 
                    : 'bg-orange-100 text-orange-800'
                }`}>
                  {q.is_resolved ? 'Resolved' : 'Pending Action'}
                </span>
              </div>

              <div className="mt-3.5 border-t border-slate-100 pt-3 text-xs">
                {q.is_resolved ? (
                  <div className="bg-white p-3 rounded-xl border border-slate-200 text-slate-700">
                    <span className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Official Resolution Response</span>
                    {q.user_answer}
                  </div>
                ) : (
                  <div>
                    {resolvingQuestionId === q.id ? (
                      <form onSubmit={(e) => submitQuestionAnswer(e, q.id)} className="flex gap-2">
                        <input 
                          type="text" 
                          required
                          value={answerInput}
                          onChange={e => setAnswerInput(e.target.value)}
                          placeholder="Type official compliance solution..."
                          className="flex-1 bg-white border border-slate-300 rounded-xl px-3 py-1.5 text-xs focus:outline-none focus:border-navy-600"
                        />
                        <button 
                          type="submit"
                          className="px-3.5 bg-navy-600 hover:bg-navy-700 text-white rounded-xl font-bold flex items-center justify-center gap-1.5 transition-colors cursor-pointer text-xs"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>Resolve</span>
                        </button>
                      </form>
                    ) : (
                      <button 
                        onClick={() => {
                          setResolvingQuestionId(q.id);
                          setAnswerInput('');
                        }}
                        className="px-3 py-1 bg-orange-500 hover:bg-orange-600 text-slate-950 font-bold rounded-xl transition-colors text-[11px] cursor-pointer"
                      >
                        Answer and Lock Compliance
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}