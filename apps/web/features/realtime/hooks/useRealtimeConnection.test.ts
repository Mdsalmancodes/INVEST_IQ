import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../../store/auth-store";
import { useRealtimeConnection } from "./useRealtimeConnection";

/**
 * A minimal, deterministic fake of the browser WebSocket API — this
 * codebase's test conventions favor small purpose-built fakes over
 * pulling in a mocking library for something this narrow (mirrors
 * lib/jwt.ts's own "no new dependency for one operation" precedent).
 * Every constructed instance is captured in `instances` so tests can
 * reach in and simulate server-driven events (onopen/onmessage/onclose).
 */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  simulateClose(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

function makeToken(): string {
  const base64UrlEncode = (input: string) =>
    btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const exp = Math.floor(Date.now() / 1000) + 15 * 60;
  const body = base64UrlEncode(JSON.stringify({ sub: "u1", role: "user", exp }));
  return `${header}.${body}.fake-signature`;
}

function getSocketAt(index: number): FakeWebSocket {
  const socket = FakeWebSocket.instances[index];
  if (!socket) throw new Error(`Expected a FakeWebSocket instance at index ${index}`);
  return socket;
}

describe("useRealtimeConnection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reports offline when not authenticated and does not open a socket", () => {
    const { result } = renderHook(() => useRealtimeConnection());

    expect(result.current.connectionState).toBe("offline");
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("connects and reaches the connected state once the socket opens", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());

    expect(result.current.connectionState).toBe("connecting");

    act(() => getSocketAt(0).simulateOpen());

    expect(result.current.connectionState).toBe("connected");
  });

  it("builds the websocket url from the http base url and includes the token", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    renderHook(() => useRealtimeConnection());

    const url = getSocketAt(0).url;
    expect(url).toContain("/api/v1/realtime/ws?token=");
    expect(url.startsWith("ws://") || url.startsWith("wss://")).toBe(true);
  });

  it("delivers a message to a subscribed topic's listener", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    const listener = vi.fn();
    act(() => {
      result.current.subscribe("quote:AAPL", listener);
    });

    act(() => {
      getSocketAt(0).simulateMessage({
        type: "quote",
        topic: "quote:AAPL",
        data: { price: "150" },
      });
    });

    expect(listener).toHaveBeenCalledWith({
      type: "quote",
      topic: "quote:AAPL",
      data: { price: "150" },
    });
  });

  it("does not deliver a message to a listener subscribed to a different topic", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    const listener = vi.fn();
    act(() => {
      result.current.subscribe("quote:AAPL", listener);
    });
    act(() => {
      getSocketAt(0).simulateMessage({ type: "quote", topic: "quote:MSFT" });
    });

    expect(listener).not.toHaveBeenCalled();
  });

  it("sends a subscribe action to the server when a new topic is subscribed to", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    act(() => {
      result.current.subscribe("portfolio:p1", vi.fn());
    });

    const sent = getSocketAt(0).sent.map((s) => JSON.parse(s));
    expect(sent).toContainEqual({ action: "subscribe", topics: ["portfolio:p1"] });
  });

  it("sends an unsubscribe action only once the last listener for a topic is removed", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    let unsubscribeA: () => void;
    let unsubscribeB: () => void;
    act(() => {
      unsubscribeA = result.current.subscribe("ai:AAPL", vi.fn());
      unsubscribeB = result.current.subscribe("ai:AAPL", vi.fn());
    });

    act(() => unsubscribeA());
    let sent = getSocketAt(0).sent.map((s) => JSON.parse(s));
    expect(sent).not.toContainEqual({ action: "unsubscribe", topics: ["ai:AAPL"] });

    act(() => unsubscribeB());
    sent = getSocketAt(0).sent.map((s) => JSON.parse(s));
    expect(sent).toContainEqual({ action: "unsubscribe", topics: ["ai:AAPL"] });
  });

  it("moves to reconnecting state after the socket closes post-connection", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    act(() => getSocketAt(0).simulateClose());

    expect(result.current.connectionState).toBe("reconnecting");
  });

  it("re-subscribes to every previously-subscribed topic after a reconnect", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    act(() => {
      result.current.subscribe("quote:AAPL", vi.fn());
    });

    act(() => getSocketAt(0).simulateClose());
    act(() => vi.advanceTimersByTime(1_000)); // INITIAL_BACKOFF_MS

    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => getSocketAt(1).simulateOpen());

    const sentOnSecondSocket = getSocketAt(1).sent.map((s) => JSON.parse(s));
    expect(sentOnSecondSocket).toContainEqual({ action: "subscribe", topics: ["quote:AAPL"] });
  });

  it("closes the socket and reports offline when the user logs out", () => {
    act(() => useAuthStore.getState().setAccessToken(makeToken()));
    const { result } = renderHook(() => useRealtimeConnection());
    act(() => getSocketAt(0).simulateOpen());

    act(() => useAuthStore.getState().clearSession());

    expect(result.current.connectionState).toBe("offline");
  });
});
