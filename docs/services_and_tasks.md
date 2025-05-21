# Services and Tasks in Brevia

This document explains the concepts of Services and Tasks in Brevia, how they are implemented, and how they can be used and customized.

## Services

Services in Brevia are high-level components responsible for handling incoming requests, processing them, and returning results. They act as an orchestration layer, often utilizing Tasks to perform specific operations.

### `BaseService`

All services in Brevia should inherit from the `brevia.services.BaseService` abstract class. This class provides a common structure for services.

The key methods of `BaseService` are:

*   **`run(self, payload: dict) -> dict`**: This is the main entry point for a service. It first calls the `validate` method to check the input `payload`. If validation is successful, it calls the `execute` method to perform the service logic. It returns a dictionary containing the result.
*   **`validate(self, payload: dict) -> bool`**: This abstract method must be implemented by concrete service classes. It's responsible for validating the input `payload` to ensure it contains all necessary data in the correct format. It should return `True` if the payload is valid, and `False` otherwise.
*   **`execute(self, payload: dict) -> dict`**: This abstract method must be implemented by concrete service classes. It contains the core logic of the service. This is where the service might interact with Tasks, databases, or other components to produce a result. It returns a dictionary containing the output of the service.

### Creating a Custom Service

To create a custom service, you need to:

1.  Define a new class that inherits from `BaseService`.
2.  Implement the `validate` method to define how the input payload should be checked.
3.  Implement the `execute` method to define the service's core logic.

#### Example of a Custom Service

Here's a simple example of a custom service that takes a name in its payload and returns a greeting:

```python
from brevia.services import BaseService

class GreetingService(BaseService):
    """A simple service that returns a greeting."""

    def validate(self, payload: dict) -> bool:
        """Validate that the payload contains a 'name'."""
        if 'name' not in payload:
            print("Validation failed: 'name' is missing from payload.")
            return False
        if not isinstance(payload['name'], str):
            print("Validation failed: 'name' must be a string.")
            return False
        return True

    def execute(self, payload: dict) -> dict:
        """Execute the service logic to return a greeting."""
        name = payload['name']
        greeting = f"Hello, {name}!"
        return {"greeting": greeting}

# Example usage (typically, a service like this would be called by an API endpoint):
# if __name__ == "__main__":
#     service = GreetingService()
#     valid_payload = {"name": "World"}
#     invalid_payload_type = {"name": 123}
#     invalid_payload_missing = {}

#     print(f"Running with valid payload: {valid_payload}")
#     result = service.run(valid_payload)
#     print(f"Result: {result}") # Output: {'greeting': 'Hello, World!'}

#     print(f"Running with invalid payload (type error): {invalid_payload_type}")
#     try:
#         service.run(invalid_payload_type)
#     except ValueError as e:
#         print(f"Error: {e}") # This will not be caught here as validate prints and returns False
                               # The run method would raise a ValueError if validate returns False

#     print(f"Running with invalid payload (missing key): {invalid_payload_missing}")
#     try:
#         service.run(invalid_payload_missing)
#     except ValueError as e:
#         print(f"Error: {e}") # Similar to above
```

In a typical Brevia application, services are often invoked by API endpoints (e.g., using FastAPI) which handle the HTTP requests and responses. The service's `run` method would be called with the request data as the payload.

## Tasks

Tasks in Brevia encapsulate the actual logic for performing specific operations, especially those involving data processing, interactions with machine learning models (like those from LangChain), or other detailed computations. Services delegate work to Tasks.

### `BaseAnalysisTask`

Many tasks, especially those performing some form of analysis, inherit from `brevia.tasks.base.BaseAnalysisTask`. This abstract class provides a basic structure for such tasks.

The key methods of `BaseAnalysisTask` are:

