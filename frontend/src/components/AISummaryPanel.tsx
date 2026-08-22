import React from 'react';
import { BrainCircuit, Sparkles, AlertCircle } from 'lucide-react';

interface AISummaryPanelProps {
  summary?: string;
  recommendations?: string[];
  isLoading?: boolean;
}

export const AISummaryPanel: React.FC<AISummaryPanelProps> = ({
  summary,
  recommendations,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-5 h-5 text-violet-400 animate-pulse" />
          <div className="w-32 h-4 skeleton rounded-lg" />
        </div>
        <div className="space-y-2">
          <div className="w-full h-3 skeleton rounded-lg" />
          <div className="w-5/6 h-3 skeleton rounded-lg" />
          <div className="w-4/5 h-3 skeleton rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800/80 rounded-2xl overflow-hidden shadow-lg">
      {/* Banner */}
      <div className="bg-gradient-to-r from-violet-600/10 to-indigo-600/5 px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <BrainCircuit className="w-5 h-5 text-violet-400" />
          <span className="font-bold text-slate-200 text-sm tracking-wide">
            AI Advisor Enrichment
          </span>
        </div>
        <div className="flex items-center gap-1 bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 rounded text-[9px] font-bold text-violet-400 uppercase tracking-widest">
          <Sparkles className="w-2.5 h-2.5" />
          <span>Grok-3 Powered</span>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Summary */}
        <div>
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2.5">
            Root Cause Explanation
          </h4>
          {summary ? (
            <p className="text-slate-300 text-sm leading-relaxed font-medium">
              {summary}
            </p>
          ) : (
            <div className="flex items-center gap-2 text-slate-500 text-sm italic">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>No explanation generated for this incident.</span>
            </div>
          )}
        </div>

        {/* Recommendations */}
        {recommendations && recommendations.length > 0 && (
          <div className="pt-5 border-t border-slate-850">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3.5">
              Prevention Recommendations
            </h4>
            <ul className="space-y-3.5">
              {recommendations.map((rec, idx) => (
                <li key={idx} className="flex items-start gap-3">
                  <span className="w-5 h-5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <span className="text-slate-300 text-sm leading-relaxed">
                    {rec}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
export default AISummaryPanel;
