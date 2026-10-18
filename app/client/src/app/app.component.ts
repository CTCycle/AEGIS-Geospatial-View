import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
} from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Subscription } from 'rxjs';

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

  private routerEventsSubscription?: Subscription;

  constructor(private readonly router: Router) {}

  private readonly resizeHandler = (): void => {
    this.updateViewportSupport();
  };

  ngOnInit(): void {
    this.updateViewportSupport();
    this.updateDocumentMetadata();
    this.routerEventsSubscription = this.router.events.subscribe((event) => {
      if (event instanceof NavigationEnd) {
        this.updateDocumentMetadata();
      }
    });
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', this.resizeHandler);
    }
  }

  ngOnDestroy(): void {
    this.routerEventsSubscription?.unsubscribe();
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', this.resizeHandler);
    }
  }

  private updateDocumentMetadata(): void {
    if (typeof document === 'undefined') {
      return;
    }
    const route = this.router.routerState.root.firstChild;
    const title = typeof route?.snapshot.data['title'] === 'string'
      ? route.snapshot.data['title']
      : 'AEGIS | Search workspace';
    const description = typeof route?.snapshot.data['description'] === 'string'
      ? route.snapshot.data['description']
      : 'Location-aware geospatial search and inspection workspace.';
    document.title = title;
    let descriptionElement = document.head.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!descriptionElement) {
      descriptionElement = document.createElement('meta');
      descriptionElement.name = 'description';
      document.head.appendChild(descriptionElement);
    }
    descriptionElement.content = description;
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
