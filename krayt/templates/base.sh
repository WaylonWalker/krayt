mkdir -p /etc/krayt
cat <<'KRAYT_INIT_SH_EOF' >/etc/krayt/init.sh
{%- if pre_init_hooks %}
{% for hook in pre_init_hooks %}{{ hook }}{% endfor %}
{% endif -%}
{%- if pre_init_scripts %}
{% for script in pre_init_scripts %}{{ script }}{% endfor %}
{% endif -%}
{% include 'install.sh' %}
{% include 'motd.sh' %}
{% include 'kraytrc.sh' %}
{%- if post_init_scripts %}
{% for script in post_init_scripts %}{{ script }}{% endfor %}
{% endif %}
{%- if post_init_hooks %}
{% for hook in post_init_hooks %}{{ hook }}{% endfor %}
{% endif %}
echo "Krayt environment ready. Sleeping forever..."
trap "echo 'Received SIGTERM. Exiting...'; exit 0" TERM
tail -f /dev/null &
wait
KRAYT_INIT_SH_EOF

chmod +x /etc/krayt/init.sh
/etc/krayt/init.sh
