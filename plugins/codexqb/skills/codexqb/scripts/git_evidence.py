#!/usr/bin/env python3
"""No-exec Git workspace evidence for CodexQB.

This module deliberately avoids porcelain commands and every Git operation
that can invoke repository-controlled diff drivers, text converters, clean
filters, hooks, or file-system monitors.  Git is used only to read immutable
index/tree metadata and path names.  Worktree blob identities are computed
from descriptor-bound raw bytes by :mod:`repository_evidence`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import threading
import time
from typing import Any

from repository_evidence import (
    RepositoryRootAnchor,
    normalize_repo_relative_path,
    open_repository_root_anchor,
    revalidate_repository_root_anchor,
    snapshot_git_paths_from_anchor,
)


GIT_EVIDENCE_SCHEMA_VERSION = 1
GIT_COMMAND_TIMEOUT_SECONDS = 60
MAX_GIT_COMMAND_OUTPUT_BYTES = 16 * 1024 * 1024
GIT_OUTPUT_CHUNK_BYTES = 64 * 1024
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

GIT_COMMAND_PREFIX = (
    "git",
    "--no-pager",
    "--no-replace-objects",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.ignorestat=false",
    "-c",
    "core.untrackedCache=false",
)

_ALLOWED_GIT_ARGUMENTS = frozenset(
    {
        ("rev-parse", "--show-object-format"),
        ("symbolic-ref", "--quiet", "--short", "HEAD"),
        ("rev-parse", "--verify", "--quiet", "HEAD"),
        ("ls-files", "--stage", "-z"),
        ("ls-tree", "-r", "-z", "--full-tree", "HEAD"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    }
)
_INDEX_MODES = frozenset({"100644", "100755", "120000", "160000"})
_OBJECT_FORMAT_LENGTHS = {"sha1": 40, "sha256": 64}
_HEX_RE = re.compile(r"[0-9a-f]+")


@dataclass(frozen=True)
class _GitProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class _IndexEntry:
    mode: str
    oid: str
    stage: int


@dataclass(frozen=True)
class _TreeEntry:
    mode: str
    object_type: str
    oid: str


@dataclass(frozen=True)
class _PlumbingSnapshot:
    object_format: str
    branch: str
    head: str
    index_raw: bytes
    tree_raw: bytes
    untracked_raw: bytes


def git_subprocess_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment with inherited Git overrides removed."""

    original = os.environ if source is None else source
    environment = {
        key: value
        for key, value in original.items()
        if isinstance(key, str)
        and isinstance(value, str)
        and not key.upper().startswith("GIT_")
        and key.upper() not in {"PWD", "OLDPWD"}
    }
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["PATH"] = os.defpath
    return environment


