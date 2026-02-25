#!/usr/bin/env python3
"""Fetch real-world package/project names for training data augmentation.

Pulls top packages from PyPI, npm, crates.io and generates realistic
docker image names, repo names, etc. Writes one name per line to
training/wordlists/*.txt files.

Usage:
    python3 fetch_wordlists.py
"""

import json
import urllib.request
from pathlib import Path

WORDLISTS_DIR = Path(__file__).parent / "wordlists"

# Commands that should NEVER appear in placeholder lists — these are
# "functional" tokens the model needs to treat as actual commands
BLOCKED_NAMES = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "cargo", "rustc", "go", "java", "javac", "ruby", "gem",
    "git", "docker", "kubectl", "terraform", "ansible",
    "ls", "cd", "rm", "cp", "mv", "cat", "grep", "find", "sed", "awk",
    "curl", "wget", "ssh", "scp", "rsync", "tar", "zip", "unzip",
    "make", "cmake", "gcc", "g++", "clang",
    "sudo", "su", "chmod", "chown", "kill", "ps", "top", "htop",
    "systemctl", "service", "journalctl",
    "apt", "apt-get", "pacman", "yay", "brew", "dnf", "yum",
    "vim", "nvim", "nano", "emacs", "code",
    "bash", "zsh", "fish", "sh",
    "test", "true", "false", "echo", "printf",
}


def fetch_json(url: str) -> dict | list:
    """Fetch JSON from a URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "shit-training/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def filter_names(names: list[str]) -> list[str]:
    """Remove blocked names and duplicates, keep only clean identifiers."""
    seen = set()
    result = []
    for name in names:
        name = name.strip().lower()
        if not name or name in BLOCKED_NAMES or name in seen:
            continue
        # Skip names that are too short (likely to collide) or too long
        if len(name) < 2 or len(name) > 40:
            continue
        # Skip names with weird characters
        if not all(c.isalnum() or c in "-_." for c in name):
            continue
        seen.add(name)
        result.append(name)
    return result


def write_wordlist(name: str, entries: list[str]):
    """Write a wordlist file (one entry per line, sorted)."""
    path = WORDLISTS_DIR / f"{name}.txt"
    # Sort for deterministic diffs in git
    entries = sorted(set(entries))
    path.write_text("\n".join(entries) + "\n")
    print(f"  {name}.txt: {len(entries)} entries")


def fetch_pypi_top() -> list[str]:
    """Fetch top PyPI packages from hugovk's top-pypi-packages dataset."""
    print("Fetching top PyPI packages...")
    try:
        data = fetch_json("https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json")
        return [row["project"] for row in data["rows"][:800]]
    except Exception as e:
        print(f"  Warning: PyPI fetch failed ({e}), using fallback")
        return []


def fetch_npm_top() -> list[str]:
    """Fetch popular npm packages from the registry."""
    print("Fetching popular npm packages...")
    names = []
    try:
        # Search across several keyword categories to get diverse results
        keywords = [
            "keywords:javascript", "keywords:typescript", "keywords:react",
            "keywords:node", "keywords:cli", "keywords:utility",
            "keywords:server", "keywords:database", "keywords:testing",
        ]
        for kw in keywords:
            for offset in range(0, 250, 250):
                url = f"https://registry.npmjs.org/-/v1/search?text={kw}&size=250&from={offset}"
                data = fetch_json(url)
                for obj in data.get("objects", []):
                    name = obj.get("package", {}).get("name", "")
                    # Skip scoped packages (@org/pkg) — they cause issues in command contexts
                    if name and not name.startswith("@"):
                        names.append(name)
        return names
    except Exception as e:
        print(f"  Warning: npm fetch failed ({e}), using fallback")
        return []


def fetch_crates_top() -> list[str]:
    """Fetch top crates from crates.io."""
    print("Fetching top crates...")
    names = []
    try:
        for page in range(1, 6):
            url = f"https://crates.io/api/v1/crates?page={page}&per_page=100&sort=downloads"
            data = fetch_json(url)
            for crate in data.get("crates", []):
                names.append(crate["id"])
        return names
    except Exception as e:
        print(f"  Warning: crates.io fetch failed ({e}), using fallback")
        return []


