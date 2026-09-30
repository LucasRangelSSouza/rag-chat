# Corpus contract

A corpus profile is the only place a deployment names its data. The interface, backend, and tests never hard-code a corpus name.

| Field | Meaning |
|---|---|
| `RAG_PROFILE` | Human-readable profile name shown in the interface (for example `PNCP corpus profile`) |
| `RAG_DATASET_SLUG` | Kaggle dataset `owner/slug` that holds the semantic Parquet files |
| `RAG_RELEASE` | Pinned dataset version |
| `RAG_MANIFEST_SHA256` | SHA-256 of the release manifest for that version |
| index metadata | `data_cutoff`, `table_count`, and `record_count`, written at index build time |

## Rules

1. The index is built only from Parquet files listed in the pinned release manifest, after their SHA-256 hashes match.
2. Each citation carries the dataset slug, the pinned version, the manifest hash, and the record identifier (`numero_controle_pncp` for the PNCP profile).
3. The interface shows the release version, cutoff, and record count from the index, never from static copy.
4. Changing the release means rebuilding the index and redeploying; a running service never follows a moving `latest`.