def trusted_git_executable() -> str:
    """Resolve Git only from the platform's fixed system search path."""

    candidate = shutil.which("git", path=os.defpath)
    if candidate is None or not os.path.isabs(candidate):
        raise ValueError("trusted_git_executable_unavailable")
    try:
        resolved = Path(candidate).resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise ValueError("trusted_git_executable_unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("trusted_git_executable_unavailable")
    return resolved.as_posix()


def _normalize_git_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
    if isinstance(arguments, (str, bytes, bytearray)) or not isinstance(arguments, Sequence):
        raise TypeError("git_evidence_arguments_must_be_sequence")
    normalized = tuple(arguments)
    if (
        normalized not in _ALLOWED_GIT_ARGUMENTS
        or any(not isinstance(argument, str) or not argument or "\x00" in argument for argument in normalized)
    ):
        raise ValueError("git_evidence_command_not_allowed")
    return normalized


def git_command(arguments: Sequence[str]) -> list[str]:
    """Build one command from the fixed no-exec allowlist."""

    normalized = _normalize_git_arguments(arguments)
    return [trusted_git_executable(), *GIT_COMMAND_PREFIX[1:], *normalized]


def _enter_anchored_root(root_fd: int) -> None:
    """Enter the opened root inode in the child without resolving its path."""

    os.fchdir(root_fd)
    os.close(root_fd)


def _revalidate_git_anchor(anchor: RepositoryRootAnchor) -> None:
    try:
        revalidate_repository_root_anchor(anchor)
    except (TypeError, ValueError) as exc:
        raise ValueError("git_evidence_root_identity_changed") from exc


def _terminate_git_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass


def _finalize_git_process(
    process: subprocess.Popen[bytes],
    selector: selectors.BaseSelector | None,
    *,
    operation: str,
) -> None:
    """Kill the whole process group, synchronously reap, and close every pipe."""

    reap_failure: BaseException | None = None
    try:
        _terminate_git_process_group(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_git_process_group(process)
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as exc:
                reap_failure = exc
        except OSError as exc:
            reap_failure = exc
    finally:
        if selector is not None:
            try:
                selector.close()
            except Exception:
                pass
        for pipe in (process.stdout, process.stderr):
            if pipe is None:
                continue
            try:
                pipe.close()
            except Exception:
                pass
    if reap_failure is not None:
        raise ValueError(f"git_evidence_command_unavailable={operation}") from reap_failure


def _run_git_process_from_anchor(
    anchor: RepositoryRootAnchor,
    arguments: Sequence[str],
    *,
    operation: str,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> _GitProcessResult:
    _revalidate_git_anchor(anchor)
    command = git_command(arguments)
    if os.name != "posix":
        raise ValueError("git_evidence_process_isolation_not_supported")
    if threading.active_count() != 1:
        raise ValueError("git_evidence_preexec_requires_single_thread")
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    stdout = bytearray()
    stderr = bytearray()
    total = 0
    output_limit_exceeded = False
    timed_out = False
    try:
        try:
            process = subprocess.Popen(
                command,
                cwd=None,
                env=git_subprocess_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(anchor.fd,),
                preexec_fn=partial(_enter_anchored_root, anchor.fd),
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"git_evidence_command_unavailable={operation}") from exc
        deadline = time.monotonic() + GIT_COMMAND_TIMEOUT_SECONDS
        _revalidate_git_anchor(anchor)
        if process.stdout is None or process.stderr is None:
            raise ValueError(f"git_evidence_command_unavailable={operation}")
        selector = selectors.DefaultSelector()
        streams = {
            process.stdout.fileno(): stdout,
            process.stderr.fileno(): stderr,
        }
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(min(0.1, remaining)):
                fd = key.fileobj.fileno()
                try:
                    chunk = os.read(
                        fd,
                        min(
                            GIT_OUTPUT_CHUNK_BYTES,
                            MAX_GIT_COMMAND_OUTPUT_BYTES - total + 1,
                        ),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                streams[fd].extend(chunk)
                total += len(chunk)
                if total > MAX_GIT_COMMAND_OUTPUT_BYTES:
                    output_limit_exceeded = True
                    break
            if output_limit_exceeded:
                break
        if not timed_out and not output_limit_exceeded:
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True

        if output_limit_exceeded:
            raise ValueError(f"git_evidence_output_limit_exceeded={operation}")
        if timed_out:
            raise ValueError(f"git_evidence_command_unavailable={operation}")
        _revalidate_git_anchor(anchor)
        returncode = int(process.returncode if process.returncode is not None else -1)
        if returncode not in allowed_returncodes:
            raise ValueError(f"git_evidence_command_failed={operation}")
        return _GitProcessResult(returncode, bytes(stdout), bytes(stderr))
    except OSError as exc:
        raise ValueError(f"git_evidence_command_unavailable={operation}") from exc
    finally:
        if process is not None:
            _finalize_git_process(process, selector, operation=operation)


def _run_git_process(
    root: str | os.PathLike[str] | RepositoryRootAnchor,
    arguments: Sequence[str],
    *,
    operation: str,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> _GitProcessResult:
    if isinstance(root, RepositoryRootAnchor):
        return _run_git_process_from_anchor(
            root,
            arguments,
            operation=operation,
            allowed_returncodes=allowed_returncodes,
        )
    try:
        with open_repository_root_anchor(root) as anchor:
            return _run_git_process_from_anchor(
                anchor,
                arguments,
                operation=operation,
                allowed_returncodes=allowed_returncodes,
            )
    except TypeError as exc:
        raise TypeError("git_evidence_root_must_be_path") from exc
    except ValueError as exc:
        if str(exc) == "repository_root_must_be_real_directory":
            raise ValueError("git_evidence_root_must_be_real_directory") from exc
        raise


def run_git_bytes(
    root: str | os.PathLike[str] | RepositoryRootAnchor,
    arguments: Sequence[str],
    *,
    operation: str = "allowed_git_query",
    allowed_returncodes: tuple[int, ...] = (0,),
) -> bytes:
    """Run one allowlisted Git query and return its byte-exact stdout."""

    return _run_git_process(
        root,
        arguments,
        operation=operation,
        allowed_returncodes=allowed_returncodes,
    ).stdout


def git_optional_text(
    root: str | os.PathLike[str] | RepositoryRootAnchor,
    arguments: Sequence[str],
) -> str | None:
    """Read one optional single-line value through the same strict allowlist."""

    result = _run_git_process(
        root,
        arguments,
        operation="optional_text",
        allowed_returncodes=(0, 1),
    )
    if result.returncode == 1:
        if result.stdout:
            raise ValueError("git_evidence_invalid_optional_text")
        return None
    return _decode_single_line(result.stdout, "optional_text")


def _decode_single_line(raw: bytes, label: str) -> str:
    value = raw[:-1] if raw.endswith(b"\n") else raw
    if not value or b"\x00" in value or b"\n" in value or b"\r" in value:
        raise ValueError(f"git_evidence_invalid_{label}")
    return os.fsdecode(value)


def _anchor_has_git_marker(anchor: RepositoryRootAnchor) -> bool:
    _revalidate_git_anchor(anchor)
    try:
        os.stat(".git", dir_fd=anchor.fd, follow_symlinks=False)
    except FileNotFoundError:
        _revalidate_git_anchor(anchor)
        return False
    except OSError as exc:
        raise ValueError("git_evidence_repository_probe_failed") from exc
    _revalidate_git_anchor(anchor)
    return True


def _looks_like_absent_repository(
    anchor: RepositoryRootAnchor,
    result: _GitProcessResult,
) -> bool:
    return (
        result.returncode == 128
        and b"not a git repository" in result.stderr.lower()
        and not _anchor_has_git_marker(anchor)
    )


def _probe_object_format(anchor: RepositoryRootAnchor) -> str | None:
    result = _run_git_process(
        anchor,
        ("rev-parse", "--show-object-format"),
        operation="object_format_probe",
        allowed_returncodes=(0, 128),
    )
    if result.returncode != 0:
        if _looks_like_absent_repository(anchor, result):
            return None
        raise ValueError("git_evidence_repository_probe_failed")
    object_format = _decode_single_line(result.stdout, "object_format")
    if object_format not in _OBJECT_FORMAT_LENGTHS:
        raise ValueError("git_evidence_unsupported_object_format")
    return object_format


def _validate_oid(value: str, object_format: str, *, allow_zero: bool = False) -> str:
    expected_length = _OBJECT_FORMAT_LENGTHS[object_format]
    if len(value) != expected_length or _HEX_RE.fullmatch(value) is None:
        raise ValueError("git_evidence_invalid_object_id")
    if not allow_zero and set(value) == {"0"}:
        raise ValueError("git_evidence_invalid_object_id")
    return value


def _decode_path(raw: bytes) -> str:
    if not raw or b"\x00" in raw or any(character in raw for character in (b"\t", b"\r", b"\n")):
        raise ValueError("git_evidence_invalid_path")
    decoded = os.fsdecode(raw)
    try:
        normalized = normalize_repo_relative_path(decoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("git_evidence_invalid_path") from exc
    if normalized != decoded or os.fsencode(decoded) != raw:
        raise ValueError("git_evidence_invalid_path")
    return normalized


def _nul_records(raw: bytes, label: str) -> list[bytes]:
    if not raw:
        return []
    if not raw.endswith(b"\x00"):
        raise ValueError(f"git_evidence_invalid_{label}")
    records = raw[:-1].split(b"\x00")
    if any(not record for record in records):
        raise ValueError(f"git_evidence_invalid_{label}")
    return records


def _parse_index(raw: bytes, object_format: str) -> dict[str, tuple[_IndexEntry, ...]]:
    grouped: dict[str, list[_IndexEntry]] = {}
    seen: set[tuple[str, int]] = set()
    for record in _nul_records(raw, "index"):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode_raw, oid_raw, stage_raw = metadata.split(b" ")
            mode = mode_raw.decode("ascii")
            oid = oid_raw.decode("ascii")
            stage_text = stage_raw.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("git_evidence_invalid_index") from exc
        if mode not in _INDEX_MODES or stage_text not in {"0", "1", "2", "3"}:
            raise ValueError("git_evidence_invalid_index")
        path = _decode_path(raw_path)
        stage = int(stage_text)
        key = (path, stage)
        if key in seen:
            raise ValueError("git_evidence_invalid_index")
        seen.add(key)
        grouped.setdefault(path, []).append(
            _IndexEntry(mode, _validate_oid(oid, object_format, allow_zero=True), stage)
        )
    return {
        path: tuple(sorted(entries, key=lambda entry: entry.stage))
        for path, entries in sorted(grouped.items())
    }


def _parse_tree(raw: bytes, object_format: str) -> dict[str, _TreeEntry]:
    tree: dict[str, _TreeEntry] = {}
    for record in _nul_records(raw, "tree"):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode_raw, type_raw, oid_raw = metadata.split(b" ")
            mode = mode_raw.decode("ascii")
            object_type = type_raw.decode("ascii")
            oid = oid_raw.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("git_evidence_invalid_tree") from exc
        path = _decode_path(raw_path)
        if (
            mode not in _INDEX_MODES
            or object_type not in {"blob", "commit"}
            or (mode == "160000") != (object_type == "commit")
            or path in tree
        ):
            raise ValueError("git_evidence_invalid_tree")
        tree[path] = _TreeEntry(mode, object_type, _validate_oid(oid, object_format))
    return dict(sorted(tree.items()))


def _parse_untracked(raw: bytes) -> list[str]:
    paths = [_decode_path(record) for record in _nul_records(raw, "untracked_paths")]
    if len(paths) != len(set(paths)):
        raise ValueError("git_evidence_invalid_untracked_paths")
    return sorted(paths)


def _capture_plumbing(
    anchor: RepositoryRootAnchor,
    object_format: str,
) -> _PlumbingSnapshot:
    branch_result = _run_git_process(
        anchor,
        ("symbolic-ref", "--quiet", "--short", "HEAD"),
        operation="branch",
        allowed_returncodes=(0, 1),
    )
    if branch_result.returncode == 0:
        branch = _decode_single_line(branch_result.stdout, "branch")
    elif branch_result.stdout:
        raise ValueError("git_evidence_invalid_branch")
    else:
        branch = "unknown"

    head_result = _run_git_process(
        anchor,
        ("rev-parse", "--verify", "--quiet", "HEAD"),
        operation="head",
        allowed_returncodes=(0, 1),
    )
    if head_result.returncode == 0:
        head = _validate_oid(_decode_single_line(head_result.stdout, "head"), object_format)
        tree_raw = run_git_bytes(
            anchor,
            ("ls-tree", "-r", "-z", "--full-tree", "HEAD"),
            operation="head_tree",
        )
    elif head_result.stdout:
        raise ValueError("git_evidence_invalid_head")
    else:
        head = "unknown"
        tree_raw = b""

    return _PlumbingSnapshot(
        object_format=object_format,
        branch=branch,
        head=head,
        index_raw=run_git_bytes(
            anchor,
            ("ls-files", "--stage", "-z"),
            operation="index",
        ),
        tree_raw=tree_raw,
        untracked_raw=run_git_bytes(
            anchor,
            ("ls-files", "--others", "--exclude-standard", "-z"),
            operation="untracked_paths",
        ),
    )


def _normal_index_entry(entries: tuple[_IndexEntry, ...] | None) -> _IndexEntry | None:
    if entries is None or len(entries) != 1 or entries[0].stage != 0:
        return None
    return entries[0]


def _staged_changes(
    index: dict[str, tuple[_IndexEntry, ...]],
    tree: dict[str, _TreeEntry],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for path in sorted(set(index) | set(tree)):
        head_entry = tree.get(path)
        index_entries = index.get(path)
        normal = _normal_index_entry(index_entries)
        if index_entries is None:
            changes.append(
                {
                    "path": path,
                    "state": "delete",
                    "head_mode": head_entry.mode if head_entry else None,
                    "head_oid": head_entry.oid if head_entry else None,
                    "index_mode": None,
                    "index_oid": None,
                }
            )
        elif normal is None:
            changes.append(
                {
                    "path": path,
                    "state": "non_normal_index",
                    "head_mode": head_entry.mode if head_entry else None,
                    "head_oid": head_entry.oid if head_entry else None,
                    "index_entries": [
                        {"mode": entry.mode, "oid": entry.oid, "stage": entry.stage}
                        for entry in index_entries
                    ],
                }
            )
        elif head_entry is None:
            changes.append(
                {
                    "path": path,
                    "state": "add",
                    "head_mode": None,
                    "head_oid": None,
                    "index_mode": normal.mode,
                    "index_oid": normal.oid,
                }
            )
        elif head_entry.mode != normal.mode or head_entry.oid != normal.oid:
            changes.append(
                {
                    "path": path,
                    "state": "modify",
                    "head_mode": head_entry.mode,
                    "head_oid": head_entry.oid,
                    "index_mode": normal.mode,
                    "index_oid": normal.oid,
                }
            )
    return changes


def _unstaged_changes(
    index: dict[str, tuple[_IndexEntry, ...]],
    worktree: list[dict[str, object]],
    excluded_paths: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    worktree_by_path = {str(entry["path"]): entry for entry in worktree}
    changes: list[dict[str, Any]] = []
    for path, entries in index.items():
        if path in excluded_paths:
            continue
        normal = _normal_index_entry(entries)
        if normal is None:
            changes.append(
                {
                    "path": path,
                    "state": "non_normal_index",
                    "index_entries": [
                        {"mode": entry.mode, "oid": entry.oid, "stage": entry.stage}
                        for entry in entries
                    ],
                }
            )
            continue
        if normal.mode == "160000":
            changes.append(
                {
                    "path": path,
                    "state": "gitlink_unverified",
                    "index_mode": normal.mode,
                    "index_oid": normal.oid,
                }
            )
            continue
        current = worktree_by_path.get(path)
        if current is None:
            raise ValueError("git_evidence_worktree_snapshot_incomplete")
        if current.get("state") == "missing":
            changes.append(
                {
                    "path": path,
                    "state": "delete",
                    "index_mode": normal.mode,
                    "index_oid": normal.oid,
                    "worktree_mode": None,
                    "worktree_oid": None,
                }
            )
        elif (
            current.get("git_mode") != normal.mode
            or current.get("git_blob_oid") != normal.oid
        ):
            changes.append(
                {
                    "path": path,
                    "state": "modify",
                    "index_mode": normal.mode,
                    "index_oid": normal.oid,
                    "worktree_mode": current.get("git_mode"),
                    "worktree_oid": current.get("git_blob_oid"),
                }
            )
    return changes


def _canonical_digest(items: list[dict[str, Any]] | list[str]) -> str:
    if not items:
        return EMPTY_SHA256
    encoded = json.dumps(
        items,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8") + b"\n"
    return hashlib.sha256(encoded).hexdigest()


def canonical_git_evidence_digest(items: list[dict[str, Any]] | list[str]) -> str:
    """Digest a canonical plumbing evidence list using the public v1 rule."""

    return _canonical_digest(items)


def _normalize_exclusions(paths: Iterable[object]) -> tuple[str, ...]:
    if isinstance(paths, (str, bytes, bytearray, dict)) or not isinstance(paths, Iterable):
        raise TypeError("excluded_untracked_paths_must_be_iterable")
    return tuple(sorted({normalize_repo_relative_path(path) for path in paths}))


def _path_is_excluded(path: str, exclusions: tuple[str, ...]) -> bool:
    return any(path == excluded or path.startswith(f"{excluded}/") for excluded in exclusions)


def _empty_evidence() -> dict[str, object]:
    return {
        "schema_version": GIT_EVIDENCE_SCHEMA_VERSION,
        "is_git": False,
        "branch": "unknown",
        "head": "unknown",
        "object_format": None,
        "tracked_paths": [],
        "untracked_paths": [],
        "worktree_entries": [],
        "untracked_entries": [],
        "staged_changes": [],
        "unstaged_changes": [],
        "status_sha256": EMPTY_SHA256,
        "staged_diff_sha256": EMPTY_SHA256,
        "unstaged_diff_sha256": EMPTY_SHA256,
        "untracked_paths_sha256": EMPTY_SHA256,
        "untracked_entries_sha256": EMPTY_SHA256,
    }


def capture_git_workspace_evidence(
    root: str | os.PathLike[str],
    excluded_untracked_paths: Iterable[object] = (),
    *,
    exclude_untracked: Callable[[str], bool] | None = None,
    exclude_tracked: Callable[[str], bool] | None = None,
) -> dict[str, object]:
    """Capture deterministic Git/index/worktree evidence without executable Git features."""

    exclusions = _normalize_exclusions(excluded_untracked_paths)
    if exclude_untracked is not None and not callable(exclude_untracked):
        raise TypeError("exclude_untracked_must_be_callable")
    if exclude_tracked is not None and not callable(exclude_tracked):
        raise TypeError("exclude_tracked_must_be_callable")
    try:
        with open_repository_root_anchor(root) as anchor:
            object_format = _probe_object_format(anchor)
            if object_format is None:
                return _empty_evidence()

            before = _capture_plumbing(anchor, object_format)
            index = _parse_index(before.index_raw, object_format)
            tree = _parse_tree(before.tree_raw, object_format)
            untracked_paths = [
                candidate
                for candidate in _parse_untracked(before.untracked_raw)
                if not _path_is_excluded(candidate, exclusions)
                and (exclude_untracked is None or not exclude_untracked(candidate))
            ]
            tracked_paths = sorted(index)
            excluded_tracked_paths = frozenset(
                path
                for path in index
                if exclude_tracked is not None and exclude_tracked(path)
            )
            tracked_snapshot_paths = [
                tracked_path
                for tracked_path, entries in index.items()
                if (normal := _normal_index_entry(entries)) is not None
                and normal.mode != "160000"
                and tracked_path not in excluded_tracked_paths
            ]
            snapshot_paths = sorted(set(tracked_snapshot_paths) | set(untracked_paths))
            combined_worktree = (
                snapshot_git_paths_from_anchor(
                    anchor,
                    snapshot_paths,
                    object_format=object_format,
                )
                if snapshot_paths
                else []
            )
            tracked_snapshot_path_set = set(tracked_snapshot_paths)
            untracked_path_set = set(untracked_paths)
            worktree = [
                entry
                for entry in combined_worktree
                if str(entry.get("path")) in tracked_snapshot_path_set
            ]
            untracked_entries = [
                entry
                for entry in combined_worktree
                if str(entry.get("path")) in untracked_path_set
            ]
            if (
                {str(entry.get("path")) for entry in untracked_entries} != untracked_path_set
                or any(entry.get("state") != "present" for entry in untracked_entries)
            ):
                raise ValueError("git_evidence_untracked_snapshot_incomplete")
            after_object_format = _probe_object_format(anchor)
            if after_object_format != object_format:
                raise ValueError("git_evidence_changed_during_capture")
            after = _capture_plumbing(anchor, object_format)
            if before != after:
                raise ValueError("git_evidence_changed_during_capture")
            _revalidate_git_anchor(anchor)

            staged_changes = _staged_changes(index, tree)
            unstaged_changes = _unstaged_changes(
                index,
                worktree,
                excluded_tracked_paths,
            )
            staged_digest = _canonical_digest(staged_changes)
            unstaged_digest = _canonical_digest(unstaged_changes)
            untracked_digest = _canonical_digest(untracked_paths)
            untracked_entries_digest = _canonical_digest(untracked_entries)
            status_entries: list[dict[str, Any]] = [
                {"domain": "staged", **change} for change in staged_changes
            ]
            status_entries.extend(
                {"domain": "unstaged", **change} for change in unstaged_changes
            )
            status_entries.extend(
                {"domain": "untracked", "path": untracked_path, "state": "untracked"}
                for untracked_path in untracked_paths
            )

            return {
                "schema_version": GIT_EVIDENCE_SCHEMA_VERSION,
                "is_git": True,
                "branch": before.branch,
                "head": before.head,
                "object_format": object_format,
                "tracked_paths": tracked_paths,
                "untracked_paths": untracked_paths,
                "worktree_entries": worktree,
                "untracked_entries": untracked_entries,
                "staged_changes": staged_changes,
                "unstaged_changes": unstaged_changes,
                "status_sha256": _canonical_digest(status_entries),
                "staged_diff_sha256": staged_digest,
                "unstaged_diff_sha256": unstaged_digest,
                "untracked_paths_sha256": untracked_digest,
                "untracked_entries_sha256": untracked_entries_digest,
            }
    except TypeError as exc:
        if str(exc) == "repository_root_must_be_path":
            raise TypeError("git_evidence_root_must_be_path") from exc
        raise
    except ValueError as exc:
        if str(exc) == "repository_root_must_be_real_directory":
            raise ValueError("git_evidence_root_must_be_real_directory") from exc
        raise


def git_tracked_paths(root: str | os.PathLike[str]) -> list[str]:
    evidence = capture_git_workspace_evidence(root)
    return list(evidence["tracked_paths"]) if evidence["is_git"] else []


def git_untracked_paths(
    root: str | os.PathLike[str],
    excluded_untracked_paths: Iterable[object] = (),
) -> list[str]:
    evidence = capture_git_workspace_evidence(root, excluded_untracked_paths)
    return list(evidence["untracked_paths"]) if evidence["is_git"] else []


def git_paths(root: str | os.PathLike[str]) -> list[str]:
    """Return the sorted union of tracked and non-ignored untracked paths."""

    evidence = capture_git_workspace_evidence(root)
    return sorted(set(evidence["tracked_paths"]) | set(evidence["untracked_paths"]))
