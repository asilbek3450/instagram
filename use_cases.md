# Instagram Analytics Pro - Loyiha Use Case'lari va Ishlash Mexanizmi

Ushbu hujjat **Instagram Analytics Pro** loyihasining qanday ishlashi va undagi asosiy foydalanish holatlari (use cases) haqida batafsil ma'lumot beradi. Loyiha asosan Instagram akkauntlarining statistikasini tahlil qilish, sun'iy intellekt orqali o'sishni bashorat qilish va kontent bo'yicha maslahatlar berish uchun mo'ljallangan.

---

## 1. Foydalanuvchi Autentifikatsiyasi va Profil
Foydalanuvchilar tizimdan foydalanishni boshlashi uchun ro'yxatdan o'tishlari kerak.

* **Ro'yxatdan o'tish (Register):** Yangi foydalanuvchi email va parol kiritish orqali ro'yxatdan o'tadi. Shuningdek, tizimda oddiy `user` yoki `admin` rolini tanlashi mumkin.
* **Tizimga kirish (Login):** Foydalanuvchi email va paroli orqali tizimga kiradi. Tizim JWT (JSON Web Token) yaratadi va xavfsiz seansni (session) boshlaydi.
* **Profilni tahrirlash:** Foydalanuvchi o'z profiliga kirib, parolini yoki email manzilini yangilashi, shuningdek elektron pochtani tasdiqlash (verify) jarayonidan o'tishi mumkin.

---

## 2. Instagram Akkauntni Ulash va Boshqarish
Tizimning asosiy vazifasi ulangan akkaunt ma'lumotlarini tahlil qilishdir. Demo versiyada ma'lumotlar simulyatsiya qilinadi.

* **Akkaunt ulash (Link Account):** Foydalanuvchi o'zining yoki tahlil qilmoqchi bo'lgan istalgan Instagram username'ini kiritadi. Backend (InstagramService) ushbu akkaunt uchun simulyatsiya qilingan (yoki kelajakda real API orqali) barcha postlar, followerlar tarixi va izohlarni generatsiya qiladi.
* **Akkauntlar o'rtasida o'tish:** Agar foydalanuvchi bir nechta akkaunt ulagan bo'lsa (masalan, SMM mutaxassislari uchun), yuqori panel (header) dagi dropdown orqali akkauntlar o'rtasida tezkor almashinishi mumkin. Barcha ma'lumotlar tanlangan akkauntga qarab yangilanadi.
* **Akkauntni o'chirish (Disconnect):** Profil sozlamalari orqali ulangan akkauntni o'chirib tashlash mumkin. Bunda tizim ushbu akkauntga tegishli keshlangan ma'lumotlarni tozalaydi.

---

## 3. Asosiy Dashboard (Dashboard)
Foydalanuvchi akkauntni tanlagandan so'ng, asosiy holatni ko'rsatuvchi oyna.

* **KPI Metrikalari:** Jami obunachilar (Followers), jalb qilish darajasi (Engagement Rate), qamrov (Reach) va taassurotlar (Impressions) raqamlarda va ularning o'tgan oydagi o'sish/tushish tendensiyasi ko'rsatiladi.
* **O'sish tarixi (Followers History):** Oxirgi 7, 15 yoki 30 kun ichidagi obunachilar o'sishini ko'rsatuvchi interaktiv chiziqli grafika (Line chart).
* **Top Postlar:** Eng ko'p layk va izoh yig'gan postlar qisqacha ro'yxati.
* **AI Copilot (Qisqacha):** Sun'iy intellekt tomonidan hisoblangan qisqacha holat, masalan, eng yaxshi post joylash vaqti va o'sish kayfiyati.

---

## 4. Auditoriya va Demografiya (Followers)
Akkaunt obunachilari haqida batafsil ma'lumot beruvchi bo'lim.

* **Yosh va Jins tahlili:** Obunachilarning necha foizi erkak yoki ayol ekanligi va qaysi yosh toifasiga (masalan, 18-24, 25-34) kirishi grafiklar (Doughnut va Bar chart) orqali ko'rsatiladi.
* **Geografik joylashuv:** Obunachilarning qaysi davlatlar va shaharlardan ekanligi foizlarda va progress barlar orqali ro'yxat tarzida taqdim etiladi.

---

## 5. Kontent Analitikasi (Posts & Stories)
Joylashtirilgan kontentlarning samaradorligini o'lchash.

