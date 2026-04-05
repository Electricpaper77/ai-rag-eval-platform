# GPU Inference Reliability Rollout Notes

## Why GPU pods should not be killed simultaneously
GPU inference pods often hold large model weights in memory and can take significant time to warm up. If all pods are disrupted at once, live traffic may hit cold-start delays or service unavailability. A PodDisruptionBudget with `minAvailable: 1` preserves baseline serving capacity during planned disruptions such as node drains.

## Why readiness checks protect live traffic
A readiness probe gates endpoint registration in the Service until a pod can answer health checks. For GPU serving, this prevents routing requests to pods that are still loading weights or not yet responsive. Using `/health` as the readiness path keeps traffic on known-good replicas.

## How rolling updates reduce downtime risk
A rolling strategy with `maxUnavailable: 0` and `maxSurge: 1` updates pods one at a time while maintaining existing capacity. New replicas are brought up before old replicas terminate, reducing user-visible errors and avoiding abrupt capacity drops during deployment changes.
