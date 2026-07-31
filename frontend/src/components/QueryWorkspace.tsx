import { useState, useRef, useCallback, useEffect } from 'react';
import { fetchDashboards, createDashboard, saveDashboardWidget } from '../lib/api';
import type { Dashboard as IDashboard } from '../lib/api';
import type { QueryResponse } from '../lib/api';
import { Send, Code, Table, BarChart2, MessageSquare, Copy, Check, AlertTriangle, Sparkles, RefreshCw, PieChart as PieChartIcon, TrendingUp, Activity, FileJson, FileSpreadsheet, Image, Save, X, Hash, MapPin } from 'lucide-react';
import { toPng } from 'html-to-image';
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area, ScatterChart, Scatter, ZAxis, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

export type ChartVariant = 'bar' | 'line' | 'pie' | 'area' | 'kpi' | 'scatter';

interface QueryWorkspaceProps {
  sampleQuestions: string[];
  activeQuestion: string;
  setActiveQuestion: (q: string) => void;
  onExecuteQuery: (question: string) => void;
  queryResponse: QueryResponse | null;
  loading: boolean;
  error: string | null;
}

const COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316'];

const TOOLTIP_STYLE = {
  background: '#0f172a',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '8px',
  fontSize: '12px',
  color: '#e2e8f0',
};

