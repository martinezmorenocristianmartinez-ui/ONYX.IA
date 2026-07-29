import os
import re
from pathlib import Path

def replace_in_file(file_path, old_str, new_str):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Reemplazamos case-sensitive y case-insensitive
        new_content = content.replace(old_str, new_str)
        # Reemplazamos "Onyx" también
        new_content = new_content.replace(old_str.title(), new_str.title())
        # Reemplazamos "onyx"
        new_content = new_content.replace(old_str.lower(), new_str.lower())
        
        if content != new_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Actualizado: {file_path}")
    except Exception as e:
        print(f"Error al procesar {file_path}: {e}")

def main():
    base_dir = Path(__file__).parent
    old_name = "ONYX"
    new_name = "ONYX"
    
    # Archivos a procesar
    extensions = ['.py', '.txt', '.md', '.json']
    
    for root, dirs, files in os.walk(base_dir):
        # Saltamos directorios de virtualenv
        if '.venv' in root:
            continue
        if '__pycache__' in root:
            continue
            
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = Path(root) / file
                replace_in_file(file_path, old_name, new_name)
    
    print("¡Reemplazo completado!")

if __name__ == "__main__":
    main()
