import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AppComponent } from './app.component';

describe('app.component', () => {
  it('renders Operations Bar navigation links', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;

    expect(text).toContain('AEGIS');
    expect(text).toContain('Search');
    expect(text).toContain('Geodata');
    expect(text).toContain('Access');
    expect(text).toContain('Model Settings');
  });
});
