import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelRowComponent } from './model-row.component';

describe('ModelRowComponent', () => {
  let fixture: ComponentFixture<ModelRowComponent>;
  let component: ModelRowComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelRowComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelRowComponent);
    component = fixture.componentInstance;
    component.model = {
      id: 'gpt-4.1-mini',
      name: 'gpt-4.1-mini',
      description: 'cloud model',
      provider: 'openai',
      capabilities: [],
      supports_tools: true,
      supports_structured_output: true,
      supports_vision: false,
      supports_embeddings: false,
      tool_support_source: 'catalog',
      metadata: {},
    };
    component.description = 'Model description';
  });

  it('renders model name and description', () => {
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('gpt-4.1-mini');
    expect(text).toContain('Model description');
  });

  it('emits modelSelected when the selection button is clicked', () => {
    spyOn(component.modelSelected, 'emit');
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.model-row__select') as HTMLButtonElement;
    button.click();

    expect(component.modelSelected.emit).toHaveBeenCalledOnceWith(component.model);
  });

  it('does not emit when disabled', () => {
    spyOn(component.modelSelected, 'emit');
    component.disabledReason = 'Agent model requires structured output.';
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.model-row__select') as HTMLButtonElement;
    button.click();

    expect(component.modelSelected.emit).not.toHaveBeenCalled();
    expect(button.disabled).toBeTrue();
  });

  it('emits pull without selecting the row', () => {
    spyOn(component.pullRequested, 'emit');
    spyOn(component.modelSelected, 'emit');
    component.requiresPull = true;
    component.model.provider = 'ollama';
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.model-row__pull') as HTMLButtonElement;
    button.click();

    expect(component.pullRequested.emit).toHaveBeenCalledWith(component.model);
    expect(component.modelSelected.emit).not.toHaveBeenCalled();
  });

  it('keeps selection and pull controls as separate buttons', () => {
    component.requiresPull = true;
    component.model.provider = 'ollama';
    fixture.detectChanges();

    const selection = fixture.nativeElement.querySelector('.model-row__select') as HTMLButtonElement;
    const pull = fixture.nativeElement.querySelector('.model-row__pull') as HTMLButtonElement;

    expect(selection.contains(pull)).toBeFalse();
  });

  it('renders selected status', () => {
    component.isSelected = true;
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Selected');
  });

  it('explains why a selected model is disabled', () => {
    component.isSelected = true;
    component.disabledReason = 'This saved model is not present in the live provider catalog.';
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Selected');
    expect(text).toContain('not present in the live provider catalog');
  });
});
