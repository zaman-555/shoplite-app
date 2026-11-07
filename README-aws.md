# ShopLite on AWS: Terraform and Ansible

Follow these steps in order. They create the AWS network, three private Kubernetes nodes, a public load balancer, three ECR repositories, and a k3s cluster. Run them from your own computer. The AWS console is only for checking the bill.

This costs money as soon as `terraform apply` succeeds. Three `t3.small` nodes, one `t3.nano` NAT instance, and an Application Load Balancer are a few US dollars per day. Destroy the stack when grading is finished. A NAT Gateway is not used: one of those is about USD 32 per month before data charges, which is already over the USD 20 budget alarm.

Every resource is tagged `project=shoplite`.

## What you are building

```text
terraform/
├── main.tf                      Wires the modules, the Session Manager bucket, and the budget
├── bootstrap/                   S3 state bucket and DynamoDB lock table
├── backend.hcl.example
├── terraform.tfvars.example
└── modules/
    ├── network/                 VPC, two public subnets, two private subnets, IGW, NAT instance
    ├── compute/                 One control plane and two workers, private only
    ├── alb/                     Public load balancer to NodePort 30080
    └── ecr/                     web, catalog-api, order-worker
ansible/
├── site.yml                     Harden, install containerd, start k3s, join the workers
├── inventory/aws_ec2.yml        Finds the running nodes through Session Manager
├── roles/
│   ├── harden/                  SSH drop-in, ops group, log ACL, UFW, backup timer
│   ├── container_runtime/       containerd
│   └── k3s/                     Control plane, Traefik on 30080, worker join, kubeconfig
└── scripts/ssm-port-forward.sh
helm/shoplite/                   One chart for web, API, worker, Postgres, and Redis
├── values.yaml                  Defaults used by every install
├── values-dev.yaml              Smaller resources
└── values-prod.yaml             ECR image names
```

| Piece | Where it lives |
|---|---|
| VPC `10.0.0.0/16`, two availability zones | `terraform/modules/network` |
| Public subnets `10.0.1.0/24` and `10.0.2.0/24` | Load balancer and the NAT instance |
| Private subnets `10.0.11.0/24` and `10.0.12.0/24` | Control plane and both workers |
| Internet gateway | Public route table |
| NAT instance `t3.nano` | Private route table. Source/destination check is off |
| Node security group | No inbound traffic from the internet. Port 30080 only from the load balancer |
| Control plane + worker-a + worker-b | Ubuntu 22.04, `t3.small`, no public IP, no SSH key |
| Admin access | AWS Systems Manager Session Manager |
| Load balancer | Public subnets, forwards HTTP to Traefik NodePort 30080 |
| Route 53 | Created only when you set a domain and a hosted zone |
| ECR | `shoplite/web`, `shoplite/catalog-api`, `shoplite/order-worker` |
| Remote state | S3 bucket plus DynamoDB table `shoplite-tfstate-lock` |
| Budget | USD 20 per month, email at 80% actual and 100% forecast |

Ansible reuses `linux/sshd_config` and the backup script. On each node it creates the `ops` group and a `deploy` user with a locked password, sets `/var/log/shoplite` to mode `700` with one `setfacl` for `ops`, and enables UFW. The nightly backup timer is enabled on the control plane. Workers do not have the database yet, so the timer stays off there. UFW also allows the VPC to reach the Kubernetes ports, or the nodes cannot form a cluster. The security group still blocks the internet from those ports.

## 1. Install the tools

On your Mac:

```bash
brew install hashicorp/tap/terraform
brew install ansible
brew install helm
brew install kubectl
brew install awscli
brew install --cask session-manager-plugin
python3.12 -m pip install --user boto3 botocore
```

`python3` on this Mac is 3.8. Ansible and the AWS collection need 3.12, which is `python3.12`.

Confirm:

```bash
terraform version
ansible --version
helm version
kubectl version --client
aws --version
session-manager-plugin --version
```

`terraform version` should be 1.5 or newer. `helm version` should print a client version.

