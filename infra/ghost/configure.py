import json
import os
import secrets
from pathlib import Path


def configure(root):
    env_path = root / ".env"
    if not env_path.exists():
        values = {
            "MYSQL_DATABASE": "ghost",
            "MYSQL_USER": "ghost",
            "MYSQL_PASSWORD": secrets.token_hex(32),
            "MYSQL_ROOT_PASSWORD": secrets.token_hex(32),
        }
        temporary = root / ".env.tmp"
        temporary.write_text(
            "".join(f"{key}={value}\n" for key, value in values.items())
        )
        temporary.chmod(0o600)
        temporary.replace(env_path)
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines())
    config = json.loads((root / "config.base.json").read_text())
    config["database"]["connection"]["password"] = values["MYSQL_PASSWORD"]
    temporary = root / "config.production.json.tmp"
    temporary.write_text(json.dumps(config))
    temporary.chmod(0o400)
    os.chown(temporary, 1000, 1000)
    temporary.replace(root / "config.production.json")


if __name__ == "__main__":
    configure(Path("/opt/ghost"))
