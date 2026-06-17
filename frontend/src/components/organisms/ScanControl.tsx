import React, { useState } from 'react';
import { startScan, stopScan } from '@/lib/api';
import { useToast } from '@/components/layout/ToastProvider';

export function ScanControl() {
  const [runningId, setRunningId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  async function handleStart() {
    setLoading(true);
    try {
      const payload = {
        top_n: 20,
        candidate_pool: 180,
        validation_pool: 35,
        strict_shortlist: true,
        min_expected_return_pct: 5,
        min_ml_probability: 62,
        min_risk_reward: 1.8,
        max_stop_distance_pct: 5,
        min_data_reliability_score: 35,
        min_profitability_score: 18,
      };
      const result = await startScan(payload as any);
      setRunningId(result.scan_id ?? null);
      toast?.push('Scan started', 'success');
    } catch (err) {
      console.error('start error', err);
      toast?.push('Failed to start scan', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleStop() {
    if (!runningId) return;
    setLoading(true);
    try {
      await stopScan(runningId);
      setRunningId(null);
      toast?.push('Scan stopped', 'info');
    } catch (err) {
      console.error('stop error', err);
      toast?.push('Failed to stop scan', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="scan-control card">
      <div className="section-head"><h3>Scan Control</h3></div>
      <div className="actions">
        <button className="button primary" onClick={handleStart} disabled={loading}>Start Scan</button>
        <button className="button secondary" onClick={handleStop} disabled={!runningId || loading}>Stop Scan</button>
      </div>
      <div className="small">Active Scan ID: {runningId ?? 'none'}</div>
    </div>
  );
}

export default ScanControl;
