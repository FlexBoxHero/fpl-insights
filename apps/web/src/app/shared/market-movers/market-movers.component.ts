import { Component, Input } from '@angular/core';
import { HomeDashboard, PlayerBrief } from '../../core/models';
import { MoverMetric, MoverTableComponent } from './mover-table.component';

interface MoverSection {
  title: string;
  desc: string;
  rows: PlayerBrief[];
  metric: MoverMetric;
}

@Component({
  selector: 'app-market-movers',
  standalone: true,
  imports: [MoverTableComponent],
  templateUrl: './market-movers.component.html',
  styleUrl: './market-movers.component.scss',
})
export class MarketMoversComponent {
  @Input({ required: true }) dashboard!: HomeDashboard;

  gwSections(): MoverSection[] {
    const d = this.dashboard;
    return [
      {
        title: 'Price risers',
        desc: 'Largest £ increases this gameweek.',
        rows: d.price_risers,
        metric: 'priceGwUp',
      },
      {
        title: 'Price fallers',
        desc: 'Largest £ decreases this gameweek.',
        rows: d.price_fallers,
        metric: 'priceGwDown',
      },
      {
        title: 'Transfers in',
        desc: 'Most bought this gameweek.',
        rows: d.transfers_in,
        metric: 'inGw',
      },
      {
        title: 'Transfers out',
        desc: 'Most sold this gameweek.',
        rows: d.transfers_out,
        metric: 'outGw',
      },
    ];
  }

  allTimeSections(): MoverSection[] {
    const d = this.dashboard;
    return [
      {
        title: 'Price risers',
        desc: 'Largest £ increases since the start of the season.',
        rows: d.price_risers_all_time,
        metric: 'priceAllUp',
      },
      {
        title: 'Price fallers',
        desc: 'Largest £ decreases since the start of the season.',
        rows: d.price_fallers_all_time,
        metric: 'priceAllDown',
      },
      {
        title: 'Transfers in',
        desc: 'Most bought this season.',
        rows: d.transfers_in_all_time,
        metric: 'inAll',
      },
      {
        title: 'Transfers out',
        desc: 'Most sold this season.',
        rows: d.transfers_out_all_time,
        metric: 'outAll',
      },
    ];
  }

  groups(): { heading: string; sections: MoverSection[] }[] {
    return [
      { heading: 'This gameweek', sections: this.gwSections() },
      { heading: 'All-time (this season)', sections: this.allTimeSections() },
    ];
  }
}
