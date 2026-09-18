import { Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { GameweekStore } from '../core/gameweek.store';
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

  ngOnInit(): void {
    this.gwStore.load();
  }
}
