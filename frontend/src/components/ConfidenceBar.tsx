import React from 'react';

interface ConfidenceBarProps {
  score: number;
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({ score }) => {
  const percent = Math.round(score * 100);

  const getColorClasses = () => {
    if (score >= 0.85) return 'bg-emerald-500 text-emerald-400';
    if (score >= 0.6) return 'bg-amber-500 text-amber-400';
    return 'bg-red-500 text-red-400';
  };

  const colorClass = getColorClasses();

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 bg-slate-800 h-2.5 rounded-full overflow-hidden border border-slate-700/50">
        <div
          className={`h-full rounded-full transition-all duration-750 ${colorClass.split(' ')[0]}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className={`text-xs font-extrabold font-mono shrink-0 tracking-wider ${colorClass.split(' ')[1]}`}>
        {percent}% Confident
      </span>
    </div>
  );
};
export default ConfidenceBar;
