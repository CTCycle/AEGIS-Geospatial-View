import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import * as Api from '../core/api';
import { AppStateStoreService } from '../core/app-state-store.service';
import { defaultAppState } from '../core/app-state';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { GeospatialPageComponent } from './geospatial-page.component';

describe('pages/geospatial-page.component', () => {
  let router: Router;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;

  beforeEach(async () => {
    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', [
      'getChatPage',
      'updateChatPage',
      'resetChatPage',
    ]);
    store.getChatPage.and.returnValue(defaultAppState().chatPage);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', [
      'toUserFacingError',
    ]);
    errors.toUserFacingError.and.returnValue('fallback error');

    await TestBed.configureTestingModule({
      imports: [GeospatialPageComponent],
      providers: [
        provideRouter([]),
        { provide: AppStateStoreService, useValue: store },
        { provide: UserFacingErrorService, useValue: errors },
      ],
    }).compileComponents();
    router = TestBed.inject(Router);
  });

  it('loads initial persisted state', () => {
    const seeded = defaultAppState().chatPage;
    seeded.chatPanel.composerDraft = 'seed draft';
    seeded.chatPanel.messages = [{ role: 'user', content: 'hello' }];
    store.getChatPage.and.returnValue(seeded);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.composerDraft).toBe('seed draft');
    expect(fixture.componentInstance.messages.length).toBe(1);
  });

  it('sendMessage happy path updates status and appends assistant', async () => {
    spyOn(Api, 'sendChatTurn').and.resolveTo({
      session_id: 42,
      assistant_message: 'Search executed successfully.',
      map_session: null,
      follow_up_required: false,
    });
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Complete');
    expect(component.messages.at(-1)?.content).toContain('Search executed successfully.');
  });

  it('request nonce blocks stale response overwrite', async () => {
    let resolveTurn: (value: unknown) => void;
    const pending = new Promise((resolve) => { resolveTurn = resolve as (value: unknown) => void; });
    spyOn(Api, 'sendChatTurn').and.returnValue(pending as Promise<unknown>);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'first';
    const sendPromise = component.sendMessage();
    component.startNewChat();
    resolveTurn!({
      session_id: 7,
      assistant_message: 'late response',
      map_session: null,
      follow_up_required: false,
    } as unknown as never);
    await sendPromise;
    expect(component.messages.find((entry) => entry.content === 'late response')).toBeUndefined();
  });

  it('error path adds fallback assistant message and Failed status', async () => {
    spyOn(Api, 'sendChatTurn').and.rejectWith(new Error('boom'));
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.composerDraft = 'show map';
    await component.sendMessage();
    expect(component.status).toBe('Failed');
    expect(component.messages.at(-1)?.content).toBe('fallback error');
  });

  it('startNewChat clears session and map/chat state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.sessionId = 7;
    component.messages = [{ role: 'assistant', content: 'x' }];
    component.composerDraft = 'draft';
    component.payload = { map_session: { overlays: [] } };
    component.startNewChat();
    expect(component.sessionId).toBeUndefined();
    expect(component.messages.length).toBe(0);
    expect(component.composerDraft).toBe('');
    expect(component.payload).toBeUndefined();
    expect(store.resetChatPage).toHaveBeenCalled();
  });

  it('overlay state updates are persisted through sync', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.onOverlayStateChange({
      overlayVisibility: { overlay_a: false },
      overlayOpacity: { overlay_a: 0.3 },
    });
    expect(component.mapState.overlayVisibility['overlay_a']).toBeFalse();
    expect(store.updateChatPage).toHaveBeenCalled();
  });

  it('navigateToSettings syncs state and routes to settings', () => {
    const navigateSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    fixture.componentInstance.navigateToSettings();
    expect(store.updateChatPage).toHaveBeenCalled();
    expect(navigateSpy).toHaveBeenCalledWith('/settings');
  });

  it('transcript scroll persistence updates state', () => {
    const fixture = TestBed.createComponent(GeospatialPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.onTranscriptScroll({ target: { scrollTop: 88 } } as unknown as Event);
    expect(component.transcriptScrollTop).toBe(88);
    expect(store.updateChatPage).toHaveBeenCalled();
  });
});
