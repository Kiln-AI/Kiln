# PyInstaller runtime hook for nltk, used in place of the one from
# pyinstaller-hooks-contrib (PyInstaller keeps the first hook registered for a
# module, and `--additional-hooks-dir` folders are read first).
#
# The contrib hook runs `import nltk` at the start of every process of the
# packaged app, which costs over a second of CPU in each multiprocessing worker.
# This hook adds the bundled `nltk_data` folder to `nltk.data.path` only when
# `nltk.data` is first imported.
import importlib.abc
import importlib.util
import os
import sys


class _BundledNltkDataLoader(importlib.abc.Loader):
    def __init__(self, loader):
        self._loader = loader

    def __getattr__(self, name):
        return getattr(self._loader, name)

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        module.path.insert(0, os.path.join(getattr(sys, "_MEIPASS"), "nltk_data"))


class _BundledNltkDataFinder(importlib.abc.MetaPathFinder):
    def __init__(self):
        self._finding = False

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "nltk.data" or self._finding:
            return None
        # The import system iterates sys.meta_path while it calls this method,
        # so the finder stays in the list and skips its own nested lookup.
        self._finding = True
        try:
            spec = importlib.util.find_spec(fullname)
        finally:
            self._finding = False
        if spec is not None and spec.loader is not None:
            spec.loader = _BundledNltkDataLoader(spec.loader)
        return spec


sys.meta_path.insert(0, _BundledNltkDataFinder())
