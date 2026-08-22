import React from 'react';
import { Settings as SettingsIcon, ShieldCheck } from 'lucide-react';

export const Settings: React.FC = () => {
  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
          System Settings
        </h2>
        <p className="text-slate-400 text-sm mt-1">
          Active settings and configurations loaded by the Phoenix Agent and Flask server.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Collector Schedule Config */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400">
              <SettingsIcon className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-slate-200 text-base">
                Collector Intervals
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Poller timing parameters configured on the agent threadpool.
              </p>
            </div>
          </div>

          <div className="space-y-3 font-mono text-xs text-slate-350">
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Docker status collector:</span>
              <span className="font-bold text-slate-250">2 seconds</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">HTTP health collector:</span>
              <span className="font-bold text-slate-250">5 seconds</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Database collector:</span>
              <span className="font-bold text-slate-250">10 seconds</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Redis collector:</span>
              <span className="font-bold text-slate-250">10 seconds</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Log tail collector:</span>
              <span className="font-bold text-slate-250">20 seconds</span>
            </div>
          </div>
        </div>

        {/* Isolation & Limits Config */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-slate-200 text-base">
                SRE Health Limits
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Phoenix self-healing thresholds and recovery parameters.
              </p>
            </div>
          </div>

          <div className="space-y-3 font-mono text-xs text-slate-350">
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Escalation threshold limit:</span>
              <span className="font-bold text-slate-250">3 retries</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Recovery timeout limit:</span>
              <span className="font-bold text-slate-250">60 seconds</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">Primary persistence layer:</span>
              <span className="font-bold text-emerald-400">MongoDB</span>
            </div>
            <div className="p-3.5 bg-slate-950/60 border border-slate-850 rounded-xl flex justify-between">
              <span className="text-slate-500">AI Advisor diagnostics:</span>
              <span className="font-bold text-violet-400">Grok-3 (Active)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default Settings;
