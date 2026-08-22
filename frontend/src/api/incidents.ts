import { apiClient } from './client';
import type { Incident, DashboardSummary, PaginatedResponse } from '../types';

export const getIncidents = async (params?: {
  service?: string;
  status?: string;
  severity?: string;
  resolved?: boolean;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<Incident>> => {
  const response = await apiClient.get('/api/incidents', { params });
  return response.data;
};

export const getIncidentById = async (id: string): Promise<Incident> => {
  const response = await apiClient.get(`/api/incidents/${id}`);
  return response.data;
};

export const getDashboardSummary = async (): Promise<DashboardSummary> => {
  const response = await apiClient.get('/api/incidents/summary');
  return response.data;
};
