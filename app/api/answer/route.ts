import { NextResponse } from "next/server";
import type { Answer, Citation } from "@/lib/contracts";

export const dynamic = "force-dynamic";
const MAX_QUESTION_CHARS = 1000;
const MAX_BODY_BYTES = 16 * 1024;

function safeCitation(value: unknown): Citation | null {
  if (!value || typeof value !== "object") return null;
  const citation = value as Record<string, unknown>;
  if (typeof citation.title !== "string" || typeof citation.source_uri !== "string") return null;
  const dataset = citation.dataset && typeof citation.dataset === "object" ? citation.dataset as Record<string, unknown> : null;
  const slug = typeof dataset?.slug === "string" && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(dataset.slug)
    ? dataset.slug.slice(0, 128)
    : undefined;
  const version = Number.isSafeInteger(dataset?.version) && Number(dataset?.version) > 0 ? Number(dataset?.version) : undefined;
  return {
    title: citation.title.slice(0, 240),
    source_uri: citation.source_uri.slice(0, 1024),
    ...(typeof citation.chunk_id === "string" ? { chunk_id: citation.chunk_id.slice(0, 160) } : {}),
    ...(typeof citation.document_id === "string" ? { document_id: citation.document_id.slice(0, 160) } : {}),
    ...(typeof citation.license_note === "string" ? { license_note: citation.license_note.slice(0, 500) } : {}),
    ...(slug && version ? { dataset: { slug, version, ...(typeof dataset?.manifest_sha256 === "string" && /^[a-f0-9]{64}$/i.test(dataset.manifest_sha256) ? { manifest_sha256: dataset.manifest_sha256.toLowerCase() } : {}) } } : {}),
    ...(Array.isArray(citation.record_ids) ? { record_ids: citation.record_ids.filter((id): id is string => typeof id === "string").slice(0, 8).map((id) => id.slice(0, 160)) } : {}),
    ...(typeof citation.score === "number" && Number.isFinite(citation.score) ? { score: citation.score } : {}),
  };
}

function safeAnswer(value: unknown): Answer | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (!["answered", "abstained", "refused"].includes(String(candidate.status))) return null;
  if (typeof candidate.answer !== "string" || !Array.isArray(candidate.citations)) return null;
  const citations = candidate.citations.map(safeCitation).filter((citation): citation is Citation => citation !== null).slice(0, 8);
  return {
    status: candidate.status as Answer["status"],
    answer: candidate.answer.slice(0, 12_000),
    citations,
    safety_reason: typeof candidate.safety_reason === "string" ? candidate.safety_reason.slice(0, 80) : null,
    ...(typeof candidate.grounded === "boolean" ? { grounded: candidate.grounded } : {}),
  };
}

export async function POST(request: Request) {
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "The request is too large." }, { status: 413 });
  }
  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch {
    return NextResponse.json({ error: "Send a valid JSON question." }, { status: 400 });
  }
  if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "The request is too large." }, { status: 413 });
  }
  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "Send a valid JSON question." }, { status: 400 });
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return NextResponse.json({ error: "Send a valid JSON question." }, { status: 400 });
  }
  const body = payload as Record<string, unknown>;
  if (Object.keys(body).some((key) => key !== "question" && key !== "corpora")) {
    return NextResponse.json({ error: "Only the question and corpora fields are accepted." }, { status: 400 });
  }
  const corpora = body.corpora === undefined ? [] : body.corpora;
  if (!Array.isArray(corpora) || corpora.length > 5 || corpora.some((id) => typeof id !== "string" || !/^[a-z0-9_-]{1,40}$/.test(id))) {
    return NextResponse.json({ error: "Choose up to five research bases." }, { status: 400 });
  }
  if (typeof body.question !== "string" || !body.question.trim() || body.question.length > MAX_QUESTION_CHARS) {
    return NextResponse.json({ error: "Enter a question of up to 1,000 characters." }, { status: 400 });
  }
  const backend = process.env.RAG_CHAT_BACKEND_URL;
  if (!backend) return NextResponse.json({ error: "The research service is not ready yet." }, { status: 503 });
  try {
    const response = await fetch(`${backend.replace(/\/$/, "")}/v1/answer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: body.question, corpora }),
      cache: "no-store",
      signal: AbortSignal.timeout(25_000),
    });
    if (!response.ok) return NextResponse.json({ error: "The research service could not answer right now." }, { status: 503 });
    const answer = safeAnswer(await response.json());
    if (!answer) return NextResponse.json({ error: "The research service returned an invalid response." }, { status: 502 });
    return NextResponse.json(answer, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "The research service is unavailable. Try again shortly." }, { status: 503 });
  }
}
