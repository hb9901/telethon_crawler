import os
import random
import socks
import sqlite3
import asyncio
import pandas as pd
import logging
from dataclasses import dataclass
from telethon import TelegramClient
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)
load_dotenv()

@dataclass
class Config:
    API_ID: int = int(os.getenv('API_ID', 0))
    API_HASH: str = os.getenv('API_HASH', '')
    PROXY_LIST: str = os.getenv('PROXY_LIST', '')
    DB_PATH: str = 'telegram_result.db'
    EXCEL_PATH: str = 'telegram_result.xlsx'
    IMG_DIR: str = 'downloaded_photos'
    
    # 딜레이 설정 (수정됨)
    DELAY_MSG_MIN: float = 0.2
    DELAY_MSG_MAX: float = 0.5
    DELAY_CHUNK: float = 1.0    # 5.0 -> 1.0초로 변경
    DELAY_IMAGE: float = 0.5    # 1.5 -> 0.5초로 변경
    # DELAY_ROOM 설정 삭제됨

class DataStorage:
    def __init__(self, config: Config):
        self.config = config

    def save(self, data):
        if not data: return
        df = pd.DataFrame(data)
        
        try:
            with sqlite3.connect(self.config.DB_PATH) as conn:
                df.to_sql('messages', conn, if_exists='append', index=False)
            logger.info(f"[SAVE] DB Saved: {len(data)} items")
        except Exception as e:
            logger.error(f"[ERROR] DB Error: {e}")

        try:
            if os.path.exists(self.config.EXCEL_PATH):
                existing = pd.read_excel(self.config.EXCEL_PATH)
                combined = pd.concat([existing, df], ignore_index=True)
                combined.to_excel(self.config.EXCEL_PATH, index=False)
            else:
                df.to_excel(self.config.EXCEL_PATH, index=False)
            logger.info(f"[SAVE] Excel Saved")
        except Exception as e:
            logger.error(f"[ERROR] Excel Error: {e}")

class TelegramCrawler:
    def __init__(self, config: Config):
        self.config = config
        self.client = TelegramClient('scraper_session', config.API_ID, config.API_HASH, proxy=self._get_proxy())

    def _get_proxy(self):
        if not self.config.PROXY_LIST: 
            logger.warning("[PROXY] No Proxy Set (Direct Connection)")
            return None
        try:
            proxies = [p.strip() for p in self.config.PROXY_LIST.split(',') if p.strip()]
            choice = random.choice(proxies).split(':')
            proxy = {
                'proxy_type': socks.SOCKS5,
                'addr': choice[0],
                'port': int(choice[1]),
                'rdns': True
            }
            if len(choice) == 4:
                proxy['username'], proxy['password'] = choice[2], choice[3]
            logger.info(f"[PROXY] Connected: {choice[0]}")
            return proxy
        except: 
            logger.error("[ERROR] Proxy Config Error")
            return None

    async def start(self):
        await self.client.start()

    async def run_full_scan(self, storage):
        if not os.path.exists(self.config.IMG_DIR):
            os.makedirs(self.config.IMG_DIR)

        async for dialog in self.client.iter_dialogs():
            # 안전한 출력을 위해 채팅방 이름 인코딩 처리 시도
            safe_name = dialog.name.encode('utf-8', 'ignore').decode('utf-8')
            logger.info(f"--------------------------------------------------")
            logger.info(f"[START] Processing Room: {safe_name}")
            
            data = []
            count = 0

            try:
                async for m in self.client.iter_messages(dialog.entity, limit=None):
                    img_path = "No Image"
                    
                    if m.photo:
                        fpath = os.path.join(self.config.IMG_DIR, f"{m.id}.jpg")
                        if not os.path.exists(fpath):
                            try:
                                await self.client.download_media(m.photo, file=fpath)
                                await asyncio.sleep(self.config.DELAY_IMAGE) # 0.5초 대기
                            except Exception:
                                pass # 이미지 다운 실패시 무시
                        img_path = fpath

                    data.append({
                        'chat': dialog.name,
                        'id': m.id,
                        'text': (m.text or "").replace('\n', ' '),
                        'date': m.date.strftime('%Y-%m-%d %H:%M:%S'),
                        'image': img_path
                    })

                    count += 1
                    await asyncio.sleep(random.uniform(self.config.DELAY_MSG_MIN, self.config.DELAY_MSG_MAX))
                    
                    if count % 100 == 0:
                        logger.info(f"[INFO] Collected {count} messages... (Resting)")
                        await asyncio.sleep(self.config.DELAY_CHUNK) # 1.0초 대기

                storage.save(data)
                
                # [삭제됨] 방 변경 대기 로직 (DELAY_ROOM) 제거 완료
                # 바로 다음 방으로 넘어갑니다.

            except Exception as e:
                logger.error(f"[ERROR] In Room {safe_name}: {e}")

async def main():
    print("[SYSTEM] Crawler Started...")
    config = Config()
    storage = DataStorage(config)
    crawler = TelegramCrawler(config)
    
    await crawler.start()
    await crawler.run_full_scan(storage)
    await crawler.client.disconnect()
    print("[SYSTEM] Finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass