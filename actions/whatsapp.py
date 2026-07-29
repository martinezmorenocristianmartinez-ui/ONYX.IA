import time
import urllib.parse
import json
import atexit
from pathlib import Path

try:
    import pyautogui
except ImportError:
    pyautogui = None

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
CONTACTS_FILE = BASE_DIR / "config" / "whatsapp_contacts.json"
WHATSAPP_PROFILE = BASE_DIR / "whatsapp_profile"

def _playwright_channel():
    """Map preferred browser to playwright channel."""
    try:
        from actions._browser_launch import _load_pref
        pref = _load_pref()
        if pref in ("edge", "microsoft edge"):
            return "msedge"
        if pref in ("firefox",):
            return "firefox"
    except Exception:
        pass
    return "chrome"

_playwright = None
_context = None
_page = None

def _ensure_page():
    global _playwright, _context, _page
    if _context is None:
        _playwright = sync_playwright().start()
        _context = _playwright.chromium.launch_persistent_context(
            user_data_dir=str(WHATSAPP_PROFILE),
            channel=_playwright_channel(),
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"]
        )
        _page = _context.pages[0] if _context.pages else _context.new_page()
    else:
        try:
            alive = _page and not _page.is_closed()
        except Exception:
            alive = False
        if not alive:
            _page = _context.pages[0] if _context.pages else _context.new_page()
    return _page

@atexit.register
def _cleanup():
    global _playwright, _context, _page
    try:
        if _context:
            _context.close()
    except Exception:
        pass
    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass

def load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        try:
            return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_contacts(contacts: dict):
    try:
        CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTACTS_FILE.write_text(json.dumps(contacts, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WhatsApp] Error saving contacts: {e}")

def whatsapp(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower()
    receiver = parameters.get("receiver", "")
    message = parameters.get("message", "")
    image_path = parameters.get("image_path", "")
    caption = parameters.get("caption", "")
    name = parameters.get("name", "")
    phone_param = parameters.get("phone", "")

    contacts = load_contacts()

    if action == "send_text":
        action = "send"
    elif action in ["read_unread", "read_chat"]:
        action = "read"
    elif action == "unread":
        action = "read"

    # --- 1. CONTACT MANAGEMENT ---
    if action == "add_contact":
        contact_name = name or receiver
        contact_phone = phone_param
        if not contact_name or not contact_phone:
            return "Error: Para agregar un contacto se requiere el nombre ('name') y el teléfono ('phone')."
        contact_phone = "".join(filter(str.isdigit, contact_phone))
        contacts[contact_name.lower()] = {
            "name": contact_name,
            "phone": contact_phone
        }
        save_contacts(contacts)
        return f"Contacto '{contact_name}' guardado exitosamente con el teléfono: {contact_phone}."

    elif action == "delete_contact":
        contact_name = name or receiver
        if not contact_name:
            return "Error: Para eliminar un contacto se requiere especificar el nombre ('name')."
        if contact_name.lower() in contacts:
            del contacts[contact_name.lower()]
            save_contacts(contacts)
            return f"Contacto '{contact_name}' eliminado de la base de datos de ONYX."
        return f"No se encontró ningún contacto con el nombre '{contact_name}'."

    elif action == "list_contacts":
        if not contacts:
            return "No tienes contactos guardados en la base de datos de ONYX todavía."
        res = "Contactos guardados en ONYX:\n"
        for k, v in contacts.items():
            res += f"• {v['name']}: {v['phone']}\n"
        return res

    # --- 2. SEND / READ VIA PLAYWRIGHT ---
    elif action in ["send", "send_image", "read"]:
        if action in ["send", "send_image"] and not receiver:
            return "Error: No se especificó el destinatario ('receiver')."

        phone = ""
        contact_name = ""

        if action in ["send", "send_image"]:
            cleaned_receiver = "".join(c for c in receiver if c.isdigit() or c == '+')
            digit_count = sum(c.isdigit() for c in cleaned_receiver)

            if digit_count >= 8:
                phone = cleaned_receiver.replace("+", "")
            else:
                match = contacts.get(receiver.lower())
                if match:
                    phone = match["phone"]
                    contact_name = match["name"]
                else:
                    for k, v in contacts.items():
                        if receiver.lower() in k or k in receiver.lower():
                            phone = v["phone"]
                            contact_name = v["name"]
                            break

        target_desc = contact_name if contact_name else receiver
        page = _ensure_page()

        try:
            if action == "read":
                page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
                if player:
                    player.write_log("💬 Abriendo WhatsApp Web...")
                return "Abriendo la bandeja de chats de WhatsApp Web."

            if player:
                player.write_log(f"💬 Enviando mensaje a {target_desc}...")

            encoded_msg = urllib.parse.quote(message)
            if phone:
                url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
            else:
                url = f"https://web.whatsapp.com/send?text={encoded_msg}"

            page.goto(url, wait_until="domcontentloaded")
            time.sleep(3)

            msg_box = page.wait_for_selector(
                'div[contenteditable="true"][role="textbox"]',
                timeout=35000
            )
            if not msg_box:
                return f"No se pudo cargar el chat de WhatsApp para '{target_desc}'. ¿Escaneaste el código QR?"

            time.sleep(1)

            if action == "send_image" and image_path:
                img_path = Path(image_path)
                if not img_path.exists():
                    page.keyboard.press("Enter")
                    time.sleep(0.5)
                    return f"Mensaje de texto enviado, pero no se encontró la imagen en: {image_path}"

                attach_btn = page.query_selector('div[title="Attach"], button[aria-label="Attach"]')
                if attach_btn:
                    attach_btn.click()
                    time.sleep(0.8)
                    file_input = page.query_selector('input[accept*="image"]')
                    if file_input:
                        file_input.set_input_files(str(img_path.absolute()))
                        time.sleep(3)
                        if caption:
                            page.keyboard.type(caption, delay=15)
                            time.sleep(0.5)
                        send_btn = page.query_selector('span[data-icon="send"], button[aria-label="Send"]')
                        if send_btn:
                            send_btn.click()
                        else:
                            page.keyboard.press("Enter")
                        time.sleep(1)
                        return f"Mensaje e imagen enviados exitosamente a '{target_desc}' vía WhatsApp Web."
                    else:
                        page.keyboard.press("Enter")
                        time.sleep(0.5)
                        return f"Mensaje de texto enviado a '{target_desc}'. No se pudo adjuntar la imagen."
                else:
                    page.keyboard.press("Enter")
                    time.sleep(0.5)
                    return f"Mensaje de texto enviado a '{target_desc}'. No se pudo adjuntar la imagen."

            page.keyboard.press("Enter")
            time.sleep(1)
            return f"Mensaje enviado exitosamente a '{target_desc}' vía WhatsApp Web."

        except Exception as e:
            return f"Error al enviar mensaje a '{target_desc}': {e}"

    else:
        page = _ensure_page()
        page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
        return f"Acción '{action}' ejecutada cargando WhatsApp Web."
