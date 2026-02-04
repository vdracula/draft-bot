import os
import asyncio
from datetime import datetime, time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
YC_API_KEY = os.getenv("YC_API_KEY")
YC_FOLDER_ID = os.getenv("YC_FOLDER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # ID твоего канала, например: @neurocodermoscow или -1001234567890

YA_ENDPOINT = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YA_MODEL_URI = f"gpt://{YC_FOLDER_ID}/yandexgpt/latest"

# База идей для автопостов
POST_IDEAS = [
    "Расскажи про интересный кейс использования AI в разработке",
    "Напиши про новый инструмент для работы с нейросетями",
    "Сделай пост про частую ошибку при работе с Telegram ботами",
    "Расскажи про лайфхак при работе с API",
    "Напиши про интересную фичу Python для AI-разработки",
    "Сделай пост про оптимизацию работы с LLM API",
    "Расскажи про интересный промпт-инжиниринг трюк",
    "Напиши про автоматизацию рутины разработчика через AI",
    "Сделай пост про интеграцию нейросетей в реальные проекты",
    "Расскажи про тестирование ботов и AI-сервисов",
]

# Состояния
class DraftStates(StatesGroup):
    waiting_for_draft = State()
    waiting_for_idea = State()

# Промпты
PROMPTS = {
    "default": """
Ты — автор контента для Telegram-канала «Нейрокодер из Москвы».
Пиши посты про AI, код, автоматизацию и практический опыт.

Правила:
1. Стиль: просто и живо, без канцелярита, личный опыт
2. Обращайся на «ты»
3. НЕ используй markdown символы: *, _, `, [, ]
4. Для выделения используй ЗАГЛАВНЫЕ буквы или эмодзи
5. Добавляй конкретные примеры и кейсы
6. Пост должен быть ПОЛЕЗНЫМ и практичным

Структура ответа:
1) Цепляющий заголовок
2) Готовый пост (8-12 предложений)
3) Призыв к действию или вопрос в конце

НЕ ДОБАВЛЯЙ призывы подписаться или рекламу.
""",
    "auto": """
Ты — автор контента для Telegram-канала «Нейрокодер из Москвы».
Генерируй ОРИГИНАЛЬНЫЙ пост на заданную тему.

Правила:
1. Пиши от первого лица, как будто это твой личный опыт
2. Добавляй КОНКРЕТНЫЕ детали (названия библиотек, команды, цифры)
3. Стиль: живой, неформальный, с лёгкой самоиронией
4. НЕ используй markdown символы: *, _, `, [, ]
5. Пост должен нести практическую пользу

Структура:
1) Заголовок (до 80 символов)
2) Пост (10-12 предложений): проблема → решение → результат
3) Вопрос читателям в конце

Важно: НЕ придумывай факты, пиши правдоподобно.
"""
}

# Хранилище
user_drafts = {}
autopost_enabled = False
last_idea_index = 0

async def call_yandexgpt(draft_text: str, style: str = "default", action: str = None) -> str:
    """Вызов YandexGPT"""
    system_prompt = PROMPTS.get(style, PROMPTS["default"])
    
    user_prompt = f"Тема/черновик:\n{draft_text}\n\n"
    
    if action == "shorter":
        user_prompt += "Сделай пост КОРОЧЕ (максимум 7-8 предложений).\n\n"
    elif action == "longer":
        user_prompt += "Сделай пост ПОДРОБНЕЕ (12-15 предложений).\n\n"
    
    user_prompt += "Сформируй ответ строго по описанным правилам."
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {YC_API_KEY}",
        "x-folder-id": YC_FOLDER_ID,
    }

    payload = {
        "modelUri": YA_MODEL_URI,
        "completionOptions": {
            "stream": False,
            "temperature": 0.7,
            "maxTokens": 2000,
        },
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(YA_ENDPOINT, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["alternatives"][0]["message"]["text"]


async def generate_and_post(bot: Bot):
    """Генерация и отправка автопоста"""
    global last_idea_index
    
    if not CHANNEL_ID:
        print("❌ CHANNEL_ID не настроен!")
        return
    
    # Выбираем следующую идею
    idea = POST_IDEAS[last_idea_index % len(POST_IDEAS)]
    last_idea_index += 1
    
    try:
        print(f"🤖 Генерирую пост на тему: {idea}")
        post_content = await call_yandexgpt(idea, style="auto")
        
        # Отправляем в канал
        await bot.send_message(CHANNEL_ID, post_content)
        print(f"✅ Пост отправлен в канал {CHANNEL_ID}")
        
    except Exception as e:
        print(f"❌ Ошибка автопостинга: {e}")


def get_action_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с действиями"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✂️ Короче", callback_data="action_shorter"),
            InlineKeyboardButton(text="📝 Подробнее", callback_data="action_longer"),
        ],
        [
            InlineKeyboardButton(text="📤 Отправить в канал", callback_data="send_to_channel"),
        ],
    ])
    return keyboard


async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализируем планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    
    # Добавляем задачи автопостинга
    # Каждый день в 10:00 и 18:00 по МСК
    scheduler.add_job(
        generate_and_post,
        trigger=CronTrigger(hour=10, minute=0),
        args=[bot],
        id="morning_post",
        replace_existing=True
    )
    scheduler.add_job(
        generate_and_post,
        trigger=CronTrigger(hour=18, minute=0),
        args=[bot],
        id="evening_post",
        replace_existing=True
    )
    
    # Можно добавить тестовый пост каждые 5 минут (закомментируй, когда не нужно)
    # scheduler.add_job(
    #     generate_and_post,
    #     trigger=CronTrigger(minute="*/5"),
    #     args=[bot],
    #     id="test_post",
    #     replace_existing=True
    # )
    
    scheduler.start()
    print("✅ Планировщик запущен")
    print(f"📅 Автопосты: каждый день в 10:00 и 18:00 МСК")
    if CHANNEL_ID:
        print(f"📢 Канал для постинга: {CHANNEL_ID}")
    else:
        print("⚠️ CHANNEL_ID не настроен! Добавь в .env")

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        await message.answer(
            "👋 Я бот-черновик с автопостингом!\n\n"
            "🤖 АВТОПОСТИНГ:\n"
            f"Отправляю посты в канал каждый день в 10:00 и 18:00 МСК\n"
            f"Канал: {CHANNEL_ID if CHANNEL_ID else 'не настроен'}\n\n"
            "✍️ РУЧНОЙ РЕЖИМ:\n"
            "Отправь черновик — я сделаю готовый пост\n\n"
            "Команды:\n"
            "/test_post — сгенерить тестовый пост\n"
            "/schedule — расписание автопостов\n"
            "/add_idea — добавить идею для автопоста\n"
            "/help — помощь"
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "📚 Функции:\n\n"
            "🤖 АВТОПОСТИНГ:\n"
            "• Генерация постов по расписанию\n"
            "• Автоотправка в канал\n"
            "• База из 10+ идей для постов\n\n"
            "✍️ РУЧНОЙ РЕЖИМ:\n"
            "• Отправь черновик\n"
            "• Получи готовый пост\n"
            "• Отправь в канал одной кнопкой\n\n"
            "Команды:\n"
            "/test_post — тестовый пост сейчас\n"
            "/schedule — когда следующий пост\n"
            "/add_idea — добавить тему"
        )

    @dp.message(Command("schedule"))
    async def cmd_schedule(message: Message):
        jobs = scheduler.get_jobs()
        schedule_text = "📅 Расписание автопостинга:\n\n"
        
        for job in jobs:
            schedule_text += f"• {job.id}: {job.next_run_time.strftime('%d.%m.%Y %H:%M')} МСК\n"
        
        schedule_text += f"\n📢 Канал: {CHANNEL_ID if CHANNEL_ID else 'не настроен'}"
        schedule_text += f"\n💡 Осталось идей: {len(POST_IDEAS) - (last_idea_index % len(POST_IDEAS))}"
        
        await message.answer(schedule_text)

    @dp.message(Command("test_post"))
    async def cmd_test_post(message: Message):
        await message.answer("🤖 Генерирую тестовый пост...")
        
        try:
            await generate_and_post(bot)
            await message.answer("✅ Тестовый пост отправлен в канал!")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")

    @dp.message(Command("add_idea"))
    async def cmd_add_idea(message: Message, state: FSMContext):
        await message.answer(
            "💡 Отправь идею для будущего автопоста\n\n"
            "Например:\n"
            "• Расскажи про деплой бота на Railway\n"
            "• Сделай пост про работу с базами данных"
        )
        await state.set_state(DraftStates.waiting_for_idea)

    @dp.message(DraftStates.waiting_for_idea)
    async def handle_new_idea(message: Message, state: FSMContext):
        new_idea = message.text.strip()
        POST_IDEAS.append(new_idea)
        await message.answer(
            f"✅ Идея добавлена!\n\n"
            f"Всего идей в базе: {len(POST_IDEAS)}"
        )
        await state.clear()

    @dp.message(F.text)
    async def handle_draft(message: Message):
        draft = message.text.strip()
        user_id = message.from_user.id
        
        user_drafts[user_id] = {"text": draft, "style": "default"}
        
        await message.answer("⏳ Думаю над текстом...")

        try:
            formatted = await call_yandexgpt(draft, style="default")
            user_drafts[user_id]["last_post"] = formatted
        except Exception as e:
            await message.answer(f"❌ Ошибка:\n{str(e)}")
            return

        if len(formatted) > 3500:
            chunks = []
            current = ""
            for line in formatted.split("\n"):
                if len(current) + len(line) + 1 > 3500:
                    chunks.append(current)
                    current = ""
                current += line + "\n"
            if current:
                chunks.append(current)
            
            for i, part in enumerate(chunks):
                if i == len(chunks) - 1:
                    await message.answer(part, reply_markup=get_action_keyboard())
                else:
                    await message.answer(part)
        else:
            await message.answer(formatted, reply_markup=get_action_keyboard())

        @dp.callback_query(F.data.startswith("action_"))
    async def handle_action(callback: CallbackQuery):
        user_id = callback.from_user.id
        action = callback.data.replace("action_", "")
        
        if user_id not in user_drafts:
            await callback.answer("❌ Сначала отправь черновик!", show_alert=True)
            return
        
        draft_data = user_drafts[user_id]
        await callback.message.answer("⏳ Переделываю...")
        
        try:
            formatted = await call_yandexgpt(
                draft_data["text"],
                style=draft_data.get("style", "default"),
                action=action
            )
            user_drafts[user_id]["last_post"] = formatted
            await callback.message.answer(formatted, reply_markup=get_action_keyboard())
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка:\n{str(e)}")
        
        await callback.answer()

    @dp.callback_query(F.data == "send_to_channel")
    async def handle_send_to_channel(callback: CallbackQuery):
        user_id = callback.from_user.id
        
        if user_id not in user_drafts or "last_post" not in user_drafts[user_id]:
            await callback.answer("❌ Сначала создай пост!", show_alert=True)
            return
        
        if not CHANNEL_ID:
            await callback.answer("❌ CHANNEL_ID не настроен в .env!", show_alert=True)
            return
        
        try:
            post_content = user_drafts[user_id]["last_post"]
            await bot.send_message(CHANNEL_ID, post_content)
            await callback.message.answer("✅ Пост отправлен в канал!")
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка отправки:\n{str(e)}")
        
        await callback.answer()

    # Запуск бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

