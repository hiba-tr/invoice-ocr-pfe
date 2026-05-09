import { NavLink } from 'react-router-dom';
import { 
  Upload, History, Database, PieChart, PenTool, Layers,

} from 'lucide-react';

const menuItems = [
  { path: '/', icon: Upload, label: 'Déposer' },
  { path: '/history', icon: History, label: 'Historique' },
  { path: '/database', icon: Database, label: 'Base de données' },
  { path: '/analyses', icon: PieChart, label: 'Analyses' },
  { path: '/manual', icon: PenTool, label: 'Saisie manuelle' },
];

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <>
      {/* Overlay pour mobile */}
      {!collapsed && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <aside 
        className={`
          fixed lg:relative z-30 h-screen flex flex-col transition-all duration-300 ease-out
          ${collapsed ? '-translate-x-full lg:translate-x-0 lg:w-20' : 'translate-x-0 w-64'}
        `}
      >
        {/* Glass background */}
        <div className="absolute inset-0 glass border-r border-white/20 dark:border-slate-700/30" />
        
        {/* Content */}
        <div className="relative flex flex-col h-full">
          {/* Logo */}
          <div className={`h-16 flex items-center border-b border-slate-200/50 dark:border-slate-700/30 px-4 ${collapsed ? 'justify-center lg:px-2' : 'px-6'}`}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-light to-blue-500 dark:from-cyan-400 dark:to-blue-500 flex items-center justify-center shadow-lg flex-shrink-0">
              <Layers className="text-white" size={22} />
            </div>
            {!collapsed && (
              <div className="ml-3 overflow-hidden">
                <h1 className="font-display font-bold text-lg text-slate-800 dark:text-white whitespace-nowrap">DocCore</h1>
                <p className="text-xs text-slate-400 dark:text-slate-500 whitespace-nowrap">Invoice Intelligence</p>
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 py-6 px-3 flex flex-col gap-1 overflow-y-auto">
            {menuItems.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? 'active' : ''} ${collapsed ? 'justify-center lg:px-2' : ''}`
                }
                title={collapsed ? item.label : undefined}
              >
                <item.icon size={20} className="flex-shrink-0" />
                {!collapsed && <span className="whitespace-nowrap">{item.label}</span>}
              </NavLink>
            ))}
          </nav>

          {/* Footer */}
          {!collapsed && (
            <div className="p-4 border-t border-slate-200/50 dark:border-slate-700/30">
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
                DocCore v1.0 · PFE 2025
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}