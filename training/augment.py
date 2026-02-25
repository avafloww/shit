#!/usr/bin/env python3
"""Augment base training examples with template variations.

Reads base examples from generate_data.py output and multiplies them by
varying file paths, branch names, package names, usernames, hostnames, etc.

Output: augmented JSONL with the same schema as the input.
"""

import argparse
import json
import random
import re
from pathlib import Path

WORDLISTS_DIR = Path(__file__).parent / "wordlists"


def load_wordlist(name: str) -> list[str]:
    """Load a wordlist from training/wordlists/{name}.txt (one entry per line)."""
    path = WORDLISTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Wordlist {path} not found. Run fetch_wordlists.py first."
        )
    entries = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return entries


# ---------------------------------------------------------------------------
# Replacement pools
# Inline lists for small/specialized pools, wordlist files for large ones
# ---------------------------------------------------------------------------

BRANCHES = [
    # main-line
    "main", "master", "develop", "staging", "production", "trunk",
    "release", "stable", "nightly", "canary",
    # features
    "feature-auth", "feature-login", "feature-api", "feature-ui",
    "feature-dashboard", "feature-search", "feature-payments",
    "feature-notifications", "feature-onboarding", "feature-settings",
    "feature-profile", "feature-admin", "feature-reports", "feature-export",
    "feature-import", "feature-webhook", "feature-oauth", "feature-2fa",
    "feature-dark-mode", "feature-mobile", "feature-redesign",
    "feature-caching", "feature-pagination", "feature-filtering",
    "feature-sorting", "feature-bulk-actions", "feature-csv-export",
    # fixes
    "fix-typo", "fix-crash", "fix-memory-leak", "fix-timeout",
    "fix-auth", "fix-login", "fix-null-pointer", "fix-race-condition",
    "fix-sql-injection", "fix-xss", "fix-csp", "fix-cors",
    "fix-pagination", "fix-encoding", "fix-timezone", "fix-locale",
    "fix-scroll", "fix-overflow", "fix-layout", "fix-z-index",
    # hotfix
    "hotfix-security", "hotfix-deploy", "hotfix-prod", "hotfix-critical",
    "hotfix-regression", "hotfix-data-loss", "hotfix-outage",
    # release
    "release-1.0", "release-1.1", "release-2.0", "release-2.3",
    "release-3.0", "release-0.9", "release-4.2", "release-1.0.1",
    # chore / refactor / ci
    "refactor-db", "refactor-auth", "refactor-api", "refactor-models",
    "chore-deps", "chore-lint", "chore-format", "chore-types",
    "ci-pipeline", "ci-docker", "ci-cache", "ci-deploy",
    "test-coverage", "test-e2e", "test-unit", "test-integration",
    "docs-api", "docs-setup", "docs-readme",
    # user-prefixed
    "alice/feature-login", "bob/fix-crash", "dev/experiment",
    "user/wip", "alice/refactor", "bob/hotfix",
]

PACKAGES = (
    load_wordlist("packages-python")
    + load_wordlist("packages-node")
    + load_wordlist("packages-rust")
)

USERNAMES = [
    "alice", "bob", "charlie", "dave", "eve", "frank", "grace",
    "henry", "iris", "jack", "kate", "leo", "mia", "noah",
    "dev", "admin", "deploy", "user", "root", "ubuntu",
    "ec2-user", "jenkins", "ci", "github-actions", "runner",
    "webapp", "api", "worker", "scheduler", "monitor",
]

HOSTNAMES = [
    "localhost", "server01", "server02", "server03",
    "prod-web-1", "prod-web-2", "prod-db-1",
    "staging.example.com", "dev.example.com",
    "db.internal", "api.example.com", "api.internal",
    "192.168.1.100", "192.168.1.101", "10.0.0.5", "10.0.0.10",
    "172.16.0.1", "my-server.cloud", "node-1.cluster.local",
    "node-2.cluster.local", "bastion.example.com",
    "jump.internal", "vpn.example.com",
]

