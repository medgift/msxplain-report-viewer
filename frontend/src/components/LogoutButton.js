import React, { useState } from 'react';
import { signOutEverywhere } from '../api';
import './LogoutButton.css';

// Fixed top-right sign-out control, rendered by ProtectedRoute so it is
// present on every authenticated page. Navigation back to /login happens via
// ProtectedRoute's onAuthStateChange listener once the session is cleared.
const LogoutButton = () => {
  const [loading, setLoading] = useState(false);

  const handleLogout = async () => {
    setLoading(true);
    // Clears the OHIF viewer cookie, then the Supabase session. signOut clears
    // the local session even if revoking server-side fails (e.g. offline), so
    // we always end up logged out.
    await signOutEverywhere();
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
