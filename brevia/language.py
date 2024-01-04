"""Language detection utilities"""
import spacy
from spacy.language import Language
import langcodes
from brevia.settings import get_settings


class Detector():
    """Language detection class"""
    nlp: Language | None = None

    def __init__(self):
        """Init internal nlp"""
        if not get_settings().feature_qa_lang_detect:
            return

        try:
            import spacy_fastlang  # noqa: F401 pylint: disable=import-outside-toplevel

            self.nlp = spacy.load('en_core_web_sm')
            self.nlp.add_pipe('language_detector')

        except Exception as exc:
            raise ImportError(
                "SpaCy `en_core_web_sm` not installed!"
            ) from exc

    def detect(self, phrase: str) -> str:
        """
            Detect language of generic phrase, return an empty string
            if Spacy has not been initialized
        """
        if not self.nlp:
            return ''
        doc = self.nlp(phrase)

        return langcodes.Language.make(language=doc._.language).display_name()
