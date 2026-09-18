import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  AfterViewInit,
  Component,
  computed,
  effect,
  ElementRef,
  HostListener,
  inject,
  signal,
  ViewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../core/api.service';
import { GameweekStore } from '../../core/gameweek.store';
import {
  PlayerPrediction,
  SquadAnalysis,
  SquadPickIn,
  SquadScreenshotMatch,
} from '../../core/models';
import { ClubMarkComponent } from '../../shared/club-mark/club-mark.component';

const STORAGE_KEY = 'fpl.myTeamPitch.v1';
const SLOTS: Record<string, number> = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const POSITIONS = ['GK', 'DEF', 'MID', 'FWD'] as const;
const DEFAULT_FORMATION = '4-4-2';
const FORMATIONS: Record<string, { DEF: number; MID: number; FWD: number }> = {
  '3-4-3': { DEF: 3, MID: 4, FWD: 3 },
  '3-5-2': { DEF: 3, MID: 5, FWD: 2 },
  '4-4-2': { DEF: 4, MID: 4, FWD: 2 },
  '4-3-3': { DEF: 4, MID: 3, FWD: 3 },
  '4-5-1': { DEF: 4, MID: 5, FWD: 1 },
  '5-4-1': { DEF: 5, MID: 4, FWD: 1 },
  '5-3-2': { DEF: 5, MID: 3, FWD: 2 },
  '5-2-3': { DEF: 5, MID: 2, FWD: 3 },
};

type Pos = (typeof POSITIONS)[number];

interface SquadSlot {
  key: string;
  position: Pos;
  starter: boolean;
  player: PlayerPrediction | null;
}

interface StoredPitch {
  formation: string;
  slotPlayers: Record<string, number | null>;
  captainId: number | null;
  viceId: number | null;
  bank?: number;
  freeTransfers: number;
  budgetCap?: number;
}

function takePlayer(queue: PlayerPrediction[]): PlayerPrediction | null {
  return queue.shift() ?? null;
}

function makeSlots(formation: string, byPos?: Record<Pos, PlayerPrediction[]>): SquadSlot[] {
  const shape = FORMATIONS[formation] ?? FORMATIONS[DEFAULT_FORMATION];
  const queues: Record<Pos, PlayerPrediction[]> = {
    GK: [...(byPos?.GK ?? [])],
    DEF: [...(byPos?.DEF ?? [])],
    MID: [...(byPos?.MID ?? [])],
    FWD: [...(byPos?.FWD ?? [])],
  };
  const slots: SquadSlot[] = [
    { key: 'xi-GK-0', position: 'GK', starter: true, player: takePlayer(queues.GK) },
  ];
  (['DEF', 'MID', 'FWD'] as const).forEach((pos) => {
    for (let i = 0; i < shape[pos]; i++) {
      slots.push({
        key: `xi-${pos}-${i}`,
        position: pos,
        starter: true,
        player: takePlayer(queues[pos]),
      });
    }
  });
  const remain: Record<Pos, number> = {
    GK: 1,
    DEF: 5 - shape.DEF,
    MID: 5 - shape.MID,
    FWD: 3 - shape.FWD,
  };
  POSITIONS.forEach((pos) => {
    for (let i = 0; i < remain[pos]; i++) {
      slots.push({
        key: `bn-${pos}-${i}`,
        position: pos,
        starter: false,
        player: takePlayer(queues[pos]),
      });
    }
  });
  return slots;
}

function groupByPos(slots: SquadSlot[], startersFirst = true): Record<Pos, PlayerPrediction[]> {
  const grouped: Record<Pos, PlayerPrediction[]> = { GK: [], DEF: [], MID: [], FWD: [] };
  const ordered = startersFirst
    ? [...slots.filter((s) => s.starter), ...slots.filter((s) => !s.starter)]
    : slots;
  for (const slot of ordered) {
    if (slot.player) {
      grouped[slot.position].push(slot.player);
    }
  }
  return grouped;
}

