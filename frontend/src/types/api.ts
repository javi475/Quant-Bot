export interface StrategySummary {
  id: string;
  name: string;
  asset_class: string;
  state: string;
  tags: string[];
  active_version_id: string | null;
}

export interface StrategyVersion {
  id: string;
  version: string;
  class_name: string;
  checksum_sha256: string;
  is_active: boolean;
  created_at: string;
}

export interface WalkForwardSummary {
  is_sharpe: number;
  oos_sharpe: number;
  degradation_pct: number;
  passed: boolean;
  meets_target: boolean;
}

export interface MonteCarloSummary {
  iterations: number;
  prob_of_ruin: number;
  max_drawdown_median: number;
  max_drawdown_p95: number;
}

export interface BacktestSummary {
  run_id: string;
  metrics: Record<string, number>;
  walk_forward: WalkForwardSummary | null;
  monte_carlo: MonteCarloSummary | null;
  gates_passed: boolean;
  gate_failures: string[];
  created_at: string;
}

export interface ConnectorSummary {
  id: string;
  name: string;
  connector_type: string;
  asset_class: string;
  is_active: boolean;
  config: Record<string, unknown>;
}

export interface SafeModeState {
  active: boolean;
  phase: string;
  triggered_by: string | null;
  halt_new_entries: boolean;
  requires_manual_restart: boolean;
}

export interface EngineStrategyState {
  enabled: boolean;
  webhook_driven: boolean;
  connector_id: string;
}

export interface EngineState {
  equity: number;
  unrealized_pnl: number;
  gross_exposure_value: number;
  open_position_count: number;
  halted: boolean;
  safe_mode: SafeModeState;
  strategies: Record<string, EngineStrategyState>;
}

export interface RiskParams {
  kelly_multiplier: number;
  max_risk_per_trade: number;
  daily_loss_breaker: number;
  max_drawdown: number;
  max_concurrent_positions: number;
  max_gross_exposure: number;
  correlation_cap: number;
  heartbeat_timeout_seconds: number;
  post_breaker_size_mult: number;
  post_breaker_duration_hours: number;
  max_leverage: number;
  correlation_lookback_days: number;
  drawdown_alert_1: number;
  drawdown_alert_2: number;
  drawdown_alert_3: number;
  recovery_phase_1_days: number;
  recovery_phase_2_days: number;
  recovery_phase_3_days: number;
  heartbeat_interval_seconds: number;
  watchdog_check_interval_seconds: number;
  min_portfolio_value: number;
  per_strategy_min_allocation: number;
  per_strategy_max_allocation: number;
  cash_reserve_min: number;
}

export interface Trade {
  trade_id: string;
  strategy_id: string;
  asset: string;
  side: string;
  quantity: number;
  entry_time: string;
  entry_price: number;
  exit_time: string | null;
  exit_price: number | null;
  pnl: number | null;
}

export interface TelegramSettings {
  bot_token_masked: string;
  bot_token_set: boolean;
  chat_id: string;
  alert_priority: string;
}

export interface WebhookSettings {
  webhook_secret_masked: string;
  webhook_secret_set: boolean;
  webhook_url: string;
}

export interface BreakerHistoryEvent {
  event_type: string;
  severity: string;
  description: string;
  action_taken: string;
  safe_mode_activated: boolean;
  occurred_at: string;
}
