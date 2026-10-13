"""One-file JSON store: the whole memory lives in a single human-inspectable file.

Mem0's memories are opaque vector embeddings — you cannot read what the
agent "knows" by opening a file. callrecall-ai goes the other way: the
store is a plain JSON document you can open, grep, back up, or delete.
Writes are atomic (tmp file + rename) and guarded by an advisory file
lock where the platform supports it.
"""
from __future__ import annotations

import json
import os
import tempfile

try:
    import fcntl  # POSIX only; Windows simply skips locking
except ImportError:  # pragma: no cover
    fcntl = None

DEFAULT_PATH = os.path.expanduser("~/.callrecall/memory.json")


class JsonFileStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = os.path.expanduser(path)

    # -- low level ------------------------------------------------------
    def _read_raw(self) -> dict:
        if not os.path.exists(self.path):
            return {"version": 1, "contacts": {}}
        with open(self.path, "r", encoding="utf-8") as f:
            self._lock(f, shared=True)
            try:
                data = json.load(f)
            finally:
                self._unlock(f)
        if not isinstance(data, dict) or "contacts" not in data:
            raise ValueError(f"corrupt memory file: {self.path}")
        return data

    def _write_raw(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".",
                                   prefix=".memory-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _lock(f, shared: bool) -> None:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)

    @staticmethod
    def _unlock(f) -> None:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # -- contact level ----------------------------------------------------
    def load(self) -> dict:
        """Return {contact_id: brief_dict}."""
        return self._read_raw().get("contacts", {})

    def save(self, contacts: dict) -> None:
        self._write_raw({"version": 1, "contacts": contacts})

    def get(self, contact_id: str) -> dict | None:
        return self.load().get(contact_id)

    def put(self, contact_id: str, brief_dict: dict) -> None:
        contacts = self.load()
        contacts[contact_id] = brief_dict
        self.save(contacts)

    def delete(self, contact_id: str) -> bool:
        contacts = self.load()
        if contact_id not in contacts:
            return False
        del contacts[contact_id]
        self.save(contacts)
        return True

    def contact_ids(self) -> list:
        return sorted(self.load().keys())
