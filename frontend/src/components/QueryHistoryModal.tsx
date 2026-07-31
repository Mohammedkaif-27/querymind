import type { QueryHistoryItem } from '../lib/api';
import { X, History, CheckCircle, AlertCircle, Clock, ArrowRight } from 'lucide-react';

interface QueryHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  history: QueryHistoryItem[];
  onSelectQuery: (question: string) => void;
}

export const QueryHistoryModal: React.FC<QueryHistoryModalProps> = ({
  isOpen,
  onClose,
  history,
  onSelectQuery,
}) => {
  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(8px)' }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '750px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: '24px', position: 'relative' }}>
        
        <button onClick={onClose} style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
          <X size={20} />
        </button>

        <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <History color="#6366f1" size={22} />
          Query History ({history.length})
        </h2>
        <p style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
          Review previous natural language queries, generated SQL statements, and execution performance.
        </p>

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {history.length === 0 ? (
            <p style={{ fontSize: '13px', color: '#64748b', fontStyle: 'italic', textAlign: 'center', padding: '40px 0' }}>
              No query history found. Start asking questions to populate your log!
            </p>
          ) : (
            history.map((item) => (
              <div
                key={item.id}
                style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '14px', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.05)', display: 'flex', flexDirection: 'column', gap: '8px' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
                    {item.question}
                  </span>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className={`badge ${item.success ? 'badge-success' : 'badge-danger'}`}>
                      {item.success ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
                      {item.success ? 'Success' : 'Failed'}
                    </span>
                    <button
                      className="btn-secondary"
                      onClick={() => { onSelectQuery(item.question); onClose(); }}
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                    >
                      Run <ArrowRight size={12} />
                    </button>
                  </div>
                </div>

                {item.generated_sql && (
                  <pre style={{ background: 'rgba(0, 0, 0, 0.4)', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', color: '#38bdf8', overflowX: 'auto', margin: 0 }}>
                    {item.generated_sql}
                  </pre>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px', color: '#64748b' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={12} /> {Math.round(item.latency_ms)}ms
                  </span>
                  <span>Rows: {item.row_count}</span>
                  <span>Date: {new Date(item.created_at).toLocaleString()}</span>
                </div>
              </div>
            ))
          )}
        </div>

      </div>
    </div>
  );
};
