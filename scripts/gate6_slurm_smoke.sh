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
conf="$root/slurm.conf"
cat > "$conf" <<EOF
ClusterName=agenttrust-gate6
SlurmctldHost=localhost
SlurmUser=$user_name
SlurmdUser=$user_name
AuthType=auth/none
SelectType=select/cons_tres
SelectTypeParameters=CR_Core
NodeName=localhost CPUs=1 RealMemory=1024 State=UNKNOWN
PartitionName=debug Nodes=localhost Default=YES MaxTime=INFINITE State=UP
SlurmctldPidFile=$root/slurmctld.pid
SlurmdPidFile=$root/slurmd.pid
StateSaveLocation=$root/state
SlurmdSpoolDir=$root/spool
SlurmctldLogFile=$root/log/slurmctld.log
SlurmdLogFile=$root/log/slurmd.log
ProctrackType=proctrack/linuxproc
TaskPlugin=task/none
JobCompType=jobcomp/filetxt
JobCompLoc=$root/jobcomp.log
EOF
export SLURM_CONF="$conf"

cleanup() {
  set +e
  [[ -n "${slurmd_pid:-}" ]] && kill "$slurmd_pid" 2>/dev/null || true
  [[ -n "${slurmctld_pid:-}" ]] && kill "$slurmctld_pid" 2>/dev/null || true
}
trap cleanup EXIT

slurmctld -D -f "$conf" > "$artifact_dir/slurmctld.stdout" 2> "$artifact_dir/slurmctld.stderr" &
slurmctld_pid=$!
slurmd -D -f "$conf" > "$artifact_dir/slurmd.stdout" 2> "$artifact_dir/slurmd.stderr" &
slurmd_pid=$!

for _ in $(seq 1 30); do
  if scontrol ping 2>/dev/null | grep -q "UP"; then break; fi
  sleep 1
done

timeout 30s scontrol ping | tee "$artifact_dir/controller-ping.txt"
timeout 30s sinfo -f | tee "$artifact_dir/sinfo.txt"
timeout 30s scontrol show node localhost | tee "$artifact_dir/node.txt"

timeout 60s srun -N1 -n1 hostname | tee "$artifact_dir/srun-hostname.txt"

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
