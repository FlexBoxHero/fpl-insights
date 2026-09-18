import { DecimalPipe, NgClass } from '@angular/common';
import { Component, computed, DestroyRef, effect, HostListener, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../../core/api.service';
import {
  difficultyClass,
  difficultyLabel,
  FDR_LEGEND,
  OPPORTUNITY_LEGEND,
  opportunityPillClass,
  overallDifficultyClass,
  overallDifficultyLabel,
} from '../../core/difficulty.util';
import { GameweekStore } from '../../core/gameweek.store';
import { FixtureDifficultyCell, FixtureMetricCell, TeamFixtureRun, TeamMetricRun } from '../../core/models';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';

type FdrSort = 'easiest' | 'hardest' | 'name';
type MetricKind = 'cs' | 'goals';

const MIN_FIXTURE_WINDOW = 3;
const MAX_FIXTURE_WINDOW = 8;
const FDR_DESKTOP_DEFAULT = 5;
const FDR_MOBILE_DEFAULT = 3;
const MOBILE_QUERY = '(max-width: 840px)';

function defaultFdrCount(): number {
  return typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches
    ? FDR_MOBILE_DEFAULT
    : FDR_DESKTOP_DEFAULT;
}

@Component({
  selector: 'app-team-predictions',
  standalone: true,
  imports: [
    FormsModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatSliderModule,
    DecimalPipe,
    NgClass,
    ClubMarkComponent,
  ],
  templateUrl: './team-predictions.component.html',
  styleUrl: './team-predictions.component.scss',
})
export class TeamPredictionsComponent {
  private readonly api = inject(ApiService);
  private readonly gwStore = inject(GameweekStore);
  private readonly destroyRef = inject(DestroyRef);
  private fdrCountTouched = false;

  readonly minFixtureWindow = MIN_FIXTURE_WINDOW;
  readonly maxFixtureWindow = MAX_FIXTURE_WINDOW;

  readonly fdrFixtureCount = signal(defaultFdrCount());
  readonly loadingFdr = signal(false);
  readonly loadingCs = signal(false);
  readonly loadingGoals = signal(false);

  readonly fixtureRuns = signal<TeamFixtureRun[]>([]);
  readonly cleanSheets = signal<TeamMetricRun[]>([]);
  readonly goalsOutlook = signal<TeamMetricRun[]>([]);

  readonly outlookGwCount = signal(3);
  readonly fdrSort = signal<FdrSort>('easiest');
  readonly openPill = signal<{ kind: MetricKind; teamId: number; index: number } | null>(null);

  readonly sortedFixtureRuns = computed(() => {
    const rows = this.fixtureRuns().filter((r) => r.fixtures.length > 0);
    const sort = this.fdrSort();
    if (sort === 'name') {
      return rows.sort((a, b) => a.team_name.localeCompare(b.team_name));
    }
    if (sort === 'hardest') {
      return rows.sort((a, b) => b.overall_fdr - a.overall_fdr);
    }
    return rows.sort((a, b) => a.overall_fdr - b.overall_fdr);
  });

  readonly fdrColumns = ['team', 'overall', 'fixtures'];
  readonly metricColumns = ['team', 'overall', 'fixtures'];

  readonly fdrLegend = FDR_LEGEND;
  readonly opportunityLegend = OPPORTUNITY_LEGEND;
  readonly diffClass = difficultyClass;
  readonly diffLabel = difficultyLabel;
  readonly overallDiffClass = overallDifficultyClass;
  readonly overallDiffLabel = overallDifficultyLabel;
  readonly opportunityClass = opportunityPillClass;

  constructor() {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onMq = (e: MediaQueryListEvent) => {
      if (!this.fdrCountTouched) {
        this.fdrFixtureCount.set(e.matches ? FDR_MOBILE_DEFAULT : FDR_DESKTOP_DEFAULT);
      }
    };
    mq.addEventListener('change', onMq);
    this.destroyRef.onDestroy(() => mq.removeEventListener('change', onMq));

    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      const count = this.fdrFixtureCount();
      if (gw) {
        this.loadFdr(gw, count);
      }
    });

    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      const oc = this.outlookGwCount();
      if (gw) {
        this.loadCs(gw, oc);
        this.loadGoals(gw, oc);
      }
    });
  }

  onFdrFixtureCountChange(value: number): void {
    this.fdrCountTouched = true;
    this.fdrFixtureCount.set(value);
  }

  // Kept for when the CS/goals fixture sliders are re-enabled in the template.
  onOutlookCountChange(value: number): void {
    this.outlookGwCount.set(value);
  }

  fixtureChipLabel(fx: FixtureDifficultyCell | FixtureMetricCell): string {
    return `${fx.opponent_short} (${fx.is_home ? 'H' : 'A'})`;
  }

  pct(value: number | undefined): number {
    return (value ?? 0) * 100;
  }

  toggleMetricPill(kind: MetricKind, teamId: number, index: number, event: Event): void {
    event.stopPropagation();
    if (!window.matchMedia('(max-width: 840px)').matches) {
      return;
    }
    const cur = this.openPill();
    if (cur && cur.kind === kind && cur.teamId === teamId && cur.index === index) {
      this.openPill.set(null);
      return;
    }
    this.openPill.set({ kind, teamId, index });
  }

  isPillOpen(kind: MetricKind, teamId: number, index: number): boolean {
    const cur = this.openPill();
    return !!cur && cur.kind === kind && cur.teamId === teamId && cur.index === index;
  }

  openMetricFixture(kind: MetricKind, row: TeamMetricRun): FixtureMetricCell | null {
    const cur = this.openPill();
    if (!cur || cur.kind !== kind || cur.teamId !== row.team_id) {
      return null;
    }
    return row.fixtures[cur.index] ?? null;
  }

  @HostListener('document:click')
  closePills(): void {
    if (this.openPill()) {
      this.openPill.set(null);
    }
  }

  private loadFdr(gw: number, count: number): void {
    this.loadingFdr.set(true);
    this.api.getTeamFixtureRuns(gw, count).subscribe({
      next: (data) => {
        this.fixtureRuns.set(data);
        this.loadingFdr.set(false);
      },
      error: () => {
        this.fixtureRuns.set([]);
        this.loadingFdr.set(false);
      },
    });
  }

  private loadCs(gw: number, count: number): void {
    this.loadingCs.set(true);
    this.api.getTeamCleanSheetOutlook(gw, count).subscribe({
      next: (data) => {
        this.cleanSheets.set(data);
        this.loadingCs.set(false);
      },
      error: () => {
        this.cleanSheets.set([]);
        this.loadingCs.set(false);
      },
    });
  }

  private loadGoals(gw: number, count: number): void {
    this.loadingGoals.set(true);
    this.api.getTeamGoalsOutlook(gw, count).subscribe({
      next: (data) => {
        this.goalsOutlook.set(data);
        this.loadingGoals.set(false);
      },
      error: () => {
        this.goalsOutlook.set([]);
        this.loadingGoals.set(false);
      },
    });
  }
}
