# Sinta Matematika ITERA Sync

Rekaman JSON profil publik **16 dosen Matematika ITERA** dari lampiran data awal. Setiap sinkronisasi memeriksa seluruh sembilan halaman publik per dosen: Scopus/profil, Garuda, Google Scholar, RAMA, penelitian, pengabdian, HKI, buku, dan metrik.

Data yang diambil:

- artikel Scopus, Garuda, Google Scholar, dan RAMA yang ditampilkan publik;
- hibah penelitian (`Researches`);
- pengabdian kepada masyarakat (`Community Services`);
- kekayaan intelektual/hak cipta (`IPRs`);
- buku;
- profil, bidang keilmuan, SINTA Score Overall, SINTA Score 3Yr, Affil Score, dan metrik.

## Cara memakai untuk dosen lain

Edit [`config/authors.json`](config/authors.json):

```json
[
  {
    "name": "Nama Dosen",
    "sinta_id": "1234567",
    "profile_url": "https://sinta.kemdiktisaintek.go.id/authors/profile/1234567",
    "enabled": true
  }
]
```

Tambahkan objek baru untuk setiap dosen. `sinta_id` dan angka terakhir pada `profile_url` harus sesuai.

## Automasi GitHub Actions

Workflow [`.github/workflows/weekly-sinta-sync.yml`](.github/workflows/weekly-sinta-sync.yml) berjalan **dua kali sebulan**, tanggal 2 dan 16 sekitar pukul **02.17 WIB**, dan juga dapat dijalankan dari menu **Actions → Full SINTA Sync → Run workflow**.

Workflow akan:

1. memvalidasi konfigurasi dan parser;
2. meminta HTML publik SINTA melalui ZenRows Fetch API;
3. membaca HTML tersebut menggunakan selector yang sama dengan Inspect Element;
4. memperbarui seluruh kategori di folder `data/`, mempertahankan rekaman lama dan data awal;
5. melakukan commit dan push menggunakan `GITHUB_TOKEN` bawaan.

Setiap profil juga wajib lolos pemeriksaan `SINTA Score Overall`. Jika elemen skor tidak ditemukan, proses dosen tersebut dianggap gagal dan JSON lama dipertahankan agar kehilangan data tidak terjadi. Bidang disimpan sebagai `profile.subjects` dan `profile.subject_details`; skor utama juga tersedia langsung sebagai `profile.sinta_score_overall` dan `profile.sinta_score_3yr`. Ringkasannya ikut ditulis ke `data/index.json` untuk seluruh dosen.

### API key wajib

SINTA menolak alamat IP runner GitHub meskipun halaman yang sama dapat dibuka dari browser biasa. Karena API resmi SINTA memerlukan akun dan whitelist IP, repository ini menggunakan ZenRows sebagai transport HTML.

1. Buat akun gratis di [ZenRows](https://app.zenrows.com/).
2. Salin API key dari dashboard.
3. Buka repository GitHub → **Settings → Secrets and variables → Actions**.
4. Pilih **New repository secret**.
5. Isi nama `ZENROWS_API_KEY`, tempel API key sebagai nilainya, lalu simpan.

API key tidak ditulis ke source code dan tidak masuk ke JSON. Scraper memakai halaman HTML server-rendered tanpa meminta JavaScript. Semua permintaan memakai **ZenRows Premium Proxy Indonesia** (`premium_proxy=true`, `proxy_country=id`). Satu `session_id` dipakai untuk sembilan halaman seorang dosen supaya alamat IP keluar tetap stabil, lalu sesi diganti untuk dosen berikutnya.

Jika ZenRows mengembalikan HTTP `422`, scraper mencoba berurutan: IP Indonesia baru, Premium Proxy tanpa penguncian negara, kemudian `js_render=true` hanya untuk request yang tetap gagal. Kegagalan satu halaman dicatat pada `collection_status` sebagai `error_preserved_previous_data`; data lama tidak dihapus dan proses berlanjut ke halaman serta dosen berikutnya. Workflow tetap menjalankan commit dengan `if: always()`, sehingga hasil parsial yang valid tidak hilang ketika salah satu request gagal.

Satu sinkronisasi lengkap memakai **9 × 16 = 144 request**, atau sekitar **1.440 kredit** bila tarif Premium Proxy adalah 10 kredit per request. Dua sinkronisasi lengkap per bulan memakai sekitar **2.880 dari 5.000 kredit**, menyisakan sekitar 2.120 kredit. Setiap eksekusi manual lengkap membutuhkan sekitar 1.440 kredit tambahan. Fallback yang berhasil dengan JavaScript dapat memakai kredit lebih besar, tetapi hanya digunakan pada URL yang tetap menerima `422` setelah dua fallback lebih ringan. Biaya aktual yang dilaporkan ZenRows dicetak pada log GitHub Actions melalui header `X-Request-Cost` jika header tersebut tersedia.

Untuk repository hasil fork, pastikan **Settings → Actions → General → Workflow permissions** mengizinkan **Read and write permissions** jika kebijakan akun tidak mengizinkannya secara otomatis.

## Menjalankan secara lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export ZENROWS_API_KEY="API_KEY_ANDA"
python scripts/scrape_sinta.py --all-views
```

Menjalankan hanya satu dosen:

```bash
python scripts/scrape_sinta.py --author-id 6750161
```

Memeriksa satu kategori tertentu atau seluruh tab:

```bash
python scripts/scrape_sinta.py --author-id 6750161 --view scopus
python scripts/scrape_sinta.py --author-id 6750161 --all-views
```

Validasi konfigurasi dan pengujian parser:

```bash
python scripts/scrape_sinta.py --check-config
python -m unittest discover -s tests -v
```

## Keluaran

- `data/index.json`: indeks seluruh dosen dan jumlah rekaman per kategori.
- `data/<sinta_id>.json`: profil, koleksi data, metrik, serta `manual_baseline` yang menyimpan data dari lampiran awal.
- `input/initial_profiles.md`: lampiran sumber data awal, agar data yang diimpor dapat diperiksa kembali.

Riwayat Git berfungsi sebagai catatan perubahan setiap sinkronisasi. Setiap rekaman awal dipertahankan, termasuk yang tidak tampil lagi pada halaman pertama. Data dari lampiran belum diverifikasi dengan API. Jika permintaan gagal, data penulis yang gagal tidak ditimpa.

## Batasan penting

Scraper ini hanya membaca halaman pertama yang dapat diakses tanpa login. Program tidak mengikuti pagination dan tidak pernah membuka tombol **View more**. Jika tombol tersebut tersedia, JSON akan menandai `public_access_limited: true`.

GitHub Actions tidak memasang Chromium atau browser lainnya. Skrip meminta seluruh tab publik setiap profil dan memeriksa struktur HTML alih-alih mengandalkan label `Content-Type`. Program tidak melakukan login, tidak memakai cookie akun SINTA, tidak menekan **View more**, dan tidak mencoba mengakses data privat. Jika API gagal, JSON lama di repository tidak ditimpa.

Struktur HTML SINTA dapat berubah. Jika provider mendapat penolakan atau kehabisan kredit, workflow akan berstatus gagal/peringatan setelah tetap meng-commit hasil yang berhasil; JSON lama untuk bagian yang gagal dipertahankan. Periksa `collection_status` pada JSON dan log workflow. Gunakan frekuensi yang wajar, patuhi ketentuan layanan sumber, dan jangan mengumpulkan data pribadi yang tidak diperlukan.

## Lisensi

[MIT](LICENSE)
