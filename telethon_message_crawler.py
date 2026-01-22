import os
import random
import socks
import pandas as pd
import asyncio
import sqlite3  # SQLite 사용을 위해 추가
from telethon import TelegramClient
from dotenv import load_dotenv
from datetime import datetime

# .env 로드
load_dotenv()

class TelegramScraper:
    def __init__(self):
        # 1. 환경 변수 로드 및 설정
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.channel_id = int(os.getenv('CHANNEL_ID'))
        self.keyword = os.getenv('KEYWORD', '').strip().lower()
        self.limit = int(os.getenv('LIMIT', 100))
        self.download_images = os.getenv('DOWNLOAD_IMAGES', 'False').lower() == 'true'
        
        self.download_path = 'downloaded_photos'
        self.db_filename = 'telegram_result.db'  # 엑셀 대신 .db 확장자 사용
        
        # 2. 프록시 및 클라이언트 초기화
        self.proxy = self._get_proxy_config()
        self.client = TelegramClient('session_name', self.api_id, self.api_hash, proxy=self.proxy)

    def _get_proxy_config(self):
        """.env에서 프록시 설정을 읽어 딕셔너리로 반환"""
        proxy_env = os.getenv('PROXY_LIST', '').strip()
        if not proxy_env:
            print("🌐 프록시 설정 없음: 직접 연결 모드")
            return None

        try:
            proxies = [p.strip() for p in proxy_env.split(',') if p.strip()]
            target = random.choice(proxies)
            parts = target.split(':')
            
            if len(parts) < 2:
                return None

            config = {
                'proxy_type': socks.SOCKS5,
                'addr': parts[0],
                'port': int(parts[1]),
                'rdns': True
            }
            if len(parts) == 4:
                config['username'], config['password'] = parts[2], parts[3]
            
            print(f"📡 프록시 선택됨: {config['addr']}:{config['port']}")
            return config
        except Exception as e:
            print(f"⚠️ 프록시 파싱 에러: {e}")
            return None

    async def download_photo(self, message):
        """사진 다운로드 처리"""
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
        
        file_path = os.path.join(self.download_path, f"{message.id}.jpg")
        return await self.client.download_media(message.photo, file=file_path)

    async def run(self):
        """메인 실행 로직"""
        try:
            print("🔗 텔레그램 연결 중...")
            await self.client.connect()

            if not await self.client.is_user_authorized():
                print("❌ 인증되지 않은 계정입니다. 로그인이 필요합니다.")
                return

            print(f"🔎 채널({self.channel_id}) 데이터 추출 시작...")
            entity = await self.client.get_entity(self.channel_id)
            messages = await self.client.get_messages(entity, limit=self.limit)

            data = []
            for msg in messages:
                content = msg.text if msg.text else ""
                if self.keyword and self.keyword not in content.lower():
                    continue

                img_info = "No Image"
                if msg.photo:
                    if self.download_images:
                        img_info = await self.download_photo(msg)
                    else:
                        img_info = f"PhotoID:{msg.photo.id}"

                data.append({
                    'message_id': msg.id,  # DB 컬럼명 관례상 소문자/언더바 추천
                    'content': content.replace('\n', ' '),
                    'created_at': msg.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'image_info': img_info
                })

            # 데이터 저장 (SQLite)
            if data:
                df = pd.DataFrame(data)
                
                # DB 연결 (파일이 없으면 자동 생성됨)
                conn = sqlite3.connect(self.db_filename)
                
                # pandas를 이용해 테이블로 저장
                # if_exists='replace': 실행 시마다 테이블 초기화 후 저장
                # if_exists='append': 실행 시마다 기존 데이터 뒤에 추가
                df.to_sql('messages', conn, if_exists='replace', index=False)
                
                conn.close()
                print(f"✅ 완료! {len(data)}개의 메시지가 {self.db_filename}의 'messages' 테이블에 저장되었습니다.")
            else:
                print("ℹ️ 조건에 맞는 메시지가 없습니다.")

        except Exception as e:
            print(f"❌ 실행 중 오류 발생: {e}")
        finally:
            await self.client.disconnect()

# 실행부
if __name__ == "__main__":
    scraper = TelegramScraper()
    with scraper.client:
        scraper.client.loop.run_until_complete(scraper.run())