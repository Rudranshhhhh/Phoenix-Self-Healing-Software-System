import { apiClient } from './client';
import type { ContainerState, MetricSnapshot } from '../types';

export const getLatestMetrics = async (): Promise<MetricSnapshot[]> => {
  const response = await apiClient.get('/api/metrics');
  return response.data;
};

export const getMetricsForService = async (
  service: string,
  hours: number = 1
): Promise<MetricSnapshot[]> => {
  const response = await apiClient.get(`/api/metrics/${service}`, {
    params: { hours },
  });
  return response.data;
};

export const getContainers = async (): Promise<ContainerState[]> => {
  const response = await apiClient.get('/api/containers');
  return response.data;
};
