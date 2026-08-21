import { DecimalPipe } from '@angular/common';
import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';

import { ModelCardDescriptor } from '../core/types';

@Component({
  selector: 'article[appModelCard]',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './model-card.component.html',
  styleUrl: './model-card.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
  host: {
    class: 'model-card',
    '[class.model-card--local]': 'isLocal',
    '[class.model-card--selected]': 'isSelected',
    '[class.model-card--disabled]': '!!disabledReason',
  },
})
export class ModelCardComponent {
  @Input({ required: true }) model!: ModelCardDescriptor;
  @Input({ required: true }) description = '';
  @Input() isLocal = false;
  @Input() requiresPull = false;
  @Input() isSelected = false;
  @Input() disabledReason: string | null = null;

  @Output() modelSelected = new EventEmitter<ModelCardDescriptor>();
  @Output() pullRequested = new EventEmitter<ModelCardDescriptor>();

  onCardSelected(): void {
    if (this.disabledReason) {
      return;
    }
    this.modelSelected.emit(this.model);
  }

  onPullRequested(): void {
    this.pullRequested.emit(this.model);
  }
}
