# Prompt AI: sinkronisasi JSON GitHub ke Google Sheets

Salin seluruh prompt berikut ke AI pembuat kode:

---

Anda adalah software engineer yang ahli Google Apps Script dan Google Sheets. Buatkan solusi lengkap dan siap tempel untuk menarik data JSON dari repository publik:

`https://github.com/fauzirifky/Sinta-Matematika-ITERA-Sync`

Sumber utama:

- indeks: `https://raw.githubusercontent.com/fauzirifky/Sinta-Matematika-ITERA-Sync/main/data/index.json`
- profil dosen: `https://raw.githubusercontent.com/fauzirifky/Sinta-Matematika-ITERA-Sync/main/data/<sinta_id>.json`

Sebelum menulis kode, baca struktur aktual `data/index.json` dan sekurang-kurangnya dua berkas profil. Jangan mengarang nama properti. Kode harus toleran terhadap properti opsional, nilai `null`, koleksi kosong, serta perbedaan antara `collections` dan `manual_baseline.collections`.

Buat Google Apps Script yang terikat pada satu Google Spreadsheet. Jangan gunakan API key, GitHub token, service account, library eksternal, atau layanan berbayar. Repository bersifat publik.

Kebutuhan wajib:

1. Sediakan fungsi `syncSintaFromGitHub()`.
2. Ambil `data/index.json`, baca daftar berkas dosen, lalu ambil semua JSON profil menggunakan `UrlFetchApp.fetchAll()`.
3. Utamakan data terkini dari `collections`. Gunakan `manual_baseline.collections` hanya sebagai pelengkap untuk rekaman yang belum ada pada koleksi terkini.
4. Deduplicasi rekaman dengan prioritas: `url`, kemudian `id`, kemudian kombinasi ternormalisasi `sinta_id + kategori + judul + tahun`.
5. Buat atau perbarui sheet berikut:
   - `Dosen`
   - `Publikasi`
   - `Penelitian`
   - `Pengabdian`
   - `HKI`
   - `Buku`
   - `Status Sync`
6. Pemetaan kategori:
   - `scopus`, `garuda`, `google_scholar`, `rama` → `Publikasi`
   - `researches` → `Penelitian`
   - `community_services` → `Pengabdian`
   - `iprs` → `HKI`
   - `books` → `Buku`
7. Setiap baris data wajib menyertakan `Nama Dosen`, `SINTA ID`, `Kategori`, `Judul`, `Tahun`, `URL`, dan `Sumber JSON`. Tambahkan kolom khusus yang relevan, misalnya publikasi, klasifikasi, sitasi, DOI, ketua, personel, dana, inventor, nomor permohonan, status, jenis HKI, penulis, penerbit, dan ISBN jika tersedia.
   Sheet `Dosen` wajib memuat sekurang-kurangnya: `Nama`, `SINTA ID`, `Afiliasi`, `Program Studi`, `Bidang`, `SINTA Score Overall`, `SINTA Score 3Yr`, `Affil Score`, `Affil Score 3Yr`, `URL Profil`, dan `Terakhir Diperiksa`. Ambil bidang dari `profile.subjects`; ambil skor dari properti eksplisit `profile.sinta_score_overall`, `profile.sinta_score_3yr`, `profile.affil_score`, dan `profile.affil_score_3yr`, dengan fallback ke `profile.scores`.
8. Jangan menulis objek JavaScript sebagai `[object Object]`. Array orang harus diratakan menjadi teks yang terbaca. Properti tambahan yang belum dipetakan disimpan sebagai JSON ringkas dalam kolom `Detail Tambahan`.
9. Penulisan data harus efisien: susun array dua dimensi dan gunakan satu `setValues()` per sheet, bukan `setValue()` per sel.
10. Hapus hanya isi sheet yang dikelola script. Jangan menghapus sheet lain milik pengguna.
11. Bekukan baris header, aktifkan filter, atur lebar kolom secara wajar, bungkus teks judul/detail, dan format header secara konsisten.
12. Tambahkan menu `SINTA Sync` saat spreadsheet dibuka, dengan item:
    - `Sinkronkan sekarang`
    - `Pasang trigger harian`
    - `Hapus trigger`
13. Trigger harian hanya memeriksa `index.json`. Simpan hash isi indeks pada `PropertiesService`. Jika indeks belum berubah, hentikan proses tanpa mengambil seluruh profil dan tulis status `Tidak ada perubahan`.
14. Sediakan fungsi `installDailyTrigger()` dan `removeSyncTriggers()`. Pastikan pemasangan berulang tidak membuat trigger ganda.
15. Gunakan `LockService` agar dua sinkronisasi tidak berjalan bersamaan.
16. Tangani HTTP non-200, JSON rusak, data kosong, dan satu profil gagal tanpa menghapus data Spreadsheet terakhir yang masih valid. Catat kegagalan pada `Status Sync`.
17. Jangan memanggil ZenRows atau SINTA. Spreadsheet hanya membaca JSON yang sudah berada di GitHub.
18. Tulis waktu menggunakan zona `Asia/Jakarta`.

Output yang harus Anda berikan:

1. `Code.gs` lengkap, bukan pseudocode.
2. `appsscript.json` bila diperlukan.
3. Langkah pemasangan dari Spreadsheet kosong sampai otorisasi dan pemasangan trigger.
4. Penjelasan singkat struktur setiap sheet.
5. Daftar pengujian: sinkronisasi pertama, tidak ada perubahan, satu JSON gagal, koleksi kosong, deduplikasi, dan trigger ganda.

Jangan meminta pengguna menyalin API key ke sel atau source code. Jangan membuat web app; solusi cukup berupa Apps Script yang terikat ke Spreadsheet.

---
