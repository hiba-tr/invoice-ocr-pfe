import { useApp } from '../context/AppContext';
import { Loader2 } from 'lucide-react';

export default function Spinner() {
  const { loading } = useApp();

  if (!loading) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-3">
        <Loader2 size={48} className="text-primary-light dark:text-primary-dark animate-spin" />
        <p className="text-sm font-mono text-slate-500 dark:text-slate-400">Chargement...</p>
      </div>
    </div>
  );
}