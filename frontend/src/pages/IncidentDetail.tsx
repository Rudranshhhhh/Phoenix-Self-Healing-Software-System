import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getIncidentById } from '../api/incidents';
import type { Incident } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { IncidentTimeline } from '../components/IncidentTimeline';
import { ConfidenceBar } from '../components/ConfidenceBar';
import { AISummaryPanel } from '../components/AISummaryPanel';
import {
  ArrowLeft,
  Loader2,
  Calendar,
  Cpu,
  HardDrive,
  RefreshCw,
  Zap,
} from 'lucide-react';

export const IncidentDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!id) return;
    const fetchDetail = async () => {
      try {
        setLoading(true);
        const data = await getIncidentById(id);
        setIncident(data);
      } catch (err) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();

    // Poll every 5s for live updates on active incident
    const interval = setInterval(fetchDetail, 5000);
    return () => clearInterval(interval);
  }, [id]);

  if (loading && !incident) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="space-y-4">
        <Link to="/incidents" className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase tracking-wider">
          <ArrowLeft className="w-4 h-4" /> Back to Incidents
        </Link>
        <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-2xl text-red-400">
          <p className="font-bold">Incident details could not be loaded.</p>
          <p className="text-sm mt-1">{error?.message || 'Incident not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header Back Button */}
      <div>
        <Link
          to="/incidents"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-slate-350 uppercase tracking-widest transition-colors mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to list</span>
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-extrabold text-slate-100 tracking-tight">
                Incident: #{incident.incident_id.slice(0, 8)}
              </h2>
              <StatusBadge type="severity" value={incident.severity} />
              <StatusBadge type="status" value={incident.status} />
            </div>
            <p className="text-slate-400 text-sm font-semibold mt-1">
              Active on service:{' '}
              <span className="text-slate-200">{incident.service}</span>
            </p>
          </div>
          <div className="flex items-center gap-2 text-slate-500 text-xs font-mono">
            <Calendar className="w-4 h-4" />
            <span>{new Date(incident.detected_at).toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Main Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Diagnosis & Timeline */}
        <div className="lg:col-span-2 space-y-8">
          {/* Diagnosis Card */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-5">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400">
              Technical Diagnosis
            </h3>
            <div>
              <p className="text-slate-250 text-base leading-relaxed font-semibold">
                {incident.root_cause}
              </p>
            </div>
            <ConfidenceBar score={incident.confidence_score} />
          </div>

          {/* AI Advisor enrichment panel */}
          <AISummaryPanel
            summary={incident.grok_summary}
            recommendations={incident.grok_recommendations}
            isLoading={loading}
          />

          {/* Incident Timeline */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-6">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400">
              Recovery Timeline
            </h3>
            <IncidentTimeline timeline={incident.timeline} />
          </div>
        </div>

        {/* Right Column: Ingested Metrics at Detection & Recovery Details */}
        <div className="space-y-8">
          {/* Recovery info */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400 mb-2">
              Recovery Log
            </h3>
            <div className="space-y-3.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500 font-semibold">Recovery Strategy:</span>
                <span className="font-bold text-slate-300 font-mono text-xs">
                  {incident.recovery_strategy || 'No Strategy Run'}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500 font-semibold">Retries attempted:</span>
                <div className="flex items-center gap-1 text-slate-300 font-bold font-mono">
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>{incident.retry_count}</span>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500 font-semibold">Resolved State:</span>
                <span
                  className={`font-bold uppercase tracking-wider text-xs ${
                    incident.resolved ? 'text-emerald-400' : 'text-red-400 animate-pulse'
                  }`}
                >
                  {incident.resolved ? 'Resolved' : 'Active / Recovering'}
                </span>
              </div>
            </div>
          </div>

          {/* Snapshot at Detection time */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400 mb-2">
              Metrics Snapshot at Failure
            </h3>
            <div className="space-y-4">
              <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-blue-400" />
                  <span className="text-xs font-bold text-slate-400">CPU Usage</span>
                </div>
                <span className="font-bold font-mono text-slate-200">
                  {incident.metrics_snapshot.cpu_percent}%
                </span>
              </div>

              <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <HardDrive className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-bold text-slate-400">Memory</span>
                </div>
                <span className="font-bold font-mono text-slate-200">
                  {incident.metrics_snapshot.memory_percent}%
                </span>
              </div>

              <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 text-violet-400" />
                  <span className="text-xs font-bold text-slate-400">Docker status</span>
                </div>
                <span className="font-bold capitalize text-slate-200">
                  {incident.metrics_snapshot.container_status}
                </span>
              </div>

              {incident.metrics_snapshot.health_status && (
                <div className="p-3 bg-slate-950/60 border border-slate-850 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-400" />
                    <span className="text-xs font-bold text-slate-400">App Health</span>
                  </div>
                  <span className="font-bold capitalize text-slate-200">
                    {incident.metrics_snapshot.health_status}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default IncidentDetail;