* **Postlar tahlili:** Barcha postlar (rasm, video/reel, karusel) ro'yxati ko'rsatiladi. Foydalanuvchi post formatiga qarab filtrlashi mumkin. Grafika orqali oxirgi postlarning layklar va izohlar nisbati (Double bar chart) tahlil qilinadi.
* **Story'lar tahlili (Stories):** 24 soat ichida qo'yilgan story'lar haqida ma'lumot. Har bir story'ning ko'rishlar soni, oxirigacha ko'rish darajasi (Completion rate) hamda foydalanuvchilarning story'dan chiqib ketish (Exit) yoki oldinga o'tkazish (Tap forward) ko'rsatkichlari beriladi.

---

## 6. Izohlar va Sentiment (Comments & Sentiment)
Postlarga yozilgan izohlarni AI yordamida chuqur tahlil qilish.

* **Hissiyotlar tahlili (Sentiment Analysis):** Barcha izohlar uch toifaga ajratiladi: Ijobiy (Positive), Neytral (Neutral) va Salbiy (Negative).
* **Spam filtri:** Tarkibida turli xil havolalar (linklar), kripto-reklamalar yoki botlar yozgan shubhali izohlar "Spam" sifatida belgilanadi.
* **Audit jurnali:** Barcha izohlar jadvali. Foydalanuvchi izohlarni faqat ijobiylar, faqat salbiylar yoki faqat spamlar bo'yicha filtrlashi mumkin.

---

## 7. Sun'iy Intellekt Yordamchisi (AI Assistant)
Kontent yaratuvchilarga to'g'ri strategiya ishlab chiqishda yordam beruvchi AI qurollari.

* **O'sishni bashorat qilish (Growth Forecast):** Mavjud o'sish tendensiyasi va interaksiyalarga asoslanib, kelgusi 7 kun ichida qancha obunachi qo'shilishi prognoz qilinadi.
* **Ideal post vaqtlari:** Foydalanuvchilar eng faol bo'ladigan haftaning qaysi kuni va soatlarida post joylash tavsiya etilishi ko'rsatiladi.
* **Kontent g'oyalari:** Niche (soha) ga mos keladigan post va video (reel) mavzulari bo'yicha maslahatlar.
* **Hashtag generatori:** Foydalanuvchi o'z postining asosiy so'zini kiritganda, tizim ommabop va trendga chiqqan hashtaglar to'plamini shakllantirib beradi. Nusxa olish (Copy) tugmasi mavjud.

---

## 8. PDF/CSV Hisobotlar (Reports)
Ma'lumotlarni arxivlash yoki mijozlarga taqdim etish uchun hisobotlar yaratish.

* **Hisobot generatsiya qilish:** Foydalanuvchi tanlangan akkaunt bo'yicha oylik yoki haftalik hisobot yaratishni so'raydi.
* **Background Worker (Celery):** Hisobotlar asosiy tizimni sekinlashtirmasligi uchun orqa fonda (Celery worker orqali) generatsiya qilinadi.
* **Yuklab olish (Download):** Jarayon yakunlangach, jadvalda "Completed" statusi va faylni yuklab olish uchun havola paydo bo'ladi.

---

## 9. Administrator Paneli (Admin Console)
Tizimni boshqarish faqat `admin` roliga ega foydalanuvchilarga ruxsat etiladi.

* **Tizim holati (System Status):** Serverdagi Python versiyasi, ma'lumotlar bazasi va Redis/Celery holati, shuningdek jami ro'yxatdan o'tgan foydalanuvchilar va akkauntlar soni kabi statistika ko'rsatiladi.
* **Foydalanuvchilarni boshqarish:** Barcha foydalanuvchilar ro'yxati. Admin ularning ruxsatlarini (role) o'zgartirishi yoki akkauntlarini o'chirib yuborishi mumkin.
* **Audit loglar (System Logs):** Tizimda sodir bo'layotgan jarayonlar (masalan, kim logindan o'tdi, qachon hisobot tayyorlandi) terminal ko'rinishidagi oynada aks etadi.

---

## Xulosa
Bu funksiyalarning barchasi zamonaviy UI/UX (Glassmorphism, Dark/Light theme) bilan jihozlangan va Bootstrap 5 hamda Chart.js yordamida interaktiv qilib yasalgan. Backend'da Flask arxitekturasi va REST API xizmat ko'rsatsa, ma'lumotlar Postgres va SQLite (simulyatsiya uchun) orqali boshqariladi.
