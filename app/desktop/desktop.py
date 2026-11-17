# Entry script of the desktop app, and the file pyinstaller builds from.
#
# Every multiprocessing child of the packaged app (code evals, code tools, PDF
# conversion) runs this script first, and `freeze_support()` hands the child
# its job and exits. Anything imported above that call is loaded again in each
# child, so keep this file to the stdlib and import the app inside `__main__`.
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    from app.desktop.desktop_main import main

    main()
