"""
Bundles of packages available in most package managers.
"""

basics = [
    "curl",
    "wget",
    "jq",
    "yq",
    "bash",
    "coreutils",
]
bundles = {
    "basics": [
        *basics,
    ],
    "pretty": [
        *basics,
        "starship",
        "atuin",
        "bash",
        "zsh",
        "fish",
        "bat",
        "eza",
    ],
    "networking": [
        *basics,
        "mtr",
        "bind-tools",
        "aws-cli",
        "curl",
        "wget",
        "iperf3",
        "nmap",
        "traceroute",
        "netcat-openbsd",
    ],
    "database": [
        *basics,
        "sqlite",
        "sqlite-dev",
        "sqlite-libs",
        "postgresql",
        "mysql",
        "mariadb",
        "redis",
        "mongodb",
    ],
    "storage": [
        *basics,
        "ncdu",
        "dust",
        "file",
        "hexyl",
        "ripgrep",
        "fd",
        "fzf",
        "difftastic",
    ],
    "search": [
        *basics,
        "ripgrep",
        "fd",
        "fzf",
        "difftastic",
    ],
    "monitoring": [
        *basics,
        "htop",
        "bottom",
        "mtr",
    ],
}

bundles["all"] = list(
    set(
        [
            *bundles["basics"],
            *bundles["pretty"],
            *bundles["networking"],
            *bundles["database"],
            *bundles["storage"],
            *bundles["search"],
            *bundles["monitoring"],
        ]
    )
)
