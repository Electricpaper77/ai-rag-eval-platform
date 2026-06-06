const path = require("path");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright");

const projectRoot = path.resolve(__dirname, "..");
const siteUrl = pathToFileURL(path.join(projectRoot, "index.html")).href;
const viewports = [
  { name: "mobile-375", width: 375, height: 812 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 1000 },
];

async function inspectViewport(browser, viewport) {
  const page = await browser.newPage({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });
  const consoleErrors = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(siteUrl, { waitUntil: "load" });

  const state = await page.evaluate(() => {
    const ctaLabels = [
      "View GitHub",
      "View Proof Artifacts",
      "Contact Me",
      "LinkedIn",
      "Email",
      "Project Walkthrough",
    ];
    const aboveFoldSelectors = {
      projectName: "h1",
      metrics: ".proof-bar",
      githubCta: ".hero-actions .primary",
      proofCta: ".hero-actions a[href='#proof']",
      pitch: ".hero-pitch",
    };
    const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id);
    const duplicateIds = Array.from(new Set(ids.filter((id, index) => ids.indexOf(id) !== index)));
    const localAnchors = Array.from(document.querySelectorAll("a[href^='#']"))
      .map((anchor) => anchor.getAttribute("href").slice(1))
      .filter(Boolean);
    const missingLocalAnchors = Array.from(
      new Set(localAnchors.filter((id) => !document.getElementById(id))),
    );

    return {
      title: document.title,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      proofMetrics: document.querySelectorAll(".proof-bar-metrics > div").length,
      artifactCards: document.querySelectorAll(".artifact-grid .artifact-card").length,
      loadedArtifactImages: Array.from(document.querySelectorAll(".artifact-card img")).filter(
        (image) => image.complete && image.naturalWidth > 0,
      ).length,
      workflowCards: document.querySelectorAll("#architecture .pipeline > li").length,
      liveConsoleExists: Boolean(document.getElementById("live-eval-console")),
      liveConsoleButtons: document.querySelectorAll(".live-console-tab").length,
      liveConsoleJsonlPreviewExists: Boolean(document.getElementById("live-console-jsonl")),
      githubEvidenceRoute: document
        .querySelector(".live-console-footer a")
        ?.getAttribute("href"),
      duplicateIds,
      missingLocalAnchors,
      ctaRoutes: Object.fromEntries(
        ctaLabels.map((label) => {
          const links = Array.from(document.querySelectorAll("a")).filter(
            (item) => item.textContent.trim() === label,
          );
          return [label, Array.from(new Set(links.map((item) => item.getAttribute("href"))))];
        }),
      ),
      aboveFold: Object.fromEntries(
        Object.entries(aboveFoldSelectors).map(([name, selector]) => {
          const element = document.querySelector(selector);
          if (!element) return [name, false];
          const rect = element.getBoundingClientRect();
          return [name, rect.top < window.innerHeight && rect.bottom > 0];
        }),
      ),
    };
  });

  await page.locator(".hero-actions a[href='#proof']").click();
  const proofAnchorWorks = new URL(page.url()).hash === "#proof";
  await page.locator("a[href='#walkthrough']").last().click();
  const walkthroughAnchorWorks = new URL(page.url()).hash === "#walkthrough";
  const liveConsoleRuns = [];
  for (const scenario of ["rag", "injection", "pii"]) {
    const tab = page.locator(`[data-console-scenario='${scenario}']`);
    await tab.click();
    liveConsoleRuns.push({
      scenario,
      selected: (await tab.getAttribute("aria-selected")) === "true",
      jsonl: await page.locator("#live-console-jsonl").textContent(),
      status: await page.locator("#live-console-status").textContent(),
    });
  }
  await page.close();

  return {
    viewport: viewport.name,
    ...state,
    proofAnchorWorks,
    walkthroughAnchorWorks,
    liveConsoleRuns,
    consoleErrors,
  };
}

function assertResult(result) {
  const failures = [];
  if (result.scrollWidth !== result.clientWidth) failures.push("horizontal overflow");
  if (result.proofMetrics !== 5) failures.push("proof metric count");
  if (result.artifactCards !== 6 || result.loadedArtifactImages !== 6) {
    failures.push("proof artifact assets");
  }
  if (result.workflowCards !== 4) failures.push("workflow card count");
  if (!result.liveConsoleExists) failures.push("live console section");
  if (result.liveConsoleButtons !== 3) failures.push("live console scenario buttons");
  if (!result.liveConsoleJsonlPreviewExists) failures.push("live console JSONL preview");
  if (result.githubEvidenceRoute !== "https://github.com/Electricpaper77/ai-rag-eval-platform") {
    failures.push("GitHub evidence CTA");
  }
  if (result.duplicateIds.length) failures.push("duplicate IDs");
  if (result.missingLocalAnchors.length) failures.push("missing local anchors");
  if (
    result.liveConsoleRuns.length !== 3 ||
    result.liveConsoleRuns.some(
      (run) => !run.selected || !run.jsonl?.includes('"case_id"') || run.status?.trim() !== "PASS",
    )
  ) {
    failures.push("live console scenario switching");
  }
  if (!Object.values(result.aboveFold).every(Boolean)) failures.push("above-fold content");
  if (!result.proofAnchorWorks || !result.walkthroughAnchorWorks) failures.push("anchor routing");
  if (result.consoleErrors.length) failures.push("console errors");

  for (const [label, routes] of Object.entries(result.ctaRoutes)) {
    if (!routes.length || routes.includes(null)) failures.push(`${label} route`);
  }

  if (failures.length) {
    throw new Error(`${result.viewport} failed: ${failures.join(", ")}`);
  }
}

(async () => {
  const launchOptions = { headless: true };
  if (process.env.BROWSER_PATH) launchOptions.executablePath = process.env.BROWSER_PATH;
  if (process.env.PLAYWRIGHT_CHANNEL) launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL;

  const browser = await chromium.launch(launchOptions);
  const results = [];

  for (const viewport of viewports) {
    const result = await inspectViewport(browser, viewport);
    assertResult(result);
    results.push(result);
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