@Component({
  selector: 'app-my-team',
  standalone: true,
  imports: [
    DecimalPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatTabsModule,
    ClubMarkComponent,
  ],
  templateUrl: './my-team.component.html',
  styleUrl: './my-team.component.scss',
})
export class MyTeamComponent implements AfterViewInit {
  private readonly api = inject(ApiService);
  private readonly gwStore = inject(GameweekStore);
  @ViewChild('pitchStage') private pitchStage?: ElementRef<HTMLElement>;
  @ViewChild('pitchFoot') private pitchFoot?: ElementRef<HTMLElement>;
  private lastPitchMaxH = '';

  readonly formationOptions = Object.keys(FORMATIONS);
  readonly pool = signal<PlayerPrediction[]>([]);
  readonly slots = signal<SquadSlot[]>(makeSlots(DEFAULT_FORMATION));
  readonly formation = signal(DEFAULT_FORMATION);
  readonly captainId = signal<number | null>(null);
  readonly viceId = signal<number | null>(null);
  readonly budgetCap = signal(100);
  readonly freeTransfers = signal(1);
  readonly entryId = signal('');
  readonly loadingPool = signal(false);
  readonly loading = signal(false);
  readonly parsing = signal(false);
  readonly error = signal<string | null>(null);
  readonly analysis = signal<SquadAnalysis | null>(null);
  readonly visionEnabled = signal(false);
  readonly screenshotMatches = signal<SquadScreenshotMatch[]>([]);
  readonly screenshotNotes = signal('');
  readonly editorOpen = signal(false);
  readonly editorSlot = signal<SquadSlot | null>(null);
  readonly editorQuery = signal('');
  readonly editorMaxPrice = signal<number | null>(null);
  readonly editorSort = signal<'xpts' | 'value' | 'price-asc' | 'price-desc'>('xpts');
  readonly editorInBudget = signal(false);
  readonly priceCaps = [4.5, 5.5, 6.5, 8.0, 10.0];
  readonly sortOptions = [
    { id: 'xpts' as const, label: 'Highest xPts' },
    { id: 'value' as const, label: 'Best value' },
    { id: 'price-asc' as const, label: 'Cheapest' },
    { id: 'price-desc' as const, label: 'Most expensive' },
  ];
  readonly selectedTab = signal(0);
  readonly entryLoaded = signal(false);
  readonly screenshotLoaded = signal(false);

  readonly showPitch = computed(() => {
    const tab = this.selectedTab();
    if (tab === 0) {
      return true;
    }
    if (tab === 1) {
      return this.entryLoaded();
    }
    return this.screenshotLoaded();
  });

  readonly picked = computed(() =>
    this.slots()
      .map((s) => s.player)
      .filter((p): p is PlayerPrediction => !!p),
  );
  readonly budgetUsed = computed(() => {
    const used = this.picked().reduce((sum, p) => sum + p.price, 0);
    return Math.round(used * 10) / 10;
  });
  /** Remaining / bank — always budget minus used. Squad cannot exceed the cap. */
  readonly budgetLeft = computed(() => Math.round((this.budgetCap() - this.budgetUsed()) * 10) / 10);
  readonly usedDisplay = computed(() => `£${this.budgetUsed().toFixed(1)}m`);
  readonly remainingDisplay = computed(() => `£${this.budgetLeft().toFixed(1)}m`);
  readonly squadFull = computed(() => {
    const list = this.picked();
    return (
      list.length === 15 &&
      POSITIONS.every((pos) => list.filter((p) => p.position === pos).length === SLOTS[pos])
    );
  });
  readonly pitchRows = computed(() => {
    const slots = this.slots().filter((s) => s.starter);
    return [...POSITIONS]
      .reverse()
      .map((pos) => ({
        pos,
        slots: slots.filter((s) => s.position === pos),
      }))
      .filter((row) => row.slots.length);
  });
  readonly benchSlots = computed(() => this.slots().filter((s) => !s.starter));
  readonly unmatchedNames = computed(() =>
    this.screenshotMatches()
      .filter((row) => !row.player)
      .map((row) => row.raw_name)
      .filter((name) => !!name),
  );
  readonly subTargets = computed(() => {
    const slot = this.editorSlot();
    if (!slot?.player || slot.starter) {
      return [];
    }
    return this.slots().filter((target) => this.canSub(slot, target));
  });
  readonly editorHits = computed(() => {
    const slot = this.editorSlot();
    if (!slot) {
      return [];
    }
    const q = this.editorQuery().trim().toLowerCase();
    const maxPrice = this.editorMaxPrice();
    const inBudget = this.editorInBudget();
    const currentId = slot.player?.player_id ?? null;
    const currentPrice = slot.player?.price ?? 0;
    const room = this.budgetCap() + 0.05 - (this.budgetUsed() - currentPrice);
    const taken = new Set(this.picked().map((p) => p.player_id));
    if (currentId != null) {
      taken.delete(currentId);
    }
    const hits = this.pool()
      .filter((p) => p.position === slot.position && !taken.has(p.player_id))
      .filter(
        (p) =>
          !q ||
          p.web_name.toLowerCase().includes(q) ||
          p.full_name.toLowerCase().includes(q) ||
          p.team.toLowerCase().includes(q),
      )
      .filter((p) => maxPrice == null || p.price <= maxPrice + 0.001)
      .filter((p) => !inBudget || p.price <= room + 0.001);
    const sort = this.editorSort();
    hits.sort((a, b) => {
      if (sort === 'price-asc') {
        return a.price - b.price || b.expected_points - a.expected_points;
      }
      if (sort === 'price-desc') {
        return b.price - a.price || b.expected_points - a.expected_points;
      }
      if (sort === 'value') {
        const va = a.price > 0 ? a.expected_points / a.price : 0;
        const vb = b.price > 0 ? b.expected_points / b.price : 0;
        return vb - va || b.expected_points - a.expected_points;
      }
      return b.expected_points - a.expected_points || a.price - b.price;
    });
    return hits.slice(0, 20);
  });

