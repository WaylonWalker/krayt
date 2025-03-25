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

# Test proxy configuration
echo "Testing proxy configuration..."
if curl -s -m 5 https://www.google.com > /dev/null; then
    echo "Proxy configuration successful!"
else
    echo "Warning: Proxy test failed. Check your proxy settings."
fi
