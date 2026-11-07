# ShopLite

Local shop with a static web UI, a catalog API, an order worker, PostgreSQL, and Redis. The API accepts an order, pushes it onto a Redis list, and the worker marks it `COMPLETED` or `FAILED`.

Follow the steps in order the first time. The sections after step 18 are reference: endpoints, schema, environment variables, and fault flags.

## New developer steps

### 1. Install the tools

You need:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Compose v2)
- `make`, `curl`, and `python3`

On macOS, `make`, `curl`, and `python3` are already available. Confirm them:

```bash
docker --version
docker compose version
make --version
curl --version
python3 --version
```

You do not need a local Python virtualenv. Tests run inside Docker.

### 2. Open a terminal in the project root

```bash
cd /path/to/Shoplite-app
pwd
ls
```

You should see `docker-compose.yml`, `Makefile`, `README.md`, `scripts/`, and `services/`. Every later command assumes this directory.

### 3. Start Docker

Open Docker Desktop and wait until it says the engine is running. Then:

```bash
docker info
```

The command prints server information and exits 0. If it hangs or says it cannot connect to the daemon, Docker is still starting.

### 4. Read the layout before you build

```text
shoplite-app/
├── services/
│   ├── web/             Static UI, served by Nginx
│   ├── catalog-api/     FastAPI catalog and order API
│   └── order-worker/    Redis consumer that finishes orders
├── docker-compose.yml   Starts web, API, worker, Postgres, and Redis
├── Makefile             build, up, down, test, smoke
└── scripts/
    └── smoke-test.sh    Places one order and waits for COMPLETED
```

```mermaid
flowchart TD
  root["shoplite-app"]
  services["services"]
  web["web<br/>Static UI, served by Nginx"]
  api["catalog-api<br/>FastAPI catalog and order API"]
  worker["order-worker<br/>Redis consumer that finishes orders"]
  compose["docker-compose.yml<br/>Starts web, API, worker, Postgres, and Redis"]
  make["Makefile<br/>build, up, down, test, smoke"]
  scripts["scripts"]
  smoke["smoke-test.sh<br/>Places one order and waits for COMPLETED"]

  root --> services
  root --> compose
  root --> make
  root --> scripts
  services --> web
  services --> api
  services --> worker
  scripts --> smoke
```

How those pieces connect once `make up` is running:

```mermaid
flowchart LR
  browser["Browser :8080"]
  web["web<br/>Nginx"]
  api["catalog-api<br/>:8000"]
  worker["order-worker"]
  pg[("postgres")]
  redis[("redis<br/>orders:pending")]

  browser -->|"open the shop"| web
  web -->|"HTML, CSS, JS"| browser
  web -->|"/products /orders"| api
  api -->|"read and write"| pg
  api -->|"RPUSH"| redis
  worker -->|"BLPOP"| redis
  worker -->|"update status and stock"| pg
```

| Folder or file | What you edit |
|---|---|
| `services/web/` | `index.html`, `styles.css`, `app.js`, Nginx config |
| `services/catalog-api/app/` | API routes, database access, queue publish, schema |
| `services/order-worker/` | Queue consumer and status updates |
| `docker-compose.yml` | Ports, environment variables, health checks |
| `Makefile` | The five developer commands |

Postgres and Redis have no source folder. Compose pulls `postgres:16-alpine` and `redis:7-alpine`.

### 5. Build the images

```bash
make build
```

This builds `web`, `catalog-api`, and `order-worker`. The first build downloads base images and can take several minutes. Later builds reuse cached layers.

Each image is a multi-stage build, runs as a non-root user, and has a `HEALTHCHECK`. Python images use Alpine. The web image listens on 8080 because the `nginx` user cannot bind port 80.

### 6. Start the stack

```bash
make up
```

Compose starts five containers:

| Service | Role |
|---|---|
| `postgres` | Stores products and orders. Seeded on first start |
| `redis` | Queue. The list key is `orders:pending` |
| `catalog-api` | Lists products, creates orders, enqueues them |
| `order-worker` | Pops the queue, processes for 1–2 seconds, updates status |
| `web` | Serves the UI and proxies API calls |

`catalog-api` and `order-worker` wait until Postgres and Redis are healthy. `web` waits until the API health check passes. Postgres and Redis stay on the Compose network and are not published to your machine.

### 7. Confirm every service is healthy

```bash
docker compose ps
```

