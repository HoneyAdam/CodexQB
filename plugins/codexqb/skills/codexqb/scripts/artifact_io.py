#!/usr/bin/env python3
"""Descriptor-bound, no-follow artifact I/O for CodexQB local helpers."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
import secrets
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from safety_contracts import (  # noqa: E402
    assert_safe_serialized_artifact,
    parse_safe_persistent_json,
    serialize_safe_persistent_json,
)


Revalidator = Callable[[], bool]


def secure_directory_open_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure_artifact_io_not_supported")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def valid_entry_name(name: str) -> bool:
    return bool(name and name not in {".", ".."} and "/" not in name and "\\" not in name and "\x00" not in name)


def open_child_directory(parent_fd: int, name: str) -> tuple[int, os.stat_result]:
    if not valid_entry_name(name):
        raise ValueError("invalid_artifact_directory_name")
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("artifact_directory_must_be_real_directory")
    child_fd = os.open(name, secure_directory_open_flags(), dir_fd=parent_fd)
    try:
        after = os.fstat(child_fd)
    except Exception:
        os.close(child_fd)
        raise
    if not same_file_identity(before, after):
        os.close(child_fd)
        raise ValueError("artifact_directory_identity_changed")
    return child_fd, after


def open_or_create_child_directory(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    mode: int = 0o700,
) -> tuple[int, os.stat_result, bool]:
    created = False
    if create:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
    child_fd, metadata = open_child_directory(parent_fd, name)
    return child_fd, metadata, created


def directory_entry_matches(parent_fd: int, name: str, metadata: os.stat_result) -> bool:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(current.st_mode) and same_file_identity(current, metadata)


def _lstat_optional(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def regular_target_metadata_at(directory_fd: int, name: str) -> os.stat_result | None:
    if not valid_entry_name(name):
        raise ValueError("invalid_artifact_name")
    metadata = _lstat_optional(directory_fd, name)
    if metadata is not None and not stat.S_ISREG(metadata.st_mode):
        raise ValueError("artifact_target_must_be_regular_file")
    return metadata


def _revalidate(revalidate: Revalidator | None) -> None:
    if revalidate is not None and not revalidate():
        raise ValueError("artifact_directory_identity_changed")


def _write_all(file_fd: int, encoded: bytes) -> None:
    offset = 0
    while offset < len(encoded):
        written = os.write(file_fd, encoded[offset:])
        if written <= 0:
            raise OSError("short artifact write")
        offset += written


def atomic_write_bytes_at(
    directory_fd: int,
    name: str,
    encoded: bytes,
    *,
    revalidate: Revalidator | None = None,
    mode: int = 0o600,
) -> None:
    if not isinstance(encoded, bytes):
        raise TypeError("encoded artifact content must be bytes")
    _revalidate(revalidate)
    initial = regular_target_metadata_at(directory_fd, name)
    assert_safe_serialized_artifact(name, encoded)
    temporary = ""
    temporary_fd = -1
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        for _ in range(32):
            candidate = f".codexqb-artifact-{secrets.token_hex(16)}"
            try:
                temporary_fd = os.open(candidate, flags, mode, dir_fd=directory_fd)
                temporary = candidate
                break
            except FileExistsError:
                continue
        if temporary_fd < 0:
            raise FileExistsError("could not allocate exclusive artifact temporary file")
        try:
            _write_all(temporary_fd, encoded)
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
            temporary_fd = -1

        _revalidate(revalidate)
        current = regular_target_metadata_at(directory_fd, name)
        if initial is None:
            if current is not None:
                raise ValueError("artifact_target_appeared_during_write")
        elif current is None or not same_file_identity(initial, current):
            raise ValueError("artifact_target_changed_during_write")
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = ""
        os.fsync(directory_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except OSError:
                pass


def atomic_write_text_at(
    directory_fd: int,
    name: str,
    text: str,
    *,
    revalidate: Revalidator | None = None,
) -> None:
    atomic_write_bytes_at(directory_fd, name, text.encode("utf-8"), revalidate=revalidate)


def atomic_write_json_at(
    directory_fd: int,
    name: str,
    payload: object,
    *,
    revalidate: Revalidator | None = None,
) -> None:
    atomic_write_text_at(
        directory_fd,
        name,
        serialize_safe_persistent_json(payload),
        revalidate=revalidate,
    )


def read_regular_unvalidated_bytes_at(
    directory_fd: int,
    name: str,
    *,
    max_bytes: int = 16 * 1024 * 1024,
) -> bytes:
    """Read stable regular-file bytes for a caller that will validate the full stream."""

    before = regular_target_metadata_at(directory_fd, name)
    if before is None:
        raise FileNotFoundError(name)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode) or not same_file_identity(before, opened):
            raise ValueError("artifact_file_identity_changed")
        if opened.st_size > max_bytes:
            raise ValueError("artifact_file_too_large")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        encoded = b"".join(chunks)
        if len(encoded) > max_bytes:
            raise ValueError("artifact_file_too_large")
    finally:
        os.close(file_fd)
    after = regular_target_metadata_at(directory_fd, name)
    if after is None or not same_file_identity(before, after):
        raise ValueError("artifact_file_identity_changed")
    return encoded


def read_regular_bytes_at(directory_fd: int, name: str, *, max_bytes: int = 16 * 1024 * 1024) -> bytes:
    encoded = read_regular_unvalidated_bytes_at(directory_fd, name, max_bytes=max_bytes)
    return assert_safe_serialized_artifact(name, encoded)


def read_regular_text_at(directory_fd: int, name: str, *, max_bytes: int = 16 * 1024 * 1024) -> str:
    return read_regular_bytes_at(directory_fd, name, max_bytes=max_bytes).decode("utf-8")


def read_regular_json_at(directory_fd: int, name: str, *, max_bytes: int = 16 * 1024 * 1024) -> dict[str, object]:
    value = parse_safe_persistent_json(read_regular_text_at(directory_fd, name, max_bytes=max_bytes))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {name}")
    return value


def unlink_regular_at(
    directory_fd: int,
    name: str,
    *,
    missing_ok: bool = False,
    revalidate: Revalidator | None = None,
) -> None:
    _revalidate(revalidate)
    metadata = regular_target_metadata_at(directory_fd, name)
    if metadata is None:
        if missing_ok:
            return
        raise FileNotFoundError(name)
    current = regular_target_metadata_at(directory_fd, name)
    if current is None or not same_file_identity(metadata, current):
        raise ValueError("artifact_target_changed_during_unlink")
    _revalidate(revalidate)
    os.unlink(name, dir_fd=directory_fd)
    os.fsync(directory_fd)


@contextmanager
def locked_directory(directory_fd: int) -> Iterator[None]:
    fcntl.flock(directory_fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(directory_fd, fcntl.LOCK_UN)
