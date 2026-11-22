"""Aides géographiques (WGS84). Les coordonnées circulent en (lat, lon) dans l'API."""
from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def point(lat: float, lon: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def polygon(coords: list[tuple[float, float]]) -> WKTElement:
    """coords en (lat, lon) ; le polygone est fermé automatiquement."""
    ring = list(coords)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    wkt = ", ".join(f"{lon} {lat}" for lat, lon in ring)
    return WKTElement(f"POLYGON(({wkt}))", srid=4326)


def latlon(geom: WKBElement | WKTElement | None) -> dict | None:
    if geom is None:
        return None
    p: Point = to_shape(geom)
    return {"lat": p.y, "lon": p.x}


def geojson(geom) -> dict | None:
    return None if geom is None else mapping(to_shape(geom))


def _geog(g):
    """Convertit une géométrie (WKB/WKT) en expression SQL de type geography."""
    return func.ST_GeogFromText(f"SRID=4326;{to_shape(g).wkt}")


def distance_m(db: Session, a, b) -> float | None:
    """Distance géodésique en mètres entre deux géométries."""
    if a is None or b is None:
        return None
    return db.scalar(
        select(func.ST_Distance(_geog(a), _geog(b)))
    )


def is_inside(db: Session, polygon_geom, point_geom) -> bool | None:
    if polygon_geom is None or point_geom is None:
        return None
    # Tolérance de 25 m pour l'imprécision GPS
    return bool(
        db.scalar(select(func.ST_DWithin(_geog(polygon_geom), _geog(point_geom), 25)))
    )
