/**
 * File purpose: Implements browser-side API access for sse parser.
 * Main declarations: parseSseJson handles parse sse json; parseSseEvents handles parse sse events;
 * splitSseBuffer handles split sse buffer.
 */

export interface ParsedSseEvent {
  data: Record<string, unknown>;
  type: string;
}

export function parseSseJson<T>(data: string, eventType: string): T | undefined {
  try {
    return JSON.parse(data) as T;
  } catch (error) {
    console.warn("Ignored malformed SSE event", {
      data,
      error,
      eventType,
    });
    return undefined;
  }
}

export function parseSseEvents(rawEvents: string): ParsedSseEvent[] {
  return rawEvents
    .split("\n\n")
    .map((rawEvent) => {
      const lines = rawEvent.split("\n");
      const type = lines
        .find((line) => line.startsWith("event:"))
        ?.slice("event:".length)
        .trim();
      const data = lines
        .find((line) => line.startsWith("data:"))
        ?.slice("data:".length)
        .trim();

      if (!type || !data) {
        return undefined;
      }

      const parsed = parseSseJson<Record<string, unknown>>(data, type);
      return parsed ? { data: parsed, type } : undefined;
    })
    .filter((event): event is ParsedSseEvent => Boolean(event));
}

export function splitSseBuffer(buffer: string) {
  const rawEvents = buffer.split("\n\n");
  const remainingBuffer = rawEvents.pop() ?? "";
  return {
    events: parseSseEvents(rawEvents.join("\n\n")),
    remainingBuffer,
  };
}
