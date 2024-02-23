# Chat, Search and Chat History

This section explores the advanced chat functionalities that enable natural and intuitive interaction with the configured language model.

Brevia provides two distinct endpoints for managing conversations:

`/chat`: This endpoint is designed to initiate fluid and natural conversations with the language model. It integrates a conversational memory and chat history system, allowing you to build on previous interactions and create a more engaging experience.

`/completion`: This endpoint is ideal for executing single commands and requests. It provides quick and concise responses without the need for conversational context, making it perfect for launching specific tasks or obtaining immediate information.

Both the `/chat` and `/completion` endpoints offer predefined prompts, but these can be customized to meet specific requirements.
Customization can be done either internally within the library or by specifying custom prompts in the body of the API requests.

In addition to chat functionalities, Brevia provides out of the box dedicated endpoints for managing search and conversation history:

`/search`: This endpoint allows you to retrieve relevant documents based on a query, without generating a response.

`/chat_history`: This endpoint allows you to access and manage conversation history data, providing valuable insights into past interactions.

## Configuration

The following environment variables control the behavior of the chat system:

`QA_COMPLETION_LLM`: Configuration for the main conversational model.

`QA_FOLLOWUP_LLM`: Configuration for the follow-up question model.

`QA_FOLLOWUP_SIM_THRESHOLD`: Similarity threshold between questions to determine if chat history should be used.

`QA_NO_CHAT_HISTORY`: Disables chat history entirely.

`SEARCH_DOCS_NUM`: Number of documents used to search for answers.

example:

```bash
QA_COMPLETION_LLM='{"_type": "openai-chat", "model_name": "gpt-3.5-turbo-16k", "temperature": 0, "max_tokens": 1000, "verbose": true}'
QA_FOLLOWUP_LLM='{"_type": "openai-chat", "model_name": "gpt-3.5-turbo-16k", "temperature": 0, "max_tokens": 200, "verbose": true}'
QA_FOLLOWUP_SIM_THRESHOLD=0.735
SEARCH_DOCS_NUM=4
```

see [configuration](config.md) for more info

## Chat System Functionality

The chat system is at the core of the BrevIA library, providing a conversational interface for interacting with the underlying RAG model. It builds upon the foundation of LangChain and expands it with essential features to ensure a seamless user experience.

### Key Features

**Conversational Memory**: Chat history is integrated, enabling context-aware conversations. From the second question onwards, a dedicated model can rephrase the query based on the chat history, creating a conversational memory that allows for a smooth flow of information without the need for constant repetition.

**Adaptive Follow-up Questions**: The `QA_FOLLOWUP_LLM` parameter allows you to configure a separate model for rephrasing questions based on chat history. This ensures that follow-up questions are relevant and coherent with the conversation context.

**Automatic Language Detection**: The chat system automatically detects the language of the incoming question and responds in the same language, facilitating communication across different languages. Or you can simply force a single language in the body of every chat request.

In addition to the features mentioned above, the chat system also provides:

**Similarity Threshold**: The `QA_FOLLOWUP_SIM_THRESHOLD` parameter defines a similarity threshold for determining when to use the chat history. If the similarity between the current and previous questions falls below this threshold, the chat history is not used, avoiding irrelevant or confusing responses.


**Customizable Similarity Algorithm**: The `distance_strategy_name` parameter in the search endpoint allows you to specify the algorithm used for measuring vector similarity. The default algorithm is "`cosine`", but you can choose from a variety of other options to suit your specific needs.

**Support for multiple prompts**: You can define different prompts for the chat system, allowing you to customize the way it responds to different types of questions.

## Endpoints

### POST `/chat`

Initiates a natural conversation with the model.

**Payloads**:

`question`: The query you want to ask the model.
`collection`: The collection of documents to search for relevant information.

```JSON
{
  "question": "{{query}}",
  "collection": "{{collection}}"
}
```

Same as the simple body, plus:
`chat_history`: An array of previous questions and answers to provide context for the current query.

```JSON
{
    "question": "{{query}}",
    "collection": "{{collection}}",
    "chat_history": [
        {
            "query": "what is artificial intelligence?",
            "answer": "Artificial intelligence (AI) refers to the simulation or approximation of human intelligence in machines. The goals of artificial intelligence include computer-enhanced learning, reasoning, and perception"
        },
        {
            "query": "Is AI good or bad?",
            "answer": "These technologies not only save time, but also potentially save lives by minimizing human error and ensuring a safer working environment. In addition, automating repetitive tasks in design, planning, and management with AI frees up human workers to focus on more complex and creative aspects."
        }
    ]
}
```

### POST `/completion`

Executes a single command or request without conversational context.

**Paylodas**:

`text`: The text you want to process or transform.
`prompt`: A custom instruction defining how to process the text.
`token_data`: (Optional) Set to true to return token-level data like part-of-speech tags.

```JSON
{
    "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum",
    "prompt": {
        "_type": "prompt",
        "input_variables": [
            "text"
        ],
        "template": "formatta il seguente testo in formato EMAIL :\n\n{text}\n\n SCRIVI L'EMAIL:"
    },
    "token_data": true
}
```

### GET `/chat_history`

### GET `/chat_history?max_date=2023-04-20&collection={{collection}}&page=1&page_size=20`

Retrieves past conversation history.

**Optional Parameters**:

`max_date`: Filter history entries by date.
`collection`: Filter history entries by collection.
`page`: Paginate through large history datasets.
`page_size`: Control the number of entries per page.

### POST `/search`

Searches for relevant documents based on a query.

Payloads:

`query`: The search query.
`collection`: The collection of documents to search.

```JSON
{
    "query": "{{query}}",
    "collection": "{{collection}}"
}
```

**Additional Parameters**:

`docs_num`: Specify the number of documents to return.
`distance_strategy_name`: Choose the algorithm for measuring document similarity.

```JSON
{
    "query": "{{query}}",
    "collection": "{{collection}}",
    "docs_num": 6,
    "distance_strategy_name": "euclidean"
}
```
