import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { ModelMeta } from '../../core/models';

@Component({
  selector: 'app-about',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './about.component.html',
  styleUrl: './about.component.scss',
})
export class AboutComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly meta = signal<ModelMeta | null>(null);

  ngOnInit(): void {
    this.api.getModelMeta().subscribe((m) => this.meta.set(m));
  }
}
