import { useState, useEffect } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { UploadCloud, History, PieChart, Database, PenTool, Layers, Sun, Moon, Menu } from 'lucide-react';

export default function Layout() {
  const [isDark, setIsDark] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true); // État de la barre latérale

  useEffect(() => {
    if (isDark) document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  }, [isDark]);

  const menu = [
    { path: '/', icon: <UploadCloud size={22} />, label: 'Déposer' },
    { path: '/history', icon: <History size={22} />, label: 'Historique' },
    { path: '/database', icon: <Database size={22} />, label: 'Base de données' },
    { path: '/analyses', icon: <PieChart size={22} />, label: 'Analyses' },
    { path: '/manual', icon: <PenTool size={22} />, label: 'Saisie manuelle' },
  ];

  return (
    <div className="flex h-screen bg-lightBg dark:bg-darkBg transition-colors duration-300 overflow-hidden">
      
      {/* Barre Latérale */}
      <aside className={`${isSidebarOpen ? 'w-64' : 'w-20'} flex flex-col border-r border-violet-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 backdrop-blur-xl transition-all duration-300 z-20`}>
        <div className="h-16 flex items-center justify-center border-b border-violet-200 dark:border-slate-800">
          <Layers className="text-primaryLight dark:text-primaryDark" size={28} />
          {isSidebarOpen && <span className="ml-3 font-bold text-xl text-violet-900 dark:text-white whitespace-nowrap overflow-hidden">DocCore</span>}
        </div>
        
        <nav className="flex-1 py-6 flex flex-col gap-2 px-3">
          {menu.map((item) => (
            <NavLink key={item.path} to={item.path} className={({ isActive }) =>
                `flex items-center ${isSidebarOpen ? 'justify-start px-4' : 'justify-center'} gap-4 py-3 rounded-lg transition-all ${
                  isActive 
                    ? 'bg-violet-100 text-primaryLight dark:bg-blue-900/30 dark:text-cyan-400 font-semibold' 
                    : 'text-slate-500 hover:bg-violet-50 dark:hover:bg-slate-800'
                }`
              }>
              {item.icon} 
              {isSidebarOpen && <span className="whitespace-nowrap">{item.label}</span>}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Topbar avec les boutons de contrôle */}
        <header className="h-16 flex justify-between items-center px-6 border-b border-violet-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/50 backdrop-blur-md">
          <div className="flex items-center gap-4">
            {/* Le bouton demandé pour glisser la barre latérale */}
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
              className="p-2 rounded-lg bg-violet-100 text-primaryLight hover:bg-violet-200 dark:bg-slate-800 dark:text-cyan-400 dark:hover:bg-slate-700 transition"
              title="Réduire/Agrandir le menu"
            >
              <Menu size={20} />
            </button>
            <h2 className="font-semibold text-violet-900 dark:text-slate-200 hidden sm:block">Espace de travail</h2>
          </div>
          
          <button onClick={() => setIsDark(!isDark)} className="p-2 rounded-full hover:bg-violet-100 text-violet-600 dark:hover:bg-slate-800 dark:text-slate-400 transition">
            {isDark ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </header>

        <div className="flex-1 overflow-auto p-4 lg:p-8">
          <Outlet /> 
        </div>
      </main>
    </div>
  );
}