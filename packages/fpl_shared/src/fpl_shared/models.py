from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fpl_shared.db import Base


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class Gameweek(Base):
    __tablename__ = "gameweeks"
    __table_args__ = (UniqueConstraint("season_id", "number", name="uq_gw_season_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    deadline_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_next: Mapped[bool] = mapped_column(Boolean, default=False)

    season: Mapped["Season"] = relationship(back_populates="gameweeks")


Season.gameweeks = relationship("Gameweek", back_populates="season")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("season_id", "fpl_team_id", name="uq_team_season_fpl"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    fpl_team_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    short_name: Mapped[str] = mapped_column(String(8))
    code: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TeamNameAlias(Base):
    __tablename__ = "team_name_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fpl_short_name: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    football_data_name: Mapped[str] = mapped_column(String(128))


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("season_id", "fpl_element_id", name="uq_player_season_fpl"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    fpl_element_id: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    web_name: Mapped[str] = mapped_column(String(128))
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    second_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str] = mapped_column(String(8))
    now_cost: Mapped[int] = mapped_column(Integer, default=0)
    selected_by_percent: Mapped[float] = mapped_column(Float, default=0.0)
    ep_next: Mapped[float | None] = mapped_column(Float, nullable=True)
    form: Mapped[float | None] = mapped_column(Float, nullable=True)
    transfers_in_event: Mapped[int] = mapped_column(Integer, default=0)
    transfers_out_event: Mapped[int] = mapped_column(Integer, default=0)
    transfers_in: Mapped[int] = mapped_column(Integer, default=0)
    transfers_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_change_event: Mapped[int] = mapped_column(Integer, default=0)
    cost_change_start: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), default="a")
    news: Mapped[str | None] = mapped_column(Text, nullable=True)
    news_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chance_of_playing_this_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chance_of_playing_next_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    price_change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_change_projected_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_change_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_change_calibrating: Mapped[bool] = mapped_column(Boolean, default=False)


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (UniqueConstraint("season_id", "fpl_fixture_id", name="uq_fixture_season_fpl"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    fpl_fixture_id: Mapped[int] = mapped_column(Integer)
    gameweek_id: Mapped[int | None] = mapped_column(ForeignKey("gameweeks.id"), nullable=True)
    gameweek_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PlayerGameweekStat(Base):
    __tablename__ = "player_gameweek_stats"
    __table_args__ = (
        UniqueConstraint("season_id", "fpl_element_id", "gameweek_number", name="uq_pgs"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    fpl_element_id: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    gameweek_number: Mapped[int] = mapped_column(Integer, index=True)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    goals_scored: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, default=0)
    goals_conceded: Mapped[int] = mapped_column(Integer, default=0)
    bonus: Mapped[int] = mapped_column(Integer, default=0)
    bps: Mapped[int] = mapped_column(Integer, default=0)
    influence: Mapped[float] = mapped_column(Float, default=0.0)
    creativity: Mapped[float] = mapped_column(Float, default=0.0)
    threat: Mapped[float] = mapped_column(Float, default=0.0)
    ict_index: Mapped[float] = mapped_column(Float, default=0.0)
    expected_goals: Mapped[float] = mapped_column(Float, default=0.0)
    expected_assists: Mapped[float] = mapped_column(Float, default=0.0)
    xP: Mapped[float | None] = mapped_column(Float, nullable=True)


class MatchStat(Base):
    __tablename__ = "match_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_code: Mapped[str] = mapped_column(String(16), index=True)
    match_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team_name: Mapped[str] = mapped_column(String(128), index=True)
    away_team_name: Mapped[str] = mapped_column(String(128), index=True)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)


class TeamRating(Base):
    __tablename__ = "team_ratings"
    __table_args__ = (
        UniqueConstraint("season_id", "team_id", "as_of_gameweek", name="uq_team_rating_gw"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    as_of_gameweek: Mapped[int] = mapped_column(Integer)
    attack_home: Mapped[float] = mapped_column(Float)
    attack_away: Mapped[float] = mapped_column(Float)
    defense_home: Mapped[float] = mapped_column(Float)
    defense_away: Mapped[float] = mapped_column(Float)


class PredictionTeamFixture(Base):
    __tablename__ = "predictions_team_fixture"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id", "gameweek_number", "model_version", name="uq_pred_team_fixture"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    gameweek_number: Mapped[int] = mapped_column(Integer, index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    home_win_prob: Mapped[float] = mapped_column(Float)
    draw_prob: Mapped[float] = mapped_column(Float)
    away_win_prob: Mapped[float] = mapped_column(Float)
    home_clean_sheet_prob: Mapped[float] = mapped_column(Float)
    away_clean_sheet_prob: Mapped[float] = mapped_column(Float)
    home_score_prob: Mapped[float] = mapped_column(Float)
    away_score_prob: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PredictionPlayerGameweek(Base):
    __tablename__ = "predictions_player_gw"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "gameweek_number",
            "model_version",
            name="uq_pred_player_gw",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_number: Mapped[int] = mapped_column(Integer, index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    expected_points: Mapped[float] = mapped_column(Float)
    baseline_last_gw: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_ep_next: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DifficultyScale(Base):
    """Frozen FDR colour cuts for a season gameweek (set at weekly inference)."""

    __tablename__ = "difficulty_scales"
    __table_args__ = (
        UniqueConstraint("season_id", "as_of_gameweek", name="uq_diff_scale_gw"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    as_of_gameweek: Mapped[int] = mapped_column(Integer)
    break_p20: Mapped[float] = mapped_column(Float)
    break_p40: Mapped[float] = mapped_column(Float)
    break_p60: Mapped[float] = mapped_column(Float)
    break_p80: Mapped[float] = mapped_column(Float)
    score_min: Mapped[float] = mapped_column(Float)
    score_max: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
