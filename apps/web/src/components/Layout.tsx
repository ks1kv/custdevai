/**
 * Layout — основной shell приложения с боковой навигацией.
 * Используется обёрткой для всех защищённых страниц.
 */

import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/Button";
import { t } from "@/lib/locales/ru";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="layout">
      <nav>
        <h1>{t.app.title}</h1>
        <NavLink to="/" end>{t.nav.dashboard}</NavLink>
        <NavLink to="/scripts">{t.nav.scripts}</NavLink>
        <NavLink to="/campaigns">{t.nav.campaigns}</NavLink>
        <NavLink to="/archive">{t.nav.archive}</NavLink>
        <NavLink to="/compare">{t.nav.compare}</NavLink>
        <NavLink to="/settings">{t.nav.settings}</NavLink>
        <div className="spacer" />
        {user && (
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>
            {user.full_name || user.email}
            <br />
            <span style={{ color: "#64748b" }}>
              {user.roles.join(", ")}
            </span>
          </div>
        )}
        <Button variant="secondary" size="sm" onClick={handleLogout}>
          {t.nav.logout}
        </Button>
      </nav>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