  constructor() {
    this.api.getSquadVisionStatus().subscribe({
      next: (s) => this.visionEnabled.set(s.enabled),
      error: () => this.visionEnabled.set(false),
    });
    effect(() => {
      const gw = this.gwStore.selectedGameweek();
      if (gw) {
        this.loadPool(gw);
      }
    });
    effect(() => {
      this.showPitch();
      this.selectedTab();
      requestAnimationFrame(() => this.fitPitchToViewport());
    });
  }

  ngAfterViewInit(): void {
    this.fitPitchToViewport();
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    this.fitPitchToViewport();
  }

  private fitPitchToViewport(): void {
    const stage = this.pitchStage?.nativeElement;
    if (!stage) {
      return;
    }
    if (window.matchMedia('(max-width: 900px)').matches) {
      this.lastPitchMaxH = '';
      stage.style.removeProperty('--pitch-max-h');
      return;
    }
    const foot = this.pitchFoot?.nativeElement;
    const top = stage.getBoundingClientRect().top + window.scrollY;
    const footH = foot?.offsetHeight ?? 0;
    const section = stage.closest('.pitch-section');
    const sectionPad = section ? parseFloat(getComputedStyle(section).paddingBottom) || 0 : 0;
    const main = document.querySelector('main.content');
    const padBottom = main ? parseFloat(getComputedStyle(main).paddingBottom) || 0 : 32;
    const maxH = Math.max(
      240,
      Math.floor(window.innerHeight - top - footH - sectionPad - padBottom - 20),
    );
    const value = `${maxH}px`;
    if (value !== this.lastPitchMaxH) {
      this.lastPitchMaxH = value;
      stage.style.setProperty('--pitch-max-h', value);
    }
    if (this.analysis()) {
      return;
    }
    requestAnimationFrame(() => {
      const overflow = document.documentElement.scrollHeight - window.innerHeight;
      if (overflow <= 1 || overflow > 80) {
        return;
      }
      const current = parseFloat(stage.style.getPropertyValue('--pitch-max-h')) || maxH;
      const adj = `${Math.max(240, Math.floor(current - overflow))}px`;
      if (adj !== this.lastPitchMaxH) {
        this.lastPitchMaxH = adj;
        stage.style.setProperty('--pitch-max-h', adj);
      }
    });
  }

  countFor(pos: string): number {
    return this.picked().filter((p) => p.position === pos).length;
  }

  setFormation(code: string): void {
    if (!FORMATIONS[code] || code === this.formation()) {
      return;
    }
    this.formation.set(code);
    this.slots.set(makeSlots(code, groupByPos(this.slots())));
    this.persist();
    if (this.squadFull()) {
      this.runAnalysis(this.picksPayload());
    }
  }

