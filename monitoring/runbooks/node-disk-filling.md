# NodeDiskFilling

A node filesystem is more than 85 percent full.

1. In Grafana Explore, run `1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)` and ignore `tmpfs` and `overlay`. Note the `instance` and `mountpoint`.
2. The Postgres volume is the ShopLite disk that grows with orders. A full node disk also stops kubelet and new pods.
3. Free space on that node, or expand the Postgres PersistentVolumeClaim `data`. Do not delete the claim if you still need the catalog.
4. Confirm the alert clears after avail/size stays under 85 percent.
