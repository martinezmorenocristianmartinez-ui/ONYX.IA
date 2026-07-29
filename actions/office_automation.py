"""office_automation.py — Control en tiempo real de Word y Excel via COM."""

import time
import pythoncom
import win32com.client
import subprocess
import threading


# ── COM inicialización (thread-safe) ──────────────────────────

_WORD_LOCK = threading.Lock()


def _ensure_com():
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass


def _get_word_app(auto_create=True):
    _ensure_com()
    with _WORD_LOCK:
        for _ in range(3):
            try:
                word = win32com.client.GetActiveObject("Word.Application")
                word.Visible = True
                if word.Documents.Count == 0 and auto_create:
                    word.Documents.Add()
                return word
            except Exception:
                time.sleep(1.5)
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        if word.Documents.Count == 0 and auto_create:
            word.Documents.Add()
        return word


def _get_excel_app():
    _ensure_com()
    for _ in range(3):
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
            excel.Visible = True
            if excel.Workbooks.Count == 0:
                excel.Workbooks.Add()
            return excel
        except Exception:
            time.sleep(1.5)
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = True
    if excel.Workbooks.Count == 0:
        excel.Workbooks.Add()
    return excel


# ── SendKeys helper (solo teclas que COM no puede) ────────────────

_SENDKEYS_CACHE = None


def _sendkeys(keys: str):
    global _SENDKEYS_CACHE
    try:
        if _SENDKEYS_CACHE is None:
            _SENDKEYS_CACHE = win32com.client.Dispatch("WScript.Shell")
        _SENDKEYS_CACHE.SendKeys(keys)
    except Exception:
        escaped = keys.replace("'", "''")
        subprocess.run(
            ["powershell", "-Command",
             f"$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('{escaped}')"],
            capture_output=True, timeout=10)


# ───────────────────────────── WORD ─────────────────────────────

def _word_escribir_texto(text: str, limpiar: bool = False):
    try:
        word = _get_word_app(auto_create=False)
        if word.Documents.Count == 0:
            return "No hay documento abierto en Word. El dictado se detiene."
        sel = word.Selection
        if limpiar:
            word.ActiveDocument.Content.Select()
            sel.Delete()
        else:
            try:
                if sel.Start > 0:
                    prev = word.ActiveDocument.Range(sel.Start - 1, sel.Start).Text
                    if prev and not prev.isspace():
                        text = ' ' + text
            except Exception:
                pass
        sel.TypeText(text)
        return f"Texto escrito en Word ({len(text)} caracteres)"
    except Exception as e:
        return _word_escribir_texto_fallback(text, limpiar, str(e))


def _word_escribir_texto_fallback(text: str, limpiar: bool = False, error: str = ""):
    try:
        import pygetwindow as gw
        import pyautogui

        word_wins = [w for w in gw.getAllWindows()
                     if w.title and ('Word' in w.title or 'word' in w.title)]
        if not word_wins:
            return (f"Error COM ({error}) y no se encontró "
                    f"ventana de Word para escribir.")

        win = word_wins[0]
        win.activate()
        time.sleep(0.6)

        if limpiar:
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.press('delete')
            time.sleep(0.3)
        else:
            pyautogui.hotkey('ctrl', 'end')
            time.sleep(0.2)

        pyautogui.write(text, interval=0.005)
        return f"Texto escrito en Word ({len(text)} caracteres) [fallback]"
    except Exception as e2:
        return f"Error al escribir en Word: COM ({error}), fallback ({e2})"


def _word_borrar(cantidad: int = 1):
    """Borra selección o N caracteres hacia atrás usando COM (MoveLeft+Delete)."""
    word = _get_word_app()
    sel = word.Selection
    try:
        if sel.Type == 1:
            sel.Delete()
            return "Texto seleccionado eliminado"
    except Exception:
        pass
    if cantidad > 0:
        sel.MoveLeft(1, cantidad, 1)
        sel.Delete()
    return f"{cantidad} carácter(es) borrado(s)"


def _word_salto_linea():
    _get_word_app().Selection.TypeParagraph()
    return "Salto de línea insertado"


