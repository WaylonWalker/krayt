from more_itertools import unique_everseen
from pydantic import BaseModel, BeforeValidator, model_validator
from typing import Annotated, List, Literal, Optional
from typing_extensions import Self


SUPPORTED_KINDS = {
    "system",
    "uv",
    "installer",
    "i",
    "curlbash",
    "curlsh",
    "brew",
    "cargo",
    "pipx",
    "npm",
    "go",
    "gh",
}


def validate_kind(v):
    if v not in SUPPORTED_KINDS:
        raise ValueError(
            f"Unknown installer kind: {v}\n    Supported kinds: {SUPPORTED_KINDS}\n   "
        )
    return v


class Package(BaseModel):
    """
    Represents a package to be installed, either via system package manager
    or an alternative installer like uv, installer.sh, brew, etc.
    """

    kind: Annotated[
        Literal[
            "system",
            "uv",
            "i",
            "curlsh",
            "curlbash",
            "brew",
            "cargo",
            "pipx",
            "npm",
            "go",
            "gh",
        ],
        BeforeValidator(validate_kind),
    ] = "system"
    value: str
    dependencies: Optional[List["Package"]] = None
    pre_install_hook: Optional[str] = None
    post_install_hook: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: str) -> "Package":
        """
        Parse a raw input string like 'uv:copier' into a Package(kind='uv', value='copier')
        """
        if ":" in raw:
            prefix, value = raw.split(":", 1)
            return cls(kind=prefix.strip(), value=value.strip())
        else:
            return cls(kind="system", value=raw.strip())

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        if self.dependencies:
            return self
        dependencies = []

        if self.kind in ["uv", "i", "installer", "curlbash", "curlsh", "gh"]:
            dependencies.append(Package.from_raw("curl"))
        if self.kind == "brew":
            dependencies.append(Package.from_raw("git"))
            dependencies.append(Package.from_raw("curl"))
            self.pre_install_hook = "NONINTERACTIVE=1"
            self.post_install_hook = """
# Setup Homebrew PATH
if [ -f /home/linuxbrew/.linuxbrew/bin/brew ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
elif [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/.linuxbrew/bin/brew shellenv)"
elif [ -f /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
else
    echo "⚠️ Brew installed but binary location unknown."
fi
"""
        if self.kind == "cargo":
            dependencies.append(Package.from_raw("cargo"))
        if self.kind == "pipx":
            dependencies.append(Package.from_raw("pipx"))
        if self.kind == "npm":
            dependencies.append(Package.from_raw("npm"))
        if self.kind == "go":
            dependencies.append(Package.from_raw("go"))

        self.dependencies = dependencies
        return self

    def is_system(self) -> bool:
        return self.kind == "system"

    def install_command(self) -> str:
        """
        Generate the bash install command snippet for this package.
        """
        cmd = ""
        if self.kind == "system":
            cmd = f"detect_package_manager_and_install {self.value}"
        elif self.kind == "uv":
            cmd = f"uv tool install {self.value}"
        elif self.kind in ["i", "installer", "gh"]:
            cmd = f"curl -fsSL https://i.jpillora.com/{self.value} | sh"
        elif self.kind == "curlsh":
            cmd = f"curl -fsSL {self.value} | sh"
        elif self.kind == "curlbash":
            cmd = f"curl -fsSL {self.value} | bash"
        elif self.kind == "brew":
            cmd = "curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | bash"
        elif self.kind == "cargo":
            cmd = f"cargo install {self.value}"
        elif self.kind == "pipx":
            cmd = f"pipx install {self.value}"
        elif self.kind == "npm":
            cmd = f"npm install -g {self.value}"
        elif self.kind == "go":
            cmd = f"go install {self.value}@latest"
        else:
            raise ValueError(f"Unknown install method for kind={self.kind}")

        # Add pre-install hook if necessary
        if self.pre_install_hook:
            return f"{self.pre_install_hook} {cmd}"
        else:
            return cmd


if __name__ == "__main__":
    raw_inputs = [
        "curl",
        "wget",
        "uv:copier",
        "i:sharkdp/fd",
        "curlsh:https://example.com/install.sh",
        "brew:bat",
    ]

    packages = [Package.from_raw(raw) for raw in raw_inputs]
    dependencies = []
    for package in packages:
        if package.dependencies:
            dependencies.extend(
                [dependency.install_command() for dependency in package.dependencies]
            )
    installs = [package.install_command() for package in packages]
    post_hooks = []
    for package in packages:
        if package.post_install_hook:
            post_hooks.append(package.post_install_hook.strip())

    # Final full script
    full_script = list(unique_everseen([*dependencies, *installs, *post_hooks]))
    print("\n".join(full_script))