PORTS = [
    "80", "443", "3000", "3001", "3306", "4000", "4200",
    "5000", "5001", "5173", "5432", "6379", "6380",
    "8000", "8080", "8081", "8443", "8888", "9000",
    "9090", "9200", "9300", "27017", "27018",
]

FILE_PATHS = [
    # Python
    "src/main.py", "src/app.py", "src/server.py", "src/cli.py",
    "app/models.py", "app/views.py", "app/controllers.py",
    "app/routes.py", "app/utils.py", "app/helpers.py",
    "config/settings.py", "config/database.py", "config/logging.py",
    "tests/test_main.py", "tests/test_api.py", "tests/test_models.py",
    "tests/conftest.py", "migrations/001_initial.py",
    # Rust
    "src/main.rs", "src/lib.rs", "src/server.rs", "src/cli.rs",
    "src/handlers.rs", "src/models.rs", "src/db.rs", "src/error.rs",
    "src/config.rs", "src/auth.rs",
    # TypeScript / JS
    "src/index.ts", "src/app.ts", "src/server.ts",
    "src/routes/index.ts", "src/controllers/auth.ts",
    "src/models/user.ts", "src/utils/helpers.ts",
    "components/Header.tsx", "components/Footer.tsx",
    "components/Button.tsx", "components/Modal.tsx",
    "pages/index.tsx", "pages/about.tsx", "pages/login.tsx",
    "styles/global.css", "styles/app.scss",
    # Go
    "pkg/server/handler.go", "internal/auth/jwt.go",
    "cmd/main.go", "internal/db/postgres.go",
    # Config
    "config/config.yaml", "config/app.toml", ".env",
    "docker-compose.yml", "Dockerfile", "Makefile",
    "package.json", "Cargo.toml", "pyproject.toml",
    # Docs
    "docs/README.md", "README.md", "CHANGELOG.md",
]

DIR_PATHS = [
    "projects/new-app", "projects/my-service", "projects/api",
    "src/components", "src/modules", "src/utils",
    "backend/api", "backend/services", "backend/workers",
    "frontend/build", "frontend/dist", "frontend/src",
    "deploy/scripts", "deploy/k8s", "deploy/terraform",
    "tmp/cache", "tmp/uploads", "tmp/exports",
    "var/log/app", "var/log/nginx", "var/run/app",
    "opt/services", "opt/apps", "opt/myapp",
    "home/user/docs", "home/user/projects", "home/user/workspace",
    "workspace/experiment", "workspace/prototype",
    "data/output", "data/input", "data/raw", "data/processed",
    "models/checkpoints", "models/weights", "models/cache",
    "logs/app", "logs/access", "logs/error",
]

# SSH key file variants
SSH_KEY_FILES = [
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "deploy_key", "github_key", "work_key",
]

DOCKER_IMAGES = load_wordlist("docker-images")

K8S_RESOURCES = load_wordlist("k8s-resources")

COMMANDS_TYPOS = {
    "build": ["biuld", "buld", "buidl", "buuild", "bulid", "buidld"],
    "install": ["isntall", "instal", "instll", "insatll", "intall", "intsall"],
    "start": ["strat", "statr", "satrt", "sart", "staart"],
    "test": ["tset", "tets", "testt", "tes", "teest"],
    "status": ["stauts", "staus", "statsu", "satus", "statuss"],
    "commit": ["comit", "commti", "commt", "committ", "coommit"],
    "push": ["psuh", "psh", "puhs", "pushh", "pssh"],
    "pull": ["plul", "pll", "pulll", "ull", "pul"],
    "checkout": ["chekout", "checout", "checkotu", "chekcout", "chcekout"],
    "merge": ["merg", "mege", "mereg", "marge", "mergge"],
    "rebase": ["reabse", "rebse", "rebas", "rebasee"],
    "clone": ["clon", "cloen", "clonee", "clne"],
    "deploy": ["depoly", "deply", "deplyo", "dploy"],
    "restart": ["restrat", "restatr", "resatrt", "retsart"],
    "upgrade": ["upgarde", "upgrad", "upgreade", "upgrae"],
}