*   **`perform_task(self) -> dict`**: This abstract method must be implemented by concrete task classes. It contains the core logic of the task, such as processing input data, interacting with LLMs, and generating results. It returns a dictionary containing the task's output.
*   **`load_analysis_prompts(self, prompts: dict | None = None)`**: This abstract method is responsible for loading and configuring the prompts that the task will use, often from dictionaries or YAML files. The structure of the `prompts` dictionary can vary based on the task's needs.

Brevia also provides more specialized base tasks, like `brevia.tasks.text_analysis.BaseTextAnalysisTask`, which can be a more suitable parent for tasks specifically dealing with text. `BaseTextAnalysisTask`, for instance, includes a `text_documents` method to help load and split text into documents.

### Interaction with LangChain

Tasks are often the place where Brevia integrates with LangChain. A task might:
*   Load LangChain LLMs (e.g., using `brevia.models.load_chatmodel`).
*   Define or load LangChain prompt templates.
*   Construct and run LangChain chains (e.g., `load_summarize_chain`, custom `LLMChain` instances, or `SequentialChain`).
*   Process the inputs for and outputs from these chains.

### Creating a Custom Task

To create a custom task, you generally need to:

1.  Define a new class that inherits from `BaseAnalysisTask` or another suitable base task class (e.g., `BaseTextAnalysisTask`).
2.  Implement the `load_analysis_prompts` method if your task uses configurable prompts.
3.  Implement the `perform_task` method to define the task's core logic. This might involve initializing models, preparing data, running chains, and formatting the output.

#### Example of a Custom Task

Here's a conceptual example of a custom task that processes some text. (Note: This is a simplified example. Real tasks often involve more complex setup, especially when using LLMs.)

```python
from brevia.tasks.base import BaseAnalysisTask
from brevia.models import load_chatmodel # For a more complex task
from langchain_core.prompts import PromptTemplate
from langchain.chains.llm import LLMChain

# Assume a simple prompt for this example
DEFAULT_PROMPT_TEMPLATE = "Analyze the following text: {text_input}. What is its main topic?"

class SimpleTextAnalysisTask(BaseAnalysisTask):
    """A simple task to analyze a piece of text."""

    def __init__(self, text: str, custom_prompt_template: str | None = None):
        self.text = text
        self.prompts = {} # Initialize prompts dictionary
        self.load_analysis_prompts({"custom_template": custom_prompt_template})
        # In a real scenario, LLM would be initialized here or in perform_task
        # For simplicity, we'll use a placeholder for LLM interaction
        # settings = get_settings()
        # self.llm = load_chatmodel(settings.llm_model_config)


    def load_analysis_prompts(self, prompts_input: dict | None = None):
        """Load analysis prompts.
        For this task, it expects a 'custom_template' in the prompts_input dict.
        """
        if prompts_input and prompts_input.get("custom_template"):
            self.prompts["analysis_prompt"] = PromptTemplate.from_template(
                prompts_input["custom_template"]
            )
        else:
            self.prompts["analysis_prompt"] = PromptTemplate.from_template(
                DEFAULT_PROMPT_TEMPLATE
            )

    def perform_task(self) -> dict:
        """Perform the text analysis."""
        # In a real task, you would use an LLM and the loaded prompt
        # For example:
        # llm_chain = LLMChain(llm=self.llm, prompt=self.prompts["analysis_prompt"])
        # result = llm_chain.run(text_input=self.text)

        # Simplified mock logic for this example:
        if "topic" in self.text.lower():
            analysis_result = "The text discusses a specific topic."
        else:
            analysis_result = "The text is general."

        return {
            "input_text": self.text,
            "analysis": analysis_result,
            "prompt_template_used": self.prompts["analysis_prompt"].template
        }

# Example usage:
# if __name__ == "__main__":
#     task1 = SimpleTextAnalysisTask(text="This text is about an important topic.")
#     result1 = task1.perform_task()
#     print(f"Result 1: {result1}")
#     # Output: Result 1: {'input_text': 'This text is about an important topic.', 'analysis': 'The text discusses a specific topic.', 'prompt_template_used': 'Analyze the following text: {text_input}. What is its main topic?'}

#     custom_prompt = "What is the sentiment of this text: {text_input}?"
#     task2 = SimpleTextAnalysisTask(text="I love Brevia!", custom_prompt_template=custom_prompt)
#     result2 = task2.perform_task()
#     print(f"Result 2: {result2}")
#     # Output: Result 2: {'input_text': 'I love Brevia!', 'analysis': 'The text is general.', 'prompt_template_used': 'What is the sentiment of this text: {text_input}?'}
```

