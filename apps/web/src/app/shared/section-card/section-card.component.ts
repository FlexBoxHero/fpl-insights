import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'app-section-card',
  standalone: true,
  template: `
    <section
      class="section-card"
      [class.compact-section]="compact"
      [class.collapsible]="collapsible"
      [class.expanded]="!collapsible || expanded"
    >
      @if (collapsible) {
        <button
          type="button"
          class="section-toggle"
          (click)="toggle()"
          [attr.aria-expanded]="expanded"
        >
          <div class="section-toggle-text">
            <h2>{{ title }}</h2>
            @if (summary && !expanded) {
              <p class="section-summary">{{ summary }}</p>
            }
          </div>
          <span class="chevron" aria-hidden="true">▸</span>
        </button>
      } @else if (title) {
        <h2>{{ title }}</h2>
      }
      <div class="section-body" [class.is-open]="!collapsible || expanded">
        <div class="section-body-inner">
          <ng-content />
        </div>
      </div>
    </section>
  `,
  styles: `
    :host {
      display: block;
      min-width: 0;
    }

    .section-toggle {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.75rem;
      width: 100%;
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      text-align: left;
      cursor: pointer;
    }

    .section-toggle-text {
      min-width: 0;
      flex: 1;
    }

    .section-toggle h2 {
      margin: 0;
    }

    .section-summary {
      margin: 0.25rem 0 0;
      color: var(--fpl-muted);
      font-size: 0.82rem;
      line-height: 1.35;
    }

    .chevron {
      flex-shrink: 0;
      color: var(--fpl-muted);
      font-size: 1.05rem;
      line-height: 1.2;
      padding-top: 0.1rem;
      display: inline-block;
      transition: transform 200ms ease;
    }

    .expanded .chevron {
      transform: rotate(90deg);
    }

    .collapsible:not(.expanded) {
      padding-bottom: 0.95rem;
    }

    .section-body {
      display: grid;
      grid-template-rows: 0fr;
      opacity: 0;
      margin-top: 0;
      pointer-events: none;
      transition:
        grid-template-rows 220ms ease,
        opacity 180ms ease,
        margin-top 220ms ease;
    }

    .section-body.is-open {
      grid-template-rows: 1fr;
      opacity: 1;
      margin-top: 0.65rem;
      pointer-events: auto;
    }

    .section-body-inner {
      min-height: 0;
      overflow: hidden;
    }

    .section-card:not(.collapsible) .section-body-inner {
      overflow: visible;
    }

    @media (prefers-reduced-motion: reduce) {
      .section-body,
      .chevron {
        transition: none;
      }
    }
  `,
})
export class SectionCardComponent {
  @Input() title = '';
  @Input() summary = '';
  @Input() compact = false;
  @Input() collapsible = false;
  @Input() expanded = true;
  @Output() expandedChange = new EventEmitter<boolean>();

  toggle(): void {
    if (!this.collapsible) {
      return;
    }
    this.expandedChange.emit(!this.expanded);
  }
}
