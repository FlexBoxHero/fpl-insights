import { Routes } from '@angular/router';
import { ShellComponent } from './layout/shell.component';

export const routes: Routes = [
  {
    path: '',
    component: ShellComponent,
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/home/home.component').then((m) => m.HomeComponent),
      },
      {
        path: 'teams',
        loadComponent: () =>
          import('./features/team-predictions/team-predictions.component').then(
            (m) => m.TeamPredictionsComponent,
          ),
      },
      {
        path: 'players',
        loadComponent: () =>
          import('./features/player-predictions/player-predictions.component').then(
            (m) => m.PlayerPredictionsComponent,
          ),
      },
      {
        path: 'chips',
        loadComponent: () =>
          import('./features/chip-strategy/chip-strategy.component').then(
            (m) => m.ChipStrategyComponent,
          ),
      },
      {
        path: 'team',
        loadComponent: () =>
          import('./features/my-team/my-team.component').then((m) => m.MyTeamComponent),
      },
      {
        path: 'about',
        loadComponent: () =>
          import('./features/about/about.component').then((m) => m.AboutComponent),
      },
    ],
  },
];
