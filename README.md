# Telegram Message Crawler (Telethon)

텔레그램 채널의 메시지를 키워드로 필터링하여 수집하고, 이미지와 함께 엑셀 파일로 정리해주는 크롤러입니다.

---

## 1. 시작하기

이 프로젝트를 실행하기 위해 필요한 라이브러리를 설치합니다.

```bash
pip install telethon pandas python-dotenv 
```

프록시를 사용한다면 아래 라이브러리도 설치합니다

```bash
pip install PySocks
```

## 2. 텔레그램 API 발행

스크립트를 사용하기 위해서는 텔레그램 API 권한이 필요합니다.
1. [my.telegram.org](https://my.telegram.org/)에 접속하여 로그인합니다.
2. **API development tools**에 들어가서 새로운 애플리케이션을 생성합니다.
3. 발행된 **App api_id**와 **App api_hash**를 안전한 곳에 기록해두세요.

---

## 3. 환경변수 설정

프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래 형식을 참고하여 내용을 입력합니다.


### .env 파일 설정 예시
```text
API_ID=발급받은 api_id
API_HASH=발급받은 api_hash
```
---

## 4. 실행 및 결과 확인

모든 설정이 완료되었다면 터미널에서 메인 크롤러 스크립트(telethon_message_crawler.py)를 실행합니다.

### 결과물 확인
* **telegram_result.db**: 수집된 메시지의 ID, 텍스트 내용, 날짜, 이미지 저장 경로(또는 정보)가 열 순서대로 정리된 db 파일입니다.
* **downloaded_photos/**: 메시지에 포함된 사진 파일들이 저장되는 폴더입니다.  
  *(※ .env 파일의 `DOWNLOAD_IMAGES`가 `True`일 경우에만 사진이 저장됩니다.)*

---

