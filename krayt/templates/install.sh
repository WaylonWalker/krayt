{% if additional_packages %}
# Detect package manager
if command -v apt >/dev/null 2>&1; then
	PKG_MANAGER="apt"
	UPDATE_CMD="apt update"
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
	exit 2
fi

echo "Using package manager: $PKG_MANAGER"

# Run update once if needed
if [ -n "$UPDATE_CMD" ]; then
	echo "Running package manager update..."
	eval "$UPDATE_CMD"
fi

detect_package_manager_and_install() {
	if [ $# -eq 0 ]; then
		echo "Usage: detect_package_manager_and_install <package1> [package2] [...]"
		return 1
	fi

	FAILED_PKGS=""

	for pkg in "$@"; do
		echo "Installing package: $pkg"
		if ! $INSTALL_CMD $pkg; then
			echo "⚠️ Warning: Failed to install package: $pkg"
			FAILED_PKGS="$FAILED_PKGS $pkg"
		fi
	done
	{% raw %}
	if [ -n "$FAILED_PKGS" ]; then
		echo "⚠️ The following packages failed to install:"
		for failed_pkg in $FAILED_PKGS; do
			echo "  - $failed_pkg"
		done
	else
		echo "✅ All requested packages installed successfully."
	fi
	{% endraw %}
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
{% endif %}

{% if additional_packages %}
{{ get_install_script(additional_packages) | safe }}
{% endif %}

