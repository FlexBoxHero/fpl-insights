import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiService } from '../../core/api.service';
import { ChipAdvice, ChipHalf, ChipId, ChipStrategy, ChipWindow } from '../../core/models';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';

const ALL_CHIPS: ChipId[] = ['wildcard', 'bench_boost', 'triple_captain', 'free_hit'];
const STORAGE_KEY = 'fpl.chipAvailability';


const CHIP_LABELS: Record<ChipId, string> = {
  wildcard: 'Wildcard',
  bench_boost: 'Bench Boost',
  triple_captain: 'Triple Captain',
  free_hit: 'Free Hit',
};

const CHIP_BLURB: Record<ChipId, string> = {
  wildcard: 'Unlimited transfers for one week. Best when fixtures swing or a double is coming.',
  bench_boost: 'Your bench scores too. Best when all 15 play — especially a double gameweek.',
  triple_captain: 'Captain scores 3×. Ranked by fixture juice — home, attack xG, and FDR — not just the usual premium.',
  free_hit: 'A one-week squad that reverts after. Best in a blank, or a punt into easy fixtures.',
};

interface StoredChips {
  first: ChipId[];
}

@Component({
  selector: 'app-chip-strategy',
  standalone: true,
  imports: [
    DecimalPipe,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    ClubMarkComponent,
  ],
  templateUrl: './chip-strategy.component.html',
  styleUrl: './chip-strategy.component.scss',
})
export class ChipStrategyComponent {
  private readonly api = inject(ApiService);

  readonly chipIds = ALL_CHIPS;
  readonly chipLabels = CHIP_LABELS;
  readonly chipBlurb = CHIP_BLURB;

  readonly firstAvailable = signal<ChipId[]>([...ALL_CHIPS]);
  readonly loading = signal(false);
  readonly strategy = signal<ChipStrategy | null>(null);

  readonly firstHalf = computed(() => this.strategy()?.first_half ?? null);

  constructor() {
    const stored = this.readStored();
    if (stored) {
      this.firstAvailable.set(stored.first);
    }
    effect(() => {
      const first = this.firstAvailable();
      this.persist(first);
      this.load(first);
    });
  }

  isOn(chip: ChipId): boolean {
    return this.firstAvailable().includes(chip);
  }

  toggle(chip: ChipId, enabled: boolean): void {
    const current = this.firstAvailable();
    this.firstAvailable.set(
      enabled ? this.addChip(current, chip) : current.filter((c) => c !== chip),
    );
  }

  chipAdvice(half: ChipHalf, chip: ChipId): ChipAdvice | undefined {
    return half.chips.find((c) => c.chip === chip);
  }

  chipClass(chip: string): string {
    return `chip-tag chip-${chip}`;
  }

  confidenceClass(value: string): string {
    return `confidence confidence-${value}`;
  }

  flagLabel(flag: string): string {
    if (flag === 'dgw') {
      return 'DGW';
    }
    if (flag === 'bgw') {
      return 'BGW';
    }
    if (flag === 'easier_run') {
      return 'Easier run';
    }
    if (flag === 'dgw_soon') {
      return 'DGW soon';
    }
    return flag;
  }

  trackWindow(_index: number, row: ChipWindow): string {
    return `${row.chip}-${row.gameweek}`;
  }

  private addChip(list: ChipId[], chip: ChipId): ChipId[] {
    if (list.includes(chip)) {
      return list;
    }
    return ALL_CHIPS.filter((id) => id === chip || list.includes(id));
  }

  private load(first: ChipId[]): void {
    this.loading.set(true);
    this.api.getChipStrategy(first, []).subscribe({
      next: (data) => {
        this.strategy.set(data);
        this.loading.set(false);
      },
      error: () => {
        this.strategy.set(null);
        this.loading.set(false);
      },
    });
  }

  private readStored(): StoredChips | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return null;
      }
      const parsed = JSON.parse(raw) as StoredChips;
      return {
        first: this.sanitize(parsed.first),
      };
    } catch {
      return null;
    }
  }

  private persist(first: ChipId[]): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ first }));
    } catch {
      /* ignore quota / private mode */
    }
  }

  private sanitize(value: ChipId[] | undefined): ChipId[] {
    if (!Array.isArray(value)) {
      return [...ALL_CHIPS];
    }
    return ALL_CHIPS.filter((id) => value.includes(id));
  }
}
