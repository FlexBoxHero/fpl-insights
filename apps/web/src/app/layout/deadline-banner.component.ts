import { Component, DestroyRef, OnInit, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval } from 'rxjs';
import { GameweekStore } from '../core/gameweek.store';

@Component({
  selector: 'app-deadline-banner',
  standalone: true,
  template: `
    <div class="gw-chip" [class.urgent]="urgent()">
      @if (gwNumber(); as n) {
        <span class="meta">
          <span class="gw">GW{{ n }}</span>
          <span class="range long">{{ duration() }}</span>
          <span class="range short">{{ durationShort() }}</span>
        </span>
        <span class="value">{{ countdown() }}</span>
      } @else {
        <span class="label">Next deadline</span>
        <span class="value">{{ countdown() }}</span>
      }
    </div>
  `,
  styles: `
    .gw-chip {
      display: flex;
      align-items: baseline;
      gap: 0.7rem;
      padding: 0.35rem 0.85rem;
      border-radius: 999px;
      background: var(--fpl-chip-bg);
      color: var(--fpl-topbar-text);
      font-size: 0.85rem;
      white-space: nowrap;
    }
    .meta {
      display: inline-flex;
      align-items: baseline;
      gap: 0.45rem;
      min-width: 0;
    }
    .gw {
      font-weight: 700;
      letter-spacing: 0.02em;
      color: var(--fpl-nav-active-text);
    }
    .range {
      opacity: 0.9;
      font-size: 0.78rem;
    }
    .range.short {
      display: none;
    }
    .label {
      opacity: 0.85;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 0.7rem;
    }
    .value {
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    @media (max-width: 840px) {
      .gw-chip {
        flex-direction: column;
        align-items: flex-end;
        gap: 0.05rem;
        padding: 0.22rem 0.55rem 0.28rem;
        border-radius: 12px;
        font-size: 0.78rem;
      }
      .range.long {
        display: none;
      }
      .range.short {
        display: inline;
        font-size: 0.68rem;
      }
      .label {
        display: none;
      }
    }
    .urgent {
      background: rgba(255, 107, 107, 0.25);
      box-shadow: 0 0 0 1px rgba(255, 107, 107, 0.35);
    }
  `,
})
export class DeadlineBannerComponent implements OnInit {
  private readonly gwStore = inject(GameweekStore);
  private readonly destroyRef = inject(DestroyRef);

  readonly countdown = signal('—');
  readonly urgent = signal(false);

  readonly gwNumber = computed(() => this.gwStore.headerGameweek()?.number ?? null);
  readonly duration = computed(() => {
    const gw = this.gwStore.headerGameweek();
    return formatGameweekSpan(gw?.first_kickoff, gw?.last_kickoff, gw?.deadline_time, false);
  });
  readonly durationShort = computed(() => {
    const gw = this.gwStore.headerGameweek();
    return formatGameweekSpan(gw?.first_kickoff, gw?.last_kickoff, gw?.deadline_time, true);
  });

  constructor() {
    effect(() => {
      this.gwStore.headerGameweek();
      this.tick();
    });
  }

  ngOnInit(): void {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.tick());
  }

  private tick(): void {
    const gw = this.gwStore.headerGameweek();
    const deadlineIso = gw?.deadline_time;
    if (!deadlineIso) {
      this.countdown.set('TBC');
      this.urgent.set(false);
      return;
    }
    const deadlineMs = Date.parse(deadlineIso);
    if (Number.isNaN(deadlineMs)) {
      this.countdown.set('TBC');
      this.urgent.set(false);
      return;
    }
    const diff = deadlineMs - Date.now();
    if (diff <= 0) {
      this.countdown.set(gw?.finished ? 'Done' : 'Live');
      this.urgent.set(!gw?.finished);
      return;
    }
    const totalSec = Math.floor(diff / 1000);
    const days = Math.floor(totalSec / 86400);
    const hours = Math.floor((totalSec % 86400) / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;
    const parts =
      days > 0
        ? `${days}d ${hours}h ${mins}m`
        : `${hours}h ${mins.toString().padStart(2, '0')}m ${secs.toString().padStart(2, '0')}s`;
    this.countdown.set(parts);
    this.urgent.set(diff < 3 * 60 * 60 * 1000);
  }
}

function parseIso(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : new Date(ms);
}

export function formatGameweekSpan(
  firstKickoff: string | null | undefined,
  lastKickoff: string | null | undefined,
  deadline: string | null | undefined,
  compact: boolean,
): string {
  const start = parseIso(firstKickoff) ?? parseIso(deadline);
  const end = parseIso(lastKickoff) ?? parseIso(firstKickoff);
  if (!start) {
    return 'Dates TBC';
  }
  if (!end || start.toDateString() === end.toDateString()) {
    return formatDay(start, true, !compact);
  }
  const sameMonth = start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth();
  if (sameMonth) {
    return `${formatDay(start, false, !compact)} – ${formatDay(end, true, !compact)}`;
  }
  return `${formatDay(start, true, !compact)} – ${formatDay(end, true, !compact)}`;
}

function formatDay(date: Date, withMonth: boolean, withWeekday: boolean): string {
  return new Intl.DateTimeFormat('en-GB', {
    ...(withWeekday ? { weekday: 'short' as const } : {}),
    day: 'numeric',
    ...(withMonth ? { month: 'short' as const } : {}),
  }).format(date);
}
