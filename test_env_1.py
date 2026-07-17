import asyncio
from core.llm_gateway import gateway

async def main():
    print("=== ENV-1 Healthcheck ===")
    print("Sending short greeting to Pro Chain...\n")
    try:
        res = await gateway.aexecute(
            state={},
            skill_prompt="안녕, 너는 현재 어떤 모델로 동작 중이야? 딱 한 줄로 짧게 대답해줘.",
            is_heavy=True,
            output_mode="document"
        )
        print("[RESPONSE]:", res)
        print("\n[OK] Healthcheck passed: LLM Gateway responded normally.")
    except Exception as e:
        print("[ERROR] Healthcheck failed:", e)
    
if __name__ == "__main__":
    asyncio.run(main())
