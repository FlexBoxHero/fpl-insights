import { Component, Input } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ClubIdentity, clubBadgeUrl, clubFullName, clubShortName } from '../../core/club-badges';

@Component({
  selector: 'app-club-mark',
  standalone: true,
  imports: [MatTooltipModule],
  template: `
    <span class="club-mark" [class.badge-only]="!showName" [matTooltip]="resolvedFullName" matTooltipPosition="right">
      @if (badgeUrl; as src) {
        <img [src]="src" alt="" [width]="size" [height]="size" (error)="onBadgeError($event)" />
      }
      @if (showName) {
        <strong>{{ resolvedShortName }}</strong>
      }
    </span>
  `,
  styles: `
    :host {
      display: inline-flex;
      vertical-align: middle;
    }

    .club-mark {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      cursor: default;
      white-space: nowrap;
    }

    img {
      object-fit: contain;
      flex-shrink: 0;
    }
  `,
})
export class ClubMarkComponent {
  @Input() team?: string | null;
  @Input() shortName?: string | null;
  @Input() fullName?: string | null;
  @Input() teamCode?: number | null;
  @Input() size = 22;
  @Input() showName = true;

  get identity(): ClubIdentity {
    return {
      team: this.team,
      short_name: this.shortName,
      team_name: this.fullName,
      team_code: this.teamCode,
    };
  }

  get resolvedShortName(): string {
    return clubShortName(this.identity);
  }

  get resolvedFullName(): string {
    return clubFullName(this.identity);
  }

  get badgeUrl(): string | null {
    return clubBadgeUrl(this.teamCode, this.resolvedShortName);
  }

  onBadgeError(event: Event): void {
    const img = event.target as HTMLImageElement | null;
    if (img) {
      img.style.display = 'none';
    }
  }
}
