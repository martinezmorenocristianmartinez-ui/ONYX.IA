class Router:

    def should_use_cloud(self, text: str, has_session: bool) -> bool:
        if not has_session:
            return False
        if text.startswith("[AUDIO_FILE]"):
            return False
        return True
