# NPS Chatbot

Banka müşteri NPS yorumlarını analiz eden, kategori/segment/duygu bazlı sorgulara cevap veren chatbot sistemi.

---

## Mac'te Çalıştırmak İçin

```bash
# 1. Repoyu klonla
git clone https://github.com/itu-itis22-kombak22/nps-chatbot.git
cd nps-chatbot

# 2. Sanal ortam oluştur ve aktive et
python3 -m venv venv
source venv/bin/activate

# 3. Bağımlılıkları kur
pip install -r requirements.txt

# 4. Uygulamayı başlat
streamlit run ui/app.py
```

Tarayıcı otomatik açılmazsa: **http://localhost:8501**

---

## Windows'ta Çalıştırmak İçin

```bash
# 1. Repoyu klonla
git clone https://github.com/itu-itis22-kombak22/nps-chatbot.git
cd nps-chatbot

# 2. Sanal ortam oluştur ve aktive et
python -m venv venv
venv\Scripts\activate

# 3. Bağımlılıkları kur
pip install -r requirements.txt

# 4. Uygulamayı başlat
streamlit run ui/app.py
```

Tarayıcı otomatik açılmazsa: **http://localhost:8501**

---

## Proje Yapısı

```
nps-chatbot/
├── .env                          # Groq API key (hazır, değiştirmeye gerek yok)
├── config/
│   ├── constants.py              # 19 kategori, duygu ve yorum tipi listeleri
│   └── llm_config.py             # LLM bağlantı ayarları (Groq varsayılan)
├── etl/
│   ├── generate_mock_data.py     # 200k mock veri üretici
│   └── offline_prep.py           # Özet tabloları ve metin özetleri üretici
├── chatbot/
│   ├── engine.py                 # Ana chatbot motoru
│   ├── intent_router.py          # State machine (DIRECT → DETAIL → RESPONSE)
│   ├── data_loader.py            # Veri okuma katmanı
│   └── modes/
│       ├── summary.py            # Haftalık/aylık/günlük özet modu
│       ├── topic.py              # Kategori/segment analiz modu
│       └── example.py            # Örnek yorum modu
├── offline_hazirlik/
│   └── nps_ozetler.csv           # Hazır metin özetleri (264 satır)
├── data/
│   ├── raw/
│   │   └── nps_mock_200k.csv     # 200.000 satır mock NPS verisi
│   └── processed/
│       ├── ozet_tablolari/       # Günlük/haftalık/aylık özet tabloları
│       └── hazir_ozetler/        # İşlenmiş özet verileri
└── ui/
    └── app.py                    # Streamlit arayüzü
```

---

## Veri Şeması

| Sütun | Tip | Açıklama |
|-------|-----|----------|
| SESSION_ID | int | Oturum ID |
| NPS_SCORE | int (0-10) | NPS skoru |
| TEXT | str | Müşteri yorumu |
| INPUT_AS_OF_DATE | datetime | Yorumun girildiği tarih |
| RESULT_AS_OF_DATE | datetime | Sonuçlandırma tarihi |
| FIRST_MAIN_CATEGORY | str | Birinci ana kategori |
| FIRST_SUBCATEGORY | str | Birinci alt kategori |
| SECOND_MAIN_CATEGORY | str | İkinci ana kategori (opsiyonel) |
| SECOND_SUBCATEGORY | str | İkinci alt kategori (opsiyonel) |
| COMMENT_TYPE | str | Şikayet / Memnuniyet / Talep/Öneri / Veri Yetersiz |
| EMOTION | str | Mutsuz / Kızgın / Endişeli / Mutlu / Umutlu / Minnettar / Veri Yetersiz |
| LOAD_DATE | datetime | Tabloya yüklenme tarihi |
