#!/bin/bash
set -euxo pipefail

dnf install -y iptables
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward = 1" > /etc/sysctl.d/99-nat.conf

IFACE="$(ip -4 route show default | awk '{print $5; exit}')"
iptables -t nat -C POSTROUTING -o "${IFACE}" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -o "${IFACE}" -j MASQUERADE
iptables -C FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -C FORWARD -j ACCEPT 2>/dev/null || iptables -A FORWARD -j ACCEPT

mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4
RESTORE="$(command -v iptables-restore)"

cat > /etc/systemd/system/nat-restore.service <<EOF
[Unit]
Description=Restore NAT rules
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${RESTORE} /etc/iptables/rules.v4

[Install]
WantedBy=multi-user.target
EOF

systemctl enable nat-restore.service
