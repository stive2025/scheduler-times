import React, { useState, useEffect } from 'react';
import { getSchedules, updateSchedule, getJustifications, createJustification, deleteJustification } from './api';
import { Settings, Check, Trash2 } from 'lucide-react';

export default function Configuration({ role }) {
  const [schedules, setSchedules] = useState([]);
  const [justifications, setJustifications] = useState([]);
  const [loading, setLoading] = useState(true);

  // Form states for Justifications
  const [jEmpId, setJEmpId] = useState('');
  const [jEmpName, setJEmpName] = useState('');
  const [jDate, setJDate] = useState('');
  const [jType, setJType] = useState('Atraso');
  const [jReason, setJReason] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const s = await getSchedules();
      const j = await getJustifications();
      setSchedules(s);
      setJustifications(j);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleScheduleChange = async (empId, empName, val) => {
    try {
      await updateSchedule({ employee_id: empId, employee_name: empName, schedule_name: val });
      fetchData(); // Refresh to show correct data
    } catch (e) {
      alert('Error guardando horario');
    }
  };

  const handleAddJustification = async (e) => {
    e.preventDefault();
    try {
      await createJustification({
        employee_id: jEmpId,
        employee_name: jEmpName,
        fecha: jDate,
        tipo: jType,
        reason: jReason
      });
      fetchData();
      setJEmpId(''); setJEmpName(''); setJDate(''); setJReason('');
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteJustification = async (id) => {
    if (window.confirm('¿Eliminar esta justificación? Se revertirá en la BD.')) {
      try {
        await deleteJustification(id);
        fetchData();
      } catch (err) {
        alert('Error al eliminar');
      }
    }
  };

  if (loading) return <div className="loader-container"><div className="spinner"></div></div>;

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1>Configuración y Justificaciones</h1>
        <p className="subtitle">Gestión de empleados y control de excepciones</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        
        {/* Schedules Panel */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h3><Settings size={18} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }}/> Horarios Fijos</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
            Fuerza un horario específico para evitar inferencias incorrectas.
          </p>
          <div className="table-container" style={{ maxHeight: '400px' }}>
            <table>
              <thead>
                <tr>
                  <th>Empleado</th>
                  <th>ID</th>
                  <th>Horario Asignado</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map(s => (
                  <tr key={s.employee_id}>
                    <td>{s.employee_name}</td>
                    <td>{s.employee_id}</td>
                    <td>
                      <select 
                        value={s.schedule_name} 
                        onChange={(e) => handleScheduleChange(s.employee_id, s.employee_name, e.target.value)}
                        style={{ padding: '6px' }}
                      >
                        <option value="Automático">Automático</option>
                        <option value="Horario A">Horario A</option>
                        <option value="Horario B">Horario B</option>
                        <option value="Horario C">Horario C</option>
                        <option value="Horario D">Horario D</option>
                        <option value="Medio Tiempo">Medio Tiempo</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Justifications Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3>Añadir Justificación</h3>
            <form onSubmit={handleAddJustification} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Cédula / ID</label>
                  <input required value={jEmpId} onChange={e => setJEmpId(e.target.value)} />
                </div>
                <div style={{ flex: 2 }}>
                  <label className="form-label">Nombre del Empleado (Opcional)</label>
                  <input value={jEmpName} onChange={e => setJEmpName(e.target.value)} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Fecha Excepción</label>
                  <input type="date" required value={jDate} onChange={e => setJDate(e.target.value)} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Tipo a perdonar</label>
                  <select value={jType} onChange={e => setJType(e.target.value)}>
                    <option value="Atraso_Man">Atraso Mañana</option>
                    <option value="Atraso_Tar">Atraso Tarde</option>
                    <option value="Atraso">Atraso General</option>
                    <option value="Salida_Anticipada">Salida Anticipada</option>
                    <option value="Todos">Todos</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="form-label">Razón / Motivo</label>
                <input required value={jReason} onChange={e => setJReason(e.target.value)} />
              </div>
              <button type="submit" className="btn btn-primary" style={{ alignSelf: 'flex-start' }}>Aplicar Justificación</button>
            </form>
          </div>

          <div className="glass-panel" style={{ padding: '24px', flex: 1 }}>
            <h3>Historial de Justificaciones</h3>
            <div className="table-container" style={{ maxHeight: '250px' }}>
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Empleado</th>
                    <th>Tipo</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {justifications.map(j => (
                    <tr key={j.id}>
                      <td>{j.date}</td>
                      <td>{j.employee_name || j.employee_id}</td>
                      <td><span className="badge badge-purple">{j.type}</span></td>
                      <td>
                        <button className="btn btn-danger" style={{ padding: '4px 8px' }} onClick={() => handleDeleteJustification(j.id)}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {justifications.length === 0 && (
                    <tr><td colSpan="4" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Sin justificaciones</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
