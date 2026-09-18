import { DecimalPipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';
import { ApiService } from '../../core/api.service';
import { GameweekStore } from '../../core/gameweek.store';
import { HomeDashboard, PlayerSeasonStat } from '../../core/models';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    MatTableModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatSelectModule,
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
  readonly dashboard = signal<HomeDashboard | null>(null);
  readonly seasonStats = signal<PlayerSeasonStat[]>([]);

  readonly statsPosition = signal('');
  readonly minMinutes = signal(90);

  readonly topGwColumns = ['player', 'team', 'pts', 'returns'];
  readonly statsColumns = ['player', 'team', 'pts', 'goals', 'assists', 'mins', 'price'];

  constructor() {
    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      const pos = this.statsPosition();
      const min = this.minMinutes();
      if (gw) {
        this.loadDashboard();
        this.loadStats(gw, pos, min);
      }
    });
  }

  onStatsPosition(value: string): void {
    this.statsPosition.set(value);
  }

  onMinMinutes(value: number): void {
    this.minMinutes.set(value);
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

  private loadStats(gw: number, position: string, minMinutes: number): void {
    this.loadingStats.set(true);
    this.api.getPlayerSeasonStats(gw, position || undefined, minMinutes, 30).subscribe({
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
