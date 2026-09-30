// Click-through of the deployed chat, the explorer page and the dashboards. Usage:
//   node tests/live/live-check.mjs [outputDir]
// Sets CHAT_URL, SITE_URL to override the defaults. Exits non-zero when a check fails.
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const CHAT = process.env.CHAT_URL ?? "https://rag.rangeltech.net";
const SITE = process.env.SITE_URL ?? "https://rangeltech.net";
const OUT = process.argv[2] ?? "docs/evidence/live";
mkdirSync(OUT, { recursive: true });

const results = [];
async function check(name, fn) {
  const started = Date.now();
  try {
    const detail = await fn();
    results.push({ name, ok: true, seconds: Math.round((Date.now() - started) / 1000), detail: detail ?? "" });
  } catch (error) {
    await page.screenshot({ path: `${OUT}/fail-${name.replace(/[^a-z0-9]+/gi, "-").slice(0, 40)}.png`, fullPage: true }).catch(() => {});
    results.push({ name, ok: false, seconds: Math.round((Date.now() - started) / 1000), detail: String(error.message ?? error).split("\n")[0] });
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

async function ask(question) {
  const box = page.getByPlaceholder(/ask about/i);
  await box.fill(question);
  await page.getByRole("button", { name: "Send question" }).click();
}

await check("chat loads and lists the research bases", async () => {
  await page.goto(CHAT, { waitUntil: "domcontentloaded" });
  await page.getByText("Model ready").waitFor({ timeout: 60000 });
  const boxes = await page.getByRole("checkbox").count();
  if (boxes < 3) throw new Error(`expected 3 bases, found ${boxes}`);
  await page.screenshot({ path: `${OUT}/01-chat-bases.png` });
  return `${boxes} bases`;
});

await check("text base answers with citations", async () => {
  await page.getByRole("checkbox").first().check();
  await ask("Quais licitações de transporte escolar existem nos registros?");
  await page.getByText(/transporte escolar/i).nth(1).waitFor({ timeout: 120000 });
  await page.getByText(/Coverage|Cobertura/i).first().waitFor({ timeout: 120000 });
  await page.screenshot({ path: `${OUT}/02-text-answer.png`, fullPage: true });
});

await check("SIOPE SQL base shows the query as evidence", async () => {
  await page.getByRole("button", { name: /new research/i }).click();
  const boxes = page.getByRole("checkbox");
  await boxes.nth(0).uncheck();
  await boxes.nth(2).check();
  await ask("What was the median education investment per student in 2023, by region?");
  await page.getByText(/SQL and result/).first().waitFor({ timeout: 150000 });
  await page.getByText(/SQL and result/).first().click();
  await page.getByText(/SELECT/).first().waitFor({ timeout: 10000 });
  await page.screenshot({ path: `${OUT}/03-siope-sql.png`, fullPage: true });
});

await check("no base selected gives a plain, ungrounded reply", async () => {
  await page.getByRole("button", { name: /new research/i }).click();
  await ask("Say hello in one short sentence.");
  await page.getByText(/./).first().waitFor();
  await page.waitForTimeout(15000);
  await page.screenshot({ path: `${OUT}/04-no-base.png` });
});

await check("explorer text search returns notices", async () => {
  await page.goto(`${SITE}/dashboards/pncp/`, { waitUntil: "networkidle" });
  await page.locator("#search-text").fill("merenda escolar");
  await page.getByRole("button", { name: "Search" }).first().click();
  await page.getByText(/matching notices/).waitFor({ timeout: 60000 });
  await page.screenshot({ path: `${OUT}/05-explorer-text.png`, fullPage: true });
});

await check("explorer semantic search answers or explains", async () => {
  await page.locator("#search-vector").fill("buying food for students");
  await page.getByRole("button", { name: "Search" }).nth(1).click();
  await page.getByText(/most similar notices|not available right now|No notice matched/).waitFor({ timeout: 60000 });
});

await check("PNCP dashboard frame renders charts", async () => {
  const frame = page.frameLocator("iframe").first();
  await frame.getByText(/PNCP notices/i).first().waitFor({ timeout: 90000 });
  await page.screenshot({ path: `${OUT}/06-pncp-dashboard.png`, fullPage: true });
});

await check("SIOPE dashboard frame renders charts", async () => {
  await page.goto(`${SITE}/dashboards/siope/`, { waitUntil: "domcontentloaded" });
  const frame = page.frameLocator("iframe").first();
  await frame.getByText(/SIOPE/i).first().waitFor({ timeout: 90000 });
  await page.screenshot({ path: `${OUT}/07-siope-dashboard.png`, fullPage: true });
});

await browser.close();
const lines = ["# Live click-through", "", `Run: ${new Date().toISOString()}`, "", "| Check | Result | Seconds | Detail |", "|---|---|---:|---|"];
for (const r of results) lines.push(`| ${r.name} | ${r.ok ? "pass" : "FAIL"} | ${r.seconds} | ${r.detail.replace(/\|/g, "/")} |`);
writeFileSync(`${OUT}/live-check.md`, lines.join("\n") + "\n");
console.log(lines.join("\n"));
process.exit(results.every((r) => r.ok) ? 0 : 1);
