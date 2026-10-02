import json
import re
from typing import Type, TypeVar
from pydantic import BaseModel
from langchain_openai import ChatOpenAI        # OpenAI and compatible APIs
from langchain_core.messages import SystemMessage, HumanMessage

from config import MAIN_AGENT_MODEL, CODE_AGENT_MODEL, API_KEY, API_ENDPOINT

T = TypeVar('T', bound=BaseModel)

def get_llm(model: str, temperature: float = 0.7):
    """Create an LLM client through the shared OpenAI-compatible interface."""
    # GPT-5 models currently accept only temperature=1 through compatible gateways.
    t = 1.0 if "gpt-5" in model.lower() else temperature
    kwargs = {}
    if API_ENDPOINT:
        kwargs["base_url"] = API_ENDPOINT
        # Some APIM gateways require an api-key header instead of bearer authentication.
        kwargs["default_headers"] = {"api-key": API_KEY}
    return ChatOpenAI(model=model, temperature=t, openai_api_key=API_KEY, **kwargs)

def get_main_agent_llm():
    """Return the conversational model used by MainAgent."""
    return get_llm(MAIN_AGENT_MODEL, temperature=0.7)

def get_code_agent_llm():
    """Return the code model used by CodeAgent."""
    return get_llm(CODE_AGENT_MODEL, temperature=0.3)  # Code generation benefits from determinism.

def call_llm(
    model: str,
    system: str,
    user: str,
    temperature: float = 0.7
) -> str:
    """
    Invoke an LLM synchronously with unstructured output.

    Args:
        model: Model name.
        system: System prompt.
        user: User message.
        temperature: Sampling temperature.

    Returns:
        Generated text.
    """
    llm = get_llm(model, temperature)
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user)
    ]
    response = llm.invoke(messages)
    return response.content

def _supports_structured_output() -> bool:
    """Return whether the current endpoint supports structured response formats."""
    # The official OpenAI endpoint supports structured output. Compatible custom gateways
    # use a prompt-enforced JSON fallback with manual parsing.
    return API_ENDPOINT is None


def call_llm_structured(
    model: str,
    system: str,
    user: str,
    output_schema: Type[T],
    temperature: float = 0.7
) -> T:
    """
    Invoke an LLM synchronously with structured output.

    Args:
        model: Model name.
        system: System prompt.
        user: User message.
        output_schema: Pydantic model defining the output shape.
        temperature: Sampling temperature.

    Returns:
        Parsed Pydantic output object.
    """
    llm = get_llm(model, temperature)
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user)
    ]

    if _supports_structured_output():
        structured_llm = llm.with_structured_output(output_schema)
        return structured_llm.invoke(messages)

    # Compatible endpoints without response formats use prompt-enforced JSON.
    schema_json = json.dumps(output_schema.model_json_schema(), ensure_ascii=False)
    enhanced_system = (
        f"{system}\n\n"
        "Return one valid JSON object matching this JSON Schema exactly. "
        "Do not use a Markdown code fence:\n"
        f"{schema_json}"
    )
    enhanced_messages = [
        SystemMessage(content=enhanced_system),
        HumanMessage(content=user)
    ]
    response = llm.invoke(enhanced_messages)
    text = response.content.strip()

    # Extract JSON from a possible Markdown code fence.
    block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if block_match:
        text = block_match.group(1).strip()
    else:
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            text = brace_match.group()

    data = json.loads(text)
    return output_schema(**data)


if __name__ == "__main__":
    print(f"Main model: {MAIN_AGENT_MODEL}")
    print(f"Code model: {CODE_AGENT_MODEL}")

    main_llm = get_main_agent_llm()
    code_llm = get_code_agent_llm()
    print(f"Main LLM: {type(main_llm).__name__}")
    print(f"Code LLM: {type(code_llm).__name__}")

    resp = call_llm(
        model=MAIN_AGENT_MODEL,
        system="You are a helpful assistant.",
        user="Reply with exactly: test passed",
    )
    print(f"\nUnstructured output: {resp}")

    from pydantic import BaseModel

    class TestOutput(BaseModel):
        result: str

    structured = call_llm_structured(
        model=MAIN_AGENT_MODEL,
        system="You are a helpful assistant.",
        user="Reply with exactly: test passed",
        output_schema=TestOutput,
    )
    print(f"Structured output: {structured.result}")
