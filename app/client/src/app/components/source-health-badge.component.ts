import { Component, Input } from '@angular/core';

import { LayerHealthStatus } from '../core/types';

@Component({
  selector: 'app-source-health-badge',
  standalone: true,
  templateUrl: './source-health-badge.component.html',
})
export class SourceHealthBadgeComponent {
  @Input() status: LayerHealthStatus | string | undefined = 'unknown';

  get normalizedStatus(): string {
    return String(this.status || 'unknown').toLowerCase();
  }

  get label(): string {
    return this.normalizedStatus.replace(/-/g, ' ');
  }
}
