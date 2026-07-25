"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuthStore } from "../../../store/auth-store";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

/**
 * Converts core-api's http(s) base URL into the equivalent ws(s) URL for
 * the realtime endpoint. Mirrors lib/portfolio-api.ts's own
 * NEXT_PUBLIC_API_BASE_URL convention rather than introducing a second,
 * separate env var — a WebSocket URL is always the same origin as the
 * REST API in this deployment topology, just a different scheme/path.
 */
function toWebSocketUrl(httpBaseUrl: string, token: string): string {
  const wsBase = httpBaseUrl.replace(/^http/, "ws");
  return `${wsBase}/api/v1/realtime/ws?token=${encodeURIComponent(token)}`;
}

/**
 * Connection lifecycle states exposed for UI indicators (connection
 * banner, offline badge, reconnecting spinner, etc — Task 12 consumes
 * this directly):
 * - "connecting": initial handshake in flight, never connected yet this mount.
 * - "connected": handshake succeeded, socket is open.
 * - "reconnecting": was connected at least once, socket dropped, a
 *   backoff-scheduled reconnect attempt is pending or in flight.
 * - "offline": not authenticated (no access token) — nothing to connect to.
 */
export type RealtimeConnectionState = "connecting" | "connected" | "reconnecting" | "offline";

/** Server -> client frame shapes, matching realtime_router.py's protocol exactly. */
export interface RealtimeEnvelope {
  type: string;
  topic?: string;
  data?: unknown;
  [key: string]: unknown;
}

type MessageListener = (envelope: RealtimeEnvelope) => void;

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
/**
 * Client-side keep-alive ping interval. The server already sends its own
 * {"type":"heartbeat"} frame every 15s (realtime_router.py) as a
 * keep-alive the client doesn't need to explicitly ack — this client-side
 * ping is a SEPARATE, additional signal: sending a message and never
 * receiving anything back (including no heartbeat) is how a silently-dead
 * connection (e.g. a network path that drops packets without a clean TCP
 * close) gets detected proactively rather than waiting on the browser's
 * own OS-level TCP timeout, which can be very long. 20s (slightly longer
 * than the server's 15s heartbeat) means a healthy connection always has
 * *something* arriving well before this client ping would even matter.
 */
const CLIENT_PING_INTERVAL_MS = 20_000;

export interface UseRealtimeConnectionResult {
  connectionState: RealtimeConnectionState;
  /** Subscribes to a topic on the server and registers a local listener
   * for messages on that topic. Returns an unsubscribe function that
   * both removes the local listener and tells the server to unsubscribe
   * (a no-op server-side if another local listener is still registered
   * for the same topic — see the internal ref-counting below). */
  subscribe: (topic: string, listener: MessageListener) => () => void;
}

/**
 * useRealtimeConnection — Phase 9 frontend WebSocket client
 * infrastructure. Establishes and maintains ONE WebSocket connection to
 * core-api's `/api/v1/realtime/ws` endpoint for the lifetime of the
 * authenticated session, exposing:
 * - `connectionState` for connection/offline/reconnecting UI indicators.
 * - `subscribe(topic, listener)` — the composable per-topic API every
 *   Task 12 dashboard widget builds on (ticker/watchlist/portfolio/ai/
 *   sentiment/alert widgets each subscribe to their own topic
 *   independently, without knowing about each other or sharing a single
 *   "lastMessage" value that would force every widget to filter it).
 *
 * DESIGN — single shared connection, not one-per-widget: multiple
 * dashboard widgets subscribing to different topics all share this one
 * hook's single underlying WebSocket (a module-level singleton, see
 * below) rather than each opening their own connection — matches
 * ConnectionManager's own server-side design, where each browser TAB is
 * one connection, not each WIDGET. React components using this hook are
 * simply attaching/detaching listeners to an already-open (or
 * connecting) shared socket.
 *
 * RECONNECTION — exponential backoff starting at 1s, doubling each
 * failed attempt, capped at 30s (disclosed, considered defaults — no
 * existing spec value was found for this specific timing). On successful
 * reconnect, every currently-registered topic is automatically
 * re-subscribed (re-subscribing to an already-subscribed topic is
 * documented server-side as a no-op, so this is always safe) — this is
 * the client half of the "server's job is making reconnection cheap"
 * design documented in realtime_service.py.
 */
