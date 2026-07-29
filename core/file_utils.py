"""file_utils.py — Industrial grade file operations for ONYX (Claude Code style)."""
import os
import subprocess
import shutil
import winreg
from pathlib import Path


def get_shell_folder(folder_name: str, default: str | None = None) -> str:
    """Obtiene la ruta real de una carpeta especial de Windows desde el registro."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            return winreg.QueryValueEx(key, folder_name)[0]
    except OSError:
        pass
    if default:
        return default
    return str(Path.home() / folder_name)


def get_desktop_path() -> Path:
    """Retorna la ruta real del Escritorio (soporta OneDrive redirection)."""
    return Path(get_shell_folder("Desktop", "Desktop"))


def get_documents_path() -> Path:
    """Retorna la ruta real de Documentos (soporta OneDrive redirection)."""
    return Path(get_shell_folder("Personal", "Documents"))

def force_save_file(file_path: str, save_func, *args, **kwargs) -> str:
    """
    Claude Code style: Force save a file by trying multiple strategies, 
    including elevation if necessary.
    """
    file_path = os.path.abspath(os.path.expanduser(file_path))
    temp_dir = Path("C:/Temp/ONYX_Buffer")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / os.path.basename(file_path)

    try:
        # Strategy 1: Direct Save
        save_func(file_path, *args, **kwargs)
        return f"Archivo guardado exitosamente en: {file_path}"
    except Exception as e:
        print(f"[FORCE_SAVE] Strategy 1 failed: {e}")
        
        try:
            # Strategy 2: Save to Temp then Force Move via PowerShell (Admin-ish)
            save_func(str(temp_file), *args, **kwargs)
            
            # Use PowerShell to force move the file, bypassing standard Python permission blocks
            ps_cmd = f'Move-Item -Path "{temp_file}" -Destination "{file_path}" -Force -ErrorAction Stop'
            subprocess.run(["powershell", "-Command", ps_cmd], check=True, capture_output=True)
            return f"Archivo forzado exitosamente en: {file_path}"
        except Exception as e2:
            print(f"[FORCE_SAVE] Strategy 2 failed: {e2}")
            
            # Strategy 3: Save to Documents as absolute fallback (if Desktop is locked by OneDrive/AV)
            documents_path = get_documents_path() / os.path.basename(file_path)
            try:
                save_func(str(documents_path), *args, **kwargs)
                return f"El sistema bloqueó la ruta original. He asegurado el archivo en su carpeta de Documentos: {documents_path}"
            except Exception as e3:
                return f"Error crítico de sistema: No se pudo escribir en ninguna ruta protegida. {e3}"

def ensure_path_permissions(directory: str):
    """Attempt to grant ONYX permissions to a folder using ICACLS."""
    try:
        subprocess.run(["icacls", directory, "/grant", f"{os.environ['USERNAME']}:(OI)(CI)F", "/T"], capture_output=True)
    except:
        pass
