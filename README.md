# Krayt - The Kubernetes Volume Inspector

![krayt hero image](./krayt.webp "A dark, cartoon-style wide-format illustration featuring a heroic explorer standing in a twilight desert beside a cracked-open dragon skull. The explorer holds a glowing pearl that reveals floating icons representing data and technology. The hero wears utility gear and a sword, with terminal and file icons on their belt. The desert backdrop includes jagged rocks, two moons in a starry sky, and moody blue and purple tones. At the top, the word “KRAYT” is displayed in bold, tech-inspired fantasy lettering.")

Like cracking open a Krayt dragon pearl, this tool helps you inspect what's inside your Kubernetes volumes.
Hunt down storage issues and explore your persistent data like a true Tatooine dragon hunter.

## Features

- 🔍 Create inspector pods with all the tools you need
- 📦 Access volumes and device mounts from any pod
- 🔎 Fuzzy search across all namespaces
- 🛠️ Built-in tools for file exploration and analysis
- 🧹 Automatic cleanup of inspector pods

## Installation

### Quick Install (Linux)

```bash
# Install latest version
curl -sSL https://github.com/waylonwalker/krayt/releases/latest/download/install.sh | sudo bash

# Install specific version
curl -sSL https://github.com/waylonwalker/krayt/releases/download/v0.1.0/install.sh | sudo bash
```

This will install the `krayt` command to `/usr/local/bin`.

### Manual Installation

1. Download the latest release for your platform from the [releases page](https://github.com/waylonwalker/krayt/releases)
2. Extract the archive: `tar xzf krayt-*.tar.gz`
3. Move the binary: `sudo mv krayt-*/krayt /usr/local/bin/krayt`
4. Make it executable: `sudo chmod +x /usr/local/bin/krayt`

## Usage

```bash
# Create a new inspector and apply it directly
krayt create | kubectl apply -f -

# Use a custom image
krayt create --image custom-image:latest | kubectl apply -f -

# Use a private image with pull secret
krayt create --image private-registry.com/image:latest --imagepullsecret my-registry-secret | kubectl apply -f -

# Or review the manifest first
krayt create > inspector.yaml
kubectl apply -f inspector.yaml

# Connect to a running inspector
krayt exec

# Clean up inspectors
krayt clean

# Show version
krayt version
```

### Available Tools

Your inspector pod comes equipped with a full arsenal of tools:

- **File Navigation**: `lf`, `exa`, `fd`
- **Search & Analysis**: `ripgrep`, `bat`, `hexyl`
- **Disk Usage**: `ncdu`, `dust`
- **File Comparison**: `difftastic`
- **System Monitoring**: `bottom`, `htop`
- **JSON/YAML Tools**: `jq`, `yq`
- **Network Tools**: `mtr`, `dig`
- **Cloud & Database**: `aws-cli`, `sqlite3`

## Customization

### Init Scripts

Krayt supports initialization scripts that run in the inspector pod before any packages are installed. These scripts are useful for:
- Setting up proxy configurations
- Installing additional tools
- Configuring custom package repositories
- Setting environment variables

Place your scripts in `~/.config/krayt/init.d/` with a `.sh` extension. Scripts are executed in alphabetical order, so you can control the execution sequence using numerical prefixes.

Example init scripts:

1. Install additional tools (`~/.config/krayt/init.d/10_install_git.sh`):
```bash
#!/bin/sh
echo "Installing additional tools..."

# Install git for source control
apk add git

# Configure git
git config --global init.defaultBranch main
git config --global core.editor vi
```

2. Set up custom repositories (`~/.config/krayt/init.d/20_custom_repos.sh`):
```bash
#!/bin/sh
echo "Adding custom package repositories..."

# Add testing repository for newer packages
echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories

# Update package list
apk update
```

### Proxy Configuration

If your environment requires a proxy, you have two options:

1. **Environment Variables** (Recommended):
   ```bash
   # Add to your shell's rc file (e.g., ~/.bashrc, ~/.zshrc)
   export HTTP_PROXY="http://proxy.example.com:8080"
   export HTTPS_PROXY="http://proxy.example.com:8080"
   export NO_PROXY="localhost,127.0.0.1,.internal.example.com"
   ```

2. **Init Script** (`~/.config/krayt/init.d/00_proxy.sh`):
   ```bash
   #!/bin/sh
   echo "Configuring proxy settings..."

   # Set proxy for Alpine package manager
   mkdir -p /etc/apk
   cat > /etc/apk/repositories << EOF
   http://dl-cdn.alpinelinux.org/alpine/latest-stable/main
   http://dl-cdn.alpinelinux.org/alpine/latest-stable/community

   # Configure proxy
   proxy=http://proxy.example.com:8080
   EOF

   # Set proxy for other tools
   export HTTP_PROXY="http://proxy.example.com:8080"
   export HTTPS_PROXY="http://proxy.example.com:8080"
   export NO_PROXY="localhost,127.0.0.1,.internal.example.com"
   ```

The proxy configuration will be applied before any packages are installed, ensuring that all package installations and network operations work correctly through your proxy.

## Quotes from the Field

> "Inside every volume lies a pearl of wisdom waiting to be discovered."
> 
> -- Ancient Tatooine proverb

> "The path to understanding your storage is through exploration."
> 
> -- Krayt dragon hunter's manual

## May the Force be with your volumes!

Remember: A Krayt dragon's pearl is valuable not just for what it is, but for what it reveals about the dragon that created it. Similarly, your volumes tell a story about your application's data journey.
