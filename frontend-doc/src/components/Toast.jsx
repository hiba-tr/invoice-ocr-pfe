import { useApp } from '../context/AppContext';
import { X, CheckCircle, AlertTriangle, AlertCircle } from 'lucide-react';

const iconMap = {
  success: CheckCircle,
  warning: AlertTriangle,
  danger: AlertCircle,
  info: AlertCircle,
};

const colorMap = {
  success: 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300',
  warning: 'border-amber-500 bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300',
  danger: 'border-red-500 bg-red-50 dark:bg-red-500/10 text-red-800 dark:text-red-300',
  info: 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 text-blue-800 dark:text-blue-300',
};

export default function Toast() {
  const { toasts, dismissToast } = useApp();

  if (!toasts?.length) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(toast => {
        const Icon = iconMap[toast.type] || AlertCircle;
        return (
          <div
            key={toast.id}
            className={`glass border-l-4 ${colorMap[toast.type]} rounded-xl p-4 flex items-start gap-3 animate-slide-up`}
            style={{ boxShadow: '0 16px 64px rgba(0, 0, 0, 0.15)' }}
          >
            <Icon size={20} className="flex-shrink-0 mt-0.5" />
            <p className="text-sm flex-1">{toast.message}</p>
            <button
              onClick={() => dismissToast(toast.id)}
              className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            >
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}