## 2. Open the project and sign in to AWS

```bash
cd /path/to/Shoplite-app
aws sts get-caller-identity
```

The command prints your account id. You need permission to create a VPC, EC2, an application load balancer, ECR, S3, DynamoDB, IAM, and a budget. If this command fails, fix the credentials before the next step. The console is not used to create resources.

## 3. Set the budget email

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit `terraform/terraform.tfvars` and replace `you@example.com` with your own address. Leave the region as `eu-central-1` unless you also change `regions` in `ansible/inventory/aws_ec2.yml` and `vpc_cidr` in `ansible/group_vars/all.yml` to match.

Leave `domain_name` and `route53_zone_id` commented out when you have no domain. Uncomment both, and only both, when the hosted zone already exists. Add `certificate_arn` only when that certificate is in the same region and you want the HTTPS listener.

`terraform.tfvars` is gitignored.

## 4. Create the remote state backend

Terraform cannot store its own state in a bucket that does not exist yet. The bootstrap stack uses local state and creates the bucket and the lock table.

```bash
cd terraform/bootstrap
terraform init
terraform apply
```

Type `yes` when asked. The outputs are the bucket name, the lock table, and the region. The bucket name looks like `shoplite-tfstate-123456789012`.

Copy the example and put that account id into the bucket name:

```bash
cd ..
cp backend.hcl.example backend.hcl
```

`terraform/backend.hcl` after the edit:

```hcl
bucket         = "shoplite-tfstate-123456789012"
key            = "shoplite/terraform.tfstate"
region         = "eu-central-1"
dynamodb_table = "shoplite-tfstate-lock"
encrypt        = true
```

`backend.hcl` is gitignored. Keep `terraform/bootstrap/terraform.tfstate` on this computer. You need it later to destroy the bucket.

## 5. Plan and apply the cluster

From the `terraform/` directory:

```bash
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

`plan` prints the VPC, subnets, NAT instance, security groups, three nodes, load balancer, ECR repositories, Session Manager bucket, and the USD 20 budget. `apply` creates them. The first apply takes several minutes.

Read the outputs:

```bash
terraform output
```

Save these values:

| Output | Use |
|---|---|
| `alb_dns_name` | Public address of the load balancer |
| `control_plane_instance_id` | Session Manager target and the port-forward script |
| `worker_instance_ids` | The two private workers |
| `node_private_ips` | Addresses inside the VPC |
| `ecr_repository_urls` | Where the three images are pushed |
| `ansible_ssm_bucket` | Required by the Ansible playbook |
| `route53_fqdn` | Set only when you configured a domain |

The load balancer targets stay unhealthy until Ansible has started Traefik on port 30080. That is expected at this point.

Ansible configures the three Ubuntu machines after Terraform has created them. It does not create the VPC or the instances. Helm installs the ShopLite pods after Ansible has built the Kubernetes cluster. Do the Ansible section before the Helm section.

## 6. Install the Ansible collections

```bash
cd ../ansible
ansible-galaxy collection install -r requirements.yml
```

This installs `amazon.aws` and `community.general`.

## 7. What the playbook changes

Ansible connects with Session Manager. The inventory hostname is the EC2 instance id. Do not set `ansible_host` to the private IP. The nodes have no public address and no SSH key.

`ansible/site.yml` has three plays:

| Play | Hosts | What it does |
|---|---|---|
| Harden and container runtime | control plane and both workers | `harden`, then `container_runtime` |
| Bootstrap k3s | control plane only | `k3s` in server mode |
| Join the workers | workers, one at a time | `k3s` in agent mode |

`harden` applies the Ubuntu milestone on every node:

- creates the `ops` group and a `deploy` user with a locked password
- installs `linux/sshd_config` as `/etc/ssh/sshd_config.d/99-shoplite.conf`
- creates `/var/log/shoplite` as root-owned mode `700`, then one `setfacl` granting `ops` read and execute
- enables UFW for 22, 80, and 443, and also allows Kubernetes ports from the VPC
- installs the backup script and timer. The timer is started on the control plane only

`container_runtime` installs and starts `containerd`.

`k3s` on the control plane installs k3s from the stable channel, publishes Traefik on NodePort 30080, and saves two files on your computer:

| File | What it is |
|---|---|
| `ansible/kubeconfig` | Admin credentials. The server address is `https://127.0.0.1:6443` |
| `ansible/.k3s-token` | Token the workers use to join. Both files are gitignored |

