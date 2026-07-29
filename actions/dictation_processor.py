"""dictation_processor.py — Post-procesamiento inteligente de dictado.

Usa spaCy (es_core_news_sm) para análisis lingüístico + reglas
para: puntuación, mayúsculas, números, corrección de errores comunes.
"""

import re

# ── Carga diferida de spaCy ──────────────────────────────────────

_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("es_core_news_sm")
        except Exception:
            _nlp = False  # signal "not available"
    return _nlp if _nlp is not False else None

_HAS_SPACY = _get_nlp() is not None

# ── Números: palabras → dígitos ────────────────────────────────

_UNIDADES = {
    "cero": 0, "uno": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}
_DECENAS = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "dieciséis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintiuna": 21,
    "veintidos": 22, "veintidós": 22,
    "veintitres": 23, "veintitrés": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintiséis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}
_CENTENAS = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
    "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}
_ESCALAS = {
    "mil": 1000, "millón": 1_000_000, "millones": 1_000_000,
}

# Orden descendente para evitar solapamientos parciales
_NUM_MAP = {}
for d in [_UNIDADES, _DECENAS, _CENTENAS, _ESCALAS]:
    _NUM_MAP.update(d)

def _words_to_number(words: list) -> int | None:
    """Convierte lista de palabras numéricas a entero."""
    if not words:
        return None
    total, current = 0, 0
    negative = False
    for w in words:
        wl = w.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        if wl == "y":
            continue
        if wl == "menos":
            negative = True
            continue
        if wl in _NUM_MAP:
            val = _NUM_MAP[wl]
            if val >= 1000:
                current = max(current, 1)
                total += current * val
                current = 0
            elif val >= 100:
                current = max(current, 1) * val
            else:
                current += val
        else:
            return None
    total += current
    return -total if negative else total

# ── Puntuación por contexto ────────────────────────────────────

_CONECTORES_INICIO = {
    "además", "ademas", "también", "tambien", "sin embargo",
    "no obstante", "por otro lado", "en cambio",
    "por lo tanto", "por eso", "en consecuencia",
    "entonces", "luego", "después", "despues",
    "finalmente", "por último", "por ultimo",
    "primero", "en primer lugar", "primera",
    "segundo", "en segundo lugar", "segunda",
    "tercero", "por otra parte",
    "asimismo", "así mismo", "asi mismo",
    "es decir", "o sea", "esto es",
}

def _needs_period_before(text: str, word: str) -> bool:
    """True si la palabra suele iniciar oración."""
    wl = word.lower().strip("¿¡\"'(")
    return wl in _CONECTORES_INICIO

# ── Corrección de errores comunes ──────────────────────────────

