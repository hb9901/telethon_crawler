import os
import pandas as pd
from telethon import TelegramClient
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 가져오기 및 형변환
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
KEYWORD = os.getenv('KEYWORD', '').strip()
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
LIMIT = int(os.getenv('LIMIT', 100))

# 불리언형 환경 변수 처리
DOWNLOAD_IMAGES_STR = os.getenv('DOWNLOAD_IMAGES', 'False').strip().lower()
DOWNLOAD_IMAGES = DOWNLOAD_IMAGES_STR == 'true'

DOWNLOAD_PATH = 'downloaded_photos'
EXCEL_FILENAME = 'telegram_result.xlsx'

client = TelegramClient('session_name', API_ID, API_HASH)

# --- 함수 분리: 사진 저장 로직 ---
async def download_photo_media(message, folder):
    if not os.path.exists(folder):
        os.makedirs(folder)
    # 파일명을 메시지 ID로 저장하여 중복 방지
    path = await client.download_media(message.photo, file=os.path.join(folder, f"{message.id}.jpg"))
    return path

# --- 메인 로직 ---
async def main():
    channel = await client.get_entity(CHANNEL_ID)
    
    # .env에서 가져온 LIMIT 값을 사용
    print(f"🔎 최근 {LIMIT}개의 메시지를 확인합니다...")
    messages = await client.get_messages(channel, limit=LIMIT)
    
    data_list = []

    for message in messages:
        # 키워드 필터링 로직
        is_keyword_match = not KEYWORD or (message.text and KEYWORD.lower() in message.text.lower())

        if is_keyword_match:
            img_info = "No Image"
            
            if message.photo:
                if DOWNLOAD_IMAGES:
                    print(f"📸 사진 다운로드 중 (메시지 ID: {message.id})...")
                    img_info = await download_photo_media(message, DOWNLOAD_PATH)
                else:
                    photo = message.photo
                    img_info = f"PhotoID:{photo.id} | AccessHash:{photo.access_hash}"

            data_list.append({
                'ID': message.id,
                'Text': (message.text or "").replace('\n', ' '),
                'Date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                'Image': img_info
            })

    # 데이터프레임 생성 및 엑셀 저장
    df = pd.DataFrame(data_list)
    df.to_excel(EXCEL_FILENAME, index=False)
    
    print(f"\n" + "="*30)
    print(f"✅ 작업 완료!")


with client:
    client.loop.run_until_complete(main())