The worker play reads that token and joins `https://<control-plane-private-ip>:6443`.

## 8. Run the playbook

Session Manager needs the nodes to register. Wait two or three minutes after apply, then from `ansible/`:

```bash
export SSM_BUCKET="$(terraform -chdir=../terraform output -raw ansible_ssm_bucket)"
export AWS_REGION=eu-central-1
ansible-inventory --graph
```

The graph lists one host under `control_plane` and two under `worker`. The host names are instance ids. If the graph is empty, wait and run it again. The inventory ignores the NAT instance.

```bash
ansible-playbook site.yml
```

The first run takes several minutes. A second run should change little: k3s is not reinstalled when it is already present.

## 9. Open the cluster

Leave this running in one terminal. It forwards the private API to your laptop:

```bash
cd ansible
./scripts/ssm-port-forward.sh "$(terraform -chdir=../terraform output -raw control_plane_instance_id)"
```

In a second terminal:

```bash
cd ansible
KUBECONFIG=./kubeconfig kubectl get nodes
```

You should see the control plane and both workers `Ready`. Leave the port-forward terminal open. `helm` and `kubectl` use that tunnel.

Traefik is listening on port 30080. The load balancer forwards public HTTP to that port. The shop pods are not installed yet, so the load balancer target can still look unhealthy.

## 10. What the Helm chart installs

Helm installs ShopLite into the cluster. The chart is one package, `helm/shoplite/`. Terraform and Ansible do not install these pods.

| File | When to use it |
|---|---|
| `values.yaml` | Always. Replica counts, probes, the autoscaler, and the empty database password |
| `values-dev.yaml` | A smaller practice install. Same replica rules, less CPU and memory |
| `values-prod.yaml` | The AWS install. Image names point at ECR. Replace `000000000000` with your account id |
| `values-secrets.yaml.example` | Optional copy if you want to choose the database password yourself. The real copy is gitignored |

On install, Helm creates:

| Workload | Kubernetes object | What to look for |
|---|---|---|
| web | Deployment, 2 replicas | Ingress path `/` |
| catalog-api | Deployment, 2 replicas | Liveness `/healthz`, readiness `/readyz`, PodDisruptionBudget `minAvailable: 1`, Ingress path `/api` |
| order-worker | Deployment plus CPU autoscaler | Minimum 1 replica, maximum 4, 90 seconds to finish an order on shutdown |
| postgres | StatefulSet and a disk | `files/schema.sql` seeds the 12 products the first time the disk is empty |
| redis | Deployment | ClusterIP Service only. No public port |

The database password is generated into the Secret `shoplite-db`. It is not written into a file in Git. Application settings such as the log level and the tracing endpoint are in a ConfigMap. NetworkPolicy allows only `catalog-api` and `order-worker` to open Postgres and Redis. Every pod has CPU and memory requests and limits, and none run as root.

## 11. Build the images and push them to ECR

Run this from the project root. The account id is the same one from `aws sts get-caller-identity`.

```bash
docker compose build
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.eu-central-1.amazonaws.com"
aws ecr get-login-password --region eu-central-1 \
  | docker login --username AWS --password-stdin "${REGISTRY}"
docker tag shoplite-web:latest "${REGISTRY}/shoplite/web:latest"
docker tag shoplite-catalog-api:latest "${REGISTRY}/shoplite/catalog-api:latest"
docker tag shoplite-order-worker:latest "${REGISTRY}/shoplite/order-worker:latest"
docker push "${REGISTRY}/shoplite/web:latest"
docker push "${REGISTRY}/shoplite/catalog-api:latest"
docker push "${REGISTRY}/shoplite/order-worker:latest"
```

