from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    background: str
    surface: str
    surface_alt: str
    text: str
    text_muted: str
    border: str
    control_border: str
    control_background: str
    accent: str
    accent_hover: str
    accent_soft: str
    selected_background: str
    selected_border: str
    drop_background: str
    stale_text: str
    progress_trough: str


THEMES: dict[str, Theme] = {
    "spring": Theme(
        key="spring",
        label="春",
        background="#FBF8F4",
        surface="#FFFFFF",
        surface_alt="#FDF1F2",
        text="#262322",
        text_muted="#665E5C",
        border="#CDC2BE",
        control_border="#A99D99",
        control_background="#F7F2F0",
        accent="#B45F75",
        accent_hover="#91475B",
        accent_soft="#F3DDE3",
        selected_background="#FBEFF2",
        selected_border="#D5A0AE",
        drop_background="#FEF6F5",
        stale_text="#9B4E62",
        progress_trough="#E9DFDC",
    ),
    "summer": Theme(
        key="summer",
        label="夏",
        background="#EFFBFF",
        surface="#FFFFFF",
        surface_alt="#E2F7FF",
        text="#102930",
        text_muted="#4D6971",
        border="#A9CDD7",
        control_border="#78AAB8",
        control_background="#F0FAFD",
        accent="#007FA3",
        accent_hover="#005F7B",
        accent_soft="#CDEFF8",
        selected_background="#E0F7FC",
        selected_border="#65BBCD",
        drop_background="#EEFAFD",
        stale_text="#006B88",
        progress_trough="#D2EAF1",
    ),
    "autumn": Theme(
        key="autumn",
        label="秋",
        background="#FAF7F1",
        surface="#FFFFFF",
        surface_alt="#F5EEDD",
        text="#251F19",
        text_muted="#625A51",
        border="#C3B6A2",
        control_border="#AA9B85",
        control_background="#F4F0E8",
        accent="#9A6127",
        accent_hover="#754619",
        accent_soft="#EAD9B8",
        selected_background="#F8EEDC",
        selected_border="#CBA56D",
        drop_background="#FCF6E9",
        stale_text="#865622",
        progress_trough="#E7DED0",
    ),
    "winter": Theme(
        key="winter",
        label="冬",
        background="#F7F9FB",
        surface="#FFFFFF",
        surface_alt="#EEF2F6",
        text="#1F2933",
        text_muted="#626E79",
        border="#C8D0D8",
        control_border="#9CAAB8",
        control_background="#F3F6F8",
        accent="#5B7187",
        accent_hover="#40566A",
        accent_soft="#E1E8EF",
        selected_background="#EEF3F7",
        selected_border="#AAB9C6",
        drop_background="#F5F8FA",
        stale_text="#50697D",
        progress_trough="#E0E6EB",
    ),
}

THEME_LABELS = {key: theme.label for key, theme in THEMES.items()}
THEME_VALUES = {theme.label: key for key, theme in THEMES.items()}


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["autumn"])
