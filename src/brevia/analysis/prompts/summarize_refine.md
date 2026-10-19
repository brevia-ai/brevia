You are summarising a long document one part at a time, in {language}.
The summary of the parts read so far, as a JSON object with a "summary" field, is:

{previous}

The user gives the next part of the document. Return the summary updated with it.
Keep the main facts, the figures, and the open points or uncertainties of every part,
and keep the summary about as long as one summary: condense, do not append.
Do not add information that is not in the document.
Write plain text in short paragraphs.
