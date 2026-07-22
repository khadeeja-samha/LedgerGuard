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
  status: string;
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

  if (status === 'failed' || error) {
    return (
      <div className="w-full mt-4 text-error p-4 bg-[#93000a]/20 border border-error rounded">
        <strong>Audit failed to complete:</strong> {error || 'An internal error occurred.'}
      </div>
    );
  }

  if (loading) {
    return <div className="text-on-surface-variant p-4">Loading findings...</div>;
  }

  if (status === 'completed' && findings.length === 0) {
    return (
      <div className="w-full mt-4 flex flex-col items-center justify-center p-12 bg-surface-container-low border border-outline-variant rounded-xl">
        <div className="text-4xl mb-4">🛡️</div>
        <h2 className="font-headline-md text-headline-md font-bold mb-2 text-primary">No vulnerabilities detected</h2>
        <p className="text-on-surface-variant max-w-md text-center font-body-md text-body-md">
          The security scan completed successfully. No critical, medium, or low risk issues were found in the scanned contract logic.
        </p>
      </div>
    );
  }

  // Count stats
  const highCount = findings.filter(f => f.risk_level.toUpperCase() === 'HIGH').length;
  const unknownCount = findings.filter(f => f.risk_level.toUpperCase() === 'UNKNOWN').length;
  const lowCount = findings.filter(f => f.risk_level.toUpperCase() === 'LOW').length;

  return (
    <div className="w-full mt-8">
      {/* Header Section */}
      <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="material-symbols-outlined text-on-surface-variant text-sm">folder_open</span>
            <span className="font-code-md text-code-md text-on-surface-variant">Target Contract / Function Scan</span>
          </div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface m-0">Vulnerability Findings</h2>
        </div>

        {/* Quick Stats / Progress */}
        <div className="flex gap-4">
          <div className="bg-surface-container-low border border-outline-variant rounded p-3 flex flex-col items-center min-w-[80px]">
            <span className="font-headline-sm text-headline-sm text-error">{highCount}</span>
            <span className="font-label-caps text-label-caps text-on-surface-variant mt-1">HIGH</span>
          </div>
          <div className="bg-surface-container-low border border-outline-variant rounded p-3 flex flex-col items-center min-w-[80px]">
            <span className="font-headline-sm text-headline-sm text-tertiary">{unknownCount}</span>
            <span className="font-label-caps text-label-caps text-on-surface-variant mt-1">UNKNOWN</span>
          </div>
          <div className="bg-surface-container-low border border-outline-variant rounded p-3 flex flex-col items-center min-w-[80px]">
            <span className="font-headline-sm text-headline-sm text-primary">{lowCount}</span>
            <span className="font-label-caps text-label-caps text-on-surface-variant mt-1">LOW</span>
          </div>
        </div>
      </div>

      {/* Findings List (Bento-style stacked cards) */}
      <div className="flex flex-col gap-4 max-w-5xl">
        {findings.map((f) => {
          let themeColor = 'outline-variant';
          let bgColor = 'bg-surface-container-low';
          let hoverBorder = 'hover:border-outline-variant';
          let pillBg = 'bg-surface';
          let pillText = 'text-on-surface';
          let pillBorder = 'border-outline-variant';

          switch (f.risk_level.toUpperCase()) {
            case 'HIGH':
              themeColor = 'bg-error';
              hoverBorder = 'hover:border-error';
              pillBg = 'bg-[#ffb4ab]/10';
              pillText = 'text-error';
              pillBorder = 'border-[#ffb4ab]/20';
              break;
            case 'UNKNOWN':
              themeColor = 'bg-tertiary';
              hoverBorder = 'hover:border-tertiary';
              pillBg = 'bg-[#bcc7de]/10';
              pillText = 'text-tertiary';
              pillBorder = 'border-[#bcc7de]/20';
              break;
            case 'LOW':
              themeColor = 'bg-primary';
              hoverBorder = 'hover:border-primary';
              pillBg = 'bg-[#adc6ff]/10';
              pillText = 'text-primary';
              pillBorder = 'border-[#adc6ff]/20';
              break;
          }

          return (
            <div key={f.id} className={`bg-surface-container-low border border-outline-variant rounded relative flex flex-col transition-colors duration-200 group ${hoverBorder}`}>
              <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${themeColor}`}></div>
              <div className="p-6 pl-8">
                
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className={`${pillBg} ${pillText} font-label-caps text-label-caps px-2 py-1 rounded-full border ${pillBorder}`}>
                      {f.risk_level.toUpperCase()} RISK
                    </span>
                    <span className="bg-surface-container-highest text-on-surface font-label-caps text-label-caps px-2 py-1 rounded border border-outline-variant flex items-center gap-1">
                      <span className="material-symbols-outlined text-[14px]">speed</span> Score {f.risk_score}
                    </span>
                    <span className="text-on-surface-variant font-body-sm text-body-sm px-2 py-1 bg-surface-container rounded">
                      {formatAttackType(f.attack_type)}
                    </span>
                  </div>
                </div>

                <div className="mb-4">
                  <h3 className="font-code-md text-code-md text-inverse-surface mb-2 bg-surface p-2 rounded inline-block border border-outline-variant">
                    {f.function_name}
                  </h3>
                  <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl leading-relaxed">
                    {f.description}
                  </p>
                </div>

              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
