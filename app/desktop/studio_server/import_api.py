import asyncio
import tkinter as tk
from tkinter import filedialog

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class KilnFileResponse(BaseModel):
    file_path: str | None


def connect_import_api(app: FastAPI, tk_root: tk.Tk | None = None):
    @app.get("/api/select_kiln_file")
    async def select_kiln_file(title: str = "Select Kiln File") -> KilnFileResponse:
        if tk_root is None:
            raise HTTPException(
                status_code=400,
                detail="Not running in app mode. Enter the Kiln file path manually.",
            )

        # Run the blocking file dialog in a thread pool to not block FastAPI
        file_path = await asyncio.to_thread(_show_file_dialog, tk_root, title)
        return KilnFileResponse(file_path=file_path)


def _show_file_dialog(tk_root: tk.Tk, title: str) -> str | None:
    """Run the blocking tkinter operations in a separate thread"""
    try:
        # In order for the dialog to appear on top we: restore app window, bring to front, hide if after the dialog is closed
        tk_root.deiconify()

        # Place the window in a reasonable place on the screen. Note: We don't know the size of the picker window so can't perfectly center it.
        screen_width = tk_root.winfo_screenwidth()
        screen_height = tk_root.winfo_screenheight()
        x = (screen_width) // 3  # 1/3 of the way across the screen
        y = (screen_height) // 3  # 1/3 of the way down the screen

        # Position the window. Size doesn't matter as it's covered by the dialog.
        tk_root.geometry(f"300x150+{x}+{y}")

        # Bring the window to front, and keep it on top until the dialog is closed
        tk_root.lift()
        tk_root.attributes("-topmost", True)
        tk_root.update_idletasks()
        tk_root.focus_force()

        file_path = filedialog.askopenfilename(
            # Windows needs a parent window to be on top, so we'll do the same for all platforms.
            parent=tk_root,
            title=title,
            filetypes=[("Kiln files", "*.kiln"), ("All files", "*.*")],
        )

        if file_path == "":
            return None
        return file_path
    finally:
        # Allow other windows to be on top again
        tk_root.attributes("-topmost", False)

        # hide the parent window after the dialog is closed
        tk_root.withdraw()
