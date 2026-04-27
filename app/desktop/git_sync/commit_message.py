def generate_commit_message(file_count: int, context: str) -> str:
    if file_count == 1:
        files_str = "1 file changed"
    else:
        files_str = f"{file_count} files changed"

    return f"[Kiln] Auto-sync: {files_str}\n\nContext: {context}"
