import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { Gameweek } from './models';

@Injectable({ providedIn: 'root' })
export class GameweekStore {
  private readonly api = inject(ApiService);

  readonly gameweeks = signal<Gameweek[]>([]);
  readonly selectedGameweek = signal<number | null>(null);
  readonly loading = signal(false);

  readonly defaultGameweek = computed(() => {
    const list = this.gameweeks();
    const next = list.find((g) => g.is_next);
    if (next) {
      return next.number;
    }
    const current = list.find((g) => g.is_current);
    if (current) {
      return current.number + 1;
    }
    const open = list.find((g) => !g.finished);
    return open?.number ?? list[list.length - 1]?.number ?? 1;
  });

  load(): void {
    this.loading.set(true);
    this.api.getGameweeks().subscribe({
      next: (gws) => {
        this.gameweeks.set(gws);
        if (this.selectedGameweek() === null) {
          this.selectedGameweek.set(this.defaultGameweek());
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  selectGameweek(n: number): void {
    this.selectedGameweek.set(n);
  }
}
