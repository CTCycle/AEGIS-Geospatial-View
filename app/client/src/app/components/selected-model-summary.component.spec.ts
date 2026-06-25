import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SelectedModelSummaryComponent } from './selected-model-summary.component';

describe('SelectedModelSummaryComponent', () => {
  let fixture: ComponentFixture<SelectedModelSummaryComponent>;
  let component: SelectedModelSummaryComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SelectedModelSummaryComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(SelectedModelSummaryComponent);
    component = fixture.componentInstance;
  });

  it('renders empty state', () => {
    component.summary = null;
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('No agent model selected');
  });

  it('renders loading state', () => {
    component.isLoading = true;
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Loading selected model');
  });

  it('renders selected model details', () => {
    component.summary = {
      model: 'gpt-4.1',
      provider: 'openai',
      runtimeMode: 'cloud',
      installedLocally: false,
      supportsTools: true,
      supportsStructuredOutput: true,
      supportsVision: false,
      supportsEmbeddings: false,
      toolSupportSource: 'catalog',
      capabilities: ['tools', 'json'],
    };
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('gpt-4.1');
    expect(text).toContain('openai');
    expect(text).toContain('Structured output');
    expect(text).toContain('tools, json');
  });
});
