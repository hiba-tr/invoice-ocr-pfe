import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Upload from './pages/Upload';
import History from './pages/History';
import Database from './pages/Database';
import Analyses from './pages/Analyses';
import Manual from './pages/Manual';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Upload />} />
        <Route path="/history" element={<History />} />
        <Route path="/database" element={<Database />} />
        <Route path="/analyses" element={<Analyses />} />
        <Route path="/manual" element={<Manual />} />
      </Route>
    </Routes>
  );
}