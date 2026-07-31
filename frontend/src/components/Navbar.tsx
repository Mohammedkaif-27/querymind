import type { User } from '@supabase/supabase-js';
import { Database, LogIn, LogOut, History, PlusCircle, Activity, Sparkles } from 'lucide-react';
import type { DataSource, HealthResponse } from '../lib/api';

interface NavbarProps {
  user: User | null;
  sources: DataSource[];
  activeSourceId: string | null;
  onSelectSource: (id: string | null) => void;
  onOpenAuth: () => void;
  onSignOut: () => void;
  onOpenSourceManager: () => void;
  onOpenHistory: () => void;
  health: HealthResponse | null;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  sources,
  activeSourceId,
  onSelectSource,
  onOpenAuth,
  onSignOut,
  onOpenSourceManager,
  onOpenHistory,
  health,
}) => {
  const isHealthy = health?.status === 'healthy';

  return (
    <header className="glass-panel" style={{ borderRadius: 0, borderTop: 0, borderLeft: 0, borderRight: 0, padding: '12px 24px', position: 'sticky', top: 0, zIndex: 50 }}>
      <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', padding: '8px', borderRadius: '10px', display: 'flex' }}>
            <Sparkles size={22} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 700, background: 'linear-gradient(90deg, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              QueryMind
            </h1>
            <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500, letterSpacing: '0.5px' }}>
              POWERED BY GROQ & SUPABASE
            </span>
          </div>
        </div>

        {/* Source selector & status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          
          {/* Data Source dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(15, 23, 42, 0.8)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
            <Database size={16} color="#06b6d4" />
            <select
              value={activeSourceId || ''}
              onChange={(e) => onSelectSource(e.target.value || null)}
              style={{ background: 'transparent', color: '#f8fafc', border: 'none', outline: 'none', fontSize: '13px', cursor: 'pointer' }}
            >
              <option value="" style={{ background: '#0f172a' }}>Northwind Database (Default Sample)</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id} style={{ background: '#0f172a' }}>
                  {s.name} ({s.type.toUpperCase()})
                </option>
              ))}
            </select>
          </div>

          {/* Manage Sources button */}
          <button className="btn-secondary" onClick={onOpenSourceManager} style={{ padding: '7px 12px', fontSize: '13px' }}>
            <PlusCircle size={15} />
            Data Sources
          </button>

          {/* Query History button */}
          {user && (
            <button className="btn-secondary" onClick={onOpenHistory} style={{ padding: '7px 12px', fontSize: '13px' }}>
              <History size={15} />
              History
            </button>
          )}

          {/* Health indicator badge */}
          <div className={`badge ${isHealthy ? 'badge-success' : 'badge-warning'}`} title={`Supabase: ${health?.components.supabase.status}, Chroma: ${health?.components.chroma.status}`}>
            <Activity size={12} />
            <span>{isHealthy ? 'System Healthy' : 'Degraded'}</span>
          </div>

          {/* Auth Button */}
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ fontSize: '13px', color: '#94a3b8', background: 'rgba(255,255,255,0.05)', padding: '6px 12px', borderRadius: '20px' }}>
                {user.email}
              </div>
              <button className="btn-secondary" onClick={onSignOut} style={{ padding: '7px 12px', fontSize: '13px' }}>
                <LogOut size={15} />
                Sign Out
              </button>
            </div>
          ) : (
            <button className="btn-primary" onClick={onOpenAuth} style={{ padding: '7px 16px', fontSize: '13px' }}>
              <LogIn size={15} />
              Sign In / Register
            </button>
          )}

        </div>

      </div>
    </header>
  );
};
