'use client';

import { useState, useEffect } from 'react';
import { API_BASE_URL } from '@/config';

type AgentAction = {
  id: string;
  audit_run_id: string;
  agent_type: string;
  action_description: string;
  tx_hash: string | null;
  result: any;
  timestamp: string;
};

export default function AgentLogView({ auditRunId, status }: { auditRunId: string, status: string }) {
  const [logs, setLogs] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    const fetchLogs = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/audit/${auditRunId}/agent-log`);
        if (res.ok) {
          const data = await res.json();
          setLogs(data);
        }
      } catch (err) {
        console.error("Failed to fetch agent logs", err);
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();

    if ((status === 'running' || status === 'queued') && !window.location.search.includes('forceId')) {
      intervalId = setInterval(fetchLogs, 3000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [auditRunId, status]);

  if (status === 'queued') {
    return (
      <div className="w-full bg-surface-container-low border border-outline-variant rounded-xl p-8 flex flex-col gap-8 shadow-lg relative overflow-hidden z-10 backdrop-blur-sm">
        <div className="flex items-start justify-between border-b border-outline-variant pb-6">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded bg-surface-container-highest border border-outline-variant flex items-center justify-center relative">
              <span className="material-symbols-outlined text-outline-variant text-2xl absolute">hourglass_empty</span>
            </div>
            <div className="flex flex-col gap-1">
              <h2 className="font-headline-md text-headline-md text-on-surface m-0 p-0 leading-none">Queued</h2>
              <p className="font-code-sm text-code-sm text-on-surface-variant mt-1">Waiting for previous audit to complete...</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-on-surface-variant font-code-sm text-code-sm">
          <span className="material-symbols-outlined text-sm spin-slow">autorenew</span>
          <span>Waiting in queue...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full bg-surface-container-low border border-outline-variant rounded-xl p-8 flex flex-col gap-8 shadow-lg relative overflow-hidden z-10 backdrop-blur-sm">
      <div className="flex items-start justify-between border-b border-outline-variant pb-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded bg-surface-container-highest border border-outline-variant flex items-center justify-center relative">
            <span className={`material-symbols-outlined text-primary text-2xl absolute ${status === 'running' ? 'spin-slow' : ''}`}>settings</span>
            <span className="material-symbols-outlined text-primary text-sm">memory</span>
          </div>
          <div className="flex flex-col gap-1">
            <h2 className="font-headline-md text-headline-md text-on-surface m-0 p-0 leading-none">
              {status === 'running' ? 'Audit in progress...' : 'Audit completed'}
            </h2>
            <p className="font-code-sm text-code-sm text-primary opacity-80 mt-1">Target: {auditRunId.substring(0, 8)}</p>
          </div>
        </div>
      </div>

      <div className="bg-[#020617] rounded border border-outline-variant p-4 flex flex-col gap-2 font-code-sm text-code-sm relative min-h-[150px] max-h-[400px] overflow-y-auto">
        <div className="absolute top-0 right-0 px-2 py-1 bg-surface-container-highest border-b border-l border-outline-variant rounded-bl text-[10px] text-on-surface-variant uppercase tracking-widest font-semibold z-10">
          Live Log
        </div>
        
        {logs.length === 0 && loading && (
          <span className="text-outline-variant">Initializing agents...</span>
        )}

        {logs.map((log) => {
          const isSuccess = log.result?.success || log.result?.exploit_outcome === 'EXPLOIT_SUCCEEDED';
          const isError = log.result?.error || log.result?.exploit_outcome === 'EXPLOIT_FAILED';

          return (
            <span key={log.id} className="text-outline-variant flex flex-wrap items-center gap-2">
              <span>[{new Date(log.timestamp).toLocaleTimeString()}]</span>
              <span className="text-secondary">{log.agent_type}: {log.action_description}</span>
              
              {isSuccess && (
                <span className="bg-[#ffb4ab]/10 text-error font-label-caps text-label-caps px-2 py-0.5 rounded-full border border-[#ffb4ab]/20 ml-2">
                  EXPLOIT_SUCCEEDED
                </span>
              )}
              {isError && (
                <span className="bg-[#f59e0b]/10 text-[#f59e0b] font-label-caps text-label-caps px-2 py-0.5 rounded-full border border-[#f59e0b]/20 ml-2">
                  FAILED
                </span>
              )}
            </span>
          );
        })}
        
        {status === 'running' && (
          <span className="text-outline-variant terminal-line active mt-2">
            <span className="text-primary">Agents are working...</span>
          </span>
        )}
      </div>
    </div>
  );
}
