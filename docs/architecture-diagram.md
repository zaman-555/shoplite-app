# ShopLite architecture

GitHub Actions builds and publishes images. Argo CD deploys whatever `shoplite-gitops` records. The pipeline does not run `kubectl apply`.

```mermaid
flowchart LR
  dev["Developer push"]
  appRepo["shoplite-app"]
  actions["GitHub Actions"]
  registry["GHCR or ECR"]
  gitops["shoplite-gitops"]
  argo["Argo CD"]
  cluster["k3s cluster"]

  dev --> appRepo --> actions
  actions -->|"test, build, push"| registry
  actions -->|"commit image tags"| gitops
  gitops --> argo
  registry --> cluster
  argo -->|"sync Helm release"| cluster
```

```mermaid
flowchart TB
  internet["Internet"]
  alb["Application load balancer"]
  traefik["Traefik NodePort 30080"]
  web["web"]
  api["catalog-api /api"]
  worker["order-worker"]
  postgres["Postgres"]
  redis["Redis"]

  internet --> alb --> traefik
  traefik --> web
  traefik --> api
  web --> api
  api --> postgres
  api --> redis
  worker --> postgres
  worker --> redis
```

The nodes stay in private subnets. Session Manager is the admin path. Prometheus, Loki, and Tempo run in the `monitoring` namespace and read the metrics, JSON logs, and OpenTelemetry traces from the shop.
