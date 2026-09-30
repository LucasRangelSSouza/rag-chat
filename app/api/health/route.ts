import { NextResponse } from "next/server";
import type { CorpusHealth } from "@/lib/contracts";

export const dynamic = "force-dynamic";

export async function GET() {
  const backend = process.env.RAG_CHAT_BACKEND_URL;
  if (!backend) {
    return NextResponse.json<CorpusHealth>({ status: "pending", corpus_name: "PNCP", model_status: "unavailable" });
  }
  try {
    const response = await fetch(`${backend.replace(/\/$/, "")}/healthz`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error("backend_unavailable");
    const payload = await response.json();
    return NextResponse.json<CorpusHealth>({
      status: payload.status === "ready" ? "ready" : "pending",
      corpus_name: typeof payload.corpus_name === "string" ? payload.corpus_name : "PNCP",
      ...(typeof payload.release_version === "string" ? { release_version: payload.release_version } : {}),
      ...(typeof payload.data_cutoff === "string" ? { data_cutoff: payload.data_cutoff } : {}),
      ...(Number.isInteger(payload.table_count) ? { table_count: payload.table_count } : {}),
      ...(Number.isInteger(payload.record_count) ? { record_count: payload.record_count } : {}),
      model_status: ["ready", "extractive", "unavailable"].includes(payload.model_status) ? payload.model_status : "unavailable",
    });
  } catch {
    return NextResponse.json<CorpusHealth>({ status: "unavailable", corpus_name: "PNCP", model_status: "unavailable" });
  }
}
