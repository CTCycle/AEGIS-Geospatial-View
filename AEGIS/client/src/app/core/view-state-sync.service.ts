import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ViewStateSyncService {
  restoreWindowScroll(scrollY: number): void {
    if (typeof window === 'undefined') {
      return;
    }
    window.scrollTo({ top: scrollY, behavior: 'auto' });
  }

  captureWindowScroll(): number {
    if (typeof window === 'undefined') {
      return 0;
    }
    return window.scrollY;
  }

  restoreElementScroll(element: HTMLElement | undefined, scrollTop: number): void {
    if (!element) {
      return;
    }
    element.scrollTop = scrollTop;
  }

  captureElementScroll(element: HTMLElement | undefined, fallback: number): number {
    if (!element) {
      return fallback;
    }
    return element.scrollTop;
  }
}
