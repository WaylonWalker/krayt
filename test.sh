detect_package_manager_and_install_command() {
	# Accept packages as arguments
	PACKAGES=("$@")

	if [[ ${#PACKAGES[@]} -eq 0 ]]; then
		echo "Usage: detect_package_manager_and_install_command <package1> [package2] [...]"
		return 1
	fi

	if command -v apt &>/dev/null; then
		PKG_MANAGER="apt"
		UPDATE_CMD="sudo apt update"
		INSTALL_CMD="sudo apt install -y"
	elif command -v dnf &>/dev/null; then
		PKG_MANAGER="dnf"
		UPDATE_CMD=""
		INSTALL_CMD="sudo dnf install -y"
	elif command -v yum &>/dev/null; then
		PKG_MANAGER="yum"
		UPDATE_CMD=""
		INSTALL_CMD="sudo yum install -y"
	elif command -v pacman &>/dev/null; then
		PKG_MANAGER="pacman"
		UPDATE_CMD=""
		INSTALL_CMD="sudo pacman -Sy --noconfirm"
	elif command -v zypper &>/dev/null; then
		PKG_MANAGER="zypper"
		UPDATE_CMD=""
		INSTALL_CMD="sudo zypper install -y"
	elif command -v apk &>/dev/null; then
		PKG_MANAGER="apk"
		UPDATE_CMD=""
		INSTALL_CMD="sudo apk add"
	else
		echo "No supported package manager found."
		return 2
	fi

	# Build the full install command
	if [[ -n "$UPDATE_CMD" ]]; then
		# echo $UPDATE_CMD
		# $UPDATE_CMD
		echo $INSTALL_CMD ${PACKAGES[*]}
		$INSTALL_CMD ${PACKAGES[*]}
	else
		echo $INSTALL_CMD ${PACKAGES[*]}
		$INSTALL_CMD ${PACKAGES[*]}
	fi
}

detect_package_manager_and_install_command git htop
