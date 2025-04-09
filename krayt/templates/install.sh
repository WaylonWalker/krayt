{% if additional_packages %}
detect_package_manager_and_install_command() {
	if [ $# -eq 0 ]; then
		echo "Usage: detect_package_manager_and_install_command <package1> [package2] [...]"
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

	PACKAGES="$*"

	if [ -n "$UPDATE_CMD" ]; then
		echo "$UPDATE_CMD
        echo $INSTALL_CMD $PACKAGES"
		$UPDATE_CMD
		$INSTALL_CMD $PACKAGES

	else
		echo "$INSTALL_CMD $PACKAGES"
		$INSTALL_CMD $PACKAGES
	fi
}

detect_package_manager_and_install_command {% for package in additional_packages %}{{ package | trim }}{% if not loop.last %} {% endif %}{% endfor %}
{% endif %}
