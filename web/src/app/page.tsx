"use client";

import { useEffect, useRef, useState } from "react";
import { askStream, Citation, PARTS, StreamEvent, ToolRun, wakeServer } from "@/lib/api";

const EXAMPLES = [
  { part: "LM358", q: "What is the typical input offset voltage of the LM358 at 25 °C?" },
  { part: "ESP32", q: "How much current does the ESP32 draw in deep-sleep mode?" },
  { part: "ATmega328P", q: "How much internal SRAM does the ATmega328P have?" },
  { part: "MCP3008", q: "How many single-ended inputs does the MCP3008 offer?" },
  { part: "Calculator", q: "What output voltage does a 10k/4.7k divider give from the ESP32's 3.3 V?" },
];

const STATS = [
  { value: "8", label: "datasheets, 1,099 pages" },
  { value: "82%", label: "recall@5 on 60 test questions" },
  { value: "~1 s", label: "hybrid search" },
];

// Matches labels the model writes, like [LM358 p.4]
const LABEL_RE = /\[([A-Za-z0-9]+),?\s*p\.\s*(\d+)\]/g;

type Done = Extract<StreamEvent, { type: "done" }>;

function partName(id: string) {
  return PARTS.find((p) => p.id === id)?.name ?? id.toUpperCase();
}

function formatTool(run: ToolRun) {
  const args = Object.entries(run.args)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  const out = run.result !== undefined ? Number(run.result.toPrecision(4)) : `error: ${run.error}`;
  return { call: `${run.tool}(${args})`, out: String(out) };
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="size-4" aria-hidden>
      <path d="M3 10a.75.75 0 0 1 .75-.75h10.64L10.2 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.2-3.96H3.75A.75.75 0 0 1 3 10Z" />
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className="size-3 opacity-60" aria-hidden>
      <path d="M6.22 8.72a.75.75 0 0 0 1.06 1.06l5.22-5.22v1.69a.75.75 0 0 0 1.5 0v-3.5a.75.75 0 0 0-.75-.75h-3.5a.75.75 0 0 0 0 1.5h1.69L6.22 8.72Z" />
      <path d="M3.5 6.75c0-.69.56-1.25 1.25-1.25H7A.75.75 0 0 0 7 4H4.75A2.75 2.75 0 0 0 2 6.75v4.5A2.75 2.75 0 0 0 4.75 14h4.5A2.75 2.75 0 0 0 12 11.25V9a.75.75 0 0 0-1.5 0v2.25c0 .69-.56 1.25-1.25 1.25h-4.5c-.69 0-1.25-.56-1.25-1.25v-4.5Z" />
    </svg>
  );
}

