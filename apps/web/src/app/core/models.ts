export interface Gameweek {
  id: number;
  number: number;
  name: string;
  finished: boolean;
  is_current: boolean;
  is_next: boolean;
  deadline_time: string | null;
}

export interface TeamPrediction {
  fixture_id: number;
  gameweek_number: number;
  home_team: string;
  away_team: string;
  kickoff_time: string | null;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  home_clean_sheet_prob: number;
  away_clean_sheet_prob: number;
  home_score_prob: number;
  away_score_prob: number;
}

export interface PlayerPrediction {
  player_id: number;
  fpl_element_id?: number | null;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  price: number;
  gameweek_number: number;
  expected_points: number;
  baseline_last_gw: number | null;
  baseline_ep_next: number | null;
}

export interface ModelMeta {
  model_version: string;
  last_etl_at: string | null;
  last_etl_job: string | null;
  last_etl_status: string | null;
}

export interface FixtureDifficultyCell {
  gameweek_number: number | null;
  opponent_short: string;
  is_home: boolean;
  fdr: number;
  difficulty_level: number;
  difficulty_label: string;
  difficulty_score: number;
}

export interface FixtureMetricCell {
  gameweek_number: number | null;
  opponent_short: string;
  is_home: boolean;
  value: number;
  /** Poisson expected goals (team), goals outlook only */
  expected_goals?: number;
}

export interface TeamMetricRun {
  team_id: number;
  team_name: string;
  short_name: string;
  team_code?: number | null;
  avg_clean_sheet_prob?: number;
  avg_score_prob?: number;
  gameweeks_covered: number;
  fixtures: FixtureMetricCell[];
}

export interface TeamFixtureRun {
  team_id: number;
  team_name: string;
  short_name: string;
  team_code?: number | null;
  overall_fdr: number;
  overall_difficulty_level?: number;
  overall_difficulty_label?: string;
  fixtures: FixtureDifficultyCell[];
  difficulty_model?: string;
  fixture_window?: number;
}

export interface TeamOutlookRow {
  team_id: number;
  team_name: string;
  short_name: string;
  avg_clean_sheet_prob?: number;
  avg_score_prob?: number;
  gameweeks_covered: number;
}

export interface CaptainPick {
  player_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  expected_points: number;
  captain_expected_points: number;
  ownership_pct: number;
}

export interface DefensiveContrib {
  player_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  threshold: number;
  likelihood: number;
  avg_minutes_last3: number;
}

export interface PlayerBrief {
  player_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  price: number;
  cost_change_event: number;
  cost_change_start: number;
  transfers_in_event: number;
  transfers_out_event: number;
  transfers_in: number;
  transfers_out: number;
  selected_by_percent: number;
}

export interface TopGwPlayer {
  player_id: number;
  web_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  gameweek_number: number;
  total_points: number;
  goals: number;
  assists: number;
  bonus: number;
}

export interface HomeDashboard {
  last_gameweek: number;
  price_risers: PlayerBrief[];
  price_fallers: PlayerBrief[];
  transfers_in: PlayerBrief[];
  transfers_out: PlayerBrief[];
  price_risers_all_time: PlayerBrief[];
  price_fallers_all_time: PlayerBrief[];
  transfers_in_all_time: PlayerBrief[];
  transfers_out_all_time: PlayerBrief[];
  top_last_gameweek: TopGwPlayer[];
}

export interface PlayerSeasonStat {
  player_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  price: number;
  minutes: number;
  total_points: number;
  goals: number;
  assists: number;
  bonus: number;
  bps: number;
  expected_goals: number;
  expected_assists: number;
  gameweeks_played: number;
}

export interface DeadlineMeta {
  deadline_time: string | null;
  server_time: string;
}

export type ChipId = 'wildcard' | 'bench_boost' | 'triple_captain' | 'free_hit';

export interface ChipPlayer {
  player_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  expected_points: number;
  triple_expected_points: number;
  n_fixtures: number;
  opponents: string;
  is_home?: boolean;
  expected_goals?: number;
}

export interface ChipWindow {
  chip: ChipId;
  chip_label: string;
  gameweek: number;
  score: number;
  confidence: 'high' | 'medium' | 'low' | string;
  headline: string;
  reason: string;
  flags: string[];
  player: ChipPlayer | null;
}

