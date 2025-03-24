#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "kubernetes",
# ]
# ///

from kubernetes import client, config
import subprocess
import typer
import yaml
import time
from typing import Any

app = typer.Typer()


def clean_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Remove None values and empty dicts from a dictionary recursively."""
    if not isinstance(d, dict):
        return d
    return {
        k: clean_dict(v)
        for k, v in d.items()
        if v is not None and v != {} and not (isinstance(v, dict) and not clean_dict(v))
    }


def format_volume_mount(vm: client.V1VolumeMount) -> dict[str, Any]:
    """Format volume mount with only relevant fields."""
    # Skip Kubernetes service account mounts
    if vm.mount_path.startswith("/var/run/secrets/kubernetes.io/"):
        return None
        
    return clean_dict({
        "name": vm.name,
        "mountPath": vm.mount_path,
        "readOnly": vm.read_only if vm.read_only else None,
    })


def format_volume(v: client.V1Volume) -> dict[str, Any]:
    """Format volume with only relevant fields."""
    # Skip Kubernetes service account volumes
    if v.name.startswith("kube-api-access-"):
        return None
        
    volume_source = None
    if v.persistent_volume_claim:
        volume_source = {
            "persistentVolumeClaim": {
                "claimName": v.persistent_volume_claim.claim_name,
                "readOnly": v.persistent_volume_claim.read_only,
            }
        }
    elif v.config_map:
        volume_source = {"configMap": {"name": v.config_map.name}}
    elif v.secret:
        volume_source = {"secret": {"secretName": v.secret.secret_name}}
    
    if not volume_source:
        return None
    
    return clean_dict({"name": v.name, **volume_source})


def fuzzy_select(options: list[str]) -> str:
    fzf = subprocess.Popen(
        ["fzf"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    input_str = "\n".join(options)
    selection, _ = fzf.communicate(input=input_str)
    return selection.strip()


def get_pods(namespace: str) -> list[str]:
    v1 = client.CoreV1Api()
    return [pod.metadata.name for pod in v1.list_namespaced_pod(namespace).items]


def get_pod_spec(pod_name: str, namespace: str):
    v1 = client.CoreV1Api()
    return v1.read_namespaced_pod(pod_name, namespace)


@app.command()
def create_inspector(
    namespace: str = typer.Option("default", help="Kubernetes namespace"),
):
    config.load_kube_config()

    pods = get_pods(namespace)
    if not pods:
        typer.echo("No pods found in the namespace.")
        raise typer.Exit(1)

    selected_pod = fuzzy_select(pods)
    pod_spec = get_pod_spec(selected_pod, namespace)

    volume_mounts = []
    volumes = []

    for container in pod_spec.spec.containers:
        volume_mounts.extend(container.volume_mounts)

    # Filter out None values from volume mounts and volumes
    volume_mounts = [vm for vm in volume_mounts if format_volume_mount(vm)]
    volumes = [v for v in pod_spec.spec.volumes if format_volume(v)]

    # Create a unique name using timestamp
    timestamp = int(time.time())
    job_name = f"{selected_pod}-inspector-{timestamp}"

    # Format mount and PVC information for environment variables
    mount_info = []
    pvc_info = []
    
    for vm in volume_mounts:
        mount_info.append(f"{vm.name}:{vm.mount_path}")
    
    for v in volumes:
        if v.persistent_volume_claim:
            pvc_info.append(f"{v.name}:{v.persistent_volume_claim.claim_name}")

    inspector_job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
        },
        "spec": {
            "ttlSecondsAfterFinished": 0,  # Delete immediately after completion
            "template": {
                "metadata": {
                    "labels": {
                        "app": "pvc-inspector"
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "inspector",
                            "image": "alpine:latest",  # Use Alpine as base for package management
                            "command": [
                                "sh", 
                                "-c", 
                                """
# Install basic tools first
apk update
apk add curl

# Install lf (terminal file manager)
curl -L https://github.com/gokcehan/lf/releases/download/r31/lf-linux-amd64.tar.gz | tar xzf - -C /usr/local/bin

# Install the rest of the tools
apk add ripgrep exa ncdu dust \
    file hexyl jq yq bat fd fzf \
    htop bottom difftastic \
    mtr bind-tools

