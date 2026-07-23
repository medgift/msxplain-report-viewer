import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { supabase } from '../supabaseClient';
import LogoutButton from './LogoutButton';

// Gates its children behind an authenticated Supabase session. While the
// session is being resolved we render nothing to avoid a login/content flash.
const ProtectedRoute = ({ children }) => {
  const [status, setStatus] = useState('loading'); // loading | in | out

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (active) setStatus(data && data.session ? 'in' : 'out');
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) setStatus(session ? 'in' : 'out');
    });

    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  if (status === 'loading') return null;
  if (status === 'out') return <Navigate to="/login" replace />;
  return (
    <>
      <LogoutButton />
      {children}
    </>
  );
};

export default ProtectedRoute;
