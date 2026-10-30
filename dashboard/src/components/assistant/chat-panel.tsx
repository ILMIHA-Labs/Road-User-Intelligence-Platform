"use client";

import { useCallback, useRef, useState } from "react";
import { buildContext, streamAssistant, type ChatMessage } from "@/data/assistant";
import type { DashboardJob } from "@/data/types";
import { cn } from "@/lib/utils";
import { useSpeechRecognition, useSpeechSynthesis } from "./use-speech";

const SUGGESTIONS = [
  "What's the yielding rate?",
  "Which class speeds most?",
  "How many critical PET events?",
];

export function ChatPanel({ job }: { job: DashboardJob }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speakAnswers, setSpeakAnswers] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const tts = useSpeechSynthesis();

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || streaming) return;
      setError(null);
      setInput("");
      const history: ChatMessage[] = [...messages, { role: "user", content }];
      setMessages([...history, { role: "assistant", content: "" }]);
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        let answer = "";
        await streamAssistant(
          { messages: history, context: buildContext([job]) },
          (chunk) => {
            answer += chunk;
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { role: "assistant", content: answer };
              return next;
            });
          },
          controller.signal,
        );
        if (speakAnswers && tts.supported && answer) tts.speak(answer);
      } catch (err) {
        setError(err instanceof Error ? err.message : "The assistant failed to respond.");
        setMessages((prev) => prev.slice(0, -1)); // drop the empty assistant bubble
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [messages, streaming, job, speakAnswers, tts],
  );

  const stt = useSpeechRecognition(
    useCallback(
      (text: string) => {
        setInput(text);
        void send(text);
      },
      [send],
    ),
  );

  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-medium">Assistant</h2>
          <p className="truncate text-xs text-muted-foreground">
            Grounded in this job&apos;s metrics · aggregates only
          </p>
        </div>
        {tts.supported ? (
          <label className="flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={speakAnswers}
              onChange={(e) => setSpeakAnswers(e.target.checked)}
              className="accent-foreground"
            />
            Speak answers
          </label>
        ) : null}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Ask about the loaded analysis — counts, speeds, yielding, PET.
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
                  m.role === "user"
                    ? "bg-foreground text-background"
                    : "border border-border bg-background",
                )}
              >
                {m.content || (streaming ? "…" : "")}
              </div>
            </div>
          ))
        )}
        {error ? (
          <p className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        ) : null}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="flex items-center gap-2 border-t border-border px-3 py-3"
      >
        {stt.supported ? (
          <button
            type="button"
            onClick={() => (stt.listening ? stt.stop() : stt.start())}
            title={stt.listening ? "Stop listening" : "Ask by voice (uses cloud transcription)"}
            aria-pressed={stt.listening}
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors",
              stt.listening
                ? "border-destructive bg-destructive/10 text-destructive"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            <MicIcon active={stt.listening} />
          </button>
        ) : null}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={stt.listening ? "Listening…" : "Ask a question…"}
          className="h-9 flex-1 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-ring"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="h-9 rounded-md bg-foreground px-3 text-sm font-medium text-background disabled:opacity-40"
        >
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="2" width="6" height="12" rx="3" fill={active ? "currentColor" : "none"} />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="17" x2="12" y2="22" />
    </svg>
  );
}
