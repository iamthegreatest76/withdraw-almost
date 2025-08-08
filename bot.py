import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from handlers import register_handlers
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8280104776:AAFcJUHRUB2d2ouMp-0OE6Zru-AYYvV4FKU"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())
register_handlers(dp, bot)

async def main():
    print("🚀 Bot running with UTR + screenshot flow...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
