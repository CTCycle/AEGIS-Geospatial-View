import { TestBed } from '@angular/core/testing';

import { ApiClientService } from '../core/api-client.service';
import { ModelSettingsResponse, ProviderAccountSetup } from '../core/types';
import { AccessConfigurationsPageComponent } from './access-configurations-page.component';

const settings: ModelSettingsResponse = {
  active_provider_mode: 'local',
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

const accountSetups: ProviderAccountSetup[] = [
  {
    provider_id: 'geoapify',
    mode: 'manual',
    automation_supported: false,
    automation_reason: 'Manual provider setup is required.',
    account_url: 'https://www.geoapify.com',
    dashboard_url: 'https://myprojects.geoapify.com',
    documentation_url: 'https://www.geoapify.com/get-started-with-maps-api/',
    credential_fields: [{ name: 'api_key', label: 'API key', secret: true, required: true }],
    steps: [{ id: 'create_key', title: 'Create an API key', description: 'Create a key.' }],
  },
  {
    provider_id: 'openmeteo',
    mode: 'not_required',
    automation_supported: false,
    credential_fields: [],
    steps: [],
  },
];

describe('pages/access-configurations-page.component', () => {
  let apiClient: jasmine.SpyObj<ApiClientService>;

  beforeEach(async () => {
    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', [
      'fetchChatSettings',
      'updateChatSettings',
      'getProviderAccountSetups',
      'getProviderAccountSetup',
      'validateProviderCredentials',
    ]);
    apiClient.fetchChatSettings.and.resolveTo(settings);
    apiClient.getProviderAccountSetups.and.resolveTo(accountSetups);
    apiClient.getProviderAccountSetup.and.resolveTo(accountSetups[0]);
    apiClient.validateProviderCredentials.and.resolveTo({
      provider_id: 'geoapify',
      valid: true,
      status: 'valid',
      message: 'accepted',
    });
    apiClient.updateChatSettings.and.callFake(async (payload): Promise<ModelSettingsResponse> => ({
      ...settings,
      credentials: payload.credentials.geoapify?.api_key ? { geoapify: { api_key: true } } : {},
      credential_health: payload.credentials.geoapify?.api_key ? { geoapify: { api_key: 'healthy' } } : {},
    }));

    await TestBed.configureTestingModule({
      imports: [AccessConfigurationsPageComponent],
      providers: [{ provide: ApiClientService, useValue: apiClient }],
    }).compileComponents();
  });

  it('loads account setups on initialization', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(apiClient.getProviderAccountSetups).toHaveBeenCalled();
    expect(fixture.componentInstance.accountSetups.length).toBe(2);
  });

  it('renders credential and no-key providers', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Geoapify');
    expect(text).toContain('Openmeteo');
    expect(text).toContain('No access key required');
  });

  it('selecting a provider opens the wizard and renders secret fields', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.selectProvider('geoapify');
    fixture.componentInstance.goToStep(4);
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input[type="password"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.type).toBe('password');
  });

  it('validates credentials and displays success', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.selectProvider('geoapify');
    fixture.componentInstance.credentialForm.controls.api_key.setValue('key');
    await fixture.componentInstance.validateCredentials();

    expect(apiClient.validateProviderCredentials).toHaveBeenCalledWith('geoapify', { api_key: 'key' });
    expect(fixture.componentInstance.validationResult?.valid).toBeTrue();
  });

  it('displays validation failure and only saves after success', async () => {
    apiClient.validateProviderCredentials.and.resolveTo({
      provider_id: 'geoapify',
      valid: false,
      status: 'invalid',
      message: 'rejected',
    });
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.selectProvider('geoapify');
    fixture.componentInstance.credentialForm.controls.api_key.setValue('key');
    await fixture.componentInstance.validateCredentials();
    await fixture.componentInstance.saveCredentials();

    expect(fixture.componentInstance.validationResult?.message).toBe('rejected');
    expect(apiClient.updateChatSettings).not.toHaveBeenCalled();
  });

  it('saves credentials after validation success and shows automation notice', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.selectProvider('geoapify');
    fixture.componentInstance.credentialForm.controls.api_key.setValue('key');
    await fixture.componentInstance.validateCredentials();
    await fixture.componentInstance.saveCredentials();
    fixture.detectChanges();

    expect(apiClient.updateChatSettings).toHaveBeenCalled();
    expect((fixture.nativeElement.textContent as string)).toContain('Manual provider setup is required.');
  });

  it('does not render username or password portal controls', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.goToStep(4);
    fixture.detectChanges();

    const inputs = Array.from(fixture.nativeElement.querySelectorAll('input')) as HTMLInputElement[];
    const names = inputs.map((input) => `${input.name} ${input.placeholder}`.toLowerCase()).join(' ');
    expect(names).not.toContain('username');
    expect(names).not.toContain('password');
  });
});
