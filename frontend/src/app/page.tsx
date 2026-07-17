'use client';

import { useState } from 'react';
import GraphViewer from './components/GraphViewer';
import FindingsReport from './components/FindingsReport';

export default function Home() {
  const [sourceCode, setSourceCode] = useState('');
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setResponse(null);
    setError('');
    setStatus('running');

    try {
      const res = await fetch('http://localhost:8000/api/audit/start', {
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
      setStatus(data.status || 'completed');
    } catch (err: any) {
      setError(err.message);
      setStatus('failed');
    }
  };

  return (
    <main style={{ padding: '2rem', minHeight: '100vh', fontFamily: 'sans-serif', background: '#020617', color: '#d4e4fa' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Ledgerguard - Smart Contract Auditor</h1>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '800px' }}>
        <textarea
          rows={10}
          value={sourceCode}
          onChange={(e) => setSourceCode(e.target.value)}
          placeholder="Paste Solidity source code here..."
          style={{ width: '100%', fontFamily: 'JetBrains Mono, monospace', padding: '1rem', background: '#0f172a', color: '#e2e8f0', border: '1px solid #1e293b', borderRadius: '8px' }}
        />
        <button 
          type="submit" 
          disabled={status === 'running'}
          style={{ 
            padding: '0.75rem 1.5rem', 
            cursor: status === 'running' ? 'not-allowed' : 'pointer', 
            background: status === 'running' ? '#1e293b' : '#3b82f6', 
            color: 'white', 
            border: 'none', 
            borderRadius: '4px',
            fontWeight: 600,
            alignSelf: 'flex-start'
          }}>
          {status === 'running' ? 'Auditing...' : 'Run Audit'}
        </button>
      </form>
      
      {/* 
        Note on Limitation: 
        If a user reloads the page or navigates directly to an audit_run_id URL without going through 
        the /api/audit/start flow, there is currently no way to re-fetch the run's status (no GET /status endpoint exists). 
        This is acceptable for the hackathon demo since the flow is fully controlled, but it should be addressed in the future.
      */}

      {status !== 'idle' && (
        <FindingsReport 
          auditRunId={response?.audit_run_id || ''} 
          status={status} 
        />
      )}

      {error && (
        <div style={{ marginTop: '1rem', color: '#ef4444', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '4px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {response && response.contract_id && status === 'completed' && (
        <div style={{ marginTop: '2rem' }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Analysis Graph:</h2>
          <GraphViewer contractId={response.contract_id} />
        </div>
      )}
    </main>
  );
}