def _word_tecla(tecla: str, veces: int = 1):
    t = tecla.lower()
    word = _get_word_app()
    sel = word.Selection
    if t in ("enter", "intro"):
        for _ in range(veces):
            sel.TypeParagraph()
        return f"Enter x{veces}"
    if t in ("backspace", "borrar"):
        for _ in range(veces):
            sel.MoveLeft(1, 1, 1)
            sel.Delete()
        return f"Backspace x{veces}"
    if t in ("delete", "supr", "suprimir"):
        for _ in range(veces):
            sel.Delete()
        return f"Delete x{veces}"
    if t == "tab":
        for _ in range(veces):
            sel.TypeText("\t")
        return f"Tab x{veces}"
    key_map = {
        "escape": "{ESC}", "esc": "{ESC}",
        "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
        "home": "{HOME}", "end": "{END}",
        "ctrl_c": "^c", "ctrl_v": "^v", "ctrl_x": "^x",
        "ctrl_z": "^z", "ctrl_y": "^y", "ctrl_s": "^s", "ctrl_a": "^a",
    }
    key = key_map.get(t, t)
    if veces > 1 and key.startswith("{"):
        inner = key.strip("{}")
        key = f"{{{{{inner} {veces}}}}}"
    if veces > 1 and not key.startswith("{"):
        for _ in range(veces):
            _sendkeys(key)
    else:
        _sendkeys(key)
    return f"Tecla '{tecla}' enviada"


def _word_mover_cursor(direccion: str, cantidad: int = 1):
    word = _get_word_app()
    sel = word.Selection
    d = direccion.lower()
    if d in ("arriba", "up"):
        sel.MoveUp(5, cantidad)
    elif d in ("abajo", "down"):
        sel.MoveDown(5, cantidad)
    elif d in ("izquierda", "left"):
        sel.MoveLeft(1, cantidad)
    elif d in ("derecha", "right"):
        sel.MoveRight(1, cantidad)
    elif d in ("inicio", "home", "principio"):
        sel.HomeKey(5)
    elif d in ("fin", "end", "final"):
        sel.EndKey(5)
    elif d in ("documento_inicio", "principio_documento"):
        sel.HomeKey(6)
    elif d in ("documento_fin", "final_documento"):
        sel.EndKey(6)
    return f"Cursor movido {direccion} ({cantidad})"


def _word_ir_a(texto: str, despues: bool = False):
    word = _get_word_app()
    rng = word.ActiveDocument.Range(0, 0)
    rng.Find.ClearFormatting()
    if not rng.Find.Execute(texto):
        return f"No se encontró '{texto}'"
    rng.Select()
    if despues:
        word.Selection.MoveRight(1, len(texto))
    return f"Cursor en '{texto}'"


def _word_seleccionar(texto: str):
    word = _get_word_app()
    rng = word.ActiveDocument.Range(0, 0)
    rng.Find.ClearFormatting()
    if not rng.Find.Execute(texto):
        return f"No se encontró '{texto}'"
    rng.Select()
    return f"'{texto}' seleccionado"


def _word_insertar_tabla(headers: list, rows: list):
    word = _get_word_app()
    sel = word.Selection
    ncols, nrows = len(headers), len(rows) + 1
    table = sel.Tables.Add(sel.Range, nrows, ncols)
    table.Style = "Tabla con cuadrícula"
    for i, h in enumerate(headers):
        cell = table.Cell(1, i + 1)
        cell.Range.Text = str(h)
        cell.Range.Font.Bold = True
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            table.Cell(r + 2, c + 1).Range.Text = str(val)
    return f"Tabla {nrows}x{ncols} insertada"


def _word_formato_texto(bold=None, italic=None, size=None, color=None,
                        font_name=None, underline=None):
    sel = _get_word_app().Selection
    if bold is not None: sel.Font.Bold = bold
    if italic is not None: sel.Font.Italic = italic
    if size: sel.Font.Size = size
    if color: sel.Font.Color = color
    if font_name: sel.Font.Name = font_name
    if underline is not None: sel.Font.Underline = underline
    return "Formato aplicado"


def _word_formato_parrafo(alineacion=None, interlineado=None,
                          espacio_antes=None, espacio_despues=None):
    pf = _get_word_app().Selection.ParagraphFormat
    if alineacion:
        pf.Alignment = {"izquierda": 0, "centro": 1,
                        "derecha": 2, "justificado": 3}.get(alineacion, 0)
    if interlineado: pf.LineSpacing = interlineado
    if espacio_antes is not None: pf.SpaceBefore = espacio_antes
    if espacio_despues is not None: pf.SpaceAfter = espacio_despues
    return "Formato de párrafo aplicado"


def _word_insertar_lista(items: list, numerada: bool = False):
    sel = _get_word_app().Selection
    for i, item in enumerate(items):
        sel.TypeText(f"{(i+1) if numerada else '-'} {item}")
        sel.TypeParagraph()
    return f"Lista de {len(items)} items"


def _word_buscar_reemplazar(buscar: str, reemplazar: str):
    _get_word_app().ActiveDocument.Content.Find.Execute(
        buscar, ReplaceWith=reemplazar, Replace=2)
    return f"'{buscar}' remplazado por '{reemplazar}'"


def _word_agregar_titulo(texto: str, nivel: int = 1):
    word = _get_word_app()
    sel = word.Selection
    try:
        sel.Style = word.ActiveDocument.Styles(f"Heading {nivel}")
    except Exception:
        sel.Font.Bold = True
        sel.Font.Size = max(12, 28 - nivel * 4)
    sel.TypeText(texto)
    sel.TypeParagraph()
    return f"Título nivel {nivel} agregado"


