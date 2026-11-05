#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

plan_only=false
if [[ "${1:-}" == --help ]]; then
  printf '%s\n' 'Usage: ./deploy.sh [--plan] [config.tfvars.json]' 'Requires Terraform, Python 3, HCLOUD_TOKEN, and CLOUDFLARE_API_TOKEN.'
  exit 0
fi
if [[ "${1:-}" == --plan ]]; then
  plan_only=true
  shift
fi
if [[ $# -gt 1 ]]; then
  echo 'Usage: ./deploy.sh [--plan] [config.tfvars.json]' >&2
  exit 2
fi

for tool in terraform python3; do
  command -v "$tool" >/dev/null || { echo "Install $tool first; see README.md." >&2; exit 1; }
done
: "${HCLOUD_TOKEN:?Set HCLOUD_TOKEN to a Hetzner Cloud read/write API token.}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN to a scoped Cloudflare API token.}"
unset TF_LOG TF_LOG_PATH TF_LOG_CORE TF_LOG_PROVIDER

cd "$(dirname "${BASH_SOURCE[0]}")"
config="${1:-config.tfvars.json}"
[[ -f "$config" ]] || { echo 'Configuration file missing. Copy config.example.tfvars.json and fill in your values.' >&2; exit 1; }
chmod 600 "$config"
work=$(mktemp -d .deploy-XXXXXX)
trap 'rm -rf "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

terraform init -input=false -lockfile=readonly
terraform validate
terraform show -json > "$work/state.json"
python3 checks.py preflight "$config" "$work/state.json"
terraform plan -input=false -lock-timeout=60s -var-file="$config" -out="$work/deploy.tfplan"
terraform show -json "$work/deploy.tfplan" > "$work/plan.json"
python3 checks.py plan "$work/plan.json"
if "$plan_only"; then
  echo 'Plan validated. No infrastructure changed.'
  exit 0
fi
terraform apply -input=false -lock-timeout=60s "$work/deploy.tfplan"
terraform output -json > "$work/state.json"
python3 checks.py verify "$work/state.json"
