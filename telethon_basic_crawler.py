import os
from telethon import TelegramClient
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
client = TelegramClient('anon', API_ID, API_HASH)

async def main():
   me = await client.get_me()
   username = me.username
   print(username)
   print(me.phone)
   
   async for dialog in client.iter_dialogs():
       print(dialog.name, 'has ID - ', dialog.id)


with client:
   client.loop.run_until_complete(main())
