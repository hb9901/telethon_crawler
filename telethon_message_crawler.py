import os
import random
import sqlite3
import asyncio
import logging
import pandas as pd
import socks
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Any

from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s', 
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

@dataclass
class Config:
    API_ID: int = int(os.getenv('API_ID', 0))
    API_HASH: str = os.getenv('API_HASH', '')
    PROXY_LIST: str = os.getenv('PROXY_LIST', '')
    
    DB_PATH: str = 'telegram_result.db'
    EXCEL_PATH: str = 'telegram_result.xlsx'
    IMG_DIR: str = 'downloaded_photos'
    
    # 딜레이 조정 (무제한 수집 시 계정 보호를 위해 너무 낮추지 않는 것을 권장)
    DELAY_MSG: tuple = (0.3, 0.7)  
    DELAY_CHUNK: float = 1.5
    DELAY_IMAGE: float = 0.5
    SAVE_INTERVAL: int = 50

class DataStorage:
    def __init__(self, config: Config):
        self.config = config
        self.lock = asyncio.Lock()
        self._prepare_directory()
        self._init_db()

    def _prepare_directory(self):
        if not os.path.exists(self.config.IMG_DIR):
            os.makedirs(self.config.IMG_DIR)

    def _init_db(self):
        with sqlite3.connect(self.config.DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    chat_name TEXT, msg_id INTEGER, sender_id INTEGER,
                    sender_name TEXT, content TEXT, date TEXT, image_path TEXT
                )
            ''')

    async def save_to_all(self, data: List[Dict[str, Any]]):
        if not data:
            return
        
        async with self.lock:
            try:
                df = pd.DataFrame(data)
                # 1. SQLite 저장
                with sqlite3.connect(self.config.DB_PATH) as conn:
                    df.to_sql('messages', conn, if_exists='append', index=False)
                
                # 2. Excel 저장
                if not os.path.exists(self.config.EXCEL_PATH):
                    df.to_excel(self.config.EXCEL_PATH, index=False)
                else:
                    with pd.ExcelWriter(self.config.EXCEL_PATH, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                        try:
                            existing_df = pd.read_excel(self.config.EXCEL_PATH)
                            new_df = pd.concat([existing_df, df], ignore_index=True)
                            new_df.to_excel(writer, index=False)
                        except Exception:
                            df.to_excel(self.config.EXCEL_PATH, index=False)
                            
                logger.info(f"[저장완료] {len(data)}건의 데이터가 DB/Excel에 기록되었습니다.")
            except Exception as e:
                logger.error(f"저장 중 오류 발생: {e}")

class TelegramCrawler:
    def __init__(self, config: Config):
        self.config = config
        self.proxy = self._parse_proxy()
        self.client = TelegramClient(
            'scraper_session', 
            config.API_ID, 
            config.API_HASH, 
            proxy=self.proxy
        )

    def _parse_proxy(self) -> Optional[Dict]:
        if not self.config.PROXY_LIST:
            return None
        try:
            proxies = [p.strip() for p in self.config.PROXY_LIST.split(',') if p.strip()]
            p = random.choice(proxies).split(':')
            c = {'proxy_type': socks.SOCKS5, 'addr': p[0], 'port': int(p[1]), 'rdns': True}
            if len(p) == 4:
                c['username'], c['password'] = p[2], p[3]
            return c
        except Exception:
            return None

    async def download_image(self, message: Message) -> str:
        if not message.photo:
            return "No Image"
        
        file_path = os.path.join(self.config.IMG_DIR, f"{message.id}.jpg")
        if os.path.exists(file_path):
            return file_path

        try:
            await asyncio.wait_for(message.download_media(file=file_path), timeout=30)
            await asyncio.sleep(self.config.DELAY_IMAGE)
            return file_path
        except Exception:
            return "Download Failed"

    async def process_single_dialog(self, dialog, storage: DataStorage, semaphore: asyncio.Semaphore):
        async with semaphore:
            room_name = dialog.name or "Unknown Room"
            logger.info(f"===> {room_name} 수집 시작 (전체 메시지)")
            current_room_data = []

            try:
                async for m in self.client.iter_messages(dialog.entity): 
                    if not m.text and not m.photo:
                        continue

                    try:
                        sender = await m.get_sender()
                        sender_name = "Unknown"
                        if sender:
                            sender_name = getattr(sender, 'username', None) or \
                                          f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                    except FloodWaitError as e:
                        logger.warning(f"속도 제한 발생: {e.seconds}초 대기 후 재개합니다.")
                        await asyncio.sleep(e.seconds)
                        continue
                    except Exception:
                        sender_name = "Unknown"

                    img_path = await self.download_image(m)

                    current_room_data.append({
                        'chat_name': room_name,
                        'msg_id': m.id,
                        'sender_id': m.sender_id,      
                        'sender_name': sender_name or "Unknown",  
                        'content': (m.text or "").replace('\n', ' '),
                        'date': m.date.strftime('%Y-%m-%d %H:%M:%S'),
                        'image_path': img_path
                    })

                    # 설정된 간격마다 중간 저장
                    if len(current_room_data) >= self.config.SAVE_INTERVAL:
                        await storage.save_to_all(current_room_data)
                        current_room_data.clear()
                        await asyncio.sleep(self.config.DELAY_CHUNK)

                    await asyncio.sleep(random.uniform(*self.config.DELAY_MSG))

                # 마지막 남은 데이터 저장
                if current_room_data:
                    await storage.save_to_all(current_room_data)
                logger.info(f"--- {room_name} 수집 완료")

            except Exception as e:
                logger.error(f"{room_name} 처리 중 에러: {e}")

    async def run_scan(self, storage: DataStorage):
        async with self.client:
            dialogs = await self.client.get_dialogs()
            semaphore = asyncio.Semaphore(2) # 동시 처리 방 개수
            
            tasks = [self.process_single_dialog(d, storage, semaphore) for d in dialogs]
            await asyncio.gather(*tasks)

async def main():
    config = Config()
    if not config.API_ID or not config.API_HASH:
        logger.error(".env 파일에 API_ID 또는 API_HASH가 없습니다.")
        return

    storage = DataStorage(config)
    crawler = TelegramCrawler(config)
    
    try:
        await crawler.run_scan(storage)
    except Exception as e:
        logger.critical(f"치명적 오류 발생: {e}")
    finally:
        logger.info("프로그램이 안전하게 종료되었습니다.")

if __name__ == "__main__":
    asyncio.run(main())