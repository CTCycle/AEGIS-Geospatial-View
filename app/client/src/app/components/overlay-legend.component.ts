import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { OverlayLegend } from '../core/types';
import { legendGradient, legendTicks } from './overlay-legend';

/** Compact colour scale (continuous bar or categorical swatches) for one overlay legend. */
@Component({
  selector: 'app-overlay-legend',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './overlay-legend.component.css',
  template: `
    @if (caption()) {
      <p class="overlay-legend__caption">{{ caption() }}</p>
    }
    @if (legend().kind === 'continuous') {
      <div class="overlay-legend__bar" role="img" [attr.aria-label]="rangeLabel()" [style.background]="gradient()"></div>
      <div class="overlay-legend__ticks" aria-hidden="true">
        @for (tick of ticks(); track tick.position) {
          <span [style.left.%]="tick.position" [style.transform]="'translateX(-' + tick.position + '%)'">{{ tick.label }}</span>
        }
      </div>
    } @else {
      <ul class="overlay-legend__categories">
        @for (entry of legend().entries; track $index) {
          <li><span class="overlay-legend__swatch" [style.background]="entry.color"></span>{{ entry.label }}</li>
        }
      </ul>
    }
    @if (readout()) {
      <p class="overlay-legend__readout">{{ readout() }}</p>
    }
  `,
})
export class OverlayLegendComponent {
  readonly legend = input.required<OverlayLegend>();
  readonly layerLabel = input('');
  readonly readout = input<string | null>(null);

  readonly gradient = computed(() => legendGradient(this.legend().entries));
  readonly ticks = computed(() => legendTicks(this.legend().entries, this.legend().units));
  readonly caption = computed(() => {
    const title = this.legend().title.trim();
    return title.toLowerCase() === this.layerLabel().trim().toLowerCase() ? '' : title;
  });
  readonly rangeLabel = computed(() => {
    const ticks = this.ticks();
    const range = ticks.length > 1 ? `${ticks[0].label} to ${ticks[ticks.length - 1].label}` : ticks[0]?.label || '';
    return `${this.legend().title} colour scale, ${range}`;
  });
}
