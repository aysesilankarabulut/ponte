# Uzman değerlendirmesi – özet (Kasım 2026)

**Değerlendirici:** tıp fakültesi 4. sınıf öğrencisi (raporda bu ifadeyle anılmayı kabul etti).
**Yöntem:** 20 rapordan rastgele seçilen 60 açıklama, 30 tahlil tanımı, 30 referans aralığı ve 14 doktor sorusu Excel formuyla puanlandı. Değerlendirici hangi açıklamayı modelin, hangisini kodun yazdığını bilmiyordu (kör değerlendirme).

## Sayısal sonuçlar

| Bölüm | Sonuç |
|---|---|
| Açıklamalar: tıbben doğruluk (1–5) | ortalama **4,39** (5 puan: 29, 4 puan: 24, 3 puan: 6; 59/60 puanlandı) |
| Açıklamalar: anlaşılırlık (1–5) | ortalama **4,66** (5 puan: 42, 4 puan: 14, 3 puan: 3) |
| Açıklamalar: yanıltıcı mı? | Hayır 31 · Emin değilim 20 · Evet 8 |
| Model ve kod cümleleri (doğruluk) | model 4,43 (53 açıklama) · kod 4,00 (6 açıklama) |
| Tahlil tanımları | ad doğru 29/30 · tanım ortalaması **4,67** |
| Referans aralıkları | makul 12/30 · düzeltme önerildi 18/30 |
| Doktor soruları | **14/14 uygun** |
| En ciddi hata | “Majör bir hata yoktu.” |

## Bulgular
- “Yanıltıcı: Evet” denen 8 açıklamanın hepsi **cinsiyete bağlı referans aralıklarıyla** ilgili (GGT, hematokrit, eritrosit, ferritin). Dil modelinin cümlelerinden değil, sentetik veride tek bir aralık kullanılmasından kaynaklanıyor.
- “Emin değilim” cevaplarının çoğu **sınırda kategorilerle** ilgili: total kolesterol 200–239, trigliserit 150–199, HbA1c %5,7–6,4, açlık glikozu 100–125 “sınırda yüksek”; D vitamini 20–29 “sınırda düşük”.
- CRP yalnızca iltihabı değil, doku hasarı ve stresi de gösterir. Kreatinin kas kütlesiyle ilişkilidir; düşük kreatinin genellikle alarm bulgusu değildir.
- Terim önerileri: “Glikoz (açlık kan şekeri)”, “Eritrosit (RBC)”, “Alkalen fosfataz (ALP)”.
- Güvenlik önerisi: değer, üst sınırın en az **2 katı** ise hasta, doktoruna hemen danışması için uyarılmalı.
- Değerlendiricinin gözden kaçırdığı bir model hatasını doğrulama katmanı yakaladı: “(40,0 – 130,0) **arasında**, yani düşük”. Bu da otomatik kontrolün ve uzman değerlendirmesinin birbirini tamamladığını gösteriyor.

## Yapılan değişiklikler
1. `data/names_tr.csv`: değerlendiricinin önerisiyle 12 tahlilin adı ya da tanımı güncellendi (eski hali `names_tr_v1.csv`).
2. `data/clinical_notes.csv` (yeni): sınırda kategorilerin eşikleri ve cinsiyete bağlı aralığı olan 10 tahlil.
3. `explain.py`:
   - her sonuç için “düşük / yüksek / sınırda düşük / sınırda yüksek” seviyesini kod hesaplıyor;
   - üst sınırın 2 katını aşan değerler için en üstte “doktorunuzla en kısa sürede konuşun” uyarısı çıkıyor;
   - cinsiyete bağlı tahliller için ayrı bir not ekleniyor.
4. `verify.py`:
   - “aralığın (…) arasında” iddiası artık **yön hatası** olarak yakalanıyor;
   - sınırda bir değere düz “yüksek” demek (ya da tersi) **kategori hatası** olarak yakalanıyor.
   - 27 birim testi geçiyor; hata ekleme deneyinde yanlış alarm 0/1159.
5. Sentetik raporlar (`tests.csv`) **değiştirilmedi**, çünkü bütün deneylerin doğru cevapları bu raporlara bağlı. Gerçek kullanımda Ponte raporda yazan aralığı kullanır. Bu, tezde sınırlılık olarak yazılacak.

6. Düşük değerler ve acil durum (değerlendiricinin ek cevabı):
   - referans aralığının altındaki her değer için, ne kadar düşük olursa olsun, doktora danışma önerisi ekleniyor;
   - normal dışı sonucu olan her açıklamada şu not yer alıyor: “Şikâyetlerinize bilinç bulanıklığı gibi acil bir belirti eşlik ediyorsa beklemeden acil servise başvurun.”
