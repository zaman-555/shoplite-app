# QueueBacklog

`order_queue_depth` is above 50 for 10 minutes. The Redis list `orders:pending` is growing faster than the worker drains it.

1. Open **ShopLite — Golden Signals**. Compare **Order queue depth**, **Worker replica count**, and **Orders created versus orders processed**.
2. If created stays above processed, the worker is behind. The HPA may add replicas up to 4 when CPU is high. If CPU is low and depth stays high, the worker is blocked on Postgres (`CHAOS_SLOW_DB`) or crash-looping.
3. Pick a `trace_id` from an `order-worker` log in Loki and open it in Tempo. The trace should contain `process order` and `postgres finish_order`. A missing worker span means the message is still in Redis.
