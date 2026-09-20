import { DecimalPipe } from '@angular/common';
import { Component, ElementRef, ViewChild, computed, effect, inject, signal } from '@angular/core';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSortModule, Sort } from '@angular/material/sort';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { clubShirtUrl } from '../../core/club-badges';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';
import { ApiService } from '../../core/api.service';
import { GameweekStore } from '../../core/gameweek.store';
import {
  DreamXi,
  DreamXiPlayer,
  HomeDashboard,
  PlayerOfTheWeek,
  PlayerSeasonStat,
  PlayerWatch,
} from '../../core/models';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    MatTableModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatSortModule,
    MatPaginatorModule,
    MatTooltipModule,
    DecimalPipe,
    ClubMarkComponent,
  ],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  private readonly api = inject(ApiService);
  private readonly gwStore = inject(GameweekStore);

  readonly loadingDash = signal(false);
  readonly loadingStats = signal(false);
  readonly loadingWatch = signal(false);
  readonly dashboard = signal<HomeDashboard | null>(null);
  readonly seasonStats = signal<PlayerSeasonStat[]>([]);
  readonly watch = signal<PlayerWatch | null>(null);

  @ViewChild('potwStrip') private potwStrip?: ElementRef<HTMLElement>;

  readonly statsPosition = signal('');
  readonly minMinutes = signal(90);
  readonly statsTeam = signal('');
  readonly statsQuery = signal('');
  readonly minPrice = signal<number | null>(null);
  readonly maxPrice = signal<number | null>(null);
  readonly statsSort = signal<Sort>({ active: 'pts', direction: 'desc' });
  readonly statsPageIndex = signal(0);
  readonly statsPageSize = signal(15);
  readonly priceOptions = [4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 10, 11, 12, 13, 14, 15];
  readonly pageSizeOptions = [15, 25, 50];

  readonly selectedColumns = ['rank', 'player', 'owned'];
  readonly captainedColumns = ['rank', 'player', 'cap'];
  readonly statsColumns = [
    'player',
    'team',
    'pos',
    'price',
    'pts',
    'starts',
    'subbed',
    'cs',
    'gc',
    'cbitr',
    'defcon',
    'form',
    'selected',
    'goals',
    'assists',
    'mins',
    'xg',
    'xa',
    'xgc',
    'ict',
    'net',
  ];

  readonly mostCaptained = computed(() => this.watch()?.most_captained ?? []);
  readonly mostSelected = computed(() => this.watch()?.most_selected ?? []);
  readonly totw = computed(() => this.dashboard()?.team_of_the_week ?? null);
  readonly tots = computed(() => this.dashboard()?.team_of_the_season ?? null);
  readonly playersOfTheWeek = computed(() => this.dashboard()?.players_of_the_week ?? []);
  readonly seasonLabel = computed(() => this.dashboard()?.season_label || 'Season');

  readonly statsTeams = computed(() => {
    const names = new Set(this.seasonStats().map((row) => row.team).filter(Boolean));
    return [...names].sort();
  });

  readonly filteredStats = computed(() => {
    const q = this.statsQuery().trim().toLowerCase();
    const team = this.statsTeam();
    const minP = this.minPrice();
    const maxP = this.maxPrice();
    let rows = this.seasonStats().filter((row) => {
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
    const sort = this.statsSort();
    if (sort.active && sort.direction) {
      const dir = sort.direction === 'asc' ? 1 : -1;
      rows = [...rows].sort((a, b) => dir * compareSeason(a, b, sort.active));
    }
    return rows;
  });

  readonly displayedStats = computed(() => {
    const start = this.statsPageIndex() * this.statsPageSize();
    return this.filteredStats().slice(start, start + this.statsPageSize());
  });

  readonly statsTotal = computed(() => this.filteredStats().length);

  constructor() {
    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      const pos = this.statsPosition();
      const min = this.minMinutes();
      if (gw) {
        this.loadDashboard();
        this.loadWatch();
        this.loadStats(gw, pos, min);
      }
    });
  }

  onStatsPosition(value: string): void {
    this.statsPosition.set(value);
    this.statsPageIndex.set(0);
  }

  onMinMinutes(value: number): void {
    this.minMinutes.set(value);
    this.statsPageIndex.set(0);
  }

  onStatsTeam(value: string): void {
    this.statsTeam.set(value);
    this.statsPageIndex.set(0);
  }

  onStatsQuery(value: string): void {
    this.statsQuery.set(value);
    this.statsPageIndex.set(0);
  }

  onMinPrice(value: number | null): void {
    this.minPrice.set(value);
    this.statsPageIndex.set(0);
  }

  onMaxPrice(value: number | null): void {
    this.maxPrice.set(value);
    this.statsPageIndex.set(0);
  }

  onStatsSort(sort: Sort): void {
    this.statsSort.set(sort);
    this.statsPageIndex.set(0);
  }

  onStatsPage(event: PageEvent): void {
    this.statsPageIndex.set(event.pageIndex);
    this.statsPageSize.set(event.pageSize);
  }

  shirtUrl(row: PlayerOfTheWeek): string | null {
    return clubShirtUrl(row.team_code, row.team, row.position === 'GK');
  }

  scrollPotw(direction: number): void {
    this.potwStrip?.nativeElement.scrollBy({ left: direction * 176, behavior: 'smooth' });
  }

  onShirtError(event: Event): void {
    const img = event.target as HTMLImageElement | null;
    if (img) {
      img.style.display = 'none';
    }
  }

  xiRows(xi: DreamXi | null): DreamXiPlayer[][] {
    if (!xi) {
      return [];
    }
    return (['GK', 'DEF', 'MID', 'FWD'] as const)
      .map((pos) => xi.players.filter((player) => player.position === pos))
      .filter((row) => row.length > 0);
  }

  private loadDashboard(): void {
    this.loadingDash.set(true);
    this.api.getHomeDashboard().subscribe({
      next: (data) => {
        this.dashboard.set(data);
        this.loadingDash.set(false);
      },
      error: () => {
        this.dashboard.set(null);
        this.loadingDash.set(false);
      },
    });
  }

  private loadWatch(): void {
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

  private loadStats(gw: number, position: string, minMinutes: number): void {
    this.loadingStats.set(true);
    this.api.getPlayerSeasonStats(gw, position || undefined, minMinutes, 200).subscribe({
      next: (data) => {
        this.seasonStats.set(data);
        this.loadingStats.set(false);
      },
      error: () => {
        this.seasonStats.set([]);
        this.loadingStats.set(false);
      },
    });
  }
}