  setTab(index: number): void {
    if (index === this.selectedTab()) {
      return;
    }
    this.selectedTab.set(index);
    this.resetScreen();
    requestAnimationFrame(() => this.fitPitchToViewport());
  }

  clearPitch(): void {
    this.formation.set(DEFAULT_FORMATION);
    this.slots.set(makeSlots(DEFAULT_FORMATION));
    this.captainId.set(null);
    this.viceId.set(null);
    this.freeTransfers.set(1);
    this.analysis.set(null);
    this.error.set(null);
    this.persist();
  }

  resetScreen(): void {
    this.closeEditor();
    this.entryId.set('');
    this.entryLoaded.set(false);
    this.screenshotMatches.set([]);
    this.screenshotNotes.set('');
    this.screenshotLoaded.set(false);
    this.parsing.set(false);
    this.loading.set(false);
    this.clearPitch();
  }

  canSub(bench: SquadSlot, xi: SquadSlot): boolean {
    if (!bench.player || !xi.player || bench.starter || !xi.starter) {
      return false;
    }
    const on = bench.player;
    const off = xi.player;
    if (on.position === 'GK' || off.position === 'GK') {
      return on.position === 'GK' && off.position === 'GK';
    }
    const nextXi = this.slots()
      .filter((s) => s.starter && s.player && s.key !== xi.key)
      .map((s) => s.player as PlayerPrediction);
    nextXi.push(on);
    const gk = nextXi.filter((p) => p.position === 'GK').length;
    const def = nextXi.filter((p) => p.position === 'DEF').length;
    const mid = nextXi.filter((p) => p.position === 'MID').length;
    const fwd = nextXi.filter((p) => p.position === 'FWD').length;
    return gk === 1 && !!FORMATIONS[`${def}-${mid}-${fwd}`];
  }

  subOn(xi: SquadSlot): void {
    const bench = this.editorSlot();
    if (!bench?.player || !xi.player || !this.canSub(bench, xi)) {
      return;
    }
    const onId = bench.player.player_id;
    const offId = xi.player.player_id;
    const starterIds = new Set(
      this.slots()
        .filter((s) => s.starter && s.player && s.player.player_id !== offId)
        .map((s) => s.player!.player_id),
    );
    starterIds.add(onId);
    this.fillSlotsFromPlayers(this.picked(), starterIds);
    this.error.set(null);
    this.persist();
    this.closeEditor();
    if (this.squadFull()) {
      this.runAnalysis(this.picksPayload());
    } else if (this.analysis()) {
      this.runAnalysis(this.picksPayload());
    }
  }

  makeCaptain(): void {
    const slot = this.editorSlot();
    const player = slot?.player;
    if (!player || !slot?.starter) {
      return;
    }
    const id = player.player_id;
    if (this.captainId() === id) {
      this.closeEditor();
      return;
    }
    const previousCap = this.captainId();
    if (this.viceId() === id) {
      this.viceId.set(previousCap);
    }
    this.captainId.set(id);
    this.persist();
    this.closeEditor();
    this.refreshAfterRoleChange();
  }

  makeVice(): void {
    const slot = this.editorSlot();
    const player = slot?.player;
    if (!player || !slot?.starter) {
      return;
    }
    const id = player.player_id;
    if (this.viceId() === id && this.captainId() !== id) {
      this.closeEditor();
      return;
    }
    const previousVice = this.viceId();
    if (this.captainId() === id) {
      this.captainId.set(previousVice);
    }
    this.viceId.set(id);
    this.persist();
    this.closeEditor();
    this.refreshAfterRoleChange();
  }

  private refreshAfterRoleChange(): void {
    if (this.picked().length >= 11) {
      this.runAnalysis(this.picksPayload());
    }
  }

  openSlot(slot: SquadSlot): void {
    this.editorSlot.set(slot);
    this.editorQuery.set('');
    this.editorMaxPrice.set(null);
    this.editorSort.set('xpts');
    this.editorInBudget.set(false);
    this.editorOpen.set(true);
  }

