You are extracting data from a long document one part at a time, following the output
schema. The data extracted from the parts read so far, as JSON, is:

{previous}

The user gives the next part of the document. Return all the data updated with it:
keep every item and value already found, change a value only when the new part
corrects or completes it, and add the new items it contains.
Use only information written in the document; never guess.
Copy names, numbers, amounts and dates exactly as they are written.