# Service names for systemctl/service commands
SERVICES = [
    "nginx", "apache2", "httpd", "postgresql", "mysql", "mariadb",
    "redis", "mongodb", "elasticsearch", "rabbitmq",
    "docker", "containerd", "kubernetes",
    "sshd", "fail2ban", "ufw", "firewalld",
    "cron", "crond", "atd",
    "NetworkManager", "systemd-resolved", "avahi-daemon",
]

# Error message formatting variants (for slight output variation)
BASH_SHELLS = ["bash", "zsh", "fish", "sh"]

REPO_NAMES = load_wordlist("repo-names")

GITHUB_USERS = load_wordlist("github-users")

# Generic script/file names used in runtime errors
SCRIPT_NAMES = [
    "app.py", "server.py", "main.py", "script.py", "run.py",
    "manage.py", "cli.py", "worker.py", "train.py", "test.py",
    "setup.py", "build.py", "deploy.py", "migrate.py", "seed.py",
    "app.js", "server.js", "index.js", "main.js", "worker.js",
    "app.ts", "server.ts", "index.ts", "main.ts",
    "main.rs", "lib.rs", "server.rs",
    "main.go", "server.go", "handler.go",
]

# Generic binary/program names for "command not found" gibberish negatives
GIBBERISH_CMDS = [
    "asdfghjkl", "qwertyuiop", "zxcvbnm", "xyzzy", "qqq",
    "flibbertigibbet", "blorgzorp", "fnorble", "greeble", "slargh",
    "wumpus", "thingamajig", "doohickey", "whatchamacallit", "thingummy",
    "frobnicator", "blorpify", "quuxify", "nooble", "plonker",
    "splunge", "furtle", "snorble", "worble", "glorp",
]

# Process IDs for kill/ps errors
PROCESS_IDS = [str(i) for i in [
    1234, 2345, 3456, 4567, 5678, 6789, 7890, 8901, 9012,
    10234, 11345, 12456, 13567, 14678, 15789, 16890, 17901,
    99999, 88888, 77777, 66666, 55555,
]]

# Line numbers for syntax errors
LINE_NUMBERS = [str(i) for i in range(1, 101)]

# Commit messages
COMMIT_MESSAGES = [
    "fix bug", "add feature", "update deps", "refactor code",
    "fix typo", "add tests", "update readme", "initial commit",
    "wip", "cleanup", "hotfix", "add logging", "fix crash",
    "improve performance", "add validation", "fix lint errors",
    "add docs", "bump version", "fix tests", "merge conflicts",
]

# File extensions for generic file references
FILE_EXTENSIONS = [
    ".py", ".js", ".ts", ".rs", ".go", ".rb", ".java", ".cpp",
    ".yaml", ".yml", ".json", ".toml", ".conf", ".cfg", ".ini",
    ".txt", ".log", ".csv", ".md", ".sh", ".bash",
]

# Generic directory names (short, single-segment) for cd/mkdir errors
GENERIC_DIRS = [
    "mydir", "newdir", "testdir", "tmpdir", "builddir", "outdir",
    "src", "lib", "bin", "dist", "build", "output", "cache",
    "uploads", "downloads", "backup", "archive", "logs", "tmp",
    "workspace", "project", "app", "service", "module",
]

# IP addresses
IP_ADDRESSES = [
    "192.168.1.1", "192.168.1.100", "192.168.0.1", "192.168.0.10",
    "10.0.0.1", "10.0.0.5", "10.0.0.10", "10.0.1.1",
    "172.16.0.1", "172.16.1.10", "127.0.0.1",
    "203.0.113.1", "198.51.100.2", "198.18.0.5",
]

SYSTEM_PACKAGES = load_wordlist("system-packages")


# ---------------------------------------------------------------------------
# Augmentation helpers
# ---------------------------------------------------------------------------

def _replace_all(text: str, old: str, new: str) -> str:
    """Replace all occurrences, case-insensitively preserving original case pattern."""
    return text.replace(old, new)


