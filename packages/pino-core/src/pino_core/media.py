"""Best-effort, immutable filesystem covers; no deployment dependencies."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import socket
import tempfile
from io import BytesIO
from time import monotonic
from urllib.parse import urljoin

import httpx
from PIL import Image, ImageOps

from pino_core.config import MediaConfig
from pino_core.models import Record, RecordImage

logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000
DOWNLOAD_SECONDS = 15


def download_image(url: str) -> bytes:
    deadline = monotonic() + DOWNLOAD_SECONDS
    with httpx.Client(trust_env=False, follow_redirects=False) as client:
        for _ in range(4):
            target = httpx.URL(url)
            if target.scheme not in {"http", "https"} or not target.host or target.userinfo:
                raise ValueError("image URL must be public HTTP(S) without credentials")
            addresses = socket.getaddrinfo(
                target.host,
                target.port or (443 if target.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global
                or ipaddress.ip_address(item[4][0]).is_multicast
                for item in addresses
            ):
                raise ValueError("image URL resolves to a non-public address")
            # Pin the validated address, preserving Host and TLS certificate verification.
            pinned = target.copy_with(host=addresses[0][4][0])
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("image download deadline exceeded")
            with client.stream(
                "GET",
                pinned,
                headers={"Host": target.netloc.decode(), "Accept-Encoding": "identity"},
                extensions={"sni_hostname": target.host},
                timeout=remaining,
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError("compressed HTTP image responses are not supported")
                if int(response.headers.get("content-length", "0")) > MAX_BYTES:
                    raise ValueError("image exceeds download size limit")
                data = bytearray()
                for chunk in response.iter_bytes(64 * 1024):
                    if monotonic() > deadline:
                        raise TimeoutError("image download deadline exceeded")
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("image exceeds download size limit")
                return bytes(data)
    raise ValueError("too many image redirects")


class MediaStore:
    def __init__(self, config: MediaConfig) -> None:
        self.directory = config.directory

    def save(self, data: bytes, *, source_url: str) -> RecordImage:
        if len(data) > MAX_BYTES:
            raise ValueError("image exceeds download size limit")
        with Image.open(BytesIO(data)) as original:
            if original.width * original.height > MAX_PIXELS:
                raise ValueError("image exceeds decoded pixel limit")
            normalized = ImageOps.exif_transpose(original).convert("RGBA")
            normalized.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            output = BytesIO()
            normalized.save(output, format="WEBP", quality=80, exif=b"", icc_profile=b"")
        content = output.getvalue()
        name = hashlib.sha256(content).hexdigest() + ".webp"
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / name
        if not destination.is_file():
            with tempfile.NamedTemporaryFile(
                dir=self.directory, suffix=".tmp", delete=False
            ) as file:
                temporary = file.name
                try:
                    file.write(content)
                    file.flush()
                    os.fchmod(file.fileno(), 0o644)
                    os.replace(temporary, destination)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        return RecordImage(path=name, source_url=source_url)

    def enrich(self, record: Record, *, payload: dict) -> Record:
        images = list(record.images)
        urls = payload.get("image_urls", [])
        urls = list(urls) if isinstance(urls, list) else []
        if payload.get("image_url"):
            urls.insert(0, payload["image_url"])
        urls.extend(image.source_url for image in images)
        for url in dict.fromkeys(url for url in urls if isinstance(url, str)):
            existing = next((image for image in images if image.source_url == url), None)
            try:
                if existing and (self.directory / existing.path).is_file():
                    continue
                image = self.save(download_image(url), source_url=url)
            except Exception as exc:
                logger.warning("Cover unavailable for record %s: %s", record.id, exc)
                continue
            if existing:
                images[images.index(existing)] = image
            else:
                images.append(image)
        order = list(dict.fromkeys(url for url in urls if isinstance(url, str)))
        images.sort(key=lambda image: order.index(image.source_url))
        return record.model_copy(update={"images": images})
