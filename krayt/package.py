from krayt.bundles import bundles
from more_itertools import unique_everseen
from pydantic import BaseModel, BeforeValidator
from typing import Annotated, List, Literal, Optional, Union


SUPPORTED_KINDS = {
    "system",
    "uv",
    "installer",
    "i",
    "curlbash",
    "curlsh",
    "cargo",
    "pipx",
    "npm",
    "go",
    "gh",
    "group",
    "bundle",
}

DEPENDENCIES = {
    "uv": [
        "curl",
        "curlsh:https://astral.sh/uv/install.sh",
    ],
    "installer": [
        "curl",
    ],
    "i": ["curl"],
    "curlbash": ["curl"],
    "curlsh": ["curl"],
    "cargo": ["cargo"],
    "pipx": ["pipx"],
    "npm": ["npm"],
    "go": ["go"],
    "gh": ["gh"],
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
    or an alternative installer like uv, installer.sh, etc.
    """

    kind: Annotated[
        Literal[*SUPPORTED_KINDS],
        BeforeValidator(validate_kind),
    ] = "system"
    value: str
    # dependencies: Optional[List["Package"]] = None
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

    # @model_validator(mode="after")
    # def validate_dependencies(self) -> Self:
    #     if self.dependencies:
    #         return self
    #     dependencies = []
    #
    #     if self.kind in ["uv", "i", "installer", "curlbash", "curlsh", "gh"]:
    #         dependencies.append(Package.from_raw("curl"))
    #         dependencies.append(
    #             Package.from_raw("curlsh:https://astral.sh/uv/install.sh")
    #         )
    #     if self.kind == "cargo":
    #         dependencies.append(Package.from_raw("cargo"))
    #     if self.kind == "pipx":
    #         dependencies.append(Package.from_raw("pipx"))
    #     if self.kind == "npm":
    #         dependencies.append(Package.from_raw("npm"))
    #     if self.kind == "go":
    #         dependencies.append(Package.from_raw("go"))
    #
    #     self.dependencies = dependencies
    #     return self
    #
    def is_system(self) -> bool:
        return self.kind == "system"

    def install_command(self) -> str:
        """
        Generate the bash install command snippet for this package.
        """
        cmd = ""
        if self.kind in ["bundle", "group"]:
            cmd = ""
        elif self.kind == "system":
            cmd = f"detect_package_manager_and_install {self.value}"
        elif self.kind == "uv":
            cmd = f"uv tool install {self.value}"
        elif self.kind in ["i", "installer", "gh"]:
            cmd = f"installer {self.value}"
        elif self.kind == "curlsh":
            cmd = f"curl -fsSL {self.value} | sh"
        elif self.kind == "curlbash":
            cmd = f"curl -fsSL {self.value} | bash"
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


def get_install_script(packages: Union[str, List[str]]) -> str:
    if packages is None:
        return []
    if isinstance(packages, str):
        packages = [packages]
    bundled_packages = []
    for package in packages:
        if package.startswith("bundle:") or package.startswith("group:"):
            _package = package.split(":")[1].strip()
            bundled_packages.extend(bundles.get(_package, []))
    packages = list(unique_everseen([*bundled_packages, *packages]))

    packages = [Package.from_raw(raw) for raw in packages]
    kinds_used = [package.kind for package in packages]
    dependencies = []
    for kind in kinds_used:
        dependencies.extend(DEPENDENCIES.get(kind, []))
    dependencies = list(
        unique_everseen(
            [Package.from_raw(raw).install_command() for raw in dependencies]
        )
    )
    # for package in packages:
    #     if package.dependencies:
    #         dependencies.extend(
    #             [dependency.install_command() for dependency in package.dependencies]
    #         )
    installs = [package.install_command() for package in packages]
    post_hooks = []
    for package in packages:
        if package.post_install_hook:
            post_hooks.append(package.post_install_hook.strip())
    pre_hooks = []
    for package in packages:
        if package.pre_install_hook:
            pre_hooks.append(package.pre_install_hook.strip())

    # Final full script
    full_script = list(
        unique_everseen([*pre_hooks, *dependencies, *installs, *post_hooks])
    )
    return "\n".join(full_script) if full_script else full_script


if __name__ == "__main__":
    raw_inputs = [
        "bundle:storage",
        "wget",
        "uv:copier",
        "i:sharkdp/fd",
        "curlsh:https://example.com/install.sh",
    ]
    full_script = get_install_script(raw_inputs)

    print("\n".join(full_script))