export const QueryWorkspace: React.FC<QueryWorkspaceProps> = ({
  sampleQuestions,
  activeQuestion,
  setActiveQuestion,
  onExecuteQuery,
  queryResponse,
  loading,
  error,
}) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'table' | 'chart' | 'sql'>('table');
  const [chartVariant, setChartVariant] = useState<ChartVariant>('bar');
  const chartContainerRef = useRef<HTMLDivElement>(null);

  // Dashboard state
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [dashboards, setDashboards] = useState<IDashboard[]>([]);
  const [selectedDashboardId, setSelectedDashboardId] = useState<string>('');
  const [newDashboardName, setNewDashboardName] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isSaveModalOpen) {
      loadDashboards();
    }
  }, [isSaveModalOpen]);

  useEffect(() => {
    if (queryResponse) {
      setChartVariant(getInitialChartVariant());
    }
  }, [queryResponse]);

  const loadDashboards = async () => {
    try {
      const data = await fetchDashboards();
      setDashboards(data);
      if (data.length > 0 && !selectedDashboardId) {
        setSelectedDashboardId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load dashboards', err);
    }
  };

  const handleSaveToDashboard = async () => {
    if (!queryResponse) return;
    try {
      setIsSaving(true);
      let dashId = selectedDashboardId;
      
      // If user typed a new name and selected "Create New" or has no dashboards
      if (selectedDashboardId === 'new' || dashboards.length === 0) {
        if (!newDashboardName.trim()) {
          alert('Please enter a dashboard name');
          return;
        }
        const newDash = await createDashboard(newDashboardName);
        dashId = newDash.id;
        setDashboards([...dashboards, newDash]);
      }

      await saveDashboardWidget(dashId, {
        question: queryResponse.question,
        sql: queryResponse.sql,
        chart_type: activeTab === 'chart' ? chartVariant : 'table',
      });
      
      setIsSaveModalOpen(false);
      setNewDashboardName('');
      alert('Saved to dashboard!');
    } catch (err) {
      console.error(err);
      alert('Failed to save to dashboard');
    } finally {
      setIsSaving(false);
    }
  };


  const handleCopySql = () => {
    if (queryResponse?.sql) {
      navigator.clipboard.writeText(queryResponse.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // --- Export helpers ---

  const downloadFile = useCallback((content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

  const handleExportCsv = () => {
    if (!queryResponse?.result.length) return;
    const cols = queryResponse.columns;
    const header = cols.join(',');
    const rows = queryResponse.result.map((r) =>
      cols.map((c) => {
        const val = r[c];
        if (val === null || val === undefined) return '';
        const s = String(val);
        return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(',')
    );
    downloadFile([header, ...rows].join('\n'), `query_result_${Date.now()}.csv`, 'text/csv');
  };

  const handleExportJson = () => {
    if (!queryResponse?.result.length) return;
    downloadFile(
      JSON.stringify(queryResponse.result, null, 2),
      `query_result_${Date.now()}.json`,
      'application/json'
    );
  };

  const handleExportChartPng = async () => {
    if (!chartContainerRef.current) return;
    try {
      // html-to-image handles all CSS computed styles and SVG intricacies safely
      const dataUrl = await toPng(chartContainerRef.current, {
        backgroundColor: '#0f172a',
        pixelRatio: 2, // High-DPI export
        style: {
          padding: '20px', // Add some padding so axes aren't cut off
        }
      });
      
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `chart_${chartVariant}_${Date.now()}.png`;
      a.click();
    } catch (err) {
      console.error('Failed to export chart:', err);
    }
  };

  const getAvailableCharts = (): { key: ChartVariant; label: string; icon: React.ReactNode }[] => {
    if (!queryResponse || !queryResponse.result.length) return [];
    const df = queryResponse.result;
    const cols = queryResponse.columns;
    const numericCols = cols.filter(c => df.some(r => typeof r[c] === 'number' || !isNaN(Number(r[c]))));
    
    // Rule 1: KPI
    if (df.length === 1 && numericCols.length === 1 && cols.length <= 2) {
      return [{ key: 'kpi', label: 'Metric', icon: <Hash size={14} /> }];
    }
    
    if (cols.length < 2 || numericCols.length === 0) return [];

    // Rule 2: Scatter / Geo
    const lowerCols = cols.map(c => c.toLowerCase());
    const hasLat = lowerCols.some(c => c.includes('lat'));
    const hasLon = lowerCols.some(c => c.includes('lon') || c.includes('lng'));
    if (hasLat && hasLon) {
      return [{ key: 'scatter', label: 'Map', icon: <MapPin size={14} /> }];
    }

    // Default charts
    const charts: { key: ChartVariant; label: string; icon: React.ReactNode }[] = [
      { key: 'bar', label: 'Bar', icon: <BarChart2 size={14} /> },
    ];
    
    // Add Line/Area if there's a date-like column
    const isTime = ['date', 'time', 'year', 'month', 'day'].some(kw => lowerCols[0].includes(kw));
    if (isTime) {
      charts.push({ key: 'line', label: 'Line', icon: <TrendingUp size={14} /> });
      charts.push({ key: 'area', label: 'Area', icon: <Activity size={14} /> });
    } else {
      // If it's not time series, we still might want line/area if it's numeric X axis, but usually bar is best.
      charts.push({ key: 'line', label: 'Line', icon: <TrendingUp size={14} /> });
    }

    if (df.length <= 15 && cols.length === 2) {
      charts.push({ key: 'pie', label: 'Pie', icon: <PieChartIcon size={14} /> });
    }
    
    return charts;
  };

  // Set initial chart variant from backend recommendation or fallback to first available
  const getInitialChartVariant = (): ChartVariant => {
    if (!queryResponse) return 'bar';
    const available = getAvailableCharts();
    if (available.length > 0) {
      // If backend explicitly suggests kpi or scatter, and it's available
      const ct = queryResponse.chart_type as ChartVariant;
      if (available.some(a => a.key === ct)) return ct;
      // Else just pick the first available
      return available[0].key;
    }
    return 'bar';
  };

  // --- Chart rendering ---

  const renderChart = (variant: ChartVariant) => {
    if (!queryResponse || !queryResponse.result.length) return null;
    const data = queryResponse.result.slice(0, 50); // Cap chart data at 50 items
    
    if (variant === 'kpi') {
      const numCol = queryResponse.columns.find(c => typeof data[0][c] === 'number') || queryResponse.columns[0];
      const labelCol = queryResponse.columns.find(c => c !== numCol);
      const val = data[0][numCol];
      const label = labelCol ? data[0][labelCol] : numCol;
      const displayVal = val === null || val === undefined ? 'N/A' : (typeof val === 'number' ? val.toLocaleString() : val);
      
      return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '380px' }}>
          <div style={{ fontSize: '16px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
            {label}
          </div>
          <div style={{ fontSize: '72px', fontWeight: 800, background: 'linear-gradient(135deg, #38bdf8, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            {displayVal}
          </div>
        </div>
      );
    }

    if (queryResponse.columns.length < 2) {
      return (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
          Insufficient data dimensions for chart visualization (need at least 2 columns).
        </div>
      );
    }

    const labelKey = queryResponse.columns[0];
    const valueKeys = queryResponse.columns.slice(1).filter((col) => {
      // Only include numeric columns for chart values
      return data.some((row) => typeof row[col] === 'number' || !isNaN(Number(row[col])));
    });
    const valueKey = valueKeys[0] || queryResponse.columns[1];

    switch (variant) {
      case 'scatter':
        const latCol = queryResponse.columns.find(c => c.toLowerCase().includes('lat')) || queryResponse.columns[1];
        const lonCol = queryResponse.columns.find(c => c.toLowerCase().includes('lon') || c.toLowerCase().includes('lng')) || queryResponse.columns[0];
        const metricCol = valueKeys.find(c => c !== latCol && c !== lonCol) || valueKeys[0];
        
        return (
          <ResponsiveContainer width="100%" height={380}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={lonCol} type="number" name="Longitude" stroke="#64748b" tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
              <YAxis dataKey={latCol} type="number" name="Latitude" stroke="#64748b" tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
              {metricCol && <ZAxis dataKey={metricCol} range={[20, 400]} name={metricCol} />}
              <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={TOOLTIP_STYLE} />
              <Scatter name="Data" data={data} fill="#06b6d4" fillOpacity={0.6} />
            </ScatterChart>
          </ResponsiveContainer>
        );
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={380}>
            <PieChart>
              <Pie
                data={data}
                dataKey={valueKey}
                nameKey={labelKey}
                cx="50%"
                cy="50%"
                outerRadius={120}
                innerRadius={50}
                paddingAngle={2}
                label={({ name, percent }) => `${name}: ${((percent || 0) * 100).toFixed(0)}%`}
                labelLine={{ stroke: '#475569' }}
              >
                {data.map((_, idx) => (
                  <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
            </PieChart>
          </ResponsiveContainer>
        );

      case 'line':
        return (
          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
              <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {valueKeys.slice(0, 3).map((vk, idx) => (
                <Line
                  key={vk}
                  type="monotone"
                  dataKey={vk}
                  stroke={COLORS[idx % COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ fill: COLORS[idx % COLORS.length], r: 4 }}
                  activeDot={{ r: 6 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );

      case 'area':
        return (
          <ResponsiveContainer width="100%" height={380}>
            <AreaChart data={data}>
              <defs>
                {valueKeys.slice(0, 3).map((vk, idx) => (
                  <linearGradient key={vk} id={`gradient-${idx}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS[idx % COLORS.length]} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={COLORS[idx % COLORS.length]} stopOpacity={0.02} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
              <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {valueKeys.slice(0, 3).map((vk, idx) => (
                <Area
                  key={vk}
                  type="monotone"
                  dataKey={vk}
                  stroke={COLORS[idx % COLORS.length]}
                  strokeWidth={2}
                  fill={`url(#gradient-${idx})`}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        );

      case 'bar':
      default:
        return (
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={labelKey} stroke="#64748b" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
              <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(99, 102, 241, 0.08)' }} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {valueKeys.slice(0, 3).map((vk, idx) => (
                <Bar key={vk} dataKey={vk} fill={COLORS[idx % COLORS.length]} radius={[6, 6, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
    }
  };

  return (
    <div style={{ maxWidth: '1280px', margin: '24px auto', padding: '0 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Search & Query Input Box */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (activeQuestion.trim()) {
              onExecuteQuery(activeQuestion);
            }
          }}
          style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}
        >
          <div style={{ position: 'relative' }}>
            <Sparkles size={20} color="#06b6d4" style={{ position: 'absolute', left: '16px', top: '16px' }} />
            <input
              type="text"
              className="input-field"
              style={{ paddingLeft: '48px', paddingRight: '120px', fontSize: '15px', height: '52px', borderRadius: '12px' }}
              placeholder="Ask any question about your data (e.g. 'Show top 5 revenue generating categories')..."
              value={activeQuestion}
              onChange={(e) => setActiveQuestion(e.target.value)}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={loading || !activeQuestion.trim()}
              style={{ position: 'absolute', right: '8px', top: '8px', bottom: '8px', borderRadius: '8px' }}
            >
              {loading ? <RefreshCw size={16} className="animate-pulse" /> : <Send size={16} />}
              {loading ? 'Analyzing...' : 'Query'}
            </button>
          </div>

          {/* Sample Questions Pills */}
          {sampleQuestions.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>Try asking:</span>
              {sampleQuestions.slice(0, 4).map((q, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => { setActiveQuestion(q); onExecuteQuery(q); }}
                  style={{
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    color: '#94a3b8',
                    padding: '4px 10px',
                    borderRadius: '20px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#6366f1')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </form>
      </div>

      {/* Error state */}
      {error && (
        <div className="glass-panel" style={{ padding: '20px', borderColor: 'rgba(244, 63, 94, 0.3)', background: 'rgba(244, 63, 94, 0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f43f5e', fontWeight: 600, fontSize: '15px' }}>
            <AlertTriangle size={20} />
            Execution Error
          </div>
          <p style={{ marginTop: '8px', fontSize: '13px', color: '#cbd5e1' }}>{error}</p>
        </div>
      )}

      {/* Query Results & Narration */}
      {queryResponse && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Metadata badges bar */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', gap: '10px' }}>
              <span className="badge badge-info">Latency: {Math.round(queryResponse.latency_ms)}ms</span>
              <span className="badge badge-success">Rows: {queryResponse.row_count}</span>
              {queryResponse.retries > 0 && (
                <span className="badge badge-warning">Self-corrected retries: {queryResponse.retries}</span>
              )}
            </div>

            {/* View tab switchers and Save */}
            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ display: 'flex', background: 'rgba(15, 23, 42, 0.6)', padding: '4px', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                <button
                  onClick={() => setActiveTab('table')}
                  className={`btn-secondary ${activeTab === 'table' ? 'btn-primary' : ''}`}
                  style={{ padding: '6px 14px', fontSize: '12px', borderRadius: '6px' }}
                >
                  <Table size={14} /> Data
                </button>
                <button
                  onClick={() => setActiveTab('chart')}
                  className={`btn-secondary ${activeTab === 'chart' ? 'btn-primary' : ''}`}
                  style={{ padding: '6px 14px', fontSize: '12px', borderRadius: '6px' }}
                >
                  <BarChart2 size={14} /> Visualize
                </button>
                <button
                  onClick={() => setActiveTab('sql')}
                  className={`btn-secondary ${activeTab === 'sql' ? 'btn-primary' : ''}`}
                  style={{ padding: '6px 14px', fontSize: '12px', borderRadius: '6px' }}
                >
                  <Code size={14} /> SQL
                </button>
              </div>

              <button
                onClick={() => setIsSaveModalOpen(true)}
                className="btn-primary"
                style={{ padding: '6px 14px', fontSize: '12px', borderRadius: '8px', background: 'linear-gradient(135deg, #10b981, #059669)' }}
              >
                <Save size={14} /> Save to Dashboard
              </button>
            </div>
          </div>

          {/* Narration summary card */}
          {queryResponse.narration && (
            <div className="glass-panel" style={{ padding: '16px 20px', borderLeft: '4px solid #06b6d4', display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <MessageSquare size={20} color="#06b6d4" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <h4 style={{ fontSize: '13px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>AI Narration</h4>
                <p style={{ fontSize: '14px', color: '#f8fafc', marginTop: '2px' }}>{queryResponse.narration}</p>
              </div>
            </div>
          )}

          {/* Tab Content */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            
            {/* Table View */}
            {activeTab === 'table' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Query Result Set</h3>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn-secondary" onClick={handleExportCsv} style={{ fontSize: '12px', padding: '6px 12px' }}>
                      <FileSpreadsheet size={14} /> CSV
                    </button>
                    <button className="btn-secondary" onClick={handleExportJson} style={{ fontSize: '12px', padding: '6px 12px' }}>
                      <FileJson size={14} /> JSON
                    </button>
                  </div>
                </div>

                {!queryResponse.result.length ? (
                  <p style={{ fontSize: '13px', color: '#64748b', padding: '20px 0' }}>Query executed successfully but returned 0 rows.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: '#94a3b8' }}>
                          {queryResponse.columns.map((col) => (
                            <th key={col} style={{ padding: '10px 14px', fontWeight: 600 }}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResponse.result.map((row, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)', background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.01)' }}>
                            {queryResponse.columns.map((col) => (
                              <td key={col} style={{ padding: '10px 14px', color: '#e2e8f0' }}>
                                {row[col] !== null && row[col] !== undefined ? String(row[col]) : <em style={{ color: '#64748b' }}>null</em>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Chart View */}
            {activeTab === 'chart' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
                  {/* Chart type selector */}
                  <div style={{ display: 'flex', gap: '6px', background: 'rgba(15, 23, 42, 0.5)', padding: '4px', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                    {getAvailableCharts().map((ct) => (
                      <button
                        key={ct.key}
                        onClick={() => setChartVariant(ct.key as ChartVariant)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '5px',
                          padding: '6px 12px', borderRadius: '7px', fontSize: '12px', fontWeight: 500, cursor: 'pointer',
                          border: 'none', transition: 'all 0.2s ease',
                          background: chartVariant === ct.key ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' : 'transparent',
                          color: chartVariant === ct.key ? '#fff' : '#94a3b8',
                          boxShadow: chartVariant === ct.key ? '0 2px 8px rgba(99, 102, 241, 0.3)' : 'none',
                        }}
                      >
                        {ct.icon} {ct.label}
                      </button>
                    ))}
                  </div>

                  {/* Export chart as PNG */}
                  <button className="btn-secondary" onClick={handleExportChartPng} style={{ fontSize: '12px', padding: '6px 12px' }}>
                    <Image size={14} /> Export PNG
                  </button>
                </div>

                <div ref={chartContainerRef}>
                  {renderChart(chartVariant)}
                </div>
              </div>
            )}

            {/* SQL View */}
            {activeTab === 'sql' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Validated SQL Query</h3>
                  <button className="btn-secondary" onClick={handleCopySql} style={{ fontSize: '12px', padding: '6px 12px' }}>
                    {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                    {copied ? 'Copied!' : 'Copy SQL'}
                  </button>
                </div>
                <pre style={{ background: '#070a12', padding: '16px', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.08)', color: '#38bdf8', fontSize: '14px', overflowX: 'auto', lineHeight: 1.6 }}>
                  {queryResponse.sql}
                </pre>
              </div>
            )}

          </div>

        </div>
      )}



      {/* Save to Dashboard Modal */}
      {isSaveModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="glass-panel" style={{ width: '400px', padding: '24px', position: 'relative' }}>
            <button onClick={() => setIsSaveModalOpen(false)} style={{ position: 'absolute', top: '16px', right: '16px', background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
              <X size={20} />
            </button>
            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '20px' }}>Save to Dashboard</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {dashboards.length > 0 && (
                <div>
                  <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '8px' }}>Select Dashboard</label>
                  <select
                    value={selectedDashboardId}
                    onChange={(e) => setSelectedDashboardId(e.target.value)}
                    className="input-field"
                    style={{ width: '100%', padding: '10px' }}
                  >
                    {dashboards.map(d => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                    <option value="new">+ Create New Dashboard</option>
                  </select>
                </div>
              )}

              {(dashboards.length === 0 || selectedDashboardId === 'new') && (
                <div>
                  <label style={{ display: 'block', fontSize: '13px', color: '#94a3b8', marginBottom: '8px' }}>New Dashboard Name</label>
                  <input
                    type="text"
                    value={newDashboardName}
                    onChange={(e) => setNewDashboardName(e.target.value)}
                    className="input-field"
                    placeholder="e.g. Sales KPI"
                    style={{ width: '100%', padding: '10px' }}
                  />
                </div>
              )}

              <button
                onClick={handleSaveToDashboard}
                disabled={isSaving}
                className="btn-primary"
                style={{ width: '100%', padding: '12px', marginTop: '10px' }}
              >
                {isSaving ? <RefreshCw className="animate-spin" size={16} /> : <Save size={16} />}
                {isSaving ? 'Saving...' : 'Save Widget'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
