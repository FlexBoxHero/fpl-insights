import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval } from 'rxjs';
import { ApiService } from '../core/api.service';

@Component({
  selector: 'app-deadline-banner',
  standalone: true,
  template: `
    <div class="deadline" [class.urgent]="urgent()">
      <span class="label">Next deadline</span>
      <span class="value">{{ countdown() }}</span>
    </div>
  `,
  styles: `
    .deadline {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.35rem 0.85rem;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      font-size: 0.85rem;
      white-space: nowrap;
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
      .deadline {
        padding: 0.28rem 0.6rem;
        font-size: 0.78rem;
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
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  private deadlineMs: number | null = null;
  readonly countdown = signal('—');
  readonly urgent = signal(false);

  ngOnInit(): void {
    this.refreshDeadline();
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.tick());
    interval(60_000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.refreshDeadline());
  }

  private refreshDeadline(): void {
    this.api.getDeadline().subscribe({
      next: (meta) => {
        this.deadlineMs = meta.deadline_time ? Date.parse(meta.deadline_time) : null;
        this.tick();
      },
    });
  }

  private tick(): void {
    if (this.deadlineMs == null) {
      this.countdown.set('TBC');
      this.urgent.set(false);
      return;
    }
    const diff = this.deadlineMs - Date.now();
    if (diff <= 0) {
      this.countdown.set('Closed');
      this.urgent.set(true);
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
