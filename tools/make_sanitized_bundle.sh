#!/usr/bin/env bash
set -euo pipefail

# Определяем корень проекта
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="sanitized_bundle.zip"

# Список исключений (папки и расширения, которые не нужно включать)
EXCLUDES=(
  "venv"
  ".git"
  "__pycache__"
  "data/uploads"
  "logs"
  "*.sqlite"
  "*.sqlite3"
  "*.db"
  "*.pyc"
  "*.log"
  "*.mp3" "*.wav" "*.m4a"
  "*.pdf" "*.png" "*.jpg" "*.jpeg" "*.webp"
  ".DS_Store"
)

# Временная директория
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "📦 Копирование файлов в временную директорию..."
mkdir -p "$TMPDIR/project"

# Копируем вручную (исключая лишнее)
find . -type f | while read -r file; do
  skip=false
  for pattern in "${EXCLUDES[@]}"; do
    if [[ "$file" == *"$pattern"* ]]; then
      skip=true
      break
    fi
  done
  if [ "$skip" = false ]; then
    dest="$TMPDIR/project/$file"
    mkdir -p "$(dirname "$dest")"
    cp "$file" "$dest" 2>/dev/null || true
  fi
done

cd "$TMPDIR/project"

# 1) Обезопасим .env — удалим реальные значения
if [[ -f ".env" ]]; then
  echo "🧹 Санитизация .env..."
  sed -E 's/^([A-Za-z0-9_]+)=.*/\1=REDACTED/g' .env > .env.redacted
  mv .env.redacted .env
fi

# 2) Обнулим любые .env.* файлы
for f in $(find . -maxdepth 2 -type f -name ".env*.*" 2>/dev/null || true); do
  sed -E 's/^([A-Za-z0-9_]+)=.*/\1=REDACTED/g' "$f" > "$f.redacted"
  mv "$f.redacted" "$f"
done

# 3) Очистим токены из YAML/JSON
for f in $(find . -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.json" \) 2>/dev/null || true); do
  sed -E -i 's/(api[_-]?key|token|secret|client[_-]?secret|refresh[_-]?token)[" ]*[:=][" ]*[A-Za-z0-9\.\-_]+/\1: "REDACTED"/gi' "$f" || true
done

# 4) Архивация средствами Python (кроссплатформенно)
cd "$TMPDIR"
echo "🗜 Создаю архив $OUT (через Python)..."
python3 - <<'PYCODE'
import shutil, sys, os
root = os.getcwd()
target = os.path.join(root, "project")
archive = os.path.join("..", "sanitized_bundle")
shutil.make_archive(archive, "zip", target)
print("✅ Архив создан:", os.path.abspath(archive + ".zip"))
PYCODE

# Переносим архив в корень проекта
mv "$TMPDIR"/sanitized_bundle.zip "$ROOT/sanitized_bundle.zip" 2>/dev/null || true
echo "✅ Готово: $ROOT/sanitized_bundle.zip"
