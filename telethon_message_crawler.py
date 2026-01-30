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

# 
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
    
    # 병렬 처리에 최적화된 딜레이 조정
    DELAY_MSG: tuple = (0.5, 1.2)  
    DELAY_CHUNK: float = 2.0 
    DELAY_IMAGE: float = 0.8
    SAVE_INTERVAL: int = 50  # 메모리 부하를 줄이기 위해 간격 조정

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
        """DB 테이블 미리 생성 (성능 최적화)"""
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
                # 1. SQLite 저장 (더 효율적인 방법)
                df = pd.DataFrame(data)
                with sqlite3.connect(self.config.DB_PATH) as conn:
                    df.to_sql('messages', conn, if_exists='append', index=False)
                
                # 2. Excel 저장 (파일이 커질 경우를 대비해 예외 처리 강화)
                if not os.path.exists(self.config.EXCEL_PATH):
                    df.to_excel(self.config.EXCEL_PATH, index=False)
                else:
                    # 데이터가 많을 경우 매번 concat하는 것은 성능에 좋지 않으므로 주의
                    with pd.ExcelWriter(self.config.EXCEL_PATH, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                        try:
                            existing_df = pd.read_excel(self.config.EXCEL_PATH)
                            new_df = pd.concat([existing_df, df], ignore_index=True)
                            new_df.to_excel(writer, index=False)
                        except Exception as e:
                            logger.error(f"Excel 합치기 오류 (새 파일 생성 시도): {e}")
                            df.to_excel(self.config.EXCEL_PATH, index=False)
                            
                logger.info(f"Successfully saved {len(data)} items.")
            except Exception as e:
                logger.error(f"Storage Save Error: {e}")

class TelegramCrawler:
    def __init__(self, config: Config):
        self.config = config
        self.proxy = self._parse_proxy()
        # session_name에 고유 식별자를 주어 세션 충돌 방지
        self.client = TelegramClient(
            'scraper_session', 
            config.API_ID, 
            config.API_HASH, 
            proxy=self.proxy,
            connection_retries=5,
            retry_delay=1
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
            # 타임아웃 설정을 통해 무한 대기 방지
            await asyncio.wait_for(message.download_media(file=file_path), timeout=30)
            await asyncio.sleep(self.config.DELAY_IMAGE)
            return file_path
        except Exception:
            return "Download Failed"

    async def process_single_dialog(self, dialog, storage: DataStorage, semaphore: asyncio.Semaphore):
        async with semaphore:
            room_name = dialog.name or "Unknown Room"
            logger.info(f">>> Processing: {room_name}")
            current_room_data = []

            try:
                # iter_messages 최적화 (limit이나 offset_date 활용 권장)
                async for m in self.client.iter_messages(dialog.entity, limit=500): 
                    if not m.text and not m.photo:
                        continue

                    try:
                        # sender 정보 캐싱 처리를 위해 get_sender() 최소화 권장
                        sender = await m.get_sender()
                        sender_name = "Unknown"
                        if sender:
                            sender_name = getattr(sender, 'username', None) or \
                                          f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                    except FloodWaitError as e:
                        logger.warning(f"FloodWait: Sleeping for {e.seconds}s")
                        await asyncio.sleep(e.seconds)
                        continue

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

                    if len(current_room_data) >= self.config.SAVE_INTERVAL:
                        await storage.save_to_all(current_room_data)
                        current_room_data.clear()
                        await asyncio.sleep(self.config.DELAY_CHUNK)

                    await asyncio.sleep(random.uniform(*self.config.DELAY_MSG))

                await storage.save_to_all(current_room_data)
                logger.info(f"--- Finished: {room_name}")

            except Exception as e:
                logger.error(f"Error in {room_name}: {e}")

    async def run_scan(self, storage: DataStorage):
        async with self.client:
            dialogs = await self.client.get_dialogs()
            semaphore = asyncio.Semaphore(2) 
            
            # 방이 너무 많을 경우를 대비해 청크 단위 실행 권장
            tasks = [self.process_single_dialog(d, storage, semaphore) for d in dialogs]
            await asyncio.gather(*tasks)

async def main():
    config = Config()
    if not config.API_ID or not config.API_HASH:
        logger.error("API ID/HASH is missing in .env")
        return

    storage = DataStorage(config)
    crawler = TelegramCrawler(config)
    
    try:
        await crawler.run_scan(storage)
    except Exception as e:
        logger.critical(f"Fatal Shutdown: {e}")
    finally:
        logger.info("Program Exited.")

if __name__ == "__main__":
    asyncio.run(main())