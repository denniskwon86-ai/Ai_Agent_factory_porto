import os
import asyncio
from dotenv import load_dotenv
load_dotenv()
from langchain_openai import ChatOpenAI

async def test():
    for model in ["meta-llama/llama-3.3-70b-instruct", "anthropic/claude-3.5-sonnet:beta", "anthropic/claude-3.5-sonnet-20241022"]:
        llm = ChatOpenAI(
            model=model,
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            openai_api_base="https://openrouter.ai/api/v1",
            max_retries=0
        )
        try:
            res = await llm.ainvoke("hello")
            print(f"Success with {model}:", res.content)
        except Exception as e:
            print(f"Error with {model}:", repr(e))

asyncio.run(test())
