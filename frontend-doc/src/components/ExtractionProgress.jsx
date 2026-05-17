import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock } from 'lucide-react';

export default function ExtractionProgress({ taskId, onComplete, onError }) {
  const [step, setStep] = useState({
    step: 'upload',
    message: 'Demarrage de l\'extraction...',
    progress: 0,
    elapsed: 0
  });
  const [done, setDone] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!taskId) return;

    const eventSource = new EventSource(`http://localhost:8000/upload/logs/${taskId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.error) {
          setStep({ ...data, hasError: true });
          setHasError(true);
          onError?.(data.error);
          eventSource.close();
          return;
        }

        setStep(data);

        if (data.step === 'done') {
          setDone(true);
          setTimeout(() => onComplete?.(data.result || data), 2000);
          eventSource.close();
        }

        if (data.step === 'error') {
          setHasError(true);
          onError?.(data.message || 'Erreur inconnue');
          eventSource.close();
        }
      } catch {
        // Ignorer les heartbeats
      }
    };

    eventSource.onerror = () => {};
    return () => eventSource.close();
  }, [taskId, onComplete, onError]);

  const fillPercent = step.progress / 100;
  const color = '#06b6d4';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-50/90 dark:bg-slate-950/90 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-6 animate-fade-in max-w-md w-full px-6">
        
        {/* Icone */}
        <div className="relative" style={{ animation: done ? 'none' : 'float 2.5s ease-in-out infinite' }}>
          {done ? (
            <div className="w-32 h-32 rounded-full bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center">
              <CheckCircle size={56} className="text-emerald-500" />
            </div>
          ) : hasError ? (
            <div className="w-32 h-32 rounded-full bg-red-100 dark:bg-red-500/20 flex items-center justify-center">
              <XCircle size={56} className="text-red-500" />
            </div>
          ) : (
            <svg width="120" height="140" viewBox="0 0 120 140" fill="none">
              <defs>
                <linearGradient id="fillGrad" x1="0" y1="1" x2="0" y2="0">
                  <stop offset="0%" stopColor={color} stopOpacity="0.2" />
                  <stop offset="100%" stopColor={color} stopOpacity="0.5" />
                </linearGradient>
                <clipPath id="docFill">
                  <path d="M18 10h50l28 28v84a4 4 0 01-4 4H18a4 4 0 01-4-4V14a4 4 0 014-4z"/>
                </clipPath>
                <filter id="glow">
                  <feGaussianBlur stdDeviation="8" result="blur" />
                  <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
              </defs>

              {/* Glow */}
              <path d="M18 10h50l28 28v84a4 4 0 01-4 4H18a4 4 0 01-4-4V14a4 4 0 014-4z" 
                    fill={color} fillOpacity="0.08" filter="url(#glow)"/>

              {/* Document */}
              <path d="M18 10h50l28 28v84a4 4 0 01-4 4H18a4 4 0 01-4-4V14a4 4 0 014-4z" 
                    fill="white" stroke={color} strokeWidth="2" className="dark:fill-slate-900"/>

              {/* Remplissage */}
              <rect x="14" y={126 - (102 * fillPercent)} width="92" height={102 * fillPercent}
                    fill="url(#fillGrad)" clipPath="url(#docFill)"
                    style={{ transition: 'all 0.8s ease-out' }}/>

              {/* Vague */}
              {fillPercent > 0.05 && fillPercent < 0.95 && (
                <g clipPath="url(#docFill)">
                  <path fill={color} fillOpacity="0.35">
                    <animate attributeName="d" dur="1.5s" repeatCount="indefinite"
                      values={`M14 ${126-(102*fillPercent)} Q40 ${122-(102*fillPercent)} 60 ${126-(102*fillPercent)} Q80 ${130-(102*fillPercent)} 106 ${126-(102*fillPercent)} L106 ${130-(102*fillPercent)} Q80 ${134-(102*fillPercent)} 60 ${130-(102*fillPercent)} Q40 ${126-(102*fillPercent)} 14 ${130-(102*fillPercent)} Z;M14 ${126-(102*fillPercent)} Q40 ${130-(102*fillPercent)} 60 ${126-(102*fillPercent)} Q80 ${122-(102*fillPercent)} 106 ${126-(102*fillPercent)} L106 ${130-(102*fillPercent)} Q80 ${126-(102*fillPercent)} 60 ${130-(102*fillPercent)} Q40 ${134-(102*fillPercent)} 14 ${130-(102*fillPercent)} Z;M14 ${126-(102*fillPercent)} Q40 ${122-(102*fillPercent)} 60 ${126-(102*fillPercent)} Q80 ${130-(102*fillPercent)} 106 ${126-(102*fillPercent)} L106 ${130-(102*fillPercent)} Q80 ${134-(102*fillPercent)} 60 ${130-(102*fillPercent)} Q40 ${126-(102*fillPercent)} 14 ${130-(102*fillPercent)} Z`}/>
                  </path>
                </g>
              )}

              {/* Pli */}
              <path d="M68 10v23a5 5 0 005 5h23" fill="white" stroke={color} strokeWidth="2" className="dark:fill-slate-900"/>
              <path d="M68 10l28 28H73a5 5 0 01-5-5V10z" fill={color} fillOpacity="0.15"/>

              {/* Texte */}
              <rect x="28" y="58" width="44" height="5" rx="2.5" fill={color} fillOpacity="0.4"/>
              <rect x="28" y="70" width="60" height="5" rx="2.5" fill={color} fillOpacity="0.3"/>
              <rect x="28" y="82" width="50" height="5" rx="2.5" fill={color} fillOpacity="0.2"/>
              <rect x="28" y="94" width="35" height="5" rx="2.5" fill={color} fillOpacity="0.15"/>
              <rect x="28" y="106" width="25" height="5" rx="2.5" fill={color} fillOpacity="0.1"/>

              {/* Pourcentage */}
              <text x="60" y="128" textAnchor="middle" fill={color} fontSize="12" fontWeight="700"
                    fontFamily="JetBrains Mono, monospace" opacity="0.8">{step.progress}%</text>
            </svg>
          )}
        </div>

        {/* Message principal */}
        <div className="text-center">
          <p className={`font-display font-bold text-xl mb-2 ${
            done ? 'text-emerald-600 dark:text-emerald-400' : 
            hasError ? 'text-red-600 dark:text-red-400' : 
            'text-slate-800 dark:text-white'
          }`}>
            {done ? 'Extraction terminee !' : 
             hasError ? 'Erreur' : 
             'Extraction en cours'}
          </p>
          <p className={`text-sm ${
            done ? 'text-emerald-500 dark:text-emerald-400' : 
            hasError ? 'text-red-500 dark:text-red-400' : 
            'text-slate-500 dark:text-slate-400'
          }`}>
            {step.message}
          </p>
        </div>

        {/* Timer */}
        {step.elapsed > 0 && !done && !hasError && (
          <div className="flex items-center gap-2 text-slate-400 dark:text-slate-500">
            <Clock size={14} />
            <span className="font-mono text-sm">{step.elapsed}s</span>
          </div>
        )}

        {/* Barre de progression */}
        <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700 ease-out"
               style={{ width: `${step.progress}%`, background: `linear-gradient(90deg, ${color}, ${color}cc)` }}/>
        </div>

        {/* Stats finales */}
        {done && step.item_count > 0 && (
          <div className="grid grid-cols-2 gap-3 w-full">
            <div className="bg-slate-100 dark:bg-slate-800 rounded-xl p-3 text-center">
              <p className="text-xs text-slate-500">Articles</p>
              <p className="font-bold text-lg text-slate-800 dark:text-white">{step.item_count}</p>
            </div>
            <div className="bg-slate-100 dark:bg-slate-800 rounded-xl p-3 text-center">
              <p className="text-xs text-slate-500">Temps total</p>
              <p className="font-bold text-lg text-slate-800 dark:text-white">{step.elapsed}s</p>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50%      { transform: translateY(-12px); }
        }
      `}</style>
    </div>
  );
}