export interface ChipAdvice {
  chip: ChipId;
  chip_label: string;
  available: boolean;
  recommended_gameweek: number | null;
  windows: ChipWindow[];
}

export interface ChipHalf {
  half: 'first' | 'second' | string;
  start_gameweek: number;
  end_gameweek: number;
  remaining_gameweeks: number[];
  expired: boolean;
  plan: ChipWindow[];
  chips: ChipAdvice[];
}

export interface ChipStrategy {
  as_of_gameweek: number;
  notes: string;
  first_half: ChipHalf;
  second_half: ChipHalf;
}

export interface SquadPickIn {
  fpl_element_id?: number | null;
  player_id?: number | null;
  is_captain?: boolean;
  is_vice?: boolean;
  starter?: boolean | null;
}

export interface SquadPlayerRow {
  player_id: number;
  fpl_element_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  team_id?: number | null;
  position: string;
  price: number;
  expected_points: number;
  n_fixtures: number;
  opponents: string;
  opp_fdr: number;
  is_home: boolean;
  form?: number | null;
  last_gw?: number | null;
  is_captain: boolean;
  is_vice: boolean;
  starter: boolean;
  captain_expected_points?: number;
  is_user_pick?: boolean;
  note?: string | null;
}

export interface SquadIssue {
  code: string;
  severity: 'high' | 'medium' | 'low' | string;
  title: string;
  detail: string;
  player_id?: number | null;
}

export interface SquadTransfer {
  out: SquadPlayerRow;
  in: SquadPlayerRow;
  gain: number;
  hit: boolean;
  remaining_bank: number;
  reason: string;
}

export interface SquadAnalysis {
  gameweek: number;
  entry: { id: number; name?: string | null; manager?: string | null; overall_rank?: number | null } | null;
  bank: number;
  free_transfers: number;
  squad_value: number;
  rating: number;
  rating_label: string;
  rating_reason: string;
  xi_xpts: number;
  xi_xpts_with_captain: number;
  template_xi_xpts: number;
  bench_xpts: number;
  formation: string;
  players: SquadPlayerRow[];
  captain: SquadPlayerRow | null;
  vice: SquadPlayerRow | null;
  global_captain: SquadPlayerRow | null;
  issues: SquadIssue[];
  transfers: SquadTransfer[];
}

export interface SquadScreenshotMatch {
  raw_name: string;
  raw_position?: string | null;
  on_bench: boolean;
  is_captain: boolean;
  is_vice: boolean;
  confidence: number;
  player: {
    player_id: number;
    fpl_element_id: number;
    web_name: string;
    full_name: string;
    position: string;
    price: number;
    team_id?: number | null;
  } | null;
}

export interface SquadScreenshotResult {
  vision_notes: string;
  matches: SquadScreenshotMatch[];
  matched: number;
  needed: number;
}

export interface PlayerWatchBrief {
  player_id: number;
  fpl_element_id: number;
  web_name: string;
  full_name: string;
  team: string;
  team_name?: string | null;
  team_code?: number | null;
  position: string;
  price: number;
}

export interface InjuryRow extends PlayerWatchBrief {
  status: string;
  status_label: string;
  news?: string | null;
  return_date?: string | null;
  chance_of_playing?: number | null;
}

export interface BookedRow extends PlayerWatchBrief {
  status: string;
  status_label: string;
  news?: string | null;
  return_date?: string | null;
  yellow_cards: number;
  red_cards: number;
}

export interface CaptainedRow extends PlayerWatchBrief {
  badge: string;
  ownership_pct: number;
}

export interface PriceChangeRow extends PlayerWatchBrief {
  progress_percent: number;
  predicted_percent?: number | null;
  likelihood?: number | null;
  outlook: string;
  direction: string;
  calibrating?: boolean;
}

export interface PlayerWatch {
  source: string;
  gameweek_number?: number | null;
  injured: InjuryRow[];
  booked: BookedRow[];
  most_captained: CaptainedRow[];
  price_rises: PriceChangeRow[];
  price_falls: PriceChangeRow[];
  price_calibrating: boolean;
}
