// Abuse guard for the endpoints that spend model capacity. It is a cost limiter, not an access control:
// anyone may ask as many questions as a person reasonably would, and nobody can turn the page into a free API.
// State is in memory (one web replica); a restart resets the counters, which is acceptable for a demo.

type Bucket = { day: string; count: number };

const today = () => new Date().toISOString().slice(0, 10);

const perIpDay = new Map<string, Bucket>();
const inFlightByIp = new Map<string, number>();
let globalDay: Bucket = { day: today(), count: 0 };
let globalInFlight = 0;

export type GuardConfig = {
  /** Requests one address may start per UTC day. */
  dailyPerIp: number;
  /** Requests the whole site may start per UTC day (a tripwire against distributed scraping). */
  dailyGlobal: number;
  /** Requests one address may have running at once. */
  concurrentPerIp: number;
  /** Requests the whole site may have running at once (protects the GPU for everyone else). */
  concurrentGlobal: number;
};

/** Behind Traefik the peer address is appended to X-Forwarded-For, so the last entry is the one the proxy saw. */
export function clientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const last = forwarded.split(",").map((part) => part.trim()).filter(Boolean).pop();
    if (last) return last.slice(0, 64);
  }
  return request.headers.get("x-real-ip")?.slice(0, 64) ?? "unknown";
}

/** Same-site browsers send Origin on POST; a cross-site page or an off-site script is turned away. Absent Origin (curl) passes to the other limits. */
export function crossSiteOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("host");
  try {
    return new URL(origin).host !== host;
  } catch {
    return true;
  }
}

function prune() {
  if (perIpDay.size > 5000) {
    const day = today();
    for (const [key, bucket] of perIpDay) if (bucket.day !== day) perIpDay.delete(key);
    if (perIpDay.size > 5000) perIpDay.clear();
  }
}

export type Admission = { ok: true; release: () => void } | { ok: false; status: 429; message: string; retryAfter: number };

export function admit(ip: string, config: GuardConfig): Admission {
  const day = today();
  if (globalDay.day !== day) globalDay = { day, count: 0 };
  const bucket = perIpDay.get(ip);
  const mine = bucket && bucket.day === day ? bucket : { day, count: 0 };
  if (mine.count >= config.dailyPerIp) {
    return { ok: false, status: 429, message: "This address reached today's question limit. It resets at midnight UTC.", retryAfter: 3600 };
  }
  if (globalDay.count >= config.dailyGlobal) {
    return { ok: false, status: 429, message: "The demo reached its daily capacity. It resets at midnight UTC.", retryAfter: 3600 };
  }
  if ((inFlightByIp.get(ip) ?? 0) >= config.concurrentPerIp) {
    return { ok: false, status: 429, message: "Wait for your running question to finish before sending another.", retryAfter: 10 };
  }
  if (globalInFlight >= config.concurrentGlobal) {
    return { ok: false, status: 429, message: "Many people are asking at once. Try again in a few seconds.", retryAfter: 10 };
  }
  mine.count += 1;
  perIpDay.set(ip, mine);
  globalDay.count += 1;
  inFlightByIp.set(ip, (inFlightByIp.get(ip) ?? 0) + 1);
  globalInFlight += 1;
  prune();
  let released = false;
  return {
    ok: true,
    release: () => {
      if (released) return;
      released = true;
      const left = (inFlightByIp.get(ip) ?? 1) - 1;
      if (left <= 0) inFlightByIp.delete(ip);
      else inFlightByIp.set(ip, left);
      globalInFlight = Math.max(0, globalInFlight - 1);
    },
  };
}

function intFromEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

export const answerLimits = (): GuardConfig => ({
  dailyPerIp: intFromEnv("GUARD_ANSWER_DAILY_PER_IP", 300),
  dailyGlobal: intFromEnv("GUARD_ANSWER_DAILY_GLOBAL", 4000),
  concurrentPerIp: intFromEnv("GUARD_ANSWER_CONCURRENT_PER_IP", 2),
  concurrentGlobal: intFromEnv("GUARD_ANSWER_CONCURRENT_GLOBAL", 6),
});

export const exploreLimits = (): GuardConfig => ({
  dailyPerIp: intFromEnv("GUARD_EXPLORE_DAILY_PER_IP", 1000),
  dailyGlobal: intFromEnv("GUARD_EXPLORE_DAILY_GLOBAL", 20000),
  concurrentPerIp: intFromEnv("GUARD_EXPLORE_CONCURRENT_PER_IP", 4),
  concurrentGlobal: intFromEnv("GUARD_EXPLORE_CONCURRENT_GLOBAL", 12),
});
