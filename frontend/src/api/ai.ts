import { apiClient } from './client';

export const getAISummary = async (incidentId: string): Promise<{ summary: string }> => {
  const response = await apiClient.get(`/api/ai/summary/${incidentId}`);
  return response.data;
};

export const getAIRecommendations = async (): Promise<{ recommendations: string[] }> => {
  const response = await apiClient.get('/api/ai/recommendations');
  return response.data;
};
