import React from 'react';
import { useIncidents } from '../hooks/useIncidents';
import { useMetrics } from '../hooks/useMetrics';
import { MetricCard } from '../components/MetricCard';
import { ContainerCard } from '../components/ContainerCard';
import { EscalationAlert } from '../components/EscalationAlert';
import { StatusBadge } from '../components/StatusBadge';
import { Link } from 'react-router-dom';
import {
  ShieldAlert,
  ShieldCheck,
  Zap,
  Activity,
  ArrowUpRight,
  Loader2,
} from 'lucide-react';

export const Overview: React.FC = () => {
  const { incidents, summary, loading: incidentsLoading } = useIncidents();
  const { containers, loading: containersLoading } = useMetrics();

  const escalatedIncidents = incidents.filter(
    (inc) => inc.status === 'ESCALATED' && !inc.resolved
  );
  const activeIncidents = incidents.filter((inc) => !inc.resolved);

  const getSystemHealthScore = () => {
    if (escalatedIncidents.length > 0) return 'Degraded';
    if (activeIncidents.length > 0) return 'Warning';
    return 'Optimal';
  };

  const getHealthColor = () => {
    const health = getSystemHealthScore();
    if (health === 'Degraded') return 'text-red-400';
    if (health === 'Warning') return 'text-amber-400';
    return 'text-emerald-400';
  };

  const isPageLoading = incidentsLoading || containersLoading;

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Upper header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
            Dashboard Overview
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Real-time status of self-healing infrastructure.
          </p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-slate-900 border border-slate-800 rounded-xl">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            System State:
          </span>
          <span className={`text-xs font-bold uppercase tracking-widest ${getHealthColor()}`}>
            {getSystemHealthScore()}
          </span>
        </div>
      </div>

      {/* Escalation Alert */}
      <EscalationAlert incidents={escalatedIncidents} />

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Active Incidents"
          value={summary.active_incidents}
          icon={ShieldAlert}
          color="red"
          description="Requires attention"
          isLoading={isPageLoading}
        />
        <MetricCard
          title="Resolved Failures"
          value={summary.resolved_incidents}
          icon={ShieldCheck}
          color="green"
          description="Recovered automatically"
          isLoading={isPageLoading}
        />
        <MetricCard
          title="Auto Recoveries"
          value={summary.resolved_incidents}
          icon={Zap}
          color="purple"
          description="Self-healing actions"
          isLoading={isPageLoading}
        />
        <MetricCard
          title="Monitored Containers"
          value={containers.length}
          icon={Activity}
          color="blue"
          description="Healthy container count"
          isLoading={isPageLoading}
        />
      </div>

      {/* Live Containers Grid */}
      <div>
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-extrabold text-lg tracking-wide text-slate-200 uppercase">
            Containers State
          </h3>
          <Link
            to="/containers"
            className="flex items-center gap-1.5 text-xs font-bold text-blue-400 hover:text-blue-300 uppercase tracking-wider transition-colors"
          >
            <span>View All</span>
            <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>

        {isPageLoading ? (
          <div className="flex items-center justify-center h-48 bg-slate-900/30 border border-slate-800/80 rounded-2xl">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          </div>
        ) : containers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-500 text-sm">
            No containers registered for monitoring.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {containers.slice(0, 3).map((container) => (
              <ContainerCard key={container.service} container={container} />
            ))}
          </div>
        )}
      </div>

      {/* Active Incident List */}
      <div>
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-extrabold text-lg tracking-wide text-slate-200 uppercase">
            Active Incidents
          </h3>
          <Link
            to="/incidents"
            className="flex items-center gap-1.5 text-xs font-bold text-blue-400 hover:text-blue-300 uppercase tracking-wider transition-colors"
          >
            <span>View History</span>
            <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>

        {isPageLoading ? (
          <div className="flex items-center justify-center h-48 bg-slate-900/30 border border-slate-800/80 rounded-2xl">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          </div>
        ) : activeIncidents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 bg-slate-900/30 border border-slate-850/80 rounded-2xl">
            <ShieldCheck className="w-8 h-8 text-emerald-500 mb-2" />
            <p className="text-slate-400 text-sm font-semibold">All systems nominal.</p>
            <p className="text-slate-600 text-xs mt-1">No active issues detected.</p>
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
                    <th className="p-4">Detected</th>
                    <th className="p-4 pr-6">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-850">
                  {activeIncidents.map((incident) => (
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
                      <td className="p-4 font-mono text-slate-500 text-xs">
                        {new Date(incident.detected_at).toLocaleTimeString()}
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
    </div>
  );
};
export default Overview;
