import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MODEL_ROLES, ModelRole } from '../core/model-selection';
import { ModelStatsPanelComponent } from './model-stats-panel.component';

describe('ModelStatsPanelComponent', () => {
  let fixture: ComponentFixture<ModelStatsPanelComponent>;
  let component: ModelStatsPanelComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelStatsPanelComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelStatsPanelComponent);
    component = fixture.componentInstance;
  });

  it('renders rows', () => {
    component.rows = [{ model: 'm1', provider: 'ollama', local: true, assignedRoles: ['chat'] }];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('m1');
    expect(fixture.nativeElement.textContent).toContain('ollama');
  });

  it('renders table headers even without rows', () => {
    component.rows = [];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Duty');
    expect(fixture.nativeElement.textContent).toContain('Status');
  });

  it('renders provider and assigned metadata', () => {
    component.rows = [{ model: 'm2', provider: 'openai', local: false, assignedRoles: ['parser', 'agent'] }];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('openai');
    expect(fixture.nativeElement.textContent).toContain('Assigned');
  });

  it('maps lowercase assigned roles to duty rows', () => {
    component.rows = [{ model: 'qwen2.5:7b', provider: 'ollama', local: true, assignedRoles: ['parser'] }];
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('qwen2.5:7b');
    expect(text).toContain('ollama');
    expect(text).toContain('Yes');
  });

  it('renders duty boundary explainer content', () => {
    component.rows = [];
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).not.toContain('Duty boundaries');
    expect(text).toContain('Parser');
    expect(text).toContain('Agent');
    expect(fixture.nativeElement.querySelector('.settings-page__model-boundaries img')).toBeNull();
  });

  it('uses model role values for assigned roles', () => {
    const row = { model: 'm3', provider: 'openai', local: false, assignedRoles: ['chat'] as ModelRole[] };
    component.rows = [row];
    expect(row.assignedRoles.every((role) => MODEL_ROLES.includes(role))).toBeTrue();
  });
});
