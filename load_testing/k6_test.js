import http from 'k6/http';
import { check } from 'k6';

export let options = {
  stages: [
    { duration: '10s', target: 10 },
    { duration: '10s', target: 25 },
    { duration: '10s', target: 50 },
    { duration: '10s', target: 0 }
  ]
};

export default function () {

  const payload = JSON.stringify({
    query: "Explain Kubernetes"
  });

  const params = {
    headers: { 'Content-Type': 'application/json' }
  };

  let res = http.post(
    'http://34.121.205.47/query',
    payload,
    params
  );

  check(res, {
    'status 200': (r) => r.status === 200,
  });
}
