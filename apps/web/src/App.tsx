/**
 * App — корневой роутер CustDevAI SPA.
 *
 * Структура: /login (открыта); всё остальное под ProtectedRoute и Layout.
 */

import { Routes, Route, Navigate } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ScriptsListPage } from "./pages/ScriptsListPage";
import { ScriptBuilderPage } from "./pages/ScriptBuilderPage";
import { CampaignsListPage } from "./pages/CampaignsListPage";
import { CampaignCreatePage } from "./pages/CampaignCreatePage";
import { CampaignDetailPage } from "./pages/CampaignDetailPage";
import { CampaignComparePage } from "./pages/CampaignComparePage";
import { ArchivePage } from "./pages/ArchivePage";
import { ReportsPage } from "./pages/ReportsPage";
import { WizardPage } from "./pages/WizardPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="scripts" element={<ScriptsListPage />} />
        <Route path="scripts/new" element={<ScriptBuilderPage />} />
        <Route path="scripts/:id" element={<ScriptBuilderPage />} />
        <Route path="campaigns" element={<CampaignsListPage />} />
        <Route path="campaigns/new" element={<CampaignCreatePage />} />
        <Route path="campaigns/:id" element={<CampaignDetailPage />} />
        <Route path="campaigns/:id/reports" element={<ReportsPage />} />
        <Route path="archive" element={<ArchivePage />} />
        <Route path="compare" element={<CampaignComparePage />} />
        <Route path="wizard" element={<WizardPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
