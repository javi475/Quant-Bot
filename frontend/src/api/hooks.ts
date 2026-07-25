import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "./client";
import type {
  BacktestSummary,
  BreakerHistoryEvent,
  ConnectorSummary,
  EngineState,
  RiskParams,
  StrategySummary,
  StrategyVersion,
  TelegramSettings,
  Trade,
  WebhookSettings,
} from "../types/api";

// ----- Auth -----

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function useLogin() {
  return useMutation({
    mutationFn: (req: LoginRequest) => apiClient.post<TokenResponse>("/api/auth/login", req),
  });
}

// ----- Monitoring -----

export function useEngineState(pollIntervalMs = 3000) {
  return useQuery({
    queryKey: ["monitoring", "state"],
    queryFn: () => apiClient.get<EngineState>("/api/monitoring/state"),
    refetchInterval: pollIntervalMs,
  });
}

// ----- Strategies -----

export function useStrategies() {
  return useQuery({
    queryKey: ["strategies"],
    queryFn: () => apiClient.get<StrategySummary[]>("/api/strategies"),
  });
}

export function useStrategyVersions(strategyId: string | null) {
  return useQuery({
    queryKey: ["strategies", strategyId, "versions"],
    queryFn: () => apiClient.get<StrategyVersion[]>(`/api/strategies/${strategyId}/versions`),
    enabled: strategyId !== null,
  });
}

export function useCreateStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { name: string; asset_class: string; tags: string[] }) =>
      apiClient.post<StrategySummary>("/api/strategies", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useUploadVersion(strategyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { source_code: string; class_name: string; parameters?: Record<string, unknown> }) =>
      apiClient.post<StrategyVersion>(`/api/strategies/${strategyId}/versions`, req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", strategyId, "versions"] });
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
  });
}

export function useActivateVersion(strategyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (version: string) =>
      apiClient.post<StrategyVersion>(`/api/strategies/${strategyId}/versions/${version}/activate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", strategyId, "versions"] });
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
  });
}

// ----- Backtests -----

export interface RunBacktestRequest {
  strategy_id: string;
  version?: string;
  config: Record<string, unknown>;
  bars: Record<string, unknown>[];
  initial_capital: number;
  run_walk_forward?: boolean;
  run_monte_carlo?: boolean;
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (req: RunBacktestRequest) => apiClient.post<BacktestSummary>("/api/backtests", req),
  });
}

export function useBacktests() {
  return useQuery({
    queryKey: ["backtests"],
    queryFn: () => apiClient.get<BacktestSummary[]>("/api/backtests"),
  });
}

// ----- Deployment -----

export function useDeploy() {
  return useMutation({
    mutationFn: (req: { strategy_id: string; config: Record<string, unknown>; version?: string }) =>
      apiClient.post<{ status: string; strategy_id: string; version: string; module_path: string }>(
        "/api/deployment/deploy",
        req,
      ),
  });
}

export function useHalt() {
  return useMutation({ mutationFn: () => apiClient.post<{ status: string }>("/api/deployment/halt") });
}

export function useFlatten() {
  return useMutation({ mutationFn: () => apiClient.post<{ status: string }>("/api/deployment/flatten") });
}

export function useKillSwitch() {
  return useMutation({ mutationFn: () => apiClient.post<{ status: string }>("/api/deployment/kill-switch") });
}

// ----- Connectors -----

export function useConnectors() {
  return useQuery({
    queryKey: ["connectors"],
    queryFn: () => apiClient.get<ConnectorSummary[]>("/api/connectors"),
  });
}

export function useCreateConnector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: {
      name: string;
      connector_type: string;
      asset_class: string;
      credentials: Record<string, string>;
      config?: Record<string, unknown>;
    }) => apiClient.post<ConnectorSummary>("/api/connectors", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["connectors"] }),
  });
}

export function useTestConnector() {
  return useMutation({
    mutationFn: (connectorId: string) =>
      apiClient.post<{ status: string; detail?: string }>(`/api/connectors/${connectorId}/test`),
  });
}

// ----- Risk -----

export function useRiskParams() {
  return useQuery({
    queryKey: ["risk", "params"],
    queryFn: () => apiClient.get<RiskParams>("/api/risk/params"),
  });
}

export function useUpdateRiskParams() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Partial<RiskParams>) => apiClient.put<RiskParams>("/api/risk/params", updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["risk", "params"] }),
  });
}

export function useBreakerHistory() {
  return useQuery({
    queryKey: ["risk", "breaker-history"],
    queryFn: () => apiClient.get<BreakerHistoryEvent[]>("/api/risk/breaker-history"),
  });
}

// ----- Trades -----

// ----- Settings / Telegram -----

export function useTelegramSettings() {
  return useQuery({
    queryKey: ["settings", "telegram"],
    queryFn: () => apiClient.get<TelegramSettings>("/api/settings/telegram"),
  });
}

export function useUpdateTelegramSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { bot_token: string; chat_id: string; alert_priority: string }) =>
      apiClient.put<TelegramSettings>("/api/settings/telegram", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "telegram"] }),
  });
}

export function useTestTelegram() {
  return useMutation({
    mutationFn: () => apiClient.post<{ status: string; detail: string }>("/api/settings/telegram/test"),
  });
}

export function useWebhookSettings() {
  return useQuery({
    queryKey: ["settings", "webhook"],
    queryFn: () => apiClient.get<WebhookSettings>("/api/settings/webhook"),
  });
}

export function useUpdateWebhookSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: { webhook_secret: string; webhook_url: string }) =>
      apiClient.put<WebhookSettings>("/api/settings/webhook", req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "webhook"] }),
  });
}

export function useTestWebhook() {
  return useMutation({
    mutationFn: () => apiClient.post<{ status: string; detail: string }>("/api/settings/webhook/test"),
  });
}

// ----- Trades -----

export function useTrades(strategyId?: string) {
  return useQuery({
    queryKey: ["trades", strategyId ?? "all"],
    queryFn: () =>
      apiClient.get<Trade[]>(`/api/trades${strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ""}`),
  });
}
