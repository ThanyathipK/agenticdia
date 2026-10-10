import Dashboard from './components/Dashboard';
import { ToastHost } from './components/Toast';

export default function App() {
  return (
    <div id="app-container" className="w-full h-screen bg-background flex flex-col font-sans text-on-surface antialiased overflow-hidden">
      <ToastHost />
      <div className="flex-1 flex overflow-hidden">
        <Dashboard />
      </div>
    </div>
  );
}
