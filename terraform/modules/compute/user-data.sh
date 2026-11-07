#!/bin/bash
# Session Manager is the admin path. SSH is not opened.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y curl ca-certificates
curl -fsSL -o /tmp/amazon-ssm-agent.deb https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
dpkg -i /tmp/amazon-ssm-agent.deb
systemctl enable --now amazon-ssm-agent
if ! id ssm-user >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash ssm-user
fi
echo 'ssm-user ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ssm-user
chmod 440 /etc/sudoers.d/ssm-user
