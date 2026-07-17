'use client';

import { useEffect, useState } from 'react';

type Finding = {
  id: string;
  function_name: string;
  risk_level: string;
  risk_score: number;
  attack_type: string;
  description: string;
};

type FindingsReportProps = {
  auditRunId: string;
  status: string; // 'running', 'completed', 'failed'
};

const formatAttackType = (type: string) => {
  const mapping: Record<string, string> = {
    'reentrancy': 'Reentrancy',
    'flashloan': 'Flash Loan',
    'access_control': 'Access Control',
    'arithmetic': 'Arithmetic',
    'logic': 'Logic Error',
  };
  return mapping[type] || type;
};

const getRiskColor = (level: string) => {
  switch (level.toUpperCase()) {
    case 'HIGH': return { bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444', border: '#ef4444' }; // Red
    case 'UNKNOWN': return { bg: 'rgba(245, 158, 11, 0.1)', text: '#f59e0b', border: '#f59e0b' }; // Amber
    case 'LOW': return { bg: 'rgba(16, 185, 129, 0.1)', text: '#10b981', border: '#10b981' }; // Green
    default: return { bg: 'rgba(107, 114, 128, 0.1)', text: '#9ca3af', border: '#6b7280' }; // Gray
  }
};

export default function FindingsReport({ auditRunId, status }: FindingsReportProps) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (status === 'completed') {
      const fetchFindings = async () => {
        setLoading(true);
        try {
          const res = await fetch(`http://localhost:8000/api/audit/${auditRunId}/findings`);
          if (!res.ok) throw new Error('Failed to fetch findings');
          const data: Finding[] = await res.json();
          const sorted = data.sort((a, b) => b.risk_score - a.risk_score);
          setFindings(sorted);
        } catch (err: any) {
          setError(err.message);
        } finally {
          setLoading(false);
        }
      };
      fetchFindings();
    }
  }, [auditRunId, status]);

  const containerStyle: React.CSSProperties = {
    background: '#051424',
    color: '#d4e4fa',
    fontFamily: 'Inter, sans-serif',
    padding: '24px',
    borderRadius: '8px',
    border: '1px solid #1e293b',
    marginTop: '16px',
  };

  // 1. In-flight POST /api/audit/start (status == 'running')
  if (status === 'running') {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0' }}>Audit in Progress</h2>
          <div style={{ background: '#0d1c2d', height: '8px', borderRadius: '4px', overflow: 'hidden', margin: '0 auto', maxWidth: '400px' }}>
            <div style={{ width: '65%', height: '100%', background: '#3b82f6', transition: 'width 0.5s' }} />
          </div>
        </div>
        <div style={{ background: '#020617', padding: '16px', borderRadius: '4px', border: '1px solid #1e293b', fontFamily: 'JetBrains Mono, monospace', fontSize: '13px', color: '#94a3b8' }}>
          <div>$ Initializing audit sequence...</div>
          <div>$ Parsing Solidity AST...</div>
          <div>$ Building knowledge graph...</div>
          <div>$ Running static analysis agents...</div>
          <div style={{ color: '#3b82f6' }}>&gt; Analyzing contract logic (still working)... <span className="blink">_</span></div>
        </div>
        <style>{`
          @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
          .blink { animation: blink 1s step-end infinite; }
        `}</style>
      </div>
    );
  }

  // 2. Error state (status == 'failed' or fetch error)
  if (status === 'failed' || error) {
    return (
      <div style={containerStyle}>
        <h2 style={{ fontSize: '24px', fontWeight: 600, color: '#ef4444' }}>Audit failed to complete</h2>
        <p style={{ color: '#94a3b8' }}>{error || 'An internal error occurred during the audit execution.'}</p>
      </div>
    );
  }

  // Loading state for fetching findings (should be very fast, but just in case)
  if (loading) {
    return <div style={containerStyle}>Loading findings...</div>;
  }

  // 3. Clean Empty State (status == 'completed' && findings.length == 0)
  if (status === 'completed' && findings.length === 0) {
    return (
      <div style={{ ...containerStyle, textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>🛡️</div>
        <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '8px', color: '#10b981' }}>No vulnerabilities detected</h2>
        <p style={{ color: '#94a3b8', maxWidth: '400px', margin: '0 auto' }}>
          The security scan completed successfully. No critical, medium, or low risk issues were found in the scanned contract logic.
        </p>
      </div>
    );
  }

  // 4. Populated List
  return (
    <div style={containerStyle}>
      <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '16px' }}>Security Findings</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {findings.map((f) => {
          const colors = getRiskColor(f.risk_level);
          return (
            <div key={f.id} style={{ 
              background: '#0f172a', 
              border: '1px solid #1e293b', 
              borderRadius: '8px',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '4px', background: colors.border }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', paddingLeft: '8px' }}>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '14px', fontWeight: 600, color: '#d4e4fa' }}>
                  {f.function_name}
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ 
                    background: '#1e293b', 
                    color: '#94a3b8', 
                    padding: '2px 8px', 
                    borderRadius: '4px', 
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase'
                  }}>
                    {formatAttackType(f.attack_type)}
                  </span>
                  <span style={{ 
                    background: colors.bg, 
                    color: colors.text, 
                    padding: '2px 8px', 
                    borderRadius: '9999px', 
                    fontSize: '11px', 
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    {f.risk_level.toUpperCase()} <span style={{ opacity: 0.8 }}>({f.risk_score}/10)</span>
                  </span>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: '13px', lineHeight: '20px', color: '#c2c6d6', paddingLeft: '8px' }}>
                {f.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