  closeEditor(): void {
    this.editorOpen.set(false);
    this.editorSlot.set(null);
    this.editorQuery.set('');
    this.editorMaxPrice.set(null);
    this.editorSort.set('xpts');
    this.editorInBudget.set(false);
  }

  setEditorMaxPrice(value: number | null): void {
    this.editorMaxPrice.set(this.editorMaxPrice() === value ? null : value);
  }

  canPlace(player: PlayerPrediction, slot: SquadSlot): string | null {
    const others = this.slots()
      .filter((s) => s.key !== slot.key && s.player)
      .map((s) => s.player as PlayerPrediction);
    if (others.some((p) => p.player_id === player.player_id)) {
      return 'Already in the squad';
    }
    if (player.position !== slot.position) {
      return `This shirt is for a ${slot.position}`;
    }
    if (others.filter((p) => p.position === player.position).length >= SLOTS[player.position]) {
      return `No ${player.position} slots left`;
    }
    if (others.filter((p) => p.team === player.team).length >= 3) {
      return `Already 3 from ${player.team}`;
    }
    const used = others.reduce((sum, p) => sum + p.price, 0);
    const cap = this.budgetCap() + 0.05;
    if (used + player.price > cap) {
      return `Over the £${this.budgetCap().toFixed(1)}m budget`;
    }
    return null;
  }

  placeOnSlot(player: PlayerPrediction): void {
    const slot = this.editorSlot();
    if (!slot) {
      return;
    }
    const blocked = this.canPlace(player, slot);
    if (blocked) {
      this.error.set(blocked);
      return;
    }
    const oldId = slot.player?.player_id ?? null;
    this.slots.update((list) =>
      list.map((s) => (s.key === slot.key ? { ...s, player } : s)),
    );
    if (oldId != null && this.captainId() === oldId) {
      this.captainId.set(player.player_id);
    }
    if (oldId != null && this.viceId() === oldId) {
      this.viceId.set(player.player_id);
    }
    this.error.set(null);
    this.persist();
    this.closeEditor();
    if (this.squadFull()) {
      this.runAnalysis(this.picksPayload());
    } else {
      this.analysis.set(null);
    }
  }

