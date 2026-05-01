import { useEffect, useRef, useCallback } from "react";

import { BASE } from "../api";

/**
 * useSSE
 * ------
 * Opens an EventSource to the SSE stream for a given sessionId.
 * Calls onEvent(parsedEvent) for each message.
 * Calls onDone() when "done" or "error" event arrives.
 * Cleans up automatically on unmount or sessionId change.
 */
export function useSSE(sessionId, onEvent, onDone) {
  const esRef = useRef(null);

  const close = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    close(); // close any previous connection

    const es = new EventSource(`${BASE}/research/${sessionId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        onEvent(event);
        if (event.type === "done" || event.type === "error") {
          close();
          onDone?.(event);
        }
      } catch (err) {
        console.error("SSE parse error", err);
      }
    };

    es.onerror = () => {
      close();
      onDone?.({ type: "error", data: { message: "Connection lost" } });
    };

    return close;
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { close };
}
