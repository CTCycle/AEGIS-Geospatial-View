export class ApiRequestError extends Error {
  detail?: unknown;
  status?: number;
  raw?: unknown;

  constructor(message: string, options?: { detail?: unknown; status?: number; raw?: unknown }) {
    super(message);
    this.name = 'ApiRequestError';
    this.detail = options?.detail;
    this.status = options?.status;
    this.raw = options?.raw;
  }
}

export class ApiContractError extends ApiRequestError {
  constructor(endpoint: string, detail: string, raw?: unknown) {
    super(`Invalid ${endpoint} API response: ${detail}`, { raw });
    this.name = 'ApiContractError';
  }
}
