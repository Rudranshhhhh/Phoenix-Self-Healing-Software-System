import React, { useState, useEffect } from 'react';
import { useIncidents } from '../hooks/useIncidents';
import { StatusBadge } from '../components/StatusBadge';
import { Link } from 'react-router-dom';
import { Loader2, Search, Filter } from 'lucide-react';

export const Incidents: React.FC = () => {
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const { incidents, loading, error } = useIncidents();
  const [filteredIncidents, setFilteredIncidents] = useState(incidents);

  useEffect(() => {
    let result = incidents;

    if (statusFilter !== 'ALL') {
      result = result.filter((inc) => inc.status === statusFilter);
    }

    if (severityFilter !== 'ALL') {
      result = result.filter((inc) => inc.severity === severityFilter);
    }

    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (inc) =>
          inc.service.toLowerCase().includes(q) ||
          inc.failure_type.toLowerCase().includes(q) ||
          inc.root_cause.toLowerCase().includes(q)
      );
    }

    setFilteredIncidents(result);
  }, [incidents, statusFilter, severityFilter, searchQuery]);

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
          Incident Center
        </h2>
        <p className="text-slate-400 text-sm mt-1">
          Detailed event log for the recovery lifecycle of all incidents.
        </p>
      </div>

      {/* Filters bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 bg-slate-900 border border-slate-800 rounded-2xl">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-3 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by service or failure type..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 text-slate-200 text-sm font-medium rounded-xl transition-all"
          />
        </div>

        {/* Dropdowns */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <span className="text-xs font-semibold text-slate-400">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-xs font-bold text-slate-300 rounded-lg px-3 py-1.5 focus:border-blue-500/50"
            >
              <option value="ALL">All Statuses</option>
              <option value="DETECTED">Detected</option>
              <option value="DIAGNOSING">Diagnosing</option>
              <option value="RECOVERING">Recovering</option>
              <option value="VERIFYING">Verifying</option>
              <option value="ESCALATED">Escalated</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Severity:</span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-xs font-bold text-slate-300 rounded-lg px-3 py-1.5 focus:border-blue-500/50"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-red-400">
          <p className="font-bold">Error loading incidents history.</p>
          <p className="text-sm mt-1 text-slate-500">{error.message}</p>
        </div>
      ) : filteredIncidents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-500">
          No matching incidents found.
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800/80 rounded-2xl overflow-hidden shadow-lg">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-xs font-bold text-slate-500 uppercase bg-slate-950/40">
                  <th className="p-4 pl-6">Service</th>
                  <th className="p-4">Failure</th>
                  <th className="p-4">Severity</th>
                  <th className="p-4">Status</th>
                  <th className="p-4">Confidence</th>
                  <th className="p-4">Detected</th>
                  <th className="p-4 pr-6">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850">
                {filteredIncidents.map((incident) => (
                  <tr
                    key={incident.incident_id}
                    className="hover:bg-slate-800/30 transition-colors"
                  >
                    <td className="p-4 pl-6 font-bold text-slate-200">
                      {incident.service}
                    </td>
                    <td className="p-4 font-semibold text-slate-400">
                      {incident.failure_type.replace('_', ' ')}
                    </td>
                    <td className="p-4">
                      <StatusBadge type="severity" value={incident.severity} />
                    </td>
                    <td className="p-4">
                      <StatusBadge type="status" value={incident.status} />
                    </td>
                    <td className="p-4 font-bold text-xs font-mono text-slate-350">
                      {Math.round(incident.confidence_score * 100)}%
                    </td>
                    <td className="p-4 font-mono text-slate-500 text-xs">
                      {new Date(incident.detected_at).toLocaleString()}
                    </td>
                    <td className="p-4 pr-6">
                      <Link
                        to={`/incidents/${incident.incident_id}`}
                        className="text-xs font-bold text-blue-400 hover:text-blue-300 uppercase tracking-wider transition-colors"
                      >
                        Details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
export default Incidents;
