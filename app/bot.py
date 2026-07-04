from telegram import Bot
import asyncio

from config import BOT_TOKEN


async def send_test_message():
    bot = Bot(token=8829551384:AAFwvJsGrV03Q5wHktFPNheQsv8EIzzASwg)

    chat_id = input("@GoalVisionAI")

    await bot.send_message(
        chat_id=chat_id,
        text="🚀 GoalVision AI is online!\n\nPirmā testa ziņa veiksmīgi nosūtīta."
    )

    print("✅ Ziņa nosūtīta!")


if __name__ == "__main__":
    asyncio.run(send_test_message())