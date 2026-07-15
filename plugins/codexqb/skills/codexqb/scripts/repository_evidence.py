#!/usr/bin/env python3
"""Descriptor-bound repository evidence primitives for CodexQB.

This module never invokes Git.  Explicit snapshots accept a caller-supplied
path set, while full-worktree inventory uses descriptor-relative discovery.
Every existing target is opened relative to the repository descriptor with
no-follow semantics before its content contributes to an evidence digest.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
try:
    import fcntl
except ImportError:  # pragma: no cover - guarded by the POSIX-only capability check
    fcntl = None  # type: ignore[assignment]
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any


REPOSITORY_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_MAX_FILE_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_PATHS = 100_000
DEFAULT_SNAPSHOT_TIMEOUT_SECONDS = 60.0

_SHA256_RE = re.compile(r"[a-f0-9]{64}")
_WINDOWS_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SNAPSHOT_STATES = frozenset({"missing", "present"})
_CHANGE_STATES = frozenset({"add", "modify", "delete", "unchanged"})
_GIT_OBJECT_FORMATS = frozenset({"sha1", "sha256"})


@dataclass(frozen=True)
class RepositoryRootAnchor:
    """One opened repository directory identity shared by an evidence capture."""

    path: Path
    fd: int
    metadata: os.stat_result
    mount_identity: tuple[object, ...]


@dataclass(frozen=True)
class AnchoredFilePayload:
    """Stable regular-file bytes opened through one repository root anchor."""

    path: str
    data: bytes
    mode: int


@dataclass
class _SnapshotBudget:
    remaining_bytes: int
    remaining_path_reads: int
    deadline: float

    def check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            raise ValueError("repository_evidence_deadline_exceeded")

    def consume_path(self) -> None:
        self.check_deadline()
        if self.remaining_path_reads <= 0:
            raise ValueError("repository_evidence_path_read_budget_exceeded")
        self.remaining_path_reads -= 1

    def consume_bytes(self, amount: int) -> None:
        self.check_deadline()
        if amount < 0 or amount > self.remaining_bytes:
            raise ValueError("repository_evidence_total_bytes_exceeded")
        self.remaining_bytes -= amount


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _secure_directory_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure_repository_evidence_not_supported")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _secure_file_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure_repository_evidence_not_supported")
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


def _secure_symlink_metadata_flags() -> int:
    if sys.platform.startswith("linux") and hasattr(os, "O_PATH") and hasattr(os, "O_NOFOLLOW"):
        return os.O_PATH | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    if sys.platform == "darwin" and hasattr(os, "O_SYMLINK"):
        return os.O_RDONLY | os.O_SYMLINK | getattr(os, "O_CLOEXEC", 0)
    raise ValueError("secure_repository_mount_identity_unavailable")


def _linux_mount_id(fd: int) -> int:
    try:
        with open(f"/proc/self/fdinfo/{fd}", "rb") as handle:
            payload = handle.read(65537)
    except OSError as exc:
        raise ValueError("secure_repository_mount_identity_unavailable") from exc
    if len(payload) > 65536:
        raise ValueError("secure_repository_mount_identity_unavailable")
    for line in payload.splitlines():
        if line.startswith(b"mnt_id:\t"):
            raw = line.removeprefix(b"mnt_id:\t")
            if raw.isdigit():
                return int(raw)
    raise ValueError("secure_repository_mount_identity_unavailable")


class _DarwinFsid(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int32 * 2)]


class _DarwinStatfs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", _DarwinFsid),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16),
        ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


def _darwin_mount_identity(fd: int) -> tuple[object, ...]:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fstatfs = libc.fstatfs
        fstatfs.argtypes = [ctypes.c_int, ctypes.POINTER(_DarwinStatfs)]
        fstatfs.restype = ctypes.c_int
        payload = _DarwinStatfs()
        if fstatfs(fd, ctypes.byref(payload)) != 0:
            raise OSError(ctypes.get_errno(), "fstatfs failed")
    except (AttributeError, OSError) as exc:
        raise ValueError("secure_repository_mount_identity_unavailable") from exc
    mount_on = bytes(payload.f_mntonname).split(b"\0", 1)[0]
    mount_from = bytes(payload.f_mntfromname).split(b"\0", 1)[0]
    filesystem_type = bytes(payload.f_fstypename).split(b"\0", 1)[0]
    if not mount_on or not mount_from or not filesystem_type:
        raise ValueError("secure_repository_mount_identity_unavailable")
    return (
        "darwin_fstatfs",
        int(payload.f_fsid.value[0]),
        int(payload.f_fsid.value[1]),
        int(payload.f_type),
        filesystem_type,
        mount_on,
        mount_from,
    )


def _descriptor_mount_identity(fd: int) -> tuple[object, ...]:
    if sys.platform.startswith("linux"):
        return ("linux_mnt_id", _linux_mount_id(fd))
    if sys.platform == "darwin":
        return _darwin_mount_identity(fd)
    raise ValueError("secure_repository_mount_identity_unavailable")


def _promote_root_fd(root_fd: int) -> int:
    """Keep the root anchor away from stdio descriptors used by subprocesses."""

    if root_fd >= 3:
        return root_fd
    duplicate_command = getattr(fcntl, "F_DUPFD_CLOEXEC", None) if fcntl is not None else None
    if duplicate_command is None:
        os.close(root_fd)
        raise ValueError("secure_repository_evidence_not_supported")
    try:
        promoted = int(fcntl.fcntl(root_fd, duplicate_command, 3))
    except OSError:
        os.close(root_fd)
        raise
    os.close(root_fd)
    if promoted < 3:
        os.close(promoted)
        raise ValueError("secure_repository_evidence_not_supported")
    return promoted


def _owner_controlled_regular(metadata: os.stat_result) -> bool:
    expected_uid = os.geteuid() if hasattr(os, "geteuid") else metadata.st_uid
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_nlink == 1
        and metadata.st_uid == expected_uid
        and metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
    )


def _stable_file_metadata(metadata: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_positive_limit(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TypeError("max_bytes_must_be_positive_integer")
    return value


def _require_positive_timeout(value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value <= 0
        or not math.isfinite(value)
    ):
        raise TypeError("timeout_seconds_must_be_positive_number")
    return float(value)


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"{label}_must_be_nonempty_string")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label}_must_be_sha256")
    return value


def normalize_repo_relative_path(value: object) -> str:
    """Return one unambiguous POSIX-style repository-relative path.

    Absolute paths, empty/dot components, traversal, NULs, leading/trailing
    whitespace, and Windows drive paths are rejected rather than reinterpreted.
    Backslashes are normalized only after the drive-path check.
    """

    if not isinstance(value, str):
        raise TypeError("repository_path_must_be_string")
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError("invalid_repository_relative_path")
    if _WINDOWS_DRIVE_RE.match(value) or value.startswith(("/", "\\")):
        raise ValueError("invalid_repository_relative_path")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid_repository_relative_path")
    return "/".join(parts)


def _normalize_allowed_paths(
    paths: object,
    *,
    max_items: int = DEFAULT_MAX_PATHS,
) -> list[str]:
    if isinstance(paths, (str, bytes, bytearray, Mapping)) or not isinstance(paths, Iterable):
        raise TypeError("allowed_paths_must_be_iterable")
    normalized: set[str] = set()
    for position, path in enumerate(paths, start=1):
        if position > max_items:
            raise ValueError("repository_evidence_path_count_exceeded")
        normalized.add(normalize_repo_relative_path(path))
    return sorted(normalized)


def _root_path(value: object) -> Path:
    if isinstance(value, bool) or not isinstance(value, (str, os.PathLike)):
        raise TypeError("repository_root_must_be_path")
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise TypeError("repository_root_must_be_path")
    return Path(os.path.abspath(raw))


def _open_root(root: object) -> tuple[Path, int, os.stat_result, tuple[object, ...]]:
    path = _root_path(root)
    try:
        before = os.stat(path, follow_symlinks=False)
        root_fd = os.open(path, _secure_directory_flags())
        root_fd = _promote_root_fd(root_fd)
    except OSError as exc:
        raise ValueError("repository_root_must_be_real_directory") from exc
    try:
        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(before.st_mode) or not stat.S_ISDIR(opened.st_mode) or not _same_identity(before, opened):
            raise ValueError("repository_root_must_be_real_directory")
        return path, root_fd, opened, _descriptor_mount_identity(root_fd)
    except Exception:
        os.close(root_fd)
        raise


@contextmanager
def open_repository_root_anchor(root: object) -> Iterator[RepositoryRootAnchor]:
    """Open one no-follow root descriptor for a complete evidence operation."""

    path, root_fd, metadata, mount_identity = _open_root(root)
    anchor = RepositoryRootAnchor(
        path=path,
        fd=root_fd,
        metadata=metadata,
        mount_identity=mount_identity,
    )
    try:
        yield anchor
    finally:
        os.close(root_fd)


def _revalidate_root(root_path: Path, root_fd: int, root_metadata: os.stat_result) -> None:
    try:
        current_path = os.stat(root_path, follow_symlinks=False)
        current_fd = os.fstat(root_fd)
    except OSError as exc:
        raise ValueError("repository_root_identity_changed") from exc
    if (
        not stat.S_ISDIR(current_path.st_mode)
        or not stat.S_ISDIR(current_fd.st_mode)
        or not _same_identity(root_metadata, current_path)
        or not _same_identity(root_metadata, current_fd)
    ):
        raise ValueError("repository_root_identity_changed")


def _revalidate_root_mount(
    root_path: Path,
    root_fd: int,
    root_metadata: os.stat_result,
    root_mount_identity: tuple[object, ...],
) -> None:
    _revalidate_root(root_path, root_fd, root_metadata)
    if _descriptor_mount_identity(root_fd) != root_mount_identity:
        raise ValueError("repository_root_mount_identity_changed")


def revalidate_repository_root_anchor(anchor: RepositoryRootAnchor) -> None:
    """Fail closed unless both the path and descriptor retain one identity."""

    if not isinstance(anchor, RepositoryRootAnchor):
        raise TypeError("repository_root_anchor_required")
    _revalidate_root_mount(
        anchor.path,
        anchor.fd,
        anchor.metadata,
        anchor.mount_identity,
    )


def require_same_repository_mount(
    anchor: RepositoryRootAnchor,
    child_fd: int,
    relative_path: object,
) -> None:
    """Reject nested mount points, including Linux same-device bind mounts."""

    if not isinstance(anchor, RepositoryRootAnchor):
        raise TypeError("repository_root_anchor_required")
    path = "." if relative_path == "." else normalize_repo_relative_path(relative_path)
    try:
        child_metadata = os.fstat(child_fd)
    except OSError as exc:
        raise ValueError("secure_repository_mount_identity_unavailable") from exc
    if (
        not stat.S_ISDIR(child_metadata.st_mode)
        or child_metadata.st_dev != anchor.metadata.st_dev
        or _descriptor_mount_identity(child_fd) != anchor.mount_identity
    ):
        raise ValueError(f"repository_nested_mount_rejected={path}")
    revalidate_repository_root_anchor(anchor)


def _require_descriptor_on_root_mount(
    root_mount_identity: tuple[object, ...],
    child_fd: int,
    relative_path: str,
) -> None:
    if _descriptor_mount_identity(child_fd) != root_mount_identity:
        raise ValueError(f"repository_nested_mount_rejected={relative_path}")


def _verify_symlink_mount_identity(
    parent_fd: int,
    name: str,
    metadata: os.stat_result,
    root_mount_identity: tuple[object, ...],
    relative_path: str,
) -> None:
    try:
        symlink_fd = os.open(name, _secure_symlink_metadata_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise ValueError("secure_repository_mount_identity_unavailable") from exc
    try:
        opened = os.fstat(symlink_fd)
        if not stat.S_ISLNK(opened.st_mode) or not _same_identity(metadata, opened):
            raise ValueError("repository_evidence_file_identity_changed")
        _require_descriptor_on_root_mount(
            root_mount_identity,
            symlink_fd,
            relative_path,
        )
    finally:
        os.close(symlink_fd)


DirectoryLink = tuple[int, str, int, os.stat_result]


def _revalidate_directory_chain(
    chain: Sequence[DirectoryLink],
    root_device: int,
    root_mount_identity: tuple[object, ...],
) -> None:
    for parent_fd, name, child_fd, metadata in chain:
        try:
            current_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            current_fd = os.fstat(child_fd)
        except OSError as exc:
            raise ValueError("repository_path_parent_identity_changed") from exc
        if (
            not stat.S_ISDIR(current_path.st_mode)
            or not stat.S_ISDIR(current_fd.st_mode)
            or current_path.st_dev != root_device
            or current_fd.st_dev != root_device
            or _descriptor_mount_identity(child_fd) != root_mount_identity
            or not _same_identity(metadata, current_path)
            or not _same_identity(metadata, current_fd)
        ):
            raise ValueError("repository_path_parent_identity_changed")


def _git_blob_oid(encoded: bytes, object_format: str) -> str:
    digest = hashlib.new(object_format)
    digest.update(f"blob {len(encoded)}\0".encode("ascii"))
    digest.update(encoded)
    return digest.hexdigest()


def _missing_entry(path: str, git_object_format: str | None = None) -> dict[str, object]:
    entry: dict[str, object] = {
        "path": path,
        "state": "missing",
        "sha256": None,
        "size": None,
    }
    if git_object_format is not None:
        entry.update(
            {
                "kind": "missing",
                "git_mode": None,
                "git_blob_oid": None,
            }
        )
    return entry


def _read_expected_hashes(
    file_fd: int,
    expected_size: int,
    budget: _SnapshotBudget,
    git_object_format: str | None = None,
) -> tuple[str, str | None, int]:
    content_digest = hashlib.sha256()
    git_digest = hashlib.new(git_object_format) if git_object_format is not None else None
    if git_digest is not None:
        git_digest.update(f"blob {expected_size}\0".encode("ascii"))
    remaining = expected_size
    bytes_read = 0
    while remaining > 0:
        budget.check_deadline()
        chunk = os.read(file_fd, min(65536, remaining))
        if not chunk:
            break
        budget.consume_bytes(len(chunk))
        content_digest.update(chunk)
        if git_digest is not None:
            git_digest.update(chunk)
        bytes_read += len(chunk)
        remaining -= len(chunk)
    return content_digest.hexdigest(), git_digest.hexdigest() if git_digest is not None else None, bytes_read


def _read_expected_bytes(
    file_fd: int,
    expected_size: int,
    budget: _SnapshotBudget,
) -> bytes:
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining > 0:
        budget.check_deadline()
        chunk = os.read(file_fd, min(65536, remaining))
        if not chunk:
            break
        budget.consume_bytes(len(chunk))
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _snapshot_one(
    root_path: Path,
    root_fd: int,
    root_metadata: os.stat_result,
    root_mount_identity: tuple[object, ...],
    path: str,
    max_bytes: int,
    budget: _SnapshotBudget,
    git_object_format: str | None = None,
) -> dict[str, object]:
    budget.consume_path()
    parts = path.split("/")
    current_fd = root_fd
    owned_fds: list[int] = []
    chain: list[DirectoryLink] = []
    try:
        for component in parts[:-1]:
            try:
                before = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
                try:
                    os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                except FileNotFoundError:
                    _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
                    _revalidate_root_mount(
                        root_path,
                        root_fd,
                        root_metadata,
                        root_mount_identity,
                    )
                    return _missing_entry(path, git_object_format)
                raise ValueError("repository_path_parent_identity_changed")
            except OSError as exc:
                raise ValueError("repository_path_parent_unavailable") from exc
            if not stat.S_ISDIR(before.st_mode):
                raise ValueError("repository_path_parent_must_be_real_directory")
            if before.st_dev != root_metadata.st_dev:
                raise ValueError("repository_path_parent_escape")
            try:
                child_fd = os.open(component, _secure_directory_flags(), dir_fd=current_fd)
                opened = os.fstat(child_fd)
            except OSError as exc:
                raise ValueError("repository_path_parent_identity_changed") from exc
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != root_metadata.st_dev
                or not _same_identity(before, opened)
            ):
                os.close(child_fd)
                raise ValueError("repository_path_parent_identity_changed")
            try:
                _require_descriptor_on_root_mount(
                    root_mount_identity,
                    child_fd,
                    "/".join(parts[: len(chain) + 1]),
                )
            except Exception:
                os.close(child_fd)
                raise
            chain.append((current_fd, component, child_fd, opened))
            owned_fds.append(child_fd)
            current_fd = child_fd

        name = parts[-1]
        try:
            before = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
        except FileNotFoundError:
            _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
            try:
                os.stat(name, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
                _revalidate_root_mount(
                    root_path,
                    root_fd,
                    root_metadata,
                    root_mount_identity,
                )
                return _missing_entry(path, git_object_format)
            raise ValueError("repository_evidence_file_identity_changed")
        except OSError as exc:
            raise ValueError("repository_evidence_target_unavailable") from exc

        if git_object_format is not None and stat.S_ISLNK(before.st_mode):
            expected_uid = os.geteuid() if hasattr(os, "geteuid") else before.st_uid
            if before.st_uid != expected_uid:
                raise ValueError("repository_evidence_target_must_be_owner_controlled_symlink")
            _verify_symlink_mount_identity(
                current_fd,
                name,
                before,
                root_mount_identity,
                path,
            )
            try:
                target_before = os.readlink(name, dir_fd=current_fd)
                after_path = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                target_after = os.readlink(name, dir_fd=current_fd)
            except OSError as exc:
                raise ValueError("repository_evidence_file_identity_changed") from exc
            if (
                not stat.S_ISLNK(after_path.st_mode)
                or not _same_identity(before, after_path)
                or _stable_file_metadata(before) != _stable_file_metadata(after_path)
                or target_before != target_after
            ):
                raise ValueError("repository_evidence_file_identity_changed")
            encoded_target = os.fsencode(target_before)
            if len(encoded_target) > max_bytes:
                raise ValueError("repository_evidence_file_too_large")
            budget.consume_bytes(len(encoded_target))
            _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
            _revalidate_root_mount(
                root_path,
                root_fd,
                root_metadata,
                root_mount_identity,
            )
            return {
                "path": path,
                "state": "present",
                "sha256": hashlib.sha256(encoded_target).hexdigest(),
                "size": len(encoded_target),
                "kind": "symlink",
                "git_mode": "120000",
                "git_blob_oid": _git_blob_oid(encoded_target, git_object_format),
            }

        if not _owner_controlled_regular(before):
            raise ValueError("repository_evidence_target_must_be_owner_controlled_regular_file")
        if before.st_size > max_bytes:
            raise ValueError("repository_evidence_file_too_large")
        if before.st_size > budget.remaining_bytes:
            raise ValueError("repository_evidence_total_bytes_exceeded")
        try:
            file_fd = os.open(name, _secure_file_flags(), dir_fd=current_fd)
        except OSError as exc:
            raise ValueError("repository_evidence_file_identity_changed") from exc
        try:
            opened = os.fstat(file_fd)
            if not _owner_controlled_regular(opened) or not _same_identity(before, opened):
                raise ValueError("repository_evidence_file_identity_changed")
            _require_descriptor_on_root_mount(
                root_mount_identity,
                file_fd,
                path,
            )
            content_sha256, git_blob_oid, bytes_read = _read_expected_hashes(
                file_fd,
                before.st_size,
                budget,
                git_object_format,
            )
            after_fd = os.fstat(file_fd)
        finally:
            os.close(file_fd)
        try:
            after_path = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError("repository_evidence_file_identity_changed") from exc
        if (
            not _owner_controlled_regular(after_fd)
            or not _owner_controlled_regular(after_path)
            or _stable_file_metadata(opened) != _stable_file_metadata(after_fd)
            or not _same_identity(opened, after_path)
            or after_fd.st_size != bytes_read
        ):
            raise ValueError("repository_evidence_file_identity_changed")
        _revalidate_directory_chain(chain, root_metadata.st_dev, root_mount_identity)
        _revalidate_root_mount(
            root_path,
            root_fd,
            root_metadata,
            root_mount_identity,
        )
        result: dict[str, object] = {
            "path": path,
            "state": "present",
            "sha256": content_sha256,
            "size": bytes_read,
        }
        if git_object_format is not None:
            result.update(
                {
                    "kind": "regular",
                    "git_mode": "100755" if opened.st_mode & 0o111 else "100644",
                    "git_blob_oid": git_blob_oid,
                }
            )
        return result
    finally:
        for directory_fd in reversed(owned_fds):
            os.close(directory_fd)


def _snapshot_paths_from_anchor(
    anchor: RepositoryRootAnchor,
    paths: Iterable[object],
    *,
    max_bytes: int,
    max_total_bytes: int,
    max_paths: int,
    timeout_seconds: float,
    git_object_format: str | None,
) -> list[dict[str, object]]:
    revalidate_repository_root_anchor(anchor)
    byte_limit = _require_positive_limit(max_bytes)
    total_limit = _require_positive_limit(max_total_bytes)
    path_limit = _require_positive_limit(max_paths)
    timeout_limit = _require_positive_timeout(timeout_seconds)
    normalized_paths = _normalize_allowed_paths(paths, max_items=path_limit)
    budget = _SnapshotBudget(
        remaining_bytes=total_limit,
        remaining_path_reads=len(normalized_paths) * 2,
        deadline=time.monotonic() + timeout_limit,
    )

    def capture() -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for path in normalized_paths:
            result.append(
                _snapshot_one(
                    anchor.path,
                    anchor.fd,
                    anchor.metadata,
                    anchor.mount_identity,
                    path,
                    byte_limit,
                    budget,
                    git_object_format,
                )
            )
        return result

    snapshot = capture()
    confirmation = capture()
    if snapshot != confirmation:
        raise ValueError("repository_snapshot_changed_during_capture")
    budget.check_deadline()
    revalidate_repository_root_anchor(anchor)
    return snapshot


def snapshot_allowed_paths(
    root: str | os.PathLike[str],
    allowed_paths: Iterable[object],
    *,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[dict[str, object]]:
    """Snapshot exactly the supplied repository-relative path set.

    Missing paths are represented explicitly.  Existing paths must be regular,
    single-link, owner-controlled files without group/other write permission.
    The byte and deadline limits cover both the initial and confirmation reads.
    """

    with open_repository_root_anchor(root) as anchor:
        return _snapshot_paths_from_anchor(
            anchor,
            allowed_paths,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
            max_paths=max_paths,
            timeout_seconds=timeout_seconds,
            git_object_format=None,
        )


def snapshot_git_paths(
    root: str | os.PathLike[str],
    tracked_paths: Iterable[object],
    *,
    object_format: str,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[dict[str, object]]:
    """Capture raw Git worktree blobs without invoking filters or following links.

    The returned blob OIDs are computed directly from stable descriptor-bound
    bytes.  This intentionally treats clean/smudge or line-ending conversions
    as worktree drift instead of executing repository-configured programs.
    """

    with open_repository_root_anchor(root) as anchor:
        return snapshot_git_paths_from_anchor(
            anchor,
            tracked_paths,
            object_format=object_format,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
            max_paths=max_paths,
            timeout_seconds=timeout_seconds,
        )


def snapshot_git_paths_from_anchor(
    anchor: RepositoryRootAnchor,
    tracked_paths: Iterable[object],
    *,
    object_format: str,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[dict[str, object]]:
    """Capture Git worktree blobs through an already-open root anchor."""

    if object_format not in _GIT_OBJECT_FORMATS:
        raise ValueError("unsupported_git_object_format")
    return _snapshot_paths_from_anchor(
        anchor,
        tracked_paths,
        max_bytes=max_bytes,
        max_total_bytes=max_total_bytes,
        max_paths=max_paths,
        timeout_seconds=timeout_seconds,
        git_object_format=object_format,
    )


InventoryExclusion = Callable[[str], bool]


def _inventory_path(parent: str, name: str) -> str:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ValueError("invalid_repository_inventory_path")
    path = f"{parent}/{name}" if parent else name
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("invalid_repository_inventory_path") from exc
    if os.fsencode(path) != encoded or normalize_repo_relative_path(path) != path:
        raise ValueError("invalid_repository_inventory_path")
    return path


def _inventory_fingerprint(
    kind: str,
    mode: str,
    *,
    content: bytes | None = None,
    content_sha256: str | None = None,
    rdev: int | None = None,
) -> str:
    if kind == "regular":
        if content_sha256 is None:
            raise ValueError("repository_inventory_regular_digest_missing")
        payload = f"regular\0{mode}\0{content_sha256}".encode("ascii")
    elif kind == "symlink":
        if content is None:
            raise ValueError("repository_inventory_symlink_target_missing")
        payload = b"symlink\0" + mode.encode("ascii") + b"\0" + content
    elif kind == "directory":
        payload = f"directory\0{mode}".encode("ascii")
    elif kind == "special":
        payload = f"special\0{mode}\0{rdev}".encode("ascii")
    else:  # pragma: no cover - private callers pass one closed enum
        raise ValueError("repository_inventory_kind_invalid")
    return hashlib.sha256(payload).hexdigest()


def _inventory_public_entry(
    *,
    path: str,
    kind: str,
    metadata: os.stat_result,
    content_sha256: str | None = None,
    size: int | None = None,
    fingerprint_sha256: str,
) -> dict[str, object]:
    return {
        "path": path,
        "kind": kind,
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "sha256": content_sha256,
        "size": size,
        "fingerprint_sha256": fingerprint_sha256,
    }


def _capture_repository_inventory_pass(
    anchor: RepositoryRootAnchor,
    *,
    exclude: InventoryExclusion,
    max_bytes: int,
    max_paths: int,
    budget: _SnapshotBudget,
) -> list[tuple[dict[str, object], tuple[int, int, int, int, int, int, int]]]:
    """Capture one descriptor-relative inventory pass including identity proof."""

    captured: list[tuple[dict[str, object], tuple[int, int, int, int, int, int, int]]] = []
    path_count = 0

    def walk(
        directory_fd: int,
        parent: str,
        chain: tuple[DirectoryLink, ...],
        depth: int,
    ) -> None:
        nonlocal path_count
        budget.check_deadline()
        if depth > 128:
            raise ValueError("repository_evidence_directory_depth_exceeded")
        try:
            directory_before = os.fstat(directory_fd)
            with os.scandir(directory_fd) as iterator:
                names: list[str] = []
                for entry in iterator:
                    budget.check_deadline()
                    path_count += 1
                    if path_count > max_paths:
                        raise ValueError("repository_evidence_path_count_exceeded")
                    names.append(entry.name)
            directory_after = os.fstat(directory_fd)
        except OSError as exc:
            raise ValueError("repository_inventory_walk_failed") from exc
        if (
            not stat.S_ISDIR(directory_before.st_mode)
            or directory_before.st_dev != anchor.metadata.st_dev
            or _stable_file_metadata(directory_before) != _stable_file_metadata(directory_after)
        ):
            raise ValueError("repository_inventory_changed_during_capture")

        for name in sorted(names):
            budget.check_deadline()
            path = _inventory_path(parent, name)
            if exclude(path):
                continue
            try:
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise ValueError("repository_inventory_changed_during_capture") from exc
            if before.st_dev != anchor.metadata.st_dev:
                raise ValueError("repository_path_parent_escape")
            mode = f"{stat.S_IMODE(before.st_mode):04o}"

            if stat.S_ISDIR(before.st_mode):
                try:
                    child_fd = os.open(name, _secure_directory_flags(), dir_fd=directory_fd)
                    opened = os.fstat(child_fd)
                except PermissionError as exc:
                    raise ValueError("repository_inventory_walk_failed") from exc
                except OSError as exc:
                    raise ValueError("repository_path_parent_identity_changed") from exc
                try:
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or opened.st_dev != anchor.metadata.st_dev
                        or not _same_identity(before, opened)
                    ):
                        raise ValueError("repository_path_parent_identity_changed")
                    require_same_repository_mount(anchor, child_fd, path)
                    link = (directory_fd, name, child_fd, opened)
                    public = _inventory_public_entry(
                        path=path,
                        kind="directory",
                        metadata=opened,
                        fingerprint_sha256=_inventory_fingerprint("directory", mode),
                    )
                    captured.append((public, _stable_file_metadata(opened)))
                    walk(child_fd, path, chain + (link,), depth + 1)
                    try:
                        after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                        after_fd = os.fstat(child_fd)
                    except OSError as exc:
                        raise ValueError("repository_path_parent_identity_changed") from exc
                    if (
                        _stable_file_metadata(opened) != _stable_file_metadata(after_fd)
                        or _stable_file_metadata(opened) != _stable_file_metadata(after_path)
                    ):
                        raise ValueError("repository_inventory_changed_during_capture")
                    _revalidate_directory_chain(
                        chain + (link,),
                        anchor.metadata.st_dev,
                        anchor.mount_identity,
                    )
                finally:
                    os.close(child_fd)
                continue

            if stat.S_ISLNK(before.st_mode):
                expected_uid = os.geteuid() if hasattr(os, "geteuid") else before.st_uid
                if before.st_uid != expected_uid:
                    raise ValueError("repository_evidence_target_must_be_owner_controlled_symlink")
                _verify_symlink_mount_identity(
                    directory_fd,
                    name,
                    before,
                    anchor.mount_identity,
                    path,
                )
                try:
                    target_before = os.readlink(name, dir_fd=directory_fd)
                    after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    target_after = os.readlink(name, dir_fd=directory_fd)
                except OSError as exc:
                    raise ValueError("repository_evidence_file_identity_changed") from exc
                if (
                    target_before != target_after
                    or _stable_file_metadata(before) != _stable_file_metadata(after_path)
                ):
                    raise ValueError("repository_evidence_file_identity_changed")
                target = os.fsencode(target_before)
                if len(target) > max_bytes:
                    raise ValueError("repository_evidence_file_too_large")
                budget.consume_bytes(len(target))
                public = _inventory_public_entry(
                    path=path,
                    kind="symlink",
                    metadata=before,
                    content_sha256=hashlib.sha256(target).hexdigest(),
                    size=len(target),
                    fingerprint_sha256=_inventory_fingerprint(
                        "symlink",
                        mode,
                        content=target,
                    ),
                )
                captured.append((public, _stable_file_metadata(before)))
                _revalidate_directory_chain(
                    chain,
                    anchor.metadata.st_dev,
                    anchor.mount_identity,
                )
                continue

            if stat.S_ISREG(before.st_mode):
                if not _owner_controlled_regular(before):
                    raise ValueError("repository_evidence_target_must_be_owner_controlled_regular_file")
                if before.st_size > max_bytes:
                    raise ValueError("repository_evidence_file_too_large")
                if before.st_size > budget.remaining_bytes:
                    raise ValueError("repository_evidence_total_bytes_exceeded")
                try:
                    file_fd = os.open(name, _secure_file_flags(), dir_fd=directory_fd)
                except OSError as exc:
                    raise ValueError("repository_evidence_file_identity_changed") from exc
                try:
                    opened = os.fstat(file_fd)
                    if not _owner_controlled_regular(opened) or not _same_identity(before, opened):
                        raise ValueError("repository_evidence_file_identity_changed")
                    _require_descriptor_on_root_mount(
                        anchor.mount_identity,
                        file_fd,
                        path,
                    )
                    content_sha256, _, bytes_read = _read_expected_hashes(
                        file_fd,
                        before.st_size,
                        budget,
                    )
                    after_fd = os.fstat(file_fd)
                finally:
                    os.close(file_fd)
                try:
                    after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise ValueError("repository_evidence_file_identity_changed") from exc
                if (
                    not _owner_controlled_regular(after_fd)
                    or not _owner_controlled_regular(after_path)
                    or _stable_file_metadata(opened) != _stable_file_metadata(after_fd)
                    or _stable_file_metadata(opened) != _stable_file_metadata(after_path)
                    or bytes_read != opened.st_size
                ):
                    raise ValueError("repository_evidence_file_identity_changed")
                public = _inventory_public_entry(
                    path=path,
                    kind="regular",
                    metadata=opened,
                    content_sha256=content_sha256,
                    size=bytes_read,
                    fingerprint_sha256=_inventory_fingerprint(
                        "regular",
                        mode,
                        content_sha256=content_sha256,
                    ),
                )
                captured.append((public, _stable_file_metadata(opened)))
                _revalidate_directory_chain(
                    chain,
                    anchor.metadata.st_dev,
                    anchor.mount_identity,
                )
                continue

            raise ValueError(f"repository_inventory_special_file_rejected={path}")

        _revalidate_directory_chain(
            chain,
            anchor.metadata.st_dev,
            anchor.mount_identity,
        )
        revalidate_repository_root_anchor(anchor)

    walk(anchor.fd, "", (), 0)
    return sorted(captured, key=lambda item: str(item[0]["path"]))


def snapshot_repository_inventory_from_anchor(
    anchor: RepositoryRootAnchor,
    *,
    exclude: InventoryExclusion | None = None,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[dict[str, object]]:
    """Inventory one full worktree through a stable root descriptor.

    The initial and confirmation traversals share one byte and deadline budget.
    Directory identities and discovery manifests must remain unchanged between
    traversals.  Excluded directories are pruned before descent.
    """

    if not isinstance(anchor, RepositoryRootAnchor):
        raise TypeError("repository_root_anchor_required")
    if exclude is None:
        exclusion: InventoryExclusion = lambda _path: False
    elif callable(exclude):
        exclusion = exclude
    else:
        raise TypeError("repository_inventory_exclusion_must_be_callable")
    byte_limit = _require_positive_limit(max_bytes)
    total_limit = _require_positive_limit(max_total_bytes)
    path_limit = _require_positive_limit(max_paths)
    timeout_limit = _require_positive_timeout(timeout_seconds)
    budget = _SnapshotBudget(
        remaining_bytes=total_limit,
        remaining_path_reads=1,
        deadline=time.monotonic() + timeout_limit,
    )
    revalidate_repository_root_anchor(anchor)
    first = _capture_repository_inventory_pass(
        anchor,
        exclude=exclusion,
        max_bytes=byte_limit,
        max_paths=path_limit,
        budget=budget,
    )
    second = _capture_repository_inventory_pass(
        anchor,
        exclude=exclusion,
        max_bytes=byte_limit,
        max_paths=path_limit,
        budget=budget,
    )
    if first != second:
        raise ValueError("repository_inventory_changed_during_capture")
    budget.check_deadline()
    revalidate_repository_root_anchor(anchor)
    return [entry for entry, _identity in first]


def snapshot_repository_inventory(
    root: str | os.PathLike[str],
    *,
    exclude: InventoryExclusion | None = None,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[dict[str, object]]:
    """Open and inventory an entire repository without following links."""

    with open_repository_root_anchor(root) as anchor:
        return snapshot_repository_inventory_from_anchor(
            anchor,
            exclude=exclude,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
            max_paths=max_paths,
            timeout_seconds=timeout_seconds,
        )


def _read_regular_payload(
    anchor: RepositoryRootAnchor,
    path: str,
    max_bytes: int,
    budget: _SnapshotBudget,
) -> AnchoredFilePayload:
    budget.consume_path()
    parts = path.split("/")
    current_fd = anchor.fd
    owned_fds: list[int] = []
    chain: list[DirectoryLink] = []
    try:
        for component in parts[:-1]:
            try:
                before = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                child_fd = os.open(component, _secure_directory_flags(), dir_fd=current_fd)
                opened = os.fstat(child_fd)
            except OSError as exc:
                raise ValueError("repository_path_parent_identity_changed") from exc
            if (
                not stat.S_ISDIR(before.st_mode)
                or not stat.S_ISDIR(opened.st_mode)
                or before.st_dev != anchor.metadata.st_dev
                or opened.st_dev != anchor.metadata.st_dev
                or not _same_identity(before, opened)
            ):
                os.close(child_fd)
                raise ValueError("repository_path_parent_identity_changed")
            try:
                require_same_repository_mount(
                    anchor,
                    child_fd,
                    "/".join(parts[: len(chain) + 1]),
                )
            except Exception:
                os.close(child_fd)
                raise
            chain.append((current_fd, component, child_fd, opened))
            owned_fds.append(child_fd)
            current_fd = child_fd

        name = parts[-1]
        try:
            before = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(f"repository_evidence_target_unavailable={path}") from exc
        if stat.S_ISLNK(before.st_mode):
            raise ValueError(f"repository_evidence_symlink_rejected={path}")
        if not _owner_controlled_regular(before):
            raise ValueError(
                f"repository_evidence_target_must_be_owner_controlled_regular_file={path}"
            )
        if before.st_size > max_bytes:
            raise ValueError(f"repository_evidence_file_too_large={path}")
        if before.st_size > budget.remaining_bytes:
            raise ValueError("repository_evidence_total_bytes_exceeded")
        try:
            file_fd = os.open(name, _secure_file_flags(), dir_fd=current_fd)
        except OSError as exc:
            raise ValueError("repository_evidence_file_identity_changed") from exc
        try:
            opened = os.fstat(file_fd)
            if not _owner_controlled_regular(opened) or not _same_identity(before, opened):
                raise ValueError("repository_evidence_file_identity_changed")
            _require_descriptor_on_root_mount(
                anchor.mount_identity,
                file_fd,
                path,
            )
            encoded = _read_expected_bytes(file_fd, before.st_size, budget)
            after_fd = os.fstat(file_fd)
        finally:
            os.close(file_fd)
        try:
            after_path = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError("repository_evidence_file_identity_changed") from exc
        if (
            not _owner_controlled_regular(after_fd)
            or not _owner_controlled_regular(after_path)
            or _stable_file_metadata(opened) != _stable_file_metadata(after_fd)
            or _stable_file_metadata(opened) != _stable_file_metadata(after_path)
            or len(encoded) != opened.st_size
        ):
            raise ValueError("repository_evidence_file_identity_changed")
        _revalidate_directory_chain(
            chain,
            anchor.metadata.st_dev,
            anchor.mount_identity,
        )
        revalidate_repository_root_anchor(anchor)
        return AnchoredFilePayload(
            path=path,
            data=encoded,
            mode=0o755 if opened.st_mode & 0o111 else 0o644,
        )
    finally:
        for directory_fd in reversed(owned_fds):
            os.close(directory_fd)


def read_regular_files_from_anchor(
    anchor: RepositoryRootAnchor,
    paths: Iterable[object],
    *,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_paths: int = DEFAULT_MAX_PATHS,
    timeout_seconds: float = DEFAULT_SNAPSHOT_TIMEOUT_SECONDS,
) -> list[AnchoredFilePayload]:
    """Read bounded regular-file payloads through one stable root descriptor."""

    if not isinstance(anchor, RepositoryRootAnchor):
        raise TypeError("repository_root_anchor_required")
    revalidate_repository_root_anchor(anchor)
    byte_limit = _require_positive_limit(max_bytes)
    total_limit = _require_positive_limit(max_total_bytes)
    path_limit = _require_positive_limit(max_paths)
    timeout_limit = _require_positive_timeout(timeout_seconds)
    normalized_paths = _normalize_allowed_paths(paths, max_items=path_limit)
    budget = _SnapshotBudget(
        remaining_bytes=total_limit,
        remaining_path_reads=len(normalized_paths),
        deadline=time.monotonic() + timeout_limit,
    )
    payloads = [
        _read_regular_payload(anchor, path, byte_limit, budget)
        for path in normalized_paths
    ]
    budget.check_deadline()
    revalidate_repository_root_anchor(anchor)
    return payloads


def _normalize_snapshot(snapshot: object) -> list[dict[str, object]]:
    if not isinstance(snapshot, (list, tuple)):
        raise TypeError("repository_snapshot_must_be_sequence")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    expected_keys = {"path", "state", "sha256", "size"}
    for item in snapshot:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("invalid_repository_snapshot_entry")
        path = normalize_repo_relative_path(item.get("path"))
        if item.get("path") != path or path in seen:
            raise ValueError("invalid_repository_snapshot_entry")
        seen.add(path)
        state = item.get("state")
        digest = item.get("sha256")
        size = item.get("size")
        if state not in _SNAPSHOT_STATES:
            raise ValueError("invalid_repository_snapshot_entry")
        if state == "missing":
            if digest is not None or size is not None:
                raise ValueError("invalid_repository_snapshot_entry")
        elif (
            not isinstance(digest, str)
            or _SHA256_RE.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ValueError("invalid_repository_snapshot_entry")
        normalized.append({"path": path, "state": state, "sha256": digest, "size": size})
    return sorted(normalized, key=lambda entry: str(entry["path"]))


def repository_snapshot_digest(snapshot: Sequence[dict[str, object]]) -> str:
    return _canonical_digest(
        {
            "kind": "codexqb_repository_snapshot",
            "schema_version": REPOSITORY_EVIDENCE_SCHEMA_VERSION,
            "files": _normalize_snapshot(snapshot),
        }
    )


def baseline_digest(snapshot: Sequence[dict[str, object]]) -> str:
    return _canonical_digest(
        {
            "kind": "codexqb_repository_baseline",
            "schema_version": REPOSITORY_EVIDENCE_SCHEMA_VERSION,
            "files": _normalize_snapshot(snapshot),
        }
    )


def build_change_manifest(
    before_snapshot: Sequence[dict[str, object]],
    after_snapshot: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    before = {str(item["path"]): item for item in _normalize_snapshot(before_snapshot)}
    after = {str(item["path"]): item for item in _normalize_snapshot(after_snapshot)}
    if set(before) != set(after):
        raise ValueError("repository_snapshot_path_set_mismatch")
    manifest: list[dict[str, object]] = []
    for path in sorted(before):
        old = before[path]
        new = after[path]
        old_present = old["state"] == "present"
        new_present = new["state"] == "present"
        if not old_present and new_present:
            state = "add"
        elif old_present and not new_present:
            state = "delete"
        elif old_present and new_present and (
            old["sha256"] != new["sha256"] or old["size"] != new["size"]
        ):
            state = "modify"
        else:
            state = "unchanged"
        manifest.append(
            {
                "path": path,
                "state": state,
                "before_sha256": old["sha256"],
                "after_sha256": new["sha256"],
                "size": new["size"] if new_present else 0,
            }
        )
    return manifest


def _normalize_manifest(manifest: object) -> list[dict[str, object]]:
    if not isinstance(manifest, (list, tuple)):
        raise TypeError("repository_manifest_must_be_sequence")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    expected_keys = {"path", "state", "before_sha256", "after_sha256", "size"}
    for item in manifest:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("invalid_repository_manifest_entry")
        path = normalize_repo_relative_path(item.get("path"))
        state = item.get("state")
        before_sha = item.get("before_sha256")
        after_sha = item.get("after_sha256")
        size = item.get("size")
        if item.get("path") != path or path in seen or state not in _CHANGE_STATES:
            raise ValueError("invalid_repository_manifest_entry")
        if before_sha is not None and (not isinstance(before_sha, str) or _SHA256_RE.fullmatch(before_sha) is None):
            raise ValueError("invalid_repository_manifest_entry")
        if after_sha is not None and (not isinstance(after_sha, str) or _SHA256_RE.fullmatch(after_sha) is None):
            raise ValueError("invalid_repository_manifest_entry")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("invalid_repository_manifest_entry")
        valid_state = (
            (state == "add" and before_sha is None and after_sha is not None)
            or (state == "modify" and before_sha is not None and after_sha is not None and before_sha != after_sha)
            or (state == "delete" and before_sha is not None and after_sha is None and size == 0)
            or (
                state == "unchanged"
                and ((before_sha is None and after_sha is None and size == 0) or before_sha == after_sha)
            )
        )
        if not valid_state:
            raise ValueError("invalid_repository_manifest_entry")
        seen.add(path)
        normalized.append(
            {
                "path": path,
                "state": state,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "size": size,
            }
        )
    return sorted(normalized, key=lambda entry: str(entry["path"]))


def changed_file_manifest(manifest: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return [entry for entry in _normalize_manifest(manifest) if entry["state"] != "unchanged"]


def changed_file_digest(manifest: Sequence[dict[str, object]]) -> str:
    return _canonical_digest(
        {
            "kind": "codexqb_changed_file_manifest",
            "schema_version": REPOSITORY_EVIDENCE_SCHEMA_VERSION,
            "files": changed_file_manifest(manifest),
        }
    )


def repository_state_digest(
    *,
    apply_run_id: str,
    task_id: str,
    apply_run_registration_id: str,
    contract_digest: str,
    generation: int,
    review_package_sha256: str,
    repository_baseline_digest: str,
    current_snapshot_digest: str,
    changed_files_digest: str,
) -> str:
    """Bind repository content evidence to one task verification generation."""

    run_id = _require_nonempty_string(apply_run_id, "apply_run_id")
    bound_task_id = _require_nonempty_string(task_id, "task_id")
    registration = _require_sha256(apply_run_registration_id, "apply_run_registration_id")
    contract = _require_sha256(contract_digest, "contract_digest")
    patch = _require_sha256(review_package_sha256, "review_package_sha256")
    baseline = _require_sha256(repository_baseline_digest, "repository_baseline_digest")
    current = _require_sha256(current_snapshot_digest, "current_snapshot_digest")
    changed = _require_sha256(changed_files_digest, "changed_files_digest")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ValueError("generation_must_be_nonnegative_integer")
    return _canonical_digest(
        {
            "kind": "codexqb_repository_state",
            "schema_version": REPOSITORY_EVIDENCE_SCHEMA_VERSION,
            "apply_run_id": run_id,
            "task_id": bound_task_id,
            "apply_run_registration_id": registration,
            "contract_digest": contract,
            "generation": generation,
            "review_package_sha256": patch,
            "repository_baseline_digest": baseline,
            "current_snapshot_digest": current,
            "changed_files_digest": changed,
        }
    )


def capture_repository_evidence(
    root: str | os.PathLike[str],
    allowed_paths: Iterable[object],
    baseline_snapshot: Sequence[dict[str, object]],
    *,
    apply_run_id: str,
    task_id: str,
    apply_run_registration_id: str,
    contract_digest: str,
    generation: int,
    review_package_sha256: str,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Re-snapshot allowed paths and return integration-ready evidence."""

    normalized_paths = _normalize_allowed_paths(allowed_paths)
    baseline = _normalize_snapshot(baseline_snapshot)
    if [str(entry["path"]) for entry in baseline] != normalized_paths:
        raise ValueError("repository_baseline_allowed_path_mismatch")
    current = snapshot_allowed_paths(root, normalized_paths, max_bytes=max_bytes)
    manifest = build_change_manifest(baseline, current)
    baseline_hash = baseline_digest(baseline)
    current_hash = repository_snapshot_digest(current)
    changed_files = changed_file_manifest(manifest)
    changed_hash = changed_file_digest(manifest)
    state_hash = repository_state_digest(
        apply_run_id=apply_run_id,
        task_id=task_id,
        apply_run_registration_id=apply_run_registration_id,
        contract_digest=contract_digest,
        generation=generation,
        review_package_sha256=review_package_sha256,
        repository_baseline_digest=baseline_hash,
        current_snapshot_digest=current_hash,
        changed_files_digest=changed_hash,
    )
    return {
        "schema_version": REPOSITORY_EVIDENCE_SCHEMA_VERSION,
        "baseline_digest": baseline_hash,
        "current_snapshot_digest": current_hash,
        "manifest": manifest,
        "changed_files": changed_files,
        "changed_files_digest": changed_hash,
        "repository_state_digest": state_hash,
    }


__all__ = [
    "AnchoredFilePayload",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_PATHS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "DEFAULT_SNAPSHOT_TIMEOUT_SECONDS",
    "REPOSITORY_EVIDENCE_SCHEMA_VERSION",
    "RepositoryRootAnchor",
    "baseline_digest",
    "build_change_manifest",
    "capture_repository_evidence",
    "changed_file_digest",
    "changed_file_manifest",
    "normalize_repo_relative_path",
    "open_repository_root_anchor",
    "read_regular_files_from_anchor",
    "repository_snapshot_digest",
    "repository_state_digest",
    "require_same_repository_mount",
    "snapshot_allowed_paths",
    "snapshot_git_paths",
    "snapshot_git_paths_from_anchor",
    "snapshot_repository_inventory",
    "snapshot_repository_inventory_from_anchor",
]
