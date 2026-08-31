import { By } from '@angular/platform-browser';
import { TestBed } from '@angular/core/testing';

import { ApiClientService } from '../core/api-client.service';
import { GeospatialProviderAccountSetup, ModelSettingsResponse } from '../core/types';
import { AccessConfigurationsPageComponent } from './access-configurations-page.component';

const settings = {
  active_provider_mode: 'cloud' as const,
  agent_model_provider: '',
  agent_model_name: '',
  ollama_url: 'http://127.0.0.1:11434',
  openai_base_url: null,
  google_base_url: null,
  deepseek_base_url: null,
  credentials: {},
  credential_health: {},
};

const setup = (providerId: string, support: GeospatialProviderAccountSetup['automation']['support'] = 'agent_assisted'): GeospatialProviderAccountSetup => ({
  providerId,
  name: providerId === 'opentripmap' ? 'OpenTripMap Tourism POIs' : 'TomTom Traffic',
  requiresCredentials: true,
  authMode: 'api-key',
  docsUrl: 'https://example.test/docs',
  configured: false,
  instructions: ['Create an account.', 'Paste the key back into AEGIS.'],
  automation: {
    support,
    signupUrl: 'https://example.test/signup',
    developerPortalUrl: 'https://example.test/portal',
    docsUrl: 'https://example.test/docs',
    requiredFields: [],
    userActionNotes: ['Pause for CAPTCHA, login, billing, 2FA, and email verification.'],
    safetyNotes: ['AEGIS does not collect provider passwords, CAPTCHA responses, 2FA codes, recovery codes, or billing credentials.'],
    experimental: true,
    experimentalLabel: 'Experimental guided setup',
  },
  credentialStorageKey: providerId,
  credentialLabel: 'api_key',
  keyFormatHint: 'Paste generated API key',
  validationSupported: false,
});

describe('pages/access-configurations-page.component', () => {
  let fetchChatSettingsMock: jasmine.Spy;
  let fetchGeospatialProviderAccountSetupsMock: jasmine.Spy;
  let updateChatSettingsMock: jasmine.Spy;
  let apiClient: jasmine.SpyObj<ApiClientService>;

  beforeEach(async () => {
    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', [
      'fetchChatSettings',
      'fetchGeospatialProviderAccountSetups',
      'updateChatSettings',
    ]);
    fetchChatSettingsMock = jasmine.createSpy('fetchChatSettings').and.resolveTo(settings);
    fetchGeospatialProviderAccountSetupsMock = jasmine.createSpy('fetchGeospatialProviderAccountSetups').and.resolveTo({
      providers: [setup('tomtom'), setup('opentripmap', 'unsupported')],
    });
    updateChatSettingsMock = jasmine.createSpy('updateChatSettings').and.callFake(async (payload): Promise<ModelSettingsResponse> => ({
      ...settings,
      credentials: payload.credentials.tomtom?.api_key
        ? ({ tomtom: { api_key: true } } as Record<string, Record<string, boolean>>)
        : ({} as Record<string, Record<string, boolean>>),
      credential_health: payload.credentials.tomtom?.api_key
        ? { tomtom: { api_key: 'healthy' } }
        : {},
    }));

    apiClient.fetchChatSettings.and.callFake(() => fetchChatSettingsMock());
    apiClient.fetchGeospatialProviderAccountSetups.and.callFake(() => fetchGeospatialProviderAccountSetupsMock());
    apiClient.updateChatSettings.and.callFake((payload) => updateChatSettingsMock(payload));

    await TestBed.configureTestingModule({
      imports: [AccessConfigurationsPageComponent],
      providers: [{ provide: ApiClientService, useValue: apiClient }],
    }).compileComponents();
  });

  it('renders existing access page content and Get API triggers', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Manage optional API keys');
    expect(fixture.nativeElement.textContent).toContain('Default workflow uses free and open providers.');
    const triggers = fixture.debugElement.queryAll(By.css('.access-signup-trigger'));
    expect(triggers.length).toBeGreaterThanOrEqual(2);
    expect(fixture.nativeElement.textContent).toContain('Get API');
  });

  it('opens modal with experimental notice, portal link action, and safe guidance', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    fixture.componentInstance.openProviderSignup(fixture.componentInstance.getAccountSetupForProvider('tomtom'));
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Experimental guided setup');
    expect(text).toContain('Start guided setup');
    expect(text).toContain('CAPTCHA');
    expect(text).not.toContain('Password');
    expect(text).not.toContain('Recovery code');
  });

  it('saves and clears geospatial provider keys through settings API', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.drafts.tomtom = 'tomtom-key';
    await component.saveProvider('tomtom');
    fixture.detectChanges();
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.configured('tomtom')).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Provider access has not been validated.');

    await component.clearProvider('tomtom');
    fixture.detectChanges();
    expect(component.statusText).toContain('cleared');
    expect(fixture.nativeElement.textContent).toContain('Optional capabilities are disabled.');
  });

  it('saves a pasted key through the guided modal flow', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance;
    const tomtom = component.getAccountSetupForProvider('tomtom');
    expect(tomtom).toBeDefined();
    component.signupKeyInput = 'generated-key';
    await component.saveGeneratedCredential(tomtom!);

    expect(updateChatSettingsMock).toHaveBeenCalledWith(jasmine.objectContaining({
      credentials: { tomtom: { api_key: 'generated-key' } },
    }));
  });

  it('shows documentation-only behavior for unsupported providers', async () => {
    const fixture = TestBed.createComponent(AccessConfigurationsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.openProviderSignup(fixture.componentInstance.getAccountSetupForProvider('opentripmap'));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Documentation only');
    expect(fixture.nativeElement.textContent).toContain('Open documentation');
    expect(fixture.nativeElement.textContent).not.toContain('Generated API key');
  });
});
