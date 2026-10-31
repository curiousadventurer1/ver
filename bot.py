import os
import random
import asyncio
from typing import List, Dict
from PIL import Image, ImageEnhance
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

album_buffer: Dict[str, List[types.Message]] = {}

# لیست User-Agent و رزولوشن‌های متنوع برای جلوگیری از تشخیص تکراری بودن سیستم
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"
]

VIEWPORTS = [
    {'width': 1366, 'height': 768},
    {'width': 1440, 'height': 900},
    {'width': 1536, 'height': 864},
    {'width': 1920, 'height': 1080}
]


def clean_image_metadata(input_path: str, output_path: str):
    """پاکسازی کامل متادیتا، تغییر جزئی روشنایی و تغییر هش فایل"""
    with Image.open(input_path) as img:
        rgb_img = img.convert("RGB")
        
        # تغییر بسیار جزئی و نامحسوس در روشنایی تصویر برای یکتا شدن در هوش مصنوعی SheerID
        enhancer = ImageEnhance.Brightness(rgb_img)
        rgb_img = enhancer.enhance(random.uniform(0.98, 1.02))
        
        data = list(rgb_img.getdata())
        clean_img = Image.new("RGB", rgb_img.size)
        clean_img.putdata(data)
        
        # تغییر چند پیکسل تصادفی در گوشه‌ها
        pixels = clean_img.load()
        w, h = clean_img.size
        for _ in range(5):
            x, y = random.randint(0, w - 1), random.randint(0, h - 1)
            r, g, b = pixels[x, y]
            pixels[x, y] = ((r + 1) % 255, (g + 1) % 255, (b + 1) % 255)
        
        clean_img.save(output_path, "JPEG", quality=random.randint(91, 98))


def merge_images_to_pdf(image_paths: List[str], pdf_path: str):
    """ترکیب چند عکس در یک فایل PDF چندصفحه‌ای"""
    images = [Image.open(p).convert("RGB") for p in image_paths]
    if images:
        images[0].save(pdf_path, save_all=True, append_images=images[1:])


async def handle_extra_fields(target_frame):
    """پر کردن خودکار منوهای کشویی (نوع مدرک) و چک‌باکس‌های احتمالی در فرم‌های مختلف SheerID"""
    try:
        # ۱. بررسی منوهای کشویی استاندارد (<select>)
        selects = target_frame.locator('select')
        count = await selects.count()
        for i in range(count):
            sel = selects.nth(i)
            if await sel.is_visible():
                # انتخاب گزینه اول بعد از Placeholder (معمولاً Class Schedule یا ID Card)
                options = await sel.locator('option').count()
                if options > 1:
                    await sel.select_option(index=1)
                    await asyncio.sleep(random.uniform(0.8, 1.5))

        # ۲. بررسی منوهای کشویی سفارشی SheerID (Custom Dropdown / Combobox)
        custom_dropdowns = target_frame.locator('[role="combobox"], [id*="documentType"], [class*="select"]')
        if await custom_dropdowns.count() > 0:
            first_dd = custom_dropdowns.first
            if await first_dd.is_visible():
                await first_dd.click()
                await asyncio.sleep(1)
                await target_frame.keyboard.press("ArrowDown")
                await target_frame.keyboard.press("Enter")
                await asyncio.sleep(1)

        # ۳. تیک زدن چک‌باکس‌های تایید قوانین در صورت وجود
        checkboxes = target_frame.locator('input[type="checkbox"]')
        cb_count = await checkboxes.count()
        for i in range(cb_count):
            cb = checkboxes.nth(i)
            if await cb.is_visible() and not await cb.is_checked():
                await cb.check()
                await asyncio.sleep(0.5)
    except Exception:
        pass


