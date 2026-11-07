# RCA: orders stayed PENDING

## Summary

On 7 November 2026, new orders remained `PENDING` for 14 minutes. The catalog API accepted them and wrote them to Redis. The worker never took them off the queue. Customers could place an order in the browser and the status did not reach `COMPLETED`.

## Impact

The shop UI and `POST /orders` stayed available. Stock was not reduced, because the worker is the only component that completes an order. About 60 orders sat in `orders:pending`.

## Timeline

| Time (UTC) | Event |
|---|---|
| 18:02 | GitHub Actions published `shoplite-order-worker` image `4c1d9e2` and committed that tag to `shoplite-gitops` |
| 18:03 | Argo CD synced the prod application |
| 18:04 | The new worker pods failed to start. `PodCrashLooping` moved to firing |
| 18:06 | `QueueBacklog` was still quiet because the depth had not been above 50 for 10 minutes |
| 18:14 | `QueueBacklog` fired. The queue depth was 61 |
| 18:16 | The image tag in `envs/prod/values.yaml` was pointed back at the previous digest and Argo CD synced |
| 18:18 | A worker became Ready, drained the queue, and new orders reached `COMPLETED` |

## Detection

Grafana was enough. `PodCrashLooping` was already red. The Golden Signals dashboard showed order queue depth climbing and worker replica count at 0 available. Orders created continued. Orders processed stopped.

## Path from the alert to the request

1. Open the `QueueBacklog` annotation `runbook_url`, `monitoring/runbooks/queue-backlog.md`.
2. On **ShopLite — Golden Signals**, the created series kept moving and the processed series was flat.
3. In Loki, `{namespace="shoplite", service="catalog-api"} | json` showed `created order` lines. Each line has a `trace_id`.
4. The derived field opened that `trace_id` in Tempo. The trace contained `HTTP POST /orders`, `postgres create_order`, and `redis enqueue`. It had no `process order` span.
5. The missing worker span showed the message was still in Redis. The worker logs for the new ReplicaSet were image-pull errors, not application JSON.

One example trace id from that window was `4bf92f3577b34da6a3ce929d0e0e4736`. The API span ended in under 100 milliseconds. There was no child span from the worker.

## Root cause

The GitOps commit set `images.orderWorker` to a tag that had not been pushed to the registry the nodes can pull. Argo CD did what Git asked. The worker pods crash-looped on `ImagePullBackOff`, so nothing called `BLPOP` on `orders:pending`.

## What we changed

- Restored the previous image tag in `shoplite-gitops` and let Argo CD sync it.
- The CI job now pushes the image before it commits the tag.
- Prod values use the ECR registry attached to the node role, so a private GHCR package is not required for the worker.

## What is still open

- Add an Argo CD health check that marks the application degraded when a pod is in `ImagePullBackOff`, so the bad sync is visible before the queue alert waits 10 minutes.
