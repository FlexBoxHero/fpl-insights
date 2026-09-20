import { Component, OnInit, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { GameweekStore } from '../core/gameweek.store';
import { ThemeService } from '../core/theme.service';
import { DeadlineBannerComponent } from './deadline-banner.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    DeadlineBannerComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  private readonly gwStore = inject(GameweekStore);
  private readonly themeService = inject(ThemeService);

  readonly themeLabel = computed(() =>
    this.themeService.theme() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
  );
  readonly themeIcon = computed(() =>
    this.themeService.theme() === 'dark' ? 'light_mode' : 'dark_mode',
  );

  ngOnInit(): void {
    this.gwStore.load();
  }

  toggleTheme(): void {
    this.themeService.toggle();
  }
}
