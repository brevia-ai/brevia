# Use Summarization Services

This comprehensive tutorial delves into the functionalities of two key endpoints for text and file summarization: `/summarize` and `/upload_summarize`.
It provides explanations, examples, and best practices to empower you with a deeper understanding of the summarization process.

## Prerequisites

Ensure you have followed the installation and configuration instructions outlined in the [Setup](../setup.md) and [Configuration](../config.md) documentation. These steps are crucial for establishing the necessary environment and configuration parameters for summarization.

Define the summarization model and parameters using the following JSON snippet as a starting point:

```JSON
SUMMARIZE_LLM='{
    "_type": "openai-chat",
    "model_name": "gpt-3.5-turbo-16k",
    "temperature": 0,
    "max_tokens": 2000
}'
```

```bash
SUMM_TOKEN_SPLITTER=4000
SUMM_TOKEN_OVERLAP=500
SUMM_DEFAULT_CHAIN=stuff
```

 For a deeper understanding of the various configuration options available, refer to the dedicated [Configuration](../config.md) page. This resource provides comprehensive documentation on each parameter and its impact on the summarization process.

## Simple Summarization

The `/summarize` endpoint enables you to summarize any text provided in the request body.

### Payload:

The following JSON payload illustrates the structure of a request to the `/summarize` endpoint:

```JSON
{
  "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum",
  "chain_type": "stuff",
  "token_data": true
}
```

`text`: The text you wish to summarize. This can be any string of text.
`chain_type`: The summarization algorithm to use. Available options include stuff (default), map_reduce, and bart. Refer to the ? page for detailed descriptions of each algorithm.
`token_data`: A boolean value indicating whether to return token-level information in the response.

### Default Prompts:

The system utilizes pre-defined prompts for summarization. These prompts guide the language model in generating a concise and informative summary.

### Custom Prompt Example:

You can also customize the prompts used for summarization.
This example demonstrates using a different summarization algorithm (map_reduce) and a custom prompt:

```JSON
{
  "text": "The Rodrigues night heron (Nycticorax megacephalus) is an extinct species of heron that was endemic to the Mascarene island of Rodrigues in the Indian Ocean. [text was cut]",
  "chain_type": "map_reduce",
  "initial_prompt": {
    "_type": "prompt",
    "input_variables": [
      "text"
    ],
    "template": "Write a concise summary of the following: \"{text}\" CONCISE SUMMARY:"
  },
  "iteration_prompt": {
    "_type": "prompt",
    "input_variables": [
      "text"
    ],
    "template": "Write a final summary of the following: \"{text}\" FINAL SUMMARY:"
  },
  "token_data": true
}
```

Custom prompts offer several advantages:
* Control over summarization style: Tailor the summary to your specific needs and preferences.
* Improved accuracy and relevance: Guide the language model towards generating a more accurate and relevant summary.
* Enhanced transparency: Understand how the summarization process works and the factors influencing the generated summary.

## File Summarization (including PDF with OCR)

The `/upload_summarize` endpoint enables you to summarize files, including PDFs. For image-based PDFs, the unstructured library performs Optical Character Recognition (OCR) before summarization.

### Payload:

Utilize FormData to construct the request payload as shown below:

```JavaScript
const formdata = new FormData();
formdata.append("file", fileInput.files[0], "/path/to/file");
formdata.append("chain_type", "map_reduce");
formdata.append("token_data", "true");
```

This POST request summarizes provided files, including PDFs. For image-based PDFs, the unstructured library performs Optical Character Recognition (OCR) before summarization.

> **Note**: Remember to replace `/path/to/file` with the actual file path.
