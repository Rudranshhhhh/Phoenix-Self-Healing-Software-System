import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  color: 'blue' | 'red' | 'green' | 'yellow' | 'purple' | 'orange';
  description?: string;
  isLoading?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  icon: Icon,
  color,
  description,
  isLoading = false,
}) => {
  const getColorClasses = () => {
    switch (color) {
      case 'blue':
        return {
          iconBg: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(59,130,246,0.1)] hover:border-blue-500/30',
        };
      case 'red':
        return {
          iconBg: 'bg-red-500/10 text-red-400 border-red-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(239,68,68,0.1)] hover:border-red-500/30',
        };
      case 'green':
        return {
          iconBg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(16,185,129,0.1)] hover:border-emerald-500/30',
        };
      case 'yellow':
        return {
          iconBg: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(245,158,11,0.1)] hover:border-amber-500/30',
        };
      case 'purple':
        return {
          iconBg: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(139,92,246,0.1)] hover:border-violet-500/30',
        };
      case 'orange':
        return {
          iconBg: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
          glow: 'hover:shadow-[0_0_30px_rgba(249,115,22,0.1)] hover:border-orange-500/30',
        };
    }
  };

  const classes = getColorClasses();

  if (isLoading) {
    return (
      <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-6 h-36 flex flex-col justify-between">
        <div className="flex justify-between items-start">
          <div className="w-24 h-4 skeleton rounded-lg" />
          <div className="w-10 h-10 skeleton rounded-xl" />
        </div>
        <div className="space-y-2">
          <div className="w-16 h-8 skeleton rounded-lg" />
          <div className="w-32 h-3 skeleton rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 transition-all duration-300 flex flex-col justify-between ${classes.glow}`}
    >
      <div className="flex justify-between items-start">
        <span className="text-slate-400 text-sm font-semibold tracking-wide">
          {title}
        </span>
        <div className={`p-2.5 rounded-xl border ${classes.iconBg}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>

      <div className="mt-4">
        <span className="text-3xl font-extrabold text-slate-100 tracking-tight font-mono">
          {value}
        </span>
        {description && (
          <p className="text-slate-500 text-xs font-semibold mt-1.5 uppercase tracking-wider">
            {description}
          </p>
        )}
      </div>
    </div>
  );
};
export default MetricCard;
