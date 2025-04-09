cat <<EOF >/etc/motd
┌───────────────────────────────────┐
│Krayt Dragon's Lair                │
│A safe haven for volume inspection │
└───────────────────────────────────┘

"Inside every volume lies a pearl of wisdom waiting to be discovered."
{%- if volumes %}

Mounted Volumes:
{%- for volume in volumes %}
- {{ volume }}
{%- endfor %}
{%- endif %}

{%- if pvcs %}

Persistent Volume Claims:
{%- for pvc in pvcs %}
- {{ pvc }}
{%- endfor %}
{%- endif %}

{%- if secrets %}

Mounted Secrets:
{%- for secret in secrets %}
- {{ secret }}
{%- endfor %}
{%- endif %}

{%- if additional_packages %}

Additional Packages:
{%- for package in additional_packages %}
- {{ package }}
{%- endfor %}
{%- endif %}

EOF
