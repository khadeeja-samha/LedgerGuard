'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState, useCallback, useRef } from 'react';

// ForceGraph2D requires dynamic import with SSR disabled
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

export default function GraphViewer({ contractId }: { contractId: string }) {
  const [graphData, setGraphData] = useState<{ nodes: any[]; links: any[] } | null>(null);
  const [error, setError] = useState('');
  const [selectedNode, setSelectedNode] = useState<any>(null);

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/audit/${contractId}/graph`);
        if (!res.ok) {
          throw new Error(`Failed to fetch graph: ${res.status}`);
        }
        const data = await res.json();
        
        // Transform the backend JSON into ForceGraph2D's { nodes, links } format
        const nodes: any[] = [];
        const links: any[] = [];

        // Add StateVariable nodes
        data.state_variables?.forEach((sv: any) => {
          nodes.push({
            id: sv.name,
            label: sv.name,
            group: 'StateVariable',
            properties: sv
          });
        });

        // Add Function nodes and their implicit READS/WRITES edges
        data.functions?.forEach((fn: any) => {
          nodes.push({
            id: fn.name,
            label: fn.name,
            group: 'Function',
            properties: fn
          });

          fn.reads?.forEach((svName: string) => {
            links.push({
              source: fn.name,
              target: svName,
              label: 'READS',
              color: '#999'
            });
          });

          fn.writes?.forEach((svName: string) => {
            links.push({
              source: fn.name,
              target: svName,
              label: 'WRITES',
              color: '#555'
            });
          });
        });

        // Add explicit Reentrancy edges (MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE)
        data.edges?.forEach((edge: any) => {
          if (edge.type === 'MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE') {
            links.push({
              source: edge.from,
              target: edge.to,
              label: 'REENTRANCY_RISK',
              color: 'red'
            });
          }
        });

        setGraphData({ nodes, links });
      } catch (err: any) {
        setError(err.message);
      }
    };

    if (contractId) {
      fetchGraph();
    }
  }, [contractId]);

  if (error) {
    return <div style={{ color: 'red' }}>Error loading graph: {error}</div>;
  }

  if (!graphData) {
    return <div>Loading graph...</div>;
  }

  return (
    <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem', border: '1px solid #ccc', borderRadius: '8px', overflow: 'hidden' }}>
      {/* Main Graph View */}
      <div style={{ flex: 1, height: '600px', backgroundColor: '#fafafa' }}>
        <ForceGraph2D
          graphData={graphData}
          nodeLabel="label"
          nodeColor={(node) => {
            if (node.group === 'Function') return '#4f46e5'; // Indigo
            if (node.group === 'StateVariable') return '#10b981'; // Emerald
            return 'gray';
          }}
          nodeVal={(node) => (node.group === 'Function' ? 5 : 3)}
          linkColor="color"
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          linkWidth={(link) => (link.color === 'red' ? 3 : 1)}
          onNodeClick={(node) => setSelectedNode(node)}
        />
      </div>

      {/* Side Panel for Click-to-Inspect */}
      <div style={{ width: '300px', padding: '1rem', backgroundColor: '#fff', borderLeft: '1px solid #ccc', overflowY: 'auto' }}>
        <h3>Inspector</h3>
        {!selectedNode ? (
          <p style={{ color: '#666', fontSize: '0.9rem' }}>Click on a node to inspect its properties.</p>
        ) : (
          <div>
            <h4 style={{ margin: '0 0 0.5rem 0', color: selectedNode.group === 'Function' ? '#4f46e5' : '#10b981' }}>
              {selectedNode.label} ({selectedNode.group})
            </h4>
            <div style={{ fontSize: '0.9rem' }}>
              {Object.entries(selectedNode.properties).map(([key, value]) => {
                // Ignore nested arrays for simple display, or join them
                let displayValue = String(value);
                if (Array.isArray(value)) {
                  displayValue = value.length > 0 ? value.join(', ') : 'none';
                }
                return (
                  <div key={key} style={{ marginBottom: '0.5rem' }}>
                    <strong>{key}:</strong> {displayValue}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
