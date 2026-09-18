import { DecimalPipe } from '@angular/common';
import { Component, Input } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ClubMarkComponent } from '../club-mark/club-mark.component';
import { PlayerBrief } from '../../core/models';

export type MoverMetric =
  | 'priceGwUp'
  | 'priceGwDown'
  | 'priceAllUp'
  | 'priceAllDown'
  | 'inGw'
  | 'outGw'
  | 'inAll'
  | 'outAll';

@Component({
  selector: 'app-mover-table',
  standalone: true,
  imports: [MatTableModule, MatTooltipModule, DecimalPipe, ClubMarkComponent],
  template: `
    @if (rows.length === 0) {
      <p class="empty">No data.</p>
    } @else {
      <div class="table-wrap">
      <table mat-table [dataSource]="rows" class="pred-table compact">
        <ng-container matColumnDef="player">
          <th mat-header-cell *matHeaderCellDef>Player</th>
          <td mat-cell *matCellDef="let row" [matTooltip]="row.full_name">{{ row.web_name }}</td>
        </ng-container>
        <ng-container matColumnDef="team">
          <th mat-header-cell *matHeaderCellDef>Team</th>
          <td mat-cell *matCellDef="let row">
            <app-club-mark
              [team]="row.team"
              [fullName]="row.team_name"
              [teamCode]="row.team_code"
              [size]="18"
            />
          </td>
        </ng-container>
        <ng-container matColumnDef="detail">
          <th mat-header-cell *matHeaderCellDef>{{ valueLabel }}</th>
          <td
            mat-cell
            *matCellDef="let row"
            [class.positive]="isPositive"
            [class.negative]="isNegative"
          >
            @if (isPrice) {
              @if (value(row) > 0) {
                +£{{ value(row) | number: '1.1-1' }}m
              } @else {
                -£{{ abs(value(row)) | number: '1.1-1' }}m
              }
            } @else {
              {{ value(row) | number }}
            }
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="columns"></tr>
        <tr mat-row *matRowDef="let row; columns: columns"></tr>
      </table>
      </div>
    }
  `,
  styles: `
    :host {
      display: block;
      min-width: 0;
    }

    .table-wrap {
      overflow-x: auto;
    }

    table {
      width: 100%;
      table-layout: fixed;
    }

    .mat-column-player {
      width: 42%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .mat-column-team {
      width: 32%;
    }

    .mat-column-detail {
      width: 26%;
      text-align: right;
      white-space: nowrap;
    }

    .positive {
      color: var(--fpl-accent);
      font-weight: 600;
    }
    .negative {
      color: var(--fpl-danger);
      font-weight: 600;
    }
    .compact td,
    .compact th {
      padding-top: 0.35rem !important;
      padding-bottom: 0.35rem !important;
    }
  `,
})
export class MoverTableComponent {
  @Input({ required: true }) rows: PlayerBrief[] = [];
  @Input({ required: true }) metric!: MoverMetric;

  readonly columns = ['player', 'team', 'detail'];

  get valueLabel(): string {
    return this.metric.startsWith('price') ? 'Change' : 'Transfers';
  }

  get isPrice(): boolean {
    return this.metric.startsWith('price');
  }

  get isPositive(): boolean {
    return this.metric === 'priceGwUp' || this.metric === 'priceAllUp';
  }

  get isNegative(): boolean {
    return this.metric === 'priceGwDown' || this.metric === 'priceAllDown';
  }

  value(row: PlayerBrief): number {
    switch (this.metric) {
      case 'priceGwUp':
      case 'priceGwDown':
        return row.cost_change_event;
      case 'priceAllUp':
      case 'priceAllDown':
        return row.cost_change_start;
      case 'inGw':
        return row.transfers_in_event;
      case 'outGw':
        return row.transfers_out_event;
      case 'inAll':
        return row.transfers_in;
      case 'outAll':
        return row.transfers_out;
    }
  }

  abs(n: number): number {
    return Math.abs(n);
  }
}