def _word_insertar_imagen(ruta: str):
    _get_word_app().ActiveDocument.InlineShapes.AddPicture(ruta)
    return f"Imagen insertada: {ruta}"


def _word_configurar_pagina(margen_superior=None, margen_inferior=None,
                            margen_izquierdo=None, margen_derecho=None,
                            orientacion=None):
    ps = _get_word_app().ActiveDocument.PageSetup
    if margen_superior: ps.TopMargin = margen_superior
    if margen_inferior: ps.BottomMargin = margen_inferior
    if margen_izquierdo: ps.LeftMargin = margen_izquierdo
    if margen_derecho: ps.RightMargin = margen_derecho
    if orientacion:
        ps.Orientation = 0 if orientacion == "vertical" else 1
    return "Página configurada"


# ───────────────────────────── EXCEL ─────────────────────────────

def _excel_escribir_celda(cell: str, value):
    _get_excel_app().ActiveSheet.Range(cell).Value = value
    return f"Celda {cell} = {value}"


def _excel_escribir_rango(cell: str, data: list):
    sheet = _get_excel_app().ActiveSheet
    sheet.Range(cell).Resize(len(data), len(data[0])).Value = data
    return f"Rango {cell} ({len(data)} filas)"


def _excel_escribir_encabezados(headers: list):
    sheet = _get_excel_app().ActiveSheet
    for i, h in enumerate(headers):
        c = sheet.Cells(1, i + 1)
        c.Value = h
        c.Font.Bold = True
    return f"Encabezados: {len(headers)} columnas"


def _excel_auto_ajustar():
    _get_excel_app().ActiveSheet.Cells.EntireColumn.AutoFit()
    return "Columnas autoajustadas"


def _excel_ancho_columna(columna: str, ancho: int):
    _get_excel_app().ActiveSheet.Range(columna).ColumnWidth = ancho
    return f"Ancho {columna} = {ancho}"


def _excel_formula(cell: str, formula: str):
    _get_excel_app().ActiveSheet.Range(cell).Formula = formula
    return f"Fórmula en {cell}"


def _excel_escribir_texto(text: str):
    sheet = _get_excel_app().ActiveSheet
    for r, line in enumerate(text.strip().split("\n")):
        for c, val in enumerate(line.split("\t")):
            sheet.Cells(r + 1, c + 1).Value = val.strip()
    return "Texto escrito en Excel"


def _excel_formato_celda(rango: str, bold=None, italic=None, size=None,
                         color=None, fill=None):
    rng = _get_excel_app().ActiveSheet.Range(rango)
    if bold is not None: rng.Font.Bold = bold
    if italic is not None: rng.Font.Italic = italic
    if size: rng.Font.Size = size
    if color: rng.Font.Color = color
    if fill: rng.Interior.Color = fill
    return f"Formato en {rango}"


def _excel_combinar_celdas(rango: str):
    _get_excel_app().ActiveSheet.Range(rango).Merge()
    return f"{rango} combinado"


def _excel_insertar_fila(fila: int):
    _get_excel_app().ActiveSheet.Rows(fila).Insert()
    return f"Fila {fila} insertada"


def _excel_insertar_columna(columna: str):
    _get_excel_app().ActiveSheet.Range(columna).EntireColumn.Insert()
    return f"Columna {columna} insertada"


def _excel_eliminar_fila(fila: int):
    _get_excel_app().ActiveSheet.Rows(fila).Delete()
    return f"Fila {fila} eliminada"


def _excel_eliminar_columna(columna: str):
    _get_excel_app().ActiveSheet.Range(columna).EntireColumn.Delete()
    return f"Columna {columna} eliminada"


def _excel_ordenar(rango: str, columna: int, descendente: bool = False):
    excel = _get_excel_app()
    excel.ActiveSheet.Range(rango).Sort(
        Key1=excel.ActiveSheet.Columns(columna),
        Order1=-1 if descendente else 1, Header=1)
    return f"Rango {rango} ordenado"


def _excel_filtro(rango: str):
    _get_excel_app().ActiveSheet.Range(rango).AutoFilter(1)
    return f"Filtro en {rango}"


def _excel_crear_grafico(tipo: str = "columnas", rango_datos: str = "",
                         titulo: str = ""):
    excel = _get_excel_app()
    chart = excel.Charts.Add()
    if rango_datos:
        chart.SetSourceData(excel.ActiveSheet.Range(rango_datos))
    chart.ChartType = {"columnas": 51, "barras": 57, "lineas": 65,
                       "pastel": 5, "areas": 1}.get(tipo, 51)
    if titulo:
        chart.HasTitle = True
        chart.ChartTitle.Text = titulo
    return f"Grafico {tipo} creado"


