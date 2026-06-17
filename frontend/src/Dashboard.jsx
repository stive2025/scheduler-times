import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { getKpis, getDashboardData, triggerSync, getSystemStatus } from './api';
import { RefreshCw, Users, Clock, AlertTriangle, XCircle, HelpCircle, CheckCircle } from 'lucide-react';

const PlotComponent = Plot.default || Plot;

const formatDate = (dateString) => {
  if (!dateString) return '';
  const datePart = dateString.split('T')[0];
  const parts = datePart.split('-');
  if (parts.length !== 3) return datePart;
  const [year, month, day] = parts;
  return `${day}/${month}/${year.slice(-2)}`;
};

export default function Dashboard({ role, theme }) {
  const fontColor = theme === 'light' ? '#0f172a' : '#f8fafc';
  const gridColor = theme === 'light' ? '#e5e7eb' : '#21262d';
  const [kpis, setKpis] = useState(null);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  // Filters
  const [month, setMonth] = useState('Todos');
  const [jornada, setJornada] = useState('Todas');
  const [estado, setEstado] = useState('Todos');
  const [empleado, setEmpleado] = useState('Todos');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [tableFilter, setTableFilter] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 50;

  useEffect(() => {
    setCurrentPage(1);
  }, [month, jornada, estado, empleado, startDate, endDate, sortConfig]);

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const fetchData = () => {
    setLoading(true);
    Promise.all([getKpis(), getDashboardData(), getSystemStatus()])
      .then(([k, d, s]) => {
        setKpis(k);
        setData(d);
        setStatus(s);
        setLoading(false);
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await triggerSync();
      fetchData();
      alert(res.message || "Sincronización completada exitosamente.");
    } catch (e) {
      alert("Error al sincronizar");
    } finally {
      setSyncing(false);
    }
  };

  if (loading || !data) {
    return <div className="loader-container"><div className="spinner"></div></div>;
  }

  // Extract unique employees for filter dropdown
  const empleados = Array.from(new Set((data?.data || []).map(r => r.nom_corto))).sort();

  // Filter Data
  let filtered = [...(data?.data || [])];
  if (month !== 'Todos') filtered = filtered.filter(r => r.mes === month);
  if (jornada !== 'Todas') filtered = filtered.filter(r => r.Jornada === jornada);
  if (estado !== 'Todos') filtered = filtered.filter(r => r.estado === estado);
  if (empleado !== 'Todos') filtered = filtered.filter(r => r.nom_corto === empleado);
  if (startDate) filtered = filtered.filter(r => r.Fecha && r.Fecha.split('T')[0] >= startDate);
  if (endDate) filtered = filtered.filter(r => r.Fecha && r.Fecha.split('T')[0] <= endDate);

  if (sortConfig.key) {
    filtered.sort((a, b) => {
      let valA = a[sortConfig.key];
      let valB = b[sortConfig.key];
      if (valA === undefined || valA === null) valA = '';
      if (valB === undefined || valB === null) valB = '';
      if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
      if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }

  // Table Filter Data (Drill Down)
  let filteredTable = filtered;
  if (tableFilter) {
    if (tableFilter.type === 'estado') filteredTable = filteredTable.filter(r => r.estado === tableFilter.value);
    if (tableFilter.type === 'empleado') filteredTable = filteredTable.filter(r => r.nom_corto === tableFilter.value);
    if (tableFilter.type === 'empleado_atrasos') filteredTable = filteredTable.filter(r => r.nom_corto === tableFilter.value && r.total_atraso > 0);
    if (tableFilter.type === 'empleado_olvidos') filteredTable = filteredTable.filter(r => r.nom_corto === tableFilter.value && (r.olvidos > 0 || r.estado === 'Olvido'));
    if (tableFilter.type === 'fecha') filteredTable = filteredTable.filter(r => r.Fecha && r.Fecha.split('T')[0] === tableFilter.value);
  }

  // Dynamic KPIs based on filtered data
  const dynamicKpis = {
    n_emp: new Set(filtered.map(r => r.nom_corto)).size,
    tot_h: filtered.reduce((acc, r) => acc + (r.horas_trab || 0), 0),
    tot_atr: filtered.reduce((acc, r) => acc + (r.total_atraso || 0), 0),
    tot_sal: filtered.reduce((acc, r) => acc + (r.total_sal_ant || 0), 0),
    n_olv: filtered.reduce((acc, r) => acc + (r.olvidos || 0), 0) + filtered.filter(r => r.estado === 'Olvido' && (!r.olvidos || r.olvidos === 0)).length,
    pct_ok: filtered.length > 0 ? (filtered.filter(r => r.estado === 'A Tiempo').length / filtered.length) * 100 : 0
  };

  // Pie Chart Data
  const stateCounts = filtered.reduce((acc, row) => {
    acc[row.estado] = (acc[row.estado] || 0) + 1;
    return acc;
  }, {});

  const pieColors = {
    "A Tiempo": "#3fb950",
    "Con Atraso": "#eab308",
    "Salida Anticipada": "#ef4444",
    "Olvido": "#a855f7",
    "Falta": "#ef4444"
  };

  const pieData = [{
    values: Object.values(stateCounts),
    labels: Object.keys(stateCounts),
    type: 'pie',
    hole: 0.6,
    marker: {
      colors: Object.keys(stateCounts).map(k => pieColors[k] || "#8b949e"),
      line: { color: '#09090b', width: 2 }
    },
    textinfo: 'percent+label',
  }];

  const pieLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: fontColor, family: 'Inter' },
    margin: { t: 40, b: 20, l: 20, r: 20 },
    showlegend: true,
    legend: { orientation: 'h', y: -0.1 },
    annotations: [{ text: `${filtered.length} Registros`, showarrow: false, font: { size: 16 } }]
  };

  // Top 5 Atrasos Data
  const topAtrasosData = filtered.reduce((acc, row) => {
    acc[row.nom_corto] = (acc[row.nom_corto] || 0) + (row.total_atraso || 0);
    return acc;
  }, {});
  const topAtrasosSorted = Object.entries(topAtrasosData)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .reverse();

  const barTopAtrasos = [{
    type: 'bar',
    x: topAtrasosSorted.map(x => x[1]),
    y: topAtrasosSorted.map(x => x[0]),
    orientation: 'h',
    marker: { color: topAtrasosSorted.map(x => x[1]), colorscale: [[0, "#1f3a5f"], [0.5, "#d29922"], [1, "#f85149"]] },
    text: topAtrasosSorted.map(x => `${x[1]} min`),
    textposition: 'outside'
  }];

  const layoutTopAtrasos = {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: fontColor, family: 'Inter' },
    margin: { t: 20, b: 40, l: 120, r: 40 },
    xaxis: { gridcolor: gridColor }
  };

  // Olvidos por Empleado
  const olvidosData = filtered.reduce((acc, row) => {
    acc[row.nom_corto] = (acc[row.nom_corto] || 0) + (row.olvidos || 0);
    return acc;
  }, {});
  const olvidosSorted = Object.entries(olvidosData).filter(x => x[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 10);

  const barOlvidos = [{
    type: 'bar',
    x: olvidosSorted.map(x => x[0]),
    y: olvidosSorted.map(x => x[1]),
    marker: { color: olvidosSorted.map(x => x[1]), colorscale: [[0, "#21262d"], [0.5, "#bc8cff"], [1, "#f85149"]] },
    text: olvidosSorted.map(x => x[1]),
    textposition: 'outside'
  }];

  const layoutOlvidos = {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: fontColor, family: 'Inter' },
    margin: { t: 20, b: 60, l: 40, r: 20 },
    yaxis: { gridcolor: gridColor }
  };

  // Horas Trabajadas
  const horasData = filtered.reduce((acc, row) => {
    acc[row.nom_corto] = (acc[row.nom_corto] || 0) + (row.horas_trab || 0);
    return acc;
  }, {});
  const horasSorted = Object.entries(horasData).sort((a, b) => b[1] - a[1]).slice(0, 15);

  const barHoras = [{
    type: 'bar',
    x: horasSorted.map(x => x[0]),
    y: horasSorted.map(x => x[1]),
    marker: { color: horasSorted.map(x => x[1]), colorscale: [[0, "#1a3a5c"], [1, "#58a6ff"]] },
    text: horasSorted.map(x => `${x[1].toFixed(1)}h`),
    textposition: 'outside'
  }];

  const layoutHoras = {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: fontColor, family: 'Inter' },
    margin: { t: 20, b: 60, l: 40, r: 20 },
    yaxis: { gridcolor: gridColor }
  };

  // Evolución Temporal (Atrasos vs Horas)
  const dailyData = filtered.reduce((acc, row) => {
    const d = row.Fecha ? row.Fecha.split('T')[0] : null;
    if (!d) return acc;
    if (!acc[d]) acc[d] = { atraso: 0, horas: 0 };
    acc[d].atraso += (row.total_atraso || 0);
    acc[d].horas += (row.horas_trab || 0);
    return acc;
  }, {});
  const sortedDates = Object.keys(dailyData).sort();

  const lineEvolucion = [
    {
      type: 'scatter',
      x: sortedDates,
      y: sortedDates.map(d => dailyData[d].atraso),
      name: 'Min. Atraso',
      line: { color: '#d29922', width: 2 },
      fill: 'tozeroy',
      fillcolor: 'rgba(210,153,34,0.15)'
    },
    {
      type: 'scatter',
      x: sortedDates,
      y: sortedDates.map(d => dailyData[d].horas),
      name: 'Horas Trabajadas',
      yaxis: 'y2',
      line: { color: '#58a6ff', width: 2 }
    }
  ];

  const layoutEvolucion = {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: fontColor, family: 'Inter' },
    margin: { t: 20, b: 40, l: 40, r: 40 },
    legend: { orientation: 'h', y: -0.2 },
    xaxis: { gridcolor: gridColor },
    yaxis: { title: 'Min. Atraso', gridcolor: gridColor },
    yaxis2: { title: 'Horas Trabajadas', overlaying: 'y', side: 'right', showgrid: false }
  };

  const SortIndicator = ({ columnKey }) => {
    if (sortConfig.key !== columnKey) return null;
    return <span>{sortConfig.direction === 'asc' ? ' ↑' : ' ↓'}</span>;
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1>Resumen y KPIs</h1>
          <p className="subtitle" style={{ margin: 0 }}>Estadísticas mensuales de asistencia</p>
        </div>
        {role !== 'rrhh' && (
          <button className="btn btn-primary" onClick={handleSync} disabled={syncing}>
            <RefreshCw size={16} className={syncing ? "spin" : ""} /> 
            {syncing ? 'Sincronizando...' : 'Forzar Sincronización DB'}
          </button>
        )}
      </div>

      <div className="kpi-grid">
        <div className="glass-panel kpi-card">
          <Users className="kpi-icon" style={{ color: '#38bdf8' }} />
          <div className="kpi-value">{dynamicKpis.n_emp}</div>
          <div className="kpi-label">Empleados</div>
        </div>
        <div className="glass-panel kpi-card">
          <Clock className="kpi-icon" style={{ color: '#3fb950' }} />
          <div className="kpi-value">{dynamicKpis.tot_h.toFixed(1)} h</div>
          <div className="kpi-label">Horas Trabajadas</div>
        </div>
        <div className="glass-panel kpi-card">
          <AlertTriangle className="kpi-icon" style={{ color: '#eab308' }} />
          <div className="kpi-value">{dynamicKpis.tot_atr} min</div>
          <div className="kpi-label">Atrasos Totales</div>
        </div>
        <div className="glass-panel kpi-card">
          <XCircle className="kpi-icon" style={{ color: '#ef4444' }} />
          <div className="kpi-value">{dynamicKpis.tot_sal} min</div>
          <div className="kpi-label">Salidas Anticipadas</div>
        </div>
        <div className="glass-panel kpi-card">
          <HelpCircle className="kpi-icon" style={{ color: '#a855f7' }} />
          <div className="kpi-value">{dynamicKpis.n_olv}</div>
          <div className="kpi-label">Olvidos de Marca</div>
        </div>
        <div className="glass-panel kpi-card">
          <CheckCircle className="kpi-icon" style={{ color: '#3fb950' }} />
          <div className="kpi-value">{dynamicKpis.pct_ok.toFixed(1)}%</div>
          <div className="kpi-label">Puntualidad Global</div>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
           <h3>Filtros de Búsqueda</h3>
           <button className="btn btn-danger" onClick={() => {
              setMonth('Todos'); setJornada('Todas'); setEstado('Todos'); setEmpleado('Todos'); setStartDate(''); setEndDate('');
              setTableFilter(null);
           }}>Resetear Filtros</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '16px' }}>
          <div>
            <label className="form-label">Empleado</label>
            <select value={empleado} onChange={e => setEmpleado(e.target.value)}>
              <option value="Todos">Todos</option>
              {empleados.map(e => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Mes Rápido</label>
            <select value={month} onChange={e => setMonth(e.target.value)}>
              <option value="Todos">Todos</option>
              {(data?.months || []).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Jornada</label>
            <select value={jornada} onChange={e => setJornada(e.target.value)}>
              <option value="Todas">Todas</option>
              {(data?.jornadas || []).map(j => <option key={j} value={j}>{j}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Estado</label>
            <select value={estado} onChange={e => setEstado(e.target.value)}>
              <option value="Todos">Todos</option>
              <option value="A Tiempo">A Tiempo</option>
              <option value="Con Atraso">Con Atraso</option>
              <option value="Salida Anticipada">Salida Anticipada</option>
              <option value="Olvido">Olvido</option>
              <option value="Falta">Falta</option>
              <option value="Medio Tiempo">Medio Tiempo</option>
            </select>
          </div>
          <div>
            <label className="form-label">Desde</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Hasta</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="charts-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <div className="glass-panel chart-container">
          <h3>Estado Global de Asistencias</h3>
          <PlotComponent 
            data={pieData} 
            layout={pieLayout} 
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', height: '320px' }}
            onClick={(d) => { if(d.points?.[0]) setTableFilter({ type: 'estado', value: d.points[0].label }); }}
          />
        </div>
        <div className="glass-panel chart-container">
          <h3>Top 5 — Mayores Atrasos</h3>
          <PlotComponent 
            data={barTopAtrasos} 
            layout={layoutTopAtrasos} 
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', height: '320px' }}
            onClick={(d) => { if(d.points?.[0]) setTableFilter({ type: 'empleado_atrasos', value: d.points[0].y }); }}
          />
        </div>
      </div>

      <div className="glass-panel chart-container" style={{ marginBottom: '24px' }}>
        <h3>Evolución Temporal — Atrasos vs Horas</h3>
        <PlotComponent 
          data={lineEvolucion} 
          layout={layoutEvolucion} 
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%', height: '350px' }}
          onClick={(d) => { 
            if(d.points?.[0]) {
              setTableFilter({ type: 'fecha', value: d.points[0].x });
            }
          }}
        />
      </div>

      <div className="charts-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <div className="glass-panel chart-container">
          <h3>Total Horas Trabajadas (Top 15)</h3>
          <PlotComponent 
            data={barHoras} 
            layout={layoutHoras} 
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', height: '320px' }}
            onClick={(d) => { if(d.points?.[0]) setTableFilter({ type: 'empleado', value: d.points[0].x }); }}
          />
        </div>
        <div className="glass-panel chart-container">
          <h3>Olvidos de Marcación</h3>
          <PlotComponent 
            data={barOlvidos} 
            layout={layoutOlvidos} 
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', height: '320px' }}
            onClick={(d) => { if(d.points?.[0]) setTableFilter({ type: 'empleado_olvidos', value: d.points[0].x }); }}
          />
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '24px', overflowX: 'auto', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0 }}>Listado de Marcaciones</h3>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{filtered.length} registros</span>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort('nom_corto')} style={{ cursor: 'pointer' }}>Empleado <SortIndicator columnKey="nom_corto" /></th>
                <th onClick={() => handleSort('Fecha')} style={{ cursor: 'pointer' }}>Fecha <SortIndicator columnKey="Fecha" /></th>
                <th onClick={() => handleSort('Horario Detectado')} style={{ cursor: 'pointer' }}>Horario <SortIndicator columnKey="Horario Detectado" /></th>
                <th onClick={() => handleSort('Jornada')} style={{ cursor: 'pointer' }}>Jornada <SortIndicator columnKey="Jornada" /></th>
                <th onClick={() => handleSort('Entrada Mañana')} style={{ cursor: 'pointer' }}>Ent. Mañana <SortIndicator columnKey="Entrada Mañana" /></th>
                <th onClick={() => handleSort('Salida Mañana')} style={{ cursor: 'pointer' }}>Sal. Mañana <SortIndicator columnKey="Salida Mañana" /></th>
                <th onClick={() => handleSort('Entrada Tarde')} style={{ cursor: 'pointer' }}>Ent. Tarde <SortIndicator columnKey="Entrada Tarde" /></th>
                <th onClick={() => handleSort('Salida Tarde')} style={{ cursor: 'pointer' }}>Sal. Tarde <SortIndicator columnKey="Salida Tarde" /></th>
                <th onClick={() => handleSort('total_atraso')} style={{ cursor: 'pointer' }}>Atr. Total <SortIndicator columnKey="total_atraso" /></th>
                <th onClick={() => handleSort('horas_trab')} style={{ cursor: 'pointer' }}>Horas Trab. <SortIndicator columnKey="horas_trab" /></th>
                <th onClick={() => handleSort('estado')} style={{ cursor: 'pointer' }}>Estado <SortIndicator columnKey="estado" /></th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize).map((row, i) => (
                <tr key={i}>
                  <td>{row.nom_corto}</td>
                  <td>{formatDate(row.Fecha)}</td>
                  <td>{row['Horario Detectado']}</td>
                  <td>{row.Jornada}</td>
                  <td>{row['Entrada Mañana'] || '-'}</td>
                  <td>{row['Salida Mañana'] || '-'}</td>
                  <td>{row['Entrada Tarde'] || '-'}</td>
                  <td>{row['Salida Tarde'] || '-'}</td>
                  <td style={{ color: row.total_atraso > 0 ? 'var(--warning)' : '' }}>
                    {row.total_atraso} min
                  </td>
                  <td>{row.horas_trab?.toFixed(2)} h</td>
                  <td>
                    <span className={`badge ${
                      row.estado === 'A Tiempo' ? 'badge-success' : 
                      row.estado === 'Falta' ? 'badge-danger' : 
                      row.estado === 'Salida Anticipada' ? 'badge-danger' : 
                      row.estado === 'Permiso' ? 'badge-warning' : 
                      row.estado === 'Con Atraso' ? 'badge-warning' : 
                      row.estado === 'Olvido' ? 'badge-purple' : 'badge-neutral'
                    }`}>
                      {row.estado}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Mostrando {filtered.length > 0 ? (currentPage - 1) * pageSize + 1 : 0} a {Math.min(currentPage * pageSize, filtered.length)} de {filtered.length} registros
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn" disabled={currentPage === 1} onClick={() => setCurrentPage(p => Math.max(1, p - 1))}>Anterior</button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 12px' }}>
              Página {currentPage} de {Math.ceil(filtered.length / pageSize) || 1}
            </span>
            <button 
              className="btn" 
              disabled={currentPage >= Math.ceil(filtered.length / pageSize) || filtered.length === 0} 
              onClick={() => setCurrentPage(p => p + 1)}
            >
              Siguiente
            </button>
          </div>
        </div>
      </div>

      {tableFilter && (
        <div className="modal-overlay" onClick={() => setTableFilter(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 style={{ margin: 0 }}>
                Detalles: {tableFilter.type === 'estado' ? 'Estado' : tableFilter.type === 'empleado' ? 'Empleado' : 'Fecha'} = {tableFilter.value}
              </h2>
              <button className="btn btn-danger" onClick={() => setTableFilter(null)}>✖ Cerrar</button>
            </div>
            <div className="modal-body">
              <div style={{ marginBottom: '16px', textAlign: 'right', color: 'var(--text-muted)' }}>
                {filteredTable.length} registros encontrados
              </div>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th onClick={() => handleSort('nom_corto')} style={{ cursor: 'pointer' }}>Empleado <SortIndicator columnKey="nom_corto" /></th>
                      <th onClick={() => handleSort('Fecha')} style={{ cursor: 'pointer' }}>Fecha <SortIndicator columnKey="Fecha" /></th>
                      <th onClick={() => handleSort('Horario Detectado')} style={{ cursor: 'pointer' }}>Horario <SortIndicator columnKey="Horario Detectado" /></th>
                      <th onClick={() => handleSort('Jornada')} style={{ cursor: 'pointer' }}>Jornada <SortIndicator columnKey="Jornada" /></th>
                      <th onClick={() => handleSort('Entrada Mañana')} style={{ cursor: 'pointer' }}>Ent. Mañana <SortIndicator columnKey="Entrada Mañana" /></th>
                      <th onClick={() => handleSort('Salida Mañana')} style={{ cursor: 'pointer' }}>Sal. Mañana <SortIndicator columnKey="Salida Mañana" /></th>
                      <th onClick={() => handleSort('Entrada Tarde')} style={{ cursor: 'pointer' }}>Ent. Tarde <SortIndicator columnKey="Entrada Tarde" /></th>
                      <th onClick={() => handleSort('Salida Tarde')} style={{ cursor: 'pointer' }}>Sal. Tarde <SortIndicator columnKey="Salida Tarde" /></th>
                      <th onClick={() => handleSort('total_atraso')} style={{ cursor: 'pointer' }}>Atr. Total <SortIndicator columnKey="total_atraso" /></th>
                      <th onClick={() => handleSort('horas_trab')} style={{ cursor: 'pointer' }}>Horas Trab. <SortIndicator columnKey="horas_trab" /></th>
                      <th onClick={() => handleSort('estado')} style={{ cursor: 'pointer' }}>Estado <SortIndicator columnKey="estado" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTable.slice(0, 100).map((row, i) => (
                      <tr key={i}>
                        <td>{row.nom_corto}</td>
                        <td>{formatDate(row.Fecha)}</td>
                        <td>{row['Horario Detectado']}</td>
                        <td>{row.Jornada}</td>
                        <td>{row['Entrada Mañana'] || '-'}</td>
                        <td>{row['Salida Mañana'] || '-'}</td>
                        <td>{row['Entrada Tarde'] || '-'}</td>
                        <td>{row['Salida Tarde'] || '-'}</td>
                        <td style={{ color: row.total_atraso > 0 ? 'var(--warning)' : '' }}>
                          {row.total_atraso} min
                        </td>
                        <td>{row.horas_trab?.toFixed(2)} h</td>
                        <td>
                          <span className={`badge ${
                            row.estado === 'A Tiempo' ? 'badge-success' : 
                            row.estado === 'Falta' ? 'badge-danger' : 
                            row.estado === 'Salida Anticipada' ? 'badge-danger' : 
                            row.estado === 'Permiso' ? 'badge-warning' : 
                            row.estado === 'Con Atraso' ? 'badge-warning' : 
                            row.estado === 'Olvido' ? 'badge-purple' : 'badge-neutral'
                          }`}>
                            {row.estado}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredTable.length > 100 && (
                <div style={{ textAlign: 'center', marginTop: '16px', color: 'var(--text-muted)' }}>
                  Mostrando los primeros 100 registros...
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