def augment_example(example: dict, rng: random.Random) -> dict:
    """Create a single augmented variation of an example.

    Performs random substitutions of identifiable patterns in the command,
    stderr, and correction fields.
    """
    cmd = example["command"]
    stderr = example["stderr"]
    correction = example["correction"]

    # ---- branch names ----
    branch_pattern = re.compile(
        r"\b(feature[-/]\w[\w-]*|fix[-/]\w[\w-]*|hotfix[-/]\w[\w-]*"
        r"|release[-/][\w.]+|refactor[-/]\w[\w-]*|chore[-/]\w[\w-]*"
        r"|ci[-/]\w[\w-]*|test[-/]\w[\w-]*|docs[-/]\w[\w-]*"
        r"|main|master|develop|staging|production|trunk|stable)\b"
    )
    if branch_pattern.search(cmd) or branch_pattern.search(stderr):
        old_branches = list(dict.fromkeys(
            branch_pattern.findall(cmd) + branch_pattern.findall(stderr)
        ))
        for old in old_branches:
            new_branch = rng.choice(BRANCHES)
            cmd = cmd.replace(old, new_branch)
            stderr = stderr.replace(old, new_branch)
            correction = correction.replace(old, new_branch)

    # ---- package names ----
    pkg_pattern = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in PACKAGES) + r")\b"
    )
    if pkg_pattern.search(cmd) or pkg_pattern.search(correction):
        matches = list(dict.fromkeys(
            pkg_pattern.findall(cmd) + pkg_pattern.findall(correction)
        ))
        for old_pkg in matches:
            new_pkg = rng.choice(PACKAGES)
            cmd = cmd.replace(old_pkg, new_pkg)
            stderr = stderr.replace(old_pkg, new_pkg)
            correction = correction.replace(old_pkg, new_pkg)

    # ---- system package names (apt/pacman/brew) ----
    sys_pkg_pattern = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in SYSTEM_PACKAGES) + r")\b"
    )
    if sys_pkg_pattern.search(cmd):
        matches = list(dict.fromkeys(sys_pkg_pattern.findall(cmd)))
        for old_pkg in matches:
            new_pkg = rng.choice(SYSTEM_PACKAGES)
            cmd = cmd.replace(old_pkg, new_pkg)
            stderr = stderr.replace(old_pkg, new_pkg)
            correction = correction.replace(old_pkg, new_pkg)

    # ---- file paths ----
    for old_path in FILE_PATHS:
        if old_path in stderr or old_path in cmd or old_path in correction:
            new_path = rng.choice(FILE_PATHS)
            cmd = cmd.replace(old_path, new_path)
            stderr = stderr.replace(old_path, new_path)
            correction = correction.replace(old_path, new_path)
            break  # replace first match only, avoid cascade confusion

    # ---- directory paths ----
    for old_dir in DIR_PATHS:
        if old_dir in stderr or old_dir in cmd or old_dir in correction:
            new_dir = rng.choice(DIR_PATHS)
            cmd = cmd.replace(old_dir, new_dir)
            stderr = stderr.replace(old_dir, new_dir)
            correction = correction.replace(old_dir, new_dir)
            break

    # ---- generic single-word dir names (cd/mkdir errors) ----
    for old_dir in GENERIC_DIRS:
        if old_dir in cmd or old_dir in stderr:
            new_dir = rng.choice(GENERIC_DIRS)
            cmd = cmd.replace(old_dir, new_dir)
            stderr = stderr.replace(old_dir, new_dir)
            correction = correction.replace(old_dir, new_dir)
            break

    # ---- script names ----
    for old_script in SCRIPT_NAMES:
        if old_script in cmd or old_script in stderr or old_script in correction:
            new_script = rng.choice(SCRIPT_NAMES)
            cmd = cmd.replace(old_script, new_script)
            stderr = stderr.replace(old_script, new_script)
            correction = correction.replace(old_script, new_script)
            break

    # ---- user@host patterns ----
    user_host_pattern = re.compile(r"(\w[\w-]*)@([\w.\-]+)")
    match = user_host_pattern.search(cmd)
    if match:
        old_user, old_host = match.group(1), match.group(2)
        new_user = rng.choice(USERNAMES)
        new_host = rng.choice(HOSTNAMES)
        cmd = cmd.replace(f"{old_user}@{old_host}", f"{new_user}@{new_host}")
        stderr = stderr.replace(f"{old_user}@{old_host}", f"{new_user}@{new_host}")
        correction = correction.replace(f"{old_user}@{old_host}", f"{new_user}@{new_host}")

    # ---- port numbers ----
    port_pattern = re.compile(r":(\d{2,5})\b")
    port_match = port_pattern.search(cmd)
    if port_match:
        old_port = port_match.group(1)
        new_port = rng.choice(PORTS)
        cmd = re.sub(r":" + re.escape(old_port) + r"\b", f":{new_port}", cmd)
        stderr = re.sub(r":" + re.escape(old_port) + r"\b", f":{new_port}", stderr)
        if correction != "?":
            try:
                old_port_int = int(old_port)
                new_port_int = int(new_port)
                correction = correction.replace(
                    str(old_port_int + 1), str(new_port_int + 1)
                )
                correction = re.sub(
                    r":" + re.escape(old_port) + r"\b", f":{new_port}", correction
                )
            except ValueError:
                correction = re.sub(
                    r":" + re.escape(old_port) + r"\b", f":{new_port}", correction
                )

    # ---- standalone port numbers (e.g. "fuser -k 3000/tcp") ----
    bare_port_pattern = re.compile(r"\b(3000|5000|8080|8000|4000|3001)\b")
    bp_match = bare_port_pattern.search(cmd)
    if bp_match and ":" not in cmd:
        old_port = bp_match.group(1)
        new_port = rng.choice(PORTS)
        cmd = re.sub(r"\b" + re.escape(old_port) + r"\b", new_port, cmd)
        stderr = re.sub(r"\b" + re.escape(old_port) + r"\b", new_port, stderr)
        if correction != "?":
            correction = re.sub(r"\b" + re.escape(old_port) + r"\b", new_port, correction)

    # ---- SSH key file names ----
    ssh_key_pattern = re.compile(r"(id_rsa|id_ed25519|id_ecdsa|id_dsa|deploy_key|github_key|work_key)")
    ssh_search = ssh_key_pattern.search(stderr) or ssh_key_pattern.search(correction)
    if ssh_search:
        old_key = ssh_search.group(1)
        new_key = rng.choice(SSH_KEY_FILES)
        stderr = stderr.replace(old_key, new_key)
        correction = correction.replace(old_key, new_key)

    # ---- service names ----
    service_pattern = re.compile(
        r"\b(" + "|".join(re.escape(s) for s in SERVICES) + r")\b"
    )
    if service_pattern.search(cmd) or service_pattern.search(correction):
        svc_matches = list(dict.fromkeys(
            service_pattern.findall(cmd) + service_pattern.findall(correction)
        ))
        for old_svc in svc_matches:
            new_svc = rng.choice(SERVICES)
            cmd = cmd.replace(old_svc, new_svc)
            stderr = stderr.replace(old_svc, new_svc)
            correction = correction.replace(old_svc, new_svc)

    # ---- docker image names ----
    docker_img_pattern = re.compile(
        r"\b(" + "|".join(re.escape(i) for i in DOCKER_IMAGES) + r")\b"
    )
    if docker_img_pattern.search(cmd) or docker_img_pattern.search(correction):
        img_matches = list(dict.fromkeys(
            docker_img_pattern.findall(cmd) + docker_img_pattern.findall(correction)
        ))
        for old_img in img_matches:
            new_img = rng.choice(DOCKER_IMAGES)
            cmd = cmd.replace(old_img, new_img)
            stderr = stderr.replace(old_img, new_img)
            correction = correction.replace(old_img, new_img)

    # ---- git tag versions ----
    tag_pattern = re.compile(r"\bv(\d+)\.(\d+)\.(\d+)\b")
    if tag_pattern.search(cmd) or tag_pattern.search(stderr):
        major = rng.randint(0, 5)
        minor = rng.randint(0, 20)
        patch = rng.randint(0, 10)
        new_tag = f"v{major}.{minor}.{patch}"
        cmd = tag_pattern.sub(new_tag, cmd)
        stderr = tag_pattern.sub(new_tag, stderr)
        correction = tag_pattern.sub(new_tag, correction)

    # ---- github user/repo in URLs ----
    gh_url_pattern = re.compile(r"github\.com[:/]([\w-]+)/([\w.-]+)")
    if gh_url_pattern.search(cmd) or gh_url_pattern.search(stderr):
        new_gh_user = rng.choice(GITHUB_USERS)
        new_repo = rng.choice(REPO_NAMES)
        def replace_gh(text):
            return gh_url_pattern.sub(
                lambda m: m.group(0)
                    .replace(m.group(1), new_gh_user)
                    .replace(m.group(2), new_repo + ".git"),
                text
            )
        cmd = replace_gh(cmd)
        stderr = replace_gh(stderr)
        correction = replace_gh(correction)

    # ---- shell name in error messages (bash: → zsh:) ----
    shell_prefix = re.compile(r"^(bash|zsh|sh|fish): ", re.MULTILINE)
    if shell_prefix.search(stderr) and rng.random() < 0.5:
        new_shell = rng.choice(BASH_SHELLS)
        stderr = shell_prefix.sub(f"{new_shell}: ", stderr)

    # ---- vary commit hash snippets ----
    hash_pattern = re.compile(r"\b([0-9a-f]{7,40})\b")
    if hash_pattern.search(stderr) or hash_pattern.search(correction):
        new_hash = format(rng.randint(0, 0xFFFFFFFF), '07x')
        stderr = hash_pattern.sub(new_hash, stderr)
        correction = hash_pattern.sub(new_hash, correction)

    # ---- process IDs in kill / ps errors ----
    pid_pattern = re.compile(r"\b(99999|88888|77777|66666|55555|\d{4,6})\b")
    if "kill" in cmd and pid_pattern.search(cmd):
        old_pid = pid_pattern.search(cmd).group(1)
        new_pid = rng.choice(PROCESS_IDS)
        cmd = cmd.replace(old_pid, new_pid)
        stderr = stderr.replace(old_pid, new_pid)

    # ---- IP addresses ----
    ip_pattern = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
    if ip_pattern.search(cmd) or ip_pattern.search(stderr):
        old_ip = (ip_pattern.search(cmd) or ip_pattern.search(stderr)).group(1)
        new_ip = rng.choice(IP_ADDRESSES)
        cmd = cmd.replace(old_ip, new_ip)
        stderr = stderr.replace(old_ip, new_ip)
        correction = correction.replace(old_ip, new_ip)

    # ---- line numbers in error messages ----
    lineno_pattern = re.compile(r"\bline (\d+)\b")
    if lineno_pattern.search(stderr):
        new_lineno = rng.choice(LINE_NUMBERS)
        stderr = lineno_pattern.sub(f"line {new_lineno}", stderr)

    # ---- commit message text in git commit commands ----
    commit_msg_pattern = re.compile(r"git commit -m '([^']+)'")
    if commit_msg_pattern.search(cmd):
        new_msg = rng.choice(COMMIT_MESSAGES)
        cmd = commit_msg_pattern.sub(f"git commit -m '{new_msg}'", cmd)
        correction = commit_msg_pattern.sub(f"git commit -m '{new_msg}'", correction)

    # ---- "command not found" gibberish — replace the unknown command token ----
    cnf_pattern = re.compile(r"^(\S+): command not found", re.MULTILINE)
    if cnf_pattern.search(stderr) and correction == "?":
        old_token = cnf_pattern.search(stderr).group(1)
        # Only replace if it's clearly gibberish (not a real tool name we care about)
        known_typos = {
            "gti", "sl", "pytohn", "ndoe", "dcoker", "kubeclt",
            "teh", "grpe", "maek", "carog", "dc",
        }
        if old_token in GIBBERISH_CMDS or old_token not in known_typos:
            new_token = rng.choice(GIBBERISH_CMDS)
            # Replace in cmd too if it matches
            if cmd.startswith(old_token):
                cmd = cmd.replace(old_token, new_token, 1)
            stderr = stderr.replace(old_token, new_token)

    # ---- trailing slash variation on dir-style args ----
    if rng.random() < 0.25:
        # Randomly add trailing slash to bare dir names in commands
        cmd = re.sub(r"\b(src|dist|build|lib|bin|tmp)\b(?!/)",
                     lambda m: m.group(0) + "/" if rng.random() < 0.5 else m.group(0),
                     cmd)

    return {
        "command": cmd,
        "stderr": stderr,
        "correction": correction,
    }


