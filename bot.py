import os
import random
import asyncio
from typing import List, Dict
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from playwright.async_api import async_playwright

BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN در بخش Variables تنظیم نشده است!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# دیکشنری موقت برای جمع‌آوری عکس‌های یک آلبوم (Media Group)
album_buffer: Dict[str, List[types.Message]] = {}


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


def merge_images_to_pdf(image_paths: List[str], pdf_path: str):
    """ترکیب چند عکس در یک فایل PDF چندصفحه‌ای (برای مواقعی که سایت فقط ۱ فایل قبول می‌کند)"""
    images = [Image.open(p).convert("RGB") for p in image_paths]
    if images:
        images[0].save(pdf_path, save_all=True, append_images=images[1:])


async def upload_docs_to_sheerid(verify_url: str, image_paths: List[str], user_id: int):
    """باز کردن لینک ایمیل SheerID و آپلود یک یا چند مدرک"""
    async with async_playwright() as p:
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

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
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
                return False, "❌ خطای شناسایی VPN/Server IP توسط SheerID. پروکسی خانگی آمریکا را تنظیم کنید.", result_screenshot

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
                return False, "⚠️ فیلد آپلود فایل در این لینک پیدا نشد (اسکرین‌شات را بررسی کنید).", result_screenshot

            # آپلود فایل‌ها (تک‌عکس یا چندعکس)
            if len(image_paths) == 1:
                await file_input.first.set_input_files(image_paths[0], timeout=20000)
            else:
                # بررسی اینکه آیا فیلد آپلود قابلیت دریافت چند فایل همزمان (multiple) را دارد؟
                is_multiple = await file_input.first.get_attribute("multiple")
                if is_multiple is not None:
                    await file_input.first.set_input_files(image_paths, timeout=20000)
                else:
                    # تلاش برای آپلود تک‌به‌تک در فیلدهای مجزا یا کلیک روی دکمه Add another file
                    uploaded_all = True
                    for idx, img_path in enumerate(image_paths):
                        inputs = target_frame.locator('input[type="file"]')
                        if idx < await inputs.count():
                            await inputs.nth(idx).set_input_files(img_path, timeout=15000)
                            await asyncio.sleep(2)
                        else:
                            # جستجوی دکمه اضافه کردن فایل جدید در SheerID
                            add_btn = target_frame.locator('button:has-text("Add"), a:has-text("Add"), [class*="add-file"]')
                            if await add_btn.count() > 0 and await add_btn.first.is_visible():
                                await add_btn.first.click()
                                await asyncio.sleep(1)
                                inputs = target_frame.locator('input[type="file"]')
                                await inputs.last.set_input_files(img_path, timeout=15000)
                                await asyncio.sleep(2)
                            else:
                                uploaded_all = False
                                break

                    # اگر صفحه فقط ۱ فایل قبول می‌کرد، همه عکس‌ها را به یک PDF تبدیل و آپلود می‌کنیم
                    if not uploaded_all:
                        pdf_path = f"merged_{user_id}.pdf"
                        merge_images_to_pdf(image_paths, pdf_path)
                        await file_input.first.set_input_files(pdf_path, timeout=20000)
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)

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
                return False, "⚠️ فایل‌ها انتخاب شدند اما دکمه Submit فعال نشد.", result_screenshot

            await asyncio.sleep(10)
            await page.screenshot(path=result_screenshot, full_page=True)
            await browser.close()
            
            return True, f"✅ تعداد {len(image_paths)} مدرک با موفقیت آپلود و ارسال شد!", result_screenshot

        except Exception as e:
            try:
                await page.screenshot(path=result_screenshot, full_page=True)
            except:
                pass
            await browser.close()
            return False, f"❌ خطا:\n{str(e)}", result_screenshot


async def process_messages(messages: List[types.Message]):
    """پردازش یک پیام یا مجموعه‌ای از پیام‌های آلبوم"""
    first_msg = messages[0]
    
    # پیدا کردن کپشن در بین عکس‌های آلبوم
    caption = ""
    for m in messages:
        if m.caption and "http" in m.caption:
            caption = m.caption
            break

    if not caption:
        await first_msg.reply("⚠️ لطفاً در کپشنِ عکس (یا آلبوم عکس‌ها)، لینک دریافتی از ایمیل SheerID را قرار دهید.")
        return

    verify_url = next((word.strip() for word in caption.split() if word.startswith("http")), "")
    status_msg = await first_msg.reply(f"⏳ در حال دانلود {len(messages)} مدرک، پاکسازی متادیتا و ارسال به SheerID...")

    user_id = first_msg.from_user.id
    raw_files = []
    clean_files = []

    try:
        # دانلود و پاکسازی تک‌تک عکس‌ها
        for idx, m in enumerate(messages):
            raw_path = f"raw_{user_id}_{idx}.jpg"
            clean_path = f"clean_{user_id}_{idx}.jpg"
            
            file_id = m.photo[-1].file_id if m.photo else m.document.file_id
            file_info = await bot.get_file(file_id)
            await bot.download_file(file_info.file_path, raw_path)
            
            clean_image_metadata(raw_path, clean_path)
            raw_files.append(raw_path)
            clean_files.append(clean_path)

        # ارسال به SheerID
        success, msg_text, screenshot_path = await upload_docs_to_sheerid(verify_url, clean_files, user_id)

        if os.path.exists(screenshot_path):
            await first_msg.reply_photo(photo=types.FSInputFile(screenshot_path), caption=msg_text)
            os.remove(screenshot_path)
        else:
            await first_msg.reply(msg_text)

    finally:
        # پاک کردن فایل‌های موقت از سرور
        for f in raw_files + clean_files:
            if os.path.exists(f):
                os.remove(f)
        await status_msg.delete()


@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 سلام!\n"
        "می‌توانید **یک عکس** یا **چند عکس همزمان (به صورت آلبوم)** بفرستید و در **کپشن** آن، لینک دریافتی از ایمیل SheerID را قرار دهید.",
        parse_mode="Markdown"
    )


@dp.message(F.photo | F.document)
async def handle_upload(message: types.Message):
    # اگر کاربر چند عکس را به صورت آلبوم (Media Group) فرستاده باشد
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in album_buffer:
            album_buffer[mg_id] = [message]
            # ۲ ثانیه صبر می‌کند تا تمام عکس‌های آلبوم از تلگرام برسند، سپس پردازش را شروع می‌کند
            await asyncio.sleep(2.5)
            messages = album_buffer.pop(mg_id, [])
            if messages:
                await process_messages(messages)
        else:
            album_buffer[mg_id].append(message)
    else:
        # اگر فقط یک عکس فرستاده باشد
        await process_messages([message])


async def main():
    print("🚀 Bot is running on Railway (Multi-Photo Supported)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