def generate_docker_images() -> list[str]:
    """Generate realistic docker image names (no myapp!)."""
    # Real official images
    official = [
        "nginx", "postgres", "redis", "mysql", "mariadb", "mongo",
        "memcached", "rabbitmq", "elasticsearch", "kibana", "logstash",
        "grafana/grafana", "prom/prometheus", "traefik", "caddy",
        "vault", "consul", "minio", "keycloak", "gitlab/gitlab-ce",
        "jenkins/jenkins", "sonarqube", "nexus3", "registry",
        "httpd", "haproxy", "envoy", "linkerd2-proxy",
        "influxdb", "clickhouse", "cassandra", "couchdb", "neo4j",
        "wordpress", "ghost", "drupal", "joomla", "mediawiki",
        "nextcloud", "gitea", "drone/drone", "argo", "airflow",
        "superset", "metabase", "redash", "jupyter/base-notebook",
        "tensorflow/tensorflow", "pytorch/pytorch",
    ]
    # Realistic app-style names (the kind people actually use)
    app_names = [
        "auth-service", "api-gateway", "user-service", "payment-service",
        "notification-service", "order-service", "inventory-service",
        "search-service", "chat-service", "email-service",
        "frontend-app", "admin-panel", "dashboard-ui", "landing-page",
        "worker-processor", "queue-consumer", "event-handler",
        "data-pipeline", "etl-runner", "cron-scheduler",
        "billing-api", "analytics-service", "recommendation-engine",
        "file-uploader", "image-resizer", "pdf-generator",
        "health-checker", "load-balancer", "rate-limiter",
        "cache-warmer", "session-store", "config-server",
        "log-aggregator", "metrics-collector", "trace-exporter",
        "deploy-bot", "ci-runner", "test-harness",
        "proxy-server", "websocket-gateway", "grpc-server",
        "task-scheduler", "job-runner", "batch-processor",
        "content-api", "media-service", "asset-manager",
    ]
    return official + app_names


def generate_repo_names() -> list[str]:
    """Generate realistic repository names."""
    return [
        # Product-style
        "acme-api", "acme-web", "acme-mobile", "acme-cli",
        "dashboard", "portal", "console", "platform",
        "marketplace", "storefront", "checkout", "cart",
        # Service-style
        "auth-service", "user-api", "billing-api", "payment-gateway",
        "notification-hub", "event-bus", "message-queue",
        "search-engine", "recommendation-api", "analytics-api",
        "file-service", "media-api", "content-api",
        # Infrastructure
        "infra", "terraform-modules", "k8s-configs", "helm-charts",
        "docker-images", "ci-pipelines", "deploy-scripts",
        "monitoring-stack", "logging-stack", "tracing-stack",
        # Libraries/tools
        "common-lib", "shared-utils", "core-sdk", "client-sdk",
        "data-models", "proto-definitions", "api-contracts",
        "lint-rules", "test-fixtures", "dev-tools",
        # Project naming patterns
        "phoenix", "atlas", "nova", "pulse", "forge",
        "beacon", "compass", "horizon", "nexus", "orbit",
        "prism", "relay", "sentinel", "shuttle", "spark",
        "summit", "titan", "vapor", "vertex", "zenith",
        "aurora", "cascade", "dynamo", "echo", "flux",
        "genesis", "hive", "iris", "jade", "kite",
        "lunar", "mesa", "oasis", "pinnacle", "quartz",
        "ripple", "sierra", "tundra", "unity", "vortex",
        # Language-specific project patterns
        "fastapi-template", "express-starter", "rails-app",
        "spring-boot-api", "flask-backend", "django-project",
        "next-app", "nuxt-app", "svelte-kit", "remix-app",
        "actix-web-api", "axum-service", "gin-api", "fiber-app",
        # Monorepo / workspace
        "monorepo", "workspace", "packages", "apps",
        "frontend", "backend", "services", "tools",
        # OSS project vibes
        "rustlings", "exercism", "leetcode-solutions",
        "dotfiles", "config", "setup", "bootstrap",
    ]