# Function to update MOTD
update_motd() {
    cat << EOF > /etc/motd
====================================
PVC Inspector Pod
====================================
Mounted Volumes:
$(echo "$MOUNTS" | tr ',' '\\n' | sed 's/^/- /')

Persistent Volume Claims:
$(echo "$PVCS" | tr ',' '\\n' | sed 's/^/- /')

Available Tools:
File Navigation:
- lf: Terminal file manager (run 'lf')
- exa: Modern ls (run 'ls', 'll', or 'tree')
- fd: Modern find (run 'fd pattern')

Search & Analysis:
- rg (ripgrep): Fast search (run 'rg pattern')
- bat: Better cat with syntax highlighting
- hexyl: Hex viewer (run 'hexyl file')
- file: File type detection

Disk Usage:
- ncdu: Interactive disk usage analyzer
- dust: Disk usage analyzer
- du: Standard disk usage tool

File Comparison:
- difft: Modern diff tool (alias 'diff')

System Monitoring:
- btm: Modern system monitor (alias 'top')
- htop: Interactive process viewer

JSON/YAML Tools:
- jq: JSON processor
- yq: YAML processor

Network Tools:
- dig: DNS lookup
- mtr: Network diagnostics

Type 'tools-help' for detailed usage information
====================================
EOF
}

# Create helpful aliases and functions
cat << 'EOF' > /root/.ashrc
if [ "$PS1" ]; then
    cat /etc/motd
fi

# Aliases for better file navigation
alias ls='exa'
alias ll='exa -l'
alias la='exa -la'
alias tree='exa --tree'
alias find='fd'
alias top='btm'
alias diff='difft'
alias cat='bat --paging=never'

# Function to show detailed tool help
tools-help() {
    echo "PVC Inspector Tools Guide:"
    echo
    echo "File Navigation:"
    echo "  lf                   : Navigate with arrow keys, q to quit, h for help"
    echo "  ls, ll, la          : List files (exa with different options)"
    echo "  tree                : Show directory structure"
    echo "  fd pattern          : Find files matching pattern"
    echo
    echo "Search & Analysis:"
    echo "  rg pattern          : Search file contents"
    echo "  bat file            : View file with syntax highlighting"
    echo "  hexyl file          : View file in hex format"
    echo "  file path           : Determine file type"
    echo
    echo "Disk Usage:"
    echo "  ncdu                : Interactive disk usage analyzer (navigate with arrows)"
    echo "  dust path           : Tree-based disk usage"
    echo "  du -sh *            : Summarize disk usage"
    echo
    echo "File Comparison:"
    echo "  diff file1 file2    : Compare files with syntax highlighting"
    echo
    echo "System Monitoring:"
    echo "  top (btm)           : Modern system monitor"
    echo "  htop                : Process viewer"
    echo
    echo "JSON/YAML Tools:"
    echo "  jq . file.json      : Format and query JSON"
    echo "  yq . file.yaml      : Format and query YAML"
    echo
    echo "Network Tools:"
    echo "  dig domain          : DNS lookup"
    echo "  mtr host            : Network diagnostics"
}

# Set some helpful environment variables
export EDITOR=vi
export PAGER=less
EOF

# Set up environment to always source our RC file
echo "export ENV=/root/.ashrc" > /etc/profile
echo "export ENV=/root/.ashrc" > /etc/environment

# Make RC file available to all shells
cp /root/.ashrc /etc/profile.d/motd.sh
ln -sf /root/.ashrc /root/.profile
ln -sf /root/.ashrc /root/.bashrc
ln -sf /root/.ashrc /root/.mkshrc
ln -sf /root/.ashrc /etc/shinit

# Create initial MOTD
update_motd

sleep 3600
                                """
                            ],
                            "env": [
                                {
                                    "name": "MOUNTS",
                                    "value": ",".join(mount_info)
                                },
                                {
                                    "name": "PVCS",
                                    "value": ",".join(pvc_info)
                                },
                                {
                                    "name": "ENV",
                                    "value": "/root/.ashrc"
                                }
                            ],
                            "volumeMounts": [format_volume_mount(vm) for vm in volume_mounts],
                        }
                    ],
                    "volumes": [format_volume(v) for v in volumes if format_volume(v)],
                    "restartPolicy": "Never"
                }
            }
        }
    }

    # Apply the job spec
    typer.echo(yaml.dump(clean_dict(inspector_job), sort_keys=False))


if __name__ == "__main__":
    app()
