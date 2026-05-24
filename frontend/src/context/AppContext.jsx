import { createContext, useContext, useState, useCallback, useEffect } from 'react';

const AppContext = createContext();

export function AppProvider({ children }) {
  const [darkMode, setDarkMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [concessionsList, setConcessionsList] = useState([]);
  const [currentConcessionId, setCurrentConcessionId] = useState(null);
  const [currentConcessionNom, setCurrentConcessionNom] = useState('');

  const toggleDarkMode = () => {
    setDarkMode(prev => {
      const newMode = !prev;
      document.documentElement.classList.toggle('dark', newMode);
      return newMode;
    });
  };

  const showSpinner = useCallback(() => setLoading(true), []);
  const hideSpinner = useCallback(() => setLoading(false), []);

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);



  return (
    <AppContext.Provider value={{
      darkMode,
      toggleDarkMode,
      loading,
      showSpinner,
      hideSpinner,
      toasts,
      showToast,
      dismissToast,
      concessionsList,
      setConcessionsList,
      currentConcessionId,
      setCurrentConcessionId,
      currentConcessionNom,
      setCurrentConcessionNom,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};