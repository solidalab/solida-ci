"""PR diff'ini lokal Ollama modeline review ettirip sonucu PR'a yorum olarak yazar.

Kullanım:
    python scripts/ollama_review.py <pr-numarası> [--dry-run]

Ortam değişkenleri:
    OLLAMA_HOST       varsayılan: http://localhost:11434
    OLLAMA_MODEL      varsayılan: qwen3:14b
    OLLAMA_NUM_CTX    varsayılan: 16384
    MAX_DIFF_CHARS    varsayılan: 40000
    GH_TOKEN          gh CLI için (workflow'da github.token)
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
MAX_DIFF_CHARS = int(os.environ.get("MAX_DIFF_CHARS", "40000"))

SYSTEM_PROMPT = """Sen deneyimli bir kıdemli yazılım mühendisisin ve bir pull request'i review ediyorsun.

Yalnızca diff'te değişen satırlara odaklan. Öncelik sırası:
1. Hatalar: yanlış mantık, kırılan davranış, edge case'ler, hatalı testler
2. Güvenlik sorunları
3. Ciddi performans sorunları
4. Yanlışlıkla bırakılmış debug kodu (print, console.log, yorum satırına alınmış kod vb.)

Kurallar:
- Sadece gerçek ve somut sorunları yaz; stil, isimlendirme veya zevk meselelerini yazma.
- Her bulgu için dosya adını, ilgili satırı, sorunun ne olduğunu ve nasıl düzeltileceğini belirt.
- Emin olmadığın bir şeyi kesin bir hataymış gibi sunma.
- Sorun yoksa bunu tek cümleyle söyle; sorun uydurma.
- Yanıtı Türkçe ve Markdown olarak ver.
"""


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def ollama_chat(system: str, user: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX, "temperature": 0.2},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        return json.load(resp)["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr", help="PR numarası")
    parser.add_argument("--dry-run", action="store_true", help="Yorumu yazma, ekrana bas")
    args = parser.parse_args()

    pr = json.loads(gh("pr", "view", args.pr, "--json", "title,body"))
    diff = gh("pr", "diff", args.pr)

    if not diff.strip():
        print("Diff boş, review atlanıyor.")
        return 0

    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS]

    user_prompt = (
        f"PR başlığı: {pr['title']}\n\n"
        f"PR açıklaması:\n{pr.get('body') or '(yok)'}\n\n"
        f"Diff:\n```diff\n{diff}\n```"
    )
    review = ollama_chat(SYSTEM_PROMPT, user_prompt)

    comment = f"## 🦙 Ollama Code Review (`{OLLAMA_MODEL}`)\n\n{review}"
    if truncated:
        comment += f"\n\n> ⚠️ Diff {MAX_DIFF_CHARS} karakterden uzun olduğu için kısaltıldı; review eksik olabilir."

    if args.dry_run:
        print(comment)
    else:
        gh("pr", "comment", args.pr, "--body", comment)
        print(f"PR #{args.pr} için review yorumu yazıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
