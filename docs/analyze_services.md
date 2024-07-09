# Analysis Services

This module leverages the BREVIA library for performing text summarization and document analysis using Large Language Models (LLMs) and LangChain library.
BREVIA provides a robust framework for managing and customizing the summarization process, making it easier to integrate and utilize LangChain's capabilities.

## Summarize

The `summarize` function is the core of the summarization service, it takes a text input and generates a summary using one of the main LangChain summarization chains: "stuff", "map_reduce", or "refine". BREVIA allows for seamless customization of prompts and efficient management of the summarization workflow.

### Key Functions

- **`summarize`**: This function performs the summarization of a given text, orchestrated by BREVIA. It supports different summarization chains and allows for custom prompts.
  - **Args**:
    - `text` (str): The input text to be summarized.
    - `chain_type` (str | None): The type of summarization chain to use. Options are "stuff", "map_reduce", and "refine". Defaults to "stuff" if not provided.
    - `initial_prompt` (dict | None): Optional custom prompt for the initial summarization.
    - `iteration_prompt` (dict | None): Optional custom prompt for iterative summarization.
  - **Returns**: `str`: The generated summary of the input text.
  - **Raises**: `ValueError`: If an unsupported summarization chain type is specified.

### Supporting Functions

- **`load_stuff_prompts`**: Loads custom prompts for the "stuff" summarization chain, facilitated by BREVIA.
- **`load_map_prompts`**: Loads custom prompts for the "map_reduce" summarization chain, utilizing BREVIA's configuration management.
- **`load_refine_prompts`**: Loads custom prompts for the "refine" summarization chain, orchestrated by BREVIA.
- **`get_summarize_llm`**: Retrieves the language model configured for summarization, managed by BREVIA.

### Key Components

- **`TokenTextSplitter`**: This utility, managed by BREVIA, is used to split the input text into manageable chunks based on token size. It ensures that the text is divided appropriately for the summarization process.
  - **Args**:
    - `chunk_size` (int): The size of each text chunk.
    - `chunk_overlap` (int): The overlap between consecutive text chunks.

## Generic Service

The module provides a generic service for text summarization that can be customized and extended based on specific needs. BREVIA's orchestration capabilities make the summarization process flexible, allowing for different algorithms and custom prompts to be used seamlessly.

### Key Components

- **`load_prompt_from_config`**: Loads prompts from a configuration, enabling customization of the summarization process through BREVIA.
- **`LoggingCallbackHandler`**: A callback handler provided by BREVIA for logging the summarization process, useful for debugging and monitoring.
- **`load_chatmodel`**: Loads the chat model based on the provided configuration, ensuring that the appropriate LLM is used for summarization, managed by BREVIA.
- **`get_settings`**: Retrieves the settings for the summarization process, including model configuration, verbosity, and token splitting parameters, all orchestrated by BREVIA.

### Example Usage

```python
from your_module import summarize

text = "Your input text here."
summary = summarize(
    text=text,
    chain_type="map_reduce",
    initial_prompt={"prompt": "Your initial prompt here."},
    iteration_prompt={"prompt": "Your iteration prompt here."}
)

print(summary)
```

This example demonstrates how to use the `summarize` function with custom prompts and the "map_reduce" summarization chain. BREVIA orchestrates the entire process, from loading the appropriate prompts to managing the LangChain summarization workflow, resulting in an efficient and customizable summarization service.
