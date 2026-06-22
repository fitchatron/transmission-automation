import pytest
from utils.media import normalize

"""
first == torrent_name in DB
second == torrent_name when on complete is triggered by Transmission
"""


@pytest.mark.parametrize(
    "input_str, expected_normalized_output",
    [
        (
            "Detroiters S01E08 Dream Cruise 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "detroiterss01e08dreamcruise1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "Idle Detroiters S01E06 3rd Floor 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "idledetroiterss01e063rdfloor1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "0.0 Downloading Detroiters S01E08 Dream Cruise 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "00downloadingdetroiterss01e08dreamcruise1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "Detroiters S01E09 Husky Boys 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "detroiterss01e09huskyboys1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "0.0 Downloading Detroiters S01E06 3rd Floor 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "00downloadingdetroiterss01e063rdfloor1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "Idle Saturday.Night.Live.S51E13.Connor.Storrie.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "idlesaturdaynightlives51e13connorstorrie1080pwebh264editheztvxtomkv",
        ),
        (
            "Detroiters S01E07 Smilin Jack 1080p AMZN WEB-DL DD 2 0 H 264-Cinefeel[TGx]",
            "detroiterss01e07smilinjack1080pamznwebdldd20h264cinefeeltgx",
        ),
        (
            "Saturday.Night.Live.S51E13.Connor.Storrie.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e13connorstorrie1080pwebh264editheztvxtomkv",
        ),
        (
            "Detroiters.S02.1080p.AMZN.WEBRip.DDP2.0.x264-AJP69[rartv]",
            "detroiterss021080pamznwebripddp20x264ajp69rartv",
        ),
        (
            "Saturday.Night.Live.S51E14.Ryan.Gosling.1080p.WEB.h264-EDITH[eztvx.to]",
            "saturdaynightlives51e14ryangosling1080pwebh264editheztvxto",
        ),
        (
            "Saturday.Night.Live.S51E15.Harry.Styles.1080p.WEB.h264-EDITH[eztvx.to]",
            "saturdaynightlives51e15harrystyles1080pwebh264editheztvxto",
        ),
        (
            "Saturday.Night.Live.S51E15.Harry.Styles.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e15harrystyles1080pwebh264editheztvxtomkv",
        ),
        (
            "One Battle After Another (2025) 1080p WEBRip x264 5.1 YTS YIFY",
            "onebattleafteranother20251080pwebripx26451ytsyify",
        ),
        (
            "One Battle After Another (2025) [1080p] [WEBRip] [5.1] [YTS.MX]",
            "onebattleafteranother20251080pwebrip51ytsmx",
        ),
        (
            "Bugonia (2025) 1080p WEBRip x264 5.1 YTS YIFY",
            "bugonia20251080pwebripx26451ytsyify",
        ),
        (
            "Bugonia (2025) [1080p] [WEBRip] [5.1] [YTS.LT]",
            "bugonia20251080pwebrip51ytslt",
        ),
        (
            "Invincible.S04E02.1080p.AMZN.WEBRip.AAC5.1.10bits.x265-Rapta",
            "invincibles04e021080pamznwebripaac5110bitsx265rapta",
        ),
        (
            "Invincible - S04E02 - I'LL GIVE YOU THE GRAND TOUR.mkv",
            "invincibles04e02illgiveyouthegrandtourmkv",
        ),
        (
            "Invincible.2021.S04E03.1080p.WEB.h264-ETHEL",
            "invincible2021s04e031080pwebh264ethel",
        ),
        (
            "Invincible.2021.S04E04.1080p.WEB.h264-ETHEL[eztvx.to]",
            "invincible2021s04e041080pwebh264etheleztvxto",
        ),
        (
            "Invincible.2021.S04E04.1080p.WEB.h264-ETHEL[EZTVx.to].mkv",
            "invincible2021s04e041080pwebh264etheleztvxtomkv",
        ),
        (
            "Invincible.2021.S04E05.1080p.WEB.h264-ETHEL[eztvx.to]",
            "invincible2021s04e051080pwebh264etheleztvxto",
        ),
        (
            "Invincible.2021.S04E05.1080p.WEB.h264-ETHEL[EZTVx.to].mkv",
            "invincible2021s04e051080pwebh264etheleztvxtomkv",
        ),
        (
            "Avatar Fire and Ash 2025 1080p WEB-DL DDP5.1 x264 Early Release-TheMrG",
            "avatarfireandash20251080pwebdlddp51x264earlyreleasethemrg",
        ),
        (
            "Louis.Theroux.Inside.the.Manosphere.2026.1080p.WEB.h264-EDITH",
            "louistherouxinsidethemanosphere20261080pwebh264edith",
        ),
        (
            "Invincible 2021 S04E06 YOU LOOK HORRIBLE 1080p AMZN WEB-DL DDP5 1 H 264-FLUX[eztvx.to]",
            "invincible2021s04e06youlookhorrible1080pamznwebdlddp51h264fluxeztvxto",
        ),
        ("The.Boys.S05E01.1080p.WEB.h264-ETHEL", "theboyss05e011080pwebh264ethel"),
        (
            "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[eztvx.to]",
            "theboyss05e021080phevcx265megustaeztvxto",
        ),
        (
            "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "theboyss05e021080phevcx265megustaeztvxtomkv",
        ),
        (
            "Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[eztvx.to]",
            "saturdaynightlives51e17colmandomingo1080pwebh264editheztvxto",
        ),
        (
            "Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e17colmandomingo1080pwebh264editheztvxtomkv",
        ),
        (
            "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "theboyss05e021080phevcx265megustaeztvxtomkv",
        ),
        (
            "Invincible.2021.S04E07.1080p.WEB.h264-ETHEL",
            "invincible2021s04e071080pwebh264ethel",
        ),
        (
            "Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e17colmandomingo1080pwebh264editheztvxtomkv",
        ),
        (
            "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "theboyss05e021080phevcx265megustaeztvxtomkv",
        ),
        (
            "Saturday.Night.Live.S51E18.Olivia.Rodrigo.1080p.WEB.h264-EDITH[eztvx.to]",
            "saturdaynightlives51e18oliviarodrigo1080pwebh264editheztvxto",
        ),
        (
            "Saturday.Night.Live.S51E18.Olivia.Rodrigo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e18oliviarodrigo1080pwebh264editheztvxtomkv",
        ),
        (
            "Saturday.Night.Live.S51E17.Colman.Domingo.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "saturdaynightlives51e17colmandomingo1080pwebh264editheztvxtomkv",
        ),
        (
            "The.Boys.S05E02.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
            "theboyss05e021080phevcx265megustaeztvxtomkv",
        ),
        (
            "The Boys S05E06 Though the Heavens Fall 1080p AMZN WEB-DL DDP5 1 Atmos H 264-playWEB[eztvx.to]",
            "theboyss05e06thoughtheheavensfall1080pamznwebdlddp51atmosh264playwebeztvxto",
        ),
        (
            "Saturday.Night.Live.S51E19.Matt.Damon.1080p.HEVC.x265-MeGusta[eztvx.to]",
            "saturdaynightlives51e19mattdamon1080phevcx265megustaeztvxto",
        ),
        (
            "Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[eztvx.to]",
            "rickandmortys09e041080pwebh264editheztvxto",
        ),
        (
            "Rick.and.Morty.S09E04.1080p.WEB.h264-EDITH[EZTVx.to].mkv",
            "rickandmortys09e041080pwebh264editheztvxtomkv",
        ),
        (
            "Rick and Morty S09E05 Jer Bud 1080p AMZN WEB-DL DDP5 1 H 264-FLUX",
            "rickandmortys09e05jerbud1080pamznwebdlddp51h264flux",
        ),
    ],
)
def test_normalize(input_str, expected_normalized_output):
    assert normalize(input_str) == expected_normalized_output