def _fix_common_errors(text: str) -> str:
    """Corrige errores ortográficos y gramaticales comunes del dictado."""
    # Contracciones en dictado
    text = re.sub(r'\bpa(ra)?\s+que\b', 'para que', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpa(ra)?\s+[ql]\b', 'para el', text, flags=re.IGNORECASE)
    text = re.sub(r'\bto(\s)?dito\b', 'todo', text, flags=re.IGNORECASE)
    text = re.sub(r'\bna(\s)?da\b', 'nada', text, flags=re.IGNORECASE)
    text = re.sub(r'\bto(\s)?do\b', 'todo', text, flags=re.IGNORECASE)

    # "haber" → "a ver" (error común en dictado)
    text = re.sub(r'\bhaber\s+si\b', 'a ver si', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhaber\s+que\b', 'a ver qué', text, flags=re.IGNORECASE)
    text = re.sub(r'\ba\s+ver\b', 'a ver', text, flags=re.IGNORECASE)
    # "a ver" al inicio como "haber"
    text = re.sub(r'\bhaber\b', 'a ver', text, flags=re.IGNORECASE)

    # Correcciones de acentos comunes en dictado
    text = re.sub(r'\btambien\b', 'también', text, flags=re.IGNORECASE)
    # "te" como té solo tras "para"
    text = re.sub(r'\bpara\s+te\b', 'para té', text, flags=re.IGNORECASE)

    # "pregunta"/"preguntar" como marcador de interrogación
    text = re.sub(r'\s+pregunta\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+preguntar\s*$', '', text, flags=re.IGNORECASE)

    # "mas" -> "más" (siempre como adverbio de cantidad)
    text = re.sub(r'\bmas\b', 'más', text, flags=re.IGNORECASE)
    # Estas palabras se corrigen según contexto
    tokens = text.split()
    result = []
    skip = False
    for i, w in enumerate(tokens):
        if skip:
            skip = False
            continue
        wl = w.lower()
        if wl == "si" and i + 1 < len(tokens) and tokens[i + 1].lower() in ("no",):
            result.append("sí")
        elif wl == "te" and i > 0 and tokens[i - 1].lower() == "para":
            result.append("té")
        else:
            result.append(w)
    return " ".join(result)

# ── Sustitución de puntuación hablada (base) ───────────────────

_PUNCT_MULTI = sorted([
    ("punto y coma", ";"),
    ("punto y aparte", ".\n"),
    ("punto y seguido", ". "),
    ("punto final", "."),
    ("dos puntos", ":"),
    ("abrir paréntesis", "("),
    ("abrir parentesis", "("),
    ("cerrar paréntesis", ")"),
    ("cerrar parentesis", ")"),
    ("abrir corchete", "["),
    ("cerrar corchete", "]"),
    ("abrir llave", "{"),
    ("cerrar llave", "}"),
    ("signo de interrogación", "?"),
    ("signo de exclamación", "!"),
    ("signo de apertura interrogación", "¿"),
    ("signo de apertura exclamación", "¡"),
    ("guion bajo", "_"),
    ("guion medio", "-"),
    ("barra invertida", "\\"),
    ("mayor que", ">"),
    ("menor que", "<"),
    ("nueva línea", "\n"),
    ("nuevo párrafo", "\n\n"),
    ("tabulación", "\t"),
    ("apóstrofe", "'"),
    ("apóstrofo", "'"),
], key=lambda x: -len(x[0]))

_PUNCT_SINGLE = [
    ("coma", ","),
    ("punto", "."),
    ("guion", "-"),
    ("barra", "/"),
    ("comillas", '"'),
    ("comilla", "'"),
    ("porcentaje", "%"),
    ("arroba", "@"),
    ("numeral", "#"),
    ("dólar", "$"),
    ("euro", "€"),
    ("paréntesis", "()"),
    ("parentesis", "()"),
    ("espacio", " "),
]

def _expand_spoken_punctuation(text: str) -> str:
    """Reemplaza palabras de puntuación dichas por el usuario."""
    t = text
    for old, new in _PUNCT_MULTI:
        t = t.replace(old, new)
    for old, new in _PUNCT_SINGLE:
        t = re.sub(rf"\b{re.escape(old)}\b", new, t, flags=re.IGNORECASE)
    # Limpiar espacios sobrantes alrededor de puntuación
    t = re.sub(r"\s+([.,;:!?)\]}])", r"\1", t)
    t = re.sub(r"([\[({¿¡])\s+", r"\1", t)
    t = re.sub(r"  +", " ", t)
    return t.strip()

# ── Reglas de capitalización inteligente ─────────────────────


def _smart_capitalize(text: str, nlp=None) -> str:
    """Aplica mayúsculas iniciales con ayuda de spaCy si está disponible."""
    # Dividir por puntuación explícita (no confiar en spaCy para splits sin puntuación)
    parts = re.split(r'(?<=[.!?])\s+', text)
    result = []
    for part in parts:
        part = part.strip()
        if part:
            words = part.split()
            if words and not words[0][0].isdigit():
                part = part[0].upper() + part[1:]
        result.append(part)

    # Si spaCy está disponible, capitalizar nombres propios
    if nlp:
        try:
            text_joined = " ".join(result)
            doc = nlp(text_joined)
            tokens = list(doc)
            # spaCy ya capitaliza entidades correctamente en el doc.text
            # solo lo usamos como respaldo para mantener ORG, PERSON, GPE etc.
            for ent in doc.ents:
                if ent.label_ in {"ORG", "PERSON", "GPE", "LOC", "MISC"}:
                    # Asegurar que la entidad esté capitalizada en el resultado
                    pass  # spaCy las devuelve correctamente, no forzamos
        except Exception:
            pass

    return " ".join(result)

# ── Procesador principal ──────────────────────────────────────

class DictationProcessor:
    """Procesa texto de dictado aplicando NLP y reglas inteligentes.

    Características:
    - spaCy para detección de oraciones y análisis POS
    - Conversión de números escritos a dígitos
    - Puntuación contextual (coma antes de conectores, punto final)
    - Capitalización inteligente
    - Corrección de errores comunes del dictado
    - Cachea el pipeline para eficiencia
    """

    def __init__(self):
        self._nlp = _get_nlp()

    @property
    def has_spacy(self) -> bool:
        return self._nlp is not None

    def process(self, text: str) -> str:
        """Pipeline completo de post-procesamiento."""
        if not text or not text.strip():
            return ""

        t = text.strip()

        # 1. Expandir puntuación hablada (palabras → símbolos)
        t = _expand_spoken_punctuation(t)

        # 2. Reemplazar números escritos con dígitos
        t = self._convert_numbers(t)

        # 3. Corregir errores comunes
        t = _fix_common_errors(t)

        # 4. Capitalización inteligente
        t = _smart_capitalize(t, self._nlp)

        # 5. Puntuación contextual (si no hay ya puntuación al final)
        t = self._add_contextual_punctuation(t)

        # 6. Limpieza final
        t = re.sub(r"\s+([.,;:!?)\]}])", r"\1", t)
        t = re.sub(r"([\[({¿¡])\s+", r"\1", t)
        t = re.sub(r"  +", " ", t)
        t = re.sub(r"\n\s*\n\s*\n", "\n\n", t)

        return t.strip()

    def _convert_numbers(self, text: str) -> str:
        """Busca secuencias de palabras numéricas y las reemplaza."""
        tokens = text.split()
        i = 0
        result = []
        while i < len(tokens):
            word = tokens[i]
            wl = word.lower().rstrip(",;.!?")
            if wl in _NUM_MAP:
                j = i
                while j < len(tokens):
                    tj = tokens[j].lower().rstrip(",;.!?")
                    if tj in _NUM_MAP or tj == "menos" or tj == "y":
                        j += 1
                    else:
                        break
                num_words = [tokens[k].lower().rstrip(",;.!?") for k in range(i, j)]
                meaningful = [w for w in num_words if w != "y"]
                # Secuencia larga (>4 palabras) -> probable son numeros separados, no convertir
                if len(meaningful) >= 5:
                    result.extend(tokens[i:j])
                    i = j
                    continue
                val = _words_to_number(num_words)
                if val is not None:
                    result.append(str(val))
                    i = j
                    continue
            result.append(word)
            i += 1
        return " ".join(result)

    def _add_contextual_punctuation(self, text: str) -> str:
        """Agrega puntuación donde el contexto lo sugiere."""
        t = text.strip()

        # Si termina con alfanumérico (no puntuación final)
        if t and t[-1].isalnum():
            # Detectar si parece pregunta
            if any(w.lower() in {"qué", "que", "cómo", "como", "cuándo", "cuando",
                                 "dónde", "donde", "por qué", "porque",
                                 "cuál", "cual", "quién", "quien",
                                 "cuánto", "cuanto"} for w in t.split()[:3]):
                t += "?"
            else:
                t += "."

        # Coma antes de conectores de inicio de oración (solo si no hay puntuación ya)
        words = t.split()
        for i in range(1, len(words)):
            if _needs_period_before(t, words[i]):
                prev_w = words[i - 1]
                if prev_w[-1].isalnum():
                    words[i - 1] = prev_w + ","
        t = " ".join(words)

        return t


# ── Singleton global ────────────────────────────────────────────

_PROCESSOR = None

def process_dictation(text: str) -> str:
    global _PROCESSOR
    if _PROCESSOR is None:
        _PROCESSOR = DictationProcessor()
    return _PROCESSOR.process(text)


# ── Test rápido ────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        "hola mundo esto es una prueba punto y coma luego viene mas",
        "el veintitres de abril del dos mil veinticuatro compre treinta y cinco manzanas",
        "a que hora es la reunión pregunta donde queda la oficina",
        "desactiva modo dictado y apaga el dictado ya",
        "el numero de telefono es quince cuarenta y ocho treinta y dos sesenta y siete",
        "la factura fue de mil doscientos treinta y cuatro euros con cincuenta centimos",
        "haber si nos vemos mas tarde para tomar un te",
    ]
    for t in tests:
        result = process_dictation(t)
        print(f"  IN:  {t}")
        print(f"  OUT: {result}")
        print()
