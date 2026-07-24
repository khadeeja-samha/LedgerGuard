'use client';

import { useState, useEffect } from 'react';
import { API_BASE_URL } from '@/config';
import GraphViewer from './components/GraphViewer';
import FindingsReport from './components/FindingsReport';
import AgentLogView from './components/AgentLogView';

export default function Home() {
  const [sourceCode, setSourceCode] = useState('');
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle');
  const [auditRunId, setAuditRunId] = useState<string>('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const forceId = params.get('forceId');
    const forceStatus = params.get('forceStatus');
    const forceContract = params.get('forceContract');
    if (forceId) {
      setAuditRunId(forceId);
      if (forceStatus) setStatus(forceStatus as any);
      if (forceContract) setResponse({ contract_id: forceContract });
    }
  }, []);

  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    if (auditRunId && (status === 'queued' || status === 'running') && !window.location.search.includes('forceId')) {
      intervalId = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE_URL}/api/audit/${auditRunId}/status`);
          if (res.ok) {
            const data = await res.json();
            setStatus(data.status);
          }
        } catch (err) {
          console.error("Failed to poll status", err);
        }
      }, 3000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [auditRunId, status]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setResponse(null);
    setAuditRunId('');
    setError('');
    setStatus('running'); // visual optimism until queued arrives

    try {
      const res = await fetch(`${API_BASE_URL}/api/audit/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ source_code: sourceCode }),
      });

      if (!res.ok) {
        throw new Error(`Error: ${res.status}`);
      }

      const data = await res.json();
      setResponse(data);
      setAuditRunId(data.audit_run_id);
      setStatus(data.status || 'queued');
    } catch (err: any) {
      setError(err.message);
      setStatus('failed');
    }
  };

  return (
    <div className="flex-1 bg-background overflow-y-auto p-container-padding flex flex-col gap-6 w-full max-w-5xl mx-auto">
      <div className="mb-4">
        <h2 className="font-headline-lg text-headline-lg text-on-surface m-0">LedgerGuard</h2>
        <p className="font-body-md text-body-md text-on-surface-variant mt-1">We attack it before someone else does.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="bg-surface-container-low border border-outline-variant rounded relative flex flex-col">
          <textarea
            rows={10}
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            placeholder="Paste Solidity source code here..."
            className="w-full font-code-sm text-code-sm p-4 bg-transparent text-on-surface focus:outline-none focus:ring-1 focus:ring-primary rounded resize-y"
          />
        </div>
        
        <button 
          type="submit" 
          disabled={status === 'running' || status === 'queued'}
          className={`self-start px-4 py-2 rounded font-label-caps text-label-caps flex items-center gap-2 transition-colors ${
            status === 'running' || status === 'queued'
              ? 'bg-surface-container-highest text-on-surface-variant cursor-not-allowed'
              : 'bg-primary-container text-on-primary-container hover:bg-primary-fixed-dim cursor-pointer active:opacity-80'
          }`}
        >
          {status === 'running' ? 'Auditing...' : status === 'queued' ? 'Queued...' : 'Run Audit'}
        </button>
      </form>
      
      {error && (
        <div className="mt-4 text-error p-4 bg-[#93000a]/20 border border-error rounded">
          <strong>Error:</strong> {error}
        </div>
      )}

      {auditRunId && (status === 'queued' || status === 'running') && (
        <div className="mt-8">
          <AgentLogView auditRunId={auditRunId} status={status} />
        </div>
      )}

      {status !== 'idle' && status !== 'queued' && status !== 'running' && (
        <FindingsReport 
          auditRunId={auditRunId} 
          status={status} 
        />
      )}

      {response && response.contract_id && status === 'completed' && (
        <div className="mt-8">
          <h2 className="font-headline-sm text-headline-sm text-on-surface mb-4">Analysis Graph:</h2>
          <div className="bg-surface-container-low border border-outline-variant rounded p-4">
            <GraphViewer contractId={response.contract_id} />
          </div>
        </div>
      )}
    </div>
  );
}
