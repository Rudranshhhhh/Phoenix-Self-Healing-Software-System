import { useEffect, useState, useCallback } from 'react';
import { getContainers } from '../api/metrics';
import { useSocket } from './useSocket';
import type { ContainerState, MetricSnapshot } from '../types';

export const useMetrics = () => {
  const [containers, setContainers] = useState<ContainerState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const socket = useSocket('/metrics');

  const fetchContainers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getContainers();
      setContainers(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchContainers();
  }, [fetchContainers]);

  useEffect(() => {
    const handleMetricUpdate = (metric: MetricSnapshot) => {
      setContainers((prev) => {
        const index = prev.findIndex((c) => c.service === metric.service);
        if (index > -1) {
          const updated = [...prev];
          updated[index] = {
            ...updated[index],
            container_status: metric.container_status || updated[index].container_status,
            cpu_percent: metric.cpu_percent,
            memory_percent: metric.memory_percent,
            memory_mb: metric.memory_mb || updated[index].memory_mb || 0,
            restart_count: metric.restart_count !== undefined ? metric.restart_count : updated[index].restart_count,
            health_status: metric.health_status || updated[index].health_status,
            last_seen: metric.collected_at || metric.timestamp || new Date().toISOString(),
          };
          return updated;
        } else {
          return [
            ...prev,
            {
              service: metric.service,
              container_name: metric.container_name,
              container_status: metric.container_status || 'running',
              cpu_percent: metric.cpu_percent,
              memory_percent: metric.memory_percent,
              memory_mb: metric.memory_mb || 0,
              restart_count: metric.restart_count || 0,
              health_status: metric.health_status,
              last_seen: metric.collected_at || metric.timestamp,
            },
          ];
        }
      });
    };

    socket.on('metric_update', handleMetricUpdate);

    return () => {
      socket.off('metric_update', handleMetricUpdate);
    };
  }, [socket]);

  return { containers, loading, error, refresh: fetchContainers };
};
export default useMetrics;
