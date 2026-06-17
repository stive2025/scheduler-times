import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Calendar as CalendarIcon, Settings, LogOut, Users, Sun, Moon, Shield } from 'lucide-react';
import { login, api } from './api';
import Dashboard from './Dashboard';
import CalendarView from './CalendarView';
import Configuration from './Configuration';
import UsersView from './UsersView';
import logoUrl from './assets/img/icon.png';

function App() {
  const [auth, setAuth] = useState(() => {
    try {
      const saved = localStorage.getItem('sefil_auth');
      if (!saved) return null;
      const parsed = JSON.parse(saved);
      if (typeof parsed?.role === 'object') {
        localStorage.removeItem('sefil_auth');
        return null; // Corrupted from previous bug
      }
      return parsed;
    } catch (e) {
      localStorage.removeItem('sefil_auth');
      return null;
    }
  });

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const [view, setView] = useState('dashboard');
  const [theme, setTheme] = useState(() => localStorage.getItem('sefil_theme') || 'dark');

  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('sefil_theme', theme);
  }, [theme]);


  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await login(username, password);
      if (res.success) {
        const authData = { username: res.username, role: res.role };
        setAuth(authData);
        localStorage.setItem('sefil_auth', JSON.stringify(authData));
        setError('');
      }
    } catch (err) {
      setError('Credenciales inválidas o error de conexión al servidor.');
    }
  };

  const handleLogout = () => {
    setAuth(null);
    localStorage.removeItem('sefil_auth');
  };

  if (!auth) {
    return (
      <div className="loader-container">
        <div className="glass-panel" style={{ padding: '40px', width: '400px', textAlign: 'center' }}>
          <img src={logoUrl} alt="SEFIL SA" style={{ maxWidth: '150px', marginBottom: '16px' }} />
          <h2 style={{ marginBottom: '8px' }}>Sistema de autenticación</h2>
          <p className="subtitle">Control de Asistencias</p>

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ textAlign: 'left' }}>
              <label className="form-label">Usuario</label>
              <input type="text" value={username} onChange={e => setUsername(e.target.value)} required />
            </div>
            <div style={{ textAlign: 'left' }}>
              <label className="form-label">Contraseña</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
            </div>
            {error && <div style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{error}</div>}
            <button type="submit" className="btn btn-primary" style={{ marginTop: '8px' }}>Ingresar</button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div style={{ textAlign: 'center', marginBottom: '16px' }}>
          <img src={logoUrl} alt="SEFIL SA" style={{ maxWidth: '120px', marginBottom: '16px' }} />
          <h2 style={{ color: 'var(--success)', margin: 0 }}>SEFIL S.A.</h2>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Módulo de Asistencias</div>
        </div>

        <nav className="nav-menu">
          <div
            className={`nav-item ${view === 'dashboard' ? 'active' : ''}`}
            onClick={() => setView('dashboard')}
          >
            <LayoutDashboard size={18} /> Atrasos / KPIs
          </div>
          <div
            className={`nav-item ${view === 'calendar' ? 'active' : ''}`}
            onClick={() => setView('calendar')}
          >
            <CalendarIcon size={18} /> Asistencias
          </div>
          <div
            className={`nav-item ${view === 'settings' ? 'active' : ''}`}
            onClick={() => setView('settings')}
          >
            <Users size={18} /> Config. Empleados
          </div>
          <div
            className={`nav-item ${view === 'security' ? 'active' : ''}`}
            onClick={() => setView('security')}
          >
            <Shield size={18} /> Seguridad y Usuarios
          </div>
        </nav>

        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
          <button
            className="btn"
            style={{ width: '100%', marginBottom: '12px' }}
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <><Sun size={16} /> Modo Claro</> : <><Moon size={16} /> Modo Oscuro</>}
          </button>
          <div style={{ fontSize: '0.85rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', fontSize: '1rem' }}>
              {auth.username.charAt(0).toUpperCase()}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left' }}>
              <span style={{ fontWeight: '600', textTransform: 'capitalize' }}>{auth.username}</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {auth.role === 'admin' ? 'Administrador' : auth.role === 'rrhh' ? 'Recursos Humanos' : auth.role}
              </span>
            </div>
          </div>
          <button className="btn btn-danger" style={{ width: '100%' }} onClick={handleLogout}>
            <LogOut size={16} /> Cerrar Sesión
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {view === 'dashboard' && <Dashboard role={auth.role} theme={theme} />}
        {view === 'calendar' && <CalendarView role={auth.role} />}
        {view === 'settings' && <Configuration role={auth.role} />}
        {view === 'security' && <UsersView role={auth.role} currentUsername={auth.username} />}
      </main>
    </div>
  );
}

export default App;
