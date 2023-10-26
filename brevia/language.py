"""Language detection utilities"""
from os import environ
from typing import Any
import langcodes


class Detector():
    """Language detection class"""
    detector: Any = None

    def __init__(self):
        """Init internal nlp"""
        if not bool(environ.get('FEATURE_QA_LANG_DETECT')):
            return

        try:
            import gcld3  # noqa: F401 pylint: disable=import-outside-toplevel

            self.detector = gcld3.NNetLanguageIdentifier(min_num_bytes=0, max_num_bytes=1000)

        except Exception as exc:
            raise ImportError(
                "gcld3 not installed!"
            ) from exc

    def detect(self, phrase: str) -> str:
        """
            Detect language of generic phrase, return an empty string
            if `gcld3` detector has not been initialized
        """
        if not self.detector:
            return ''
        result = self.detector.FindLanguage(text=phrase)

        return langcodes.Language.make(language=result.language).display_name()
