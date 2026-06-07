const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright");

const projectRoot = path.resolve(__dirname, "..");
const siteUrl = pathToFileURL(path.join(projectRoot, "index.html")).href;
const deploymentUrl = pathToFileURL(path.join(projectRoot, "frontend", "index.html")).href;
const resumeRelativePath = "assets/Zohaib_Ahmed_AI_Solutions_Engineer_GenAI_Resume.pdf";
const resumePath = path.join(projectRoot, resumeRelativePath);
const deploymentResumePath = path.join(projectRoot, "frontend", resumeRelativePath);
const faviconRelativePath = "assets/favicon.svg";
const faviconPath = path.join(projectRoot, faviconRelativePath);
const deploymentFaviconPath = path.join(projectRoot, "frontend", faviconRelativePath);
const recruiterConversionText =
  "AI Solutions Engineer candidate | LLM Evaluation • RAG Reliability • Agent Guardrails";
const strongestResumeBullet =
  "Built a FastAPI-based agent reliability and LLM evaluation platform with JSONL audit artifacts, Prometheus metrics, replay validation, governance workflows, and automated regression testing; achieved 87% eval pass rate, 43 req/sec throughput, p95 270ms latency, 99%+ workflow success, and reduced hallucination rate from 18% to 6%.";
const recruiterConversionLabels = [
  "Download Resume",
  "Copy Resume Bullet",
  "Contact",
];
const headerActionLabels = ["Download Resume", "View GitHub"];
const heroActionLabels = ["View GitHub", "Download Resume", "See Proof Artifacts"];
const reviewPathLabels = ["Resume", "Proof Artifacts", "Live Eval Console", "Contact"];
const proofSummary =
  "Built to demonstrate production-readiness for GenAI systems: deterministic eval fixtures, JSONL audit logs, guardrails, regression checks, and measurable RAG reliability metrics.";
const recruiterActionSubtitle =
  "For AI Solutions Engineer, LLM Evaluation, Forward Deployed AI, and Applied GenAI roles.";
const recruiterActionTitles = [
  "Download resume",
  "Inspect proof artifacts",
  "Review Live Eval Console",
  "Contact candidate",
];
const recruiterActionButtonLabels = [
  "Download Resume",
  "View Proof Artifacts",
  "View Demo",
  "Contact Me",
];
const recruiterAvailability =
  "Available for Bay Area hybrid and remote AI Solutions Engineer / LLM Evaluation roles.";
const hiringSummary =
  "Zohaib Ahmed is targeting AI Solutions Engineer, LLM Evaluation, Forward Deployed AI, and Applied GenAI roles. His AI Agent Reliability Platform demonstrates RAG evaluation, JSONL audit logs, guardrails, pytest regression checks, Prometheus-style metrics, and production-readiness validation.";
const staleDemoStrings = [
  "Live Eval " + "Simulator",
  "Good " + "Answer",
  "Missing " + "Citation",
  "Unsafe " + "Request",
  "Select a sample " + "AI output",
  "Fixed sample scenarios " + "demonstrate",
  "AI RAG " + "Eval Site",
];
const viewports = [
  { name: "mobile-375", width: 375, height: 812 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 1000 },
];
const agentTraceStepTitles = [
  "User request",
  "Planner",
  "Retriever",
  "Guardrail",
  "Evaluation gates",
  "JSONL audit export",
];
const employerProofPathText =
  "Employer proof path: Resume \u2192 GitHub \u2192 Live Eval \u2192 Agent Flow \u2192 Trace Replay \u2192 Contact";
const employerProofPathLabels = [
  "Resume",
  "GitHub",
  "Live Eval",
  "Agent Flow",
  "Trace Replay",
  "Contact",
];
const recruiterReviewRows = [
  ["Role fit", "AI Solutions Engineer / LLM Evaluation / Applied GenAI"],
  ["Proof", "GitHub repo, resume PDF, JSONL logs, eval dashboard, trace replay"],
  ["Stack", "Python, FastAPI, RAG, vector search, LLM evals, guardrails, Docker, CI/CD"],
  [
    "Signal",
    "Production-readiness, measurable reliability metrics, customer-facing explanation",
  ],
];
const recruiterReadyResumeBullet =
  "Built a FastAPI-based AI Agent Reliability Platform for evaluating RAG and LLM outputs across hallucination risk, citation quality, refusal behavior, prompt injection, and PII handling using deterministic eval fixtures, JSONL audit logs, regression checks, and trace replay proof artifacts.";
const employerValueBullets = [
  "Tests LLM outputs with deterministic eval fixtures, JSONL audit logs, and regression checks.",
  "Measures hallucination risk, citation quality, refusal behavior, prompt injection handling, and PII protection.",
  "Demonstrates customer-facing AI reliability work: explainable outputs, trace replay, proof artifacts, and production-readiness checks.",
  "Maps directly to AI Solutions Engineer, Forward Deployed Engineer, LLM Evaluation, and Applied GenAI roles.",
];
const agentTraceCtaLabels = ["Download Resume", "View GitHub", "Contact"];
const agentFlowStepLabels = [
  "User prompt",
  "RAG retrieval",
  "Guardrail scan",
  "Evaluation harness",
  "JSONL + trace replay",
];
const agentFlowStepStatuses = [
  "Input received",
  "Context prepared",
  "Safe to answer",
  "Eval passed",
  "Proof ready",
];
const agentFlowProductionBullets = [
  "Makes AI behavior inspectable instead of subjective.",
  "Converts prompt testing into repeatable eval evidence.",
  "Helps teams debug failed RAG answers, unsafe outputs, and citation gaps.",
  "Creates proof artifacts hiring managers can verify in GitHub, screenshots, and live demos.",
];
const agentFlowResumeBullet =
  "Built an agentic AI reliability workflow that evaluates RAG outputs from prompt intake through retrieval, guardrail scanning, LLM scoring, JSONL audit logging, and trace replay, producing inspectable proof artifacts for hallucination risk, citation precision, PII handling, and regression safety.";
const agentFlowCtaLabels = ["View GitHub", "Download Resume", "Jump to Trace Replay"];

