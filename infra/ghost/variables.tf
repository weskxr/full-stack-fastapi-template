variable "deployment_name" {
  type    = string
  default = "ghost-blog"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.deployment_name))
    error_message = "Use a deployment name of 2–32 lowercase letters, digits, or hyphens."
  }
}

variable "cloudflare_account_id" {
  type = string

  validation {
    condition     = can(regex("^[a-f0-9]{32}$", var.cloudflare_account_id))
    error_message = "Supply a Cloudflare account ID."
  }
}

variable "cloudflare_zone_id" {
  type = string

  validation {
    condition     = can(regex("^[a-f0-9]{32}$", var.cloudflare_zone_id))
    error_message = "Supply a Cloudflare zone ID."
  }
}

variable "zone_name" {
  type = string

  validation {
    condition     = length(var.zone_name) <= 253 && can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}$", var.zone_name))
    error_message = "Use the lowercase DNS name of your active Cloudflare zone."
  }
}

variable "subdomains" {
  type = object({
    blog  = string
    admin = string
    ssh   = string
  })
  default = {
    blog  = "blog"
    admin = "ghost-admin"
    ssh   = "ghost-ssh"
  }

  validation {
    condition = length(distinct(values(var.subdomains))) == 3 && alltrue([
      for name in values(var.subdomains) : can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", name))
    ])
    error_message = "Use three distinct, single-label subdomains."
  }
}

variable "access_team_name" {
  type = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.access_team_name))
    error_message = "Supply the team name from TEAM.cloudflareaccess.com."
  }
}

variable "admin_email" {
  type = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.admin_email))
    error_message = "Supply the email address allowed to authenticate through Cloudflare Access."
  }
}

variable "ssh_public_key" {
  type = string

  validation {
    condition     = can(regex("^ssh-ed25519 [A-Za-z0-9+/]+={0,3}( [^\\r\\n]*)?$", var.ssh_public_key))
    error_message = "Supply a single OpenSSH Ed25519 public key, without authorized_keys options."
  }
}

variable "server_type" {
  type    = string
  default = "cx23"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "smtp" {
  type = object({
    host     = string
    port     = number
    secure   = bool
    user     = string
    password = string
    from     = string
  })
  default   = null
  sensitive = true

  validation {
    condition     = var.smtp == null ? true : var.smtp.port >= 1 && var.smtp.port <= 65535 && floor(var.smtp.port) == var.smtp.port
    error_message = "SMTP port must be an integer between 1 and 65535."
  }
}
