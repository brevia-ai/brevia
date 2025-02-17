""" This module contains functions and classes related to handling prompts."""

from os import path
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
    load_prompt,
)
from langchain_core.prompts.loading import load_prompt_from_config


# system = load_prompt(f'{prompts_path}/qa/default.system.yaml')
# jinja2 template from file was disabled by langchain so, for now
# we load from here
SYSTEM_TEMPLATE = """
                As an AI assistant your task is to provide valuable
                information and support to our users. Answer the question
                as truthfully as possible using the provided context
                between ##Context start## and ##Context end##.
                If the answer is not contained within the provided context,
                say that you are sorry but that you cannot answer
                to that question. Don't try to make up an answer.
                ##Context start## {{context}} ##Context end##
                Answer in {% if lang|length %}{{ lang }}{% else %}
                the same language of the question{% endif %}
                """


def load_qa_prompt(prompts: dict | None) -> ChatPromptTemplate:
    """
        load prompt for RAG-Q/A functions, following openIA system/human/ai pattern:
        SYSTEM_TEMPLATE: is a jinja2 template with language checking from api call.
                         For security reason, the default is loaded from here and
                         overwritten from api call.
        HUMAN_TEMPLATE:  is a normal template, loaded from /prompts/qa and overwritten
                         by api call

    """

    prompts_path = f'{path.dirname(__file__)}/prompts'
    system = PromptTemplate.from_template(SYSTEM_TEMPLATE, template_format="jinja2")
    human = load_prompt(f'{prompts_path}/qa/default.human.yaml')

    if prompts:
        if prompts.get('system'):
            system = load_prompt_from_config(prompts.get('system'))
        if prompts.get('human'):
            human = load_prompt_from_config(prompts.get('human'))

    system_message_prompt = SystemMessagePromptTemplate(prompt=system)
    human_message_prompt = HumanMessagePromptTemplate(prompt=human)

    return ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )


def load_condense_prompt(prompts: dict | None):
    """
        Check if specific few-shot prompt file exists for the collection, if not,
        check for condense prompt file, otherwise, load default condense prompt file.
        few-shot can improve condensing the chat history especially when the chat
        history is about eterogenous topics.
    """
    if prompts and prompts.get('_type'):
        return load_prompt_from_config(prompts)

    prompts_path = f'{path.dirname(__file__)}/prompts'

    return load_prompt(f'{prompts_path}/qa/default.condense.yaml')
