
# Appended to the selected upstream Containerfile; retain the full compiler/kernel path.
FROM full AS toolbox
RUN set -eu; apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bash sudo passwd procps iproute2; rm -rf /var/lib/apt/lists/*; if getent passwd hipfire >/dev/null; then userdel hipfire; fi; if getent group hipfire >/dev/null; then groupdel hipfire; fi
COPY --from=builder /hipfire/LICENSE /hipfire/LICENSE-APACHE /hipfire/LICENSE-MIT /hipfire/NOTICE /usr/share/doc/hipfire/
ARG HIPFIRE_REVISION
RUN mkdir -p /opt/hipfire/share/toolbox /tmp/hipfire && chmod 1777 /tmp/hipfire && printf '%s\n' "$HIPFIRE_REVISION" > /opt/hipfire/share/toolbox/source-revision && hipfire --version && hipfire --help
ENV HIPFIRE_HOME=/tmp/hipfire HIPFIRE_HOST=127.0.0.1
ENTRYPOINT []
WORKDIR /home
CMD ["/bin/bash"]
