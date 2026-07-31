import { Loader2 } from 'lucide-react';

interface StartupLoaderProps {
  status: 'loading' | 'retrying' | 'degraded';
}

export function StartupLoader({ status }: StartupLoaderProps) {
  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: '#0f172a',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      color: 'white',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <Loader2 size={48} className="animate-spin" style={{ color: '#818cf8', marginBottom: '24px', animation: 'spin 2s linear infinite' }} />
      <style>
        {`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}
      </style>
      
      <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '12px' }}>
        Waking up QueryMind Backend
      </h2>
      
      <p style={{ color: '#94a3b8', maxWidth: '400px', textAlign: 'center', lineHeight: 1.5 }}>
        {status === 'loading' && "Connecting to the server. If it was asleep, this might take up to 50 seconds..."}
        {status === 'retrying' && "Server is still starting up. Retrying connection..."}
        {status === 'degraded' && "Server is degraded. Waiting for it to become fully healthy..."}
      </p>
    </div>
  );
}
