import { useEffect, useState } from 'react';
import { BookOpenCheck, CheckCircle2, FileUp, Loader2, ShieldCheck, X } from 'lucide-react';
import { api } from '../api/client';
import type { BankingKnowledgeDocumentPayload } from '../api/types';
import { handleError, notify } from './Toast';

interface BankingKnowledgeModalProps {
  open: boolean;
  onClose: () => void;
}

export function BankingKnowledgeModal({ open, onClose }: BankingKnowledgeModalProps) {
  const [documents, setDocuments] = useState<BankingKnowledgeDocumentPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [documentType, setDocumentType] = useState('best_practice');
  const [jurisdiction, setJurisdiction] = useState('global');
  const [tags, setTags] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      setDocuments(await api.listBankingKnowledge());
    } catch (error) {
      handleError('Could not load reusable banking knowledge.', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void load();
  }, [open]);

  if (!open) return null;

  const upload = async () => {
    if (!file || !title.trim()) return;
    setWorkingId('upload');
    try {
      const created = await api.uploadBankingKnowledge(file, {
        title: title.trim(),
        document_type: documentType.trim() || 'best_practice',
        jurisdiction: jurisdiction.trim() || 'global',
        tags,
      });
      setDocuments((current) => [created, ...current]);
      setFile(null);
      setTitle('');
      setTags('');
      notify('Banking knowledge uploaded as a draft. Approve it before audits can retrieve it.', 'success');
    } catch (error) {
      handleError('Could not upload the banking knowledge document.', error);
    } finally {
      setWorkingId(null);
    }
  };

  const changeStatus = async (document: BankingKnowledgeDocumentPayload, action: 'approve' | 'retire') => {
    setWorkingId(document.id);
    try {
      const updated = action === 'approve'
        ? await api.approveBankingKnowledge(document.id)
        : await api.retireBankingKnowledge(document.id);
      setDocuments((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify(action === 'approve' ? 'Knowledge approved for Banking RAG.' : 'Knowledge retired from Banking RAG.', 'success');
    } catch (error) {
      handleError(`Could not ${action} the banking knowledge document.`, error);
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-outline bg-surface shadow-xl">
        <div className="flex items-start justify-between border-b border-outline px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 font-bold text-on-surface"><BookOpenCheck className="h-4.5 w-4.5 text-primary" /> Banking Knowledge Base</h2>
            <p className="mt-1 text-xs text-on-surface-variant">Approved documents are reused across your projects and retrieved by relevance before audits.</p>
          </div>
          <button type="button" aria-label="Close banking knowledge" onClick={onClose}><X className="h-4 w-4" /></button>
        </div>

        <div className="overflow-y-auto p-5 space-y-5">
          <div className="rounded-xl border border-outline bg-slate-50 p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-bold text-on-surface"><FileUp className="h-4 w-4 text-primary" /> Add reusable guidance</div>
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Document title" maxLength={255} className="rounded-lg border border-outline bg-white p-2.5 text-sm" />
              <input value={documentType} onChange={(event) => setDocumentType(event.target.value)} placeholder="Type: policy, regulation, best_practice" className="rounded-lg border border-outline bg-white p-2.5 text-sm" />
              <input value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} placeholder="Jurisdiction: TH, global…" className="rounded-lg border border-outline bg-white p-2.5 text-sm" />
              <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Tags, comma separated" className="rounded-lg border border-outline bg-white p-2.5 text-sm" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <input
                type="file"
                accept=".pdf,.docx,.md,.txt"
                onChange={(event) => {
                  const next = event.target.files?.[0] ?? null;
                  setFile(next);
                  if (next && !title.trim()) setTitle(next.name.replace(/\.[^.]+$/, ''));
                }}
                className="max-w-full text-xs text-on-surface-variant"
              />
              <button type="button" disabled={!file || !title.trim() || workingId === 'upload'} onClick={() => void upload()} className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-bold text-on-primary disabled:opacity-50">
                {workingId === 'upload' && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Upload draft
              </button>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-bold text-on-surface">Reusable documents</h3>
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-sm text-on-surface-variant"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
            ) : documents.length === 0 ? (
              <p className="py-6 text-sm text-on-surface-variant">No reusable banking documents yet.</p>
            ) : (
              <div className="mt-2 space-y-2">
                {documents.map((document) => (
                  <div key={document.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-outline p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-on-surface">{document.title}</p>
                      <p className="mt-0.5 text-[11px] text-on-surface-variant">{document.document_type} · {document.jurisdiction} · v{document.version}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${document.status === 'approved' ? 'bg-emerald-50 text-emerald-700' : document.status === 'retired' ? 'bg-slate-100 text-slate-600' : 'bg-amber-50 text-amber-700'}`}>{document.status}</span>
                        {document.tags.map((tag) => <span key={tag} className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-700">{tag}</span>)}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {document.status !== 'approved' && (
                        <button type="button" disabled={workingId === document.id} onClick={() => void changeStatus(document, 'approve')} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 disabled:opacity-50"><CheckCircle2 className="h-3.5 w-3.5" /> Approve</button>
                      )}
                      {document.status === 'approved' && (
                        <button type="button" disabled={workingId === document.id} onClick={() => void changeStatus(document, 'retire')} className="inline-flex items-center gap-1 rounded-lg border border-outline px-2.5 py-1.5 text-xs font-semibold text-on-surface-variant disabled:opacity-50"><ShieldCheck className="h-3.5 w-3.5" /> Retire</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
