mock_provider "hcloud" {
  mock_resource "hcloud_firewall" {
    defaults = { id = "123" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "456" }
  }
  mock_resource "hcloud_server" {
    defaults = {
      id           = "789"
      ipv4_address = "192.0.2.1"
      ipv6_address = "2001:db8::1"
    }
  }
}

mock_provider "cloudflare" {
  mock_resource "cloudflare_zero_trust_access_application" {
    defaults = { aud = "test-audience" }
  }
  mock_data "cloudflare_zero_trust_tunnel_cloudflared_token" {
    defaults = { token = "test-tunnel-token" }
  }
}

variables {
  cloudflare_account_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  cloudflare_zone_id    = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  zone_name             = "example.com"
  access_team_name      = "test-team"
  admin_email           = "admin@example.com"
  ssh_public_key        = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}

run "secure_deployment" {
  command = apply

  assert {
    condition     = length(hcloud_firewall.ghost.rule) == 0 && hcloud_server.ghost.firewall_ids == toset([123])
    error_message = "Deny-inbound firewall must be attached in the server create request."
  }

  assert {
    condition     = hcloud_server.ghost.delete_protection && hcloud_server.ghost.rebuild_protection
    error_message = "Server data must be protected from deletion and rebuild."
  }

  assert {
    condition = alltrue([
      for route in slice(cloudflare_zero_trust_tunnel_cloudflared_config.ghost.config.ingress, 0, 2) :
      route.origin_request.access.required && route.origin_request.access.aud_tag == tolist(["test-audience"])
    ])
    error_message = "Admin and SSH origins must validate Access tokens."
  }

  assert {
    condition     = length(cloudflare_zero_trust_access_policy.administrator.include) == 1 && one(cloudflare_zero_trust_access_policy.administrator.include).email.email == "admin@example.com"
    error_message = "Access must allow only the configured administrator."
  }

  assert {
    condition     = cloudflare_zero_trust_tunnel_cloudflared_config.ghost.config.ingress[3].service == "http_status:404"
    error_message = "Unmatched tunnel traffic must be rejected."
  }

  assert {
    condition     = !yamldecode(local.cloud_init).ssh_pwauth && yamldecode(local.cloud_init).disable_root && yamldecode(local.cloud_init).users[0].name == "ghostadmin"
    error_message = "Bootstrap must disable password and root SSH and create the administrator."
  }

  assert {
    condition     = length(local.cloud_init) <= 32768 && local.files["/etc/cloudflared/token"].permissions == "0600"
    error_message = "Cloud-init must fit Hetzner's limit and restrict the tunnel credential."
  }

  assert {
    condition     = !can(yamldecode(local.files["/opt/ghost/compose.yml"].content).services.db.ports) && !can(yamldecode(local.files["/opt/ghost/compose.yml"].content).services.ghost.ports) && alltrue([for port in yamldecode(local.files["/opt/ghost/compose.yml"].content).services.proxy.ports : startswith(port, "127.0.0.1:")])
    error_message = "Only proxy loopback ports may be published."
  }

  assert {
    condition     = local.ghost_config.url == "https://blog.example.com" && local.ghost_config.admin.url == "https://ghost-admin.example.com" && !can(local.ghost_config.database.connection.password)
    error_message = "Ghost must use HTTPS, a separate admin hostname, and server-generated database credentials."
  }

  assert {
    condition     = strcontains(local.files["/opt/ghost/nginx.conf"].content, "proxy_set_header Host ghost-admin.example.com;") && strcontains(local.files["/opt/ghost/nginx.conf"].content, "proxy_set_header X-Forwarded-Host ghost-admin.example.com;")
    error_message = "The public Content API must reach Ghost's backend virtual host without redirecting visitors to the protected admin domain."
  }
}

run "reject_duplicate_hostnames" {
  command = plan
  variables {
    subdomains = { blog = "blog", admin = "blog", ssh = "ssh" }
  }
  expect_failures = [var.subdomains]
}

run "reject_key_options" {
  command = plan
  variables {
    ssh_public_key = "command=evil ssh-ed25519 AAAA"
  }
  expect_failures = [var.ssh_public_key]
}

run "smtp_is_structured_data" {
  command = plan
  variables {
    smtp = {
      host     = "smtp.example.com"
      port     = 587
      secure   = false
      user     = "ghost"
      password = "quoted\"$HOME`example`"
      from     = "blog@example.com"
    }
  }
  assert {
    condition     = jsondecode(local.files["/opt/ghost/config.base.json"].content).mail.options.auth.pass == var.smtp.password
    error_message = "SMTP secrets must be JSON encoded, never interpolated into shell code."
  }
}
