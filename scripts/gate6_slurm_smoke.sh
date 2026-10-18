#!/usr/bin/env bash
set -euo pipefail

artifact_dir="${1:-artifacts/gate6/slurm}"
root="${GATE6_SLURM_ROOT:-.tmp/gate6-slurm}"
mkdir -p "$artifact_dir" "$root/state" "$root/spool" "$root/log"
root="$(cd "$root" && pwd)"

if ! command -v slurmctld >/dev/null || ! command -v slurmd >/dev/null || ! command -v srun >/dev/null; then
  echo "SLURM_NOT_EXECUTED: required Slurm binaries are unavailable" | tee "$artifact_dir/status.txt"
  exit 2
fi

user_name="$(id -un)"
node_name="$(hostname -s)"
cpus="$(nproc)"
real_memory="$(awk '/^MemTotal:/ {print int($2 / 1024); exit}' /proc/meminfo)"
slurmd_privileged=0
if sudo -n true 2>/dev/null; then
  slurmd_privileged=1
fi
slurmd_user="$user_name"
if [[ "$slurmd_privileged" -eq 1 ]]; then
  slurmd_user=root
fi
conf="$root/slurm.conf"
cat > "$root/cgroup.conf" <<'EOF'
CgroupPlugin=autodetect
IgnoreSystemd=yes
EOF
cat > "$conf" <<EOF
ClusterName=agenttrust-gate6
SlurmctldHost=$node_name
SlurmUser=$user_name
SlurmdUser=$slurmd_user
AuthType=auth/none
SelectType=select/cons_tres
SelectTypeParameters=CR_Core
NodeName=$node_name NodeAddr=127.0.0.1 NodeHostname=$node_name CPUs=$cpus RealMemory=$real_memory State=UNKNOWN
PartitionName=debug Nodes=$node_name Default=YES MaxTime=INFINITE State=UP
SlurmctldPidFile=$root/slurmctld.pid
SlurmdPidFile=$root/slurmd.pid
StateSaveLocation=$root/state
SlurmdSpoolDir=$root/spool
SlurmctldLogFile=$root/log/slurmctld.log
SlurmdLogFile=$root/log/slurmd.log
ProctrackType=proctrack/linuxproc
TaskPlugin=task/none
SlurmdParameters=config_overrides
JobCompType=jobcomp/filetxt
JobCompLoc=$root/jobcomp.log
EOF
export SLURM_CONF="$conf"

cleanup() {
  set +e
  if [[ -n "${slurmd_pid:-}" ]]; then
    if [[ "${slurmd_privileged:-0}" -eq 1 ]]; then
      sudo -n kill "$slurmd_pid" 2>/dev/null || true
    else
      kill "$slurmd_pid" 2>/dev/null || true
    fi
  fi
  [[ -n "${slurmctld_pid:-}" ]] && kill "$slurmctld_pid" 2>/dev/null || true
}
trap cleanup EXIT

slurmctld -Dvvv -f "$conf" > "$artifact_dir/slurmctld.stdout" 2> "$artifact_dir/slurmctld.stderr" &
slurmctld_pid=$!
if [[ "$slurmd_privileged" -eq 1 ]]; then
  sudo -n slurmd -Dvvv -f "$conf" > "$artifact_dir/slurmd.stdout" 2> "$artifact_dir/slurmd.stderr" &
else
  slurmd -Dvvv -f "$conf" > "$artifact_dir/slurmd.stdout" 2> "$artifact_dir/slurmd.stderr" &
fi
slurmd_pid=$!

controller_ready=0
for _ in $(seq 1 30); do
  if scontrol ping 2>/dev/null | grep -q "UP"; then controller_ready=1; break; fi
  if ! kill -0 "$slurmctld_pid" 2>/dev/null; then break; fi
  sleep 1
done

if [[ "$controller_ready" -ne 1 ]]; then
  {
    echo "SLURM_CONTROLLER_STARTUP_FAILED"
    ps -ef | grep -E "[s]lurm(ctld|d)"
    echo "--- slurmctld stdout ---"
    cat "$artifact_dir/slurmctld.stdout"
    echo "--- slurmctld stderr ---"
    cat "$artifact_dir/slurmctld.stderr"
    echo "--- slurmd stdout ---"
    cat "$artifact_dir/slurmd.stdout"
    echo "--- slurmd stderr ---"
    cat "$artifact_dir/slurmd.stderr"
  } | tee "$artifact_dir/startup-diagnostics.txt"
  exit 1
fi

timeout 30s scontrol ping | tee "$artifact_dir/controller-ping.txt"
timeout 30s sinfo -l | tee "$artifact_dir/sinfo.txt"
timeout 30s scontrol show node "$node_name" | tee "$artifact_dir/node.txt"

timeout 60s srun -N1 -n1 hostname | tee "$artifact_dir/srun-hostname.txt"
timeout 30s scontrol update NodeName="$node_name" State=IDLE | tee "$artifact_dir/node-resume.txt"
timeout 30s scontrol show node "$node_name" | tee "$artifact_dir/node-after-registration.txt"

job_script="$root/benchmark-job.sh"
cat > "$job_script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
hostname
python3 - <<'PY'
print("GATE6_SLURM_BENCHMARK_PASS")
print(sum(i * i for i in range(1000)))
PY
EOF
chmod 0755 "$job_script"
job_id="$(timeout 30s sbatch --parsable --wait --output="$artifact_dir/job-%j.out" --error="$artifact_dir/job-%j.err" "$job_script")"
echo "job_id=$job_id" | tee "$artifact_dir/job-id.txt"
timeout 30s squeue -j "$job_id" -o "%.18i %.9T %.20j" | tee "$artifact_dir/squeue.txt" || true
timeout 30s sacct -X -j "$job_id" --starttime="$(date -d '2 minutes ago' '+%Y-%m-%dT%H:%M:%S')" --format=JobID,State,ExitCode | tee "$artifact_dir/sacct.txt" || true
grep -R "GATE6_SLURM_BENCHMARK_PASS" "$root" "$artifact_dir" | tee "$artifact_dir/job-output.txt"
echo "SLURM: PASS" | tee "$artifact_dir/status.txt"
