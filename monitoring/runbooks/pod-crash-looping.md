# PodCrashLooping

A container in the `shoplite` namespace has an increasing restart count over 10 minutes.

1. In Grafana Explore, run `increase(kube_pod_container_status_restarts_total{namespace="shoplite"}[10m])` and note the `pod` and `container` labels.
2. In Loki, query `{namespace="shoplite", pod="<pod>"}` and read the last JSON lines before the restart.
3. `catalog-api` and `order-worker` exit when Postgres or Redis is unreachable. Confirm those pods are Ready. The NetworkPolicy allows only those two apps to open ports 5432 and 6379.
4. After the pod stays up, place one order and confirm its trace reaches `COMPLETED`.