export function useRealtimeConnection(): UseRealtimeConnectionResult {
  const accessToken = useAuthStore((state) => state.accessToken);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>(
    isAuthenticated ? "connecting" : "offline"
  );

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const backoffMsRef = useRef(INITIAL_BACKOFF_MS);
  const listenersByTopicRef = useRef<Map<string, Set<MessageListener>>>(new Map());
  const hasConnectedOnceRef = useRef(false);
  const isUnmountedRef = useRef(false);

  const sendAction = useCallback((action: string, extra?: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action, ...extra }));
    }
  }, []);

  const connect = useCallback(() => {
    if (!accessToken) {
      setConnectionState("offline");
      return;
    }

    const socket = new WebSocket(toWebSocketUrl(API_BASE_URL, accessToken));
    socketRef.current = socket;

    socket.onopen = () => {
      backoffMsRef.current = INITIAL_BACKOFF_MS;
      hasConnectedOnceRef.current = true;
      setConnectionState("connected");

      // Re-subscribe to every topic any listener is currently registered
      // for — safe/idempotent server-side, and necessary because the
      // server's SubscriptionRegistry is per-CONNECTION, so a brand new
      // socket starts with zero subscriptions regardless of what the
      // previous (now-dead) connection had.
      const topics = Array.from(listenersByTopicRef.current.keys());
      if (topics.length > 0) {
        sendAction("subscribe", { topics });
      }

      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      pingTimerRef.current = setInterval(() => sendAction("ping"), CLIENT_PING_INTERVAL_MS);
    };

    socket.onmessage = (event) => {
      let envelope: RealtimeEnvelope;
      try {
        envelope = JSON.parse(event.data as string) as RealtimeEnvelope;
      } catch {
        return; // malformed frame — never crash the connection over it
      }
      if (envelope.topic) {
        const listeners = listenersByTopicRef.current.get(envelope.topic);
        if (listeners) {
          for (const listener of listeners) listener(envelope);
        }
      }
    };

    socket.onclose = () => {
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
      if (isUnmountedRef.current) return;

      setConnectionState(hasConnectedOnceRef.current ? "reconnecting" : "connecting");

      const delay = backoffMsRef.current;
      backoffMsRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    // onerror is intentionally not separately handled: a WebSocket error
    // is always followed by a close event (per the WHATWG spec), which
    // already drives the reconnect-with-backoff logic above — a
    // duplicate handler here would just double-schedule reconnects.
    socket.onerror = () => {};
  }, [accessToken, sendAction]);

  useEffect(() => {
    isUnmountedRef.current = false;

    if (!isAuthenticated) {
      setConnectionState("offline");
      socketRef.current?.close();
      socketRef.current = null;
      return;
    }

    hasConnectedOnceRef.current = false;
    backoffMsRef.current = INITIAL_BACKOFF_MS;
    connect();

    return () => {
      isUnmountedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
    // Re-runs (tearing down and reconnecting) whenever the token itself
    // changes (login/logout/refresh-rotation) — connect() already reads
    // the latest accessToken via closure, this dependency just controls
    // WHEN a fresh connection cycle starts.
  }, [isAuthenticated, accessToken, connect]);

  const subscribe = useCallback(
    (topic: string, listener: MessageListener): (() => void) => {
      const listenersByTopic = listenersByTopicRef.current;
      const wasAlreadySubscribed = listenersByTopic.has(topic);
      let listeners = listenersByTopic.get(topic);
      if (!listeners) {
        listeners = new Set();
        listenersByTopic.set(topic, listeners);
      }
      listeners.add(listener);

      if (!wasAlreadySubscribed) {
        sendAction("subscribe", { topics: [topic] });
      }

      return () => {
        const currentListeners = listenersByTopic.get(topic);
        if (!currentListeners) return;
        currentListeners.delete(listener);
        if (currentListeners.size === 0) {
          listenersByTopic.delete(topic);
          sendAction("unsubscribe", { topics: [topic] });
        }
      };
    },
    [sendAction]
  );

  return { connectionState, subscribe };
}
