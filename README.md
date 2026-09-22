# Sinta Matematika ITERA Sync

Scraper ringan untuk merekam data **publik** profil dosen dari SINTA ke JSON secara otomatis setiap minggu. Repository ini mula-mula dikonfigurasi untuk Rifky Fauzi, Program Studi Matematika, Institut Teknologi Sumatera.

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
2. mengakses halaman publik SINTA dengan jeda antarkoneksi;
3. memperbarui JSON di folder `data/`;
4. melakukan commit dan push menggunakan `GITHUB_TOKEN` bawaan.

Untuk repository hasil fork, pastikan **Settings → Actions → General → Workflow permissions** mengizinkan **Read and write permissions** jika kebijakan akun tidak mengizinkannya secara otomatis.

## Menjalankan secara lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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

Scraper ini hanya membaca halaman yang dapat diakses tanpa login. Jika SINTA membatasi daftar publik dengan tombol **View more** menuju halaman login, JSON akan menandai `public_access_limited: true`. Program tidak mencoba melewati autentikasi, CAPTCHA, atau pembatasan akses.

Struktur HTML SINTA dapat berubah. Periksa status workflow dan sesuaikan parser jika selector halaman berubah. Gunakan frekuensi yang wajar, patuhi ketentuan layanan sumber, dan jangan mengumpulkan data pribadi yang tidak diperlukan.

## Lisensi

[MIT](LICENSE)
