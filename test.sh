mkdir -p /etc/krayt
cat <<'KRAYT_INIT_SH_EOF' >/etc/krayt/init.sh
detect_package_manager_and_install() {
	if [ $# -eq 0 ]; then
		echo "Usage: detect_package_manager_and_install <package1> [package2] [...]"
		return 1
	fi

	if command -v apt >/dev/null 2>&1; then
		PKG_MANAGER="apt"
		UPDATE_CMD="apt update &&"
		INSTALL_CMD="apt install -y"
	elif command -v dnf >/dev/null 2>&1; then
		PKG_MANAGER="dnf"
		UPDATE_CMD=""
		INSTALL_CMD="dnf install -y"
	elif command -v yum >/dev/null 2>&1; then
		PKG_MANAGER="yum"
		UPDATE_CMD=""
		INSTALL_CMD="yum install -y"
	elif command -v pacman >/dev/null 2>&1; then
		PKG_MANAGER="pacman"
		UPDATE_CMD=""
		INSTALL_CMD="pacman -Sy --noconfirm"
	elif command -v zypper >/dev/null 2>&1; then
		PKG_MANAGER="zypper"
		UPDATE_CMD=""
		INSTALL_CMD="zypper install -y"
	elif command -v apk >/dev/null 2>&1; then
		PKG_MANAGER="apk"
		UPDATE_CMD=""
		INSTALL_CMD="apk add"
	else
		echo "No supported package manager found."
		return 2
	fi

	echo "Using package manager: $PKG_MANAGER"

	if [ -n "$UPDATE_CMD" ]; then
		echo "Running package manager update..."
		eval "$UPDATE_CMD"
	fi

	FAILED_PKGS=""

	for pkg in "$@"; do
		echo "Installing package: $pkg"
		if ! eval "$INSTALL_CMD $pkg"; then
			echo "⚠️ Warning: Failed to install package: $pkg"
			FAILED_PKGS="$FAILED_PKGS $pkg"
		fi
	done
	
	if [ -n "$FAILED_PKGS" ]; then
		echo "⚠️ The following packages failed to install:"
		for failed_pkg in $FAILED_PKGS; do
			echo "  - $failed_pkg"
		done
	else
		echo "✅ All requested packages installed successfully."
	fi
	
}

installer() {
	if [ $# -eq 0 ]; then
		echo "Usage: installer <package1> [package2] [...]"
		return 1
	fi

	for pkg in "$@"; do
		echo "Installing package with installer: $pkg"
		(
		orig_dir="$(pwd)"
		cd /usr/local/bin || exit 1
		curl -fsSL https://i.jpillora.com/${pkg} | sh
		cd "$orig_dir" || exit 1
		)
	done
}



detect_package_manager_and_install eza
detect_package_manager_and_install hexyl
detect_package_manager_and_install mariadb
detect_package_manager_and_install coreutils
detect_package_manager_and_install ncdu
detect_package_manager_and_install postgresql
detect_package_manager_and_install atuin
detect_package_manager_and_install redis
detect_package_manager_and_install file
detect_package_manager_and_install netcat-openbsd
detect_package_manager_and_install traceroute
detect_package_manager_and_install fd
detect_package_manager_and_install iperf3
detect_package_manager_and_install aws-cli
detect_package_manager_and_install dust
detect_package_manager_and_install sqlite-dev
detect_package_manager_and_install fish
detect_package_manager_and_install bat
detect_package_manager_and_install ripgrep
detect_package_manager_and_install difftastic
detect_package_manager_and_install zsh
detect_package_manager_and_install sqlite-libs
detect_package_manager_and_install bind-tools
detect_package_manager_and_install nmap
detect_package_manager_and_install mysql
detect_package_manager_and_install htop
detect_package_manager_and_install sqlite
detect_package_manager_and_install fzf
detect_package_manager_and_install bottom
detect_package_manager_and_install wget
detect_package_manager_and_install mtr
detect_package_manager_and_install bash
detect_package_manager_and_install curl
detect_package_manager_and_install starship
detect_package_manager_and_install mongodb
detect_package_manager_and_install jq
detect_package_manager_and_install yq



cat <<EOF >/etc/motd
┌───────────────────────────────────┐
│Krayt Dragon's Lair                │
│A safe haven for volume inspection │
└───────────────────────────────────┘

"Inside every volume lies a pearl of wisdom waiting to be discovered."

Additional Packages:
- bundle:all

EOF
KRAYT_MARKER_START="# >>> Added by krayt-inject <<<"
KRAYT_MARKER_END='# <<< End krayt-inject >>>'
KRAYT_BLOCK='
if [ -t 1 ] && [ -f /etc/motd ] && [ -z "$MOTD_SHOWN" ]; then
    cat /etc/motd
    export MOTD_SHOWN=1
fi

# fix $SHELL, not set in some distros like alpine
if [ -n "$BASH_VERSION" ]; then
    export SHELL=/bin/bash
elif [ -n "$ZSH_VERSION" ]; then
    export SHELL=/bin/zsh
else
    export SHELL=/bin/sh
fi

# krayt ENVIRONMENT
export KRAYT_ADDITIONAL_PACKAGES="bundle:all"
# Universal shell initializers

# Prompt
if command -v starship >/dev/null 2>&1; then
	eval "$(starship init "$(basename "$SHELL")")"
fi

# Smarter cd
if command -v zoxide >/dev/null 2>&1; then
	eval "$(zoxide init "$(basename "$SHELL")")"
fi

# Smarter shell history
if command -v atuin >/dev/null 2>&1; then
	eval "$(atuin init "$(basename "$SHELL")")"
fi

if command -v mcfly >/dev/null 2>&1; then
	eval "$(mcfly init "$(basename "$SHELL")")"
fi

# Directory-based environment
if command -v direnv >/dev/null 2>&1; then
	eval "$(direnv hook "$(basename "$SHELL")")"
fi

if command -v fzf >/dev/null 2>&1; then
    case "$(basename "$SHELL")" in
        bash|zsh|fish)
            eval "$(fzf --$(basename "$SHELL"))"
            ;;
        *)
            # shell not supported for fzf init
            ;;
    esac
