import { useEffect, useState, useCallback } from 'react';
import { getIncidents, getDashboardSummary } from '../api/incidents';
import { useSocket } from './useSocket';
import type { Incident, DashboardSummary } from '../types';
import { toast } from 'react-hot-toast';

export const useIncidents = (filters?: {
  service?: string;
  status?: string;
  severity?: string;
  resolved?: boolean;
}) => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [summary, setSummary] = useState<DashboardSummary>({
    total_incidents: 0,
    active_incidents: 0,
    resolved_incidents: 0,
    escalated_incidents: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const socket = useSocket('/incidents');

  const fetchIncidentsAndSummary = useCallback(async () => {
    try {
      setLoading(true);
      const [incidentsData, summaryData] = await Promise.all([
        getIncidents({ ...filters, page_size: 50 }),
        getDashboardSummary(),
      ]);
      setIncidents(incidentsData.items);
      setSummary(summaryData);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchIncidentsAndSummary();
  }, [fetchIncidentsAndSummary]);

  useEffect(() => {
    const handleIncidentUpdate = (updatedIncident: Incident) => {
      // Update state reactively
      setIncidents((prev) => {
        const index = prev.findIndex(
          (inc) => inc.incident_id === updatedIncident.incident_id
        );
        if (index > -1) {
          const updated = [...prev];
          updated[index] = updatedIncident;
          return updated;
        } else {
          return [updatedIncident, ...prev];
        }
      });

      // Update dashboard summary
      getDashboardSummary().then((summaryData) => {
        setSummary(summaryData);
      });

      // Alerts/Notifications based on incident state
      if (updatedIncident.status === 'ESCALATED') {
        toast.error(`🚨 ESCALATED: Service "${updatedIncident.service}" recovery failed. Manual intervention needed!`, {
          duration: 10000,
          position: 'top-right',
        });
      } else if (updatedIncident.status === 'RESOLVED') {
        toast.success(`✅ RESOLVED: Service "${updatedIncident.service}" has recovered successfully.`, {
          duration: 5000,
          position: 'top-right',
        });
      } else if (updatedIncident.status === 'RECOVERING') {
        toast.loading(`🔧 RECOVERING: Phoenix is recovering "${updatedIncident.service}" using ${updatedIncident.recovery_strategy}...`, {
          duration: 4000,
          position: 'top-right',
        });
      } else if (updatedIncident.status === 'DETECTED') {
        toast.error(`⚠️ DETECTED: Incident on "${updatedIncident.service}" (${updatedIncident.failure_type})`, {
          duration: 5000,
          position: 'top-right',
        });
      }
    };

    socket.on('incident_update', handleIncidentUpdate);

    return () => {
      socket.off('incident_update', handleIncidentUpdate);
    };
  }, [socket]);

  return { incidents, summary, loading, error, refresh: fetchIncidentsAndSummary };
};
export default useIncidents;
