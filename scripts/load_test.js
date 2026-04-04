import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const vus = Number(__ENV.VUS || 10);
const duration = __ENV.DURATION || '30s';
const baseUrl = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const endpoint = '/v1/chat/completions';
const outputPath = __ENV.SUMMARY_PATH || 'artifacts/proof/load_test_summary.json';

const latency = new Trend('inference_latency', true);
const errorRate = new Rate('inference_error_rate');

export const options = {
  vus,
  duration,
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<5000'],
  },
};

export default function () {
  const payload = JSON.stringify({
    model: __ENV.MODEL || 'gpt-4o-mini',
    messages: [
      { role: 'system', content: 'You are a concise assistant.' },
      { role: 'user', content: 'Say hello in one short sentence.' },
    ],
    temperature: 0,
    max_tokens: 32,
  });

  const headers = {
    'Content-Type': 'application/json',
  };

  if (__ENV.API_KEY) {
    headers.Authorization = `Bearer ${__ENV.API_KEY}`;
  }

  const response = http.post(`${baseUrl}${endpoint}`, payload, { headers });

  latency.add(response.timings.duration);

  const ok = check(response, {
    'status is 200': (r) => r.status === 200,
    'response has choices': (r) => {
      try {
        const body = r.json();
        return Array.isArray(body.choices) && body.choices.length > 0;
      } catch (_) {
        return false;
      }
    },
  });

  errorRate.add(!ok);
  sleep(Number(__ENV.SLEEP_SECONDS || 0));
}

function getMetric(data, name, key) {
  return data?.metrics?.[name]?.values?.[key] ?? null;
}

export function handleSummary(data) {
  const reqCount = getMetric(data, 'http_reqs', 'count') || 0;
  const runDurationMs = data?.state?.testRunDurationMs || 0;
  const requestsPerSec = runDurationMs > 0 ? reqCount / (runDurationMs / 1000) : null;

  const summary = {
    generated_at: new Date().toISOString(),
    target: `${baseUrl}${endpoint}`,
    config: {
      vus,
      duration,
    },
    metrics: {
      p50_latency_ms: getMetric(data, 'http_req_duration', 'p(50)'),
      p95_latency_ms: getMetric(data, 'http_req_duration', 'p(95)'),
      requests_per_sec: requestsPerSec,
      error_rate: getMetric(data, 'http_req_failed', 'rate'),
    },
  };

  return {
    [outputPath]: JSON.stringify(summary, null, 2),
    stdout: `\nWrote load test summary to ${outputPath}\n`,
  };
}
