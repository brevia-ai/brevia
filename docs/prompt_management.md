# Prompt Management

This section provides a detailed explanation of the different prompt types used in Brevia.

## Conversational Chat Prompts for RAG Systems

The prompts in the prompts/rag directory offer specialized configurations for efficient retrieval-augmented generation, ensuring streamlined query handling and precise system responses.

- **Human Prompt:**
    This prompt type is designed to handle user queries. It accepts a single variable ("question") and formats it in a straightforward manner suitable for a conversational AI. When queries are processed through a Retrieval-Augmented Generation (RAG) system, the Human prompt is responsible for capturing the user's input as is.

- **System Prompt:**
    The System prompt is specialized for generating context-aware responses. It requires additional input variables (such as "context" and "lang") and is used to produce answers that reference explicit sources from the provided context. This ensures that the assistant responds accurately within the constraints of the given document segments.

## Memory Management Prompts

These mechanisms ensure the dialogue remains coherent and contextually relevant throughout the interaction.

- **Condense Prompt (Default):**
    The condense prompt plays a crucial role in managing the dialogue history. It formats the conversation and the follow-up question into a standalone query, thereby condensing previous interactions into a succinct context. If specific prompt names (e.g., few_shot) are not used during configuration, the system automatically falls back to the condense prompt as the default for memory management.

- **Few Shot Prompt:**
    This prompt type includes a set of predefined examples that guide the assistant in reformatting or rephrasing questions. It employs examples to illustrate the desired transformation from a conversational sentence to a clear, standalone question. However, if explicit naming is not applied for memory-related interactions, the default behavior reverts to using the condense prompt instead of the few shot configuration.

This split ensures that the system handles both direct conversational interactions (via the Human and System prompts) and more complex memory management tasks (via the condense or few shot prompts) with clarity and consistency. You have to specify either a `condense` or a `few_shot` prompt. In case both prompts are present the `few_shot` prompt will be used.

Below is an example configuration with a **condense** prompt:

```json
{
    "condense": {
        "_type": "prompt",
        "input_variables": [
            "chat_history",
            "question"
        ],
        "template": "You are an AI assistant. Your task is to provide valuable information and support to users. Given the following conversation and a follow-up question, rephrase the follow-up question as a standalone question. Write in the same language as the follow-up question.\nconversation:\n\n{chat_history}\n\nfollow-up question: {question}\n\nStandalone question:"
    },
    "human": {
        "_type": "prompt",
        "input_variables": [
            "question"
        ],
        "template": "Question: {question}\n"
    },
    "system": {
        "_type": "prompt",
        "input_variables": [
            "context",
            "lang"
        ],
        "template": "You are an AI assistant. You are provided with extracted parts of a document along with a question. Provide a conversational answer using only the sources explicitly listed in the context. If the question does not relate to the provided content, state that you are limited to addressing the given information. If you do not know the answer, simply indicate that you don't know.\n\n=========\n{context}\n=========\n\nAnswer in {lang}:"
    }
}
```

Below another example with a **few_shot** prompt:

```json
{
    "few_shot": {
        "_type": "few_shot",
        "input_variables": [
            "chat_history",
            "question"
        ],
        "prefix": "You are an AI assistant. Your task is to provide valuable information and support to users. Given the following conversation and a sentence, if the sentence is a question, rephrase it as a standalone question. If not, repeat the sentence without modification. Write in the same language as the sentence.\n",
        "example_prompt": {
            "_type": "prompt",
            "input_variables": [
                "chat_history",
                "fquestion",
                "squestion"
            ],
            "template": "\nconversation:\n\n{chat_history}\n\nsentence: {fquestion}\n\nquestion: {squestion}\n"
        },
        "examples": [
            {
                "chat_history": "User: hello\nAssistant: Hello! How can I help you today?\n",
                "fquestion": "how are you?",
                "squestion": "how are you?"
            },
            {
                "chat_history": "User: hello\nAssistant: Hello! How can I help you today?\n",
                "fquestion": "what can you do?",
                "squestion": "what functions do you have?"
            }
        ],
        "suffix": "conversation:\n\n{chat_history}\n\nsentence: {question}\n\nquestion:"
    },
    "human": {
        "_type": "prompt",
        "input_variables": [
            "question"
        ],
        "template": "Question: {question}\n"
    },
    "system": {
        "_type": "prompt",
        "input_variables": [
            "context",
            "lang"
        ],
        "template": "You are an AI assistant. You are provided with extracted parts of a document along with a question. Provide a conversational answer using only the sources explicitly listed in the context. If the question does not relate to the provided content, state that you are limited to addressing the given information. If you do not know the answer, simply indicate that you don't know.\n\n=========\n{context}\n=========\n\nAnswer in {lang}:"
    }
}
```

## Text Analysis Prompts

You can define a folder with prompts in YAML format for text analysis tasks.
This folder can be configured in `settings.prompts_base_path`.
You can then use the relative paths of these prompt files in the `prompts` field of the analysis task configuration.
For instance you can configure `RefineTextAnalysisService` with the following configuration, specifying relative paths:

```json
{
    "prompts": {
        "initial_prompt": "text_analysis/initial_prompt.yml",
        "refine_prompt": "text_analysis/refine_prompt.yml"
    }
}
```

Alternatively you can use the `prompts` field in the analysis task configuration to specify the prompt directly in the task configuratio, like this:

```json
{
    "prompts": {
        "initial_prompt": {
            "_type": "prompt",
            "input_variables": [
                "text"
            ],
            "template": "Analyze the following text and generate 1-2 multiple choice questions, each with four options (A, B, C, D), of which only one is correct. Highlight the correct answer and make sure that the questions are relevant and understandable.\n\nReference text:\n-------------------\n{text}"
        },
        "refine_prompt": {
            "_type": "prompt",
            "input_variables": [
                "existing_answer",
                "text"
            ],
            "template": "You are given the following partial document containing a list of multiple choice questions:\nPartial Document:\n-------------------\n{existing_answer}\n-------------------\nRewrite the list of questions by adding 1-2 more questions at the bottom from the context provided below:\n-------------\n{text}\n-------------------"
        }
    }
}
```

As a reference you can find some prompts in the `prompts/text_analysis` directory. designed to assist with generating and refining questions based on provided text. These prompts ensure that the questions are relevant, understandable, and contextually accurate.