  clearSlot(): void {
    const slot = this.editorSlot();
    if (!slot?.player) {
      this.closeEditor();
      return;
    }
    const oldId = slot.player.player_id;
    this.slots.update((list) =>
      list.map((s) => (s.key === slot.key ? { ...s, player: null } : s)),
    );
    if (this.captainId() === oldId) {
      this.captainId.set(null);
    }
    if (this.viceId() === oldId) {
      this.viceId.set(null);
    }
    this.analysis.set(null);
    this.persist();
    this.closeEditor();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.editorOpen()) {
      this.closeEditor();
    }
  }

  analyzePicked(): void {
    if (!this.squadFull()) {
      this.error.set('Fill all 15 shirts (2 GK, 5 DEF, 5 MID, 3 FWD).');
      return;
    }
    this.runAnalysis(this.picksPayload());
  }

  setBudgetCap(raw: number): void {
    const value = Number.isFinite(raw) ? Math.max(0, Math.round(raw * 10) / 10) : 100;
    this.budgetCap.set(Math.max(this.budgetUsed(), value));
    this.persist();
  }

  loadFromEntry(): void {
    const id = Number(this.entryId());
    if (!Number.isInteger(id) || id <= 0) {
      this.error.set('Enter a numeric FPL team ID (from your FPL URL).');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.entryLoaded.set(false);
    this.api.analyzeSquadFromEntry(id).subscribe({
      next: (data) => {
        this.applyAnalysis(data, true);
        this.entryLoaded.set(true);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.errMessage(err, 'Could not load that FPL team.'));
      },
    });
  }

  onScreenshot(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      this.parsing.set(true);
      this.error.set(null);
      this.screenshotLoaded.set(false);
      this.api.parseSquadScreenshot(result, file.type || 'image/png').subscribe({
        next: (data) => {
          this.screenshotMatches.set(data.matches);
          this.screenshotNotes.set(data.vision_notes);
          this.parsing.set(false);
          this.applyScreenshotMatches(data.matches);
        },
        error: (err: HttpErrorResponse) => {
          this.parsing.set(false);
          this.error.set(this.errMessage(err, 'Could not read that screenshot.'));
        },
      });
    };
    reader.readAsDataURL(file);
    input.value = '';
  }

  isPitchCaptain(player: PlayerPrediction | null): boolean {
    return !!player && this.captainId() === player.player_id;
  }

  isPitchVice(player: PlayerPrediction | null): boolean {
    return !!player && this.viceId() === player.player_id && this.captainId() !== player.player_id;
  }

  severityClass(value: string): string {
    return `sev sev-${value}`;
  }

  ratingClass(label: string): string {
    return `rating-badge rating-${label.replace(/\s+/g, '-')}`;
  }

  private applyScreenshotMatches(matches: SquadScreenshotMatch[]): void {
    const mapped: PlayerPrediction[] = [];
    const picks: SquadPickIn[] = [];
    let cap: number | null = null;
    let vice: number | null = null;
    for (const row of matches) {
      if (!row.player) {
        continue;
      }
      const fromPool = this.pool().find((p) => p.player_id === row.player?.player_id);
      const player =
        fromPool ?? {
          player_id: row.player.player_id,
          fpl_element_id: row.player.fpl_element_id,
          web_name: row.player.web_name,
          full_name: row.player.full_name,
          team: '',
          position: row.player.position as Pos,
          price: row.player.price,
          gameweek_number: this.gwStore.selectedGameweek() ?? 0,
          expected_points: 0,
          baseline_last_gw: null,
          baseline_ep_next: null,
        };
      mapped.push(player);
      picks.push({
        player_id: player.player_id,
        fpl_element_id: player.fpl_element_id,
        is_captain: row.is_captain,
        is_vice: row.is_vice,
        starter: !row.on_bench,
      });
      if (row.is_captain) {
        cap = player.player_id;
      }
      if (row.is_vice) {
        vice = player.player_id;
      }
    }
    this.captainId.set(cap);
    this.viceId.set(vice);
    const starterIds = new Set(
      matches.filter((row) => row.player && !row.on_bench).map((row) => row.player!.player_id),
    );
    this.fillSlotsFromPlayers(mapped, starterIds);
    this.ensureBudgetCoversUsed();
    this.persist();
    if (mapped.length === 0) {
      this.screenshotLoaded.set(false);
      this.analysis.set(null);
      this.error.set('Could not match any players from that screenshot. Try a clearer pitch image.');
      return;
    }
    this.screenshotLoaded.set(true);
    if (mapped.length < 11) {
      this.analysis.set(null);
      this.error.set(
        `Only matched ${mapped.length} players. Tap empty shirts on the pitch to finish the 15.`,
      );
      return;
    }
    this.runAnalysis(picks, true);
  }

  private fillSlotsFromPlayers(players: PlayerPrediction[], starterIds?: Set<number>): void {
    const byPos: Record<Pos, PlayerPrediction[]> = { GK: [], DEF: [], MID: [], FWD: [] };
    const xi = starterIds
      ? players.filter((p) => starterIds.has(p.player_id))
      : players;
    const bench = starterIds ? players.filter((p) => !starterIds.has(p.player_id)) : [];
    for (const p of [...xi, ...bench]) {
      const pos = p.position as Pos;
      if (byPos[pos]) {
        byPos[pos].push(p);
      }
    }
    const code = this.formationFromCounts(
      xi.filter((p) => p.position === 'DEF').length,
      xi.filter((p) => p.position === 'MID').length,
      xi.filter((p) => p.position === 'FWD').length,
    );
    this.formation.set(code);
    this.slots.set(makeSlots(code, byPos));
  }

  private formationFromCounts(def: number, mid: number, fwd: number): string {
    const code = `${def}-${mid}-${fwd}`;
    return FORMATIONS[code] ? code : this.formation();
  }

  private applyAnalysis(data: SquadAnalysis, fromExternalLoad = false): void {
    this.analysis.set(data);
    const mapped: PlayerPrediction[] = data.players.map((p) => ({
      player_id: p.player_id,
      fpl_element_id: p.fpl_element_id,
      web_name: p.web_name,
      full_name: p.full_name,
      team: p.team,
      team_name: p.team_name,
      team_code: p.team_code,
      position: p.position,
      price: p.price,
      gameweek_number: data.gameweek,
      expected_points: p.expected_points,
      baseline_last_gw: p.last_gw ?? null,
      baseline_ep_next: null,
    }));
    const starterIds = new Set(data.players.filter((p) => p.starter).map((p) => p.player_id));
    this.fillSlotsFromPlayers(mapped, starterIds);
    const cap =
      data.players.find((p) => p.is_captain)?.player_id ?? data.captain?.player_id ?? null;
    let vice = data.players.find((p) => p.is_vice)?.player_id ?? data.vice?.player_id ?? null;
    if (vice === cap) {
      vice = data.vice && data.vice.player_id !== cap ? data.vice.player_id : null;
    }
    this.captainId.set(cap);
    this.viceId.set(vice);
    this.freeTransfers.set(data.free_transfers);
    if (fromExternalLoad) {
      const reported = Math.round(((data.squad_value ?? 0) + (data.bank ?? 0)) * 10) / 10;
      this.budgetCap.set(Math.max(this.budgetUsed(), reported > 0 ? reported : this.budgetUsed()));
    } else {
      this.ensureBudgetCoversUsed();
    }
    this.persist();
  }

  private runAnalysis(picks: SquadPickIn[], scrollToPitch = false): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.analyzeSquad(picks, Math.max(0, this.budgetLeft()), this.freeTransfers()).subscribe({
      next: (data) => {
        this.applyAnalysis(data);
        this.loading.set(false);
        if (scrollToPitch) {
          queueMicrotask(() =>
            document.querySelector('.pitch-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
          );
        }
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.errMessage(err, 'Analysis failed.'));
      },
    });
  }

  private picksPayload(): SquadPickIn[] {
    const cap = this.captainId();
    const vice = this.viceId();
    return this.slots()
      .filter((s) => s.player)
      .map((s) => ({
        player_id: s.player!.player_id,
        fpl_element_id: s.player!.fpl_element_id,
        is_captain: cap === s.player!.player_id,
        is_vice: vice === s.player!.player_id,
        starter: s.starter,
      }));
  }

  private loadPool(gw: number): void {
    this.loadingPool.set(true);
    this.api.getPlayerPredictions(gw).subscribe({
      next: (rows) => {
        this.pool.set(rows);
        this.restore(rows);
        this.loadingPool.set(false);
      },
      error: () => this.loadingPool.set(false),
    });
  }

  private persist(): void {
    const slotPlayers: Record<string, number | null> = {};
    for (const slot of this.slots()) {
      slotPlayers[slot.key] = slot.player?.player_id ?? null;
    }
    const payload: StoredPitch = {
      formation: this.formation(),
      slotPlayers,
      captainId: this.captainId(),
      viceId: this.viceId(),
      freeTransfers: this.freeTransfers(),
      budgetCap: this.budgetCap(),
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      /* ignore */
    }
  }

  private restore(pool: PlayerPrediction[]): void {
    if (this.picked().length) {
      return;
    }
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return;
      }
      const stored = JSON.parse(raw) as StoredPitch;
      const code = FORMATIONS[stored.formation] ? stored.formation : DEFAULT_FORMATION;
      const byId = new Map(pool.map((p) => [p.player_id, p]));
      const slots = makeSlots(code);
      this.formation.set(code);
      this.slots.set(
        slots.map((slot) => {
          const id = stored.slotPlayers?.[slot.key];
          return { ...slot, player: id != null ? byId.get(id) ?? null : null };
        }),
      );
      this.captainId.set(stored.captainId);
      this.viceId.set(stored.viceId);
      this.freeTransfers.set(stored.freeTransfers ?? 1);
      this.budgetCap.set(stored.budgetCap ?? 100);
      this.ensureBudgetCoversUsed();
    } catch {
      /* ignore */
    }
  }

  private ensureBudgetCoversUsed(): void {
    const used = this.budgetUsed();
    if (used > this.budgetCap()) {
      this.budgetCap.set(used);
    }
  }

  private errMessage(err: HttpErrorResponse, fallback: string): string {
    const detail = err.error?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
    return fallback;
  }
}
