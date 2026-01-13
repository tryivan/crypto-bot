import yaml


def generate_compose(pairs_file: str) -> None:
    """
    Gera docker-compose.yml a partir da lista de pares.
    Arquivo config/pairs.yml
    """

    with open(pairs_file, "r") as f:
        config = yaml.safe_load(f)

    services = {}
    volumes = {}

    for pair in config["pairs"]:
        name = pair["symbol"].split("/")[0].lower()
        service_name = f"bot-{name}"
        volume_name = f"logs-{name}"

        services[service_name] = {
            "build": ".",
            "env_file": f"./config/{pair['env_file']}",
            "volumes": [f"{volume_name}:/app/logs"],
            "restart": "unless-stopped",
        }

        volumes[volume_name] = None

    compose = {
        "services": services,
        "volumes": volumes,
    }

    with open("docker-compose.yml", "w") as f:
        yaml.dump(compose, f, default_flow_style=False)

    print(f"✅ docker-compose.yml gerado com {len(services)} bots")


if __name__ == "__main__":
    generate_compose("config/pairs.yml")
