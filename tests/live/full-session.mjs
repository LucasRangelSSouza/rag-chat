// Drives the deployed chat like a person: each base alone, all three combined, and one long conversation.
// Records the seconds each answer took and a screenshot after each step.
//   node tests/live/full-session.mjs [outputDir]      (CHAT_URL overrides the address)
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const CHAT = process.env.CHAT_URL ?? "https://rag.rangeltech.net";
const OUT = process.argv[2] ?? "docs/evidence/live-session";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const log = [];

async function open() {
  await page.goto(CHAT, { waitUntil: "domcontentloaded" });
  await page.getByText("Model ready").waitFor({ timeout: 60000 });
}
async function select(indexes) {
  const boxes = page.getByRole("checkbox");
  const n = await boxes.count();
  for (let i = 0; i < n; i++) {
    const want = indexes.includes(i);
    if ((await boxes.nth(i).isChecked()) !== want) want ? await boxes.nth(i).check() : await boxes.nth(i).uncheck();
  }
}
/** Sends a question and waits for the assistant turn to settle. Returns the visible status and seconds. */
async function ask(label, question, shot) {
  const before = await page.locator("[data-role='assistant'], article, [class*='assistant']").count().catch(() => 0);
  const box = page.getByPlaceholder(/ask about/i);
  await box.fill(question);
  const started = Date.now();
  await page.getByRole("button", { name: "Send question" }).click();
  let outcome = "timeout";
  const deadline = Date.now() + 170000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(1500);
    const text = await page.locator("main").innerText();
    if (/research service is unavailable|could not answer|Service unavailable|daily limit|question limit|Many people/i.test(text.slice(-1500))) { outcome = "error"; break; }
    if (/Coverage|Cobertura|SQL and result|could not find|Not enough evidence|Sem evid/i.test(text.slice(-4000))) {
      const stillThinking = await page.getByText(/Searching|Thinking|Retrieving|Pensando/i).count();
      if (!stillThinking) { outcome = "answered"; break; }
    }
  }
  const seconds = Math.round((Date.now() - started) / 1000);
  const tail = (await page.locator("main").innerText()).replace(/\s+/g, " ").slice(-420);
  await page.screenshot({ path: `${OUT}/${shot}.png`, fullPage: true });
  log.push({ label, question, outcome, seconds, tail });
  console.log(label, outcome, seconds + "s");
}
async function fresh() {
  await page.getByRole("button", { name: /new research/i }).click();
  await page.waitForTimeout(500);
}

await open();
await select([0]);
await ask("PNCP text+vector", "Quais licitações de transporte escolar existem nos registros?", "01-pncp-text");
await fresh(); await select([1]);
await ask("PNCP SQL", "Which municipality signed the most contracts in 2025?", "02-pncp-sql");
await fresh(); await select([2]);
await ask("SIOPE SQL", "What was the median education investment per student in 2023, by region?", "03-siope-sql");
await fresh(); await select([0, 1, 2]);
await ask("combined 1", "Which municipality signed the most contracts in 2025?", "04-combined-1");
await ask("combined 2", "E sobre editais de merenda escolar, o que aparece nos registros?", "05-combined-2");
await ask("combined 3", "How many municipalities reported to SIOPE in 2024?", "06-combined-3");
// long conversation: follow-ups in one thread
await ask("long 4", "Resuma em uma frase o que você encontrou sobre merenda escolar.", "07-long-4");
await ask("long 5", "Which region had the highest median investment per student in 2023?", "08-long-5");
await ask("long 6", "Quais editais de uniforme escolar existem?", "09-long-6");
await ask("long 7", "What is the capital of France?", "10-off-topic");

const ok = log.filter((l) => l.outcome === "answered").length;
writeFileSync(`${OUT}/results.json`, JSON.stringify({ chat: CHAT, at: new Date().toISOString(), answered: ok, total: log.length, log }, null, 1));
console.log(`answered ${ok}/${log.length}`);
await browser.close();
