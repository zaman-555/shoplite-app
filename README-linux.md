# ShopLite on Ubuntu: users, permissions, backup, and firewall

Run these steps on one Ubuntu 22.04 or 24.04 server. That server can be an EC2 instance or a local virtual machine. Do not run them on the Mac you used to build the app. The Docker Compose stack from this repository must already be running on that server (`make up` from the project directory).

The Compose project name is `shoplite`. Postgres is the container `shoplite-postgres-1`, database `shoplite`, user `shoplite`, password `shoplite`. Postgres is not published to the host. The stack publishes:

| Port on the server | Service |
|---|---|
| 8080 | Shop web UI |
| 8000 | Catalog API |
| 8001 | Worker metrics |

The firewall task allows inbound 22, 80, and 443 only. Ports 8000, 8001, and 8080 stay closed to other machines.

Keep a second SSH session open for the whole of sections 3.1 and 3.4. If a rule locks the first session, the second session is how you undo it.

The files for this milestone live under `linux/`:

```text
linux/
├── sshd_config
├── systemd/
│   ├── shoplite-backup.service
│   ├── shoplite-backup.timer
│   └── shoplite-backup.sh
├── firewall/
│   └── ufw.sh
└── evidence/
```

Put the terminal screenshots for each section in `linux/evidence/`.

## 3.1 Users and SSH

### 1. Create the ops group and the deploy user

```bash
sudo groupadd ops
sudo useradd --create-home --shell /bin/bash deploy
sudo usermod --append --groups ops deploy
id deploy
```

`id deploy` must list `ops` in the groups. Screenshot that line.

### 2. Give deploy a key before you turn passwords off

On your own computer, if you do not already have a key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/shoplite_deploy -N ""
```

Copy the public key to the server. Replace `SERVER` with the server address. This still uses your current login, before password login is disabled:

```bash
ssh-copy-id -i ~/.ssh/shoplite_deploy.pub deploy@SERVER
```

If `ssh-copy-id` cannot log in as `deploy` yet, from the server:

```bash
sudo mkdir -p /home/deploy/.ssh
sudo cp ~/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

From your computer, confirm the key works. Leave this session open:

```bash
ssh -i ~/.ssh/shoplite_deploy deploy@SERVER
```

### 3. Disable root login and password login

On the server:

```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
sudo cp linux/sshd_config /etc/ssh/sshd_config.d/99-shoplite.conf
sudo sshd -t
sudo systemctl reload ssh
```

`sshd -t` must print nothing. If it prints an error, restore the backup and do not reload:

```bash
sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
sudo rm /etc/ssh/sshd_config.d/99-shoplite.conf
sudo systemctl reload ssh
```

Screenshot `sshd -t` and the contents of `99-shoplite.conf`.

### 4. Show that root and password login are refused

From your computer, not from the server. The key login from step 2 must still be open.

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@SERVER
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no deploy@SERVER
```

Both must fail. The root attempt is refused because root login is disabled. The deploy attempt is refused because password login is disabled. Screenshot both failures. Then confirm the key still works:

```bash
ssh -i ~/.ssh/shoplite_deploy deploy@SERVER
```

## 3.2 File permissions

Create the log directory so only the `ops` group can read it. These three commands are the whole change: one `chown`, one `chmod`, and one `setfacl` rule.

```bash
sudo mkdir -p /var/log/shoplite
sudo chown root:root /var/log/shoplite
sudo chmod 700 /var/log/shoplite
sudo setfacl -m g:ops:r-x /var/log/shoplite
sudo ls -l -d /var/log/shoplite
sudo getfacl /var/log/shoplite
```

`ls -l` shows owner `root` and mode `drwxr-x---+`. The `+` means an ACL is present. `getfacl` shows one extra group line, `group:ops:r-x`, and `other::---`. Screenshot both commands.

Check the access with the two users:

```bash
sudo -u deploy ls /var/log/shoplite
sudo -u nobody ls /var/log/shoplite
```

`deploy` can list the directory because `deploy` is in `ops`. `nobody` is denied.

Mode `777` is incorrect because it lets every account on the server read, write, and enter the directory.

## 3.3 systemd backup

The backup script dumps the ShopLite database from inside `shoplite-postgres-1` and writes a timestamped `.sql` file under `/var/backups/shoplite/`. The service runs as root because it uses the Docker socket and writes into `/var/backups`.

### 1. Install the files

From the project directory on the server:

```bash
sudo mkdir -p /var/backups/shoplite
sudo cp linux/systemd/shoplite-backup.sh /usr/local/bin/shoplite-backup.sh
sudo chmod 755 /usr/local/bin/shoplite-backup.sh
sudo cp linux/systemd/shoplite-backup.service /etc/systemd/system/shoplite-backup.service
sudo cp linux/systemd/shoplite-backup.timer /etc/systemd/system/shoplite-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now shoplite-backup.timer
```

The timer fires every night at 02:00. `Persistent=true` runs a missed backup after the server boots. The service unit sets `Restart=on-failure`.

### 2. Run one backup now and record the evidence

```bash
sudo systemctl start shoplite-backup.service
sudo systemctl status shoplite-backup.service --no-pager
sudo systemctl list-timers shoplite-backup.timer --no-pager
sudo ls -l /var/backups/shoplite
```

`status` shows `status=0/SUCCESS` after a successful run, and the unit file contains `Restart=on-failure`. `list-timers` shows the next 02:00 run. `ls` shows a file named `shoplite-YYYYMMDDTHHMMSSZ.sql`. Screenshot all three.

The stack must be up. If the container name is different, `docker ps` shows the Postgres name. The script expects `shoplite-postgres-1`.

## 3.4 Firewall and ports

### 1. Allow only 22, 80, and 443

Keep the second SSH session open. Apply UFW from the first session:

```bash
sudo bash linux/firewall/ufw.sh
```

`status` must show the default incoming policy as `deny`, and only `22/tcp`, `80/tcp`, and `443/tcp` allowed. Screenshot that.

### 2. Show what is listening

On the server:

```bash
sudo ss -tulpn
```

You should see `sshd` on port 22. ShopLite also listens on 8080, 8000, and 8001 because Compose publishes them. Those three ports are not in the UFW allow list. Screenshot `ss -tulpn`.

### 3. From another machine, show one open port and one blocked port

Replace `SERVER` with the server address. Run these on your computer, not on the server.

Open port 22:

```bash
nc -vz -w 5 SERVER 22
```

`nc` reports that the connection succeeded. Screenshot it.

Blocked port 9000. Nothing in this project listens on 9000, and UFW denies it:

```bash
nc -vz -w 5 SERVER 9000
```

`nc` times out or reports that the port is filtered. Screenshot it.

Docker inserts its own firewall rules for published ports. A UFW deny does not always block 8000, 8001, or 8080. Use port 9000 for the blocked-port screenshot so the evidence is the UFW deny rule. Do not remove the SSH allow rule while you are connected.

## Evidence checklist

| Section | Save |
|---|---|
| 3.1 | `id deploy`; `linux/sshd_config`; failed `ssh` as root; failed password `ssh` as deploy; successful key `ssh` as deploy |
| 3.2 | `ls -l -d` and `getfacl` of `/var/log/shoplite`; the one-line reason mode 777 is wrong |
| 3.3 | files in `linux/systemd/`; `systemctl status`; `systemctl list-timers`; the `.sql` file in `/var/backups/shoplite` |
| 3.4 | `linux/firewall/ufw.sh`; `ufw status verbose`; `ss -tulpn`; `nc` to port 22; `nc` to port 9000 |
