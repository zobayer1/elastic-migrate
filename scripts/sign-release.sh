#!/usr/bin/env bash
set -euo pipefail

REPO="${ESMIGRATE_RELEASE_REPO:-zobayer1/elastic-migrate}"
SIGNING_KEY="${ESMIGRATE_SIGNING_KEY:-A76F280EEB0DF3D404CCACCD4295322A9F97C188}"
TRUSTED_TAG_SIGNERS="${ESMIGRATE_TAG_SIGNERS:-2A31D4615AE02B026F3FD8997B6577AF8F94762E A76F280EEB0DF3D404CCACCD4295322A9F97C188}"

usage() {
    echo "usage: $(basename "$0") [--dry-run] [--yes] TAG" >&2
    echo "  Verify, reproduce and sign the draft GitHub release TAG, then publish it." >&2
    exit 2
}

die() {
    echo "error: $*" >&2
    exit 1
}

dry_run=false
assume_yes=false
tag=""
while (($#)); do
    case "$1" in
        --dry-run) dry_run=true ;;
        -y | --yes) assume_yes=true ;;
        -*) usage ;;
        *)
            [[ -z "$tag" ]] || usage
            tag="$1"
            ;;
    esac
    shift
done
[[ -n "$tag" ]] || usage

for tool in gh gpg git uv sha256sum cmp; do
    command -v "$tool" > /dev/null || die "$tool is required"
done

root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "==> Checking that $tag is a draft release"
draft="$(gh release view "$tag" --repo "$REPO" --json isDraft --jq .isDraft 2> /dev/null)" ||
    die "release $tag not found in $REPO"
[[ "$draft" == "true" ]] || die "release $tag is already published"

echo "==> Verifying the tag signature"
git -C "$root" fetch --quiet --force origin "refs/tags/$tag:refs/tags/$tag"
status="$(git -C "$root" verify-tag --raw "$tag" 2>&1)" || die "tag $tag has no valid signature"
validsig="$(grep -E '^\[GNUPG:\] VALIDSIG ' <<< "$status" || true)"
[[ -n "$validsig" ]] || die "tag $tag has no valid signature"
signer="$(awk '{print $3}' <<< "$validsig")"
primary="$(awk '{print $NF}' <<< "$validsig")"
trusted=false
for fingerprint in $TRUSTED_TAG_SIGNERS; do
    [[ "$signer" == "$fingerprint" || "$primary" == "$fingerprint" ]] && trusted=true
done
$trusted || die "tag $tag is signed by $signer, which is not a trusted release key"

echo "==> Downloading and checking release assets"
gh release download "$tag" --repo "$REPO" --dir "$work/release"
compgen -G "$work/release/*.asc" > /dev/null && die "release $tag already has signatures"
(cd "$work/release" && sha256sum --check --strict SHA256SUMS)
mapfile -t artifacts < <(cd "$work/release" && ls -- *.whl *.tar.gz)
[[ "${#artifacts[@]}" -eq 2 ]] || die "expected exactly one wheel and one source archive"
for artifact in "${artifacts[@]}"; do
    gh attestation verify "$work/release/$artifact" --repo "$REPO" > /dev/null
    echo "    attestation ok: $artifact"
done

echo "==> Rebuilding $tag locally"
git clone --quiet --branch "$tag" "$root" "$work/source" 2> /dev/null
(
    cd "$work/source"
    SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" uv build --quiet \
        --build-constraints build-constraints.txt --require-hashes --out-dir "$work/local"
)
for artifact in "${artifacts[@]}"; do
    cmp --silent "$work/release/$artifact" "$work/local/$artifact" ||
        die "$artifact differs from the local build"
    echo "    reproduced: $artifact"
done

echo "==> Signing with $SIGNING_KEY"
for file in "${artifacts[@]}" SHA256SUMS; do
    gpg --yes --local-user "${SIGNING_KEY}!" --armor --detach-sign --output "$work/release/$file.asc" "$work/release/$file"
    gpg --verify "$work/release/$file.asc" "$work/release/$file" 2> /dev/null || die "signature check failed for $file"
    echo "    signed: $file"
done

if $dry_run; then
    echo "Dry run: signatures created and verified, nothing uploaded."
    exit 0
fi

if ! $assume_yes; then
    read -r -p "Upload signatures and publish release $tag? [y/N] " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]] || die "aborted, release $tag is still a draft"
fi

gh release upload "$tag" "$work/release"/*.asc --repo "$REPO"
gh release edit "$tag" --repo "$REPO" --draft=false
echo "Published $tag: https://github.com/$REPO/releases/tag/$tag"
