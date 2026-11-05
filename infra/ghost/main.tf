locals {
  hostnames = { for kind, label in var.subdomains : kind => "${label}.${var.zone_name}" }
  ghost_config = merge({
    url    = "https://${local.hostnames.blog}"
    admin  = { url = "https://${local.hostnames.admin}" }
    server = { host = "0.0.0.0", port = 2368 }
    database = {
      client = "mysql"
      connection = {
        host     = "db"
        user     = "ghost"
        database = "ghost"
      }
    }
    paths   = { contentPath = "/var/lib/ghost/content" }
    logging = { transports = ["stdout"] }
    }, var.smtp == null ? {} : {
    mail = {
      transport = "SMTP"
      from      = var.smtp.from
      options = {
        host   = var.smtp.host
        port   = var.smtp.port
        secure = var.smtp.secure
        auth   = { user = var.smtp.user, pass = var.smtp.password }
      }
    }
  })
  files = {
    "/opt/ghost/compose.yml"                             = { content = file("${path.module}/compose.yml"), permissions = "0600" }
    "/opt/ghost/nginx.conf"                              = { content = file("${path.module}/nginx.conf"), permissions = "0644" }
    "/opt/ghost/config.base.json"                        = { content = jsonencode(local.ghost_config), permissions = "0600" }
    "/opt/ghost/bootstrap.sh"                            = { content = file("${path.module}/bootstrap.sh"), permissions = "0700" }
    "/opt/ghost/backup.sh"                               = { content = file("${path.module}/backup.sh"), permissions = "0700" }
    "/opt/ghost/configure.py"                            = { content = file("${path.module}/configure.py"), permissions = "0600" }
    "/etc/cloudflared/token"                             = { content = data.cloudflare_zero_trust_tunnel_cloudflared_token.ghost.token, permissions = "0600" }
    "/etc/systemd/system/cloudflared.service"            = { content = file("${path.module}/cloudflared.service"), permissions = "0644" }
    "/etc/systemd/system/ghost.service"                  = { content = file("${path.module}/ghost.service"), permissions = "0644" }
    "/etc/systemd/system/docker.service.d/metadata.conf" = { content = file("${path.module}/docker-metadata.conf"), permissions = "0644" }
    "/etc/ssh/sshd_config.d/00-ghost.conf" = {
      content = join("\n", [
        "AddressFamily inet",
        "ListenAddress 127.0.0.1",
        "PermitRootLogin no",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PubkeyAuthentication yes",
        "AllowUsers ghostadmin",
        "AllowAgentForwarding no",
        "X11Forwarding no",
        ""
      ])
      permissions = "0644"
    }
  }
  cloud_init = sensitive("#cloud-config\n${yamlencode({
    ssh_pwauth   = false
    disable_root = true
    users = [{
      name                = "ghostadmin"
      shell               = "/bin/bash"
      groups              = ["sudo"]
      sudo                = "ALL=(ALL) NOPASSWD:ALL"
      lock_passwd         = true
      ssh_authorized_keys = [var.ssh_public_key]
    }]
    write_files = [for path, file in local.files : {
      path        = path
      owner       = "root:root"
      permissions = file.permissions
      encoding    = "b64"
      content     = base64encode(file.content)
    }]
    runcmd = [["/bin/bash", "/opt/ghost/bootstrap.sh"]]
  })}")
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "ghost" {
  account_id = var.cloudflare_account_id
  name       = var.deployment_name
  config_src = "cloudflare"
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "ghost" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.ghost.id
}

resource "cloudflare_zero_trust_access_policy" "administrator" {
  account_id = var.cloudflare_account_id
  name       = "${var.deployment_name}-administrator"
  decision   = "allow"
  include    = [{ email = { email = var.admin_email } }]
}

resource "cloudflare_zero_trust_access_application" "protected" {
  for_each = toset(["admin", "ssh"])

  account_id                  = var.cloudflare_account_id
  name                        = "${var.deployment_name}-${each.key}"
  domain                      = local.hostnames[each.key]
  type                        = "self_hosted"
  session_duration            = "8h"
  allow_authenticate_via_warp = false
  http_only_cookie_attribute  = true
  policies = [{
    id         = cloudflare_zero_trust_access_policy.administrator.id
    precedence = 1
  }]
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "ghost" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.ghost.id
  config = {
    ingress = [
      {
        hostname = local.hostnames.admin
        service  = "http://127.0.0.1:8081"
        origin_request = {
          access = {
            required  = true
            team_name = var.access_team_name
            aud_tag   = [cloudflare_zero_trust_access_application.protected["admin"].aud]
          }
        }
      },
      {
        hostname = local.hostnames.ssh
        service  = "ssh://127.0.0.1:22"
        origin_request = {
          access = {
            required  = true
            team_name = var.access_team_name
            aud_tag   = [cloudflare_zero_trust_access_application.protected["ssh"].aud]
          }
        }
      },
      { hostname = local.hostnames.blog, service = "http://127.0.0.1:8080" },
      { service = "http_status:404" }
    ]
  }
}

resource "cloudflare_dns_record" "ghost" {
  for_each = local.hostnames

  zone_id = var.cloudflare_zone_id
  name    = each.value
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.ghost.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1

  depends_on = [cloudflare_zero_trust_tunnel_cloudflared_config.ghost]
}

resource "hcloud_firewall" "ghost" {
  name   = var.deployment_name
  labels = { deployment = var.deployment_name }
}

resource "hcloud_ssh_key" "administrator" {
  name       = "${var.deployment_name}-administrator"
  public_key = var.ssh_public_key
}

resource "hcloud_server" "ghost" {
  name               = var.deployment_name
  image              = "ubuntu-24.04"
  server_type        = var.server_type
  location           = var.location
  ssh_keys           = [hcloud_ssh_key.administrator.id]
  firewall_ids       = [hcloud_firewall.ghost.id]
  user_data          = local.cloud_init
  delete_protection  = true
  rebuild_protection = true
  labels             = { deployment = var.deployment_name }

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [cloudflare_dns_record.ghost]

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(local.cloud_init) <= 32768
      error_message = "Rendered cloud-init exceeds Hetzner's 32 KiB limit."
    }
  }
}

output "deployment" {
  value = {
    server_id   = hcloud_server.ghost.id
    ipv4        = hcloud_server.ghost.ipv4_address
    ipv6        = hcloud_server.ghost.ipv6_address
    tunnel_id   = cloudflare_zero_trust_tunnel_cloudflared.ghost.id
    hostnames   = local.hostnames
    dns_ids     = { for kind, record in cloudflare_dns_record.ghost : kind => record.id }
    access_ids  = { for kind, app in cloudflare_zero_trust_access_application.protected : kind => app.id }
    account_id  = var.cloudflare_account_id
    team_name   = var.access_team_name
    firewall_id = hcloud_firewall.ghost.id
  }
}
