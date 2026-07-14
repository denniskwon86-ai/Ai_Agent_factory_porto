import sys
import asyncio
from api.routes.factory_control import create_mega_project, MegaProjectCreateRequest

async def test():
    req = MegaProjectCreateRequest(mega_project_id="test_mega_001", template_id="manufacturing-production")
    res = await create_mega_project(req)
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
