import axios from 'axios';
import { supabase } from './supabaseClient';

// Central place to obtain the current access token. supabase-js refreshes it
// automatically, so we always read the freshest value right before a request.
export async function getAccessToken() {
  const { data } = await supabase.auth.getSession();
  return data && data.session ? data.session.access_token : null;
}

// Sign out of the app AND the OHIF viewer. The viewer authenticates with an
// HttpOnly cookie that JS cannot touch, so ask the backend to clear it first
// (while the access token is still valid), then end the Supabase session —
// which also revokes it server-side, so any lingering cookie stops working.
export async function signOutEverywhere() {
  try {
    const token = await getAccessToken();
    if (token) {
      await fetch('/api/viewer-session', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
        credentials: 'same-origin',
      });
    }
  } catch (err) {
    // Non-fatal: the backend rejects the cookie once the session is gone.
    console.error('Could not clear viewer session:', err);
  }
  await supabase.auth.signOut();
}

function redirectToLogin() {
  supabase.auth.signOut().finally(() => {
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  });
}

// Axios instance with bearer injection + 401 handling.
const api = axios.create();

api.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      redirectToLogin();
    }
    return Promise.reject(error);
  }
);

// fetch() wrapper for callers that need streaming/FormData semantics
// (uploads, polling). Injects the bearer token and handles 401 the same way.
export async function authFetch(url, options = {}) {
  const token = await getAccessToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    redirectToLogin();
  }
  return response;
}

export default api;
