"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_seasons_code", "seasons", ["code"], unique=True)

    op.create_table(
        "team_name_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fpl_short_name", sa.String(length=8), nullable=False),
        sa.Column("football_data_name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fpl_short_name"),
    )
    op.create_index("ix_team_name_aliases_fpl_short_name", "team_name_aliases", ["fpl_short_name"])

    op.create_table(
        "gameweeks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("deadline_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("is_next", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "number", name="uq_gw_season_number"),
    )
    op.create_index("ix_gameweeks_season_id", "gameweeks", ["season_id"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("fpl_team_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("short_name", sa.String(length=8), nullable=False),
        sa.Column("code", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "fpl_team_id", name="uq_team_season_fpl"),
    )
    op.create_index("ix_teams_season_id", "teams", ["season_id"])

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("fpl_element_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("web_name", sa.String(length=128), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=False),
        sa.Column("now_cost", sa.Integer(), nullable=False),
        sa.Column("selected_by_percent", sa.Float(), nullable=False),
        sa.Column("ep_next", sa.Float(), nullable=True),
        sa.Column("form", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "fpl_element_id", name="uq_player_season_fpl"),
    )
    op.create_index("ix_players_season_id", "players", ["season_id"])
    op.create_index("ix_players_fpl_element_id", "players", ["fpl_element_id"])

    op.create_table(
        "fixtures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("fpl_fixture_id", sa.Integer(), nullable=False),
        sa.Column("gameweek_id", sa.Integer(), nullable=True),
        sa.Column("gameweek_number", sa.Integer(), nullable=True),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("kickoff_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("home_difficulty", sa.Integer(), nullable=True),
        sa.Column("away_difficulty", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["gameweek_id"], ["gameweeks.id"]),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "fpl_fixture_id", name="uq_fixture_season_fpl"),
    )
    op.create_index("ix_fixtures_season_id", "fixtures", ["season_id"])
    op.create_index("ix_fixtures_gameweek_number", "fixtures", ["gameweek_number"])

    op.create_table(
        "player_gameweek_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("fpl_element_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=True),
        sa.Column("gameweek_number", sa.Integer(), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("goals_scored", sa.Integer(), nullable=False),
        sa.Column("assists", sa.Integer(), nullable=False),
        sa.Column("clean_sheets", sa.Integer(), nullable=False),
        sa.Column("goals_conceded", sa.Integer(), nullable=False),
        sa.Column("bonus", sa.Integer(), nullable=False),
        sa.Column("bps", sa.Integer(), nullable=False),
        sa.Column("influence", sa.Float(), nullable=False),
        sa.Column("creativity", sa.Float(), nullable=False),
        sa.Column("threat", sa.Float(), nullable=False),
        sa.Column("ict_index", sa.Float(), nullable=False),
        sa.Column("expected_goals", sa.Float(), nullable=False),
        sa.Column("expected_assists", sa.Float(), nullable=False),
        sa.Column("xP", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "fpl_element_id", "gameweek_number", name="uq_pgs"),
    )
    op.create_index("ix_player_gameweek_stats_season_id", "player_gameweek_stats", ["season_id"])
    op.create_index(
        "ix_player_gameweek_stats_fpl_element_id", "player_gameweek_stats", ["fpl_element_id"]
    )
    op.create_index(
        "ix_player_gameweek_stats_gameweek_number", "player_gameweek_stats", ["gameweek_number"]
    )

    op.create_table(
        "match_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_code", sa.String(length=16), nullable=False),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team_name", sa.String(length=128), nullable=False),
        sa.Column("away_team_name", sa.String(length=128), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("fixture_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_stats_season_code", "match_stats", ["season_code"])
    op.create_index("ix_match_stats_home_team_name", "match_stats", ["home_team_name"])
    op.create_index("ix_match_stats_away_team_name", "match_stats", ["away_team_name"])

    op.create_table(
        "team_ratings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("as_of_gameweek", sa.Integer(), nullable=False),
        sa.Column("attack_home", sa.Float(), nullable=False),
        sa.Column("attack_away", sa.Float(), nullable=False),
        sa.Column("defense_home", sa.Float(), nullable=False),
        sa.Column("defense_away", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "team_id", "as_of_gameweek", name="uq_team_rating_gw"),
    )
    op.create_index("ix_team_ratings_season_id", "team_ratings", ["season_id"])
    op.create_index("ix_team_ratings_team_id", "team_ratings", ["team_id"])

    op.create_table(
        "predictions_team_fixture",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("gameweek_number", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("home_win_prob", sa.Float(), nullable=False),
        sa.Column("draw_prob", sa.Float(), nullable=False),
        sa.Column("away_win_prob", sa.Float(), nullable=False),
        sa.Column("home_clean_sheet_prob", sa.Float(), nullable=False),
        sa.Column("away_clean_sheet_prob", sa.Float(), nullable=False),
        sa.Column("home_score_prob", sa.Float(), nullable=False),
        sa.Column("away_score_prob", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fixture_id", "gameweek_number", "model_version", name="uq_pred_team_fixture"
        ),
    )
    op.create_index(
        "ix_predictions_team_fixture_fixture_id", "predictions_team_fixture", ["fixture_id"]
    )
    op.create_index(
        "ix_predictions_team_fixture_gameweek_number",
        "predictions_team_fixture",
        ["gameweek_number"],
    )

    op.create_table(
        "predictions_player_gw",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("gameweek_number", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("expected_points", sa.Float(), nullable=False),
        sa.Column("baseline_last_gw", sa.Float(), nullable=True),
        sa.Column("baseline_ep_next", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "player_id", "gameweek_number", "model_version", name="uq_pred_player_gw"
        ),
    )
    op.create_index("ix_predictions_player_gw_player_id", "predictions_player_gw", ["player_id"])
    op.create_index(
        "ix_predictions_player_gw_gameweek_number", "predictions_player_gw", ["gameweek_number"]
    )

    op.create_table(
        "etl_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_etl_runs_job_name", "etl_runs", ["job_name"])


def downgrade() -> None:
    for table in [
        "etl_runs",
        "predictions_player_gw",
        "predictions_team_fixture",
        "team_ratings",
        "match_stats",
        "player_gameweek_stats",
        "fixtures",
        "players",
        "teams",
        "gameweeks",
        "team_name_aliases",
        "seasons",
    ]:
        op.drop_table(table)