fi
# "Did you mean...?" for mistyped commands
if command -v thefuck >/dev/null 2>&1; then
	eval "$(thefuck --alias)"
fi
'
cat <<EOF >/etc/.kraytrc
$KRAYT_MARKER_START
$KRAYT_BLOCK
$KRAYT_MARKER_END
EOF

KRAYT_RC_SOURCE='
if [ -f /etc/.kraytrc ]; then
    . /etc/.kraytrc
fi
'

# List of common rc/profile files to patch
RC_FILES="
/etc/profile
/etc/bash.bashrc
/etc/bash/bashrc
/etc/bashrc
/etc/ashrc
/etc/zsh/zshrc
/etc/zsh/zprofile
/etc/shinit
/etc/fish/config.fish
"

echo "Searching for rc files..."

for rc_file in $RC_FILES; do
	if [ -f "$rc_file" ]; then
		echo "* Found $rc_file"

		# Check if already patched
		if grep -q "$KRAYT_MARKER_START" "$rc_file"; then
			echo "- $rc_file already has krayt block. Skipping."
		else
			echo "+ Patching $rc_file"
			echo "" >>"$rc_file"
			echo "$KRAYT_MARKER_START" >>"$rc_file"
			echo "$KRAYT_RC_SOURCE" >>"$rc_file"
			echo "$KRAYT_MARKER_END" >>"$rc_file"
		fi
	fi
done
echo "Krayt environment ready. Sleeping forever..."
trap "echo 'Received SIGTERM. Exiting...'; exit 0" TERM
tail -f /dev/null &
wait
KRAYT_INIT_SH_EOF

chmod +x /etc/krayt/init.sh
/etc/krayt/init.sh
