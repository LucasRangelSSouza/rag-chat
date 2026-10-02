import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const readyHealth = {
  status: "ready",
  corpus_name: "PNCP",
  release_version: "1",
  data_cutoff: "2026-07-31",
  table_count: 47,
  record_count: 125000,
  model_status: "ready",
  corpora: [
    { id: "pncp", label: "PNCP procurement", release_version: "v1", data_cutoff: "2026-07-31", record_count: 125000 },
    { id: "siope", label: "SIOPE education finance", release_version: "v1", data_cutoff: "2025-12-31", record_count: 27830 },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: readyHealth }));
});

test("shows a bounded research workspace while the release is pending", async ({ page, isMobile }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: {
    status: "pending", corpus_name: "PNCP", model_status: "unavailable",
  } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Ask the record/i })).toBeVisible();
  if (!isMobile) await expect(page.getByText("Release pending").first()).toBeVisible();
  await expect(page.getByRole("textbox", { name: /Ask a question/i })).toBeDisabled();
  await expect(page.getByText("The public chat opens after the complete catalogue is pinned and verified.")).toBeVisible();
});

test("sends a question and shows exact source provenance", async ({ page, isMobile }) => {
  await page.route("**/api/answer", (route) => route.fulfill({ json: {
    status: "answered",
    answer: "Four records list school transport services. [record-2026-0004]",
    citations: [{
      title: "Semantic procurement notices",
      source_uri: "https://www.kaggle.com/datasets/lucasrangelss/pncp-semantic-editais-semantico",
      dataset: { slug: "lucasrangelss/pncp-semantic-editais-semantico", version: 3, manifest_sha256: "abc" },
      record_ids: ["record-2026-0004"],
      chunk_id: "record-2026-0004#c000",
    }],
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: /What procurement notices include school transport services/i }).click();
  await expect(page.getByText("Four records list school transport services.")).toBeVisible();
  await expect(page.getByText("record-2026-0004").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Open source/i }).first()).toHaveAttribute(
    "href", "https://www.kaggle.com/datasets/lucasrangelss/pncp-semantic-editais-semantico/versions/3",
  );
  await expect(page.locator(".inline-citations").first()).toBeVisible();
  void isMobile;
});

test("keeps the answer in the visitor's question language", async ({ page }) => {
  await page.route("**/api/answer", (route) => route.fulfill({ json: {
    status: "answered",
    answer: "Encontrei dois editais com essa descrição. [record-pt-02]",
    citations: [{ title: "Semantic procurement notices", source_uri: "https://www.kaggle.com/datasets/lucasrangelss/pncp-semantic-editais-semantico", record_ids: ["record-pt-02"] }],
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: /Quais editais de material escolar/i }).click();
  await expect(page.getByText("Encontrei dois editais com essa descrição.")).toBeVisible();
});

test("reports service failures without losing the visitor's question", async ({ page }) => {
  await page.route("**/api/answer", (route) => route.fulfill({ status: 503, json: { error: "The research service is unavailable. Try again shortly." } }));
  await page.goto("/");
  const question = "Quais editais de material escolar foram publicados em 2026?";
  await page.getByRole("textbox", { name: /Ask a question/i }).fill(question);
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".message--user").getByText(question)).toBeVisible();
  await expect(page.getByText("The research service is unavailable. Try again shortly.").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Try again/i })).toBeVisible();
});

test("uses Enter to send and Shift+Enter to keep a line break", async ({ page }) => {
  await page.route("**/api/answer", async (route) => {
    const request = route.request();
    const payload = request.postDataJSON();
    await route.fulfill({ json: { status: "abstained", answer: `No released record supports: ${payload.question}`, citations: [] } });
  });
  await page.goto("/");
  const composer = page.getByRole("textbox", { name: /Ask a question/i });
  await composer.fill("What is a PNCP record?");
  await composer.press("Shift+Enter");
  await expect(composer).toHaveValue("What is a PNCP record?\n");
  await composer.fill("What is a PNCP record?");
  await composer.press("Enter");
  await expect(page.getByText("No released record supports: What is a PNCP record?")).toBeVisible();
});

test("keeps the layout within the viewport from phone to wide desktop", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  for (const width of [320, 375, 430, 768, 1024, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole("heading", { name: /Ask the record/i })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow, `horizontal overflow at ${width}px`).toBe(false);
    if (width === 320 || width === 1440) {
      await page.screenshot({ path: `test-results/chat-${width}.png`, fullPage: true });
    }
  }
});

