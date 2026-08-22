import React from 'react';
import { ShieldAlert, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Incident } from '../types';

interface EscalationAlertProps {
  incidents: Incident[];
}

export const EscalationAlert: React.FC<EscalationAlertProps> = ({ incidents }) => {
  if (incidents.length === 0) return null;

  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 animate-pulse-red">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-red-500/20 text-red-400 border border-red-500/30 rounded-xl shrink-0">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <div>
          <h3 className="font-extrabold text-red-400 text-base tracking-wide uppercase">
            Human Intervention Required
          </h3>
          <p className="text-slate-350 text-sm mt-0.5 leading-relaxed">
            Automatic recovery has failed {incidents.length} time(s). Please inspect active incidents immediately.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <Link
          to="/incidents?status=ESCALATED"
          className="flex items-center gap-2 px-4 py-2.5 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xs font-extrabold uppercase tracking-wider transition-colors shadow-lg"
        >
          <span>View Escalations</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
};
export default EscalationAlert;
