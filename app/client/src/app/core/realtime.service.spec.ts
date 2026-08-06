import { RealtimeService } from './realtime.service';

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly sent: string[] = [];
  readyState = FakeWebSocket.CONNECTING;
  onopen?: () => void;
  onmessage?: (event: MessageEvent<unknown>) => void;
  onerror?: () => void;
  onclose?: (event: CloseEvent) => void;
  closeCode?: number;
  closeReason?: string;

  constructor(readonly url: string, readonly protocol: string) {}

  send(value: string): void {
    this.sent.push(value);
  }

  close(code = 1000, reason = ''): void {
    this.closeCode = code;
    this.closeReason = reason;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  receive(value: unknown): void {
    this.onmessage?.({ data: value } as MessageEvent<unknown>);
  }
}

describe('RealtimeService', () => {
  let service: RealtimeService;
  let sockets: FakeWebSocket[];
  let originalWebSocket: typeof WebSocket;
  let clockInstalled = false;

  beforeEach(() => {
    service = new RealtimeService();
    sockets = [];
    originalWebSocket = window.WebSocket;
    class RecordingWebSocket extends FakeWebSocket {
      static override readonly OPEN = FakeWebSocket.OPEN;
      static override readonly CLOSED = FakeWebSocket.CLOSED;

      constructor(url: string | URL, protocols?: string | string[]) {
        super(url.toString(), Array.isArray(protocols) ? protocols[0] ?? '' : protocols ?? '');
        sockets.push(this);
      }
    }
    (window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      RecordingWebSocket as unknown as typeof WebSocket;
  });

  afterEach(() => {
    service.disconnect({ discardPending: true });
    if (clockInstalled) {
      jasmine.clock().uninstall();
      clockInstalled = false;
    }
    window.WebSocket = originalWebSocket;
  });

  it('sends each pending command once per socket generation', () => {
    service.connect('conv-1');
    sockets[0].open();
    service.sendRunStart('hello', 'request-1');
    service.sendRunSteer('run-1', 'refine', 'steer-1');

    const commands = sockets[0].sent
      .map((value) => JSON.parse(value) as { type: string });
    expect(commands.filter((command) => command.type === 'run.start').length).toBe(1);
    expect(commands.filter((command) => command.type === 'run.steer').length).toBe(1);
  });

  it('replays an unacknowledged command after reconnect', () => {
    jasmine.clock().install();
    clockInstalled = true;
    spyOn(Math, 'random').and.returnValue(0);
    service.connect('conv-1');
    sockets[0].open();
    service.sendRunStart('hello', 'request-1');
    sockets[0].close(1006, 'network');
    jasmine.clock().tick(500);
    expect(sockets.length).toBe(2);
    sockets[1].open();
    const resent = sockets[1].sent
      .map((value) => JSON.parse(value) as { type: string })
      .filter((command) => command.type === 'run.start');
    expect(resent.length).toBe(1);
    jasmine.clock().uninstall();
    clockInstalled = false;
  });

  it('does not carry pending commands across conversations', () => {
    service.connect('conv-1');
    sockets[0].open();
    service.sendRunStart('first conversation', 'request-1');

    service.connect('conv-2');
    expect(sockets[0].closeCode).toBe(1000);
    sockets[1].open();
    service.sendRunStart('second conversation', 'request-2');

    const secondConversationCommands = sockets[1].sent
      .map((value) => JSON.parse(value) as { type: string; payload: { message?: string } });
    expect(secondConversationCommands.filter(
      (command) => command.type === 'run.start' && command.payload.message === 'first conversation',
    ).length).toBe(0);
    expect(secondConversationCommands.filter(
      (command) => command.type === 'run.start' && command.payload.message === 'second conversation',
    ).length).toBe(1);
  });

  it('does not replay a command rejected by the server', () => {
    jasmine.clock().install();
    clockInstalled = true;
    spyOn(Math, 'random').and.returnValue(0);
    service.connect('conv-1');
    sockets[0].open();
    service.sendRunStart('hello', 'request-1');
    const start = JSON.parse(sockets[0].sent.at(-1) ?? '{}') as { message_id?: string };
    sockets[0].receive(JSON.stringify({
      protocol_version: 1,
      type: 'protocol.error',
      conversation_id: 'conv-1',
      correlation_id: start.message_id,
      payload: { code: 'run_conflict', fatal: false },
    }));
    sockets[0].close(1006, 'network');
    jasmine.clock().tick(500);
    sockets[1].open();
    const resent = sockets[1].sent
      .map((value) => JSON.parse(value) as { type: string })
      .filter((command) => command.type === 'run.start');
    expect(resent.length).toBe(0);
    jasmine.clock().uninstall();
    clockInstalled = false;
  });

  it('closes the socket when a server envelope cannot be validated', () => {
    service.connect('conv-1');
    sockets[0].open();
    sockets[0].receive('{not-json');
    expect(sockets[0].closeCode).toBe(1002);
    expect(service.connectionState).toBe('closed');
  });

  it('detects a stale connection without incoming heartbeats', () => {
    jasmine.clock().install();
    clockInstalled = true;
    service.connect('conv-1');
    sockets[0].open();
    service['lastIncomingAt'] = Date.now() - 50_000;
    jasmine.clock().tick(5_000);
    expect(sockets[0].closeCode).toBe(4408);
    jasmine.clock().uninstall();
    clockInstalled = false;
  });
});
