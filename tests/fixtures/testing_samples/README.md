# Nikon NEF testing samples (local corpus)

This tree holds **third-party** `.NEF` files for **D300**, **D90**, **Z6 II**, and **Z8** interoperability testing (metadata, previews, pipeline). It is **not** for personal photos.

## Intended use

- **Local / developer machine:** download, verify, point indexing or tests at this folder.
- **Redistribution:** samples from **raw.pixls.us** are **CC0**. **rawsamples.ch** files are under **CC BY-SA 2.5 (Switzerland)** — attribute and respect share-alike if you republish. Files you add from other sites may be **all rights reserved**; check each source before committing or shipping in CI artifacts.

## Populate

From the **image-scoring-backend** repo:

```text
python scripts/python/download_nef_testing_samples.py
```

Optional: `NEF_TEST_SAMPLES_ROOT` or pass the root path as the first argument.

## Verify

```text
python scripts/python/verify_nef_testing_samples.py
python scripts/python/verify_nef_testing_samples.py --exiftool
```

```text
python scripts/python/build_nef_testing_manifest.py
```

`manifest.json` in this folder records **SHA-256** and (when `exiftool` is on `PATH`) **Make**, **Model**, **BitsPerSample**, **NEFCompression**, **Compression**, **ImageSize**.

## Reference

Repo docs: `scripts/python/NEF_TESTING_SAMPLES_URLS.md`.
