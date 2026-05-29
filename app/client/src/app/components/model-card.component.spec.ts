import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelCardComponent } from './model-card.component';

describe('ModelCardComponent', () => {
  let fixture: ComponentFixture<ModelCardComponent>;
  let component: ModelCardComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelCardComponent);
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
    component.settings = {
      active_provider_mode: 'cloud',
      chat_model_provider: 'openai',
      chat_model_name: 'gpt-4.1-mini',
      parser_model_provider: 'openai',
      parser_model_name: 'gpt-4.1-mini',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1-mini',
      ollama_url: 'http://localhost:11434',
      credentials: {},
    };
    component.description = 'Model description';
  });

  it('renders model name, provider metadata, and description', () => {
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('gpt-4.1-mini');
    expect(text).toContain('Model description');
  });

  it('emits roleSelected when role actions emits', () => {
    const spy = jasmine.createSpy('roleSelected');
    component.roleSelected.subscribe(spy);
    component.onRoleSelected('chat');
    expect(spy).toHaveBeenCalledWith('chat');
  });

  it('emits pullRequested with the model', () => {
    const spy = jasmine.createSpy('pullRequested');
    component.pullRequested.subscribe(spy);
    component.onPullRequested();
    expect(spy).toHaveBeenCalledWith(component.model);
  });
});
