import { Injectable, signal } from '@angular/core';

export type ColorTheme = 'dark' | 'light';

const STORAGE_KEY = 'fpl.theme';
const DARK_THEME_COLOR = '#1a0533';
const LIGHT_THEME_COLOR = '#ece7f8';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<ColorTheme>('dark');

  constructor() {
    this.apply(this.read());
  }

  toggle(): void {
    this.apply(this.theme() === 'dark' ? 'light' : 'dark');
  }

  private read(): ColorTheme {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  }

  private apply(theme: ColorTheme): void {
    this.theme.set(theme);
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === 'light' ? LIGHT_THEME_COLOR : DARK_THEME_COLOR);
    }
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore quota / private mode */
    }
  }
}
