import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';

import { ModelCardDescriptor } from '../core/types';
import { formatCompactTokenCount } from '../core/token-format';

@Component({
  selector: 'article[appModelRow]',
  standalone: true,
  imports: [],
  templateUrl: './model-row.component.html',
  styleUrl: './model-row.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
  host: {
    class: 'model-row',
    '[class.model-row--local]': 'isLocal',
    '[class.model-row--selected]': 'isSelected',
    '[class.model-row--disabled]': '!!disabledReason',
  },
})
export class ModelRowComponent {
  @Input({ required: true }) model!: ModelCardDescriptor;
  @Input({ required: true }) description = '';
  @Input() isLocal = false;
  @Input() requiresPull = false;
  @Input() isSelected = false;
  @Input() disabledReason: string | null = null;

  @Output() modelSelected = new EventEmitter<ModelCardDescriptor>();
  @Output() pullRequested = new EventEmitter<ModelCardDescriptor>();

  formatContextWindow(value: number | null | undefined): string {
    return formatCompactTokenCount(value);
  }

  get toolSupportLabel(): string {
    if (this.model.supports_tools === true) {
      return 'Tool support: detected';
    }
    return this.model.supports_tools === false ? 'Tool support: unavailable' : 'Tool support: not verified';
  }

  onRowSelected(): void {
    if (this.disabledReason) {
      return;
    }
    this.modelSelected.emit(this.model);
  }

  onPullRequested(): void {
    this.pullRequested.emit(this.model);
  }
}
