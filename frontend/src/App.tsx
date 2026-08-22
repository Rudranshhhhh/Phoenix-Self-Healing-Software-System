import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Overview from './pages/Overview';
import Containers from './pages/Containers';
import Incidents from './pages/Incidents';
import IncidentDetail from './pages/IncidentDetail';
import Metrics from './pages/Metrics';
import Logs from './pages/Logs';
import AIAdvisor from './pages/AIAdvisor';
import Settings from './pages/Settings';
import { Toaster } from 'react-hot-toast';

export const App: React.FC = () => {
  return (
    <Router>
      <div className="flex h-screen w-screen overflow-hidden bg-[#090e1a]">
        {/* Sidebar Nav */}
        <Sidebar />

        {/* Main Content Workspace */}
        <main className="flex-1 overflow-y-auto p-8 md:p-12">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/containers" element={<Containers />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/incidents/:id" element={<IncidentDetail />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/ai-advisor" element={<AIAdvisor />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>

        {/* Global Real-Time Toaster */}
        <Toaster
          toastOptions={{
            style: {
              background: '#111827',
              color: '#f1f5f9',
              border: '1px solid #1e2d45',
              borderRadius: '12px',
              fontSize: '13px',
              fontWeight: 500,
            },
          }}
        />
      </div>
    </Router>
  );
};
export default App;
