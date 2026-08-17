import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

@Component({
  selector: 'section[appSettingsWarning]',
  standalone: true,
  template: `
    <span class="settings-page__warning-badge">{{ badge }}</span>
    <span class="settings-page__warning-copy">
      <strong>{{ title }}</strong>
      {{ message }}
    </span>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class SettingsWarningBannerComponent {
  @Input({ required: true }) badge!: string;
  @Input({ required: true }) title!: string;
  @Input({ required: true }) message!: string;
}
