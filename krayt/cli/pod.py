import iterfzf
from krayt.templates import env
from kubernetes import client, config
import logging
import os
import time
import typer
from typing import Any, List, Optional
import yaml
from krayt.__about__ import __version__


logging.basicConfig(level=logging.WARNING)

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

    return clean_dict(
        {
            "name": vm.name,
            "mountPath": vm.mount_path,
            "readOnly": vm.read_only if vm.read_only else None,
        }
    )


def format_volume(v: client.V1Volume) -> dict[str, Any]:
    """Format volume into a dictionary, return None if it should be skipped"""
    # Skip Kubernetes service account volumes
    if v.name.startswith("kube-api-access-"):
        return None

    volume_source = None
    if v.persistent_volume_claim:
        volume_source = {
            "persistentVolumeClaim": {"claimName": v.persistent_volume_claim.claim_name}
        }
    elif v.config_map:
        volume_source = {"configMap": {"name": v.config_map.name}}
    elif v.secret:
        volume_source = {"secret": {"secretName": v.secret.secret_name}}
    elif v.host_path:  # Add support for hostPath volumes (used for device mounts)
        volume_source = {
            "hostPath": {
                "path": v.host_path.path,
                "type": v.host_path.type if v.host_path.type else None,
            }
        }
    elif v.empty_dir:  # Add support for emptyDir volumes (used for /dev/shm)
        volume_source = {
            "emptyDir": {
                "medium": v.empty_dir.medium if v.empty_dir.medium else None,
                "sizeLimit": v.empty_dir.size_limit if v.empty_dir.size_limit else None,
            }
        }

    if not volume_source:
        return None

    return clean_dict({"name": v.name, **volume_source})


def fuzzy_select(items):
    """Use fzf to select from a list of (name, namespace) tuples"""
    if not items:
        return None, None

    # If there's only one item, return it without prompting
    if len(items) == 1:
        return items[0]

    # Format items for display
    formatted_items = [f"{name} ({namespace})" for name, namespace in items]

    # Use fzf for selection
    try:
        # selected = inquirer.fuzzy(
        #     message="Select a pod to clone:", choices=formatted_items
        # ).execute()

        selected = iterfzf.iterfzf(
            formatted_items,
            prompt="Select a pod to clone:",
            # preview='''kubectl describe pod "$(echo {} | awk -F'[(|)]' '{gsub(/\x1b\[[0-9;]*m/, "", $1); print $1}' | xargs)" -n "$(echo {} | awk -F'[(|)]' '{gsub(/\x1b\[[0-9;]*m/, "", $2); print $2}' | xargs)"''',
        )
        if not selected:
            return None, None

        # Parse selection back into name and namespace
        # Example: "pod-name (namespace)" -> ("pod-name", "namespace")
        name = selected.split(" (")[0]
        namespace = selected.split(" (")[1][:-1]
        return name, namespace

    except Exception as e:
        typer.echo(f"Error during selection: {e}")
        return None, None


def get_pods(
    namespace=None,
    label_selector: str = "app=krayt",
):
    """Get list of pods in the specified namespace or all namespaces"""
    try:
        config.load_kube_config()
        api = client.CoreV1Api()
        if namespace:
            pods = api.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
            )
        else:
            pods = api.list_pod_for_all_namespaces(
                label_selector=label_selector,
            )

        # Convert to list of (name, namespace) tuples
        pod_list = []
        for pod in pods.items:
            if pod.metadata.namespace not in PROTECTED_NAMESPACES:
                pod_list.append((pod.metadata.name, pod.metadata.namespace))
        return pod_list

    except client.rest.ApiException as e:
        typer.echo(f"Error listing pods: {e}")
        raise typer.Exit(1)


def get_pod_spec(pod_name, namespace):
    config.load_kube_config()
    v1 = client.CoreV1Api()
    return v1.read_namespaced_pod(pod_name, namespace)


