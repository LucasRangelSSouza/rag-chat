import { NextResponse } from "next/server";
import { admit, clientIp, exploreLimits } from "@/lib/guard";

export const dynamic = "force-dynamic";

const MODES = new Set(["text", "vector", "hybrid"]);

type ExploreResult = {
  id: string;
  org: string | null;
  municipality: string | null;
  uf: string | null;
  modality: string | null;
  published: string;
  text: string;
  link: string | null;
  rank: number;
};

function clean(value: unknown, max: number): string | null {
  return typeof value === "string" ? value.slice(0, max) : null;
}

/** Search-page endpoint: text, vector or hybrid retrieval over the same Postgres the chat reads. */
export async function GET(request: Request) {
  const backend = process.env.RAG_CHAT_BACKEND_URL;
  if (!backend) return NextResponse.json({ error: "Search is not available." }, { status: 503 });
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode") ?? "hybrid";
  const q = (url.searchParams.get("q") ?? "").trim();
  const limit = Math.max(1, Math.min(20, Number(url.searchParams.get("limit") ?? 12) || 12));
  if (!MODES.has(mode) || q.length < 3 || q.length > 200) {
    return NextResponse.json({ error: "Type between 3 and 200 characters." }, { status: 400 });
  }
  const admission = admit(clientIp(request), exploreLimits());
  if (!admission.ok) {
    return NextResponse.json({ error: admission.message }, { status: 429, headers: { "retry-after": String(admission.retryAfter) } });
  }
  try {
    const response = await fetch(
      `${backend.replace(/\/$/, "")}/v1/search?mode=${mode}&limit=${limit}&q=${encodeURIComponent(q)}`,
      { cache: "no-store", signal: AbortSignal.timeout(25000) },
    );
    if (!response.ok) throw new Error("backend");
    const payload = await response.json();
    const results: ExploreResult[] = (Array.isArray(payload.results) ? payload.results : []).slice(0, limit).map((r: Record<string, unknown>) => ({
      id: String(r.id ?? "").slice(0, 80),
      org: clean(r.org, 200),
      municipality: clean(r.municipality, 80),
      uf: clean(r.uf, 2),
      modality: clean(r.modality, 80),
      published: String(r.published ?? "").slice(0, 10),
      text: String(r.text ?? "").slice(0, 400),
      link: typeof r.link === "string" && r.link.startsWith("https://pncp.gov.br/") ? r.link.slice(0, 300) : null,
      rank: Number(r.rank) || 0,
    }));
    return NextResponse.json({
      mode,
      total: Number.isFinite(Number(payload.total)) ? Number(payload.total) : results.length,
      results,
      vector_available: Boolean(payload.vector_available),
    });
  } catch {
    return NextResponse.json({ error: "The search service is unavailable." }, { status: 503 });
  } finally {
    admission.release();
  }
}
