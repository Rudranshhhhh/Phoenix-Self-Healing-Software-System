import React from 'react';
import type { ContainerState } from '../types';
import { Cpu, HardDrive, RefreshCw } from 'lucide-react';

interface ContainerCardProps {
  container: ContainerState;
}

export const ContainerCard: React.FC<ContainerCardProps> = ({ container }) => {
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'bg-emerald-500';
      case 'exited':
      case 'dead':
        return 'bg-red-500';
      case 'restarting':
        return 'bg-amber-500 animate-spin';
      default:
        return 'bg-slate-500';
    }
  };

  const getHealthBadge = (health?: string) => {
    if (!health) return null;
    const color =
      health === 'healthy'
        ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
        : 'bg-red-500/10 border-red-500/20 text-red-400 animate-pulse';

    return (
      <span className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border ${color}`}>
        {health}
      </span>
    );
  };

  return (
    <div className="bg-slate-900 border border-slate-800 hover:border-slate-700/80 rounded-2xl p-6 transition-all duration-300 hover:shadow-[0_0_30px_rgba(30,41,59,0.5)]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-bold text-slate-100 tracking-tight">
            {container.service}
          </h3>
          <p className="text-slate-500 text-xs font-mono mt-0.5 truncate max-w-[180px]">
            {container.container_name || 'N/A'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {getHealthBadge(container.health_status)}
          <div className="flex items-center gap-1.5 bg-slate-950/80 px-2.5 py-1 rounded-lg border border-slate-850">
            <span className={`w-2.5 h-2.5 rounded-full ${getStatusColor(container.container_status)}`} />
            <span className="text-xs font-bold text-slate-400 capitalize">
              {container.container_status}
            </span>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-4 mt-6">
        {/* CPU */}
        <div className="p-3 bg-slate-950/50 rounded-xl border border-slate-850/60">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <Cpu className="w-4 h-4 text-blue-400" />
            <span className="text-xs font-semibold">CPU Usage</span>
          </div>
          <span className="text-xl font-bold font-mono text-slate-200">
            {container.cpu_percent.toFixed(1)}%
          </span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, container.cpu_percent)}%` }}
            />
          </div>
        </div>

        {/* Memory */}
        <div className="p-3 bg-slate-950/50 rounded-xl border border-slate-850/60">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <HardDrive className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-semibold">Memory</span>
          </div>
          <span className="text-xl font-bold font-mono text-slate-200">
            {container.memory_percent.toFixed(1)}%
          </span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, container.memory_percent)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="flex items-center justify-between mt-5 pt-4 border-t border-slate-850">
        <div className="flex items-center gap-1.5 text-slate-500 text-xs font-semibold">
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Restarts:</span>
          <span className="font-mono text-slate-300 font-bold">
            {container.restart_count}
          </span>
        </div>
        {container.last_seen && (
          <span className="text-[10px] font-medium text-slate-500 font-mono">
            Updated {new Date(container.last_seen).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
};
export default ContainerCard;
