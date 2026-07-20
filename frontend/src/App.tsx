import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { BacktestingPage } from "./pages/BacktestingPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { DeploymentPage } from "./pages/DeploymentPage";
import { EmergencyPage } from "./pages/EmergencyPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RiskPage } from "./pages/RiskPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StrategiesPage } from "./pages/StrategiesPage";

function withLayout(element: JSX.Element) {
  return (
    <ProtectedRoute>
      <Layout>{element}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={withLayout(<OverviewPage />)} />
      <Route path="/strategies" element={withLayout(<StrategiesPage />)} />
      <Route path="/backtesting" element={withLayout(<BacktestingPage />)} />
      <Route path="/deployment" element={withLayout(<DeploymentPage />)} />
      <Route path="/risk" element={withLayout(<RiskPage />)} />
      <Route path="/connectors" element={withLayout(<ConnectorsPage />)} />
      <Route path="/settings" element={withLayout(<SettingsPage />)} />
      <Route path="/emergency" element={withLayout(<EmergencyPage />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
