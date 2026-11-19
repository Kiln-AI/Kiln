# PyInstaller runtime hook for nltk, used in place of the one from
# pyinstaller-hooks-contrib (PyInstaller keeps the first hook registered for a
# module, and `--additional-hooks-dir` folders are read first).
#
# The contrib hook runs `import nltk` at the start of every process of the
# packaged app, which costs over a second of CPU in each multiprocessing worker.
# This hook adds the bundled `nltk_data` folder to `nltk.data.path` only when
# `nltk.data` is first imported.
#
# The build log says "Runtime hooks for nltk have already been defined.
# Skipping the runtime hooks for nltk that are defined in
# .../_pyinstaller_hooks_contrib/rthooks". That warning is expected: it is this
# override taking effect.
import importlib.abc
import os
import sys


class _BundledNltkDataLoader(importlib.abc.Loader):
    def __init__(self, loader):
        self._loader = loader

    def __getattr__(self, name):
        # Forward the other loader methods (get_source, get_filename, ...). A
        # copy or an unpickle looks up attributes before `_loader` is set.
        if name == "_loader":
            raise AttributeError(name)
        return getattr(self._loader, name)

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        module.path.insert(0, os.path.join(getattr(sys, "_MEIPASS"), "nltk_data"))


class _BundledNltkDataFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "nltk.data":
            return None
        # Ask the other finders, as the import system would, and wrap the loader
        # of the spec they find.
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                if spec.loader is not None:
                    spec.loader = _BundledNltkDataLoader(spec.loader)
                return spec
        return None


sys.meta_path.insert(0, _BundledNltkDataFinder())
