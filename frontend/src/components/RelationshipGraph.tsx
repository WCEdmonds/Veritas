'use client';

/**
 * Relationship graph renderer for conflict-of-interest findings.
 *
 * Consumes the `relationship_graph` object emitted by the backend
 * ConflictOfInterestTool: entity nodes (applicant side, intermediaries,
 * counterparties) plus shared-identifier nodes (an address, a phone number,
 * a bank account) that make the hidden link visible, and edges labelled by
 * relationship type and confidence.
 *
 * Pure SVG, no layout library: nodes are placed in columns by side so the
 * eye reads left to right, applicant → intermediaries → counterparty.
 */

export interface GraphNode {
  id: string;
  label: string;
  kind: 'person' | 'organization' | 'identifier';
  role?: string;
  side: 'applicant' | 'intermediary' | 'counterparty' | 'identifier';
  flagged?: boolean;
  on_path?: boolean;
  identifier_type?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: string;
  confidence: number;
  structural?: boolean;
  label?: string;
  evidence?: string[];
}

export interface RelationshipGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const COLUMN_X: Record<GraphNode['side'], number> = {
  applicant: 0.12,
  intermediary: 0.4,
  identifier: 0.58,
  counterparty: 0.86,
};

const IDENTIFIER_ICON: Record<string, string> = {
  residential_address: '⌂',
  address: '⌂',
  phone: '☎',
  email: '@',
  bank_account: '$',
  tax_id: '#',
  private_domain: '🌐',
  device: '▣',
  ip_address: '◎',
};

function truncate(text: string, max = 28): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export default function RelationshipGraph({
  data,
  width = 900,
  height,
}: {
  data: RelationshipGraphData;
  width?: number;
  height?: number;
}) {
  if (!data || !data.nodes?.length) return null;

  // Only draw nodes that participate in at least one edge, plus the applicant.
  const connected = new Set<string>();
  data.edges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });
  const nodes = data.nodes.filter((n) => connected.has(n.id) || n.side === 'applicant');

  const bySide: Record<string, GraphNode[]> = { applicant: [], intermediary: [], identifier: [], counterparty: [] };
  nodes.forEach((n) => bySide[n.side]?.push(n));
  // Flagged counterparties first so the most important rows sit at the top.
  bySide.counterparty.sort((a, b) => Number(b.flagged) - Number(a.flagged));

  const rows = Math.max(...Object.values(bySide).map((list) => list.length), 1);
  const h = height ?? Math.max(260, rows * 64 + 60);
  const pos = new Map<string, { x: number; y: number }>();
  (Object.keys(bySide) as GraphNode['side'][]).forEach((side) => {
    const list = bySide[side];
    list.forEach((n, i) => {
      const y = ((i + 1) / (list.length + 1)) * (h - 40) + 20;
      pos.set(n.id, { x: COLUMN_X[side] * width, y });
    });
  });

  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const edges = data.edges.filter((e) => pos.has(e.source) && pos.has(e.target));

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${h}`}
        width="100%"
        style={{ minWidth: 640, maxWidth: width }}
        role="img"
        aria-label="Relationship graph showing links between the applicant and its contractors and vendors"
      >
        <defs>
          <marker id="rg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
          </marker>
        </defs>

        {/* Column headers */}
        {(['applicant', 'intermediary', 'counterparty'] as const).map((side) => (
          <text key={side} x={COLUMN_X[side] * width} y={14} textAnchor="middle" fontSize={11} fill="#64748b" fontWeight={600}>
            {side === 'applicant' ? 'APPLICANT SIDE' : side === 'intermediary' ? 'HIDDEN LINKS' : 'CONTRACTORS / VENDORS'}
          </text>
        ))}

        {/* Edges */}
        {edges.map((e, i) => {
          const a = pos.get(e.source)!;
          const b = pos.get(e.target)!;
          const isIdentifier = e.kind === 'has_identifier';
          const strong = e.confidence >= 0.8;
          const stroke = isIdentifier ? '#94a3b8' : strong ? '#dc2626' : '#f59e0b';
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={`${e.source}-${e.target}-${i}`}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={stroke}
                strokeWidth={isIdentifier ? 1 : strong ? 2.2 : 1.5}
                strokeDasharray={isIdentifier ? '3 3' : e.structural ? undefined : '6 3'}
                markerEnd={isIdentifier ? undefined : 'url(#rg-arrow)'}
                opacity={0.9}
              >
                <title>
                  {e.label || e.kind} · {(e.confidence * 100).toFixed(0)}%{e.evidence?.length ? `\n${e.evidence.join('\n')}` : ''}
                </title>
              </line>
              {!isIdentifier && (
                <text x={mx} y={my - 5} textAnchor="middle" fontSize={10} fill={stroke} style={{ paintOrder: 'stroke', stroke: '#fff', strokeWidth: 3 }}>
                  {truncate(e.label || e.kind.replace(/_/g, ' '), 26)} {(e.confidence * 100).toFixed(0)}%
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const p = pos.get(n.id)!;
          const fill = n.flagged ? '#fee2e2' : n.side === 'applicant' ? '#dbeafe' : n.kind === 'identifier' ? '#f1f5f9' : '#f8fafc';
          const stroke = n.flagged ? '#dc2626' : n.side === 'applicant' ? '#2563eb' : n.on_path ? '#f59e0b' : '#94a3b8';
          const label = truncate(n.label);
          const w = Math.max(90, label.length * 6.4 + 24);
          return (
            <g key={n.id}>
              <title>
                {n.label}
                {n.role ? ` (${n.role.replace(/_/g, ' ')})` : ''}
              </title>
              {n.kind === 'identifier' ? (
                <rect x={p.x - w / 2} y={p.y - 13} width={w} height={26} rx={13} fill={fill} stroke={stroke} strokeWidth={1} />
              ) : n.kind === 'person' ? (
                <rect x={p.x - w / 2} y={p.y - 16} width={w} height={32} rx={16} fill={fill} stroke={stroke} strokeWidth={n.flagged || n.on_path ? 2 : 1.2} />
              ) : (
                <rect x={p.x - w / 2} y={p.y - 16} width={w} height={32} rx={4} fill={fill} stroke={stroke} strokeWidth={n.flagged || n.on_path ? 2 : 1.2} />
              )}
              <text x={p.x} y={p.y + 4} textAnchor="middle" fontSize={11} fill="#0f172a" fontWeight={n.flagged ? 600 : 400}>
                {n.kind === 'identifier' ? `${IDENTIFIER_ICON[n.identifier_type || ''] || '•'} ` : ''}
                {label}
              </text>
              {nodeById.get(n.id)?.role && n.kind !== 'identifier' && (
                <text x={p.x} y={p.y + 27} textAnchor="middle" fontSize={9} fill="#64748b">
                  {n.role!.replace(/_/g, ' ')}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
        <span><span className="inline-block w-3 h-0.5 bg-red-600 align-middle mr-1" /> confirmed link (≥80%)</span>
        <span><span className="inline-block w-3 h-0.5 bg-amber-500 align-middle mr-1" /> needs verification</span>
        <span><span className="inline-block w-3 border-t border-dashed border-slate-400 align-middle mr-1" /> shared identifier</span>
        <span>solid = registry / vital record · dashed = inferred</span>
      </div>
    </div>
  );
}