def get_pod_volumes_and_mounts(pod_spec):
    """Extract all volumes and mounts from a pod spec"""
    volume_mounts = []
    for container in pod_spec.spec.containers:
        if container.volume_mounts:
            volume_mounts.extend(container.volume_mounts)

    # Filter out None values from volume mounts
    volume_mounts = [vm for vm in volume_mounts if format_volume_mount(vm)]

    # Get all volumes, including device mounts
    volumes = []
    if pod_spec.spec.volumes:
        for v in pod_spec.spec.volumes:
            # Handle device mounts
            if v.name in ["cache-volume"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        empty_dir=client.V1EmptyDirVolumeSource(medium="Memory"),
                    )
                )
            elif v.name in ["coral-device"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        host_path=client.V1HostPathVolumeSource(
                            path="/dev/apex_0", type="CharDevice"
                        ),
                    )
                )
            elif v.name in ["qsv-device"]:
                volumes.append(
                    client.V1Volume(
                        name=v.name,
                        host_path=client.V1HostPathVolumeSource(
                            path="/dev/dri", type="Directory"
                        ),
                    )
                )
            else:
                volumes.append(v)

    # Filter out None values from volumes
    volumes = [v for v in volumes if format_volume(v)]

    return volume_mounts, volumes


def get_env_vars_and_secret_volumes(api, namespace: str):
    """Get environment variables and secret volumes for the inspector pod"""
    env_vars = []
    volumes = []

    # Add proxy environment variables if they exist in the host environment
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]

    for var in proxy_vars:
        if var in os.environ:
            env_vars.append({"name": var, "value": os.environ[var]})

    # Look for secret volumes in the namespace
    try:
        secrets = api.list_namespaced_secret(namespace)
        for secret in secrets.items:
            # Skip service account tokens and other system secrets
            if secret.type != "Opaque" or secret.metadata.name.startswith(
                "default-token-"
            ):
                continue

            # Mount each secret as a volume
            volume_name = f"secret-{secret.metadata.name}"
            volumes.append(
                client.V1Volume(
                    name=volume_name,
                    secret=client.V1SecretVolumeSource(
                        secret_name=secret.metadata.name
                    ),
                )
            )

    except client.exceptions.ApiException as e:
        if e.status != 404:  # Ignore if no secrets found
            logging.warning(f"Failed to list secrets in namespace {namespace}: {e}")

    return env_vars, volumes


def create_inspector_job(
    api,
    namespace: str,
    pod_name: str,
    volume_mounts: list,
    volumes: list,
    image: str = "alpine:latest",
    imagepullsecret: Optional[str] = None,
    additional_packages: Optional[List[str]] = None,
    pre_init_scripts: Optional[List[str]] = None,
    post_init_scripts: Optional[List[str]] = None,
    pre_init_hooks: Optional[List[str]] = None,
    post_init_hooks: Optional[List[str]] = None,
):
    """Create a Krayt inspector job with the given mounts"""
    timestamp = int(time.time())
    job_name = f"{pod_name}-krayt-{timestamp}"

    # Get environment variables and secret volumes from the target pod
    env_vars, secret_volumes = get_env_vars_and_secret_volumes(api, namespace)

    # Add secret volumes to our volumes list
    volumes.extend(secret_volumes)

    # Create corresponding volume mounts for secrets
    secret_mounts = []
    for vol in secret_volumes:
        secret_mounts.append(
            {
                "name": vol.name,
                "mountPath": f"/mnt/secrets/{vol.secret.secret_name}",
                "readOnly": True,
            }
        )

    # Convert volume mounts to dictionaries
    formatted_mounts = [format_volume_mount(vm) for vm in volume_mounts]
    formatted_mounts.extend(secret_mounts)

    # Format mount and PVC info for MOTD
    mount_info = []
    for vm in formatted_mounts:
        if vm:
            mount_info.append(f"{vm['name']}:{vm['mountPath']}")

    pvc_info = []
    for v in volumes:
        if hasattr(v, "persistent_volume_claim") and v.persistent_volume_claim:
            pvc_info.append(f"{v.name}:{v.persistent_volume_claim.claim_name}")

    template_name = "base.sh"
    template = env.get_template(template_name)
    pvcs = None
    pre_init_scripts = None
    post_init_scripts = None
    pre_init_hooks = None
    post_init_hooks = None
    command = template.render(
        volumes=volumes,
        pvcs=pvcs,
        additional_packages=additional_packages,
        pre_init_scripts=pre_init_scripts,
        post_init_scripts=post_init_scripts,
        pre_init_hooks=pre_init_hooks,
        post_init_hooks=post_init_hooks,
    )

    inspector_job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {"app": "krayt"},
            "annotations": {"pvcs": ",".join(pvc_info) if pvc_info else "none"},
        },
        "spec": {
            "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {"labels": {"app": "krayt"}},
                "spec": {
                    "containers": [
                        {
                            "name": "inspector",
                            "image": image,
                            "command": ["sh", "-c", command],
                            "env": env_vars,
                            "volumeMounts": formatted_mounts,
                        }
                    ],
                    "volumes": [format_volume(v) for v in volumes if format_volume(v)],
                    "imagePullSecrets": [{"name": imagepullsecret}]
                    if imagepullsecret
                    else None,
                    "restartPolicy": "Never",
                },
            },
        },
    }
    return inspector_job


