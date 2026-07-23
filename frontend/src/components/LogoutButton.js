import React, { useState } from 'react';
import { supabase } from '../supabaseClient';
import './LogoutButton.css';

// Fixed top-right sign-out control, rendered by ProtectedRoute so it is
// present on every authenticated page. Navigation back to /login happens via
// ProtectedRoute's onAuthStateChange listener once the session is cleared.
const LogoutButton = () => {
  const [loading, setLoading] = useState(false);

  const handleLogout = async () => {
    setLoading(true);
    // signOut clears the local session even if revoking the refresh token
    // server-side fails (e.g. offline), so we always end up logged out.
    await supabase.auth.signOut();
    setLoading(false);
  };

  return (
    <button
      type="button"
      className="logout-button"
      onClick={handleLogout}
      disabled={loading}
    >
      {loading ? 'Signing out…' : 'Sign out'}
    </button>
  );
};

export default LogoutButton;
