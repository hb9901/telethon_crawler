import os
import random
import socks
import sqlite3
import asyncio
import pandas as pd
from telethon import TelegramClient
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

class TelegramScraper:
    def __init__(self):
        # 1. 기본 설정 (환경변수)
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        
        # 2. 크롤링 옵션 (실행 시 할당)
        self.target_id = None
        self.keyword = ""
        self.limit = 100
        self.download_images = False
        
        # 3. 경로 및 파일 설정
        self.db_path = 'telegram_result.db'
        self.img_dir = 'downloaded_photos'
        
        # 4. 프록시 및 클라이언트 초기화
        self.proxy = self._setup_proxy()
        self.client = TelegramClient('scraper_session', self.api_id, self.api_hash, proxy=self.proxy)

    def _setup_proxy(self):
        """프록시 리스트에서 무작위 선택 및 설정"""
        proxy_env = os.getenv('PROXY_LIST', '').strip()
        if not proxy_env:
            print("🌐 프록시 미설정: 직접 연결 모드로 진행합니다.")
            return None
        try:
            proxies = [p.strip() for p in proxy_env.split(',') if p.strip()]
            choice = random.choice(proxies).split(':')
            config = {
                'proxy_type': socks.SOCKS5,
                'addr': choice[0],
                'port': int(choice[1]),
                'rdns': True
            }
            if len(choice) == 4:
                config['username'], config['password'] = choice[2], choice[3]
            print(f"📡 프록시 적용: {config['addr']}:{config['port']}")
            return config
        except Exception:
            print("⚠️ 프록시 설정 형식이 올바르지 않습니다. 직접 연결을 시도합니다.")
            return None

    async def ensure_connection(self):
        """서버 연결 및 로그인 상태 확인"""
        if not self.client.is_connected():
            await self.client.connect()
        if not await self.client.is_user_authorized():
            print("🔑 첫 실행: 인증이 필요합니다.")
            await self.client.start()
            print("✅ 인증 성공!")

    def _ask_user_options(self, include_id=False):
        """사용자로부터 수집 조건 입력받기"""
        print("\n" + "─"*30 + "\n[ 수집 옵션 설정 ]")
        
        if include_id:
            while True:
                val = input("🆔 대상 채팅방 ID: ").strip()
                if val:
                    try: self.target_id = int(val); break
                    except ValueError: print("❌ ID는 숫자로 입력해주세요.")
                else: print("❌ ID 입력은 필수입니다.")

        self.keyword = input("🔍 필터링 키워드 (엔터 시 전체): ").strip().lower()
        
        lim = input("📊 수집 개수 (기본 100): ").strip()
        self.limit = int(lim) if lim.isdigit() else 100
        
        dl = input("📸 이미지 다운로드? (y/n, 기본 n): ").strip().lower()
        self.download_images = True if dl == 'y' else False
        print("─"*30)

    async def _fetch_messages(self, entity, chat_name):
        """실제 메시지 수집 로직 (메서드 분리)"""
        try:
            messages = await self.client.get_messages(entity, limit=self.limit)
            rows = []
            for m in messages:
                text = m.text if m.text else ""
                if self.keyword and self.keyword not in text.lower():
                    continue

                img_val = "No Image"
                if m.photo:
                    if self.download_images:
                        if not os.path.exists(self.img_dir): os.makedirs(self.img_dir)
                        img_val = await self.client.download_media(m.photo, file=os.path.join(self.img_dir, f"{m.id}.jpg"))
                    else:
                        img_val = f"PhotoID:{m.photo.id}"

                rows.append({
                    'chat_name': chat_name,
                    'msg_id': m.id,
                    'content': text.replace('\n', ' '),
                    'date': m.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'image': img_val
                })
            return rows
        except Exception as e:
            print(f"⚠️ {chat_name} 수집 중 오류: {e}")
            return []

    def _save_to_db(self, data):
        """데이터를 SQLite DB에 저장"""
        if not data:
            print("ℹ️ 수집된 데이터가 없어 저장을 건너뜁니다.")
            return
        
        df = pd.DataFrame(data)
        with sqlite3.connect(self.db_path) as conn:
            df.to_sql('messages', conn, if_exists='replace', index=False)
        print(f"💾 저장 완료: {len(data)}건 ({self.db_path})")

    # --- 실행 기능들 ---

    async def cmd_show_list(self):
        """기능 1: 대화방 리스트 확인"""
        await self.ensure_connection()
        print(f"\n{'[ 대화방 이름 ]':<25} | {'[ ID ]'}")
        print("─"*50)
        async for d in self.client.iter_dialogs():
            print(f"{str(d.name)[:25]:<25} | {d.id}")
        print("─"*50)

    async def cmd_single_scrape(self):
        """기능 2: 특정 방 크롤링"""
        await self.ensure_connection()
        self._ask_user_options(include_id=True)
        try:
            ent = await self.client.get_entity(self.target_id)
            title = getattr(ent, 'title', 'Private Chat')
            print(f"🚀 [{title}] 크롤링 중...")
            data = await self._fetch_messages(ent, title)
            self._save_to_db(data)
        except Exception as e:
            print(f"❌ 해당 ID를 찾을 수 없습니다: {e}")

    async def cmd_all_scrape(self):
        """기능 3: 전체 크롤링"""
        await self.ensure_connection()
        self._ask_user_options(include_id=False)
        print("🚀 전체 대화방 수집을 시작합니다...")
        
        all_results = []
        async for d in self.client.iter_dialogs():
            print(f"🔄 [{d.name}] 읽는 중...")
            all_results.extend(await self._fetch_messages(d.id, d.name))
        
        self._save_to_db(all_results)

# --- 메인 메뉴 컨트롤러 ---
async def main():
    app = TelegramScraper()
    while True:
        print("\n" + "■"*30)
        print("   TELEGRAM CRAWLER V2.0")
        print("   1. 대화방 리스트/ID 확인")
        print("   2. 선택 채팅방 크롤링")
        print("   3. 전체 채팅방 크롤링")
        print("   0. 프로그램 종료")
        print("■"*30)
        
        menu = input("👉 선택: ").strip()
        
        if menu == '1': await app.cmd_show_list()
        elif menu == '2': await app.cmd_single_scrape()
        elif menu == '3': await app.cmd_all_scrape()
        elif menu == '0': break
        else: print("❌ 메뉴 번호를 다시 확인해주세요.")
    
    if app.client.is_connected():
        await app.client.disconnect()
    print("👋 프로그램을 종료합니다.")

if __name__ == "__main__":
    asyncio.run(main())