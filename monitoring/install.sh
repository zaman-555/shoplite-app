#!/bin/bash
# Install Prometheus, Loki, Promtail, Tempo, and Grafana into the monitoring namespace.
# Grafana's admin password is not stored in Git.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
: "${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD before installing Grafana}"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

kubectl apply -f "${root}/monitoring/namespace.yaml"

helm upgrade --install loki grafana/loki \
  --namespace monitoring \
  --values "${root}/monitoring/helm/loki-values.yaml"

helm upgrade --install promtail grafana/promtail \
  --namespace monitoring \
  --values "${root}/monitoring/helm/promtail-values.yaml"

helm upgrade --install tempo grafana/tempo \
  --namespace monitoring \
  --values "${root}/monitoring/helm/tempo-values.yaml"

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values "${root}/monitoring/helm/kube-prometheus-stack-values.yaml" \
  --set "grafana.adminPassword=${GRAFANA_ADMIN_PASSWORD}"

if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
  helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --reuse-values \
    --set "alertmanager.config.receivers[0].webhook_configs[0].url=${ALERT_WEBHOOK_URL}"
fi

kubectl apply -f "${root}/monitoring/alert-rules/shoplite.yaml"

kubectl create configmap shoplite-golden-signals \
  --namespace monitoring \
  --from-file=shoplite-golden-signals.json="${root}/monitoring/dashboards/shoplite-golden-signals.json" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl label configmap shoplite-golden-signals \
  --namespace monitoring \
  grafana_dashboard=1 --overwrite

echo "Grafana datasources: Prometheus uid=prometheus, Loki uid=loki, Tempo uid=tempo"
echo "Change the Alertmanager URL with ALERT_WEBHOOK_URL or edit monitoring/helm/kube-prometheus-stack-values.yaml"
