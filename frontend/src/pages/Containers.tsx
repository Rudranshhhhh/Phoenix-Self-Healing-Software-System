import React from 'react';
import { useMetrics } from '../hooks/useMetrics';
import { ContainerCard } from '../components/ContainerCard';
import { Loader2 } from 'lucide-react';

export const Containers: React.FC = () => {
  const { containers, loading, error } = useMetrics();

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
          Monitored Containers
        </h2>
        <p className="text-slate-400 text-sm mt-1">
          Detailed metrics, health status, and configurations for monitored containers.
        </p>
      </div>

      {/* Main Containers Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-red-400">
          <p className="font-bold">Error loading containers status.</p>
          <p className="text-sm mt-1 text-slate-500">{error.message}</p>
        </div>
      ) : containers.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-500">
          No registered containers found.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {containers.map((container) => (
            <ContainerCard key={container.service} container={container} />
          ))}
        </div>
      )}
    </div>
  );
};
export default Containers;
