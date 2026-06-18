import base64
from pathlib import Path

from PIL import Image, ImageChops


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_IMAGE = PROJECT_ROOT / "icon_original.png"
ICON_FILE = PROJECT_ROOT / "icon.ico"
ICON_DATA_FILE = PROJECT_ROOT / "icon_data.py"
ICON_SIZE = 256
BLACK_TOLERANCE = 12


def crop_center_icon(image: Image.Image) -> Image.Image:
    """
    Remove bordas de fundo preto plano e retorna um recorte quadrado central.
    O bbox principal vem da diferenca contra uma imagem preta com pequena tolerancia;
    depois o recorte e expandido para quadrado sem sair dos limites originais.
    """
    rgba_image = image.convert("RGBA")
    rgb_image = rgba_image.convert("RGB")
    black_background = Image.new("RGB", rgb_image.size, (0, 0, 0))
    difference = ImageChops.difference(rgb_image, black_background)

    mask = difference.convert("L").point(
        lambda pixel: 255 if pixel > BLACK_TOLERANCE else 0
    )
    bbox = mask.getbbox()
    if not bbox:
        raise ValueError("Nao foi possivel identificar o icone dentro da imagem.")

    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    side = max(width, height)

    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    crop_left = center_x - side // 2
    crop_top = center_y - side // 2
    crop_right = crop_left + side
    crop_bottom = crop_top + side

    crop_left, crop_right = fit_range(crop_left, crop_right, rgba_image.width)
    crop_top, crop_bottom = fit_range(crop_top, crop_bottom, rgba_image.height)

    return rgba_image.crop((crop_left, crop_top, crop_right, crop_bottom))


def fit_range(start: int, end: int, limit: int) -> tuple[int, int]:
    size = end - start
    if start < 0:
        start = 0
        end = size
    if end > limit:
        end = limit
        start = limit - size
    return max(start, 0), min(end, limit)


def create_icon(source_path: Path, icon_path: Path) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"Imagem original nao encontrada: {source_path}")

    with Image.open(source_path) as image:
        cropped_icon = crop_center_icon(image)
        resized_icon = cropped_icon.resize(
            (ICON_SIZE, ICON_SIZE),
            Image.Resampling.LANCZOS,
        )
        resized_icon.save(
            icon_path,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )


def write_icon_data(icon_path: Path, output_path: Path) -> None:
    icon_base64 = base64.b64encode(icon_path.read_bytes()).decode("ascii")
    output_path.write_text(
        f'ICON_DATA_BASE64 = "{icon_base64}"\n',
        encoding="utf-8",
    )


def main() -> None:
    create_icon(SOURCE_IMAGE, ICON_FILE)
    write_icon_data(ICON_FILE, ICON_DATA_FILE)
    print(f"Gerado: {ICON_FILE}")
    print(f"Gerado: {ICON_DATA_FILE}")


if __name__ == "__main__":
    main()
