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
      liveConsoleExists:
        document.querySelector("#live-eval-console h2")?.textContent.trim() ===
        "Live Eval Console",
      liveEvalSimulatorAbsent: !document.body.textContent.includes("Live Eval Simulator"),
      liveConsoleSubtitle:
        document.querySelector("#live-eval-console .section-note")?.textContent
          .replace(/\s+/g, " ")
          .trim() ===
        "Select a reliability scenario and inspect the gates used before releasing a GenAI workflow to production.",
      liveConsoleDisclosure:
        document.querySelector("#live-eval-console .simulator-disclosure")?.textContent
          .replace(/\s+/g, " ")
          .trim() ===
        "Static demo data mirrors deterministic repository fixtures and JSONL proof artifacts; this browser demo is not connected to a backend.",
      liveConsoleHeadingCount: Array.from(document.querySelectorAll("h2")).filter(
        (heading) => heading.textContent.trim() === "Live Eval Console",
      ).length,
      evalTraceExists:
        document.querySelector("#eval-trace-title")?.textContent.trim() ===
        "Eval Trace Timeline",
      liveConsoleButtons: Array.from(
        document.querySelectorAll("#live-eval-console .simulator-tab"),
      ).map((button) => button.textContent.trim()),
      platformNameExists: document.body.textContent.includes("AI Agent Reliability Platform"),
      demoNavTargetsConsole:
        document.querySelector(".nav-links a[href='#live-eval-console']")?.textContent.trim() ===
        "Demo",
      liveConsoleJsonlPreviewExists: Boolean(document.getElementById("simulator-json")),
      executiveProofExists:
        document.querySelector("#executive-proof h2")?.textContent.trim() ===
        "Executive Proof Mode",
      executiveProofCards: document.querySelectorAll(
        "#executive-proof .executive-proof-card",
      ).length,
      executiveMetricStripExists: Boolean(
        document.querySelector("#executive-proof .executive-metric-strip"),
      ),
      executivePitchExists:
        document.querySelector("#executive-proof .executive-pitch h3")?.textContent.trim() ===
        "60-second interview pitch",
      copyProjectPitchButtonExists:
        document.querySelector("#copy-project-pitch")?.textContent.trim() ===
        "Copy Project Pitch",
      applicationPackageExists:
        document.querySelector("#application-package")?.getAttribute("aria-label") ===
        "Application Package",
      applicationPackageCards: document.querySelectorAll(
        "#application-package .application-package-card",
      ).length,
      applicationPackageTitles: Array.from(
        document.querySelectorAll("#application-package .application-package-card h3"),
      ).map((heading) => heading.textContent.trim()),
      applicationCopyButtons: Array.from(
        document.querySelectorAll("#application-package .application-copy-button"),
      ).map((button) => button.textContent.trim()),
      applicationVerificationItems: document.querySelectorAll(
        "#application-package .application-verification li",
      ).length,
      applicationPackagePlacement: (() => {
        const executiveProof = document.getElementById("executive-proof");
        const applicationPackage = document.getElementById("application-package");
        const contact = document.getElementById("contact");
        return Boolean(
          executiveProof &&
            applicationPackage &&
            contact &&
            executiveProof.compareDocumentPosition(applicationPackage) &
              Node.DOCUMENT_POSITION_FOLLOWING &&
            applicationPackage.compareDocumentPosition(contact) &
              Node.DOCUMENT_POSITION_FOLLOWING,
        );
      })(),
      proofIntegrityExists:
        document.querySelector("#proof-integrity")?.getAttribute("aria-label") ===
        "Proof Integrity Layer",
      proofIntegrityTitle:
        document.querySelector("#proof-integrity h2")?.textContent.trim() ===
        "Reproducible proof, not a one-off demo",
      integrityCards: document.querySelectorAll("#proof-integrity .integrity-card").length,
      evidenceFlowExists:
        document.querySelector("#evidence-flow-title")?.textContent.trim() === "Evidence Flow",
      evidenceFlowSteps: document.querySelectorAll("#proof-integrity .evidence-flow li").length,
      integrityRecordExists:
        document.querySelector("#proof-integrity .integrity-console h3")?.textContent.trim() ===
        "Example integrity record",
      integrityRecordHasFixtureHash:
        document.getElementById("integrity-record")?.textContent.includes('"fixture_hash"') ?? false,
      passReviewExists: document.body.textContent.includes("PASS / REVIEW"),
      proofIntegrityPlacement: (() => {
        const applicationPackage = document.getElementById("application-package");
        const proofIntegrity = document.getElementById("proof-integrity");
        const contact = document.getElementById("contact");
        return Boolean(
          applicationPackage &&
            proofIntegrity &&
            contact &&
            applicationPackage.compareDocumentPosition(proofIntegrity) &
              Node.DOCUMENT_POSITION_FOLLOWING &&
            proofIntegrity.compareDocumentPosition(contact) &
              Node.DOCUMENT_POSITION_FOLLOWING,
        );
      })(),
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
  await page.locator(".nav-links a[href='#live-eval-console']").evaluate((anchor) => anchor.click());
  const demoAnchorWorks = new URL(page.url()).hash === "#live-eval-console";
  const demoAnchorLandsOnConsole = await page.locator("#live-eval-console h2").evaluate((heading) => {
    const rect = heading.getBoundingClientRect();
    return rect.top >= 0 && rect.top < window.innerHeight;
  });
  await page.locator("a[href='#walkthrough']").last().click();
  const walkthroughAnchorWorks = new URL(page.url()).hash === "#walkthrough";
  const liveConsoleRuns = [];
  for (const scenario of ["rag", "citation", "injection"]) {
    const tab = page.locator(`[data-scenario='${scenario}']`);
    await tab.click();
    liveConsoleRuns.push({
      scenario,
      selected: (await tab.getAttribute("aria-selected")) === "true",
      jsonl: await page.locator("#simulator-json").textContent(),
      status: await page.locator("#simulator-status").textContent(),
      risk: await page.locator("#simulator-risk").textContent(),
      traceSteps: await page.locator("#simulator-trace > li").count(),
      traceBadges: await page.locator("#simulator-trace .trace-badge").count(),
    });
  }
  await page.locator("#copy-project-pitch").click();
  await page.waitForFunction(
    () => document.getElementById("project-pitch-status")?.textContent.trim() === "Copied",
  );
  const projectPitchCopyStatus = (
    await page.locator("#project-pitch-status").textContent()
  )?.trim();
  const applicationCopyRuns = [];
  const applicationButtons = page.locator(".application-copy-button");
  for (let index = 0; index < (await applicationButtons.count()); index += 1) {
    const button = applicationButtons.nth(index);
    const statusId = await button.getAttribute("data-status-target");
    await button.click();
    await page.waitForFunction(
      (id) => document.getElementById(id)?.textContent.trim() === "Copied",
      statusId,
    );
    applicationCopyRuns.push({
      label: (await button.textContent())?.trim(),
      status: (await page.locator(`#${statusId}`).textContent())?.trim(),
    });
  }
  await page.close();

  return {
    viewport: viewport.name,
    ...state,
    proofAnchorWorks,
    demoAnchorWorks,
    demoAnchorLandsOnConsole,
    walkthroughAnchorWorks,
    liveConsoleRuns,
    projectPitchCopyStatus,
    applicationCopyRuns,
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
  if (!result.liveEvalSimulatorAbsent) failures.push("retired live eval simulator naming");
  if (!result.liveConsoleSubtitle) failures.push("live console subtitle");
  if (!result.liveConsoleDisclosure) failures.push("live console disclosure");
  if (result.liveConsoleHeadingCount !== 1) failures.push("single live console heading");
  if (!result.platformNameExists) failures.push("platform naming");
  if (!result.demoNavTargetsConsole) failures.push("demo navigation target");
  if (!result.evalTraceExists) failures.push("eval trace timeline");
  if (
    JSON.stringify(result.liveConsoleButtons) !==
    JSON.stringify([
      "RAG Citation Check",
      "Citation Failure Case",
      "Prompt Injection Defense",
    ])
  ) {
    failures.push("live console scenario buttons");
  }
  if (!result.liveConsoleJsonlPreviewExists) failures.push("live console JSONL preview");
  if (!result.executiveProofExists) failures.push("executive proof section");
  if (result.executiveProofCards !== 5) failures.push("executive proof cards");
  if (!result.executiveMetricStripExists) failures.push("executive metric strip");
  if (!result.executivePitchExists) failures.push("executive interview pitch");
  if (!result.copyProjectPitchButtonExists) failures.push("copy project pitch button");
  if (result.projectPitchCopyStatus !== "Copied") failures.push("project pitch copy behavior");
  if (!result.applicationPackageExists) failures.push("application package section");
  if (result.applicationPackageCards !== 4) failures.push("application package cards");
  if (
    JSON.stringify(result.applicationPackageTitles) !==
    JSON.stringify(["Resume Bullet", "Recruiter Summary", "Interview Pitch", "Role Match"])
  ) {
    failures.push("application package card titles");
  }
  if (
    JSON.stringify(result.applicationCopyButtons) !==
    JSON.stringify([
      "Copy Resume Bullet",
      "Copy Recruiter Summary",
      "Copy Interview Pitch",
      "Copy Role Match",
    ])
  ) {
    failures.push("application package copy buttons");
  }
  if (result.applicationVerificationItems !== 6) {
    failures.push("application verification checklist");
  }
  if (!result.applicationPackagePlacement) failures.push("application package placement");
  if (
    result.applicationCopyRuns.length !== 4 ||
    result.applicationCopyRuns.some((run) => run.status !== "Copied")
  ) {
    failures.push("application package copy behavior");
  }
  if (!result.proofIntegrityExists) failures.push("proof integrity section");
  if (!result.proofIntegrityTitle) failures.push("proof integrity title");
  if (result.integrityCards !== 4) failures.push("proof integrity cards");
  if (!result.evidenceFlowExists || result.evidenceFlowSteps !== 7) {
    failures.push("evidence flow");
  }
  if (!result.integrityRecordExists) failures.push("example integrity record");
  if (!result.integrityRecordHasFixtureHash) failures.push("fixture hash record");
  if (!result.passReviewExists) failures.push("PASS / REVIEW status language");
  if (!result.proofIntegrityPlacement) failures.push("proof integrity placement");
  if (result.duplicateIds.length) failures.push("duplicate IDs");
  if (result.missingLocalAnchors.length) failures.push("missing local anchors");
  if (
    result.liveConsoleRuns.length !== 3 ||
    result.liveConsoleRuns.some(
      (run) =>
        !run.selected ||
        !run.jsonl?.includes('"case_id"') ||
        run.traceSteps !== 5 ||
        run.traceBadges !== 5,
    ) ||
    !result.liveConsoleRuns.find((run) => run.scenario === "rag")?.jsonl.includes("rag_citation_014") ||
    !result.liveConsoleRuns
      .find((run) => run.scenario === "citation")
      ?.jsonl.includes("rag_citation_021") ||
    !result.liveConsoleRuns
      .find((run) => run.scenario === "injection")
      ?.jsonl.includes("security_injection_007") ||
    !result.liveConsoleRuns.some((run) => run.status?.trim() === "PASS") ||
    !result.liveConsoleRuns.some((run) => run.status?.trim() === "REVIEW") ||
    !result.liveConsoleRuns.some((run) => run.risk?.trim() === "LOW RISK") ||
    !result.liveConsoleRuns.some((run) => run.risk?.trim() === "MEDIUM RISK")
  ) {
    failures.push("live console scenario switching");
  }
  if (!Object.values(result.aboveFold).every(Boolean)) failures.push("above-fold content");
  if (!result.proofAnchorWorks || !result.demoAnchorWorks || !result.walkthroughAnchorWorks) {
    failures.push("anchor routing");
  }
  if (!result.demoAnchorLandsOnConsole) failures.push("demo anchor position");
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
