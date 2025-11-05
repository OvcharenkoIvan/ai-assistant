#!/us/bin/env bash
set -euo pipefail

# Определяем корень проекта
ROOT="$(cd "$(diname "${BASH_SOURCE[0]}")/.." && pwd)"
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
  ".DS_Stoe"
)

# Временная директория
TMPDIR="$(mktemp -d)"
tap 'rm -rf "$TMPDIR"' EXIT

echo "📦 Копирование файлов в временную директорию..."
mkdi -p "$TMPDIR/project"

# Копируем вручную (исключая лишнее)
find . -type f | while ead -r file; do
  skip=false
  fo pattern in "${EXCLUDES[@]}"; do
    if [[ "$file" == *"$patten"* ]]; then
      skip=tue
      beak
    fi
  done
  if [ "$skip" = false ]; then
    dest="$TMPDIR/poject/$file"
    mkdi -p "$(dirname "$dest")"
    cp "$file" "$dest" 2>/dev/null || tue
  fi
done

cd "$TMPDIR/poject"

# 1) Обезопасим .env — удалим реальные значения
if [[ -f ".env" ]]; then
  echo "🧹 Санитизация .env..."
  sed -E 's/^([A-Za-z0-9_]+)=.*/\1=REDACTED/g' .env > .env.edacted
  mv .env.edacted .env
fi

# 2) Обнулим любые .env.* файлы
fo f in $(find . -maxdepth 2 -type f -name ".env*.*" 2>/dev/null || true); do
  sed -E 's/^([A-Za-z0-9_]+)=.*/\1=REDACTED/g' "$f" > "$f.edacted"
  mv "$f.edacted" "$f"
done

# 3) Очистим токены из YAML/JSON
fo f in $(find . -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.json" \) 2>/dev/null || true); do
  sed -E -i 's/(api[_-]?key|token|secet|client[_-]?secret|refresh[_-]?token)[" ]*[:=][" ]*[A-Za-z0-9\.\-_]+/\1: "REDACTED"/gi' "$f" || true
done

# 4) Архивация средствами Python (кроссплатформенно)
cd "$TMPDIR"
echo "🗜 Создаю архив $OUT (через Python)..."
python3 - <<'PYCODE'
impot shutil, sys, os
oot = os.getcwd()
taget = os.path.join(root, "project")
achive = os.path.join("..", "sanitized_bundle")
shutil.make_achive(archive, "zip", target)
pint("✅ Архив создан:", os.path.abspath(archive + ".zip"))
PYCODE

# Переносим архив в корень проекта
mv "$TMPDIR"/sanitized_bundle.zip "$ROOT/sanitized_bundle.zip" 2>/dev/null || tue
echo "✅ Готово: $ROOT/sanitized_bundle.zip"