/** Answer text with each [PART p.N] label shown as a small inline badge (a link once its PDF link is known). */
function AnswerText({ text, citations, streaming }: { text: string; citations: Citation[]; streaming: boolean }) {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LABEL_RE)) {
    const at = m.index ?? 0;
    out.push(text.slice(last, at));
    const cite = citations.find((c) => c.part === m[1].toLowerCase() && c.page === Number(m[2]));
    const badge = "mx-0.5 rounded-md px-1.5 py-0.5 font-mono text-[0.78em] whitespace-nowrap";
    out.push(
      cite?.url ? (
        <a key={at} href={cite.url} target="_blank" rel="noreferrer"
          className={`${badge} bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-100`}>
          {partName(cite.part)} p.{cite.page}
        </a>
      ) : (
        <span key={at} className={`${badge} bg-zinc-100 text-zinc-500`}>
          {m[1]} p.{m[2]}
        </span>
      ),
    );
    last = at + m[0].length;
  }
  out.push(text.slice(last));
  return <p className={`text-[17px] leading-8 text-zinc-800 whitespace-pre-wrap ${streaming ? "caret" : ""}`}>{out}</p>;
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [part, setPart] = useState("any");
  const [asked, setAsked] = useState("");
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState("");
  const [tools, setTools] = useState<ToolRun[]>([]);
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [waking, setWaking] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [android, setAndroid] = useState(false);

  useEffect(wakeServer, []);
  // Chrome on Android opens PDFs at page 1 and ignores #page=N, so tell the reader which page to go to.
  useEffect(() => setAndroid(/Android/i.test(navigator.userAgent)), []);

  async function ask(q: string) {
    q = q.trim();
    if (q.length < 3 || loading) return;
    setQuestion(q);
    setAsked(q);
    setAnswer("");
    setStatus("Connecting");
    setTools([]);
    setDone(null);
    setError("");
    setLoading(true);
    setWaking(false);
    // On a phone: close the keyboard and jump to the top, where the answer appears.
    inputRef.current?.blur();
    window.scrollTo({ top: 0, behavior: "smooth" });

    // Free Render sleeps when idle; if nothing arrives in 3 s, say so.
    let gotFirst = false;
    const wakeTimer = setTimeout(() => !gotFirst && setWaking(true), 3000);

    function onEvent(e: StreamEvent) {
      if (!gotFirst) {
        gotFirst = true;
        setWaking(false);
      }
      if (e.type === "status") setStatus(e.text);
      else if (e.type === "token") {
        setStatus("");
        setAnswer((a) => a + e.text);
      } else if (e.type === "tool") setTools((t) => [...t, e]);
      else if (e.type === "retry") {
        setAnswer("");
        setTools([]);
      } else if (e.type === "error") setError(e.message);
      else if (e.type === "done") {
        setAnswer(e.answer);
        setTools(e.tools ?? []);
        setDone(e);
      }
    }

    try {
      await askStream(q, part === "any" ? null : part, onEvent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      clearTimeout(wakeTimer);
      setWaking(false);
      setStatus("");
      setLoading(false);
    }
  }

  function reset() {
    setAsked("");
    setQuestion("");
    setAnswer("");
    setDone(null);
    inputRef.current?.focus();
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Background: grid + soft colour glow at the top */}
      <div className="grid-bg pointer-events-none absolute inset-x-0 top-0 h-[560px]" />
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[820px] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-300/40 via-sky-200/40 to-violet-300/40 blur-3xl" />

      <nav className="relative mx-auto flex max-w-5xl items-center justify-between px-5 py-5">
        <button onClick={reset} className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-lg bg-zinc-900 font-mono text-xs text-white">DS</span>
          DatasheetGPT
        </button>
        <div className="flex items-center gap-5 text-sm text-zinc-500">
          <a href="https://github.com/project-devo/datasheetgpt" target="_blank" rel="noreferrer" className="hover:text-zinc-900">
            GitHub
          </a>
        </div>
      </nav>

      <main className="relative mx-auto flex max-w-3xl flex-col px-5 pb-16">
        {!asked && (
          <section className="pt-10 pb-8 text-center sm:pt-16">
            <span className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white/70 px-3 py-1 text-xs text-zinc-600 shadow-sm backdrop-blur">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              Every answer cites the datasheet page
            </span>
            <h1 className="mx-auto mt-6 max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
              Ask your datasheets.{" "}
              <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-sky-500 bg-clip-text text-transparent">
                Get the page.
              </span>
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-lg text-zinc-600 text-balance">
              Specs from ESP32, STM32, ATmega328P, LM358 and more, answered from the manufacturer&apos;s PDF with a link
              to the exact page.
            </p>
          </section>
        )}

        {/* Ask box */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
          className={`group rounded-2xl border border-zinc-200 bg-white/90 p-2 shadow-[0_8px_30px_rgb(0,0,0,0.06)] backdrop-blur transition focus-within:border-indigo-300 focus-within:ring-4 focus-within:ring-indigo-100 ${asked ? "mt-6" : ""}`}
        >
          <textarea
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(question);
              }
            }}
            rows={2}
            maxLength={500}
            placeholder="Ask about a pin, a current, a voltage limit..."
            className="block w-full resize-none bg-transparent px-3 pt-2 text-[16px] outline-none placeholder:text-zinc-400"
          />
          <div className="flex items-center justify-between gap-2 px-1 pt-1">
            <select
              value={part}
              onChange={(e) => setPart(e.target.value)}
              aria-label="Part"
              className="rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm text-zinc-700 outline-none hover:bg-zinc-100"
            >
              <option value="any">All parts</option>
              {PARTS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={loading || question.trim().length < 3}
              className="inline-flex items-center gap-1.5 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:bg-zinc-300"
            >
              {loading ? "Thinking" : "Ask"}
              <ArrowIcon />
            </button>
          </div>
        </form>

        {/* Example questions */}
        {!asked && (
          <section className="mt-8">
            <p className="mb-3 text-xs font-medium tracking-wide text-zinc-400 uppercase">Try an example</p>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {EXAMPLES.map(({ part: tag, q }, i) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className={`${i === EXAMPLES.length - 1 ? "sm:col-span-2" : ""} group/ex flex items-start justify-between gap-3 rounded-xl border border-zinc-200 bg-white/80 p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md`}
                >
                  <span>
                    <span className="mb-1.5 inline-block rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-500">
                      {tag}
                    </span>
                    <span className="block text-sm text-zinc-700">{q}</span>
                  </span>
                  <span className="mt-6 text-zinc-300 transition group-hover/ex:translate-x-0.5 group-hover/ex:text-indigo-500">
                    <ArrowIcon />
                  </span>
                </button>
              ))}
            </div>

            <div className="mt-12 grid grid-cols-3 divide-x divide-zinc-200 rounded-2xl border border-zinc-200 bg-white/70 text-center">
              {STATS.map((s) => (
                <div key={s.label} className="px-2 py-5">
                  <div className="text-2xl font-semibold tracking-tight">{s.value}</div>
                  <div className="mt-1 text-xs text-zinc-500">{s.label}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Answer */}
        {asked && (
          <section className="rise mt-8">
            <div className="mb-4 flex items-start gap-3">
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-500">
                You
              </span>
              <p className="pt-0.5 font-medium text-zinc-900">{asked}</p>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-[0_8px_30px_rgb(0,0,0,0.05)]">
              {waking && (
                <div className="mb-4 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <span className="size-2 animate-ping rounded-full bg-amber-500" />
                  Waking up the server. The free host sleeps when idle, so the first answer can take up to a minute.
                </div>
              )}

              {tools.map((t, i) => {
                const { call, out } = formatTool(t);
                return (
                  <div key={i} className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-zinc-950 px-4 py-2.5 font-mono text-[13px] text-zinc-300">
                    <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] text-emerald-400">calculator</span>
                    <span>{call}</span>
                    <span className="text-zinc-500">=</span>
                    <span className="text-white">{out}</span>
                  </div>
                );
              })}

              {!answer && loading && (
                <div className="space-y-2.5">
                  <p className="flex items-center gap-2 text-sm text-zinc-500">
                    <span className="size-1.5 animate-pulse rounded-full bg-indigo-500" />
                    {status}...
                  </p>
                  <div className="h-3 w-11/12 animate-pulse rounded bg-zinc-100" />
                  <div className="h-3 w-3/4 animate-pulse rounded bg-zinc-100" />
                </div>
              )}

              {answer && <AnswerText text={answer} citations={done?.citations ?? []} streaming={loading} />}
              {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

              {done && done.citations.length > 0 && (
                <div className="mt-6 border-t border-zinc-100 pt-4">
                  <p className="mb-2 text-xs font-medium tracking-wide text-zinc-400 uppercase">Sources</p>
                  <div className="flex flex-wrap gap-2">
                    {done.citations.map((c) => (
                      <a
                        key={`${c.part}-${c.page}`}
                        href={c.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-700 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                      >
                        <span className="font-medium">{partName(c.part)}</span>
                        <span className="text-zinc-400">page {c.page}</span>
                        <ExternalIcon />
                      </a>
                    ))}
                  </div>
                  {android && (
                    <p className="mt-2 text-xs text-zinc-400">
                      On Android the PDF opens at page 1. Scroll to the page number shown on the chip.
                    </p>
                  )}
                </div>
              )}

              {done && (
                <div className="mt-5 flex items-center justify-between text-xs text-zinc-400">
                  <span className="font-mono">
                    {done.model} · {(done.latency_ms / 1000).toFixed(1)} s{done.cached ? " · cached" : ""}
                  </span>
                  <button onClick={reset} className="font-medium text-zinc-600 hover:text-zinc-900">
                    New question
                  </button>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      <footer className="relative mx-auto max-w-5xl px-5 pb-8 text-center text-xs text-zinc-400">
        Answers come only from the datasheets: hybrid search over pgvector + full text, then Gemini (Groq as fallback).
        Check the cited page before you build.
      </footer>
    </div>
  );
}
