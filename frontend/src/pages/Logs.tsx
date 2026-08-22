import React, { useState, useEffect } from 'react';
import { useMetrics } from '../hooks/useMetrics';
import { getIncidents } from '../api/incidents';
import type { Incident } from '../types';
import { Loader2, Terminal, AlertTriangle } from 'lucide-react';

export const Logs: React.FC = () => {
  const { containers, loading: containersLoading } = useMetrics();
  const [selectedService, setSelectedService] = useState<string>('');
  const [logErrors, setLogErrors] = useState<string[]>([]);
  const [loadingLogs, setLoadingLogs] = useState<boolean>(false);

  useEffect(() => {
    if (containers.length > 0 && !selectedService) {
      setSelectedService(containers[0].service);
    }
  }, [containers, selectedService]);

  useEffect(() => {
    if (!selectedService) return;

    const fetchLogs = async () => {
      try {
        setLoadingLogs(true);
        // Query incidents for this service to fetch log error entries
        const data = await getIncidents({ service: selectedService, page_size: 5 });
        const errorsList: string[] = [];
        data.items.forEach((inc: Incident) => {
          if (inc.metrics_snapshot?.log_errors) {
            inc.metrics_snapshot.log_errors.forEach((err) => {
              if (!errorsList.includes(err)) {
                errorsList.push(err);
              }
            });
          }
        });
        setLogErrors(errorsList);
      } catch (err) {
        console.error('Error fetching logs:', err);
      } finally {
        setLoadingLogs(false);
      }
    };

    fetchLogs();
  }, [selectedService]);

  const isPageLoading = containersLoading || loadingLogs;

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
            Log Inspector
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Track flagged container stderr/stdout log events and matched error filters.
          </p>
        </div>

        {/* Dropdowns */}
        <select
          value={selectedService}
          onChange={(e) => setSelectedService(e.target.value)}
          className="bg-slate-900 border border-slate-800 text-xs font-bold text-slate-200 rounded-xl px-4 py-2.5 focus:border-blue-500/50"
        >
          {containers.map((c) => (
            <option key={c.service} value={c.service}>
              {c.service}
            </option>
          ))}
        </select>
      </div>

      {/* Terminal logs panel */}
      <div className="bg-slate-950 border border-slate-850 rounded-2xl overflow-hidden shadow-2xl flex flex-col">
        {/* Terminal Header */}
        <div className="bg-slate-900 px-6 py-4.5 border-b border-slate-850 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-blue-400" />
            <span className="font-mono text-xs font-bold text-slate-400">
              phoenix@logs:~/{selectedService || 'select-service'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/30" />
            <span className="w-3 h-3 rounded-full bg-amber-500/20 border border-amber-500/30" />
            <span className="w-3 h-3 rounded-full bg-emerald-500/20 border border-emerald-500/30" />
          </div>
        </div>

        {/* Terminal logs body */}
        <div className="p-6 bg-slate-950 font-mono text-sm leading-relaxed overflow-y-auto h-[480px] space-y-4">
          {isPageLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            </div>
          ) : logErrors.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600">
              <Terminal className="w-8 h-8 text-slate-700 mb-2" />
              <span>No critical error signals captured in logs.</span>
            </div>
          ) : (
            logErrors.map((err, idx) => (
              <div key={idx} className="flex items-start gap-3 text-red-400 bg-red-500/5 border border-red-500/10 p-3 rounded-xl">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-500 mt-1" />
                <span className="text-slate-300 font-medium break-all">{err}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
export default Logs;
