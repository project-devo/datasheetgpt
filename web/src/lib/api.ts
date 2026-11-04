// Talks to the FastAPI server: POST /ask/stream sends server-sent events.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7860";

export const PARTS = [
  { id: "esp32", name: "ESP32" },
  { id: "stm32f103", name: "STM32F103" },
  { id: "atmega328p", name: "ATmega328P" },
  { id: "lm358", name: "LM358" },
  { id: "ne555", name: "NE555" },
  { id: "lm317", name: "LM317" },
  { id: "mcp3008", name: "MCP3008" },
  { id: "bme280", name: "BME280" },
];

export type Citation = { part: string; page: number; url?: string };
export type ToolRun = { tool: string; args: Record<string, unknown>; result?: number; error?: string };

export type StreamEvent =
  | { type: "status"; text: string }
  | { type: "token"; text: string }
  | ({ type: "tool" } & ToolRun)
  | { type: "retry" }
  | { type: "error"; message: string }
  | {
      type: "done";
      answer: string;
      citations: Citation[];
      not_found: boolean;
      model: string;
      tools: ToolRun[];
      cached: boolean;
      latency_ms: number;
    };

/** Wake the free Render server as soon as the page opens, so the first question is faster. */
export function wakeServer() {
  fetch(`${API_URL}/health`).catch(() => {});
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Ask a question and call onEvent for every event as it arrives.
 * While Render is waking up, the request can fail (network error, 429, 502, 503),
 * so it is retried every 5 s for up to about a minute.
 */
export async function askStream(question: string, part: string | null, onEvent: (e: StreamEvent) => void) {
  let res: Response | null = null;
  for (let attempt = 0; attempt < 12; attempt++) {
    try {
      res = await fetch(`${API_URL}/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, part }),
      });
      if (![429, 502, 503].includes(res.status)) break;
    } catch {
      res = null; // network error: server still asleep
    }
    await sleep(5000);
  }
  if (!res) throw new Error("Could not reach the server. Please try again in a minute.");
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Server error ${res.status}`;
    throw new Error(detail);
  }

  // SSE format: each event is "data: {json}" followed by a blank line.
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, end).trim();
      buffer = buffer.slice(end + 2);
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
    }
  }
}
