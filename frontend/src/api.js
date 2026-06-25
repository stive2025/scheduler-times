import axios from 'axios';

// Usamos ruta relativa. En desarrollo Vite hara proxy, en produccion Nginx hara proxy.
export const api = axios.create({
  baseURL: '/api',
});

// Auth endpoints
export const login = (username, password) => api.post('/auth/login', { username, password }).then(r => r.data);
export const changePassword = (username, old_password, new_password) => 
  api.post('/auth/change-password', { username, old_password, new_password }).then(r => r.data);

// Data endpoints
export const getDashboardData = () => api.get('/dashboard/data').then(r => r.data);
export const getKpis = () => api.get('/dashboard/kpis').then(r => r.data);
export const getCalendarMatrix = (year, month) => api.get(`/calendar?year=${year}&month=${month}`).then(r => r.data);

// System endpoints
export const getSystemStatus = () => api.get('/system/status').then(r => r.data);
export const triggerSync = () => api.post('/system/sync').then(r => r.data);

// Configurations
export const getJustifications = (month) => api.get(`/justifications${month ? `?month=${month}` : ''}`).then(r => r.data);
export const createJustification = (data) => api.post('/justifications', data).then(r => r.data);
export const deleteJustification = (id) => api.delete(`/justifications/${id}`).then(r => r.data);

export const toggleUserStatus = (username, is_active) => api.put(`/users/${username}/status`, { is_active }).then(r => r.data);

export const getSchedules = () => api.get('/schedules').then(r => r.data);
export const updateSchedule = (data) => api.post('/schedules', data).then(r => r.data);
export const saveCalendarOverrides = (entries) => api.post('/calendar/overrides', entries).then(r => r.data);
export const overrideSchedule = (data) => api.post('/calendar/override_schedule', data).then(r => r.data);