def generate_github_users() -> list[str]:
    """Generate realistic GitHub usernames and org names."""
    return [
        # Personal-style
        "jsmith", "akim", "mchen", "patel", "garcia", "mueller",
        "tanaka", "silva", "wang", "johnson", "williams", "brown",
        "jones", "davis", "miller", "wilson", "moore", "taylor",
        "dev-alex", "code-sam", "hack-max", "byte-lee",
        # Org-style
        "acme-corp", "bigtech-inc", "startup-labs", "open-source-co",
        "cloud-systems", "data-team", "infra-ops", "platform-eng",
        "dev-tools-inc", "api-co", "web-studio", "mobile-labs",
        "ml-research", "security-team", "devops-crew", "sre-team",
        # Community/project orgs
        "rust-lang", "golang", "nodejs", "python", "dotnet",
        "apache", "eclipse", "mozilla", "linux", "kubernetes",
        "hashicorp", "elastic", "grafana", "prometheus",
        "vercel", "netlify", "supabase", "prisma", "turbo",
        "tailwindlabs", "shadcn", "radix-ui", "headlessui",
    ]


def generate_k8s_resources() -> list[str]:
    """Generate realistic Kubernetes resource names."""
    return [
        # Services
        "auth-service", "user-service", "order-service",
        "payment-service", "notification-service", "search-service",
        "gateway", "api-gateway", "ingress-nginx",
        # Deployments
        "frontend", "backend", "worker", "scheduler", "cron",
        "web-app", "admin-app", "api-server", "grpc-server",
        # Databases
        "postgres", "redis", "mongo", "elasticsearch",
        "mysql", "cassandra", "rabbitmq", "kafka",
        # Infra
        "prometheus", "grafana", "jaeger", "fluentd",
        "cert-manager", "external-dns", "vault",
        "istio-proxy", "envoy-sidecar", "linkerd",
        # Jobs
        "db-migration", "data-sync", "backup-job",
        "cleanup-cron", "report-generator", "index-rebuild",
    ]


def generate_system_packages() -> list[str]:
    """Generate realistic system package names (apt/pacman/brew)."""
    return [
        # Core tools
        "vim", "neovim", "nano", "emacs",
        "git", "git-lfs", "tig", "lazygit",
        "curl", "wget", "aria2", "httpie",
        "htop", "btop", "glances", "nmon",
        "tmux", "screen", "byobu", "zellij",
        "zsh", "fish", "starship", "oh-my-zsh",
        # Dev tools
        "build-essential", "gcc", "g++", "clang", "llvm",
        "cmake", "meson", "ninja-build", "autoconf", "automake",
        "gdb", "lldb", "valgrind", "strace", "ltrace",
        "python3", "python3-pip", "python3-venv", "python3-dev",
        "nodejs", "npm", "yarn",
        "rustup", "golang", "openjdk-17-jdk",
        # Networking
        "openssh-server", "openssh-client", "mosh",
        "nmap", "netcat", "socat", "tcpdump", "wireshark",
        "iptables", "nftables", "ufw", "firewalld",
        "dnsutils", "bind-utils", "dig", "nslookup",
        "iproute2", "net-tools", "traceroute", "mtr",
        # System
        "systemd", "cron", "logrotate", "rsyslog",
        "lsof", "procps", "psmisc", "sysstat",
        "e2fsprogs", "xfsprogs", "btrfs-progs", "lvm2",
        "smartmontools", "hdparm", "nvme-cli",
        # Modern CLI tools
        "ripgrep", "fd-find", "bat", "exa", "eza",
        "fzf", "delta", "dust", "duf", "procs",
        "sd", "choose", "jq", "yq", "xsv",
        "tree", "ncdu", "ranger", "lf", "nnn",
        "tokei", "hyperfine", "bandwhich", "bottom",
        # Containers / orchestration
        "docker-ce", "docker-compose", "podman", "buildah",
        "kubectl", "helm", "k9s", "kubectx", "kubens",
        "terraform", "ansible", "puppet", "chef",
        # Databases (client packages)
        "postgresql-client", "mysql-client", "sqlite3",
        "redis-tools", "mongodb-clients",
        # Libraries (commonly installed via system pkg manager)
        "libssl-dev", "libffi-dev", "libpq-dev",
        "zlib1g-dev", "libbz2-dev", "libreadline-dev",
        "libsqlite3-dev", "libncurses-dev", "liblzma-dev",
        "pkg-config", "libdbus-1-dev", "libglib2.0-dev",
    ]


