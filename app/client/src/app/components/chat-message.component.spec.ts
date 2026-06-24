import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ChatMessageComponent } from './chat-message.component';

describe('ChatMessageComponent', () => {
  let fixture: ComponentFixture<ChatMessageComponent>;
  let component: ChatMessageComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ChatMessageComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(ChatMessageComponent);
    component = fixture.componentInstance;
  });

  it('renders assistant Markdown as sanitized HTML', () => {
    component.message = {
      role: 'assistant',
      content: [
        '## Result',
        '',
        '**Rain:** moderate',
        '',
        '- Current layer',
        '- Verified source',
        '',
        '[Details](https://example.com)',
        '',
        '`precipitation`',
        '',
        '<img src=x onerror="alert(1)">',
      ].join('\n'),
    };

    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h2')?.textContent).toBe('Result');
    expect(element.querySelector('strong')?.textContent).toBe('Rain:');
    expect(element.querySelectorAll('li').length).toBe(2);
    expect(element.querySelector('a')?.getAttribute('href')).toBe('https://example.com');
    expect(element.querySelector('code')?.textContent).toBe('precipitation');
    expect(element.querySelector('img')?.hasAttribute('onerror')).toBeFalse();
  });

  it('keeps user Markdown syntax as escaped plain text', () => {
    component.message = {
      role: 'user',
      content: '**not bold** <script>alert(1)</script>',
    };

    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('strong')).toBeNull();
    expect(element.querySelector('script')).toBeNull();
    expect(element.querySelector('p')?.textContent).toBe(
      '**not bold** <script>alert(1)</script>',
    );
  });
});
