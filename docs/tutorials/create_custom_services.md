# Use and create Servieces

This tutorial provides how to build a service using the BREVIA and LangChain libraries in Python. We will walk through the creation of a service class, setting up chains for analysis, and exposing the functionality through a FastAPI endpoint.

## Introduction

Brevia is a powerful library designed to simplify the creation of external services by integrating with pre-built chains from LangChain. This tutorial will walk you through building a service that performs text analysis on documents, leveraging LangChain's prompt templates and chain configurations.

## Prerequisites

Ensure you have followed the installation and configuration instructions outlined in the [Setup](../setup.md) and [Configuration](../config.md) documentation. These steps are crucial for establishing the necessary environment and configuration parameters for summarization.

## Setting Up the Service

We will start by defining our main service class using Brevia.

### Define the Service Class

Create a file named service.py and add the following code:

```Python
from brevia.services import BaseService
from analysis import do_analysis

class AnalysisService(BaseService):
    """Perform text analysis"""
    def execute(self, payload: dict):
        """Service logic"""
        prompts = payload.get('prompts', {})
        if prompts is None:
            prompts = {}

        return do_analysis(
            file_path=payload.get('file_path'),
            prompts=prompts,
        )

    def validate(self, payload: dict):
        """Payload validation"""
        if not payload.get('file_path'):
            return False
        return True
```

The AnalysisService class is designed to perform a specific type of text analysis.

This class inherits from `BaseService`, indicating that it follows a standardized service structure provided by the Brevia library implementing the `execute` methods that takes a payload dictionary as input, which contains various parameters required for the analysis.

### Extracting Prompts

The method first attempts to extract prompts from the payload. If the payload does not contain any prompts, it initializes prompts as an empty dictionary. This ensures that the method has a valid dictionary to work with, even if no prompts are provided.

```python
prompts = payload.get('prompts', {})
if prompts is None:
    prompts = {}
```

### Calling do_analysis

The core functionality is delegated to the `do_analysis` function. This function is called with three key parameters extracted from the payload:

`file_path`: The path to the file that needs to be analyzed.
`prompts`: The prompts used to guide the analysis.

```python
return do_analysis(
    file_path=payload.get('file_path'),
    prompts=prompts)
)
```

It is also possible to implement the input validation function, in this case, to validate the `file_path`.

## Perform the Analysis

The `do_analysis` function is responsible for conducting the main analysis task.

```python
from brevia import load_file
from brevia.callback import LoggingCallbackHandler

def do_analysis(file_path: str, prompts: dict) -> dict:
"""Analysis task"""

[...]

text = load_file.read(file_path=file_path, **LOAD_PDF_OPTIONS)
pages = load_splitter().split_documents([Document(page_content=text)])

output = run_chain(pages, prompts)

result = {
    'input_documents': [{
            'page_content': doc.page_content,
            'metadata': doc.metadata
        } for doc in pages
    ],
    'output': output,
    'document_url': file_path
}

return result
```

It can reads the text content using `load_file.read` and then splits the text into smaller documents using the load_splitter function.

The function then calls the `run_chain` function, passing the loaded pages and prompts to it. This function processes the documents and returns the analysis results.

The function constructs a result dictionary containing the original input documents, the formatted output, and the file path of document.

## Running the chain

The run_chain function is responsible for running a sequence of analysis steps (chains) on the provided documents

```python
from brevia.models import load_chatmodel
from langchain.chains.summarize import load_summarize_chain

def run_chain(pages: list[Document], prompts: dict) -> dict[str, str]:
    """Run anlysis chain"""
    prompts = load_analysis_prompts(prompts)
    logging_handler = LoggingCallbackHandler()
    llm_text = load_chatmodel({
        '_type': 'openai-chat',
        'model_name': 'gpt-4o',
        'temperature': 0.0,
        'callbacks': [logging_handler],
    })

    chain_1 = load_summarize_chain(
        llm_text,
        chain_type="refine",
        question_prompt=prompts.get('summarize_prompt'),
        refine_prompt=prompts.get('refine_prompt'),
        output_key="input",
    )

    chain_2 = LLMChain(
        llm=llm_text,
        prompt=prompts.get('prompt_2'),
        output_key="output_2",
        callbacks=[logging_handler],
    )

    overall_chain = SequentialChain(
        chains=[
            chain_1,
            chain_2,
        ],
        input_variables=["input_documents"],
        output_variables=[
            "input", "output_2"
        ],
        # verbose=True,
    )

    return overall_chain({'input_documents': pages})
```

In this example, we can see how it is possible to chain multiple chains together using the power of LangChain and the versatility of Brevia.

First, a chat model is created using Brevia's `load_chatmodel`, which allows for creating a model with just a few parameters.

The model is then used in two chains. The first chain is directly taken from LangChain, the summarization chain, to which two custom prompts are passed to perform the two steps of the summarization `refine` algorithm.

A second fully custom chain is created with personalized prompts and outputs, and finally, the two chains are combined to be executed in sequence.

## Expose by FASTApi

Finally, we can expose our method via API using the FastAPI library integrated into Brevia.

```python
from brevia.routers.app_routers import add_routers
from brevia.dependencies import get_dependencies

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)
add_routers(app)

@app.get('/myapi/analysis/{file_name}')
def analysis_file(file_name: str):
    """ Analyze text file"""
    service = AnalysisService()

    ## get the file path and custom prompts
    return service.run()

```

Simply, we can create a new route and then launch the service, perhaps after loading the custom prompts (locally within the application or remotely)
