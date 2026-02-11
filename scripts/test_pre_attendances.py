import sys
from pathlib import Path

# Ensure project root is on sys.path so `import app` works when running this script directly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers.pre_attendance import get_pre_attendances

import asyncio


async def main():
    # Call handler directly. We need to pass db=None because our cruds functions expect AsyncSession;
    # this will likely raise if cruds uses db, but this test checks whether the function is invoked and prints.
    try:
        await get_pre_attendances(db=None)
    except Exception as e:
        print("Handler raised:", type(e), e)


if __name__ == '__main__':
    asyncio.run(main())
