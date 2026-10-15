# Build explicitly; run only by scripts/office_preview_runner.py with a reviewed digest.
# Security updates require bumping this exact package version and re-running document fixtures.
FROM debian:trixie-slim
ARG LIBREOFFICE_VERSION=4:25.2.3-2+deb13u8
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer=${LIBREOFFICE_VERSION} \
    libreoffice-calc=${LIBREOFFICE_VERSION} \
    libreoffice-impress=${LIBREOFFICE_VERSION} \
    python3 fonts-noto-cjk fonts-dejavu-core \
    && dpkg-query -W > /usr/share/admincore-packages.txt \
    && rm -rf /var/lib/apt/lists/*
COPY convert.py /opt/admincore/convert.py
USER 65532:65532
ENV HOME=/tmp
ENTRYPOINT ["/usr/bin/python3", "/opt/admincore/convert.py"]