function compareSeason(a: PlayerSeasonStat, b: PlayerSeasonStat, column: string): number {
  const num = (row: PlayerSeasonStat, key: string): number => {
    switch (key) {
      case 'pts':
        return row.total_points;
      case 'starts':
        return row.starts ?? 0;
      case 'subbed':
        return row.subbed_in ?? 0;
      case 'cs':
        return row.clean_sheets ?? 0;
      case 'gc':
        return row.goals_conceded ?? 0;
      case 'defcon':
        return row.defensive_contribution ?? 0;
      case 'form':
        return row.form ?? 0;
      case 'selected':
        return row.selected_by_percent ?? 0;
      case 'goals':
        return row.goals;
      case 'assists':
        return row.assists;
      case 'mins':
        return row.minutes;
      case 'price':
        return row.price;
      case 'xg':
        return row.expected_goals;
      case 'xa':
        return row.expected_assists;
      case 'xgc':
        return row.expected_goals_conceded ?? 0;
      case 'ict':
        return row.ict_index ?? 0;
      case 'net':
        return row.net_transfers ?? 0;
      case 'cbitr':
        return (row.clearances_blocks_interceptions ?? 0)
          + (row.tackles ?? 0)
          + (row.recoveries ?? 0);
      default:
        return 0;
    }
  };
  if (column === 'player') {
    return a.web_name.localeCompare(b.web_name);
  }
  if (column === 'team') {
    return a.team.localeCompare(b.team);
  }
  if (column === 'pos') {
    return a.position.localeCompare(b.position);
  }
  return num(a, column) - num(b, column);
}
