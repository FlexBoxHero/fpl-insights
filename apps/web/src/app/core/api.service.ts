import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  CaptainPick,
  ChipStrategy,
  DeadlineMeta,
  DefensiveContrib,
  Gameweek,
  HomeDashboard,
  ModelMeta,
  PlayerPrediction,
  PlayerSeasonStat,
  SquadAnalysis,
  SquadPickIn,
  SquadScreenshotResult,
  TeamFixtureRun,
  TeamMetricRun,
  TeamPrediction,
  PlayerWatch,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  getGameweeks(): Observable<Gameweek[]> {
    return this.http.get<Gameweek[]>(`${this.base}/v1/gameweeks`);
  }

  getTeamPredictions(gameweek: number): Observable<TeamPrediction[]> {
    const params = new HttpParams().set('gameweek', gameweek);
    return this.http.get<TeamPrediction[]>(`${this.base}/v1/predictions/teams`, { params });
  }

  getPlayerPredictions(
    gameweek: number,
    position?: string,
    teamId?: number,
  ): Observable<PlayerPrediction[]> {
    let params = new HttpParams().set('gameweek', gameweek);
    if (position) {
      params = params.set('position', position);
    }
    if (teamId) {
      params = params.set('team_id', teamId);
    }
    return this.http.get<PlayerPrediction[]>(`${this.base}/v1/predictions/players`, { params });
  }

  getTeamFixtureRuns(startGameweek: number, fixtureCount: number): Observable<TeamFixtureRun[]> {
    const params = new HttpParams()
      .set('start_gameweek', startGameweek)
      .set('fixture_count', fixtureCount);
    return this.http.get<TeamFixtureRun[]>(`${this.base}/v1/insights/team-fixture-runs`, { params });
  }

  getTeamCleanSheetOutlook(
    startGameweek: number,
    gameweekCount: number,
  ): Observable<TeamMetricRun[]> {
    const params = new HttpParams()
      .set('start_gameweek', startGameweek)
      .set('gameweek_count', gameweekCount);
    return this.http.get<TeamMetricRun[]>(`${this.base}/v1/insights/team-clean-sheets`, { params });
  }

  getTeamGoalsOutlook(startGameweek: number, gameweekCount: number): Observable<TeamMetricRun[]> {
    const params = new HttpParams()
      .set('start_gameweek', startGameweek)
      .set('gameweek_count', gameweekCount);
    return this.http.get<TeamMetricRun[]>(`${this.base}/v1/insights/team-goals`, { params });
  }

  getCaptainPicks(gameweek: number): Observable<CaptainPick[]> {
    const params = new HttpParams().set('gameweek', gameweek);
    return this.http.get<CaptainPick[]>(`${this.base}/v1/insights/captain`, { params });
  }

  getDefensiveContributions(gameweek: number): Observable<DefensiveContrib[]> {
    const params = new HttpParams().set('gameweek', gameweek);
    return this.http.get<DefensiveContrib[]>(`${this.base}/v1/insights/defensive-contributions`, {
      params,
    });
  }

  getHomeDashboard(gameweek?: number): Observable<HomeDashboard> {
    let params = new HttpParams();
    if (gameweek != null) {
      params = params.set('gameweek', gameweek);
    }
    return this.http.get<HomeDashboard>(`${this.base}/v1/dashboard/home`, { params });
  }

  getPlayerSeasonStats(
    gameweek?: number,
    position?: string,
    minMinutes = 0,
    limit = 50,
  ): Observable<PlayerSeasonStat[]> {
    let params = new HttpParams().set('min_minutes', minMinutes).set('limit', limit);
    if (gameweek != null) {
      params = params.set('gameweek', gameweek);
    }
    if (position) {
      params = params.set('position', position);
    }
    return this.http.get<PlayerSeasonStat[]>(`${this.base}/v1/players/season-stats`, { params });
  }

  getDeadline(): Observable<DeadlineMeta> {
    return this.http.get<DeadlineMeta>(`${this.base}/v1/meta/deadline`);
  }

  getModelMeta(): Observable<ModelMeta> {
    return this.http.get<ModelMeta>(`${this.base}/v1/meta/model-version`);
  }

  getChipStrategy(firstChips: string[], secondChips: string[]): Observable<ChipStrategy> {
    const params = new HttpParams()
      .set('first_chips', firstChips.join(','))
      .set('second_chips', secondChips.join(','));
    return this.http.get<ChipStrategy>(`${this.base}/v1/insights/chip-strategy`, { params });
  }

  analyzeSquad(picks: SquadPickIn[], bank = 0, freeTransfers = 1): Observable<SquadAnalysis> {
    return this.http.post<SquadAnalysis>(`${this.base}/v1/insights/squad-analysis`, {
      picks,
      bank,
      free_transfers: freeTransfers,
    });
  }

  analyzeSquadFromEntry(entryId: number): Observable<SquadAnalysis> {
    const params = new HttpParams().set('entry_id', entryId);
    return this.http.get<SquadAnalysis>(`${this.base}/v1/insights/squad-analysis/from-entry`, {
      params,
    });
  }

  getSquadVisionStatus(): Observable<{ enabled: boolean }> {
    return this.http.get<{ enabled: boolean }>(`${this.base}/v1/insights/squad-vision-status`);
  }

  parseSquadScreenshot(imageBase64: string, mediaType = 'image/png'): Observable<SquadScreenshotResult> {
    return this.http.post<SquadScreenshotResult>(`${this.base}/v1/insights/squad-from-screenshot`, {
      image_base64: imageBase64,
      media_type: mediaType,
    });
  }

  getPlayerWatch(): Observable<PlayerWatch> {
    return this.http.get<PlayerWatch>(`${this.base}/v1/insights/player-watch`);
  }
}
