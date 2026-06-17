import React, { useState, useEffect } from 'react';
import { getCalendarMatrix, saveCalendarOverrides } from './api';

export default function CalendarView({ role }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('Todos');
  const [selectedCell, setSelectedCell] = useState(null);
  const [newStatus, setNewStatus] = useState('');

  const fetchCalendar = () => {
    setLoading(true);
    getCalendarMatrix(year, month).then(d => {
      setData(d);
      setLoading(false);
    });
  };

  useEffect(() => {
    fetchCalendar();
  }, [year, month]);

  const handleMonthChange = (e) => {
    const val = e.target.value;
    const [y, m] = val.split('-');
    setYear(parseInt(y, 10));
    setMonth(parseInt(m, 10));
  };

  const handleOverride = async () => {
    if (!selectedCell || !newStatus) return;
    try {
      const dateStr = `${year}-${month.toString().padStart(2, '0')}-${selectedCell.day.padStart(2, '0')}`;
      await saveCalendarOverrides([{
        employee_id: selectedCell.employee_id,
        employee_name: selectedCell.employee_name,
        date_str: dateStr,
        status: newStatus
      }]);
      setSelectedCell(null);
      fetchCalendar();
    } catch (e) {
      alert("Error al actualizar el estado");
    }
  };

  if (loading || !data) {
    return <div className="loader-container"><div className="spinner"></div></div>;
  }

  const getCellClass = (val) => {
    if (val === 'Asistencia') return 'badge badge-success';
    if (val === 'Falta') return 'badge badge-danger';
    if (val === 'Permiso') return 'badge badge-warning';
    if (val === 'No Laborable') return 'badge badge-neutral';
    return '';
  };

  const isDimmed = (val) => {
    if (filter === 'Todos') return false;
    return val !== filter;
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1>Calendario de Asistencias</h1>
          <p className="subtitle" style={{ margin: 0 }}>Vista dinámica mensual</p>
        </div>
        <div>
          <input 
            type="month" 
            value={`${year}-${month.toString().padStart(2, '0')}`} 
            onChange={handleMonthChange}
            style={{ width: 'auto' }}
          />
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '16px', marginBottom: '24px', display: 'flex', gap: '8px' }}>
        <button className={`btn ${filter === 'Todos' ? 'btn-primary' : ''}`} onClick={() => setFilter('Todos')}>👁️ Todos</button>
        <button className={`btn ${filter === 'Asistencia' ? 'btn-primary' : ''}`} onClick={() => setFilter('Asistencia')}>✅ Asistencia</button>
        <button className={`btn ${filter === 'Falta' ? 'btn-primary' : ''}`} onClick={() => setFilter('Falta')}>❌ Falta</button>
        <button className={`btn ${filter === 'Permiso' ? 'btn-primary' : ''}`} onClick={() => setFilter('Permiso')}>📋 Permiso</button>
        <button className={`btn ${filter === 'No Laborable' ? 'btn-primary' : ''}`} onClick={() => setFilter('No Laborable')}>🔘 No Laborable</button>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th style={{ minWidth: '180px', position: 'sticky', left: 0, zIndex: 2 }}>Empleado</th>
              {data.all_days.map(d => (
                <th key={d} style={{ textAlign: 'center', minWidth: '80px' }}>{d}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.data.map((row, i) => (
              <tr key={row.employee_id || i}>
                <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', zIndex: 1, fontWeight: 500 }}>
                  {row.Empleado}
                </td>
                {data.all_days.map(d => {
                  const val = row[d];
                  const dimmed = isDimmed(val);
                  
                  const getCellBg = (val) => {
                    if (val === 'Asistencia') return 'rgba(63, 185, 80, 0.15)';
                    if (val === 'Falta') return 'rgba(248, 81, 73, 0.15)';
                    if (val === 'Permiso') return 'rgba(210, 153, 34, 0.15)';
                    if (val === 'No Laborable') return 'rgba(139, 148, 158, 0.15)';
                    return 'transparent';
                  };

                  return (
                    <td key={d} 
                        onClick={() => {
                          setSelectedCell({ employee_id: row.employee_id, employee_name: row.Empleado, day: d, current_status: val });
                          setNewStatus(val);
                        }}
                        style={{ 
                        textAlign: 'center', 
                        backgroundColor: getCellBg(val),
                        opacity: dimmed ? 0.1 : 1, 
                        transition: 'opacity 0.2s',
                        padding: '8px 4px',
                        verticalAlign: 'middle',
                        border: '1px solid rgba(255,255,255,0.05)',
                        cursor: 'pointer'
                    }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                         <span style={{ fontSize: '1.2rem', marginBottom: '4px' }}>
                           {val === 'Asistencia' ? '✅' : val === 'Falta' ? '❌' : val === 'Permiso' ? '📋' : '🔘'}
                         </span>
                         <span style={{ fontSize: '0.65rem', fontWeight: 600, color: val === 'Asistencia' ? 'var(--success)' : val === 'Falta' ? 'var(--danger)' : val === 'Permiso' ? 'var(--warning)' : 'var(--text-muted)' }}>
                           {val}
                         </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedCell && (
        <div className="modal-overlay" onClick={() => setSelectedCell(null)}>
          <div className="modal-content" style={{ maxWidth: '400px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>Modificar Estado</h3>
              <button className="btn btn-danger" style={{ padding: '4px 8px' }} onClick={() => setSelectedCell(null)}>✖</button>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: '8px' }}><strong>Empleado:</strong> {selectedCell.employee_name}</p>
              <p style={{ marginBottom: '16px' }}><strong>Fecha:</strong> {selectedCell.day}/{month.toString().padStart(2, '0')}/{year}</p>
              
              <div className="form-group">
                <label className="form-label">Nuevo Estado:</label>
                <select value={newStatus} onChange={e => setNewStatus(e.target.value)}>
                  <option value="Asistencia">✅ Asistencia</option>
                  <option value="Falta">❌ Falta</option>
                  <option value="Permiso">📋 Permiso</option>
                  <option value="No Laborable">🔘 No Laborable</option>
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
                <button className="btn" onClick={() => setSelectedCell(null)}>Cancelar</button>
                <button className="btn btn-primary" onClick={handleOverride}>Confirmar Cambio</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
