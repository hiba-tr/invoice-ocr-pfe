import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Upload from './pages/Upload';
import Analyses from './pages/Analyses';
import History from './pages/History';
import Database from './pages/Database';
import Manual from './pages/Manual';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Upload />} />
          <Route path="history" element={<History />} />
          <Route path="analyses" element={<Analyses />} />
          <Route path="database" element={<Database />} />
          <Route path="manual" element={<Manual />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}