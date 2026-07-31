import { useState } from 'react';
import type { User } from '@supabase/supabase-js';
import type { DataSource } from '../lib/api';
import { uploadSource, connectSource, deleteSource } from '../lib/api';
import { X, Upload, Database, Trash2, FileSpreadsheet, Server, CheckCircle, AlertCircle, LogIn } from 'lucide-react';
import { ConfirmModal } from './ConfirmModal';

interface SourceManagerProps {
  isOpen: boolean;
  onClose: () => void;
  sources: DataSource[];
  onRefreshSources: () => void;
  onSelectSource: (id: string | null) => void;
  user: User | null;
  onOpenAuth: () => void;
}

export const SourceManager: React.FC<SourceManagerProps> = ({
  isOpen,
  onClose,
  sources,
  onRefreshSources,
  onSelectSource,
  user,
  onOpenAuth,
}) => {
  const [activeTab, setActiveTab] = useState<'upload' | 'connect'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState('');
  
  const [dbName, setDbName] = useState('');
  const [dbUri, setDbUri] = useState('');
  const [dbType, setDbType] = useState<'postgres' | 'mysql'>('postgres');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [confirmModalState, setConfirmModalState] = useState<{isOpen: boolean, sourceId: string | null}>({isOpen: false, sourceId: null});

  if (!isOpen) return null;

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      setError('Please Sign In / Register first to upload custom data sources.');
      return;
    }
    if (!file) {
      setError('Please select a CSV or XLSX file to upload.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const source = await uploadSource(file, datasetName || undefined);
      setSuccessMsg(`Successfully uploaded dataset "${source.name}"!`);
      setFile(null);
      setDatasetName('');
      onRefreshSources();
      onSelectSource(source.id);
    } catch (err: any) {
      setError(err.message || 'File upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleConnectDb = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      setError('Please Sign In / Register first to connect external databases.');
      return;
    }
    if (!dbUri || !dbName) {
      setError('Please provide a connection name and database URI.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const source = await connectSource({ name: dbName, uri: dbUri, type: dbType });
      setSuccessMsg(`Successfully connected database "${source.name}" (${source.table_count} tables indexed)!`);
      setDbName('');
      setDbUri('');
      onRefreshSources();
      onSelectSource(source.id);
    } catch (err: any) {
      setError(err.message || 'Database connection failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    setConfirmModalState({ isOpen: true, sourceId: id });
  };

  const confirmDelete = async () => {
    if (!confirmModalState.sourceId) return;
    try {
      await deleteSource(confirmModalState.sourceId);
      onRefreshSources();
    } catch (err: any) {
      alert(err.message || 'Failed to delete source');
    } finally {
      setConfirmModalState({ isOpen: false, sourceId: null });
    }
  };

  return (
    <>
    <ConfirmModal 
      isOpen={confirmModalState.isOpen}
      title="Delete Data Source"
      message="Are you sure you want to delete this data source? This action cannot be undone."
      confirmText="Delete"
      onConfirm={confirmDelete}
      onClose={() => setConfirmModalState({ isOpen: false, sourceId: null })}
    />
    <div style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(8px)' }}>
      <div className="glass-panel" style={{ width: '100%', maxWidth: '650px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: '24px', position: 'relative', overflow: 'hidden' }}>
        
        <button onClick={onClose} style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
          <X size={20} />
        </button>

        <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Database color="#06b6d4" size={22} />
          Data Sources Management
        </h2>
        <p style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
          Upload custom CSV/XLSX files or connect external SQL databases for semantic querying.
        </p>

        {!user && (
          <div className="glass-panel" style={{ padding: '12px 16px', marginBottom: '16px', borderColor: 'rgba(99, 102, 241, 0.3)', background: 'rgba(99, 102, 241, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '13px', color: '#cbd5e1' }}>
              Sign in to upload custom CSV/XLSX datasets & save query history.
            </span>
            <button className="btn-primary" onClick={() => { onClose(); onOpenAuth(); }} style={{ padding: '6px 12px', fontSize: '12px' }}>
              <LogIn size={14} /> Sign In
            </button>
          </div>
        )}

        {/* Tab Buttons */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(255, 255, 255, 0.1)', paddingBottom: '12px' }}>
          <button
            onClick={() => { setActiveTab('upload'); setError(null); setSuccessMsg(null); }}
            className={`btn-secondary ${activeTab === 'upload' ? 'btn-primary' : ''}`}
            style={{ fontSize: '13px', padding: '8px 14px' }}
          >
            <FileSpreadsheet size={16} /> Upload CSV / XLSX
          </button>
          <button
            onClick={() => { setActiveTab('connect'); setError(null); setSuccessMsg(null); }}
            className={`btn-secondary ${activeTab === 'connect' ? 'btn-primary' : ''}`}
            style={{ fontSize: '13px', padding: '8px 14px' }}
          >
            <Server size={16} /> Connect SQL Database
          </button>
        </div>

        {error && (
          <div className="badge badge-danger" style={{ borderRadius: '8px', padding: '10px', marginBottom: '16px', width: '100%' }}>
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {successMsg && (
          <div className="badge badge-success" style={{ borderRadius: '8px', padding: '10px', marginBottom: '16px', width: '100%' }}>
            <CheckCircle size={15} /> {successMsg}
          </div>
        )}

        {/* Tab 1: Upload CSV/XLSX */}
        {activeTab === 'upload' && (
          <form onSubmit={handleFileUpload} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>Dataset Name (Optional)</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Q3 Sales Data"
                value={datasetName}
                onChange={(e) => setDatasetName(e.target.value)}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>File (.csv or .xlsx)</label>
              <input
                type="file"
                accept=".csv, .xlsx, .xls"
                className="input-field"
                style={{ padding: '8px' }}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={loading} style={{ justifyContent: 'center', marginTop: '6px' }}>
              <Upload size={16} />
              {loading ? 'Ingesting & Indexing File...' : 'Upload & Build Schema Index'}
            </button>
          </form>
        )}

        {/* Tab 2: Connect DB */}
        {activeTab === 'connect' && (
          <form onSubmit={handleConnectDb} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>Connection Name</label>
                <input
                  type="text"
                  required
                  className="input-field"
                  placeholder="e.g. Production Analytics DB"
                  value={dbName}
                  onChange={(e) => setDbName(e.target.value)}
                />
              </div>
              <div style={{ width: '140px' }}>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>Dialect</label>
                <select
                  value={dbType}
                  onChange={(e) => setDbType(e.target.value as any)}
                  className="input-field"
                  style={{ cursor: 'pointer' }}
                >
                  <option value="postgres">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>SQLAlchemy Connection URI</label>
              <input
                type="text"
                required
                className="input-field"
                placeholder="postgresql://user:password@host:5432/dbname"
                value={dbUri}
                onChange={(e) => setDbUri(e.target.value)}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={loading} style={{ justifyContent: 'center', marginTop: '6px' }}>
              <Server size={16} />
              {loading ? 'Testing & Indexing Schema...' : 'Connect & Index Database'}
            </button>
          </form>
        )}

        {/* Existing Data Sources List */}
        <div style={{ marginTop: '24px', flex: 1, overflowY: 'auto' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#cbd5e1', marginBottom: '10px' }}>
            Registered Data Sources ({sources.length})
          </h3>

          {sources.length === 0 ? (
            <p style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic' }}>
              No custom datasets uploaded yet. You can query the default Northwind database anytime.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sources.map((s) => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(15, 23, 42, 0.6)', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>{s.name}</div>
                    <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', gap: '12px', marginTop: '2px' }}>
                      <span>Type: <strong style={{ color: '#06b6d4' }}>{s.type.toUpperCase()}</strong></span>
                      <span>Tables: {s.table_count}</span>
                      <span>Created: {new Date(s.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <button className="btn-danger" onClick={() => handleDelete(s.id)}>
                    <Trash2 size={14} /> Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
    </>
  );
}