function findStaleTrackedStrings() {
  const textExtensions = new Set([
    ".cjs",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
  ]);
  const trackedFiles = execFileSync("git", ["ls-files"], {
    cwd: projectRoot,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean);
  const matches = [];

  for (const relativePath of trackedFiles) {
    if (!textExtensions.has(path.extname(relativePath).toLowerCase())) continue;
    const absolutePath = path.join(projectRoot, relativePath);
    const content = fs.readFileSync(absolutePath, "utf8");
    for (const staleString of staleDemoStrings) {
      if (content.includes(staleString)) matches.push({ file: relativePath, staleString });
    }
  }

  return matches;
}

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
      "See Proof Artifacts",
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
    const recruiterConversion = document.querySelector(".recruiter-conversion");
    const recruiterConversionRect = recruiterConversion?.getBoundingClientRect();
    const headerRect = document.querySelector(".site-header")?.getBoundingClientRect();

    return {
      title: document.title,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      faviconHref: document.querySelector("link[rel='icon']")?.getAttribute("href"),
      recruiterConversionCount: document.querySelectorAll(".recruiter-conversion").length,
      recruiterConversionText: recruiterConversion
        ?.querySelector("p")
        ?.textContent.replace(/\s+/g, " ")
        .trim(),
      recruiterConversionButtons: Array.from(
        recruiterConversion?.querySelectorAll(".conversion-button") ?? [],
      ).map((element) => ({
        label: element.textContent.trim(),
        tagName: element.tagName,
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      recruiterConversionSticky:
        recruiterConversion && getComputedStyle(recruiterConversion).position === "sticky",
      recruiterConversionBelowHeader:
        recruiterConversionRect && headerRect
          ? recruiterConversionRect.top >= headerRect.bottom - 1
          : false,
      strongestResumeBullet:
        document.getElementById("resume-strongest-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      headerActions: Array.from(document.querySelectorAll(".header-actions .button")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      heroActions: Array.from(document.querySelectorAll(".hero-actions .button")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      reviewPathText:
        document.querySelector(".hero-review-path")?.textContent.replace(/\s+/g, " ").trim() ?? "",
      reviewPathLinks: Array.from(document.querySelectorAll(".hero-review-path a")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      employerProofPathCount: document.querySelectorAll(".employer-proof-path").length,
      employerProofPathText:
        document.querySelector(".employer-proof-path")?.textContent.replace(/\s+/g, " ").trim() ??
        "",
      employerProofPathSticky:
        document.querySelector(".employer-proof-path") &&
        getComputedStyle(document.querySelector(".employer-proof-path")).position === "sticky",
      employerProofPathLinks: Array.from(
        document.querySelectorAll(".employer-proof-path a"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      recruiterQuickReviewTitle:
        document.getElementById("recruiter-quick-review-title")?.textContent.trim() ?? "",
      recruiterReviewRows: Array.from(
        document.querySelectorAll("#recruiter-quick-review .recruiter-review-card dl > div"),
      ).map((row) => [
        row.querySelector("dt")?.textContent.trim() ?? "",
        row.querySelector("dd")?.textContent.replace(/\s+/g, " ").trim() ?? "",
      ]),
      recruiterReadyResumeBulletTitle:
        document.querySelector("#recruiter-quick-review .recruiter-bullet-card h2")?.textContent
          .trim() ?? "",
      recruiterReadyResumeBullet:
        document.getElementById("recruiter-ready-resume-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterReadyResumeBulletButton:
        document.querySelector(".recruiter-bullet-copy-button")?.textContent.trim() ?? "",
      hiringSnapshot:
        document.querySelector(".hero-panel")?.getAttribute("aria-label") === "Hiring Snapshot" &&
        document.querySelector(".hero-panel .panel-kicker")?.textContent.trim() ===
          "Hiring Snapshot",
      validationSnapshotAbsent: !document.body.textContent
        .toLowerCase()
        .includes("validation snapshot"),
      proofSummary:
        document.querySelector(".hero-proof-summary")?.textContent.replace(/\s+/g, " ").trim() ??
        "",
      topFoldQuestionsAnswered: {
        what: Boolean(document.querySelector("h1")),
        role: Boolean(document.querySelector(".hero-panel .validation-list")),
        resume: Boolean(document.querySelector(".hero-actions a[href$='_Resume.pdf']")),
        proof: Boolean(document.querySelector(".hero-actions a[href='#proof']")),
        contact: Boolean(document.querySelector(".hero-review-path a[href='#contact']")),
      },
      recruiterActionCount: document.querySelectorAll("#recruiter-action-panel").length,
      recruiterActionEyebrow:
        document.querySelector("#recruiter-action-panel .eyebrow")?.textContent.trim() ?? "",
      recruiterActionTitle:
        document.querySelector("#recruiter-action-title")?.textContent.trim() ?? "",
      recruiterActionSubtitle:
        document.querySelector("#recruiter-action-panel .section-note")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterActionCards: Array.from(
        document.querySelectorAll("#recruiter-action-panel .recruiter-action-card"),
      ).map((card) => {
        const link = card.querySelector("a.button");
        return {
          title: card.querySelector("h3")?.textContent.trim() ?? "",
          label: link?.textContent.trim() ?? "",
          href: link?.getAttribute("href") ?? null,
          target: link?.getAttribute("target") ?? null,
          rel: link?.getAttribute("rel") ?? null,
        };
      }),
      recruiterAvailability:
        document.querySelector("#recruiter-action-panel .recruiter-action-footer > p")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      hiringSummary:
        document.getElementById("hiring-summary-copy-text")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterActionPlacement: (() => {
        const employerPath = document.querySelector(".hero")?.nextElementSibling;
        const quickReview = employerPath?.nextElementSibling;
        const recruiterAction = quickReview?.nextElementSibling;
        return Boolean(
          employerPath?.classList.contains("employer-proof-path") &&
            quickReview?.id === "recruiter-quick-review" &&
            recruiterAction?.id === "recruiter-action-panel" &&
            recruiterAction.nextElementSibling?.id === "resume-hub",
        );
      })(),
      proofMetrics: document.querySelectorAll(".proof-bar-metrics > div").length,
      artifactCards: document.querySelectorAll(".artifact-grid .artifact-card").length,
      loadedArtifactImages: Array.from(document.querySelectorAll(".artifact-card img")).filter(
        (image) => image.complete && image.naturalWidth > 0,
      ).length,
      workflowCards: document.querySelectorAll("#architecture .pipeline > li").length,
      resumeHubExists:
        document.querySelector("#resume-hub")?.getAttribute("aria-label") === "Resume Hub",
      resumeHubCount: document.querySelectorAll("#resume-hub").length,
      resumeHubTitle:
        document.querySelector("#resume-hub h2")?.textContent.trim() ===
        "AI Solutions Engineer resume + proof assets",
      resumeHubCards: document.querySelectorAll("#resume-hub .resume-hub-card").length,
      resumeHubCardTitles: Array.from(
        document.querySelectorAll("#resume-hub .resume-hub-card h3"),
      ).map((heading) => heading.textContent.trim()),
      resumeCopyButtons: Array.from(
        document.querySelectorAll("#resume-hub .resume-copy-button"),
      ).map((button) => button.textContent.trim()),
      recruiterVerificationExists:
        document.querySelector("#recruiter-verification-title")?.textContent.trim() ===
        "Recruiter Verification Path",
      recruiterVerificationSteps: document.querySelectorAll(
        "#resume-hub .recruiter-verification li",
      ).length,
      resumeMetricsMatch:
        document.getElementById("resume-proof-metrics")?.textContent
          .replace(/\s+/g, " ")
          .trim() ===
        "87% eval pass rate, 145+ passing tests, 43 req/sec throughput, p50 57ms / p95 270ms latency, 1,000+ automated evaluations, 99%+ workflow success, hallucination reduction from 18% to 6%.",
      resumeLinks: Array.from(
        document.querySelectorAll(
          `a[href='assets/Zohaib_Ahmed_AI_Solutions_Engineer_GenAI_Resume.pdf']`,
        ),
      ).map((link) => ({
        label: link.textContent.trim(),
        target: link.getAttribute("target"),
        rel: link.getAttribute("rel"),
      })),
      downloadResumeLinkExists: Array.from(
        document.querySelectorAll(
          `a[href='assets/Zohaib_Ahmed_AI_Solutions_Engineer_GenAI_Resume.pdf']`,
        ),
      ).some((link) => link.textContent.trim() === "Download Resume"),
      resumeCtasVisible: [".header-resume", ".hero-actions a[href$='_Resume.pdf']"].every(
        (selector) => {
          const element = document.querySelector(selector);
          if (!element) return false;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0
          );
        },
      ),
      resumeHubPlacement:
        document.getElementById("recruiter-action-panel")?.nextElementSibling?.id === "resume-hub",
      liveConsoleExists:
        document.querySelector("#live-eval-console h2")?.textContent.trim() ===
        "Live Eval Console",
      liveEvalSimulatorAbsent: !document.body.textContent.includes(
        ["Live Eval", "Simulator"].join(" "),
      ),
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
      agentFlowExists:
        document.querySelector("#agent-flow .eyebrow")?.textContent.trim() ===
          "AGENTIC RELIABILITY FLOW" &&
        document.getElementById("agent-flow-title")?.textContent.trim() ===
          "From prompt to proof: how the agent run is evaluated",
      agentFlowSubtitle:
        document.querySelector("#agent-flow .agent-flow-heading .section-note")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      agentFlowStepLabels: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-step-copy strong"),
      ).map((element) => element.textContent.trim()),
      agentFlowStepStatuses: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-status"),
      ).map((element) => element.textContent.trim()),
      agentFlowButtonsAccessible: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-step"),
      ).every(
        (button) =>
          button.tagName === "BUTTON" &&
          button.getAttribute("type") === "button" &&
          button.getAttribute("aria-controls") === "agent-flow-detail" &&
          button.hasAttribute("aria-pressed"),
      ),
      agentFlowDefaultStep:
        document.querySelector("#agent-flow .agent-flow-step.is-active")?.dataset.agentFlowStep ??
        "",
      agentFlowProductionTitle:
        document.getElementById("agent-flow-production-title")?.textContent.trim() ?? "",
      agentFlowProductionBullets: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-production li"),
      ).map((element) => element.textContent.replace(/\s+/g, " ").trim()),
      agentFlowResumeTitle:
        document.getElementById("agent-flow-resume-title")?.textContent.trim() ?? "",
      agentFlowResumeBullet:
        document.getElementById("agent-flow-resume-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      agentFlowCtaButtons: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-actions .button"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      agentFlowPlacement:
        document.getElementById("live-eval-console")?.nextElementSibling?.id === "agent-flow" &&
        document.getElementById("agent-flow")?.nextElementSibling?.id === "agent-trace-replay",
      agentTraceReplayExists:
        document.querySelector("#agent-trace-replay .eyebrow")?.textContent.trim() ===
          "AGENT TRACE REPLAY" &&
        document.querySelector("#agent-trace-replay-title")?.textContent.trim() ===
          "Replay an AI agent workflow with reliability gates",
      agentTraceStepTitles: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-step h3"),
      ).map((heading) => heading.textContent.trim()),
      agentTraceStatuses: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-badge"),
      ).map((badge) => badge.textContent.trim()),
      agentTraceJsonTitle:
        document.querySelector("#agent-trace-replay .agent-replay-console h3")?.textContent.trim() ??
        "",
      agentTraceJson: document.getElementById("agent-trace-json")?.textContent ?? "",
      agentTraceCtaTitle:
        document.querySelector("#agent-trace-replay .agent-replay-cta h3")?.textContent.trim() ?? "",
      agentTraceCtaButtons: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-actions .button"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      agentTracePlacement: (() => {
        const liveConsole = document.getElementById("live-eval-console");
        const agentFlow = document.getElementById("agent-flow");
        const agentTrace = document.getElementById("agent-trace-replay");
        const proofIntegrity = document.getElementById("proof-integrity");
        return Boolean(
          liveConsole?.nextElementSibling === agentFlow &&
            agentFlow?.nextElementSibling === agentTrace &&
            agentTrace &&
            proofIntegrity &&
            agentTrace.compareDocumentPosition(proofIntegrity) &
              Node.DOCUMENT_POSITION_FOLLOWING,
        );
      })(),
      employerValueTitle:
        document.getElementById("employer-value-title")?.textContent.trim() ?? "",
      employerValueBullets: Array.from(
        document.querySelectorAll("#proof .employer-value-card li"),
      ).map((item) => item.textContent.replace(/\s+/g, " ").trim()),
      employerValuePlacement: Boolean(
        document.querySelector("#proof > .employer-value-card"),
      ),
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
  await page
    .locator(".employer-proof-path a[href='#agent-flow']")
    .evaluate((anchor) => anchor.click());
  const agentFlowAnchorWorks = new URL(page.url()).hash === "#agent-flow";
  const agentFlowAnchorLandsOnSection = await page.locator("#agent-flow h2").evaluate((heading) => {
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
  const agentFlowRuns = [];
  for (const stage of ["prompt", "retrieval", "guardrail", "evaluation", "proof"]) {
    const button = page.locator(`[data-agent-flow-step='${stage}']`);
    await button.click();
    agentFlowRuns.push({
      stage,
      pressed: (await button.getAttribute("aria-pressed")) === "true",
      title: (await page.locator("#agent-flow-detail-title").textContent())?.trim(),
      status: (await page.locator("#agent-flow-detail-status").textContent())?.trim(),
      metrics: await page
        .locator("#agent-flow-detail-metrics > div")
        .evaluateAll((rows) =>
          rows.map((row) => [
            row.querySelector("dt")?.textContent.trim(),
            row.querySelector("dd")?.textContent.trim(),
          ]),
        ),
      json: await page.locator("#agent-flow-json").textContent(),
      hiring: (await page.locator("#agent-flow-hiring-relevance").textContent())
        ?.replace(/\s+/g, " ")
        .trim(),
    });
  }
  await page.locator("[data-agent-flow-step='prompt']").focus();
  await page.locator("[data-agent-flow-step='prompt']").press("End");
  const agentFlowKeyboardWorks =
    (await page.locator("[data-agent-flow-step='proof']").getAttribute("aria-pressed")) === "true" &&
    (await page.evaluate(() => document.activeElement?.dataset.agentFlowStep)) === "proof";
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
  const resumeCopyRuns = [];
  const resumeButtons = page.locator(".resume-copy-button");
  for (let index = 0; index < (await resumeButtons.count()); index += 1) {
    const button = resumeButtons.nth(index);
    const statusId = await button.getAttribute("data-status-target");
    await button.click();
    await page.waitForFunction(
      (id) => document.getElementById(id)?.textContent.trim() === "Copied",
      statusId,
    );
    resumeCopyRuns.push({
      label: (await button.textContent())?.trim(),
      status: (await page.locator(`#${statusId}`).textContent())?.trim(),
    });
  }
  await page.locator(".recruiter-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("recruiter-copy-status")?.textContent.trim() === "Copied",
  );
  const recruiterCopyStatus = (
    await page.locator("#recruiter-copy-status").textContent()
  )?.trim();
  await page.locator(".recruiter-bullet-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("recruiter-bullet-copy-status")?.textContent.trim() === "Copied",
  );
  const recruiterBulletCopyStatus = (
    await page.locator("#recruiter-bullet-copy-status").textContent()
  )?.trim();
  await page.locator(".agent-flow-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("agent-flow-copy-status")?.textContent.trim() === "Copied",
  );
  const agentFlowCopyStatus = (
    await page.locator("#agent-flow-copy-status").textContent()
  )?.trim();
  await page.locator(".hiring-summary-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("hiring-summary-copy-status")?.textContent.trim() === "Copied",
  );
  const hiringSummaryCopyStatus = (
    await page.locator("#hiring-summary-copy-status").textContent()
  )?.trim();
  await page.close();

  return {
    viewport: viewport.name,
    ...state,
    proofAnchorWorks,
    demoAnchorWorks,
    demoAnchorLandsOnConsole,
    agentFlowAnchorWorks,
    agentFlowAnchorLandsOnSection,
    walkthroughAnchorWorks,
    liveConsoleRuns,
    agentFlowRuns,
    agentFlowKeyboardWorks,
    projectPitchCopyStatus,
    applicationCopyRuns,
    resumeCopyRuns,
    recruiterCopyStatus,
    recruiterBulletCopyStatus,
    agentFlowCopyStatus,
    hiringSummaryCopyStatus,
    consoleErrors,
  };
}

async function inspectDeploymentViewport(browser, viewport) {
  const page = await browser.newPage({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });
  const consoleErrors = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(deploymentUrl, { waitUntil: "load" });
  const state = await page.evaluate(() => {
    const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id);
    const duplicateIds = Array.from(new Set(ids.filter((id, index) => ids.indexOf(id) !== index)));
    const localAnchors = Array.from(document.querySelectorAll("a[href^='#']"))
      .map((anchor) => anchor.getAttribute("href").slice(1))
      .filter(Boolean);
    const missingLocalAnchors = Array.from(
      new Set(localAnchors.filter((id) => !document.getElementById(id))),
    );
    const recruiterConversion = document.querySelector(".recruiter-conversion");
    const recruiterConversionRect = recruiterConversion?.getBoundingClientRect();
    const headerRect = document.querySelector(".site-header")?.getBoundingClientRect();

    return {
      title: document.title,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      faviconHref: document.querySelector("link[rel='icon']")?.getAttribute("href"),
      recruiterConversionCount: document.querySelectorAll(".recruiter-conversion").length,
      recruiterConversionText: recruiterConversion
        ?.querySelector("p")
        ?.textContent.replace(/\s+/g, " ")
        .trim(),
      recruiterConversionButtons: Array.from(
        recruiterConversion?.querySelectorAll(".conversion-button") ?? [],
      ).map((element) => ({
        label: element.textContent.trim(),
        tagName: element.tagName,
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      recruiterConversionSticky:
        recruiterConversion && getComputedStyle(recruiterConversion).position === "sticky",
      recruiterConversionBelowHeader:
        recruiterConversionRect && headerRect
          ? recruiterConversionRect.top >= headerRect.bottom - 1
          : false,
      strongestResumeBullet:
        document.getElementById("resume-strongest-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      headerActions: Array.from(document.querySelectorAll(".header-actions .button")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      heroActions: Array.from(document.querySelectorAll(".hero-actions .button")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      reviewPathText:
        document.querySelector(".hero-review-path")?.textContent.replace(/\s+/g, " ").trim() ?? "",
      reviewPathLinks: Array.from(document.querySelectorAll(".hero-review-path a")).map(
        (element) => ({
          label: element.textContent.trim(),
          href: element.getAttribute("href"),
          target: element.getAttribute("target"),
          rel: element.getAttribute("rel"),
        }),
      ),
      employerProofPathCount: document.querySelectorAll(".employer-proof-path").length,
      employerProofPathText:
        document.querySelector(".employer-proof-path")?.textContent.replace(/\s+/g, " ").trim() ??
        "",
      employerProofPathSticky:
        document.querySelector(".employer-proof-path") &&
        getComputedStyle(document.querySelector(".employer-proof-path")).position === "sticky",
      employerProofPathLinks: Array.from(
        document.querySelectorAll(".employer-proof-path a"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      recruiterQuickReviewTitle:
        document.getElementById("recruiter-quick-review-title")?.textContent.trim() ?? "",
      recruiterReviewRows: Array.from(
        document.querySelectorAll("#recruiter-quick-review .recruiter-review-card dl > div"),
      ).map((row) => [
        row.querySelector("dt")?.textContent.trim() ?? "",
        row.querySelector("dd")?.textContent.replace(/\s+/g, " ").trim() ?? "",
      ]),
      recruiterReadyResumeBulletTitle:
        document.querySelector("#recruiter-quick-review .recruiter-bullet-card h2")?.textContent
          .trim() ?? "",
      recruiterReadyResumeBullet:
        document.getElementById("recruiter-ready-resume-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterReadyResumeBulletButton:
        document.querySelector(".recruiter-bullet-copy-button")?.textContent.trim() ?? "",
      hiringSnapshot:
        document.querySelector(".hero-panel")?.getAttribute("aria-label") === "Hiring Snapshot" &&
        document.querySelector(".hero-panel .panel-kicker")?.textContent.trim() ===
          "Hiring Snapshot",
      validationSnapshotAbsent: !document.body.textContent
        .toLowerCase()
        .includes("validation snapshot"),
      proofSummary:
        document.querySelector(".hero-proof-summary")?.textContent.replace(/\s+/g, " ").trim() ??
        "",
      topFoldQuestionsAnswered: {
        what: Boolean(document.querySelector("h1")),
        role: Boolean(document.querySelector(".hero-panel .validation-list")),
        resume: Boolean(document.querySelector(".hero-actions a[href$='_Resume.pdf']")),
        proof: Boolean(document.querySelector(".hero-actions a[href='#proof']")),
        contact: Boolean(document.querySelector(".hero-review-path a[href='#contact']")),
      },
      recruiterActionCount: document.querySelectorAll("#recruiter-action-panel").length,
      recruiterActionEyebrow:
        document.querySelector("#recruiter-action-panel .eyebrow")?.textContent.trim() ?? "",
      recruiterActionTitle:
        document.querySelector("#recruiter-action-title")?.textContent.trim() ?? "",
      recruiterActionSubtitle:
        document.querySelector("#recruiter-action-panel .section-note")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterActionCards: Array.from(
        document.querySelectorAll("#recruiter-action-panel .recruiter-action-card"),
      ).map((card) => {
        const link = card.querySelector("a.button");
        return {
          title: card.querySelector("h3")?.textContent.trim() ?? "",
          label: link?.textContent.trim() ?? "",
          href: link?.getAttribute("href") ?? null,
          target: link?.getAttribute("target") ?? null,
          rel: link?.getAttribute("rel") ?? null,
        };
      }),
      recruiterAvailability:
        document.querySelector("#recruiter-action-panel .recruiter-action-footer > p")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      hiringSummary:
        document.getElementById("hiring-summary-copy-text")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      recruiterActionPlacement: (() => {
        const employerPath = document.querySelector(".hero")?.nextElementSibling;
        const quickReview = employerPath?.nextElementSibling;
        const recruiterAction = quickReview?.nextElementSibling;
        return Boolean(
          employerPath?.classList.contains("employer-proof-path") &&
            quickReview?.id === "recruiter-quick-review" &&
            recruiterAction?.id === "recruiter-action-panel" &&
            recruiterAction.nextElementSibling?.id === "resume-hub",
        );
      })(),
      platformNameExists:
        document.title === "AI Agent Reliability Platform" &&
        document.querySelector("h1")?.textContent.trim() === "AI Agent Reliability Platform",
      resumeHubExists:
        document.querySelector("#resume-hub")?.getAttribute("aria-label") === "Resume Hub",
      resumeHubCount: document.querySelectorAll("#resume-hub").length,
      resumeHubTitle:
        document.querySelector("#resume-hub h2")?.textContent.trim() ===
        "AI Solutions Engineer resume + proof assets",
      resumeHubCards: document.querySelectorAll("#resume-hub .resume-hub-card").length,
      resumeHubCardTitles: Array.from(
        document.querySelectorAll("#resume-hub .resume-hub-card h3"),
      ).map((heading) => heading.textContent.trim()),
      resumeCopyButtons: Array.from(
        document.querySelectorAll("#resume-hub .resume-copy-button"),
      ).map((button) => button.textContent.trim()),
      recruiterVerificationExists:
        document.querySelector("#recruiter-verification-title")?.textContent.trim() ===
        "Recruiter Verification Path",
      recruiterVerificationSteps: document.querySelectorAll(
        "#resume-hub .recruiter-verification li",
      ).length,
      resumeMetricsMatch:
        document.getElementById("resume-proof-metrics")?.textContent
          .replace(/\s+/g, " ")
          .trim() ===
        "87% eval pass rate, 145+ passing tests, 43 req/sec throughput, p50 57ms / p95 270ms latency, 1,000+ automated evaluations, 99%+ workflow success, hallucination reduction from 18% to 6%.",
      resumeLinks: Array.from(
        document.querySelectorAll(
          `a[href='assets/Zohaib_Ahmed_AI_Solutions_Engineer_GenAI_Resume.pdf']`,
        ),
      ).map((link) => ({
        label: link.textContent.trim(),
        target: link.getAttribute("target"),
        rel: link.getAttribute("rel"),
      })),
      downloadResumeLinkExists: Array.from(
        document.querySelectorAll(
          `a[href='assets/Zohaib_Ahmed_AI_Solutions_Engineer_GenAI_Resume.pdf']`,
        ),
      ).some((link) => link.textContent.trim() === "Download Resume"),
      resumeCtasVisible: [".header-resume", ".hero-actions a[href$='_Resume.pdf']"].every(
        (selector) => {
          const element = document.querySelector(selector);
          if (!element) return false;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0
          );
        },
      ),
      resumeHubPlacement:
        document.getElementById("recruiter-action-panel")?.nextElementSibling?.id === "resume-hub",
      liveConsoleExists:
        document.querySelector("#live-eval-console h2")?.textContent.trim() ===
        "Live Eval Console",
      liveConsoleButtons: Array.from(
        document.querySelectorAll("#live-eval-console .simulator-tab"),
      ).map((button) => button.textContent.trim()),
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
      agentFlowExists:
        document.querySelector("#agent-flow .eyebrow")?.textContent.trim() ===
          "AGENTIC RELIABILITY FLOW" &&
        document.getElementById("agent-flow-title")?.textContent.trim() ===
          "From prompt to proof: how the agent run is evaluated",
      agentFlowSubtitle:
        document.querySelector("#agent-flow .agent-flow-heading .section-note")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      agentFlowStepLabels: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-step-copy strong"),
      ).map((element) => element.textContent.trim()),
      agentFlowStepStatuses: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-status"),
      ).map((element) => element.textContent.trim()),
      agentFlowButtonsAccessible: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-step"),
      ).every(
        (button) =>
          button.tagName === "BUTTON" &&
          button.getAttribute("type") === "button" &&
          button.getAttribute("aria-controls") === "agent-flow-detail" &&
          button.hasAttribute("aria-pressed"),
      ),
      agentFlowDefaultStep:
        document.querySelector("#agent-flow .agent-flow-step.is-active")?.dataset.agentFlowStep ??
        "",
      agentFlowProductionTitle:
        document.getElementById("agent-flow-production-title")?.textContent.trim() ?? "",
      agentFlowProductionBullets: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-production li"),
      ).map((element) => element.textContent.replace(/\s+/g, " ").trim()),
      agentFlowResumeTitle:
        document.getElementById("agent-flow-resume-title")?.textContent.trim() ?? "",
      agentFlowResumeBullet:
        document.getElementById("agent-flow-resume-bullet")?.textContent
          .replace(/\s+/g, " ")
          .trim() ?? "",
      agentFlowCtaButtons: Array.from(
        document.querySelectorAll("#agent-flow .agent-flow-actions .button"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      agentFlowPlacement:
        document.getElementById("live-eval-console")?.nextElementSibling?.id === "agent-flow" &&
        document.getElementById("agent-flow")?.nextElementSibling?.id === "agent-trace-replay",
      agentTraceReplayExists:
        document.querySelector("#agent-trace-replay .eyebrow")?.textContent.trim() ===
          "AGENT TRACE REPLAY" &&
        document.querySelector("#agent-trace-replay-title")?.textContent.trim() ===
          "Replay an AI agent workflow with reliability gates",
      agentTraceStepTitles: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-step h3"),
      ).map((heading) => heading.textContent.trim()),
      agentTraceStatuses: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-badge"),
      ).map((badge) => badge.textContent.trim()),
      agentTraceJsonTitle:
        document.querySelector("#agent-trace-replay .agent-replay-console h3")?.textContent.trim() ??
        "",
      agentTraceJson: document.getElementById("agent-trace-json")?.textContent ?? "",
      agentTraceCtaTitle:
        document.querySelector("#agent-trace-replay .agent-replay-cta h3")?.textContent.trim() ?? "",
      agentTraceCtaButtons: Array.from(
        document.querySelectorAll("#agent-trace-replay .agent-replay-actions .button"),
      ).map((element) => ({
        label: element.textContent.trim(),
        href: element.getAttribute("href"),
        target: element.getAttribute("target"),
        rel: element.getAttribute("rel"),
      })),
      agentTracePlacement:
        document.getElementById("agent-flow")?.nextElementSibling?.id === "agent-trace-replay",
      employerValueTitle:
        document.getElementById("employer-value-title")?.textContent.trim() ?? "",
      employerValueBullets: Array.from(
        document.querySelectorAll("#proof .employer-value-card li"),
      ).map((item) => item.textContent.replace(/\s+/g, " ").trim()),
      employerValuePlacement: Boolean(
        document.querySelector("#proof > .employer-value-card"),
      ),
      staleDemoStringsAbsent: ![
        ["Live Eval", "Simulator"].join(" "),
        ["Good", "Answer"].join(" "),
        ["Missing", "Citation"].join(" "),
        ["Unsafe", "Request"].join(" "),
        ["Select a sample", "AI output"].join(" "),
        ["Fixed sample scenarios", "demonstrate"].join(" "),
        ["AI RAG", "Eval Site"].join(" "),
      ].some((label) => document.body.textContent.includes(label)),
      demoNavTargetsConsole:
        document.querySelector(".nav-links a[href='#live-eval-console']")?.textContent.trim() ===
        "Demo",
      deploymentStylesLoaded: Array.from(document.styleSheets).some((sheet) =>
        sheet.href?.endsWith("/frontend/styles.css"),
      ),
      duplicateIds,
      missingLocalAnchors,
    };
  });

  await page.locator(".nav-links a[href='#live-eval-console']").evaluate((anchor) => anchor.click());
  const demoAnchorWorks = new URL(page.url()).hash === "#live-eval-console";
  const demoAnchorLandsOnConsole = await page.locator("#live-eval-console h2").evaluate((heading) => {
    const rect = heading.getBoundingClientRect();
    return rect.top >= 0 && rect.top < window.innerHeight;
  });
  await page
    .locator(".employer-proof-path a[href='#agent-flow']")
    .evaluate((anchor) => anchor.click());
  const agentFlowAnchorWorks = new URL(page.url()).hash === "#agent-flow";
  const agentFlowAnchorLandsOnSection = await page.locator("#agent-flow h2").evaluate((heading) => {
    const rect = heading.getBoundingClientRect();
    return rect.top >= 0 && rect.top < window.innerHeight;
  });
  const scenarioRuns = [];
  for (const scenario of ["good", "citation", "unsafe"]) {
    const tab = page.locator(`[data-scenario='${scenario}']`);
    await tab.click();
    scenarioRuns.push({
      scenario,
      selected: (await tab.getAttribute("aria-selected")) === "true",
      label: (await page.locator("#simulator-scenario-label").textContent())?.trim(),
    });
  }
  const agentFlowRuns = [];
  for (const stage of ["prompt", "retrieval", "guardrail", "evaluation", "proof"]) {
    const button = page.locator(`[data-agent-flow-step='${stage}']`);
    await button.click();
    agentFlowRuns.push({
      stage,
      pressed: (await button.getAttribute("aria-pressed")) === "true",
      title: (await page.locator("#agent-flow-detail-title").textContent())?.trim(),
      status: (await page.locator("#agent-flow-detail-status").textContent())?.trim(),
      metrics: await page
        .locator("#agent-flow-detail-metrics > div")
        .evaluateAll((rows) =>
          rows.map((row) => [
            row.querySelector("dt")?.textContent.trim(),
            row.querySelector("dd")?.textContent.trim(),
          ]),
        ),
      json: await page.locator("#agent-flow-json").textContent(),
      hiring: (await page.locator("#agent-flow-hiring-relevance").textContent())
        ?.replace(/\s+/g, " ")
        .trim(),
    });
  }
  await page.locator("[data-agent-flow-step='prompt']").focus();
  await page.locator("[data-agent-flow-step='prompt']").press("End");
  const agentFlowKeyboardWorks =
    (await page.locator("[data-agent-flow-step='proof']").getAttribute("aria-pressed")) === "true" &&
    (await page.evaluate(() => document.activeElement?.dataset.agentFlowStep)) === "proof";
  const resumeCopyRuns = [];
  const resumeButtons = page.locator(".resume-copy-button");
  for (let index = 0; index < (await resumeButtons.count()); index += 1) {
    const button = resumeButtons.nth(index);
    const statusId = await button.getAttribute("data-status-target");
    await button.click();
    await page.waitForFunction(
      (id) => document.getElementById(id)?.textContent.trim() === "Copied",
      statusId,
    );
    resumeCopyRuns.push({
      label: (await button.textContent())?.trim(),
      status: (await page.locator(`#${statusId}`).textContent())?.trim(),
    });
  }
  await page.locator(".recruiter-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("recruiter-copy-status")?.textContent.trim() === "Copied",
  );
  const recruiterCopyStatus = (
    await page.locator("#recruiter-copy-status").textContent()
  )?.trim();
  await page.locator(".recruiter-bullet-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("recruiter-bullet-copy-status")?.textContent.trim() === "Copied",
  );
  const recruiterBulletCopyStatus = (
    await page.locator("#recruiter-bullet-copy-status").textContent()
  )?.trim();
  await page.locator(".agent-flow-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("agent-flow-copy-status")?.textContent.trim() === "Copied",
  );
  const agentFlowCopyStatus = (
    await page.locator("#agent-flow-copy-status").textContent()
  )?.trim();
  await page.locator(".hiring-summary-copy-button").click();
  await page.waitForFunction(
    () => document.getElementById("hiring-summary-copy-status")?.textContent.trim() === "Copied",
  );
  const hiringSummaryCopyStatus = (
    await page.locator("#hiring-summary-copy-status").textContent()
  )?.trim();
  await page.close();

  return {
    viewport: `deployment-${viewport.name}`,
    ...state,
    demoAnchorWorks,
    demoAnchorLandsOnConsole,
    agentFlowAnchorWorks,
    agentFlowAnchorLandsOnSection,
    scenarioRuns,
    agentFlowRuns,
    agentFlowKeyboardWorks,
    resumeCopyRuns,
    recruiterCopyStatus,
    recruiterBulletCopyStatus,
    agentFlowCopyStatus,
    hiringSummaryCopyStatus,
    consoleErrors,
  };
}

function assertResult(result) {
  const failures = [];
  if (result.scrollWidth !== result.clientWidth) failures.push("horizontal overflow");
  if (result.faviconHref !== "./assets/favicon.svg") failures.push("favicon link");
  assertTopConversionFlow(result, failures);
  assertRecruiterConversion(result, failures);
  assertEmployerProofUpgrade(result, failures);
  assertRecruiterActionPanel(result, failures);
  if (result.proofMetrics !== 5) failures.push("proof metric count");
  if (result.artifactCards !== 6 || result.loadedArtifactImages !== 6) {
    failures.push("proof artifact assets");
  }
  if (result.workflowCards !== 4) failures.push("workflow card count");
  if (!result.resumeHubExists || !result.resumeHubTitle || result.resumeHubCount !== 1) {
    failures.push("resume hub");
  }
  if (result.resumeHubCards !== 4) failures.push("resume hub cards");
  if (
    JSON.stringify(result.resumeHubCardTitles) !==
    JSON.stringify(["Download Resume", "Best-fit roles", "Proof metrics", "Strongest resume bullet"])
  ) {
    failures.push("resume hub card titles");
  }
  if (
    JSON.stringify(result.resumeCopyButtons) !==
    JSON.stringify(["Copy Role Targets", "Copy Metrics", "Copy Resume Bullet"])
  ) {
    failures.push("resume hub copy buttons");
  }
  if (!result.recruiterVerificationExists || result.recruiterVerificationSteps !== 6) {
    failures.push("recruiter verification path");
  }
  if (!result.resumeMetricsMatch) failures.push("resume proof metrics");
  if (
    result.resumeLinks.length < 4 ||
    result.resumeLinks.some(
      (link) => link.target !== "_blank" || !link.rel?.split(/\s+/).includes("noopener"),
    )
  ) {
    failures.push("resume PDF links");
  }
  if (!result.downloadResumeLinkExists) failures.push("download resume link");
  if (!result.resumeHubPlacement) failures.push("resume hub placement");
  if (!result.resumeCtasVisible) failures.push("resume CTA visibility");
  if (
    result.resumeCopyRuns.length !== 3 ||
    result.resumeCopyRuns.some((run) => run.status !== "Copied")
  ) {
    failures.push("resume hub copy behavior");
  }
  if (!result.liveConsoleExists) failures.push("live console section");
  if (!result.liveEvalSimulatorAbsent) failures.push("retired live eval simulator naming");
  if (!result.liveConsoleSubtitle) failures.push("live console subtitle");
  if (!result.liveConsoleDisclosure) failures.push("live console disclosure");
  if (result.liveConsoleHeadingCount !== 1) failures.push("single live console heading");
  if (!result.platformNameExists) failures.push("platform naming");
  if (!result.resumeHubExists || !result.resumeHubTitle || result.resumeHubCount !== 1) {
    failures.push("resume hub");
  }
  if (result.resumeHubCards !== 4) failures.push("resume hub cards");
  if (
    JSON.stringify(result.resumeHubCardTitles) !==
    JSON.stringify(["Download Resume", "Best-fit roles", "Proof metrics", "Strongest resume bullet"])
  ) {
    failures.push("resume hub card titles");
  }
  if (
    JSON.stringify(result.resumeCopyButtons) !==
    JSON.stringify(["Copy Role Targets", "Copy Metrics", "Copy Resume Bullet"])
  ) {
    failures.push("resume hub copy buttons");
  }
  if (!result.recruiterVerificationExists || result.recruiterVerificationSteps !== 6) {
    failures.push("recruiter verification path");
  }
  if (!result.resumeMetricsMatch) failures.push("resume proof metrics");
  if (
    result.resumeLinks.length < 4 ||
    result.resumeLinks.some(
      (link) => link.target !== "_blank" || !link.rel?.split(/\s+/).includes("noopener"),
    )
  ) {
    failures.push("resume PDF links");
  }
  if (!result.downloadResumeLinkExists) failures.push("download resume link");
  if (!result.resumeHubPlacement) failures.push("resume hub placement");
  if (!result.resumeCtasVisible) failures.push("resume CTA visibility");
  if (
    result.resumeCopyRuns.length !== 3 ||
    result.resumeCopyRuns.some((run) => run.status !== "Copied")
  ) {
    failures.push("resume hub copy behavior");
  }
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
  assertAgentFlow(result, failures);
  assertAgentTraceReplay(result, failures);
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

function assertDeploymentResult(result) {
  const failures = [];
  if (result.scrollWidth !== result.clientWidth) failures.push("horizontal overflow");
  if (result.faviconHref !== "./assets/favicon.svg") failures.push("favicon link");
  assertTopConversionFlow(result, failures);
  assertRecruiterConversion(result, failures);
  assertEmployerProofUpgrade(result, failures);
  assertRecruiterActionPanel(result, failures);
  if (!result.platformNameExists) failures.push("platform naming");
  if (!result.liveConsoleExists) failures.push("live console section");
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
  if (!result.liveConsoleSubtitle) failures.push("live console subtitle");
  if (!result.liveConsoleDisclosure) failures.push("live console disclosure");
  assertAgentFlow(result, failures);
  assertAgentTraceReplay(result, failures);
  if (!result.staleDemoStringsAbsent) failures.push("stale demo strings");
  if (!result.demoNavTargetsConsole || !result.demoAnchorWorks || !result.demoAnchorLandsOnConsole) {
    failures.push("demo navigation");
  }
  if (!result.deploymentStylesLoaded) failures.push("deployment stylesheet");
  if (result.duplicateIds.length) failures.push("duplicate IDs");
  if (result.missingLocalAnchors.length) failures.push("missing local anchors");
  if (
    result.scenarioRuns.length !== 3 ||
    result.scenarioRuns.some((run) => !run.selected) ||
    JSON.stringify(result.scenarioRuns.map((run) => run.label)) !==
      JSON.stringify([
        "RAG Citation Check",
        "Citation Failure Case",
        "Prompt Injection Defense",
      ])
  ) {
    failures.push("scenario switching");
  }
  if (result.consoleErrors.length) failures.push("console errors");

  if (failures.length) {
    throw new Error(`${result.viewport} failed: ${failures.join(", ")}`);
  }
}

function assertAgentTraceReplay(result, failures) {
  if (!result.agentTraceReplayExists) failures.push("Agent Trace Replay section");
  if (JSON.stringify(result.agentTraceStepTitles) !== JSON.stringify(agentTraceStepTitles)) {
    failures.push("Agent Trace Replay steps");
  }
  if (
    JSON.stringify(result.agentTraceStatuses) !==
    JSON.stringify(["RECEIVED", "PASS", "PASS", "PASS", "PASS", "PASS"])
  ) {
    failures.push("Agent Trace Replay statuses");
  }
  if (result.agentTraceJsonTitle !== "Agent trace JSONL") {
    failures.push("Agent trace JSONL title");
  }
  if (
    !result.agentTraceJson.includes('"trace_id"') ||
    !result.agentTraceJson.includes('"release_status"')
  ) {
    failures.push("Agent trace JSONL fields");
  }
  if (!result.agentTracePlacement) failures.push("Agent Trace Replay placement");
}

function assertAgentFlow(result, failures) {
  if (
    !result.agentFlowExists ||
    result.agentFlowSubtitle !==
      "Follow one AI agent request through retrieval, guardrails, scoring, JSONL logging, and trace replay." ||
    JSON.stringify(result.agentFlowStepLabels) !== JSON.stringify(agentFlowStepLabels) ||
    JSON.stringify(result.agentFlowStepStatuses) !== JSON.stringify(agentFlowStepStatuses) ||
    !result.agentFlowButtonsAccessible ||
    result.agentFlowDefaultStep !== "prompt" ||
    !result.agentFlowPlacement
  ) {
    failures.push("Agentic Reliability Flow structure");
  }

  if (
    result.agentFlowProductionTitle !== "Why this matters in production" ||
    JSON.stringify(result.agentFlowProductionBullets) !==
      JSON.stringify(agentFlowProductionBullets)
  ) {
    failures.push("Agentic Reliability Flow production callout");
  }

  if (
    result.agentFlowResumeTitle !== "Resume bullet this proves" ||
    result.agentFlowResumeBullet !== agentFlowResumeBullet ||
    result.agentFlowCopyStatus !== "Copied"
  ) {
    failures.push("Agentic Reliability Flow resume bullet");
  }

  if (
    JSON.stringify(result.agentFlowCtaButtons.map((button) => button.label)) !==
    JSON.stringify(agentFlowCtaLabels)
  ) {
    failures.push("Agentic Reliability Flow CTAs");
  }
  const [github, resume, trace] = result.agentFlowCtaButtons;
  if (
    github?.href !== "https://github.com/Electricpaper77/ai-rag-eval-platform" ||
    github.target !== "_blank" ||
    resume?.href !== resumeRelativePath ||
    resume.target !== "_blank" ||
    !resume.rel?.split(/\s+/).includes("noopener") ||
    trace?.href !== "#agent-trace-replay"
  ) {
    failures.push("Agentic Reliability Flow CTA routes");
  }

  const expectedMetrics = [
    [
      ["Input status", "received"],
      ["Citation requirement", "enabled"],
    ],
    [
      ["Retrieved chunks", "6"],
      ["Citation coverage", "92%"],
      ["Context latency", "420ms"],
    ],
    [
      ["Prompt injection", "blocked"],
      ["PII risk", "low"],
      ["Refusal policy", "pass"],
    ],
    [
      ["Eval pass rate", "94%"],
      ["Hallucination risk", "3%"],
      ["Citation precision", "91%"],
      ["Cost/request", "$0.014"],
    ],
    [
      ["JSONL record", "generated"],
      ["Trace replay", "available"],
      ["Regression suite", "passed"],
    ],
  ];
  const expectedStages = [
    "user_prompt",
    "rag_retrieval",
    "guardrail_scan",
    "llm_response_eval",
    "proof_artifact",
  ];
  if (
    result.agentFlowRuns.length !== 5 ||
    result.agentFlowRuns.some(
      (run, index) =>
        !run.pressed ||
        run.title !== agentFlowStepLabels[index] ||
        run.status !== agentFlowStepStatuses[index] ||
        JSON.stringify(run.metrics) !== JSON.stringify(expectedMetrics[index]) ||
        !run.json?.includes('"run_id": "agent_eval_042"') ||
        !run.json?.includes(`"stage": "${expectedStages[index]}"`) ||
        !run.hiring?.startsWith("Hiring relevance:"),
    )
  ) {
    failures.push("Agentic Reliability Flow interactions");
  }

  if (!result.agentFlowKeyboardWorks) {
    failures.push("Agentic Reliability Flow keyboard navigation");
  }

  if (!result.agentFlowAnchorWorks || !result.agentFlowAnchorLandsOnSection) {
    failures.push("Agentic Reliability Flow anchor");
  }
}

function assertEmployerProofUpgrade(result, failures) {
  if (
    result.employerProofPathCount !== 1 ||
    result.employerProofPathText !== employerProofPathText ||
    !result.employerProofPathSticky ||
    JSON.stringify(result.employerProofPathLinks.map((link) => link.label)) !==
      JSON.stringify(employerProofPathLabels)
  ) {
    failures.push("employer proof path");
  }

  const [pathResume, pathGithub, pathLiveEval, pathAgentFlow, pathTraceReplay, pathContact] =
    result.employerProofPathLinks;
  if (
    pathResume?.href !== resumeRelativePath ||
    pathResume.target !== "_blank" ||
    !pathResume.rel?.split(/\s+/).includes("noopener") ||
    pathGithub?.href !== "https://github.com/Electricpaper77/ai-rag-eval-platform" ||
    pathGithub.target !== "_blank" ||
    pathLiveEval?.href !== "#live-eval-console" ||
    pathAgentFlow?.href !== "#agent-flow" ||
    pathTraceReplay?.href !== "#agent-trace-replay" ||
    pathContact?.href !== "#contact"
  ) {
    failures.push("employer proof path routes");
  }

  if (
    result.recruiterQuickReviewTitle !== "30-second recruiter review" ||
    JSON.stringify(result.recruiterReviewRows) !== JSON.stringify(recruiterReviewRows)
  ) {
    failures.push("30-second recruiter review");
  }
  if (
    result.recruiterReadyResumeBulletTitle !== "Copy-ready resume bullet" ||
    result.recruiterReadyResumeBullet !== recruiterReadyResumeBullet ||
    result.recruiterReadyResumeBulletButton !== "Copy Bullet" ||
    result.recruiterBulletCopyStatus !== "Copied"
  ) {
    failures.push("copy-ready resume bullet");
  }

  if (
    result.employerValueTitle !== "Why this matters to AI teams" ||
    JSON.stringify(result.employerValueBullets) !== JSON.stringify(employerValueBullets) ||
    !result.employerValuePlacement
  ) {
    failures.push("employer value card");
  }

  if (
    result.agentTraceCtaTitle !== "Review the full proof trail" ||
    JSON.stringify(result.agentTraceCtaButtons.map((button) => button.label)) !==
      JSON.stringify(agentTraceCtaLabels)
  ) {
    failures.push("Agent Trace Replay CTA");
  }
  const [traceResume, traceGithub, traceContact] = result.agentTraceCtaButtons;
  if (
    traceResume?.href !== resumeRelativePath ||
    traceResume.target !== "_blank" ||
    !traceResume.rel?.split(/\s+/).includes("noopener") ||
    traceGithub?.href !== "https://github.com/Electricpaper77/ai-rag-eval-platform" ||
    traceGithub.target !== "_blank" ||
    traceContact?.href !== "#contact"
  ) {
    failures.push("Agent Trace Replay CTA routes");
  }
}

function assertRecruiterConversion(result, failures) {
  if (
    result.recruiterConversionCount !== 1 ||
    result.recruiterConversionText !== recruiterConversionText
  ) {
    failures.push("recruiter conversion header");
  }
  if (
    JSON.stringify(result.recruiterConversionButtons.map((button) => button.label)) !==
    JSON.stringify(recruiterConversionLabels)
  ) {
    failures.push("recruiter conversion buttons");
  }

  const [resume, copy, contact] = result.recruiterConversionButtons;
  if (
    resume?.href !== resumeRelativePath ||
    resume.target !== "_blank" ||
    !resume.rel?.split(/\s+/).includes("noopener")
  ) {
    failures.push("recruiter resume route");
  }
  if (copy?.tagName !== "BUTTON" || copy.href !== null) {
    failures.push("recruiter copy button");
  }
  if (contact?.href !== "#contact") failures.push("recruiter contact route");
  if (!result.recruiterConversionSticky || !result.recruiterConversionBelowHeader) {
    failures.push("recruiter sticky placement");
  }
  if (result.strongestResumeBullet !== strongestResumeBullet) {
    failures.push("recruiter resume bullet text");
  }
  if (result.recruiterCopyStatus !== "Copied") {
    failures.push("recruiter copy behavior");
  }
}

function assertTopConversionFlow(result, failures) {
  if (
    JSON.stringify(result.headerActions.map((action) => action.label)) !==
    JSON.stringify(headerActionLabels)
  ) {
    failures.push("header action hierarchy");
  }
  const [headerResume, headerGithub] = result.headerActions;
  if (
    headerResume?.href !== resumeRelativePath ||
    headerResume.target !== "_blank" ||
    !headerResume.rel?.split(/\s+/).includes("noopener")
  ) {
    failures.push("header resume route");
  }
  if (
    headerGithub?.href !== "https://github.com/Electricpaper77/ai-rag-eval-platform" ||
    headerGithub.target !== "_blank"
  ) {
    failures.push("header GitHub route");
  }

  if (
    JSON.stringify(result.heroActions.map((action) => action.label)) !==
    JSON.stringify(heroActionLabels)
  ) {
    failures.push("hero action hierarchy");
  }
  const [heroGithub, heroResume, heroProof] = result.heroActions;
  if (
    heroGithub?.href !== "https://github.com/Electricpaper77/ai-rag-eval-platform" ||
    heroResume?.href !== resumeRelativePath ||
    heroProof?.href !== "#proof"
  ) {
    failures.push("hero action routes");
  }

  if (
    result.reviewPathText !==
      "Recommended review path: Resume → Proof Artifacts → Live Eval Console → Contact" ||
    JSON.stringify(result.reviewPathLinks.map((link) => link.label)) !==
      JSON.stringify(reviewPathLabels)
  ) {
    failures.push("review path");
  }
  const [reviewResume, reviewProof, reviewDemo, reviewContact] = result.reviewPathLinks;
  if (
    reviewResume?.href !== resumeRelativePath ||
    reviewResume.target !== "_blank" ||
    !reviewResume.rel?.split(/\s+/).includes("noopener") ||
    reviewProof?.href !== "#proof" ||
    reviewDemo?.href !== "#live-eval-console" ||
    reviewContact?.href !== "#contact"
  ) {
    failures.push("review path routes");
  }
  if (!result.hiringSnapshot || !result.validationSnapshotAbsent) {
    failures.push("hiring snapshot naming");
  }
  if (result.proofSummary !== proofSummary) failures.push("hero proof summary");
  if (!Object.values(result.topFoldQuestionsAnswered).every(Boolean)) {
    failures.push("top fold hiring questions");
  }
}

function assertRecruiterActionPanel(result, failures) {
  if (
    result.recruiterActionCount !== 1 ||
    result.recruiterActionEyebrow !== "FAST HIRING PATH" ||
    result.recruiterActionTitle !== "What to review first" ||
    result.recruiterActionSubtitle !== recruiterActionSubtitle
  ) {
    failures.push("recruiter action panel");
  }
  if (
    result.recruiterActionCards.length !== 4 ||
    JSON.stringify(result.recruiterActionCards.map((card) => card.title)) !==
      JSON.stringify(recruiterActionTitles) ||
    JSON.stringify(result.recruiterActionCards.map((card) => card.label)) !==
      JSON.stringify(recruiterActionButtonLabels)
  ) {
    failures.push("recruiter action cards");
  }

  const [resume, proof, demo, contact] = result.recruiterActionCards;
  if (
    resume?.href !== resumeRelativePath ||
    resume.target !== "_blank" ||
    !resume.rel?.split(/\s+/).includes("noopener")
  ) {
    failures.push("recruiter action resume route");
  }
  if (proof?.href !== "#proof") failures.push("recruiter action proof route");
  if (demo?.href !== "#live-eval-console") failures.push("recruiter action demo route");
  if (contact?.href !== "#contact") failures.push("recruiter action contact route");
  if (result.recruiterAvailability !== recruiterAvailability) {
    failures.push("recruiter availability");
  }
  if (result.hiringSummary !== hiringSummary) failures.push("hiring summary text");
  if (result.hiringSummaryCopyStatus !== "Copied") {
    failures.push("hiring summary copy behavior");
  }
  if (!result.recruiterActionPlacement) failures.push("recruiter action placement");
}

(async () => {
  const staleTrackedStrings = findStaleTrackedStrings();
  if (staleTrackedStrings.length) {
    throw new Error(`stale tracked demo strings: ${JSON.stringify(staleTrackedStrings)}`);
  }
  if (!fs.existsSync(resumePath) || !fs.existsSync(deploymentResumePath)) {
    throw new Error("resume PDF missing from one or more deployment roots");
  }
  if (!fs.existsSync(faviconPath) || !fs.existsSync(deploymentFaviconPath)) {
    throw new Error("favicon missing from one or more deployment roots");
  }
  for (const trackedResumePath of [
    resumeRelativePath,
    path.posix.join("frontend", resumeRelativePath),
  ]) {
    try {
      execFileSync("git", ["ls-files", "--error-unmatch", "--", trackedResumePath], {
        cwd: projectRoot,
        stdio: "ignore",
      });
    } catch {
      throw new Error(`resume PDF is not tracked by git: ${trackedResumePath}`);
    }
  }
  const resumeBytes = fs.readFileSync(resumePath);
  const deploymentResumeBytes = fs.readFileSync(deploymentResumePath);
  if (
    !resumeBytes.subarray(0, 5).equals(Buffer.from("%PDF-")) ||
    !resumeBytes.equals(deploymentResumeBytes)
  ) {
    throw new Error("resume PDF assets are invalid or differ between deployment roots");
  }

  const launchOptions = { headless: true };
  if (process.env.BROWSER_PATH) launchOptions.executablePath = process.env.BROWSER_PATH;
  if (process.env.PLAYWRIGHT_CHANNEL) launchOptions.channel = process.env.PLAYWRIGHT_CHANNEL;

  const browser = await chromium.launch(launchOptions);
  const results = [];

  for (const viewport of viewports) {
    const result = await inspectViewport(browser, viewport);
    assertResult(result);
    results.push(result);

    const deploymentResult = await inspectDeploymentViewport(browser, viewport);
    assertDeploymentResult(deploymentResult);
    results.push(deploymentResult);
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
