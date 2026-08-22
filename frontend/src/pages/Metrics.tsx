import React, { useState, useEffect } from 'react';
import { getMetricsForService } from '../api/metrics';
import type { MetricSnapshot } from '../types';
import { useMetrics } from '../hooks/useMetrics';
import {
  ResponsiveContainer,
  LineChart as ReChartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { Loader2 } from 'lucide-react';

export const Metrics: React.FC = () => {
  const { containers, loading: containersLoading } = useMetrics();
  const [selectedService, setSelectedService] = useState<string>('');
  const [metricsData, setMetricsData] = useState<MetricSnapshot[]>([]);
  const [timeRange, setTimeRange] = useState<number>(1); // hours
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);

  useEffect(() => {
    if (containers.length > 0 && !selectedService) {
      setSelectedService(containers[0].service);
    }
  }, [containers, selectedService]);

  useEffect(() => {
    if (!selectedService) return;

    const fetchMetrics = async () => {
      try {
        setLoadingMetrics(true);
        const data = await getMetricsForService(selectedService, timeRange);
        setMetricsData(data);
      } catch (err) {
        console.error('Error fetching metrics charts:', err);
      } finally {
        setLoadingMetrics(false);
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, [selectedService, timeRange]);

  const formatXAxis = (tickItem: string) => {
    try {
      const d = new Date(tickItem);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return tickItem;
    }
  };

  const isPageLoading = containersLoading || (loadingMetrics && metricsData.length === 0);

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
            Telemetry Metrics
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Time-series telemetry visualization for CPU, Memory, and Latencies.
          </p>
        </div>

        {/* Dropdowns */}
        <div className="flex items-center gap-3">
          <select
            value={selectedService}
            onChange={(e) => setSelectedService(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs font-bold text-slate-200 rounded-xl px-4 py-2.5 focus:border-blue-500/50"
          >
            {containers.map((c) => (
              <option key={c.service} value={c.service}>
                {c.service}
              </option>
            ))}
          </select>

          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="bg-slate-900 border border-slate-800 text-xs font-bold text-slate-200 rounded-xl px-4 py-2.5 focus:border-blue-500/50"
          >
            <option value={1}>Last Hour</option>
            <option value={3}>Last 3 Hours</option>
            <option value={6}>Last 6 Hours</option>
            <option value={24}>Last 24 Hours</option>
          </select>
        </div>
      </div>

      {isPageLoading ? (
        <div className="flex items-center justify-center h-96 bg-slate-900/30 border border-slate-800/80 rounded-2xl">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      ) : metricsData.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-96 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-500">
          No metrics telemetry recorded for service "{selectedService}" in this timeframe.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-8">
          {/* CPU Chart */}
          <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-6">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400 mb-6">
              CPU Utilization (%)
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ReChartsLineChart data={metricsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={formatXAxis}
                    stroke="#4b5563"
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                  />
                  <YAxis
                    stroke="#4b5563"
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#1e293b',
                      borderRadius: '12px',
                    }}
                    labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                    itemStyle={{ color: '#3b82f6', fontSize: '12px' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="cpu_percent"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    dot={false}
                    name="CPU Usage"
                  />
                </ReChartsLineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Memory Chart */}
          <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-6">
            <h3 className="text-sm font-extrabold uppercase tracking-widest text-slate-400 mb-6">
              Memory Utilization (%)
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ReChartsLineChart data={metricsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={formatXAxis}
                    stroke="#4b5563"
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                  />
                  <YAxis
                    stroke="#4b5563"
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#1e293b',
                      borderRadius: '12px',
                    }}
                    labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                    itemStyle={{ color: '#10b981', fontSize: '12px' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="memory_percent"
                    stroke="#10b981"
                    strokeWidth={2.5}
                    dot={false}
                    name="Memory Usage"
                  />
                </ReChartsLineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default Metrics;