test("keeps the composer prompt readable at the narrowest mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/");
  const composer = page.getByRole("textbox", { name: /Ask a question/i });
  await expect(composer).toBeVisible();
  await expect(composer).toHaveCSS("min-height", "48px");
  const box = await composer.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(48);
});

test("opens and closes the mobile navigation and passes axe checks", async ({ page, isMobile }) => {
  await page.goto("/");
  if (isMobile) {
    const open = page.getByRole("button", { name: "Open navigation" });
    await open.click();
    await expect(page.getByRole("complementary", { name: "Research navigation" })).toBeVisible();
    await page.getByRole("complementary", { name: "Research navigation" }).getByRole("button", { name: "Close navigation" }).click();
  }
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
});

test("conversation history: new research, reopen, persist across reload, delete", async ({ page, isMobile }) => {
  let calls = 0;
  await page.route("**/api/answer", (route) => {
    calls += 1;
    return route.fulfill({ json: {
      status: "answered",
      answer: `Answer number ${calls}. [record-${calls}]`,
      citations: [{ title: "Semantic procurement notices", source_uri: "https://www.kaggle.com/datasets/lucasrangelss/x", record_ids: [`record-${calls}`] }],
    } });
  });
  await page.goto("/");
  const box = page.getByRole("textbox", { name: /Ask a question/i });
  const openMenu = async () => { if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click(); };

  await box.fill("First question about school meals");
  await box.press("Enter");
  await expect(page.getByText("Answer number 1.")).toBeVisible();

  await openMenu();
  const history = page.getByRole("navigation", { name: "Conversation history" });
  await expect(history.getByRole("button", { name: "First question about school meals", exact: true })).toBeVisible();

  await page.getByRole("button", { name: /New chat/i }).click();
  await expect(page.getByRole("heading", { name: /Ask the record/i })).toBeVisible();
  await expect(page.getByText("Answer number 1.")).toHaveCount(0);

  await box.fill("Second question about transport");
  await box.press("Enter");
  await expect(page.getByText("Answer number 2.")).toBeVisible();

  await openMenu();
  await expect(history.getByRole("button")).toHaveCount(4); // two conversations, each with an open and a delete button

  await history.getByRole("button", { name: "First question about school meals", exact: true }).click();
  await expect(page.getByText("Answer number 1.")).toBeVisible();
  await expect(page.getByText("Answer number 2.")).toHaveCount(0);

  await page.reload();
  await openMenu();
  await expect(history.getByRole("button", { name: "Second question about transport", exact: true })).toBeVisible();

  await history.getByRole("button", { name: /Delete conversation: Second question about transport/ }).click();
  await expect(history.getByRole("button", { name: "Second question about transport", exact: true })).toHaveCount(0);
  await expect(history.getByRole("button", { name: "First question about school meals", exact: true })).toBeVisible();
});


test("research bases: checkboxes choose what is searched, none means an unsourced answer", async ({ page, isMobile }) => {
  const bodies: Array<{ question: string; corpora: string[] }> = [];
  await page.route("**/api/answer", (route) => {
    bodies.push(route.request().postDataJSON());
    return route.fulfill({ json: { status: "answered", answer: "ok", citations: [], grounded: bodies.at(-1)!.corpora.length > 0 } });
  });
  await page.goto("/");
  if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  const pncp = page.getByRole("checkbox", { name: /PNCP procurement/ });
  const siope = page.getByRole("checkbox", { name: /SIOPE education finance/ });
  await expect(pncp).toBeChecked();
  await expect(siope).not.toBeChecked();
  await siope.check({ force: true });
  await expect(page.getByText("Answers cite records from all selected bases.")).toBeVisible();
  if (isMobile) await page.locator(".sidebar__close").click();
  const box = page.getByRole("textbox", { name: /Ask a question/i });
  await box.fill("first");
  await box.press("Enter");
  await expect(page.getByText("ok").first()).toBeVisible();
  expect(bodies[0].corpora.sort()).toEqual(["pncp", "siope"]);

  if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  await pncp.uncheck({ force: true });
  await siope.uncheck({ force: true });
  await expect(page.getByText("No base selected: answers are not sourced.")).toBeVisible();
  if (isMobile) await page.locator(".sidebar__close").click();
  await box.fill("second");
  await box.press("Enter");
  await expect(page.getByText("No sources used")).toBeVisible();
  expect(bodies[1].corpora).toEqual([]);

  await page.reload();
  if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("checkbox", { name: /PNCP procurement/ })).not.toBeChecked();  // the empty choice persists
});
