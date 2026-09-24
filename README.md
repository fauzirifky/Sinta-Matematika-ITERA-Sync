# Sinta Matematika ITERA Sync

Scraper ringan untuk merekam data **halaman publik pertama** profil dosen dari SINTA ke JSON secara otomatis setiap minggu. Repository ini mula-mula dikonfigurasi untuk Rifky Fauzi, Program Studi Matematika, Institut Teknologi Sumatera.

Data yang diambil:

- artikel Scopus, Garuda, Google Scholar, dan RAMA yang ditampilkan publik;
- hibah penelitian (`Researches`);
- pengabdian kepada masyarakat (`Community Services`);
- kekayaan intelektual/hak cipta (`IPRs`);
- buku;
- profil, skor SINTA, dan metrik.

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

Workflow [`.github/workflows/weekly-sinta-sync.yml`](.github/workflows/weekly-sinta-sync.yml) berjalan setiap Minggu pukul **02.17 WIB** dan juga dapat dijalankan dari menu **Actions → Weekly SINTA Sync → Run workflow**.

Workflow akan:

1. memvalidasi konfigurasi dan parser;
2. meminta HTML publik SINTA melalui ZenRows Fetch API;
3. membaca HTML tersebut menggunakan selector yang sama dengan Inspect Element;
4. memperbarui JSON di folder `data/`;
5. melakukan commit dan push menggunakan `GITHUB_TOKEN` bawaan.

### API key wajib

SINTA menolak alamat IP runner GitHub meskipun halaman yang sama dapat dibuka dari browser biasa. Karena API resmi SINTA memerlukan akun dan whitelist IP, repository ini menggunakan ZenRows sebagai transport HTML.

1. Buat akun gratis di [ZenRows](https://app.zenrows.com/).
2. Salin API key dari dashboard.
3. Buka repository GitHub → **Settings → Secrets and variables → Actions**.
4. Pilih **New repository secret**.
5. Isi nama `ZENROWS_API_KEY`, tempel API key sebagai nilainya, lalu simpan.

API key tidak ditulis ke source code dan tidak masuk ke JSON. Scraper memakai halaman HTML server-rendered tanpa JavaScript. Satu dosen memerlukan sekitar sembilan request per sinkronisasi. Seluruh tab memakai `session_id` ZenRows yang sama agar IP keluar tetap sama selama rangkaian request; ID ini hanya mengikat IP dan tidak membuat cookie login SINTA.

Untuk repository hasil fork, pastikan **Settings → Actions → General → Workflow permissions** mengizinkan **Read and write permissions** jika kebijakan akun tidak mengizinkannya secara otomatis.

## Menjalankan secara lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export ZENROWS_API_KEY="API_KEY_ANDA"
python scripts/scrape_sinta.py
```

Menjalankan hanya satu dosen:

```bash
python scripts/scrape_sinta.py --author-id 6750161
```

Validasi konfigurasi dan pengujian parser:

```bash
python scripts/scrape_sinta.py --check-config
python -m unittest discover -s tests -v
```

## Keluaran

- `data/index.json`: indeks seluruh dosen dan jumlah rekaman per kategori.
- `data/<sinta_id>.json`: profil, koleksi data, metrik, serta status setiap bagian.

Riwayat Git berfungsi sebagai catatan perubahan mingguan. Jika satu kategori gagal diakses sementara, scraper mempertahankan bagian terakhir yang berhasil dan menandainya sebagai `stale`; data lama tidak diganti dengan daftar kosong.

## Batasan penting

Scraper ini hanya membaca halaman pertama yang dapat diakses tanpa login. Program tidak mengikuti pagination dan tidak pernah membuka tombol **View more**. Jika tombol tersebut tersedia, JSON akan menandai `public_access_limited: true`.

GitHub Actions tidak memasang Chromium atau browser lainnya. ZenRows hanya mengembalikan HTML publik yang sama dengan respons browser. Program tidak melakukan login, tidak memakai cookie akun SINTA, tidak menekan **View more**, dan tidak mencoba mengakses data privat. Jika API gagal, JSON lama di repository tidak ditimpa.

Struktur HTML SINTA dapat berubah. ZenRows pun belum terbukti berhasil mengakses SINTA sampai workflow diuji dengan key Anda; jika provider tetap mendapat 403, workflow akan gagal jelas dan JSON lama dipertahankan. Periksa status workflow dan sesuaikan parser jika selector halaman berubah. Gunakan frekuensi yang wajar, patuhi ketentuan layanan sumber, dan jangan mengumpulkan data pribadi yang tidak diperlukan.

## Lisensi

[MIT](LICENSE)
