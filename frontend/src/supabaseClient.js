import { createClient } from '@supabase/supabase-js';

// Both values are public (safe to ship in the bundle). webpack DefinePlugin
// replaces process.env.SUPABASE_* with string literals at build time — so we
// reference them DIRECTLY (no `typeof process` guard, which would be false in
// the browser and defeat the replacement). URL falls back to the current
// origin, which works behind the nginx /auth/v1 proxy (single-host deployment).
const supabaseUrl = process.env.SUPABASE_URL || window.location.origin;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY || '';

// createClient() throws "supabaseKey is required." on an empty key, which would
// crash the whole SPA at import time (blank page, no message). Surface a clear,
// actionable error instead — this only happens on a misbuilt bundle.
export const supabaseConfigured = Boolean(supabaseAnonKey);
if (!supabaseConfigured) {
  // eslint-disable-next-line no-console
  console.error(
    'SUPABASE_ANON_KEY was not set at build time. Set it (and SUPABASE_URL if ' +
      'not same-origin) before building the frontend — authentication is disabled.'
  );
}

export const supabase = createClient(
  supabaseUrl,
  // Fall back to a harmless placeholder so createClient doesn't throw; any auth
  // call will fail cleanly (and ProtectedRoute keeps users on /login) instead
  // of white-screening the app.
  supabaseAnonKey || 'anon-key-not-configured',
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      storage: window.localStorage,
    },
  }
);
