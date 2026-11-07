#!/bin/bash
# Allow inbound SSH, HTTP, and HTTPS only. Deny everything else.
# Keep a second SSH session open before you run this.
set -euo pipefail

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose
