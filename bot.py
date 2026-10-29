import os
import random
import asyncio
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from playwright.async_api import async_playwright

# خواندن اطلاعات از بخش Variables در Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_SERVER = os.getenv("PROXY_SERVER", "")      # مثال: http://gate.smartproxy.com:7000
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN در بخش Variables تنظیم نشده است!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def clean_image_metadata(input_path: str, output_path: str):
    """پاکسازی متادیتای عکس و تغییر جزئی هش فایل"""
    with Image.open(input_path) as img:
        data = list(img.convert("RGB").getdata())
        clean_img = Image.new("RGB", img.size)
        clean_img.putdata(data)
        
        pixels = clean_img.load()
        r, g, b = pixels[0, 0]
        pixels[0, 0] = (r, g, (b + random.randint(1, 5)) % 255)
        
        clean_img.save(output_path, "JPEG", quality=random.randint(92, 98))


async def upload_doc_to_sheerid(verify_url: str, image_path: str, user_id: int):
    """باز کردن لینک ایمیل SheerID و آپلود مدرک"""
    async with async_playwright() as p:
        # کانفیگ اجرای مرورگر در محیط Docker/Railway به همراه غیرفعال کردن فلگ اتوماسیون
        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        }
        
        if PROXY_SERVER:
            proxy_cfg = {"server": PROXY_SERVER}
            if PROXY_USERNAME and PROXY_PASSWORD:
                proxy_cfg["username"] = PROXY_USERNAME
                proxy_cfg["password"] = PROXY_PASSWORD
            launch_args["proxy"] = proxy_cfg

        browser = await p.chromium.launch(**launch_args)

        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York"
        )

        # جایگزین بومی و بدون خطای playwright-stealth برای مخفی کردن webdriver
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

        page = await context.new_page()
        result_screenshot = f"result_{user_id}.png"

        try:
            await page.goto(verify_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(4)

            page_content = await page.content()
            if "vpn" in page_content.lower() and "not allowed" in page_content.lower():
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "❌ خطای شناسایی VPN/Server IP توسط SheerID. پروکسی خانگی آمریکا را در Variables تنظیم کنید.", result_screenshot

            # پیدا کردن تگ آپلود فایل
            target_frame = page
            file_input = page.locator('input[type="file"]')
            
            if await file_input.count() == 0:
                for frame in page.frames:
                    if await frame.locator('input[type="file"]').count() > 0:
                        file_input = frame.locator('input[type="file"]')
                        target_frame = frame
                        break

            if await file_input.count() == 0:
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "⚠️ فیلد آپلود فایل در این لینک پیدا نشد (اسکرین‌شات صفحه را بررسی کنید).", result_screenshot

            await file_input.first.set_input_files(image_path, timeout=20000)
            await asyncio.sleep(3)

            # پیدا کردن و کلیک روی دکمه ارسال
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Continue")',
                'button:has-text("Upload")',
                '[id*="submit"]'
            ]
            
            clicked = False
            for selector in submit_selectors:
                btn = target_frame.locator(selector)
                if await btn.count() > 0 and await btn.first.is_enabled():
                    await btn.first.click()
                    clicked = True
                    break

            if not clicked:
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "⚠️ فایل انتخاب شد اما دکمه Submit فعال نشد یا نیاز به پر کردن فیلد دیگری در صفحه است.", result_screenshot

            await asyncio.sleep(10)
            await page.screenshot(path=result_screenshot, full_page=True)
            await browser.close()
            
            return True, "✅ مدرک با موفقیت آپلود و ارسال شد!", result_screenshot

        except Exception as e:
            try:
                await page.screenshot(path=result_screenshot, full_page=True)
            except:
                pass
            await browser.close()
            return False, f"❌ خطا:\n{str(e)}", result_screenshot


@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 سلام!\n"
        "عکس اسکرین‌شات پورتال دانشجو را بفرستید و در **کپشن (توضیحات عکس)**، لینک دریافتی از ایمیل SheerID را قرار دهید.",
        parse_mode="Markdown"
    )


@dp.message(F.photo | F.document)
async def handle_upload(message: types.Message):
    caption = message.caption
    if not caption or "http" not in caption:
        await message.reply("⚠️ لطفاً در کپشن عکس، لینک دریافتی از ایمیل SheerID را قرار دهید.")
        return

    verify_url = next((word.strip() for word in caption.split() if word.startswith("http")), "")
    status_msg = await message.reply("⏳ در حال پردازش و ارسال مدرک به SheerID...")

    user_id = message.from_user.id
    raw_image = f"raw_{user_id}.jpg"
    clean_image = f"clean_{user_id}.jpg"

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, raw_image)

    clean_image_metadata(raw_image, clean_image)
    success, msg_text, screenshot_path = await upload_doc_to_sheerid(verify_url, clean_image, user_id)

    if os.path.exists(screenshot_path):
        await message.reply_photo(photo=types.FSInputFile(screenshot_path), caption=msg_text)
        os.remove(screenshot_path)
    else:
        await message.reply(msg_text)

    for f in [raw_image, clean_image]:
        if os.path.exists(f):
            os.remove(f)
    await status_msg.delete()


async def main():
    print("🚀 Bot is running on Railway...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
