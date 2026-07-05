"""Pure-helper tests for the query-param parsing logic."""

from params import (
    clamp_quality,
    int_param,
    is_watermark_bypassed,
    resolve_fit,
    resolve_format,
)

LIST = "logos/bdgcafe.png, partners/, promos/2026-*"


class TestIsWatermarkBypassed:
    def test_exact_path(self):
        assert is_watermark_bypassed("logos/bdgcafe.png", LIST) is True
        assert is_watermark_bypassed("logos/other.png", LIST) is False

    def test_folder_prefix(self):
        assert is_watermark_bypassed("partners/acme/logo.png", LIST) is True
        assert is_watermark_bypassed("partner/acme.png", LIST) is False

    def test_wildcard_prefix(self):
        assert is_watermark_bypassed("promos/2026-summer.jpg", LIST) is True
        assert is_watermark_bypassed("promos/2025-summer.jpg", LIST) is False

    def test_tolerates_newlines_and_blanks(self):
        assert is_watermark_bypassed("a/b.jpg", "\n a/b.jpg \n\n") is True

    def test_empty_or_none_never_matches(self):
        assert is_watermark_bypassed("anything.jpg", "") is False
        assert is_watermark_bypassed("anything.jpg", None) is False

    def test_ordinary_cafe_image_not_bypassed(self):
        assert is_watermark_bypassed("cafes/abc/cover.jpg", LIST) is False


class TestIntParam:
    def test_picks_first_valid_alias(self):
        assert int_param({"width": "300"}, "width", "w") == 300
        assert int_param({"w": "250"}, "width", "w") == 250

    def test_rounds_and_rejects_nonpositive(self):
        assert int_param({"w": "199.6"}, "w") == 200
        assert int_param({"w": "0"}, "w") is None
        assert int_param({"w": "-5"}, "w") is None
        assert int_param({"w": "abc"}, "w") is None
        assert int_param({}, "w") is None


class TestResolveFit:
    def test_default_cover_when_both_dims(self):
        assert resolve_fit(300, 200, None) == "cover"

    def test_default_scale_down_otherwise(self):
        assert resolve_fit(300, None, None) == "scale-down"
        assert resolve_fit(None, None, None) == "scale-down"

    def test_explicit_fit_wins(self):
        assert resolve_fit(300, 200, "contain") == "contain"

    def test_unknown_fit_ignored(self):
        assert resolve_fit(300, 200, "bogus") == "cover"


class TestResolveFormat:
    def test_aliases(self):
        assert resolve_format("jpeg", "") == "jpeg"
        assert resolve_format("jpg", "") == "jpeg"
        assert resolve_format("png", "") == "png"
        assert resolve_format("webp", "") == "webp"

    def test_default_webp(self):
        assert resolve_format(None, "") == "webp"
        assert resolve_format("bogus", "") == "webp"

    def test_auto_negotiation_without_avif_accept(self):
        assert resolve_format("auto", "image/webp,*/*") == "webp"


class TestClampQuality:
    def test_default_and_clamp(self):
        assert clamp_quality(None) == 82
        assert clamp_quality(90) == 90
        assert clamp_quality(150) == 100
