# GPU node labels and taints (example)

This repository does **not** assume a live Kubernetes cluster. Use these examples to align node pools and scheduling policies.

## Example labels for GPU node pools

```bash
kubectl label node gpu-node-a gpu-tier=standard platform=ai-eval accelerator=nvidia-l4
kubectl label node gpu-node-b gpu-tier=premium platform=ai-eval accelerator=nvidia-a100
```

## Example taints for dedicated GPU capacity

```bash
kubectl taint node gpu-node-a nvidia.com/gpu=present:NoSchedule
kubectl taint node gpu-node-b nvidia.com/gpu=present:NoSchedule
```

## Why these labels exist

- `gpu-tier`: maps workload latency/quality goals to a scheduler-visible tier.
- `platform`: keeps AI evaluation workloads isolated from non-platform clusters.
- `accelerator`: documents underlying GPU family for placement debugging.
