import { TestBed } from '@angular/core/testing';

import * as Api from '../core/api';
import { AccessConfigurationsPageComponent } from './access-configurations-page.component';

const settings = {
  active_provider_mode: 'local' as const,
  chat_model_provider: 'ollama',
  chat_model_name: 'llama3.2',
  parser_model_provider: 'ollama',
  parser_model_name: 'llama3.2',
  agent_model_provider: 'ollama',
  agent_model_name: 'llama3.2',
  ollama_url: 'http://localhost:11434',
  openai_base_url: null,
  google_base_url: null,
  credentials: {},
  credential_health: {},
};

describe('pages/access-configurations-page.component', () => {
  beforeEach(async () => {
    spyOn(Api, 'fetchChatSettings').and.resolveTo(settings);
    spyOn(Api, 'updateChatSettings').and.callFake(async (payload) => ({
      ...settings,
      credentials: payload.credentials.geoapify?.api_key
        ? { geoapify: { api_key: true } }
        : {},
      credential_health: payload.credentials.geoapify?.api_key
        ? { geoapify: { api_key: 'healthy' } }
        : {},
    }));

    await TestBed.configureTestingModule({
      imports: [AccessConfigurationsPageComponent],
    }).compileComponents();
  });

  it('saves and clears geospatial provider keys through settings API', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance;
    component.drafts.geoapify = 'geo-key';
    await component.saveProvider('geoapify');
    expect(Api.updateChatSettings).toHaveBeenCalled();
    expect(component.configured('geoapify')).toBeTrue();

    await component.clearProvider('geoapify');
    expect(component.statusText).toContain('cleared');
  });
});
