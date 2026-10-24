# Downloads

Releases are published on [GitHub Releases](https://github.com/zobayer1/elastic-migrate/releases) only. Each release
contains the wheel, the source archive, a `SHA256SUMS` file and a detached GPG signature (`.asc`) for every file.

```{include} _generated/latest-release.md
```

## Verifying a download

Release files are signed with the maintainer's OpenPGP key. Its primary key is kept offline; releases are signed with a
dedicated signing subkey.

| Key | Fingerprint |
|---|---|
| Primary (Zobayer Hasan) | `2A31 D461 5AE0 2B02 6F3F D899 7B65 77AF 8F94 762E` |
| Signing subkey | `A76F 280E EB0D F3D4 04CC ACCD 4295 322A 9F97 C188` |

Import the public key from this site ([zobayer1.asc](_static/zobayer1.asc)) or from GitHub, and check the fingerprint:

```bash
curl -fsSL https://github.com/zobayer1.gpg | gpg --import
gpg --fingerprint 7B6577AF8F94762E
```

Verify the signature and the checksum of each file you downloaded, for example the wheel:

```bash
gpg --verify elastic_migrate-2.0.0-py3-none-any.whl.asc elastic_migrate-2.0.0-py3-none-any.whl
sha256sum --check --ignore-missing SHA256SUMS
```

Every release file also carries a GitHub build provenance attestation, which records the workflow and commit that
built it:

```bash
gh attestation verify elastic_migrate-2.0.0-py3-none-any.whl --repo zobayer1/elastic-migrate
```
