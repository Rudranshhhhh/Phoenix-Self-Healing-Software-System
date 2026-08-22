import React, { useEffect, useState } from 'react';
import { useIncidents } from '../hooks/useIncidents';
import { BrainCircuit, Sparkles, HelpCircle } from 'lucide-react';

export const AIAdvisor: React.FC = () => {
  const { incidents, loading } = useIncidents();
  const [recommendations, setRecommendations] = useState<string[]>([]);

  useEffect(() => {
    // Extract unique Grok recommendations from past incidents
    const uniqueRecs: string[] = [];
    incidents.forEach((inc) => {
      if (inc.grok_recommendations) {
        inc.grok_recommendations.forEach((rec) => {
          if (!uniqueRecs.includes(rec)) {
            uniqueRecs.push(rec);
          }
        });
      }
    });
    setRecommendations(uniqueRecs);
  }, [incidents]);

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
            AI Advisor Dashboard
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Grok-3 powered post-incident diagnostics and preventive engineering.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-violet-500/10 border border-violet-500/20 px-3 py-1.5 rounded-xl text-xs font-bold text-violet-400 uppercase tracking-widest">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Grok-3 Powered</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Recommendations */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-violet-500/10 border border-violet-500/20 rounded-xl text-violet-400">
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-extrabold text-slate-200 text-base">
                  Actionable Architecture Recommendations
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Extracted suggestions based on recent failure patterns.
                </p>
              </div>
            </div>

            {loading ? (
              <div className="space-y-3">
                <div className="w-full h-12 skeleton rounded-xl" />
                <div className="w-full h-12 skeleton rounded-xl" />
                <div className="w-full h-12 skeleton rounded-xl" />
              </div>
            ) : recommendations.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 border border-dashed border-slate-800 rounded-xl text-slate-500 text-sm">
                <HelpCircle className="w-8 h-8 text-slate-700 mb-2" />
                <span>No recommendations available yet. Incidents trigger advisor metrics.</span>
              </div>
            ) : (
              <ul className="space-y-4">
                {recommendations.map((rec, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-4 p-4.5 bg-slate-950/40 border border-slate-850 rounded-2xl hover:border-slate-800 transition-colors"
                  >
                    <span className="w-6 h-6 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {idx + 1}
                    </span>
                    <span className="text-slate-300 text-sm leading-relaxed">
                      {rec}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Right Column: AI Model Info */}
        <div className="space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400">
              Advisor Isolation Protocol
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Phoenix follows SRE best-practices. The AI Advisor enriches diagnostics records but never commands orchestrators. Recovery loops are strictly deterministic.
            </p>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between text-xs font-mono">
              <span className="text-slate-500">Autonomous restarts:</span>
              <span className="text-red-400 uppercase font-bold">Blocked</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between text-xs font-mono">
              <span className="text-slate-500">Diagnostics write-access:</span>
              <span className="text-emerald-400 uppercase font-bold">Read-Only</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default AIAdvisor;
