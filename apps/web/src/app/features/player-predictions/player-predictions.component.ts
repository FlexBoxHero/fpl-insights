import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { GameweekStore } from '../../core/gameweek.store';
import { CaptainPick, DefensiveContrib, HomeDashboard, PlayerPrediction, PlayerWatch } from '../../core/models';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';
import { MarketMoversComponent } from '../../shared/market-movers/market-movers.component';

const MAX_COMPARE = 3;
const INSIGHTS_ROW_LIMIT = 15;

@Component({
  selector: 'app-player-predictions',
  standalone: true,
  imports: [
    MatTableModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTooltipModule,
    MatPaginatorModule,
    MatCheckboxModule,
    MatButtonModule,
    DecimalPipe,
    MarketMoversComponent,
    ClubMarkComponent,
  ],
  templateUrl: './player-predictions.component.html',
  styleUrl: './player-predictions.component.scss',
})
export class PlayerPredictionsComponent {
  private readonly api = inject(ApiService);
  private readonly gwStore = inject(GameweekStore);

  readonly loading = signal(false);
  readonly loadingCaptain = signal(false);
  readonly loadingDef = signal(false);
  readonly loadingMovers = signal(false);
  readonly loadingWatch = signal(false);

  readonly allRows = signal<PlayerPrediction[]>([]);
  readonly compareIds = signal<number[]>([]);

  readonly pageIndex = signal(0);
  readonly pageSize = signal(15);

  readonly pagedRows = computed(() => {
    const start = this.pageIndex() * this.pageSize();
    return this.allRows().slice(start, start + this.pageSize());
  });

  readonly totalPlayers = computed(() => this.allRows().length);

  readonly comparedPlayers = computed(() => {
    const ids = new Set(this.compareIds());
    return this.allRows().filter((p) => ids.has(p.player_id));
  });

  readonly captains = signal<CaptainPick[]>([]);
  readonly defensive = signal<DefensiveContrib[]>([]);
  readonly dashboard = signal<HomeDashboard | null>(null);
  readonly watch = signal<PlayerWatch | null>(null);

  readonly captainPreview = computed(() => this.captains().slice(0, INSIGHTS_ROW_LIMIT));
  readonly defensivePreview = computed(() => this.defensive().slice(0, INSIGHTS_ROW_LIMIT));

  readonly positionFilter = signal('');

  readonly pageSizeOptions = [15, 25, 50, 100];

  readonly displayedColumns = [
    'compare',
    'player',
    'team',
    'pos',
    'price',
    'xpts',
    'lastGw',
    'epNext',
    'delta',
  ];

  readonly captainColumns = ['rank', 'player', 'captainXp'];
  readonly defColumns = ['player', 'likelihood'];
  readonly injuryColumns = ['player', 'status', 'return'];
  readonly bookedColumns = ['player', 'status', 'yellows', 'reds', 'return'];
  readonly captainedColumns = ['rank', 'player', 'badge', 'owned'];
  readonly priceColumns = ['player', 'progress', 'predicted', 'outlook'];

  readonly tooltips = {
    compare: 'Select up to 3 players to compare side by side.',
    xpts: 'Model expected FPL points for the selected gameweek.',
    lastGw: 'Actual points scored in the player’s most recent completed gameweek.',
    epNext: 'Official FPL “ep_next” from the game (their published expected points).',
    delta: 'Model xPts minus FPL ep_next — positive means our model is more optimistic.',
    captain: 'Top captain options ranked by 2× model expected points.',
    defensive:
      'Estimated chance of hitting defensive contribution thresholds (DEF 10+, MID 12+). Based on minutes and form; not official CBIT data.',
    injured: 'Official FPL injury and doubt flags, including a return date when FPL publishes one.',
    booked: 'Suspended players, plus anyone on 2+ yellows this season.',
    captained:
      'Official most captained and most vice-captained this gameweek. Remaining spots are the next most-owned players — FPL only names one captain leader.',
    price:
      'Official FPL Price Change Predictor. Progress is toward a rise (positive) or drop (negative) at 00:00 UK. Over 100% means a change is expected unless transfers swing the other way.',
  };

