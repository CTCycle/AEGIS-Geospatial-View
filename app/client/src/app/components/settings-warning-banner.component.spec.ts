import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SettingsWarningBannerComponent } from './settings-warning-banner.component';

@Component({
  standalone: true,
  imports: [SettingsWarningBannerComponent],
  template: `
    <section
      appSettingsWarning
      class="settings-page__warning"
      badge="Needs attention"
      title="Selected local model unavailable."
      message="Pull the model before using the workspace."
    ></section>
  `,
})
class TestHostComponent {}

describe('components/settings-warning-banner.component', () => {
  let fixture: ComponentFixture<TestHostComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHostComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(TestHostComponent);
    fixture.detectChanges();
  });

  it('keeps the section host while rendering the typed warning content', () => {
    const warning = fixture.nativeElement.querySelector('section.settings-page__warning') as HTMLElement;
    expect(warning).not.toBeNull();
    expect(warning.getAttribute('role')).toBeNull();
    expect(warning.querySelector('.settings-page__warning-badge')?.textContent?.trim()).toBe('Needs attention');
    expect(warning.querySelector('.settings-page__warning-copy strong')?.textContent?.trim())
      .toBe('Selected local model unavailable.');
    expect(warning.textContent).toContain('Pull the model before using the workspace.');
  });
});
