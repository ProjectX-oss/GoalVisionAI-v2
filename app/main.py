import asyncio

from app.core.application import GoalVisionApp


async def main():
    app = GoalVisionApp()
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())