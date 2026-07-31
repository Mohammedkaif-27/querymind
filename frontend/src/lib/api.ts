import { supabase } from './supabase';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : typeof window !== 'undefined' && window.location.port === '3000'
    ? ''
    : 'http://localhost:8000';

export interface QueryRequest {
  question: string;
  source_id?: string;
}

export interface QueryResponse {
  question: string;
  sql: string;
  result: Record<string, any>[];
  columns: string[];
  narration: string;
  chart_type: 'bar' | 'line' | 'pie' | 'table' | 'none' | 'kpi' | 'scatter';
  error: string;
  retries: number;
  latency_ms: number;
  row_count: number;
}

export interface DataSource {
  id: string;
  name: string;
  type: 'csv' | 'xlsx' | 'postgres' | 'mysql';
  chroma_collection_name: string;
  table_count: number;
  created_at: string;
}

export interface QueryHistoryItem {
  id: string;
  source_id: string | null;
  question: string;
  generated_sql: string;
  success: boolean;
  latency_ms: number;
  row_count: number;
  error: string;
  created_at: string;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  timestamp: string;
  components: {
    api: { status: string; version: string };
    llm: { status: string; model: string };
    database: { status: string; dialect?: string; table_count?: number };
    supabase: { status: string };
    chroma: { status: string; collections?: number };
  };
}

async function getAuthHeaders(): Promise<HeadersInit> {
  const { data } = await supabase.auth.getSession();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (data.session?.access_token) {
    headers['Authorization'] = `Bearer ${data.session.access_token}`;
  }
  return headers;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`);
  return res.json();
}

export async function fetchSampleQuestions(sourceId?: string): Promise<string[]> {
  const url = sourceId ? `${API_BASE_URL}/sample-questions?source_id=${sourceId}` : `${API_BASE_URL}/sample-questions`;
  const res = await fetch(url);
  const data = await res.json();
  return data.questions || [];
}

export async function runQuery(req: { question: string; source_id?: string }): Promise<QueryResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers,
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: 'Server error' }));
    throw new Error(err.message || err.detail || 'Query execution failed');
  }

  return res.json();
}

export async function fetchSources(): Promise<DataSource[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/sources`, { headers });
  if (!res.ok) return [];
  return res.json();
}

export async function uploadSource(file: File, customName?: string): Promise<DataSource> {
  const { data } = await supabase.auth.getSession();
  const formData = new FormData();
  formData.append('file', file);
  if (customName) {
    formData.append('name', customName);
  }

  const headers: Record<string, string> = {};
  if (data.session?.access_token) {
    headers['Authorization'] = `Bearer ${data.session.access_token}`;
  }

  const res = await fetch(`${API_BASE_URL}/api/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('Please Sign In / Register first to upload custom data sources.');
    }
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || err.message || `File upload failed (${res.status})`);
  }

  return res.json();
}

export async function connectSource(req: { name: string; uri: string; type: 'postgres' | 'mysql' }): Promise<DataSource> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/connect`, {
    method: 'POST',
    headers,
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('Please Sign In / Register first to connect external databases.');
    }
    const err = await res.json().catch(() => ({ detail: 'Connection failed' }));
    throw new Error(err.detail || err.message || `Database connection failed (${res.status})`);
  }

  return res.json();
}

export async function deleteSource(sourceId: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/sources/${sourceId}`, {
    method: 'DELETE',
    headers,
  });
  if (!res.ok) {
    throw new Error('Failed to delete data source');
  }
}

export async function fetchQueryHistory(sourceId?: string): Promise<QueryHistoryItem[]> {
  const headers = await getAuthHeaders();
  let url = `${API_BASE_URL}/api/history?limit=50`;
  if (sourceId) {
    url += `&source_id=${encodeURIComponent(sourceId)}`;
  }
  const res = await fetch(url, { headers });
  if (!res.ok) return [];
  return res.json();
}

// --- Dashboards ---

export interface Dashboard {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
}

export interface DashboardWidget {
  id: string;
  dashboard_id: string;
  source_id?: string;
  question: string;
  sql: string;
  chart_type: string;
  created_at: string;
}

export async function fetchDashboards(): Promise<Dashboard[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards`, { headers });
  if (!res.ok) throw new Error('Failed to fetch dashboards');
  return res.json();
}

export async function createDashboard(name: string): Promise<Dashboard> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Failed to create dashboard');
  return res.json();
}

export async function fetchDashboardWidgets(dashboardId: string): Promise<DashboardWidget[]> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards/${dashboardId}/widgets`, { headers });
  if (!res.ok) throw new Error('Failed to fetch dashboard widgets');
  return res.json();
}

export async function saveDashboardWidget(
  dashboardId: string,
  widgetData: { source_id?: string; question: string; sql: string; chart_type: string }
): Promise<DashboardWidget> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards/${dashboardId}/widgets`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(widgetData),
  });
  if (!res.ok) throw new Error('Failed to save widget to dashboard');
  return res.json();
}

export async function deleteDashboard(dashboardId: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards/${dashboardId}`, {
    method: 'DELETE',
    headers,
  });
  if (!res.ok) throw new Error('Failed to delete dashboard');
}

export async function deleteDashboardWidget(dashboardId: string, widgetId: string): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/api/dashboards/${dashboardId}/widgets/${widgetId}`, {
    method: 'DELETE',
    headers,
  });
  if (!res.ok) throw new Error('Failed to delete widget');
}