def augment_dataset(
    examples: list[dict],
    n_variations: int,
    seed: int,
    target_count: int | None = None,
) -> list[dict]:
    """Augment a dataset by generating variations of each example.

    Args:
        examples: Base examples to augment.
        n_variations: Number of variations to generate per example (used when
                      target_count is None).
        seed: Random seed for reproducibility.
        target_count: If set, keep generating until we have at least this many
                      unique examples (after dedup).

    Returns:
        List of all examples (originals + augmented), deduplicated.
    """
    rng = random.Random(seed)

    # Shuffle all wordlist-backed pools for this run
    for pool in [PACKAGES, DOCKER_IMAGES, K8S_RESOURCES, REPO_NAMES,
                 GITHUB_USERS, SYSTEM_PACKAGES]:
        rng.shuffle(pool)

    # Always include originals
    seen: set[str] = set()
    unique: list[dict] = []

    def add(ex: dict) -> bool:
        key = json.dumps(ex, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(ex)
            return True
        return False

    for ex in examples:
        add(ex)

    if target_count is not None:
        # Keep cycling through examples and augmenting until we hit the target.
        # Stall detection: if we go a full pass without adding anything new, give up.
        stall_passes = 0
        max_stall_passes = 10
        while len(unique) < target_count and stall_passes < max_stall_passes:
            added_this_pass = 0
            rng.shuffle(examples)
            for ex in examples:
                if len(unique) >= target_count:
                    break
                varied = augment_example(ex, rng)
                if add(varied):
                    added_this_pass += 1
            if added_this_pass == 0:
                stall_passes += 1
            else:
                stall_passes = 0
        if len(unique) < target_count:
            print(f"  (stalled at {len(unique):,} after {max_stall_passes} empty passes)")
        return unique
    else:
        # Fixed n_variations per example
        for example in examples:
            for _ in range(n_variations):
                varied = augment_example(example, rng)
                add(varied)
        return unique


def main():
    parser = argparse.ArgumentParser(
        description="Augment base training examples with template variations"
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("data/base_examples.jsonl"),
        help="Input JSONL file from generate_data.py (default: data/base_examples.jsonl)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/augmented.jsonl"),
        help="Output augmented JSONL file (default: data/augmented.jsonl)",
    )
    parser.add_argument(
        "-n",
        "--n-variations",
        type=int,
        default=100,
        help="Number of variations per example (default: 100)",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=None,
        help="Keep augmenting until this many unique examples exist (overrides -n)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: input file {args.input} not found")
        print("Run generate_data.py first to create base examples.")
        raise SystemExit(1)

    # Read base examples
    examples = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    print(f"Read {len(examples)} base examples from {args.input}")

    if args.target_count:
        print(f"Targeting {args.target_count:,} unique examples…")
    else:
        print(f"Generating {args.n_variations} variations per example…")

    # Augment (dedup is now done inside augment_dataset)
    unique = augment_dataset(
        examples,
        n_variations=args.n_variations,
        seed=args.seed,
        target_count=args.target_count,
    )

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for ex in unique:
            f.write(json.dumps(ex) + "\n")

    n_positive = sum(1 for ex in unique if ex["correction"] != "?")
    n_negative = sum(1 for ex in unique if ex["correction"] == "?")

    print(f"Generated {len(unique):,} unique examples")
    print(f"  Positive: {n_positive:,}")
    print(f"  Negative: {n_negative:,}")
    print(f"  Negative ratio: {n_negative / len(unique):.1%}")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
