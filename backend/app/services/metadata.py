from fractions import Fraction

from PIL import ExifTags, Image


def _decimal_coordinate(values: tuple[object, object, object], reference: str) -> float:
    degrees = float(Fraction(values[0]))
    minutes = float(Fraction(values[1]))
    seconds = float(Fraction(values[2]))
    coordinate = degrees + minutes / 60 + seconds / 3600
    return -coordinate if reference in {"S", "W"} else coordinate


def extract_gps(image: Image.Image) -> tuple[float | None, float | None]:
    """Read GPS coordinates from standard JPG EXIF metadata when available."""

    exif = image.getexif()
    if not exif:
        return None, None
    gps_info = exif.get_ifd(ExifTags.IFD.GPSInfo)
    if not gps_info:
        return None, None
    gps = {ExifTags.GPSTAGS.get(key, key): value for key, value in gps_info.items()}
    latitude_values = gps.get("GPSLatitude")
    latitude_reference = gps.get("GPSLatitudeRef")
    longitude_values = gps.get("GPSLongitude")
    longitude_reference = gps.get("GPSLongitudeRef")
    if not all((latitude_values, latitude_reference, longitude_values, longitude_reference)):
        return None, None
    return (
        round(_decimal_coordinate(latitude_values, str(latitude_reference)), 7),
        round(_decimal_coordinate(longitude_values, str(longitude_reference)), 7),
    )