  constructor() {
    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      const pos = this.positionFilter();
      if (gw) {
        this.compareIds.set([]);
        this.pageIndex.set(0);
        this.fetchPoints(gw, pos || undefined);
        this.fetchCaptain(gw);
        this.fetchDefensive(gw);
        this.fetchMovers();
        this.fetchWatch();
      }
    });
  }

  onPositionChange(value: string): void {
    this.positionFilter.set(value);
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
  }

  isCompared(row: PlayerPrediction): boolean {
    return this.compareIds().includes(row.player_id);
  }

  canAddCompare(): boolean {
    return this.compareIds().length < MAX_COMPARE;
  }

  toggleCompare(row: PlayerPrediction, checked: boolean): void {
    const ids = [...this.compareIds()];
    if (checked) {
      if (ids.length >= MAX_COMPARE || ids.includes(row.player_id)) {
        return;
      }
      ids.push(row.player_id);
    } else {
      const idx = ids.indexOf(row.player_id);
      if (idx >= 0) {
        ids.splice(idx, 1);
      }
    }
    this.compareIds.set(ids);
  }

  clearCompare(): void {
    this.compareIds.set([]);
  }

  compareBest(
    players: PlayerPrediction[],
    field: keyof PlayerPrediction,
    higherIsBetter = true,
  ): number | null {
    if (players.length < 2) {
      return null;
    }
    const values = players
      .map((p) => p[field])
      .filter((v): v is number => typeof v === 'number');
    if (!values.length) {
      return null;
    }
    const target = higherIsBetter ? Math.max(...values) : Math.min(...values);
    const winner = players.find((p) => p[field] === target);
    return winner?.player_id ?? null;
  }

  delta(row: PlayerPrediction): number | null {
    if (row.baseline_ep_next == null) {
      return null;
    }
    return row.expected_points - row.baseline_ep_next;
  }

  deltaBest(players: PlayerPrediction[]): number | null {
    if (players.length < 2) {
      return null;
    }
    let bestId: number | null = null;
    let bestDelta = -Infinity;
    for (const p of players) {
      const d = this.delta(p);
      if (d != null && d > bestDelta) {
        bestDelta = d;
        bestId = p.player_id;
      }
    }
    return bestId;
  }

  pct(value: number): number {
    return value * 100;
  }

  newsTip(row: { full_name: string; news?: string | null }): string {
    return row.news ? `${row.full_name} — ${row.news}` : row.full_name;
  }

  progressWidth(percent: number): number {
    return (Math.min(Math.abs(percent), 150) / 150) * 100;
  }

  signedPercent(value: number | null | undefined): string {
    if (value == null) {
      return '—';
    }
    const rounded = value.toFixed(1);
    return value > 0 ? `+${rounded}%` : `${rounded}%`;
  }

  outlookShort(label: string): string {
    return label
      .replace(' to rise', '')
      .replace(' to drop', '')
      .replace(' to change', '');
  }

  private fetchPoints(gw: number, position?: string): void {
    this.loading.set(true);
    this.api.getPlayerPredictions(gw, position).subscribe({
      next: (data) => {
        this.allRows.set(data);
        this.loading.set(false);
      },
      error: () => {
        this.allRows.set([]);
        this.loading.set(false);
      },
    });
  }

  private fetchCaptain(gw: number): void {
    this.loadingCaptain.set(true);
    this.api.getCaptainPicks(gw).subscribe({
      next: (data) => {
        this.captains.set(data);
        this.loadingCaptain.set(false);
      },
      error: () => {
        this.captains.set([]);
        this.loadingCaptain.set(false);
      },
    });
  }

  private fetchDefensive(gw: number): void {
    this.loadingDef.set(true);
    this.api.getDefensiveContributions(gw).subscribe({
      next: (data) => {
        this.defensive.set(data);
        this.loadingDef.set(false);
      },
      error: () => {
        this.defensive.set([]);
        this.loadingDef.set(false);
      },
    });
  }

  private fetchMovers(): void {
    this.loadingMovers.set(true);
    this.api.getHomeDashboard().subscribe({
      next: (data) => {
        this.dashboard.set(data);
        this.loadingMovers.set(false);
      },
      error: () => {
        this.dashboard.set(null);
        this.loadingMovers.set(false);
      },
    });
  }

  private fetchWatch(): void {
    this.loadingWatch.set(true);
    this.api.getPlayerWatch().subscribe({
      next: (data) => {
        this.watch.set(data);
        this.loadingWatch.set(false);
      },
      error: () => {
        this.watch.set(null);
        this.loadingWatch.set(false);
      },
    });
  }
}
