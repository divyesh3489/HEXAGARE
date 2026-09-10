import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useIsAuthenticated } from "@/hooks/use-auth";

/** Gate for the authenticated app. Redirects to /login, preserving the target. */
export function ProtectedRoute() {
  const isAuthenticated = useIsAuthenticated();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
