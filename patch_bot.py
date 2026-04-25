import re

with open('bot.py', 'r') as f:
    content = f.read()

# Add _reply_with_retry function after _send_long definition
retry_func = """import asyncio

async def _reply_with_retry(update, *args, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await update.message.reply_text(*args, **kwargs)
        except (TimedOut, NetworkError) as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to reply text after {max_retries} attempts: {e}")
                raise
            logger.warning(f"Network error during reply (attempt {attempt + 1}/{max_retries}): {e}. Retrying in 1s...")
            await asyncio.sleep(1)

"""

# We need to make sure we don't duplicate it if already exists
if '_reply_with_retry' not in content:
    content = content.replace('async def _send_long', retry_func + 'async def _send_long')

# Replace `await update.message.reply_text(` with `await _reply_with_retry(update, `
content = re.sub(r'await update\.message\.reply_text\(', r'await _reply_with_retry(update, ', content)

# But wait, inside _reply_with_retry itself, we need to call `await update.message.reply_text`!
# Let's fix that back.
content = content.replace('await _reply_with_retry(update, *args, **kwargs)', 'await update.message.reply_text(*args, **kwargs)')

with open('bot.py', 'w') as f:
    f.write(content)
print("Patched bot.py")
