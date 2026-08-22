import React from 'react';
import type { Severity, IncidentStatus } from '../types';

interface StatusBadgeProps {
  type: 'severity' | 'status';
  value: Severity | IncidentStatus;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ type, value }) => {
  const getStyles = () => {
    if (type === 'severity') {
      switch (value as Severity) {
        case 'CRITICAL':
          return 'bg-red-500/10 border border-red-500/30 text-red-400';
        case 'HIGH':
          return 'bg-orange-500/10 border border-orange-500/30 text-orange-400';
        case 'MEDIUM':
          return 'bg-amber-500/10 border border-amber-500/30 text-amber-400';
        case 'LOW':
          return 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400';
        default:
          return 'bg-slate-500/10 border border-slate-500/30 text-slate-400';
      }
    } else {
      switch (value as IncidentStatus) {
        case 'RESOLVED':
          return 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400';
        case 'ESCALATED':
          return 'bg-red-500/15 border border-red-500/40 text-red-400 animate-pulse';
        case 'RECOVERING':
          return 'bg-orange-500/10 border border-orange-500/30 text-orange-400';
        case 'VERIFYING':
          return 'bg-blue-500/10 border border-blue-500/30 text-blue-400';
        case 'DIAGNOSING':
          return 'bg-violet-500/10 border border-violet-500/30 text-violet-400';
        case 'DETECTED':
          return 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-400';
        default:
          return 'bg-slate-500/10 border border-slate-500/30 text-slate-400';
      }
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide capitalize ${getStyles()}`}
    >
      {value.toLowerCase()}
    </span>
  );
};
export default StatusBadge;