This example demonstrates the basic structure. Real-world tasks in Brevia, like `SummarizeTextAnalysisTask` or `RefineTextAnalysisTask` (in `brevia.tasks.text_analysis`), show more complex interactions with LangChain, document splitting, and prompt management.

## Relationship between Services and Tasks

Services and Tasks work together in Brevia to process requests and generate results. The relationship is hierarchical:

*   **Services are the entry points**: They receive external requests (e.g., from an API call).
*   **Services validate input**: They use their `validate` method to check the incoming payload.
*   **Services delegate to Tasks**: The core logic is often delegated to one or more Tasks. A Service's `execute` method will typically:
    1.  Instantiate the required Task(s), passing any necessary data from the payload or configuration.
    2.  Call the Task's `perform_task` method.
    3.  Process the result from the Task, if needed, and return the final output.

### Typical Workflow

1.  An external client (e.g., a web UI, another application) makes a request to a Brevia API endpoint.
2.  The API endpoint handler calls the `run` method of the appropriate Service, passing the request data as the payload.
3.  The Service's `run` method calls its `validate` method.
    *   If validation fails, the `run` method raises a `ValueError`.
4.  If validation succeeds, the Service's `run` method calls its `execute` method.
5.  Inside the `execute` method:
    *   The Service instantiates a specific Task class (e.g., `SummarizeTextAnalysisTask`). It might pass configuration details, text input, or prompt information from its own payload to the Task's constructor.
    *   The Service calls the `perform_task` method on the Task instance.
    *   The Task executes its logic (e.g., loads data, interacts with LangChain, processes text).
    *   The Task returns a result dictionary to the Service.
6.  The Service's `execute` method receives the Task's result, potentially formats it or adds more information, and returns its own result dictionary.
7.  This result is then typically converted into an HTTP response by the API endpoint.

This separation of concerns makes the system modular:
*   **Services** handle the "how" of being called (API interaction, basic validation).
*   **Tasks** handle the "what" of the actual work (detailed processing, model interaction).

## Usage and Customization

Brevia's Service and Task architecture is designed to be extensible.

### Creating Custom Services and Tasks

As shown in the examples above, you can create your own services by inheriting from `BaseService` and your own tasks by inheriting from `BaseAnalysisTask` or other specialized base tasks like `BaseTextAnalysisTask`.

For a detailed walkthrough of creating a custom service that performs a specific analysis, including how to structure the analysis logic (which would be part of a custom task), refer to the tutorial:
*   **[Create Custom Services Tutorial](./tutorials/create_custom_services.md)**

This tutorial covers defining a service, implementing its analysis logic (akin to a task), handling file inputs, and integrating with LangChain components.

### Customizing Prompts

A key aspect of customizing tasks, especially those involving Large Language Models, is the ability to define and use custom prompts.

Tasks typically load their prompts in the `load_analysis_prompts` method. Brevia supports loading prompts from YAML files (using `brevia.prompts.load_prompt_from_yaml`) or directly from dictionary configurations (e.g., using `langchain_core.prompts.loading.load_prompt_from_config` for LangChain prompts).

When you create a custom task, you can define its expected prompt structure and implement `load_analysis_prompts` to load them. When a Service uses your custom task, it can pass the required prompt configurations to the task's constructor.

Refer to the specific task's documentation or implementation (e.g., `SummarizeTextAnalysisTask`) to see how it expects prompts to be structured and provided. The `docs/prompt_management.md` guide also provides more general information on how prompts are handled in Brevia.
