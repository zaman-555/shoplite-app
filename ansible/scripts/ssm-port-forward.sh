#!/bin/bash
# Forward the control-plane API to 127.0.0.1:6443.
# The kubeconfig saved by Ansible already points at that address.
# Usage: ./scripts/ssm-port-forward.sh <control-plane-instance-id>
set -euo pipefail

instance_id="${1:-}"
if [[ -z "${instance_id}" ]]; then
  echo "usage: $0 <control-plane-instance-id>" >&2
  exit 1
fi

exec aws ssm start-session \
  --target "${instance_id}" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["127.0.0.1"],"portNumber":["6443"],"localPortNumber":["6443"]}'
