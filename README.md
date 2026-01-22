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
3. 발행된 **App api_id**와 **App api_hash**를 기록해 둡니다. 

---

## 3. 환경변수 설정

프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래 형식을 참고하여 내용을 입력합니다.


### .env 파일 설정 예시
```text
API_ID=발급받은 api_id
API_HASH=발급받은 api_hash

#프록시 사용시 작성
PROXY_LIST=xxx.xxx.xx.xxx:xxxx, xxxx.xxx.xx.xxx:xxxx:user1:pw1
```
---

## 4. 실행 

정상적으로 실행이 되었다면 아래와 같은 화면을 보게 됩니다.
<br/>
<img width="227" height="135" alt="image" src="https://github.com/user-attachments/assets/9c640e83-a990-4ea9-928b-dcb3858d4efb" />

1. 대화방 리스트/ID 확인
  - 사용자가 속한 대화방에 대한 ID를 확인할 수 있습니다.
2. 선택 채팅방 크롤링
  - 특정 대화방의 대화 내역을 크롤링 할 수 있습니다.
  - 대화 내역을 크롤링 하기 위해서는 1번에서 대화방에 대한 ID를 확인해야 합니다.
  - 수집 옵션은 다음과 같습니다.
    - 필터링 키워드
    - 수집 개수
    - 이미지 다운로드 여부 
3. 전체 채팅방 크롤링
  - 사용자가 속한 모든 대화방의 채팅 내역을 수집합니다.
  - 수집 옵션은 다음과 같습니다.
    - 필터링 키워드
    - 수집 개수
    - 이미지 다운로드 여부
0. 프로그램 종료
   - 프로그램을 종료합니다.

## 5. 결과 확인

모든 설정이 완료되었다면 터미널에서 메인 크롤러 스크립트(telethon_message_crawler.py)를 실행합니다.

### 결과물 확인
* **telegram_result.db**: 수집된 메시지의 ID, 텍스트 내용, 날짜, 이미지 저장 경로(또는 정보)가 열 순서대로 정리된 db 파일입니다.
* **downloaded_photos/**: 메시지에 포함된 사진 파일들이 저장되는 폴더입니다.  
  *(※ .env 파일의 `DOWNLOAD_IMAGES`가 `True`일 경우에만 사진이 저장됩니다.)*

---

