"""Gera assets/icone.ico para o PainelGBMX.exe."""
from pathlib import Path

from PIL import Image, ImageDraw

AQUI = Path(__file__).resolve().parent
LOGO = AQUI.parent / "dashboard" / "assets" / "logo_gbmx.png"
SAIDA = AQUI / "assets" / "icone.ico"
VERDE_ESCURO, VERDE_LIMAO = (0, 115, 48), (159, 198, 59)
LADO = 256


def icone_com_logo() -> Image.Image:
    base = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle([0, 0, LADO - 1, LADO - 1], radius=44, fill=VERDE_ESCURO)
    logo = Image.open(LOGO).convert("RGBA")
    logo.thumbnail((int(LADO * 0.82), int(LADO * 0.82)))
    base.alpha_composite(logo, ((LADO - logo.width) // 2, (LADO - logo.height) // 2))
    return base


def icone_desenhado() -> Image.Image:
    img = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, LADO - 1, LADO - 1], radius=44, fill=VERDE_ESCURO)
    d.polygon([(178, 48), (118, 128), (178, 208), (138, 208), (78, 128), (138, 48)], fill=VERDE_LIMAO)
    return img


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    img = icone_com_logo() if LOGO.is_file() else icone_desenhado()
    img.save(SAIDA, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Ícone gerado: {SAIDA} ({'logo oficial' if LOGO.is_file() else 'desenho padrão'})")


if __name__ == "__main__":
    main()
