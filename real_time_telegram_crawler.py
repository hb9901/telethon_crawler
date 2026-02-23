import os
import sqlite3
import asyncio
import logging
import pandas as pd
import random
from dataclasses import dataclass
from typing import List, Dict, Any

from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaWebPage
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(override=True)

@dataclass
class Config:
    API_ID: int = int(os.getenv('API_ID', 0))
    API_HASH: str = os.getenv('API_HASH', '')
    DB_PATH: str = 'telegram_result.db'
    EXCEL_PATH: str = 'telegram_result.xlsx'
    IMG_DIR: str = 'downloaded_photos'
    DELAY_MSG: tuple = (0.2, 0.5)
    DELAY_IMAGE: float = 0.3
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
                    chat_name TEXT, channel_id INTEGER, msg_id INTEGER, 
                    sender_id INTEGER, is_channel_post BOOLEAN,
                    sender_name TEXT, content TEXT, date TEXT, image_path TEXT
                )
            ''')

    async def save_to_all(self, data: List[Dict[str, Any]]):
        if not data: return
        async with self.lock:
            try:
                df = pd.DataFrame(data)
                # 1. SQLite 저장
                with sqlite3.connect(self.config.DB_PATH) as conn:
                    df.to_sql('messages', conn, if_exists='append', index=False)
                
                # 2. 엑셀 저장 (기존 데이터가 있으면 합쳐서 저장)
                if not os.path.exists(self.config.EXCEL_PATH):
                    df.to_excel(self.config.EXCEL_PATH, index=False)
                else:
                    try:
                        existing_df = pd.read_excel(self.config.EXCEL_PATH)
                        pd.concat([existing_df, df], ignore_index=True).to_excel(self.config.EXCEL_PATH, index=False)
                    except Exception as e:
                        logger.error(f"엑셀 업데이트 실패 (새 파일로 생성): {e}")
                        df.to_excel(self.config.EXCEL_PATH, index=False)
                
                logger.info(f"[저장완료] {len(data)}건 기록 추가됨")
            except Exception as e:
                logger.error(f"저장 중 오류 발생: {e}")

class TelegramCrawler:
    def __init__(self, config: Config):
        self.config = config
        self.client = TelegramClient('scraper_session', config.API_ID, config.API_HASH)

    async def download_image(self, message: Message) -> str:
        """이미지 고유 ID를 확인하여 다운로드 (없으면 메시지 ID 사용)"""
        if message.photo:
            try:
                # 텔레그램 이미지 고유 ID 추출
                photo_id = getattr(message.photo, 'id', message.id)
                filename = f"{photo_id}.jpg"
                save_path = os.path.join(self.config.IMG_DIR, filename)
                
                # 이미 존재하면 다운로드 스킵
                if os.path.exists(save_path):
                    return save_path

                path = await message.download_media(file=save_path)
                await asyncio.sleep(self.config.DELAY_IMAGE)
                return path if path else ""
            except Exception as e:
                logger.error(f"이미지 다운로드 실패: {e}")
                return ""
        return ""

    async def run_scan(self, storage: DataStorage, only_unread: bool = False, skip_existing_chats: bool = True):
        await self.client.start()
        
        # 1. 기존 엑셀에서 이미 수집된 채팅방 ID 목록 추출
        existing_chat_ids = set()
        if skip_existing_chats and os.path.exists(self.config.EXCEL_PATH):
            try:
                # 엑셀 전체를 읽지 않고 channel_id 컬럼만 읽어 속도 최적화
                temp_df = pd.read_excel(self.config.EXCEL_PATH, usecols=['channel_id'])
                existing_chat_ids = set(temp_df['channel_id'].unique())
                logger.info(f"기존 엑셀에서 {len(existing_chat_ids)}개의 채팅방 확인.")
            except Exception as e:
                logger.warning(f"기존 엑셀 로드 실패: {e}")

        dialogs = await self.client.get_dialogs()
        
        for dialog in dialogs:
            # 2. 엑셀에 이미 있는 방이면 건너뛰기
            if skip_existing_chats and dialog.id in existing_chat_ids:
                logger.info(f"===> [{dialog.name}] 이미 저장된 방이므로 스킵합니다.")
                continue

            if only_unread and dialog.unread_count == 0:
                continue

            room_name = dialog.name or "Unknown"
            curr_channel_id = dialog.id
            msg_limit = dialog.unread_count if only_unread else None
            
            logger.info(f"===> [{room_name}] 수집 시작 (ID: {curr_channel_id})")
            
            current_room_data = []
            async for m in self.client.iter_messages(dialog, limit=msg_limit):
                # 텍스트와 이미지 둘 다 없는 경우 스킵
                if not m.text and (not m.media or isinstance(m.media, MessageMediaWebPage)):
                    continue

                is_channel_post = bool(m.sender_id == curr_channel_id)
                sender_name = ""
                try:
                    sender = await m.get_sender()
                    if sender:
                        sender_name = getattr(sender, 'username', None) or \
                                      f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                except: pass

                # 이미지 다운로드 로직 호출
                img_path = await self.download_image(m)

                current_room_data.append({
                    'chat_name': room_name,
                    'channel_id': curr_channel_id,
                    'msg_id': m.id,
                    'sender_id': m.sender_id,
                    'is_channel_post': is_channel_post,
                    'sender_name': sender_name,
                    'content': (m.text or "").replace('\n', ' '),
                    'date': m.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'image_path': img_path
                })

                # 일정 주기마다 저장
                if len(current_room_data) >= self.config.SAVE_INTERVAL:
                    await storage.save_to_all(current_room_data)
                    current_room_data.clear()
                
                await asyncio.sleep(random.uniform(*self.config.DELAY_MSG))

            # 잔여 데이터 저장
            if current_room_data:
                await storage.save_to_all(current_room_data)
            
            logger.info(f"--- [{room_name}] 수집 완료")

async def main():
    config = Config()
    if not config.API_ID or not config.API_HASH:
        logger.error(".env 파일에 API_ID와 API_HASH를 설정해주세요.")
        return

    storage = DataStorage(config)
    crawler = TelegramCrawler(config)
    
    print("="*35)
    print(" 텔레그램 메시지 크롤러 (엑셀 중복방지 포함)")
    print("="*35)
    print("1. 전체 메시지 수집 (기존 방 제외)")
    print("2. 안 읽은 메시지만 수집")
    print("="*35)
    choice = input("모드를 선택하세요 (1/2): ")
    
    only_unread = True if choice == "2" else False
    # 1번 선택 시 기존 엑셀에 있는 방은 아예 스킵합니다.
    skip_existing = True if choice == "1" else False

    async with crawler.client:
        await crawler.run_scan(storage, only_unread=only_unread, skip_existing_chats=skip_existing)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n사용자에 의해 종료되었습니다.")