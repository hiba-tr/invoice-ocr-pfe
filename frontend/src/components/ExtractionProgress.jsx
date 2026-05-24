import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';

export default function ExtractionProgress({ onComplete, onError, message = 'Extraction en cours...' }) {
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [statusMessage, setStatusMessage] = useState(message);

  useEffect(() => {
    const startTime = Date.now();
    
    const timerInterval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 90) return prev;
        return prev + Math.random() * 8;
      });
    }, 600);
    
    return () => {
      clearInterval(timerInterval);
      clearInterval(progressInterval);
    };
  }, []);

  useEffect(() => {
    const handleComplete = (event) => {
      if (event.detail?.success) {
        setProgress(100);
        setIsComplete(true);
        setStatusMessage('Extraction terminée !');
        setTimeout(() => onComplete?.(event.detail.result), 500);
      } else if (event.detail?.error) {
        setHasError(true);
        setStatusMessage(event.detail.error);
        onError?.(event.detail.error);
      }
    };
    
    window.addEventListener('extraction-complete', handleComplete);
    window.addEventListener('extraction-error', handleComplete);
    
    return () => {
      window.removeEventListener('extraction-complete', handleComplete);
      window.removeEventListener('extraction-error', handleComplete);
    };
  }, [onComplete, onError]);

  const fillPercent = Math.min(progress / 100, 1);
  const color = '#06b6d4';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-50/90 dark:bg-slate-950/90 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-6 animate-fade-in max-w-md w-full px-6">
        
        <div className="relative" style={{ animation: isComplete ? 'none' : 'float 2.5s ease-in-out infinite' }}>
          {isComplete ? (
            <div className="w-32 h-32 rounded-full bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center">
              <CheckCircle size={56} className="text-emerald-500" />
            </div>
          ) : hasError ? (
            <div className="w-32 h-32 rounded-full bg-red-100 dark:bg-red-500/20 flex items-center justify-center">
              <XCircle size={56} className="text-red-500" />
            </div>
          ) : (
            <div className="w-32 h-32 rounded-full bg-cyan-100 dark:bg-cyan-500/20 flex items-center justify-center">
              <Loader2 size={48} className="text-cyan-500 animate-spin" />
            </div>
          )}
        </div>

        <div className="text-center">
          <p className={`font-display font-bold text-xl mb-2 ${
            isComplete ? 'text-emerald-600 dark:text-emerald-400' : 
            hasError ? 'text-red-600 dark:text-red-400' : 
            'text-slate-800 dark:text-white'
          }`}>
            {isComplete ? 'Extraction terminée !' : 
             hasError ? 'Erreur' : 
             'Extraction en cours'}
          </p>
          <p className={`text-sm ${
            isComplete ? 'text-emerald-500 dark:text-emerald-400' : 
            hasError ? 'text-red-500 dark:text-red-400' : 
            'text-slate-500 dark:text-slate-400'
          }`}>
            {statusMessage}
          </p>
        </div>

        {elapsed > 0 && !isComplete && !hasError && (
          <div className="flex items-center gap-2 text-slate-400 dark:text-slate-500">
            <Clock size={14} />
            <span className="font-mono text-sm">{elapsed}s</span>
          </div>
        )}

        <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
          <div 
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{ 
              width: `${fillPercent * 100}%`, 
              background: `linear-gradient(90deg, ${color}, ${color}cc)` 
            }}
          />
        </div>

        {!isComplete && !hasError && (
          <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
            Analyse du document et reconnaissance OCR en cours...
          </p>
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