PROTECTED_NAMESPACES = {
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "argo-events",
    "argo-rollouts",
    "argo-workflows",
    "argocd",
    "cert-manager",
    "ingress-nginx",
    "monitoring",
    "prometheus",
    "istio-system",
    "linkerd",
}


def setup_environment():
    """Set up the environment with proxy settings and other configurations"""
    # Load environment variables for proxies
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]

    for var in proxy_vars:
        if var in os.environ:
            # Make both upper and lower case versions available
            os.environ[var.upper()] = os.environ[var]
            os.environ[var.lower()] = os.environ[var]


def version_callback(value: bool):
    if value:
        typer.echo(f"Version: {__version__}")
        raise typer.Exit()


def get_pod(namespace: Optional[str] = None):
    config.load_kube_config()
    batch_api = client.BatchV1Api()

    try:
        if namespace:
            logging.debug(f"Listing jobs in namespace {namespace}")
            jobs = batch_api.list_namespaced_job(
                namespace=namespace, label_selector="app=krayt"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(label_selector="app=krayt")

        running_inspectors = []
        for job in jobs.items:
            # Get the pod for this job
            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(
                namespace=job.metadata.namespace,
                label_selector=f"job-name={job.metadata.name}",
            )
            for pod in pods.items:
                if pod.status.phase == "Running":
                    running_inspectors.append(
                        (pod.metadata.name, pod.metadata.namespace)
                    )

        if not running_inspectors:
            typer.echo("No running inspector pods found.")
            raise typer.Exit(1)

        if len(running_inspectors) == 1:
            pod_name, pod_namespace = running_inspectors[0]
        else:
            pod_name, pod_namespace = fuzzy_select(running_inspectors)
            if not pod_name:
                typer.echo("No inspector selected.")
                raise typer.Exit(1)

    except client.exceptions.ApiException as e:
        logging.error(f"Failed to list jobs: {e}")
        typer.echo(f"Failed to list jobs: {e}", err=True)
        raise typer.Exit(1)

    return pod_name, pod_namespace


@app.command()
def exec(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
):
    """
    Enter the Krayt dragon's lair! Connect to a running inspector pod.
    If multiple inspectors are found, you'll get to choose which one to explore.
    """

    pod_name, pod_namespace = get_pod(namespace)
    exec_command = [
        "kubectl",
        "exec",
        "-it",
        "-n",
        pod_namespace,
        pod_name,
        "--",
        "/bin/bash",
        "-l",
    ]

    os.execvp("kubectl", exec_command)


@app.command()
def port_forward(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
    port: str = typer.Option(
        "8080:8080",
        "--port",
        "-p",
        help="Port to forward to the inspector pod",
    ),
):
    """
    Enter the Krayt dragon's lair! Connect to a running inspector pod.
    If multiple inspectors are found, you'll get to choose which one to explore.
    """
    if ":" not in port:
        # if port does not contain a ":" it should be an int
        port = int(port)
        port = f"{port}:{port}"

    pod_name, pod_namespace = get_pod(namespace)
    port_forward_command = [
        "kubectl",
        "port-forward",
        "-n",
        pod_namespace,
        pod_name,
        port,
    ]

    os.execvp("kubectl", port_forward_command)


@app.command()
def clean(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will cleanup in all namespaces.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
):
    """
    Clean up after your hunt! Remove all Krayt inspector jobs.
    Use --yes/-y to skip confirmation and clean up immediately.
    """
    config.load_kube_config()
    batch_api = client.BatchV1Api()

    try:
        if namespace:
            if namespace in PROTECTED_NAMESPACES:
                typer.echo(f"Error: Cannot cleanup in protected namespace {namespace}")
                raise typer.Exit(1)
            logging.debug(f"Listing jobs in namespace {namespace}")
            jobs = batch_api.list_namespaced_job(
                namespace=namespace, label_selector="app=krayt"
            )
        else:
            logging.debug("Listing jobs in all namespaces")
            jobs = batch_api.list_job_for_all_namespaces(label_selector="app=krayt")

        # Filter out jobs in protected namespaces
        jobs.items = [
            job
            for job in jobs.items
            if job.metadata.namespace not in PROTECTED_NAMESPACES
        ]

        if not jobs.items:
            typer.echo("No Krayt inspector jobs found.")
            return

        # Show confirmation prompt
        if not yes:
            job_list = "\n".join(
                f"  {job.metadata.namespace}/{job.metadata.name}" for job in jobs.items
            )
            typer.echo(f"The following inspector jobs will be deleted:\n{job_list}")
            if not typer.confirm("Are you sure you want to continue?"):
                typer.echo("Operation cancelled.")
                return

        # Delete each job
        for job in jobs.items:
            try:
                logging.debug(
                    f"Deleting job {job.metadata.namespace}/{job.metadata.name}"
                )
                batch_api.delete_namespaced_job(
                    name=job.metadata.name,
                    namespace=job.metadata.namespace,
                    body=client.V1DeleteOptions(propagation_policy="Background"),
                )
                typer.echo(f"Deleted job: {job.metadata.namespace}/{job.metadata.name}")
            except client.exceptions.ApiException as e:
                logging.error(
                    f"Failed to delete job {job.metadata.namespace}/{job.metadata.name}: {e}"
                )
                typer.echo(
                    f"Failed to delete job {job.metadata.namespace}/{job.metadata.name}: {e}",
                    err=True,
                )

    except client.exceptions.ApiException as e:
        logging.error(f"Failed to list jobs: {e}")
        typer.echo(f"Failed to list jobs: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def create(
    namespace: Optional[str] = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Kubernetes namespace. If not specified, will search for pods across all namespaces.",
    ),
    clone: Optional[str] = typer.Option(
        None,
        "--clone",
        "-c",
        help="Clone an existing pod",
    ),
    image: str = typer.Option(
        "alpine:latest",
        "--image",
        "-i",
        help="Container image to use for the inspector pod",
    ),
    imagepullsecret: Optional[str] = typer.Option(
        None,
        "--imagepullsecret",
        help="Name of the image pull secret to use for pulling private images",
    ),
    additional_packages: Optional[List[str]] = typer.Option(
        None,
        "--additional-packages",
        "-ap",
        help="additional packages to install in the inspector pod",
    ),
    additional_package_bundles: Optional[List[str]] = typer.Option(
        None,
        "--additional-package-bundles",
        "-ab",
        help="additional packages to install in the inspector pod",
    ),
    pre_init_scripts: Optional[List[str]] = typer.Option(
        None,
        "--pre-init-scripts",
        help="additional scripts to execute at the end of container initialization",
    ),
    post_init_scripts: Optional[List[str]] = typer.Option(
        None,
        "--post-init-scripts",
        "--init-scripts",
        help="additional scripts to execute at the start of container initialization",
    ),
    pre_init_hooks: Optional[List[str]] = typer.Option(
        None,
        "--pre-init-hooks",
        help="additional hooks to execute at the end of container initialization",
    ),
    post_init_hooks: Optional[List[str]] = typer.Option(
        None,
        "--post-init-hooks",
        help="additional hooks to execute at the start of container initialization",
    ),
):
    """
    Krack open a Krayt dragon! Create an inspector pod to explore what's inside your volumes.
    If namespace is not specified, will search for pods across all namespaces.
    The inspector will be created in the same namespace as the selected pod.
    """
    # For create, we want to list all pods, not just Krayt pods
    selected_namespace = None
    selected_pod = None

    if namespace is None and clone is not None and "/" in clone:
        selected_namespace, selected_pod = clone.split("/", 1)
    elif namespace is not None and clone is not None:
        selected_namespace = namespace
        selected_pod = clone

    pods = get_pods(namespace, label_selector=None)
    if not pods:
        typer.echo("No pods found.")
        raise typer.Exit(1)

    if selected_pod not in (p[0] for p in pods) or selected_pod is None:
        if selected_pod is not None:
            pods = [p for p in pods if selected_pod in p[0]]
        if len(pods) == 1:
            selected_pod, selected_namespace = pods[0]
        else:
            selected_pod, selected_namespace = fuzzy_select(pods)
        if not selected_pod:
            typer.echo("No pod selected.")
            raise typer.Exit(1)

    # typer.echo(f"Selected pod exists: {selected_pod in (p[0] for p in pods)}")
    # typer.echo(f"Selected pod: {selected_pod} ({selected_namespace})")

    pod_spec = get_pod_spec(selected_pod, selected_namespace)
    volume_mounts, volumes = get_pod_volumes_and_mounts(pod_spec)

    inspector_job = create_inspector_job(
        client.CoreV1Api(),
        selected_namespace,
        selected_pod,
        volume_mounts,
        volumes,
        image=image,
        imagepullsecret=imagepullsecret,
        additional_packages=additional_packages,
        pre_init_scripts=pre_init_scripts,
        post_init_scripts=post_init_scripts,
        pre_init_hooks=pre_init_hooks,
        post_init_hooks=post_init_hooks,
    )

    # Output the job manifest
    typer.echo(yaml.dump(clean_dict(inspector_job), sort_keys=False))