Edit `helm/shoplite/values-prod.yaml` and replace every `000000000000` with that account id. The nodes can pull from these repositories because Terraform attached the ECR read-only policy.

## 12. Install the chart

Keep the Session Manager port-forward from step 9 running. In another terminal, from the project root:

```bash
export KUBECONFIG="$PWD/ansible/kubeconfig"
helm upgrade --install shoplite helm/shoplite \
  --namespace shoplite \
  --create-namespace \
  -f helm/shoplite/values.yaml \
  -f helm/shoplite/values-prod.yaml
kubectl get pods -n shoplite
kubectl get ingress -n shoplite
```

Wait until the pods are `Running` and their Ready column matches the replica count. Postgres and the API can take a minute on the first start.

```bash
kubectl get pods -n shoplite
terraform -chdir=terraform output -raw alb_dns_name
```

Open `http://` followed by that DNS name. Place an order in the browser. The status should move to `COMPLETED`. Direct API calls use the same host with the `/api` prefix, for example `http://<alb-dns-name>/api/products`.

For a local practice cluster that already has the images, use `values-dev.yaml` instead of `values-prod.yaml`.

## 13. Install monitoring

```bash
export GRAFANA_ADMIN_PASSWORD='choose-a-password'
export ALERT_WEBHOOK_URL='https://your-webhook.example/alerts'
chmod +x monitoring/install.sh
./monitoring/install.sh
```

This installs kube-prometheus-stack, Loki, Promtail, and Tempo in the `monitoring` namespace. Grafana loads `monitoring/dashboards/shoplite-golden-signals.json`. Alerts in `monitoring/alert-rules/shoplite.yaml` point at the runbooks in `monitoring/runbooks/`. A log line's `trace_id` opens the matching Tempo trace, and latency panels include exemplars.

## 14. Check the bill

In the AWS console, open Billing and Budgets. The budget name is `shoplite-monthly`. The alarm address is the email from `terraform.tfvars`. Confirm the email when AWS sends the subscription message, or the alarm cannot notify you.

## 15. CI and GitOps

GitHub Actions lives in `.github/workflows/`. On a pull request it runs the unit tests. On a push to `main` it also publishes the three images. It then commits the new image tags into the second repository, `shoplite-gitops`, which is the folder next to this project. Argo CD watches that repository and installs the Helm chart. The workflows do not deploy to the cluster.

Create the GitHub repository `shoplite-gitops` from `/Users/mohammaduzzaman/shoplite-gitops`. In the application repository settings, add:

| Name | Kind | Value |
|---|---|---|
| `GITOPS_REPOSITORY` | variable | `your-user/shoplite-gitops` |
| `GITOPS_TOKEN` | secret | a token that can push to that repository |
| `ECR_REGISTRY` | variable | optional, `123456789012.dkr.ecr.eu-central-1.amazonaws.com` |
| `AWS_ROLE_ARN` | secret | optional role used only when `ECR_REGISTRY` is set |

Replace `REPLACE_ME` in `shoplite-gitops` before the first Argo CD sync. The one-time Argo CD install is in that repository's README. After the first sync, a push to `main` is enough: Actions publishes the images, updates `envs/dev/values.yaml` and `envs/prod/values.yaml`, and Argo CD rolls the pods.

The diagram is `docs/architecture-diagram`. An example incident write-up is `docs/RCA`.

## 16. Destroy the stack after grading

Destroy the cluster before the state bucket. From `terraform/`:

```bash
terraform destroy
```

Type `yes`. Then remove the bucket and the lock table:

```bash
cd bootstrap
terraform destroy
```

`destroy` on the cluster removes the instances, the load balancer, the NAT instance, the VPC, ECR, and the budget. ECR repositories are set to delete even if they contain images. The bootstrap state file is local, so this command must be run on the same computer that applied the bootstrap stack.
