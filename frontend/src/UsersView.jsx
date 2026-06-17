import React, { useState, useEffect } from 'react';
import { api } from './api';
import { Shield, Key, UserPlus, Power } from 'lucide-react';

export default function UsersView({ role, currentUsername }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Change password state
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwdMessage, setPwdMessage] = useState('');

  // New user state
  const [newUsername, setNewUsername] = useState('');
  const [newUserPwd, setNewUserPwd] = useState('');
  const [newUserRole, setNewUserRole] = useState('rrhh');

  const fetchUsers = async () => {
    if (role !== 'admin') return;
    setLoading(true);
    try {
      const res = await api.get('/users');
      setUsers(res.data);
    } catch (err) {
      console.error(err);
      setError('Error cargando usuarios');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchUsers();
  }, [role]);

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwdMessage('');
    if (newPassword !== confirmPassword) {
      setPwdMessage('Las nuevas contraseñas no coinciden.');
      return;
    }
    try {
      await api.post('/auth/change-password', {
        username: currentUsername,
        old_password: oldPassword,
        new_password: newPassword
      });
      setPwdMessage('Contraseña actualizada exitosamente.');
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPwdMessage(err.response?.data?.detail || err.message || 'Error al cambiar contraseña.');
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      await api.post('/users', {
        username: newUsername,
        password: newUserPwd,
        role: newUserRole
      });
      setNewUsername('');
      setNewUserPwd('');
      fetchUsers();
    } catch (err) {
      alert(err.response?.data?.detail || err.message || 'Error creando usuario');
    }
  };

  const handleToggleStatus = async (username, is_active) => {
    if (!window.confirm(`¿Estás seguro de ${is_active ? 'activar' : 'desactivar'} el acceso para el usuario ${username}?`)) return;
    try {
      await api.put(`/users/${username}/status`, { is_active });
      fetchUsers();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error cambiando estado del usuario');
    }
  };

  const handleRoleChange = async (username, newRole) => {
    try {
      await api.put(`/users/${username}/role`, { role: newRole });
      fetchUsers();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error actualizando rol');
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Shield /> Seguridad y Usuarios
      </h1>
      <p className="subtitle">Gestiona tu contraseña y los accesos al sistema.</p>

      <div style={{ display: 'grid', gridTemplateColumns: role === 'admin' ? '1fr 2fr' : '1fr', gap: '24px', marginTop: '24px' }}>
        
        {/* Cambiar Contraseña Panel */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3><Key size={18} style={{ verticalAlign: 'middle', marginRight: '8px' }} /> Cambiar mi Contraseña</h3>
          <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
            <div>
              <label className="form-label">Contraseña Actual</label>
              <input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} required />
            </div>
            <div>
              <label className="form-label">Nueva Contraseña</label>
              <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required minLength={6} />
            </div>
            <div>
              <label className="form-label">Confirmar Nueva Contraseña</label>
              <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required minLength={6} />
            </div>
            {pwdMessage && <div style={{ color: pwdMessage.includes('exitosamente') ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>{pwdMessage}</div>}
            <button type="submit" className="btn btn-primary" style={{ marginTop: '8px' }}>Actualizar Contraseña</button>
          </form>
        </div>

        {/* Panel Admin: Gestión de Usuarios */}
        {role === 'admin' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            {/* Crear Usuario */}
            <div className="glass-panel" style={{ padding: '24px' }}>
              <h3><UserPlus size={18} style={{ verticalAlign: 'middle', marginRight: '8px' }} /> Crear Nuevo Usuario</h3>
              <form onSubmit={handleCreateUser} style={{ display: 'flex', gap: '16px', marginTop: '16px', alignItems: 'flex-end' }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Usuario</label>
                  <input type="text" value={newUsername} onChange={e => setNewUsername(e.target.value)} required />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Contraseña</label>
                  <input type="password" value={newUserPwd} onChange={e => setNewUserPwd(e.target.value)} required minLength={6} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Rol</label>
                  <select value={newUserRole} onChange={e => setNewUserRole(e.target.value)}>
                    <option value="rrhh">RRHH</option>
                    <option value="admin">Administrador</option>
                  </select>
                </div>
                <button type="submit" className="btn btn-success">Crear</button>
              </form>
            </div>

            {/* Lista de Usuarios */}
            <div className="glass-panel" style={{ padding: '24px' }}>
              <h3>Cuentas Activas</h3>
              {loading ? (
                <div>Cargando...</div>
              ) : (
                <div className="table-container" style={{ marginTop: '16px' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Usuario</th>
                        <th>Estado</th>
                        <th>Rol</th>
                        <th>Acceso</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map(u => (
                        <tr key={u.username}>
                          <td>{u.username} {u.username === currentUsername && <span style={{fontSize:'0.8rem', color:'var(--success)'}}>(Tú)</span>}</td>
                          <td>
                            <span className={`badge ${u.is_active ? 'badge-success' : 'badge-danger'}`}>
                              {u.is_active ? 'Activo' : 'Inactivo'}
                            </span>
                          </td>
                          <td>
                            <select 
                              value={u.role} 
                              onChange={(e) => handleRoleChange(u.username, e.target.value)}
                              disabled={u.username === 'admin'} // Evitar cambiar rol al admin root
                              style={{ width: 'auto', padding: '4px' }}
                            >
                              <option value="rrhh">RRHH</option>
                              <option value="admin">Administrador</option>
                            </select>
                          </td>
                          <td>
                            <button 
                              className={`btn ${u.is_active ? 'btn-danger' : 'btn-success'}`} 
                              style={{ padding: '4px 8px' }}
                              onClick={() => handleToggleStatus(u.username, !u.is_active)}
                              disabled={u.username === 'admin' || u.username === currentUsername}
                              title={u.is_active ? "Desactivar Acceso" : "Activar Acceso"}
                            >
                              <Power size={14} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                              {u.is_active ? "Desactivar" : "Activar"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
