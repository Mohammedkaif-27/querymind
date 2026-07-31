import React, { useEffect, useState } from 'react';
import { fetchDashboards, createDashboard, fetchDashboardWidgets, deleteDashboard, deleteDashboardWidget } from '../lib/api';
import type { Dashboard as IDashboard, DashboardWidget } from '../lib/api';
import { LayoutDashboard, Plus, Loader2, BarChart2, Table as TableIcon, Trash2, Hash, MapPin, TrendingUp, Activity, PieChart as PieChartIcon } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area, ScatterChart, Scatter, ZAxis, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { ConfirmModal } from './ConfirmModal';

const COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];
const TOOLTIP_STYLE = { background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '12px', color: '#e2e8f0' };

export const Dashboard: React.FC = () => {
  const [dashboards, setDashboards] = useState<IDashboard[]>([]);
  const [selectedDashboard, setSelectedDashboard] = useState<IDashboard | null>(null);
  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [loading, setLoading] = useState(true);
  const [widgetData, setWidgetData] = useState<Record<string, any[]>>({});
  const [loadingWidgets, setLoadingWidgets] = useState<Record<string, boolean>>({});
  const [newDashboardName, setNewDashboardName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    type: 'dashboard' | 'widget';
    id: string | null;
    name?: string;
  }>({ isOpen: false, type: 'dashboard', id: null });

  useEffect(() => {
    loadDashboards();
  }, []);

  const loadDashboards = async () => {
    try {
      setLoading(true);
      const data = await fetchDashboards();
      setDashboards(data);
      if (data.length > 0 && !selectedDashboard) {
        setSelectedDashboard(data[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedDashboard) {
      loadWidgets(selectedDashboard.id);
    }
  }, [selectedDashboard]);

  const loadWidgets = async (dashboardId: string) => {
    try {
      setWidgets([]);
      const data = await fetchDashboardWidgets(dashboardId);
      setWidgets(data);
      
      // Fetch data for each widget by re-running the SQL
      data.forEach(widget => fetchWidgetData(widget));
    } catch (err) {
      console.error(err);
    }
  };

  const fetchWidgetData = async (widget: DashboardWidget) => {
    setLoadingWidgets(prev => ({ ...prev, [widget.id]: true }));
    try {
      // Import dynamically to avoid circular dependency if not careful, but we can just use fetch
      const token = localStorage.getItem('supabase_access_token');
      const headers: any = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL !== undefined 
        ? import.meta.env.VITE_API_BASE_URL 
        : typeof window !== 'undefined' && window.location.port === '3000' 
        ? '' 
        : 'http://localhost:8000';

      const res = await fetch(`${API_BASE_URL}/query`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ question: widget.question, source_id: widget.source_id })
      });
      
      if (res.ok) {
        const result = await res.json();
        setWidgetData(prev => ({ ...prev, [widget.id]: result.result }));
      }
    } catch (err) {
      console.error(`Failed to fetch data for widget ${widget.id}`, err);
    } finally {
      setLoadingWidgets(prev => ({ ...prev, [widget.id]: false }));
    }
  };

  const handleCreateDashboard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDashboardName.trim()) return;
    try {
      setIsCreating(true);
      const dash = await createDashboard(newDashboardName);
      setDashboards([dash, ...dashboards]);
      setSelectedDashboard(dash);
      setNewDashboardName('');
    } catch (err) {
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteDashboard = async () => {
    if (!selectedDashboard) return;
    setConfirmModal({
      isOpen: true,
      type: 'dashboard',
      id: selectedDashboard.id,
      name: selectedDashboard.name
    });
  };

  const confirmDeleteDashboard = async (id: string) => {
    try {
      await deleteDashboard(id);
      const updated = dashboards.filter(d => d.id !== id);
      setDashboards(updated);
      setSelectedDashboard(updated.length > 0 ? updated[0] : null);
      setConfirmModal({ ...confirmModal, isOpen: false });
    } catch (err) {
      console.error(err);
      alert('Failed to delete dashboard');
    }
  };

  const handleDeleteWidget = async (widgetId: string) => {
    if (!selectedDashboard) return;
    setConfirmModal({
      isOpen: true,
      type: 'widget',
      id: widgetId
    });
  };

  const confirmDeleteWidget = async (widgetId: string) => {
    if (!selectedDashboard) return;
    try {
      await deleteDashboardWidget(selectedDashboard.id, widgetId);
      setWidgets(widgets.filter(w => w.id !== widgetId));
      setConfirmModal({ ...confirmModal, isOpen: false });
    } catch (err) {
      console.error(err);
      alert('Failed to delete widget');
    }
  };

  const confirmAction = () => {
    if (confirmModal.type === 'dashboard' && confirmModal.id) {
      confirmDeleteDashboard(confirmModal.id);
    } else if (confirmModal.type === 'widget' && confirmModal.id) {
      confirmDeleteWidget(confirmModal.id);
    }
  };

  const renderWidgetContent = (widget: DashboardWidget) => {
    const isLoading = loadingWidgets[widget.id];
    const data = widgetData[widget.id];

    if (isLoading) {
      return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '250px' }}>
          <Loader2 className="animate-spin" color="#64748b" />
        </div>
      );
    }

    if (!data || data.length === 0) {
      return <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>No data returned</div>;
    }

    const keys = Object.keys(data[0]);

    if (widget.chart_type === 'kpi') {
      const numCol = keys.find(c => typeof data[0][c] === 'number') || keys[0];
      const labelCol = keys.find(c => c !== numCol);
      const val = data[0][numCol];
      const label = labelCol ? data[0][labelCol] : numCol;
      return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '250px' }}>
          <div style={{ fontSize: '14px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
            {label}
          </div>
          <div style={{ fontSize: '56px', fontWeight: 800, background: 'linear-gradient(135deg, #38bdf8, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            {typeof val === 'number' ? val.toLocaleString() : val}
          </div>
        </div>
      );
    }

    if (keys.length < 2 || widget.chart_type === 'table') {
      // Render Table
      return (
        <div style={{ overflowX: 'auto', maxHeight: '250px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#94a3b8' }}>
                {keys.map(k => <th key={k} style={{ padding: '8px' }}>{k}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.map((row, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  {keys.map(k => <td key={k} style={{ padding: '8px' }}>{String(row[k])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    const labelKey = keys[0];
    const valueKeys = keys.slice(1).filter(c => data.some(r => typeof r[c] === 'number'));
    const valueKey = valueKeys[0] || keys[1];

    if (widget.chart_type === 'scatter') {
      const latCol = keys.find(c => c.toLowerCase().includes('lat')) || keys[1];
      const lonCol = keys.find(c => c.toLowerCase().includes('lon') || c.toLowerCase().includes('lng')) || keys[0];
      const metricCol = valueKeys.find(c => c !== latCol && c !== lonCol) || valueKeys[0];
      return (
        <ResponsiveContainer width="100%" height={250}>
          <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={lonCol} type="number" name="Longitude" stroke="#64748b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
            <YAxis dataKey={latCol} type="number" name="Latitude" stroke="#64748b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
            {metricCol && <ZAxis dataKey={metricCol} range={[20, 400]} name={metricCol} />}
            <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={TOOLTIP_STYLE} />
            <Scatter name="Data" data={data} fill="#06b6d4" fillOpacity={0.6} />
          </ScatterChart>
        </ResponsiveContainer>
      );
    }

    if (widget.chart_type === 'pie') {
      return (
        <ResponsiveContainer width="100%" height={250}>
          <PieChart>
            <Pie data={data} dataKey={valueKey} nameKey={labelKey} cx="50%" cy="50%" outerRadius={80} innerRadius={40}>
              {data.map((_, idx) => <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} />
          </PieChart>
        </ResponsiveContainer>
      );
    }

    if (widget.chart_type === 'line') {
      return (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 10 }} />
            <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Line type="monotone" dataKey={valueKey} stroke={COLORS[0]} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      );
    }

    if (widget.chart_type === 'area') {
      return (
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 10 }} />
            <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Area type="monotone" dataKey={valueKey} stroke={COLORS[1]} fill={COLORS[1]} fillOpacity={0.2} />
          </AreaChart>
        </ResponsiveContainer>
      );
    }

    // Default to Bar
    return (
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 10 }} />
          <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(99,102,241,0.08)' }} />
          <Bar dataKey={valueKey} fill={COLORS[0]} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '60px' }}>
        <Loader2 className="animate-spin" size={32} color="#06b6d4" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1280px', margin: '24px auto', padding: '0 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.type === 'dashboard' ? 'Delete Dashboard' : 'Remove Widget'}
        message={
          confirmModal.type === 'dashboard' 
            ? `Are you sure you want to delete the dashboard "${confirmModal.name}" and all its widgets?`
            : 'Are you sure you want to remove this widget from the dashboard?'
        }
        confirmText="Delete"
        onConfirm={confirmAction}
        onClose={() => setConfirmModal({ ...confirmModal, isOpen: false, id: null })}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <LayoutDashboard size={24} color="#6366f1" />
          <h2 style={{ fontSize: '20px', fontWeight: 600 }}>Dashboards</h2>
        </div>

        {dashboards.length > 0 && (
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <select
              value={selectedDashboard?.id || ''}
              onChange={(e) => setSelectedDashboard(dashboards.find(d => d.id === e.target.value) || null)}
              className="input-field"
              style={{ width: '250px', padding: '8px 12px' }}
            >
              {dashboards.map(d => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            
            <button
              onClick={handleDeleteDashboard}
              className="btn-secondary"
              style={{ padding: '8px', color: '#f43f5e', borderColor: 'rgba(244, 63, 94, 0.3)' }}
              title="Delete Dashboard"
            >
              <Trash2 size={16} />
            </button>
          </div>
        )}
      </div>

      {!dashboards.length ? (
        <div className="glass-panel" style={{ padding: '40px', textAlign: 'center' }}>
          <LayoutDashboard size={48} color="#64748b" style={{ margin: '0 auto 16px', opacity: 0.5 }} />
          <h3 style={{ fontSize: '18px', fontWeight: 500, marginBottom: '8px' }}>No Dashboards Yet</h3>
          <p style={{ color: '#94a3b8', marginBottom: '24px' }}>Create a dashboard to save your favorite charts and queries.</p>
          <form onSubmit={handleCreateDashboard} style={{ display: 'flex', gap: '10px', justifyContent: 'center', maxWidth: '400px', margin: '0 auto' }}>
            <input
              type="text"
              value={newDashboardName}
              onChange={(e) => setNewDashboardName(e.target.value)}
              placeholder="Dashboard Name (e.g. Sales KPI)"
              className="input-field"
              required
            />
            <button type="submit" className="btn-primary" disabled={isCreating}>
              <Plus size={16} /> Create
            </button>
          </form>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(450px, 1fr))', gap: '20px' }}>
            {widgets.map(widget => (
              <div key={widget.id} className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', gap: '12px' }}>
                  <h4 style={{ fontSize: '14px', fontWeight: 500, lineHeight: 1.4, flex: 1 }}>{widget.question}</h4>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {widget.chart_type === 'table' && <TableIcon size={12} />}
                      {widget.chart_type === 'kpi' && <Hash size={12} />}
                      {widget.chart_type === 'scatter' && <MapPin size={12} />}
                      {widget.chart_type === 'line' && <TrendingUp size={12} />}
                      {widget.chart_type === 'area' && <Activity size={12} />}
                      {widget.chart_type === 'pie' && <PieChartIcon size={12} />}
                      {widget.chart_type === 'bar' && <BarChart2 size={12} />}
                      {widget.chart_type}
                    </div>
                    <button
                      onClick={() => handleDeleteWidget(widget.id)}
                      style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', padding: '4px' }}
                      title="Remove Widget"
                      onMouseEnter={e => e.currentTarget.style.color = '#f43f5e'}
                      onMouseLeave={e => e.currentTarget.style.color = '#64748b'}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                
                <div style={{ flex: 1, minHeight: '250px' }}>
                  {renderWidgetContent(widget)}
                </div>
              </div>
            ))}
          </div>

          {widgets.length === 0 && (
            <div className="glass-panel" style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
              No widgets saved to this dashboard yet.<br/><br/>
              Go to the <strong>Query Workspace</strong>, run a query, and click <strong>"Save to Dashboard"</strong> to add one!
            </div>
          )}
        </>
      )}
    </div>
  );
};
