from datetime import datetime

from pydantic import BaseModel


class GameweekOut(BaseModel):
    id: int
    number: int
    name: str
    finished: bool
    is_current: bool
    is_next: bool
    deadline_time: datetime | None = None


class TeamPredictionOut(BaseModel):
    fixture_id: int
    gameweek_number: int
    home_team: str
    away_team: str
    kickoff_time: datetime | None
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    home_clean_sheet_prob: float
    away_clean_sheet_prob: float
    home_score_prob: float
    away_score_prob: float


class PlayerPredictionOut(BaseModel):
    player_id: int
    fpl_element_id: int | None = None
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    price: float
    gameweek_number: int
    expected_points: float
    baseline_last_gw: float | None
    baseline_ep_next: float | None


class FixtureOut(BaseModel):
    id: int
    gameweek_number: int | None
    home_team: str
    away_team: str
    kickoff_time: datetime | None
    finished: bool
    home_score: int | None
    away_score: int | None


class ModelMetaOut(BaseModel):
    model_version: str
    last_etl_at: datetime | None
    last_etl_job: str | None
    last_etl_status: str | None


class FixtureDifficultyCellOut(BaseModel):
    gameweek_number: int | None
    opponent_short: str
    is_home: bool
    fdr: int
    difficulty_level: int
    difficulty_label: str
    difficulty_score: float


class FixtureMetricCellOut(BaseModel):
    gameweek_number: int | None
    opponent_short: str
    is_home: bool
    value: float
    expected_goals: float | None = None


class TeamMetricRunOut(BaseModel):
    team_id: int
    team_name: str
    short_name: str
    team_code: int | None = None
    avg_clean_sheet_prob: float | None = None
    avg_score_prob: float | None = None
    gameweeks_covered: int
    fixtures: list[FixtureMetricCellOut]


class TeamFixtureRunOut(BaseModel):
    team_id: int
    team_name: str
    short_name: str
    team_code: int | None = None
    overall_fdr: float
    overall_difficulty_level: int = 3
    overall_difficulty_label: str = "neutral"
    fixtures: list[FixtureDifficultyCellOut]
    difficulty_model: str = "strength_v2"
    fixture_window: int = 3


class TeamOutlookRowOut(BaseModel):
    team_id: int
    team_name: str
    short_name: str
    avg_clean_sheet_prob: float | None = None
    avg_score_prob: float | None = None
    gameweeks_covered: int


class CaptainPickOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    expected_points: float
    captain_expected_points: float
    ownership_pct: float


class DefensiveContribOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    threshold: int
    likelihood: float
    avg_minutes_last3: float


class BonusOutlookOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    last_gw_bps: int
    last_gw_bonus: int
    bonus_outlook_score: float


class PlayerBriefOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    price: float
    cost_change_event: float
    cost_change_start: float
    transfers_in_event: int
    transfers_out_event: int
    transfers_in: int
    transfers_out: int
    selected_by_percent: float


class TopGwPlayerOut(BaseModel):
    player_id: int
    web_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    gameweek_number: int
    total_points: int
    goals: int
    assists: int
    bonus: int


class HomeDashboardOut(BaseModel):
    last_gameweek: int
    price_risers: list[PlayerBriefOut]
    price_fallers: list[PlayerBriefOut]
    transfers_in: list[PlayerBriefOut]
    transfers_out: list[PlayerBriefOut]
    price_risers_all_time: list[PlayerBriefOut]
    price_fallers_all_time: list[PlayerBriefOut]
    transfers_in_all_time: list[PlayerBriefOut]
    transfers_out_all_time: list[PlayerBriefOut]
    top_last_gameweek: list[TopGwPlayerOut]


class PlayerSeasonStatOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    price: float
    minutes: int
    total_points: int
    goals: int
    assists: int
    bonus: int
    bps: int
    expected_goals: float
    expected_assists: float
    gameweeks_played: int


class DeadlineOut(BaseModel):
    deadline_time: datetime | None
    server_time: datetime


class ChipPlayerOut(BaseModel):
    player_id: int
    web_name: str
    full_name: str
    team: str
    team_name: str | None = None
    team_code: int | None = None
    position: str
    expected_points: float
    triple_expected_points: float
    n_fixtures: int
    opponents: str
    is_home: bool = False
    expected_goals: float = 0.0


class ChipWindowOut(BaseModel):
    chip: str
    chip_label: str
    gameweek: int
    score: float
    confidence: str
    headline: str
    reason: str
    flags: list[str] = []
    player: ChipPlayerOut | None = None


class ChipAdviceOut(BaseModel):
    chip: str
    chip_label: str
    available: bool
    recommended_gameweek: int | None = None
    windows: list[ChipWindowOut]


class ChipHalfOut(BaseModel):
    half: str
    start_gameweek: int
    end_gameweek: int
    remaining_gameweeks: list[int]
    expired: bool
    plan: list[ChipWindowOut]
    chips: list[ChipAdviceOut]


class ChipStrategyOut(BaseModel):
    as_of_gameweek: int
    notes: str
    first_half: ChipHalfOut
    second_half: ChipHalfOut


class SquadPickIn(BaseModel):
    fpl_element_id: int | None = None
    player_id: int | None = None
    is_captain: bool = False
    is_vice: bool = False
    starter: bool | None = None


class SquadAnalysisIn(BaseModel):
    picks: list[SquadPickIn]
    bank: float = 0.0
    free_transfers: int = 1


class SquadScreenshotIn(BaseModel):
    image_base64: str
    media_type: str = "image/png"


class SquadVisionStatusOut(BaseModel):
    enabled: bool