Each row should show `healthy`. Then:

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/readyz
```

`/healthz` returns `{"status":"ok"}`. `/readyz` returns `"status":"ready"` with `"database":"ok"` and `"queue":"ok"`.

| Surface | URL |
|---|---|
| Web UI | http://127.0.0.1:8080 |
| Catalog API | http://127.0.0.1:8000 |
| Worker metrics | http://127.0.0.1:8001/metrics |

If a port is already taken, `make up` fails with an address-in-use error. Stop the other process, or change the host port on the left side of `ports` in `docker-compose.yml` (for example `"8081:8080"`).

### 8. Place an order in the browser

1. Open http://127.0.0.1:8080.
2. Confirm the page lists 12 products. On a brand-new database the first product is Wireless Mouse at 24.99 with stock 100. Stock is lower if orders were already completed on this volume.
3. Choose a quantity that is at most the stock shown, then place the order.
4. Wait. The page polls once a second for up to 60 seconds.
5. The status becomes `COMPLETED`, and the stock on the card drops by the quantity you ordered.

The page stores recent order ids in the browser under the `localStorage` key `shoplite.orders`. The browser calls the API through Nginx on the same origin. Nginx proxies `/products`, `/orders`, `/healthz`, `/readyz`, and `/metrics` to `catalog-api`.

### 9. Place an order from the terminal

```bash
curl -s http://127.0.0.1:8000/products
```

Pick an `id` from that list, then:

```bash
curl -s -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: dev-order-1' \
  -d '{"product_id": 1, "quantity": 1}'
```

A new order returns HTTP 201 and a JSON body with `id`, `status` `PENDING`, `created_at`, and `completed_at` set to `null`. Copy the `id`. The response header `X-Trace-Id` matches the request id you sent.

`product_id` and `quantity` must be integers greater than 0. A bad body returns `422`. An unknown product returns `404`.

### 10. Watch that order finish

Replace `ORDER_ID` with the id from step 9:

```bash
curl -s http://127.0.0.1:8000/orders/ORDER_ID
```

Run it again after a couple of seconds. The status moves `PENDING` → `PROCESSING` → `COMPLETED`. `completed_at` is set only for `COMPLETED`.

What happened:

```mermaid
flowchart TD
  post["POST /orders"]
  pending["PENDING<br/>row saved in postgres"]
  queue["RPUSH orders:pending"]
  processing["PROCESSING<br/>worker claimed the order"]
  wait["Wait 1 to 2 seconds"]
  stock{"Enough stock?"}
  completed["COMPLETED<br/>stock decremented"]
  failed["FAILED<br/>completed_at stays empty"]
  queueDown["Queue write failed"]

  post --> pending
  pending --> queue
  pending -->|"enqueue error"| queueDown
  queueDown --> failed
  queue --> processing
  processing --> wait
  wait --> stock
  stock -->|yes| completed
  stock -->|"no, or an error"| failed
```

1. `POST /orders` inserted the row as `PENDING` and pushed `{"order_id", "trace_id"}` onto the Redis list `orders:pending`.
2. The worker popped that message, set the order to `PROCESSING`, and waited a random 1–2 seconds.
3. The worker decremented stock and set `COMPLETED` because the product had enough stock.
4. If stock is too low, the product is missing, or processing raises, the status becomes `FAILED` and `completed_at` stays empty.
5. If the API cannot push to Redis, it marks that order `FAILED` and returns `503`.

On `SIGTERM`, the worker stops taking new work. A message popped but not yet processed is put back with `LPUSH`. Compose gives the worker 30 seconds to exit.

### 11. Read the logs

```bash
docker compose logs -f catalog-api order-worker
```

Each line is one JSON object with `timestamp`, `level`, `service`, `message`, and `trace_id`. `trace_id` is `-` when the caller did not send `X-Request-ID`. Press Ctrl+C to stop following logs. The containers keep running.

### 12. Look at metrics

```bash
curl -s http://127.0.0.1:8000/metrics
curl -s http://127.0.0.1:8001/metrics
```

Catalog API:

- `http_requests_total`
- `http_request_duration_seconds`
- `orders_created_total`

Worker:

- `orders_processed_total` (label `status`)
- `order_processing_duration_seconds`
- `orders_in_progress`

### 13. Automatic unit tests

From the project root:

```bash
make test
```

That command does four things:

1. Builds the catalog-api test image from `services/catalog-api/Dockerfile`.
2. Runs that image. Pytest executes `services/catalog-api/tests/`.
3. Builds the order-worker test image from `services/order-worker/Dockerfile`.
4. Runs that image. Pytest executes `services/order-worker/tests/`.

The stack does not need to be running. These tests use fakes for Postgres and Redis. Test-only packages stay out of the runtime images.

Pass: the command ends with pytest output for both suites and the shell prompt returns with no error.

Fail: the first failing suite stops the command. Read the pytest failure above that prompt, fix the code or the test, then run `make test` again.

What the suites cover:

| Suite | File | Checks |
|---|---|---|
| Catalog API | `services/catalog-api/tests/test_api.py` | Products, create order, status codes, `/healthz`, `/readyz`, `/metrics`, trace id, queue key, chaos flags |
| Schema | `services/catalog-api/tests/test_schema.py` | Product and order columns, at least 10 seeded products |
| Worker | `services/order-worker/tests/test_worker.py` | `PENDING` to `COMPLETED`, 1–2 second delay, `FAILED` on low stock, `SIGTERM`, requeue, chaos flags, JSON logs |

### 14. Automatic smoke test

This checks the real containers, not fakes. From the project root:

```bash
make smoke
```

`make smoke` runs `scripts/smoke-test.sh`, which:

1. Runs `docker compose up -d --build`.
2. Polls `http://127.0.0.1:8000/readyz` for up to about two minutes.
3. `POST`s `{"product_id": 1, "quantity": 1}`.
4. Polls `GET /orders/{id}` once a second for up to 40 seconds.
5. Exits 0 only when the status is `COMPLETED`.