@app.command()
def version():
    """Show the version of Krayt."""
    typer.echo(f"Version: {__version__}")


@app.command()
def logs(
    namespace: Optional[str] = typer.Option(
        None,
        help="Kubernetes namespace. If not specified, will search for inspectors across all namespaces.",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow the logs in real-time",
    ),
):
    """
    View logs from a Krayt inspector pod.
    If multiple inspectors are found, you'll get to choose which one to explore.
    """
    pods = get_pods(namespace)
    if not pods:
        typer.echo("No pods found.")
        raise typer.Exit(1)

    selected_pod, selected_namespace = fuzzy_select(pods)
    if not selected_pod:
        typer.echo("No pod selected.")
        raise typer.Exit(1)

    try:
        config.load_kube_config()
        api = client.CoreV1Api()
        logs = api.read_namespaced_pod_log(
            name=selected_pod,
            namespace=selected_namespace,
            follow=follow,
            _preload_content=False,
        )

        if follow:
            for line in logs:
                typer.echo(line.decode("utf-8").strip())
        else:
            typer.echo(logs.read().decode("utf-8"))

    except client.rest.ApiException as e:
        typer.echo(f"Error reading logs: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_pods():
    pods = get_pods()
    if not pods:
        typer.echo("No pods found.")
        raise typer.Exit(1)

    for pod, namespace in pods:
        typer.echo(f"{pod} ({namespace})")


def main():
    setup_environment()
    app()


if __name__ == "__main__":
    main()
