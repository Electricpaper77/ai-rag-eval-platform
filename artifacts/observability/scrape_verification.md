# Prometheus Operator Scrape Verification

This file captures repeatable verification commands for ServiceMonitor-based scraping.

## 1) Apply manifests

```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/servicemonitor.yaml
```

## 2) Verify labels/selectors line up

```bash
kubectl get svc ai-rag-eval-api -o yaml | grep -E "app.kubernetes.io/name|app.kubernetes.io/component|monitoring"
kubectl get servicemonitor ai-rag-eval-metrics -o yaml | grep -E "matchLabels|http-metrics|/metrics|interval"
```

## 3) Confirm target discovery in Prometheus Operator

```bash
kubectl get servicemonitor ai-rag-eval-metrics
kubectl get endpoints ai-rag-eval-api
```

## 4) Spot-check metrics locally through port-forward

```bash
kubectl port-forward svc/ai-rag-eval-api 8080:8080
curl -s http://127.0.0.1:8080/metrics | head
```

## Common failure mode

If Prometheus does not discover targets, the most frequent issue is a mismatch between:
- `ServiceMonitor.spec.selector.matchLabels`
- `Service.metadata.labels`
- `Service.spec.selector` vs pod template labels in Deployment.
