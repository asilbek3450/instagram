# 🗺️ Instagram Analytics Pro — Real API Ulash Roadmap

Hozirda loyiha **simulyatsiya (mock) ma'lumotlar** bilan ishlaydi.
Quyidagi yo'l xaritasi orqali **real Instagram API** ga ulanish mumkin.

---

## ✅ To'g'ri Havola

**Instagram API with Instagram Login:**
> https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login

Bu **yangi va tavsiya etilgan** API uslubi. Facebook Page talab qilmaydi.
Creator va Business akkauntlarga to'liq mos keladi.

---

## 📋 5 Bosqich

---

### BOSQICH 1 — Meta Developer App yaratish

1. **https://developers.facebook.com** ga kiring
2. **"My Apps"** → **"Create App"** bosing
3. App type: **"Other"** → **"Business"** tanlang
4. App nomini kiriting (masalan: `InstaTrack Pro`)
5. Quyidagilarni oling va `config.py` ga saqlang:

```
INSTAGRAM_APP_ID     = 1033098339148001
INSTAGRAM_APP_SECRET =  "5b237e92362802c51dbc1eb21521f41b"
INSTAGRAM_REDIRECT_URI = "https://yoursite.com/auth/instagram/callback"
```

---

### BOSQICH 2 — Instagram Product va Ruxsatlar

App sozlamalarida:
1. **"Add Product"** → **"Instagram"** tanlang
2. **"Instagram Login for Business"** ni yoqing
3. **"Permissions"** bo'limida quyidagilarni qo'shing:

| Scope (Ruxsat) | Nima uchun kerak |
|---|---|
| `instagram_business_basic` | Profil, followers, bio ma'lumotlari |
| `instagram_business_content_publish` | Post joylash |
| `instagram_business_manage_comments` | Izohlarni o'qish va boshqarish |

> **Eslatma:** Analytics uchun faqat `instagram_business_basic` yetarli.

---

### BOSQICH 3 — OAuth 2.0 Login Oqimi

Foydalanuvchi **"Instagram bilan kirish"** bosganida quyidagi oqim ishlaydi:

```
1. Foydalanuvchi → sizning saytga keladi
2. Sizning sayt → Instagram OAuth sahifasiga yo'naltiradi:

   https://www.instagram.com/oauth/authorize
     ?client_id=YOUR_APP_ID
     &redirect_uri=https://yoursite.com/auth/instagram/callback
     &scope=instagram_business_basic,instagram_business_manage_comments
     &response_type=code

3. Foydalanuvchi ruxsat beradi (Allow bosadi)
4. Instagram → sizga "code" qaytaradi (redirect_uri orqali)

5. Backend: code → access_token ga almashtiradi:
   POST https://api.instagram.com/oauth/access_token
     {
       client_id, client_secret,
       redirect_uri, code,
       grant_type: "authorization_code"
     }

6. access_token olinadi → ma'lumotlar so'raladi
```

**Flask'da bu endpoint taxminan shunday ko'rinadi:**

```python
# app/routes/auth.py

@auth_bp.route('/instagram/callback')
def instagram_callback():
    code = request.args.get('code')
    # code bilan access_token so'raladi
    response = requests.post('https://api.instagram.com/oauth/access_token', data={
        'client_id': Config.INSTAGRAM_APP_ID,
        'client_secret': Config.INSTAGRAM_APP_SECRET,
        'redirect_uri': Config.INSTAGRAM_REDIRECT_URI,
        'code': code,
        'grant_type': 'authorization_code'
    })
    token_data = response.json()
    access_token = token_data['access_token']
    instagram_user_id = token_data['user_id']
    # access_token ni bazaga saqlang
    ...
```

---

### BOSQICH 4 — Real Ma'lumotlarni So'rash

`access_token` bilan Instagram Graph API so'rovlari:

```python
import requests

BASE = "https://graph.instagram.com"

# 1. Profil ma'lumotlari
def get_profile(token):
    url = f"{BASE}/me"
    params = {
        "fields": "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url",
        "access_token": token
    }
    return requests.get(url, params=params).json()

# 2. Postlar ro'yxati
def get_media(token):
    url = f"{BASE}/me/media"
    params = {
        "fields": "id,caption,like_count,comments_count,timestamp,media_type,media_url,permalink",
        "access_token": token
    }
    return requests.get(url, params=params).json()

# 3. Post bo'yicha insights (statistika)
def get_media_insights(media_id, token):
    url = f"{BASE}/{media_id}/insights"
    params = {
        "metric": "impressions,reach,engagement,saved",
        "access_token": token
    }
    return requests.get(url, params=params).json()

# 4. Akkaunt insights
def get_account_insights(ig_user_id, token):
    url = f"{BASE}/{ig_user_id}/insights"
    params = {
        "metric": "follower_count,impressions,reach,profile_views",
        "period": "day",
        "access_token": token
    }
    return requests.get(url, params=params).json()
```

---

### BOSQICH 5 — App Review (Boshqalarga ochish)

| Holat | Kimlar foydalana oladi |
|---|---|
| **Development mode** | Faqat siz va qo'shilgan test foydalanuvchilar (max 5) |
| **App Review o'tgan** | Istalgan Instagram foydalanuvchi |

**Review uchun talab qilinadigan narsalar:**
1. ✅ Privacy Policy URL (maxfiylik siyosati sahifasi)
2. ✅ Terms of Service URL
3. ✅ Video demo (app qanday ishlashini ko'rsatadi)
4. ✅ Ruxsatlar nima uchun kerakligi izohi

**Hujjatlar:**
- App Review: https://developers.facebook.com/docs/instagram-platform/app-review
- Privacy Policy Generator: https://www.privacypolicygenerator.info

---

## ⚠️ Muhim Cheklovlar

| Cheklov | Qiymat |
|---|---|
| Soatlik so'rovlar limiti | 200 so'rov (token boshiga) |
| Insights ko'rish | Faqat **o'z** akkauntingiz |
| Boshqa akkaunt tahlili | **Ruxsatga ega bo'lmasangiz mumkin emas** |
| Followerlar ro'yxati | API tomonidan **ta'qiqlangan** (privacy) |

---

## 🔧 Loyihada Amalga Oshirish Rejasi

Hozir `app/services/instagram_service.py` mock ma'lumotlar qaytaradi.
Real API ga ulash uchun quyidagi fayllar yangilanishi kerak:

```
config.py
  └─ INSTAGRAM_APP_ID, APP_SECRET, REDIRECT_URI qo'shish

app/routes/auth.py
  └─ /instagram/login endpoint (OAuth redirect)
  └─ /instagram/callback endpoint (token olish)

app/models/user.py yoki instagram_account.py
  └─ instagram_access_token ustuni qo'shish

app/services/instagram_service.py
  └─ mock ma'lumotlar → real API so'rovlari
  └─ token bilan Graph API chaqiruvi
```

---

## 🆚 Qaysi API Tanlanishi Kerak?

| | Instagram API with **Instagram Login** | Instagram API with **Facebook Login** |
|---|---|---|
| Facebook Page kerakmi? | ❌ Yo'q | ✅ Ha |
| Murakkablik | Oddiyroq | Murakkabroq |
| Tavsiya | ✅ **Tavsiya etiladi** | Eski usul |
| Hujjat havolasi | [Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login) | [Facebook Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login) |

---

> **Xulosa:** Siz ko'rsatgan havola (`instagram-api-with-instagram-login`) **to'g'ri va eng yangi** usul.
> Loyihani real API ga ulashga tayyor bo'lganingizda, `BOSQICH 1`dan boshlang.
