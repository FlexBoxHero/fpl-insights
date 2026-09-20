import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSortModule, Sort } from '@angular/material/sort';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { GameweekStore } from '../../core/gameweek.store';
import {
  CaptainPick,
  DefensiveContrib,
  HomeDashboard,
  PlayerPrediction,
  PlayerWatch,
  PriceChangeRow,
} from '../../core/models';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';
import { MarketMoversComponent } from '../../shared/market-movers/market-movers.component';
import { SectionCardComponent } from '../../shared/section-card/section-card.component';

const MAX_COMPARE = 3;
const INSIGHTS_ROW_LIMIT = 15;
const SECTION_KEY = 'fpl.playerSections';

type SectionId = 'price' | 'movers' | 'captain' | 'defcon' | 'injured' | 'booked';
type InjuryFilter = 'all' | 'i' | 'd';
type BookedFilter = 'all' | 'suspended' | 'booked';

const SECTION_DEFAULTS: Record<SectionId, boolean> = {
  price: false,
  movers: false,
  captain: false,
  defcon: false,
  injured: false,
  booked: false,
};

@Component({
  selector: 'app-player-predictions',
  standalone: true,
  imports: [
    MatTableModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatTooltipModule,
    MatPaginatorModule,
    MatCheckboxModule,
    MatButtonModule,
    MatSortModule,
    DecimalPipe,
    MarketMoversComponent,
    ClubMarkComponent,
    SectionCardComponent,
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
  readonly positionFilter = signal('');
  readonly teamFilter = signal('');
  readonly minPrice = signal<number | null>(null);
  readonly maxPrice = signal<number | null>(null);
  readonly nameQuery = signal('');
  readonly pointsSort = signal<Sort>({ active: 'xpts', direction: 'desc' });
  readonly priceSort = signal<Sort>({ active: 'progress', direction: 'desc' });
  readonly injuryFilter = signal<InjuryFilter>('all');
  readonly bookedFilter = signal<BookedFilter>('all');
  readonly openSections = signal<Record<SectionId, boolean>>(readSections());

  readonly captains = signal<CaptainPick[]>([]);
  readonly defensive = signal<DefensiveContrib[]>([]);
  readonly dashboard = signal<HomeDashboard | null>(null);
  readonly watch = signal<PlayerWatch | null>(null);

  readonly captainPreview = computed(() => this.captains().slice(0, INSIGHTS_ROW_LIMIT));
  readonly defensivePreview = computed(() => this.defensive().slice(0, INSIGHTS_ROW_LIMIT));

  readonly teamOptions = computed(() => {
    const names = new Set(this.allRows().map((row) => row.team).filter(Boolean));
    return [...names].sort();
  });

  readonly priceOptions = [4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 10, 11, 12, 13, 14, 15];

  readonly filteredRows = computed(() => {
    const team = this.teamFilter();
    const minP = this.minPrice();
    const maxP = this.maxPrice();
    const q = this.nameQuery().trim().toLowerCase();
    let rows = this.allRows().filter((row) => {
      if (team && row.team !== team) {
        return false;
      }
      if (minP != null && row.price < minP) {
        return false;
      }
      if (maxP != null && row.price > maxP) {
        return false;
      }
      if (
        q &&
        !row.web_name.toLowerCase().includes(q) &&
        !row.full_name.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
    const sort = this.pointsSort();
    if (sort.active && sort.direction) {
      const dir = sort.direction === 'asc' ? 1 : -1;
      rows = [...rows].sort((a, b) => dir * comparePoints(a, b, sort.active, this.delta.bind(this)));
    }
    return rows;
  });

  readonly pagedRows = computed(() => {
    const start = this.pageIndex() * this.pageSize();
    return this.filteredRows().slice(start, start + this.pageSize());
  });

  readonly totalPlayers = computed(() => this.filteredRows().length);

  readonly comparedPlayers = computed(() => {
    const ids = new Set(this.compareIds());
    return this.allRows().filter((p) => ids.has(p.player_id));
  });

  readonly filteredInjured = computed(() => {
    const rows = this.watch()?.injured ?? [];
    const filter = this.injuryFilter();
    return filter === 'all' ? rows : rows.filter((row) => row.status === filter);
  });

  readonly filteredBooked = computed(() => {
    const rows = this.watch()?.booked ?? [];
    const filter = this.bookedFilter();
    if (filter === 'suspended') {
      return rows.filter((row) => row.status === 's' || row.red_cards > 0);
    }
    if (filter === 'booked') {
      return rows.filter((row) => row.status_label === 'Booked');
    }
    return rows;
  });

  readonly sortedRises = computed(() => sortPrice(this.watch()?.price_rises ?? [], this.priceSort(), 1));
  readonly sortedFalls = computed(() => sortPrice(this.watch()?.price_falls ?? [], this.priceSort(), -1));

  readonly pageSizeOptions = [15, 25, 50, 100];

  readonly displayedColumns = [
    'compare',
    'player',
    'team',
    'pos',
    'opp',
    'price',
    'xpts',
    'lastGw',
    'epNext',
    'delta',
  ];

  readonly captainColumns = ['rank', 'player', 'captainXp'];
  readonly defColumns = ['player', 'likelihood', 'defcons'];
  readonly injuryColumns = ['player', 'status', 'return'];
  readonly bookedColumns = ['player', 'status', 'yellows', 'reds', 'return'];
  readonly priceColumns = ['player', 'progress', 'predicted', 'outlook'];

  readonly tooltips = {
    compare: 'Select up to 3 players to compare side by side.',
    xpts: 'Model expected FPL points for the selected gameweek.',
    lastGw: 'Actual points scored in the player’s most recent completed gameweek.',
    epNext: 'Official FPL “ep_next” from the game (their published expected points).',
    delta: 'Model xPts minus FPL ep_next — positive means our model is more optimistic.',
    opp: 'Opponent(s) this gameweek. H = home, A = away. Blank weeks show Blank.',
    captain: 'Top captain options ranked by 2× model expected points.',
    defensive:
      'Chance of hitting the DefCon bar this match (DEF 10+ CBI+tackles, MID/FWD 12+ CBI+tackles+recoveries). DefCons is the predicted action count toward that bar.',
    injured: 'Official FPL injury and doubt flags, including a return date when FPL publishes one.',
    booked: 'Suspended players, plus anyone on 2+ yellows this season.',
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

  isOpen(id: SectionId): boolean {
    return this.openSections()[id];
  }

  setOpen(id: SectionId, open: boolean): void {
    const next: Record<SectionId, boolean> = { ...SECTION_DEFAULTS };
    if (open) {
      next[id] = true;
    }
    this.openSections.set(next);
    persistSections(next);
  }

  priceSummary(): string {
    const watch = this.watch();
    if (!watch) {
      return 'Price rises and drops';
    }
    return `${watch.price_rises.length} rise · ${watch.price_falls.length} drop`;
  }

  captainSummary(): string {
    const top = this.captainPreview()[0];
    return top ? `${top.web_name} · ${top.captain_expected_points.toFixed(1)} Cap xP` : 'Captain tracker';
  }

  defSummary(): string {
    const top = this.defensivePreview()[0];
    return top ? `${top.web_name} · ${(top.likelihood * 100).toFixed(0)}%` : 'Defensive contributions';
  }

  injuredSummary(): string {
    const rows = this.watch()?.injured ?? [];
    const injured = rows.filter((row) => row.status === 'i').length;
    const doubtful = rows.filter((row) => row.status === 'd').length;
    return `${injured} injured · ${doubtful} doubtful`;
  }

  bookedSummary(): string {
    const rows = this.watch()?.booked ?? [];
    const suspended = rows.filter((row) => row.status === 's' || row.red_cards > 0).length;
    return `${suspended} suspended · ${rows.length} listed`;
  }

  onPositionChange(value: string): void {
    this.positionFilter.set(value);
  }

  onTeamChange(value: string): void {
    this.teamFilter.set(value);
    this.pageIndex.set(0);
  }

  onMinPrice(value: number | null): void {
    this.minPrice.set(value);
    this.pageIndex.set(0);
  }

  onMaxPrice(value: number | null): void {
    this.maxPrice.set(value);
    this.pageIndex.set(0);
  }

  onNameQuery(value: string): void {
    this.nameQuery.set(value);
    this.pageIndex.set(0);
  }

  onPointsSort(sort: Sort): void {
    this.pointsSort.set(sort);
    this.pageIndex.set(0);
  }

  onPriceSort(sort: Sort): void {
    this.priceSort.set(sort);
  }

  onInjuryFilter(value: InjuryFilter): void {
    this.injuryFilter.set(value);
  }

  onBookedFilter(value: BookedFilter): void {
    this.bookedFilter.set(value);
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

function readSections(): Record<SectionId, boolean> {
  try {
    const raw = sessionStorage.getItem(SECTION_KEY);
    if (!raw) {
      return { ...SECTION_DEFAULTS };
    }
    const merged = { ...SECTION_DEFAULTS, ...JSON.parse(raw) };
    const openIds = (Object.keys(merged) as SectionId[]).filter((id) => merged[id]);
    if (openIds.length <= 1) {
      return merged;
    }
    return { ...SECTION_DEFAULTS, [openIds[0]]: true };
  } catch {
    return { ...SECTION_DEFAULTS };
  }
}

function persistSections(value: Record<SectionId, boolean>): void {
  try {
    sessionStorage.setItem(SECTION_KEY, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

function comparePoints(
  a: PlayerPrediction,
  b: PlayerPrediction,
  column: string,
  deltaFn: (row: PlayerPrediction) => number | null,
): number {
  if (column === 'player') {
    return a.web_name.localeCompare(b.web_name);
  }
  if (column === 'team') {
    return a.team.localeCompare(b.team);
  }
  if (column === 'pos') {
    return a.position.localeCompare(b.position);
  }
  if (column === 'opp') {
    return (a.opponents || '').localeCompare(b.opponents || '');
  }
  if (column === 'price') {
    return a.price - b.price;
  }
  if (column === 'xpts') {
    return a.expected_points - b.expected_points;
  }
  if (column === 'lastGw') {
    return (a.baseline_last_gw ?? -Infinity) - (b.baseline_last_gw ?? -Infinity);
  }
  if (column === 'epNext') {
    return (a.baseline_ep_next ?? -Infinity) - (b.baseline_ep_next ?? -Infinity);
  }
  if (column === 'delta') {
    return (deltaFn(a) ?? -Infinity) - (deltaFn(b) ?? -Infinity);
  }
  return 0;
}

function sortPrice(rows: PriceChangeRow[], sort: Sort, defaultDir: number): PriceChangeRow[] {
  if (!sort.active || !sort.direction) {
    return rows;
  }
  const dir = sort.direction === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort.active === 'player') {
      return dir * a.web_name.localeCompare(b.web_name);
    }
    if (sort.active === 'predicted') {
      return dir * ((a.predicted_percent ?? 0) - (b.predicted_percent ?? 0));
    }
    if (sort.active === 'outlook') {
      return dir * a.outlook.localeCompare(b.outlook);
    }
    return dir * (a.progress_percent - b.progress_percent);
  });
}
