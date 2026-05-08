import { ComponentFixture, TestBed } from '@angular/core/testing';

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
    expect(fixture.nativeElement.textContent).toContain('Model');
    expect(fixture.nativeElement.textContent).toContain('Assigned');
  });

  it('renders provider and assigned metadata', () => {
    component.rows = [{ model: 'm2', provider: 'openai', local: false, assignedRoles: ['parser', 'agent'] }];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('openai');
    expect(fixture.nativeElement.textContent).toContain('parser, agent');
  });
});
