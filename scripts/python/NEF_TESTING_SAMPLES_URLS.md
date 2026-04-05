# Free Nikon NEF sample files — URLs for testing

Curated links for **D300**, **D90**, **Z6 II**, and **Z8** (no-login sources where possible). Use with repo **`tests/fixtures/testing_samples`** subfolders: `D300`, `D90`, `Z6II`, `Z8`.

**Automation:** Run `python scripts/python/download_nef_testing_samples.py` to fetch from **rawsamples.ch** and **raw.pixls.us** (reliable for scripts). That step also writes **`manifest.json`** and **`README.md`** (if missing) unless you pass **`--no-manifest`**. Regenerate the manifest any time with `python scripts/python/build_nef_testing_manifest.py` (`--no-exiftool` for SHA-256 only; `--force-readme` to replace README). Imaging Resource FULLRES and raw-files.com links below are often **404** or HTML for scripts—use a browser or raw.pixls.us. Verify with `python scripts/python/verify_nef_testing_samples.py` and optional **`--exiftool`** when ExifTool is installed.

---

## Nikon D300 (12.3 MP, 4288×2848)

**rawsamples.ch**

- http://www.rawsamples.ch/raws/nikon/d300/RAW_NIKON_D300.NEF (~15 MB)

**Imaging Resource** — index: https://www.imaging-resource.com/PRODS/D300/D300RAWINDEX.HTM

| Scene        | ISO | URL |
|-------------|-----|-----|
| Still Life  | 200 | https://www.imaging-resource.com/PRODS/D300/FULLRES/D300hSLI0200.NEF |
| Multi-Target| 400 | https://www.imaging-resource.com/PRODS/D300/FULLRES/D300hMULTII0400.NEF |
| Far-Field   | 100 | https://www.imaging-resource.com/PRODS/D300/FULLRES/D300FARI0100.NEF |

**raw.pixls.us** (CC0): https://raw.pixls.us/data/Nikon/D300/ — browse in a browser.

*Note:* Some browsers save IR downloads as `.TIFF`; rename to `.NEF` if needed.

---

## Nikon D90 (12.3 MP, 4288×2848, 12-bit NEF)

**rawsamples.ch**

- http://www.rawsamples.ch/raws/nikon/d90/RAW_NIKON_D90.NEF (~10.7 MB)

**Imaging Resource** — review: https://www.imaging-resource.com/PRODS/D90/D90A7.HTM

| Scene       | ISO | Likely URL |
|------------|-----|------------|
| Still Life | 200 | https://www.imaging-resource.com/PRODS/D90/FULLRES/D90hSLI0200.NEF |
| Still Life | 800 | https://www.imaging-resource.com/PRODS/D90/FULLRES/D90hSLI0800.NEF |

**raw.pixls.us** (CC0): https://raw.pixls.us/data/Nikon/D90/

---

## Nikon Z6 II (24.5 MP, 6048×4024)

**raw-files.com** (`camera=3`)

| Lens              | URL |
|-------------------|-----|
| Z 24-70mm f/2.8 S | https://www.raw-files.com/raw.php?lens=0&camera=3 |
| Z 70-200mm f/2.8 S| https://www.raw-files.com/raw.php?lens=2&camera=3 |
| Z 85mm f/1.8 S    | https://www.raw-files.com/raw.php?lens=11&camera=3 |
| Z MC 105mm f/2.8 S| https://www.raw-files.com/raw.php?lens=12&camera=3 |

**Imaging Resource** — overview: https://www.imaging-resource.com/PRODS/nikon-z6-ii/nikon-z6-iiA7.HTM

| ISO  | Download page (get NEF from page) |
|------|-----------------------------------|
| 100  | https://www.imaging-resource.com/cameras/nikon-z6-ii-review/samples/Z6IIhSLI000100NR0.NEF.HTM |
| 800  | https://www.imaging-resource.com/cameras/nikon-z6-ii-review/samples/Z6IIhSLI000800NR0.NEF.HTM |
| 6400 | https://www.imaging-resource.com/cameras/nikon-z6-ii-review/samples/Z6IIhSLI006400NR0.NEF.HTM |

**raw.pixls.us** (CC0): https://raw.pixls.us/data/Nikon/Z%206_2/

---

## Nikon Z8 (45.7 MP, 8256×5504, 14-bit; HE / HE★ available)

**raw-files.com** (`camera=1`)

| Lens                 | URL |
|----------------------|-----|
| Z 24-120mm f/4 S     | https://www.raw-files.com/raw.php?lens=4&camera=1 |
| Z 400mm f/4.5 VR S   | https://www.raw-files.com/raw.php?lens=7&camera=1 |
| Z 800mm f/6.3 VR S   | https://www.raw-files.com/raw.php?lens=8&camera=1 |
| Z 20mm f/1.8 S       | https://www.raw-files.com/raw.php?lens=9&camera=1 |

**DPreview** (good for High Efficiency NEFs — download original from gallery UI)

- https://www.dpreview.com/sample-galleries/3002635523/nikon-z8-pre-production-sample-gallery
- https://www.dpreview.com/samples/6534850381/nikon-z8-production-sample-gallery
- https://www.dpreview.com/sample-galleries/6045530466/nikon-z8-sample-gallery/2666876840

**Photography Life** (referrer protection — use site download, no hotlinking)

- https://photographylife.com/nikon-z8-sample-images-raws

**rawsamples.ru / Google Drive** (Z 135mm f/1.8 S Plena, ISO 64)

- https://drive.google.com/file/d/1H9_hINMMZF4ass_PwoxKogqg9I8CsVJP/view?usp=share_link
- https://drive.google.com/file/d/1ymW4L732drTX_ocMc_xVXVlZSMtJa8nR/view?usp=share_link
- https://drive.google.com/file/d/1O-_hiNeehiWSNVw0nns1v0rrP6w7D-kS/view?usp=share_link

Bulk (Yandex): https://disk.yandex.ru/d/qjej3SGzEV3rbg

---

## Quick reference

| Camera | Best direct / first try |
|--------|------------------------|
| D300   | http://www.rawsamples.ch/raws/nikon/d300/RAW_NIKON_D300.NEF |
| D90    | http://www.rawsamples.ch/raws/nikon/d90/RAW_NIKON_D90.NEF |
| Z6 II  | https://www.raw-files.com/raw.php?lens=0&camera=3 |
| Z8     | https://www.raw-files.com/raw.php?lens=4&camera=1 |

**Sources summary:** rawsamples.ch for legacy DSLRs; raw-files.com for mirrorless; Imaging Resource for ISO ladders; DPreview for Z8 HE emphasis; raw.pixls.us (CC0) as fallback — browse `/data/Nikon/` in a browser.
