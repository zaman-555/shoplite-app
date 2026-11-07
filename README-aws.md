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
├── inventory/aws_ec2.yml
├── roles/
│   ├── harden/                  SSH drop-in, ops group, log ACL, UFW, backup timer
│   ├── container_runtime/       containerd
│   └── k3s/                     Control plane, Traefik on 30080, worker join, kubeconfig
└── scripts/ssm-port-forward.sh
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
brew install awscli
brew install --cask session-manager-plugin
python3.12 -m pip install --user boto3 botocore
```

`python3` on this Mac is 3.8. Ansible and the AWS collection need 3.12, which is `python3.12`.

Confirm:

```bash
terraform version
ansible --version
aws --version
session-manager-plugin --version
```

`terraform version` should be 1.5 or newer.

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

## 6. Install the Ansible collections

```bash
cd ../ansible
ansible-galaxy collection install -r requirements.yml
```

This installs `amazon.aws` and `community.general`.

## 7. Run the playbook

Session Manager needs the nodes to register. Wait two or three minutes after apply, then:

```bash
export SSM_BUCKET="$(terraform -chdir=../terraform output -raw ansible_ssm_bucket)"
export AWS_REGION=eu-central-1
ansible-inventory --graph
```

The graph lists one host under `control_plane` and two under `worker`. The host names are instance ids. If the graph is empty, wait and run it again. The inventory ignores the NAT instance.

```bash
ansible-playbook site.yml
```

The playbook does three plays:

1. On every node: SSH drop-in, `ops` and `deploy`, the log directory ACL, UFW, the backup files, and containerd. The backup timer is started on the control plane only.
2. On the control plane: install k3s from the stable channel, publish Traefik on NodePort 30080, and copy the kubeconfig to `ansible/kubeconfig`.
3. On the workers, one at a time: join the cluster with the node token.

`ansible/kubeconfig` and `ansible/.k3s-token` are gitignored. The kubeconfig points at `https://127.0.0.1:6443`.

## 8. Open the cluster

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

You should see the control plane and both workers `Ready`.

The shop UI is the load balancer, after the targets are healthy:

```bash
terraform -chdir=../terraform output -raw alb_dns_name
```

Open `http://` that name. Traefik answers before the ShopLite pods exist. Deploying the shop into the cluster is a later step. The load balancer is already aimed at the ingress.

## 9. Check the bill

In the AWS console, open Billing and Budgets. The budget name is `shoplite-monthly`. The alarm address is the email from `terraform.tfvars`. Confirm the email when AWS sends the subscription message, or the alarm cannot notify you.

## 10. Destroy the stack after grading

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
