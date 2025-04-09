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

{%- if pvcs %}
export KRAYT_PVCS="{{ pvcs | join(' ') }}"
{% endif -%}
{%- if volumes %}
export KRAYT_VOLUMES="{{ volumes | join(' ') }}"
{% endif -%}
{%- if secrets %}
export KRAYT_SECRETS="{{ secrets | join(' ') }}"
{% endif -%}
{%- if additional_packages %}
export KRAYT_ADDITIONAL_PACKAGES="{{ additional_packages | join(' ') }}"
{% endif -%}

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
