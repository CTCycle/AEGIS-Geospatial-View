import { TestBed } from '@angular/core/testing';

import * as Api from '../core/api';
import { ModelSettingsResponse } from '../core/types';
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
  let fetchChatSettingsMock: jasmine.Spy;
  let updateChatSettingsMock: jasmine.Spy;

  beforeEach(async () => {
    fetchChatSettingsMock = jasmine.createSpy('fetchChatSettings').and.resolveTo(settings);
    updateChatSettingsMock = jasmine.createSpy('updateChatSettings').and.callFake(async (payload): Promise<ModelSettingsResponse> => ({
      ...settings,
      credentials: payload.credentials.geoapify?.api_key
        ? ({ geoapify: { api_key: true } } as Record<string, Record<string, boolean>>)
        : ({} as Record<string, Record<string, boolean>>),
      credential_health: payload.credentials.geoapify?.api_key
        ? { geoapify: { api_key: 'healthy' } }
        : {},
    }));

    spyOnProperty(Api, 'fetchChatSettings', 'get').and.returnValue(fetchChatSettingsMock);
    spyOnProperty(Api, 'updateChatSettings', 'get').and.returnValue(updateChatSettingsMock);

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
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.configured('geoapify')).toBeTrue();

    await component.clearProvider('geoapify');
    expect(component.statusText).toContain('cleared');
  });
});