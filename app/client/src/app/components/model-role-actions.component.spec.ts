import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ModelRoleActionsComponent } from './model-role-actions.component';

describe('ModelRoleActionsComponent', () => {
  let fixture: ComponentFixture<ModelRoleActionsComponent>;
  let component: ModelRoleActionsComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelRoleActionsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelRoleActionsComponent);
    component = fixture.componentInstance;
    component.model = {
      id: 'model',
      name: 'model',
      description: 'model',
      provider: 'openai',
      capabilities: ['chat'],
      supports_tools: false,
      supports_structured_output: false,
      supports_vision: false,
      supports_embeddings: false,
      tool_support_source: 'unknown',
      metadata: {},
    };
    component.settings = {
      active_provider_mode: 'cloud',
      chat_model_provider: 'openai',
      chat_model_name: 'model',
      parser_model_provider: 'openai',
      parser_model_name: 'parser',
      agent_model_provider: 'openai',
      agent_model_name: 'agent',
      ollama_url: 'http://localhost:11434',
      credentials: {},
    };
  });

  it('does not emit disabled agent assignments', () => {
    const spy = jasmine.createSpy('selectRole');
    component.selectRole.subscribe(spy);
    component.onSelect('agent');
    expect(spy).not.toHaveBeenCalled();
  });

  it('does not emit disabled parser assignments', () => {
    const spy = jasmine.createSpy('selectRole');
    component.selectRole.subscribe(spy);
    component.onSelect('parser');
    expect(spy).not.toHaveBeenCalled();
  });

  it('emits chat assignments for normal chat models', () => {
    const spy = jasmine.createSpy('selectRole');
    component.selectRole.subscribe(spy);
    component.onSelect('chat');
    expect(spy).toHaveBeenCalledWith('chat');
  });
});

