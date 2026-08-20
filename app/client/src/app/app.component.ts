import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
} from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.component.css',
})
export class AppComponent implements OnInit, OnDestroy {
  readonly minimumDesktopViewportWidth = 1024;
  isDesktopViewport = true;

  @ViewChild('desktopViewportGate') private desktopViewportGate?: ElementRef<HTMLElement>;

  private readonly resizeHandler = (): void => {
    this.updateViewportSupport();
  };

  ngOnInit(): void {
    this.updateViewportSupport();
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', this.resizeHandler);
    }
  }

  ngOnDestroy(): void {
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', this.resizeHandler);
    }
  }

  private updateViewportSupport(): void {
    if (typeof window === 'undefined') {
      this.isDesktopViewport = true;
      return;
    }

    const wasDesktopViewport = this.isDesktopViewport;
    this.isDesktopViewport = window.innerWidth >= this.minimumDesktopViewportWidth;
    if (wasDesktopViewport && !this.isDesktopViewport) {
      window.setTimeout(() => {
        if (!this.isDesktopViewport) {
          this.desktopViewportGate?.nativeElement.focus();
        }
      });
    }
  }
}