Pass looks like this:

```text
Starting the ShopLite stack
Waiting for http://127.0.0.1:8000/readyz
Placing an order
Created order 12
order 12 status=PENDING
order 12 status=PROCESSING
order 12 status=COMPLETED
Smoke test passed
```

`PROCESSING` may be missing from the printout if the worker finishes between two polls. `COMPLETED` is the required last status.

Fail: the script exits non-zero. Typical messages are `readyz did not become available`, `order N failed`, or `order N did not become COMPLETED in time`. Product 1 must still have stock. If that product is sold out, the order becomes `FAILED` and the smoke test fails. Reset with step 17, then run `make smoke` again.

To point the script at another API address:

```bash
BASE_URL=http://127.0.0.1:8000 ./scripts/smoke-test.sh
```

### 15. Manual smoke test

Do this when you want to see each check yourself. Start the stack first:

```bash
make up
docker compose ps
```

Every service should be `healthy`. Then run the checks in order. Stop if one fails.

**1. Liveness**

```bash
curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/healthz
```

Expect HTTP `200` and `{"status":"ok"}`.

**2. Readiness**

```bash
curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/readyz
```

Expect HTTP `200` and `"status":"ready"` with `"database":"ok"` and `"queue":"ok"`. HTTP `503` means Postgres or Redis is not reachable yet. Wait a few seconds and run the same command again.

**3. Products**

```bash
curl -s http://127.0.0.1:8000/products
```

Expect a JSON list. On a fresh database the first item is Wireless Mouse, id `1`.

**4. Place one order**

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"product_id": 1, "quantity": 1}'
```

Expect HTTP `201`. The body has `"status":"PENDING"` and `"completed_at":null`. Copy the `id`. This response is always `PENDING`. The worker updates the row after this call returns.

**5. Poll until it finishes**

Replace `11` with the id from step 4:

```bash
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -s http://127.0.0.1:8000/orders/11
  echo
  sleep 0.5
