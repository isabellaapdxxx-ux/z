#!/usr/bin/env bash
# Downloads the TTS + speech-recognition models from the npm registry (no Hugging Face / GitHub needed).
#   Kokoro-82M v1.0 q8 ONNX (Apache-2.0)        <- npm: kokoro-q8-shards
#   Kokoro voice style vectors (Apache-2.0)     <- npm: kokoro-local-runtime (voices/*.bin)
#   Whisper small, CTranslate2 int8 (MIT)       <- npm: @skillninja/shortmovie-telop-model-p0..p3
# usage: tools/fetch_models.sh <models dir>
set -euo pipefail
OUT=$(realpath -m "${1:?usage: fetch_models.sh <models dir>}")
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT/whisper-small"
cd "$TMP"
npm pack kokoro-q8-shards@1.0.0 kokoro-local-runtime@0.1.0 \
  @skillninja/shortmovie-telop-model-p0@1.0.0 @skillninja/shortmovie-telop-model-p1@1.0.0 \
  @skillninja/shortmovie-telop-model-p2@1.0.0 @skillninja/shortmovie-telop-model-p3@1.0.0 --silent >/dev/null
for f in *.tgz; do mkdir -p "x_${f%.tgz}"; tar -xzf "$f" -C "x_${f%.tgz}"; done
cat x_kokoro-q8-shards-1.0.0/package/kokoro-q8.part{0,1,2,3,4,5}.bin > "$OUT/kokoro-q8.onnx"
echo "fbae9257e1e05ffc727e951ef9b9c98418e6d79f1c9b6b13bd59f5c9028a1478  $OUT/kokoro-q8.onnx" | sha256sum -c
python3 - "$TMP/x_kokoro-local-runtime-0.1.0/package/voices" "$OUT/voices.bin" <<'PY'
import glob, os, sys, numpy as np
v = {os.path.basename(f)[:-4]: np.fromfile(f, np.float32).reshape(510, 1, 256) for f in sorted(glob.glob(sys.argv[1] + '/*.bin'))}
with open(sys.argv[2], 'wb') as fh:
    np.savez(fh, **v)
print(len(v), 'voices')
PY
P=x_skillninja-shortmovie-telop-model-p
cp ${P}0-1.0.0/package/{config.json,preprocessor_config.json,tokenizer.json,vocabulary.json} "$OUT/whisper-small/"
cat ${P}0-1.0.0/package/model.bin.part0 ${P}1-1.0.0/package/model.bin.part1 ${P}2-1.0.0/package/model.bin.part2 ${P}3-1.0.0/package/model.bin.part3 > "$OUT/whisper-small/model.bin"
echo "$(cat ${P}0-1.0.0/package/model.sha256 | cut -c1-64)  $OUT/whisper-small/model.bin" | sha256sum -c
echo "models ready in $OUT"
