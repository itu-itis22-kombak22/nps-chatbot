"""
Sabit listeler: kategoriler, alt kategoriler, yorum tipleri, duygu durumları.
"""
from typing import Dict, List

# --- 19 ana kategori için alt kategori mapping ---
SUBMAP: Dict[str, List[str]] = {
    "Alışveriş Kredisi":    ["Başvuru", "Faiz", "Mağaza", "Taksit İşlemleri", "Yaygınlık", "Limit"],
    "ATM":                  ["Sistem Arızası", "Yaygınlık", "Kullanım / Deneyim"],
    "İhtiyaç Kredileri":    ["Bilgilendirme", "Faiz", "Kullanım / Deneyim", "Taksit İşlemleri", "Ücret Komisyon", "Hız", "Limit"],
    "Mobil Bankacılık":     ["Kullanım / Deneyim", "Hız", "Fonksiyon", "Sistem Arızası", "Tasarım Arayüz", "İletişim Sıklığı"],
    "Şube":                 ["Sistem Arızası", "Yaygınlık", "Hız", "Personel"],
    "Banka":                ["Faiz", "Fonksiyon", "Hız", "İletişim Sıklığı", "Kullanım / Deneyim", "Marka Algısı", "Sistem Arızası", "Ücret Komisyon"],
    "Borsa Market":         ["Kullanım / Deneyim", "Sistem Arızası", "Tasarım Arayüz", "Ücret Komisyon", "Hız", "Fonksiyon"],
    "Çağrı Merkezi":        ["İletişim Sıklığı", "Hız", "Fonksiyon", "Personel"],
    "Fon Market":           ["Ücret Komisyon", "Tasarım Arayüz", "Kullanım / Deneyim", "Sistem Arızası", "Hız", "Fonksiyon"],
    "Getirfinans":          ["Başvuru", "Kullanım / Deneyim", "Sistem Arızası", "Teslimat Kurye", "Ücret Komisyon", "Limit"],
    "FX Market":            ["Kullanım / Deneyim", "Fonksiyon", "Makas"],
    "Görüntülü Bankacılık": ["Sistem Arızası", "Kullanım / Deneyim", "Hız", "Kimlik okuma", "Yüz tanıma"],
    "Kartlar":              ["Başvuru", "Kullanım / Deneyim", "Sistem Arızası", "Teslimat Kurye", "Ücret Komisyon", "Taksit İşlemleri", "Limit"],
    "Kiraz (Vadeli Hesap)": ["Başvuru", "Bilgilendirme", "Faiz", "Kullanım / Deneyim"],
    "Hızlı Para (KMH)":     ["Başvuru", "Faiz", "Kullanım / Deneyim", "Taksit İşlemleri"],
    "Kripto Market":        ["Kullanım / Deneyim", "Hız", "Sistem Arızası", "Tasarım Arayüz", "Fonksiyon"],
    "Kurumsal Bankacılık":  ["Kullanım / Deneyim", "Hız", "Fonksiyon", "Sistem Arızası", "Tasarım Arayüz"],
    "Kampanyalar":          [],   # tabloda boştu → güvenli varsayılan
    "Diğer":                [],   # serbest havuz
}

# --- Yorum tipi → izin verilen duygu durumları ---
ALLOWED: Dict[str, List[str]] = {
    "Şikayet":        ["Mutsuz", "Kızgın", "Endişeli", "Veri Yetersiz"],
    "Memnuniyet":     ["Mutlu", "Umutlu", "Minnettar", "Veri Yetersiz"],
    "Talep/Öneri":    ["Mutsuz", "Kızgın", "Endişeli", "Mutlu", "Umutlu", "Minnettar", "Veri Yetersiz"],
    "Veri Yetersiz":  ["Mutsuz", "Kızgın", "Endişeli", "Mutlu", "Umutlu", "Minnettar", "Veri Yetersiz"],
}

COMMENT_TYPES: List[str] = list(ALLOWED.keys())
EMOTIONS: List[str] = ["Mutsuz", "Kızgın", "Endişeli", "Mutlu", "Umutlu", "Minnettar", "Veri Yetersiz"]
MAIN_CATEGORIES: List[str] = list(SUBMAP.keys())

# NPS segmentasyonu
NPS_SEGMENTS = {
    "Detractor":  range(0, 7),   # 0-6
    "Passive":    range(7, 9),   # 7-8
    "Promoter":   range(9, 11),  # 9-10
}

# Offline özet tipleri
SUMMARY_TYPES = [
    "Günlük Negatif Özet",
    "Haftalık Konu Özeti",
    "Aylık Konu Özeti",
    "Haftalık Segment Dağılımı",
    "Aylık Segment Dağılımı",
    "Haftalık Duygu Dağılımı",
    "Aylık Duygu Dağılımı",
]
