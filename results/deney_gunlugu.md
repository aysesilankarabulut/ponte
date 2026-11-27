# Ponte – Deney günlüğü (tez için ham malzeme)

Bütün sayılar sentetik raporlarla ölçüldü (gerçek hasta verisi yok).
Donanım: dizüstü bilgisayar, Intel Iris Xe (tümleşik), 16 GB RAM, sadece işlemci (CPU).
Modeller Ollama ile yerel olarak çalıştı, sıcaklık 0.

## 1. Veri
- `tests.csv`: 30 tahlil; LOINC kodu, 4 dilde ad, birim ve referans aralığı.
- Temiz raporlar: 4 dil × 25 = 100 rapor (seed 42).
- Dağınık raporlar: 4 dil × 25 = 100 rapor (seed 43).
  - 4 biçim: classic, dots, colon, columns.
  - Kısaltmalar, büyük harf, OCR hataları, H/L işaretleri ve farklı aralık yazımları içerir.
- Ayrım: her dilde 001–005 geliştirme (20 rapor), 006–025 test (80 rapor).

## 2. Rapor okuma (20 geliştirme raporu, 248 normal dışı değer)
| Yöntem | Alan doğruluğu | Kaçırılan anormal | sn/rapor |
|---|---|---|---|
| Kural tabanlı (regex) | %9,8 | 224 | – |
| 3B, rapor modu | %63,0 | 107 | 102 |
| 3B, satır modu | %61,2 | 99 | 134 |
| 3B, karma v1 | %41,5 | 150 | 152 |
| 3B, karma + JSON şeması | %69,7 | 74 | 65 |
| 3B, daraltmalı | %71,1 | 62 | 128 |
| **8B, karma + JSON şeması** | **%96,9** | **9** | 144 |

Notlar:
- Model büyüklüğü, tasarım hilelerinden daha belirleyici çıktı.
- 3B daraltmalı denemede model döngüye girdi: 460 satıra 857 cevap verdi.

## 3. Bağımsız test (8B karma, 80 rapor, 911 normal dışı değer)
- Doğruluk: **%96,2**. Kaçırılan anormal değer: 44/911 (%4,8). Ortalama 136 sn/rapor.
- Dillere göre: Almanca %94,0 · İngilizce %98,4 · İspanyolca %95,9 · İtalyanca %96,6.
- Biçimlere göre: classic %96,5 · colon %98,1 · columns %94,9 · dots %95,5.
- Kaçırılan 44 değerin 41'i satır hiç okunamadığı için kaçtı. Sadece 3'ü yanlış okunup "normal" denen değerdi.
- Okunamayan değerlerin dağılımı (100 raporda toplam 98): HbA1c 31, ürik asit 14, MCV 10, trombosit 8.

### 3a. Birim onarımı
Kural: modelin seçtiği tahlilin birimi satırda yoksa, satırdaki birime uyan tahliller arasından adı en çok benzeyen seçilir. Onarım, modelin kendi yaptığı bir atamanın üzerine yazmaz.

| | Onarımsız | Onarımlı |
|---|---|---|
| Geliştirme doğruluk | %96,9 | %98,7 |
| Geliştirme kaçırılan anormal | 9 | 4 |
| Test doğruluk | %96,2 | %97,9 |
| Test kaçırılan anormal | 44 | 25 |

- 52 satır onarıldı; 52'si de doğru.
- **Sınırlılık:** Bu kural, test setindeki hatalara bakılarak tasarlandı. Son ölçüm, hiç kullanılmamış yeni bir rapor setiyle (yeni seed) tekrarlanmalı.

### 3b. Ad tutarlılığı kontrolü
Bazı satırlarda model, birimi tutan ama adı tutmayan bir tahlil seçti. Örnekler: "Harnsäure" (ürik asit) satırına kalsiyum, "Gamma-GT" satırına ALP. Bu hata "okunamayan satır" uyarısı vermez, çünkü değer makul görünür.
- Kural: satırdaki ad, aynı birimdeki başka bir tahlille çok daha iyi uyuyorsa (benzerlik ≥ 0,85 ve en az 0,20 fark), kod modelin seçimini düzeltir.
- Aynı tahlile iki satır atanmışsa, adı daha iyi uyan satır kalır.

| | Onarımsız | Ad + birim onarımı |
|---|---|---|
| Geliştirme doğruluk | %96,9 | %100 |
| Test (80) doğruluk | %96,2 | %99,8 |
| Test (80) kaçırılan anormal | 44 | 2 |

- 111 düzeltme yapıldı; 111'i de doğru.
- Bu kural da 100 rapordaki hatalara bakılarak tasarlandı, bu yüzden son test yeni raporlarla yapıldı (bölüm 9).

## 4. Türkçe açıklama ve doğrulama (8B, 20 rapor, 248 normal dışı değer)
| Talimat sürümü | Reddedilen cümle | Kodun eklediği | sn/rapor |
|---|---|---|---|
| v1: ilk talimat | 77 (%31) | 131 | 183 |
| v2: "hiçbirine normal deme" + örnek | 44 (%18) | 44 | 194 |
| v3: uzman önerileri + düşük/yüksek/sınırda örnekleri | **1 (%0,4)** | 1 | 287 |

(Üç sürüm de güncel doğrulayıcıyla yeniden kontrol edildi.)

- v1'de 20 raporun 5'inde model, normal dışı **bütün** değerlere "normal aralığındadır" dedi (57 cümle). İlk doğrulayıcı bunları kaçırıyordu; "normal" iddiası kontrolü eklendi.
- v1'de bir raporda model yüzde hesapladı (13 cümle). Hepsi sayı hatası olarak reddedildi.
- v2'deki hataların çoğu, talimattaki tek örneğin (düşük değer) yüksek değerlere kopyalanmasıydı: "altında, yani yüksek".
- v3'te kalan tek hata: 217 mg/dL trigliserite "sınırda yüksek" denmesi (doğrusu "yüksek"). Kategori kontrolü bunu yakaladı.
- Bedel: talimat uzadıkça rapor başına süre arttı (183 → 287 sn).

