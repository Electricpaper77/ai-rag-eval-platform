import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

export default function () {
  const res = http.get('https://ai-rag-eval-69725201265.us-central1.run.app/health');

  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(1);
}
