"""
Türkçe yorum şablonları.
Her (yorum_tipi, duygu) çifti için gerçekçi cümleler.
Üretim sırasında kategori/alt kategori kelimeleri placeholder'lara enjekte edilir.
"""

# Şablon değişkenleri: {kategori}, {alt_kategori}
# Birden fazla seçenek → üretimde random seçilir

TEMPLATES = {
    # ── MEM─────────────────────────────────────────────────────────────────────
    ("Memnuniyet", "Minnettar"): [
        "{kategori} konusunda gösterdiğiniz ilgi için çok teşekkür ederim.",
        "{alt_kategori} sürecini bu kadar kolay ve hızlı hale getirdiğiniz için minnettarım.",
        "Uygulamayı kullandım, {alt_kategori} özelliği gerçekten harika çalışıyor. Teşekkürler.",
        "{kategori} ile ilgili sorunum anında çözüldü, memnun kaldım.",
        "Çok uzun süredir {kategori} kullanıyorum ve her geçen gün daha iyi hale geliyor.",
    ],
    ("Memnuniyet", "Mutlu"): [
        "{alt_kategori} işlemim çok hızlı ve sorunsuz tamamlandı.",
        "{kategori} kullanımı son derece pratik, çok memnunum.",
        "Mobil uygulama üzerinden {alt_kategori} işlemimi saniyeler içinde hallettim.",
        "{kategori} konusundaki gelişmeler için teşekkürler, harika iş çıkarıyorsunuz.",
        "İşlemlerimi evden halledebildiğim için {kategori} çok işime yarıyor.",
    ],
    ("Memnuniyet", "Umutlu"): [
        "{kategori} giderek gelişiyor, daha da iyi olacağını düşünüyorum.",
        "{alt_kategori} sürecinde küçük aksaklıklar olsa da genel olarak olumlu bir deneyim yaşadım.",
        "Bankanın {kategori} alanındaki yatırımları gelecek için umut vaat ediyor.",
        "{alt_kategori} henüz tam oturmamış ama potansiyel gördüm, devam edin.",
    ],
    ("Memnuniyet", "Veri Yetersiz"): [
        "{kategori} ile ilgili işlem yaptım.",
        "{alt_kategori} adımını tamamladım.",
        "İşlem tamam.",
    ],

    # ── ŞİKAYET ────────────────────────────────────────────────────────────────
    ("Şikayet", "Kızgın"): [
        "{kategori} konusunda yaşadığım sorun hâlâ çözülmedi, bu kabul edilemez!",
        "{alt_kategori} işlemim defalarca hata verdi, bu durumdan çok rahatsız oldum.",
        "{kategori} ücretleri hiçbir açıklama yapılmadan artırıldı, bu saygısızlıktır.",
        "Çağrı merkezi {alt_kategori} konusunda beni saatlerce bekletti, şiddetle protesto ediyorum.",
        "{kategori} sistemi sürekli çöküyor ve kayıplarım oluyor, bu duruma bir son verin.",
    ],
    ("Şikayet", "Mutsuz"): [
        "{kategori} konusunda beklentilerimi karşılayamıyorsunuz.",
        "{alt_kategori} süreci çok uzun ve yorucu, iyileştirme yapılması şart.",
        "{kategori} işlemim sırasında yaşadığım aksaklık beni hayal kırıklığına uğrattı.",
        "{alt_kategori} özelliği diğer bankalarda çok daha iyi çalışıyor.",
        "Yıllardır müşterinizim fakat {kategori} konusundaki bu tutum beni üzüyor.",
    ],
    ("Şikayet", "Endişeli"): [
        "{kategori} konusunda güvenlik açığı olduğundan endişeleniyorum.",
        "{alt_kategori} sırasında verilerimin ne olduğu hakkında bilgi almak istiyorum.",
        "{kategori} sisteminde yaşanan hatalar hesap güvenliğimi tehdit ediyor mu?",
        "{alt_kategori} işlemi beklenmedik bir şekilde iptal edildi, param nerede?",
        "{kategori} konusunda herhangi bir bildirim almıyorum, bu beni kaygılandırıyor.",
    ],
    ("Şikayet", "Veri Yetersiz"): [
        "{kategori} ile ilgili bir sorun var.",
        "{alt_kategori} konusunda problem yaşıyorum.",
        "Şikayetim mevcut.",
    ],

    # ── TALEP/ÖNERİ ────────────────────────────────────────────────────────────
    ("Talep/Öneri", "Mutlu"): [
        "{kategori} gerçekten iyi ama {alt_kategori} işlemine kısayol eklenmesi harika olur.",
        "Uygulamayı seviyorum, {alt_kategori} sekmesine daha kolay erişim sağlayabilirsiniz.",
        "{kategori} özelliklerini kullananlar için bildirim sistemi öneririm.",
        "{alt_kategori} konusunda daha fazla esneklik olmasını talep ediyorum.",
    ],
    ("Talep/Öneri", "Umutlu"): [
        "{kategori} alanında yapılacak geliştirmeleri sabırsızlıkla bekliyorum.",
        "{alt_kategori} sürecinin dijitalleştirileceğini umuyorum.",
        "{kategori} için daha kapsamlı bir self-servis seçeneği çok faydalı olacaktır.",
        "{alt_kategori} konusunda iyileştirme yapılırsa müşteri memnuniyeti artacaktır.",
    ],
    ("Talep/Öneri", "Mutsuz"): [
        "{alt_kategori} konusunu bir türlü çözemedim, lütfen daha iyi bir süreç sunun.",
        "{kategori} için kullanılabilirliği artıracak adımlar atılmasını bekliyorum.",
        "{alt_kategori} işleminde gereksiz adımlar var, sadeleştirilmeli.",
    ],
    ("Talep/Öneri", "Kızgın"): [
        "{kategori} konusundaki eksiklikleri çözmenizi talep ediyorum, artık bıktım!",
        "{alt_kategori} için defalarca istek ilettim ama hiçbir şey değişmedi.",
    ],
    ("Talep/Öneri", "Endişeli"): [
        "{kategori} konusunda daha şeffaf bir iletişim yapılmasını istiyorum.",
        "{alt_kategori} sürecinde müşterilerin daha iyi bilgilendirilmesi gerekiyor.",
    ],
    ("Talep/Öneri", "Minnettar"): [
        "{kategori} için teşekkürler, {alt_kategori} konusunda ek bir önerim var.",
        "Harika bir deneyimdi, {alt_kategori} özelliğine ekleme yapılırsa mükemmel olur.",
    ],
    ("Talep/Öneri", "Veri Yetersiz"): [
        "{kategori} konusunda önerim var.",
        "{alt_kategori} için talep iletmek istiyorum.",
    ],

    # ── VERİ YETERSİZ ──────────────────────────────────────────────────────────
    ("Veri Yetersiz", "Veri Yetersiz"): [
        ".",
        "İyi",
        "Fena değil",
        "Bilmiyorum",
        "Yorum yok",
        "Nötr",
        "Geçiyorum",
    ],
    ("Veri Yetersiz", "Mutlu"):    ["İyi gidiyor.", "Güzel.", "Tamam.", "Memnunum."],
    ("Veri Yetersiz", "Mutsuz"):   ["Pek iyi değil.", "İdare eder.", "Meh."],
    ("Veri Yetersiz", "Kızgın"):   ["Kötü.", "Beğenmedim.", "Olmaz."],
    ("Veri Yetersiz", "Endişeli"): ["Emin değilim.", "Karar vermedim.", "Belirsiz."],
    ("Veri Yetersiz", "Umutlu"):   ["Olabilir.", "Bakalım.", "Ümit ediyorum."],
    ("Veri Yetersiz", "Minnettar"):["Teşekkürler.", "Sağ olun.", "Eyvallah."],
}
