import Anthropic from "@anthropic-ai/sdk";
import { NextResponse } from "next/server";
import {
  buildSystemPrompt,
  DEFAULT_MODEL_TIER,
  MODEL_IDS,
  type ChatRequest,
} from "@/data/assistant";

// Runs on the default Node runtime (Anthropic SDK + server-side key).
const MAX_TOKENS = 1024;

function badRequest(error: string, status = 400) {
  return NextResponse.json({ error }, { status });
}

export async function POST(request: Request) {
  if (!process.env.ANTHROPIC_API_KEY) {
    return badRequest(
      "The assistant is not configured on this deployment (ANTHROPIC_API_KEY is unset).",
      501,
    );
  }

  let body: ChatRequest;
  try {
    body = (await request.json()) as ChatRequest;
  } catch {
    return badRequest("Invalid JSON body.");
  }

  const messages = Array.isArray(body.messages) ? body.messages : [];
  if (messages.length === 0) return badRequest("`messages` must be a non-empty array.");
  if (!body.context || !Array.isArray(body.context.jobs) || body.context.jobs.length === 0) {
    return badRequest("`context.jobs` must contain at least one job.");
  }

  const tier = body.model && body.model in MODEL_IDS ? body.model : DEFAULT_MODEL_TIER;
  const model = process.env.ASSISTANT_MODEL ?? MODEL_IDS[tier];

  const anthropic = new Anthropic();
  const stream = anthropic.messages.stream({
    model,
    max_tokens: MAX_TOKENS,
    system: buildSystemPrompt(body.context),
    messages: messages.map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: String(m.content ?? ""),
    })),
  });

  const encoder = new TextEncoder();
  const readable = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const event of stream) {
          if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
            controller.enqueue(encoder.encode(event.delta.text));
          }
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      }
    },
    cancel() {
      stream.abort();
    },
  });

  return new Response(readable, {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
  });
}
