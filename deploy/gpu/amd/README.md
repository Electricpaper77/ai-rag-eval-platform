# AMD GPU device-plugin integration

This directory documents an AMD Kubernetes device-plugin integration.  It is
not installed by the CPU-only Gate 6 workflow and is not a claim that this
repository has access to AMD hardware.

The reference is the official `ROCm/k8s-device-plugin` release
`v1.31.0.10`, source revision `dea1db1`.  Review the release assets and image
digest in the target environment before installation:

```text
https://github.com/ROCm/k8s-device-plugin/tree/v1.31.0.10
```

The expected node contract is:

- label AMD nodes with `agenttrust.ai/accelerator=amd-gpu`;
- load the AMD kernel driver and expose `/dev/kfd` and `/dev/dri` on those
  nodes only;
- install the pinned release's AMD device-plugin DaemonSet;
- verify that the node advertises `amd.com/gpu` before scheduling workloads.

The Gate 6 Helm example requests `amd.com/gpu` only when
`gpu.count > 0`.  The plugin itself is intentionally not applied in ordinary
CI because a CPU runner has no AMD device files and should not receive host
device access or privileged containers.
