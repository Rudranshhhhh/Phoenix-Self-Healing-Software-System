import React from 'react';
import type { TimelineEvent } from '../types';
import {
  CheckCircle2,
  AlertTriangle,
  Play,
  ChevronsUp,
  Activity,
  History,
} from 'lucide-react';

interface IncidentTimelineProps {
  timeline: TimelineEvent[];
}

export const IncidentTimeline: React.FC<IncidentTimelineProps> = ({ timeline }) => {
  const getPhaseIcon = (phase: string) => {
    switch (phase) {
      case 'RESOLVED':
      case 'VERIFIED':
        return <CheckCircle2 className="w-5 h-5 text-emerald-400" />;
      case 'DETECTED':
        return <AlertTriangle className="w-5 h-5 text-cyan-400 animate-pulse" />;
      case 'DIAGNOSED':
        return <Activity className="w-5 h-5 text-violet-400" />;
      case 'RECOVERY_STARTED':
        return <Play className="w-5 h-5 text-orange-400 animate-spin" style={{ animationDuration: '3s' }} />;
      case 'RECOVERY_COMPLETED':
        return <CheckCircle2 className="w-5 h-5 text-orange-400" />;
      case 'RECOVERY_FAILED':
      case 'VERIFICATION_FAILED':
        return <AlertTriangle className="w-5 h-5 text-red-400" />;
      case 'ESCALATED':
        return <ChevronsUp className="w-5 h-5 text-red-500 animate-bounce" />;
      default:
        return <History className="w-5 h-5 text-slate-400" />;
    }
  };

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case 'RESOLVED':
      case 'VERIFIED':
        return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
      case 'DETECTED':
        return 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400';
      case 'DIAGNOSED':
        return 'border-violet-500/30 bg-violet-500/10 text-violet-400';
      case 'RECOVERY_STARTED':
      case 'RECOVERY_COMPLETED':
        return 'border-orange-500/30 bg-orange-500/10 text-orange-400';
      case 'RECOVERY_FAILED':
      case 'VERIFICATION_FAILED':
      case 'ESCALATED':
        return 'border-red-500/30 bg-red-500/10 text-red-400';
      default:
        return 'border-slate-700 bg-slate-800 text-slate-400';
    }
  };

  return (
    <div className="relative pl-6 border-l border-slate-800 space-y-8 py-2">
      {timeline.map((event, idx) => {
        const icon = getPhaseIcon(event.phase);
        const colorStyles = getPhaseColor(event.phase);
        const date = new Date(event.timestamp);

        return (
          <div key={idx} className="relative group animate-fade-up">
            {/* Timeline Dot Icon */}
            <div
              className={`absolute -left-11 top-0.5 p-2 rounded-xl border flex items-center justify-center shadow-lg transition-transform duration-200 group-hover:scale-110 ${colorStyles}`}
            >
              {icon}
            </div>

            {/* Content Card */}
            <div className="bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 rounded-2xl p-5 transition-all duration-200">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                  {event.phase.replace('_', ' ')}
                </span>
                <span className="text-xs font-medium text-slate-400 font-mono">
                  {date.toLocaleTimeString()} ({date.toLocaleDateString()})
                </span>
              </div>
              <p className="text-slate-200 text-sm leading-relaxed">{event.message}</p>

              {/* Embedded Metadata if exists */}
              {event.metadata && Object.keys(event.metadata).length > 0 && (
                <div className="mt-4 p-3 bg-slate-950/60 rounded-xl border border-slate-800/60 text-xs font-mono text-slate-400 space-y-1">
                  {Object.entries(event.metadata).map(([key, val]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-slate-500">{key}:</span>
                      <span>{typeof val === 'object' ? JSON.stringify(val) : String(val)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
export default IncidentTimeline;