async def upload_docs_to_sheerid(verify_url: str, image_paths: List[str], user_id: int):
    """باز کردن لینک SheerID، شبیه‌سازی رفتار انسانی، آپلود مدارک و تحلیل نتیجه"""
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

        # انتخاب تصادفی مشخصات مرورگر برای هر درخواست
        chosen_ua = random.choice(USER_AGENTS)
        chosen_vp = random.choice(VIEWPORTS)

        context = await browser.new_context(
            viewport=chosen_vp,
            user_agent=chosen_ua,
            locale="en-US",
            timezone_id="America/New_York"
        )

        # مخفی‌سازی پیشرفته WebDriver و شبیه‌سازی سخت‌افزار تصادفی
        hw_concurrency = random.choice([4, 8, 12, 16])
        device_mem = random.choice([8, 16, 32])
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
            window.chrome = {{ runtime: {{}} }};
            Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en'] }});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_concurrency} }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_mem} }});
            Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3, 4, 5] }});
        """)

        page = await context.new_page()
        result_screenshot = f"result_{user_id}.png"

        try:
            await page.goto(verify_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(4.0, 6.0))

            # حرکت تصادفی موس برای شبیه‌سازی حضور کاربر واقعی
            await page.mouse.move(random.randint(100, 500), random.randint(100, 500))
            await page.mouse.wheel(0, random.randint(100, 300))
            await asyncio.sleep(1)

            page_content = (await page.content()).lower()
            if "vpn" in page_content and "not allowed" in page_content:
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "❌ **خطای شناسایی VPN / Server IP توسط SheerID!**\nلطفاً یک پروکسی مسکونی آمریکا (US Residential Proxy) در بخش Variables تنظیم کنید.", result_screenshot

            # پیدا کردن فریم یا صفحه حاوی فیلد آپلود فایل
            target_frame = page
            file_input = page.locator('input[type="file"]')
            
            if await file_input.count() == 0:
                for frame in page.frames:
                    if await frame.locator('input[type="file"]').count() > 0:
                        file_input = frame.locator('input[type="file"]')
                        target_frame = frame
                        break

            # گاهی قبل از رسیدن به کادر آپلود، دکمه‌ای مثل "Upload Document" یا "Try another way" وجود دارد
            if await file_input.count() == 0:
                pre_upload_btns = page.locator(
                    'button:has-text("Upload"), a:has-text("Upload"), button:has-text("document"), a:has-text("document")'
                )
                if await pre_upload_btns.count() > 0 and await pre_upload_btns.first.is_visible():
                    await pre_upload_btns.first.click()
                    await asyncio.sleep(3)
                    file_input = target_frame.locator('input[type="file"]')

            if await file_input.count() == 0:
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "⚠️ فیلد آپلود فایل در این صفحه پیدا نشد (وضعیت صفحه را در اسکرین‌شات بررسی کنید).", result_screenshot

            # پر کردن منوهای کشویی یا چک‌باکس‌های احتمالی قبل از آپلود
            await handle_extra_fields(target_frame)

            # آپلود فایل‌ها (تک‌عکس، چندعکس یا تبدیل خودکار به PDF)
            if len(image_paths) == 1:
                await file_input.first.set_input_files(image_paths[0], timeout=20000)
            else:
                is_multiple = await file_input.first.get_attribute("multiple")
                if is_multiple is not None:
                    await file_input.first.set_input_files(image_paths, timeout=20000)
                else:
                    uploaded_all = True
                    for idx, img_path in enumerate(image_paths):
                        inputs = target_frame.locator('input[type="file"]')
                        if idx < await inputs.count():
                            await inputs.nth(idx).set_input_files(img_path, timeout=15000)
                            await asyncio.sleep(2)
                        else:
                            add_btn = target_frame.locator(
                                'button:has-text("Add"), a:has-text("Add"), [class*="add-file"], button:has-text("another")'
                            )
                            if await add_btn.count() > 0 and await add_btn.first.is_visible():
                                await add_btn.first.click()
                                await asyncio.sleep(1.5)
                                inputs = target_frame.locator('input[type="file"]')
                                await inputs.last.set_input_files(img_path, timeout=15000)
                                await asyncio.sleep(2)
                            else:
                                uploaded_all = False
                                break

                    if not uploaded_all:
                        pdf_path = f"merged_{user_id}.pdf"
                        merge_images_to_pdf(image_paths, pdf_path)
                        await file_input.first.set_input_files(pdf_path, timeout=20000)
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)

            await asyncio.sleep(random.uniform(2.5, 4.0))

            # بررسی مجدد منوهای کشویی (گاهی منوی انتخاب نوع مدرک بعد از انتخاب فایل ظاهر می‌شود)
            await handle_extra_fields(target_frame)

            # پیدا کردن و کلیک روی دکمه ارسال نهایی
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Continue")',
                'button:has-text("Upload")',
                'button:has-text("Verify")',
                '[id*="submit"]'
            ]
            
            clicked = False
            for selector in submit_selectors:
                btns = target_frame.locator(selector)
                count = await btns.count()
                for i in range(count):
                    btn = btns.nth(i)
                    if await btn.is_visible() and await btn.is_enabled():
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        await btn.click()
                        clicked = True
                        break
                if clicked:
                    break

            if not clicked:
                await page.screenshot(path=result_screenshot, full_page=True)
                await browser.close()
                return False, "⚠️ مدارک داخل کادر قرار گرفتند اما دکمه Submit فعال نشد (اسکرین‌شات را بررسی کنید).", result_screenshot

            # انتظار برای پردازش هوش مصنوعی SheerID (معمولاً بین ۱۰ تا ۱۵ ثانیه)
            await asyncio.sleep(14)
            await page.screenshot(path=result_screenshot, full_page=True)
            
            final_text = (await target_frame.inner_text("body")).lower()
            await browser.close()

            # تحلیل هوشمند متن صفحه نهایی
            if any(w in final_text for w in ["congratulations", "verified", "you're in", "offer applied", "eligible", "success!"]):
                status_report = (
                    f"🎉 **تایید آنی (Approved)!**\n"
                    f"مدارک ({len(image_paths)} عدد) با موفقیت توسط SheerID تایید شد."
                )
            elif any(w in final_text for w in ["unable to verify", "rejected", "try again", "didn't work", "not match", "unacceptable", "limit exceeded", "expired"]):
                status_report = (
                    f"❌ **مدرک رد شد یا خطایی رخ داد (Rejected)!**\n"
                    f"سامانه SheerID مدرک را نپذیرفت. دلیل دقیق خطا در اسکرین‌شات بالا مشخص است."
                )
            elif any(w in final_text for w in ["review", "received", "check your email", "24 hours", "pending", "thank you for submitting", "we'll email you"]):
                status_report = (
                    f"⏳ **در انتظار بررسی (Under Review)**\n"
                    f"مدارک با موفقیت ثبت شد و در صف بررسی SheerID قرار گرفت. نتیجه به ایمیل دانشجو ارسال می‌شود."
                )
            else:
                status_report = (
                    f"📤 **مدارک ({len(image_paths)} عدد) ارسال شد.**\n"
                    f"لطفاً نتیجه نهایی را در تصویر بالا مشاهده کنید."
                )

            return True, status_report, result_screenshot

        except Exception as e:
            try:
                await page.screenshot(path=result_screenshot, full_page=True)
            except Exception:
                pass
            await browser.close()
            return False, f"❌ خطا در حین اجرا:\n`{str(e)}`", result_screenshot


async def process_messages(messages: List[types.Message]):
    """مدیریت دانلود عکس‌ها، پاکسازی و فراخوانی تابع SheerID"""
    first_msg = messages[0]
    
    caption = ""
    for m in messages:
        if m.caption and "http" in m.caption:
            caption = m.caption
            break

    if not caption:
        await first_msg.reply("⚠️ لطفاً در کپشن عکس (یا آلبوم عکس‌ها)، لینک دریافتی از ایمیل SheerID را قرار دهید.")
        return

    verify_url = next((word.strip() for word in caption.split() if word.startswith("http")), "")
    status_msg = await first_msg.reply(
        f"⏳ در حال پردازش {len(messages)} مدرک، پاکسازی متادیتا و ارسال به SheerID...\n"
        f"(این فرآیند حدود ۲۰ تا ۳۰ ثانیه زمان می‌برد)"
    )

    user_id = first_msg.from_user.id
    raw_files = []
    clean_files = []

    try:
        for idx, m in enumerate(messages):
            raw_path = f"raw_{user_id}_{idx}.jpg"
            clean_path = f"clean_{user_id}_{idx}.jpg"
            
            file_id = m.photo[-1].file_id if m.photo else m.document.file_id
            file_info = await bot.get_file(file_id)
            await bot.download_file(file_info.file_path, raw_path)
            
            clean_image_metadata(raw_path, clean_path)
            raw_files.append(raw_path)
            clean_files.append(clean_path)

        success, msg_text, screenshot_path = await upload_docs_to_sheerid(verify_url, clean_files, user_id)

        if os.path.exists(screenshot_path):
            await first_msg.reply_photo(
                photo=types.FSInputFile(screenshot_path),
                caption=msg_text,
                parse_mode="Markdown"
            )
            os.remove(screenshot_path)
        else:
            await first_msg.reply(msg_text, parse_mode="Markdown")

    finally:
        for f in raw_files + clean_files:
            if os.path.exists(f):
                os.remove(f)
        await status_msg.delete()


@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 **ربات هوشمند وریفای SheerID آماده است!**\n\n"
        "📌 **نحوه استفاده:**\n"
        "۱. یک یا چند عکس از مدارک پورتال دانشجویی را انتخاب کنید.\n"
        "۲. در بخش **Caption (توضیحات عکس)**، لینک آپلود دریافتی از ایمیل SheerID را قرار دهید و ارسال کنید.\n"
        "۳. ربات متادیتای عکس را پاک کرده، فرم را پر می‌کند و نتیجه نهایی را به همراه اسکرین‌شات برایتان می‌فرستد.",
        parse_mode="Markdown"
    )


@dp.message(F.photo | F.document)
async def handle_upload(message: types.Message):
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in album_buffer:
            album_buffer[mg_id] = [message]
            await asyncio.sleep(2.5)
            messages = album_buffer.pop(mg_id, [])
            if messages:
                await process_messages(messages)
        else:
            album_buffer[mg_id].append(message)
    else:
        await process_messages([message])


async def main():
    print("🚀 Pro SheerID Bot is running on Railway...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
