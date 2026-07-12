'use client';

import { useState } from 'react';
import GraphViewer from './components/GraphViewer';

export default function Home() {
  const [sourceCode, setSourceCode] = useState('');
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setResponse(null);
    setError('');

    try {
      const res = await fetch('http://localhost:8000/api/contracts/upload', {
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
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <main style={{ padding: '2rem', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Ledgerguard - Contract Upload</h1>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '600px' }}>
        <textarea
          rows={10}
          value={sourceCode}
          onChange={(e) => setSourceCode(e.target.value)}
          placeholder="Paste Solidity source code here..."
          style={{ width: '100%', fontFamily: 'monospace', padding: '0.5rem', color: 'black' }}
        />
        <button type="submit" style={{ padding: '0.5rem 1rem', cursor: 'pointer', background: '#0070f3', color: 'white', border: 'none', borderRadius: '4px' }}>
          Submit
        </button>
      </form>
      
      {error && (
        <div style={{ marginTop: '1rem', color: 'red' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {response && response.contract_id ? (
        <div style={{ marginTop: '1rem' }}>
          <h2>Analysis Graph:</h2>
          <GraphViewer contractId={response.contract_id} />
        </div>
      ) : response ? (
        <div style={{ marginTop: '1rem' }}>
          <h2>Response:</h2>
          <pre style={{ background: '#f4f4f4', padding: '1rem', overflowX: 'auto', color: 'black', borderRadius: '4px' }}>
            {JSON.stringify(response, null, 2)}
          </pre>
        </div>
      ) : null}
    </main>
  );
}
