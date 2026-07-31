import { useState, useEffect } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from './lib/supabase';
import { Navbar } from './components/Navbar';
import { AuthModal } from './components/AuthModal';
import { SourceManager } from './components/SourceManager';
import { QueryHistoryModal } from './components/QueryHistoryModal';
import { QueryWorkspace } from './components/QueryWorkspace';
import { Dashboard } from './components/Dashboard';
import { StartupLoader } from './components/StartupLoader';
import { LayoutDashboard, Terminal } from 'lucide-react';
import type {
  DataSource,
  HealthResponse,
  QueryResponse,
  QueryHistoryItem,
} from './lib/api';
import {
  fetchHealth,
  fetchSampleQuestions,
  fetchSources,
  runQuery,
  fetchQueryHistory,
} from './lib/api';

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  
  // App startup states
  const [startupStatus, setStartupStatus] = useState<'loading' | 'retrying' | 'degraded' | 'ready'>('loading');

  const [sampleQuestions, setSampleQuestions] = useState<string[]>([]);
  const [activeQuestion, setActiveQuestion] = useState('');

  const [queryResponse, setQueryResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<QueryHistoryItem[]>([]);

  // Modals state
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [isSourceManagerOpen, setIsSourceManagerOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  // View state
  const [currentView, setCurrentView] = useState<'workspace' | 'dashboard'>('workspace');

  // Initialize auth state
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setUser(data.session?.user ?? null);
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_, session) => {
      setUser(session?.user ?? null);
    });

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, []);

  // Poll health on mount to handle cold starts
  useEffect(() => {
    let isCancelled = false;
    let retryTimeout: NodeJS.Timeout;

    const checkHealth = async () => {
      try {
        const res = await fetchHealth();
        if (isCancelled) return;
        setHealth(res);
        if (res.status === 'healthy') {
          setStartupStatus('ready');
        } else {
          setStartupStatus('degraded');
          // If degraded, it might still be starting, check again in 5s
          retryTimeout = setTimeout(checkHealth, 5000);
        }
      } catch (err) {
        if (isCancelled) return;
        setStartupStatus('retrying');
        // Retry connection every 3 seconds
        retryTimeout = setTimeout(checkHealth, 3000);
      }
    };

    checkHealth();

    return () => {
      isCancelled = true;
      clearTimeout(retryTimeout);
    };
  }, []);

  // Fetch sample questions when active source changes
  useEffect(() => {
    fetchSampleQuestions(activeSourceId || undefined)
      .then(setSampleQuestions)
      .catch(console.error);
  }, [activeSourceId]);

  // Fetch sources whenever user logs in or updates sources
  const refreshSources = () => {
    if (user) {
      fetchSources().then(setSources).catch(console.error);
    } else {
      setSources([]);
    }
  };

  useEffect(() => {
    refreshSources();
  }, [user]);

  // Fetch history when history modal is opened or query runs
  const refreshHistory = () => {
    if (user) {
      fetchQueryHistory(activeSourceId || undefined)
        .then(setHistory)
        .catch(console.error);
    }
  };

  useEffect(() => {
    if (isHistoryOpen) {
      refreshHistory();
    }
  }, [isHistoryOpen, activeSourceId]);

  // Execute query handler
  const handleExecuteQuery = async (questionText: string) => {
    setLoading(true);
    setError(null);
    setQueryResponse(null);

    try {
      const res = await runQuery({
        question: questionText,
        source_id: activeSourceId || undefined,
      });

      if (res.error) {
        setError(res.error);
      }
      setQueryResponse(res);
      refreshHistory();
    } catch (err: any) {
      setError(err.message || 'Failed to execute query');
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    setActiveSourceId(null);
    setSources([]);
  };

  if (startupStatus !== 'ready') {
    return <StartupLoader status={startupStatus} />;
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar
        user={user}
        sources={sources}
        activeSourceId={activeSourceId}
        onSelectSource={setActiveSourceId}
        onOpenAuth={() => setIsAuthOpen(true)}
        onSignOut={handleSignOut}
        onOpenSourceManager={() => setIsSourceManagerOpen(true)}
        onOpenHistory={() => setIsHistoryOpen(true)}
        health={health}
      />

      <main style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', background: 'rgba(15, 23, 42, 0.6)', padding: '4px', borderRadius: '12px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
            <button
              onClick={() => setCurrentView('workspace')}
              className={`btn-secondary ${currentView === 'workspace' ? 'btn-primary' : ''}`}
              style={{ padding: '8px 24px', fontSize: '14px', borderRadius: '8px', display: 'flex', gap: '8px', alignItems: 'center' }}
            >
              <Terminal size={16} /> Query Workspace
            </button>
            <button
              onClick={() => setCurrentView('dashboard')}
              className={`btn-secondary ${currentView === 'dashboard' ? 'btn-primary' : ''}`}
              style={{ padding: '8px 24px', fontSize: '14px', borderRadius: '8px', display: 'flex', gap: '8px', alignItems: 'center' }}
            >
              <LayoutDashboard size={16} /> Dashboards
            </button>
          </div>
        </div>

        {currentView === 'workspace' ? (
          <QueryWorkspace
            sampleQuestions={sampleQuestions}
            activeQuestion={activeQuestion}
            setActiveQuestion={setActiveQuestion}
            onExecuteQuery={handleExecuteQuery}
            queryResponse={queryResponse}
            loading={loading}
            error={error}
          />
        ) : (
          <Dashboard />
        )}
      </main>

      {/* Modals */}
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
      <SourceManager
        isOpen={isSourceManagerOpen}
        onClose={() => setIsSourceManagerOpen(false)}
        sources={sources}
        onRefreshSources={refreshSources}
        onSelectSource={setActiveSourceId}
        user={user}
        onOpenAuth={() => setIsAuthOpen(true)}
      />
      <QueryHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        history={history}
        onSelectQuery={(q) => {
          setActiveQuestion(q);
          handleExecuteQuery(q);
        }}
      />
    </div>
  );
}

export default App;
