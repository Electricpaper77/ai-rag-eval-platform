#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-artifacts/gate13-runner-preflight}"
mkdir -p "$OUTPUT_DIR"

fail() {
  echo "AMD_RUNNER_PREFLIGHT: FAIL: $*" >&2
  exit 1
}

os_name="$(uname -s)"
arch="$(uname -m)"
[[ "$os_name" == "Linux" ]] || fail "Linux is required (found $os_name)"
[[ "$arch" == "x86_64" ]] || fail "Linux x86_64 is required (found $arch)"

command -v rocminfo >/dev/null 2>&1 || fail "rocminfo is not installed"
command -v rocm-smi >/dev/null 2>&1 || fail "rocm-smi is not installed"
command -v hipconfig >/dev/null 2>&1 || fail "hipconfig is not installed"

[[ -e /dev/kfd ]] || fail "/dev/kfd is missing"
[[ -e /dev/dri ]] || fail "/dev/dri is missing"

uname -a | tee "$OUTPUT_DIR/kernel.txt"
cat /etc/os-release | tee "$OUTPUT_DIR/os-release.txt"
printf 'architecture=%s\n' "$arch" | tee "$OUTPUT_DIR/architecture.txt"
ls -l /dev/kfd /dev/dri | tee "$OUTPUT_DIR/device-nodes.txt"
lspci -nn | tee "$OUTPUT_DIR/lspci.txt"

rocminfo_output="$OUTPUT_DIR/rocminfo.txt"
rocm_smi_output="$OUTPUT_DIR/rocm-smi.txt"
hipconfig_output="$OUTPUT_DIR/hipconfig.txt"
rocminfo | tee "$rocminfo_output"
rocm-smi --showproductname --json | tee "$rocm_smi_output"
hipconfig --full | tee "$hipconfig_output"

grep -Eiq 'Device Type:[[:space:]]*GPU' "$rocminfo_output" || fail "rocminfo reported no GPU agent"
grep -Eiq '(^|[[:space:]])Name:[[:space:]]*gfx[0-9A-Za-z.-]+' "$rocminfo_output" || fail "rocminfo reported no AMD gfx GPU agent"

gpu_model="$(grep -Eim1 'Marketing Name:[[:space:]]*.+|Name:[[:space:]]*gfx[0-9A-Za-z.-]+' "$rocminfo_output" || true)"
rocm_version="$(grep -Eim1 "ROCm version:[[:space:]]*.+|Runtime Version:[[:space:]]*.+|ROCm:[[:space:]]*.+|ROCm version[[:space:]]*=.+" "$hipconfig_output" "$rocminfo_output" 2>/dev/null || true)"
hip_version="$(grep -Eim1 "HIP version:[[:space:]]*.+|HIP version[[:space:]]*=.+|HIP:[[:space:]]*.+" "$hipconfig_output" 2>/dev/null || true)"
[[ -n "$gpu_model" ]] || fail "AMD GPU model could not be recorded"
[[ -n "$rocm_version" ]] || fail "ROCm version could not be recorded"
[[ -n "$hip_version" ]] || fail "HIP version could not be recorded"

{
  echo "os=$os_name"
  echo "architecture=$arch"
  echo "gpu_model=$gpu_model"
  echo "rocm_version=$rocm_version"
  echo "hip_version=$hip_version"
  echo "kfd=/dev/kfd"
  echo "dri=/dev/dri"
} | tee "$OUTPUT_DIR/preflight-summary.txt"

echo "AMD_RUNNER_PREFLIGHT: PASS"