def main():
    WORDLISTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing wordlists to {WORDLISTS_DIR}/\n")

    # Fetch from APIs
    pypi_names = fetch_pypi_top()
    npm_names = fetch_npm_top()
    crate_names = fetch_crates_top()

    # Python packages: API results + fallback extras
    python_pkgs = filter_names(pypi_names) if pypi_names else []
    if len(python_pkgs) < 200:
        print("  Adding fallback Python packages...")
        python_pkgs = filter_names(python_pkgs + [
            "requests", "flask", "django", "fastapi", "numpy", "pandas",
            "scipy", "matplotlib", "sqlalchemy", "celery", "redis", "boto3",
            "pytest", "black", "mypy", "pydantic", "httpx", "aiohttp",
            "pillow", "cryptography", "uvicorn", "gunicorn", "poetry",
            "click", "typer", "rich", "loguru", "tqdm", "attrs",
            "alembic", "peewee", "pymongo", "psycopg2", "asyncpg",
            "scrapy", "selenium", "beautifulsoup4", "lxml",
            "openai", "anthropic", "langchain", "transformers", "torch",
            "tensorflow", "scikit-learn", "xgboost", "lightgbm",
        ])
    write_wordlist("packages-python", python_pkgs)

    # npm packages
    node_pkgs = filter_names(npm_names) if npm_names else []
    if len(node_pkgs) < 200:
        print("  Adding fallback npm packages...")
        node_pkgs = filter_names(node_pkgs + [
            "express", "react", "vue", "next", "webpack", "typescript",
            "lodash", "axios", "prisma", "tailwindcss", "eslint", "prettier",
            "jest", "vitest", "mocha", "chai", "supertest",
            "fastify", "koa", "nestjs", "socket.io",
            "dotenv", "winston", "cors", "helmet", "joi", "zod",
            "date-fns", "dayjs", "moment", "luxon",
            "redux", "mobx", "zustand", "jotai", "xstate",
            "vite", "rollup", "esbuild", "swc", "babel",
        ])
    write_wordlist("packages-node", node_pkgs)

    # Rust crates
    rust_pkgs = filter_names(crate_names) if crate_names else []
    if len(rust_pkgs) < 100:
        print("  Adding fallback Rust crates...")
        rust_pkgs = filter_names(rust_pkgs + [
            "tokio", "serde", "clap", "actix-web", "reqwest", "anyhow",
            "thiserror", "tracing", "log", "chrono", "uuid",
            "rand", "rayon", "crossbeam", "once_cell",
            "async-trait", "futures", "hyper", "axum", "warp",
            "diesel", "sqlx", "sea-orm",
        ])
    write_wordlist("packages-rust", rust_pkgs)

    # Docker images
    write_wordlist("docker-images", generate_docker_images())

    # Repo names
    write_wordlist("repo-names", generate_repo_names())

    # GitHub users
    write_wordlist("github-users", generate_github_users())

    # K8s resources
    write_wordlist("k8s-resources", generate_k8s_resources())

    # System packages
    write_wordlist("system-packages", generate_system_packages())

    print(f"\nDone! Wordlists written to {WORDLISTS_DIR}/")


if __name__ == "__main__":
    main()