done
```

A passing run shows `PENDING`, then `PROCESSING`, then `COMPLETED`. `completed_at` stays `null` until the status is `COMPLETED`, and then it is a timestamp. Later lines stay `COMPLETED` because polling does not change a finished order.

**6. Confirm in the browser**

Open http://127.0.0.1:8080, place an order, and wait until the page shows `COMPLETED` and the stock drops by the quantity you ordered.

The manual smoke test passes when steps 1, 2, and 4 return those status codes and step 5 reaches `COMPLETED`.

### 16. Stop the stack

```bash
make down
```

Containers are removed. The named volume `postgres_data` stays, so products, stock, and orders are still there the next time you run `make up`.

### 17. Reset the database

Use this when you want the original 12 products and an empty order table:

```bash
docker compose down -v
make up
```

`-v` deletes `postgres_data`. The next Postgres start runs `services/catalog-api/app/schema.sql` again.

### 18. After you change code

| You changed | Run |
|---|---|
| Python, static files, Dockerfiles, or `schema.sql` used by the images | `make build` then `make up` |
| Only `docker-compose.yml` (ports or environment) | `docker compose up -d` |
| Tests | `make test`, then `make smoke` |

`schema.sql` uses `CREATE TABLE IF NOT EXISTS`. A volume that already has tables will not pick up new columns. Reset with step 17 when the schema itself changes.

Useful files once you start changing behavior:

- `services/catalog-api/app/main.py` — routes and status codes
- `services/catalog-api/app/schema.sql` — tables and seed data
- `services/catalog-api/app/queue.py` — Redis list `orders:pending`
- `services/order-worker/worker.py` — consume, delay, shutdown
- `services/order-worker/db.py` — stock decrement and status updates
- `services/web/app.js` — product list, place order, poll status

## API reference

| Method | Path | Success | Errors |
|---|---|---|---|
| `GET` | `/products` | `200` list of products | |
| `GET` | `/products/{id}` | `200` one product | `404` unknown id |
| `POST` | `/orders` | `201` created order | `404` unknown product, `422` invalid body, `500` injected fault, `503` queue write failed |
| `GET` | `/orders/{id}` | `200` order | `404` unknown id |
| `GET` | `/healthz` | `200` `{"status":"ok"}` | |
| `GET` | `/readyz` | `200` when database and Redis answer | `503` if either is down |
| `GET` | `/metrics` | Prometheus text | |

Order body:

```json
{"product_id": 1, "quantity": 2}
```

## Database

Postgres user, password, and database name are all `shoplite`.

`products`: `id`, `name` (unique), `price`, `stock`.

`orders`: `id`, `product_id`, `quantity`, `status`, `created_at`, `completed_at`.

Status is one of `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`.

Seeded products: Wireless Mouse, Mechanical Keyboard, USB-C Hub, Laptop Stand, Noise-Cancelling Headphones, Webcam 1080p, 27-inch Monitor, Desk Lamp, Portable SSD 1TB, Ethernet Cable, Notebook, Water Bottle.

Inserts use `ON CONFLICT (name) DO NOTHING`, so a later startup does not reset stock. The API and the worker also apply `schema.sql` on startup.

## Configuration

Compose sets these. Change them in `docker-compose.yml`, then run `docker compose up -d`.

Catalog API:

| Variable | Default in Compose | Meaning |
|---|---|---|
| `SERVICE_NAME` | `catalog-api` | Name written in each log line |
| `DATABASE_URL` | `postgresql://shoplite:shoplite@postgres:5432/shoplite` | Postgres connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Python log level |
| `CHAOS_LATENCY_MS` | `0` | Extra delay, in milliseconds, on some product lookups |
| `CHAOS_ERROR_RATE` | `0` | Fraction of `POST /orders` that return HTTP 500 |

Order worker:

| Variable | Default in Compose | Meaning |
|---|---|---|
| `SERVICE_NAME` | `order-worker` | Name written in each log line |
| `DATABASE_URL` | same as the API | Postgres connection |
| `REDIS_URL` | same as the API | Redis connection |
| `SCHEMA_PATH` | `/app/schema.sql` | Schema file inside the image |
| `METRICS_PORT` | `8001` | Prometheus listen port |
| `LOG_LEVEL` | `INFO` | Python log level |
| `CHAOS_MEMORY_LEAK` | `false` | Keep a growing in-memory list of processed orders |
| `CHAOS_SLOW_DB` | `false` | Run `SELECT pg_sleep(2)` before each status update |

`CHAOS_MEMORY_LEAK` and `CHAOS_SLOW_DB` turn on for `1`, `true`, `yes`, or `on`.

## Fault injection

Leave these at the defaults while you learn the happy path. To try one, edit its value in `docker-compose.yml` and run `docker compose up -d`.

| Flag | Effect |
|---|---|
| `CHAOS_LATENCY_MS` | When greater than 0, about 30% of `GET /products/{id}` sleep for that many milliseconds before the lookup, including unknown ids |
| `CHAOS_ERROR_RATE` | `0.1` makes about 10% of `POST /orders` return HTTP 500. The fault happens before the row is inserted, so no order is created |
| `CHAOS_MEMORY_LEAK` | After each processed order the worker appends a record with 64 KB of padding and never clears the list |
| `CHAOS_SLOW_DB` | The worker runs `SELECT pg_sleep(2)` immediately before each database update |

## Makefile

| Command | What it does |
|---|---|
| `make build` | Build web, catalog-api, and order-worker |
| `make up` | Start all five containers in the background |
| `make down` | Stop and remove containers; keep the Postgres volume |
| `make test` | Automatic unit tests. Fakes only. The stack can be stopped |
| `make smoke` | Automatic smoke test. Real containers, one order, must reach `COMPLETED` |

## Later milestones

| Guide | What it covers |
|---|---|
| [README-linux.md](README-linux.md) | Ubuntu users, SSH, permissions, the nightly backup, and UFW |
| [README-aws.md](README-aws.md) | Terraform VPC, private k3s nodes, the load balancer, ECR, and the Ansible bootstrap |