### 4a. Hata ekleme deneyi (doğrulayıcının yakalama oranı)
| Kaynak | Cümle | Sayı | Yön | Normal | Teşhis | Küçümseme | Yanlış alarm |
|---|---|---|---|---|---|---|---|
| Kod cümleleri | 1159 | %100 | %100 | %100 | %100 | %100 | 0/1159 |
| 8B v3 cümleleri | 247 | %100 | %100 | %100 | %100 | %100 | 0/247 |

- Bilinen sınır: anlam hatalarını (ör. yanlış tıbbi tanım) doğrulayıcı yakalayamaz; bunun için uzman değerlendirmesi yapıldı.

### 4b. Küçük model (3B) ile açıklama
- İlk denemede 3B ilk raporda döngüye girdi ve 20 dakikalık zaman aşımına takıldı. Bunun üzerine cevap uzunluğu sınırı ve yarım cevaptan cümle kurtarma eklendi.
- Sınırla tekrar çalıştırıldı:
  - Süre: 142 sn/rapor (8B'nin yarısı).
  - 248 sonuçtan sadece 150'si için cümle yazdı; 7 cevap döngü nedeniyle yarıda kesildi.
  - Yazdığı cümlelerin 58'i reddedildi (%39), çoğu yön hatası ("altında, yani yüksek"). Ayrıca İngilizce parçalar ve bozuk kelimeler ("Şlksek") içeriyordu.
  - Kod 156 güvenli cümle eklemek zorunda kaldı.
- Sonuç: açıklama için 8B gerekli. Doğrulama katmanı sayesinde 3B'nin hataları kullanıcıya ulaşmadı.

## 5. Doktora sorulacak sorular
- v1 (4 rapor): 5 soru reddedildi (1 yön hatası, 4 çok cümleli). Ek sorunlar:
  - Bazı sorular doktor ağzından yazıldı ("seviyeniz").
  - İlaç/beslenme soruları çoğu raporda eksik kaldı.
  - Hangi tahlillerin sorulacağı seçimi gelişigüzeldi.
- v2:
  - Sorular, en çok sapan 3 sonuç için yazılıyor.
  - "Yanlış kişi" kontrolü eklendi.
  - 3 genel soru (tedavi, beslenme, tekrar) her raporda sabit.
  - Sonuç: 12/12 model sorusu kabul edildi.
- Arayüz denemesinde samimi hitap ("ALP değerin") görüldü; bunun için kural ve test eklendi.

## 6. Uzman değerlendirmesi
Ayrıntılar: `uzman_degerlendirme_ozeti.md`.
- Doğruluk 4,39/5 · anlaşılırlık 4,66/5 · tanımlar 4,67/5 · doktor soruları 14/14 uygun.
- "Majör bir hata yoktu."

## 7. Hız (it_010 raporu, 8B, CPU)
| Adım | Süre |
|---|---|
| Model yükleme (bellekteyken) | 2 sn |
| Okuma, bütün satırlar modele | 126 sn |
| Okuma, tek birimli satırları kod atıyor | **100 sn** (doğruluk aynı, 145/150) |
| Açıklama, tek istek | 195 sn |
| Açıklama, 3 paralel istek | 195 sn (kazanç yok: Ollama CPU'da istekleri sırayla işliyor) |
| Doktor soruları | 32 sn |

- Arayüzde okuma bitince değerler tablosu hemen gösteriliyor. Açıklama cümleleri yazıldıkça, doğrulandıktan sonra ekranda beliriyor.
- Kullanıcının boş ekrana baktığı süre ~1,5–2 dakika.

## 8. Yazılım testleri
- `tests/test_verify.py`: 28 birim testi. Gerçek model hatalarından türetilmiş regresyon testleri de var.

## 9. Son test (hiç görülmemiş raporlar)
- 60 yeni dağınık rapor: 4 dil × 15, yeni tohum (seed 44), `data/reports_final`. Geliştirme sırasında hiçbirine bakılmadı.
- Okuma web arayüzüyle aynı yoldan yapıldı: 8B karma okuyucu, tek birimli satırları kod atıyor, ardından ad ve birim onarımı.

| Ölçüt | Sonuç |
|---|---|
| Alan doğruluğu (genel) | **%100** |
| Her dil (de, en, es, it) | %100 |
| Her biçim (classic, colon, columns, dots) | %100 |
| Kaçırılan anormal değer | **0 / 692** |
| Okunamayan satır uyarısı | 0 |
| Kodun düzelttiği satır | 28 / 1800 |
| Ortalama okuma süresi | 113 sn/rapor |

**Yorum ve sınırlılık:**
- Sonuç, sistemin sentetik rapor üreticisinin içerdiği çeşitliliği tamamen çözebildiğini gösteriyor: 4 dil, 4 biçim, kısaltmalar, OCR hataları, aralık yazımları.
- Ama yeni tohum yalnızca değerleri ve birleşimleri değiştirir; tahlil adları, kısaltma listesi ve biçimler aynıdır.
- Bu yüzden %100, gerçek laboratuvar raporlarında da %100 anlamına gelmez. Gerçek raporlarda şunlar olabilir: başka biçimler, PDF/fotoğraf kaynaklı hatalar, listede olmayan tahliller, farklı birimler.
- Gerçek dünya başarısı ancak gerçek (anonim) raporlarla ölçülebilir. Bu, gelecek çalışma olarak önerilir.
