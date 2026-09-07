import Dashboard from './components/Dashboard';
import { ToastHost } from './components/Toast';

export default function App() {
  return (
    <div id="app-container" className="w-full h-screen bg-background flex flex-col font-sans text-on-surface antialiased overflow-hidden">
      
      {/* Centralized error/warning/system toasts (covers Dashboard & ConfirmationPanel) */}
      <ToastHost />
      
      {/* GLOBAL TOP NAVBAR */}
      <header className="h-16 w-full shrink-0 flex items-center justify-between gap-2 px-4 sm:px-6 bg-surface border-b border-outline z-50">
        {/* Left: Branding & workspace title (same "Ai" mark as the sidebar) */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center text-on-primary text-[11px] font-bold shrink-0 shadow-sm">
            Ai
          </div>
          <div className="hidden sm:flex items-baseline gap-2.5 min-w-0">
            <h1 className="font-bold text-sm text-on-surface truncate">Agentic-AI</h1>
            <span className="text-xs text-on-surface-variant whitespace-nowrap">Requirements Workspace</span>
          </div>
        </div>
        
        </header>

      {/* MAIN CONTAINER FRAME */}
      <div className="flex-1 flex overflow-hidden">
        <Dashboard />
      </div>
    </div>
  );
}