"""Language detection utilities"""
import spacy
from spacy.language import Language
import langcodes


class Detector():
    """Language detection class"""
    nlp: Language

    def __init__(self):
        """Init internal nlp"""
        try:
            import spacy_fastlang  # noqa: F401 pylint: disable=import-outside-toplevel

            self.nlp = spacy.load('en_core_web_sm')
            self.nlp.add_pipe('language_detector')

        except ImportError as exc:
            raise ImportError(
                "SpaCy `en_core_web_sm` not installed!"
            ) from exc

    def detect(self, phrase: str) -> str:
        """Detect language of generic phrase"""
        doc = self.nlp(phrase)

        return langcodes.Language.make(language=doc._.language).display_name()