# ───────────────────────────── ACTION MAPS ─────────────────────────────

WORD_ACTIONS = {
    "escribir_texto": lambda p: _word_escribir_texto(
        p.get("text", ""), p.get("limpiar", False)),
    "borrar": lambda p: _word_borrar(p.get("cantidad", 1)),
    "salto_linea": lambda p: _word_salto_linea(),
    "tecla": lambda p: _word_tecla(p.get("tecla", ""), p.get("veces", 1)),
    "mover_cursor": lambda p: _word_mover_cursor(
        p.get("direccion", ""), p.get("cantidad", 1)),
    "ir_a": lambda p: _word_ir_a(
        p.get("texto", ""), p.get("despues", False)),
    "seleccionar": lambda p: _word_seleccionar(p.get("texto", "")),
    "insertar_tabla": lambda p: _word_insertar_tabla(
        p.get("headers", []), p.get("rows", [])),
    "formato_texto": lambda p: _word_formato_texto(
        p.get("bold"), p.get("italic"), p.get("size"),
        p.get("color"), p.get("font_name"), p.get("underline")),
    "formato_parrafo": lambda p: _word_formato_parrafo(
        p.get("alineacion"), p.get("interlineado"),
        p.get("espacio_antes"), p.get("espacio_despues")),
    "insertar_lista": lambda p: _word_insertar_lista(
        p.get("items", []), p.get("numerada", False)),
    "buscar_reemplazar": lambda p: _word_buscar_reemplazar(
        p.get("text", ""), p.get("reemplazo", "")),
    "agregar_titulo": lambda p: _word_agregar_titulo(
        p.get("text", ""), p.get("nivel", 1)),
    "insertar_imagen": lambda p: _word_insertar_imagen(p.get("ruta", "")),
    "configurar_pagina": lambda p: _word_configurar_pagina(
        p.get("margen_superior"), p.get("margen_inferior"),
        p.get("margen_izquierdo"), p.get("margen_derecho"),
        p.get("orientacion")),
}

EXCEL_ACTIONS = {
    "escribir_celda": lambda p: _excel_escribir_celda(
        p.get("cell", "A1"), p.get("value", "")),
    "escribir_rango": lambda p: _excel_escribir_rango(
        p.get("cell", "A1"), p.get("data", [])),
    "escribir_encabezados": lambda p: _excel_escribir_encabezados(
        p.get("headers", [])),
    "escribir_texto": lambda p: _excel_escribir_texto(p.get("text", "")),
    "auto_ajustar": lambda p: _excel_auto_ajustar(),
    "ancho_columna": lambda p: _excel_ancho_columna(
        p.get("columna", ""), p.get("ancho", 10)),
    "agregar_formula": lambda p: _excel_formula(
        p.get("cell", "A1"), p.get("formula", "")),
    "formato_celda": lambda p: _excel_formato_celda(
        p.get("rango", "A1"), p.get("bold"), p.get("italic"),
        p.get("size"), p.get("color"), p.get("fill")),
    "combinar_celdas": lambda p: _excel_combinar_celdas(p.get("rango", "")),
    "insertar_fila": lambda p: _excel_insertar_fila(p.get("fila", 1)),
    "insertar_columna": lambda p: _excel_insertar_columna(p.get("columna", "A")),
    "eliminar_fila": lambda p: _excel_eliminar_fila(p.get("fila", 1)),
    "eliminar_columna": lambda p: _excel_eliminar_columna(p.get("columna", "A")),
    "ordenar": lambda p: _excel_ordenar(
        p.get("rango", ""), p.get("columna", 1), p.get("descendente", False)),
    "filtro": lambda p: _excel_filtro(p.get("rango", "")),
    "crear_grafico": lambda p: _excel_crear_grafico(
        p.get("tipo", "columnas"), p.get("rango_datos", ""), p.get("titulo", "")),
}


def office_automation(parameters: dict, player=None) -> str:
    app = parameters.get("app", "").lower()
    action = parameters.get("action", "")

    if app == "word":
        fn = WORD_ACTIONS.get(action)
        if fn:
            try:
                return fn(parameters)
            except Exception as e:
                return f"Error en Word: {e}"
        return (f"Accion '{action}' no reconocida. "
                f"Word: {', '.join(WORD_ACTIONS.keys())}")

    if app == "excel":
        fn = EXCEL_ACTIONS.get(action)
        if fn:
            try:
                return fn(parameters)
            except Exception as e:
                return f"Error en Excel: {e}"
        return (f"Accion '{action}' no reconocida. "
                f"Excel: {', '.join(EXCEL_ACTIONS.keys())}")

    return "Usa app='word' o app='excel'"
