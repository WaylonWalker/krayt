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
            "brew",
            "cargo",
            "pipx",
            "npm",
            "go",
            "gh",
        ],
        BeforeValidator(validate_kind),
    ] = "system"
    dependencies: Optional[List[str]] = None
    value: str

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
        else:
            if self.kind == "system":
                return self
            dependencies = []
            if self.kind in ["uv", "i", "installer", "curlbash", "curlsh", "gh"]:
                dependencies.extend(
                    [
                        Package.from_raw("curl"),
                    ]
                )
            if self.kind == "brew":
                dependencies.extend(
                    [
                        Package.from_raw("brew"),
                        Package.from_raw("git"),
                    ]
                )
            if self.kind == "cargo":
                dependencies.extend(
                    [
                        Package.from_raw("cargo"),
                    ]
                )
            if self.kind == "pipx":
                dependencies.extend(
                    [
                        Package.from_raw("pipx"),
                    ]
                )
            if self.kind == "npm":
                dependencies.extend(
                    [
                        Package.from_raw("npm"),
                    ]
                )
            if self.kind == "go":
                dependencies.extend(
                    [
                        Package.from_raw("go"),
                    ]
                )
            self.dependencies = dependencies
            return self

    def __str__(self):
        return f"{self.kind}:{self.value}" if self.kind != "system" else self.value

    def is_system(self) -> bool:
        return self.kind == "system"

    def install_command(self) -> str:
        """
        Generate the bash install command snippet for this package.
        """
        if self.kind == "system":
            return f"detect_package_manager_and_install {self.value}"
        elif self.kind == "uv":
            return f"uv tool install {self.value}"
        elif self.kind in ["i", "installer", "gh"]:
            return f"curl -fsSL https://i.jpillora.com/{self.value} | sh"
        elif self.kind == "curlsh":
            return f"curl -fsSL {self.value} | sh"
        elif self.kind == "curlbash":
            return f"curl -fsSL {self.value} | bash"
        elif self.kind == "brew":
            return f"brew install {self.value}"
        elif self.kind == "cargo":
            return f"cargo install {self.value}"
        elif self.kind == "pipx":
            return f"pipx install {self.value}"
        elif self.kind == "npm":
            return f"npm install -g {self.value}"
        elif self.kind == "go":
            return f"go install {self.value}@latest"
        else:
            raise ValueError(f"Unknown install method for kind={self.kind}")


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
    print("\n".join(install for install in unique_everseen([*dependencies, *installs])))
