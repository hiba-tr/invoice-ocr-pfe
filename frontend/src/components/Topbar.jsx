import { Sun, Moon, ChevronLeft, ChevronRight } from 'lucide-react';
import { useApp } from '../context/AppContext';

export default function Topbar({ collapsed, onToggle }) {
  const { darkMode, toggleDarkMode } = useApp();

  return (
    <header className="h-16 glass border-b border-white/20 dark:border-slate-700/30 flex items-center justify-between px-4 lg:px-6 flex-shrink-0 relative z-10">
      <div className="flex items-center gap-3">
        {/* Bouton de glissement - visible sur tous les écrans */}
        <button 
          onClick={onToggle} 
          className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-all duration-200 group"
          title={collapsed ? "Ouvrir le menu" : "Réduire le menu"}
        >
          {collapsed ? (
            <ChevronRight size={20} className="text-slate-500 dark:text-slate-400 group-hover:text-primary-light dark:group-hover:text-primary-dark transition-colors" />
          ) : (
            <ChevronLeft size={20} className="text-slate-500 dark:text-slate-400 group-hover:text-primary-light dark:group-hover:text-primary-dark transition-colors" />
          )}
        </button>
        
        <h2 className="font-display font-semibold text-slate-700 dark:text-slate-200 hidden sm:block">
          Espace de travail
        </h2>
      </div>

      <div className="flex items-center gap-3">
       

        {/* Dark mode toggle */}
        <button
          onClick={toggleDarkMode}
          className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-all duration-200"
          title={darkMode ? "Mode clair" : "Mode sombre"}
        >
          {darkMode ? (
            <Sun size={20} className="text-amber-400 hover:rotate-90 transition-transform duration-500" />
          ) : (
            <Moon size={20} className="text-slate-500 hover:-rotate-12 transition-transform duration-500" />
          )}
        </button>
      </div>
    </header>
  );
}