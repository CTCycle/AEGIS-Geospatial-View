import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class UserFacingErrorService {
  private static readonly LOW_LEVEL_CONNECTION_PATTERN =
    /winerror\s*10061|connection refused|econnrefused|urlopen error|failed to establish a new connection|failed to fetch|network request failed|networkerror|err_aborted|request interrupted|aborterror/i;

  toUserFacingError(error: unknown, fallback: string): string {
    const message = this.toErrorText(error);
    return this.isLowLevelConnectionError(message) ? fallback : message;
  }

  normalizeDisplayText(text: string, fallback = 'Could not complete this action right now.'): string {
    return this.isLowLevelConnectionError(text) ? fallback : text;
  }

  isLowLevelConnectionError(message: string): boolean {
    return UserFacingErrorService.LOW_LEVEL_CONNECTION_PATTERN.test(message);
  }

  private toErrorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
}
