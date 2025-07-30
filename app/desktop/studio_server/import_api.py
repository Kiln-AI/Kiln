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
    # In order for the dialog to appear on top we: restore app window, bring to front, hide again
    tk_root.deiconify()
    tk_root.lift()
    tk_root.attributes("-topmost", True)
    tk_root.update_idletasks()
    tk_root.focus_force()
    tk_root.withdraw()
    # Allow other windows to be on top again in 10ms
    tk_root.after(10, lambda: tk_root.attributes("-topmost", False))

    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=[("Kiln files", "*.kiln"), ("All files", "*.*")],
    )
    if file_path == "":
        return None
    return file_path
